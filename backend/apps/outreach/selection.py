"""Read-only current Ready trades and explicit recipient choices."""

from django.conf import settings
from django.db.models import F

from apps.contractors.models import ScopeContractorCandidate
from apps.scope_packages.models import ScopePackage, ScopePackageVersion

from .delivery import readiness
from .models import (
    InvitationCampaign,
    OutreachProviderEmail,
    OutreachSenderSettings,
    ResendWebhookEvent,
)
from .setup import format_project_local
from .smtp import provider_status


def _recipient_activity(recipient):
    provider_ids = list(
        OutreachProviderEmail.objects.filter(message__recipient=recipient).values_list(
            "provider_email_id", flat=True
        )
    )
    provider_events = ResendWebhookEvent.objects.filter(
        organization=recipient.batch.campaign.organization,
        provider_email_id__in=provider_ids,
    )
    activity = [
        {
            "kind": "status",
            "label": f"Status: {row.new_status.replace('_', ' ')}",
            "at": row.occurred_at,
        }
        for row in recipient.status_events.all()
    ]
    activity += [
        {
            "kind": "response",
            "label": f"{row.channel.replace('_', ' ').title()}: {row.outcome.replace('_', ' ')}",
            "at": row.occurred_at,
            "note": row.note or (row.body_text[:500] if row.content_status == "retrieved" else ""),
        }
        for row in recipient.outreachresponse_set.all()
    ]
    activity += [
        {
            "kind": "qualification",
            "label": f"Qualification: {row.state.replace('_', ' ')}",
            "at": row.occurred_at,
            "note": row.note,
        }
        for row in recipient.qualification_decisions.all()
    ]
    activity += [
        {
            "kind": "provider",
            "label": f"Provider reported {row.event_type.removeprefix('email.').replace('_', ' ')}",
            "at": row.occurred_at,
        }
        for row in provider_events
    ]
    return sorted(activity, key=lambda item: item["at"])


def outreach_workspace(project):
    packages = list(
        ScopePackage.objects.filter(
            project=project,
            lifecycle=ScopePackage.Lifecycle.ACTIVE,
            current_version__status=ScopePackageVersion.Status.READY,
        ).select_related("current_version")
    )
    candidate_queryset = ScopeContractorCandidate.objects.filter(
        project=project,
        status=ScopeContractorCandidate.Status.APPROVED,
        scope_package__lifecycle=ScopePackage.Lifecycle.ACTIVE,
        scope_version=F("scope_package__current_version"),
    )
    if settings.CONTRACTOR_DISCOVERY_PROVIDER == "google_places":
        candidate_queryset = candidate_queryset.exclude(company__external_provider="fake")
    candidates = list(
        candidate_queryset.select_related("company").prefetch_related("company__contacts")
    )
    campaigns = list(
        InvitationCampaign.objects.filter(project=project)
        .select_related("scope_version")
        .prefetch_related(
            "batches__recipients__messages__attempts",
            "batches__recipients__status_events",
            "batches__recipients__qualification_decisions",
            "batches__recipients__outreachresponse_set",
            "batches__recipients__bidsubmission_set",
            "batches__recipients__resendwebhookevent_set",
        )
    )
    sender = OutreachSenderSettings.objects.filter(organization=project.organization).first()
    return {
        "sender": {
            "configured": bool(sender and sender.is_enabled),
            "display_name": sender.display_name if sender else "",
            "from_address": sender.from_address if sender else "",
            "reply_to": sender.reply_to if sender else "",
        },
        "provider": provider_status(project.organization),
        "trades": [
            {
                "scope_package_id": package.pk,
                "scope_version_id": package.current_version_id,
                "scope_version": package.current_version.version,
                "trade": package.trade_category,
                "approved_count": sum(
                    candidate.scope_package_id == package.pk
                    and candidate.scope_version_id == package.current_version_id
                    for candidate in candidates
                ),
                "approved_candidates": [
                    {
                        "id": candidate.pk,
                        "company_name": candidate.company.display_name,
                        "contacts": [
                            {
                                "id": contact.pk,
                                "name": contact.name,
                                "title": contact.title,
                                "email": contact.email,
                                "is_primary": contact.is_primary,
                            }
                            for contact in candidate.company.contacts.all()
                            if contact.is_active and contact.email
                        ],
                    }
                    for candidate in candidates
                    if candidate.scope_package_id == package.pk
                    and candidate.scope_version_id == package.current_version_id
                ],
                "campaign": next(
                    (
                        {
                            "id": campaign.pk,
                            "status": campaign.status,
                            "bid_due_local": format_project_local(
                                campaign.bid_deadline, project.project_timezone
                            ),
                            "questions_due_local": format_project_local(
                                campaign.questions_deadline, project.project_timezone
                            ),
                            "project_timezone": project.project_timezone,
                            "setup_version": campaign.setup_version,
                            "batches": [
                                {
                                    "id": batch.pk,
                                    "sequence": batch.sequence,
                                    "status": batch.status,
                                    "delivery_readiness": readiness(batch),
                                    "send_approved": readiness(batch)["send_approved"],
                                    "recipients": [
                                        {
                                            "id": recipient.pk,
                                            "candidate_id": recipient.candidate_id,
                                            "company_name": recipient.company_name,
                                            "contact_name": recipient.contact_name,
                                            "email": recipient.email,
                                            "status": recipient.current_status,
                                            "delivery_state": recipient.delivery_state,
                                            "engagement_state": recipient.engagement_state,
                                            "response_state": recipient.response_state,
                                            "qualification_state": recipient.qualification_state,
                                            "activity": _recipient_activity(recipient),
                                            "attachment_notice": any(
                                                response.attachment_count > 0
                                                for response in recipient.outreachresponse_set.all()
                                            ),
                                            "inbound_attachment_responses": [
                                                {
                                                    "id": response.pk,
                                                    "attachment_count": response.attachment_count,
                                                }
                                                for response in recipient.outreachresponse_set.all()
                                                if response.channel == "inbound_email"
                                                and response.attachment_count > 0
                                            ],
                                            "quote_submissions": [
                                                submission.pk
                                                for submission in recipient.bidsubmission_set.all()
                                            ],
                                            "imported_response_ids": [
                                                submission.source_response_id
                                                for submission in recipient.bidsubmission_set.all()
                                                if submission.source_response_id
                                            ],
                                            "messages": [
                                                {
                                                    "id": message.pk,
                                                    "sequence": message.sequence,
                                                    "from_name": message.from_name,
                                                    "from_address": message.from_address,
                                                    "reply_to": message.reply_to,
                                                    "to_address": message.to_address,
                                                    "subject": message.subject,
                                                    "body": message.body,
                                                    "template_version": message.template_version,
                                                    "scope_version_id": (
                                                        message.source_scope_version_id
                                                    ),
                                                    "attempts": [
                                                        {
                                                            "id": attempt.pk,
                                                            "sequence": attempt.sequence,
                                                            "status": attempt.status,
                                                            "safe_error_message": (
                                                                attempt.safe_error_message
                                                            ),
                                                        }
                                                        for attempt in message.attempts.all()
                                                    ],
                                                }
                                                for message in recipient.messages.all()
                                            ],
                                        }
                                        for recipient in batch.recipients.all()
                                    ],
                                }
                                for batch in campaign.batches.all()
                            ],
                        }
                        for campaign in campaigns
                        if campaign.scope_package_id == package.pk
                        and campaign.scope_version_id == package.current_version_id
                    ),
                    None,
                ),
            }
            for package in packages
        ],
    }
