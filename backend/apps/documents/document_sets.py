from collections import Counter

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.processing.models import ProcessingJob
from apps.projects.audit import record_event
from apps.scope_packages.taxonomy import ELECTRICAL, FIRE_PROTECTION, HVAC, LOW_VOLTAGE, PLUMBING

from .models import Document, ProjectDocumentSelection

INDEX_JOB_BY_MIME = {
    "application/pdf": ProcessingJob.JobType.PDF_INDEXING,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        ProcessingJob.JobType.PRESENTATION_INDEXING
    ),
}

RELATED_DISCIPLINES = {
    Document.Discipline.MECHANICAL: (
        Document.Discipline.ELECTRICAL,
        Document.Discipline.PLUMBING,
        Document.Discipline.FIRE_PROTECTION,
    ),
    Document.Discipline.PLUMBING: (Document.Discipline.MECHANICAL,),
    Document.Discipline.FIRE_PROTECTION: (Document.Discipline.MECHANICAL,),
    Document.Discipline.ELECTRICAL: (
        Document.Discipline.MECHANICAL,
        Document.Discipline.LOW_VOLTAGE,
    ),
}

DISCIPLINE_TRADE_LABELS = {
    Document.Discipline.MECHANICAL: HVAC.label,
    Document.Discipline.PLUMBING: PLUMBING.label,
    Document.Discipline.FIRE_PROTECTION: FIRE_PROTECTION.label,
    Document.Discipline.ELECTRICAL: ELECTRICAL.label,
    Document.Discipline.LOW_VOLTAGE: LOW_VOLTAGE.label,
}


def _preparation(document):
    revision = document.current_revision
    if revision is None:
        return "not_prepared", None, 0
    mime_type = revision.project_file.file_asset.detected_mime_type.lower()
    if mime_type in {"image/jpeg", "image/png"}:
        source_job = next(
            (
                item
                for item in revision.processing_jobs.all()
                if item.job_type == ProcessingJob.JobType.SOURCE_VERIFICATION
            ),
            None,
        )
        if source_job is None:
            return "not_prepared", None, 0
        if source_job.status in {ProcessingJob.Status.QUEUED, ProcessingJob.Status.RUNNING}:
            return "preparing", source_job, 0
        if source_job.status == ProcessingJob.Status.FAILED:
            return "failed", source_job, 0
        page_count = revision.pages.count()
        return (
            ("prepared", source_job, page_count)
            if page_count == 1
            else (
                "not_prepared",
                source_job,
                0,
            )
        )
    job_type = INDEX_JOB_BY_MIME.get(mime_type)
    if job_type is None:
        return "not_supported", None, 0
    job = next((item for item in revision.processing_jobs.all() if item.job_type == job_type), None)
    if job is None:
        return "not_prepared", None, 0
    status = {
        ProcessingJob.Status.QUEUED: "preparing",
        ProcessingJob.Status.RUNNING: "preparing",
        ProcessingJob.Status.SUCCEEDED: "prepared",
        ProcessingJob.Status.FAILED: "failed",
    }[job.status]
    return status, job, revision.pages.count() if status == "prepared" else 0


def _coordination_summary(included_entries):
    selected_disciplines = {
        entry["discipline"]
        for entry in included_entries
        if entry["discipline"] not in {Document.Discipline.UNKNOWN, Document.Discipline.OTHER}
    }
    flags = []
    seen = set()
    for discipline in sorted(selected_disciplines):
        for related in RELATED_DISCIPLINES.get(discipline, ()):
            key = (discipline, related)
            if related in selected_disciplines or key in seen:
                continue
            seen.add(key)
            source_label = Document.Discipline(discipline).label
            related_label = Document.Discipline(related).label
            flags.append(
                {
                    "code": "related_discipline_not_selected",
                    "source_discipline": discipline,
                    "related_discipline": related,
                    "related_trade_label": DISCIPLINE_TRADE_LABELS.get(related, related_label),
                    "message": (
                        f"{source_label} may require coordination with {related_label}. "
                        "No prepared document from that discipline is currently selected; verify "
                        "coverage before review."
                    ),
                }
            )
    has_responsibility_schedule = any(
        entry["category"] == Document.Category.RESPONSIBILITY_SCHEDULE for entry in included_entries
    )
    if included_entries and not has_responsibility_schedule:
        flags.append(
            {
                "code": "responsibility_schedule_not_selected",
                "source_discipline": "general",
                "related_discipline": "general",
                "message": (
                    "No responsibility schedule is selected. Confirm responsibility and "
                    "coordination assignments from approved project information."
                ),
            }
        )
    return {
        "selected_disciplines": sorted(selected_disciplines),
        "responsibility_label": "Responsibility / coordination",
        "flags": flags,
    }


