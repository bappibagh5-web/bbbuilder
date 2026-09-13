from collections import defaultdict

from django.db.models import Exists, OuterRef, Subquery

from apps.analysis.models import (
    AnalysisRun,
    ExtractedFinding,
    FindingReview,
    FindingSource,
    IntelligenceConflict,
    ProjectIntelligenceApproval,
)
from apps.analysis.services import summary_handling_status
from apps.documents.models import Document, ProjectDocumentSelection

from .models import AuditEvent, Project


def _project_payload(project):
    return {
        "id": project.pk,
        "project_number": project.project_number,
        "name": project.name,
        "status": project.status,
        "status_label": project.get_status_display(),
        "city": project.city,
        "province_state": project.province_state,
        "is_active": project.is_active,
    }


def dashboard_summary(organization):
    project_runs = AnalysisRun.objects.filter(
        project_context_id=OuterRef("pk"), run_kind=AnalysisRun.RunKind.PROJECT_SET
    ).order_by("-created_at", "-id")
    projects = list(
        Project.objects.filter(organization=organization, is_active=True).annotate(
            latest_project_run_id=Subquery(project_runs.values("id")[:1]),
            latest_successful_project_run_id=Subquery(
                project_runs.filter(status=AnalysisRun.Status.SUCCEEDED).values("id")[:1]
            ),
        )
    )
    project_ids = [project.pk for project in projects]
    selected_project_run_ids = {
        project.latest_successful_project_run_id or project.latest_project_run_id
        for project in projects
    } - {None}
    project_runs_by_id = AnalysisRun.objects.in_bulk(selected_project_run_ids)
    project_set_project_ids = {
        project.pk for project in projects if project.latest_project_run_id is not None
    }
    latest_successful_run = (
        AnalysisRun.objects.filter(
            document_revision_id=OuterRef("current_revision_id"),
            run_kind=AnalysisRun.RunKind.DOCUMENT,
            status=AnalysisRun.Status.SUCCEEDED,
        )
        .order_by("-id")
        .values("id")[:1]
    )
    document_rows = list(
        Document.objects.filter(
            project_id__in=project_ids,
            is_active=True,
            current_revision__isnull=False,
        )
        .annotate(latest_run_id=Subquery(latest_successful_run))
        .values("project_id", "latest_run_id")
    )
    legacy_run_ids = {
        row["latest_run_id"]
        for row in document_rows
        if row["project_id"] not in project_set_project_ids and row["latest_run_id"]
    }
    run_ids = list(legacy_run_ids | selected_project_run_ids)
    selections_by_project = defaultdict(list)
    for row in ProjectDocumentSelection.objects.filter(
        project_id__in=project_set_project_ids,
        is_included=True,
        document__is_active=True,
    ).values("project_id", "selected_revision_id", "document__current_revision_id"):
        selections_by_project[row["project_id"]].append(row)
    latest_review = FindingReview.objects.filter(finding_id=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    finding_rows = list(
        ExtractedFinding.objects.filter(analysis_run_id__in=run_ids)
        .annotate(
            latest_review_decision=Subquery(latest_review.values("decision")[:1]),
            has_source=Exists(FindingSource.objects.filter(finding_id=OuterRef("pk"))),
        )
        .values(
            "id",
            "analysis_run_id",
            "category",
            "machine_support",
            "latest_review_decision",
            "has_source",
        )
    )
    open_conflict_rows = IntelligenceConflict.objects.filter(
        project_id__in=project_ids,
        analysis_run_id__in=run_ids,
        status=IntelligenceConflict.Status.OPEN,
        superseded_by__isnull=True,
    ).values_list("analysis_run_id", "id", "findings__id")
    open_conflict_ids_by_run = defaultdict(set)
    open_conflict_findings_by_run = defaultdict(set)
    for run_id, conflict_id, finding_id in open_conflict_rows:
        open_conflict_ids_by_run[run_id].add(conflict_id)
        if finding_id is not None:
            open_conflict_findings_by_run[run_id].add(finding_id)

    findings_by_run = defaultdict(list)
    for row in finding_rows:
        findings_by_run[row["analysis_run_id"]].append(row)

    approvals_by_project = defaultdict(list)
    approvals = ProjectIntelligenceApproval.objects.filter(
        project_id__in=project_ids
    ).select_related("snapshot", "approver")
    for approval in approvals:
        approvals_by_project[approval.project_id].append(approval)

    documents_by_project = defaultdict(list)
    for row in document_rows:
        documents_by_project[row["project_id"]].append(row)

    result = []
    for project in projects:
        documents = documents_by_project[project.pk]
        project_run = project_runs_by_id.get(
            project.latest_successful_project_run_id or project.latest_project_run_id
        )
        counts = {
            "total": 0,
            "ai_handled": 0,
            "reviewed_by_user": 0,
            "needs_attention": 0,
            "conflicts": 0,
        }
        reviewed_documents = 0
        selected_documents = []
        run_current = False
        if project_run:
            selected_documents = selections_by_project[project.pk]
            manifest_revisions = project_run.input_manifest.get("document_revision_ids", [])
            run_current = (
                bool(manifest_revisions)
                and len(selected_documents) == len(manifest_revisions)
                and {row["selected_revision_id"] for row in selected_documents}
                == set(manifest_revisions)
                and all(
                    row["selected_revision_id"] == row["document__current_revision_id"]
                    for row in selected_documents
                )
            )
        run_ids_for_project = (
            [project_run.pk]
            if project_run
            else [document["latest_run_id"] for document in documents]
        )
        for run_id in run_ids_for_project:
            findings = findings_by_run[run_id] if run_id else []
            statuses = [
                summary_handling_status(row, open_conflict_findings_by_run[run_id])
                for row in findings
            ]
            run_conflicts = len(open_conflict_ids_by_run[run_id])
            run_attention = sum(
                status in {"needs_attention", "human_needs_follow_up"} for status in statuses
            )
            counts["total"] += len(findings)
            counts["ai_handled"] += statuses.count("ai_handled")
            counts["reviewed_by_user"] += sum(status.startswith("human_") for status in statuses)
            counts["needs_attention"] += run_attention
            counts["conflicts"] += run_conflicts
            if not project_run and findings and not run_attention and not run_conflicts:
                reviewed_documents += 1

        project_approvals = approvals_by_project[project.pk]
        latest_approval = max(
            project_approvals, key=lambda approval: approval.snapshot.version, default=None
        )
        active_document_count = len(documents)
        review_complete = (
            bool(counts["total"])
            and not counts["needs_attention"]
            and not counts["conflicts"]
            and (
                project_run.status == AnalysisRun.Status.SUCCEEDED and run_current
                if project_run
                else active_document_count == reviewed_documents
            )
        )
        needs_attention = not review_complete
        result.append(
            {
                "project": _project_payload(project),
                "active_document_count": active_document_count,
                "reviewed_document_count": reviewed_documents,
                "review_mode": "project_set" if project_run else "document",
                "project_review": (
                    {
                        "run_id": project_run.pk,
                        "document_count": len(
                            project_run.input_manifest.get("document_revision_ids", [])
                        ),
                        "page_count": project_run.input_manifest.get("page_count", 0),
                        "current": run_current,
                    }
                    if project_run
                    else None
                ),
                "review": {
                    **counts,
                    "complete": review_complete,
                },
                "approved_snapshot": (
                    {
                        "version": latest_approval.snapshot.version,
                        "approver": latest_approval.approver.get_full_name()
                        or latest_approval.approver.email,
                        "approved_at": latest_approval.approved_at,
                    }
                    if latest_approval
                    else None
                ),
                "approved_snapshot_count": len(project_approvals),
                "needs_attention": needs_attention,
            }
        )

    return {
        "summary": {
            "active_projects": len(result),
            "needs_attention": sum(item["needs_attention"] for item in result),
            "project_reviews_complete": sum(item["review"]["complete"] for item in result),
            "approved_information": sum(item["approved_snapshot_count"] for item in result),
        },
        "projects": result,
    }


def dashboard_activity(organization, limit=8):
    events = (
        AuditEvent.objects.filter(organization=organization, project__is_active=True)
        .select_related("actor", "project")
        .order_by("-occurred_at", "-id")[:limit]
    )
    return [
        {
            "id": event.pk,
            "action_code": event.action_code,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "actor": (
                event.actor.get_full_name() or event.actor.email if event.actor else "System"
            ),
            "occurred_at": event.occurred_at,
            "project_id": event.project_id,
            "project_name": event.project.name,
        }
        for event in events
    ]
