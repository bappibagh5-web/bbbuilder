"""Explicit, backend-gated invitation delivery over configured SMTP only."""

import hashlib
import json

from django.core.exceptions import ValidationError
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
    OutreachSenderSettings,
)
from .rfq import COMPANY_PLACEHOLDER, build_rfq_preview
from .services import _audit, _authorize, create_outreach_message
from .smtp import SMTPDeliveryProvider, provider_status, safe_smtp_failure


def _related_rows(instance, relation):
    cached = getattr(instance, "_prefetched_objects_cache", {}).get(relation)
    return list(cached) if cached is not None else list(getattr(instance, relation).all())


def _latest_message(recipient):
    messages = _related_rows(recipient, "messages")
    return max(messages, key=lambda message: message.sequence, default=None)


def _message_fingerprint(recipients):
    latest = [_latest_message(recipient) for recipient in recipients]
    if not recipients or any(message is None for message in latest):
        return None
    payload = [(message.recipient_id, message.pk, message.sequence) for message in latest]
    return hashlib.sha256(json.dumps(sorted(payload)).encode()).hexdigest()


def _expected_message(message, campaign, sender, preview):
    return (
        message.from_name == sender.display_name
        and message.from_address == sender.from_address
        and message.reply_to == sender.reply_to
        and message.to_address == message.recipient.email
        and message.subject
        == preview.subject.replace(COMPANY_PLACEHOLDER, message.recipient.company_name)
        and message.body
        == preview.body.replace(COMPANY_PLACEHOLDER, message.recipient.company_name)
        and message.template_version == preview.template_version
        and message.source_scope_version_id == campaign.scope_version_id
        and message.campaign_setup_version == campaign.setup_version
        and message.bid_deadline == campaign.bid_deadline
        and message.questions_deadline == campaign.questions_deadline
    )


