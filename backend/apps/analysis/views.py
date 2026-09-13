from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document, DocumentRevision
from apps.documents.views import ProjectDocumentContextMixin, api_validation_error
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator

from .models import (
    AnalysisRun,
    AnalysisTaskRun,
    ExtractedFinding,
    FindingReview,
    FindingSource,
    IntelligenceConflict,
    ProjectIntelligenceApproval,
    ProjectIntelligenceSnapshot,
)
from .serializers import (
    AnalysisRunSerializer,
    AnalysisTaskRunSerializer,
    ConflictResolutionSerializer,
    ExtractedFindingSerializer,
    FindingReviewCreateSerializer,
    FindingReviewSerializer,
    FindingSourceSerializer,
    IntelligenceApprovalCreateSerializer,
    IntelligenceApprovalSerializer,
    IntelligenceConflictSerializer,
    IntelligenceReadinessSerializer,
    IntelligenceSnapshotCreateSerializer,
    IntelligenceSnapshotSerializer,
)
from .services import (
    AI_HANDLED,
    approve_intelligence_snapshot,
    cancel_analysis_run,
    create_intelligence_snapshot,
    finding_handling_status,
    materialize_findings,
    request_analysis_run,
    request_project_set_analysis_run,
    resolve_conflict,
    retry_analysis_run,
    review_finding,
    snapshot_freshness,
    snapshot_readiness,
    summary_handling_status,
)


def run_queryset(project):
    return (
        AnalysisRun.objects.filter(document_revision__document__project=project)
        .select_related(
            "document_revision__document", "project_context", "requested_by", "predecessor"
        )
        .prefetch_related("task_runs")
    )


def latest_project_review_run(project):
    runs = (
        run_queryset(project)
        .filter(run_kind=AnalysisRun.RunKind.PROJECT_SET)
        .order_by("-created_at", "-id")
    )
    return runs.filter(status=AnalysisRun.Status.SUCCEEDED).first() or runs.first()


def summary_finding_queryset(project):
    source_queryset = FindingSource.objects.select_related(
        "document_page__drawing_sheet", "document_revision__document", "analysis_task_run"
    )
    review_queryset = FindingReview.objects.select_related("reviewer")
    return (
        ExtractedFinding.objects.filter(analysis_run__document_revision__document__project=project)
        .select_related("analysis_run")
        .prefetch_related(
            Prefetch("sources", queryset=source_queryset),
            Prefetch("reviews", queryset=review_queryset),
        )
    )


