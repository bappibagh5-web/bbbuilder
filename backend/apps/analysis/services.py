import hashlib
import json
import logging
import re
from collections import defaultdict
from copy import deepcopy
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q
from django.utils import timezone
from pydantic import ValidationError as PydanticValidationError

from apps.documents.image_indexing import is_image_asset
from apps.documents.models import DocumentRevision, ProjectDocumentSelection
from apps.documents.pdf_indexing import is_pdf_asset
from apps.organizations.models import Membership
from apps.organizations.services import active_membership
from apps.processing.models import ProcessingJob
from apps.projects.audit import record_event
from apps.projects.models import Project
from apps.scope_packages.taxonomy import (
    DEMOLITION,
    DOORS_HARDWARE,
    ELECTRICAL,
    ENVIRONMENTAL,
    FIRE_PROTECTION,
    GENERAL,
    HVAC,
    LOW_VOLTAGE,
    PLUMBING,
    SPECIALTY_EQUIPMENT,
    STOREFRONT,
    scope_items_for_entry,
)

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
from .project_reconciliation import reconcile_project_set_page_results
from .prompts import (
    ANALYSIS_VERSION,
    DOCUMENT_PROMPT_VERSION,
    DOCUMENT_SYSTEM_PROMPT,
    PAGE_PROMPT_VERSION,
    PAGE_SYSTEM_PROMPT,
    PROJECT_SET_ANALYSIS_VERSION,
    PROJECT_SET_PROMPT_VERSION,
    PROJECT_SET_SYSTEM_PROMPT,
)
from .providers import ProviderFailure, get_analysis_provider
from .rendering import PageRenderFailure, render_page_data_url
from .sanitization import sanitize_provider_value
from .schemas import DOCUMENT_SCHEMA_VERSION, PAGE_SCHEMA_VERSION, json_schema_for, validate_result

logger = logging.getLogger(__name__)


class AnalysisCancellationDetected(Exception):
    pass


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
    asset = revision.project_file.file_asset
    if not (is_pdf_asset(asset) or is_image_asset(asset)):
        raise ValidationError(
            "AI analysis currently supports validated PDF and image revisions only."
        )
    if not ProcessingJob.objects.filter(
        document_revision=revision,
        job_type=ProcessingJob.JobType.SOURCE_VERIFICATION,
        status=ProcessingJob.Status.SUCCEEDED,
    ).exists():
        raise ValidationError("Source verification must succeed before AI analysis.")
    if (
        is_pdf_asset(asset)
        and not ProcessingJob.objects.filter(
            document_revision=revision,
            job_type=ProcessingJob.JobType.PDF_INDEXING,
            status=ProcessingJob.Status.SUCCEEDED,
        ).exists()
    ):
        raise ValidationError("PDF indexing must succeed before AI analysis.")
    pages = list(revision.pages.select_related("drawing_sheet").order_by("page_number"))
    if not pages:
        raise ValidationError("Document preparation must produce durable pages before AI analysis.")
    if len(pages) > settings.AI_MAX_PAGES_PER_RUN:
        raise ValidationError(
            f"This revision has {len(pages)} pages; the configured analysis limit is "
            f"{settings.AI_MAX_PAGES_PER_RUN}."
        )
    return pages


def dispatch_analysis_run(run_id, *, force=False):
    from .tasks import process_analysis_page_task

    run = AnalysisRun.objects.get(pk=run_id)
    if run.status != AnalysisRun.Status.QUEUED:
        return False
    if run.last_dispatched_at and not force:
        return False
    page_tasks = list(
        run.task_runs.filter(
            task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
            status=AnalysisTaskRun.Status.QUEUED,
        ).values_list("pk", flat=True)
    )
    try:
        results = [
            process_analysis_page_task.apply_async(args=(task_id,)) for task_id in page_tasks
        ]
    except Exception:
        logger.exception(
            "Analysis dispatch failed; durable run remains queued.", extra={"run_id": run.pk}
        )
        return False
    AnalysisRun.objects.filter(pk=run.pk, status=AnalysisRun.Status.QUEUED).update(
        celery_task_id=results[0].id if results else "",
        last_dispatched_at=timezone.now(),
        dispatch_attempt_count=F("dispatch_attempt_count") + 1,
    )
    if not page_tasks:
        dispatch_analysis_synthesis(run.pk)
    return True