def readiness(
    batch,
    *,
    require_approval=True,
    require_messages=True,
    require_provider=True,
    for_retry=False,
    sender=None,
    provider=None,
):
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
    batch_recipients = _related_rows(batch, "recipients")
    recipients = [
        recipient
        for recipient in batch_recipients
        if recipient.current_status == InvitationRecipient.Status.PREPARED
    ]
    if not recipients:
        if all_recipients := [
            recipient
            for recipient in batch_recipients
            if recipient.current_status != InvitationRecipient.Status.CANCELLED
        ]:
            if all(
                recipient.current_status != InvitationRecipient.Status.PREPARED
                for recipient in all_recipients
            ):
                if all(
                    any(
                        attempt.status == OutreachDeliveryAttempt.Status.SUCCEEDED
                        for message in _related_rows(recipient, "messages")
                        for attempt in _related_rows(message, "attempts")
                    )
                    for recipient in all_recipients
                ):
                    block(
                        "all_recipients_sent",
                        "Invitations sent successfully; no unsent recipients remain",
                    )
                else:
                    block("no_unsent_recipients", "No unsent recipients remain in this batch")
        else:
            block("recipient_required", "Add at least one prepared recipient")
    if any(not recipient.email for recipient in recipients):
        block("recipient_email_required", "A prepared recipient is missing an email address")
    if not campaign.bid_deadline:
        block("bid_deadline_required", "Bid deadline required")
    elif timezone.is_naive(campaign.bid_deadline) or campaign.bid_deadline <= timezone.now():
        block("bid_deadline_invalid", "Bid deadline must be a valid future date and time")
    if campaign.questions_deadline and (
        timezone.is_naive(campaign.questions_deadline)
        or campaign.questions_deadline <= timezone.now()
        or (campaign.bid_deadline and campaign.questions_deadline >= campaign.bid_deadline)
    ):
        block(
            "questions_deadline_invalid",
            "Questions deadline must be before the bid deadline and in the future",
        )
    if sender is None:
        sender = OutreachSenderSettings.objects.filter(
            organization_id=campaign.organization_id
        ).first()
    if sender is None or not sender.is_enabled:
        block("sender_required", "Sender configuration required")
    if provider is None:
        provider = provider_status(campaign.organization)
    if require_provider and provider["state"] != "configured":
        block("delivery_not_configured", "Email delivery is not configured")
    all_recipients = list(
        batch.recipients.exclude(current_status=InvitationRecipient.Status.CANCELLED)
    )
    fingerprint = _message_fingerprint(all_recipients)
    if require_messages and fingerprint is None:
        block("messages_required", "Prepare invitation messages first")
    messages_current = False
    if fingerprint and sender:
        preview = build_rfq_preview(campaign=campaign)
        messages_current = all(
            _expected_message(_latest_message(recipient), campaign, sender, preview)
            for recipient in all_recipients
        )
        if require_messages and not messages_current:
            block("messages_stale", "Messages changed; prepare new versions before sending")
    approval_valid = bool(
        fingerprint
        and messages_current
        and any(
            approval.message_fingerprint == fingerprint
            and approval.campaign_setup_version == campaign.setup_version
            for approval in _related_rows(batch, "send_approvals")
        )
    )
    if require_approval and not approval_valid:
        if _related_rows(batch, "send_approvals"):
            block(
                "send_approval_stale", "Messages changed after approval; review and approve again"
            )
        else:
            block("send_approval_required", "Explicit send approval required")
    if not for_retry and any(
        any(
            attempt.status == OutreachDeliveryAttempt.Status.FAILED
            for message in _related_rows(recipient, "messages")
            for attempt in _related_rows(message, "attempts")
        )
        for recipient in recipients
    ):
        block("retry_required", "A failed delivery requires an explicit retry")
    if any(
        any(
            attempt.status
            in (
                OutreachDeliveryAttempt.Status.PENDING,
                OutreachDeliveryAttempt.Status.UNCERTAIN,
            )
            for message in _related_rows(recipient, "messages")
            for attempt in _related_rows(message, "attempts")
        )
        for recipient in recipients
    ):
        block("delivery_unresolved", "A delivery outcome needs investigation before another send")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "send_approved": approval_valid,
        "provider": provider,
    }


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
    _require_ready(batch, require_approval=False)
    fingerprint = _message_fingerprint(
        list(batch.recipients.exclude(current_status=InvitationRecipient.Status.CANCELLED))
    )
    approval, created = BatchSendApproval.objects.get_or_create(
        batch=batch,
        message_fingerprint=fingerprint,
        defaults={"approved_by": actor, "campaign_setup_version": batch.campaign.setup_version},
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
    sender = OutreachSenderSettings.objects.get(organization_id=batch.campaign.organization_id)
    result = []
    for recipient in batch.recipients.filter(current_status=InvitationRecipient.Status.PREPARED):
        body = preview.body.replace(COMPANY_PLACEHOLDER, recipient.company_name)
        subject = preview.subject.replace(COMPANY_PLACEHOLDER, recipient.company_name)
        previous = recipient.messages.order_by("-sequence").first()
        content = (
            sender.display_name,
            sender.from_address,
            sender.reply_to,
            recipient.email,
            subject,
            body,
            preview.template_version,
            batch.campaign.scope_version_id,
            batch.campaign.setup_version,
            batch.campaign.bid_deadline,
            batch.campaign.questions_deadline,
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
                previous.template_version,
                previous.source_scope_version_id,
                previous.campaign_setup_version,
                previous.bid_deadline,
                previous.questions_deadline,
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
            and previous.attempts.filter(
                status__in=(
                    OutreachDeliveryAttempt.Status.PENDING,
                    OutreachDeliveryAttempt.Status.UNCERTAIN,
                )
            ).exists()
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
                template_version=preview.template_version,
                source_scope_version=batch.campaign.scope_version,
                campaign_setup_version=batch.campaign.setup_version,
                bid_deadline=batch.campaign.bid_deadline,
                questions_deadline=batch.campaign.questions_deadline,
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
            raise ValidationError("This invitation was already delivered.")
        _require_ready(batch, require_messages=True, for_retry=retry)
        if message.recipient.current_status != InvitationRecipient.Status.PREPARED:
            raise ValidationError("Only prepared recipients can be sent an invitation.")
        if message.recipient.messages.order_by("-sequence").first().pk != message.pk:
            raise ValidationError("Only the latest immutable message version can be sent.")
        if last:
            if last.status in (
                OutreachDeliveryAttempt.Status.PENDING,
                OutreachDeliveryAttempt.Status.UNCERTAIN,
            ):
                raise ValidationError("Delivery outcome needs investigation; do not resubmit.")
            if not retry:
                raise ValidationError("A failed delivery requires an explicit retry.")
        elif retry:
            raise ValidationError("There is no failed delivery to retry.")
        attempt = OutreachDeliveryAttempt.objects.create(
            message=message,
            sequence=(last.sequence + 1 if last else 1),
            provider_key=SMTPDeliveryProvider.key,
            idempotency_key=_message_key(message),
            submitted_rfc_message_id=(
                f"<{_message_key(message)}@{message.from_address.rsplit('@', 1)[-1]}>"
            ),
        )
        _audit(actor, "outreach_delivery.attempted", message, {"attempt_id": attempt.pk})
    try:
        reference = SMTPDeliveryProvider().deliver(
            message=message, idempotency_key=attempt.idempotency_key
        )
    except Exception as error:
        # Never persist/log a raw provider exception (it could contain addresses or secrets).
        code, safe_message, uncertain = safe_smtp_failure(error)
        with transaction.atomic():
            attempt = OutreachDeliveryAttempt.objects.select_for_update().get(pk=attempt.pk)
            attempt.status = (
                OutreachDeliveryAttempt.Status.UNCERTAIN
                if uncertain
                else OutreachDeliveryAttempt.Status.FAILED
            )
            attempt.completed_at = timezone.now()
            attempt.safe_error_code = code
            attempt.safe_error_message = safe_message
            attempt.save()
            _audit(
                actor,
                "outreach_delivery.failed",
                message,
                {
                    "attempt_id": attempt.pk,
                    "safe_error_code": code,
                },
            )
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
                current_status=InvitationRecipient.Status.INVITED,
                delivery_state="sent",
            )
            InvitationRecipientStatusEvent.objects.create(
                recipient=recipient,
                previous_status=InvitationRecipient.Status.PREPARED,
                new_status=InvitationRecipient.Status.INVITED,
                actor=actor,
                source="system",
                reason="Delivery succeeded.",
            )
        elif recipient.delivery_state == "not_sent":
            InvitationRecipient.objects.filter(pk=recipient.pk).update(delivery_state="sent")
        _audit(actor, "outreach_delivery.succeeded", message, {"attempt_id": attempt.pk})
    return attempt
