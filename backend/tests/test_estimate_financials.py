from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.outreach.bid_selection import (
    create_review,
    finalize_review,
    save_bidder_decision,
    save_outcome,
)
from apps.projects.models import AuditEvent
from apps.proposals.calculations import calculate_estimate_version
from apps.proposals.commercial import (
    assemble_selected_reviews,
    save_allowance,
    save_alternate,
    save_exclusion,
    save_financial_adjustment,
)
from apps.proposals.models import (
    EstimateAllowance,
    EstimateAlternate,
    EstimateExclusion,
    EstimateFinancialAdjustment,
    EstimateLine,
)
from apps.proposals.services import create_estimate, create_estimate_version

from .test_bid_comparisons import storage as comparison_storage
from .test_bid_selection import ready_comparison
from .test_outreach import setup as outreach_setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(user, organization, membership):
    return outreach_setup.__wrapped__(user, organization, membership)


@pytest.fixture
def storage(monkeypatch):
    return comparison_storage.__wrapped__(monkeypatch)


def finalized_selection(setup, user, storage):
    comparison, selected, rejected, revision, _ = ready_comparison(setup, user, storage)
    review, _ = create_review(comparison=comparison, actor=user)
    save_bidder_decision(
        decision=review.decisions.get(comparison_entry=selected),
        actor=user,
        state="shortlisted",
        note="Selected by estimator",
    )
    save_bidder_decision(
        decision=review.decisions.get(comparison_entry=rejected),
        actor=user,
        state="not_shortlisted",
        note="Not selected",
    )
    review.refresh_from_db()
    save_outcome(
        review=review,
        actor=user,
        outcome="selected_for_proposal",
        selected_entry=selected,
        rationale="Explicit human procurement selection.",
    )
    review.refresh_from_db()
    return finalize_review(review=review, actor=user), selected, revision


def estimate_version(project, user):
    return create_estimate(project=project, actor=user)[1]


def test_selected_bid_assembly_preserves_base_and_leveling_separately_and_is_idempotent(
    setup, user, storage
):
    review, entry, revision = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    original_base = revision.base_bid
    source_adjustment = entry.adjustments.get()
    original_adjustment = source_adjustment.amount

    created = assemble_selected_reviews(version=version, review_ids=[review.pk], actor=user)
    repeated = assemble_selected_reviews(version=version, review_ids=[review.pk], actor=user)

    assert len(created) == 2
    assert repeated == []
    base, leveling = version.source_lines.order_by("sequence")
    assert base.line_type == EstimateLine.LineType.SOURCE_BASE_BID
    assert base.amount == Decimal("176500.00")
    assert base.source_bid_revision_id == revision.pk
    assert base.source_human_review_id == review.pk
    assert base.source_scope_version_id == review.scope_version_id
    assert leveling.line_type == EstimateLine.LineType.M3_LEVELING
    assert leveling.amount == Decimal("3000.00")
    assert leveling.source_leveling_adjustment_id == source_adjustment.pk
    state = calculate_estimate_version(version)
    assert state.direct_source_cost == Decimal("176500.00")
    assert state.leveling_adjustments == Decimal("3000.00")
    assert state.normalized_direct_cost == Decimal("179500.00")
    revision.refresh_from_db()
    source_adjustment.refresh_from_db()
    assert revision.base_bid == original_base
    assert source_adjustment.amount == original_adjustment


def test_historical_estimate_version_does_not_follow_later_versions_or_source_labels(
    setup, user, storage
):
    review, _entry, _revision = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    assemble_selected_reviews(version=version, review_ids=[review.pk], actor=user)
    original_snapshots = list(
        version.source_lines.order_by("sequence").values_list(
            "company_name_snapshot", "trade_snapshot", "amount"
        )
    )

    later = create_estimate_version(estimate=version.estimate, actor=user)
    review.selected_entry.company.display_name = "A later display-name change"
    review.selected_entry.company.save(update_fields=["display_name"])

    assert (
        list(
            version.source_lines.order_by("sequence").values_list(
                "company_name_snapshot", "trade_snapshot", "amount"
            )
        )
        == original_snapshots
    )
    assert later.source_lines.count() == 0


def test_commercial_items_without_selected_bid_do_not_fabricate_zero_total(setup, user, storage):
    review, *_ = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    save_allowance(
        version=version,
        actor=user,
        data={
            "description": "Explicitly excluded allowance",
            "amount": "500",
            "currency": "CAD",
            "treatment": "excluded",
        },
    )

    state = calculate_estimate_version(version)
    assert state.calculated_estimate_amount is None
    assert state.direct_source_cost is None
    assert "Assemble at least one selected bid" in state.blockers[0]


