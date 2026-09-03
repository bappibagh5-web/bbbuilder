import logging
from collections import defaultdict

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from pydantic import ValidationError as PydanticValidationError

from apps.documents.pdf_indexing import is_pdf_asset
from apps.processing.models import ProcessingJob
from apps.projects.audit import record_event
from apps.projects.models import Project

from .models import AnalysisRun, AnalysisTaskRun
from .prompts import (
    ANALYSIS_VERSION,
    DOCUMENT_PROMPT_VERSION,
    DOCUMENT_SYSTEM_PROMPT,
    PAGE_PROMPT_VERSION,
    PAGE_SYSTEM_PROMPT,
)
from .providers import ProviderFailure, get_analysis_provider
from .rendering import PageRenderFailure, render_page_data_url
from .schemas import DOCUMENT_SCHEMA_VERSION, PAGE_SCHEMA_VERSION, json_schema_for, validate_result

logger = logging.getLogger(__name__)


def _input_mode(page):
    if hasattr(page, "drawing_sheet"):
        return AnalysisTaskRun.InputMode.NATIVE_TEXT_VISION
    if page.has_native_text:
        return AnalysisTaskRun.InputMode.NATIVE_TEXT
    return AnalysisTaskRun.InputMode.VISION


def _eligible_pages(revision):
    if not is_pdf_asset(revision.project_file.file_asset):
        raise ValidationError("AI analysis currently supports validated PDF revisions only.")
    if not ProcessingJob.objects.filter(
        document_revision=revision,
        job_type=ProcessingJob.JobType.SOURCE_VERIFICATION,
        status=ProcessingJob.Status.SUCCEEDED,
    ).exists():
        raise ValidationError("Source verification must succeed before AI analysis.")
    if not ProcessingJob.objects.filter(
        document_revision=revision,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
        status=ProcessingJob.Status.SUCCEEDED,
    ).exists():
        raise ValidationError("PDF indexing must succeed before AI analysis.")
    pages = list(revision.pages.select_related("drawing_sheet").order_by("page_number"))
    if not pages:
        raise ValidationError("PDF indexing must produce durable pages before AI analysis.")
    if len(pages) > settings.AI_MAX_PAGES_PER_RUN:
        raise ValidationError(
            f"This revision has {len(pages)} pages; the configured analysis limit is "
            f"{settings.AI_MAX_PAGES_PER_RUN}."
        )
    return pages


def dispatch_analysis_run(run_id, *, force=False):
    from .tasks import process_analysis_run

    run = AnalysisRun.objects.get(pk=run_id)
    if run.status != AnalysisRun.Status.QUEUED:
        return False
    if run.last_dispatched_at and not force:
        return False
    try:
        result = process_analysis_run.apply_async(args=(run.pk,))
    except Exception:
        logger.exception(
            "Analysis dispatch failed; durable run remains queued.", extra={"run_id": run.pk}
        )
        return False
    AnalysisRun.objects.filter(pk=run.pk, status=AnalysisRun.Status.QUEUED).update(
        celery_task_id=result.id,
        last_dispatched_at=timezone.now(),
        dispatch_attempt_count=F("dispatch_attempt_count") + 1,
    )
    return True


