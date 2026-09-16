import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.contractors.models import ScopeContractorCandidate
from apps.documents.models import ImmutableFieldsMixin
from apps.scope_packages.models import ScopeItem, ScopePackage, ScopePackageVersion


class InvitationCampaign(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PREPARED = "prepared", "Prepared"
        CLOSED = "closed", "Closed"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT)
    scope_package = models.ForeignKey(ScopePackage, on_delete=models.PROTECT)
    scope_version = models.ForeignKey(ScopePackageVersion, on_delete=models.PROTECT)
    trade_key = models.CharField(max_length=100)
    trade_category = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    bid_deadline = models.DateTimeField(null=True, blank=True)
    questions_deadline = models.DateTimeField(null=True, blank=True)
    setup_version = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "organization_id",
        "project_id",
        "scope_package_id",
        "scope_version_id",
        "trade_key",
        "trade_category",
        "created_by_id",
        "created_at",
    )

    def clean(self):
        super().clean()
        if self.project.organization_id != self.organization_id:
            raise ValidationError("Campaign organization must match its project.")
        if self.scope_package.project_id != self.project_id:
            raise ValidationError("Campaign scope must belong to its project.")
        if self.scope_version.package_id != self.scope_package_id:
            raise ValidationError("Campaign version must belong to its scope package.")
        if not self.pk:
            if not self.project.is_active:
                raise ValidationError("Archived projects cannot prepare outreach campaigns.")
            if self.scope_package.lifecycle != ScopePackage.Lifecycle.ACTIVE:
                raise ValidationError("Campaign requires an Active scope package.")
            if self.scope_package.current_version_id != self.scope_version_id:
                raise ValidationError("Campaign requires the current scope version.")
            if self.scope_version.status != ScopePackageVersion.Status.READY:
                raise ValidationError("Campaign requires a Ready scope version.")
            if (self.trade_key, self.trade_category) != (
                self.scope_package.trade_key,
                self.scope_package.trade_category,
            ):
                raise ValidationError("Campaign trade snapshot must match its scope package.")
        if (
            self.questions_deadline
            and self.bid_deadline
            and self.questions_deadline >= self.bid_deadline
        ):
            raise ValidationError("Questions deadline must be before the bid deadline.")


class OutreachSenderSettings(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.PROTECT, related_name="outreach_sender"
    )
    display_name = models.CharField(max_length=255)
    from_address = models.EmailField()
    reply_to = models.EmailField()
    is_enabled = models.BooleanField(default=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if any(character in self.display_name for character in "\r\n"):
            raise ValidationError("Sender display name cannot contain line breaks.")


class OutreachSMTPConfiguration(models.Model):
    class Security(models.TextChoices):
        STARTTLS = "starttls", "STARTTLS"
        SSL = "ssl", "SSL"
        NONE = "none", "None"

    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.PROTECT, related_name="outreach_smtp"
    )
    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=255, blank=True)
    encrypted_password = models.TextField(blank=True)
    security = models.CharField(max_length=12, choices=Security, default=Security.STARTTLS)
    timeout_seconds = models.PositiveSmallIntegerField(default=20)
    is_enabled = models.BooleanField(default=False)
    last_test_status = models.CharField(max_length=40, blank=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if not 1 <= self.port <= 65535:
            raise ValidationError("Enter a valid SMTP port.")
        if not 1 <= self.timeout_seconds <= 120:
            raise ValidationError("Connection timeout must be between 1 and 120 seconds.")
        if self.security == self.Security.NONE and self.is_enabled:
            raise ValidationError("Enable STARTTLS or SSL before enabling email delivery.")


class CampaignSetupEvent(ImmutableFieldsMixin):
    campaign = models.ForeignKey(
        InvitationCampaign, on_delete=models.PROTECT, related_name="setup_events"
    )
    version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    bid_deadline = models.DateTimeField(null=True, blank=True)
    questions_deadline = models.DateTimeField(null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    occurred_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "campaign_id",
        "version",
        "bid_deadline",
        "questions_deadline",
        "actor_id",
        "occurred_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "version"), name="outreach_unique_setup_version"
            )
        ]


class InvitationBatch(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        PREPARED = "prepared", "Prepared"
        CLOSED = "closed", "Closed"

    campaign = models.ForeignKey(
        InvitationCampaign, on_delete=models.PROTECT, related_name="batches"
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=Status, default=Status.PREPARED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("campaign_id", "sequence", "created_by_id", "created_at")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "sequence"), name="outreach_unique_batch_sequence"
            )
        ]


