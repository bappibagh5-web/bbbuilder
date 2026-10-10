import pytest
from rest_framework.test import APIClient

from apps.contractors.models import Company, Contact
from apps.organizations.models import Membership, Organization
from apps.prospecting.campaigns import (
    campaign_readiness,
    create_campaign,
    enroll_entries,
    process_due_prospecting_messages,
    remove_or_archive_campaign,
    restore_campaign,
    save_step,
)
from apps.prospecting.models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectCampaignVersion,
    ProspectDeliveryAttempt,
    ProspectEmailTemplate,
    ProspectList,
    ProspectListEntry,
    ProspectMessage,
    ProspectSequenceStepVersion,
)

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def entry_for(organization, user):
    company = Company.objects.create(
        organization=organization,
        display_name="Lifecycle Mechanical",
        created_by=user,
        updated_by=user,
    )
    contact = Contact.objects.create(
        company=company, name="Taylor Smith", email="taylor@example.com"
    )
    prospect_list = ProspectList.objects.create(
        organization=organization, name="Lifecycle list", created_by=user
    )
    entry = ProspectListEntry.objects.create(
        prospect_list=prospect_list,
        company=company,
        primary_contact=contact,
        status=ProspectListEntry.Status.CONTACT_READY,
        added_by=user,
    )
    return prospect_list, entry


def test_readiness_blockers_follow_user_workflow_priority(user, organization, membership):
    campaign = create_campaign(organization=organization, actor=user, name="Readiness")
    assert campaign_readiness(campaign)["blockers"][0] == "Add the initial email"

    save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 1,
            "label": "Initial Email",
            "subject": "Hello",
            "body": "Body",
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    assert campaign_readiness(campaign)["blockers"][0] == "Enroll eligible prospects"

    _, entry = entry_for(organization, user)
    enroll_entries(
        campaign=campaign,
        entries=ProspectListEntry.objects.filter(pk=entry.pk),
        actor=user,
    )
    assert campaign_readiness(campaign)["blockers"][0] == "Enable Prospecting email delivery"


