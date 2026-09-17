"""Human-only M3-09 decisions over immutable Ready bid comparisons."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Prefetch
from django.utils import timezone

from apps.projects.audit import record_event

from .comparisons import evaluated_amount
from .models import (
    BidComparison,
    BidHumanDecision,
    BidHumanReview,
)


def _audit(review, actor, action, metadata=None, target=None):
    record_event(
        organization=review.organization,
        project=review.project,
        actor=actor,
        action_code=action,
        target=target or review,
        metadata=metadata or {},
    )


def review_queryset(comparison):
    decisions = (
        BidHumanDecision.objects.select_related("comparison_entry__revision", "decided_by")
        .prefetch_related("comparison_entry__adjustments")
        .order_by("comparison_entry__company_name", "id")
    )
    return (
        BidHumanReview.objects.filter(comparison=comparison)
        .select_related(
            "comparison",
            "scope_package",
            "scope_version",
            "selected_entry__revision",
            "created_by",
            "finalized_by",
            "supersedes",
        )
        .prefetch_related(Prefetch("decisions", queryset=decisions))
    )


def ensure_draft(review):
    if review.status != BidHumanReview.Status.DRAFT:
        raise ValidationError("Finalized human review is immutable. Create a successor.")


@transaction.atomic
def create_review(*, comparison, actor):
    comparison = BidComparison.objects.select_for_update().get(pk=comparison.pk)
    if comparison.status != BidComparison.Status.READY:
        raise ValidationError("Human review requires a comparison Ready for Human Review.")
    latest = (
        BidHumanReview.objects.filter(comparison=comparison).order_by("-sequence", "-id").first()
    )
    if latest and latest.status == BidHumanReview.Status.DRAFT:
        return latest, False
    sequence = (
        BidHumanReview.objects.filter(comparison=comparison).aggregate(Max("sequence"))[
            "sequence__max"
        ]
        or 0
    ) + 1
    review = BidHumanReview.objects.create(
        organization=comparison.organization,
        project=comparison.project,
        comparison=comparison,
        scope_package=comparison.scope_package,
        scope_version=comparison.scope_version,
        supersedes=latest,
        sequence=sequence,
        created_by=actor,
    )
    BidHumanDecision.objects.bulk_create(
        [
            BidHumanDecision(review=review, comparison_entry=entry)
            for entry in comparison.entries.all()
        ]
    )
    _audit(
        review,
        actor,
        "bid_human_review.created",
        {
            "comparison_id": comparison.pk,
            "sequence": sequence,
            "entry_count": comparison.entries.count(),
        },
    )
    return review, True


@transaction.atomic
def save_bidder_decision(*, decision, actor, state, note=""):
    review = BidHumanReview.objects.select_for_update().get(pk=decision.review_id)
    ensure_draft(review)
    decision = BidHumanDecision.objects.select_related("comparison_entry").get(
        pk=decision.pk, review=review
    )
    previous = decision.state
    decision.state = state
    decision.note = note.strip()
    if state == BidHumanDecision.State.UNDECIDED:
        decision.decided_by = None
        decision.decided_at = None
    else:
        decision.decided_by = actor
        decision.decided_at = timezone.now()
    decision.save()
    if (
        review.selected_entry_id == decision.comparison_entry_id
        and state != BidHumanDecision.State.SHORTLISTED
    ):
        review.selected_entry = None
        if review.outcome == BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL:
            review.outcome = ""
        review.save()
    _audit(
        review,
        actor,
        "bid_human_review.bidder_decided",
        {
            "decision_id": decision.pk,
            "entry_id": decision.comparison_entry_id,
            "previous_state": previous,
            "state": state,
        },
        decision,
    )
    return review


@transaction.atomic
def save_outcome(*, review, actor, outcome, selected_entry=None, rationale=""):
    review = BidHumanReview.objects.select_for_update().get(pk=review.pk)
    ensure_draft(review)
    if outcome == BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL:
        if not selected_entry or selected_entry.comparison_id != review.comparison_id:
            raise ValidationError("Choose one bid from this exact comparison.")
        decision = review.decisions.filter(comparison_entry=selected_entry).first()
        if not decision or decision.state != BidHumanDecision.State.SHORTLISTED:
            raise ValidationError("Selected for Proposal must be a Shortlisted bid.")
        review.selected_entry = selected_entry
    elif outcome == BidHumanReview.Outcome.NO_ACCEPTABLE_BID:
        if selected_entry is not None:
            raise ValidationError("No Acceptable Bid cannot include a selected bid.")
        review.selected_entry = None
    elif outcome:
        raise ValidationError("Choose a supported human review outcome.")
    else:
        review.selected_entry = None
    previous_outcome = review.outcome
    review.outcome = outcome
    review.rationale = rationale.strip()
    review.save()
    _audit(
        review,
        actor,
        "bid_human_review.outcome_changed",
        {
            "previous_outcome": previous_outcome,
            "outcome": outcome,
            "selected_entry_id": review.selected_entry_id,
        },
    )
    return review


@transaction.atomic
def finalize_review(*, review, actor):
    review = BidHumanReview.objects.select_for_update().get(pk=review.pk)
    ensure_draft(review)
    decisions = list(review.decisions.select_related("comparison_entry"))
    if not decisions or any(item.state == BidHumanDecision.State.UNDECIDED for item in decisions):
        raise ValidationError("Review every bidder before finalizing.")
    if not review.rationale.strip():
        raise ValidationError("Final decision rationale is required.")
    if review.outcome == BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL:
        selected = next(
            (item for item in decisions if item.comparison_entry_id == review.selected_entry_id),
            None,
        )
        if not selected or selected.state != BidHumanDecision.State.SHORTLISTED:
            raise ValidationError("Selected for Proposal must be a Shortlisted bid.")
    elif review.outcome == BidHumanReview.Outcome.NO_ACCEPTABLE_BID:
        if review.selected_entry_id:
            raise ValidationError("No Acceptable Bid cannot include a selected bid.")
    else:
        raise ValidationError("Choose an overall human decision before finalizing.")
    review.status = BidHumanReview.Status.FINALIZED
    review.finalized_by = actor
    review.finalized_at = timezone.now()
    review.save()
    _audit(
        review,
        actor,
        "bid_human_review.finalized",
        {
            "outcome": review.outcome,
            "selected_entry_id": review.selected_entry_id,
            "decision_count": len(decisions),
        },
    )
    return review


def blockers(review):
    values = []
    decisions = list(review.decisions.all())
    if any(item.state == BidHumanDecision.State.UNDECIDED for item in decisions):
        values.append("Review every bidder")
    if not review.outcome:
        values.append("Choose an overall outcome")
    if not review.rationale.strip():
        values.append("Add final decision rationale")
    if review.outcome == BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL:
        selected = next(
            (item for item in decisions if item.comparison_entry_id == review.selected_entry_id),
            None,
        )
        if not selected or selected.state != BidHumanDecision.State.SHORTLISTED:
            values.append("Select one Shortlisted bid")
    if review.outcome == BidHumanReview.Outcome.NO_ACCEPTABLE_BID and review.selected_entry_id:
        values.append("Remove the selected bid")
    return values


def review_data(review):
    decisions = list(review.decisions.all())
    finalized_by_name = None
    if review.finalized_by_id:
        finalized_by_name = (
            review.finalized_by.get_full_name() or review.finalized_by.get_username()
        )
    return {
        "id": review.pk,
        "sequence": review.sequence,
        "status": review.status,
        "comparison_id": review.comparison_id,
        "scope_package_id": review.scope_package_id,
        "scope_version_id": review.scope_version_id,
        "supersedes_id": review.supersedes_id,
        "outcome": review.outcome,
        "selected_entry_id": review.selected_entry_id,
        "selected_company_name": review.selected_entry.company_name
        if review.selected_entry_id
        else None,
        "rationale": review.rationale,
        "created_by_id": review.created_by_id,
        "created_at": review.created_at,
        "finalized_by_id": review.finalized_by_id,
        "finalized_by_name": finalized_by_name,
        "finalized_at": review.finalized_at,
        "blockers": blockers(review) if review.status == BidHumanReview.Status.DRAFT else [],
        "decisions": [
            {
                "id": item.pk,
                "entry_id": item.comparison_entry_id,
                "revision_id": item.comparison_entry.revision_id,
                "company_name": item.comparison_entry.company_name,
                "state": item.state,
                "note": item.note,
                "decided_by_id": item.decided_by_id,
                "decided_at": item.decided_at,
                "source_base_bid": (
                    str(item.comparison_entry.revision.base_bid)
                    if item.comparison_entry.revision.base_bid is not None
                    else None
                ),
                "currency": item.comparison_entry.revision.currency,
                "evaluated_amount": (
                    str(evaluated_amount(item.comparison_entry))
                    if evaluated_amount(item.comparison_entry) is not None
                    else None
                ),
            }
            for item in decisions
        ],
    }
