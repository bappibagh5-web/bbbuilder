from collections import defaultdict
from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.outreach.models import ResendWebhookEvent

from .models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectDeliveryAttempt,
    ProspectMessage,
    ProspectProviderEmail,
    ProspectReply,
    ProspectSuppression,
)

RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90, "all": None}
EVENT_TYPES = {
    "delivered": "email.delivered",
    "opened": "email.opened",
    "clicked": "email.clicked",
    "bounced": "email.bounced",
    "complained": "email.complained",
}


def analytics_window(value):
    key = value if value in RANGE_DAYS else "30d"
    days = RANGE_DAYS[key]
    return key, timezone.now() - timedelta(days=days) if days else None


def _rate(numerator, denominator):
    return round(numerator * 100 / denominator, 1) if denominator else None


def _campaign_base(organization, campaign_id=None):
    queryset = ProspectCampaign.objects.filter(organization=organization)
    return queryset.filter(pk=campaign_id) if campaign_id else queryset


def _message_queryset(organization, since=None, campaign_id=None):
    queryset = ProspectMessage.objects.filter(
        recipient__campaign__organization=organization,
        attempts__status=ProspectDeliveryAttempt.Status.SUCCEEDED,
    ).distinct()
    if campaign_id:
        queryset = queryset.filter(recipient__campaign_id=campaign_id)
    if since:
        queryset = queryset.filter(attempts__completed_at__gte=since)
    return queryset


def _event_queryset(organization, message_ids, since=None):
    provider_ids = ProspectProviderEmail.objects.filter(message_id__in=message_ids).values(
        "provider_email_id"
    )
    queryset = ResendWebhookEvent.objects.filter(
        organization=organization, provider_email_id__in=provider_ids
    )
    if since:
        queryset = queryset.filter(occurred_at__gte=since)
    return queryset


def _event_counts(events):
    result = {}
    for key, event_type in EVENT_TYPES.items():
        result[key] = (
            events.filter(event_type=event_type).values("provider_email_id").distinct().count()
        )
    return result


def metric_bundle(organization, *, since=None, campaign_id=None):
    messages = _message_queryset(organization, since, campaign_id)
    message_ids = messages.values_list("id", flat=True)
    recipient_ids = messages.values("recipient_id")
    events = _event_queryset(organization, message_ids, since)
    event_counts = _event_counts(events)
    contacted = messages.values("recipient_id").distinct().count()
    sent = messages.count()
    replies = ProspectReply.objects.filter(
        recipient__campaign__organization=organization,
        message_id__in=message_ids,
    )
    suppressions = ProspectSuppression.objects.filter(
        organization=organization,
        source_recipient_id__in=recipient_ids,
    )
    if campaign_id:
        replies = replies.filter(recipient__campaign_id=campaign_id)
        suppressions = suppressions.filter(source_recipient__campaign_id=campaign_id)
    if since:
        replies = replies.filter(received_at__gte=since)
        suppressions = suppressions.filter(created_at__gte=since)
    replied = replies.values("recipient_id").distinct().count()
    unsubscribed = (
        suppressions.filter(reason=ProspectSuppression.Reason.UNSUBSCRIBE)
        .values("source_recipient_id")
        .distinct()
        .count()
    )
    metrics = {
        "prospects_contacted": contacted,
        "messages_sent": sent,
        **event_counts,
        "replied": replied,
        "unsubscribed": unsubscribed,
    }
    metrics["rates"] = {
        "delivery": _rate(metrics["delivered"], sent),
        "open": _rate(metrics["opened"], metrics["delivered"]),
        "click": _rate(metrics["clicked"], metrics["delivered"]),
        "reply": _rate(replied, contacted),
        "bounce": _rate(metrics["bounced"], sent),
        "unsubscribe": _rate(unsubscribed, contacted),
    }
    metrics["tracking"] = {
        "available": events.exists(),
        "event_count": events.count(),
        "message": (
            "Provider tracking events have been received."
            if events.exists()
            else "Provider events have not been received for these sent messages."
            if sent
            else "No emails were sent in this period."
        ),
    }
    return metrics


