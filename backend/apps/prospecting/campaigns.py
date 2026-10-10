# ruff: noqa: E501
import hashlib
import json
import logging
import re
import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.organizations.models import Membership
from apps.organizations.services import active_membership
from apps.outreach.models import OutreachSenderSettings
from apps.outreach.smtp import _send, provider_status, safe_smtp_failure
from apps.projects.audit import record_event
from apps.projects.models import AuditEvent

from .models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectCampaignVersion,
    ProspectDeliveryAttempt,
    ProspectingSettings,
    ProspectMessage,
    ProspectProviderEmail,
    ProspectReply,
    ProspectSequenceStep,
    ProspectSequenceStepVersion,
    ProspectSuppression,
    ProspectUnsubscribeToken,
)

ALLOWED_TOKENS = {"contact_name", "first_name", "name", "company_name", "city", "trade"}
TOKEN_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")
RFC_MESSAGE_ID_PATTERN = re.compile(r"^<[^<>\s@]+@[^<>\s@]+>$")
logger = logging.getLogger(__name__)
STOPPED_STATES = {
    ProspectCampaignRecipient.State.REPLIED,
    ProspectCampaignRecipient.State.COMPLETED,
    ProspectCampaignRecipient.State.BOUNCED,
    ProspectCampaignRecipient.State.COMPLAINED,
    ProspectCampaignRecipient.State.UNSUBSCRIBED,
    ProspectCampaignRecipient.State.SUPPRESSED,
    ProspectCampaignRecipient.State.FAILED,
    ProspectCampaignRecipient.State.CANCELLED,
}


def normalize_email(value):
    email = str(value or "").strip().lower()
    validate_email(email)
    return email


def _membership(actor, organization, *, admin=False):
    membership = active_membership(actor, organization)
    allowed = (
        {Membership.Role.ADMIN}
        if admin
        else {
            Membership.Role.ADMIN,
            Membership.Role.ESTIMATOR_OPERATOR,
        }
    )
    if not membership or membership.role not in allowed:
        raise ValidationError("Organization access does not allow this action.")
    return membership


def validate_template(subject, body):
    unknown = (
        set(TOKEN_PATTERN.findall(subject)) | set(TOKEN_PATTERN.findall(body))
    ) - ALLOWED_TOKENS
    if unknown:
        raise ValidationError(f"Unsupported personalization token: {sorted(unknown)[0]}.")


def campaign_readiness(campaign):
    blockers = []
    config = ProspectingSettings.objects.filter(organization=campaign.organization).first()
    sender = OutreachSenderSettings.objects.filter(organization=campaign.organization).first()
    provider = provider_status(campaign.organization)
    steps = campaign.sequence_steps.filter(enabled=True)
    eligible = campaign.recipients.filter(state=ProspectCampaignRecipient.State.PENDING)
    if not steps.exists():
        blockers.append("Add the initial email")
    if not eligible.exists():
        blockers.append("Enroll eligible prospects")
    if not config or not config.is_enabled:
        blockers.append("Enable Prospecting email delivery")
    if not config or not config.business_identity.strip() or not config.compliance_footer.strip():
        blockers.append("Configure business identity and compliance footer")
    if not sender or not sender.is_enabled:
        blockers.append("Configure sender identity")
    if provider["state"] != "configured":
        blockers.append("SMTP connection/configuration not ready")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "eligible_recipients": eligible.count(),
        "provider": provider,
    }


@transaction.atomic
def create_campaign(*, organization, actor, name, list_ids=()):
    _membership(actor, organization)
    campaign = ProspectCampaign.objects.create(
        organization=organization, name=" ".join(name.split()), created_by=actor
    )
    lists = organization.prospect_lists.filter(pk__in=list_ids, status="active")
    if lists.count() != len(set(list_ids)):
        raise ValidationError("One or more selected prospect lists are unavailable.")
    campaign.source_lists.set(lists)
    record_event(
        organization=organization,
        project=None,
        actor=actor,
        action_code="prospecting_campaign.created",
        target=campaign,
        metadata={"campaign_id": campaign.pk},
    )
    return campaign


@transaction.atomic
def save_step(*, campaign, actor, values, step=None):
    _membership(actor, campaign.organization)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != ProspectCampaign.Status.DRAFT:
        raise ValidationError("Only a Draft campaign can be edited.")
    created = step is None
    previous_enabled = step.enabled if step else None
    if step is None:
        step = ProspectSequenceStep(campaign=campaign)
    elif step.campaign_id != campaign.pk:
        raise ValidationError("Sequence step does not belong to this campaign.")
    subject = values.get("subject", step.subject)
    body = values.get("body", step.body)
    validate_template(subject, body)
    for field in ("step_number", "label", "subject", "body", "delay_minutes", "enabled"):
        if field in values:
            setattr(step, field, values[field])
    step.full_clean()
    step.save()
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code=(
            "prospecting.sequence_step.created"
            if created
            else "prospecting.sequence_step.disabled"
            if previous_enabled and not step.enabled
            else "prospecting.sequence_step.updated"
        ),
        target=step,
        metadata={"campaign_id": campaign.pk, "step_number": step.step_number},
    )
    return step