def test_draft_with_recipient_is_deleted_without_deleting_canonical_prospect_data(
    user, organization, membership
):
    prospect_list, entry = entry_for(organization, user)
    empty = create_campaign(
        organization=organization,
        actor=user,
        name="Disposable",
        list_ids=[prospect_list.pk],
    )
    save_step(
        campaign=empty,
        actor=user,
        values={
            "step_number": 1,
            "label": "Initial",
            "subject": "Hello",
            "body": "Body",
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    _, recipients = enroll_entries(
        campaign=empty,
        entries=ProspectListEntry.objects.filter(pk=entry.pk),
        actor=user,
    )
    empty_id = empty.pk
    company_id = entry.company_id
    contact_id = entry.primary_contact_id
    entry_id = entry.pk
    response = client_for(user).delete(
        f"/api/v1/organizations/{organization.slug}/prospecting/campaigns/{empty_id}/"
    )
    assert response.status_code == 200
    assert response.data["outcome"] == "deleted"
    assert not ProspectCampaign.objects.filter(pk=empty_id).exists()
    assert not ProspectCampaignRecipient.objects.filter(pk=recipients[0].pk).exists()
    assert Company.objects.filter(pk=company_id).exists()
    assert Contact.objects.filter(pk=contact_id).exists()
    assert ProspectListEntry.objects.filter(pk=entry_id, is_active=True).exists()
    assert ProspectList.objects.filter(pk=prospect_list.pk).exists()


def test_draft_with_delivery_history_is_archived_and_stopped(user, organization, membership):
    prospect_list, entry = entry_for(organization, user)

    historical = create_campaign(
        organization=organization,
        actor=user,
        name="Historical",
        list_ids=[prospect_list.pk],
    )
    _, recipients = enroll_entries(
        campaign=historical,
        entries=ProspectListEntry.objects.filter(pk=entry.pk),
        actor=user,
    )
    recipient = recipients[0]
    step = save_step(
        campaign=historical,
        actor=user,
        values={
            "step_number": 1,
            "label": "Initial",
            "subject": "Hello",
            "body": "Body",
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    version = ProspectCampaignVersion.objects.create(
        campaign=historical,
        version_number=1,
        sender_name="BB Builders",
        from_address="sender@example.com",
        reply_to="reply@example.com",
        business_identity="BB Builders",
        compliance_footer="Footer",
        sequence_fingerprint="a" * 64,
        created_by=user,
    )
    step_version = ProspectSequenceStepVersion.objects.create(
        campaign_version=version,
        step_number=1,
        label=step.label,
        subject=step.subject,
        body=step.body,
        delay_minutes=0,
    )
    recipient.campaign_version = version
    recipient.state = ProspectCampaignRecipient.State.SCHEDULED
    recipient.next_due_at = recipient.enrolled_at
    recipient.save(update_fields=("campaign_version", "state", "next_due_at"))
    message = ProspectMessage.objects.create(
        recipient=recipient,
        step_version=step_version,
        from_name="BB Builders",
        from_address="sender@example.com",
        reply_to="reply@example.com",
        to_address=recipient.normalized_email,
        subject="Hello",
        body="Body",
        unsubscribe_url="https://example.com/unsubscribe/test",
        rfc_message_id="<lifecycle@example.com>",
    )
    attempt = ProspectDeliveryAttempt.objects.create(
        message=message,
        sequence=1,
        provider_key="smtp",
        idempotency_key="lifecycle-attempt",
        rfc_message_id=message.rfc_message_id,
    )
    assert remove_or_archive_campaign(campaign=historical, actor=user) == "archived"
    historical.refresh_from_db()
    recipient.refresh_from_db()
    assert historical.status == ProspectCampaign.Status.ARCHIVED
    assert recipient.state == ProspectCampaignRecipient.State.CANCELLED
    assert recipient.next_due_at is None
    assert historical.recipients.get().pk == recipient.pk
    assert ProspectDeliveryAttempt.objects.filter(pk=attempt.pk).exists()
    assert process_due_prospecting_messages(send_function=lambda *args, **kwargs: None) == []
    detail = client_for(user).get(
        f"/api/v1/organizations/{organization.slug}/prospecting/campaigns/{historical.pk}/"
    )
    assert detail.status_code == 200
    assert detail.data["campaign"]["status"] == ProspectCampaign.Status.ARCHIVED
    assert detail.data["recipients"][0]["id"] == recipient.pk

    restore_campaign(campaign=historical, actor=user)
    historical.refresh_from_db()
    recipient.refresh_from_db()
    assert historical.status == ProspectCampaign.Status.DRAFT
    assert recipient.state == ProspectCampaignRecipient.State.CANCELLED
    assert recipient.next_due_at is None


def test_archived_campaign_and_list_are_hidden_by_default_but_history_resolves(
    user, organization, membership
):
    prospect_list, _ = entry_for(organization, user)
    campaign = create_campaign(
        organization=organization,
        actor=user,
        name="Archived campaign",
        list_ids=[prospect_list.pk],
    )
    campaign.status = ProspectCampaign.Status.ARCHIVED
    campaign.save(update_fields=("status",))
    prospect_list.status = ProspectList.Status.ARCHIVED
    prospect_list.save(update_fields=("status",))

    root = f"/api/v1/organizations/{organization.slug}/prospecting"
    active_campaigns = client_for(user).get(f"{root}/campaigns/")
    archived_campaigns = client_for(user).get(f"{root}/campaigns/?status=archived")
    active_lists = client_for(user).get(f"{root}/lists/")
    archived_lists = client_for(user).get(f"{root}/lists/?status=archived")
    assert active_campaigns.data["count"] == 0
    assert archived_campaigns.data["results"][0]["id"] == campaign.pk
    assert active_lists.data["count"] == 0
    assert archived_lists.data["results"][0]["id"] == prospect_list.pk
    campaign.refresh_from_db()
    assert list(campaign.source_lists.values_list("id", flat=True)) == [prospect_list.pk]


def test_template_archive_preserves_copied_step_and_restore_is_explicit(
    user, organization, membership
):
    template = ProspectEmailTemplate.objects.create(
        organization=organization,
        name="Reusable",
        subject="Hello {{company_name}}",
        body="Hi {{first_name}}",
        created_by=user,
        updated_by=user,
    )
    campaign = create_campaign(organization=organization, actor=user, name="Template campaign")
    step = save_step(
        campaign=campaign,
        actor=user,
        values={
            "step_number": 1,
            "label": "Initial",
            "subject": template.subject,
            "body": template.body,
            "delay_minutes": 0,
            "enabled": True,
        },
    )
    url = f"/api/v1/organizations/{organization.slug}/prospecting/templates/{template.pk}/"
    assert client_for(user).patch(url, {"is_active": False}, format="json").status_code == 200
    active = client_for(user).get(
        f"/api/v1/organizations/{organization.slug}/prospecting/templates/"
    )
    assert active.data["results"] == []
    step.refresh_from_db()
    assert step.subject == "Hello {{company_name}}"
    assert client_for(user).patch(url, {"is_active": True}, format="json").status_code == 200


def test_viewer_and_cross_org_cannot_remove_campaign(user, organization, membership):
    campaign = create_campaign(organization=organization, actor=user, name="Protected")
    url = f"/api/v1/organizations/{organization.slug}/prospecting/campaigns/{campaign.pk}/"
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client_for(user).delete(url).status_code == 403
    other = Organization.objects.create(name="Other", slug="other-lifecycle")
    assert (
        client_for(user)
        .delete(f"/api/v1/organizations/{other.slug}/prospecting/campaigns/{campaign.pk}/")
        .status_code
        == 403
    )
    assert ProspectCampaign.objects.filter(pk=campaign.pk).exists()
