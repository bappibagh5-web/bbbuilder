from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.contractors.models import Company, Contact
from apps.organizations.models import Membership, Organization
from apps.outreach.models import ResendWebhookConfiguration, ResendWebhookEvent
from apps.prospecting.analytics import metric_bundle, recipient_rows, sequence_step_rows
from apps.prospecting.models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectCampaignVersion,
    ProspectDeliveryAttempt,
    ProspectList,
    ProspectListEntry,
    ProspectMessage,
    ProspectProviderEmail,
    ProspectSequenceStepVersion,
)

pytestmark = pytest.mark.django_db


def analytics_fixture(organization, user):
    company = Company.objects.create(
        organization=organization,
        display_name="Analytics Mechanical",
        created_by=user,
        updated_by=user,
    )
    contact = Contact.objects.create(
        company=company,
        name="Taylor Smith",
        email="taylor@example.com",
        is_active=True,
    )
    prospect_list = ProspectList.objects.create(
        organization=organization,
        name="Analytics list",
        created_by=user,
    )
    entry = ProspectListEntry.objects.create(
        prospect_list=prospect_list,
        company=company,
        primary_contact=contact,
        status=ProspectListEntry.Status.CONTACT_READY,
        added_by=user,
    )
    campaign = ProspectCampaign.objects.create(
        organization=organization,
        name="Analytics campaign",
        status=ProspectCampaign.Status.ACTIVE,
        created_by=user,
        launched_by=user,
        launched_at=timezone.now(),
    )
    version = ProspectCampaignVersion.objects.create(
        campaign=campaign,
        version_number=1,
        sender_name="BB Builders",
        from_address="prospecting@example.com",
        reply_to="reply@example.com",
        business_identity="BB Builders Ltd.",
        compliance_footer="Reply to unsubscribe.",
        sequence_fingerprint="a" * 64,
        created_by=user,
    )
    step = ProspectSequenceStepVersion.objects.create(
        campaign_version=version,
        step_number=1,
        label="Initial email",
        subject="Hello",
        body="Hello",
        delay_minutes=0,
    )
    recipient = ProspectCampaignRecipient.objects.create(
        campaign=campaign,
        campaign_version=version,
        prospect_entry=entry,
        company=company,
        contact=contact,
        company_name=company.display_name,
        contact_name=contact.name,
        normalized_email=contact.email,
        state=ProspectCampaignRecipient.State.COMPLETED,
        current_step=1,
        enrolled_by=user,
    )
    message = ProspectMessage.objects.create(
        recipient=recipient,
        step_version=step,
        from_name="BB Builders",
        from_address="prospecting@example.com",
        reply_to="reply@example.com",
        to_address=contact.email,
        subject="Hello",
        body="Hello",
        unsubscribe_url="https://example.com/unsubscribe/token",
        rfc_message_id="<analytics@example.com>",
    )
    now = timezone.now()
    ProspectDeliveryAttempt.objects.create(
        message=message,
        sequence=1,
        provider_key="fake",
        idempotency_key="analytics-attempt",
        rfc_message_id=message.rfc_message_id,
        status=ProspectDeliveryAttempt.Status.SUCCEEDED,
        completed_at=now,
    )
    configuration = ResendWebhookConfiguration.objects.create(
        organization=organization,
        is_enabled=True,
        updated_by=user,
    )
    mapping = ProspectProviderEmail.objects.create(
        organization=organization,
        message=message,
        provider_email_id="provider-email-1",
        rfc_message_id=message.rfc_message_id,
    )
    for index, event_type in enumerate(
        ("email.delivered", "email.opened", "email.opened", "email.clicked")
    ):
        ResendWebhookEvent.objects.create(
            configuration=configuration,
            organization=organization,
            webhook_id=f"analytics-event-{index}",
            event_type=event_type,
            provider_email_id=mapping.provider_email_id,
            rfc_message_id=mapping.rfc_message_id,
            occurred_at=now + timedelta(seconds=index),
        )
    return campaign, recipient


def test_metrics_distinguish_messages_recipients_and_unique_events(organization, user):
    campaign, _ = analytics_fixture(organization, user)
    metrics = metric_bundle(organization, campaign_id=campaign.pk)
    assert metrics["prospects_contacted"] == 1
    assert metrics["messages_sent"] == 1
    assert metrics["delivered"] == 1
    assert metrics["opened"] == 1
    assert metrics["clicked"] == 1
    assert metrics["rates"]["open"] == 100.0
    assert metrics["tracking"]["available"] is True


def test_recipient_events_keep_repeated_event_counts_and_step_metrics(organization, user):
    campaign, recipient = analytics_fixture(organization, user)
    row = recipient_rows(organization, campaign_id=campaign.pk)[0]
    assert row["id"] == recipient.pk
    assert row["open_count"] == 2
    assert row["click_count"] == 1
    step = sequence_step_rows(organization, campaign)[0]
    assert step["sent"] == 1
    assert step["opened"] == 1


def test_analytics_endpoints_are_org_scoped_and_paginated(organization, user):
    campaign, recipient = analytics_fixture(organization, user)
    Membership.objects.create(
        organization=organization,
        user=user,
        role=Membership.Role.VIEWER,
    )
    client = APIClient()
    client.force_authenticate(user)
    root = f"/api/v1/organizations/{organization.slug}/prospecting/analytics"
    assert client.get(f"{root}/?range=30d").data["summary"]["messages_sent"] == 1
    campaigns = client.get(f"{root}/campaigns/?range=30d")
    assert campaigns.status_code == 200
    assert campaigns.data["results"][0]["id"] == campaign.pk
    recipients = client.get(f"{root}/recipients/?engagement=opened")
    assert recipients.status_code == 200
    assert recipients.data["results"][0]["id"] == recipient.pk

    other = Organization.objects.create(name="Other", slug="other")
    assert client.get(f"/api/v1/organizations/{other.slug}/prospecting/analytics/").status_code in {
        403,
        404,
    }


def test_sent_without_provider_events_reports_tracking_unavailable(organization, user):
    campaign, _ = analytics_fixture(organization, user)
    ResendWebhookEvent.objects.all().delete()
    metrics = metric_bundle(organization, campaign_id=campaign.pk)
    assert metrics["messages_sent"] == 1
    assert metrics["opened"] == 0
    assert metrics["tracking"]["available"] is False
    assert "not been received" in metrics["tracking"]["message"]


def test_analytics_date_filter_excludes_old_messages_and_events(organization, user):
    campaign, _ = analytics_fixture(organization, user)
    old = timezone.now() - timedelta(days=120)
    ProspectDeliveryAttempt.objects.update(completed_at=old)
    ResendWebhookEvent.objects.update(occurred_at=old)
    metrics = metric_bundle(
        organization,
        campaign_id=campaign.pk,
        since=timezone.now() - timedelta(days=30),
    )
    assert metrics["messages_sent"] == 0
    assert metrics["delivered"] == 0
    assert metrics["tracking"]["message"] == "No emails were sent in this period."
