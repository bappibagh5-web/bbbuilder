# ruff: noqa: E501
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contractors.enrichment import enrich_company_contacts
from apps.contractors.models import Company, Contact
from apps.contractors.providers import ContractorProviderError
from apps.contractors.serializers import ContactSerializer, ContactWriteSerializer
from apps.contractors.services import create_contact
from apps.organizations.models import Organization
from apps.organizations.permissions import (
    ActiveOrganizationMember,
    OrganizationAdmin,
    OrganizationOperator,
)
from apps.outreach.smtp import provider_status
from apps.projects.audit import record_event
from apps.scope_packages.trades import TRADE_CHOICES

from .analytics import (
    analytics_window,
    campaign_rows,
    metric_bundle,
    recipient_rows,
    recipient_timeline,
    sequence_step_rows,
    trend_data,
)
from .campaigns import (
    approve_campaign,
    campaign_metrics,
    campaign_readiness,
    create_campaign,
    delete_step,
    duplicate_step,
    enroll_entries,
    enrollment_preview,
    launch_campaign,
    process_due_prospecting_messages,
    remove_or_archive_campaign,
    remove_suppression,
    render_draft_preview,
    reorder_steps,
    restore_campaign,
    save_step,
    send_test_email,
    set_campaign_state,
    suppress_email,
    unsubscribe,
    unsubscribe_token,
)
from .intake import (
    IMPORT_TEMPLATE_FILENAME,
    add_manual_prospect,
    build_import_template,
    confirm_import,
    preview_import,
)
from .models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectEmailTemplate,
    ProspectImport,
    ProspectingDiscoveryRun,
    ProspectingSettings,
    ProspectList,
    ProspectListEntry,
    ProspectSequenceStep,
    ProspectSuppression,
)
from .serializers import (
    AddResultsSerializer,
    CampaignRecipientSerializer,
    CampaignSerializer,
    DiscoveryInputSerializer,
    DiscoveryResultSerializer,
    EmailTemplateSerializer,
    EntryUpdateSerializer,
    ManualProspectSerializer,
    ProspectEntrySerializer,
    ProspectListSerializer,
    SequenceStepSerializer,
)
from .services import add_discovery_results, run_discovery, update_entry


def safe_validation(error):
    if hasattr(error, "message_dict"):
        raise serializers.ValidationError(error.message_dict) from error
    raise serializers.ValidationError(error.messages) from error


class ProspectingContextMixin:
    organization = None

    def get_organization(self):
        if self.organization is None:
            self.organization = get_object_or_404(
                Organization, slug=self.kwargs["organization_slug"]
            )
        return self.organization

    def get_list(self):
        return get_object_or_404(
            ProspectList, organization=self.get_organization(), pk=self.kwargs["list_pk"]
        )

    def get_entry(self):
        return get_object_or_404(
            ProspectListEntry.objects.select_related(
                "prospect_list", "company", "primary_contact"
            ).prefetch_related("tags", "company__trade_capabilities", "company__contacts"),
            prospect_list__organization=self.get_organization(),
            is_active=True,
            pk=self.kwargs["entry_pk"],
        )


class ProspectingPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def list_queryset(organization):
    return ProspectList.objects.filter(organization=organization).annotate(
        prospect_count=Count("entries", filter=Q(entries__is_active=True), distinct=True),
        contact_ready_count=Count(
            "entries",
            filter=Q(
                entries__is_active=True,
                entries__status=ProspectListEntry.Status.CONTACT_READY,
            ),
            distinct=True,
        ),
    )


