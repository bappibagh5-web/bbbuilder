# ruff: noqa: E501
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.contractors.models import Company, Contact
from apps.documents.models import ImmutableFieldsMixin
from apps.organizations.models import Organization
from apps.scope_packages.trades import TRADE_CHOICES


class ProspectList(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="prospect_lists"
    )
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_prospect_lists"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"), name="prospecting_unique_list_name"
            )
        ]


class ProspectTag(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="prospect_tags"
    )
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"), name="prospecting_unique_tag_name"
            )
        ]


class ProspectListEntry(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWING = "reviewing", "Reviewing"
        CONTACT_READY = "contact_ready", "Contact ready"
        NOT_A_FIT = "not_a_fit", "Not a fit"
        SUPPRESSED = "suppressed", "Suppressed"

    prospect_list = models.ForeignKey(
        ProspectList, on_delete=models.PROTECT, related_name="entries"
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="prospect_entries")
    primary_contact = models.ForeignKey(
        Contact,
        on_delete=models.PROTECT,
        related_name="primary_prospect_entries",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=24, choices=Status, default=Status.NEW)
    source_type = models.CharField(max_length=40, blank=True)
    source_reference = models.CharField(max_length=255, blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    source_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    tags = models.ManyToManyField(ProspectTag, through="ProspectListEntryTag", blank=True)
    is_active = models.BooleanField(default=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="removed_prospect_list_entries",
        null=True,
        blank=True,
    )
    removed_at = models.DateTimeField(null=True, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="added_prospects"
    )
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("company__display_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("prospect_list", "company"), name="prospecting_unique_list_company"
            )
        ]

    def clean(self):
        super().clean()
        organization_id = self.prospect_list.organization_id
        if self.company.organization_id != organization_id:
            raise ValidationError("Prospect company must belong to the list organization.")
        if self.primary_contact_id and self.primary_contact.company_id != self.company_id:
            raise ValidationError("Primary contact must belong to the prospect company.")
        if self.status == self.Status.CONTACT_READY:
            contact = self.primary_contact
            if contact is None or not contact.is_active or not contact.email:
                raise ValidationError(
                    "Contact ready requires an active selected contact with an email address."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProspectListEntryTag(models.Model):
    entry = models.ForeignKey(ProspectListEntry, on_delete=models.CASCADE)
    tag = models.ForeignKey(ProspectTag, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entry", "tag"), name="prospecting_unique_entry_tag")
        ]


class ProspectingDiscoveryRun(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="prospecting_discovery_runs"
    )
    query = models.CharField(max_length=200)
    trade_key = models.CharField(max_length=100, choices=TRADE_CHOICES)
    keywords = models.JSONField(default=list, blank=True)
    city = models.CharField(max_length=120)
    province = models.CharField(max_length=80)
    country = models.CharField(max_length=80)
    radius_miles = models.PositiveIntegerField(null=True, blank=True)
    provider = models.CharField(max_length=50)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prospecting_discovery_runs",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    result_count = models.PositiveIntegerField(default=0)
    provider_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-requested_at", "-id")


class ProspectingDiscoveryResult(models.Model):
    run = models.ForeignKey(
        ProspectingDiscoveryRun, on_delete=models.PROTECT, related_name="results"
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="prospecting_discovery_results",
        null=True,
        blank=True,
    )
    display_name = models.CharField(max_length=255)
    website = models.URLField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    province = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=80, blank=True)
    external_place_id = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    source_url = models.URLField(blank=True)
    provider_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("display_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("run", "external_place_id"),
                name="prospecting_unique_run_provider_result",
            )
        ]


class ProspectImport(models.Model):
    class Status(models.TextChoices):
        PREVIEWED = "previewed", "Previewed"
        COMPLETED = "completed", "Completed"

    class FileType(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "Excel workbook"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="prospect_imports"
    )
    prospect_list = models.ForeignKey(
        ProspectList, on_delete=models.PROTECT, related_name="imports"
    )
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=12, choices=FileType)
    file_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status, default=Status.PREVIEWED)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    warning_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    preview_rows = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prospect_imports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def clean(self):
        super().clean()
        if self.prospect_list.organization_id != self.organization_id:
            raise ValidationError("Prospect import must belong to the list organization.")


