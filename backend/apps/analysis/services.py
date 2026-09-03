import hashlib
import json
import logging
import re
from collections import defaultdict

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q
from django.utils import timezone
from pydantic import ValidationError as PydanticValidationError

from apps.documents.pdf_indexing import is_pdf_asset
from apps.organizations.models import Membership
from apps.organizations.services import active_membership
from apps.processing.models import ProcessingJob
from apps.projects.audit import record_event
from apps.projects.models import Project

from .models import (
    AnalysisRun,
    AnalysisTaskRun,
    ExtractedFinding,
    FindingReview,
    FindingSource,
    IntelligenceConflict,
    ProjectIntelligenceApproval,
    ProjectIntelligenceSnapshot,
    ProjectIntelligenceSnapshotEntry,
    ProjectIntelligenceSnapshotProvenance,
    ProjectIntelligenceSnapshotSource,
)
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

CONFLICT_CATEGORIES = {
    "project_fact",
    "date_deadline",
    "bid_condition",
    "responsibility",
    "permit_inspection",
    "landlord_requirement",
    "owner_third_party_item",
    "commercial",
    "submittal_closeout",
}


def _require_operator(user, organization):
    membership = active_membership(user, organization)
    if membership is None or membership.role not in {
        Membership.Role.ADMIN,
        Membership.Role.ESTIMATOR_OPERATOR,
    }:
        raise ValidationError("An active Admin or Estimator / Operator membership is required.")


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


def _stable_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _semantic_key(category, subject):
    normalized_subject = re.sub(r"[^a-z0-9]+", ".", subject.casefold()).strip(".")
    if not normalized_subject:
        normalized_subject = _stable_hash(subject)[:16]
    return f"{category}.{normalized_subject}"[:255]


def _normalized_value(category, value):
    normalized = " ".join(value.split()).casefold()
    if category == ExtractedFinding.Category.DATE_DEADLINE:
        # ISO-like values are comparable as written; ambiguous prose remains conservative text.
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:[tT ](.+))?", normalized)
        if match:
            return match.group(1) + (f"t{match.group(2)}" if match.group(2) else "")
    return normalized


def _latest_conflicts(queryset):
    return [conflict for conflict in queryset if not hasattr(conflict, "superseded_by")]


def detect_conflicts(*, analysis_run, actor=None):
    created = []
    groups = defaultdict(list)
    for finding in analysis_run.findings.all():
        if finding.category in CONFLICT_CATEGORIES:
            groups[finding.semantic_key].append(finding)
    for semantic_key, findings in groups.items():
        values = {finding.normalized_machine_value for finding in findings}
        if len(findings) < 2 or len(values) < 2:
            continue
        participant_ids = sorted(finding.pk for finding in findings)
        participant_key = _stable_hash(participant_ids)
        conflict, was_created = IntelligenceConflict.objects.get_or_create(
            analysis_run=analysis_run,
            participant_key=participant_key,
            version=1,
            defaults={
                "project": analysis_run.project,
                "semantic_key": semantic_key,
                "explanation": "Materially different values share the same semantic key.",
            },
        )
        if was_created:
            conflict.full_clean()
            conflict.findings.set(findings)
            created.append(conflict)
            if actor:
                record_event(
                    organization=analysis_run.organization,
                    project=analysis_run.project,
                    actor=actor,
                    action_code="conflict.detected",
                    target=conflict,
                    metadata={"analysis_run_id": analysis_run.pk},
                )
    return created