def trend_data(organization, *, since=None):
    messages = _message_queryset(organization, since)
    events = _event_queryset(organization, messages.values_list("id", flat=True), since)
    replies = ProspectReply.objects.filter(message_id__in=messages.values("id"))
    if since:
        replies = replies.filter(received_at__gte=since)
    buckets = defaultdict(lambda: {"sent": 0, "delivered": 0, "opened": 0, "replied": 0})
    sent_rows = messages.values("id", "attempts__completed_at")
    for row in sent_rows:
        if row["attempts__completed_at"]:
            buckets[row["attempts__completed_at"].date().isoformat()]["sent"] += 1
    seen = set()
    for row in events.filter(event_type__in=("email.delivered", "email.opened")).values(
        "provider_email_id", "event_type", "occurred_at"
    ):
        key = (row["provider_email_id"], row["event_type"])
        if key in seen:
            continue
        seen.add(key)
        metric = "delivered" if row["event_type"] == "email.delivered" else "opened"
        buckets[row["occurred_at"].date().isoformat()][metric] += 1
    for row in replies.values("recipient_id", "received_at"):
        buckets[row["received_at"].date().isoformat()]["replied"] += 1
    return [{"date": date, **buckets[date]} for date in sorted(buckets)]


def campaign_rows(organization, *, since=None, sort="newest", campaign_id=None):
    campaigns = _campaign_base(organization, campaign_id).annotate(
        enrolled=Count("recipients", distinct=True),
        active=Count(
            "recipients",
            filter=Q(recipients__state__in=("scheduled", "active")),
            distinct=True,
        ),
        completed=Count("recipients", filter=Q(recipients__state="completed"), distinct=True),
        cancelled=Count("recipients", filter=Q(recipients__state="cancelled"), distinct=True),
        step_count=Count("sequence_steps", filter=Q(sequence_steps__enabled=True), distinct=True),
    )
    campaign_list = list(campaigns[:250])
    campaign_ids = [item.pk for item in campaign_list]
    messages = _message_queryset(organization, since).filter(
        recipient__campaign_id__in=campaign_ids
    )
    message_rows = list(messages.values("id", "recipient_id", "recipient__campaign_id"))
    message_campaign = {row["id"]: row["recipient__campaign_id"] for row in message_rows}
    recipient_campaign = {
        row["recipient_id"]: row["recipient__campaign_id"] for row in message_rows
    }
    buckets = defaultdict(
        lambda: {
            "messages": set(),
            "recipients": set(),
            "events": defaultdict(set),
            "replies": set(),
            "unsubscribed": set(),
        }
    )
    for row in message_rows:
        bucket = buckets[row["recipient__campaign_id"]]
        bucket["messages"].add(row["id"])
        bucket["recipients"].add(row["recipient_id"])
    provider_campaign = {}
    for provider_id, message_id in ProspectProviderEmail.objects.filter(
        message_id__in=message_campaign
    ).values_list("provider_email_id", "message_id"):
        provider_campaign[provider_id] = message_campaign[message_id]
    events = ResendWebhookEvent.objects.filter(
        organization=organization,
        provider_email_id__in=provider_campaign,
        event_type__in=EVENT_TYPES.values(),
    )
    if since:
        events = events.filter(occurred_at__gte=since)
    event_names = {value: key for key, value in EVENT_TYPES.items()}
    for provider_id, event_type in events.values_list("provider_email_id", "event_type"):
        buckets[provider_campaign[provider_id]]["events"][event_names[event_type]].add(provider_id)
    replies = ProspectReply.objects.filter(message_id__in=message_campaign)
    if since:
        replies = replies.filter(received_at__gte=since)
    for recipient_id in replies.values_list("recipient_id", flat=True):
        if recipient_id in recipient_campaign:
            buckets[recipient_campaign[recipient_id]]["replies"].add(recipient_id)
    suppressions = ProspectSuppression.objects.filter(
        organization=organization,
        reason=ProspectSuppression.Reason.UNSUBSCRIBE,
        source_recipient_id__in=recipient_campaign,
    )
    if since:
        suppressions = suppressions.filter(created_at__gte=since)
    for recipient_id in suppressions.values_list("source_recipient_id", flat=True):
        if recipient_id in recipient_campaign:
            buckets[recipient_campaign[recipient_id]]["unsubscribed"].add(recipient_id)
    activity = dict(
        ProspectDeliveryAttempt.objects.filter(
            message_id__in=message_campaign,
            status=ProspectDeliveryAttempt.Status.SUCCEEDED,
        )
        .values("message__recipient__campaign_id")
        .annotate(value=Max("completed_at"))
        .values_list("message__recipient__campaign_id", "value")
    )
    rows = []
    for campaign in campaign_list:
        bucket = buckets[campaign.pk]
        sent = len(bucket["messages"])
        contacted = len(bucket["recipients"])
        event_counts = {key: len(bucket["events"][key]) for key in EVENT_TYPES}
        replied = len(bucket["replies"])
        unsubscribed = len(bucket["unsubscribed"])
        tracking_available = any(event_counts.values())
        metrics = {
            "prospects_contacted": contacted,
            "messages_sent": sent,
            **event_counts,
            "replied": replied,
            "unsubscribed": unsubscribed,
            "rates": {
                "delivery": _rate(event_counts["delivered"], sent),
                "open": _rate(event_counts["opened"], event_counts["delivered"]),
                "click": _rate(event_counts["clicked"], event_counts["delivered"]),
                "reply": _rate(replied, contacted),
                "bounce": _rate(event_counts["bounced"], sent),
                "unsubscribe": _rate(unsubscribed, contacted),
            },
            "tracking": {
                "available": tracking_available,
                "event_count": sum(len(values) for values in bucket["events"].values()),
                "message": (
                    "Provider tracking events have been received."
                    if tracking_available
                    else "Provider events have not been received for these sent messages."
                    if sent
                    else "No emails were sent in this period."
                ),
            },
        }
        rows.append(
            {
                "id": campaign.pk,
                "name": campaign.name,
                "status": campaign.status,
                "launched_at": campaign.launched_at,
                "created_at": campaign.created_at,
                "last_activity": activity.get(campaign.pk),
                "enrolled": campaign.enrolled,
                "active": campaign.active,
                "completed": campaign.completed,
                "cancelled": campaign.cancelled,
                "step_count": campaign.step_count,
                **metrics,
            }
        )
    sorters = {
        "sent": lambda item: (item["messages_sent"], item["id"]),
        "open_rate": lambda item: (item["rates"]["open"] or -1, item["id"]),
        "reply_rate": lambda item: (item["rates"]["reply"] or -1, item["id"]),
        "newest": lambda item: (item["created_at"], item["id"]),
    }
    return sorted(rows, key=sorters.get(sort, sorters["newest"]), reverse=True)


