from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.outreach.models import (
    BidComparison,
    BidHumanReview,
    InvitationRecipient,
    OutreachDeliveryAttempt,
    OutreachMessage,
)
from apps.outreach.services import (
    add_invitation_recipient,
    create_invitation_batch,
    create_invitation_campaign,
)
from apps.projects.models import Project
from apps.proposals.models import ProjectAward, ProposalVersion
from apps.proposals.services import create_estimate, create_proposal

from .test_outreach import setup as outreach_setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(user, organization, membership):
    return outreach_setup.__wrapped__(user, organization, membership)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def url(name, organization):
    return reverse(name, kwargs={"organization_slug": organization.slug})


def test_campaign_directory_is_bounded_real_and_viewer_readable(setup, user, membership):
    project, package, ready, candidate, contact = setup
    campaign = create_invitation_campaign(
        project=project, scope_package=package, scope_version=ready, actor=user
    )
    batch = create_invitation_batch(campaign=campaign, actor=user)
    recipient = add_invitation_recipient(
        batch=batch, candidate=candidate, contact=contact, actor=user
    )
    InvitationRecipient.objects.filter(pk=recipient.pk).update(
        current_status=InvitationRecipient.Status.RESPONDED,
        delivery_state="delivered",
        response_state="responded",
        qualification_state="qualified",
    )
    message = OutreachMessage.objects.create(
        recipient=recipient,
        sequence=1,
        kind=OutreachMessage.Kind.INVITATION,
        from_name="BB Builders",
        from_address="bids@example.invalid",
        to_address=recipient.email,
        subject="Invitation",
        body="Bounded test message",
        source_scope_version=ready,
        created_by=user,
    )
    OutreachDeliveryAttempt.objects.create(
        message=message,
        sequence=1,
        provider_key="fake",
        idempotency_key="directory-test",
        status=OutreachDeliveryAttempt.Status.SUCCEEDED,
        completed_at=timezone.now(),
    )
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=["role"])

    response = client_for(user).get(
        url("procurement-campaign-directory", project.organization),
        {"search": "Outreach", "page_size": 25},
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    item = response.data["results"][0]
    assert item["scope_version_id"] == ready.pk
    assert item["recipient_count"] == 1
    assert item["invited_count"] == 1
    assert item["delivered_count"] == 1
    assert item["responded_count"] == 1
    assert item["qualified_count"] == 1
    assert item["project_url"] == f"/projects/{project.pk}/outreach?campaign={campaign.pk}"
    assert "body" not in item


def test_comparison_directory_has_no_recommendation_or_price_inference(setup, user):
    project, package, ready, _, _ = setup
    comparison = BidComparison.objects.create(
        organization=project.organization,
        project=project,
        scope_package=package,
        scope_version=ready,
        sequence=1,
        status=BidComparison.Status.READY,
        created_by=user,
        reviewed_by=user,
        reviewed_at=timezone.now(),
    )
    BidHumanReview.objects.create(
        organization=project.organization,
        project=project,
        comparison=comparison,
        scope_package=package,
        scope_version=ready,
        sequence=1,
        status=BidHumanReview.Status.FINALIZED,
        outcome=BidHumanReview.Outcome.NO_ACCEPTABLE_BID,
        rationale="Explicit human outcome",
        created_by=user,
        finalized_by=user,
        finalized_at=timezone.now(),
    )
    response = client_for(user).get(url("procurement-comparison-directory", project.organization))
    assert response.status_code == 200
    item = response.data["results"][0]
    assert item["scope_version_id"] == ready.pk
    assert item["human_review_status"] == "finalized"
    assert item["selected_for_proposal"] is False
    assert item["project_url"].endswith(f"?comparison={comparison.pk}")
    assert "recommendation" not in item
    assert "price" not in item


def test_proposal_directory_uses_latest_client_facing_snapshot_only(organization, user, membership):
    project = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="PROP-1",
        name="Client Proposal",
        client_name="Example Client",
    )
    estimate, estimate_version = create_estimate(project=project, actor=user)
    proposal, proposal_version = create_proposal(
        estimate=estimate, estimate_version=estimate_version, actor=user
    )
    ProposalVersion.objects.filter(pk=proposal_version.pk).update(
        status=ProposalVersion.Status.FINALIZED,
        proposal_number="PROP-1-P0001",
        commercial_snapshot={
            "currency": "CAD",
            "total_amount": "125000.00",
            "contractor_base_bid": "90000.00",
            "internal_markup_rate": "0.10",
        },
        finalized_by=user,
        finalized_at=timezone.now(),
    )
    ProjectAward.objects.create(
        organization=organization,
        project=project,
        proposal_version=proposal_version,
        estimate_version=estimate_version,
        sequence=1,
        status=ProjectAward.Status.CONFIRMED,
        award_amount=Decimal("125000.00"),
        currency="CAD",
        award_date=timezone.localdate(),
        rationale="Explicit test award",
        created_by=user,
        confirmed_by=user,
        confirmed_at=timezone.now(),
    )
    response = client_for(user).get(
        url("client-proposal-directory", organization), {"search": "Example Client"}
    )
    assert response.status_code == 200
    assert response.data["summary"] == {
        "total": 1,
        "draft": 0,
        "finalized": 1,
        "awarded": 1,
    }
    item = response.data["results"][0]
    assert item["proposal_number"] == "PROP-1-P0001"
    assert item["estimate_version_id"] == estimate_version.pk
    assert item["currency"] == "CAD"
    assert item["proposed_amount"] == "125000.00"
    assert item["award_status"] == "confirmed"
    assert item["issue_date"] is None
    assert "contractor_base_bid" not in item
    assert "internal_markup_rate" not in item


@pytest.mark.parametrize(
    "route_name",
    [
        "procurement-campaign-directory",
        "procurement-comparison-directory",
        "client-proposal-directory",
    ],
)
def test_procurement_directories_require_membership_and_are_org_scoped(
    route_name, organization, user
):
    assert client_for(user).get(url(route_name, organization)).status_code == 403
    other = Organization.objects.create(name="Other Organization", slug="other")
    Membership.objects.create(user=user, organization=other, role=Membership.Role.VIEWER)
    response = client_for(user).get(url(route_name, other), {"page_size": 1})
    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["page_size"] == 1
