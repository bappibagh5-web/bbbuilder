"""Human-owned interpretation of an immutable subcontractor quote."""

import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.projects.audit import record_event

from .models import (
    BidAttachment,
    BidCandidateDecision,
    BidCommercialItem,
    BidEvidence,
    BidExtractionRun,
    BidRevision,
    BidScopeCoverage,
    BidSubmission,
    InvitationRecipient,
)

MONEY_PATTERN = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?$")


def decimal_money(value):
    """Money enters the commercial domain as an unambiguous decimal string."""
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not MONEY_PATTERN.fullmatch(value):
        raise ValidationError({"amount": "Use a nonnegative amount with up to two decimals."})
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValidationError({"amount": "Enter a valid decimal amount."}) from error
    if not amount.is_finite() or amount >= Decimal("10000000000000000"):
        raise ValidationError({"amount": "Amount is outside the supported range."})
    return amount.quantize(Decimal("0.01"))


def audit(revision, actor, action, metadata=None):
    record_event(
        organization=revision.organization,
        project=revision.project,
        actor=actor,
        action_code=action,
        target=revision,
        metadata=metadata or {},
    )


def require_active_project(revision):
    if not revision.project.is_active:
        raise ValidationError("Archived projects remain readable but cannot structure new bids.")


@transaction.atomic
def create_revision(*, submission, actor, label="", supersedes=None, request_key=None):
    source = BidSubmission.objects.select_for_update().get(pk=submission.pk)
    if not source.project.is_active:
        raise ValidationError("Archived projects remain readable but cannot structure new bids.")
    InvitationRecipient.objects.select_for_update().get(pk=source.recipient_id)
    if request_key:
        existing = BidRevision.objects.filter(submission=source, request_key=request_key).first()
        if existing:
            return existing
    if supersedes and (
        supersedes.recipient_id != source.recipient_id
        or supersedes.scope_version_id != source.scope_version_id
        or supersedes.sequence <= 0
    ):
        raise ValidationError("Earlier revision must match this exact invitation and scope.")
    sequence = (
        BidRevision.objects.filter(recipient=source.recipient).aggregate(Max("sequence"))[
            "sequence__max"
        ]
        or 0
    ) + 1
    revision = BidRevision.objects.create(
        organization=source.organization,
        project=source.project,
        scope_package=source.scope_package,
        scope_version=source.scope_version,
        company=source.company,
        recipient=source.recipient,
        submission=source,
        supersedes=supersedes,
        sequence=sequence,
        contractor_label=label,
        request_key=request_key,
        created_by=actor,
    )
    audit(revision, actor, "bid_revision.created", {"submission_id": source.pk})
    return revision


@transaction.atomic
def save_summary(*, revision, actor, values):
    revision = BidRevision.objects.select_for_update().get(pk=revision.pk)
    require_active_project(revision)
    if revision.status != BidRevision.Status.DRAFT:
        raise ValidationError("Ready bid history is frozen. Create a successor revision.")
    allowed = {
        "contractor_label",
        "currency",
        "currency_review",
        "base_bid_review",
        "tax_treatment",
        "tax_reviewed",
        "commercial_items_reviewed",
        "scope_reviewed",
        "validity_date",
        "validity_days",
        "schedule_text",
        "estimator_notes",
    }
    for key, value in values.items():
        if key not in allowed and key != "base_bid":
            raise ValidationError({key: "This field cannot be edited."})
        setattr(revision, key, decimal_money(value) if key == "base_bid" else value)
    revision.save()
    audit(revision, actor, "bid_revision.updated", {"fields": sorted(values)})
    return revision


@transaction.atomic
def save_commercial_item(*, revision, actor, values, item=None):
    revision = BidRevision.objects.select_for_update().get(pk=revision.pk)
    require_active_project(revision)
    if revision.status != BidRevision.Status.DRAFT:
        raise ValidationError("Ready bid history is frozen.")
    fields = {
        "kind",
        "contractor_label",
        "title",
        "description",
        "category",
        "treatment",
        "currency",
        "included_in_base",
        "scope_item_id",
        "estimator_note",
    }
    if item:
        item = BidCommercialItem.objects.get(pk=item.pk, revision=revision)
    else:
        sequence = (
            BidCommercialItem.objects.filter(revision=revision).aggregate(Max("sequence"))[
                "sequence__max"
            ]
            or 0
        ) + 1
        item = BidCommercialItem(revision=revision, sequence=sequence)
    for key, value in values.items():
        if key not in fields and key != "amount":
            raise ValidationError({key: "This field cannot be edited."})
        setattr(item, key, decimal_money(value) if key == "amount" else value)
    item.save()
    if revision.commercial_items_reviewed:
        revision.commercial_items_reviewed = False
        revision.save()
    audit(revision, actor, "bid_revision.item_saved", {"item_id": item.pk, "kind": item.kind})
    return item