@transaction.atomic
def reorder_steps(*, campaign, actor, ordered_step_ids):
    _membership(actor, campaign.organization)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != ProspectCampaign.Status.DRAFT:
        raise ValidationError("Only a Draft campaign can be edited.")
    steps = list(campaign.sequence_steps.order_by("step_number", "id"))
    if set(ordered_step_ids) != {item.pk for item in steps} or len(ordered_step_ids) != len(steps):
        raise ValidationError("Provide every sequence step exactly once.")
    by_id = {item.pk: item for item in steps}
    for offset, step_id in enumerate(ordered_step_ids, start=101):
        ProspectSequenceStep.objects.filter(pk=step_id).update(step_number=offset)
    for number, step_id in enumerate(ordered_step_ids, start=1):
        step = by_id[step_id]
        step.step_number = number
        if number == 1:
            step.delay_minutes = 0
        elif step.delay_minutes == 0:
            step.delay_minutes = 1440
        step.full_clean()
        step.save(update_fields=("step_number", "delay_minutes", "updated_at"))
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code="prospecting.sequence_step.reordered",
        target=campaign,
        metadata={"ordered_step_ids": ordered_step_ids},
    )
    return campaign.sequence_steps.order_by("step_number", "id")


@transaction.atomic
def delete_step(*, campaign, actor, step):
    _membership(actor, campaign.organization)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != ProspectCampaign.Status.DRAFT:
        raise ValidationError("Only a Draft campaign can be edited.")
    if step.campaign_id != campaign.pk:
        raise ValidationError("Sequence step does not belong to this campaign.")
    removed_number = step.step_number
    step.delete()
    remaining = list(campaign.sequence_steps.order_by("step_number", "id"))
    for number, item in enumerate(remaining, start=1):
        updates = {"step_number": number}
        if number == 1:
            updates["delay_minutes"] = 0
        ProspectSequenceStep.objects.filter(pk=item.pk).update(**updates)
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code="prospecting.sequence_step.removed",
        target=campaign,
        metadata={"removed_step_number": removed_number},
    )


def duplicate_step(*, campaign, actor, step):
    if campaign.sequence_steps.count() >= 5:
        raise ValidationError("A campaign can contain at most five sequence steps.")
    if step.campaign_id != campaign.pk:
        raise ValidationError("Sequence step does not belong to this campaign.")
    return save_step(
        campaign=campaign,
        actor=actor,
        values={
            "step_number": campaign.sequence_steps.count() + 1,
            "label": f"{step.label or 'Follow-up'} copy",
            "subject": step.subject,
            "body": step.body,
            "delay_minutes": step.delay_minutes or 1440,
            "enabled": step.enabled,
        },
    )


def enrollment_preview(campaign, entries):
    seen = set(campaign.recipients.values_list("normalized_email", flat=True))
    counts = {
        "selected": len(entries),
        "contact_ready": 0,
        "duplicates": 0,
        "suppressed": 0,
        "invalid": 0,
        "eligible": 0,
    }
    eligible = []
    for entry in entries:
        contact = entry.primary_contact
        if entry.status != entry.Status.CONTACT_READY or not contact or not contact.is_active:
            counts["invalid"] += 1
            continue
        counts["contact_ready"] += 1
        try:
            email = normalize_email(contact.email)
        except ValidationError:
            counts["invalid"] += 1
            continue
        if email in seen:
            counts["duplicates"] += 1
            continue
        if ProspectSuppression.objects.filter(
            organization=campaign.organization, normalized_email=email, active=True
        ).exists():
            counts["suppressed"] += 1
            continue
        seen.add(email)
        eligible.append((entry, contact, email))
    counts["eligible"] = len(eligible)
    return counts, eligible


@transaction.atomic
def enroll_entries(*, campaign, entries, actor):
    _membership(actor, campaign.organization)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != ProspectCampaign.Status.DRAFT:
        raise ValidationError("Recipients can be enrolled only while the campaign is Draft.")
    entries = list(entries.select_related("prospect_list", "company", "primary_contact"))
    if any(entry.prospect_list.organization_id != campaign.organization_id for entry in entries):
        raise ValidationError("Prospect entries must belong to this organization.")
    counts, eligible = enrollment_preview(campaign, entries)
    recipients = []
    for entry, contact, email in eligible:
        recipient = ProspectCampaignRecipient.objects.create(
            campaign=campaign,
            prospect_entry=entry,
            company=entry.company,
            contact=contact,
            company_name=entry.company.display_name,
            contact_name=contact.name,
            contact_title=contact.title,
            normalized_email=email,
            enrolled_by=actor,
        )
        record_event(
            organization=campaign.organization,
            project=None,
            actor=actor,
            action_code="prospecting_recipient.enrolled",
            target=recipient,
            metadata={"campaign_id": campaign.pk, "recipient_id": recipient.pk},
        )
        recipients.append(recipient)
    return counts, recipients


