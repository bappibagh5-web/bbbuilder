# ruff: noqa: E501
from email.utils import parseaddr

from django.db import transaction

from apps.outreach.models import OutreachProviderEmail
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
    if message is None:
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
            "rfc_message_id": event.rfc_message_id,
            "provider_event": event,
        },
    )
    if mapping.message_id != message.pk or mapping.rfc_message_id != event.rfc_message_id:
        return None
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
