import re

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.organizations.models import Membership
from apps.organizations.services import active_membership

from .models import Project, ProjectContact


class OffsetDateTimeField(serializers.DateTimeField):
    timezone_pattern = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$", re.IGNORECASE)

    def to_internal_value(self, value):
        if isinstance(value, str) and not self.timezone_pattern.search(value.strip()):
            self.fail("invalid", format="ISO 8601 datetime with a UTC offset")
        parsed = super().to_internal_value(value)
        if timezone.is_naive(parsed):
            self.fail("invalid", format="ISO 8601 datetime with a UTC offset")
        return parsed


class ProjectSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    project_type_label = serializers.CharField(source="get_project_type_display", read_only=True)
    area_unit_label = serializers.CharField(source="get_area_unit_display", read_only=True)
    organization = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    created_by = serializers.EmailField(source="created_by.email", read_only=True)
    bid_deadline = OffsetDateTimeField(required=False, allow_null=True)
    questions_deadline = OffsetDateTimeField(required=False, allow_null=True)
    location = serializers.SerializerMethodField()
    deadlines = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            "id",
            "organization",
            "project_number",
            "name",
            "status",
            "status_label",
            "created_by",
            "client_name",
            "site_address_line_1",
            "site_address_line_2",
            "city",
            "province_state",
            "postal_zip_code",
            "country",
            "project_timezone",
            "project_type",
            "project_type_label",
            "description",
            "estimated_area",
            "area_unit",
            "area_unit_label",
            "bid_deadline",
            "questions_deadline",
            "site_visit_date",
            "planned_start_date",
            "substantial_completion_date",
            "opening_or_handover_date",
            "is_active",
            "location",
            "deadlines",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "organization", "created_by", "created_at", "updated_at")

    def validate(self, attrs):
        organization = self.context["organization"]
        if "is_active" in attrs:
            membership = active_membership(self.context["request"].user, organization)
            if membership is None or membership.role != Membership.Role.ADMIN:
                raise PermissionDenied(
                    "Only an organization admin may archive or reactivate a project."
                )
        project_number = attrs.get("project_number", getattr(self.instance, "project_number", None))
        if project_number:
            matching = Project.objects.filter(
                organization=organization, project_number__iexact=project_number
            )
            if self.instance:
                matching = matching.exclude(pk=self.instance.pk)
            if matching.exists():
                raise serializers.ValidationError(
                    {"project_number": "This project number already exists in the organization."}
                )
        return attrs

    def get_location(self, project):
        return {
            "address_line_1": project.site_address_line_1,
            "address_line_2": project.site_address_line_2,
            "city": project.city,
            "province_state": project.province_state,
            "postal_zip_code": project.postal_zip_code,
            "country": project.country,
        }

    def get_deadlines(self, project):
        return {
            "bid": project.bid_deadline,
            "questions": project.questions_deadline,
            "site_visit": project.site_visit_date,
            "planned_start": project.planned_start_date,
            "substantial_completion": project.substantial_completion_date,
            "opening_or_handover": project.opening_or_handover_date,
        }


class ProjectContactSerializer(serializers.ModelSerializer):
    contact_role_label = serializers.CharField(source="get_contact_role_display", read_only=True)
    project = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ProjectContact
        fields = (
            "id",
            "project",
            "company_name",
            "person_name",
            "email",
            "phone",
            "contact_role",
            "contact_role_label",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "project", "created_at", "updated_at")