def project_review_summary_rows(project, run):
    latest_review = FindingReview.objects.filter(finding_id=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    return list(
        ExtractedFinding.objects.filter(
            analysis_run=run,
            analysis_run__document_revision__document__project=project,
        )
        .annotate(
            latest_review_decision=Subquery(latest_review.values("decision")[:1]),
            has_source=Exists(FindingSource.objects.filter(finding_id=OuterRef("pk"))),
        )
        .values(
            "id",
            "source_candidate_key",
            "category",
            "machine_support",
            "latest_review_decision",
            "has_source",
        )
    )


def intelligence_candidate_rows(project, runs):
    """Return bounded finding state for candidate summaries without N+1 queries."""
    run_ids = [run.pk for run in runs]
    if not run_ids:
        return {}, {}
    latest_review = FindingReview.objects.filter(finding_id=OuterRef("pk")).order_by(
        "-created_at", "-id"
    )
    rows_by_run = {run_id: [] for run_id in run_ids}
    rows = (
        ExtractedFinding.objects.filter(
            analysis_run_id__in=run_ids,
            analysis_run__document_revision__document__project=project,
        )
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
    for row in rows:
        rows_by_run[row["analysis_run_id"]].append(row)

    open_conflicts_by_run = {run_id: set() for run_id in run_ids}
    conflict_rows = IntelligenceConflict.objects.filter(
        project=project,
        analysis_run_id__in=run_ids,
        status=IntelligenceConflict.Status.OPEN,
        superseded_by__isnull=True,
    ).values_list("analysis_run_id", "findings__id")
    for run_id, finding_id in conflict_rows:
        if finding_id is not None:
            open_conflicts_by_run[run_id].add(finding_id)
    return rows_by_run, open_conflicts_by_run


def finding_matches_review_filter(finding, review_filter, *, open_conflict_finding_ids):
    handling = finding_handling_status(finding, open_conflict_finding_ids=open_conflict_finding_ids)
    if review_filter == "ai_handled":
        return handling == AI_HANDLED
    if review_filter == "needs_attention":
        return handling in {"needs_attention", "human_needs_follow_up"}
    if review_filter == "conflicts":
        return handling == "conflicting"
    if review_filter == "reviewed_by_you":
        return handling.startswith("human_")
    return True


def project_review_summary(run, findings, *, open_conflict_finding_ids):
    counts = {
        "total": len(findings),
        "confirmed": 0,
        "not_relevant": 0,
        "follow_up": 0,
        "unreviewed": 0,
        "ai_handled": 0,
        "conflicting": 0,
        "reviewed_by_human": 0,
        "needs_attention": 0,
    }
    filter_keys = ("all", "ai_handled", "needs_attention", "conflicts", "reviewed_by_you")
    trades = {}
    trade_map = (
        run.usage_metadata.get("reconciliation", {}).get("finding_trades", {}) if run else {}
    )
    for finding in findings:
        review_status = finding["latest_review_decision"] or "unreviewed"
        handling = summary_handling_status(finding, open_conflict_finding_ids)
        counts["confirmed"] += review_status in {"accepted", "edited_accepted"}
        counts["not_relevant"] += review_status == "rejected"
        counts["follow_up"] += review_status == "needs_clarification"
        counts["unreviewed"] += review_status == "unreviewed"
        counts["ai_handled"] += handling == AI_HANDLED
        counts["conflicting"] += handling == "conflicting"
        counts["reviewed_by_human"] += handling.startswith("human_")
        counts["needs_attention"] += handling in {
            "needs_attention",
            "human_needs_follow_up",
        }
        trade = trade_map.get(finding["source_candidate_key"], "General Requirements")
        trade_counts = trades.setdefault(trade, {key: 0 for key in filter_keys})
        trade_counts["all"] += 1
        trade_counts["ai_handled"] += handling == AI_HANDLED
        trade_counts["needs_attention"] += handling in {
            "needs_attention",
            "human_needs_follow_up",
        }
        trade_counts["conflicts"] += handling == "conflicting"
        trade_counts["reviewed_by_you"] += handling.startswith("human_")
    counts["reviewed"] = counts["confirmed"] + counts["not_relevant"] + counts["follow_up"]
    counts["complete"] = bool(findings) and not (counts["needs_attention"] or counts["conflicting"])
    return {
        "counts": counts,
        "trade_counts": dict(sorted(trades.items())),
        "materialized": bool(findings),
    }


class RevisionAnalysisContextMixin(ProjectDocumentContextMixin):
    def get_document(self):
        return get_object_or_404(
            Document, pk=self.kwargs["document_pk"], project=self.get_project()
        )

    def get_revision(self):
        return get_object_or_404(
            DocumentRevision.objects.select_related(
                "document__project__organization", "project_file__file_asset"
            ),
            pk=self.kwargs["revision_pk"],
            document=self.get_document(),
        )


class RevisionAnalysisRunListView(RevisionAnalysisContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        runs = run_queryset(self.get_project()).filter(document_revision=self.get_revision())
        return Response(AnalysisRunSerializer(runs, many=True).data)

    def post(self, request, *args, **kwargs):
        if not OrganizationOperator().has_permission(request, self):
            self.permission_denied(request)
        try:
            run = request_analysis_run(revision=self.get_revision(), requested_by=request.user)
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        run = run_queryset(self.get_project()).get(pk=run.pk)
        return Response(AnalysisRunSerializer(run).data, status=status.HTTP_201_CREATED)


class ProjectSetAnalysisRunListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        runs = run_queryset(self.get_project()).filter(run_kind=AnalysisRun.RunKind.PROJECT_SET)
        return Response(AnalysisRunSerializer(runs, many=True).data)

    def post(self, request, *args, **kwargs):
        if not OrganizationOperator().has_permission(request, self):
            self.permission_denied(request)
        try:
            run = request_project_set_analysis_run(
                project=self.get_project(), requested_by=request.user
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        run = run_queryset(self.get_project()).get(pk=run.pk)
        return Response(AnalysisRunSerializer(run).data, status=status.HTTP_201_CREATED)


class ProjectReviewStateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        with transaction.atomic():
            current = latest_project_review_run(project)
            findings = (
                project_review_summary_rows(project, current)
                if current and current.status == AnalysisRun.Status.SUCCEEDED
                else []
            )
            open_conflicts = IntelligenceConflict.objects.none()
            if current and current.status == AnalysisRun.Status.SUCCEEDED:
                open_conflicts = IntelligenceConflict.objects.filter(
                    project=project,
                    analysis_run=current,
                    status=IntelligenceConflict.Status.OPEN,
                    superseded_by__isnull=True,
                )
            open_conflict_finding_ids = set(open_conflicts.values_list("findings__id", flat=True))
            summary = project_review_summary(
                current, findings, open_conflict_finding_ids=open_conflict_finding_ids
            )
            current_data = AnalysisRunSerializer(current).data if current is not None else None
            if current_data is not None:
                current_data["result_summary"] = {}
                current_data["usage_metadata"] = {
                    key: value
                    for key, value in current_data["usage_metadata"].items()
                    if key != "reconciliation"
                }
            return Response(
                {
                    "current_run": current_data,
                    **summary,
                    "open_conflict_group_count": open_conflicts.count(),
                }
            )


class ProjectReviewFindingListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        current = latest_project_review_run(project)
        if current is None or current.status != AnalysisRun.Status.SUCCEEDED:
            return Response({"count": 0, "page": 1, "page_size": 25, "results": []})

        trade = request.query_params.get("trade", "").strip()
        review_filter = request.query_params.get("filter", "all").strip()
        try:
            page = max(1, int(request.query_params.get("page", "1")))
            page_size = min(50, max(1, int(request.query_params.get("page_size", "25"))))
        except ValueError:
            page, page_size = 1, 25

        queryset = finding_queryset(project).filter(analysis_run=current)
        trade_map = current.usage_metadata.get("reconciliation", {}).get("finding_trades", {})
        if trade:
            candidate_keys = [key for key, value in trade_map.items() if value == trade]
            queryset = queryset.filter(source_candidate_key__in=candidate_keys)

        start = (page - 1) * page_size
        if review_filter == "all":
            count = queryset.count()
            results = list(queryset[start : start + page_size])
            return Response(
                {
                    "count": count,
                    "page": page,
                    "page_size": page_size,
                    "results": ExtractedFindingSerializer(results, many=True).data,
                }
            )

        findings = list(queryset)
        open_conflict_finding_ids = set(
            IntelligenceConflict.objects.filter(
                project=project,
                analysis_run=current,
                status=IntelligenceConflict.Status.OPEN,
                superseded_by__isnull=True,
            ).values_list("findings__id", flat=True)
        )
        if review_filter != "all":
            findings = [
                finding
                for finding in findings
                if finding_matches_review_filter(
                    finding,
                    review_filter,
                    open_conflict_finding_ids=open_conflict_finding_ids,
                )
            ]
        count = len(findings)
        results = findings[start : start + page_size]
        return Response(
            {
                "count": count,
                "page": page,
                "page_size": page_size,
                "results": ExtractedFindingSerializer(results, many=True).data,
            }
        )


class AnalysisRunDetailView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get_run(self):
        return get_object_or_404(run_queryset(self.get_project()), pk=self.kwargs["run_pk"])

    def get(self, request, *args, **kwargs):
        return Response(AnalysisRunSerializer(self.get_run()).data)


class AnalysisRunTaskListView(AnalysisRunDetailView):
    def get(self, request, *args, **kwargs):
        tasks = self.get_run().task_runs.select_related("document_page__drawing_sheet")
        return Response(AnalysisTaskRunSerializer(tasks, many=True).data)


class RetryAnalysisRunView(AnalysisRunDetailView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        try:
            run = retry_analysis_run(run=self.get_run(), requested_by=request.user)
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        run = run_queryset(self.get_project()).get(pk=run.pk)
        return Response(AnalysisRunSerializer(run).data, status=status.HTTP_201_CREATED)


class CancelAnalysisRunView(AnalysisRunDetailView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        try:
            run, _created = cancel_analysis_run(run=self.get_run(), actor=request.user)
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        run = run_queryset(self.get_project()).get(pk=run.pk)
        return Response(AnalysisRunSerializer(run).data)


def finding_queryset(project):
    return (
        summary_finding_queryset(project)
        .select_related("analysis_task_run", "document_revision__document")
        .prefetch_related(
            "conflicts__superseded_by",
        )
    )


class AnalysisRunFindingListView(AnalysisRunDetailView):
    def get(self, request, *args, **kwargs):
        findings = finding_queryset(self.get_project()).filter(analysis_run=self.get_run())
        return Response(ExtractedFindingSerializer(findings, many=True).data)


class MaterializeAnalysisRunView(AnalysisRunDetailView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        try:
            findings = materialize_findings(analysis_run=self.get_run(), actor=request.user)
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        queryset = finding_queryset(self.get_project()).filter(
            pk__in=findings.values_list("pk", flat=True)
        )
        return Response(ExtractedFindingSerializer(queryset, many=True).data)


class FindingContextMixin(ProjectDocumentContextMixin):
    def get_finding(self):
        return get_object_or_404(finding_queryset(self.get_project()), pk=self.kwargs["finding_pk"])


class FindingDetailView(FindingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        return Response(ExtractedFindingSerializer(self.get_finding()).data)


class FindingSourceListView(FindingDetailView):
    def get(self, request, *args, **kwargs):
        return Response(FindingSourceSerializer(self.get_finding().sources.all(), many=True).data)


class FindingReviewListView(FindingDetailView):
    def get(self, request, *args, **kwargs):
        return Response(FindingReviewSerializer(self.get_finding().reviews.all(), many=True).data)

    def post(self, request, *args, **kwargs):
        if not OrganizationOperator().has_permission(request, self):
            self.permission_denied(request)
        serializer = FindingReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            review, created = review_finding(
                finding=self.get_finding(),
                reviewer=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(FindingReviewSerializer(review).data, status=response_status)


def conflict_queryset(project):
    return (
        IntelligenceConflict.objects.filter(project=project, superseded_by__isnull=True)
        .select_related("analysis_run", "resolved_by", "supersedes")
        .prefetch_related(
            "findings__sources__document_page__drawing_sheet",
            "findings__sources__document_revision__document",
            "findings__reviews__reviewer",
            "findings__conflicts__superseded_by",
        )
    )


class ConflictListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        return Response(
            IntelligenceConflictSerializer(conflict_queryset(self.get_project()), many=True).data
        )


class ResolveConflictView(ConflictListView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        conflict = get_object_or_404(
            conflict_queryset(self.get_project()), pk=self.kwargs["conflict_pk"]
        )
        serializer = ConflictResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            replacement = resolve_conflict(
                conflict=conflict, actor=request.user, **serializer.validated_data
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        replacement = conflict_queryset(self.get_project()).get(pk=replacement.pk)
        return Response(
            IntelligenceConflictSerializer(replacement).data,
            status=status.HTTP_201_CREATED,
        )


def snapshot_queryset(project):
    return (
        ProjectIntelligenceSnapshot.objects.filter(project=project)
        .select_related("created_by", "approval__approver")
        .prefetch_related(
            "sources__analysis_run",
            "sources__document_revision__document",
            "sources__entries__finding",
            "sources__entries__finding_review",
            "sources__entries__provenance__finding_source",
            "sources__entries__provenance__document_page",
            "sources__entries__provenance__drawing_sheet",
        )
    )


def snapshot_stale_map(snapshots):
    result = {}
    for snapshot in snapshots:
        run_ids = list(snapshot.sources.values_list("analysis_run_id", flat=True))
        state = snapshot_freshness(project=snapshot.project, run_ids=run_ids)
        result[snapshot.pk] = not state["eligible"] or state["fingerprint"] != snapshot.fingerprint
    return result


def snapshot_approval_blockers_map(snapshots):
    result = {}
    for snapshot in snapshots:
        if hasattr(snapshot, "approval"):
            result[snapshot.pk] = []
            continue
        archived = snapshot.sources.filter(document_revision__document__is_active=False).exists()
        result[snapshot.pk] = (
            [
                {
                    "code": "document_archived",
                    "message": "One of the source documents for this version is archived.",
                    "count": 1,
                }
            ]
            if archived
            else []
        )
    return result


def snapshot_serializer_context(snapshots):
    return {
        "stale_by_id": snapshot_stale_map(snapshots),
        "approval_blockers_by_id": snapshot_approval_blockers_map(snapshots),
    }


class IntelligenceReadinessView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        runs = list(
            AnalysisRun.objects.filter(
                document_revision__document__project=project,
                status=AnalysisRun.Status.SUCCEEDED,
                document_revision__document__is_active=True,
            )
            .select_related("document_revision__document", "project_context")
            .annotate(
                has_findings=Exists(
                    ExtractedFinding.objects.filter(analysis_run_id=OuterRef("pk"))
                ),
                candidate_page_count=Count(
                    "task_runs",
                    filter=Q(task_runs__task_type=AnalysisTaskRun.TaskType.PAGE_ANALYSIS),
                ),
            )
            .filter(
                has_findings=True,
            )
            .order_by("-created_at", "-id")
        )
        rows_by_run, open_conflicts_by_run = intelligence_candidate_rows(project, runs)
        candidates = []
        for run in runs:
            findings = rows_by_run[run.pk]
            statuses = [finding["latest_review_decision"] or "unreviewed" for finding in findings]
            handling_statuses = [
                summary_handling_status(finding, open_conflicts_by_run[run.pk])
                for finding in findings
            ]
            candidates.append(
                {
                    "id": run.pk,
                    "run_kind": run.run_kind,
                    "document_id": run.document_revision.document_id,
                    "document_title": run.document_revision.document.title,
                    "document_revision_id": run.document_revision_id,
                    "revision_label": run.document_revision.revision_label,
                    "is_current_revision": run.document_revision.document.current_revision_id
                    == run.document_revision_id,
                    "finding_count": len(findings),
                    "unreviewed_count": sum(
                        status
                        not in (AI_HANDLED, "human_confirmed", "human_edited", "human_rejected")
                        for status in handling_statuses
                    ),
                    "needs_clarification_count": statuses.count("needs_clarification"),
                    "created_at": run.created_at,
                    "document_count": len(run.input_manifest.get("documents", []))
                    if run.run_kind == AnalysisRun.RunKind.PROJECT_SET
                    else 1,
                    "page_count": run.candidate_page_count,
                    "covered_document_revision_ids": run.input_manifest.get(
                        "document_revision_ids", [run.document_revision_id]
                    ),
                }
            )
        return Response({"candidate_runs": candidates})

    def post(self, request, *args, **kwargs):
        serializer = IntelligenceReadinessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        state = snapshot_readiness(
            project=self.get_project(), run_ids=serializer.validated_data["analysis_run_ids"]
        )
        return Response(
            {key: value for key, value in state.items() if key not in ("manifest", "runs")}
        )


class IntelligenceSnapshotListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        snapshots = list(snapshot_queryset(self.get_project()))
        return Response(
            IntelligenceSnapshotSerializer(
                snapshots, many=True, context=snapshot_serializer_context(snapshots)
            ).data
        )

    def post(self, request, *args, **kwargs):
        if not OrganizationOperator().has_permission(request, self):
            self.permission_denied(request)
        serializer = IntelligenceSnapshotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            snapshot, created = create_intelligence_snapshot(
                project=self.get_project(),
                creator=request.user,
                run_ids=serializer.validated_data["analysis_run_ids"],
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        snapshot = snapshot_queryset(self.get_project()).get(pk=snapshot.pk)
        return Response(
            IntelligenceSnapshotSerializer(
                snapshot, context=snapshot_serializer_context([snapshot])
            ).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class IntelligenceSnapshotDetailView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get_snapshot(self):
        return get_object_or_404(
            snapshot_queryset(self.get_project()), pk=self.kwargs["snapshot_pk"]
        )

    def get(self, request, *args, **kwargs):
        snapshot = self.get_snapshot()
        return Response(
            IntelligenceSnapshotSerializer(
                snapshot, context=snapshot_serializer_context([snapshot])
            ).data
        )


class IntelligenceSnapshotApprovalView(IntelligenceSnapshotDetailView):
    def get(self, request, *args, **kwargs):
        approval = get_object_or_404(
            ProjectIntelligenceApproval.objects.select_related("approver"),
            snapshot=self.get_snapshot(),
        )
        return Response(IntelligenceApprovalSerializer(approval).data)

    def post(self, request, *args, **kwargs):
        if not OrganizationOperator().has_permission(request, self):
            self.permission_denied(request)
        serializer = IntelligenceApprovalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            approval, created = approve_intelligence_snapshot(
                snapshot=self.get_snapshot(), approver=request.user, **serializer.validated_data
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return Response(
            IntelligenceApprovalSerializer(approval).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
