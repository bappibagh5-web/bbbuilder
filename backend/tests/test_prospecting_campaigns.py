# ruff: noqa: E501
import smtplib
from datetime import timedelta
from urllib.parse import urlparse

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.contractors.models import Company, Contact
from apps.organizations.models import Membership, Organization
from apps.outreach.models import (
    OutreachSenderSettings,
    OutreachSMTPConfiguration,
    ResendWebhookConfiguration,
    ResendWebhookEvent,
)
from apps.prospecting.analytics import metric_bundle
from apps.prospecting.campaigns import (
    approve_campaign,
    campaign_metrics,
    create_campaign,
    deliver_recipient,
    enroll_entries,
    launch_campaign,
    process_due_prospecting_messages,
    remove_suppression,
    save_step,
    suppress_email,
    unsubscribe,
)
from apps.prospecting.models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectDeliveryAttempt,
    ProspectingSettings,
    ProspectList,
    ProspectListEntry,
    ProspectMessage,
    ProspectProviderEmail,
    ProspectReply,
    ProspectSuppression,
)
from apps.prospecting.webhooks import _exact_sent_message, reconcile_event

pytestmark = pytest.mark.django_db


def setup_email(organization, user):
    ProspectingSettings.objects.create(
        organization=organization,
        is_enabled=True,
        max_sends_per_hour=20,
        max_sends_per_day=100,
        sending_timezone="UTC",
        allowed_start_hour=0,
        allowed_end_hour=24,
        business_identity="BB Builders Ltd.",
        compliance_footer="Contact BB Builders for information about this message.",
        updated_by=user,
    )
    OutreachSenderSettings.objects.create(
        organization=organization,
        display_name="BB Builders",
        from_address="prospecting@example.com",
        reply_to="replies@example.com",
        updated_by=user,
    )
    OutreachSMTPConfiguration.objects.create(
        organization=organization,
        host="smtp.example.com",
        port=587,
        username="user",
        encrypted_password="test-only",
        security="starttls",
        is_enabled=True,
        updated_by=user,
    )


def make_entry(organization, user, *, email="contact@example.com", name="Acme Mechanical"):
    company = Company.objects.create(
        organization=organization,
        display_name=name,
        city="Toronto",
        province="ON",
        created_by=user,
        updated_by=user,
    )
    contact = Contact.objects.create(
        company=company, name="Taylor Smith", email=email, is_active=True
    )
    prospect_list = ProspectList.objects.create(
        organization=organization, name=f"{name} list", created_by=user
    )
    entry = ProspectListEntry.objects.create(
        prospect_list=prospect_list,
        company=company,
        primary_contact=contact,
        status=ProspectListEntry.Status.CONTACT_READY,
        added_by=user,
    )
    return entry


def make_campaign(monkeypatch, settings, organization, user, entry):
    settings.FRONTEND_ORIGIN = "https://app.example.com"
    setup_email(organization, user)
    campaign = create_campaign(
        organization=organization,
        actor=user,
        name="Introduction",
        list_ids=[entry.prospect_list_id],
    )
    save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 1,
            "subject": "Hello {{first_name}}",
            "body": "Hello {{contact_name}} at {{company_name}}",
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 2,
            "subject": "Following up",
            "body": "Hello again",
            "delay_minutes": 60,
            "enabled": True,
        },
    )
    counts, recipients = enroll_entries(
        campaign=campaign,
        entries=ProspectListEntry.objects.filter(pk=entry.pk),
        actor=user,
    )
    assert counts["eligible"] == 1
    monkeypatch.setattr(
        "apps.prospecting.campaigns.provider_status",
        lambda organization: {"state": "configured"},
    )
    membership = Membership.objects.get(organization=organization, user=user)
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=("role",))
    approve_campaign(campaign=campaign, actor=user)
    launch_campaign(campaign=campaign, actor=user)
    recipients[0].refresh_from_db()
    return campaign, recipients[0]