def materialize_findings(*, analysis_run, actor):
    _require_operator(actor, analysis_run.organization)
    if analysis_run.status != AnalysisRun.Status.SUCCEEDED:
        raise ValidationError("Only a successful analysis run can be prepared for review.")
    validated = validate_result(
        AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS, analysis_run.result_summary
    )
    with transaction.atomic():
        run = (
            AnalysisRun.objects.select_for_update()
            .select_related("document_revision__document__project__organization")
            .get(pk=analysis_run.pk)
        )
        synthesis = run.task_runs.get(
            task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS,
            status=AnalysisTaskRun.Status.SUCCEEDED,
        )
        page_tasks = {
            task.document_page_id: task
            for task in run.task_runs.filter(
                task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
                status=AnalysisTaskRun.Status.SUCCEEDED,
            ).select_related("document_page__drawing_sheet")
        }
        created_count = 0
        for candidate in validated["candidates"]:
            candidate_key = _stable_hash(candidate)
            finding, created = ExtractedFinding.objects.get_or_create(
                analysis_run=run,
                source_candidate_key=candidate_key,
                defaults={
                    "analysis_task_run": synthesis,
                    "document_revision": run.document_revision,
                    "semantic_key": _semantic_key(candidate["category"], candidate["subject"]),
                    "category": candidate["category"],
                    "subject": candidate["subject"],
                    "machine_value": candidate["value"],
                    "normalized_machine_value": _normalized_value(
                        candidate["category"], candidate["value"]
                    ),
                    "machine_support": candidate["support"],
                    "schema_version": run.schema_version,
                },
            )
            if created:
                finding.full_clean()
                created_count += 1
            for evidence in candidate["evidence"]:
                page_task = page_tasks.get(evidence["document_page_id"])
                if not page_task or page_task.document_page.page_number != evidence["page_number"]:
                    raise ValidationError("Finding evidence does not belong to the analysis run.")
                page = page_task.document_page
                sheet = getattr(page, "drawing_sheet", None)
                if evidence.get("drawing_sheet_id") not in (None, sheet.pk if sheet else None):
                    raise ValidationError("Finding evidence sheet does not belong to its page.")
                excerpt = evidence["evidence_excerpt"]
                mode = (
                    FindingSource.EvidenceMode.NATIVE_TEXT
                    if excerpt
                    else FindingSource.EvidenceMode.VISUAL
                )
                source_values = {
                    "document_page_id": page.pk,
                    "drawing_sheet_id": sheet.pk if evidence.get("drawing_sheet_id") else None,
                    "evidence_excerpt": excerpt,
                    "visual_evidence_description": evidence["visual_evidence_description"],
                    "evidence_mode": mode,
                }
                source, source_created = FindingSource.objects.get_or_create(
                    finding=finding,
                    source_key=_stable_hash(source_values),
                    defaults={
                        "document_revision": run.document_revision,
                        "document_page": page,
                        "drawing_sheet": sheet if evidence.get("drawing_sheet_id") else None,
                        "analysis_task_run": page_task,
                        "evidence_mode": mode,
                        "evidence_excerpt": excerpt,
                        "visual_evidence_description": evidence["visual_evidence_description"],
                    },
                )
                if source_created:
                    source.full_clean()
        detect_conflicts(analysis_run=run, actor=actor)
        project = Project.objects.select_for_update().get(pk=run.project.pk)
        if project.status == Project.Status.AI_ANALYSIS:
            project.status = Project.Status.HUMAN_SCOPE_REVIEW
            project.save(update_fields=("status", "updated_at"))
            record_event(
                organization=project.organization,
                project=project,
                actor=actor,
                action_code="project.status_changed",
                target=project,
                metadata={
                    "before": Project.Status.AI_ANALYSIS,
                    "after": Project.Status.HUMAN_SCOPE_REVIEW,
                },
            )
        if created_count:
            record_event(
                organization=run.organization,
                project=project,
                actor=actor,
                action_code="findings.materialized",
                target=run,
                metadata={"finding_count": created_count},
            )
    return run.findings.prefetch_related("sources", "reviews")


def review_finding(*, finding, reviewer, decision, reviewed_value="", review_note=""):
    _require_operator(reviewer, finding.analysis_run.organization)
    with transaction.atomic():
        locked = ExtractedFinding.objects.select_for_update().get(pk=finding.pk)
        previous = locked.reviews.order_by("-created_at", "-id").first()
        normalized_value = (reviewed_value or "").strip()
        normalized_note = (review_note or "").strip()
        if previous and (
            previous.decision == decision
            and previous.reviewed_value == normalized_value
            and previous.review_note == normalized_note
        ):
            return previous, False
        review = FindingReview(
            finding=locked,
            reviewer=reviewer,
            decision=decision,
            reviewed_value=normalized_value,
            review_note=normalized_note,
            supersedes=previous,
        )
        review.full_clean()
        review.save()
        action = {
            FindingReview.Decision.ACCEPTED: "finding.accepted",
            FindingReview.Decision.EDITED_ACCEPTED: "finding.edited",
            FindingReview.Decision.REJECTED: "finding.rejected",
            FindingReview.Decision.NEEDS_CLARIFICATION: "finding.needs_clarification",
        }[decision]
        record_event(
            organization=locked.analysis_run.organization,
            project=locked.analysis_run.project,
            actor=reviewer,
            action_code=action,
            target=review,
            metadata={"finding_id": locked.pk, "analysis_run_id": locked.analysis_run_id},
        )
    return review, True


