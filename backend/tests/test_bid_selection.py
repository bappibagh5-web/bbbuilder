"""M3-09 explicit human shortlist and selected-for-proposal workflow."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.outreach.bid_selection import (
    create_review,
    finalize_review,
    save_bidder_decision,
    save_outcome,
)
from apps.outreach.comparisons import (
    add_entry,
    create_comparison,
    evaluated_amount,
    mark_comparison_ready,
    save_adjustment,
)
from apps.outreach.models import (
    BidComparison,
    BidHumanReview,
    InvitationBatch,
    InvitationCampaign,
)

from .test_bid_comparisons import ready_revision
from .test_bid_comparisons import storage as comparison_storage
from .test_outreach import setup as outreach_setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(user, organization, membership):
    return outreach_setup.__wrapped__(user, organization, membership)


@pytest.fixture
def storage(monkeypatch):
    return comparison_storage.__wrapped__(monkeypatch)


def ready_comparison(setup, user, storage):
    first = ready_revision(setup, user, amount="176500.00")
    second = ready_revision(setup, user, second=True, amount="185000.00")
    comparison = create_comparison(
        project=first.project, scope_version=first.scope_version, actor=user
    )
    first_entry = add_entry(comparison=comparison, revision=first, actor=user)
    second_entry = add_entry(comparison=comparison, revision=second, actor=user)
    save_adjustment(
        entry=first_entry,
        actor=user,
        values={
            "direction": "add",
            "amount": "3000.00",
            "currency": "CAD",
            "category": "permit_fee",
            "description": "Permit leveling allowance",
        },
    )
    comparison = mark_comparison_ready(comparison=comparison, actor=user)
    return comparison, first_entry, second_entry, first, second


def decide(review, entry, user, state, note=""):
    decision = review.decisions.get(comparison_entry=entry)
    save_bidder_decision(decision=decision, actor=user, state=state, note=note)
    return BidHumanReview.objects.get(pk=review.pk)


def test_ready_comparison_creates_undecided_review_without_price_based_selection(
    setup, user, storage
):
    comparison, first_entry, _, first, _ = ready_comparison(setup, user, storage)
    original_base = first.base_bid
    original_adjustment = first_entry.adjustments.get().amount
    review, created = create_review(comparison=comparison, actor=user)

    assert created is True
    assert review.comparison_id == comparison.pk
    assert review.scope_version_id == comparison.scope_version_id
    assert review.outcome == ""
    assert review.selected_entry_id is None
    assert list(review.decisions.values_list("state", flat=True)) == ["undecided", "undecided"]
    assert evaluated_amount(first_entry) == Decimal("179500.00")
    first.refresh_from_db()
    first_entry.adjustments.get().refresh_from_db()
    assert first.base_bid == original_base
    assert first_entry.adjustments.get().amount == original_adjustment


def test_draft_comparison_cannot_start_human_review(setup, user, storage):
    revision = ready_revision(setup, user)
    comparison = create_comparison(
        project=revision.project, scope_version=revision.scope_version, actor=user
    )
    with pytest.raises(ValidationError, match="Ready for Human Review"):
        create_review(comparison=comparison, actor=user)


def test_decisions_are_exact_and_selected_entry_must_be_shortlisted(setup, user, storage):
    comparison, first_entry, second_entry, *_ = ready_comparison(setup, user, storage)
    review, _ = create_review(comparison=comparison, actor=user)
    decide(review, first_entry, user, "shortlisted", "Carry for final review")
    decide(review, second_entry, user, "not_shortlisted", "Scope conditions")
    review.refresh_from_db()

    with pytest.raises(ValidationError, match="Shortlisted"):
        save_outcome(
            review=review,
            actor=user,
            outcome="selected_for_proposal",
            selected_entry=second_entry,
            rationale="Human procurement judgment",
        )
    save_outcome(
        review=review,
        actor=user,
        outcome="selected_for_proposal",
        selected_entry=first_entry,
        rationale="Human procurement judgment",
    )
    review.refresh_from_db()
    assert review.selected_entry_id == first_entry.pk
    assert review.outcome == "selected_for_proposal"

    other = BidComparison.objects.create(
        organization=comparison.organization,
        project=comparison.project,
        scope_package=comparison.scope_package,
        scope_version=comparison.scope_version,
        sequence=2,
        created_by=user,
    )
    # An entry from another comparison can never be selected.
    with pytest.raises(ValidationError, match="exact comparison"):
        save_outcome(
            review=review,
            actor=user,
            outcome="selected_for_proposal",
            selected_entry=type(first_entry)(comparison=other),
            rationale="Invalid",
        )


def test_finalization_guards_and_finalized_history_is_immutable(setup, user, storage):
    comparison, first_entry, second_entry, *_ = ready_comparison(setup, user, storage)
    review, _ = create_review(comparison=comparison, actor=user)
    with pytest.raises(ValidationError, match="Review every bidder"):
        finalize_review(review=review, actor=user)
    decide(review, first_entry, user, "shortlisted")
    decide(review, second_entry, user, "not_shortlisted")
    review.refresh_from_db()
    save_outcome(
        review=review,
        actor=user,
        outcome="selected_for_proposal",
        selected_entry=first_entry,
        rationale="",
    )
    review.refresh_from_db()
    with pytest.raises(ValidationError, match="rationale"):
        finalize_review(review=review, actor=user)
    save_outcome(
        review=review,
        actor=user,
        outcome="selected_for_proposal",
        selected_entry=first_entry,
        rationale="Estimator selected this exact bid for proposal carry.",
    )
    review.refresh_from_db()
    finalized = finalize_review(review=review, actor=user)
    assert finalized.status == "finalized"
    with pytest.raises(ValidationError, match="immutable"):
        save_bidder_decision(
            decision=finalized.decisions.first(), actor=user, state="not_shortlisted"
        )
    with pytest.raises(ValidationError, match="immutable"):
        save_outcome(
            review=finalized,
            actor=user,
            outcome="no_acceptable_bid",
            selected_entry=None,
            rationale="Changed",
        )


def test_no_acceptable_bid_requires_null_selection_and_rationale(setup, user, storage):
    comparison, first_entry, second_entry, *_ = ready_comparison(setup, user, storage)
    review, _ = create_review(comparison=comparison, actor=user)
    decide(review, first_entry, user, "not_shortlisted")
    decide(review, second_entry, user, "not_shortlisted")
    review.refresh_from_db()
    with pytest.raises(ValidationError, match="cannot include"):
        save_outcome(
            review=review,
            actor=user,
            outcome="no_acceptable_bid",
            selected_entry=first_entry,
            rationale="Neither bid is acceptable",
        )
    save_outcome(
        review=review,
        actor=user,
        outcome="no_acceptable_bid",
        selected_entry=None,
        rationale="Neither bid is acceptable",
    )
    review.refresh_from_db()
    assert finalize_review(review=review, actor=user).selected_entry_id is None


def test_viewer_reads_but_cannot_create_or_mutate(setup, user, membership, storage):
    comparison, *_ = ready_comparison(setup, user, storage)
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse(
        "bid-human-review-list",
        kwargs={
            "organization_slug": comparison.organization.slug,
            "project_pk": comparison.project_id,
            "comparison_pk": comparison.pk,
        },
    )
    membership.role = Membership.Role.VIEWER
    membership.save()
    assert client.get(url).status_code == 200
    assert client.post(url, {}, format="json").status_code == 403
    assert BidHumanReview.objects.count() == 0


def test_project_isolation_and_no_outreach_or_award_side_effects(setup, user, storage):
    comparison, first_entry, second_entry, *_ = ready_comparison(setup, user, storage)
    campaign_count = InvitationCampaign.objects.count()
    batch_count = InvitationBatch.objects.count()
    review, _ = create_review(comparison=comparison, actor=user)
    decide(review, first_entry, user, "shortlisted")
    decide(review, second_entry, user, "not_shortlisted")
    review.refresh_from_db()
    save_outcome(
        review=review,
        actor=user,
        outcome="selected_for_proposal",
        selected_entry=first_entry,
        rationale="Explicit human choice",
    )
    review.refresh_from_db()
    finalize_review(review=review, actor=user)
    assert InvitationCampaign.objects.count() == campaign_count
    assert InvitationBatch.objects.count() == batch_count
    assert not hasattr(review, "award")

    other = Organization.objects.create(name="Other", slug="other")
    Membership.objects.create(
        organization=other, user=user, role=Membership.Role.ESTIMATOR_OPERATOR
    )
    client = APIClient()
    client.force_authenticate(user=user)
    cross_url = reverse(
        "bid-human-review-list",
        kwargs={
            "organization_slug": other.slug,
            "project_pk": comparison.project_id,
            "comparison_pk": comparison.pk,
        },
    )
    assert client.get(cross_url).status_code == 404
