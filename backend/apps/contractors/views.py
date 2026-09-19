from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Exists, F, Max, OuterRef, Q
from django.db.models.functions import Greatest
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.models import Organization
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator
from apps.scope_packages.models import ScopePackage

from .enrichment import enrich_company_contacts
from .models import Company, Contact, ScopeContractorCandidate, TradeCapability
from .providers import ContractorProviderError
from .serializers import (
    CandidateSerializer,
    CandidateStatusSerializer,
    CompanyDirectorySerializer,
    CompanyProfileSerializer,
    CompanySerializer,
    ContactSerializer,
    ContactWriteSerializer,
    SearchSerializer,
    TradeCapabilitySerializer,
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
        .select_related("company", "scope_package", "scope_version", "project")
        .prefetch_related("company__trade_capabilities", "company__contacts")
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


class CompanyDirectoryPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "results": data,
                **self.request.directory_metadata,
            }
        )


class OrganizationCompanyContextMixin:
    organization = None

    def get_organization(self):
        if self.organization is None:
            self.organization = get_object_or_404(
                Organization, slug=self.kwargs["organization_slug"]
            )
        return self.organization

    def get_company(self):
        return get_object_or_404(
            Company.objects.filter(organization=self.get_organization()).exclude(
                external_provider="fake"
            ),
            pk=self.kwargs["company_pk"],
        )


def directory_queryset(organization):
    usable_contacts = Contact.objects.filter(company_id=OuterRef("pk"), is_active=True).filter(
        Q(email__gt="") | Q(phone__gt="")
    )
    primary_email = Contact.objects.filter(
        company_id=OuterRef("pk"), is_active=True, is_primary=True, email__gt=""
    )
    return (
        Company.objects.filter(organization=organization)
        .exclude(external_provider="fake")
        .prefetch_related("trade_capabilities")
        .annotate(
            usable_contact_count=Count(
                "contacts",
                filter=Q(contacts__is_active=True)
                & (Q(contacts__email__gt="") | Q(contacts__phone__gt="")),
                distinct=True,
            ),
            primary_email_ready=Exists(primary_email),
            has_usable_contact=Exists(usable_contacts),
            project_count=Count("project_candidates__project", distinct=True),
            outreach_count=Count("invitationrecipient", distinct=True),
            bid_count=Count("bidsubmission", distinct=True),
            last_candidate_at=Max("project_candidates__updated_at"),
            last_outreach_at=Max("invitationrecipient__created_at"),
            last_bid_at=Max("bidsubmission__received_at"),
        )
        .annotate(
            last_activity_at=Greatest(
                "updated_at", "last_candidate_at", "last_outreach_at", "last_bid_at"
            )
        )
    )


class CompanyDirectoryView(OrganizationCompanyContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)
    http_method_names = ("get", "head", "options")

    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        queryset = directory_queryset(organization)
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(contacts__name__icontains=search)
                | Q(contacts__email__icontains=search)
            ).distinct()
        active = request.query_params.get("active")
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        trade = request.query_params.get("trade", "").strip()
        if trade:
            queryset = queryset.filter(
                trade_capabilities__trade_key=trade,
                trade_capabilities__is_active=True,
            )
        for parameter, field in (
            ("city", "city__iexact"),
            ("province", "province__iexact"),
            ("country", "country__iexact"),
            ("source", "source_type"),
        ):
            value = request.query_params.get(parameter, "").strip()
            if value:
                queryset = queryset.filter(**{field: value})
        contact_ready = request.query_params.get("contact_ready")
        if contact_ready in {"true", "false"}:
            queryset = queryset.filter(has_usable_contact=contact_ready == "true")

        ordering_map = {
            "name": ("display_name", "id"),
            "-name": ("-display_name", "id"),
            "recent": (F("last_activity_at").desc(nulls_last=True), "display_name"),
            "projects": ("-project_count", "display_name"),
        }
        ordering = request.query_params.get("ordering", "name")
        queryset = queryset.order_by(*ordering_map.get(ordering, ordering_map["name"]))

        base = Company.objects.filter(organization=organization).exclude(external_provider="fake")
        trade_keys = list(
            TradeCapability.objects.filter(company__in=base, is_active=True)
            .order_by("trade_key")
            .values_list("trade_key", flat=True)
            .distinct()
        )
        trade_labels = dict(TradeCapability._meta.get_field("trade_key").choices)
        request.directory_metadata = {
            "summary": {
                "total": base.count(),
                "active": base.filter(is_active=True).count(),
                "contact_ready": base.filter(
                    Exists(
                        Contact.objects.filter(company_id=OuterRef("pk"), is_active=True).filter(
                            Q(email__gt="") | Q(phone__gt="")
                        )
                    )
                ).count(),
                "trades_covered": len(trade_keys),
            },
            "filters": {
                "trades": [
                    {"trade_key": key, "trade_label": trade_labels.get(key, key)}
                    for key in trade_keys
                ],
                "cities": list(
                    base.exclude(city="").order_by("city").values_list("city", flat=True).distinct()
                ),
                "provinces": list(
                    base.exclude(province="")
                    .order_by("province")
                    .values_list("province", flat=True)
                    .distinct()
                ),
                "countries": list(
                    base.exclude(country="")
                    .order_by("country")
                    .values_list("country", flat=True)
                    .distinct()
                ),
            },
        }
        paginator = CompanyDirectoryPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(CompanyDirectorySerializer(page, many=True).data)