class ProspectingSettings(models.Model):
    organization = models.OneToOneField(
        Organization, on_delete=models.PROTECT, related_name="prospecting_settings"
    )
    is_enabled = models.BooleanField(default=False)
    max_sends_per_hour = models.PositiveIntegerField(default=20)
    max_sends_per_day = models.PositiveIntegerField(default=100)
    sending_timezone = models.CharField(max_length=64, default="America/Toronto")
    allowed_start_hour = models.PositiveSmallIntegerField(
        default=9, validators=[MinValueValidator(0), MaxValueValidator(23)]
    )
    allowed_end_hour = models.PositiveSmallIntegerField(
        default=17, validators=[MinValueValidator(1), MaxValueValidator(24)]
    )
    business_identity = models.CharField(max_length=255, blank=True)
    compliance_footer = models.TextField(blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.allowed_start_hour >= self.allowed_end_hour:
            raise ValidationError("Sending end hour must be after the start hour.")
        try:
            ZoneInfo(self.sending_timezone)
        except ZoneInfoNotFoundError as error:
            raise ValidationError({"sending_timezone": "Enter a valid IANA timezone."}) from error


class ProspectCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="prospect_campaigns"
    )
    name = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    source_lists = models.ManyToManyField(ProspectList, blank=True, related_name="campaigns")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_prospect_campaigns",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_prospect_campaigns",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    launched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="launched_prospect_campaigns",
    )
    launched_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"), name="prospecting_unique_campaign_name"
            )
        ]


class ProspectSequenceStep(models.Model):
    campaign = models.ForeignKey(
        ProspectCampaign, on_delete=models.PROTECT, related_name="sequence_steps"
    )
    step_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    label = models.CharField(max_length=100, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    delay_minutes = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("step_number", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "step_number"), name="prospecting_unique_sequence_step"
            )
        ]

    def clean(self):
        super().clean()
        if self.campaign.status != ProspectCampaign.Status.DRAFT:
            raise ValidationError("Only a Draft campaign sequence can be edited.")
        if self.step_number == 1 and self.delay_minutes != 0:
            raise ValidationError("The first sequence step must have zero delay.")
        if self.step_number > 1 and self.delay_minutes < 1:
            raise ValidationError("Follow-up steps require a positive delay.")


class ProspectCampaignVersion(ImmutableFieldsMixin):
    campaign = models.ForeignKey(
        ProspectCampaign, on_delete=models.PROTECT, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    sender_name = models.CharField(max_length=255)
    from_address = models.EmailField()
    reply_to = models.EmailField()
    business_identity = models.CharField(max_length=255)
    compliance_footer = models.TextField()
    sequence_fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "version_number"), name="prospecting_unique_campaign_version"
            )
        ]

    immutable_fields = (
        "campaign_id",
        "version_number",
        "sender_name",
        "from_address",
        "reply_to",
        "business_identity",
        "compliance_footer",
        "sequence_fingerprint",
        "created_by_id",
        "created_at",
    )


class ProspectSequenceStepVersion(ImmutableFieldsMixin):
    campaign_version = models.ForeignKey(
        ProspectCampaignVersion, on_delete=models.PROTECT, related_name="steps"
    )
    step_number = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=100, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    delay_minutes = models.PositiveIntegerField()

    class Meta:
        ordering = ("step_number", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("campaign_version", "step_number"),
                name="prospecting_unique_step_version",
            )
        ]

    immutable_fields = (
        "campaign_version_id",
        "step_number",
        "label",
        "subject",
        "body",
        "delay_minutes",
    )


class ProspectEmailTemplate(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="prospect_email_templates"
    )
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=100, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_prospect_email_templates",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_prospect_email_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"),
                name="prospecting_unique_email_template_name",
            )
        ]


class ProspectCampaignRecipient(models.Model):
    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        SCHEDULED = "scheduled", "Scheduled"
        ACTIVE = "active", "Active"
        REPLIED = "replied", "Replied"
        COMPLETED = "completed", "Completed"
        BOUNCED = "bounced", "Bounced"
        COMPLAINED = "complained", "Complained"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"
        SUPPRESSED = "suppressed", "Suppressed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    campaign = models.ForeignKey(
        ProspectCampaign, on_delete=models.PROTECT, related_name="recipients"
    )
    campaign_version = models.ForeignKey(
        ProspectCampaignVersion,
        on_delete=models.PROTECT,
        related_name="recipients",
        null=True,
        blank=True,
    )
    prospect_entry = models.ForeignKey(
        ProspectListEntry, on_delete=models.PROTECT, related_name="campaign_enrollments"
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    contact = models.ForeignKey(Contact, on_delete=models.PROTECT)
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255)
    contact_title = models.CharField(max_length=255, blank=True)
    normalized_email = models.EmailField()
    state = models.CharField(max_length=24, choices=State, default=State.PENDING)
    current_step = models.PositiveSmallIntegerField(default=0)
    next_due_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    stop_reason = models.CharField(max_length=255, blank=True)
    enrolled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("company_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "normalized_email"),
                name="prospecting_unique_campaign_email",
            )
        ]

    def clean(self):
        super().clean()
        if self.prospect_entry.prospect_list.organization_id != self.campaign.organization_id:
            raise ValidationError("Prospect entry must belong to the campaign organization.")
        if self.company_id != self.prospect_entry.company_id:
            raise ValidationError("Recipient company must match the prospect entry.")
        if self.contact.company_id != self.company_id or not self.contact.is_active:
            raise ValidationError("Recipient requires an active contact from the same company.")
        if self.prospect_entry.status != ProspectListEntry.Status.CONTACT_READY:
            raise ValidationError("Only Contact ready prospects can be enrolled.")


