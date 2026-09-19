import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.projects.audit import record_event

from .calculations import calculate_estimate_version, calculation_queryset
from .models import EstimateVersion, ProposalVersion
from .services import _require_active_project, _require_operator


def _fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def proposal_number(version):
    project = version.proposal.project
    return f"{project.project_number}-P{version.proposal_id:04d}"


def _client_snapshot(version, actor, finalized_at):
    proposal = version.proposal
    project = proposal.project
    organization = proposal.organization
    contact = version.client_contact or proposal.client_contact
    return {
        "organization_name": organization.name,
        "organization_legal_name": organization.legal_name,
        "project_number": project.project_number,
        "project_name": project.name,
        "site_address": {
            "line_1": project.site_address_line_1,
            "line_2": project.site_address_line_2,
            "city": project.city,
            "province_state": project.province_state,
            "postal_zip_code": project.postal_zip_code,
            "country": project.country,
        },
        "client_name": project.client_name,
        "client_contact": None
        if contact is None
        else {
            "company_name": contact.company_name,
            "person_name": contact.person_name,
            "email": contact.email,
            "phone": contact.phone,
        },
        "proposal_number": proposal_number(version),
        "proposal_version": version.version,
        "issue_date": version.issue_date.isoformat(),
        "prepared_by": version.created_by.get_full_name() or version.created_by.email,
        "finalized_by": actor.get_full_name() or actor.email,
        "finalized_at": finalized_at.isoformat(),
    }


def _commercial_snapshot(version, calculation, calculation_fingerprint):
    estimate = version.estimate_version
    return {
        "estimate_version_id": estimate.pk,
        "estimate_version": estimate.version,
        "currency": calculation.currency,
        "pre_tax_amount": str(calculation.pre_tax_subtotal),
        "tax_amount": str(calculation.tax_impact or "0.00"),
        "total_amount": str(calculation.calculated_estimate_amount),
        "calculation_fingerprint": calculation_fingerprint,
        "allowances": [
            {"description": item.description, "amount": str(item.amount), "currency": item.currency}
            for item in estimate.allowances.filter(treatment="included").order_by("sequence", "id")
            if item.amount is not None
        ],
        "alternates": [
            {
                "description": item.description,
                "direction": item.direction,
                "amount": str(item.amount),
                "currency": item.currency,
            }
            for item in estimate.alternates.filter(included_in_estimate=True).order_by(
                "sequence", "id"
            )
            if item.amount is not None
        ],
        "exclusions": [
            {"description": item.description}
            for item in estimate.exclusions.order_by("sequence", "id")
        ],
    }


def update_draft_content(*, version, actor, data):
    _require_operator(actor=actor, organization=version.proposal.organization)
    _require_active_project(version.proposal.project)
    if version.status != ProposalVersion.Status.DRAFT:
        raise ValidationError("Finalized proposal versions are immutable.")
    allowed = {
        "issue_date",
        "introduction",
        "scope_summary",
        "commercial_notes",
        "terms_conditions",
        "client_contact",
    }
    changed = []
    for field, value in data.items():
        if field in allowed and getattr(version, field) != value:
            setattr(version, field, value)
            changed.append(field)
    if changed:
        version.save(update_fields=[*changed])
        record_event(
            organization=version.proposal.organization,
            project=version.proposal.project,
            actor=actor,
            action_code="proposal.content_updated",
            target=version,
            metadata={"fields": sorted(changed)},
        )
    return version


@transaction.atomic
def finalize_proposal(*, version, actor, note=""):
    _require_operator(actor=actor, organization=version.proposal.organization)
    _require_active_project(version.proposal.project)
    locked = (
        ProposalVersion.objects.select_for_update()
        # client_contact is nullable. Joining it into a SELECT FOR UPDATE query
        # makes PostgreSQL reject the lock because the related row is on the
        # nullable side of an outer join. Load it lazily after the proposal
        # version itself has been locked instead.
        .select_related("proposal__project", "proposal__organization", "created_by")
        .get(pk=version.pk)
    )
    estimate = calculation_queryset().select_for_update().get(pk=locked.estimate_version_id)
    if locked.status != ProposalVersion.Status.DRAFT:
        raise ValidationError("Only a Draft proposal can be finalized.")
    if estimate.status != EstimateVersion.Status.DRAFT:
        raise ValidationError("The exact source estimate is already frozen.")
    calculation = calculate_estimate_version(estimate)
    if (
        calculation.blockers
        or calculation.calculated_estimate_amount is None
        or not calculation.currency
    ):
        raise ValidationError("A valid single-currency deterministic estimate is required.")
    project = locked.proposal.project
    if (
        not project.project_number.strip()
        or not project.name.strip()
        or not project.client_name.strip()
    ):
        raise ValidationError("Project and client identity are required before finalization.")
    if locked.issue_date is None or not locked.scope_summary.strip():
        raise ValidationError("Issue date and client-facing scope summary are required.")
    now = timezone.now()
    calculation_hash = _fingerprint(calculation.as_dict())
    client_snapshot = _client_snapshot(locked, actor, now)
    commercial_snapshot = _commercial_snapshot(locked, calculation, calculation_hash)
    snapshot_hash = _fingerprint(
        {
            "client": client_snapshot,
            "commercial": commercial_snapshot,
            "content": {
                "introduction": locked.introduction,
                "scope_summary": locked.scope_summary,
                "commercial_notes": locked.commercial_notes,
                "terms_conditions": locked.terms_conditions,
            },
        }
    )
    estimate.status = EstimateVersion.Status.FROZEN
    estimate.frozen_by = actor
    estimate.frozen_at = now
    estimate.calculation_fingerprint = calculation_hash
    estimate.save(update_fields=["status", "frozen_by", "frozen_at", "calculation_fingerprint"])
    locked.status = ProposalVersion.Status.FINALIZED
    locked.proposal_number = client_snapshot["proposal_number"]
    locked.client_project_snapshot = client_snapshot
    locked.commercial_snapshot = commercial_snapshot
    locked.snapshot_fingerprint = snapshot_hash
    locked.finalized_by = actor
    locked.finalized_at = now
    locked.finalization_note = note.strip()
    locked.save(
        update_fields=[
            "status",
            "proposal_number",
            "client_project_snapshot",
            "commercial_snapshot",
            "snapshot_fingerprint",
            "finalized_by",
            "finalized_at",
            "finalization_note",
        ]
    )
    for action, target, metadata in (
        ("estimate.version_frozen", estimate, {"proposal_version_id": locked.pk}),
        (
            "proposal.finalized",
            locked,
            {"estimate_version_id": estimate.pk, "fingerprint": snapshot_hash},
        ),
    ):
        record_event(
            organization=locked.proposal.organization,
            project=project,
            actor=actor,
            action_code=action,
            target=target,
            metadata=metadata,
        )
    return locked
