from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.projects.models import Project
from apps.proposals.awards import (
    confirm_project_award,
    confirm_trade_award,
    create_project_award,
    create_trade_award,
    transition_project_to_awarded,
)
from apps.proposals.lifecycle import finalize_proposal
from apps.proposals.models import (
    AwardedProjectHandoffSnapshot,
    ProjectAward,
    TradeAward,
)

from .test_bid_comparisons import storage as comparison_storage
from .test_outreach import setup as outreach_setup
from .test_proposal_finalization import prepared

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(user, organization, membership):
    return outreach_setup.__wrapped__(user, organization, membership)


@pytest.fixture
def storage(monkeypatch):
    return comparison_storage.__wrapped__(monkeypatch)


def finalized_project(setup, user, storage):
    project, _, estimate, _, proposal = prepared(setup, user, storage)
    finalize_proposal(version=proposal, actor=user)
    return project, estimate, proposal


def project_award_data(proposal, amount="193725.00"):
    return {
        "award_amount": amount,
        "currency": "CAD",
        "award_date": date(2026, 9, 20),
        "rationale": "Controlled client acceptance recorded by the estimator.",
        "client_reference": "CLIENT-PO-TEST",
    }


def test_project_award_requires_finalized_proposal_and_explicit_commercial_input(
    setup, user, storage
):
    project, _, _, _, proposal = prepared(setup, user, storage)
    with pytest.raises(ValidationError, match="Finalized proposal"):
        create_project_award(
            project=project,
            proposal_version=proposal,
            actor=user,
            data=project_award_data(proposal),
        )
    finalize_proposal(version=proposal, actor=user)
    invalid = project_award_data(proposal, "190000.00")
    invalid["rationale"] = "short"
    with pytest.raises(ValidationError, match="differs"):
        create_project_award(project=project, proposal_version=proposal, actor=user, data=invalid)
    assert ProjectAward.objects.count() == 0


def test_project_award_confirmation_is_explicit_immutable_and_does_not_change_sources(
    setup, user, storage
):
    project, estimate, proposal = finalized_project(setup, user, storage)
    award = create_project_award(
        project=project,
        proposal_version=proposal,
        actor=user,
        data=project_award_data(proposal),
    )
    assert award.status == ProjectAward.Status.DRAFT
    assert project.status != Project.Status.AWARDED
    confirmed, created = confirm_project_award(award=award, actor=user)
    assert created is True and confirmed.status == ProjectAward.Status.CONFIRMED
    proposal.refresh_from_db()
    estimate.refresh_from_db()
    assert proposal.status == "finalized" and estimate.status == "frozen"
    confirmed.rationale = "Changed"
    with pytest.raises(ValidationError, match="immutable"):
        confirmed.save()


def test_trade_award_freezes_selected_bid_values_not_internal_leveling(setup, user, storage):
    project, _, _ = finalized_project(setup, user, storage)
    review = project.bidhumanreview_set.get(sequence=1)
    award = create_trade_award(
        project=project,
        review=review,
        actor=user,
        data={
            "award_amount": "177000.00",
            "currency": "CAD",
            "award_date": date(2026, 9, 20),
            "rationale": "Explicit controlled subcontractor award amount.",
        },
    )
    assert award.quoted_base_bid == Decimal("176500.00")
    assert award.evaluated_amount == Decimal("179500.00")
    assert award.award_amount == Decimal("177000.00")
    confirmed, created = confirm_trade_award(award=award, actor=user)
    assert created is True and confirmed.status == TradeAward.Status.CONFIRMED
    review.refresh_from_db()
    assert review.status == "finalized" and review.selected_entry.revision.base_bid == Decimal(
        "176500.00"
    )
    confirmed.award_amount = Decimal("1.00")
    with pytest.raises(ValidationError, match="immutable"):
        confirmed.save()


def test_awarded_transition_requires_confirmed_project_award_and_versions_handoff(
    setup, user, storage
):
    project, _, proposal = finalized_project(setup, user, storage)
    award = create_project_award(
        project=project,
        proposal_version=proposal,
        actor=user,
        data=project_award_data(proposal),
    )
    with pytest.raises(ValidationError, match="Confirm"):
        transition_project_to_awarded(award=award, actor=user)
    confirm_project_award(award=award, actor=user)
    snapshot, created = transition_project_to_awarded(award=award, actor=user)
    repeated, created_again = transition_project_to_awarded(award=award, actor=user)
    project.refresh_from_db()
    assert created is True and created_again is False and repeated.pk == snapshot.pk
    assert project.status == Project.Status.AWARDED
    assert snapshot.snapshot["project_award"]["proposal_version_id"] == proposal.pk
    assert snapshot.snapshot["project_award"]["estimate_version_id"] == proposal.estimate_version_id
    assert AwardedProjectHandoffSnapshot.objects.count() == 1
    snapshot.snapshot = {}
    with pytest.raises(ValidationError):
        snapshot.save()


def test_viewer_cannot_create_award_and_cross_project_source_is_blocked(
    setup, user, membership, storage
):
    project, _, proposal = finalized_project(setup, user, storage)
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=["role"])
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse(
        "project-award-create",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    payload = project_award_data(proposal)
    payload["proposal_version_id"] = proposal.pk
    assert client.post(url, payload, format="json").status_code == 403
    assert ProjectAward.objects.count() == 0