class InvitationRecipient(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        PREPARED = "prepared", "Prepared"
        CANCELLED = "cancelled", "Cancelled"
        INVITED = "invited", "Invited"
        DELIVERED = "delivered", "Delivered"
        OPENED = "opened", "Opened"
        RESPONDED = "responded", "Responded"
        BID_SUBMITTED = "bid_submitted", "Quote received"
        DECLINED = "declined", "Declined"
        FAILED = "failed", "Failed"
        NEEDS_FOLLOW_UP = "needs_follow_up", "Needs follow-up"

    batch = models.ForeignKey(InvitationBatch, on_delete=models.PROTECT, related_name="recipients")
    candidate = models.ForeignKey(ScopeContractorCandidate, on_delete=models.PROTECT)
    company = models.ForeignKey("contractors.Company", on_delete=models.PROTECT)
    contact = models.ForeignKey("contractors.Contact", on_delete=models.PROTECT)
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255)
    contact_title = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    current_status = models.CharField(max_length=20, choices=Status, default=Status.PREPARED)
    delivery_state = models.CharField(max_length=20, default="not_sent")
    delivery_event_at = models.DateTimeField(null=True, blank=True)
    engagement_state = models.CharField(max_length=20, default="none")
    engagement_event_at = models.DateTimeField(null=True, blank=True)
    response_state = models.CharField(max_length=20, default="no_response")
    qualification_state = models.CharField(max_length=20, default="not_reviewed")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "batch_id",
        "candidate_id",
        "company_id",
        "contact_id",
        "company_name",
        "contact_name",
        "contact_title",
        "email",
        "phone",
        "created_by_id",
        "created_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "candidate"), name="outreach_unique_batch_candidate"
            )
        ]

    def clean(self):
        super().clean()
        campaign = self.batch.campaign
        if (
            self.candidate.project_id != campaign.project_id
            or self.candidate.scope_package_id != campaign.scope_package_id
            or self.candidate.scope_version_id != campaign.scope_version_id
            or self.candidate.company_id != self.company_id
            or self.company.organization_id != campaign.organization_id
        ):
            raise ValidationError(
                "Recipient candidate must match campaign scope, project, and company."
            )
        if self.contact.company_id != self.company_id:
            raise ValidationError("Selected contact must belong to recipient company.")
        if not self.pk:
            if self.candidate.status != ScopeContractorCandidate.Status.APPROVED:
                raise ValidationError("Candidate must be approved for outreach.")
            if not self.contact.is_active or not self.contact.email:
                raise ValidationError("Select an active contact with an email address.")
            if (
                self.company_name != self.company.display_name
                or self.contact_name != self.contact.name
                or self.contact_title != self.contact.title
                or self.email != self.contact.email
                or self.phone != self.contact.phone
            ):
                raise ValidationError(
                    "Recipient identity must snapshot the selected company/contact."
                )

    def save(self, *args, **kwargs):
        if (
            self.pk
            and type(self)
            .objects.filter(pk=self.pk)
            .exclude(current_status=self.current_status)
            .exists()
        ):
            raise ValidationError("Recipient status changes require a status event service.")
        return super().save(*args, **kwargs)


class InvitationRecipientStatusEvent(ImmutableFieldsMixin):
    recipient = models.ForeignKey(
        InvitationRecipient, on_delete=models.PROTECT, related_name="status_events"
    )
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, choices=InvitationRecipient.Status)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    source = models.CharField(max_length=20, default="human")
    reason = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "recipient_id",
        "previous_status",
        "new_status",
        "actor_id",
        "source",
        "reason",
        "occurred_at",
    )

    class Meta:
        ordering = ("occurred_at", "id")


class OutreachMessage(ImmutableFieldsMixin):
    class Kind(models.TextChoices):
        INVITATION = "invitation", "Invitation"
        REVISION = "revision", "Revision"

    recipient = models.ForeignKey(
        InvitationRecipient, on_delete=models.PROTECT, related_name="messages"
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    channel = models.CharField(max_length=20, default="email", choices=[("email", "Email")])
    kind = models.CharField(max_length=20, choices=Kind)
    from_name = models.CharField(max_length=255)
    from_address = models.EmailField()
    reply_to = models.EmailField(blank=True)
    to_address = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    template_version = models.PositiveIntegerField(default=3)
    source_scope_version = models.ForeignKey(
        ScopePackageVersion, on_delete=models.PROTECT, null=True, blank=True
    )
    campaign_setup_version = models.PositiveIntegerField(default=0)
    bid_deadline = models.DateTimeField(null=True, blank=True)
    questions_deadline = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "recipient_id",
        "sequence",
        "channel",
        "kind",
        "from_name",
        "from_address",
        "reply_to",
        "to_address",
        "subject",
        "body",
        "template_version",
        "source_scope_version_id",
        "campaign_setup_version",
        "bid_deadline",
        "questions_deadline",
        "created_by_id",
        "created_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "sequence"), name="outreach_unique_message_sequence"
            )
        ]

    def clean(self):
        super().clean()
        if self.to_address != self.recipient.email:
            raise ValidationError("Prepared message must use the frozen recipient email address.")


class BatchSendApproval(ImmutableFieldsMixin):
    batch = models.ForeignKey(
        InvitationBatch, on_delete=models.PROTECT, related_name="send_approvals"
    )
    message_fingerprint = models.CharField(max_length=64, default="")
    campaign_setup_version = models.PositiveIntegerField(default=0)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "batch_id",
        "message_fingerprint",
        "campaign_setup_version",
        "approved_by_id",
        "approved_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "message_fingerprint"), name="outreach_unique_send_approval_state"
            )
        ]


