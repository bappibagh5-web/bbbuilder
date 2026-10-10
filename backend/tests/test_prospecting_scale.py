from collections import Counter
from datetime import timedelta
from time import perf_counter

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.contractors.models import Company, Contact
from apps.organizations.models import Membership
from apps.outreach.models import (
    OutreachSenderSettings,
    OutreachSMTPConfiguration,
    ResendWebhookConfiguration,
    ResendWebhookEvent,
)
from apps.prospecting.analytics import metric_bundle
from apps.prospecting.campaigns import (
    approve_campaign,
    create_campaign,
    enroll_entries,
    launch_campaign,
    process_due_prospecting_messages,
    save_step,
)
from apps.prospecting.models import (
    ProspectCampaignRecipient,
    ProspectDeliveryAttempt,
    ProspectingSettings,
    ProspectList,
    ProspectListEntry,
    ProspectMessage,
    ProspectProviderEmail,
)

pytestmark = pytest.mark.django_db(transaction=True)

SCALE = 500
RESERVED_DOMAIN = "@example.test"


def _scale_campaign(monkeypatch, settings, organization, user, membership):
    settings.FRONTEND_ORIGIN = "https://app.example.test"
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=("role",))
    ProspectingSettings.objects.create(
        organization=organization,
        is_enabled=True,
        max_sends_per_hour=5000,
        max_sends_per_day=5000,
        sending_timezone="UTC",
        allowed_start_hour=0,
        allowed_end_hour=24,
        business_identity="BB Builders test environment",
        compliance_footer="Synthetic validation message only.",
        updated_by=user,
    )
    OutreachSenderSettings.objects.create(
        organization=organization,
        display_name="BB Builders Test",
        from_address="sender@example.test",
        reply_to="reply@example.test",
        updated_by=user,
    )
    OutreachSMTPConfiguration.objects.create(
        organization=organization,
        host="smtp.example.test",
        port=587,
        username="fake",
        encrypted_password="fake-test-value",
        security="starttls",
        is_enabled=True,
        updated_by=user,
    )
    monkeypatch.setattr(
        "apps.prospecting.campaigns.provider_status",
        lambda _organization: {"state": "configured"},
    )

    companies = Company.objects.bulk_create(
        [
            Company(
                organization=organization,
                display_name=f"Synthetic Prospect {index:04d}",
                city="Test City",
                country="Canada",
                created_by=user,
                updated_by=user,
            )
            for index in range(1, SCALE + 1)
        ]
    )
    contacts = Contact.objects.bulk_create(
        [
            Contact(
                company=company,
                name=f"Prospect {index:04d}",
                email=f"prospect-{index:04d}{RESERVED_DOMAIN}",
                is_active=True,
            )
            for index, company in enumerate(companies, start=1)
        ]
    )
    prospect_list = ProspectList.objects.create(
        organization=organization, name="500 recipient scale validation", created_by=user
    )
    entries = ProspectListEntry.objects.bulk_create(
        [
            ProspectListEntry(
                prospect_list=prospect_list,
                company=company,
                primary_contact=contact,
                status=ProspectListEntry.Status.CONTACT_READY,
                source_type="synthetic_scale_test",
                added_by=user,
            )
            for company, contact in zip(companies, contacts, strict=True)
        ]
    )
    campaign = create_campaign(
        organization=organization,
        actor=user,
        name="Synthetic 500 recipient campaign",
        list_ids=[prospect_list.pk],
    )
    for step_number, delay_minutes, label in (
        (1, 0, "Initial email"),
        (2, 2 * 24 * 60, "Follow-up 1"),
        (3, 4 * 24 * 60, "Final follow-up"),
    ):
        save_step(
            campaign=campaign,
            actor=user,
            values={
                "step_number": step_number,
                "label": label,
                "subject": f"Step {step_number} for {{{{company_name}}}}",
                "body": "Hello {{contact_name}} at {{company_name}}.",
                "delay_minutes": delay_minutes,
                "enabled": True,
            },
        )
    counts, recipients = enroll_entries(
        campaign=campaign,
        entries=ProspectListEntry.objects.filter(pk__in=[entry.pk for entry in entries]),
        actor=user,
    )
    assert counts["eligible"] == SCALE
    assert len(recipients) == SCALE
    approve_campaign(campaign=campaign, actor=user)
    launch_campaign(campaign=campaign, actor=user)
    return campaign


