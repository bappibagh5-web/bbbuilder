from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination

from apps.organizations.models import Organization
from apps.organizations.permissions import OrganizationReadWritePermission

from .audit import (
    CONTACT_AUDIT_FIELDS,
    PROJECT_AUDIT_FIELDS,
    record_event,
    snapshot,
    update_action,
)
from .models import AuditEvent, Project, ProjectContact
from .serializers import AuditEventSerializer, ProjectContactSerializer, ProjectSerializer


class OrganizationContextMixin:
    organization = None

    def get_organization(self):
        if self.organization is None:
            self.organization = get_object_or_404(
                Organization, slug=self.kwargs["organization_slug"]
            )
        return self.organization

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["organization"] = self.get_organization()
        return context


class ProjectDomainPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class ProjectViewSet(
    OrganizationContextMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProjectSerializer
    permission_classes = (OrganizationReadWritePermission,)
    pagination_class = ProjectDomainPagination

    def get_queryset(self):
        return Project.objects.select_related("organization", "created_by").filter(
            organization=self.get_organization()
        )

    @transaction.atomic
    def perform_create(self, serializer):
        project = serializer.save(
            organization=self.get_organization(), created_by=self.request.user
        )
        record_event(
            organization=project.organization,
            project=project,
            actor=self.request.user,
            action_code="project.created",
            target=project,
            metadata={"after": snapshot(project, PROJECT_AUDIT_FIELDS)},
        )

    @transaction.atomic
    def perform_update(self, serializer):
        project = self.get_object()
        before = snapshot(project, PROJECT_AUDIT_FIELDS)
        project = serializer.save()
        after = snapshot(project, PROJECT_AUDIT_FIELDS)
        changed = [name for name in PROJECT_AUDIT_FIELDS if before[name] != after[name]]
        if changed:
            record_event(
                organization=project.organization,
                project=project,
                actor=self.request.user,
                action_code=update_action(target_type="project", before=before, after=after),
                target=project,
                metadata={"changed_fields": changed, "before": before, "after": after},
            )


class ProjectContactViewSet(
    OrganizationContextMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ProjectContactSerializer
    permission_classes = (OrganizationReadWritePermission,)
    pagination_class = ProjectDomainPagination

    def get_project(self):
        if not hasattr(self, "project"):
            self.project = get_object_or_404(
                Project,
                pk=self.kwargs["project_pk"],
                organization=self.get_organization(),
            )
        return self.project

    def get_queryset(self):
        return ProjectContact.objects.select_related("project").filter(project=self.get_project())

    @transaction.atomic
    def perform_create(self, serializer):
        contact = serializer.save(project=self.get_project())
        record_event(
            organization=contact.project.organization,
            project=contact.project,
            actor=self.request.user,
            action_code="project_contact.created",
            target=contact,
            metadata={"after": snapshot(contact, CONTACT_AUDIT_FIELDS)},
        )

    @transaction.atomic
    def perform_update(self, serializer):
        contact = self.get_object()
        before = snapshot(contact, CONTACT_AUDIT_FIELDS)
        contact = serializer.save()
        after = snapshot(contact, CONTACT_AUDIT_FIELDS)
        changed = [name for name in CONTACT_AUDIT_FIELDS if before[name] != after[name]]
        if changed:
            record_event(
                organization=contact.project.organization,
                project=contact.project,
                actor=self.request.user,
                action_code=update_action(
                    target_type="project_contact", before=before, after=after
                ),
                target=contact,
                metadata={"changed_fields": changed, "before": before, "after": after},
            )


class ProjectAuditEventViewSet(
    OrganizationContextMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AuditEventSerializer
    permission_classes = (OrganizationReadWritePermission,)
    pagination_class = ProjectDomainPagination
    http_method_names = ("get", "head", "options")

    def get_project(self):
        if not hasattr(self, "project"):
            self.project = get_object_or_404(
                Project,
                pk=self.kwargs["project_pk"],
                organization=self.get_organization(),
            )
        return self.project

    def get_queryset(self):
        return AuditEvent.objects.select_related("actor").filter(project=self.get_project())
