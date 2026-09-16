"""Deterministic human-owned bid leveling over immutable Ready revisions."""

import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Prefetch
from django.utils import timezone

from apps.projects.audit import record_event
from apps.scope_packages.models import ScopePackageVersion

from .bid_revisions import decimal_money
from .models import (
    BidCommercialItem,
    BidComparison,
    BidComparisonEntry,
    BidLevelingAdjustment,
    BidRevision,
    BidScopeCoverage,
)


def commercial_item_detail(item):
    """Return only detail deterministically grounded in the item's exact evidence."""
    if item.kind != BidCommercialItem.Kind.CONDITION:
        return ""
    title = " ".join(item.title.split()).strip(" .:-")
    if not title:
        return ""
    for raw in (item.description, *(source.excerpt for source in item.evidence.all())):
        text = " ".join((raw or "").split()).strip()
        text = re.sub(r"^qualification\s*:\s*", "", text, flags=re.IGNORECASE)
        match = re.fullmatch(
            rf"{re.escape(title)}\s*(?:is|:|[-—])\s*(.+?)\.?",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
    return ""


def audit(comparison, actor, action, metadata=None, target=None):
    record_event(
        organization=comparison.organization,
        project=comparison.project,
        actor=actor,
        action_code=action,
        target=target or comparison,
        metadata=metadata or {},
    )


def ensure_draft(comparison):
    if comparison.status != BidComparison.Status.DRAFT:
        raise ValidationError("Ready comparison history is frozen. Create a successor.")


@transaction.atomic
def create_comparison(*, project, scope_version, actor, notes="", supersedes=None):
    scope_version = (
        ScopePackageVersion.objects.select_for_update()
        .select_related("package__project__organization")
        .get(pk=scope_version.pk)
    )
    package = scope_version.package
    if not project.is_active:
        raise ValidationError("Archived projects remain readable but cannot create comparisons.")
    if (
        scope_version.status != ScopePackageVersion.Status.READY
        or package.project_id != project.pk
        or package.organization_id != project.organization_id
    ):
        raise ValidationError("Choose a Ready scope version from this project.")
    if supersedes and (
        supersedes.status != BidComparison.Status.READY
        or supersedes.scope_version_id != scope_version.pk
    ):
        raise ValidationError("A successor must reference a Ready comparison for this scope.")
    sequence = (
        BidComparison.objects.filter(project=project, scope_version=scope_version).aggregate(
            Max("sequence")
        )["sequence__max"]
        or 0
    ) + 1
    comparison = BidComparison.objects.create(
        organization=project.organization,
        project=project,
        scope_package=package,
        scope_version=scope_version,
        supersedes=supersedes,
        sequence=sequence,
        notes=notes,
        created_by=actor,
    )
    audit(
        comparison,
        actor,
        "bid_comparison.created",
        {"scope_version_id": scope_version.pk, "sequence": sequence},
    )
    return comparison


@transaction.atomic
def save_comparison_notes(*, comparison, actor, notes):
    comparison = BidComparison.objects.select_for_update().get(pk=comparison.pk)
    ensure_draft(comparison)
    comparison.notes = notes
    comparison.save()
    audit(comparison, actor, "bid_comparison.updated", {"fields": ["notes"]})
    return comparison


@transaction.atomic
def add_entry(*, comparison, revision, actor):
    comparison = BidComparison.objects.select_for_update().get(pk=comparison.pk)
    ensure_draft(comparison)
    revision = BidRevision.objects.select_related("company").get(pk=revision.pk)
    entry = BidComparisonEntry.objects.create(
        comparison=comparison,
        revision=revision,
        company=revision.company,
        company_name=revision.company.display_name,
        revision_label=revision.contractor_label,
        added_by=actor,
    )
    audit(
        comparison,
        actor,
        "bid_comparison.entry_added",
        {"entry_id": entry.pk, "revision_id": revision.pk, "company_id": revision.company_id},
        entry,
    )
    return entry


@transaction.atomic
def remove_entry(*, entry, actor):
    comparison = BidComparison.objects.select_for_update().get(pk=entry.comparison_id)
    ensure_draft(comparison)
    entry = BidComparisonEntry.objects.get(pk=entry.pk)
    entry_id, revision_id, company_id = entry.pk, entry.revision_id, entry.company_id
    entry.delete()
    audit(
        comparison,
        actor,
        "bid_comparison.entry_removed",
        {"entry_id": entry_id, "revision_id": revision_id, "company_id": company_id},
    )


@transaction.atomic
def save_adjustment(*, entry, actor, values, adjustment=None):
    comparison = BidComparison.objects.select_for_update().get(pk=entry.comparison_id)
    ensure_draft(comparison)
    is_new = adjustment is None
    if adjustment:
        adjustment = BidLevelingAdjustment.objects.get(pk=adjustment.pk, entry=entry)
    else:
        adjustment = BidLevelingAdjustment(entry=entry, created_by=actor)
    for field in (
        "direction",
        "currency",
        "category",
        "description",
        "scope_item",
        "source_commercial_item",
    ):
        if field in values:
            setattr(adjustment, field, values[field])
    if "amount" in values:
        adjustment.amount = decimal_money(values["amount"])
    adjustment.save()
    action = "bid_leveling_adjustment.created" if is_new else "bid_leveling_adjustment.updated"
    audit(
        comparison,
        actor,
        action,
        {
            "adjustment_id": adjustment.pk,
            "entry_id": entry.pk,
            "direction": adjustment.direction,
            "amount": str(adjustment.amount),
            "currency": adjustment.currency,
            "category": adjustment.category,
        },
        adjustment,
    )
    return adjustment


@transaction.atomic
def remove_adjustment(*, adjustment, actor):
    comparison = BidComparison.objects.select_for_update().get(pk=adjustment.entry.comparison_id)
    ensure_draft(comparison)
    adjustment = BidLevelingAdjustment.objects.get(pk=adjustment.pk)
    metadata = {"adjustment_id": adjustment.pk, "entry_id": adjustment.entry_id}
    adjustment.delete()
    audit(comparison, actor, "bid_leveling_adjustment.removed", metadata)


@transaction.atomic
def mark_comparison_ready(*, comparison, actor):
    comparison = BidComparison.objects.select_for_update().get(pk=comparison.pk)
    ensure_draft(comparison)
    if comparison.entries.count() < 2:
        raise ValidationError("Select at least two Ready bidder revisions.")
    comparison.status = BidComparison.Status.READY
    comparison.reviewed_by = actor
    comparison.reviewed_at = timezone.now()
    comparison.save()
    audit(
        comparison,
        actor,
        "bid_comparison.ready",
        {"entry_count": comparison.entries.count()},
    )
    return comparison


def evaluated_amount(entry):
    revision = entry.revision
    if revision.base_bid is None or revision.currency_review != BidRevision.ReviewState.CONFIRMED:
        return None
    value = revision.base_bid
    for item in entry.adjustments.all():
        if item.currency != revision.currency:
            return None
        value += (
            item.amount if item.direction == BidLevelingAdjustment.Direction.ADD else -item.amount
        )
    return value.quantize(Decimal("0.01"))


def eligible_ready_revisions(project):
    revisions = (
        BidRevision.objects.filter(project=project, status=BidRevision.Status.READY)
        .select_related("company", "submission", "scope_package", "scope_version")
        .order_by("scope_version_id", "company__display_name", "-sequence", "-id")
    )
    return [
        {
            "id": row.pk,
            "company_id": row.company_id,
            "company_name": row.company.display_name,
            "revision_label": row.contractor_label,
            "revision_sequence": row.sequence,
            "submission_id": row.submission_id,
            "scope_package_id": row.scope_package_id,
            "scope_version_id": row.scope_version_id,
            "trade": row.scope_package.trade_category,
            "scope_version": row.scope_version.version,
            "base_bid": str(row.base_bid) if row.base_bid is not None else None,
            "currency": row.currency,
            "received_at": row.submission.received_at,
        }
        for row in revisions
    ]


def comparison_queryset(project):
    return (
        BidComparison.objects.filter(project=project)
        .select_related("scope_package", "scope_version")
        .prefetch_related("entries")
        .annotate(entry_count=Count("entries"))
    )


def summary_data(comparison):
    return {
        "id": comparison.pk,
        "sequence": comparison.sequence,
        "status": comparison.status,
        "trade": comparison.scope_package.trade_category,
        "scope_package_id": comparison.scope_package_id,
        "scope_version_id": comparison.scope_version_id,
        "scope_version": comparison.scope_version.version,
        "bidder_count": (
            comparison.entry_count
            if hasattr(comparison, "entry_count")
            else len(comparison.entries.all())
        ),
        "updated_at": comparison.updated_at,
    }


def detail_queryset(project):
    return (
        BidComparison.objects.filter(project=project)
        .select_related("scope_package", "scope_version", "created_by", "reviewed_by")
        .prefetch_related(
            "scope_version__scope_items",
            Prefetch(
                "entries",
                queryset=BidComparisonEntry.objects.select_related(
                    "revision__submission", "revision__company"
                ).prefetch_related(
                    "revision__submission__attachments",
                    "revision__commercial_items__evidence",
                    "revision__scope_coverage",
                    "revision__evidence",
                    "adjustments",
                ),
            ),
        )
    )


def detail_data(comparison):
    entries = list(comparison.entries.all())
    currencies = {
        entry.revision.currency
        for entry in entries
        if entry.revision.currency_review == BidRevision.ReviewState.CONFIRMED
        and entry.revision.currency
    }
    comparable_currency = (
        len(entries) >= 2
        and len(currencies) == 1
        and all(
            entry.revision.currency_review == BidRevision.ReviewState.CONFIRMED
            and entry.revision.base_bid is not None
            for entry in entries
        )
    )
    scope_items = list(comparison.scope_version.scope_items.all())
    entry_rows = []
    for entry in entries:
        revision = entry.revision
        coverage = {item.scope_item_id: item for item in revision.scope_coverage.all()}
        attachments = list(revision.submission.attachments.all())
        commercial = list(revision.commercial_items.all())
        adjustments = list(entry.adjustments.all())
        flags = []
        if revision.base_bid is None:
            flags.append("Missing Base Bid")
        if revision.currency_review != BidRevision.ReviewState.CONFIRMED:
            flags.append("Currency not confirmed")
        if any(item.kind == BidCommercialItem.Kind.EXCLUSION for item in commercial):
            flags.append("Explicit exclusions")
        if any(
            item.state == BidScopeCoverage.State.NEEDS_CLARIFICATION for item in coverage.values()
        ):
            flags.append("Scope needs clarification")
        if any(item.state == BidScopeCoverage.State.NOT_ADDRESSED for item in coverage.values()):
            flags.append("Scope not addressed")
        entry_rows.append(
            {
                "id": entry.pk,
                "revision_id": revision.pk,
                "revision_sequence": revision.sequence,
                "revision_label": entry.revision_label,
                "company_id": entry.company_id,
                "company_name": entry.company_name,
                "submission_id": revision.submission_id,
                "received_at": revision.submission.received_at,
                "base_bid": str(revision.base_bid) if revision.base_bid is not None else None,
                "currency": revision.currency,
                "currency_review": revision.currency_review,
                "tax_treatment": revision.tax_treatment,
                "validity_days": revision.validity_days,
                "validity_date": revision.validity_date,
                "schedule_text": revision.schedule_text,
                "attachments": [
                    {"id": item.pk, "filename": item.original_filename} for item in attachments
                ],
                "commercial_items": [
                    {
                        "id": item.pk,
                        "kind": item.kind,
                        "title": item.title,
                        "description": item.description,
                        "detail": commercial_item_detail(item),
                        "treatment": item.treatment,
                        "amount": str(item.amount) if item.amount is not None else None,
                        "currency": item.currency,
                        "included_in_base": item.included_in_base,
                        "scope_item_id": item.scope_item_id,
                        "evidence": [
                            {
                                "attachment_id": source.attachment_id,
                                "page_number": source.page_number,
                                "excerpt": source.excerpt,
                            }
                            for source in item.evidence.all()
                        ],
                    }
                    for item in commercial
                ],
                "unmapped_items": [item.pk for item in commercial if item.scope_item_id is None],
                "coverage": {
                    str(item.pk): {
                        "state": coverage[item.pk].state
                        if item.pk in coverage
                        else "not_addressed",
                        "recorded": item.pk in coverage,
                        "wording": coverage[item.pk].wording if item.pk in coverage else "",
                    }
                    for item in scope_items
                },
                "adjustments": [
                    {
                        "id": item.pk,
                        "direction": item.direction,
                        "amount": str(item.amount),
                        "currency": item.currency,
                        "category": item.category,
                        "description": item.description,
                        "scope_item_id": item.scope_item_id,
                        "source_commercial_item_id": item.source_commercial_item_id,
                    }
                    for item in adjustments
                ],
                "evaluated_amount": (
                    str(evaluated_amount(entry)) if evaluated_amount(entry) is not None else None
                ),
                "attention_flags": flags,
            }
        )
    if len(currencies) > 1:
        for row in entry_rows:
            row["attention_flags"].append("Different bid currencies")
    return {
        **summary_data(comparison),
        "notes": comparison.notes,
        "supersedes_id": comparison.supersedes_id,
        "created_by_id": comparison.created_by_id,
        "reviewed_by_id": comparison.reviewed_by_id,
        "created_at": comparison.created_at,
        "reviewed_at": comparison.reviewed_at,
        "currency_comparable": comparable_currency,
        "comparison_currency": next(iter(currencies)) if comparable_currency else None,
        "scope_items": [
            {"id": item.pk, "sequence": item.sequence, "title": item.title} for item in scope_items
        ],
        "entries": entry_rows,
    }
