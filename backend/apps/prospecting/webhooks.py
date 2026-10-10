# ruff: noqa: E501
from datetime import timedelta
from email.utils import parseaddr

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.outreach.models import OutreachProviderEmail, ResendWebhookEvent
from apps.projects.audit import record_event

from .campaigns import suppress_email
from .models import (
    ProspectCampaignRecipient,
    ProspectDeliveryAttempt,
    ProspectProviderEmail,
    ProspectReply,
    ProspectSuppression,
)


def _header(headers, key):
    if isinstance(headers, dict):
        return str(headers.get(key) or headers.get(key.title()) or "")
    if isinstance(headers, list):
        for item in headers:
            if isinstance(item, dict) and str(item.get("name", "")).lower() == key:
                return str(item.get("value", ""))
    return ""


def outbound_message(organization, provider_email_id, rfc_message_id):
    mapping = (
        ProspectProviderEmail.objects.filter(
            organization=organization, provider_email_id=provider_email_id
        )
        .select_related("message")
        .first()
    )
    if mapping:
        return (
            mapping.message
            if not rfc_message_id or mapping.rfc_message_id == rfc_message_id
            else None
        )
    matches = list(
        ProspectDeliveryAttempt.objects.filter(
            message__recipient__campaign__organization=organization,
            status__in=(
                ProspectDeliveryAttempt.Status.PENDING,
                ProspectDeliveryAttempt.Status.SUCCEEDED,
            ),
            rfc_message_id=rfc_message_id,
        ).select_related("message")[:2]
    )
    return matches[0].message if rfc_message_id and len(matches) == 1 else None


def _sent_details(organization, provider_email_id):
    """Reuse the bounded, exact-ID Resend retrieval used by M3 Outreach."""
    from apps.outreach.resend_webhooks import _sent_details as retrieve_sent_details

    return retrieve_sent_details(organization, provider_email_id)


def _exact_sent_message(organization, details):
    """Resolve exactly one Prospecting message from provider-returned immutable content."""
    if not details or not isinstance(details.get("text"), str):
        return None
    from_address = parseaddr(str(details.get("from") or ""))[1].lower()
    to_addresses = details.get("to")
    if not isinstance(to_addresses, list) or len(to_addresses) != 1:
        return None
    to_address = parseaddr(str(to_addresses[0]))[1].lower()
    created_at = parse_datetime(str(details.get("created_at") or ""))
    if not from_address or not to_address or created_at is None or created_at.tzinfo is None:
        return None
    provider_text = details["text"]
    acceptable_texts = [provider_text]
    if provider_text.endswith("\n"):
        acceptable_texts.append(provider_text[:-1])
    candidates = ProspectDeliveryAttempt.objects.filter(
        message__recipient__campaign__organization=organization,
        status__in=(
            ProspectDeliveryAttempt.Status.PENDING,
            ProspectDeliveryAttempt.Status.SUCCEEDED,
        ),
        message__from_address__iexact=from_address,
        message__to_address__iexact=to_address,
        message__subject=details.get("subject"),
        message__body__in=acceptable_texts,
        attempted_at__gte=created_at - timedelta(seconds=60),
        attempted_at__lte=created_at + timedelta(seconds=5),
    ).select_related("message")
    matches = list(candidates[:2])
    if len(matches) != 1:
        return None

    # Fail closed if these same provider details also identify an M3 Outreach message.
    from apps.outreach.resend_webhooks import _exact_sent_message as exact_outreach_message

    provider_rfc_message_id = str(details.get("message_id") or "")
    if exact_outreach_message(organization, details, provider_rfc_message_id) is not None:
        return None
    return matches[0].message


def _apply_outbound_event(event, message):
    recipient = ProspectCampaignRecipient.objects.select_for_update().get(pk=message.recipient_id)
    if event.event_type == "email.bounced":
        suppress_email(
            organization=event.organization,
            email=recipient.normalized_email,
            reason=ProspectSuppression.Reason.HARD_BOUNCE,
            recipient=recipient,
            message=message,
            provider_event=event,
        )
    elif event.event_type == "email.complained":
        suppress_email(
            organization=event.organization,
            email=recipient.normalized_email,
            reason=ProspectSuppression.Reason.COMPLAINT,
            recipient=recipient,
            message=message,
            provider_event=event,
        )
    elif event.event_type == "email.failed":
        _stop(recipient, ProspectCampaignRecipient.State.FAILED, "Provider delivery failure")