def cancel_analysis_run(*, run, actor):
    """Cancel outstanding work while preserving every durable successful result."""
    _require_operator(actor, run.organization)
    now = timezone.now()
    with transaction.atomic():
        locked = AnalysisRun.objects.select_for_update().get(pk=run.pk)
        if locked.status == AnalysisRun.Status.CANCELLED:
            return locked, False
        if locked.status not in (AnalysisRun.Status.QUEUED, AnalysisRun.Status.RUNNING):
            raise ValidationError("Only queued or running analysis can be cancelled.")
        locked.task_runs.filter(
            status__in=(AnalysisTaskRun.Status.QUEUED, AnalysisTaskRun.Status.RUNNING)
        ).update(
            status=AnalysisTaskRun.Status.CANCELLED,
            finished_at=now,
            error_code=AnalysisRun.ErrorCode.ANALYSIS_CANCELLED,
            safe_error_message="AI analysis was cancelled by an authorized user.",
        )
        locked.status = AnalysisRun.Status.CANCELLED
        locked.finished_at = now
        locked.lease_expires_at = None
        locked.failure_code = AnalysisRun.ErrorCode.ANALYSIS_CANCELLED
        locked.safe_failure_message = "AI analysis was cancelled by an authorized user."
        locked.save(
            update_fields=(
                "status",
                "finished_at",
                "lease_expires_at",
                "failure_code",
                "safe_failure_message",
                "updated_at",
            )
        )
        record_event(
            organization=locked.organization,
            project=locked.project,
            actor=actor,
            action_code="analysis.cancelled",
            target=locked,
            metadata={"document_revision_id": locked.document_revision_id},
        )
    return locked, True


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
                run_kind=AnalysisRun.RunKind.DOCUMENT,
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
            page_tasks = []
            for page in pages:
                reusable = None
                if predecessor is not None:
                    reusable = (
                        AnalysisTaskRun.objects.filter(
                            analysis_run__document_revision=revision,
                            analysis_run__analysis_version=run.analysis_version,
                            document_page=page,
                            task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
                            input_mode=_input_mode(page),
                            status=AnalysisTaskRun.Status.SUCCEEDED,
                            provider=run.provider,
                            model=run.model,
                            prompt_version=PAGE_PROMPT_VERSION,
                            schema_version=PAGE_SCHEMA_VERSION,
                        )
                        .order_by("-finished_at", "-id")
                        .first()
                    )
                task = AnalysisTaskRun(
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
                if reusable:
                    task.status = AnalysisTaskRun.Status.SUCCEEDED
                    task.reused_from = reusable
                    task.structured_result = reusable.structured_result
                    task.provider_request_id = reusable.provider_request_id
                    task.usage_metadata = {"reused": True, "source_task_id": reusable.pk}
                    task.started_at = task.queued_at
                    task.finished_at = task.queued_at
                page_tasks.append(task)
            AnalysisTaskRun.objects.bulk_create(
                page_tasks
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


def _source_priority(document):
    filename = document.current_revision.source_filename.lower()
    searchable = f"{document.title} {filename}".lower()
    if document.category == document.Category.NARRATIVE or any(
        token in searchable for token in ("ifc", "rfi", "narrative")
    ):
        return "project_authoritative"
    if any(token in filename for token in ("shop", "quote", "quotation")):
        return "project_supporting"
    return "generic_supporting"


def request_project_set_analysis_run(*, project, requested_by):
    selections = list(
        ProjectDocumentSelection.objects.filter(
            project=project, is_included=True, document__is_active=True
        )
        .select_related("document__current_revision__project_file__file_asset", "selected_revision")
        .prefetch_related("selected_revision__pages__drawing_sheet")
        .order_by("document__category", "document__discipline", "document_id")
    )
    if not project.is_active:
        raise ValidationError("Archived projects cannot start project-wide review.")
    if not selections:
        raise ValidationError("Select at least one prepared document for project-wide review.")
    if any(item.selected_revision_id != item.document.current_revision_id for item in selections):
        raise ValidationError("Every selected document must still reference its current revision.")
    pages = [page for item in selections for page in item.selected_revision.pages.all()]
    if not pages or len(pages) > settings.AI_MAX_PAGES_PER_RUN:
        raise ValidationError(
            f"The selected set must contain 1 to {settings.AI_MAX_PAGES_PER_RUN} prepared pages."
        )
    manifest_documents = [
        {
            "document_id": item.document_id,
            "document_revision_id": item.selected_revision_id,
            "title": item.document.title,
            "category": item.document.category,
            "discipline": item.document.discipline,
            "source_priority": _source_priority(item.document),
            "page_ids": [page.pk for page in item.selected_revision.pages.all()],
        }
        for item in selections
    ]
    anchor = selections[0].selected_revision
    document_manifest_by_id = {item["document_id"]: item for item in manifest_documents}
    try:
        with transaction.atomic():
            run = AnalysisRun.objects.create(
                document_revision=anchor,
                project_context=project,
                run_kind=AnalysisRun.RunKind.PROJECT_SET,
                requested_by=requested_by,
                provider=settings.AI_PROVIDER,
                model=settings.AI_MODEL,
                prompt_version=PROJECT_SET_PROMPT_VERSION,
                schema_version=DOCUMENT_SCHEMA_VERSION,
                analysis_version=PROJECT_SET_ANALYSIS_VERSION,
                input_manifest={
                    "project_id": project.pk,
                    "document_revision_ids": [item.selected_revision_id for item in selections],
                    "page_ids": [page.pk for page in pages],
                    "page_count": len(pages),
                    "documents": manifest_documents,
                    "responsibility_labels": [
                        "Supply & Install",
                        "Install Only",
                        "Owner Supplied",
                        "Landlord Supplied",
                        "Existing to Remain",
                        "Relocate-Reuse",
                        "By Others",
                        "Unclear",
                    ],
                    "trade_taxonomy": [
                        item.label
                        for item in (
                            HVAC,
                            PLUMBING,
                            FIRE_PROTECTION,
                            ELECTRICAL,
                            LOW_VOLTAGE,
                            DEMOLITION,
                            ENVIRONMENTAL,
                            STOREFRONT,
                            DOORS_HARDWARE,
                            SPECIALTY_EQUIPMENT,
                            GENERAL,
                        )
                    ],
                },
            )
            page_tasks = []
            for page in pages:
                reusable = (
                    AnalysisTaskRun.objects.filter(
                        document_page=page,
                        analysis_run__analysis_version__in=(
                            ANALYSIS_VERSION,
                            PROJECT_SET_ANALYSIS_VERSION,
                        ),
                        task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
                        input_mode=_input_mode(page),
                        status=AnalysisTaskRun.Status.SUCCEEDED,
                        provider=run.provider,
                        model=run.model,
                        prompt_version=PAGE_PROMPT_VERSION,
                        schema_version=PAGE_SCHEMA_VERSION,
                    )
                    .order_by("-finished_at", "-id")
                    .first()
                )
                task = AnalysisTaskRun(
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
                        "document_id": page.document_revision.document_id,
                        "document_revision_id": page.document_revision_id,
                        "document_page_id": page.pk,
                        "page_number": page.page_number,
                        "document_type": page.document_revision.document.category,
                        "discipline": page.document_revision.document.discipline,
                        "source_priority": document_manifest_by_id[
                            page.document_revision.document_id
                        ]["source_priority"],
                    },
                )
                if reusable:
                    task.status = AnalysisTaskRun.Status.SUCCEEDED
                    task.reused_from = reusable
                    task.structured_result = reusable.structured_result
                    task.provider_request_id = reusable.provider_request_id
                    task.usage_metadata = {"reused": True, "source_task_id": reusable.pk}
                    task.started_at = task.queued_at
                    task.finished_at = task.queued_at
                page_tasks.append(task)
            AnalysisTaskRun.objects.bulk_create(
                page_tasks
                + [
                    AnalysisTaskRun(
                        analysis_run=run,
                        task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS,
                        input_mode=AnalysisTaskRun.InputMode.STRUCTURED_PAGE_RESULTS,
                        max_attempts=settings.AI_TASK_MAX_ATTEMPTS,
                        provider=run.provider,
                        model=run.model,
                        prompt_version=PROJECT_SET_PROMPT_VERSION,
                        schema_version=DOCUMENT_SCHEMA_VERSION,
                        input_metadata={"page_task_count": len(pages)},
                    )
                ]
            )
            record_event(
                organization=project.organization,
                project=project,
                actor=requested_by,
                action_code="project_set_analysis.requested",
                target=run,
                metadata={"document_count": len(selections), "page_count": len(pages)},
            )
            if settings.AI_AUTO_DISPATCH:
                transaction.on_commit(lambda: dispatch_analysis_run(run.pk))
    except IntegrityError as error:
        raise ValidationError("This project already has an active project-wide review.") from error
    return run


RECONCILIATION_ANALYSIS_VERSION = "m2-project-set-reconciliation.v3"
RECONCILIATION_PROVIDER = "deterministic_reconciliation"


def materialize_reconciled_project_set_run(*, source_run, actor):
    """Create one append-only deterministic successor from saved page results."""
    _require_operator(actor, source_run.organization)
    if source_run.run_kind != AnalysisRun.RunKind.PROJECT_SET:
        raise ValidationError("Only a project-set review can be reconciled.")
    if source_run.status != AnalysisRun.Status.SUCCEEDED:
        raise ValidationError("Only a successful project-set review can be reconciled.")
    page_tasks = list(
        source_run.task_runs.filter(task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS)
        .select_related("document_page")
        .order_by("document_page_id", "id")
    )
    if not page_tasks or any(
        task.status != AnalysisTaskRun.Status.SUCCEEDED for task in page_tasks
    ):
        raise ValidationError("Every saved page result must be successful before reconciliation.")
    reconciliation = reconcile_project_set_page_results(source_run)
    document_count = len(source_run.input_manifest.get("documents", []))
    result_summary = {
        "document_type_candidate": "Project estimating document set",
        "document_summary": (
            f"Deterministic reconciliation of {document_count} documents and "
            f"{len(page_tasks)} prepared pages/slides."
        ),
        "candidates": reconciliation["candidates"],
        "unresolved_questions": list(
            (source_run.result_summary or {}).get("unresolved_questions", [])
        )[:100],
    }
    validated_result = validate_result(AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS, result_summary)
    now = timezone.now()
    with transaction.atomic():
        existing = AnalysisRun.objects.filter(
            predecessor=source_run,
            analysis_version=RECONCILIATION_ANALYSIS_VERSION,
        ).first()
        if existing:
            if existing.status != AnalysisRun.Status.SUCCEEDED:
                raise ValidationError("The existing reconciled successor is not successful.")
            successor = existing
            created = False
        else:
            successor = AnalysisRun(
                document_revision=source_run.document_revision,
                project_context=source_run.project_context,
                run_kind=AnalysisRun.RunKind.PROJECT_SET,
                requested_by=actor,
                predecessor=source_run,
                status=AnalysisRun.Status.SUCCEEDED,
                provider=RECONCILIATION_PROVIDER,
                model="saved-page-results",
                prompt_version=source_run.prompt_version,
                schema_version=source_run.schema_version,
                analysis_version=RECONCILIATION_ANALYSIS_VERSION,
                input_manifest={
                    **deepcopy(source_run.input_manifest),
                    "source_analysis_run_id": source_run.pk,
                    "reconciliation_version": RECONCILIATION_ANALYSIS_VERSION,
                },
                result_summary=validated_result,
                usage_metadata={
                    "provider_requests": 0,
                    "source_analysis_run_id": source_run.pk,
                    "reconciliation": {
                        "source_candidate_count": reconciliation["source_candidate_count"],
                        "consolidated_finding_count": reconciliation["consolidated_finding_count"],
                        "source_reference_count": reconciliation["source_reference_count"],
                        "provenance_reference_count": reconciliation["provenance_reference_count"],
                        "dispositions": reconciliation["dispositions"],
                        "omissions": reconciliation["omissions"],
                        "coverage": reconciliation["coverage"],
                        "finding_trades": {
                            _stable_hash(item["candidate"]): item["trade"]
                            for item in reconciliation["items"]
                        },
                    },
                },
                queued_at=now,
                started_at=now,
                finished_at=now,
            )
            successor.full_clean()
            successor.save()
            successor_tasks = []
            for source_task in page_tasks:
                task = AnalysisTaskRun(
                    analysis_run=successor,
                    document_page=source_task.document_page,
                    task_type=source_task.task_type,
                    input_mode=source_task.input_mode,
                    status=AnalysisTaskRun.Status.SUCCEEDED,
                    attempt_count=0,
                    max_attempts=source_task.max_attempts,
                    provider=source_task.provider,
                    model=source_task.model,
                    prompt_version=source_task.prompt_version,
                    schema_version=source_task.schema_version,
                    input_metadata=deepcopy(source_task.input_metadata),
                    structured_result=deepcopy(source_task.structured_result),
                    usage_metadata={"reused": True, "source_task_id": source_task.pk},
                    reused_from=source_task,
                    queued_at=now,
                    started_at=now,
                    finished_at=now,
                )
                task.full_clean()
                successor_tasks.append(task)
            AnalysisTaskRun.objects.bulk_create(successor_tasks)
            synthesis = AnalysisTaskRun(
                analysis_run=successor,
                task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS,
                input_mode=AnalysisTaskRun.InputMode.STRUCTURED_PAGE_RESULTS,
                status=AnalysisTaskRun.Status.SUCCEEDED,
                attempt_count=0,
                max_attempts=source_run.task_runs.get(
                    task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS
                ).max_attempts,
                provider=RECONCILIATION_PROVIDER,
                model="saved-page-results",
                prompt_version=source_run.prompt_version,
                schema_version=source_run.schema_version,
                input_metadata={
                    "page_task_count": len(page_tasks),
                    "source_analysis_run_id": source_run.pk,
                },
                structured_result=validated_result,
                usage_metadata=deepcopy(successor.usage_metadata["reconciliation"]),
                queued_at=now,
                started_at=now,
                finished_at=now,
            )
            synthesis.full_clean()
            synthesis.save()
            record_event(
                organization=successor.organization,
                project=successor.project,
                actor=actor,
                action_code="project_set_analysis.reconciled",
                target=successor,
                metadata={
                    "source_analysis_run_id": source_run.pk,
                    "finding_candidate_count": reconciliation["consolidated_finding_count"],
                    "provider_requests": 0,
                },
            )
            created = True
        findings = materialize_findings(analysis_run=successor, actor=actor)
    return successor, findings, reconciliation, created


def retry_analysis_run(*, run, requested_by):
    if run.status not in (AnalysisRun.Status.FAILED, AnalysisRun.Status.CANCELLED):
        raise ValidationError("Only a failed or cancelled analysis run can be retried.")
    if run.run_kind == AnalysisRun.RunKind.PROJECT_SET:
        raise ValidationError(
            "Project-wide reviews use the current estimating set. Start a new explicit review."
        )
    return request_analysis_run(
        revision=run.document_revision,
        requested_by=requested_by,
        predecessor=run,
        audit_action="analysis.retry_requested",
    )


def _claim_task(task_id, expected_type):
    now = timezone.now()
    with transaction.atomic():
        task = (
            AnalysisTaskRun.objects.select_for_update()
            .select_related("analysis_run")
            .get(pk=task_id)
        )
        run = AnalysisRun.objects.select_for_update().get(pk=task.analysis_run_id)
        claimable = task.status == AnalysisTaskRun.Status.QUEUED
        if task.task_type != expected_type or not claimable:
            return None
        if run.status not in (AnalysisRun.Status.QUEUED, AnalysisRun.Status.RUNNING):
            return None
        task.status = AnalysisTaskRun.Status.RUNNING
        task.started_at = now
        task.attempt_count += 1
        task.save(update_fields=("status", "started_at", "attempt_count", "updated_at"))
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
    return AnalysisTaskRun.objects.select_related(
        "analysis_run",
        "document_page__drawing_sheet",
        "document_page__document_revision__project_file__file_asset",
    ).get(pk=task_id)


def _claim_run(run_id):
    now = timezone.now()
    with transaction.atomic():
        run = AnalysisRun.objects.select_for_update().get(pk=run_id)
        if run.status in (
            AnalysisRun.Status.SUCCEEDED,
            AnalysisRun.Status.FAILED,
            AnalysisRun.Status.CANCELLED,
        ):
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
    payload = {
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
    if task.analysis_run.run_kind == AnalysisRun.RunKind.PROJECT_SET:
        document = page.document_revision.document
        manifest_document = next(
            (
                item
                for item in task.analysis_run.input_manifest.get("documents", [])
                if item["document_id"] == document.pk
            ),
            {},
        )
        payload["project_context"] = {
            "document_id": document.pk,
            "document_revision_id": page.document_revision_id,
            "document_title": document.title,
            "document_type": document.category,
            "discipline": document.discipline,
            "source_priority": manifest_document.get("source_priority", "generic_supporting"),
            "responsibility_labels": task.analysis_run.input_manifest.get(
                "responsibility_labels", []
            ),
            "trade_taxonomy": task.analysis_run.input_manifest.get("trade_taxonomy", []),
        }
    return payload


def _validate_evidence(task, result):
    expected_page = task.document_page
    if expected_page is None:
        allowed = {
            page_task.document_page_id: page_task.document_page
            for page_task in task.analysis_run.task_runs.filter(
                task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS
            ).select_related("document_page__drawing_sheet")
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


def _filter_synthesis_evidence(task, result):
    """Keep only evidence that is grounded in an exact indexed revision page."""
    pages = {
        page_task.document_page_id: page_task.document_page
        for page_task in task.analysis_run.task_runs.filter(
            task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS
        ).select_related("document_page__drawing_sheet")
    }
    page_tasks = {
        page_task.document_page_id: page_task
        for page_task in task.analysis_run.task_runs.filter(
            task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
            status=AnalysisTaskRun.Status.SUCCEEDED,
        )
    }
    candidates = []
    counts = {"accepted": 0, "recovered_whitespace": 0, "rejected": 0, "skipped": 0}
    for candidate in result.get("candidates", []):
        valid_evidence = []
        for evidence in candidate["evidence"]:
            page = pages.get(evidence["document_page_id"])
            page_task = page_tasks.get(evidence["document_page_id"])
            sheet = getattr(page, "drawing_sheet", None) if page else None
            actual_sheet_id = sheet.pk if sheet else None
            actual_sheet_number = sheet.sheet_number if sheet else ""
            coordinates_valid = (
                page is not None
                and page_task is not None
                and evidence["page_number"] == page.page_number
                and evidence.get("drawing_sheet_id") in (None, actual_sheet_id)
                and evidence.get("sheet_number", "") in ("", actual_sheet_number)
            )
            if not coordinates_valid:
                counts["rejected"] += 1
                continue
            excerpt = evidence.get("evidence_excerpt", "")
            if excerpt:
                grounded = _grounded_excerpt(excerpt, page.native_text)
                if not grounded:
                    counts["rejected"] += 1
                    continue
                exact_excerpt, method = grounded
                if method == "whitespace":
                    evidence = {**evidence, "evidence_excerpt": exact_excerpt}
                    counts["recovered_whitespace"] += 1
                else:
                    counts["accepted"] += 1
            elif evidence.get("visual_evidence_description") and page_task.input_mode in (
                AnalysisTaskRun.InputMode.VISION,
                AnalysisTaskRun.InputMode.NATIVE_TEXT_VISION,
            ):
                counts["accepted"] += 1
            else:
                counts["rejected"] += 1
                continue
            valid_evidence.append(evidence)
        if valid_evidence:
            candidates.append({**candidate, "evidence": valid_evidence})
        else:
            counts["skipped"] += 1
    return {**result, "candidates": candidates}, counts


def _execute_task(task, provider, page_results):
    if task.status != AnalysisTaskRun.Status.RUNNING:
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
        prompt = (
            PROJECT_SET_SYSTEM_PROMPT
            if task.analysis_run.run_kind == AnalysisRun.RunKind.PROJECT_SET
            else DOCUMENT_SYSTEM_PROMPT
        )
    result = provider.analyze(
        model=task.model,
        system_prompt=prompt,
        input_payload=payload,
        schema=json_schema_for(task.task_type),
        image_data_url=image,
    )
    task.provider_request_id = sanitize_provider_value(result.request_id)
    task.usage_metadata = {
        **sanitize_provider_value(result.usage or {}),
        **render_metadata,
    }
    task.save(update_fields=("provider_request_id", "usage_metadata", "updated_at"))
    sanitized_output = sanitize_provider_value(result.structured_output)
    validated = validate_result(task.task_type, sanitized_output)
    if task.task_type == AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS:
        validated, evidence_counts = _filter_synthesis_evidence(task, validated)
        if task.analysis_run.run_kind == AnalysisRun.RunKind.PROJECT_SET:
            reconciliation = reconcile_project_set_page_results(task.analysis_run)
            page_candidates = reconciliation["candidates"]
            identities = {
                (
                    candidate["category"],
                    _semantic_key(candidate["category"], candidate["subject"]),
                    _normalized_value(candidate["category"], candidate["value"]),
                )
                for candidate in page_candidates
            }
            additive = []
            for candidate in validated["candidates"]:
                identity = (
                    candidate["category"],
                    _semantic_key(candidate["category"], candidate["subject"]),
                    _normalized_value(candidate["category"], candidate["value"]),
                )
                if identity not in identities:
                    additive.append(candidate)
                    identities.add(identity)
            validated = {**validated, "candidates": page_candidates + additive}
            task.usage_metadata["project_reconciliation"] = {
                "dispositions": reconciliation["dispositions"],
                "coverage": reconciliation["coverage"],
                "source_candidate_count": reconciliation["source_candidate_count"],
                "source_reference_count": reconciliation["source_reference_count"],
                "grounded_candidate_count": reconciliation["grounded_candidate_count"],
                "consolidated_finding_count": reconciliation["consolidated_finding_count"],
                "additive_synthesis_count": len(additive),
                "provenance_reference_count": reconciliation["provenance_reference_count"],
            }
        task.usage_metadata = {
            **task.usage_metadata,
            "synthesis_evidence_filter": evidence_counts,
        }
    else:
        _validate_evidence(task, validated)
    if AnalysisRun.objects.filter(
        pk=task.analysis_run_id, status=AnalysisRun.Status.CANCELLED
    ).exists():
        raise AnalysisCancellationDetected
    task.status = AnalysisTaskRun.Status.SUCCEEDED
    task.finished_at = timezone.now()
    task.structured_result = validated
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


def _finish_run(run):
    tasks = list(run.task_runs.order_by("id"))
    synthesis = next(
        task for task in tasks if task.task_type == AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS
    )
    totals = defaultdict(int)
    for task in tasks:
        if task.reused_from_id:
            continue
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
        "request_count": sum(
            task.status == AnalysisTaskRun.Status.SUCCEEDED and not task.reused_from_id
            for task in tasks
        ),
        "reused_page_count": sum(bool(task.reused_from_id) for task in tasks),
        "vision_page_count": sum(
            task.input_mode
            in (AnalysisTaskRun.InputMode.VISION, AnalysisTaskRun.InputMode.NATIVE_TEXT_VISION)
            for task in tasks
            if not task.reused_from_id
        ),
    }
    if run.run_kind == AnalysisRun.RunKind.PROJECT_SET:
        represented = {item.get("discipline") for item in run.input_manifest.get("documents", [])}
        covered_trades = set()
        unmapped_candidate_count = 0
        for index, candidate in enumerate(
            synthesis.structured_result.get("candidates", []), start=1
        ):
            entry = SimpleNamespace(
                pk=f"project-set-{index}",
                finding=SimpleNamespace(subject=candidate.get("subject", "")),
                effective_value=str(candidate.get("value", "")),
            )
            mapped = scope_items_for_entry(entry)
            if mapped:
                covered_trades.update(item.trade.label for item in mapped)
            else:
                unmapped_candidate_count += 1
        run.usage_metadata["coverage"] = {
            "represented_disciplines": sorted(value for value in represented if value),
            "coordination_questions": len(
                synthesis.structured_result.get("unresolved_questions", [])
            ),
            "covered_trade_packages": sorted(covered_trades),
            "unmapped_candidate_count": unmapped_candidate_count,
            "scope_taxonomy_check": "complete",
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


def execute_analysis_task(task_id, task_type):
    existing = AnalysisTaskRun.objects.select_related("analysis_run").get(pk=task_id)
    if (
        task_type == AnalysisTaskRun.TaskType.PAGE_ANALYSIS
        and existing.status == AnalysisTaskRun.Status.SUCCEEDED
    ):
        dispatched = dispatch_analysis_synthesis(existing.analysis_run_id)
        return {"outcome": "succeeded" if dispatched else "noop"}
    task = _claim_task(task_id, task_type)
    if task is None:
        return {"outcome": "noop"}
    run = task.analysis_run
    page_results = [
        {
            "document_id": item.document_page.document_revision.document_id,
            "document_revision_id": item.document_page.document_revision_id,
            "page_id": item.document_page_id,
            "source_context": item.input_metadata,
            "result": item.structured_result,
        }
        for item in run.task_runs.filter(
            task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS,
            status=AnalysisTaskRun.Status.SUCCEEDED,
        )
        .select_related("document_page__document_revision")
        .order_by("document_page__document_revision_id", "document_page__page_number")
    ]
    if (
        task_type == AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS
        and run.task_runs.filter(task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS)
        .exclude(status=AnalysisTaskRun.Status.SUCCEEDED)
        .exists()
    ):
        task.status = AnalysisTaskRun.Status.QUEUED
        task.started_at = None
        task.save(update_fields=("status", "started_at", "updated_at"))
        return {"outcome": "waiting"}
    try:
        _execute_task(task, get_analysis_provider(), page_results)
    except AnalysisCancellationDetected:
        return {"outcome": "cancelled"}
    except ProviderFailure as error:
        if error.transient and task.attempt_count < task.max_attempts:
            task.status = AnalysisTaskRun.Status.QUEUED
            task.started_at = None
            task.error_code = error.code
            task.safe_error_message = error.safe_message
            task.save(
                update_fields=(
                    "status",
                    "started_at",
                    "error_code",
                    "safe_error_message",
                    "updated_at",
                )
            )
            return {
                "outcome": "retry",
                "countdown": min(
                    settings.AI_RETRY_MAX_SECONDS,
                    settings.AI_RETRY_BASE_SECONDS * (2 ** (task.attempt_count - 1)),
                ),
                "error_code": error.code,
            }
        code, message = error.code, error.safe_message
    except (PageRenderFailure, PydanticValidationError) as error:
        code = getattr(error, "code", "invalid_structured_response")
        message = getattr(
            error, "safe_message", "The AI provider returned an invalid structured response."
        )
    except Exception:
        logger.exception("Unexpected analysis task failure.", extra={"analysis_task_id": task.pk})
        code, message = "analysis_failed", "AI analysis could not be completed safely."
    else:
        if task_type == AnalysisTaskRun.TaskType.PAGE_ANALYSIS:
            if not dispatch_analysis_synthesis(run.pk):
                refreshed = AnalysisRun.objects.get(pk=run.pk)
                if (
                    refreshed.status in (AnalysisRun.Status.QUEUED, AnalysisRun.Status.RUNNING)
                    and not refreshed.task_runs.filter(
                        task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS
                    )
                    .exclude(status=AnalysisTaskRun.Status.SUCCEEDED)
                    .exists()
                ):
                    return {"outcome": "retry_dispatch", "countdown": 5}
        else:
            _finish_run(AnalysisRun.objects.get(pk=run.pk))
        return {"outcome": "succeeded"}
    task.status = AnalysisTaskRun.Status.FAILED
    task.finished_at = timezone.now()
    task.error_code = code
    task.safe_error_message = message
    task.save(
        update_fields=("status", "finished_at", "error_code", "safe_error_message", "updated_at")
    )
    AnalysisRun.objects.filter(pk=run.pk).update(
        status=AnalysisRun.Status.FAILED,
        finished_at=timezone.now(),
        lease_expires_at=None,
        failure_code=code,
        safe_failure_message=message,
    )
    return {"outcome": "failed", "error_code": code}


def dispatch_analysis_synthesis(run_id):
    from .tasks import process_analysis_synthesis_task

    with transaction.atomic():
        run = AnalysisRun.objects.select_for_update().get(pk=run_id)
        if run.status not in (AnalysisRun.Status.QUEUED, AnalysisRun.Status.RUNNING):
            return False
        if (
            run.task_runs.filter(task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS)
            .exclude(status=AnalysisTaskRun.Status.SUCCEEDED)
            .exists()
        ):
            return False
        synthesis = run.task_runs.select_for_update().get(
            task_type=AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS
        )
        if synthesis.status != AnalysisTaskRun.Status.QUEUED:
            return False
        synthesis_id = synthesis.pk
    try:
        process_analysis_synthesis_task.apply_async(args=(synthesis_id,))
    except Exception:
        logger.exception(
            "Analysis synthesis dispatch failed; durable task remains queued.",
            extra={"analysis_task_id": synthesis_id},
        )
        return False
    return True


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
    except AnalysisCancellationDetected:
        return {"outcome": "cancelled"}
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


def _grounded_excerpt(excerpt, page_text):
    if not excerpt:
        return None
    if excerpt in page_text:
        return excerpt, "exact"
    chunks = excerpt.split()
    if not chunks:
        return None
    pattern = re.compile(r"\s+".join(re.escape(chunk) for chunk in chunks))
    matches = list(pattern.finditer(page_text))
    if len(matches) != 1:
        return None
    return matches[0].group(0), "whitespace"


def _latest_conflicts(queryset):
    return [conflict for conflict in queryset if not hasattr(conflict, "superseded_by")]


_GENERIC_CONFLICT_SUBJECTS = {
    "commercial",
    "date deadline",
    "project fact",
    "responsibility",
    "owner third party item",
    "permit inspection",
    "landlord requirement",
    "bid condition",
    "submittal closeout",
}


def _conflict_value_meaning(category, value):
    text = " ".join(value.casefold().split())
    if category == ExtractedFinding.Category.DATE_DEADLINE:
        if any(term in text for term in ("revision", "rev date", "product data", "catalog")):
            return "product_revision_date"
        if any(term in text for term in ("ifc", "issued for construction", "issue date")):
            return "project_issue_date"
        if any(term in text for term in ("bid", "tender", "close", "deadline")):
            return "bid_deadline"
        if any(term in text for term in ("schedule", "milestone", "completion")):
            return "schedule_date"
        return "date"
    if category == ExtractedFinding.Category.COMMERCIAL:
        if any(term in text for term in ("email", "contact", "telephone", "phone", "designer")):
            return "contact_information"
        if any(term in text for term in ("net 30", "payment", "deposit", "invoice")):
            return "payment_terms"
        if any(term in text for term in ("price", "pricing", "unit rate", "quote", "quotation")):
            return "pricing"
        if any(term in text for term in ("delivery", "freight", "lead time")):
            return "delivery_terms"
        return "commercial_terms"
    return category


def _conflict_source_context(finding):
    sources = list(finding.sources.select_related("document_revision__document").all())
    if not sources:
        document = finding.document_revision.document
        return ("project", document.category, document.discipline)
    contexts = set()
    project_authority = {
        "drawings",
        "addendum",
        "client_scope",
        "landlord_requirements",
        "responsibility_schedule",
        "bid_requirements",
        "schedule",
        "narrative",
    }
    for source in sources:
        document = source.document_revision.document
        if document.category in project_authority:
            contexts.add(("project", document.category, document.discipline))
        else:
            entity = re.sub(r"[^a-z0-9]+", ".", document.title.casefold()).strip(".")
            contexts.add(("supporting", document.category, entity))
    # A consolidated finding spanning unlike source contexts is not one safely
    # comparable assertion, so it cannot participate in automatic conflicts.
    return next(iter(contexts)) if len(contexts) == 1 else None


def _conflict_context_key(finding):
    subject = " ".join(finding.subject.casefold().split())
    normalized_subject = re.sub(r"[^a-z0-9]+", " ", subject).strip()
    trailing_subject = normalized_subject.rsplit(" ", 1)[-1]
    if ":" in finding.subject or normalized_subject in _GENERIC_CONFLICT_SUBJECTS:
        return None
    if trailing_subject in {"commercial", "responsibility", "fact", "deadline"}:
        return None
    source_context = _conflict_source_context(finding)
    if source_context is None:
        return None
    value_meaning = _conflict_value_meaning(finding.category, finding.machine_value)
    return (finding.category, normalized_subject, value_meaning, source_context)


def detect_conflicts(*, analysis_run, actor=None):
    created = []
    groups = defaultdict(list)
    findings = analysis_run.findings.prefetch_related("sources__document_revision__document").all()
    for finding in findings:
        if finding.category in CONFLICT_CATEGORIES:
            context_key = _conflict_context_key(finding)
            if context_key is not None:
                groups[context_key].append(finding)
    desired_participant_keys = set()
    for context_key, findings in groups.items():
        values = {finding.normalized_machine_value for finding in findings}
        if len(findings) < 2 or len(values) < 2:
            continue
        participant_ids = sorted(finding.pk for finding in findings)
        participant_key = _stable_hash(participant_ids)
        desired_participant_keys.add(participant_key)
        semantic_key = ".".join(str(part) for part in context_key)[:255]
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
    if actor:
        current_conflicts = _latest_conflicts(
            analysis_run.intelligence_conflicts.prefetch_related("findings").all()
        )
        for conflict in current_conflicts:
            if (
                conflict.status == IntelligenceConflict.Status.OPEN
                and conflict.participant_key not in desired_participant_keys
            ):
                resolve_conflict(
                    conflict=conflict,
                    actor=actor,
                    status=IntelligenceConflict.Status.DISMISSED,
                    resolution_note=(
                        "No longer qualifies after strict subject, field, source-authority, "
                        "and entity comparison."
                    ),
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
        provenance_counts = {
            "candidates_considered": len(validated["candidates"]),
            "candidates_materialized": 0,
            "candidates_skipped_no_valid_provenance": 0,
            "evidence_refs_accepted_exact": 0,
            "evidence_refs_recovered_whitespace": 0,
            "evidence_refs_rejected_invalid": 0,
        }
        created_count = 0
        for candidate in validated["candidates"]:
            grounded_sources = []
            for evidence in candidate["evidence"]:
                page_task = page_tasks.get(evidence["document_page_id"])
                if not page_task or page_task.document_page.page_number != evidence["page_number"]:
                    provenance_counts["evidence_refs_rejected_invalid"] += 1
                    continue
                page = page_task.document_page
                sheet = getattr(page, "drawing_sheet", None)
                if evidence.get("drawing_sheet_id") not in (None, sheet.pk if sheet else None):
                    provenance_counts["evidence_refs_rejected_invalid"] += 1
                    continue
                excerpt = evidence["evidence_excerpt"]
                if excerpt:
                    grounded = _grounded_excerpt(excerpt, page.native_text)
                    if grounded is None:
                        provenance_counts["evidence_refs_rejected_invalid"] += 1
                        continue
                    excerpt, match_type = grounded
                    provenance_counts[
                        "evidence_refs_accepted_exact"
                        if match_type == "exact"
                        else "evidence_refs_recovered_whitespace"
                    ] += 1
                    mode = FindingSource.EvidenceMode.NATIVE_TEXT
                else:
                    provenance_counts["evidence_refs_accepted_exact"] += 1
                    mode = FindingSource.EvidenceMode.VISUAL
                grounded_sources.append((evidence, page_task, page, sheet, excerpt, mode))
            if not grounded_sources:
                provenance_counts["candidates_skipped_no_valid_provenance"] += 1
                continue
            provenance_counts["candidates_materialized"] += 1
            candidate_key = _stable_hash(candidate)
            finding, created = ExtractedFinding.objects.get_or_create(
                analysis_run=run,
                source_candidate_key=candidate_key,
                defaults={
                    "analysis_task_run": synthesis,
                    "document_revision": grounded_sources[0][2].document_revision,
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
            for evidence, page_task, page, sheet, excerpt, mode in grounded_sources:
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
                        "document_revision": page.document_revision,
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
                metadata={"finding_count": created_count, **provenance_counts},
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

AI_HANDLED = "ai_handled"
NEEDS_ATTENTION = "needs_attention"
CONFLICTING = "conflicting"
HUMAN_CONFIRMED = "human_confirmed"
HUMAN_EDITED = "human_edited"
HUMAN_REJECTED = "human_rejected"
HUMAN_NEEDS_FOLLOW_UP = "human_needs_follow_up"


def summary_handling_status(row, open_conflict_finding_ids):
    """Classify aggregate finding rows without loading full provenance payloads."""
    if row["id"] in open_conflict_finding_ids:
        return CONFLICTING
    decision = row["latest_review_decision"]
    if decision:
        return {
            FindingReview.Decision.ACCEPTED: HUMAN_CONFIRMED,
            FindingReview.Decision.EDITED_ACCEPTED: HUMAN_EDITED,
            FindingReview.Decision.REJECTED: HUMAN_REJECTED,
            FindingReview.Decision.NEEDS_CLARIFICATION: HUMAN_NEEDS_FOLLOW_UP,
        }[decision]
    if row["category"] == ExtractedFinding.Category.OPEN_QUESTION:
        return NEEDS_ATTENTION
    if row["machine_support"] not in {
        ExtractedFinding.Support.EXPLICIT,
        ExtractedFinding.Support.STRONGLY_SUPPORTED,
    }:
        return NEEDS_ATTENTION
    return AI_HANDLED if row["has_source"] else NEEDS_ATTENTION


def _candidate_for_finding(finding):
    try:
        candidates = validate_result(
            AnalysisTaskRun.TaskType.DOCUMENT_SYNTHESIS,
            finding.analysis_run.result_summary,
        )["candidates"]
    except (KeyError, PydanticValidationError, ValidationError):
        return None
    return next(
        (
            candidate
            for candidate in candidates
            if _stable_hash(candidate) == finding.source_candidate_key
        ),
        None,
    )


def _has_strict_complete_provenance(finding):
    sources = list(finding.sources.all())
    if not sources:
        return False
    candidate = _candidate_for_finding(finding)
    if not candidate or not candidate["evidence"]:
        return False
    pages = {source.document_page_id: source.document_page for source in sources}
    for evidence in candidate["evidence"]:
        page = pages.get(evidence["document_page_id"])
        if page is None or page.page_number != evidence["page_number"]:
            return False
        sheet = getattr(page, "drawing_sheet", None)
        if evidence.get("drawing_sheet_id") not in (None, sheet.pk if sheet else None):
            return False
        excerpt = evidence["evidence_excerpt"]
        if excerpt:
            grounded = _grounded_excerpt(excerpt, page.native_text)
            if grounded is None:
                return False
            expected_excerpt = grounded[0]
            expected_mode = FindingSource.EvidenceMode.NATIVE_TEXT
        else:
            if not evidence["visual_evidence_description"]:
                return False
            expected_excerpt = ""
            expected_mode = FindingSource.EvidenceMode.VISUAL
        if not any(
            source.document_page_id == page.pk
            and source.drawing_sheet_id == evidence.get("drawing_sheet_id")
            and source.evidence_mode == expected_mode
            and source.evidence_excerpt == expected_excerpt
            and source.visual_evidence_description == evidence["visual_evidence_description"]
            for source in sources
        ):
            return False
    allowed_revision_ids = (
        set(finding.analysis_run.input_manifest.get("document_revision_ids", []))
        if finding.analysis_run.run_kind == AnalysisRun.RunKind.PROJECT_SET
        else {finding.document_revision_id}
    )
    return all(
        source.document_revision_id in allowed_revision_ids
        and source.document_page.document_revision_id == source.document_revision_id
        and source.analysis_task_run.analysis_run_id == finding.analysis_run_id
        and source.analysis_task_run.document_page_id == source.document_page_id
        and (
            source.evidence_mode != FindingSource.EvidenceMode.NATIVE_TEXT
            or (
                bool(source.evidence_excerpt)
                and source.evidence_excerpt in source.document_page.native_text
            )
        )
        and (
            source.evidence_mode != FindingSource.EvidenceMode.VISUAL
            or (not source.evidence_excerpt and bool(source.visual_evidence_description))
        )
        for source in sources
    )


def finding_handling_status(finding, *, open_conflict_finding_ids=None):
    if open_conflict_finding_ids is None:
        cached_conflicts = getattr(finding, "_prefetched_objects_cache", {}).get("conflicts")
        if cached_conflicts is None:
            has_open_conflict = IntelligenceConflict.objects.filter(
                findings=finding,
                status=IntelligenceConflict.Status.OPEN,
                superseded_by__isnull=True,
            ).exists()
        else:
            has_open_conflict = any(
                conflict.status == IntelligenceConflict.Status.OPEN
                and not hasattr(conflict, "superseded_by")
                for conflict in cached_conflicts
            )
    else:
        has_open_conflict = finding.pk in open_conflict_finding_ids
    if has_open_conflict:
        return CONFLICTING
    review = max(finding.reviews.all(), key=lambda item: (item.created_at, item.pk), default=None)
    if review:
        return {
            FindingReview.Decision.ACCEPTED: HUMAN_CONFIRMED,
            FindingReview.Decision.EDITED_ACCEPTED: HUMAN_EDITED,
            FindingReview.Decision.REJECTED: HUMAN_REJECTED,
            FindingReview.Decision.NEEDS_CLARIFICATION: HUMAN_NEEDS_FOLLOW_UP,
        }[review.decision]
    if finding.category == ExtractedFinding.Category.OPEN_QUESTION:
        return NEEDS_ATTENTION
    if finding.machine_support not in {
        ExtractedFinding.Support.EXPLICIT,
        ExtractedFinding.Support.STRONGLY_SUPPORTED,
    }:
        return NEEDS_ATTENTION
    return AI_HANDLED if _has_strict_complete_provenance(finding) else NEEDS_ATTENTION


def _snapshot_block(code, message, count=1):
    return {"code": code, "message": message, "count": count}


def _snapshot_state(*, project, run_ids, require_active_documents):
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
        "ai_handled": 0,
        "needs_attention": 0,
        "conflicting": 0,
    }
    accepted_by_key_and_run = defaultdict(lambda: defaultdict(set))
    for run in runs:
        project_set_revision_ids = (
            run.input_manifest.get("document_revision_ids", [])
            if run.run_kind == AnalysisRun.RunKind.PROJECT_SET
            else [run.document_revision_id]
        )
        project_set_documents = list(
            DocumentRevision.objects.filter(pk__in=project_set_revision_ids).select_related(
                "document__current_revision"
            )
        )
        if require_active_documents and any(
            not revision.document.is_active for revision in project_set_documents
        ):
            blockers.append(
                _snapshot_block(
                    "document_archived",
                    "A source document is archived and is not part of active project information.",
                )
            )
        if run.status != AnalysisRun.Status.SUCCEEDED:
            blockers.append(
                _snapshot_block("run_not_succeeded", f"Analysis Run #{run.pk} has not succeeded.")
            )
        if any(
            revision.document.current_revision_id != revision.pk
            for revision in project_set_documents
        ):
            blockers.append(
                _snapshot_block(
                    "revision_not_current",
                    f"Analysis Run #{run.pk} includes a historical document revision.",
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
        open_conflicts = [
            conflict
            for conflict in run.intelligence_conflicts.all()
            if not hasattr(conflict, "superseded_by")
            and conflict.status == IntelligenceConflict.Status.OPEN
        ]
        open_conflict_finding_ids = {
            finding.pk for conflict in open_conflicts for finding in conflict.findings.all()
        }
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
                handling_status = finding_handling_status(
                    finding, open_conflict_finding_ids=open_conflict_finding_ids
                )
                if handling_status == CONFLICTING:
                    counts["conflicting"] += 1
                    continue
                if handling_status != AI_HANDLED:
                    counts["unreviewed"] += 1
                    counts["needs_attention"] += 1
                    blockers.append(
                        _snapshot_block(
                            "unreviewed",
                            f"Finding #{finding.pk} needs human attention.",
                        )
                    )
                    continue
                counts["ai_handled"] += 1
                decision = ProjectIntelligenceSnapshotEntry.Decision.MACHINE_HANDLED
                effective_value = finding.machine_value
                review_id = None
            else:
                counts[review.decision] += 1
                decision = review.decision
                review_id = review.pk
                effective_value = (
                    review.reviewed_value
                    if review.decision == FindingReview.Decision.EDITED_ACCEPTED
                    else finding.machine_value
                    if review.decision == FindingReview.Decision.ACCEPTED
                    else ""
                )
            if review and review.decision == FindingReview.Decision.NEEDS_CLARIFICATION:
                blockers.append(
                    _snapshot_block(
                        "needs_clarification", f"Finding #{finding.pk} needs clarification."
                    )
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
                "finding_review_id": review_id,
                "decision": decision,
                "effective_value": effective_value,
                "semantic_key": finding.semantic_key,
                "category": finding.category,
                "subject": finding.subject,
                "provenance": provenance,
            }
            run_entries.append(entry)
            all_entries.append(entry)
            if effective_value:
                accepted_by_key_and_run[finding.semantic_key][run.pk].add(
                    _normalized_value(finding.category, effective_value)
                )
                approved_entries.append(entry)
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
    cross_run_conflicts = sorted(
        key
        for key, values_by_run in accepted_by_key_and_run.items()
        if len(values_by_run) > 1
        and len({value for values in values_by_run.values() for value in values}) > 1
    )
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
    return _snapshot_state(project=project, run_ids=run_ids, require_active_documents=True)


def snapshot_freshness(*, project, run_ids):
    """Evaluate frozen source/review divergence without treating archive as staleness."""
    return _snapshot_state(project=project, run_ids=run_ids, require_active_documents=False)


def create_intelligence_snapshot(*, project, creator, run_ids):
    _require_operator(creator, project.organization)
    with transaction.atomic():
        locked_project = Project.objects.select_for_update().get(pk=project.pk)
        state = snapshot_readiness(project=locked_project, run_ids=run_ids)
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
                review = (
                    finding.reviews.get(pk=item["finding_review_id"])
                    if item["finding_review_id"]
                    else None
                )
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
        freshness = snapshot_freshness(project=current.project, run_ids=run_ids)
        operational = snapshot_readiness(project=current.project, run_ids=run_ids)
        if not freshness["eligible"] or freshness["fingerprint"] != current.fingerprint:
            blocked_snapshot = current
            blocked_reason = "stale"
        elif not operational["eligible"]:
            blocked_snapshot = current
            blocked_reason = "document_archived"
        else:
            approval = ProjectIntelligenceApproval(
                project=current.project,
                snapshot=current,
                approver=approver,
                approval_note=(approval_note or "").strip(),
                readiness_result={
                    "eligible": True,
                    "fingerprint": freshness["fingerprint"],
                    "summary_counts": freshness["summary_counts"],
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
    if blocked_snapshot and blocked_reason == "stale":
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
    if blocked_snapshot:
        raise ValidationError(
            {
                "snapshot": (
                    "document_archived: One of the source documents for this version is archived. "
                    "Restore the document or prepare a new project-information version."
                )
            }
        )
    return approval, True
