from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.organizations.models import Organization, validate_timezone


class Project(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        DOCUMENTS_UPLOADED = "documents_uploaded", "Documents Uploaded"
        AI_ANALYSIS = "ai_analysis", "AI Analysis"
        HUMAN_SCOPE_REVIEW = "human_scope_review", "Human Scope Review"
        TRADE_PACKAGES_READY = "trade_packages_ready", "Trade Packages Ready"
        CONTRACTOR_DISCOVERY = "contractor_discovery", "Contractor Discovery"
        OUTREACH_ACTIVE = "outreach_active", "Outreach Active"
        BID_COLLECTION = "bid_collection", "Bid Collection"
        BID_LEVELING = "bid_leveling", "Bid Leveling"
        HUMAN_AWARD_REVIEW = "human_award_review", "Human Award Review"
        FINAL_PROPOSAL = "final_proposal", "Final Proposal"
        AWARDED = "awarded", "Awarded"

    class ProjectType(models.TextChoices):
        RETAIL = "retail", "Retail"
        RESTAURANT = "restaurant", "Restaurant"
        OFFICE = "office", "Office"
        COMMERCIAL = "commercial", "Commercial"
        OTHER = "other", "Other"

    class AreaUnit(models.TextChoices):
        SQUARE_FEET = "sf", "Square feet"
        SQUARE_METRES = "m2", "Square metres"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="projects"
    )
    project_number = models.CharField(max_length=80)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=40, choices=Status, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_projects",
    )

    client_name = models.CharField(max_length=255, blank=True)
    site_address_line_1 = models.CharField(max_length=255, blank=True)
    site_address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    province_state = models.CharField(max_length=120, blank=True)
    postal_zip_code = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=2, default="CA")
    project_timezone = models.CharField(max_length=64, validators=[validate_timezone])

    project_type = models.CharField(max_length=30, choices=ProjectType, default=ProjectType.OTHER)
    description = models.TextField(blank=True)
    estimated_area = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    area_unit = models.CharField(max_length=10, choices=AreaUnit, default=AreaUnit.SQUARE_FEET)

    bid_deadline = models.DateTimeField(blank=True, null=True)
    questions_deadline = models.DateTimeField(blank=True, null=True)
    site_visit_date = models.DateField(blank=True, null=True)
    planned_start_date = models.DateField(blank=True, null=True)
    substantial_completion_date = models.DateField(blank=True, null=True)
    opening_or_handover_date = models.DateField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "project_number")
        constraints = [
            models.UniqueConstraint(
                Lower("project_number"),
                "organization",
                name="unique_project_number_per_organization",
            ),
            models.CheckConstraint(
                condition=Q(estimated_area__isnull=True) | Q(estimated_area__gt=0),
                name="project_estimated_area_positive",
            ),
        ]

    def __str__(self):
        return f"{self.project_number} — {self.name}"


class ProjectContact(models.Model):
    class Role(models.TextChoices):
        CLIENT = "client", "Client"
        ARCHITECT = "architect", "Architect"
        CONSULTANT = "consultant", "Consultant"
        LANDLORD = "landlord", "Landlord"
        PROJECT_MANAGER = "project_manager", "Project Manager"
        BID_CONTACT = "bid_contact", "Bid Contact"
        SITE_CONTACT = "site_contact", "Site Contact"
        OTHER = "other", "Other"

    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="contacts")
    company_name = models.CharField(max_length=255, blank=True)
    person_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    contact_role = models.CharField(max_length=30, choices=Role, default=Role.OTHER)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("contact_role", "company_name", "person_name", "id")

    def __str__(self):
        return self.person_name or self.company_name or f"Contact {self.pk}"


class AuditEvent(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="audit_events"
    )
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="audit_events", blank=True, null=True
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        blank=True,
        null=True,
    )
    action_code = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100)
    occurred_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-occurred_at", "-id")
        indexes = [
            models.Index(fields=("organization", "occurred_at")),
            models.Index(fields=("project", "occurred_at")),
        ]

    def __str__(self):
        return f"{self.action_code} {self.target_type}:{self.target_id}"
