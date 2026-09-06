from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.analysis.models import ProjectIntelligenceSnapshot, ProjectIntelligenceSnapshotEntry
from apps.documents.models import ImmutableFieldsMixin
from apps.organizations.models import Organization
from apps.projects.models import Project


class ScopePackage(models.Model):
    class Lifecycle(models.TextChoices):
        ACTIVE = "active", "Active"
        SUPERSEDED = "superseded", "Superseded"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="scope_packages"
    )
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="scope_packages")
    source_snapshot = models.ForeignKey(
        ProjectIntelligenceSnapshot,
        on_delete=models.PROTECT,
        related_name="scope_packages",
    )
    trade_key = models.SlugField(max_length=100)
    trade_category = models.CharField(max_length=200)
    generation_rule_version = models.PositiveIntegerField(default=1)
    lifecycle = models.CharField(max_length=20, choices=Lifecycle, default=Lifecycle.ACTIVE)
    current_version = models.OneToOneField(
        "ScopePackageVersion",
        on_delete=models.PROTECT,
        related_name="current_for_package",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_scope_packages",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_scope_packages",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("trade_category", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("project", "source_snapshot", "trade_key"),
                name="scope_unique_project_snapshot_trade",
            )
        ]

    def clean(self):
        super().clean()
        if self.project.organization_id != self.organization_id:
            raise ValidationError({"organization": "Organization must match the project."})
        if self.source_snapshot.project_id != self.project_id:
            raise ValidationError({"source_snapshot": "Snapshot must belong to the project."})
        if self.current_version_id and self.current_version.package_id != self.pk:
            raise ValidationError(
                {"current_version": "Current version must belong to this package."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project.project_number} — {self.trade_category}"


class ScopePackageVersion(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"

    package = models.ForeignKey(ScopePackage, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    inclusions = models.JSONField(default=list, blank=True)
    exclusions = models.JSONField(default=list, blank=True)
    clarifications = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_scope_package_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "package_id",
        "version",
        "title",
        "description",
        "inclusions",
        "exclusions",
        "clarifications",
        "status",
        "created_by_id",
        "created_at",
    )

    class Meta:
        ordering = ("-version", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("package", "version"), name="scope_unique_package_version"
            )
        ]

    def clean(self):
        super().clean()
        for field in ("inclusions", "exclusions", "clarifications"):
            value = getattr(self, field)
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValidationError({field: "Enter a list of text values."})

    def __str__(self):
        return f"{self.package} — V{self.version}"


class ScopePackageSource(ImmutableFieldsMixin):
    package_version = models.ForeignKey(
        ScopePackageVersion, on_delete=models.PROTECT, related_name="sources"
    )
    snapshot_entry = models.ForeignKey(
        ProjectIntelligenceSnapshotEntry,
        on_delete=models.PROTECT,
        related_name="scope_package_sources",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = ("package_version_id", "snapshot_entry_id", "created_at")

    class Meta:
        ordering = ("package_version_id", "snapshot_entry_id")
        constraints = [
            models.UniqueConstraint(
                fields=("package_version", "snapshot_entry"),
                name="scope_unique_version_snapshot_entry",
            )
        ]

    def clean(self):
        super().clean()
        package = self.package_version.package
        if self.snapshot_entry.snapshot_id != package.source_snapshot_id:
            raise ValidationError(
                {"snapshot_entry": "Source entry must belong to the package snapshot."}
            )
        if not self.snapshot_entry.included_in_intelligence:
            raise ValidationError(
                {"snapshot_entry": "Only approved included information can source a scope."}
            )
