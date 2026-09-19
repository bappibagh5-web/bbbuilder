import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.outreach.comparisons import evaluated_amount
from apps.outreach.models import BidHumanDecision, BidHumanReview
from apps.projects.audit import record_event
from apps.projects.models import Project

from .calculations import money
from .models import (
    AwardedProjectHandoffSnapshot,
    EstimateVersion,
    ProjectAward,
    ProposalVersion,
    TradeAward,
)
from .services import _require_active_project, _require_operator


def _amount(value, field="award_amount"):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError({field: "Enter a valid award amount."}) from error
    if not result.is_finite() or result < 0:
        raise ValidationError({field: "Enter a non-negative finite award amount."})
    return money(result)


def _currency(value):
    result = (value or "").strip().upper()
    if len(result) != 3 or not result.isalpha():
        raise ValidationError({"currency": "Enter a three-letter currency code."})
    return result


def _next(model, **filters):
    return (model.objects.filter(**filters).aggregate(value=Max("sequence"))["value"] or 0) + 1


@transaction.atomic
def create_project_award(*, project, proposal_version, actor, data):
    _require_operator(actor=actor, organization=project.organization)
    _require_active_project(project)
    version = ProposalVersion.objects.select_related(
        "proposal__project", "proposal__organization", "estimate_version"
    ).get(pk=proposal_version.pk)
    if (
        version.status != ProposalVersion.Status.FINALIZED
        or version.proposal.project_id != project.pk
        or version.estimate_version.status != EstimateVersion.Status.FROZEN
        or version.proposal.organization_id != project.organization_id
        or not version.commercial_snapshot
    ):
        raise ValidationError(
            "Project award requires this project's exact Finalized proposal and Frozen estimate."
        )
    amount = _amount(data.get("award_amount"))
    currency = _currency(data.get("currency"))
    rationale = (data.get("rationale") or "").strip()
    if not rationale:
        raise ValidationError({"rationale": "Record the client acceptance or award basis."})
    proposal_total = _amount(version.commercial_snapshot.get("total_amount"), "proposal_total")
    proposal_currency = version.commercial_snapshot.get("currency")
    if (amount != proposal_total or currency != proposal_currency) and len(rationale) < 10:
        raise ValidationError(
            {"rationale": "Explain why the accepted amount differs from the finalized proposal."}
        )
    evidence = data.get("acceptance_evidence")
    if evidence and evidence.organization_id != project.organization_id:
        raise ValidationError(
            {"acceptance_evidence": "Acceptance evidence must belong to this organization."}
        )
    award = ProjectAward.objects.create(
        organization=project.organization,
        project=project,
        proposal_version=version,
        estimate_version=version.estimate_version,
        sequence=_next(ProjectAward, project=project),
        supersedes=ProjectAward.objects.filter(
            project=project, status=ProjectAward.Status.CONFIRMED
        ).first(),
        award_amount=amount,
        currency=currency,
        award_date=data["award_date"],
        rationale=rationale,
        client_reference=(data.get("client_reference") or "").strip(),
        acceptance_evidence=evidence,
        created_by=actor,
    )
    record_event(
        organization=project.organization,
        project=project,
        actor=actor,
        action_code="project_award.draft_created",
        target=award,
        metadata={
            "proposal_version_id": version.pk,
            "estimate_version_id": version.estimate_version_id,
        },
    )
    return award


@transaction.atomic
def confirm_project_award(*, award, actor):
    _require_operator(actor=actor, organization=award.organization)
    locked = (
        ProjectAward.objects.select_for_update()
        .select_related("organization", "project", "proposal_version", "estimate_version")
        .get(pk=award.pk)
    )
    if locked.status == ProjectAward.Status.CONFIRMED:
        return locked, False
    if locked.status != ProjectAward.Status.DRAFT:
        raise ValidationError("Only a Draft Project Award can be confirmed.")
    if (
        locked.proposal_version.status != ProposalVersion.Status.FINALIZED
        or locked.estimate_version.status != EstimateVersion.Status.FROZEN
        or locked.proposal_version.estimate_version_id != locked.estimate_version_id
    ):
        raise ValidationError("The exact proposal and estimate must remain Finalized and Frozen.")
    locked.status = ProjectAward.Status.CONFIRMED
    locked.confirmed_by = actor
    locked.confirmed_at = timezone.now()
    locked.save(update_fields=["status", "confirmed_by", "confirmed_at"])
    record_event(
        organization=locked.organization,
        project=locked.project,
        actor=actor,
        action_code="project_award.confirmed",
        target=locked,
        metadata={"proposal_version_id": locked.proposal_version_id},
    )
    return locked, True


