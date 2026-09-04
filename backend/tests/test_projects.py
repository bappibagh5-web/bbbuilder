from datetime import date, datetime
from decimal import Decimal

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.admin import ProjectAdmin, ProjectContactAdmin
from apps.projects.models import AuditEvent, Project, ProjectContact

pytestmark = pytest.mark.django_db


def project_values(organization, user, **overrides):
    values = {
        "organization": organization,
        "created_by": user,
        "project_number": "BB-2026-041",
        "name": "Retail Store Tenant Improvement",
        "project_timezone": "America/Vancouver",
    }
    values.update(overrides)
    return values


def project_payload(**overrides):
    values = {
        "project_number": "BB-2026-041",
        "name": "Retail Store Tenant Improvement",
        "project_timezone": "America/Vancouver",
        "project_type": "retail",
    }
    values.update(overrides)
    return values


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def projects_url(organization):
    return reverse("project-list", kwargs={"organization_slug": organization.slug})


def project_url(project, organization=None):
    return reverse(
        "project-detail",
        kwargs={
            "organization_slug": (organization or project.organization).slug,
            "pk": project.pk,
        },
    )


def contacts_url(project, organization=None):
    return reverse(
        "project-contact-list",
        kwargs={
            "organization_slug": (organization or project.organization).slug,
            "project_pk": project.pk,
        },
    )


def contact_url(contact, organization=None, project=None):
    return reverse(
        "project-contact-detail",
        kwargs={
            "organization_slug": (organization or contact.project.organization).slug,
            "project_pk": (project or contact.project).pk,
            "pk": contact.pk,
        },
    )


def audit_events_url(project, organization=None):
    return reverse(
        "project-audit-event-list",
        kwargs={
            "organization_slug": (organization or project.organization).slug,
            "project_pk": project.pk,
        },
    )


@pytest.fixture
def project(organization, user):
    return Project.objects.create(**project_values(organization, user))


def set_role(membership, role):
    membership.role = role
    membership.save(update_fields=("role",))


def test_project_defaults_and_relationships(organization, user):
    project = Project.objects.create(**project_values(organization, user))

    assert project.status == Project.Status.DRAFT
    assert project.is_active is True
    assert project.organization == organization
    assert project.created_by == user


@pytest.mark.parametrize("field", ["project_number", "name", "project_timezone"])
def test_project_required_fields(organization, user, field):
    values = project_values(organization, user)
    values[field] = ""
    project = Project(**values)

    with pytest.raises(ValidationError):
        project.full_clean()


def test_project_timezone_validation(organization, user):
    valid = Project(**project_values(organization, user, project_timezone="America/Toronto"))
    valid.full_clean()

    invalid = Project(**project_values(organization, user, project_timezone="Mars/Olympus"))
    with pytest.raises(ValidationError):
        invalid.full_clean()


@pytest.mark.parametrize("area", [Decimal("0"), Decimal("-1")])
def test_project_estimated_area_must_be_positive(organization, user, area):
    project = Project(**project_values(organization, user, estimated_area=area))
    with pytest.raises(ValidationError):
        project.full_clean()


def test_project_positive_estimated_area_is_valid(organization, user):
    project = Project(**project_values(organization, user, estimated_area=Decimal("8450")))
    project.full_clean()


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "invented"), ("project_type", "warehouse")],
)
def test_project_controlled_choices(organization, user, field, value):
    project = Project(**project_values(organization, user, **{field: value}))
    with pytest.raises(ValidationError):
        project.full_clean()


def test_project_number_is_case_insensitively_unique_per_organization(organization, user):
    Project.objects.create(**project_values(organization, user, project_number="BB-001"))

    with pytest.raises(IntegrityError), transaction.atomic():
        Project.objects.create(**project_values(organization, user, project_number="bb-001"))


def test_same_project_number_is_allowed_in_different_organizations(organization, user):
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    Project.objects.create(**project_values(organization, user, project_number="BB-001"))
    other_project = Project.objects.create(**project_values(other, user, project_number="bb-001"))
    assert other_project.pk


def test_project_contact_model_validation(project):
    contact = ProjectContact(
        project=project,
        company_name="Example Architect",
        email="architect@example.com",
        contact_role=ProjectContact.Role.ARCHITECT,
    )
    contact.full_clean()
    contact.save()
    assert contact.project == project
    assert contact.is_active is True

    contact.is_active = False
    contact.save()
    contact.refresh_from_db()
    assert contact.is_active is False


