from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from apps.outreach.models import (
    BidHumanDecision,
    BidHumanReview,
    BidRevision,
)
from apps.projects.audit import record_event

from .calculations import money, persist_calculated_adjustments
from .models import (
    EstimateAllowance,
    EstimateAlternate,
    EstimateExclusion,
    EstimateFinancialAdjustment,
    EstimateLine,
    EstimateVersion,
)
from .services import _require_active_project, _require_operator


def _draft(version, actor):
    _require_operator(actor=actor, organization=version.estimate.organization)
    _require_active_project(version.estimate.project)
    if version.status != EstimateVersion.Status.DRAFT:
        raise ValidationError("Only a Draft Estimate version can be changed.")


def _next_sequence(model, version):
    return (
        model.objects.filter(estimate_version=version).aggregate(value=Max("sequence"))["value"]
        or 0
    ) + 1


def _decimal(value, field, *, required=True):
    if value in (None, ""):
        if required:
            raise ValidationError({field: "This amount is required."})
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError({field: "Enter a valid decimal value."}) from error
    if not result.is_finite() or result < 0:
        raise ValidationError({field: "Enter a non-negative finite value."})
    return money(result)


def _rate(value):
    if value in (None, ""):
        raise ValidationError({"percentage_rate": "This rate is required."})
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError({"percentage_rate": "Enter a valid decimal rate."}) from error
    if not result.is_finite() or result < 0:
        raise ValidationError({"percentage_rate": "Enter a non-negative finite rate."})
    return result.quantize(Decimal("0.000001"))


def _currency(value, *, required):
    value = (value or "").strip().upper()
    if required and (len(value) != 3 or not value.isalpha()):
        raise ValidationError({"currency": "Enter a three-letter currency code."})
    if value and (len(value) != 3 or not value.isalpha()):
        raise ValidationError({"currency": "Enter a three-letter currency code."})
    return value


def eligible_selected_reviews(project, estimate_version):
    assembled = set(
        EstimateLine.objects.filter(
            estimate_version=estimate_version,
            line_type=EstimateLine.LineType.SOURCE_BASE_BID,
        ).values_list("source_human_review_id", flat=True)
    )
    reviews = (
        BidHumanReview.objects.filter(
            project=project,
            status=BidHumanReview.Status.FINALIZED,
            outcome=BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL,
            selected_entry__isnull=False,
        )
        .select_related(
            "selected_entry__revision",
            "selected_entry__company",
            "scope_package",
            "scope_version",
        )
        .order_by("scope_package__trade_category", "id")
    )
    return [
        {
            "review_id": item.pk,
            "review_version": item.sequence,
            "entry_id": item.selected_entry_id,
            "bid_revision_id": item.selected_entry.revision_id,
            "scope_version_id": item.scope_version_id,
            "trade": item.scope_package.trade_category,
            "company_id": item.selected_entry.company_id,
            "company_name": item.selected_entry.company_name,
            "base_bid": str(item.selected_entry.revision.base_bid)
            if item.selected_entry.revision.base_bid is not None
            else None,
            "currency": item.selected_entry.revision.currency,
            "already_assembled": item.pk in assembled,
        }
        for item in reviews
    ]


