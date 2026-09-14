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
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "recipient_id",
        "previous_status",
        "new_status",
        "actor_id",
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
    status = models.CharField(max_length=20, choices=Status, default=Status.PENDING)
    attempted_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    safe_error_code = models.CharField(max_length=80, blank=True)
    safe_error_message = models.CharField(max_length=255, blank=True)

    immutable_fields = ("message_id", "sequence", "provider_key", "idempotency_key", "attempted_at")

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