@transaction.atomic
def save_scope_coverage(*, revision, actor, scope_item, state, wording="", note="", reviewed=False):
    revision = BidRevision.objects.select_for_update().get(pk=revision.pk)
    require_active_project(revision)
    if revision.status != BidRevision.Status.DRAFT:
        raise ValidationError("Ready scope coverage is frozen.")
    if scope_item.package_version_id != revision.scope_version_id:
        raise ValidationError("Coverage must use the exact quoted Ready scope version.")
    coverage, _ = BidScopeCoverage.objects.get_or_create(revision=revision, scope_item=scope_item)
    coverage.state = state
    coverage.wording = wording
    coverage.estimator_note = note
    coverage.reviewed = reviewed
    coverage.save()
    if revision.scope_reviewed:
        revision.scope_reviewed = False
        revision.save()
    audit(revision, actor, "bid_revision.coverage_saved", {"scope_item_id": scope_item.pk})
    return coverage


@transaction.atomic
def remove_commercial_item(*, revision, actor, item):
    revision = BidRevision.objects.select_for_update().get(pk=revision.pk)
    require_active_project(revision)
    item = BidCommercialItem.objects.get(pk=item.pk, revision=revision)
    if revision.status != BidRevision.Status.DRAFT:
        raise ValidationError("Ready bid history is frozen.")
    if item.evidence.exists():
        raise ValidationError("Remove the linked Draft evidence before removing this item.")
    item_id = item.pk
    item.delete()
    if revision.commercial_items_reviewed:
        revision.commercial_items_reviewed = False
        revision.save()
    audit(revision, actor, "bid_revision.item_removed", {"item_id": item_id})


@transaction.atomic
def add_evidence(
    *,
    revision,
    actor,
    attachment=None,
    commercial_item=None,
    coverage=None,
    field_key="",
    source="quote",
    page_number=None,
    excerpt="",
    note="",
):
    revision = BidRevision.objects.select_for_update().get(pk=revision.pk)
    require_active_project(revision)
    if revision.status != BidRevision.Status.DRAFT:
        raise ValidationError("Ready bid evidence is frozen.")
    evidence = BidEvidence.objects.create(
        revision=revision,
        attachment=attachment,
        commercial_item=commercial_item,
        coverage=coverage,
        field_key=field_key,
        source=source,
        page_number=page_number,
        excerpt=excerpt,
        note=note,
    )
    audit(revision, actor, "bid_revision.evidence_added", {"evidence_id": evidence.pk})
    return evidence


@transaction.atomic
def remove_evidence(*, revision, actor, evidence):
    revision = BidRevision.objects.select_for_update().get(pk=revision.pk)
    require_active_project(revision)
    evidence = BidEvidence.objects.get(pk=evidence.pk, revision=revision)
    if revision.status != BidRevision.Status.DRAFT:
        raise ValidationError("Ready bid evidence is frozen.")
    evidence_id = evidence.pk
    evidence.delete()
    audit(revision, actor, "bid_revision.evidence_removed", {"evidence_id": evidence_id})


def readiness(revision):
    blockers = []
    if not BidAttachment.objects.filter(submission=revision.submission).exists():
        blockers.append("source_quote_missing")
    if revision.scope_version.status != "ready":
        blockers.append("scope_version_not_ready")
    if revision.currency_review == BidRevision.ReviewState.UNREVIEWED:
        blockers.append("currency_not_reviewed")
    if revision.base_bid_review == BidRevision.ReviewState.UNREVIEWED:
        blockers.append("base_bid_not_reviewed")
    if not revision.tax_reviewed:
        blockers.append("tax_not_reviewed")
    if not revision.commercial_items_reviewed:
        blockers.append("commercial_items_not_reviewed")
    if not revision.scope_reviewed:
        blockers.append("scope_not_reviewed")
    if BidScopeCoverage.objects.filter(revision=revision, reviewed=False).exists():
        blockers.append("scope_coverage_not_reviewed")
    # Unknown quote values remain unknown; ready never fabricates them.
    return blockers


@transaction.atomic
def mark_ready(*, revision, actor):
    revision = BidRevision.objects.select_for_update().get(pk=revision.pk)
    require_active_project(revision)
    if revision.status == BidRevision.Status.READY:
        return revision
    if revision.status != BidRevision.Status.DRAFT:
        raise ValidationError("Only a Draft bid can become Ready for Comparison.")
    blockers = readiness(revision)
    if blockers:
        raise ValidationError({"blockers": blockers})
    revision.status = BidRevision.Status.READY
    revision.reviewed_by = actor
    revision.reviewed_at = timezone.now()
    revision.save()
    audit(revision, actor, "bid_revision.ready", {"submission_id": revision.submission_id})
    return revision