class CompanyDirectoryDetailView(OrganizationCompanyContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)
    http_method_names = ("get", "head", "options")

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        contacts = company.contacts.filter(is_active=True).order_by("-is_primary", "name", "id")
        capabilities = company.trade_capabilities.filter(is_active=True).order_by("trade_key")
        project_rows = list(
            company.project_candidates.select_related(
                "project", "scope_package", "scope_version"
            ).order_by("-updated_at", "-id")[:25]
        )
        outreach_rows = list(
            company.invitationrecipient_set.select_related("batch__campaign__project").order_by(
                "-created_at", "-id"
            )[:25]
        )
        bid_rows = list(
            company.bidsubmission_set.select_related("project", "scope_package")
            .prefetch_related("revisions")
            .order_by("-received_at", "-id")[:25]
        )
        project_groups = {}
        status_priority = {
            ScopeContractorCandidate.Status.APPROVED: 3,
            ScopeContractorCandidate.Status.SHORTLISTED: 2,
            ScopeContractorCandidate.Status.CANDIDATE: 1,
            ScopeContractorCandidate.Status.REJECTED: 0,
        }
        for row in project_rows:
            key = (row.project_id, row.scope_package.trade_key)
            history_item = {
                "candidate_id": row.pk,
                "scope_package_id": row.scope_package_id,
                "scope_version_id": row.scope_version_id,
                "candidate_status": row.status,
                "is_current_scope": (
                    row.scope_package.lifecycle == ScopePackage.Lifecycle.ACTIVE
                    and row.scope_package.current_version_id == row.scope_version_id
                ),
                "last_activity_at": row.updated_at,
            }
            if key not in project_groups:
                project_groups[key] = {
                    "project_id": row.project_id,
                    "project_number": row.project.project_number,
                    "project_name": row.project.name,
                    "trade_key": row.scope_package.trade_key,
                    "trade": row.scope_package.trade_category,
                    "history": [],
                }
            project_groups[key]["history"].append(history_item)
        project_history = []
        for group in project_groups.values():
            group["history"].sort(
                key=lambda item: (
                    item["is_current_scope"],
                    status_priority.get(item["candidate_status"], -1),
                    item["last_activity_at"],
                    item["candidate_id"],
                ),
                reverse=True,
            )
            relevant = group["history"][0]
            project_history.append(
                {
                    **{key: value for key, value in group.items() if key != "history"},
                    "scope_package_id": relevant["scope_package_id"],
                    "scope_version_id": relevant["scope_version_id"],
                    "candidate_status": relevant["candidate_status"],
                    "last_activity_at": relevant["last_activity_at"],
                    "history_count": len(group["history"]),
                    "history": group["history"],
                }
            )
        project_history.sort(
            key=lambda item: (item["last_activity_at"], item["project_id"], item["trade_key"]),
            reverse=True,
        )
        return Response(
            {
                "company": CompanySerializer(company).data | {"legal_name": company.legal_name},
                "contacts": ContactSerializer(contacts, many=True).data,
                "trade_capabilities": TradeCapabilitySerializer(capabilities, many=True).data,
                "contact_ready": contacts.filter(is_primary=True)
                .filter(Q(email__gt="") | Q(phone__gt=""))
                .exists(),
                "project_history": project_history,
                "outreach_history": [
                    {
                        "recipient_id": row.pk,
                        "project_id": row.batch.campaign.project_id,
                        "project_name": row.batch.campaign.project.name,
                        "campaign_id": row.batch.campaign_id,
                        "batch_id": row.batch_id,
                        "trade": row.batch.campaign.trade_category,
                        "invitation_state": row.current_status,
                        "response_state": row.response_state,
                        "qualification_state": row.qualification_state,
                        "created_at": row.created_at,
                    }
                    for row in outreach_rows
                ],
                "bid_history": [
                    {
                        "submission_id": row.pk,
                        "project_id": row.project_id,
                        "project_name": row.project.name,
                        "trade": row.scope_package.trade_category,
                        "received_at": row.received_at,
                        "source": row.source,
                        "structured_status": (
                            "ready"
                            if any(revision.status == "ready" for revision in row.revisions.all())
                            else "draft"
                            if any(revision.status == "draft" for revision in row.revisions.all())
                            else "not_started"
                        ),
                    }
                    for row in bid_rows
                ],
                "history_note": (
                    "Qualification states are invitation-specific history, not a universal "
                    "company qualification."
                ),
            }
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
