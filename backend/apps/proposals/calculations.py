from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Prefetch

from .models import (
    EstimateAllowance,
    EstimateAlternate,
    EstimateFinancialAdjustment,
    EstimateLine,
    EstimateVersion,
)

MONEY_QUANTUM = Decimal("0.01")
PERCENT_DIVISOR = Decimal("100")
ROUNDING_MODE = ROUND_HALF_UP


def money(value):
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUNDING_MODE)


def signed(amount, direction):
    value = money(amount)
    return -value if direction == EstimateLine.Direction.DEDUCT else value


def calculation_queryset():
    return EstimateVersion.objects.prefetch_related(
        Prefetch("source_lines", queryset=EstimateLine.objects.order_by("sequence", "id")),
        Prefetch("allowances", queryset=EstimateAllowance.objects.order_by("sequence", "id")),
        Prefetch("alternates", queryset=EstimateAlternate.objects.order_by("sequence", "id")),
        Prefetch(
            "financial_adjustments",
            queryset=EstimateFinancialAdjustment.objects.order_by("sequence", "id"),
        ),
    )


def _money_text(value):
    return None if value is None else f"{money(value):.2f}"


@dataclass(frozen=True)
class CalculationState:
    currency: str | None
    direct_source_cost: Decimal | None
    leveling_adjustments: Decimal | None
    normalized_direct_cost: Decimal | None
    allowance_impact: Decimal | None
    included_alternate_impact: Decimal | None
    commercial_adjustments: Decimal | None
    pre_tax_subtotal: Decimal | None
    tax_impact: Decimal | None
    calculated_estimate_amount: Decimal | None
    blockers: tuple[str, ...]
    adjustment_breakdown: tuple[dict, ...]

    def as_dict(self):
        return {
            "currency": self.currency,
            "direct_source_cost": _money_text(self.direct_source_cost),
            "leveling_adjustments": _money_text(self.leveling_adjustments),
            "normalized_direct_cost": _money_text(self.normalized_direct_cost),
            "allowance_impact": _money_text(self.allowance_impact),
            "included_alternate_impact": _money_text(self.included_alternate_impact),
            "commercial_adjustments": _money_text(self.commercial_adjustments),
            "pre_tax_subtotal": _money_text(self.pre_tax_subtotal),
            "tax_impact": _money_text(self.tax_impact),
            "calculated_estimate_amount": _money_text(self.calculated_estimate_amount),
            "blockers": list(self.blockers),
            "adjustment_breakdown": list(self.adjustment_breakdown),
            "rounding": "ROUND_HALF_UP to 0.01 after each calculated adjustment",
        }