class OutreachDeliveryAttempt(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        UNCERTAIN = "uncertain", "Outcome uncertain"

    message = models.ForeignKey(OutreachMessage, on_delete=models.PROTECT, related_name="attempts")
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    provider_key = models.CharField(max_length=40)
    idempotency_key = models.CharField(max_length=100)
    submitted_rfc_message_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.PENDING)
    attempted_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    safe_error_code = models.CharField(max_length=80, blank=True)
    safe_error_message = models.CharField(max_length=255, blank=True)

    immutable_fields = (
        "message_id",
        "sequence",
        "provider_key",
        "idempotency_key",
        "submitted_rfc_message_id",
        "attempted_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("message", "sequence"), name="outreach_unique_delivery_attempt_sequence"
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if (
                old.status != self.Status.PENDING
                or self.status
                not in {self.Status.SUCCEEDED, self.Status.FAILED, self.Status.UNCERTAIN}
                or old.completed_at is not None
            ):
                raise ValidationError("Completed delivery attempts are immutable.")
        return super().save(*args, **kwargs)


class ResendWebhookConfiguration(models.Model):
    organization = models.OneToOneField(
        "organizations.Organization", on_delete=models.PROTECT, related_name="resend_webhook"
    )
    endpoint_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    encrypted_signing_secret = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)


class ResendWebhookEvent(ImmutableFieldsMixin):
    configuration = models.ForeignKey(ResendWebhookConfiguration, on_delete=models.PROTECT)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    webhook_id = models.CharField(max_length=120)
    event_type = models.CharField(max_length=40)
    provider_email_id = models.CharField(max_length=120, blank=True)
    rfc_message_id = models.CharField(max_length=255, blank=True)
    message = models.ForeignKey(OutreachMessage, on_delete=models.PROTECT, null=True, blank=True)
    recipient = models.ForeignKey(
        InvitationRecipient, on_delete=models.PROTECT, null=True, blank=True
    )
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "configuration_id",
        "organization_id",
        "webhook_id",
        "event_type",
        "provider_email_id",
        "rfc_message_id",
        "message_id",
        "recipient_id",
        "occurred_at",
        "received_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("configuration", "webhook_id"), name="outreach_unique_resend_event"
            )
        ]


class OutreachProviderEmail(ImmutableFieldsMixin):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    message = models.ForeignKey(OutreachMessage, on_delete=models.PROTECT)
    provider_email_id = models.CharField(max_length=120)
    rfc_message_id = models.CharField(max_length=255)
    first_event = models.ForeignKey(ResendWebhookEvent, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "organization_id",
        "message_id",
        "provider_email_id",
        "rfc_message_id",
        "first_event_id",
        "created_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "provider_email_id"), name="outreach_unique_provider_email"
            ),
            models.UniqueConstraint(
                fields=("organization", "rfc_message_id"),
                name="outreach_unique_provider_message_id",
            ),
        ]


class OutreachResponse(ImmutableFieldsMixin):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, null=True, blank=True)
    recipient = models.ForeignKey(
        InvitationRecipient, on_delete=models.PROTECT, null=True, blank=True
    )
    message = models.ForeignKey(OutreachMessage, on_delete=models.PROTECT, null=True, blank=True)
    provider_event = models.OneToOneField(
        ResendWebhookEvent, on_delete=models.PROTECT, null=True, blank=True
    )
    provider_email_id = models.CharField(max_length=120, blank=True)
    rfc_message_id = models.CharField(max_length=255, blank=True)
    in_reply_to = models.CharField(max_length=255, blank=True)
    references = models.CharField(max_length=1000, blank=True)
    from_address = models.EmailField(blank=True)
    to_address = models.EmailField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    body_text = models.TextField(blank=True)
    content_status = models.CharField(max_length=20, default="not_applicable")
    attachment_count = models.PositiveIntegerField(default=0)
    channel = models.CharField(max_length=20)
    outcome = models.CharField(max_length=20, default="responded")
    note = models.CharField(max_length=1000, blank=True)
    occurred_at = models.DateTimeField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "organization_id",
        "project_id",
        "recipient_id",
        "message_id",
        "provider_event_id",
        "provider_email_id",
        "rfc_message_id",
        "in_reply_to",
        "references",
        "from_address",
        "to_address",
        "subject",
        "body_text",
        "content_status",
        "attachment_count",
        "channel",
        "outcome",
        "note",
        "occurred_at",
        "actor_id",
        "created_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "provider_email_id"),
                condition=models.Q(channel="inbound_email") & ~models.Q(provider_email_id=""),
                name="outreach_unique_inbound_email",
            )
        ]


