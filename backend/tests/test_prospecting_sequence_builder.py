import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.contractors.models import Company, Contact
from apps.organizations.models import Membership, Organization
from apps.outreach.models import OutreachSenderSettings, OutreachSMTPConfiguration
from apps.prospecting.campaigns import (
    approve_campaign,
    create_campaign,
    delete_step,
    deliver_recipient,
    duplicate_step,
    enroll_entries,
    launch_campaign,
    render_draft_preview,
    reorder_steps,
    save_step,
    send_test_email,
)
from apps.prospecting.models import (
    ProspectCampaignRecipient,
    ProspectDeliveryAttempt,
    ProspectEmailTemplate,
    ProspectingSettings,
    ProspectList,
    ProspectListEntry,
    ProspectMessage,
)

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def entry_for(organization, user, *, name="Acme Mechanical", email="taylor@example.com"):
    company = Company.objects.create(
        organization=organization,
        display_name=name,
        created_by=user,
        updated_by=user,
    )
    contact = Contact.objects.create(
        company=company, name="Taylor Smith", email=email, is_active=True
    )
    prospect_list = ProspectList.objects.create(
        organization=organization, name=f"{name} list", created_by=user
    )
    return ProspectListEntry.objects.create(
        prospect_list=prospect_list,
        company=company,
        primary_contact=contact,
        status=ProspectListEntry.Status.CONTACT_READY,
        added_by=user,
    )


def sending_setup(organization, user):
    ProspectingSettings.objects.create(
        organization=organization,
        is_enabled=True,
        allowed_start_hour=0,
        allowed_end_hour=24,
        business_identity="BB Builders Ltd.",
        compliance_footer="Reply if you would prefer not to hear from us.",
        updated_by=user,
    )
    OutreachSenderSettings.objects.create(
        organization=organization,
        display_name="BB Builders",
        from_address="prospecting@example.com",
        reply_to="replies@example.com",
        is_enabled=True,
        updated_by=user,
    )
    OutreachSMTPConfiguration.objects.create(
        organization=organization,
        host="smtp.example.com",
        port=587,
        username="test",
        encrypted_password="test-only",
        security="starttls",
        is_enabled=True,
        updated_by=user,
    )


def test_ordered_sequence_editing_delay_tokens_and_frozen_safety(user, organization, membership):
    campaign = create_campaign(organization=organization, actor=user, name="Builder")
    first = save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 1,
            "label": "Initial Email",
            "subject": "Hello {{name}}",
            "body": "Hi {{first_name}} at {{company_name}}",
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    second = save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 2,
            "label": "Follow-up 1",
            "subject": "Following up about {{trade}}",
            "body": "Checking in",
            "delay_minutes": 4320,
            "enabled": True,
        },
    )
    with pytest.raises(ValidationError):
        save_step(
            campaign=campaign,
            actor=user,
            values={
                "step_number": 1,
                "subject": "Invalid first step",
                "body": "Body",
                "delay_minutes": 60,
                "enabled": True,
            },
            step=first,
        )
    with pytest.raises(ValidationError, match="Unsupported personalization token"):
        save_step(
            campaign=campaign,
            actor=user,
            values={
                "step_number": 3,
                "subject": "{{unknown_value}}",
                "body": "Body",
                "delay_minutes": 60,
                "enabled": True,
            },
        )
    reorder_steps(campaign=campaign, actor=user, ordered_step_ids=[second.pk, first.pk])
    second.refresh_from_db()
    first.refresh_from_db()
    assert (second.step_number, second.delay_minutes, first.step_number) == (1, 0, 2)
    duplicate = duplicate_step(campaign=campaign, actor=user, step=first)
    assert duplicate.step_number == 3
    save_step(
        campaign=campaign,
        actor=user,
        step=duplicate,
        values={"enabled": False},
    )
    duplicate.refresh_from_db()
    assert duplicate.enabled is False
    delete_step(campaign=campaign, actor=user, step=duplicate)
    assert list(campaign.sequence_steps.values_list("step_number", flat=True)) == [1, 2]