@pytest.mark.parametrize(
    ("field", "value"),
    [("email", "not-an-email"), ("contact_role", "subcontractor")],
)
def test_project_contact_rejects_invalid_values(project, field, value):
    contact = ProjectContact(project=project, **{field: value})
    with pytest.raises(ValidationError):
        contact.full_clean()


def test_unauthenticated_project_api_is_denied(organization):
    assert APIClient().get(projects_url(organization)).status_code in {401, 403}


@pytest.mark.parametrize("role", [Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR])
def test_admin_and_estimator_can_create_read_and_update(organization, user, membership, role):
    set_role(membership, role)
    client = authenticated_client(user)
    created = client.post(projects_url(organization), project_payload(), format="json")
    assert created.status_code == 201, created.data
    detail_url = project_url(Project.objects.get(pk=created.data["id"]))
    assert client.get(detail_url).status_code == 200
    updated = client.patch(detail_url, {"client_name": "Demo Client"}, format="json")
    assert updated.status_code == 200
    assert updated.data["client_name"] == "Demo Client"


def test_viewer_is_read_only(organization, user, membership, project):
    set_role(membership, Membership.Role.VIEWER)
    client = authenticated_client(user)
    assert client.get(projects_url(organization)).status_code == 200
    assert client.get(project_url(project)).status_code == 200
    assert (
        client.post(projects_url(organization), project_payload(), format="json").status_code == 403
    )
    assert client.patch(project_url(project), {"name": "No"}, format="json").status_code == 403


def test_inactive_membership_is_denied(organization, user, membership):
    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert authenticated_client(user).get(projects_url(organization)).status_code == 403


def test_estimator_cannot_archive_or_reactivate_project(user, membership, project):
    client = authenticated_client(user)
    response = client.patch(project_url(project), {"is_active": False}, format="json")
    assert response.status_code == 403
    project.refresh_from_db()
    assert project.is_active is True

    project.is_active = False
    project.save(update_fields=("is_active",))
    response = client.patch(project_url(project), {"is_active": True}, format="json")
    assert response.status_code == 403


def test_admin_can_archive_and_reactivate_and_project_remains_visible(
    organization, user, membership, project
):
    set_role(membership, Membership.Role.ADMIN)
    client = authenticated_client(user)
    assert (
        client.patch(project_url(project), {"is_active": False}, format="json").status_code == 200
    )
    project.refresh_from_db()
    assert project.is_active is False
    assert client.get(project_url(project)).status_code == 200
    assert project.pk in [
        item["id"] for item in client.get(projects_url(organization)).data["results"]
    ]
    assert client.patch(project_url(project), {"is_active": True}, format="json").status_code == 200


def test_project_delete_is_unavailable(user, membership, project):
    assert authenticated_client(user).delete(project_url(project)).status_code == 405
    assert Project.objects.filter(pk=project.pk).exists()


def test_cross_organization_isolation_and_list_scoping(organization, user, membership, project):
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    other_project = Project.objects.create(**project_values(other, user, project_number="OTHER-1"))
    client = authenticated_client(user)
    assert client.get(projects_url(other)).status_code == 403
    assert client.get(project_url(other_project, organization)).status_code == 404

    Membership.objects.create(
        organization=other, user=user, role=Membership.Role.ESTIMATOR_OPERATOR
    )
    ids = [item["id"] for item in client.get(projects_url(organization)).data["results"]]
    assert project.pk in ids
    assert other_project.pk not in ids


def test_project_organization_cannot_be_forged(organization, user, membership):
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    response = authenticated_client(user).post(
        projects_url(organization),
        project_payload(organization=other.slug),
        format="json",
    )
    assert response.status_code == 201
    assert Project.objects.get(pk=response.data["id"]).organization == organization


def test_project_api_validation(organization, user, membership, project):
    client = authenticated_client(user)
    duplicate = client.post(
        projects_url(organization), project_payload(project_number="bb-2026-041"), format="json"
    )
    assert duplicate.status_code == 400
    assert (
        client.post(
            projects_url(organization),
            project_payload(project_timezone="Invalid/Zone"),
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            projects_url(organization), project_payload(estimated_area="0"), format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            projects_url(organization), project_payload(status="invalid"), format="json"
        ).status_code
        == 400
    )