def test_only_finalized_selected_review_is_eligible(setup, user, storage):
    comparison, selected, rejected, *_ = ready_comparison(setup, user, storage)
    version = estimate_version(comparison.project, user)
    draft, _ = create_review(comparison=comparison, actor=user)
    with pytest.raises(ValidationError, match="finalized Selected-for-Proposal"):
        assemble_selected_reviews(version=version, review_ids=[draft.pk], actor=user)

    save_bidder_decision(
        decision=draft.decisions.get(comparison_entry=selected),
        actor=user,
        state="not_shortlisted",
    )
    save_bidder_decision(
        decision=draft.decisions.get(comparison_entry=rejected),
        actor=user,
        state="not_shortlisted",
    )
    draft.refresh_from_db()
    save_outcome(
        review=draft,
        actor=user,
        outcome="no_acceptable_bid",
        selected_entry=None,
        rationale="No acceptable bid.",
    )
    draft.refresh_from_db()
    finalized = finalize_review(review=draft, actor=user)
    with pytest.raises(ValidationError, match="finalized Selected-for-Proposal"):
        assemble_selected_reviews(version=version, review_ids=[finalized.pk], actor=user)
    assert version.source_lines.count() == 0


def test_deterministic_calculation_order_allowances_alternates_adjustments_and_tax(
    setup, user, storage
):
    review, *_ = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    assemble_selected_reviews(version=version, review_ids=[review.pk], actor=user)
    save_allowance(
        version=version,
        actor=user,
        data={
            "description": "Included allowance",
            "amount": "1000",
            "currency": "CAD",
            "treatment": "included",
        },
    )
    save_allowance(
        version=version,
        actor=user,
        data={
            "description": "Excluded allowance",
            "amount": "500",
            "currency": "CAD",
            "treatment": "excluded",
        },
    )
    save_alternate(
        version=version,
        actor=user,
        data={
            "description": "Included add",
            "amount": "2000",
            "currency": "CAD",
            "direction": "add",
            "included_in_estimate": True,
        },
    )
    save_alternate(
        version=version,
        actor=user,
        data={
            "description": "Included deduct",
            "amount": "500",
            "currency": "CAD",
            "direction": "deduct",
            "included_in_estimate": True,
        },
    )
    save_alternate(
        version=version,
        actor=user,
        data={
            "description": "Optional add",
            "amount": "999",
            "currency": "CAD",
            "direction": "add",
            "included_in_estimate": False,
        },
    )
    save_exclusion(version=version, actor=user, data={"description": "By others"})
    save_financial_adjustment(
        version=version,
        actor=user,
        data={
            "category": "overhead",
            "description": "Fixed overhead",
            "method": "fixed_amount",
            "basis": "running_subtotal",
            "fixed_amount": "1000",
            "currency": "CAD",
        },
    )
    save_financial_adjustment(
        version=version,
        actor=user,
        data={
            "category": "profit",
            "description": "Profit markup",
            "method": "percentage",
            "basis": "running_subtotal",
            "percentage_rate": "10",
            "currency": "CAD",
        },
    )
    save_financial_adjustment(
        version=version,
        actor=user,
        data={
            "category": "tax",
            "description": "Explicit tax",
            "method": "percentage",
            "basis": "pre_tax_subtotal",
            "percentage_rate": "13",
            "currency": "CAD",
        },
    )
    state = calculate_estimate_version(version)
    assert state.allowance_impact == Decimal("1000.00")
    assert state.included_alternate_impact == Decimal("1500.00")
    assert state.commercial_adjustments == Decimal("19300.00")
    assert state.pre_tax_subtotal == Decimal("201300.00")
    assert state.tax_impact == Decimal("26169.00")
    assert state.calculated_estimate_amount == Decimal("227469.00")
    assert EstimateExclusion.objects.filter(estimate_version=version).count() == 1


def test_percentage_rounding_is_half_up_without_float_drift(setup, user, storage):
    review, *_ = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    assemble_selected_reviews(version=version, review_ids=[review.pk], actor=user)
    adjustment, _ = save_financial_adjustment(
        version=version,
        actor=user,
        data={
            "category": "markup",
            "description": "Fractional-cent rate",
            "method": "percentage",
            "basis": "direct_cost",
            "percentage_rate": "0.333333",
            "currency": "CAD",
        },
    )
    assert adjustment.percentage_rate == Decimal("0.333333")
    assert adjustment.calculated_amount == Decimal("598.33")
    assert calculate_estimate_version(version).calculated_estimate_amount == Decimal("180098.33")