def test_preview_and_test_send_share_personalization_without_campaign_side_effects(
    monkeypatch, settings, user, organization, membership
):
    settings.FRONTEND_ORIGIN = "https://app.example.com"
    entry = entry_for(organization, user)
    sending_setup(organization, user)
    campaign = create_campaign(
        organization=organization,
        actor=user,
        name="Preview",
        list_ids=[entry.prospect_list_id],
    )
    step = save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 1,
            "label": "Initial Email",
            "subject": "Quick question for {{company_name}}",
            "body": "Hi {{first_name}}, trade: {{trade}}",
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    _, recipients = enroll_entries(
        campaign=campaign,
        entries=ProspectListEntry.objects.filter(pk=entry.pk),
        actor=user,
    )
    recipient = recipients[0]
    preview = render_draft_preview(campaign=campaign, step=step, recipient=recipient)
    assert preview["to_address"] == "taylor@example.com"
    assert preview["subject"] == "Quick question for Acme Mechanical"
    assert "Hi Taylor" in preview["body"]
    assert "[not available]" in preview["body"]
    assert "[personalized unsubscribe link]" in preview["body"]

    monkeypatch.setattr(
        "apps.prospecting.campaigns.provider_status", lambda organization: {"state": "configured"}
    )
    sent = []
    send_test_email(
        campaign=campaign,
        step=step,
        actor=user,
        test_email="owner@example.com",
        recipient=recipient,
        send_function=lambda *args, **kwargs: sent.append(kwargs),
    )
    assert sent[0]["to_address"] == "owner@example.com"
    assert sent[0]["subject"] == "[TEST] Quick question for Acme Mechanical"
    assert "[test message - no subscription link]" in sent[0]["body"]
    recipient.refresh_from_db()
    assert recipient.state == ProspectCampaignRecipient.State.PENDING
    assert recipient.current_step == 0
    assert ProspectMessage.objects.count() == 0
    assert ProspectDeliveryAttempt.objects.count() == 0

    step.refresh_from_db()
    assert step.subject == "Quick question for {{company_name}}"
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=("role",))
    version = approve_campaign(campaign=campaign, actor=user)
    assert version.steps.get(step_number=1).subject == "Quick question for {{company_name}}"
    launch_campaign(campaign=campaign, actor=user)
    recipient.refresh_from_db()
    real_sent = []
    attempt = deliver_recipient(
        recipient,
        send_function=lambda *args, **kwargs: real_sent.append(kwargs),
    )
    assert attempt.status == ProspectDeliveryAttempt.Status.SUCCEEDED
    assert real_sent[0]["subject"] == "Quick question for Acme Mechanical"
    assert not real_sent[0]["subject"].startswith("[TEST]")
    assert "/unsubscribe/" in real_sent[0]["body"]
    assert "[test message - no subscription link]" not in real_sent[0]["body"]
    message = ProspectMessage.objects.get()
    assert message.subject == "Quick question for Acme Mechanical"
    assert "/unsubscribe/" in message.unsubscribe_url


def test_templates_are_org_scoped_copied_content_and_viewer_read_only(
    user, organization, membership
):
    url = f"/api/v1/organizations/{organization.slug}/prospecting/templates/"
    created = client_for(user).post(
        url,
        {
            "name": "Mechanical intro",
            "category": "HVAC",
            "subject": "Hello {{company_name}}",
            "body": "Hi {{first_name}}",
        },
        format="json",
    )
    assert created.status_code == 201
    template = ProspectEmailTemplate.objects.get(pk=created.data["id"])
    campaign = create_campaign(organization=organization, actor=user, name="Template copy")
    step = save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 1,
            "label": "Initial Email",
            "subject": template.subject,
            "body": template.body,
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    patched = client_for(user).patch(
        f"{url}{template.pk}/", {"subject": "Updated template"}, format="json"
    )
    assert patched.status_code == 200
    step.refresh_from_db()
    assert step.subject == "Hello {{company_name}}"

    other = Organization.objects.create(name="Other", slug="other-builder")
    assert (
        client_for(user)
        .get(f"/api/v1/organizations/{other.slug}/prospecting/templates/")
        .status_code
        == 403
    )
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client_for(user).get(url).status_code == 200
    assert (
        client_for(user)
        .post(
            url,
            {"name": "Denied", "subject": "Subject", "body": "Body"},
            format="json",
        )
        .status_code
        == 403
    )
