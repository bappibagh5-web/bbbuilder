from datetime import date, datetime
from decimal import Decimal

from .models import AuditEvent

PROJECT_AUDIT_FIELDS = (
    "project_number",
    "name",
    "status",
    "client_name",
    "site_address_line_1",
    "site_address_line_2",
    "city",
    "province_state",
    "postal_zip_code",
    "country",
    "project_timezone",
    "project_type",
    "description",
    "estimated_area",
    "area_unit",
    "bid_deadline",
    "questions_deadline",
    "site_visit_date",
    "planned_start_date",
    "substantial_completion_date",
    "opening_or_handover_date",
    "is_active",
)
CONTACT_AUDIT_FIELDS = (
    "company_name",
    "person_name",
    "email",
    "phone",
    "contact_role",
    "notes",
    "is_active",
)


def audit_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def snapshot(instance, field_names):
    return {name: audit_value(getattr(instance, name)) for name in field_names}


def record_event(*, organization, project, actor, action_code, target, metadata=None):
    return AuditEvent.objects.create(
        organization=organization,
        project=project,
        actor=actor,
        action_code=action_code,
        target_type=target._meta.label_lower,
        target_id=str(target.pk),
        metadata=metadata or {},
    )


def update_action(*, target_type, before, after):
    if before["is_active"] != after["is_active"]:
        state = "reactivated" if after["is_active"] else "archived"
        if target_type == "project_contact":
            state = "reactivated" if after["is_active"] else "deactivated"
        return f"{target_type}.{state}"
    return f"{target_type}.updated"
