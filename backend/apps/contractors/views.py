from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator
from apps.scope_packages.models import ScopePackage

from .enrichment import enrich_company_contacts
from .models import Company, Contact, ScopeContractorCandidate
from .providers import ContractorProviderError
from .serializers import (
    CandidateSerializer,
    CandidateStatusSerializer,
    CompanyProfileSerializer,
    ContactSerializer,
    ContactWriteSerializer,
    SearchSerializer,
)
from .services import (
    build_trade_coverage,
    create_contact,
    discover_contractors,
    set_candidate_status,
    update_contact,
)


def candidates(project):
    queryset = (
        ScopeContractorCandidate.objects.filter(
            project=project,
            scope_package__lifecycle=ScopePackage.Lifecycle.ACTIVE,
            scope_version=F("scope_package__current_version"),
        )
        .select_related("company", "scope_package", "project")
        .prefetch_related("company__trade_capabilities")
    )
    if settings.CONTRACTOR_DISCOVERY_PROVIDER == "google_places":
        queryset = queryset.exclude(company__external_provider="fake")
    return queryset


def company_for_project(project, company_pk):
    return get_object_or_404(
        Company.objects.filter(
            pk=company_pk,
            organization=project.organization,
            project_candidates__project=project,
            project_candidates__scope_package__lifecycle=ScopePackage.Lifecycle.ACTIVE,
        )
        .prefetch_related("trade_capabilities", "contacts")
        .distinct()
    )


class CandidateListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        queryset = candidates(self.get_project())
        scope_package_id = request.query_params.get("scope_package")
        if scope_package_id:
            try:
                scope_package_id = int(scope_package_id)
            except ValueError as error:
                raise serializers.ValidationError(
                    {"scope_package": "Enter a valid scope package ID."}
                ) from error
            queryset = queryset.filter(scope_package_id=scope_package_id)
        return Response(CandidateSerializer(queryset, many=True).data)


class TradeCoverageView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        return Response(
            build_trade_coverage(project=project, candidate_queryset=candidates(project))
        )


class CompanyProfileView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        company = company_for_project(project, self.kwargs["company_pk"])
        return Response(CompanyProfileSerializer(company, context={"project": project}).data)


class ContactEnrichmentView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        company = company_for_project(self.get_project(), self.kwargs["company_pk"])
        return Response(enrich_company_contacts(company))


class ContactListCreateView(ProjectDocumentContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    def get(self, request, *args, **kwargs):
        company = company_for_project(self.get_project(), self.kwargs["company_pk"])
        return Response(ContactSerializer(company.contacts.all(), many=True).data)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        company = company_for_project(project, self.kwargs["company_pk"])
        serializer = ContactWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            contact, created = create_contact(
                company=company,
                project=project,
                actor=request.user,
                values=serializer.validated_data,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError({"detail": error.messages}) from error
        return Response(
            ContactSerializer(contact).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ContactDetailView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def patch(self, request, *args, **kwargs):
        project = self.get_project()
        company = company_for_project(project, self.kwargs["company_pk"])
        contact = get_object_or_404(
            Contact.objects.select_related("company"),
            pk=self.kwargs["contact_pk"],
            company=company,
        )
        serializer = ContactWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            contact, _ = update_contact(
                contact=contact,
                project=project,
                actor=request.user,
                values=serializer.validated_data,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError({"detail": error.messages}) from error
        return Response(ContactSerializer(contact).data)


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
                "partial_results": bool(
                    discovery.provider_metadata.get("partial_failure_count", 0)
                ),
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
