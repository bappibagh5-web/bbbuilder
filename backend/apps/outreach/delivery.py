"""Explicit, backend-gated invitation delivery. No real transport is configured here."""

import hashlib
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.scope_packages.models import ScopePackage, ScopePackageVersion

from .models import (
    BatchSendApproval,
    InvitationBatch,
    InvitationRecipient,
    InvitationRecipientStatusEvent,
    OutreachDeliveryAttempt,
    OutreachMessage,
)
from .rfq import COMPANY_PLACEHOLDER, build_rfq_preview
from .services import _audit, _authorize, create_outreach_message


class DisabledDeliveryProvider:
    key = "disabled"

    def deliver(self, *, message, idempotency_key):
        raise ValidationError("Outbound delivery is disabled.")


class FakeDeliveryProvider:
    key = "fake"

    def deliver(self, *, message, idempotency_key):
        return hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]


def _provider():
    key = settings.OUTREACH_DELIVERY_PROVIDER
    return FakeDeliveryProvider() if key == "fake" else DisabledDeliveryProvider()


def _message_fingerprint(recipients):
    latest = [recipient.messages.order_by("-sequence").first() for recipient in recipients]
    if not recipients or any(message is None for message in latest):
        return None
    payload = [(message.recipient_id, message.pk, message.sequence) for message in latest]
    return hashlib.sha256(json.dumps(sorted(payload)).encode()).hexdigest()


def readiness(batch, *, require_approval=True, require_messages=True, require_provider=True):
    """Stable public blocker codes; every send endpoint re-evaluates these."""
    campaign = batch.campaign
    project = campaign.project
    package = campaign.scope_package
    blockers = []

    def block(code, label):
        blockers.append({"code": code, "label": label})

    if not project.is_active or campaign.status == "closed" or batch.status != "prepared":
        block("campaign_inactive", "This campaign is not open for sending")
    if (
        package.lifecycle != ScopePackage.Lifecycle.ACTIVE
        or package.current_version_id != campaign.scope_version_id
        or campaign.scope_version.status != ScopePackageVersion.Status.READY
    ):
        block(
            "scope_version_not_current_ready", "The exact Ready scope version is no longer current"
        )
    recipients = list(batch.recipients.filter(current_status=InvitationRecipient.Status.PREPARED))
    if not recipients:
        block("recipient_required", "Add at least one prepared recipient")
    if any(not recipient.email for recipient in recipients):
        block("recipient_email_required", "A prepared recipient is missing an email address")
    if not project.bid_deadline:
        block("bid_deadline_required", "Bid deadline required")
    elif timezone.is_naive(project.bid_deadline) or project.bid_deadline <= timezone.now():
        block("bid_deadline_invalid", "Bid deadline must be a valid future date and time")
    if project.questions_deadline and (
        timezone.is_naive(project.questions_deadline)
        or project.questions_deadline <= timezone.now()
        or (project.bid_deadline and project.questions_deadline > project.bid_deadline)
    ):
        block(
            "questions_deadline_invalid",
            "Questions deadline must be before the bid deadline and in the future",
        )
    if not settings.OUTREACH_FROM_NAME or not settings.OUTREACH_FROM_ADDRESS:
        block("sender_required", "Sender name and email configuration required")
    else:
        try:
            validate_email(settings.OUTREACH_FROM_ADDRESS)
            if settings.OUTREACH_REPLY_TO:
                validate_email(settings.OUTREACH_REPLY_TO)
        except ValidationError:
            block("sender_invalid", "Sender email configuration is invalid")
    if require_provider and _provider().key == "disabled":
        block("delivery_disabled", "Outbound delivery is disabled")
    fingerprint = _message_fingerprint(
        list(batch.recipients.exclude(current_status=InvitationRecipient.Status.CANCELLED))
    )
    if require_messages and fingerprint is None:
        block("messages_required", "Prepare invitation messages first")
    approval_valid = bool(
        fingerprint
        and BatchSendApproval.objects.filter(batch=batch, message_fingerprint=fingerprint).exists()
    )
    if require_approval and not approval_valid:
        block("send_approval_required", "Explicit send approval required")
    return {"ready": not blockers, "blockers": blockers, "send_approved": approval_valid}


def _require_ready(batch, **kwargs):
    state = readiness(batch, **kwargs)
    if not state["ready"]:
        raise ValidationError([blocker["label"] for blocker in state["blockers"]])


@transaction.atomic
def approve_batch_send(*, batch, actor):
    _authorize(actor, batch.campaign.organization)
    batch = (
        InvitationBatch.objects.select_for_update()
        .select_related("campaign__project", "campaign__scope_package", "campaign__scope_version")
        .get(pk=batch.pk)
    )
    _require_ready(batch, require_approval=False, require_provider=False)
    fingerprint = _message_fingerprint(
        list(batch.recipients.exclude(current_status=InvitationRecipient.Status.CANCELLED))
    )
    approval, created = BatchSendApproval.objects.get_or_create(
        batch=batch, message_fingerprint=fingerprint, defaults={"approved_by": actor}
    )
    if created:
        _audit(actor, "outreach_batch.send_approved", batch, {"approval_id": approval.pk})
    return approval