def make_batch_campaign(monkeypatch, settings, organization, user, membership, *, count=5):
    settings.FRONTEND_ORIGIN = "https://app.example.com"
    setup_email(organization, user)
    entries = [
        make_entry(
            organization,
            user,
            email=f"recipient-{index}@example.com",
            name=f"Company {index}",
        )
        for index in range(1, count + 1)
    ]
    campaign = create_campaign(organization=organization, actor=user, name="Batch delivery")
    save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 1,
            "subject": "Hello {{company_name}}",
            "body": "Hello {{contact_name}}",
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 2,
            "subject": "Following up",
            "body": "Hello again",
            "delay_minutes": 2,
            "enabled": True,
        },
    )
    _, recipients = enroll_entries(
        campaign=campaign,
        entries=ProspectListEntry.objects.filter(pk__in=[entry.pk for entry in entries]),
        actor=user,
    )
    monkeypatch.setattr(
        "apps.prospecting.campaigns.provider_status",
        lambda organization: {"state": "configured"},
    )
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=("role",))
    approve_campaign(campaign=campaign, actor=user)
    launch_campaign(campaign=campaign, actor=user)
    return campaign, list(
        ProspectCampaignRecipient.objects.filter(campaign=campaign).order_by("id")
    )


def test_estimator_drafts_admin_approves_and_viewer_cannot_mutate(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    setup_email(organization, user)
    campaign = create_campaign(
        organization=organization, actor=user, name="Draft", list_ids=[entry.prospect_list_id]
    )
    save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 1,
            "subject": "Hello",
            "body": "Body",
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    enroll_entries(
        campaign=campaign, entries=ProspectListEntry.objects.filter(pk=entry.pk), actor=user
    )
    monkeypatch.setattr(
        "apps.prospecting.campaigns.provider_status", lambda org: {"state": "configured"}
    )
    with pytest.raises(ValidationError):
        approve_campaign(campaign=campaign, actor=user)
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=("role",))
    version = approve_campaign(campaign=campaign, actor=user)
    assert version.steps.count() == 1
    with pytest.raises(ValidationError, match="Draft"):
        save_step(
            campaign=campaign,
            actor=user,
            values={
                "step_number": 1,
                "subject": "Changed",
                "body": "Changed",
                "delay_minutes": 0,
                "enabled": True,
            },
            step=campaign.sequence_steps.get(),
        )
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    with pytest.raises(ValidationError):
        create_campaign(organization=organization, actor=user, name="Denied")


def test_enrollment_requires_contact_ready_same_org_and_deduplicates_email(
    user, organization, membership
):
    campaign = create_campaign(organization=organization, actor=user, name="Campaign")
    entry = make_entry(organization, user)
    other_company = Company.objects.create(
        organization=organization, display_name="Second", created_by=user, updated_by=user
    )
    same_email = Contact.objects.create(
        company=other_company, name="Same Person", email=entry.primary_contact.email
    )
    second_list = ProspectList.objects.create(
        organization=organization, name="Second list", created_by=user
    )
    duplicate_entry = ProspectListEntry.objects.create(
        prospect_list=second_list,
        company=other_company,
        primary_contact=same_email,
        status=ProspectListEntry.Status.CONTACT_READY,
        added_by=user,
    )
    counts, recipients = enroll_entries(
        campaign=campaign,
        entries=ProspectListEntry.objects.filter(pk__in=[entry.pk, duplicate_entry.pk]),
        actor=user,
    )
    assert counts == {
        "selected": 2,
        "contact_ready": 2,
        "duplicates": 1,
        "suppressed": 0,
        "invalid": 0,
        "eligible": 1,
    }
    assert len(recipients) == 1
    other = Organization.objects.create(name="Other", slug="other-prospecting")
    other_list = ProspectList.objects.create(organization=other, name="Other", created_by=user)
    other_company = Company.objects.create(
        organization=other, display_name="Other company", created_by=user, updated_by=user
    )
    other_contact = Contact.objects.create(
        company=other_company, name="Other", email="other@example.com"
    )
    other_entry = ProspectListEntry.objects.create(
        prospect_list=other_list,
        company=other_company,
        primary_contact=other_contact,
        status=ProspectListEntry.Status.CONTACT_READY,
        added_by=user,
    )
    with pytest.raises(ValidationError, match="organization"):
        enroll_entries(
            campaign=campaign,
            entries=ProspectListEntry.objects.filter(pk=other_entry.pk),
            actor=user,
        )


