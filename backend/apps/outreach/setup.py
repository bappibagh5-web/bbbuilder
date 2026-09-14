"""Human-controlled campaign dates and organization sender identity."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.organizations.models import Membership
from apps.organizations.services import active_membership
from apps.projects.audit import record_event

from .models import CampaignSetupEvent, InvitationCampaign, OutreachSenderSettings
from .services import _audit, _authorize


def parse_project_local(value, project_timezone):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or "T" not in value:
        raise ValidationError("Enter a local date and time.")
    try:
        local = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValidationError("Enter a valid local date and time.") from error
    if timezone.is_aware(local):
        raise ValidationError("Enter a local date and time without a timezone offset.")
    zone = ZoneInfo(project_timezone)
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValidationError(
            "This local time is ambiguous or does not exist. Choose another time."
        )
    if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local:
        raise ValidationError("This local time does not exist. Choose another time.")
    return first


def format_project_local(value, project_timezone):
    if value is None:
        return ""
    return timezone.localtime(value, ZoneInfo(project_timezone)).strftime("%Y-%m-%dT%H:%M")


@transaction.atomic
def save_campaign_setup(*, campaign, actor, bid_local, questions_local):
    _authorize(actor, campaign.organization)
    campaign = (
        InvitationCampaign.objects.select_for_update()
        .select_related("project", "organization")
        .get(pk=campaign.pk)
    )
    if not campaign.project.is_active or campaign.status == InvitationCampaign.Status.CLOSED:
        raise ValidationError("This campaign is closed for setup changes.")
    zone = campaign.project.project_timezone
    bid = parse_project_local(bid_local, zone)
    questions = parse_project_local(questions_local, zone)
    now = timezone.now()
    if bid is not None and bid <= now:
        raise ValidationError("Bid deadline must be in the future.")
    if questions is not None and (bid is None or questions <= now or questions >= bid):
        raise ValidationError("Questions deadline must be in the future and before Bid Due.")
    if campaign.bid_deadline == bid and campaign.questions_deadline == questions:
        return campaign
    campaign.bid_deadline = bid
    campaign.questions_deadline = questions
    campaign.setup_version += 1
    campaign.save(update_fields=("bid_deadline", "questions_deadline", "setup_version"))
    CampaignSetupEvent.objects.create(
        campaign=campaign,
        version=campaign.setup_version,
        bid_deadline=bid,
        questions_deadline=questions,
        actor=actor,
    )
    _audit(
        actor,
        "outreach_campaign.setup_changed",
        campaign,
        {"setup_version": campaign.setup_version},
    )
    return campaign


@transaction.atomic
def save_sender_settings(
    *, organization, actor, display_name, from_address, reply_to, enabled=True
):
    membership = active_membership(actor, organization)
    if membership is None or membership.role != Membership.Role.ADMIN:
        raise PermissionDenied("Organization Admin access is required.")
    values = {
        "display_name": display_name.strip(),
        "from_address": from_address.strip(),
        "reply_to": reply_to.strip(),
        "is_enabled": enabled,
    }
    if not values["display_name"] or not values["from_address"] or not values["reply_to"]:
        raise ValidationError("Sender name, From email, and Reply-To email are required.")
    OutreachSenderSettings(organization=organization, updated_by=actor, **values).full_clean(
        validate_unique=False
    )
    sender, created = OutreachSenderSettings.objects.select_for_update().get_or_create(
        organization=organization, defaults={**values, "updated_by": actor}
    )
    changed = created or any(getattr(sender, key) != value for key, value in values.items())
    if not created and changed:
        for key, value in values.items():
            setattr(sender, key, value)
        sender.updated_by = actor
        sender.save()
    if changed:
        record_event(
            organization=organization,
            project=None,
            actor=actor,
            action_code="outreach_sender.updated",
            target=sender,
            metadata={"enabled": sender.is_enabled},
        )
    return sender
