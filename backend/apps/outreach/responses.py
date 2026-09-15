"""Append-only contractor responses and human qualification decisions."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    InvitationRecipient,
    InvitationRecipientStatusEvent,
    OutreachQualificationDecision,
    OutreachResponse,
)
from .services import _audit, _authorize

_PROGRESS = {
    "prepared": 0,
    "invited": 1,
    "failed": 1,
    "delivered": 2,
    "opened": 3,
    "needs_follow_up": 3,
    "responded": 4,
    "bid_submitted": 5,
    "declined": 5,
}


def advance_recipient(recipient, status, *, actor=None, source="provider", reason=""):
    """Keep one current display status without rewriting its append-only trail."""
    if status not in InvitationRecipient.Status.values:
        raise ValidationError("Invalid recipient status.")
    old = recipient.current_status
    if old in {"cancelled", "declined"} or (
        _PROGRESS.get(status, 0) <= _PROGRESS.get(old, 0)
        and not (old == "invited" and status == "failed")
    ):
        return False
    InvitationRecipient.objects.filter(pk=recipient.pk).update(current_status=status)
    InvitationRecipientStatusEvent.objects.create(
        recipient=recipient,
        previous_status=old,
        new_status=status,
        actor=actor,
        source=source,
        reason=reason[:255],
    )
    recipient.current_status = status
    return True


@transaction.atomic
def record_manual_response(*, recipient, actor, outcome, channel, note, occurred_at=None):
    recipient = (
        InvitationRecipient.objects.select_for_update()
        .select_related("batch__campaign__organization", "batch__campaign__project")
        .get(pk=recipient.pk)
    )
    campaign = recipient.batch.campaign
    _authorize(actor, campaign.organization)
    if recipient.current_status in {"prepared", "cancelled"}:
        raise ValidationError("Record a response only after an invitation was sent.")
    if outcome not in {"responded", "declined", "needs_follow_up"}:
        raise ValidationError("Choose a supported response outcome.")
    if channel not in {"phone", "email", "other"} or not note.strip():
        raise ValidationError("Choose a response channel and enter a short note.")
    occurred_at = occurred_at or timezone.now()
    if occurred_at > timezone.now() + timedelta(minutes=5):
        raise ValidationError("Response time cannot be in the future.")
    response = OutreachResponse.objects.create(
        organization=campaign.organization,
        project=campaign.project,
        recipient=recipient,
        channel=channel,
        outcome=outcome,
        note=note.strip()[:1000],
        occurred_at=occurred_at,
        actor=actor,
    )
    InvitationRecipient.objects.filter(pk=recipient.pk).update(response_state=outcome)
    advance_recipient(
        recipient, outcome, actor=actor, source="human", reason="Manual response recorded."
    )
    _audit(
        actor,
        "outreach_response.recorded",
        recipient,
        {"response_id": response.pk, "outcome": outcome},
    )
    return response


@transaction.atomic
def decide_qualification(*, recipient, actor, state, note=""):
    recipient = (
        InvitationRecipient.objects.select_for_update()
        .select_related("batch__campaign__organization")
        .get(pk=recipient.pk)
    )
    _authorize(actor, recipient.batch.campaign.organization)
    if recipient.current_status in {"prepared", "cancelled"}:
        raise ValidationError("Qualification requires a sent invitation.")
    if state not in {"needs_follow_up", "qualified", "not_qualified"}:
        raise ValidationError("Choose a supported qualification decision.")
    if state == "not_qualified" and not note.strip():
        raise ValidationError("Explain why this contractor is not qualified.")
    decision = OutreachQualificationDecision.objects.create(
        recipient=recipient, state=state, note=note.strip()[:1000], actor=actor
    )
    InvitationRecipient.objects.filter(pk=recipient.pk).update(qualification_state=state)
    _audit(
        actor,
        "outreach_qualification.decided",
        recipient,
        {"decision_id": decision.pk, "state": state},
    )
    return decision
