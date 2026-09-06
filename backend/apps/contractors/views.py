from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator
from apps.scope_packages.models import ScopePackage

from .models import ScopeContractorCandidate
from .providers import ContractorProviderError
from .serializers import CandidateSerializer, CandidateStatusSerializer, SearchSerializer
from .services import discover_contractors, set_candidate_status


def candidates(project):
    queryset = (
        ScopeContractorCandidate.objects.filter(
            project=project, scope_package__lifecycle=ScopePackage.Lifecycle.ACTIVE
        )
        .select_related("company", "scope_package", "project")
        .prefetch_related("company__trade_capabilities")
    )
    if settings.CONTRACTOR_DISCOVERY_PROVIDER == "google_places":
        queryset = queryset.exclude(company__external_provider="fake")
    return queryset


class CandidateListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        return Response(CandidateSerializer(candidates(self.get_project()), many=True).data)


class DiscoverySearchView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = SearchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = self.get_project()
        package = get_object_or_404(
            ScopePackage.objects.select_related("current_version"),
            pk=serializer.validated_data["scope_package_id"],
            project=project,
            lifecycle=ScopePackage.Lifecycle.ACTIVE,
        )
        try:
            discovery = discover_contractors(
                project=project,
                package=package,
                actor=request.user,
                city=serializer.validated_data["city"],
                province=serializer.validated_data["province"],
                country=serializer.validated_data["country"],
                radius_km=serializer.validated_data.get("radius_km"),
                keywords=serializer.validated_data.get("keywords", []),
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError({"detail": error.messages}) from error
        except ContractorProviderError as error:
            return Response(
                {"code": "contractor_provider_unavailable", "detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "discovery_request_id": discovery.pk,
                "result_count": discovery.result_count,
                "candidates": CandidateSerializer(
                    candidates(project).filter(scope_package=package), many=True
                ).data,
            },
            status=201,
        )


class CandidateStatusView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def patch(self, request, *args, **kwargs):
        serializer = CandidateStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        candidate = get_object_or_404(
            candidates(self.get_project()), pk=self.kwargs["candidate_pk"]
        )
        try:
            candidate, _ = set_candidate_status(
                candidate=candidate, status=serializer.validated_data["status"], actor=request.user
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError({"detail": error.messages}) from error
        return Response(CandidateSerializer(candidate).data)
