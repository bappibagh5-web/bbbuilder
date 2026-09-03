from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document, DocumentRevision
from apps.documents.views import ProjectDocumentContextMixin, api_validation_error
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator

from .models import AnalysisRun
from .serializers import AnalysisRunSerializer, AnalysisTaskRunSerializer
from .services import request_analysis_run, retry_analysis_run


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