@transaction.atomic
def approve_campaign(*, campaign, actor):
    _membership(actor, campaign.organization, admin=True)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != ProspectCampaign.Status.DRAFT:
        raise ValidationError("Only a Draft campaign can be approved.")
    state = campaign_readiness(campaign)
    if not state["ready"]:
        raise ValidationError(state["blockers"])
    config = ProspectingSettings.objects.get(organization=campaign.organization)
    sender = OutreachSenderSettings.objects.get(organization=campaign.organization)
    steps = list(campaign.sequence_steps.filter(enabled=True).order_by("step_number"))
    sequence = [
        {
            "step": number,
            "label": item.label,
            "subject": item.subject,
            "body": item.body,
            "delay": item.delay_minutes,
        }
        for number, item in enumerate(steps, start=1)
    ]
    fingerprint = hashlib.sha256(json.dumps(sequence, sort_keys=True).encode()).hexdigest()
    version = ProspectCampaignVersion.objects.create(
        campaign=campaign,
        version_number=campaign.versions.count() + 1,
        sender_name=sender.display_name,
        from_address=sender.from_address,
        reply_to=sender.reply_to,
        business_identity=config.business_identity,
        compliance_footer=config.compliance_footer,
        sequence_fingerprint=fingerprint,
        created_by=actor,
    )
    ProspectSequenceStepVersion.objects.bulk_create(
        [
            ProspectSequenceStepVersion(
                campaign_version=version,
                step_number=number,
                label=step.label,
                subject=step.subject,
                body=step.body,
                delay_minutes=0 if number == 1 else step.delay_minutes,
            )
            for number, step in enumerate(steps, start=1)
        ]
    )
    campaign.status = ProspectCampaign.Status.APPROVED
    campaign.approved_by = actor
    campaign.approved_at = timezone.now()
    campaign.save(update_fields=("status", "approved_by", "approved_at", "updated_at"))
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code="prospecting_campaign.approved",
        target=campaign,
        metadata={"campaign_version_id": version.pk},
    )
    return version


@transaction.atomic
def launch_campaign(*, campaign, actor):
    _membership(actor, campaign.organization, admin=True)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != ProspectCampaign.Status.APPROVED:
        raise ValidationError("Campaign must be approved before launch.")
    state = campaign_readiness(campaign)
    if not state["ready"]:
        raise ValidationError(state["blockers"])
    version = campaign.versions.order_by("-version_number").first()
    now = timezone.now()
    campaign.recipients.filter(state=ProspectCampaignRecipient.State.PENDING).update(
        campaign_version=version,
        state=ProspectCampaignRecipient.State.SCHEDULED,
        current_step=0,
        next_due_at=now,
    )
    campaign.status = ProspectCampaign.Status.ACTIVE
    campaign.launched_by = actor
    campaign.launched_at = now
    campaign.save(update_fields=("status", "launched_by", "launched_at", "updated_at"))
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code="prospecting_campaign.launched",
        target=campaign,
        metadata={"campaign_version_id": version.pk},
    )
    return campaign


@transaction.atomic
def set_campaign_state(*, campaign, actor, action):
    membership = _membership(actor, campaign.organization)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    if action == "pause" and campaign.status == ProspectCampaign.Status.ACTIVE:
        campaign.status, campaign.paused_at = ProspectCampaign.Status.PAUSED, timezone.now()
        code = "prospecting_campaign.paused"
    elif action == "resume" and campaign.status == ProspectCampaign.Status.PAUSED:
        campaign.status, campaign.paused_at = ProspectCampaign.Status.ACTIVE, None
        code = "prospecting_campaign.resumed"
    elif (
        action == "archive"
        and membership.role == Membership.Role.ADMIN
        and campaign.status != ProspectCampaign.Status.ACTIVE
    ):
        campaign.status = ProspectCampaign.Status.ARCHIVED
        code = "prospecting_campaign.archived"
    else:
        raise ValidationError("Campaign state cannot be changed that way.")
    campaign.save(update_fields=("status", "paused_at", "updated_at"))
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code=code,
        target=campaign,
    )
    return campaign