def test_project_put_is_supported(organization, user, membership, project):
    payload = project_payload(name="Updated by PUT", project_number=project.project_number)
    response = authenticated_client(user).put(project_url(project), payload, format="json")
    assert response.status_code == 200, response.data
    assert response.data["name"] == "Updated by PUT"


def test_deadlines_and_date_only_values_round_trip(organization, user, membership):
    response = authenticated_client(user).post(
        projects_url(organization),
        project_payload(
            bid_deadline="2026-09-15T14:30:00-04:00",
            questions_deadline="2026-09-10T12:00:00Z",
            site_visit_date="2026-09-05",
            planned_start_date="2026-10-01",
            substantial_completion_date="2026-12-15",
            opening_or_handover_date="2027-01-03",
        ),
        format="json",
    )
    assert response.status_code == 201, response.data
    project = Project.objects.get(pk=response.data["id"])
    assert timezone.is_aware(project.bid_deadline)
    assert project.bid_deadline == datetime.fromisoformat("2026-09-15T14:30:00-04:00")
    assert project.site_visit_date == date(2026, 9, 5)
    assert project.opening_or_handover_date == date(2027, 1, 3)

    retrieved = authenticated_client(user).get(project_url(project))
    assert (
        datetime.fromisoformat(retrieved.data["bid_deadline"].replace("Z", "+00:00"))
        == project.bid_deadline
    )
    assert retrieved.data["site_visit_date"] == "2026-09-05"
    assert retrieved.data["opening_or_handover_date"] == "2027-01-03"


def test_deadline_requires_explicit_offset(organization, user, membership):
    response = authenticated_client(user).post(
        projects_url(organization),
        project_payload(bid_deadline="2026-09-15T14:30:00"),
        format="json",
    )
    assert response.status_code == 400


