"""Verified, replay-safe Resend event ingestion. No unverified payload reaches models."""

import base64
import hashlib
import hmac
import json
import re
import time
import urllib.request
from datetime import UTC, timedelta
from email.utils import parseaddr

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.organizations.models import Membership
from apps.organizations.services import active_membership

from .credentials import decrypt_password, encrypt_password, encryption_ready
from .models import (
    InvitationRecipient,
    OutreachDeliveryAttempt,
    OutreachProviderEmail,
    OutreachResponse,
    OutreachSMTPConfiguration,
    ResendWebhookConfiguration,
    ResendWebhookEvent,
)
from .responses import advance_recipient

EVENT_TYPES = {
    "email.sent",
    "email.delivered",
    "email.delivery_delayed",
    "email.bounced",
    "email.failed",
    "email.complained",
    "email.opened",
    "email.clicked",
    "email.received",
}
_MESSAGE_ID = re.compile(r"^<([0-9a-f]{64})@([A-Za-z0-9.-]+)>$")


@transaction.atomic
def save_webhook_configuration(*, organization, actor, signing_secret, enabled):
    membership = active_membership(actor, organization)
    if not membership or membership.role != Membership.Role.ADMIN:
        raise ValidationError("Organization Admin access is required.")
    configuration, _ = ResendWebhookConfiguration.objects.get_or_create(
        organization=organization, defaults={"updated_by": actor}
    )
    if signing_secret:
        if not signing_secret.startswith("whsec_"):
            raise ValidationError("Enter the Resend webhook signing secret from its dashboard.")
        try:
            key = base64.b64decode(signing_secret[6:], validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise ValidationError("Invalid webhook signing secret format.") from error
        if len(key) < 16:
            raise ValidationError("Invalid webhook signing secret format.")
        configuration.encrypted_signing_secret = encrypt_password(signing_secret)
    if enabled and (not configuration.encrypted_signing_secret or not encryption_ready()):
        raise ValidationError("Save a signing secret before enabling the webhook.")
    configuration.is_enabled = enabled
    configuration.updated_by = actor
    configuration.save()
    return configuration


def verify_signature(raw_body, headers, signing_secret, *, now=None):
    """Svix/Resend v1 signature over the raw request bytes, with a 5-minute window."""
    event_id = headers.get("svix-id", "")
    timestamp = headers.get("svix-timestamp", "")
    supplied = headers.get("svix-signature", "")
    if not event_id or len(event_id) > 120 or not timestamp.isdecimal() or not supplied:
        raise ValidationError("Invalid webhook signature.")
    now = int(time.time()) if now is None else now
    if abs(now - int(timestamp)) > 300:
        raise ValidationError("Invalid webhook signature.")
    try:
        key = base64.b64decode(signing_secret.removeprefix("whsec_"), validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise ValidationError("Invalid webhook signature.") from error
    signed = event_id.encode() + b"." + timestamp.encode() + b"." + raw_body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    if not any(
        hmac.compare_digest(part.split(",", 1)[1], expected)
        for part in supplied.split()
        if part.startswith("v1,")
    ):
        raise ValidationError("Invalid webhook signature.")
    return event_id


def _date(value):
    parsed = parse_datetime(value) if isinstance(value, str) else None
    if parsed is None:
        raise ValidationError("Invalid webhook event timestamp.")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _outbound_message(organization, provider_email_id, rfc_message_id):
    mapping = (
        OutreachProviderEmail.objects.filter(
            organization=organization, provider_email_id=provider_email_id
        )
        .select_related("message__recipient")
        .first()
    )
    if mapping:
        if rfc_message_id and mapping.rfc_message_id != rfc_message_id:
            return None
        return mapping.message
    persisted = (
        OutreachDeliveryAttempt.objects.filter(
            message__recipient__batch__campaign__organization=organization,
            status__in=(
                OutreachDeliveryAttempt.Status.PENDING,
                OutreachDeliveryAttempt.Status.SUCCEEDED,
            ),
            submitted_rfc_message_id=rfc_message_id,
        )
        .select_related("message__recipient")
        .first()
    )
    if persisted and rfc_message_id:
        return persisted.message
    match = _MESSAGE_ID.fullmatch(rfc_message_id)
    if not match:
        return None
    attempt = (
        OutreachDeliveryAttempt.objects.filter(
            message__recipient__batch__campaign__organization=organization,
            status__in=(
                OutreachDeliveryAttempt.Status.PENDING,
                OutreachDeliveryAttempt.Status.SUCCEEDED,
            ),
            idempotency_key=match.group(1),
        )
        .select_related("message__recipient")
        .first()
    )
    if (
        attempt
        and attempt.message.from_address.rsplit("@", 1)[-1].lower() == match.group(2).lower()
    ):
        return attempt.message
    return None


def _sent_details(organization, email_id):
    """Read one Resend-signed event's email ID; never search by subject/address."""
    config = OutreachSMTPConfiguration.objects.filter(organization=organization).first()
    if not config or config.host.lower() != "smtp.resend.com" or not config.encrypted_password:
        return None
    if not re.fullmatch(r"[A-Za-z0-9-]{1,120}", email_id):
        return None
    try:
        api_key = decrypt_password(config.encrypted_password)
        request = urllib.request.Request(
            f"https://api.resend.com/emails/{email_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "BB-Builders-Outreach/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(131073)
        if len(body) > 131072:
            return None
        details = json.loads(body)
        return details if isinstance(details, dict) and details.get("id") == email_id else None
    except (OSError, ValueError, ValidationError, KeyError, TypeError):
        return None


def _exact_sent_message(organization, details, rfc_message_id):
    """Match exact text, allowing only one SMTP-added terminal LF.

    Repeated identical invitations remain ambiguous unless Resend's creation time
    isolates one delivery attempt within a short, fail-closed acceptance window.
    """
    if (
        not details
        or not rfc_message_id
        or details.get("message_id") != rfc_message_id
        or not isinstance(details.get("text"), str)
    ):
        return None
    from_address = parseaddr(str(details.get("from") or ""))[1].lower()
    to_addresses = details.get("to")
    if not isinstance(to_addresses, list) or len(to_addresses) != 1:
        return None
    to_address = parseaddr(str(to_addresses[0]))[1].lower()
    if not from_address or not to_address:
        return None
    provider_text = details["text"]
    acceptable_texts = [provider_text]
    if provider_text.endswith("\n"):
        acceptable_texts.append(provider_text[:-1])
    candidates = OutreachDeliveryAttempt.objects.filter(
        message__recipient__batch__campaign__organization=organization,
        status__in=(
            OutreachDeliveryAttempt.Status.PENDING,
            OutreachDeliveryAttempt.Status.SUCCEEDED,
        ),
        message__from_address__iexact=from_address,
        message__to_address__iexact=to_address,
        message__subject=details.get("subject"),
        message__body__in=acceptable_texts,
    ).select_related("message")
    matches = list(candidates[:2])
    if len(matches) != 1:
        created_at = parse_datetime(details.get("created_at", ""))
        if created_at is None or created_at.tzinfo is None:
            return None
        matches = list(
            candidates.filter(
                attempted_at__gte=created_at - timedelta(seconds=60),
                attempted_at__lte=created_at + timedelta(seconds=5),
            )[:2]
        )
    return matches[0].message if len(matches) == 1 else None


def _apply_outbound_event(event, message):
    recipient = InvitationRecipient.objects.select_for_update().get(pk=message.recipient_id)
    delivery = {
        "email.sent": "sent",
        "email.delivered": "delivered",
        "email.delivery_delayed": "delayed",
        "email.bounced": "bounced",
        "email.failed": "failed",
        "email.complained": "complained",
    }.get(event.event_type)
    engagement = {"email.opened": "opened", "email.clicked": "clicked"}.get(event.event_type)
    changes = {}
    delivery_rank = {
        "not_sent": 0,
        "sent": 1,
        "delayed": 1,
        "delivered": 2,
        "bounced": 3,
        "failed": 3,
        "complained": 4,
    }
    if (
        delivery
        and (not recipient.delivery_event_at or event.occurred_at >= recipient.delivery_event_at)
        and delivery_rank[delivery] >= delivery_rank.get(recipient.delivery_state, 0)
    ):
        changes.update(delivery_state=delivery, delivery_event_at=event.occurred_at)
    if engagement and (
        not recipient.engagement_event_at or event.occurred_at >= recipient.engagement_event_at
    ):
        changes.update(engagement_state=engagement, engagement_event_at=event.occurred_at)
    if changes:
        InvitationRecipient.objects.filter(pk=recipient.pk).update(**changes)
    if event.event_type == "email.delivered":
        advance_recipient(
            recipient, "delivered", source="provider", reason="Provider delivery evidence."
        )
    elif event.event_type in {"email.opened", "email.clicked"}:
        advance_recipient(
            recipient, "opened", source="provider", reason="Provider-reported engagement."
        )
    elif event.event_type in {"email.bounced", "email.failed"}:
        advance_recipient(
            recipient, "failed", source="provider", reason="Provider delivery failure."
        )


def _reconcile_outbound_event(event):
    if not event.provider_email_id or event.event_type == "email.received":
        return None
    organization = event.organization
    message = _outbound_message(organization, event.provider_email_id, event.rfc_message_id)
    if message is None:
        message = _exact_sent_message(
            organization, _sent_details(organization, event.provider_email_id), event.rfc_message_id
        )
    if message is None:
        return None
    mapping, created = OutreachProviderEmail.objects.get_or_create(
        organization=organization,
        provider_email_id=event.provider_email_id,
        defaults={
            "message": message,
            "rfc_message_id": event.rfc_message_id,
            "first_event": event,
        },
    )
    if mapping.message_id != message.pk or mapping.rfc_message_id != event.rfc_message_id:
        return None
    # Previously accepted events remain immutable; replay only their projection.
    if created or event.message_id is None:
        for stored in ResendWebhookEvent.objects.filter(
            organization=organization, provider_email_id=event.provider_email_id
        ).order_by("occurred_at", "pk"):
            if stored.rfc_message_id == mapping.rfc_message_id:
                _apply_outbound_event(stored, message)
    else:
        _apply_outbound_event(event, message)
    return message


def _received_details(organization, email_id):
    """Resend inbound webhooks omit body/headers; fetch only this trusted email ID."""
    config = OutreachSMTPConfiguration.objects.filter(organization=organization).first()
    if not config or config.host.lower() != "smtp.resend.com" or not config.encrypted_password:
        return None
    if not re.fullmatch(r"[A-Za-z0-9-]{1,120}", email_id):
        return None
    try:
        api_key = decrypt_password(config.encrypted_password)
        request = urllib.request.Request(
            f"https://api.resend.com/emails/receiving/{email_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "BB-Builders-Outreach/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(131073)
        if len(body) > 131072:
            return None
        data = json.loads(body)
        return data if data.get("id") == email_id else None
    except (OSError, ValueError, ValidationError, KeyError, TypeError):
        return None


def _header(headers, key):
    if isinstance(headers, dict):
        return str(headers.get(key) or headers.get(key.title()) or "")
    if isinstance(headers, list):
        for item in headers:
            if isinstance(item, dict) and str(item.get("name", "")).lower() == key:
                return str(item.get("value", ""))
    return ""


def _inbound_match(organization, details, from_address, to_address):
    """Resolve one exact outbound thread; never infer a reply from address or subject."""
    if not details:
        return None, "", ""
    headers = details.get("headers", {})
    in_reply_to = _header(headers, "in-reply-to")[:255]
    references = _header(headers, "references")[:1000]
    thread_ids = {part for part in [in_reply_to, *references.split()] if part}
    if not thread_ids:
        return None, in_reply_to, references
    mappings = list(
        OutreachProviderEmail.objects.filter(
            organization=organization, rfc_message_id__in=thread_ids
        ).select_related("message__recipient__batch__campaign")[:2]
    )
    if not mappings:
        # Provider-generated RFC IDs may not have mapped on the first outbound webhook.
        # Reconcile only events whose exact RFC ID appears in the received headers.
        seen_provider_ids = set()
        for event in (
            ResendWebhookEvent.objects.filter(
                organization=organization, rfc_message_id__in=thread_ids
            )
            .exclude(event_type="email.received")
            .order_by("pk")
        ):
            if event.provider_email_id in seen_provider_ids:
                continue
            seen_provider_ids.add(event.provider_email_id)
            _reconcile_outbound_event(event)
        mappings = list(
            OutreachProviderEmail.objects.filter(
                organization=organization, rfc_message_id__in=thread_ids
            ).select_related("message__recipient__batch__campaign")[:2]
        )
    if len(mappings) != 1:
        return None, in_reply_to, references
    message = mappings[0].message
    recipient = message.recipient
    detail_from = parseaddr(str(details.get("from") or ""))[1].lower()
    detail_to = details.get("to")
    detail_to_address = (
        parseaddr(str(detail_to[0]))[1].lower()
        if isinstance(detail_to, list) and len(detail_to) == 1
        else ""
    )
    if (
        from_address != recipient.email.lower()
        or to_address not in {message.reply_to.lower(), message.from_address.lower()}
        or detail_from != from_address
        or detail_to_address != to_address
    ):
        return None, in_reply_to, references
    return message, in_reply_to, references


def _reconcile_inbound_event(event):
    """Enrich and assign one previously unassigned response on signed replay."""
    response = OutreachResponse.objects.select_for_update().filter(provider_event=event).first()
    if not response or response.recipient_id or not event.provider_email_id:
        return response
    details = _received_details(event.organization, event.provider_email_id)
    message, in_reply_to, references = _inbound_match(
        event.organization, details, response.from_address, response.to_address
    )
    if not message:
        return response
    recipient = message.recipient
    text = details.get("text")
    # A metadata-only row is enriched once in place; its identity and event stay fixed.
    OutreachResponse.objects.filter(pk=response.pk, recipient__isnull=True).update(
        project=recipient.batch.campaign.project,
        recipient=recipient,
        message=message,
        in_reply_to=in_reply_to,
        references=references,
        body_text=text.replace("\x00", "\ufffd")[:10000] if isinstance(text, str) else "",
        content_status="retrieved",
    )
    InvitationRecipient.objects.filter(pk=recipient.pk).update(response_state="responded")
    advance_recipient(recipient, "responded", source="provider", reason="Correlated inbound reply.")
    response.refresh_from_db()
    return response


def _inbound_response(configuration, event, data, details):
    organization = configuration.organization
    provider_email_id = str(data.get("email_id") or "")[:120]
    if not provider_email_id:
        return None
    existing = OutreachResponse.objects.filter(
        organization=organization, channel="inbound_email", provider_email_id=provider_email_id
    ).first()
    if existing:
        return existing
    from_address = parseaddr(str(data.get("from") or ""))[1].lower()
    recipients = data.get("to") or []
    to_address = (
        parseaddr(str(recipients[0]))[1].lower()
        if isinstance(recipients, list) and recipients
        else ""
    )
    message, in_reply_to, references = _inbound_match(
        organization, details, from_address, to_address
    )
    recipient = message.recipient if message else None
    campaign = recipient.batch.campaign if recipient else None
    text = details.get("text") if details else None
    response = OutreachResponse.objects.create(
        organization=organization,
        project=campaign.project if campaign else None,
        recipient=recipient,
        message=message,
        provider_event=event,
        provider_email_id=provider_email_id,
        rfc_message_id=str(data.get("message_id") or "")[:255],
        in_reply_to=in_reply_to,
        references=references,
        from_address=from_address,
        to_address=to_address,
        subject=str(data.get("subject") or "")[:255],
        body_text=text.replace("\x00", "\ufffd")[:10000] if isinstance(text, str) else "",
        content_status="retrieved" if details else "metadata_only",
        attachment_count=min(len(data.get("attachments") or []), 10000),
        channel="inbound_email",
        outcome="responded",
        occurred_at=event.occurred_at,
    )
    if recipient:
        InvitationRecipient.objects.filter(pk=recipient.pk).update(response_state="responded")
        advance_recipient(
            recipient, "responded", source="provider", reason="Correlated inbound reply."
        )
    return response


@transaction.atomic
def ingest_verified_event(configuration, raw_body, headers):
    if not configuration.is_enabled or not configuration.encrypted_signing_secret:
        raise ValidationError("Webhook is not enabled.")
    event_id = verify_signature(
        raw_body, headers, decrypt_password(configuration.encrypted_signing_secret)
    )
    configuration = ResendWebhookConfiguration.objects.select_for_update().get(pk=configuration.pk)
    if not configuration.is_enabled:
        raise ValidationError("Webhook is not enabled.")
    if existing := ResendWebhookEvent.objects.filter(
        configuration=configuration, webhook_id=event_id
    ).first():
        if existing.event_type == "email.received":
            _reconcile_inbound_event(existing)
        else:
            _reconcile_outbound_event(existing)
        return existing, False
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeError) as error:
        raise ValidationError("Invalid webhook payload.") from error
    if not isinstance(payload, dict):
        raise ValidationError("Invalid webhook payload.")
    event_type = payload.get("type")
    data = payload.get("data")
    if event_type not in EVENT_TYPES or not isinstance(data, dict):
        raise ValidationError("Unsupported webhook event.")
    provider_email_id = str(data.get("email_id") or "")[:120]
    rfc_message_id = str(data.get("message_id") or "")[:255]
    occurred_at = _date(payload.get("created_at"))
    if event_type != "email.received" and provider_email_id:
        duplicate = ResendWebhookEvent.objects.filter(
            organization=configuration.organization,
            provider_email_id=provider_email_id,
            event_type=event_type,
            occurred_at=occurred_at,
            rfc_message_id=rfc_message_id,
        ).first()
        if duplicate:
            _reconcile_outbound_event(duplicate)
            return duplicate, False
    details = (
        _received_details(configuration.organization, provider_email_id)
        if event_type == "email.received"
        else None
    )
    message = None
    if event_type != "email.received" and provider_email_id:
        message = _outbound_message(configuration.organization, provider_email_id, rfc_message_id)
    event = ResendWebhookEvent.objects.create(
        configuration=configuration,
        organization=configuration.organization,
        webhook_id=event_id,
        event_type=event_type,
        provider_email_id=provider_email_id,
        rfc_message_id=rfc_message_id,
        message=message,
        recipient=message.recipient if message else None,
        occurred_at=occurred_at,
    )
    if event_type == "email.received":
        _inbound_response(configuration, event, data, details)
    else:
        _reconcile_outbound_event(event)
    return event, True