@transaction.atomic
def remove_or_archive_campaign(*, campaign, actor):
    _membership(actor, campaign.organization)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    has_communication_history = (
        ProspectDeliveryAttempt.objects.filter(message__recipient__campaign=campaign).exists()
        or ProspectProviderEmail.objects.filter(message__recipient__campaign=campaign).exists()
        or ProspectReply.objects.filter(recipient__campaign=campaign).exists()
        or ProspectSuppression.objects.filter(
            Q(source_recipient__campaign=campaign) | Q(source_message__recipient__campaign=campaign)
        ).exists()
        or ProspectUnsubscribeToken.objects.filter(
            recipient__campaign=campaign, used_at__isnull=False
        ).exists()
        or campaign.recipients.filter(last_sent_at__isnull=False).exists()
        or AuditEvent.objects.filter(
            organization=campaign.organization,
            target_type=campaign._meta.label_lower,
            target_id=str(campaign.pk),
            action_code="prospecting.test_email.sent",
        ).exists()
    )
    if campaign.status == ProspectCampaign.Status.DRAFT and not has_communication_history:
        campaign_id = campaign.pk
        organization = campaign.organization
        ProspectUnsubscribeToken.objects.filter(recipient__campaign=campaign).delete()
        ProspectMessage.objects.filter(recipient__campaign=campaign).delete()
        campaign.recipients.all().delete()
        ProspectSequenceStepVersion.objects.filter(campaign_version__campaign=campaign).delete()
        campaign.versions.all().delete()
        campaign.sequence_steps.all().delete()
        record_event(
            organization=organization,
            project=None,
            actor=actor,
            action_code="prospect_campaign.deleted",
            target=campaign,
            metadata={"campaign_id": campaign_id},
        )
        try:
            campaign.delete()
        except (ProtectedError, IntegrityError) as error:
            raise ValidationError(
                "This campaign has historical records and must be archived instead."
            ) from error
        return "deleted"
    campaign.recipients.filter(
        state__in=(
            ProspectCampaignRecipient.State.PENDING,
            ProspectCampaignRecipient.State.SCHEDULED,
            ProspectCampaignRecipient.State.ACTIVE,
        )
    ).update(
        state=ProspectCampaignRecipient.State.CANCELLED,
        next_due_at=None,
        stop_reason="Campaign archived",
    )
    campaign.status = ProspectCampaign.Status.ARCHIVED
    campaign.paused_at = timezone.now()
    campaign.save(update_fields=("status", "paused_at", "updated_at"))
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code="prospect_campaign.archived",
        target=campaign,
        metadata={"campaign_id": campaign.pk},
    )
    return "archived"


@transaction.atomic
def restore_campaign(*, campaign, actor):
    _membership(actor, campaign.organization)
    campaign = ProspectCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status != ProspectCampaign.Status.ARCHIVED:
        raise ValidationError("Only an Archived campaign can be restored.")
    campaign.status = ProspectCampaign.Status.DRAFT
    campaign.paused_at = None
    campaign.save(update_fields=("status", "paused_at", "updated_at"))
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code="prospect_campaign.restored",
        target=campaign,
        metadata={"campaign_id": campaign.pk},
    )
    return campaign


def _personalization_values(recipient=None):
    trade = ""
    if recipient is not None:
        trade = next(
            (
                item.get_trade_key_display()
                for item in recipient.company.trade_capabilities.all()
                if item.is_active
            ),
            "",
        )
    contact_name = recipient.contact_name if recipient else ""
    values = {
        "contact_name": contact_name,
        "name": contact_name,
        "first_name": contact_name.split()[0] if contact_name else "",
        "company_name": recipient.company_name if recipient else "",
        "city": recipient.company.city if recipient else "",
        "trade": trade,
    }
    return {key: value or "[not available]" for key, value in values.items()}


def _render(template, recipient=None):
    values = _personalization_values(recipient)
    return TOKEN_PATTERN.sub(lambda match: values[match.group(1)], template)


def render_draft_preview(*, campaign, step, recipient):
    if step.campaign_id != campaign.pk or recipient.campaign_id != campaign.pk:
        raise ValidationError("Preview prospect and step must belong to this campaign.")
    validate_template(step.subject, step.body)
    config = ProspectingSettings.objects.filter(organization=campaign.organization).first()
    sender = OutreachSenderSettings.objects.filter(organization=campaign.organization).first()
    content = _render(step.body, recipient).rstrip()
    business_identity = config.business_identity if config else ""
    compliance_footer = config.compliance_footer if config else ""
    body = (
        f"{content}\n\n{business_identity}\n{compliance_footer}"
        "\nUnsubscribe: [personalized unsubscribe link]"
    )
    return {
        "from_name": sender.display_name if sender else "",
        "from_address": sender.from_address if sender else "",
        "reply_to": sender.reply_to if sender else "",
        "to_name": recipient.contact_name,
        "to_address": recipient.normalized_email,
        "subject": _render(step.subject, recipient),
        "body": body,
        "business_identity": business_identity,
        "compliance_footer": compliance_footer,
        "unsubscribe": "[personalized unsubscribe link]",
    }


