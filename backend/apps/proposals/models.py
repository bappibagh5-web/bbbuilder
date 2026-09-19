from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.documents.models import ImmutableFieldsMixin
from apps.organizations.models import Organization
from apps.projects.models import Project, ProjectContact


class Estimate(ImmutableFieldsMixin):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="estimates"
    )
    project = models.OneToOneField(Project, on_delete=models.PROTECT, related_name="estimate")
    title = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_estimates"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("organization_id", "project_id", "title", "created_by_id")

    class Meta:
        ordering = ("project_id", "id")

    def clean(self):
        super().clean()
        if self.project_id and self.organization_id != self.project.organization_id:
            raise ValidationError({"organization": "Estimate organization must match its project."})

    def __str__(self):
        return f"{self.project} — {self.title}"


class EstimateVersion(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"

    estimate = models.ForeignKey(Estimate, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="successor",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_estimate_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "estimate_id",
        "version",
        "supersedes_id",
        "status",
        "created_by_id",
    )

    class Meta:
        ordering = ("estimate_id", "version")
        constraints = [
            models.UniqueConstraint(
                fields=("estimate", "version"), name="unique_estimate_version_number"
            ),
            models.CheckConstraint(condition=Q(version__gt=0), name="estimate_version_positive"),
        ]

    def clean(self):
        super().clean()
        if self.supersedes_id:
            if self.supersedes.estimate_id != self.estimate_id:
                raise ValidationError({"supersedes": "A predecessor must belong to this estimate."})
            if self.supersedes.version >= self.version:
                raise ValidationError({"supersedes": "A predecessor must be an earlier version."})

    def __str__(self):
        return f"{self.estimate} V{self.version}"


class Proposal(ImmutableFieldsMixin):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="proposals"
    )
    project = models.OneToOneField(Project, on_delete=models.PROTECT, related_name="proposal")
    estimate = models.OneToOneField(Estimate, on_delete=models.PROTECT, related_name="proposal")
    title = models.CharField(max_length=255)
    client_contact = models.ForeignKey(
        ProjectContact,
        on_delete=models.PROTECT,
        related_name="proposals",
        blank=True,
        null=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_proposals"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "organization_id",
        "project_id",
        "estimate_id",
        "title",
        "client_contact_id",
        "created_by_id",
    )

    class Meta:
        ordering = ("project_id", "id")

    def clean(self):
        super().clean()
        errors = {}
        if self.project_id and self.organization_id != self.project.organization_id:
            errors["organization"] = "Proposal organization must match its project."
        if self.estimate_id and self.estimate.project_id != self.project_id:
            errors["estimate"] = "Proposal estimate must belong to its project."
        if self.client_contact_id and self.client_contact.project_id != self.project_id:
            errors["client_contact"] = "Proposal contact must belong to its project."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.project} — {self.title}"


class ProposalVersion(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"

    proposal = models.ForeignKey(Proposal, on_delete=models.PROTECT, related_name="versions")
    estimate_version = models.ForeignKey(
        EstimateVersion, on_delete=models.PROTECT, related_name="proposal_versions"
    )
    version = models.PositiveIntegerField()
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="successor",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_proposal_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "proposal_id",
        "estimate_version_id",
        "version",
        "supersedes_id",
        "status",
        "created_by_id",
    )

    class Meta:
        ordering = ("proposal_id", "version")
        constraints = [
            models.UniqueConstraint(
                fields=("proposal", "version"), name="unique_proposal_version_number"
            ),
            models.CheckConstraint(condition=Q(version__gt=0), name="proposal_version_positive"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.estimate_version_id
            and self.proposal_id
            and self.estimate_version.estimate_id != self.proposal.estimate_id
        ):
            errors["estimate_version"] = "Proposal version must use its proposal's estimate."
        if self.supersedes_id:
            if self.supersedes.proposal_id != self.proposal_id:
                errors["supersedes"] = "A predecessor must belong to this proposal."
            elif self.supersedes.version >= self.version:
                errors["supersedes"] = "A predecessor must be an earlier version."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.proposal} V{self.version}"
