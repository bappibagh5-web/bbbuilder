from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analysis.models import ProjectIntelligenceSnapshot
from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator

from .coverage_preview import build_scope_coverage_preview
from .models import ScopePackage
from .serializers import (
    ScopePackageEditSerializer,
    ScopePackageGenerateSerializer,
    ScopePackageSerializer,
)
from .services import generate_scope_packages, revise_scope_package


def api_validation_error(error):
    if hasattr(error, "message_dict"):
        return serializers.ValidationError(error.message_dict)
    return serializers.ValidationError({"detail": error.messages})


def package_queryset(project, *, include_history=False):
    queryset = ScopePackage.objects.filter(project=project)
    if not include_history:
        queryset = queryset.filter(lifecycle=ScopePackage.Lifecycle.ACTIVE)
    return queryset.select_related(
        "project",
        "organization",
        "source_snapshot__approval",
        "created_by",
        "updated_by",
        "current_version__created_by",
    ).prefetch_related(
        "versions__created_by",
        "versions__sources__snapshot_entry__finding",
        "versions__sources__snapshot_entry__provenance",
        "versions__scope_items__sources__snapshot_entry",
        "versions__scope_items__sources__snapshot_provenance__document_revision__document",
        "versions__scope_items__sources__snapshot_provenance__document_page",
        "versions__scope_items__sources__snapshot_provenance__drawing_sheet",
        "versions__scope_items__sources__snapshot_provenance__finding_source",
    )


class ScopePackageListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        queryset = package_queryset(
            self.get_project(),
            include_history=request.query_params.get("include_history") == "true",
        )
        return Response(ScopePackageSerializer(queryset, many=True).data)


class ScopeCoveragePreviewView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        preview = build_scope_coverage_preview(self.get_project())
        if preview is None:
            return Response(
                {"detail": "Approved project information is required for a scope preview."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(preview)


class ScopePackageGenerateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = ScopePackageGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        snapshot = get_object_or_404(
            ProjectIntelligenceSnapshot,
            pk=serializer.validated_data["snapshot_id"],
            project=self.get_project(),
        )
        try:
            created, existing = generate_scope_packages(
                project=self.get_project(), snapshot=snapshot, actor=request.user
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        packages = package_queryset(self.get_project()).filter(source_snapshot=snapshot)
        return Response(
            {
                "created_count": len(created),
                "existing_count": len(existing),
                "packages": ScopePackageSerializer(packages, many=True).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ScopePackageDetailView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get_package(self):
        return get_object_or_404(package_queryset(self.get_project()), pk=self.kwargs["package_pk"])

    def get(self, request, *args, **kwargs):
        return Response(ScopePackageSerializer(self.get_package()).data)

    def patch(self, request, *args, **kwargs):
        if not OrganizationOperator().has_permission(request, self):
            self.permission_denied(request)
        serializer = ScopePackageEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            revise_scope_package(
                package=self.get_package(), actor=request.user, values=serializer.validated_data
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return Response(
            ScopePackageSerializer(
                package_queryset(self.get_project()).get(pk=self.kwargs["package_pk"])
            ).data
        )


class ScopePackageReadyView(ScopePackageDetailView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        try:
            _, created = revise_scope_package(
                package=self.get_package(), actor=request.user, values={}, mark_ready=True
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        package = package_queryset(self.get_project()).get(pk=self.kwargs["package_pk"])
        return Response(
            ScopePackageSerializer(package).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