def sequence_step_rows(organization, campaign, since=None):
    version = campaign.versions.order_by("-version_number", "-id").first()
    if not version:
        return []
    rows = []
    for step in version.steps.order_by("step_number", "id"):
        messages = _message_queryset(organization, since, campaign.pk).filter(step_version=step)
        events = _event_queryset(organization, messages.values("id"), since)
        replies = ProspectReply.objects.filter(message__in=messages)
        if since:
            replies = replies.filter(received_at__gte=since)
        counts = _event_counts(events)
        sent = messages.count()
        rows.append(
            {
                "id": step.pk,
                "step_number": step.step_number,
                "label": step.label
                or (
                    "Initial email"
                    if step.step_number == 1
                    else f"Follow-up {step.step_number - 1}"
                ),
                "sent": sent,
                **counts,
                "replied": replies.values("recipient_id").distinct().count(),
            }
        )
    return rows


def recipient_rows(organization, *, since=None, campaign_id=None, engagement="all", search=""):
    recipients = ProspectCampaignRecipient.objects.filter(campaign__organization=organization)
    if campaign_id:
        recipients = recipients.filter(campaign_id=campaign_id)
    if search:
        recipients = recipients.filter(
            Q(contact_name__icontains=search)
            | Q(company_name__icontains=search)
            | Q(normalized_email__icontains=search)
        )
    recipient_list = list(
        recipients.select_related("campaign").order_by("-enrolled_at", "-id")[:500]
    )
    recipient_ids = [item.pk for item in recipient_list]
    attempts = ProspectDeliveryAttempt.objects.filter(
        message__recipient_id__in=recipient_ids,
        status=ProspectDeliveryAttempt.Status.SUCCEEDED,
    ).select_related("message__step_version")
    if since:
        attempts = attempts.filter(completed_at__gte=since)
    messages_by_recipient = defaultdict(dict)
    message_recipient = {}
    sent_at = {}
    for attempt in attempts:
        message = attempt.message
        messages_by_recipient[message.recipient_id][message.pk] = message
        message_recipient[message.pk] = message.recipient_id
        timestamp = attempt.completed_at or attempt.attempted_at
        if message.recipient_id not in sent_at or timestamp < sent_at[message.recipient_id]:
            sent_at[message.recipient_id] = timestamp
    provider_message = dict(
        ProspectProviderEmail.objects.filter(message_id__in=message_recipient).values_list(
            "provider_email_id", "message_id"
        )
    )
    events = ResendWebhookEvent.objects.filter(
        organization=organization,
        provider_email_id__in=provider_message,
        event_type__in=EVENT_TYPES.values(),
    )
    if since:
        events = events.filter(occurred_at__gte=since)
    events_by_recipient = defaultdict(lambda: defaultdict(list))
    event_names = {value: key for key, value in EVENT_TYPES.items()}
    for provider_id, event_type, occurred_at in events.values_list(
        "provider_email_id", "event_type", "occurred_at"
    ):
        recipient_id = message_recipient[provider_message[provider_id]]
        events_by_recipient[recipient_id][event_names[event_type]].append(occurred_at)
    replies_by_recipient = {}
    replies = ProspectReply.objects.filter(
        recipient_id__in=recipient_ids,
        message_id__in=message_recipient,
    ).order_by("received_at")
    if since:
        replies = replies.filter(received_at__gte=since)
    for reply in replies:
        replies_by_recipient.setdefault(reply.recipient_id, reply)
    suppressions_by_recipient = {
        item.source_recipient_id: item
        for item in ProspectSuppression.objects.filter(
            source_recipient_id__in=recipient_ids,
            active=True,
        ).order_by("created_at")
    }
    result = []
    for recipient in recipient_list:
        messages = list(messages_by_recipient[recipient.pk].values())
        message_ids = [item.pk for item in messages]
        if not message_ids and since:
            continue
        grouped = {}
        for event_type in EVENT_TYPES:
            timestamps = events_by_recipient[recipient.pk][event_type]
            grouped[event_type] = {
                "first": min(timestamps) if timestamps else None,
                "last": max(timestamps) if timestamps else None,
                "count": len(timestamps),
            }
        reply = replies_by_recipient.get(recipient.pk)
        suppression = suppressions_by_recipient.get(recipient.pk)
        latest_message = max(
            messages,
            key=lambda item: item.step_version.step_number,
            default=None,
        )
        flags = {
            "opened": bool(grouped["opened"]["count"]),
            "clicked": bool(grouped["clicked"]["count"]),
            "replied": bool(reply),
            "bounced": bool(grouped["bounced"]["count"]),
            "unsubscribed": bool(
                suppression and suppression.reason == ProspectSuppression.Reason.UNSUBSCRIBE
            ),
        }
        if engagement == "not_opened" and flags["opened"]:
            continue
        if engagement not in ("all", "not_opened") and not flags.get(engagement, False):
            continue
        result.append(
            {
                "id": recipient.pk,
                "name": recipient.contact_name,
                "company": recipient.company_name,
                "email": recipient.normalized_email,
                "campaign": {"id": recipient.campaign_id, "name": recipient.campaign.name},
                "step": latest_message.step_version.step_number if latest_message else None,
                "sent_at": sent_at.get(recipient.pk),
                "delivered_at": grouped["delivered"]["first"],
                "first_opened_at": grouped["opened"]["first"],
                "last_opened_at": grouped["opened"]["last"],
                "open_count": grouped["opened"]["count"],
                "first_clicked_at": grouped["clicked"]["first"],
                "click_count": grouped["clicked"]["count"],
                "replied_at": reply.received_at if reply else None,
                "state": recipient.state,
                "flags": flags,
            }
        )
    return result


