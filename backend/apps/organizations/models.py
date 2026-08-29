from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise ValidationError("Enter a valid IANA timezone.") from error


class Organization(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=200, blank=True)
    slug = models.SlugField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=Status, default=Status.ACTIVE)
    default_timezone = models.CharField(
        max_length=64, default="America/Vancouver", validators=[validate_timezone]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        ESTIMATOR_OPERATOR = "estimator_operator", "Estimator / Operator"
        VIEWER = "viewer", "Viewer"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    role = models.CharField(max_length=30, choices=Role)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "user"), name="unique_organization_membership"
            ),
            models.CheckConstraint(
                condition=Q(ends_at__isnull=True) | Q(ends_at__gte=F("starts_at")),
                name="membership_end_not_before_start",
            ),
        ]

    def __str__(self):
        return f"{self.user.email} — {self.organization.name} ({self.get_role_display()})"