class BidSubmission(ImmutableFieldsMixin):
    class Source(models.TextChoices):
        INBOUND_EMAIL = "inbound_email", "Received by email"
        MANUAL_UPLOAD = "manual_upload", "Uploaded manually"

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT)
    scope_package = models.ForeignKey(ScopePackage, on_delete=models.PROTECT)
    scope_version = models.ForeignKey(ScopePackageVersion, on_delete=models.PROTECT)
    campaign = models.ForeignKey(InvitationCampaign, on_delete=models.PROTECT)
    batch = models.ForeignKey(InvitationBatch, on_delete=models.PROTECT)
    recipient = models.ForeignKey(InvitationRecipient, on_delete=models.PROTECT)
    company = models.ForeignKey("contractors.Company", on_delete=models.PROTECT)
    contact = models.ForeignKey("contractors.Contact", on_delete=models.PROTECT)
    source_response = models.OneToOneField(
        OutreachResponse, on_delete=models.PROTECT, null=True, blank=True
    )
    source = models.CharField(max_length=20, choices=Source)
    status = models.CharField(max_length=20, choices=Status, default=Status.RECEIVED)
    received_at = models.DateTimeField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    intake_note = models.CharField(max_length=1000, blank=True)
    request_key = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "organization_id",
        "project_id",
        "scope_package_id",
        "scope_version_id",
        "campaign_id",
        "batch_id",
        "recipient_id",
        "company_id",
        "contact_id",
        "source_response_id",
        "source",
        "status",
        "received_at",
        "recorded_by_id",
        "intake_note",
        "request_key",
        "created_at",
    )

    class Meta:
        ordering = ("-received_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "request_key"),
                condition=models.Q(request_key__isnull=False),
                name="outreach_unique_bid_request_key",
            ),
        ]

    def clean(self):
        super().clean()
        campaign = self.recipient.batch.campaign
        if (
            self.organization_id != campaign.organization_id
            or self.project_id != campaign.project_id
            or self.scope_package_id != campaign.scope_package_id
            or self.scope_version_id != campaign.scope_version_id
            or self.campaign_id != campaign.pk
            or self.batch_id != self.recipient.batch_id
            or self.company_id != self.recipient.company_id
            or self.contact_id != self.recipient.contact_id
        ):
            raise ValidationError("Quote must match the exact invitation, scope, and contractor.")
        if self.source == self.Source.INBOUND_EMAIL:
            if (
                not self.source_response_id
                or self.source_response.recipient_id != self.recipient_id
                or self.source_response.organization_id != self.organization_id
                or self.source_response.channel != "inbound_email"
                or self.source_response.attachment_count < 1
            ):
                raise ValidationError(
                    "Import requires a correlated inbound reply with attachments."
                )
        elif self.source_response_id:
            raise ValidationError("Manual upload cannot claim an inbound reply.")


class BidAttachment(ImmutableFieldsMixin):
    submission = models.ForeignKey(
        BidSubmission, on_delete=models.PROTECT, related_name="attachments"
    )
    file_asset = models.OneToOneField("documents.FileAsset", on_delete=models.PROTECT)
    original_filename = models.CharField(max_length=500)
    content_type = models.CharField(max_length=255)
    byte_size = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    checksum = models.CharField(max_length=64)
    provider_attachment_id = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "submission_id",
        "file_asset_id",
        "original_filename",
        "content_type",
        "byte_size",
        "checksum",
        "provider_attachment_id",
        "created_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("submission", "provider_attachment_id"),
                condition=~models.Q(provider_attachment_id=""),
                name="outreach_unique_bid_provider_attachment",
            ),
        ]

    def clean(self):
        super().clean()
        asset = self.file_asset
        if (
            asset.organization_id != self.submission.organization_id
            or self.original_filename != asset.original_filename
            or self.content_type != (asset.detected_mime_type or asset.declared_mime_type)
            or self.byte_size != asset.byte_size
            or self.checksum != asset.checksum
        ):
            raise ValidationError("Quote attachment must match its immutable stored file.")


