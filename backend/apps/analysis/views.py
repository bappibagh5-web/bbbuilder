from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document, DocumentRevision
from apps.documents.views import ProjectDocumentContextMixin, api_validation_error
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator

from .models import (
    AnalysisRun,
    ExtractedFinding,
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
    approve_intelligence_snapshot,
    create_intelligence_snapshot,
    materialize_findings,
    request_analysis_run,
    resolve_conflict,
    retry_analysis_run,
    review_finding,
    snapshot_readiness,
)


def run_queryset(project):
    return (
        AnalysisRun.objects.filter(document_revision__document__project=project)
        .select_related("document_revision__document", "requested_by", "predecessor")
        .prefetch_related("task_runs")
    )


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


def finding_queryset(project):
    return (
        ExtractedFinding.objects.filter(analysis_run__document_revision__document__project=project)
        .select_related("analysis_run", "analysis_task_run", "document_revision__document")
        .prefetch_related(
            "sources__document_page__drawing_sheet",
            "sources__document_revision__document",
            "reviews__reviewer",
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
        state = snapshot_readiness(project=snapshot.project, run_ids=run_ids)
        result[snapshot.pk] = not state["eligible"] or state["fingerprint"] != snapshot.fingerprint
    return result


class IntelligenceReadinessView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        runs = (
            run_queryset(project)
            .filter(status=AnalysisRun.Status.SUCCEEDED, findings__isnull=False)
            .distinct()
        )
        candidates = []
        for run in runs:
            findings = list(run.findings.all())
            statuses = [finding.review_status for finding in findings]
            candidates.append(
                {
                    "id": run.pk,
                    "document_id": run.document_revision.document_id,
                    "document_title": run.document_revision.document.title,
                    "document_revision_id": run.document_revision_id,
                    "revision_label": run.document_revision.revision_label,
                    "is_current_revision": run.document_revision.document.current_revision_id
                    == run.document_revision_id,
                    "finding_count": len(findings),
                    "unreviewed_count": statuses.count("unreviewed"),
                    "needs_clarification_count": statuses.count("needs_clarification"),
                    "created_at": run.created_at,
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
                snapshots, many=True, context={"stale_by_id": snapshot_stale_map(snapshots)}
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
                snapshot, context={"stale_by_id": {snapshot.pk: False}}
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
                snapshot, context={"stale_by_id": snapshot_stale_map([snapshot])}
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
