import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.contractors.models import ScopeContractorCandidate
from apps.documents.models import ImmutableFieldsMixin
from apps.scope_packages.models import ScopePackage, ScopePackageVersion


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