class OutreachQualificationDecision(ImmutableFieldsMixin):
    recipient = models.ForeignKey(
        InvitationRecipient, on_delete=models.PROTECT, related_name="qualification_decisions"
    )
    state = models.CharField(max_length=20)
    note = models.CharField(max_length=1000, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    occurred_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("recipient_id", "state", "note", "actor_id", "occurred_at")


class BidRevision(ImmutableFieldsMixin):
    """Human-controlled commercial interpretation; the source quote remains immutable."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready for Comparison"
        SUPERSEDED = "superseded", "Superseded"

    class TaxTreatment(models.TextChoices):
        INCLUDED = "included", "Included"
        EXTRA = "extra", "Extra"
        EXEMPT = "exempt", "Exempt"
        NOT_STATED = "not_stated", "Not stated / needs confirmation"

    class ReviewState(models.TextChoices):
        UNREVIEWED = "unreviewed", "Not yet reviewed"
        CONFIRMED = "confirmed", "Human confirmed"
        NOT_STATED = "not_stated", "Not stated in quote"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT)
    scope_package = models.ForeignKey(ScopePackage, on_delete=models.PROTECT)
    scope_version = models.ForeignKey(ScopePackageVersion, on_delete=models.PROTECT)
    company = models.ForeignKey("contractors.Company", on_delete=models.PROTECT)
    recipient = models.ForeignKey(InvitationRecipient, on_delete=models.PROTECT)
    submission = models.ForeignKey(
        BidSubmission, on_delete=models.PROTECT, related_name="revisions"
    )
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="successors"
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    contractor_label = models.CharField(max_length=120, blank=True)
    request_key = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    currency = models.CharField(max_length=3, blank=True)
    currency_review = models.CharField(
        max_length=20, choices=ReviewState, default=ReviewState.UNREVIEWED
    )
    base_bid = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    base_bid_review = models.CharField(
        max_length=20, choices=ReviewState, default=ReviewState.UNREVIEWED
    )
    tax_treatment = models.CharField(
        max_length=20, choices=TaxTreatment, default=TaxTreatment.NOT_STATED
    )
    tax_reviewed = models.BooleanField(default=False)
    commercial_items_reviewed = models.BooleanField(default=False)
    scope_reviewed = models.BooleanField(default=False)
    validity_date = models.DateField(null=True, blank=True)
    validity_days = models.PositiveIntegerField(null=True, blank=True)
    schedule_text = models.CharField(max_length=500, blank=True)
    estimator_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_bid_revisions"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ready_bid_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    immutable_fields = (
        "organization_id",
        "project_id",
        "scope_package_id",
        "scope_version_id",
        "company_id",
        "recipient_id",
        "submission_id",
        "supersedes_id",
        "sequence",
        "request_key",
        "created_by_id",
        "created_at",
    )

    class Meta:
        ordering = ("-sequence", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "sequence"), name="outreach_unique_bid_revision_sequence"
            ),
            models.UniqueConstraint(
                fields=("submission", "request_key"),
                condition=models.Q(request_key__isnull=False),
                name="outreach_unique_bid_revision_request",
            ),
        ]

    def clean(self):
        super().clean()
        source = self.submission
        if (
            self.organization_id != source.organization_id
            or self.project_id != source.project_id
            or self.scope_package_id != source.scope_package_id
            or self.scope_version_id != source.scope_version_id
            or self.company_id != source.company_id
            or self.recipient_id != source.recipient_id
        ):
            raise ValidationError("Structured bid must match the exact source submission.")
        if self.supersedes_id and (
            self.supersedes_id == self.pk
            or self.supersedes.recipient_id != self.recipient_id
            or self.supersedes.scope_version_id != self.scope_version_id
            or self.supersedes.sequence >= self.sequence
        ):
            raise ValidationError("Superseded revision must be earlier for this exact invitation.")
        if self.currency and (
            len(self.currency) != 3
            or not self.currency.isalpha()
            or self.currency != self.currency.upper()
        ):
            raise ValidationError({"currency": "Enter a three-letter uppercase currency code."})
        if self.currency_review == self.ReviewState.CONFIRMED and not self.currency:
            raise ValidationError({"currency": "A confirmed currency requires a value."})
        if self.currency_review == self.ReviewState.NOT_STATED and self.currency:
            raise ValidationError({"currency": "Not stated currency must remain blank."})
        if self.base_bid is not None and (
            not self.base_bid.is_finite() or self.base_bid < Decimal("0")
        ):
            raise ValidationError({"base_bid": "Enter a nonnegative finite amount."})
        if self.base_bid_review == self.ReviewState.CONFIRMED and self.base_bid is None:
            raise ValidationError({"base_bid": "A confirmed base bid requires an amount."})
        if self.base_bid_review == self.ReviewState.NOT_STATED and self.base_bid is not None:
            raise ValidationError({"base_bid": "Not stated base bid must remain blank."})
        if self.validity_date and self.validity_days:
            raise ValidationError("Use either a validity date or stated number of days.")
        if self.status != self.Status.DRAFT and (not self.reviewed_by_id or not self.reviewed_at):
            raise ValidationError("Ready commercial data requires an explicit reviewer and time.")

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("status").first()
            if previous and previous["status"] != self.Status.DRAFT:
                raise ValidationError("Ready bid history is frozen. Create a successor revision.")
        return super().save(*args, **kwargs)


class BidCommercialItem(ImmutableFieldsMixin):
    class Kind(models.TextChoices):
        ALTERNATE = "alternate", "Alternate / option"
        ALLOWANCE = "allowance", "Allowance"
        FEE = "fee", "Permit / fee / tax"
        EXCLUSION = "exclusion", "Explicit exclusion"
        CONDITION = "condition", "Qualification / condition"

    class Treatment(models.TextChoices):
        ADD = "add", "Add"
        DEDUCT = "deduct", "Deduct"
        NO_COST = "no_cost", "No cost"
        PRICE_ON_REQUEST = "price_on_request", "Price on request"
        INCLUDED = "included", "Included"
        EXCLUDED = "excluded", "Excluded"
        EXTRA = "extra", "Extra"
        ALLOWANCE = "allowance", "Allowance"
        NOT_STATED = "not_stated", "Not stated"

    class Inclusion(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        UNCLEAR = "unclear", "Unclear"

    revision = models.ForeignKey(
        BidRevision, on_delete=models.PROTECT, related_name="commercial_items"
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    kind = models.CharField(max_length=20, choices=Kind)
    contractor_label = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=40, blank=True)
    treatment = models.CharField(max_length=30, choices=Treatment, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    included_in_base = models.CharField(max_length=10, choices=Inclusion, default=Inclusion.UNCLEAR)
    scope_item = models.ForeignKey(ScopeItem, null=True, blank=True, on_delete=models.PROTECT)
    estimator_note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("revision_id", "sequence", "created_at")

    class Meta:
        ordering = ("sequence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "sequence"), name="outreach_unique_bid_item_sequence"
            )
        ]

    def clean(self):
        super().clean()
        if not BidRevision.objects.filter(
            pk=self.revision_id, status=BidRevision.Status.DRAFT
        ).exists():
            raise ValidationError("Ready bid items are frozen.")
        if (
            self.scope_item_id
            and self.scope_item.package_version_id != self.revision.scope_version_id
        ):
            raise ValidationError("Scope item must belong to the exact quoted Ready scope version.")
        if self.amount is not None and (not self.amount.is_finite() or self.amount < Decimal("0")):
            raise ValidationError({"amount": "Enter a nonnegative finite amount."})
        if self.amount is not None and not self.currency:
            raise ValidationError({"currency": "An amount requires an explicit currency."})
        if self.currency and (
            len(self.currency) != 3
            or not self.currency.isalpha()
            or self.currency != self.currency.upper()
        ):
            raise ValidationError({"currency": "Enter a three-letter uppercase currency code."})
        if self.kind == self.Kind.ALTERNATE:
            if (
                self.treatment in (self.Treatment.ADD, self.Treatment.DEDUCT)
                and self.amount is None
            ):
                raise ValidationError("Priced add/deduct alternates require an explicit amount.")
            if self.treatment == self.Treatment.NO_COST and self.amount not in (None, Decimal("0")):
                raise ValidationError("No-cost alternate cannot have a positive amount.")

    def delete(self, *args, **kwargs):
        if not BidRevision.objects.filter(
            pk=self.revision_id, status=BidRevision.Status.DRAFT
        ).exists():
            raise ValidationError("Ready bid items are frozen.")
        return super().delete(*args, **kwargs)


class BidScopeCoverage(ImmutableFieldsMixin):
    class State(models.TextChoices):
        INCLUDED = "included", "Confirmed included"
        EXCLUDED = "excluded", "Confirmed excluded"
        QUALIFIED = "qualified", "Qualified / conditional"
        NOT_ADDRESSED = "not_addressed", "Not addressed"
        NEEDS_CLARIFICATION = "needs_clarification", "Needs clarification"

    revision = models.ForeignKey(
        BidRevision, on_delete=models.PROTECT, related_name="scope_coverage"
    )
    scope_item = models.ForeignKey(ScopeItem, on_delete=models.PROTECT)
    state = models.CharField(max_length=30, choices=State, default=State.NOT_ADDRESSED)
    wording = models.TextField(blank=True)
    estimator_note = models.CharField(max_length=1000, blank=True)
    reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("revision_id", "scope_item_id", "created_at")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "scope_item"), name="outreach_unique_bid_scope_coverage"
            )
        ]

    def clean(self):
        super().clean()
        if not BidRevision.objects.filter(
            pk=self.revision_id, status=BidRevision.Status.DRAFT
        ).exists():
            raise ValidationError("Ready scope coverage is frozen.")
        if self.scope_item.package_version_id != self.revision.scope_version_id:
            raise ValidationError("Coverage must use the exact quoted Ready scope version.")
        if (
            self.state in (self.State.INCLUDED, self.State.EXCLUDED, self.State.QUALIFIED)
            and not self.wording.strip()
        ):
            raise ValidationError("Confirmed coverage requires contractor wording or evidence.")

    def delete(self, *args, **kwargs):
        if not BidRevision.objects.filter(
            pk=self.revision_id, status=BidRevision.Status.DRAFT
        ).exists():
            raise ValidationError("Ready scope coverage is frozen.")
        return super().delete(*args, **kwargs)


class BidEvidence(ImmutableFieldsMixin):
    class Source(models.TextChoices):
        QUOTE = "quote", "Original quote"
        ESTIMATOR = "estimator", "Estimator note"
        CONTRACTOR = "contractor", "Contractor clarification"
        AI_SUGGESTED = "ai_suggested", "AI suggested"

    revision = models.ForeignKey(BidRevision, on_delete=models.PROTECT, related_name="evidence")
    attachment = models.ForeignKey(BidAttachment, null=True, blank=True, on_delete=models.PROTECT)
    commercial_item = models.ForeignKey(
        BidCommercialItem, null=True, blank=True, on_delete=models.PROTECT, related_name="evidence"
    )
    coverage = models.ForeignKey(
        BidScopeCoverage, null=True, blank=True, on_delete=models.PROTECT, related_name="evidence"
    )
    field_key = models.CharField(max_length=50, blank=True)
    source = models.CharField(max_length=20, choices=Source)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    excerpt = models.TextField(blank=True)
    note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "revision_id",
        "attachment_id",
        "commercial_item_id",
        "coverage_id",
        "field_key",
        "source",
        "page_number",
        "excerpt",
        "note",
        "created_at",
    )

    def clean(self):
        super().clean()
        if not BidRevision.objects.filter(
            pk=self.revision_id, status=BidRevision.Status.DRAFT
        ).exists():
            raise ValidationError("Ready bid evidence is frozen.")
        if self.attachment_id and self.attachment.submission_id != self.revision.submission_id:
            raise ValidationError("Evidence file must belong to the exact source submission.")
        if self.commercial_item_id and self.commercial_item.revision_id != self.revision_id:
            raise ValidationError("Evidence item must belong to this structured revision.")
        if self.coverage_id and self.coverage.revision_id != self.revision_id:
            raise ValidationError("Evidence coverage must belong to this structured revision.")
        if (
            sum(
                bool(value) for value in (self.commercial_item_id, self.coverage_id, self.field_key)
            )
            != 1
        ):
            raise ValidationError(
                "Evidence must support one commercial field, item or scope decision."
            )
        if self.page_number and not self.attachment_id:
            raise ValidationError("A page reference requires a source attachment.")
        if self.source == self.Source.QUOTE and not self.attachment_id:
            raise ValidationError("Original-quote evidence requires its exact source attachment.")
        if self.source != self.Source.QUOTE and not self.note.strip():
            raise ValidationError("Estimator or contractor evidence requires a human note.")
        if (
            self.source == self.Source.QUOTE
            and self.attachment_id
            and self.attachment.content_type == "application/pdf"
            and self.excerpt
            and not self.page_number
        ):
            raise ValidationError("A PDF excerpt requires its exact source page.")
        if (
            self.source == self.Source.QUOTE
            and self.attachment_id
            and self.page_number
            and self.excerpt
            and self.attachment.content_type == "application/pdf"
        ):
            from .bid_extraction import quote_pages

            page = next(
                (
                    item
                    for item in quote_pages(self.attachment)
                    if item["page_number"] == self.page_number
                ),
                None,
            )
            if page is None or self.excerpt not in page["text"]:
                raise ValidationError("Quote excerpt must occur exactly on the source PDF page.")

    def delete(self, *args, **kwargs):
        if not BidRevision.objects.filter(
            pk=self.revision_id, status=BidRevision.Status.DRAFT
        ).exists():
            raise ValidationError("Ready bid evidence is frozen.")
        return super().delete(*args, **kwargs)


class BidExtractionRun(ImmutableFieldsMixin):
    """Durable provider proposal, never a commercial decision or Ready revision."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    submission = models.ForeignKey(
        BidSubmission, on_delete=models.PROTECT, related_name="extraction_runs"
    )
    attachment = models.ForeignKey(BidAttachment, on_delete=models.PROTECT)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=100)
    schema_version = models.PositiveIntegerField(default=1)
    request_key = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.QUEUED)
    candidates = models.JSONField(default=list, blank=True)
    request_id = models.CharField(max_length=120, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    safe_error_code = models.CharField(max_length=60, blank=True)
    safe_error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    immutable_fields = (
        "submission_id",
        "attachment_id",
        "requested_by_id",
        "provider",
        "model",
        "schema_version",
        "request_key",
        "created_at",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("submission", "request_key"),
                condition=models.Q(request_key__isnull=False),
                name="outreach_unique_bid_extraction_request",
            )
        ]

    def clean(self):
        super().clean()
        if self.attachment.submission_id != self.submission_id:
            raise ValidationError("Extraction file must belong to the exact quote submission.")
        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values("status").first()
            if old and old["status"] in (self.Status.SUCCEEDED, self.Status.FAILED):
                raise ValidationError("Completed AI extraction history is frozen.")