@transaction.atomic
def decide_candidate(*, run, revision, actor, index, decision, corrections=None):
    """An explicit human action applies, corrects, or ignores an AI suggestion."""
    run = BidExtractionRun.objects.select_for_update().get(pk=run.pk)
    revision = BidRevision.objects.select_for_update().get(pk=revision.pk)
    require_active_project(revision)
    existing = BidCandidateDecision.objects.filter(
        run=run, candidate_index=index, revision=revision
    ).first()
    if existing:
        return existing
    if (
        run.status != BidExtractionRun.Status.SUCCEEDED
        or run.submission_id != revision.submission_id
        or revision.status != BidRevision.Status.DRAFT
        or index < 0
        or index >= len(run.candidates)
    ):
        raise ValidationError("Suggestion must belong to this Draft and source quote.")
    if decision not in BidCandidateDecision.Decision.values:
        raise ValidationError("Choose accept, correct, or ignore.")
    if decision == BidCandidateDecision.Decision.CORRECTED and not (
        corrections and isinstance(corrections.get("note"), str) and corrections["note"].strip()
    ):
        raise ValidationError("A human correction requires a brief reason.")
    candidate = run.candidates[index]
    values = {**candidate, **(corrections or {})}
    item = None
    evidence = None
    if decision != BidCandidateDecision.Decision.IGNORED:
        kind = candidate["kind"]
        if kind == "base_bid":
            save_summary(
                revision=revision,
                actor=actor,
                values={
                    "base_bid": values["amount"],
                    "base_bid_review": BidRevision.ReviewState.CONFIRMED
                    if values["amount"] is not None
                    else BidRevision.ReviewState.NOT_STATED,
                },
            )
            field_key = "base_bid"
        elif kind == "currency":
            save_summary(
                revision=revision,
                actor=actor,
                values={
                    "currency": values.get("currency") or "",
                    "currency_review": BidRevision.ReviewState.CONFIRMED
                    if values.get("currency")
                    else BidRevision.ReviewState.NOT_STATED,
                },
            )
            field_key = "currency"
        elif kind == "tax":
            treatment = values.get("treatment")
            if treatment not in BidRevision.TaxTreatment.values:
                raise ValidationError("Confirm a valid tax treatment.")
            save_summary(
                revision=revision,
                actor=actor,
                values={
                    "tax_treatment": treatment,
                    "tax_reviewed": True,
                },
            )
            field_key = "tax_treatment"
        elif kind == "scope_coverage":
            from apps.scope_packages.models import ScopeItem

            if values.get("scope_item_id") is None:
                raise ValidationError(
                    "Choose the exact quoted ScopeItem before confirming coverage."
                )
            scope_item = ScopeItem.objects.get(
                pk=values["scope_item_id"], package_version=revision.scope_version
            )
            coverage = save_scope_coverage(
                revision=revision,
                actor=actor,
                scope_item=scope_item,
                state=values.get("state", BidScopeCoverage.State.NEEDS_CLARIFICATION),
                wording=values.get("wording", values["excerpt"]),
                reviewed=True,
            )
            evidence = add_evidence(
                revision=revision,
                actor=actor,
                attachment=run.attachment,
                coverage=coverage,
                source=BidEvidence.Source.QUOTE,
                page_number=candidate["page_number"],
                excerpt=candidate["excerpt"],
                note=values.get("note", ""),
            )
            field_key = ""
        else:
            mapped = {
                "alternate": BidCommercialItem.Kind.ALTERNATE,
                "allowance": BidCommercialItem.Kind.ALLOWANCE,
                "fee": BidCommercialItem.Kind.FEE,
                "exclusion": BidCommercialItem.Kind.EXCLUSION,
                "condition": BidCommercialItem.Kind.CONDITION,
                "validity": BidCommercialItem.Kind.CONDITION,
                "schedule": BidCommercialItem.Kind.CONDITION,
            }
            if kind not in mapped:
                raise ValidationError("This suggestion cannot be applied as commercial truth.")
            item = save_commercial_item(
                revision=revision,
                actor=actor,
                values={
                    "kind": mapped[kind],
                    "title": values["title"],
                    "description": values["description"],
                    "treatment": values.get("treatment") or "",
                    "amount": values.get("amount"),
                    "currency": values.get("currency") or "",
                    "category": values.get("category", ""),
                    "included_in_base": values.get("included_in_base", "unclear"),
                },
            )
            field_key = ""
            evidence = add_evidence(
                revision=revision,
                actor=actor,
                attachment=run.attachment,
                commercial_item=item,
                source=BidEvidence.Source.QUOTE,
                page_number=candidate["page_number"],
                excerpt=candidate["excerpt"],
                note=values.get("note", ""),
            )
        if field_key:
            evidence = add_evidence(
                revision=revision,
                actor=actor,
                attachment=run.attachment,
                field_key=field_key,
                source=BidEvidence.Source.QUOTE,
                page_number=candidate["page_number"],
                excerpt=candidate["excerpt"],
                note=values.get("note", ""),
            )
    record = BidCandidateDecision.objects.create(
        run=run,
        candidate_index=index,
        revision=revision,
        decision=decision,
        commercial_item=item,
        evidence=evidence,
        actor=actor,
    )
    audit(
        revision,
        actor,
        "bid_extraction.reviewed",
        {
            "run_id": run.pk,
            "candidate_index": index,
            "decision": decision,
        },
    )
    return record