@transaction.atomic
def assemble_selected_reviews(*, version, review_ids, actor):
    _draft(version, actor)
    version = (
        EstimateVersion.objects.select_for_update()
        .select_related("estimate__project", "estimate__organization")
        .get(pk=version.pk)
    )
    created = []
    for review_id in dict.fromkeys(review_ids):
        review = (
            BidHumanReview.objects.select_related(
                "comparison",
                "selected_entry__revision",
                "selected_entry__company",
                "scope_package",
                "scope_version",
            )
            .prefetch_related("selected_entry__adjustments")
            .filter(pk=review_id, project=version.estimate.project)
            .first()
        )
        if (
            review is None
            or review.status != BidHumanReview.Status.FINALIZED
            or review.outcome != BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL
            or not review.selected_entry_id
        ):
            raise ValidationError("Only a finalized Selected-for-Proposal review is eligible.")
        decision = review.decisions.filter(comparison_entry=review.selected_entry).first()
        if decision is None or decision.state != BidHumanDecision.State.SHORTLISTED:
            raise ValidationError("The exact selected comparison entry must be Shortlisted.")
        entry = review.selected_entry
        revision = entry.revision
        if (
            revision.status != BidRevision.Status.READY
            or revision.base_bid is None
            or revision.base_bid_review != BidRevision.ReviewState.CONFIRMED
            or revision.currency_review != BidRevision.ReviewState.CONFIRMED
            or not revision.currency
        ):
            raise ValidationError("The selected bid must have a confirmed Base Bid and currency.")
        if EstimateLine.objects.filter(
            estimate_version=version,
            line_type=EstimateLine.LineType.SOURCE_BASE_BID,
            source_human_review=review,
        ).exists():
            continue
        sequence = _next_sequence(EstimateLine, version)
        common = {
            "organization": version.estimate.organization,
            "project": version.estimate.project,
            "estimate_version": version,
            "currency": revision.currency,
            "included": True,
            "source_human_review": review,
            "source_comparison_entry": entry,
            "source_bid_revision": revision,
            "source_scope_version": review.scope_version,
            "source_company": entry.company,
            "company_name_snapshot": entry.company_name,
            "trade_snapshot": review.scope_package.trade_category,
            "created_by": actor,
        }
        base = EstimateLine.objects.create(
            **common,
            line_type=EstimateLine.LineType.SOURCE_BASE_BID,
            description=f"{entry.company_name} — {review.scope_package.trade_category} Base Bid",
            amount=revision.base_bid,
            direction=EstimateLine.Direction.ADD,
            sequence=sequence,
        )
        created.append(base)
        for offset, adjustment in enumerate(entry.adjustments.order_by("created_at", "id"), 1):
            if adjustment.currency != revision.currency:
                raise ValidationError("M3 leveling currency must match the selected Base Bid.")
            created.append(
                EstimateLine.objects.create(
                    **common,
                    line_type=EstimateLine.LineType.M3_LEVELING,
                    description=adjustment.description,
                    amount=adjustment.amount,
                    direction=adjustment.direction,
                    sequence=sequence + offset,
                    source_leveling_adjustment=adjustment,
                    source_category_snapshot=adjustment.get_category_display(),
                )
            )
        record_event(
            organization=version.estimate.organization,
            project=version.estimate.project,
            actor=actor,
            action_code="estimate.selected_bid_assembled",
            target=version,
            metadata={
                "review_id": review.pk,
                "comparison_entry_id": entry.pk,
                "bid_revision_id": revision.pk,
                "scope_version_id": review.scope_version_id,
                "line_count": 1 + entry.adjustments.count(),
            },
        )
    persist_calculated_adjustments(version)
    return created


def _validate_source_pair(version, revision, commercial_item):
    if commercial_item and not revision:
        revision = commercial_item.revision
    if commercial_item and commercial_item.revision_id != revision.pk:
        raise ValidationError("Commercial source must belong to the selected bid revision.")
    if revision and (
        revision.project_id != version.estimate.project_id
        or revision.scope_version_id
        not in version.source_lines.values_list("source_scope_version_id", flat=True)
    ):
        raise ValidationError("Commercial source must belong to an assembled selected bid.")
    return revision


def _commercial_values(*, version, data, actor, instance=None):
    _draft(version, actor)
    description = str(data.get("description", getattr(instance, "description", ""))).strip()
    if not description:
        raise ValidationError({"description": "Description is required."})
    return description


@transaction.atomic
def save_allowance(*, version, data, actor, instance=None):
    description = _commercial_values(version=version, data=data, actor=actor, instance=instance)
    amount = _decimal(
        data.get("amount", getattr(instance, "amount", None)), "amount", required=False
    )
    currency = _currency(
        data.get("currency", getattr(instance, "currency", "")), required=amount is not None
    )
    treatment = data.get("treatment", getattr(instance, "treatment", ""))
    if treatment not in EstimateAllowance.Treatment.values:
        raise ValidationError({"treatment": "Choose Included or Excluded."})
    if treatment == EstimateAllowance.Treatment.INCLUDED and amount is None:
        raise ValidationError({"amount": "An included allowance requires an amount."})
    obj = instance or EstimateAllowance(
        estimate_version=version,
        sequence=_next_sequence(EstimateAllowance, version),
        created_by=actor,
    )
    obj.description, obj.amount, obj.currency, obj.treatment, obj.updated_by = (
        description,
        amount,
        currency,
        treatment,
        actor,
    )
    obj.full_clean()
    obj.save()
    persist_calculated_adjustments(version)
    _audit_commercial(obj, actor, "allowance", instance is not None)
    return obj


