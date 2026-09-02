from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.models import Document, DocumentRevision
from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator

from .models import ProcessingJob
from .serializers import ProcessingJobSerializer
from .services import request_source_verification, retry_processing_job


def api_validation_error(error):
    if hasattr(error, "message_dict"):
        return serializers.ValidationError(error.message_dict)
    return serializers.ValidationError({"detail": error.messages})


class RevisionProcessingContextMixin(ProjectDocumentContextMixin):
    def get_document(self):
        if not hasattr(self, "document"):
            self.document = get_object_or_404(
                Document, pk=self.kwargs["document_pk"], project=self.get_project()
            )
        return self.document

    def get_revision(self):
        if not hasattr(self, "revision"):
            self.revision = get_object_or_404(
                DocumentRevision,
                pk=self.kwargs["revision_pk"],
                document=self.get_document(),
            )
        return self.revision


class RevisionProcessingJobListView(RevisionProcessingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        jobs = ProcessingJob.objects.filter(document_revision=self.get_revision()).select_related(
            "document_revision"
        )
        return Response(ProcessingJobSerializer(jobs, many=True).data)


class RequestSourceVerificationView(RevisionProcessingContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        revision = self.get_revision()
        if not revision.document.project.is_active or not revision.document.is_active:
            raise serializers.ValidationError(
                {"detail": "Archived projects or documents cannot start source verification."}
            )
        try:
            job = request_source_verification(
                revision=revision,
                requested_by=request.user,
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return Response(ProcessingJobSerializer(job).data, status=status.HTTP_201_CREATED)


class RetryProcessingJobView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        job = get_object_or_404(
            ProcessingJob.objects.select_related("document_revision__document__project"),
            pk=self.kwargs["job_pk"],
            document_revision__document__project=project,
        )
        if not project.is_active or not job.document_revision.document.is_active:
            raise serializers.ValidationError(
                {"detail": "Archived projects or documents cannot retry source verification."}
            )
        try:
            retry = retry_processing_job(job=job, requested_by=request.user)
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return Response(ProcessingJobSerializer(retry).data, status=status.HTTP_201_CREATED)