def resolve_conflict(*, conflict, actor, status, resolution_note=""):
    _require_operator(actor, conflict.analysis_run.organization)
    if status not in (
        IntelligenceConflict.Status.RESOLVED,
        IntelligenceConflict.Status.DISMISSED,
    ):
        raise ValidationError("Conflict resolution must be resolved or dismissed.")
    with transaction.atomic():
        current = IntelligenceConflict.objects.select_for_update().get(pk=conflict.pk)
        if hasattr(current, "superseded_by"):
            raise ValidationError("This conflict version has already been superseded.")
        replacement = IntelligenceConflict(
            project=current.project,
            analysis_run=current.analysis_run,
            semantic_key=current.semantic_key,
            participant_key=current.participant_key,
            version=current.version + 1,
            conflict_type=current.conflict_type,
            explanation=current.explanation,
            status=status,
            resolved_by=actor,
            resolution_note=resolution_note.strip(),
            resolved_at=timezone.now(),
            supersedes=current,
        )
        replacement.full_clean()
        replacement.save()
        replacement.findings.set(current.findings.all())
        record_event(
            organization=current.analysis_run.organization,
            project=current.project,
            actor=actor,
            action_code=f"conflict.{status}",
            target=replacement,
            metadata={"supersedes_conflict_id": current.pk},
        )
    return replacement


SNAPSHOT_SCHEMA_VERSION = "project-intelligence-v1"


def _snapshot_block(code, message, count=1):
    return {"code": code, "message": message, "count": count}