def test_delivery_is_idempotent_reserves_before_send_and_schedules_next(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    campaign, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    seen = []

    def fake_send(*args, **kwargs):
        seen.append(ProspectDeliveryAttempt.objects.get().status)
        assert kwargs["additional_headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    attempt = deliver_recipient(recipient, send_function=fake_send)
    assert seen == [ProspectDeliveryAttempt.Status.PENDING]
    assert attempt.status == ProspectDeliveryAttempt.Status.SUCCEEDED
    recipient.refresh_from_db()
    assert recipient.current_step == 1
    assert recipient.state == ProspectCampaignRecipient.State.ACTIVE
    assert recipient.next_due_at > recipient.last_sent_at
    with pytest.raises(ValidationError):
        deliver_recipient(recipient, send_function=fake_send)
    assert ProspectMessage.objects.count() == 1
    assert ProspectDeliveryAttempt.objects.count() == 1
    campaign.refresh_from_db()
    assert campaign.status == ProspectCampaign.Status.ACTIVE


def test_suppression_blocks_all_campaigns_is_org_scoped_and_unsuppress_never_resumes(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    campaign, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    suppression, _ = suppress_email(
        organization=organization,
        email=recipient.normalized_email,
        reason=ProspectSuppression.Reason.MANUAL,
        actor=user,
    )
    recipient.refresh_from_db()
    assert recipient.state == ProspectCampaignRecipient.State.SUPPRESSED
    with pytest.raises(ValidationError, match="suppressed"):
        deliver_recipient(recipient, send_function=lambda *args, **kwargs: None)
    other = Organization.objects.create(name="Other", slug="suppression-other")
    assert not ProspectSuppression.objects.filter(organization=other).exists()
    remove_suppression(suppression=suppression, actor=user)
    recipient.refresh_from_db()
    assert recipient.state == ProspectCampaignRecipient.State.SUPPRESSED
    assert recipient.next_due_at is None
    assert campaign.recipients.count() == 1


def test_unsubscribe_digest_and_idempotent_public_action(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    _, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    from apps.prospecting.campaigns import prepare_message

    prepared = prepare_message(recipient)
    raw = urlparse(prepared.unsubscribe_url).path.rsplit("/", 1)[-1]
    token = recipient.unsubscribe_tokens.get()
    assert raw not in token.token_digest
    suppression, created = unsubscribe(raw)
    assert created and suppression.reason == ProspectSuppression.Reason.UNSUBSCRIBE
    _, created_again = unsubscribe(raw)
    assert created_again is False
    recipient.refresh_from_db()
    assert recipient.state == ProspectCampaignRecipient.State.UNSUBSCRIBED


def test_due_scheduler_skips_paused_suppressed_and_replied(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    campaign, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    campaign.status = ProspectCampaign.Status.PAUSED
    campaign.save(update_fields=("status",))
    assert process_due_prospecting_messages(send_function=lambda *args, **kwargs: None) == []
    campaign.status = ProspectCampaign.Status.ACTIVE
    campaign.save(update_fields=("status",))
    recipient.state = ProspectCampaignRecipient.State.REPLIED
    recipient.save(update_fields=("state",))
    assert process_due_prospecting_messages(send_function=lambda *args, **kwargs: None) == []


def test_due_batch_sends_five_and_schedules_each_follow_up_independently(
    monkeypatch, settings, user, organization, membership
):
    campaign, recipients = make_batch_campaign(
        monkeypatch, settings, organization, user, membership
    )
    sent = []
    summary = process_due_prospecting_messages(
        organization=organization,
        send_function=lambda *args, **kwargs: sent.append(kwargs["to_address"]),
        return_summary=True,
    )
    assert summary == {"processed": 5, "sent": 5, "scheduled": 5, "skipped": 0, "failed": 0}
    assert len(sent) == 5
    assert ProspectDeliveryAttempt.objects.filter(status="succeeded").count() == 5
    for recipient in recipients:
        recipient.refresh_from_db()
        assert recipient.current_step == 1
        assert recipient.state == ProspectCampaignRecipient.State.ACTIVE
        assert recipient.next_due_at > recipient.last_sent_at
    assert campaign.recipients.values_list("next_due_at", flat=True).distinct().count() == 5


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (smtplib.SMTPRecipientsRefused({"recipient-3@example.com": (550, b"rejected")}), "failed"),
        (smtplib.SMTPServerDisconnected("connection lost"), "uncertain"),
    ],
)
def test_due_batch_isolates_middle_provider_failure_and_protects_successful_retries(
    monkeypatch, settings, user, organization, membership, failure, expected_status
):
    _, recipients = make_batch_campaign(monkeypatch, settings, organization, user, membership)

    def fake_send(*args, **kwargs):
        if kwargs["to_address"] == "recipient-3@example.com":
            raise failure

    summary = process_due_prospecting_messages(
        organization=organization, send_function=fake_send, return_summary=True
    )
    assert summary == {"processed": 5, "sent": 4, "scheduled": 4, "skipped": 0, "failed": 1}
    attempts = list(ProspectDeliveryAttempt.objects.order_by("message__recipient_id"))
    assert [attempt.status for attempt in attempts] == [
        "succeeded",
        "succeeded",
        expected_status,
        "succeeded",
        "succeeded",
    ]
    assert attempts[2].safe_error_message
    assert attempts[2].safe_error_message != str(failure)
    successful_ids = [attempt.pk for attempt in attempts if attempt.status == "succeeded"]
    retried = []
    retry = process_due_prospecting_messages(
        organization=organization,
        send_function=lambda *args, **kwargs: retried.append(kwargs["to_address"]),
        return_summary=True,
    )
    if expected_status == "failed":
        assert retry == {
            "processed": 1,
            "sent": 1,
            "scheduled": 1,
            "skipped": 0,
            "failed": 0,
        }
        assert retried == ["recipient-3@example.com"]
    else:
        assert retry == {
            "processed": 1,
            "sent": 0,
            "scheduled": 0,
            "skipped": 1,
            "failed": 0,
        }
        assert retried == []
    assert (
        list(
            ProspectDeliveryAttempt.objects.filter(pk__in=successful_ids).values_list(
                "pk", flat=True
            )
        )
        == successful_ids
    )
    for recipient in recipients[:2] + recipients[3:]:
        recipient.refresh_from_db()
        assert recipient.current_step == 1


def test_due_batch_enforces_rate_limit_at_success_boundary(
    monkeypatch, settings, user, organization, membership
):
    _, _ = make_batch_campaign(monkeypatch, settings, organization, user, membership, count=2)
    config = ProspectingSettings.objects.get(organization=organization)
    config.max_sends_per_hour = 1
    config.save(update_fields=("max_sends_per_hour",))
    summary = process_due_prospecting_messages(
        organization=organization,
        send_function=lambda *args, **kwargs: None,
        return_summary=True,
    )
    assert summary == {"processed": 2, "sent": 1, "scheduled": 1, "skipped": 1, "failed": 0}
    assert ProspectDeliveryAttempt.objects.filter(status="succeeded").count() == 1


def test_process_due_api_returns_bounded_aggregate_instead_of_provider_details(
    monkeypatch, user, organization, membership
):
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=("role",))
    expected = {"processed": 5, "sent": 4, "scheduled": 4, "skipped": 0, "failed": 1}
    monkeypatch.setattr(
        "apps.prospecting.views.process_due_prospecting_messages",
        lambda **kwargs: expected,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        f"/api/v1/organizations/{organization.slug}/prospecting/process-due/",
        {},
        format="json",
    )
    assert response.status_code == 200
    assert response.data == expected


def test_two_recipients_send_threaded_follow_up_and_complete_independently(
    monkeypatch, settings, user, organization, membership
):
    campaign, recipients = make_batch_campaign(
        monkeypatch, settings, organization, user, membership, count=2
    )
    first_headers = {}

    def first_send(*args, **kwargs):
        first_headers[kwargs["to_address"]] = kwargs

    first = process_due_prospecting_messages(
        organization=organization, send_function=first_send, return_summary=True
    )
    assert first == {"processed": 2, "sent": 2, "scheduled": 2, "skipped": 0, "failed": 0}
    assert all("<html><body>" in sent["html_body"] for sent in first_headers.values())
    assert all(">Unsubscribe</a>" in sent["html_body"] for sent in first_headers.values())
    realistic_message_id = (
        "<852469f750de4959d9f5fdf73aae7120f34cd2b722151466d11db78780614bbd@mybusinesslocal.com>"
    )
    first_message = recipients[0].messages.get(step_version__step_number=1)
    ProspectMessage.objects.filter(pk=first_message.pk).update(rfc_message_id=realistic_message_id)
    campaign.recipients.update(next_due_at=timezone.now() - timedelta(seconds=1))
    follow_ups = {}

    def follow_up_send(*args, **kwargs):
        follow_ups[kwargs["to_address"]] = kwargs

    second = process_due_prospecting_messages(
        organization=organization, send_function=follow_up_send, return_summary=True
    )
    assert second == {
        "processed": 2,
        "sent": 2,
        "scheduled": 0,
        "skipped": 0,
        "failed": 0,
    }
    for recipient in recipients:
        recipient.refresh_from_db()
        assert recipient.current_step == 2
        assert recipient.state == ProspectCampaignRecipient.State.COMPLETED
        assert recipient.next_due_at is None
        messages = list(recipient.messages.order_by("step_version__step_number"))
        assert len(messages) == 2
        headers = follow_ups[recipient.normalized_email]["additional_headers"]
        expected_message_id = (
            realistic_message_id if recipient.pk == recipients[0].pk else messages[0].rfc_message_id
        )
        assert headers["In-Reply-To"] == expected_message_id
        assert headers["References"] == expected_message_id
        assert "<html><body>" in follow_ups[recipient.normalized_email]["html_body"]
        assert ">Unsubscribe</a>" in follow_ups[recipient.normalized_email]["html_body"]
    assert ProspectDeliveryAttempt.objects.filter(status="succeeded").count() == 4
    assert process_due_prospecting_messages(
        organization=organization,
        send_function=lambda *args, **kwargs: pytest.fail("completed follow-up was retried"),
        return_summary=True,
    ) == {"processed": 0, "sent": 0, "scheduled": 0, "skipped": 0, "failed": 0}


def test_follow_up_missing_previous_message_id_is_safe_and_failure_is_isolated(
    monkeypatch, settings, user, organization, membership
):
    campaign, recipients = make_batch_campaign(
        monkeypatch, settings, organization, user, membership, count=2
    )
    process_due_prospecting_messages(
        organization=organization,
        send_function=lambda *args, **kwargs: None,
        return_summary=True,
    )
    first_message = recipients[0].messages.get(step_version__step_number=1)
    ProspectMessage.objects.filter(pk=first_message.pk).update(rfc_message_id="")
    campaign.recipients.update(next_due_at=timezone.now() - timedelta(seconds=1))
    follow_up_calls = []

    def follow_up_send(*args, **kwargs):
        follow_up_calls.append(kwargs)
        if kwargs["to_address"] == recipients[1].normalized_email:
            raise smtplib.SMTPRecipientsRefused(
                {recipients[1].normalized_email: (550, b"rejected")}
            )

    summary = process_due_prospecting_messages(
        organization=organization, send_function=follow_up_send, return_summary=True
    )
    assert summary == {"processed": 2, "sent": 1, "scheduled": 0, "skipped": 0, "failed": 1}
    safe_headers = follow_up_calls[0]["additional_headers"]
    assert "In-Reply-To" not in safe_headers
    assert "References" not in safe_headers
    recipients[0].refresh_from_db()
    recipients[1].refresh_from_db()
    assert recipients[0].state == ProspectCampaignRecipient.State.COMPLETED
    assert recipients[1].state == ProspectCampaignRecipient.State.ACTIVE
    assert recipients[1].current_step == 1
    retried = []
    retry = process_due_prospecting_messages(
        organization=organization,
        send_function=lambda *args, **kwargs: retried.append(kwargs["to_address"]),
        return_summary=True,
    )
    assert retry == {"processed": 1, "sent": 1, "scheduled": 0, "skipped": 0, "failed": 0}
    assert retried == [recipients[1].normalized_email]
    assert recipients[0].messages.filter(step_version__step_number=2).count() == 1


def test_hard_bounce_creates_suppression_and_provider_events_are_analytics_only(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    campaign, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    attempt = deliver_recipient(recipient, send_function=lambda *args, **kwargs: None)
    config = ResendWebhookConfiguration.objects.create(organization=organization, updated_by=user)
    event = ResendWebhookEvent.objects.create(
        configuration=config,
        organization=organization,
        webhook_id="evt-bounce",
        event_type="email.bounced",
        provider_email_id="provider-1",
        rfc_message_id=attempt.rfc_message_id,
        occurred_at=timezone.now(),
    )
    reconcile_event(event)
    recipient.refresh_from_db()
    assert recipient.state == ProspectCampaignRecipient.State.BOUNCED
    assert ProspectSuppression.objects.filter(
        organization=organization,
        normalized_email=recipient.normalized_email,
        reason=ProspectSuppression.Reason.HARD_BOUNCE,
        active=True,
    ).exists()
    opened = ResendWebhookEvent.objects.create(
        configuration=config,
        organization=organization,
        webhook_id="evt-open",
        event_type="email.opened",
        provider_email_id="provider-1",
        rfc_message_id=attempt.rfc_message_id,
        occurred_at=timezone.now(),
    )
    reconcile_event(opened)
    assert campaign_metrics(campaign)["opened"] == 1
    assert ProspectReply.objects.count() == 0


def test_rewritten_resend_message_id_uses_exact_details_and_replays_stored_events(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    campaign, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    attempt = deliver_recipient(recipient, send_function=lambda *args, **kwargs: None)
    message = attempt.message
    provider_id = "prospecting-provider-rewritten"
    provider_rfc = "<provider-generated@email.amazonses.com>"
    config = ResendWebhookConfiguration.objects.create(organization=organization, updated_by=user)
    events = []
    for index, event_type in enumerate(
        ("email.sent", "email.delivered", "email.opened", "email.opened", "email.clicked")
    ):
        events.append(
            ResendWebhookEvent.objects.create(
                configuration=config,
                organization=organization,
                webhook_id=f"prospecting-replay-{index}",
                event_type=event_type,
                provider_email_id=provider_id,
                rfc_message_id=provider_rfc,
                occurred_at=attempt.attempted_at + timedelta(seconds=index),
            )
        )
    details = {
        "id": provider_id,
        "message_id": provider_rfc,
        "from": message.from_address,
        "to": [message.to_address],
        "subject": message.subject,
        "text": f"{message.body}\n",
        "created_at": attempt.attempted_at.isoformat(),
    }
    monkeypatch.setattr("apps.prospecting.webhooks._sent_details", lambda *args: details)

    assert reconcile_event(events[-1]) == message
    mapping = ProspectProviderEmail.objects.get(provider_email_id=provider_id)
    assert mapping.message_id == message.pk
    assert mapping.rfc_message_id == provider_rfc
    metrics = metric_bundle(organization, campaign_id=campaign.pk)
    assert metrics["delivered"] == 1
    assert metrics["opened"] == 1
    assert metrics["clicked"] == 1
    assert reconcile_event(events[0]) == message
    assert ProspectProviderEmail.objects.filter(provider_email_id=provider_id).count() == 1
    assert ResendWebhookEvent.objects.filter(provider_email_id=provider_id).count() == 5


@pytest.mark.parametrize(
    ("changed_field", "changed_value"),
    [
        ("from", "wrong@example.com"),
        ("to", ["wrong@example.com"]),
        ("subject", "Wrong subject"),
        ("text", "Wrong body"),
    ],
)
def test_provider_detail_fallback_rejects_changed_content(
    monkeypatch,
    settings,
    user,
    organization,
    membership,
    changed_field,
    changed_value,
):
    entry = make_entry(organization, user)
    _, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    attempt = deliver_recipient(recipient, send_function=lambda *args, **kwargs: None)
    message = attempt.message
    details = {
        "id": "provider-exact-check",
        "message_id": "<provider-generated@email.amazonses.com>",
        "from": message.from_address,
        "to": [message.to_address],
        "subject": message.subject,
        "text": message.body,
        "created_at": attempt.attempted_at.isoformat(),
        changed_field: changed_value,
    }
    assert _exact_sent_message(organization, details) is None


def test_provider_detail_fallback_rejects_old_or_ambiguous_attempts(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    _, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    attempt = deliver_recipient(recipient, send_function=lambda *args, **kwargs: None)
    message = attempt.message
    details = {
        "id": "provider-timing-check",
        "message_id": "<provider-generated@email.amazonses.com>",
        "from": message.from_address,
        "to": [message.to_address],
        "subject": message.subject,
        "text": message.body,
        "created_at": (attempt.attempted_at + timedelta(hours=1)).isoformat(),
    }
    assert _exact_sent_message(organization, details) is None
    details["created_at"] = attempt.attempted_at.isoformat()
    ProspectDeliveryAttempt.objects.create(
        message=message,
        sequence=2,
        provider_key="smtp",
        idempotency_key="ambiguous-provider-attempt",
        rfc_message_id=message.rfc_message_id,
        status=ProspectDeliveryAttempt.Status.SUCCEEDED,
        completed_at=attempt.completed_at,
    )
    assert _exact_sent_message(organization, details) is None


def test_provider_detail_fallback_fails_when_details_also_match_m3(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    _, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    attempt = deliver_recipient(recipient, send_function=lambda *args, **kwargs: None)
    message = attempt.message
    details = {
        "id": "provider-domain-collision",
        "message_id": "<provider-generated@email.amazonses.com>",
        "from": message.from_address,
        "to": [message.to_address],
        "subject": message.subject,
        "text": message.body,
        "created_at": attempt.attempted_at.isoformat(),
    }
    monkeypatch.setattr(
        "apps.outreach.resend_webhooks._exact_sent_message",
        lambda *args, **kwargs: object(),
    )
    assert _exact_sent_message(organization, details) is None


def test_provider_id_already_owned_by_m3_never_fetches_or_maps_prospecting(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    _, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    attempt = deliver_recipient(recipient, send_function=lambda *args, **kwargs: None)
    config = ResendWebhookConfiguration.objects.create(organization=organization, updated_by=user)
    event = ResendWebhookEvent.objects.create(
        configuration=config,
        organization=organization,
        webhook_id="m3-owned-provider-id",
        event_type="email.sent",
        provider_email_id="provider-owned-by-m3",
        rfc_message_id="<provider-generated@email.amazonses.com>",
        occurred_at=attempt.attempted_at,
    )

    class ExistingOwnership:
        @staticmethod
        def exists():
            return True

    class M3OwnershipManager:
        @staticmethod
        def filter(**kwargs):
            return ExistingOwnership()

    from apps.prospecting import webhooks

    monkeypatch.setattr(webhooks.OutreachProviderEmail, "objects", M3OwnershipManager())
    monkeypatch.setattr(
        webhooks,
        "_sent_details",
        lambda *args: pytest.fail("M3-owned provider ID must not be retrieved"),
    )
    assert reconcile_event(event) is None
    assert ProspectProviderEmail.objects.count() == 0


def test_limits_and_sending_window_block_delivery(
    monkeypatch, settings, user, organization, membership
):
    entry = make_entry(organization, user)
    _, recipient = make_campaign(monkeypatch, settings, organization, user, entry)
    config = ProspectingSettings.objects.get(organization=organization)
    recipient.refresh_from_db()
    due_time = recipient.next_due_at + timedelta(seconds=1)
    config.allowed_start_hour = 1 if due_time.hour == 0 else 0
    config.allowed_end_hour = 2 if due_time.hour == 0 else 1
    config.save(update_fields=("allowed_start_hour", "allowed_end_hour"))
    with pytest.raises(ValidationError, match="window"):
        deliver_recipient(recipient, send_function=lambda *args, **kwargs: None, now=due_time)