def recipient_timeline(organization, recipient):
    messages = ProspectMessage.objects.filter(recipient=recipient).select_related("step_version")
    mappings = dict(
        ProspectProviderEmail.objects.filter(message__recipient=recipient).values_list(
            "provider_email_id", "message_id"
        )
    )
    timeline = []
    for message in messages:
        for attempt in message.attempts.filter(status=ProspectDeliveryAttempt.Status.SUCCEEDED):
            timeline.append(
                {
                    "at": attempt.completed_at or attempt.attempted_at,
                    "type": "sent",
                    "label": f"Step {message.step_version.step_number} submitted",
                }
            )
    events = ResendWebhookEvent.objects.filter(
        organization=organization, provider_email_id__in=mappings
    ).order_by("occurred_at", "id")
    labels = {
        "email.delivered": "Delivered",
        "email.opened": "Opened",
        "email.clicked": "Link clicked",
        "email.bounced": "Bounced",
        "email.complained": "Complaint reported",
    }
    for event in events:
        if event.event_type in labels:
            timeline.append(
                {
                    "at": event.occurred_at,
                    "type": event.event_type.removeprefix("email."),
                    "label": labels[event.event_type],
                }
            )
    for reply in recipient.replies.all():
        timeline.append({"at": reply.received_at, "type": "replied", "label": "Replied"})
    for suppression in ProspectSuppression.objects.filter(source_recipient=recipient):
        timeline.append(
            {
                "at": suppression.created_at,
                "type": suppression.reason,
                "label": suppression.get_reason_display(),
            }
        )
    return sorted(timeline, key=lambda item: item["at"])