def _snapshot_state(*, project, run_ids):
    selected_ids = sorted({int(run_id) for run_id in run_ids})
    blockers = []
    if project.status != Project.Status.HUMAN_SCOPE_REVIEW:
        blockers.append(
            _snapshot_block(
                "project_not_in_human_review",
                "Project must be in Human Scope Review before creating intelligence snapshots.",
            )
        )
    if not selected_ids:
        blockers.append(
            _snapshot_block("source_runs_required", "Select at least one reviewed analysis run.")
        )
        return {
            "eligible": False,
            "blockers": blockers,
            "manifest": {},
            "fingerprint": "",
            "summary_counts": {},
            "runs": [],
        }
    runs = list(
        AnalysisRun.objects.filter(pk__in=selected_ids)
        .select_related("document_revision__document__current_revision")
        .prefetch_related(
            "findings__reviews",
            "findings__sources",
            "intelligence_conflicts__findings",
        )
        .order_by("id")
    )
    if len(runs) != len(selected_ids) or any(run.project.pk != project.pk for run in runs):
        blockers.append(
            _snapshot_block("invalid_source_run", "Every selected run must belong to this project.")
        )
    if blockers:
        return {
            "eligible": False,
            "blockers": blockers,
            "manifest": {},
            "fingerprint": "",
            "summary_counts": {},
            "runs": [],
        }
    revision_ids = [run.document_revision_id for run in runs]
    if len(revision_ids) != len(set(revision_ids)):
        blockers.append(
            _snapshot_block(
                "duplicate_revision_run", "Select only one analysis run for each document revision."
            )
        )
    run_manifest = []
    approved_entries = []
    all_entries = []
    counts = {
        "runs": len(runs),
        "findings": 0,
        "accepted": 0,
        "edited_accepted": 0,
        "rejected": 0,
        "needs_clarification": 0,
        "unreviewed": 0,
        "open_conflicts": 0,
        "approved_entries": 0,
    }
    accepted_by_key = defaultdict(set)
    for run in runs:
        if run.status != AnalysisRun.Status.SUCCEEDED:
            blockers.append(
                _snapshot_block("run_not_succeeded", f"Analysis Run #{run.pk} has not succeeded.")
            )
        if run.document_revision.document.current_revision_id != run.document_revision_id:
            blockers.append(
                _snapshot_block(
                    "revision_not_current",
                    f"Analysis Run #{run.pk} targets a historical document revision.",
                )
            )
        findings = list(run.findings.all().order_by("id"))
        if not findings:
            blockers.append(
                _snapshot_block(
                    "findings_not_materialized",
                    f"Analysis Run #{run.pk} has no materialized findings.",
                )
            )
        run_entries = []
        for finding in findings:
            counts["findings"] += 1
            review = max(
                finding.reviews.all(), key=lambda item: (item.created_at, item.pk), default=None
            )
            sources = sorted(finding.sources.all(), key=lambda source: source.pk)
            if not sources:
                blockers.append(
                    _snapshot_block(
                        "missing_provenance", f"Finding #{finding.pk} has no source provenance."
                    )
                )
            if review is None:
                counts["unreviewed"] += 1
                blockers.append(
                    _snapshot_block("unreviewed", f"Finding #{finding.pk} has not been reviewed.")
                )
                continue
            counts[review.decision] += 1
            if review.decision == FindingReview.Decision.NEEDS_CLARIFICATION:
                blockers.append(
                    _snapshot_block(
                        "needs_clarification", f"Finding #{finding.pk} needs clarification."
                    )
                )
            effective_value = (
                review.reviewed_value
                if review.decision == FindingReview.Decision.EDITED_ACCEPTED
                else finding.machine_value
                if review.decision == FindingReview.Decision.ACCEPTED
                else ""
            )
            provenance = [
                {
                    "finding_source_id": source.pk,
                    "document_revision_id": source.document_revision_id,
                    "document_page_id": source.document_page_id,
                    "drawing_sheet_id": source.drawing_sheet_id,
                    "analysis_task_run_id": source.analysis_task_run_id,
                    "relation": source.relation,
                    "evidence_mode": source.evidence_mode,
                    "evidence_excerpt": source.evidence_excerpt,
                    "visual_evidence_description": source.visual_evidence_description,
                }
                for source in sources
            ]
            entry = {
                "finding_id": finding.pk,
                "finding_review_id": review.pk,
                "decision": review.decision,
                "effective_value": effective_value,
                "semantic_key": finding.semantic_key,
                "category": finding.category,
                "subject": finding.subject,
                "provenance": provenance,
            }
            run_entries.append(entry)
            all_entries.append(entry)
            if effective_value:
                accepted_by_key[finding.semantic_key].add(
                    _normalized_value(finding.category, effective_value)
                )
                approved_entries.append(entry)
        open_conflicts = [
            conflict
            for conflict in run.intelligence_conflicts.all()
            if not hasattr(conflict, "superseded_by")
            and conflict.status == IntelligenceConflict.Status.OPEN
        ]
        if open_conflicts:
            counts["open_conflicts"] += len(open_conflicts)
            blockers.append(
                _snapshot_block(
                    "open_conflict",
                    f"Analysis Run #{run.pk} has unresolved conflicts.",
                    len(open_conflicts),
                )
            )
        run_manifest.append(
            {
                "analysis_run_id": run.pk,
                "document_revision_id": run.document_revision_id,
                "document_id": run.document_revision.document_id,
                "resolved_conflict_ids": sorted(
                    conflict.pk
                    for conflict in run.intelligence_conflicts.all()
                    if not hasattr(conflict, "superseded_by")
                    and conflict.status != IntelligenceConflict.Status.OPEN
                ),
                "findings": run_entries,
            }
        )
    cross_run_conflicts = sorted(key for key, values in accepted_by_key.items() if len(values) > 1)
    if cross_run_conflicts:
        blockers.append(
            _snapshot_block(
                "cross_run_conflict",
                "Selected runs contain materially different reviewed values "
                "for the same semantic key.",
                len(cross_run_conflicts),
            )
        )
    counts["approved_entries"] = len(approved_entries)
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "project_id": project.pk,
        "source_runs": run_manifest,
        "approved_intelligence": approved_entries,
    }
    fingerprint = _stable_hash(manifest)
    return {
        "eligible": not blockers,
        "blockers": blockers,
        "manifest": manifest,
        "fingerprint": fingerprint,
        "summary_counts": counts,
        "runs": runs,
    }


def snapshot_readiness(*, project, run_ids):
    return _snapshot_state(project=project, run_ids=run_ids)