class ProspectingSummaryView(ProspectingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        entries = ProspectListEntry.objects.filter(
            prospect_list__organization=organization, is_active=True
        )
        recent = ProspectingDiscoveryRun.objects.filter(organization=organization)[:5]
        return Response(
            {
                "total_prospects": entries.values("company_id").distinct().count(),
                "contact_ready": entries.filter(
                    status=ProspectListEntry.Status.CONTACT_READY
                ).count(),
                "needs_contact": entries.exclude(
                    status__in=(
                        ProspectListEntry.Status.CONTACT_READY,
                        ProspectListEntry.Status.NOT_A_FIT,
                        ProspectListEntry.Status.SUPPRESSED,
                    )
                ).count(),
                "lists": ProspectList.objects.filter(
                    organization=organization, status=ProspectList.Status.ACTIVE
                ).count(),
                "recent_discovery": [
                    {
                        "id": run.pk,
                        "trade_key": run.trade_key,
                        "trade_label": run.get_trade_key_display(),
                        "query": run.query,
                        "location": ", ".join(
                            value for value in (run.city, run.province, run.country) if value
                        ),
                        "provider": run.provider,
                        "result_count": run.result_count,
                        "requested_at": run.requested_at,
                    }
                    for run in recent
                ],
            }
        )


class ProspectListCollectionView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    def get(self, request, *args, **kwargs):
        queryset = list_queryset(self.get_organization())
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        list_status = request.query_params.get("status", "").strip()
        if list_status in ProspectList.Status.values:
            queryset = queryset.filter(status=list_status)
        elif not list_status:
            queryset = queryset.filter(status=ProspectList.Status.ACTIVE)
        queryset = queryset.order_by("-updated_at", "-id")
        paginator = ProspectingPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(ProspectListSerializer(page, many=True).data)
        response.data["can_manage"] = OrganizationOperator().has_permission(request, self)
        return response

    def post(self, request, *args, **kwargs):
        name = " ".join(str(request.data.get("name", "")).split())
        if not name:
            raise serializers.ValidationError({"name": "Enter a prospect list name."})
        if ProspectList.objects.filter(
            organization=self.get_organization(), name__iexact=name
        ).exists():
            raise serializers.ValidationError({"name": "A prospect list already uses this name."})
        prospect_list = ProspectList.objects.create(
            organization=self.get_organization(),
            name=name,
            description=str(request.data.get("description", "")).strip(),
            created_by=request.user,
        )
        record_event(
            organization=prospect_list.organization,
            project=None,
            actor=request.user,
            action_code="prospect_list.created",
            target=prospect_list,
            metadata={"prospect_list_id": prospect_list.pk},
        )
        prospect_list.prospect_count = 0
        prospect_list.contact_ready_count = 0
        return Response(ProspectListSerializer(prospect_list).data, status=status.HTTP_201_CREATED)


class ProspectListDetailView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    def get(self, request, *args, **kwargs):
        prospect_list = self.get_list()
        entries = (
            prospect_list.entries.filter(is_active=True)
            .select_related("company", "primary_contact")
            .prefetch_related("tags", "company__trade_capabilities", "company__contacts")
            .order_by("company__display_name", "id")
        )
        search = request.query_params.get("search", "").strip()
        if search:
            entries = entries.filter(company__display_name__icontains=search)
        entry_status = request.query_params.get("status", "").strip()
        if entry_status in ProspectListEntry.Status.values:
            entries = entries.filter(status=entry_status)
        paginator = ProspectingPagination()
        page = paginator.paginate_queryset(entries, request, view=self)
        return Response(
            {
                "list": {
                    "id": prospect_list.pk,
                    "name": prospect_list.name,
                    "description": prospect_list.description,
                    "status": prospect_list.status,
                    "updated_at": prospect_list.updated_at,
                },
                "can_manage": OrganizationOperator().has_permission(request, self),
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "page": paginator.page.number,
                "results": ProspectEntrySerializer(page, many=True).data,
            }
        )

    def patch(self, request, *args, **kwargs):
        prospect_list = self.get_list()
        list_status = request.data.get("status")
        if list_status not in ProspectList.Status.values:
            raise serializers.ValidationError({"status": "Choose Active or Archived."})
        if prospect_list.status != list_status:
            prospect_list.status = list_status
            prospect_list.save(update_fields=("status", "updated_at"))
            record_event(
                organization=prospect_list.organization,
                project=None,
                actor=request.user,
                action_code=(
                    "prospect_list.archived"
                    if list_status == ProspectList.Status.ARCHIVED
                    else "prospect_list.restored"
                ),
                target=prospect_list,
                metadata={"prospect_list_id": prospect_list.pk},
            )
        return Response(
            {
                "id": prospect_list.pk,
                "name": prospect_list.name,
                "description": prospect_list.description,
                "status": prospect_list.status,
                "updated_at": prospect_list.updated_at,
            }
        )


class ProspectCompanyOptionsView(ProspectingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        search = request.query_params.get("search", "").strip()
        queryset = Company.objects.filter(
            organization=self.get_organization(), is_active=True
        ).order_by("display_name", "id")
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(email__icontains=search)
            )
        return Response(
            {
                "trades": [{"value": key, "label": label} for key, label in TRADE_CHOICES],
                "results": [
                    {
                        "id": company.pk,
                        "name": company.display_name,
                        "city": company.city,
                        "province": company.province,
                    }
                    for company in queryset[:25]
                ],
            }
        )


class ProspectManualCreateView(ProspectingContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        prospect_list = self.get_list()
        serializer = ManualProspectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            entry, created = add_manual_prospect(
                prospect_list=prospect_list,
                actor=request.user,
                values=serializer.validated_data,
            )
        except DjangoValidationError as error:
            safe_validation(error)
        entry = (
            ProspectListEntry.objects.select_related("company", "primary_contact")
            .prefetch_related("tags", "company__trade_capabilities", "company__contacts")
            .get(pk=entry.pk)
        )
        return Response(
            {"created": created, "entry": ProspectEntrySerializer(entry).data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProspectImportCollectionView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    @staticmethod
    def summary(item):
        return {
            "id": item.pk,
            "filename": item.filename,
            "file_type": item.file_type,
            "status": item.status,
            "total_rows": item.total_rows,
            "valid_rows": item.valid_rows,
            "warning_rows": item.warning_rows,
            "error_rows": item.error_rows,
            "imported_rows": item.imported_rows,
            "skipped_rows": item.skipped_rows,
            "created_at": item.created_at,
            "completed_at": item.completed_at,
        }

    def get(self, request, *args, **kwargs):
        imports = self.get_list().imports.order_by("-created_at", "-id")[:25]
        return Response({"results": [self.summary(item) for item in imports]})

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            raise serializers.ValidationError({"file": "Choose a CSV or XLSX file."})
        try:
            record, summary = preview_import(
                prospect_list=self.get_list(), uploaded_file=uploaded_file, actor=request.user
            )
        except DjangoValidationError as error:
            safe_validation(error)
        return Response(
            {
                "import": self.summary(record),
                "summary": summary,
                "rows": record.preview_rows,
            },
            status=status.HTTP_201_CREATED,
        )


class ProspectImportTemplateView(ProspectingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        self.get_organization()
        return FileResponse(
            build_import_template(),
            as_attachment=True,
            filename=IMPORT_TEMPLATE_FILENAME,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class ProspectImportConfirmView(ProspectImportCollectionView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        record = get_object_or_404(
            ProspectImport,
            organization=self.get_organization(),
            prospect_list=self.get_list(),
            pk=self.kwargs["import_pk"],
        )
        try:
            record = confirm_import(import_record=record, actor=request.user)
        except DjangoValidationError as error:
            safe_validation(error)
        return Response({"import": self.summary(record)})


class ProspectEntryDetailView(ProspectingContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def patch(self, request, *args, **kwargs):
        entry = self.get_entry()
        serializer = EntryUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        contact = None
        if "primary_contact_id" in serializer.validated_data:
            contact = get_object_or_404(
                Contact,
                pk=serializer.validated_data["primary_contact_id"],
                company=entry.company,
            )
        try:
            entry = update_entry(
                entry=entry,
                actor=request.user,
                status=serializer.validated_data.get("status"),
                notes=serializer.validated_data.get("notes"),
                tag_names=serializer.validated_data.get("tags"),
                primary_contact=contact,
            )
        except DjangoValidationError as error:
            safe_validation(error)
        return Response(ProspectEntrySerializer(self.get_entry()).data)

    def delete(self, request, *args, **kwargs):
        entry = self.get_entry()
        entry.is_active = False
        entry.removed_by = request.user
        entry.removed_at = timezone.now()
        entry.save(update_fields=("is_active", "removed_by", "removed_at", "updated_at"))
        record_event(
            organization=entry.prospect_list.organization,
            project=None,
            actor=request.user,
            action_code="prospect.removed",
            target=entry,
            metadata={
                "prospect_list_id": entry.prospect_list_id,
                "company_id": entry.company_id,
            },
        )
        return Response(
            {"detail": "Prospect removed from the active list. Historical activity was preserved."}
        )


class ProspectDiscoveryView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    def get(self, request, *args, **kwargs):
        runs = ProspectingDiscoveryRun.objects.filter(organization=self.get_organization())[:25]
        return Response(
            {
                "trades": [{"value": key, "label": label} for key, label in TRADE_CHOICES],
                "results": [
                    {
                        "id": run.pk,
                        "trade_key": run.trade_key,
                        "trade_label": run.get_trade_key_display(),
                        "query": run.query,
                        "city": run.city,
                        "province": run.province,
                        "country": run.country,
                        "radius_miles": run.radius_miles,
                        "provider": run.provider,
                        "result_count": run.result_count,
                        "requested_at": run.requested_at,
                    }
                    for run in runs
                ],
            }
        )

    def post(self, request, *args, **kwargs):
        serializer = DiscoveryInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        selected_list = None
        if serializer.validated_data.get("prospect_list_id"):
            selected_list = get_object_or_404(
                ProspectList,
                organization=self.get_organization(),
                pk=serializer.validated_data["prospect_list_id"],
            )
        try:
            run = run_discovery(
                organization=self.get_organization(),
                actor=request.user,
                trade_key=serializer.validated_data["trade_key"],
                query=serializer.validated_data.get("query", ""),
                keywords=serializer.validated_data.get("keywords", []),
                city=serializer.validated_data["city"],
                province=serializer.validated_data["province"],
                country=serializer.validated_data["country"],
                radius_miles=serializer.validated_data.get("radius_miles"),
            )
        except DjangoValidationError as error:
            safe_validation(error)
        except ContractorProviderError as error:
            return Response(
                {"code": "prospecting_provider_unavailable", "detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        selected_list_company_ids = set()
        if selected_list:
            selected_list_company_ids = set(
                selected_list.entries.filter(is_active=True).values_list("company_id", flat=True)
            )
        return Response(
            {
                "id": run.pk,
                "provider": run.provider,
                "result_count": run.result_count,
                "results": DiscoveryResultSerializer(
                    run.results.select_related("company"),
                    many=True,
                    context={"selected_list_company_ids": selected_list_company_ids},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ProspectDiscoveryAddView(ProspectingContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, run_pk, *args, **kwargs):
        serializer = AddResultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = get_object_or_404(
            ProspectingDiscoveryRun, organization=self.get_organization(), pk=run_pk
        )
        prospect_list = get_object_or_404(
            ProspectList,
            organization=self.get_organization(),
            pk=serializer.validated_data["prospect_list_id"],
        )
        try:
            entries = add_discovery_results(
                prospect_list=prospect_list,
                run=run,
                result_ids=serializer.validated_data["result_ids"],
                actor=request.user,
            )
        except DjangoValidationError as error:
            safe_validation(error)
        return Response({"added_count": len(entries), "entry_ids": [entry.pk for entry in entries]})


class ProspectEntryEnrichmentView(ProspectingContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        return Response(enrich_company_contacts(self.get_entry().company))


class ProspectEntryContactCreateView(ProspectingContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        entry = self.get_entry()
        serializer = ContactWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            contact, created = create_contact(
                company=entry.company,
                project=None,
                actor=request.user,
                values=serializer.validated_data,
            )
            entry = update_entry(
                entry=entry,
                actor=request.user,
                status=ProspectListEntry.Status.CONTACT_READY,
                primary_contact=contact,
            )
        except DjangoValidationError as error:
            safe_validation(error)
        return Response(
            {
                "contact": ContactSerializer(contact).data,
                "entry": ProspectEntrySerializer(self.get_entry()).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProspectCampaignCollectionView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    def get(self, request, *args, **kwargs):
        queryset = ProspectCampaign.objects.filter(organization=self.get_organization()).annotate(
            recipient_count=Count("recipients", distinct=True),
            step_count=Count("sequence_steps", distinct=True),
        )
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        campaign_status = request.query_params.get("status", "").strip()
        if campaign_status in ProspectCampaign.Status.values:
            queryset = queryset.filter(status=campaign_status)
        elif not campaign_status:
            queryset = queryset.exclude(status=ProspectCampaign.Status.ARCHIVED)
        queryset = queryset.order_by("-updated_at", "-id")
        paginator = ProspectingPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(CampaignSerializer(page, many=True).data)
        response.data["can_manage"] = OrganizationOperator().has_permission(request, self)
        response.data["can_admin"] = OrganizationAdmin().has_permission(request, self)
        return response

    def post(self, request, *args, **kwargs):
        name = str(request.data.get("name", "")).strip()
        if not name:
            raise serializers.ValidationError({"name": "Enter a campaign name."})
        try:
            campaign = create_campaign(
                organization=self.get_organization(),
                actor=request.user,
                name=name,
                list_ids=request.data.get("list_ids", []),
            )
        except DjangoValidationError as error:
            safe_validation(error)
        campaign.recipient_count = 0
        campaign.step_count = 0
        return Response(CampaignSerializer(campaign).data, status=status.HTTP_201_CREATED)


class ProspectCampaignDetailView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    def campaign(self):
        return get_object_or_404(
            ProspectCampaign.objects.select_related("organization").prefetch_related(
                "sequence_steps", "source_lists"
            ),
            organization=self.get_organization(),
            pk=self.kwargs["campaign_pk"],
        )

    def get(self, request, *args, **kwargs):
        campaign = self.campaign()
        recipients = campaign.recipients.select_related("company", "contact").order_by(
            "company_name"
        )
        paginator = ProspectingPagination()
        page = paginator.paginate_queryset(recipients, request, view=self)
        return Response(
            {
                "campaign": {
                    **CampaignSerializer(campaign).data,
                    "source_list_ids": list(campaign.source_lists.values_list("id", flat=True)),
                },
                "steps": SequenceStepSerializer(campaign.sequence_steps.all(), many=True).data,
                "readiness": campaign_readiness(campaign),
                "metrics": campaign_metrics(campaign),
                "recipients": CampaignRecipientSerializer(page, many=True).data,
                "recipient_count": paginator.page.paginator.count,
                "recipient_next": paginator.get_next_link(),
                "recipient_previous": paginator.get_previous_link(),
                "can_manage": OrganizationOperator().has_permission(request, self),
                "can_admin": OrganizationAdmin().has_permission(request, self),
            }
        )

    def delete(self, request, *args, **kwargs):
        campaign = self.campaign()
        try:
            outcome = remove_or_archive_campaign(campaign=campaign, actor=request.user)
        except DjangoValidationError as error:
            safe_validation(error)
        return Response(
            {
                "outcome": outcome,
                "detail": (
                    "Unused Draft campaign deleted."
                    if outcome == "deleted"
                    else "Campaign archived. Future sends were stopped and history was preserved."
                ),
            }
        )


class ProspectCampaignStepView(ProspectCampaignDetailView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        campaign = self.campaign()
        values = {
            "step_number": request.data.get("step_number"),
            "label": str(request.data.get("label", "")).strip(),
            "subject": str(request.data.get("subject", "")).strip(),
            "body": str(request.data.get("body", "")).strip(),
            "delay_minutes": request.data.get("delay_minutes", 0),
            "enabled": bool(request.data.get("enabled", True)),
        }
        step = None
        if self.kwargs.get("step_pk"):
            step = get_object_or_404(
                ProspectSequenceStep, campaign=campaign, pk=self.kwargs["step_pk"]
            )
        try:
            result = save_step(campaign=campaign, actor=request.user, values=values, step=step)
        except (DjangoValidationError, ValueError, TypeError) as error:
            if isinstance(error, DjangoValidationError):
                safe_validation(error)
            raise serializers.ValidationError("Enter valid sequence step values.") from error
        return Response(
            SequenceStepSerializer(result).data,
            status=status.HTTP_200_OK if step else status.HTTP_201_CREATED,
        )

    def delete(self, request, *args, **kwargs):
        campaign = self.campaign()
        step = get_object_or_404(
            ProspectSequenceStep, campaign=campaign, pk=self.kwargs.get("step_pk")
        )
        try:
            delete_step(campaign=campaign, actor=request.user, step=step)
        except DjangoValidationError as error:
            safe_validation(error)
        return Response({"detail": "Sequence step removed. Remaining steps were reordered."})


class ProspectCampaignSequenceActionView(ProspectCampaignDetailView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        campaign = self.campaign()
        action = self.kwargs["action"]
        try:
            if action == "reorder":
                ordered = [int(value) for value in request.data.get("ordered_step_ids", [])]
                steps = reorder_steps(
                    campaign=campaign, actor=request.user, ordered_step_ids=ordered
                )
                return Response(SequenceStepSerializer(steps, many=True).data)
            if action == "duplicate":
                step = get_object_or_404(
                    ProspectSequenceStep,
                    campaign=campaign,
                    pk=request.data.get("step_id"),
                )
                duplicate = duplicate_step(campaign=campaign, actor=request.user, step=step)
                return Response(
                    SequenceStepSerializer(duplicate).data,
                    status=status.HTTP_201_CREATED,
                )
        except (DjangoValidationError, ValueError, TypeError) as error:
            if isinstance(error, DjangoValidationError):
                safe_validation(error)
            raise serializers.ValidationError("Enter a valid sequence order.") from error
        raise serializers.ValidationError("Unsupported sequence action.")


class ProspectCampaignPreviewView(ProspectCampaignDetailView):
    permission_classes = (ActiveOrganizationMember,)

    def post(self, request, *args, **kwargs):
        campaign = self.campaign()
        step = get_object_or_404(
            ProspectSequenceStep, campaign=campaign, pk=request.data.get("step_id")
        )
        recipient = get_object_or_404(
            ProspectCampaignRecipient.objects.select_related("company").prefetch_related(
                "company__trade_capabilities"
            ),
            campaign=campaign,
            pk=request.data.get("recipient_id"),
        )
        try:
            preview = render_draft_preview(campaign=campaign, step=step, recipient=recipient)
        except DjangoValidationError as error:
            safe_validation(error)
        return Response(preview)


class ProspectCampaignTestEmailView(ProspectCampaignDetailView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        campaign = self.campaign()
        step = get_object_or_404(
            ProspectSequenceStep, campaign=campaign, pk=request.data.get("step_id")
        )
        recipient = None
        if request.data.get("recipient_id"):
            recipient = get_object_or_404(
                ProspectCampaignRecipient.objects.select_related("company").prefetch_related(
                    "company__trade_capabilities"
                ),
                campaign=campaign,
                pk=request.data.get("recipient_id"),
            )
        try:
            send_test_email(
                campaign=campaign,
                step=step,
                actor=request.user,
                test_email=request.data.get("test_email", ""),
                recipient=recipient,
            )
        except DjangoValidationError as error:
            safe_validation(error)
        return Response({"detail": "Test email sent. Campaign recipients were unchanged."})


class ProspectEmailTemplateCollectionView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    def get(self, request, *args, **kwargs):
        queryset = ProspectEmailTemplate.objects.filter(organization=self.get_organization())
        template_status = request.query_params.get("status", "active")
        queryset = queryset.filter(is_active=template_status != "archived")
        queryset = queryset.order_by("name", "id")[:100]
        return Response({"results": EmailTemplateSerializer(queryset, many=True).data})

    def post(self, request, *args, **kwargs):
        serializer = EmailTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .campaigns import validate_template

        try:
            validate_template(
                serializer.validated_data["subject"], serializer.validated_data["body"]
            )
            template = ProspectEmailTemplate.objects.create(
                organization=self.get_organization(),
                created_by=request.user,
                updated_by=request.user,
                **serializer.validated_data,
            )
        except DjangoValidationError as error:
            safe_validation(error)
        record_event(
            organization=template.organization,
            project=None,
            actor=request.user,
            action_code="prospecting.template.created",
            target=template,
            metadata={"template_id": template.pk},
        )
        return Response(EmailTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


class ProspectEmailTemplateDetailView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = (
            ActiveOrganizationMember if self.request.method == "GET" else OrganizationOperator
        )
        return [permission()]

    def template(self):
        return get_object_or_404(
            ProspectEmailTemplate,
            organization=self.get_organization(),
            pk=self.kwargs["template_pk"],
        )

    def patch(self, request, *args, **kwargs):
        template = self.template()
        previous_active = template.is_active
        serializer = EmailTemplateSerializer(template, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        from .campaigns import validate_template

        subject = serializer.validated_data.get("subject", template.subject)
        body = serializer.validated_data.get("body", template.body)
        try:
            validate_template(subject, body)
        except DjangoValidationError as error:
            safe_validation(error)
        serializer.save(updated_by=request.user)
        if request.data.get("is_active") is False:
            action = "prospect_template.archived"
        elif request.data.get("is_active") is True and not previous_active:
            action = "prospect_template.restored"
        else:
            action = "prospecting.template.updated"
        record_event(
            organization=template.organization,
            project=None,
            actor=request.user,
            action_code=action,
            target=template,
            metadata={"template_id": template.pk},
        )
        return Response(serializer.data)


class ProspectCampaignEnrollmentView(ProspectCampaignDetailView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        campaign = self.campaign()
        entry_ids = set(request.data.get("entry_ids", []))
        list_ids = set(request.data.get("list_ids", []))
        entries = ProspectListEntry.objects.filter(
            Q(pk__in=entry_ids) | Q(prospect_list_id__in=list_ids),
            prospect_list__organization=campaign.organization,
            is_active=True,
        ).distinct()
        if request.data.get("preview", False):
            counts, _ = enrollment_preview(
                campaign, list(entries.select_related("primary_contact"))
            )
            return Response(counts)
        try:
            counts, recipients = enroll_entries(
                campaign=campaign, entries=entries, actor=request.user
            )
        except DjangoValidationError as error:
            safe_validation(error)
        return Response({**counts, "recipient_ids": [item.pk for item in recipients]})


class ProspectCampaignActionView(ProspectCampaignDetailView):
    def get_permissions(self):
        permission = (
            OrganizationAdmin
            if self.kwargs.get("action") in {"approve", "launch"}
            else OrganizationOperator
        )
        return [permission()]

    def post(self, request, *args, **kwargs):
        campaign = self.campaign()
        action = self.kwargs["action"]
        try:
            if action == "approve":
                version = approve_campaign(campaign=campaign, actor=request.user)
                return Response({"campaign_version_id": version.pk, "status": "approved"})
            if action == "launch":
                launch_campaign(campaign=campaign, actor=request.user)
            elif action in {"pause", "resume"}:
                set_campaign_state(campaign=campaign, actor=request.user, action=action)
            elif action == "archive":
                outcome = remove_or_archive_campaign(campaign=campaign, actor=request.user)
                return Response({"outcome": outcome})
            elif action == "restore":
                restore_campaign(campaign=campaign, actor=request.user)
            else:
                raise serializers.ValidationError("Unsupported campaign action.")
        except DjangoValidationError as error:
            safe_validation(error)
        campaign.refresh_from_db()
        return Response({"status": campaign.status})


class ProspectCampaignRecipientCancelView(ProspectingContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        recipient = get_object_or_404(
            ProspectCampaignRecipient,
            campaign__organization=self.get_organization(),
            pk=self.kwargs["recipient_pk"],
        )
        if recipient.state not in {
            ProspectCampaignRecipient.State.PENDING,
            ProspectCampaignRecipient.State.SCHEDULED,
            ProspectCampaignRecipient.State.ACTIVE,
        }:
            raise serializers.ValidationError("This recipient is already stopped.")
        recipient.state = ProspectCampaignRecipient.State.CANCELLED
        recipient.next_due_at = None
        recipient.stop_reason = "Cancelled by user"
        recipient.save(update_fields=("state", "next_due_at", "stop_reason"))
        record_event(
            organization=recipient.campaign.organization,
            project=None,
            actor=request.user,
            action_code="prospecting_recipient.stopped",
            target=recipient,
            metadata={"campaign_id": recipient.campaign_id, "reason": "cancelled"},
        )
        return Response({"state": recipient.state})


class ProspectingSuppressionView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = ActiveOrganizationMember if self.request.method == "GET" else OrganizationAdmin
        return [permission()]

    def get(self, request, *args, **kwargs):
        queryset = ProspectSuppression.objects.filter(organization=self.get_organization())
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(normalized_email__icontains=search)
        active = request.query_params.get("active")
        if active in {"true", "false"}:
            queryset = queryset.filter(active=active == "true")
        paginator = ProspectingPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = [
            {
                "id": item.pk,
                "email": item.normalized_email,
                "reason": item.reason,
                "active": item.active,
                "created_at": item.created_at,
                "removed_at": item.removed_at,
            }
            for item in page
        ]
        response = paginator.get_paginated_response(data)
        response.data["can_admin"] = OrganizationAdmin().has_permission(request, self)
        return response

    def post(self, request, *args, **kwargs):
        try:
            suppression, created = suppress_email(
                organization=self.get_organization(),
                email=request.data.get("email"),
                reason=ProspectSuppression.Reason.MANUAL,
                actor=request.user,
            )
        except DjangoValidationError as error:
            safe_validation(error)
        return Response(
            {"id": suppression.pk, "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProspectingSuppressionRemoveView(ProspectingContextMixin, APIView):
    permission_classes = (OrganizationAdmin,)

    def post(self, request, *args, **kwargs):
        suppression = get_object_or_404(
            ProspectSuppression,
            organization=self.get_organization(),
            pk=self.kwargs["suppression_pk"],
        )
        remove_suppression(suppression=suppression, actor=request.user)
        return Response({"active": False, "re_enrolled": False})


class ProspectingSettingsView(ProspectingContextMixin, APIView):
    def get_permissions(self):
        permission = ActiveOrganizationMember if self.request.method == "GET" else OrganizationAdmin
        return [permission()]

    def get(self, request, *args, **kwargs):
        config = ProspectingSettings.objects.filter(organization=self.get_organization()).first()
        sender = getattr(self.get_organization(), "outreach_sender", None)
        return Response(
            {
                "is_enabled": bool(config and config.is_enabled),
                "max_sends_per_hour": config.max_sends_per_hour if config else 20,
                "max_sends_per_day": config.max_sends_per_day if config else 100,
                "sending_timezone": config.sending_timezone if config else "America/Toronto",
                "allowed_start_hour": config.allowed_start_hour if config else 9,
                "allowed_end_hour": config.allowed_end_hour if config else 17,
                "business_identity": config.business_identity if config else "",
                "compliance_footer": config.compliance_footer if config else "",
                "smtp": provider_status(self.get_organization()),
                "sender_configured": bool(sender and sender.is_enabled),
                "suppression_controls": "Suppression and unsubscribe controls enabled",
                "can_admin": OrganizationAdmin().has_permission(request, self),
            }
        )

    def patch(self, request, *args, **kwargs):
        config, _ = ProspectingSettings.objects.get_or_create(
            organization=self.get_organization(), defaults={"updated_by": request.user}
        )
        for field in (
            "is_enabled",
            "max_sends_per_hour",
            "max_sends_per_day",
            "sending_timezone",
            "allowed_start_hour",
            "allowed_end_hour",
            "business_identity",
            "compliance_footer",
        ):
            if field in request.data:
                setattr(config, field, request.data[field])
        config.updated_by = request.user
        try:
            config.full_clean()
            config.save()
        except DjangoValidationError as error:
            safe_validation(error)
        return self.get(request, *args, **kwargs)


class ProspectingProcessDueView(ProspectingContextMixin, APIView):
    permission_classes = (OrganizationAdmin,)

    def post(self, request, *args, **kwargs):
        return Response(
            process_due_prospecting_messages(
                limit=50,
                organization=self.get_organization(),
                return_summary=True,
            )
        )


class ProspectingAnalyticsView(ProspectingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        range_key, since = analytics_window(request.query_params.get("range"))
        organization = self.get_organization()
        return Response(
            {
                "range": range_key,
                "summary": metric_bundle(organization, since=since),
                "trend": trend_data(organization, since=since),
            }
        )


class ProspectingAnalyticsCampaignsView(ProspectingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        range_key, since = analytics_window(request.query_params.get("range"))
        rows = campaign_rows(
            self.get_organization(), since=since, sort=request.query_params.get("sort", "newest")
        )
        paginator = PageNumberPagination()
        paginator.page_size = 25
        paginator.max_page_size = 50
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response(page)
        response.data["range"] = range_key
        return response


class ProspectingAnalyticsCampaignDetailView(ProspectingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        range_key, since = analytics_window(request.query_params.get("range"))
        organization = self.get_organization()
        campaign = get_object_or_404(
            ProspectCampaign, organization=organization, pk=self.kwargs["campaign_pk"]
        )
        row = campaign_rows(organization, since=since, campaign_id=campaign.pk)[0]
        return Response(
            {
                "range": range_key,
                "campaign": row,
                "steps": sequence_step_rows(organization, campaign, since),
            }
        )


class ProspectingAnalyticsRecipientsView(ProspectingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        range_key, since = analytics_window(request.query_params.get("range"))
        campaign_id = request.query_params.get("campaign")
        if campaign_id and not str(campaign_id).isdigit():
            raise serializers.ValidationError({"campaign": "Select a valid campaign."})
        rows = recipient_rows(
            self.get_organization(),
            since=since,
            campaign_id=int(campaign_id) if campaign_id else None,
            engagement=request.query_params.get("engagement", "all"),
            search=request.query_params.get("search", "")[:200],
        )
        paginator = PageNumberPagination()
        paginator.page_size = 25
        paginator.max_page_size = 50
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response(page)
        response.data["range"] = range_key
        return response


class ProspectingAnalyticsRecipientDetailView(ProspectingContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        recipient = get_object_or_404(
            ProspectCampaignRecipient.objects.select_related("campaign"),
            campaign__organization=organization,
            pk=self.kwargs["recipient_pk"],
        )
        suppression = ProspectSuppression.objects.filter(
            organization=organization,
            normalized_email=recipient.normalized_email,
            active=True,
        ).first()
        return Response(
            {
                "recipient": {
                    "id": recipient.pk,
                    "name": recipient.contact_name,
                    "company": recipient.company_name,
                    "email": recipient.normalized_email,
                    "campaign": {"id": recipient.campaign_id, "name": recipient.campaign.name},
                    "state": recipient.state,
                    "current_step": recipient.current_step,
                    "next_due_at": recipient.next_due_at,
                    "reply_state": "replied" if recipient.replies.exists() else "no_reply",
                    "suppression": suppression.reason if suppression else None,
                    "unsubscribed": bool(
                        suppression and suppression.reason == ProspectSuppression.Reason.UNSUBSCRIBE
                    ),
                },
                "timeline": recipient_timeline(organization, recipient),
            }
        )


class PublicProspectUnsubscribeView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request, token, *args, **kwargs):
        record = unsubscribe_token(token)
        if record is None:
            return Response({"state": "invalid"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"state": "already_unsubscribed" if record.used_at else "confirm"})

    def post(self, request, token, *args, **kwargs):
        suppression, created = unsubscribe(token)
        if suppression is None:
            return Response({"state": "invalid"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"state": "unsubscribed" if created else "already_unsubscribed"})