def send_test_email(*, campaign, step, actor, test_email, recipient=None, send_function=_send):
    _membership(actor, campaign.organization)
    if campaign.status != ProspectCampaign.Status.DRAFT:
        raise ValidationError("Test emails can be sent only while the campaign is Draft.")
    test_email = normalize_email(test_email)
    if step.campaign_id != campaign.pk:
        raise ValidationError("Sequence step does not belong to this campaign.")
    if recipient is not None and recipient.campaign_id != campaign.pk:
        raise ValidationError("Preview prospect does not belong to this campaign.")
    config = ProspectingSettings.objects.filter(
        organization=campaign.organization, is_enabled=True
    ).first()
    sender = OutreachSenderSettings.objects.filter(
        organization=campaign.organization, is_enabled=True
    ).first()
    if config is None:
        raise ValidationError("Enable Prospecting email delivery before sending a test.")
    if sender is None:
        raise ValidationError("Configure sender identity before sending a test.")
    if provider_status(campaign.organization)["state"] != "configured":
        raise ValidationError("SMTP connection/configuration is not ready.")
    validate_template(step.subject, step.body)
    content = _render(step.body, recipient).rstrip()
    body = (
        f"{content}\n\n{config.business_identity}\n{config.compliance_footer}"
        "\nUnsubscribe: [test message - no subscription link]"
    )
    key = hashlib.sha256(
        f"prospecting-test:{campaign.pk}:{step.pk}:{test_email}:{timezone.now().isoformat()}".encode()
    ).hexdigest()
    domain = sender.from_address.rsplit("@", 1)[-1]
    try:
        send_function(
            campaign.organization,
            from_name=sender.display_name,
            from_address=sender.from_address,
            reply_to=sender.reply_to,
            to_address=test_email,
            subject=f"[TEST] {_render(step.subject, recipient)}",
            body=body,
            message_id=f"<{key}@{domain}>",
            additional_headers={"X-BB-Builders-Test": "true"},
        )
    except Exception as error:
        _, safe_message, _ = safe_smtp_failure(error)
        raise ValidationError(safe_message) from error
    record_event(
        organization=campaign.organization,
        project=None,
        actor=actor,
        action_code="prospecting.test_email.sent",
        target=campaign,
        metadata={"campaign_id": campaign.pk, "step_id": step.pk},
    )


def _new_token(recipient):
    raw = secrets.token_urlsafe(32)
    token = ProspectUnsubscribeToken.objects.create(
        recipient=recipient, token_digest=hashlib.sha256(raw.encode()).hexdigest()
    )
    return token, raw


def _prepare_message_locked(recipient):
    next_step_number = recipient.current_step + 1
    step = ProspectSequenceStepVersion.objects.get(
        campaign_version=recipient.campaign_version, step_number=next_step_number
    )
    existing = ProspectMessage.objects.filter(recipient=recipient, step_version=step).first()
    if existing:
        return existing
    _, raw = _new_token(recipient)
    origin = settings.FRONTEND_ORIGIN.rstrip("/")
    if not origin:
        raise ValidationError("Frontend origin is not configured for unsubscribe links.")
    unsubscribe_url = f"{origin}/unsubscribe/{raw}"
    version = recipient.campaign_version
    subject = _render(step.subject, recipient)
    content = _render(step.body, recipient).rstrip()
    body = f"{content}\n\n{version.business_identity}\n{version.compliance_footer}\nUnsubscribe: {unsubscribe_url}"
    key = hashlib.sha256(f"prospecting:{recipient.pk}:{step.pk}".encode()).hexdigest()
    domain = version.from_address.rsplit("@", 1)[-1]
    return ProspectMessage.objects.create(
        recipient=recipient,
        step_version=step,
        from_name=version.sender_name,
        from_address=version.from_address,
        reply_to=version.reply_to,
        to_address=recipient.normalized_email,
        subject=subject,
        body=body,
        unsubscribe_url=unsubscribe_url,
        rfc_message_id=f"<{key}@{domain}>",
    )


@transaction.atomic
def prepare_message(recipient):
    recipient = (
        ProspectCampaignRecipient.objects.select_for_update()
        .select_related("campaign", "company")
        .prefetch_related("company__trade_capabilities")
        .get(pk=recipient.pk)
    )
    return _prepare_message_locked(recipient)


def _limit_blocker(recipient, now):
    config = ProspectingSettings.objects.get(organization=recipient.campaign.organization)
    try:
        local_now = now.astimezone(ZoneInfo(config.sending_timezone))
    except ZoneInfoNotFoundError as error:
        raise ValidationError("Prospecting sending timezone is invalid.") from error
    if not config.allowed_start_hour <= local_now.hour < config.allowed_end_hour:
        return "Prospecting sending window is closed."
    attempts = ProspectDeliveryAttempt.objects.filter(
        message__recipient__campaign__organization=recipient.campaign.organization,
        status=ProspectDeliveryAttempt.Status.SUCCEEDED,
    )
    if (
        attempts.filter(completed_at__gte=now - timedelta(hours=1)).count()
        >= config.max_sends_per_hour
    ):
        return "Prospecting hourly send limit reached."
    if (
        attempts.filter(completed_at__gte=now - timedelta(days=1)).count()
        >= config.max_sends_per_day
    ):
        return "Prospecting daily send limit reached."
    return ""