def test_contact_api_crud_permissions_and_ownership(organization, user, membership, project):
    client = authenticated_client(user)
    created = client.post(
        contacts_url(project),
        {
            "project": 999999,
            "company_name": "Demo Architects",
            "person_name": "Jamie Chen",
            "email": "jamie@example.com",
            "contact_role": "architect",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    contact = ProjectContact.objects.get(pk=created.data["id"])
    assert contact.project == project
    assert client.get(contacts_url(project)).status_code == 200
    assert client.get(contact_url(contact)).status_code == 200
    assert (
        client.patch(contact_url(contact), {"is_active": False}, format="json").status_code == 200
    )
    contact.refresh_from_db()
    assert contact.is_active is False
    assert client.patch(contact_url(contact), {"is_active": True}, format="json").status_code == 200
    put = client.put(
        contact_url(contact),
        {"person_name": "Jamie Chen", "email": "new@example.com", "contact_role": "architect"},
        format="json",
    )
    assert put.status_code == 200
    assert client.delete(contact_url(contact)).status_code == 405
    assert ProjectContact.objects.filter(pk=contact.pk).exists()


def test_contact_validation_and_viewer_permissions(user, membership, project):
    client = authenticated_client(user)
    assert (
        client.post(
            contacts_url(project), {"email": "bad", "contact_role": "invalid"}, format="json"
        ).status_code
        == 400
    )
    contact = ProjectContact.objects.create(project=project, person_name="Viewer Contact")
    set_role(membership, Membership.Role.VIEWER)
    assert client.get(contacts_url(project)).status_code == 200
    assert client.get(contact_url(contact)).status_code == 200
    assert (
        client.post(contacts_url(project), {"person_name": "No"}, format="json").status_code == 403
    )
    assert (
        client.patch(contact_url(contact), {"person_name": "No"}, format="json").status_code == 403
    )


def test_cross_organization_contact_isolation(organization, user, membership, project):
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    other_project = Project.objects.create(**project_values(other, user, project_number="OTHER-1"))
    other_contact = ProjectContact.objects.create(project=other_project, person_name="Other")
    client = authenticated_client(user)
    assert client.get(contacts_url(other_project)).status_code == 403
    assert (
        client.get(
            contact_url(other_contact, organization=organization, project=project)
        ).status_code
        == 404
    )


def test_api_project_audit_events(organization, user, membership):
    set_role(membership, Membership.Role.ADMIN)
    client = authenticated_client(user)
    created = client.post(projects_url(organization), project_payload(), format="json")
    project = Project.objects.get(pk=created.data["id"])
    event = AuditEvent.objects.get(action_code="project.created")
    assert event.actor == user
    assert event.organization == organization
    assert event.project == project
    assert event.metadata["after"]["project_number"] == project.project_number

    client.patch(project_url(project), {"client_name": "Changed"}, format="json")
    assert AuditEvent.objects.filter(action_code="project.updated", project=project).exists()
    client.patch(project_url(project), {"is_active": False}, format="json")
    client.patch(project_url(project), {"is_active": True}, format="json")
    assert AuditEvent.objects.filter(action_code="project.archived", project=project).exists()
    assert AuditEvent.objects.filter(action_code="project.reactivated", project=project).exists()


def test_api_contact_audit_events(user, membership, project):
    client = authenticated_client(user)
    created = client.post(
        contacts_url(project), {"person_name": "Jamie", "contact_role": "client"}, format="json"
    )
    contact = ProjectContact.objects.get(pk=created.data["id"])
    assert AuditEvent.objects.filter(
        action_code="project_contact.created", actor=user, project=project
    ).exists()
    client.patch(contact_url(contact), {"phone": "555-0100"}, format="json")
    client.patch(contact_url(contact), {"is_active": False}, format="json")
    client.patch(contact_url(contact), {"is_active": True}, format="json")
    assert AuditEvent.objects.filter(action_code="project_contact.updated").exists()
    assert AuditEvent.objects.filter(action_code="project_contact.deactivated").exists()
    assert AuditEvent.objects.filter(action_code="project_contact.reactivated").exists()


def test_project_audit_api_is_scoped_read_only_and_omits_metadata(
    organization, user, membership, project
):
    event = AuditEvent.objects.create(
        organization=organization,
        project=project,
        actor=user,
        action_code="project.created",
        target_type="projects.project",
        target_id=str(project.pk),
        metadata={"private_detail": "not exposed"},
    )
    client = authenticated_client(user)

    response = client.get(audit_events_url(project))

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"] == [
        {
            "id": event.pk,
            "action_code": "project.created",
            "target_type": "projects.project",
            "target_id": str(project.pk),
            "actor": "Alex Morgan",
            "occurred_at": response.data["results"][0]["occurred_at"],
        }
    ]
    assert "metadata" not in response.data["results"][0]
    assert client.post(audit_events_url(project), {}, format="json").status_code == 405
    assert client.patch(audit_events_url(project), {}, format="json").status_code == 405
    assert client.delete(audit_events_url(project)).status_code == 405

    set_role(membership, Membership.Role.VIEWER)
    assert client.get(audit_events_url(project)).status_code == 200


def test_project_audit_api_denies_inactive_and_cross_organization_access(
    organization, user, membership, project
):
    other = Organization.objects.create(name="Other Builder", slug="other-audit-builder")
    other_project = Project.objects.create(
        **project_values(other, user, project_number="OTHER-AUDIT-1")
    )
    client = authenticated_client(user)

    assert client.get(audit_events_url(other_project)).status_code == 403
    assert client.get(audit_events_url(other_project, organization=organization)).status_code == 404

    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert client.get(audit_events_url(project)).status_code == 403


def test_django_admin_project_and_contact_mutations_are_audited(organization, user):
    request = RequestFactory().post("/admin/")
    request.user = user
    project_admin = ProjectAdmin(Project, admin.site)
    project = Project(**project_values(organization, user))
    project_admin.save_model(request, project, form=None, change=False)
    assert AuditEvent.objects.filter(
        action_code="project.created", actor=user, project=project
    ).exists()

    project.name = "Admin Updated Project"
    project_admin.save_model(request, project, form=None, change=True)
    assert AuditEvent.objects.filter(
        action_code="project.updated", actor=user, project=project
    ).exists()
    project.is_active = False
    project_admin.save_model(request, project, form=None, change=True)
    assert AuditEvent.objects.filter(
        action_code="project.archived", actor=user, project=project
    ).exists()
    assert project_admin.has_delete_permission(request, project) is False

    contact_admin = ProjectContactAdmin(ProjectContact, admin.site)
    contact = ProjectContact(project=project, person_name="Admin Contact")
    contact_admin.save_model(request, contact, form=None, change=False)
    assert AuditEvent.objects.filter(
        action_code="project_contact.created", actor=user, project=project
    ).exists()

    contact.is_active = False
    contact_admin.save_model(request, contact, form=None, change=True)
    assert AuditEvent.objects.filter(
        action_code="project_contact.deactivated", actor=user, project=project
    ).exists()
    assert contact_admin.has_delete_permission(request, contact) is False
