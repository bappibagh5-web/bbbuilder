import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.contractors.models import Company, Contact
from apps.organizations.models import Membership, Organization
from apps.outreach.models import InvitationCampaign, InvitationRecipient
from apps.projects.models import AuditEvent
from apps.prospecting.models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectingDiscoveryRun,
    ProspectList,
    ProspectListEntry,
)

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def lists_url(organization):
    return f"/api/v1/organizations/{organization.slug}/prospecting/lists/"


def discoveries_url(organization):
    return f"/api/v1/organizations/{organization.slug}/prospecting/discoveries/"


def create_list(user, organization, name="Toronto HVAC"):
    response = client_for(user).post(
        lists_url(organization), {"name": name, "description": "Reusable prospects"}, format="json"
    )
    assert response.status_code == 201
    return ProspectList.objects.get(pk=response.data["id"])


def make_company(organization, user, **values):
    defaults = {
        "display_name": "Existing Mechanical",
        "city": "Toronto",
        "province": "ON",
        "created_by": user,
        "updated_by": user,
    }
    defaults.update(values)
    return Company.objects.create(organization=organization, **defaults)


def test_admin_and_estimator_manage_lists_but_viewer_is_read_only(user, organization, membership):
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=["role"])
    prospect_list = create_list(user, organization)
    assert AuditEvent.objects.filter(action_code="prospect_list.created").exists()

    archived = client_for(user).patch(
        f"{lists_url(organization)}{prospect_list.pk}/", {"status": "archived"}, format="json"
    )
    assert archived.status_code == 200
    assert archived.data["status"] == "archived"
    assert AuditEvent.objects.filter(action_code="prospect_list.archived").exists()

    membership.role = Membership.Role.ESTIMATOR_OPERATOR
    membership.save(update_fields=["role"])
    assert create_list(user, organization, "Estimator list").name == "Estimator list"

    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=["role"])
    assert client_for(user).get(lists_url(organization)).status_code == 200
    denied = client_for(user).post(lists_url(organization), {"name": "Denied"}, format="json")
    assert denied.status_code == 403


def test_lists_and_entries_are_organization_isolated(user, organization, membership):
    prospect_list = create_list(user, organization)
    other = Organization.objects.create(name="Other", slug="other")
    other_user = get_user_model().objects.create_user(
        email="other-prospecting@example.com", password="valid-pass"
    )
    Membership.objects.create(
        organization=other, user=other_user, role=Membership.Role.ESTIMATOR_OPERATOR
    )
    other_list = create_list(other_user, other, "Other prospects")

    response = client_for(user).get(lists_url(organization))
    ids = [item["id"] for item in response.data["results"]]
    assert prospect_list.pk in ids
    assert other_list.pk not in ids
    assert client_for(user).get(f"{lists_url(organization)}{other_list.pk}/").status_code == 404


def test_duplicate_entry_and_cross_organization_company_are_rejected(
    user, organization, membership
):
    prospect_list = create_list(user, organization)
    company = make_company(organization, user)
    ProspectListEntry.objects.create(prospect_list=prospect_list, company=company, added_by=user)
    with pytest.raises(ValidationError):
        duplicate = ProspectListEntry(prospect_list=prospect_list, company=company, added_by=user)
        duplicate.full_clean()

    other = Organization.objects.create(name="Other", slug="other-company")
    other_company = make_company(other, user, display_name="Cross Org")
    with pytest.raises(ValidationError, match="list organization"):
        ProspectListEntry(
            prospect_list=prospect_list, company=other_company, added_by=user
        ).full_clean()


def test_contact_ready_requires_active_selected_email_contact(user, organization, membership):
    prospect_list = create_list(user, organization)
    company = make_company(organization, user)
    entry = ProspectListEntry(
        prospect_list=prospect_list,
        company=company,
        added_by=user,
        status=ProspectListEntry.Status.CONTACT_READY,
    )
    with pytest.raises(ValidationError, match="active selected contact"):
        entry.full_clean()
    contact = Contact.objects.create(company=company, name="Estimator", email="bid@example.com")
    entry.primary_contact = contact
    entry.full_clean()