def create_intelligence_snapshot(*, project, creator, run_ids):
    _require_operator(creator, project.organization)
    with transaction.atomic():
        locked_project = Project.objects.select_for_update().get(pk=project.pk)
        state = _snapshot_state(project=locked_project, run_ids=run_ids)
        if not state["eligible"]:
            raise ValidationError(
                {"snapshot": [blocker["message"] for blocker in state["blockers"]]}
            )
        existing = ProjectIntelligenceSnapshot.objects.filter(
            project=locked_project, fingerprint=state["fingerprint"]
        ).first()
        if existing:
            return existing, False
        version = (
            ProjectIntelligenceSnapshot.objects.filter(project=locked_project).aggregate(
                value=Max("version")
            )["value"]
            or 0
        ) + 1
        snapshot = ProjectIntelligenceSnapshot(
            project=locked_project,
            version=version,
            fingerprint=state["fingerprint"],
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            manifest=state["manifest"],
            summary_counts=state["summary_counts"],
            created_by=creator,
        )
        snapshot.full_clean()
        snapshot.save()
        runs_by_id = {run.pk: run for run in state["runs"]}
        for run_data in state["manifest"]["source_runs"]:
            run = runs_by_id[run_data["analysis_run_id"]]
            source = ProjectIntelligenceSnapshotSource(
                snapshot=snapshot, analysis_run=run, document_revision=run.document_revision
            )
            source.full_clean()
            source.save()
            findings_by_id = {finding.pk: finding for finding in run.findings.all()}
            for item in run_data["findings"]:
                finding = findings_by_id[item["finding_id"]]
                review = finding.reviews.get(pk=item["finding_review_id"])
                entry = ProjectIntelligenceSnapshotEntry(
                    snapshot=snapshot,
                    snapshot_source=source,
                    finding=finding,
                    finding_review=review,
                    decision=item["decision"],
                    effective_value=item["effective_value"],
                    semantic_key=item["semantic_key"],
                    category=item["category"],
                    included_in_intelligence=bool(item["effective_value"]),
                )
                entry.full_clean()
                entry.save()
                finding_sources = {value.pk: value for value in finding.sources.all()}
                for frozen in item["provenance"]:
                    finding_source = finding_sources[frozen["finding_source_id"]]
                    provenance = ProjectIntelligenceSnapshotProvenance(
                        snapshot_entry=entry,
                        finding_source=finding_source,
                        document_revision_id=frozen["document_revision_id"],
                        document_page_id=frozen["document_page_id"],
                        drawing_sheet_id=frozen["drawing_sheet_id"],
                        analysis_task_run_id=frozen["analysis_task_run_id"],
                    )
                    provenance.full_clean()
                    provenance.save()
        record_event(
            organization=locked_project.organization,
            project=locked_project,
            actor=creator,
            action_code="intelligence_snapshot.created",
            target=snapshot,
            metadata={
                "version": version,
                "fingerprint": snapshot.fingerprint,
                **snapshot.summary_counts,
            },
        )
    return snapshot, True


def approve_intelligence_snapshot(*, snapshot, approver, approval_note=""):
    _require_operator(approver, snapshot.project.organization)
    blocked_snapshot = None
    with transaction.atomic():
        current = (
            ProjectIntelligenceSnapshot.objects.select_for_update()
            .select_related("project")
            .get(pk=snapshot.pk)
        )
        existing = ProjectIntelligenceApproval.objects.filter(snapshot=current).first()
        if existing:
            return existing, False
        run_ids = list(current.sources.values_list("analysis_run_id", flat=True))
        state = _snapshot_state(project=current.project, run_ids=run_ids)
        if not state["eligible"] or state["fingerprint"] != current.fingerprint:
            blocked_snapshot = current
        else:
            approval = ProjectIntelligenceApproval(
                project=current.project,
                snapshot=current,
                approver=approver,
                approval_note=(approval_note or "").strip(),
                readiness_result={
                    "eligible": True,
                    "fingerprint": state["fingerprint"],
                    "summary_counts": state["summary_counts"],
                },
            )
            approval.full_clean()
            approval.save()
            record_event(
                organization=current.project.organization,
                project=current.project,
                actor=approver,
                action_code="intelligence_snapshot.approved",
                target=approval,
                metadata={
                    "snapshot_id": current.pk,
                    "version": current.version,
                    "fingerprint": current.fingerprint,
                    "approval_id": approval.pk,
                },
            )
    if blocked_snapshot:
        record_event(
            organization=blocked_snapshot.project.organization,
            project=blocked_snapshot.project,
            actor=approver,
            action_code="intelligence_snapshot.approval_blocked_stale",
            target=blocked_snapshot,
            metadata={
                "version": blocked_snapshot.version,
                "fingerprint": blocked_snapshot.fingerprint,
            },
        )
        raise ValidationError(
            {"snapshot": "snapshot_stale: Create a new snapshot from the current reviewed state."}
        )
    return approval, True