@transaction.atomic
def save_alternate(*, version, data, actor, instance=None):
    description = _commercial_values(version=version, data=data, actor=actor, instance=instance)
    amount = _decimal(
        data.get("amount", getattr(instance, "amount", None)), "amount", required=False
    )
    currency = _currency(
        data.get("currency", getattr(instance, "currency", "")), required=amount is not None
    )
    direction = data.get("direction", getattr(instance, "direction", ""))
    if direction not in EstimateAlternate.Direction.values:
        raise ValidationError({"direction": "Choose Add or Deduct."})
    included = bool(
        data.get("included_in_estimate", getattr(instance, "included_in_estimate", False))
    )
    if included and amount is None:
        raise ValidationError({"amount": "An included alternate requires an amount."})
    obj = instance or EstimateAlternate(
        estimate_version=version,
        sequence=_next_sequence(EstimateAlternate, version),
        created_by=actor,
    )
    obj.description, obj.amount, obj.currency, obj.direction = (
        description,
        amount,
        currency,
        direction,
    )
    obj.included_in_estimate, obj.updated_by = included, actor
    obj.full_clean()
    obj.save()
    persist_calculated_adjustments(version)
    _audit_commercial(obj, actor, "alternate", instance is not None)
    return obj


@transaction.atomic
def save_exclusion(*, version, data, actor, instance=None):
    description = _commercial_values(version=version, data=data, actor=actor, instance=instance)
    obj = instance or EstimateExclusion(
        estimate_version=version,
        sequence=_next_sequence(EstimateExclusion, version),
        created_by=actor,
    )
    obj.description, obj.updated_by = description, actor
    obj.full_clean()
    obj.save()
    _audit_commercial(obj, actor, "exclusion", instance is not None)
    return obj


@transaction.atomic
def save_financial_adjustment(*, version, data, actor, instance=None):
    description = _commercial_values(version=version, data=data, actor=actor, instance=instance)
    category = data.get("category", getattr(instance, "category", ""))
    method = data.get("method", getattr(instance, "method", ""))
    basis = data.get("basis", getattr(instance, "basis", ""))
    if category not in EstimateFinancialAdjustment.Category.values:
        raise ValidationError({"category": "Choose a valid adjustment category."})
    if method not in EstimateFinancialAdjustment.Method.values:
        raise ValidationError({"method": "Choose Fixed amount or Percentage."})
    if basis not in EstimateFinancialAdjustment.Basis.values:
        raise ValidationError({"basis": "Choose an explicit calculation basis."})
    if (
        category == EstimateFinancialAdjustment.Category.TAX
        and basis != EstimateFinancialAdjustment.Basis.PRE_TAX_SUBTOTAL
    ):
        raise ValidationError({"basis": "Tax must use the explicit Pre-tax subtotal basis."})
    if (
        category != EstimateFinancialAdjustment.Category.TAX
        and basis == EstimateFinancialAdjustment.Basis.PRE_TAX_SUBTOTAL
    ):
        raise ValidationError(
            {"basis": "Pre-tax subtotal is reserved for explicit tax adjustments."}
        )
    fixed_value = data.get("fixed_amount", getattr(instance, "fixed_amount", None))
    rate_value = data.get("percentage_rate", getattr(instance, "percentage_rate", None))
    fixed = (
        _decimal(fixed_value, "fixed_amount")
        if method == EstimateFinancialAdjustment.Method.FIXED_AMOUNT
        else None
    )
    rate = _rate(rate_value) if method == EstimateFinancialAdjustment.Method.PERCENTAGE else None
    currency = _currency(data.get("currency", getattr(instance, "currency", "")), required=True)
    obj = instance or EstimateFinancialAdjustment(
        estimate_version=version,
        sequence=_next_sequence(EstimateFinancialAdjustment, version),
        created_by=actor,
    )
    obj.category, obj.description, obj.method, obj.basis = category, description, method, basis
    obj.fixed_amount, obj.percentage_rate, obj.currency, obj.updated_by = (
        fixed,
        rate,
        currency,
        actor,
    )
    obj.full_clean()
    obj.save()
    state = persist_calculated_adjustments(version)
    obj.refresh_from_db()
    _audit_commercial(obj, actor, "financial_adjustment", instance is not None)
    return obj, state


def _audit_commercial(obj, actor, label, changed):
    version = obj.estimate_version
    record_event(
        organization=version.estimate.organization,
        project=version.estimate.project,
        actor=actor,
        action_code=f"estimate.{label}_{'updated' if changed else 'created'}",
        target=obj,
        metadata={"estimate_version_id": version.pk, "sequence": obj.sequence},
    )