def request_analysis_run(
    *, revision, requested_by, predecessor=None, audit_action="analysis.requested"
):
    pages = _eligible_pages(revision)
    if not revision.document.project.is_active or not revision.document.is_active:
        raise ValidationError("Archived projects or documents cannot start AI analysis.")
    try:
        with transaction.atomic():
            run = AnalysisRun.objects.create(
                document_revision=revision,
                requested_by=requested_by,
                predecessor=predecessor,
                provider=settings.AI_PROVIDER,
                model=settings.AI_MODEL,
                prompt_version=DOCUMENT_PROMPT_VERSION,
                schema_version=DOCUMENT_SCHEMA_VERSION,
                analysis_version=ANALYSIS_VERSION,
                input_manifest={
                    "document_revision_id": revision.pk,
                    "file_asset_id": revision.project_file.file_asset_id,
                    "checksum": revision.project_file.file_asset.checksum,
                    "page_ids": [page.pk for page in pages],
                    "page_count": len(pages),
                },
            )
            AnalysisTaskRun.objects.bulk_create(
                [
                    AnalysisTaskRun(
                        analysis_run=run,
                        document_page=page,
                        task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
                        input_mode=_input_mode(page),
                        max_attempts=settings.AI_TASK_MAX_ATTEMPTS,
                        provider=run.provider,
                        model=run.model,
                        prompt_version=PAGE_PROMPT_VERSION,
                        schema_version=PAGE_SCHEMA_VERSION,
                        input_metadata={
                            "document_page_id": page.pk,
                            "page_number": page.page_number,
                            "native_text_char_count": page.native_text_char_count,
                            "native_text_limit": settings.AI_MAX_NATIVE_TEXT_CHARS,
                            "native_text_truncated": page.native_text_char_count
                            > settings.AI_MAX_NATIVE_TEXT_CHARS,
                        },
                    )
                    for page in pages
                ]
                + [
                    AnalysisTaskRun(
                        analysis_run=run,
                        task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS,
                        input_mode=AnalysisTaskRun.InputMode.STRUCTURED_PAGE_RESULTS,
                        max_attempts=settings.AI_TASK_MAX_ATTEMPTS,
                        provider=run.provider,
                        model=run.model,
                        prompt_version=DOCUMENT_PROMPT_VERSION,
                        schema_version=DOCUMENT_SCHEMA_VERSION,
                        input_metadata={"page_task_count": len(pages)},
                    )
                ]
            )
            project = Project.objects.select_for_update().get(pk=revision.document.project_id)
            if project.status == Project.Status.DOCUMENTS_UPLOADED:
                project.status = Project.Status.AI_ANALYSIS
                project.save(update_fields=("status", "updated_at"))
                record_event(
                    organization=project.organization,
                    project=project,
                    actor=requested_by,
                    action_code="project.status_changed",
                    target=project,
                    metadata={
                        "before": Project.Status.DOCUMENTS_UPLOADED,
                        "after": Project.Status.AI_ANALYSIS,
                    },
                )
            record_event(
                organization=project.organization,
                project=project,
                actor=requested_by,
                action_code=audit_action,
                target=run,
                metadata={"document_id": revision.document_id, "document_revision_id": revision.pk},
            )
            if settings.AI_AUTO_DISPATCH:
                transaction.on_commit(lambda: dispatch_analysis_run(run.pk))
    except IntegrityError as error:
        raise ValidationError("This revision already has a queued or running analysis.") from error
    return run


def retry_analysis_run(*, run, requested_by):
    if run.status != AnalysisRun.Status.FAILED:
        raise ValidationError("Only a failed analysis run can be retried.")
    return request_analysis_run(
        revision=run.document_revision,
        requested_by=requested_by,
        predecessor=run,
        audit_action="analysis.retry_requested",
    )


def _claim_run(run_id):
    now = timezone.now()
    with transaction.atomic():
        run = AnalysisRun.objects.select_for_update().get(pk=run_id)
        if run.status in (AnalysisRun.Status.SUCCEEDED, AnalysisRun.Status.FAILED):
            return None
        if run.status == AnalysisRun.Status.RUNNING and run.lease_expires_at > now:
            return None
        run.status = AnalysisRun.Status.RUNNING
        run.started_at = run.started_at or now
        run.lease_expires_at = run.lease_until(now)
        run.failure_code = ""
        run.safe_failure_message = ""
        run.save(
            update_fields=(
                "status",
                "started_at",
                "lease_expires_at",
                "failure_code",
                "safe_failure_message",
                "updated_at",
            )
        )
    return run


def _page_payload(task):
    page = task.document_page
    sheet = getattr(page, "drawing_sheet", None)
    text = page.native_text[: settings.AI_MAX_NATIVE_TEXT_CHARS]
    return {
        "task_type": "page_analysis",
        "page": {
            "document_page_id": page.pk,
            "page_number": page.page_number,
            "page_label": page.page_label,
            "drawing_sheet_id": sheet.pk if sheet else None,
            "sheet_number": sheet.sheet_number if sheet else "",
            "sheet_title": sheet.sheet_title if sheet else "",
            "native_text": text,
            "native_text_truncated": page.native_text_char_count > len(text),
        },
    }


