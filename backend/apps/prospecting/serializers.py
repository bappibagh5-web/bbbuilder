from rest_framework import serializers

from apps.contractors.serializers import ContactSerializer
from apps.scope_packages.trades import TRADE_CHOICES

from .models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectEmailTemplate,
    ProspectingDiscoveryResult,
    ProspectList,
    ProspectListEntry,
    ProspectSequenceStep,
)


class ProspectListSerializer(serializers.ModelSerializer):
    prospect_count = serializers.IntegerField(read_only=True)
    contact_ready_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProspectList
        fields = (
            "id",
            "name",
            "description",
            "status",
            "prospect_count",
            "contact_ready_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ProspectEntrySerializer(serializers.ModelSerializer):
    company = serializers.SerializerMethodField()
    primary_contact = ContactSerializer(read_only=True)
    tags = serializers.SerializerMethodField()

    def get_company(self, entry):
        company = entry.company
        return {
            "id": company.pk,
            "display_name": company.display_name,
            "website": company.website,
            "phone": company.phone,
            "email": company.email,
            "city": company.city,
            "province": company.province,
            "country": company.country,
            "source_type": company.source_type,
            "trades": [
                {"trade_key": item.trade_key, "trade_label": item.get_trade_key_display()}
                for item in company.trade_capabilities.all()
                if item.is_active
            ],
            "contacts": ContactSerializer(company.contacts.all(), many=True).data,
        }

    def get_tags(self, entry):
        return [{"id": tag.pk, "name": tag.name} for tag in entry.tags.all()]

    class Meta:
        model = ProspectListEntry
        fields = (
            "id",
            "company",
            "primary_contact",
            "status",
            "source_type",
            "source_reference",
            "source_url",
            "notes",
            "tags",
            "added_at",
            "updated_at",
        )
        read_only_fields = fields


class DiscoveryResultSerializer(serializers.ModelSerializer):
    already_in_directory = serializers.SerializerMethodField()
    already_on_selected_list = serializers.SerializerMethodField()

    def get_already_in_directory(self, result):
        return result.company_id is not None

    def get_already_on_selected_list(self, result):
        return bool(
            result.company_id
            and result.company_id in self.context.get("selected_list_company_ids", set())
        )

    class Meta:
        model = ProspectingDiscoveryResult
        fields = (
            "id",
            "display_name",
            "website",
            "phone",
            "address",
            "city",
            "province",
            "postal_code",
            "country",
            "source_url",
            "provider_metadata",
            "already_in_directory",
            "already_on_selected_list",
        )
        read_only_fields = fields


class DiscoveryInputSerializer(serializers.Serializer):
    trade_key = serializers.ChoiceField(choices=TRADE_CHOICES)
    query = serializers.CharField(max_length=200, required=False, allow_blank=True)
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, max_length=10
    )
    city = serializers.CharField(max_length=120)
    province = serializers.CharField(max_length=80)
    country = serializers.CharField(max_length=80)
    radius_miles = serializers.IntegerField(min_value=1, max_value=200, required=False)
    prospect_list_id = serializers.IntegerField(min_value=1, required=False)


class EntryUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ProspectListEntry.Status, required=False)
    notes = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    primary_contact_id = serializers.IntegerField(min_value=1, required=False)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=80), required=False, max_length=20
    )


class AddResultsSerializer(serializers.Serializer):
    prospect_list_id = serializers.IntegerField(min_value=1)
    result_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), min_length=1, max_length=100
    )


class ManualProspectSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    company = serializers.CharField(max_length=255, required=False, allow_blank=True)
    trade = serializers.ChoiceField(choices=TRADE_CHOICES, required=False, allow_blank=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=80), required=False, max_length=20
    )
    notes = serializers.CharField(max_length=5000, required=False, allow_blank=True)


class CampaignSerializer(serializers.ModelSerializer):
    recipient_count = serializers.IntegerField(read_only=True, default=0)
    step_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ProspectCampaign
        fields = (
            "id",
            "name",
            "status",
            "recipient_count",
            "step_count",
            "approved_at",
            "launched_at",
            "paused_at",
            "completed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class SequenceStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProspectSequenceStep
        fields = (
            "id",
            "step_number",
            "label",
            "subject",
            "body",
            "delay_minutes",
            "enabled",
        )
        read_only_fields = fields


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProspectEmailTemplate
        fields = (
            "id",
            "name",
            "category",
            "subject",
            "body",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class CampaignRecipientSerializer(serializers.ModelSerializer):
    company_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProspectCampaignRecipient
        fields = (
            "id",
            "company_id",
            "company_name",
            "contact_name",
            "contact_title",
            "normalized_email",
            "state",
            "current_step",
            "next_due_at",
            "last_sent_at",
            "stop_reason",
            "enrolled_at",
        )
        read_only_fields = fields
