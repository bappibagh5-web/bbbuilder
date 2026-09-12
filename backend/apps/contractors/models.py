from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.organizations.models import Organization
from apps.projects.models import Project
from apps.scope_packages.models import ScopePackage, ScopePackageVersion
from apps.scope_packages.trades import TRADE_CHOICES


class Company(models.Model):
    class Source(models.TextChoices):
        INTERNAL = "internal", "Internal"
        DISCOVERED = "discovered", "External"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="companies"
    )
    legal_name = models.CharField(max_length=255, blank=True)
    display_name = models.CharField(max_length=255)
    website = models.URLField(blank=True)
    domain = models.CharField(max_length=255, blank=True, db_index=True)
    phone = models.CharField(max_length=50, blank=True)
    normalized_phone = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    province = models.CharField(max_length=80, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=80, default="Canada")
    source_type = models.CharField(max_length=20, choices=Source, default=Source.INTERNAL)
    external_provider = models.CharField(max_length=50, blank=True)
    external_place_id = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_companies"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_companies"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "external_provider", "external_place_id"),
                condition=~models.Q(external_place_id=""),
                name="contractor_unique_external_place",
            )
        ]

    def save(self, *args, **kwargs):
        from .services import normalize_domain, normalize_phone

        self.domain = normalize_domain(self.website or self.domain)
        self.normalized_phone = normalize_phone(self.phone)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name


class Contact(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="contacts")
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_primary", "name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("company",),
                condition=models.Q(is_active=True, is_primary=True),
                name="contractor_unique_active_primary_contact",
            )
        ]


class TradeCapability(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="trade_capabilities"
    )
    trade_key = models.CharField(max_length=100, choices=TRADE_CHOICES)
    keywords = models.JSONField(default=list, blank=True)
    service_cities = models.JSONField(default=list, blank=True)
    province = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    source_type = models.CharField(
        max_length=20, choices=Company.Source, default=Company.Source.INTERNAL
    )
    source_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("company", "trade_key"), name="contractor_unique_company_trade"
            )
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.keywords, list) or not isinstance(self.service_cities, list):
            raise ValidationError("Keywords and service cities must be lists.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ScopeContractorCandidate(models.Model):
    class Status(models.TextChoices):
        CANDIDATE = "candidate", "Candidate"
        SHORTLISTED = "shortlisted", "Shortlisted"
        APPROVED = "approved_for_outreach", "Approved for outreach"
        REJECTED = "rejected", "Rejected"

    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="contractor_candidates"
    )
    scope_package = models.ForeignKey(
        ScopePackage, on_delete=models.PROTECT, related_name="contractor_candidates"
    )
    scope_version = models.ForeignKey(
        ScopePackageVersion,
        on_delete=models.PROTECT,
        related_name="contractor_candidates",
    )
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="project_candidates"
    )
    status = models.CharField(max_length=30, choices=Status, default=Status.CANDIDATE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_contractor_candidates",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_contractor_candidates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("project", "scope_version", "company"),
                name="contractor_unique_scope_version_company",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.scope_version_id and self.scope_package_id:
            self.scope_version_id = self.scope_package.current_version_id
        if (
            self.scope_package.project_id != self.project_id
            or self.company.organization_id != self.project.organization_id
        ):
            raise ValidationError("Candidate organization and project scope must align.")
        if self.scope_version.package_id != self.scope_package_id:
            raise ValidationError("Candidate scope version must belong to its scope package.")

    def save(self, *args, **kwargs):
        if not self.scope_version_id and self.scope_package_id:
            self.scope_version_id = self.scope_package.current_version_id
        self.full_clean()
        return super().save(*args, **kwargs)


class DiscoveryRequest(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="discovery_requests"
    )
    scope_package = models.ForeignKey(
        ScopePackage, on_delete=models.PROTECT, related_name="discovery_requests"
    )
    scope_version = models.ForeignKey(
        ScopePackageVersion, on_delete=models.PROTECT, related_name="discovery_requests"
    )
    trade_key = models.CharField(max_length=100, choices=TRADE_CHOICES)
    city = models.CharField(max_length=120)
    province = models.CharField(max_length=80)
    radius_km = models.PositiveIntegerField(null=True, blank=True)
    radius_miles = models.PositiveIntegerField(default=200)
    project_location_key = models.CharField(max_length=64, blank=True)
    center_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    center_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    center_reference = models.CharField(max_length=255, blank=True)
    keywords = models.JSONField(default=list, blank=True)
    search_terms = models.JSONField(default=list)
    provider = models.CharField(max_length=50)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="contractor_discovery_requests",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    result_count = models.PositiveIntegerField(default=0)
    provider_metadata = models.JSONField(default=dict, blank=True)

    def clean(self):
        super().clean()
        if (
            self.scope_package.project_id != self.project_id
            or self.scope_version.package_id != self.scope_package_id
        ):
            raise ValidationError("Discovery request must bind to the exact project scope version.")
        if self.scope_version.status != ScopePackageVersion.Status.READY:
            raise ValidationError("Only Ready scope packages can be searched.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