def _stop(recipient, state, reason):
    if recipient.state in {
        ProspectCampaignRecipient.State.UNSUBSCRIBED,
        ProspectCampaignRecipient.State.COMPLAINED,
        ProspectCampaignRecipient.State.BOUNCED,
    }:
        return
    ProspectCampaignRecipient.objects.filter(pk=recipient.pk).update(
        state=state, next_due_at=None, stop_reason=reason
    )


@transaction.atomic
def reconcile_outbound_event(event):
    if event.message_id or not event.provider_email_id:
        return None
    message = outbound_message(event.organization, event.provider_email_id, event.rfc_message_id)
    provider_rfc_message_id = event.rfc_message_id
    if message is None:
        if OutreachProviderEmail.objects.filter(
            organization=event.organization, provider_email_id=event.provider_email_id
        ).exists():
            return None
        details = _sent_details(event.organization, event.provider_email_id)
        if not details or details.get("id") != event.provider_email_id:
            return None
        provider_rfc_message_id = str(details.get("message_id") or event.rfc_message_id)[:255]
        message = _exact_sent_message(event.organization, details)
    if message is None or not provider_rfc_message_id:
        return None
    # A durable provider ID can belong to only one outbound domain.
    if OutreachProviderEmail.objects.filter(
        organization=event.organization, provider_email_id=event.provider_email_id
    ).exists():
        return None
    mapping, _ = ProspectProviderEmail.objects.get_or_create(
        organization=event.organization,
        provider_email_id=event.provider_email_id,
        defaults={
            "message": message,
            "rfc_message_id": provider_rfc_message_id,
            "provider_event": event,
        },
    )
    if mapping.message_id != message.pk or mapping.rfc_message_id != provider_rfc_message_id:
        return None
    # Once the exact provider ID is mapped, replay every immutable stored event in order.
    for stored in ResendWebhookEvent.objects.filter(
        organization=event.organization,
        provider_email_id=event.provider_email_id,
    ).order_by("occurred_at", "pk"):
        _apply_outbound_event(stored, message)
    return message


@transaction.atomic
def reconcile_inbound_event(event, details):
    if event.message_id or not details or not event.provider_email_id:
        return None
    headers = details.get("headers", {})
    in_reply_to = _header(headers, "in-reply-to")[:255]
    references = _header(headers, "references")[:1000]
    thread_ids = {value for value in (in_reply_to, *references.split()) if value}
    if not thread_ids:
        return None
    mappings = list(
        ProspectProviderEmail.objects.filter(
            organization=event.organization, rfc_message_id__in=thread_ids
        ).select_related("message__recipient")[:2]
    )
    if len(mappings) != 1:
        return None
    mapping = mappings[0]
    if OutreachProviderEmail.objects.filter(
        organization=event.organization, rfc_message_id__in=thread_ids
    ).exists():
        return None
    message, recipient = mapping.message, mapping.message.recipient
    from_address = parseaddr(str(details.get("from") or ""))[1].lower()
    to_values = details.get("to")
    to_address = (
        parseaddr(str(to_values[0]))[1].lower()
        if isinstance(to_values, list) and len(to_values) == 1
        else ""
    )
    if from_address != recipient.normalized_email or to_address not in {
        message.from_address.lower(),
        message.reply_to.lower(),
    }:
        return None
    reply, created = ProspectReply.objects.get_or_create(
        provider_event=event,
        defaults={
            "recipient": recipient,
            "message": message,
            "provider_reference": event.provider_email_id,
            "from_address": from_address,
            "to_address": to_address,
            "subject": str(details.get("subject") or "")[:255],
            "body_text": str(details.get("text") or "").replace("\x00", "�")[:10000],
            "in_reply_to": in_reply_to,
            "references": references,
            "received_at": event.occurred_at,
        },
    )
    if created:
        _stop(recipient, ProspectCampaignRecipient.State.REPLIED, "Inbound reply received")
        record_event(
            organization=event.organization,
            project=None,
            actor=None,
            action_code="prospecting_reply.received",
            target=reply,
            metadata={"campaign_id": recipient.campaign_id},
        )
    return reply


def reconcile_event(event, details=None):
    if event.event_type == "email.received":
        return reconcile_inbound_event(event, details)
    return reconcile_outbound_event(event)