def eligible_trade_reviews(project):
    reviews = (
        BidHumanReview.objects.filter(
            project=project,
            status=BidHumanReview.Status.FINALIZED,
            outcome=BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL,
            selected_entry__isnull=False,
        )
        .select_related(
            "scope_package",
            "scope_version",
            "comparison",
            "selected_entry__company",
            "selected_entry__revision",
        )
        .prefetch_related("selected_entry__adjustments", "decisions")
    )
    result = []
    for review in reviews:
        decision = next(
            (
                item
                for item in review.decisions.all()
                if item.comparison_entry_id == review.selected_entry_id
            ),
            None,
        )
        if decision is None or decision.state != BidHumanDecision.State.SHORTLISTED:
            continue
        entry = review.selected_entry
        result.append(
            {
                "review": review,
                "entry": entry,
                "trade": review.scope_package.trade_category,
                "company": entry.company_name,
                "base_bid": entry.revision.base_bid,
                "currency": entry.revision.currency,
                "evaluated_amount": evaluated_amount(entry),
            }
        )
    return result


@transaction.atomic
def create_trade_award(*, project, review, actor, data):
    _require_operator(actor=actor, organization=project.organization)
    _require_active_project(project)
    eligible = next(
        (item for item in eligible_trade_reviews(project) if item["review"].pk == review.pk), None
    )
    if eligible is None:
        raise ValidationError("Only the exact finalized Selected-for-Proposal bidder is eligible.")
    entry = eligible["entry"]
    award = TradeAward.objects.create(
        organization=project.organization,
        project=project,
        scope_package=review.scope_package,
        scope_version=review.scope_version,
        company=entry.company,
        human_review=review,
        comparison=review.comparison,
        comparison_entry=entry,
        bid_revision=entry.revision,
        sequence=_next(TradeAward, project=project, scope_package=review.scope_package),
        supersedes=TradeAward.objects.filter(
            project=project,
            scope_package=review.scope_package,
            status=TradeAward.Status.CONFIRMED,
        ).first(),
        quoted_base_bid=entry.revision.base_bid,
        evaluated_amount=eligible["evaluated_amount"],
        award_amount=_amount(data.get("award_amount")),
        currency=_currency(data.get("currency")),
        award_date=data["award_date"],
        rationale=(data.get("rationale") or "").strip(),
        reference_number=(data.get("reference_number") or "").strip(),
        created_by=actor,
    )
    if not award.rationale:
        raise ValidationError({"rationale": "Record the subcontractor award basis."})
    if award.currency != entry.revision.currency:
        raise ValidationError(
            {"currency": "Award currency must match the selected quote currency."}
        )
    award.full_clean()
    record_event(
        organization=project.organization,
        project=project,
        actor=actor,
        action_code="trade_award.draft_created",
        target=award,
        metadata={"review_id": review.pk, "bid_revision_id": entry.revision_id},
    )
    return award


@transaction.atomic
def confirm_trade_award(*, award, actor):
    _require_operator(actor=actor, organization=award.organization)
    locked = (
        TradeAward.objects.select_for_update()
        .select_related("organization", "project")
        .get(pk=award.pk)
    )
    if locked.status == TradeAward.Status.CONFIRMED:
        return locked, False
    if locked.status != TradeAward.Status.DRAFT:
        raise ValidationError("Only a Draft Trade Award can be confirmed.")
    eligible_ids = {item["review"].pk for item in eligible_trade_reviews(locked.project)}
    if locked.human_review_id not in eligible_ids:
        raise ValidationError("The exact selected bidder is no longer eligible for confirmation.")
    locked.status = TradeAward.Status.CONFIRMED
    locked.confirmed_by = actor
    locked.confirmed_at = timezone.now()
    locked.save(update_fields=["status", "confirmed_by", "confirmed_at"])
    record_event(
        organization=locked.organization,
        project=locked.project,
        actor=actor,
        action_code="trade_award.confirmed",
        target=locked,
        metadata={"bid_revision_id": locked.bid_revision_id},
    )
    return locked, True