def test_unknown_and_mixed_currency_never_default_or_convert(setup, user, storage):
    review, *_ = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    assemble_selected_reviews(version=version, review_ids=[review.pk], actor=user)
    save_allowance(
        version=version,
        actor=user,
        data={
            "description": "USD allowance",
            "amount": "100",
            "currency": "USD",
            "treatment": "included",
        },
    )
    state = calculate_estimate_version(version)
    assert state.currency is None
    assert state.calculated_estimate_amount is None
    assert "Mixed currencies" in state.blockers[0]
    with pytest.raises(ValidationError, match="currency"):
        save_alternate(
            version=version,
            actor=user,
            data={
                "description": "Unknown currency",
                "amount": "10",
                "direction": "add",
                "included_in_estimate": True,
            },
        )


def test_source_commercial_terms_are_not_promoted_without_human_action(setup, user, storage):
    review, *_ = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    assemble_selected_reviews(version=version, review_ids=[review.pk], actor=user)
    assert EstimateAllowance.objects.filter(estimate_version=version).count() == 0
    assert EstimateAlternate.objects.filter(estimate_version=version).count() == 0
    assert EstimateExclusion.objects.filter(estimate_version=version).count() == 0
    assert EstimateFinancialAdjustment.objects.filter(estimate_version=version).count() == 0
    assert calculate_estimate_version(version).tax_impact is None


def test_viewer_cannot_assemble_or_add_commercial_items(setup, user, membership, storage):
    review, *_ = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=["role"])
    client = APIClient()
    client.force_authenticate(user=user)
    kwargs = {
        "organization_slug": review.organization.slug,
        "project_pk": review.project_id,
        "version_pk": version.pk,
    }
    assemble_url = reverse("estimate-version-assemble", kwargs=kwargs)
    assert client.post(assemble_url, {"review_ids": [review.pk]}, format="json").status_code == 403
    item_url = reverse("estimate-commercial-create", kwargs={**kwargs, "kind": "allowances"})
    assert (
        client.post(
            item_url,
            {"description": "No", "amount": "1", "currency": "CAD", "treatment": "included"},
            format="json",
        ).status_code
        == 403
    )
    assert version.source_lines.count() == 0


def test_draft_commercial_patch_keeps_identity_audits_and_recalculates(setup, user, storage):
    review, *_ = finalized_selection(setup, user, storage)
    version = estimate_version(review.project, user)
    assemble_selected_reviews(version=version, review_ids=[review.pk], actor=user)
    allowance = save_allowance(
        version=version,
        actor=user,
        data={
            "description": "Controls allowance",
            "amount": "5000",
            "currency": "CAD",
            "treatment": "included",
        },
    )
    alternate = save_alternate(
        version=version,
        actor=user,
        data={
            "description": "Controls upgrade",
            "amount": "4500",
            "currency": "CAD",
            "direction": "add",
            "included_in_estimate": False,
        },
    )
    exclusion = save_exclusion(
        version=version, actor=user, data={"description": "Electrical work by others"}
    )
    adjustment, _ = save_financial_adjustment(
        version=version,
        actor=user,
        data={
            "category": "overhead",
            "description": "Explicit overhead",
            "method": "fixed_amount",
            "basis": "running_subtotal",
            "fixed_amount": "1000",
            "currency": "CAD",
        },
    )
    client = APIClient()
    client.force_authenticate(user=user)
    common = {
        "organization_slug": review.organization.slug,
        "project_pk": review.project_id,
        "version_pk": version.pk,
    }
    patches = [
        (
            "allowances",
            allowance.pk,
            {"amount": "6000.00"},
            "estimate.allowance_updated",
        ),
        (
            "alternates",
            alternate.pk,
            {"included_in_estimate": True},
            "estimate.alternate_updated",
        ),
        (
            "exclusions",
            exclusion.pk,
            {"description": "Electrical disconnect by others"},
            "estimate.exclusion_updated",
        ),
        (
            "adjustments",
            adjustment.pk,
            {"fixed_amount": "1500.00"},
            "estimate.financial_adjustment_updated",
        ),
    ]
    for kind, item_pk, payload, action_code in patches:
        url = reverse(
            "estimate-commercial-detail",
            kwargs={**common, "kind": kind, "item_pk": item_pk},
        )
        response = client.patch(url, payload, format="json")
        assert response.status_code == 200
        assert AuditEvent.objects.filter(project=review.project, action_code=action_code).exists()

    allowance.refresh_from_db()
    alternate.refresh_from_db()
    exclusion.refresh_from_db()
    adjustment.refresh_from_db()
    assert allowance.amount == Decimal("6000.00")
    assert alternate.included_in_estimate is True
    assert exclusion.description == "Electrical disconnect by others"
    assert adjustment.fixed_amount == Decimal("1500.00")
    assert version.allowances.count() == 1
    assert version.alternates.count() == 1
    assert version.exclusions.count() == 1
    assert version.financial_adjustments.count() == 1
    assert calculate_estimate_version(version).calculated_estimate_amount == Decimal("191500.00")