def _drain_due(organization, fake_send):
    totals = {"processed": 0, "sent": 0, "scheduled": 0, "skipped": 0, "failed": 0}
    invocations = 0
    while True:
        result = process_due_prospecting_messages(
            organization=organization,
            limit=50,
            send_function=fake_send,
            return_summary=True,
        )
        invocations += 1
        for key in totals:
            totals[key] += result[key]
        if result["processed"] == 0:
            break
    return totals, invocations


def test_500_recipient_three_step_delivery_is_bounded_and_idempotent(
    monkeypatch, settings, organization, user, membership
):
    campaign = _scale_campaign(monkeypatch, settings, organization, user, membership)
    submitted = []

    def fake_send(*_args, **kwargs):
        assert kwargs["to_address"].endswith(RESERVED_DOMAIN)
        assert kwargs["from_address"].endswith(RESERVED_DOMAIN)
        submitted.append((kwargs["to_address"], kwargs["subject"], kwargs["message_id"]))

    started = perf_counter()
    with CaptureQueriesContext(connection) as first_batch_queries:
        first_batch = process_due_prospecting_messages(
            organization=organization,
            limit=50,
            send_function=fake_send,
            return_summary=True,
        )
    remaining_step_one, remaining_invocations = _drain_due(organization, fake_send)
    step_one = {
        key: first_batch[key] + remaining_step_one[key]
        for key in ("processed", "sent", "scheduled", "skipped", "failed")
    }
    step_one_invocations = remaining_invocations + 1
    step_one_seconds = perf_counter() - started
    assert step_one == {
        "processed": SCALE,
        "sent": SCALE,
        "scheduled": SCALE,
        "skipped": 0,
        "failed": 0,
    }
    assert step_one_invocations == 11
    assert len(submitted) == SCALE
    assert (
        ProspectMessage.objects.filter(
            recipient__campaign=campaign, step_version__step_number=1
        ).count()
        == SCALE
    )
    assert (
        ProspectDeliveryAttempt.objects.filter(
            message__recipient__campaign=campaign,
            message__step_version__step_number=1,
            status=ProspectDeliveryAttempt.Status.SUCCEEDED,
        ).count()
        == SCALE
    )
    assert not any(count > 1 for count in Counter(submitted).values())
    assert (
        campaign.recipients.filter(
            state=ProspectCampaignRecipient.State.ACTIVE,
            current_step=1,
            next_due_at__isnull=False,
        ).count()
        == SCALE
    )

    no_retry, _ = _drain_due(organization, fake_send)
    assert no_retry == {
        "processed": 0,
        "sent": 0,
        "scheduled": 0,
        "skipped": 0,
        "failed": 0,
    }
    assert len(submitted) == SCALE

    clock = timezone.now() + timedelta(days=3)
    monkeypatch.setattr("apps.prospecting.campaigns.timezone.now", lambda: clock)
    step_two, step_two_invocations = _drain_due(organization, fake_send)
    assert step_two == {
        "processed": SCALE,
        "sent": SCALE,
        "scheduled": SCALE,
        "skipped": 0,
        "failed": 0,
    }
    assert step_two_invocations == 11
    assert campaign.recipients.filter(current_step=2, state="active").count() == SCALE

    clock += timedelta(days=5)
    step_three, step_three_invocations = _drain_due(organization, fake_send)
    assert step_three == {
        "processed": SCALE,
        "sent": SCALE,
        "scheduled": 0,
        "skipped": 0,
        "failed": 0,
    }
    assert step_three_invocations == 11
    assert (
        campaign.recipients.filter(
            current_step=3, state=ProspectCampaignRecipient.State.COMPLETED, next_due_at=None
        ).count()
        == SCALE
    )
    assert ProspectMessage.objects.filter(recipient__campaign=campaign).count() == SCALE * 3
    assert (
        ProspectDeliveryAttempt.objects.filter(
            message__recipient__campaign=campaign, status=ProspectDeliveryAttempt.Status.SUCCEEDED
        ).count()
        == SCALE * 3
    )
    assert len(submitted) == SCALE * 3
    assert len(set(submitted)) == SCALE * 3

    step_one_messages = list(
        ProspectMessage.objects.filter(
            recipient__campaign=campaign, step_version__step_number=1
        ).order_by("id")
    )
    mappings = ProspectProviderEmail.objects.bulk_create(
        [
            ProspectProviderEmail(
                organization=organization,
                message=message,
                provider_email_id=f"fake-provider-{index:04d}",
                rfc_message_id=message.rfc_message_id,
            )
            for index, message in enumerate(step_one_messages, start=1)
        ]
    )
    configuration = ResendWebhookConfiguration.objects.create(
        organization=organization, is_enabled=True, updated_by=user
    )
    events = []
    event_number = 0

    def add_event(mapping, event_type):
        nonlocal event_number
        event_number += 1
        events.append(
            ResendWebhookEvent(
                configuration=configuration,
                organization=organization,
                webhook_id=f"fake-scale-event-{event_number:05d}",
                event_type=event_type,
                provider_email_id=mapping.provider_email_id,
                rfc_message_id=mapping.rfc_message_id,
                occurred_at=clock,
            )
        )

    for mapping in mappings[:450]:
        add_event(mapping, "email.delivered")
    for mapping in mappings[:300]:
        add_event(mapping, "email.opened")
    for mapping in mappings[:100]:
        add_event(mapping, "email.opened")
    for mapping in mappings[:80]:
        add_event(mapping, "email.clicked")
    for mapping in mappings[:20]:
        add_event(mapping, "email.clicked")
    ResendWebhookEvent.objects.bulk_create(events)
    metrics = metric_bundle(organization, campaign_id=campaign.pk)
    assert metrics["messages_sent"] == SCALE * 3
    assert metrics["delivered"] == 450
    assert metrics["opened"] == 300
    assert metrics["clicked"] == 80
    assert metrics["tracking"]["event_count"] == 950

    with CaptureQueriesContext(connection) as queries:
        assert (
            process_due_prospecting_messages(
                organization=organization,
                limit=50,
                send_function=lambda *_args, **_kwargs: pytest.fail("completed message resent"),
                return_summary=True,
            )["processed"]
            == 0
        )
    assert len(queries) <= 2
    print(
        "SCALE_METRICS",
        {
            "recipients": SCALE,
            "batch_size": 50,
            "step_one_seconds": round(step_one_seconds, 3),
            "first_batch_queries": len(first_batch_queries),
            "empty_batch_queries": len(queries),
            "provider_submissions": len(submitted),
            "analytics": {
                "sent": metrics["messages_sent"],
                "delivered": metrics["delivered"],
                "unique_opened": metrics["opened"],
                "total_open_events": 400,
                "unique_clicked": metrics["clicked"],
                "total_click_events": 100,
            },
        },
    )