def calculate_estimate_version(version):
    lines = list(version.source_lines.all())
    allowances = list(version.allowances.all())
    alternates = list(version.alternates.all())
    adjustments = list(version.financial_adjustments.all())
    blockers = []
    currencies = {
        item.currency
        for item in [*lines, *allowances, *alternates, *adjustments]
        if getattr(item, "currency", "")
        and (
            not isinstance(item, EstimateAllowance)
            or item.treatment == EstimateAllowance.Treatment.INCLUDED
        )
        and (not isinstance(item, EstimateAlternate) or item.included_in_estimate)
    }
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    if len(currencies) > 1:
        blockers.append("Mixed currencies cannot be calculated without explicit FX treatment.")
    for allowance in allowances:
        if allowance.treatment == EstimateAllowance.Treatment.INCLUDED and allowance.amount is None:
            blockers.append(f"Included allowance '{allowance.description}' needs an amount.")
    for alternate in alternates:
        if alternate.included_in_estimate and alternate.amount is None:
            blockers.append(f"Included alternate '{alternate.description}' needs an amount.")
    if not lines:
        if allowances or alternates or adjustments:
            blockers.append("Assemble at least one selected bid before calculating the estimate.")
        return CalculationState(
            currency=currency,
            direct_source_cost=None,
            leveling_adjustments=None,
            normalized_direct_cost=None,
            allowance_impact=None,
            included_alternate_impact=None,
            commercial_adjustments=None,
            pre_tax_subtotal=None,
            tax_impact=None,
            calculated_estimate_amount=None,
            blockers=tuple(blockers),
            adjustment_breakdown=(),
        )
    if blockers:
        return CalculationState(
            currency=currency,
            direct_source_cost=None,
            leveling_adjustments=None,
            normalized_direct_cost=None,
            allowance_impact=None,
            included_alternate_impact=None,
            commercial_adjustments=None,
            pre_tax_subtotal=None,
            tax_impact=None,
            calculated_estimate_amount=None,
            blockers=tuple(blockers),
            adjustment_breakdown=(),
        )

    direct = money(
        sum(
            (
                item.amount
                for item in lines
                if item.line_type == EstimateLine.LineType.SOURCE_BASE_BID
            ),
            Decimal("0"),
        )
    )
    leveling = money(
        sum(
            (
                signed(item.amount, item.direction)
                for item in lines
                if item.line_type == EstimateLine.LineType.M3_LEVELING
            ),
            Decimal("0"),
        )
    )
    normalized = money(direct + leveling)
    included_allowances = [
        item
        for item in allowances
        if item.treatment == EstimateAllowance.Treatment.INCLUDED and item.amount is not None
    ]
    included_alternates = [
        item for item in alternates if item.included_in_estimate and item.amount is not None
    ]
    allowance_impact = money(sum((item.amount for item in included_allowances), Decimal("0")))
    alternate_impact = money(
        sum((signed(item.amount, item.direction) for item in included_alternates), Decimal("0"))
    )
    running = money(normalized + allowance_impact + alternate_impact)
    breakdown = []
    commercial_total = Decimal("0")
    tax_items = []
    for item in adjustments:
        if item.category == EstimateFinancialAdjustment.Category.TAX:
            tax_items.append(item)
            continue
        if item.method == EstimateFinancialAdjustment.Method.FIXED_AMOUNT:
            calculated = money(item.fixed_amount)
            basis_amount = None
        else:
            basis_amount = (
                normalized
                if item.basis == EstimateFinancialAdjustment.Basis.DIRECT_COST
                else running
            )
            calculated = money(basis_amount * item.percentage_rate / PERCENT_DIVISOR)
        running = money(running + calculated)
        commercial_total = money(commercial_total + calculated)
        breakdown.append(
            {
                "id": item.pk,
                "category": item.category,
                "description": item.description,
                "method": item.method,
                "basis": item.basis,
                "basis_amount": _money_text(basis_amount),
                "rate": str(item.percentage_rate) if item.percentage_rate is not None else None,
                "calculated_amount": _money_text(calculated),
                "currency": item.currency,
            }
        )
    pre_tax = money(running)
    tax_total = Decimal("0")
    for item in tax_items:
        if item.method == EstimateFinancialAdjustment.Method.FIXED_AMOUNT:
            calculated = money(item.fixed_amount)
            basis_amount = None
        else:
            basis_amount = pre_tax
            calculated = money(pre_tax * item.percentage_rate / PERCENT_DIVISOR)
        tax_total = money(tax_total + calculated)
        breakdown.append(
            {
                "id": item.pk,
                "category": item.category,
                "description": item.description,
                "method": item.method,
                "basis": item.basis,
                "basis_amount": _money_text(basis_amount),
                "rate": str(item.percentage_rate) if item.percentage_rate is not None else None,
                "calculated_amount": _money_text(calculated),
                "currency": item.currency,
            }
        )
    final = money(pre_tax + tax_total)
    return CalculationState(
        currency=currency,
        direct_source_cost=direct,
        leveling_adjustments=leveling,
        normalized_direct_cost=normalized,
        allowance_impact=allowance_impact if allowances else None,
        included_alternate_impact=alternate_impact if alternates else None,
        commercial_adjustments=commercial_total
        if any(item.category != EstimateFinancialAdjustment.Category.TAX for item in adjustments)
        else None,
        pre_tax_subtotal=pre_tax,
        tax_impact=money(tax_total) if tax_items else None,
        calculated_estimate_amount=final,
        blockers=(),
        adjustment_breakdown=tuple(breakdown),
    )


def persist_calculated_adjustments(version, state=None):
    state = state or calculate_estimate_version(version)
    amounts = {item["id"]: item["calculated_amount"] for item in state.adjustment_breakdown}
    for adjustment in version.financial_adjustments.all():
        value = amounts.get(adjustment.pk)
        expected = Decimal(value) if value is not None else None
        if adjustment.calculated_amount != expected:
            EstimateFinancialAdjustment.objects.filter(pk=adjustment.pk).update(
                calculated_amount=expected
            )
    return state
