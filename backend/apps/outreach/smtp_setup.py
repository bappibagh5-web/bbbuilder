"""Admin-only SMTP configuration and explicit tests, with safe audit metadata."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.contractors.models import Contact
from apps.organizations.models import Membership
from apps.organizations.services import active_membership
from apps.projects.audit import record_event

from .credentials import encrypt_password, encryption_ready
from .models import OutreachSenderSettings, OutreachSMTPConfiguration
from .smtp import provider_status, safe_smtp_failure, send_test_email, test_connection


def _admin(actor, organization):
    membership = active_membership(actor, organization)
    if membership is None or membership.role != Membership.Role.ADMIN:
        raise PermissionDenied("Organization Admin access is required.")


@transaction.atomic
def save_smtp_configuration(
    *,
    organization,
    actor,
    host,
    port,
    username,
    password,
    clear_password,
    security,
    timeout_seconds,
    enabled,
):
    _admin(actor, organization)
    if password and clear_password:
        raise ValidationError("Choose either replace or clear password, not both.")
    if password and not encryption_ready():
        raise ValidationError(
            "Server credential encryption is not configured. Ask an administrator."
        )
    config, _ = OutreachSMTPConfiguration.objects.select_for_update().get_or_create(
        organization=organization, defaults={"updated_by": actor}
    )
    config.host = host.strip()
    config.port = port
    config.username = username.strip()
    config.security = security
    config.timeout_seconds = timeout_seconds
    config.is_enabled = enabled
    if clear_password:
        config.encrypted_password = ""
    elif password:
        config.encrypted_password = encrypt_password(password)
    if enabled and not encryption_ready():
        raise ValidationError(
            "Server credential encryption is not configured. Ask an administrator."
        )
    if enabled and not config.encrypted_password:
        raise ValidationError("Save an SMTP password before enabling email delivery.")
    config.last_test_status = ""
    config.last_tested_at = None
    config.updated_by = actor
    config.full_clean()
    config.save()
    record_event(
        organization=organization,
        project=None,
        actor=actor,
        action_code="smtp_configuration.updated",
        target=config,
        metadata={"enabled": config.is_enabled, "security": config.security},
    )
    return config


def run_connection_test(*, organization, actor):
    _admin(actor, organization)
    config = OutreachSMTPConfiguration.objects.filter(organization=organization).first()
    if config is None:
        raise ValidationError("Save SMTP configuration first.")
    try:
        test_connection(organization)
    except Exception as error:
        code, message, _ = safe_smtp_failure(error)
        if code == "delivery_uncertain":
            code, message = "smtp_timeout", "The SMTP connection timed out."
        if isinstance(error, ValidationError):
            code, message = (
                "smtp_configuration",
                "Email delivery is not configured. Check Settings.",
            )
        config.last_test_status = code
        config.last_tested_at = timezone.now()
        config.save(update_fields=("last_test_status", "last_tested_at"))
        record_event(
            organization=organization,
            project=None,
            actor=actor,
            action_code="smtp_connection.tested",
            target=config,
            metadata={"result": code},
        )
        return {"success": False, "code": code, "message": message}
    config.last_test_status = "succeeded"
    config.last_tested_at = timezone.now()
    config.save(update_fields=("last_test_status", "last_tested_at"))
    record_event(
        organization=organization,
        project=None,
        actor=actor,
        action_code="smtp_connection.tested",
        target=config,
        metadata={"result": "succeeded"},
    )
    return {"success": True, "code": "smtp_connected", "message": "Connection successful"}


def run_test_email(*, organization, actor, recipient_email):
    _admin(actor, organization)
    validate_email(recipient_email)
    if Contact.objects.filter(
        company__organization=organization, email__iexact=recipient_email
    ).exists():
        raise ValidationError("Use a controlled test mailbox, not a contractor contact.")
    if provider_status(organization)["state"] != "configured":
        raise ValidationError("Email delivery is not configured. Check Settings.")
    if not OutreachSenderSettings.objects.filter(
        organization=organization, is_enabled=True
    ).exists():
        raise ValidationError("Configure and enable the outreach sender first.")
    try:
        send_test_email(organization, recipient_email)
    except Exception as error:
        code, message, _ = safe_smtp_failure(error)
        record_event(
            organization=organization,
            project=None,
            actor=actor,
            action_code="smtp_test_email.failed",
            target=OutreachSMTPConfiguration.objects.get(organization=organization),
            metadata={"result": code},
        )
        return {"success": False, "code": code, "message": message}
    record_event(
        organization=organization,
        project=None,
        actor=actor,
        action_code="smtp_test_email.sent",
        target=OutreachSMTPConfiguration.objects.get(organization=organization),
        metadata={"result": "succeeded"},
    )
    return {"success": True, "code": "test_email_sent", "message": "Test email sent"}