def test_500_due_recipients_respect_hourly_and_daily_boundaries(
    monkeypatch, settings, organization, user, membership
):
    campaign = _scale_campaign(monkeypatch, settings, organization, user, membership)
    config = ProspectingSettings.objects.get(organization=organization)
    config.max_sends_per_hour = 20
    config.max_sends_per_day = 100
    config.save(update_fields=("max_sends_per_hour", "max_sends_per_day"))
    submitted = []

    def fake_send(*_args, **kwargs):
        assert kwargs["to_address"].endswith(RESERVED_DOMAIN)
        submitted.append(kwargs["to_address"])

    clock = timezone.now()
    monkeypatch.setattr("apps.prospecting.campaigns.timezone.now", lambda: clock)
    for _hour in range(5):
        summary = process_due_prospecting_messages(
            organization=organization,
            limit=50,
            send_function=fake_send,
            return_summary=True,
        )
        assert summary == {
            "processed": 50,
            "sent": 20,
            "scheduled": 20,
            "skipped": 30,
            "failed": 0,
        }
        clock += timedelta(hours=1, seconds=1)
    assert len(submitted) == 100
    assert len(set(submitted)) == 100
    daily_block = process_due_prospecting_messages(
        organization=organization,
        limit=50,
        send_function=lambda *_args, **_kwargs: pytest.fail("daily limit exceeded"),
        return_summary=True,
    )
    assert daily_block == {
        "processed": 50,
        "sent": 0,
        "scheduled": 0,
        "skipped": 50,
        "failed": 0,
    }
    assert campaign.recipients.filter(current_step=1).count() == 100
    assert campaign.recipients.filter(current_step=0).count() == 400