def test_discovery_stores_provenance_reuses_company_and_never_creates_rfq_records(
    settings, user, organization, membership
):
    settings.CONTRACTOR_DISCOVERY_PROVIDER = "fake"
    prospect_list = create_list(user, organization)
    existing = make_company(
        organization,
        user,
        display_name="Demo Hvac Mechanical Contractors",
        external_provider="fake",
        external_place_id="fake-hvac-mechanical-toronto",
    )
    response = client_for(user).post(
        discoveries_url(organization),
        {
            "trade_key": "hvac-mechanical",
            "query": "HVAC contractors",
            "keywords": ["commercial"],
            "city": "Toronto",
            "province": "ON",
            "country": "Canada",
            "radius_miles": 50,
            "prospect_list_id": prospect_list.pk,
        },
        format="json",
    )
    assert response.status_code == 201
    run = ProspectingDiscoveryRun.objects.get(pk=response.data["id"])
    assert run.provider == "fake"
    assert run.query == "HVAC contractors"
    assert run.city == "Toronto"
    assert run.result_count == 1
    result = run.results.get()
    assert result.company == existing
    assert response.data["results"][0]["already_in_directory"] is True

    added = client_for(user).post(
        f"{discoveries_url(organization)}{run.pk}/add/",
        {"prospect_list_id": prospect_list.pk, "result_ids": [result.pk]},
        format="json",
    )
    assert added.status_code == 200
    entry = ProspectListEntry.objects.get(prospect_list=prospect_list)
    assert entry.company == existing
    assert entry.source_metadata["discovery_run_id"] == run.pk
    assert Company.objects.filter(organization=organization).count() == 1
    assert AuditEvent.objects.filter(action_code="prospecting.discovery.completed").exists()
    assert AuditEvent.objects.filter(action_code="prospect.added").exists()
    assert InvitationCampaign.objects.count() == 0
    assert InvitationRecipient.objects.count() == 0


def test_entry_status_contact_selection_tags_and_removal_are_audited(
    user, organization, membership
):
    prospect_list = create_list(user, organization)
    company = make_company(organization, user)
    contact = Contact.objects.create(
        company=company, name="Taylor Estimator", email="taylor@example.com", is_active=True
    )
    entry = ProspectListEntry.objects.create(
        prospect_list=prospect_list, company=company, added_by=user
    )
    entry_url = f"/api/v1/organizations/{organization.slug}/prospecting/entries/{entry.pk}/"
    updated = client_for(user).patch(
        entry_url,
        {
            "status": "contact_ready",
            "primary_contact_id": contact.pk,
            "tags": ["Priority", "Toronto"],
            "notes": "Reviewed by estimator.",
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["status"] == "contact_ready"
    assert {item["name"] for item in updated.data["tags"]} == {"Priority", "Toronto"}
    assert AuditEvent.objects.filter(action_code="prospect.status_changed").exists()
    assert AuditEvent.objects.filter(action_code="prospect.contact_selected").exists()

    removed = client_for(user).delete(entry_url)
    assert removed.status_code == 200
    entry.refresh_from_db()
    assert entry.is_active is False
    assert entry.removed_by == user
    assert entry.removed_at is not None
    assert Company.objects.filter(pk=company.pk).exists()
    assert Contact.objects.filter(pk=contact.pk).exists()
    assert AuditEvent.objects.filter(action_code="prospect.removed").exists()

    listed = client_for(user).get(f"{lists_url(organization)}{prospect_list.pk}/")
    assert listed.status_code == 200
    assert listed.data["count"] == 0
    assert listed.data["results"] == []


def test_removal_preserves_campaign_history_and_manual_readd_reactivates(
    user, organization, membership
):
    prospect_list = create_list(user, organization)
    company = make_company(organization, user, display_name="Copperhead Mechanical")
    contact = Contact.objects.create(
        company=company,
        name="Copperhead Estimator",
        email="estimating@copperhead.example.com",
        is_active=True,
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
        name="Historical campaign",
        created_by=user,
    )
    recipient = ProspectCampaignRecipient.objects.create(
        campaign=campaign,
        prospect_entry=entry,
        company=company,
        contact=contact,
        company_name=company.display_name,
        contact_name=contact.name,
        normalized_email=contact.email,
        enrolled_by=user,
    )

    entry_url = f"/api/v1/organizations/{organization.slug}/prospecting/entries/{entry.pk}/"
    removed = client_for(user).delete(entry_url)
    assert removed.status_code == 200
    recipient.refresh_from_db()
    assert recipient.prospect_entry_id == entry.pk
    assert ProspectCampaignRecipient.objects.filter(pk=recipient.pk).exists()

    readded = client_for(user).post(
        f"{lists_url(organization)}{prospect_list.pk}/prospects/manual/",
        {
            "name": contact.name,
            "email": contact.email,
            "company": company.display_name,
        },
        format="json",
    )
    assert readded.status_code == 200
    entry.refresh_from_db()
    assert entry.is_active is True
    assert entry.removed_by is None
    assert entry.removed_at is None
    assert (
        Company.objects.filter(organization=organization, display_name=company.display_name).count()
        == 1
    )
    assert Contact.objects.filter(company=company, email=contact.email).count() == 1
    assert ProspectCampaignRecipient.objects.get(pk=recipient.pk).prospect_entry_id == entry.pk