def project_document_set(project):
    documents = list(
        Document.objects.filter(project=project, is_active=True)
        .select_related(
            "current_revision__project_file__file_asset",
            "estimating_selection__selected_revision",
        )
        .prefetch_related(
            "current_revision__processing_jobs",
            "current_revision__pages",
            "estimating_selection__selected_revision__pages",
        )
        .order_by("category", "discipline", "title", "id")
    )
    checksum_counts = Counter(
        document.current_revision.project_file.file_asset.checksum
        for document in documents
        if document.current_revision_id
    )
    entries = []
    for document in documents:
        status, job, page_count = _preparation(document)
        selection = getattr(document, "estimating_selection", None)
        current_revision = document.current_revision
        selected_revision = selection.selected_revision if selection else None
        selected_pages = list(selected_revision.pages.all()) if selected_revision else []
        warnings = []
        if (
            current_revision
            and checksum_counts[current_revision.project_file.file_asset.checksum] > 1
        ):
            warnings.append(
                {
                    "code": "duplicate_source",
                    "message": "Another active document uses identical source bytes.",
                }
            )
        if selection and selection.selected_revision_id != document.current_revision_id:
            warnings.append(
                {
                    "code": "selected_revision_superseded",
                    "message": (
                        "The selected estimating-set revision is older than the current revision."
                    ),
                }
            )
        entries.append(
            {
                "document_id": document.pk,
                "document_title": document.title,
                "category": document.category,
                "category_label": document.get_category_display(),
                "discipline": document.discipline or Document.Discipline.UNKNOWN,
                "discipline_label": document.get_discipline_display() or "Unknown",
                "current_revision_id": document.current_revision_id,
                "revision_label": current_revision.revision_label if current_revision else "",
                "selected_revision_id": selection.selected_revision_id if selection else None,
                "selected_page_count": len(selected_pages),
                "selected_pages": [
                    {
                        "document_page_id": page.pk,
                        "page_number": page.page_number,
                        "page_label": page.page_label,
                    }
                    for page in selected_pages
                ],
                "included": bool(selection and selection.is_included),
                "preparation_status": status,
                "processing_job_id": job.pk if job else None,
                "page_count": page_count,
                "warnings": warnings,
            }
        )
    included = [entry for entry in entries if entry["included"]]
    groups = []
    for category, discipline in sorted({(e["category"], e["discipline"]) for e in entries}):
        grouped = [
            entry
            for entry in entries
            if entry["category"] == category and entry["discipline"] == discipline
        ]
        groups.append(
            {
                "category": category,
                "category_label": grouped[0]["category_label"],
                "discipline": discipline,
                "discipline_label": grouped[0]["discipline_label"],
                "documents": grouped,
            }
        )
    return {
        "project_id": project.pk,
        "groups": groups,
        "included_document_count": len(included),
        "included_page_count": sum(entry["selected_page_count"] for entry in included),
        "source_manifest": [
            {
                "document_id": entry["document_id"],
                "document_revision_id": entry["selected_revision_id"],
                "page_count": entry["selected_page_count"],
                "pages": entry["selected_pages"],
            }
            for entry in included
        ],
        "coordination": _coordination_summary(included),
    }


@transaction.atomic
def set_document_included(*, project, document, included, actor):
    if not project.is_active:
        raise ValidationError("Documents in an archived project cannot be selected for review.")
    if document.project_id != project.pk or not document.is_active:
        raise ValidationError("Only an active document in this project can be selected.")
    if document.current_revision is None:
        raise ValidationError("Select a current revision before including this document.")
    status, _, _ = _preparation(document)
    if included and status != "prepared":
        raise ValidationError("Only a prepared current document can be included.")
    selection = (
        ProjectDocumentSelection.objects.select_for_update()
        .filter(project=project, document=document)
        .first()
    )
    before = (
        {
            "included": selection.is_included,
            "selected_revision_id": selection.selected_revision_id,
        }
        if selection
        else {"included": False, "selected_revision_id": None}
    )
    if selection is None:
        selection = ProjectDocumentSelection(
            project=project,
            document=document,
            selected_revision=document.current_revision,
            is_included=included,
            updated_by=actor,
        )
    else:
        selection.selected_revision = document.current_revision
        selection.is_included = included
        selection.updated_by = actor
    after = {
        "included": included,
        "selected_revision_id": document.current_revision_id,
    }
    if before == after:
        return selection, False
    selection.save()
    record_event(
        organization=project.organization,
        project=project,
        actor=actor,
        action_code="project_document_set.updated",
        target=selection,
        metadata={
            "document_id": document.pk,
            "before": before,
            "after": after,
        },
    )
    return selection, True