def _validate_evidence(task, result):
    expected_page = task.document_page
    if expected_page is None:
        allowed = {
            page.pk: page
            for page in task.analysis_run.document_revision.pages.select_related("drawing_sheet")
        }
        for candidate in result.get("candidates", []):
            for evidence in candidate["evidence"]:
                page = allowed.get(evidence["document_page_id"])
                sheet = getattr(page, "drawing_sheet", None) if page else None
                if (
                    page is None
                    or evidence["page_number"] != page.page_number
                    or evidence.get("drawing_sheet_id") not in (None, sheet.pk if sheet else None)
                ):
                    raise ProviderFailure(
                        "invalid_structured_response",
                        "The AI provider returned an invalid evidence reference.",
                    )
        return
    for candidate in result.get("candidates", []):
        for evidence in candidate["evidence"]:
            if (
                evidence["document_page_id"] != expected_page.pk
                or evidence["page_number"] != expected_page.page_number
            ):
                raise ProviderFailure(
                    "invalid_structured_response",
                    "The AI provider returned an invalid evidence reference.",
                )
            sheet = getattr(expected_page, "drawing_sheet", None)
            if evidence.get("drawing_sheet_id") not in (None, sheet.pk if sheet else None):
                raise ProviderFailure(
                    "invalid_structured_response",
                    "The AI provider returned an invalid evidence reference.",
                )


def _execute_task(task, provider, page_results):
    task.status = AnalysisTaskRun.Status.RUNNING
    task.started_at = timezone.now()
    task.attempt_count += 1
    task.save(update_fields=("status", "started_at", "attempt_count", "updated_at"))
    image = None
    render_metadata = {}
    if task.task_type == AnalysisTaskRun.TaskType.PAGE_ANALYSIS:
        payload = _page_payload(task)
        if task.input_mode in (
            AnalysisTaskRun.InputMode.VISION,
            AnalysisTaskRun.InputMode.NATIVE_TEXT_VISION,
        ):
            image, render_metadata = render_page_data_url(task.document_page)
        prompt = PAGE_SYSTEM_PROMPT
    else:
        payload = {"task_type": "document_synthesis", "page_results": page_results}
        prompt = DOCUMENT_SYSTEM_PROMPT
    result = provider.analyze(
        model=task.model,
        system_prompt=prompt,
        input_payload=payload,
        schema=json_schema_for(task.task_type),
        image_data_url=image,
    )
    validated = validate_result(task.task_type, result.structured_output)
    _validate_evidence(task, validated)
    task.status = AnalysisTaskRun.Status.SUCCEEDED
    task.finished_at = timezone.now()
    task.structured_result = validated
    task.provider_request_id = result.request_id
    task.usage_metadata = {**(result.usage or {}), **render_metadata}
    task.error_code = ""
    task.safe_error_message = ""
    task.save(
        update_fields=(
            "status",
            "finished_at",
            "structured_result",
            "provider_request_id",
            "usage_metadata",
            "error_code",
            "safe_error_message",
            "updated_at",
        )
    )
    return validated


def _queue_transient_retry(run, task, error):
    task.status = AnalysisTaskRun.Status.QUEUED
    task.started_at = None
    task.finished_at = None
    task.error_code = error.code
    task.safe_error_message = error.safe_message
    task.save(
        update_fields=(
            "status",
            "started_at",
            "finished_at",
            "error_code",
            "safe_error_message",
            "updated_at",
        )
    )
    run.status = AnalysisRun.Status.QUEUED
    run.queued_at = timezone.now()
    run.lease_expires_at = None
    run.failure_code = error.code
    run.safe_failure_message = error.safe_message
    run.save(
        update_fields=(
            "status",
            "queued_at",
            "lease_expires_at",
            "failure_code",
            "safe_failure_message",
            "updated_at",
        )
    )
    return {
        "outcome": "retry",
        "countdown": settings.AI_RETRY_BASE_SECONDS * (2 ** (task.attempt_count - 1)),
        "error_code": error.code,
    }


