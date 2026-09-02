from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.exceptions import APIException, NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Organization
from apps.organizations.permissions import (
    ActiveOrganizationMember,
    OrganizationOperator,
    OrganizationReadWritePermission,
)
from apps.projects.audit import record_event
from apps.projects.models import Project
from apps.projects.views import ProjectDomainPagination

from .models import Document, DocumentRevision
from .serializers import (
    DocumentRevisionSerializer,
    DocumentSerializer,
    NewDocumentUploadSerializer,
    RevisionUploadSerializer,
)
from .services import set_current_revision
from .storage import ObjectStorageError, get_object_storage
from .uploads import upload_document_revision, upload_new_document


class StorageUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Object storage is currently unavailable. Try again shortly."


def document_queryset(project):
    return (
        Document.objects.filter(project=project)
        .select_related(
            "project",
            "created_by",
            "current_revision__created_by",
            "current_revision__project_file__file_asset",
        )
        .annotate(revision_count=Count("revisions"))
        .order_by("title", "id")
    )


def api_validation_error(error):
    if hasattr(error, "message_dict"):
        return serializers.ValidationError(error.message_dict)
    return serializers.ValidationError({"detail": error.messages})


class ProjectDocumentContextMixin:
    organization = None
    project = None

    def get_organization(self):
        if self.organization is None:
            self.organization = get_object_or_404(
                Organization, slug=self.kwargs["organization_slug"]
            )
        return self.organization

    def get_project(self):
        if self.project is None:
            self.project = get_object_or_404(
                Project,
                pk=self.kwargs["project_pk"],
                organization=self.get_organization(),
            )
        return self.project


class DocumentViewSet(
    ProjectDocumentContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DocumentSerializer
    permission_classes = (OrganizationReadWritePermission,)
    pagination_class = ProjectDomainPagination

    def get_queryset(self):
        return document_queryset(self.get_project())

    @transaction.atomic
    def perform_update(self, serializer):
        document = self.get_object()
        if not document.project.is_active:
            raise serializers.ValidationError(
                {"detail": "Documents in an archived project cannot be changed."}
            )
        fields = ("title", "category", "discipline", "description", "is_active")
        before = {field: getattr(document, field) for field in fields}
        document = serializer.save()
        after = {field: getattr(document, field) for field in fields}
        changed = [field for field in fields if before[field] != after[field]]
        if changed:
            action_code = "document.updated"
            if "is_active" in changed:
                action_code = "document.reactivated" if document.is_active else "document.archived"
            record_event(
                organization=document.project.organization,
                project=document.project,
                actor=self.request.user,
                action_code=action_code,
                target=document,
                metadata={"changed_fields": changed, "before": before, "after": after},
            )


class DocumentRevisionViewSet(
    ProjectDocumentContextMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DocumentRevisionSerializer
    permission_classes = (ActiveOrganizationMember,)
    pagination_class = ProjectDomainPagination

    def get_document(self):
        if not hasattr(self, "document"):
            self.document = get_object_or_404(
                Document,
                pk=self.kwargs["document_pk"],
                project=self.get_project(),
            )
        return self.document

    def get_queryset(self):
        return DocumentRevision.objects.filter(document=self.get_document()).select_related(
            "document",
            "created_by",
            "supersedes",
            "project_file__file_asset",
        )


class NewDocumentUploadView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        input_serializer = NewDocumentUploadSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            document, _ = upload_new_document(
                project=self.get_project(),
                user=request.user,
                uploaded_file=input_serializer.validated_data.pop("file"),
                **input_serializer.validated_data,
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        except ObjectStorageError as error:
            raise StorageUnavailable() from error

        result = document_queryset(self.get_project()).get(pk=document.pk)
        return Response(DocumentSerializer(result).data, status=status.HTTP_201_CREATED)


class RevisionUploadView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)
    parser_classes = (MultiPartParser, FormParser)

    def get_document(self):
        return get_object_or_404(
            Document,
            pk=self.kwargs["document_pk"],
            project=self.get_project(),
        )

    def post(self, request, *args, **kwargs):
        input_serializer = RevisionUploadSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        values = input_serializer.validated_data
        supersedes_id = values.pop("supersedes")
        supersedes = None
        if supersedes_id is not None:
            supersedes = get_object_or_404(
                DocumentRevision,
                pk=supersedes_id,
                document=self.get_document(),
            )
        try:
            _, revision = upload_document_revision(
                document=self.get_document(),
                user=request.user,
                uploaded_file=values.pop("file"),
                supersedes=supersedes,
                **values,
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        except ObjectStorageError as error:
            raise StorageUnavailable() from error
        revision = DocumentRevision.objects.select_related(
            "document", "created_by", "supersedes", "project_file__file_asset"
        ).get(pk=revision.pk)
        return Response(
            DocumentRevisionSerializer(revision).data,
            status=status.HTTP_201_CREATED,
        )


class SetCurrentRevisionView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        document = get_object_or_404(Document, pk=self.kwargs["document_pk"], project=project)
        revision = get_object_or_404(
            DocumentRevision,
            pk=self.kwargs["revision_pk"],
            document=document,
        )
        if not project.is_active or not document.is_active:
            raise serializers.ValidationError(
                {"detail": "Archived projects or documents cannot change current revision."}
            )
        try:
            set_current_revision(document=document, revision=revision, actor=request.user)
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        result = document_queryset(project).get(pk=document.pk)
        return Response(DocumentSerializer(result).data)


class RevisionDownloadView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        document = get_object_or_404(
            Document,
            pk=self.kwargs["document_pk"],
            project=self.get_project(),
        )
        revision = get_object_or_404(
            DocumentRevision.objects.select_related("project_file__file_asset"),
            pk=self.kwargs["revision_pk"],
            document=document,
        )
        asset = revision.project_file.file_asset
        try:
            stored_file = get_object_storage().open(asset.storage_key)
        except ObjectStorageError as error:
            raise StorageUnavailable() from error
        if stored_file is None:
            raise NotFound("The stored file is unavailable for this historical revision.")
        content_type = asset.detected_mime_type or asset.declared_mime_type
        response = FileResponse(
            stored_file,
            as_attachment=True,
            filename=asset.original_filename,
            content_type=content_type or "application/octet-stream",
        )
        response["Content-Length"] = asset.byte_size
        return response