def deliver_recipient(recipient, *, send_function=_send, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        recipient = (
            ProspectCampaignRecipient.objects.select_for_update()
            .select_related("campaign__organization", "company")
            .prefetch_related("company__trade_capabilities")
            .get(pk=recipient.pk)
        )
        if recipient.campaign.status != ProspectCampaign.Status.ACTIVE:
            raise ValidationError("Campaign is not active.")
        if ProspectSuppression.objects.filter(
            organization=recipient.campaign.organization,
            normalized_email=recipient.normalized_email,
            active=True,
        ).exists():
            recipient.state = ProspectCampaignRecipient.State.SUPPRESSED
            recipient.stop_reason = "Organization suppression"
            recipient.next_due_at = None
            recipient.save(update_fields=("state", "stop_reason", "next_due_at"))
            raise ValidationError("Recipient email is suppressed.")
        if (
            recipient.state in STOPPED_STATES
            or recipient.next_due_at is None
            or recipient.next_due_at > now
        ):
            raise ValidationError("Recipient is not due for delivery.")
        config = ProspectingSettings.objects.filter(
            organization=recipient.campaign.organization, is_enabled=True
        ).first()
        if (
            config is None
            or provider_status(recipient.campaign.organization)["state"] != "configured"
        ):
            raise ValidationError("Prospecting email delivery is not configured and enabled.")
        blocker = _limit_blocker(recipient, now)
        if blocker:
            raise ValidationError(blocker)
        message = _prepare_message_locked(recipient)
        prior_attempts = list(message.attempts.values_list("sequence", "status"))
        succeeded = any(
            status == ProspectDeliveryAttempt.Status.SUCCEEDED for _, status in prior_attempts
        )
        unresolved = any(
            status
            in (
                ProspectDeliveryAttempt.Status.PENDING,
                ProspectDeliveryAttempt.Status.UNCERTAIN,
            )
            for _, status in prior_attempts
        )
        if succeeded or unresolved:
            raise ValidationError(
                "This sequence step already has a completed or unresolved delivery."
            )
        sequence = max((sequence for sequence, _ in prior_attempts), default=0) + 1
        idempotency = hashlib.sha256(
            f"prospecting-attempt:{message.pk}:{sequence}".encode()
        ).hexdigest()
        attempt = ProspectDeliveryAttempt.objects.create(
            message=message,
            sequence=sequence,
            provider_key="smtp",
            idempotency_key=idempotency,
            rfc_message_id=message.rfc_message_id,
        )
        record_event(
            organization=recipient.campaign.organization,
            project=None,
            actor=None,
            action_code="prospecting_delivery.attempted",
            target=attempt,
            metadata={"campaign_id": recipient.campaign_id, "step": recipient.current_step + 1},
        )
    headers = {
        "List-Unsubscribe": f"<{message.unsubscribe_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    previous_message = None
    if message.step_version.step_number > 1:
        previous_message = (
            ProspectMessage.objects.filter(
                recipient=recipient,
                step_version__step_number__lt=message.step_version.step_number,
                attempts__status=ProspectDeliveryAttempt.Status.SUCCEEDED,
            )
            .order_by("-step_version__step_number", "-id")
            .first()
        )
    if previous_message and RFC_MESSAGE_ID_PATTERN.fullmatch(previous_message.rfc_message_id):
        headers["In-Reply-To"] = previous_message.rfc_message_id
        headers["References"] = previous_message.rfc_message_id
    if ProspectSuppression.objects.filter(
        organization=recipient.campaign.organization,
        normalized_email=recipient.normalized_email,
        active=True,
    ).exists():
        ProspectDeliveryAttempt.objects.filter(pk=attempt.pk).update(
            status=ProspectDeliveryAttempt.Status.FAILED,
            completed_at=timezone.now(),
            safe_error_code="suppressed",
            safe_error_message="Recipient email is suppressed.",
        )
        ProspectCampaignRecipient.objects.filter(pk=recipient.pk).update(
            state=ProspectCampaignRecipient.State.SUPPRESSED,
            next_due_at=None,
            stop_reason="Organization suppression",
        )
        attempt.refresh_from_db()
        return attempt
    try:
        send_function(
            recipient.campaign.organization,
            from_name=message.from_name,
            from_address=message.from_address,
            reply_to=message.reply_to,
            to_address=message.to_address,
            subject=message.subject,
            body=message.body,
            message_id=message.rfc_message_id,
            additional_headers=headers,
        )
    except Exception as error:
        code, safe_message, uncertain = safe_smtp_failure(error)
        ProspectDeliveryAttempt.objects.filter(pk=attempt.pk).update(
            status=(
                ProspectDeliveryAttempt.Status.UNCERTAIN
                if uncertain
                else ProspectDeliveryAttempt.Status.FAILED
            ),
            completed_at=timezone.now(),
            safe_error_code=code,
            safe_error_message=safe_message,
        )
        record_event(
            organization=recipient.campaign.organization,
            project=None,
            actor=None,
            action_code="prospecting_delivery.failed",
            target=attempt,
            metadata={"campaign_id": recipient.campaign_id, "error_code": code},
        )
        return attempt
    completed_at = timezone.now()
    with transaction.atomic():
        ProspectDeliveryAttempt.objects.filter(pk=attempt.pk).update(
            status=ProspectDeliveryAttempt.Status.SUCCEEDED, completed_at=completed_at
        )
        recipient = ProspectCampaignRecipient.objects.select_for_update().get(pk=recipient.pk)
        recipient.current_step += 1
        recipient.last_sent_at = completed_at
        next_step = ProspectSequenceStepVersion.objects.filter(
            campaign_version=recipient.campaign_version,
            step_number=recipient.current_step + 1,
        ).first()
        if next_step:
            recipient.state = ProspectCampaignRecipient.State.ACTIVE
            recipient.next_due_at = completed_at + timedelta(minutes=next_step.delay_minutes)
        else:
            recipient.state = ProspectCampaignRecipient.State.COMPLETED
            recipient.next_due_at = None
        recipient.save(update_fields=("current_step", "last_sent_at", "state", "next_due_at"))
        if (
            recipient.state == ProspectCampaignRecipient.State.COMPLETED
            and not recipient.campaign.recipients.exclude(state__in=STOPPED_STATES).exists()
        ):
            ProspectCampaign.objects.filter(
                pk=recipient.campaign_id, status=ProspectCampaign.Status.ACTIVE
            ).update(status=ProspectCampaign.Status.COMPLETED, completed_at=completed_at)
            record_event(
                organization=recipient.campaign.organization,
                project=None,
                actor=None,
                action_code="prospecting_campaign.completed",
                target=recipient.campaign,
            )
    record_event(
        organization=recipient.campaign.organization,
        project=None,
        actor=None,
        action_code="prospecting_delivery.succeeded",
        target=attempt,
        metadata={"campaign_id": recipient.campaign_id, "step": recipient.current_step},
    )
    attempt.refresh_from_db()
    return attempt


def process_due_prospecting_messages(
    *, limit=50, send_function=_send, organization=None, return_summary=False
):
    limit = min(max(int(limit), 1), 100)
    queryset = ProspectCampaignRecipient.objects.filter(
        campaign__status=ProspectCampaign.Status.ACTIVE,
        state__in=(
            ProspectCampaignRecipient.State.SCHEDULED,
            ProspectCampaignRecipient.State.ACTIVE,
        ),
        next_due_at__lte=timezone.now(),
    ).order_by("next_due_at", "id")
    if organization is not None:
        queryset = queryset.filter(campaign__organization=organization)
    if connection.features.has_select_for_update_skip_locked:
        with transaction.atomic():
            recipient_ids = list(
                queryset.select_for_update(skip_locked=True).values_list("id", flat=True)[:limit]
            )
    else:
        recipient_ids = list(queryset.values_list("id", flat=True)[:limit])
    attempts = []
    summary = {"processed": 0, "sent": 0, "scheduled": 0, "skipped": 0, "failed": 0}
    for recipient in ProspectCampaignRecipient.objects.filter(pk__in=recipient_ids).order_by(
        "next_due_at", "id"
    ):
        summary["processed"] += 1
        try:
            attempt = deliver_recipient(recipient, send_function=send_function)
        except ValidationError:
            summary["skipped"] += 1
            continue
        except Exception:
            logger.exception(
                "Unexpected Prospecting due-send failure for recipient_id=%s next_step=%s",
                recipient.pk,
                recipient.current_step + 1,
            )
            raise
        attempts.append(attempt)
        if attempt.status == ProspectDeliveryAttempt.Status.SUCCEEDED:
            summary["sent"] += 1
            recipient.refresh_from_db(fields=("state", "next_due_at"))
            if (
                recipient.state == ProspectCampaignRecipient.State.ACTIVE
                and recipient.next_due_at is not None
            ):
                summary["scheduled"] += 1
        else:
            summary["failed"] += 1
    return summary if return_summary else attempts


@transaction.atomic
def suppress_email(
    *, organization, email, reason, actor=None, recipient=None, message=None, provider_event=None
):
    normalized = normalize_email(email)
    suppression, created = ProspectSuppression.objects.get_or_create(
        organization=organization,
        normalized_email=normalized,
        active=True,
        defaults={
            "reason": reason,
            "created_by": actor,
            "source_recipient": recipient,
            "source_message": message,
            "provider_event": provider_event,
        },
    )
    ProspectCampaignRecipient.objects.filter(
        campaign__organization=organization, normalized_email=normalized
    ).exclude(state__in=STOPPED_STATES).update(
        state=(
            ProspectCampaignRecipient.State.UNSUBSCRIBED
            if reason == ProspectSuppression.Reason.UNSUBSCRIBE
            else ProspectCampaignRecipient.State.BOUNCED
            if reason == ProspectSuppression.Reason.HARD_BOUNCE
            else ProspectCampaignRecipient.State.COMPLAINED
            if reason == ProspectSuppression.Reason.COMPLAINT
            else ProspectCampaignRecipient.State.SUPPRESSED
        ),
        next_due_at=None,
        stop_reason=suppression.get_reason_display(),
    )
    if created:
        record_event(
            organization=organization,
            project=None,
            actor=actor,
            action_code="prospecting_suppression.created",
            target=suppression,
            metadata={"reason": reason},
        )
    return suppression, created


@transaction.atomic
def remove_suppression(*, suppression, actor):
    _membership(actor, suppression.organization, admin=True)
    suppression = ProspectSuppression.objects.select_for_update().get(pk=suppression.pk)
    if suppression.active:
        suppression.active = False
        suppression.removed_by = actor
        suppression.removed_at = timezone.now()
        suppression.save(update_fields=("active", "removed_by", "removed_at"))
        record_event(
            organization=suppression.organization,
            project=None,
            actor=actor,
            action_code="prospecting_suppression.removed",
            target=suppression,
        )
    return suppression


def unsubscribe_token(raw_token):
    if not raw_token or len(raw_token) > 100:
        return None
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    return (
        ProspectUnsubscribeToken.objects.select_related("recipient__campaign__organization")
        .filter(token_digest=digest)
        .first()
    )


@transaction.atomic
def unsubscribe(raw_token):
    token = unsubscribe_token(raw_token)
    if token is None:
        return None, False
    suppression, created = suppress_email(
        organization=token.recipient.campaign.organization,
        email=token.recipient.normalized_email,
        reason=ProspectSuppression.Reason.UNSUBSCRIBE,
        recipient=token.recipient,
    )
    if token.used_at is None:
        token.used_at = timezone.now()
        token.save(update_fields=("used_at",))
        record_event(
            organization=token.recipient.campaign.organization,
            project=None,
            actor=None,
            action_code="prospecting_unsubscribe.completed",
            target=suppression,
            metadata={"campaign_id": token.recipient.campaign_id},
        )
    return suppression, created


def campaign_metrics(campaign):
    counts = campaign.recipients.aggregate(
        enrolled=Count("id"),
        sent=Count(
            "id",
            filter=Q(messages__attempts__status=ProspectDeliveryAttempt.Status.SUCCEEDED),
            distinct=True,
        ),
        active=Count(
            "id",
            filter=Q(
                state__in=(
                    ProspectCampaignRecipient.State.SCHEDULED,
                    ProspectCampaignRecipient.State.ACTIVE,
                )
            ),
        ),
        completed=Count("id", filter=Q(state=ProspectCampaignRecipient.State.COMPLETED)),
        replied=Count("id", filter=Q(state=ProspectCampaignRecipient.State.REPLIED)),
        bounced=Count("id", filter=Q(state=ProspectCampaignRecipient.State.BOUNCED)),
        complained=Count("id", filter=Q(state=ProspectCampaignRecipient.State.COMPLAINED)),
        unsubscribed=Count("id", filter=Q(state=ProspectCampaignRecipient.State.UNSUBSCRIBED)),
        suppressed=Count("id", filter=Q(state=ProspectCampaignRecipient.State.SUPPRESSED)),
        failed=Count("id", filter=Q(state=ProspectCampaignRecipient.State.FAILED)),
    )
    from apps.outreach.models import ResendWebhookEvent

    mappings = ProspectMessage.objects.filter(recipient__campaign=campaign).values_list(
        "prospectprovideremail__provider_email_id", flat=True
    )
    events = ResendWebhookEvent.objects.filter(
        organization=campaign.organization, provider_email_id__in=mappings
    )
    counts.update(
        {
            "delivered": events.filter(event_type="email.delivered")
            .values("provider_email_id")
            .distinct()
            .count(),
            "opened": events.filter(event_type="email.opened")
            .values("provider_email_id")
            .distinct()
            .count(),
            "clicked": events.filter(event_type="email.clicked")
            .values("provider_email_id")
            .distinct()
            .count(),
        }
    )
    counts["eligible"] = counts["enrolled"] - counts["suppressed"]
    counts["rates"] = {
        name: (round(counts[name] * 100 / counts["sent"], 1) if counts["sent"] else None)
        for name in ("delivered", "opened", "clicked", "replied")
    }
    return counts
