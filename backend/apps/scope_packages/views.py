from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator

from .coverage_preview import build_scope_coverage_preview
from .models import ScopePackage, ScopePackageSource, ScopePackageVersion
from .serializers import (
    ScopePackageEditSerializer,
    ScopePackageGenerateSerializer,
    ScopePackageSerializer,
    ScopePackageSummarySerializer,
)
from .services import (
    SCOPE_PLAN_CHANGED_MESSAGE,
    generate_scope_plan_packages,
    revise_scope_package,
)


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
        "current_version__sources__snapshot_entry__finding",
        "current_version__sources__snapshot_entry__provenance",
        "current_version__scope_items__sources__snapshot_entry",
        "current_version__scope_items__sources__snapshot_provenance__document_revision__document",
        "current_version__scope_items__sources__snapshot_provenance__document_page",
        "current_version__scope_items__sources__snapshot_provenance__drawing_sheet",
        "current_version__scope_items__sources__snapshot_provenance__finding_source",
        "versions__created_by",
        "versions__sources__snapshot_entry__finding",
        "versions__sources__snapshot_entry__provenance",
        "versions__scope_items__sources__snapshot_entry",
        "versions__scope_items__sources__snapshot_provenance__document_revision__document",
        "versions__scope_items__sources__snapshot_provenance__document_page",
        "versions__scope_items__sources__snapshot_provenance__drawing_sheet",
        "versions__scope_items__sources__snapshot_provenance__finding_source",
    )


def package_summary_queryset(project, *, include_history=False):
    queryset = ScopePackage.objects.filter(project=project)
    if not include_history:
        queryset = queryset.filter(lifecycle=ScopePackage.Lifecycle.ACTIVE)
    version_counts = (
        ScopePackageVersion.objects.filter(package_id=OuterRef("pk"))
        .values("package_id")
        .annotate(total=Count("pk"))
        .values("total")
    )
    item_counts = (
        ScopePackageVersion.objects.filter(pk=OuterRef("current_version_id"))
        .values("pk")
        .annotate(total=Count("scope_items"))
        .values("total")
    )
    confirmation_counts = (
        ScopePackageVersion.objects.filter(pk=OuterRef("current_version_id"))
        .values("pk")
        .annotate(total=Count("scope_items", filter=Q(scope_items__responsibility="unclear")))
        .values("total")
    )
    source_counts = (
        ScopePackageSource.objects.filter(package_version_id=OuterRef("current_version_id"))
        .values("package_version_id")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return (
        queryset.select_related("source_snapshot", "current_version__created_by")
        .annotate(
            version_count=Coalesce(Subquery(version_counts), Value(0), output_field=IntegerField()),
            scope_item_count=Coalesce(Subquery(item_counts), Value(0), output_field=IntegerField()),
            needs_confirmation_count=Coalesce(
                Subquery(confirmation_counts), Value(0), output_field=IntegerField()
            ),
            source_count=Coalesce(Subquery(source_counts), Value(0), output_field=IntegerField()),
        )
        .order_by("trade_category", "id")
    )


class ScopePackageListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        queryset = package_summary_queryset(
            self.get_project(),
            include_history=request.query_params.get("include_history") == "true",
        )
        return Response(ScopePackageSummarySerializer(queryset, many=True).data)


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
        try:
            created, existing, plan = generate_scope_plan_packages(
                project=self.get_project(),
                actor=request.user,
                expected_plan_fingerprint=serializer.validated_data["expected_plan_fingerprint"],
                expected_project_information_version=serializer.validated_data[
                    "expected_project_information_version"
                ],
            )
        except DjangoValidationError as error:
            if SCOPE_PLAN_CHANGED_MESSAGE in error.messages:
                return Response(
                    {"detail": SCOPE_PLAN_CHANGED_MESSAGE},
                    status=status.HTTP_409_CONFLICT,
                )
            raise api_validation_error(error) from error
        return Response(
            {
                "created_count": len(created),
                "existing_count": len(existing),
                "package_count": plan["proposed_package_count"],
                "scope_item_count": plan["proposed_scope_item_count"],
                "project_wide_requirement_count": plan["project_wide_requirement_count"],
                "source_snapshot_version": plan["source_snapshot_version"],
                "plan_fingerprint": plan["plan_fingerprint"],
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