def execute_analysis_run(run_id):
    run = _claim_run(run_id)
    if run is None:
        return {"outcome": "noop"}
    provider = get_analysis_provider()
    page_results = []
    try:
        tasks = list(
            run.task_runs.select_related(
                "document_page__drawing_sheet",
                "document_page__document_revision__project_file__file_asset",
            ).order_by("id")
        )
        for task in tasks:
            if task.status == AnalysisTaskRun.Status.SUCCEEDED:
                if task.task_type == AnalysisTaskRun.TaskType.PAGE_ANALYSIS:
                    page_results.append(
                        {"page_id": task.document_page_id, "result": task.structured_result}
                    )
                continue
            if task.attempt_count >= task.max_attempts:
                raise ProviderFailure(
                    task.error_code or "analysis_failed",
                    task.safe_error_message or "The analysis task exhausted its retry limit.",
                )
            try:
                validated = _execute_task(task, provider, page_results)
            except ProviderFailure as error:
                if error.transient and task.attempt_count < task.max_attempts:
                    return _queue_transient_retry(run, task, error)
                raise
            if task.task_type == AnalysisTaskRun.TaskType.PAGE_ANALYSIS:
                page_results.append({"page_id": task.document_page_id, "result": validated})
        synthesis = tasks[-1]
        totals = defaultdict(int)
        for task in tasks:
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                value = task.usage_metadata.get(key)
                if isinstance(value, int):
                    totals[key] += value
        run.status = AnalysisRun.Status.SUCCEEDED
        run.finished_at = timezone.now()
        run.lease_expires_at = None
        run.result_summary = synthesis.structured_result
        run.usage_metadata = {
            **totals,
            "request_count": len(tasks),
            "vision_page_count": sum(
                task.input_mode
                in (AnalysisTaskRun.InputMode.VISION, AnalysisTaskRun.InputMode.NATIVE_TEXT_VISION)
                for task in tasks
            ),
        }
        run.save(
            update_fields=(
                "status",
                "finished_at",
                "lease_expires_at",
                "result_summary",
                "usage_metadata",
                "updated_at",
            )
        )
        record_event(
            organization=run.organization,
            project=run.project,
            actor=run.requested_by,
            action_code="analysis.completed",
            target=run,
            metadata={"document_revision_id": run.document_revision_id},
        )
        return {"outcome": "succeeded"}
    except (ProviderFailure, PageRenderFailure, PydanticValidationError) as error:
        code = getattr(error, "code", "invalid_structured_response")
        message = getattr(
            error, "safe_message", "The AI provider returned an invalid structured response."
        )
    except Exception:
        logger.exception("Unexpected analysis failure.", extra={"analysis_run_id": run.pk})
        code, message = "analysis_failed", "AI analysis could not be completed safely."
    active = run.task_runs.filter(status=AnalysisTaskRun.Status.RUNNING).first()
    if active:
        active.status = AnalysisTaskRun.Status.FAILED
        active.finished_at = timezone.now()
        active.error_code = code
        active.safe_error_message = message
        active.save(
            update_fields=(
                "status",
                "finished_at",
                "error_code",
                "safe_error_message",
                "updated_at",
            )
        )
    AnalysisRun.objects.filter(pk=run.pk).update(
        status=AnalysisRun.Status.FAILED,
        finished_at=timezone.now(),
        lease_expires_at=None,
        failure_code=code,
        safe_failure_message=message,
    )
    return {"outcome": "failed", "error_code": code}


def recover_stale_analysis_runs(*, run_ids=None, dispatch=True):
    now = timezone.now()
    recovered = []
    with transaction.atomic():
        queryset = AnalysisRun.objects.select_for_update().filter(
            Q(status=AnalysisRun.Status.RUNNING),
            Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now),
        )
        if run_ids is not None:
            queryset = queryset.filter(pk__in=run_ids)
        for run in queryset:
            run.status = AnalysisRun.Status.QUEUED
            run.queued_at = now
            run.started_at = None
            run.lease_expires_at = None
            run.celery_task_id = ""
            run.last_dispatched_at = None
            run.failure_code = AnalysisRun.ErrorCode.WORKER_LOST
            run.safe_failure_message = "A worker lease expired; analysis was safely re-queued."
            run.save(
                update_fields=(
                    "status",
                    "queued_at",
                    "started_at",
                    "lease_expires_at",
                    "celery_task_id",
                    "last_dispatched_at",
                    "failure_code",
                    "safe_failure_message",
                    "updated_at",
                )
            )
            run.task_runs.filter(status=AnalysisTaskRun.Status.RUNNING).update(
                status=AnalysisTaskRun.Status.QUEUED,
                started_at=None,
                error_code=AnalysisRun.ErrorCode.WORKER_LOST,
                safe_error_message="A worker lease expired; this task was safely re-queued.",
            )
            recovered.append(run.pk)
        if dispatch:
            for run_id in recovered:
                transaction.on_commit(
                    lambda run_id=run_id: dispatch_analysis_run(run_id, force=True)
                )
    return recovered
