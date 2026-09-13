"""Controlled preparation only. No delivery/provider behavior belongs here."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max

from apps.contractors.models import Contact, ScopeContractorCandidate
from apps.organizations.models import Membership
from apps.organizations.services import active_membership
from apps.projects.audit import record_event
from apps.projects.models import Project
from apps.scope_packages.models import ScopePackage, ScopePackageVersion

from .models import (
    InvitationBatch,
    InvitationCampaign,
    InvitationRecipient,
    InvitationRecipientStatusEvent,
    OutreachMessage,
)


def _authorize(actor, organization):
    membership = active_membership(actor, organization)
    if membership is None or membership.role not in {
        Membership.Role.ADMIN,
        Membership.Role.ESTIMATOR_OPERATOR,
    }:
        raise PermissionDenied("An active organization operator is required.")


def _audit(actor, action, target, metadata=None):
    campaign = (
        target
        if isinstance(target, InvitationCampaign)
        else (
            target.campaign
            if isinstance(target, InvitationBatch)
            else target.batch.campaign
            if isinstance(target, InvitationRecipient)
            else target.recipient.batch.campaign
        )
    )
    record_event(
        organization=campaign.organization,
        project=campaign.project,
        actor=actor,
        action_code=action,
        target=target,
        metadata=metadata or {},
    )


@transaction.atomic
def create_invitation_campaign(*, project, scope_package, scope_version, actor):
    project = Project.objects.select_for_update().select_related("organization").get(pk=project.pk)
    _authorize(actor, project.organization)
    scope_package = ScopePackage.objects.select_for_update().get(pk=scope_package.pk)
    scope_version = ScopePackageVersion.objects.get(pk=scope_version.pk)
    campaign = InvitationCampaign.objects.create(
        organization=project.organization,
        project=project,
        scope_package=scope_package,
        scope_version=scope_version,
        trade_key=scope_package.trade_key,
        trade_category=scope_package.trade_category,
        created_by=actor,
    )
    _audit(actor, "outreach_campaign.created", campaign, {"scope_version_id": scope_version.pk})
    return campaign


@transaction.atomic
def create_invitation_batch(*, campaign, actor, sequence=None):
    _authorize(actor, campaign.organization)
    campaign = InvitationCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status == InvitationCampaign.Status.CLOSED:
        raise ValidationError("Closed campaigns cannot receive batches.")
    if sequence is None:
        sequence = (
            InvitationBatch.objects.filter(campaign=campaign).aggregate(n=Max("sequence"))["n"] or 0
        ) + 1
    batch, created = InvitationBatch.objects.get_or_create(
        campaign=campaign, sequence=sequence, defaults={"created_by": actor}
    )
    if created:
        _audit(actor, "outreach_batch.created", batch, {"sequence": sequence})
    return batch


@transaction.atomic
def add_invitation_recipient(*, batch, candidate, contact, actor):
    _authorize(actor, batch.campaign.organization)
    batch = InvitationBatch.objects.select_for_update().get(pk=batch.pk)
    candidate = (
        ScopeContractorCandidate.objects.select_for_update()
        .select_related("company")
        .get(pk=candidate.pk)
    )
    contact = Contact.objects.select_for_update().get(pk=contact.pk)
    existing = InvitationRecipient.objects.filter(batch=batch, candidate=candidate).first()
    if existing:
        if existing.contact_id != contact.pk:
            raise ValidationError("This candidate is already prepared with a different contact.")
        return existing
    if batch.status != InvitationBatch.Status.PREPARED:
        raise ValidationError("Batch is not open for preparation.")
    if candidate.status != ScopeContractorCandidate.Status.APPROVED:
        raise ValidationError("Candidate must be approved for outreach.")
    recipient = InvitationRecipient.objects.create(
        batch=batch,
        candidate=candidate,
        company=candidate.company,
        contact=contact,
        company_name=candidate.company.display_name,
        contact_name=contact.name,
        contact_title=contact.title,
        email=contact.email,
        phone=contact.phone,
        created_by=actor,
    )
    InvitationRecipientStatusEvent.objects.create(
        recipient=recipient,
        previous_status="",
        new_status=InvitationRecipient.Status.PREPARED,
        actor=actor,
        reason="Recipient prepared.",
    )
    _audit(actor, "outreach_recipient.created", recipient, {"candidate_id": candidate.pk})
    return recipient


@transaction.atomic
def transition_invitation_recipient_status(*, recipient, new_status, actor, reason=""):
    _authorize(actor, recipient.batch.campaign.organization)
    recipient = InvitationRecipient.objects.select_for_update().get(pk=recipient.pk)
    if recipient.current_status == new_status:
        return recipient
    if (recipient.current_status, new_status) != (
        InvitationRecipient.Status.PREPARED,
        InvitationRecipient.Status.CANCELLED,
    ):
        raise ValidationError("M3-01 permits only prepared-to-cancelled status changes.")
    previous = recipient.current_status
    InvitationRecipient.objects.filter(pk=recipient.pk).update(current_status=new_status)
    recipient.current_status = new_status
    InvitationRecipientStatusEvent.objects.create(
        recipient=recipient,
        previous_status=previous,
        new_status=new_status,
        actor=actor,
        reason=reason[:255],
    )
    _audit(
        actor, "outreach_recipient.status_changed", recipient, {"from": previous, "to": new_status}
    )
    return recipient


@transaction.atomic
def create_outreach_message(
    *,
    recipient,
    actor,
    from_name,
    from_address,
    subject,
    body,
    reply_to="",
    kind=OutreachMessage.Kind.INVITATION,
    sequence=None,
):
    _authorize(actor, recipient.batch.campaign.organization)
    recipient = InvitationRecipient.objects.select_for_update().get(pk=recipient.pk)
    if recipient.current_status != InvitationRecipient.Status.PREPARED:
        raise ValidationError("Only prepared recipients can have prepared messages.")
    if sequence is None:
        sequence = (
            OutreachMessage.objects.filter(recipient=recipient).aggregate(n=Max("sequence"))["n"]
            or 0
        ) + 1
    if OutreachMessage.objects.filter(recipient=recipient, sequence=sequence).exists():
        raise ValidationError("Message sequence already exists; create the next immutable version.")
    message = OutreachMessage.objects.create(
        recipient=recipient,
        sequence=sequence,
        kind=kind,
        from_name=from_name,
        from_address=from_address,
        reply_to=reply_to,
        to_address=recipient.email,
        subject=subject,
        body=body,
        created_by=actor,
    )
    _audit(actor, "outreach_message.created", message, {"sequence": sequence, "kind": kind})
    return message
