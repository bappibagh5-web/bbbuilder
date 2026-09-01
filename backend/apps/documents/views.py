from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets

from apps.organizations.models import Organization
from apps.organizations.permissions import ActiveOrganizationMember
from apps.projects.models import Project
from apps.projects.views import ProjectDomainPagination

from .models import Document, DocumentRevision
from .serializers import DocumentRevisionSerializer, DocumentSerializer


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
    viewsets.GenericViewSet,
):
    serializer_class = DocumentSerializer
    permission_classes = (ActiveOrganizationMember,)
    pagination_class = ProjectDomainPagination

    def get_queryset(self):
        return (
            Document.objects.filter(project=self.get_project())
            .select_related(
                "project",
                "created_by",
                "current_revision__created_by",
                "current_revision__project_file__file_asset",
            )
            .annotate(revision_count=Count("revisions"))
            .order_by("title", "id")
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