@transaction.atomic
def prepare_batch_messages(*, batch, actor):
    _authorize(actor, batch.campaign.organization)
    batch = (
        InvitationBatch.objects.select_for_update()
        .select_related("campaign__project", "campaign__scope_package", "campaign__scope_version")
        .get(pk=batch.pk)
    )
    _require_ready(batch, require_approval=False, require_messages=False, require_provider=False)
    preview = build_rfq_preview(campaign=batch.campaign)
    result = []
    for recipient in batch.recipients.filter(current_status=InvitationRecipient.Status.PREPARED):
        body = preview.body.replace(COMPANY_PLACEHOLDER, recipient.company_name)
        subject = preview.subject.replace(COMPANY_PLACEHOLDER, recipient.company_name)
        previous = recipient.messages.order_by("-sequence").first()
        content = (
            settings.OUTREACH_FROM_NAME,
            settings.OUTREACH_FROM_ADDRESS,
            settings.OUTREACH_REPLY_TO,
            recipient.email,
            subject,
            body,
        )
        if (
            previous
            and (
                previous.from_name,
                previous.from_address,
                previous.reply_to,
                previous.to_address,
                previous.subject,
                previous.body,
            )
            == content
        ):
            result.append(previous)
            continue
        if (
            previous
            and previous.attempts.filter(status=OutreachDeliveryAttempt.Status.SUCCEEDED).exists()
        ):
            raise ValidationError("A delivered invitation cannot be silently replaced.")
        if (
            previous
            and previous.attempts.filter(status=OutreachDeliveryAttempt.Status.PENDING).exists()
        ):
            raise ValidationError("A pending delivery cannot be replaced.")
        result.append(
            create_outreach_message(
                recipient=recipient,
                actor=actor,
                from_name=content[0],
                from_address=content[1],
                reply_to=content[2],
                subject=subject,
                body=body,
                sequence=(previous.sequence + 1 if previous else 1),
                kind=(
                    OutreachMessage.Kind.REVISION if previous else OutreachMessage.Kind.INVITATION
                ),
            )
        )
    return result


def _message_key(message):
    return hashlib.sha256(f"outreach-message:{message.pk}".encode()).hexdigest()


def deliver_message(*, message, actor, retry=False):
    """Reserve a durable pending attempt before invoking any provider."""
    _authorize(actor, message.recipient.batch.campaign.organization)
    with transaction.atomic():
        message = (
            OutreachMessage.objects.select_for_update()
            .select_related(
                "recipient__batch__campaign__project",
                "recipient__batch__campaign__scope_package",
                "recipient__batch__campaign__scope_version",
            )
            .get(pk=message.pk)
        )
        batch = message.recipient.batch
        last = message.attempts.order_by("-sequence").first()
        if last and last.status == OutreachDeliveryAttempt.Status.SUCCEEDED:
            return last
        _require_ready(batch, require_messages=True)
        if message.recipient.current_status != InvitationRecipient.Status.PREPARED:
            raise ValidationError("Only prepared recipients can be sent an invitation.")
        if message.recipient.messages.order_by("-sequence").first().pk != message.pk:
            raise ValidationError("Only the latest immutable message version can be sent.")
        if last:
            if last.status == OutreachDeliveryAttempt.Status.PENDING:
                raise ValidationError("Delivery is already in progress; do not resubmit.")
            if not retry:
                raise ValidationError("A failed delivery requires an explicit retry.")
        elif retry:
            raise ValidationError("There is no failed delivery to retry.")
        attempt = OutreachDeliveryAttempt.objects.create(
            message=message,
            sequence=(last.sequence + 1 if last else 1),
            provider_key=_provider().key,
            idempotency_key=_message_key(message),
        )
        _audit(actor, "outreach_delivery.attempted", message, {"attempt_id": attempt.pk})
    try:
        reference = _provider().deliver(message=message, idempotency_key=attempt.idempotency_key)
    except Exception:
        # Never persist/log a raw provider exception (it could contain addresses or secrets).
        with transaction.atomic():
            attempt = OutreachDeliveryAttempt.objects.select_for_update().get(pk=attempt.pk)
            attempt.status = OutreachDeliveryAttempt.Status.FAILED
            attempt.completed_at = timezone.now()
            attempt.safe_error_code = "delivery_failed"
            attempt.safe_error_message = "Delivery failed. You may retry explicitly."
            attempt.save()
            _audit(actor, "outreach_delivery.failed", message, {"attempt_id": attempt.pk})
        return attempt
    with transaction.atomic():
        attempt = OutreachDeliveryAttempt.objects.select_for_update().get(pk=attempt.pk)
        attempt.status = OutreachDeliveryAttempt.Status.SUCCEEDED
        attempt.completed_at = timezone.now()
        attempt.provider_reference = str(reference)[:120]
        attempt.save()
        recipient = InvitationRecipient.objects.select_for_update().get(pk=message.recipient_id)
        if recipient.current_status == InvitationRecipient.Status.PREPARED:
            InvitationRecipient.objects.filter(pk=recipient.pk).update(
                current_status=InvitationRecipient.Status.INVITED
            )
            InvitationRecipientStatusEvent.objects.create(
                recipient=recipient,
                previous_status=InvitationRecipient.Status.PREPARED,
                new_status=InvitationRecipient.Status.INVITED,
                actor=actor,
                reason="Delivery succeeded.",
            )
        _audit(actor, "outreach_delivery.succeeded", message, {"attempt_id": attempt.pk})
    return attempt