class BidCandidateDecision(ImmutableFieldsMixin):
    class Decision(models.TextChoices):
        ACCEPTED = "accepted", "Accepted by human"
        CORRECTED = "corrected", "Corrected by human"
        IGNORED = "ignored", "Ignored by human"

    run = models.ForeignKey(BidExtractionRun, on_delete=models.PROTECT, related_name="decisions")
    candidate_index = models.PositiveIntegerField()
    revision = models.ForeignKey(BidRevision, on_delete=models.PROTECT)
    decision = models.CharField(max_length=20, choices=Decision)
    commercial_item = models.ForeignKey(
        BidCommercialItem, null=True, blank=True, on_delete=models.PROTECT
    )
    evidence = models.ForeignKey(BidEvidence, null=True, blank=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "run_id",
        "candidate_index",
        "revision_id",
        "decision",
        "commercial_item_id",
        "evidence_id",
        "actor_id",
        "created_at",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("run", "candidate_index", "revision"),
                name="outreach_unique_bid_candidate_decision",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.run.submission_id != self.revision.submission_id
            or not BidRevision.objects.filter(
                pk=self.revision_id, status=BidRevision.Status.DRAFT
            ).exists()
            or self.candidate_index >= len(self.run.candidates)
            or self.run.status != BidExtractionRun.Status.SUCCEEDED
        ):
            raise ValidationError("Candidate decision must belong to this Draft and source quote.")
        if self.commercial_item_id and self.commercial_item.revision_id != self.revision_id:
            raise ValidationError("Candidate item must belong to this Draft.")
        if self.evidence_id and self.evidence.revision_id != self.revision_id:
            raise ValidationError("Candidate evidence must belong to this Draft.")


