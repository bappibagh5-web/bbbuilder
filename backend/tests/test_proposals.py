import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import AuditEvent, Project, ProjectContact
from apps.proposals.models import Estimate, EstimateVersion, ProposalVersion
from apps.proposals.services import (
    create_estimate,
    create_estimate_version,
    create_proposal,
    create_proposal_version,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="M4-01",
        name="Proposal Foundation",
        client_name="Example Client",
        project_timezone="America/Toronto",
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def workspace_url(project, organization=None):
    return reverse(
        "proposal-workspace",
        kwargs={
            "organization_slug": (organization or project.organization).slug,
            "project_pk": project.pk,
        },
    )


def test_operator_creates_versioned_estimate_and_audit(project, user, membership):
    estimate, first = create_estimate(project=project, actor=user)
    second = create_estimate_version(estimate=estimate, actor=user)
    assert first.version == 1
    assert second.version == 2
    assert second.supersedes == first
    assert list(estimate.versions.values_list("status", flat=True)) == ["draft", "draft"]
    assert AuditEvent.objects.filter(
        project=project, action_code="estimate.created", target_id=str(estimate.pk)
    ).exists()
    assert AuditEvent.objects.filter(
        project=project, action_code="estimate.version_created", target_id=str(second.pk)
    ).exists()


def test_estimate_versions_are_immutable_and_database_constrained(project, user, membership):
    estimate, first = create_estimate(project=project, actor=user)
    first.version = 8
    with pytest.raises(ValidationError, match="immutable"):
        first.save()
    with pytest.raises(IntegrityError), transaction.atomic():
        EstimateVersion.objects.bulk_create(
            [
                EstimateVersion(
                    estimate=estimate,
                    version=1,
                    status=EstimateVersion.Status.DRAFT,
                    created_by=user,
                )
            ]
        )


def test_proposal_version_binds_exact_estimate_version_and_preserves_history(
    project, user, membership
):
    estimate, estimate_v1 = create_estimate(project=project, actor=user)
    proposal, proposal_v1 = create_proposal(
        estimate=estimate, estimate_version=estimate_v1, actor=user
    )
    estimate_v2 = create_estimate_version(estimate=estimate, actor=user)
    proposal_v2 = create_proposal_version(
        proposal=proposal, estimate_version=estimate_v2, actor=user
    )
    proposal_v1.refresh_from_db()
    assert proposal_v1.estimate_version == estimate_v1
    assert proposal_v2.estimate_version == estimate_v2
    assert proposal_v2.supersedes == proposal_v1
    assert proposal_v1.status == ProposalVersion.Status.DRAFT


def test_proposal_contact_and_cross_project_bindings_are_validated(
    project, user, organization, membership
):
    estimate, estimate_v1 = create_estimate(project=project, actor=user)
    other = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="OTHER",
        name="Other Project",
        project_timezone="America/Toronto",
    )
    wrong_contact = ProjectContact.objects.create(project=other, person_name="Wrong Client")
    with pytest.raises(ValidationError, match="does not belong"):
        create_proposal(
            estimate=estimate,
            estimate_version=estimate_v1,
            actor=user,
            client_contact=wrong_contact,
        )


def test_workspace_is_readable_by_viewer_but_mutation_is_denied(project, user, membership):
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=["role"])
    client = client_for(user)
    assert client.get(workspace_url(project)).status_code == 200
    create_url = reverse(
        "estimate-create",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    assert client.post(create_url, {}, format="json").status_code == 403
    assert Estimate.objects.count() == 0


def test_workspace_and_creates_are_organization_and_project_scoped(project, user):
    other_user = get_user_model().objects.create_user(email="other@example.com", password="pass")
    other_org = Organization.objects.create(name="Other Org", slug="other-org")
    Membership.objects.create(user=other_user, organization=other_org, role=Membership.Role.ADMIN)
    client = client_for(other_user)
    assert client.get(workspace_url(project, other_org)).status_code == 404
    assert client.get(workspace_url(project)).status_code == 403


def test_api_creates_explicit_drafts_without_financial_or_award_side_effects(
    project, user, membership
):
    client = client_for(user)
    estimate_url = reverse(
        "estimate-create",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    response = client.post(estimate_url, {}, format="json")
    assert response.status_code == 201
    estimate_version_id = response.data["estimate"]["versions"][0]["id"]
    proposal_url = reverse(
        "proposal-create",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    response = client.post(
        proposal_url, {"estimate_version_id": estimate_version_id}, format="json"
    )
    assert response.status_code == 201
    assert response.data["proposal"]["versions"][0]["estimate_version_id"] == estimate_version_id
    assert set(response.data["proposal"]["versions"][0]) == {
        "id",
        "version",
        "status",
        "status_label",
        "estimate_version_id",
        "estimate_version",
        "supersedes_id",
        "created_by",
        "created_at",
    }


def test_archived_project_is_read_only(project, user, membership):
    project.is_active = False
    project.save(update_fields=["is_active"])
    create_url = reverse(
        "estimate-create",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    response = client_for(user).post(create_url, {}, format="json")
    assert response.status_code == 400
    assert "Archived projects are read-only" in str(response.data)
