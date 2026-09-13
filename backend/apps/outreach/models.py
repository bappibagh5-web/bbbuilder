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