class ProspectMessage(ImmutableFieldsMixin):
    recipient = models.ForeignKey(
        ProspectCampaignRecipient, on_delete=models.PROTECT, related_name="messages"
    )
    step_version = models.ForeignKey(
        ProspectSequenceStepVersion, on_delete=models.PROTECT, related_name="messages"
    )
    from_name = models.CharField(max_length=255)
    from_address = models.EmailField()
    reply_to = models.EmailField()
    to_address = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    unsubscribe_url = models.URLField(max_length=500)
    rfc_message_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "step_version"), name="prospecting_unique_recipient_step"
            ),
            models.UniqueConstraint(
                fields=("rfc_message_id",), name="prospecting_unique_rfc_message_id"
            ),
        ]

    immutable_fields = (
        "recipient_id",
        "step_version_id",
        "from_name",
        "from_address",
        "reply_to",
        "to_address",
        "subject",
        "body",
        "unsubscribe_url",
        "rfc_message_id",
        "created_at",
    )


class ProspectDeliveryAttempt(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        UNCERTAIN = "uncertain", "Outcome uncertain"

    message = models.ForeignKey(ProspectMessage, on_delete=models.PROTECT, related_name="attempts")
    sequence = models.PositiveIntegerField()
    provider_key = models.CharField(max_length=40)
    idempotency_key = models.CharField(max_length=100, unique=True)
    rfc_message_id = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status, default=Status.PENDING)
    attempted_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    safe_error_code = models.CharField(max_length=80, blank=True)
    safe_error_message = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("message", "sequence"), name="prospecting_unique_attempt_sequence"
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            if previous.status != self.Status.PENDING or self.status not in {
                self.Status.SUCCEEDED,
                self.Status.FAILED,
                self.Status.UNCERTAIN,
            }:
                raise ValidationError("Completed delivery attempts are immutable.")
        return super().save(*args, **kwargs)


class ProspectProviderEmail(ImmutableFieldsMixin):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    message = models.ForeignKey(ProspectMessage, on_delete=models.PROTECT)
    provider_email_id = models.CharField(max_length=120)
    rfc_message_id = models.CharField(max_length=255)
    provider_event = models.ForeignKey(
        "outreach.ResendWebhookEvent", on_delete=models.PROTECT, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "provider_email_id"),
                name="prospecting_unique_provider_email",
            ),
            models.UniqueConstraint(
                fields=("organization", "rfc_message_id"),
                name="prospecting_unique_provider_rfc",
            ),
        ]

    immutable_fields = (
        "organization_id",
        "message_id",
        "provider_email_id",
        "rfc_message_id",
        "provider_event_id",
        "created_at",
    )


class ProspectReply(ImmutableFieldsMixin):
    recipient = models.ForeignKey(
        ProspectCampaignRecipient, on_delete=models.PROTECT, related_name="replies"
    )
    message = models.ForeignKey(ProspectMessage, on_delete=models.PROTECT)
    provider_event = models.OneToOneField(
        "outreach.ResendWebhookEvent", on_delete=models.PROTECT, related_name="prospect_reply"
    )
    provider_reference = models.CharField(max_length=120, unique=True)
    from_address = models.EmailField()
    to_address = models.EmailField()
    subject = models.CharField(max_length=255, blank=True)
    body_text = models.TextField(blank=True)
    in_reply_to = models.CharField(max_length=255)
    references = models.CharField(max_length=1000, blank=True)
    received_at = models.DateTimeField()

    immutable_fields = (
        "recipient_id",
        "message_id",
        "provider_event_id",
        "provider_reference",
        "from_address",
        "to_address",
        "subject",
        "body_text",
        "in_reply_to",
        "references",
        "received_at",
    )


class ProspectSuppression(models.Model):
    class Reason(models.TextChoices):
        UNSUBSCRIBE = "unsubscribe", "Unsubscribe"
        HARD_BOUNCE = "hard_bounce", "Hard bounce"
        COMPLAINT = "complaint", "Complaint"
        MANUAL = "manual", "Manual"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="prospect_suppressions"
    )
    normalized_email = models.EmailField()
    reason = models.CharField(max_length=20, choices=Reason)
    source_recipient = models.ForeignKey(
        ProspectCampaignRecipient, on_delete=models.PROTECT, null=True, blank=True
    )
    source_message = models.ForeignKey(
        ProspectMessage, on_delete=models.PROTECT, null=True, blank=True
    )
    provider_event = models.ForeignKey(
        "outreach.ResendWebhookEvent", on_delete=models.PROTECT, null=True, blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="removed_prospect_suppressions",
    )
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "normalized_email"),
                condition=models.Q(active=True),
                name="prospecting_unique_active_suppression",
            )
        ]


class ProspectUnsubscribeToken(models.Model):
    recipient = models.ForeignKey(
        ProspectCampaignRecipient, on_delete=models.PROTECT, related_name="unsubscribe_tokens"
    )
    token_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
