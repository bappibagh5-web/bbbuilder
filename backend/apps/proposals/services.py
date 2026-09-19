from django.core.exceptions import ValidationError
from django.db import transaction

from apps.organizations.models import Membership
from apps.organizations.services import active_membership
from apps.projects.audit import record_event

from .models import Estimate, EstimateVersion, Proposal, ProposalVersion


def _require_operator(*, actor, organization):
    membership = active_membership(actor, organization)
    if membership is None or membership.role not in {
        Membership.Role.ADMIN,
        Membership.Role.ESTIMATOR_OPERATOR,
    }:
        raise ValidationError("An active Admin or Estimator membership is required.")


def _require_active_project(project):
    if not project.is_active:
        raise ValidationError("Archived projects are read-only.")


@transaction.atomic
def create_estimate(*, project, actor, title=None):
    _require_operator(actor=actor, organization=project.organization)
    _require_active_project(project)
    if Estimate.objects.filter(project=project).exists():
        raise ValidationError("This project already has an estimate.")
    estimate = Estimate.objects.create(
        organization=project.organization,
        project=project,
        title=(title or f"{project.name} Estimate").strip(),
        created_by=actor,
    )
    version = EstimateVersion.objects.create(
        estimate=estimate, version=1, status=EstimateVersion.Status.DRAFT, created_by=actor
    )
    record_event(
        organization=project.organization,
        project=project,
        actor=actor,
        action_code="estimate.created",
        target=estimate,
        metadata={"estimate_version_id": version.pk, "version": version.version},
    )
    return estimate, version


@transaction.atomic
def create_estimate_version(*, estimate, actor):
    _require_operator(actor=actor, organization=estimate.organization)
    _require_active_project(estimate.project)
    locked = Estimate.objects.select_for_update().get(pk=estimate.pk)
    predecessor = locked.versions.order_by("-version").first()
    version = EstimateVersion.objects.create(
        estimate=locked,
        version=(predecessor.version + 1 if predecessor else 1),
        supersedes=predecessor,
        status=EstimateVersion.Status.DRAFT,
        created_by=actor,
    )
    record_event(
        organization=locked.organization,
        project=locked.project,
        actor=actor,
        action_code="estimate.version_created",
        target=version,
        metadata={"estimate_id": locked.pk, "version": version.version},
    )
    return version


@transaction.atomic
def create_proposal(*, estimate, estimate_version, actor, title=None, client_contact=None):
    _require_operator(actor=actor, organization=estimate.organization)
    _require_active_project(estimate.project)
    if estimate_version.estimate_id != estimate.pk:
        raise ValidationError("The selected estimate version does not belong to this estimate.")
    if client_contact is not None and client_contact.project_id != estimate.project_id:
        raise ValidationError("The selected contact does not belong to this project.")
    if Proposal.objects.filter(project=estimate.project).exists():
        raise ValidationError("This project already has a proposal.")
    proposal = Proposal.objects.create(
        organization=estimate.organization,
        project=estimate.project,
        estimate=estimate,
        title=(title or f"{estimate.project.name} Proposal").strip(),
        client_contact=client_contact,
        created_by=actor,
    )
    version = ProposalVersion.objects.create(
        proposal=proposal,
        estimate_version=estimate_version,
        version=1,
        status=ProposalVersion.Status.DRAFT,
        created_by=actor,
    )
    record_event(
        organization=proposal.organization,
        project=proposal.project,
        actor=actor,
        action_code="proposal.created",
        target=proposal,
        metadata={
            "proposal_version_id": version.pk,
            "version": version.version,
            "estimate_version_id": estimate_version.pk,
        },
    )
    return proposal, version


@transaction.atomic
def create_proposal_version(*, proposal, estimate_version, actor):
    _require_operator(actor=actor, organization=proposal.organization)
    _require_active_project(proposal.project)
    if estimate_version.estimate_id != proposal.estimate_id:
        raise ValidationError("The selected estimate version does not belong to this proposal.")
    locked = Proposal.objects.select_for_update().get(pk=proposal.pk)
    predecessor = locked.versions.order_by("-version").first()
    version = ProposalVersion.objects.create(
        proposal=locked,
        estimate_version=estimate_version,
        version=(predecessor.version + 1 if predecessor else 1),
        supersedes=predecessor,
        status=ProposalVersion.Status.DRAFT,
        created_by=actor,
    )
    record_event(
        organization=locked.organization,
        project=locked.project,
        actor=actor,
        action_code="proposal.version_created",
        target=version,
        metadata={
            "proposal_id": locked.pk,
            "version": version.version,
            "estimate_version_id": estimate_version.pk,
        },
    )
    return version