def _handoff_content(project, project_award):
    proposal = project_award.proposal_version
    trade_awards = TradeAward.objects.filter(
        project=project, status=TradeAward.Status.CONFIRMED
    ).select_related("scope_package", "scope_version", "company", "bid_revision")
    return {
        "project": {
            "id": project.pk,
            "organization_id": project.organization_id,
            "project_number": project.project_number,
            "name": project.name,
            "client_name": project.client_name,
            "site": {
                "line_1": project.site_address_line_1,
                "line_2": project.site_address_line_2,
                "city": project.city,
                "province_state": project.province_state,
                "postal_zip_code": project.postal_zip_code,
                "country": project.country,
            },
            "contacts": list(
                project.contacts.filter(is_active=True).values(
                    "id", "company_name", "person_name", "email", "phone", "contact_role"
                )
            ),
        },
        "project_award": {
            "id": project_award.pk,
            "proposal_version_id": proposal.pk,
            "proposal_number": proposal.proposal_number,
            "proposal_version": proposal.version,
            "estimate_version_id": project_award.estimate_version_id,
            "award_amount": str(project_award.award_amount),
            "currency": project_award.currency,
            "award_date": project_award.award_date.isoformat(),
            "client_reference": project_award.client_reference,
            "proposal_fingerprint": proposal.snapshot_fingerprint,
            "estimate_fingerprint": project_award.estimate_version.calculation_fingerprint,
        },
        "trade_awards": [
            {
                "id": item.pk,
                "trade": item.scope_package.trade_category,
                "scope_version_id": item.scope_version_id,
                "company_id": item.company_id,
                "company_name": item.company.display_name,
                "bid_revision_id": item.bid_revision_id,
                "award_amount": str(item.award_amount),
                "currency": item.currency,
                "award_date": item.award_date.isoformat(),
            }
            for item in trade_awards
        ],
    }


@transaction.atomic
def transition_project_to_awarded(*, award, actor):
    _require_operator(actor=actor, organization=award.organization)
    locked = (
        ProjectAward.objects.select_for_update()
        .select_related("organization", "project", "proposal_version", "estimate_version")
        .get(pk=award.pk)
    )
    if locked.status != ProjectAward.Status.CONFIRMED:
        raise ValidationError("Confirm the Project Award before transitioning the project.")
    project = Project.objects.select_for_update().get(pk=locked.project_id)
    content = _handoff_content(project, locked)
    fingerprint = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    existing = AwardedProjectHandoffSnapshot.objects.filter(
        project=project, fingerprint=fingerprint
    ).first()
    if existing:
        return existing, False
    latest = AwardedProjectHandoffSnapshot.objects.filter(project=project).first()
    snapshot = AwardedProjectHandoffSnapshot.objects.create(
        organization=project.organization,
        project=project,
        project_award=locked,
        sequence=(latest.sequence + 1 if latest else 1),
        supersedes=latest,
        snapshot=content,
        fingerprint=fingerprint,
        created_by=actor,
    )
    if project.status != Project.Status.AWARDED:
        previous = project.status
        project.status = Project.Status.AWARDED
        project.save(update_fields=["status", "updated_at"])
        record_event(
            organization=project.organization,
            project=project,
            actor=actor,
            action_code="project.awarded",
            target=project,
            metadata={"previous_status": previous, "project_award_id": locked.pk},
        )
    record_event(
        organization=project.organization,
        project=project,
        actor=actor,
        action_code="awarded_handoff.created",
        target=snapshot,
        metadata={"project_award_id": locked.pk, "sequence": snapshot.sequence},
    )
    return snapshot, True