class BidComparison(ImmutableFieldsMixin):
    """Human-created leveling workspace bound to one exact Ready scope version."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready for Human Review"

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT)
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT)
    scope_package = models.ForeignKey(ScopePackage, on_delete=models.PROTECT)
    scope_version = models.ForeignKey(ScopePackageVersion, on_delete=models.PROTECT)
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="successors"
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_bid_comparisons"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_bid_comparisons",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    immutable_fields = (
        "organization_id",
        "project_id",
        "scope_package_id",
        "scope_version_id",
        "supersedes_id",
        "sequence",
        "created_by_id",
        "created_at",
    )

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("project", "scope_version", "sequence"),
                name="outreach_unique_comparison_sequence",
            )
        ]

    def clean(self):
        super().clean()
        package = self.scope_version.package
        if (
            self.organization_id != self.project.organization_id
            or self.project_id != package.project_id
            or self.scope_package_id != package.pk
        ):
            raise ValidationError("Comparison must match one exact project scope version.")
        if self.supersedes_id and (
            self.supersedes_id == self.pk
            or self.supersedes.scope_version_id != self.scope_version_id
            or self.supersedes.sequence >= self.sequence
        ):
            raise ValidationError("Superseded comparison must be earlier for this scope version.")
        if self.status == self.Status.READY and (not self.reviewed_by_id or not self.reviewed_at):
            raise ValidationError("Ready comparison requires an explicit human reviewer and time.")

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values("status").first()
            if previous and previous["status"] == self.Status.READY:
                raise ValidationError("Ready comparison history is frozen. Create a successor.")
        return super().save(*args, **kwargs)


class BidComparisonEntry(ImmutableFieldsMixin):
    comparison = models.ForeignKey(BidComparison, on_delete=models.PROTECT, related_name="entries")
    revision = models.ForeignKey(BidRevision, on_delete=models.PROTECT)
    company = models.ForeignKey("contractors.Company", on_delete=models.PROTECT)
    company_name = models.CharField(max_length=255)
    revision_label = models.CharField(max_length=120, blank=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    added_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "comparison_id",
        "revision_id",
        "company_id",
        "company_name",
        "revision_label",
        "added_by_id",
        "added_at",
    )

    class Meta:
        ordering = ("company_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("comparison", "revision"), name="outreach_unique_comparison_revision"
            ),
            models.UniqueConstraint(
                fields=("comparison", "company"), name="outreach_unique_comparison_company"
            ),
        ]

    def clean(self):
        super().clean()
        revision = self.revision
        comparison = self.comparison
        if comparison.status != BidComparison.Status.DRAFT:
            raise ValidationError("Ready comparison entries are frozen.")
        if (
            revision.status != BidRevision.Status.READY
            or revision.organization_id != comparison.organization_id
            or revision.project_id != comparison.project_id
            or revision.scope_package_id != comparison.scope_package_id
            or revision.scope_version_id != comparison.scope_version_id
            or revision.company_id != self.company_id
        ):
            raise ValidationError("Select a Ready bid for this exact project scope version.")

    def delete(self, *args, **kwargs):
        if self.comparison.status != BidComparison.Status.DRAFT:
            raise ValidationError("Ready comparison entries are frozen.")
        return super().delete(*args, **kwargs)


class BidLevelingAdjustment(ImmutableFieldsMixin):
    class Direction(models.TextChoices):
        ADD = "add", "Add"
        DEDUCT = "deduct", "Deduct"

    class Category(models.TextChoices):
        SCOPE_GAP = "scope_gap", "Scope gap"
        EXCLUSION = "exclusion_normalization", "Exclusion normalization"
        ALTERNATE = "alternate_option", "Alternate / option"
        ALLOWANCE = "allowance_normalization", "Allowance normalization"
        PERMIT_FEE = "permit_fee", "Permit / fee"
        OTHER = "other", "Other estimator adjustment"

    entry = models.ForeignKey(
        BidComparisonEntry, on_delete=models.PROTECT, related_name="adjustments"
    )
    direction = models.CharField(max_length=10, choices=Direction)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    category = models.CharField(max_length=40, choices=Category)
    description = models.CharField(max_length=500)
    scope_item = models.ForeignKey(ScopeItem, null=True, blank=True, on_delete=models.PROTECT)
    source_commercial_item = models.ForeignKey(
        BidCommercialItem, null=True, blank=True, on_delete=models.PROTECT
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("entry_id", "created_by_id", "created_at")

    class Meta:
        ordering = ("created_at", "id")

    def clean(self):
        super().clean()
        comparison = self.entry.comparison
        if comparison.status != BidComparison.Status.DRAFT:
            raise ValidationError("Ready leveling adjustments are frozen.")
        if not self.amount.is_finite() or self.amount <= Decimal("0"):
            raise ValidationError({"amount": "Enter a positive finite amount."})
        if len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
            raise ValidationError({"currency": "Enter a three-letter uppercase currency code."})
        revision = self.entry.revision
        if revision.currency and self.currency != revision.currency:
            raise ValidationError("Adjustment currency must match the selected bid currency.")
        if self.scope_item_id and self.scope_item.package_version_id != comparison.scope_version_id:
            raise ValidationError("Adjustment scope item must belong to the frozen scope version.")
        if self.source_commercial_item_id and (
            self.source_commercial_item.revision_id != revision.pk
        ):
            raise ValidationError("Source commercial item must belong to this selected bid.")

    def delete(self, *args, **kwargs):
        if self.entry.comparison.status != BidComparison.Status.DRAFT:
            raise ValidationError("Ready leveling adjustments are frozen.")
        return super().delete(*args, **kwargs)
