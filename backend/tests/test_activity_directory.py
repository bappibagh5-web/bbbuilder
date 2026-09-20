from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import AuditEvent, Project

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def directory_url(organization):
    return reverse(
        "organization-activity-directory",
        kwargs={"organization_slug": organization.slug},
    )


def project_for(organization, user, number="ACT-1", name="Activity Project"):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number=number,
        name=name,
        project_timezone="America/Toronto",
    )


def event_for(organization, project, user, action, metadata=None):
    return AuditEvent.objects.create(
        organization=organization,
        project=project,
        actor=user,
        action_code=action,
        target_type="projects.project",
        target_id=str(project.pk) if project else "configuration",
        metadata=metadata or {},
    )


def test_activity_directory_is_safe_newest_first_and_viewer_readable(
    organization, user, membership
):
    project = project_for(organization, user)
    older = event_for(organization, project, user, "project.created")
    newest = event_for(
        organization,
        project,
        user,
        "proposal.finalized",
        {"secret": "never expose", "body": "private proposal data"},
    )
    AuditEvent.objects.filter(pk=older.pk).update(occurred_at=timezone.now() - timedelta(days=1))
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=["role"])

    response = client_for(user).get(directory_url(organization))

    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [newest.pk, older.pk]
    item = response.data["results"][0]
    assert item["label"] == "Proposal finalized"
    assert item["family_label"] == "Proposals"
    assert item["actor"] == "Alex Morgan"
    assert item["project"] == {
        "id": project.pk,
        "project_number": "ACT-1",
        "name": "Activity Project",
    }
    assert item["route"] == f"/projects/{project.pk}/proposal"
    assert "metadata" not in item
    assert "action_code" not in item
    assert "secret" not in str(response.data)
    assert client_for(user).post(directory_url(organization), {}).status_code == 405


def test_activity_directory_filters_and_paginates(organization, user, membership):
    first = project_for(organization, user, "ACT-1", "First")
    second = project_for(organization, user, "ACT-2", "Second")
    event_for(organization, first, user, "document.created")
    event_for(organization, first, user, "scope_package.ready")
    event_for(organization, second, user, "proposal.finalized")

    response = client_for(user).get(
        directory_url(organization),
        {"project": first.pk, "family": "documents", "page_size": 1},
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["page_size"] == 1
    assert response.data["results"][0]["family"] == "documents"
    assert len(response.data["filters"]["projects"]) == 2
    assert (
        client_for(user).get(directory_url(organization), {"family": "invalid"}).status_code == 400
    )


def test_activity_directory_is_organization_scoped_and_requires_membership(
    organization, user, membership
):
    own_project = project_for(organization, user)
    own = event_for(organization, own_project, user, "project.created")
    other = Organization.objects.create(name="Other", slug="other-activity")
    other_project = project_for(other, user, "OTHER-1", "Other Project")
    event_for(other, other_project, user, "proposal.finalized")

    response = client_for(user).get(directory_url(organization))
    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [own.pk]
    assert client_for(user).get(directory_url(other)).status_code == 403


def test_activity_directory_unknown_and_org_events_degrade_safely(organization, user, membership):
    unknown = event_for(organization, None, None, "future_internal.operation", {"token": "x"})
    response = client_for(user).get(directory_url(organization), {"family": "other"})
    assert response.status_code == 200
    assert response.data["results"] == [
        {
            "id": unknown.pk,
            "timestamp": response.data["results"][0]["timestamp"],
            "actor": "System",
            "project": None,
            "family": "other",
            "family_label": "Other",
            "label": "Activity recorded",
            "target_type": "projects.project",
            "target_reference": None,
            "route": None,
        }
    ]
    assert "future_internal" not in str(response.data)
    assert "token" not in str(response.data)


def test_activity_directory_query_count_is_bounded(organization, user, membership):
    project = project_for(organization, user)
    for index in range(30):
        event_for(organization, project, user, f"document.event_{index}")
    client = client_for(user)
    with CaptureQueriesContext(connection) as queries:
        response = client.get(directory_url(organization), {"page_size": 25})
    assert response.status_code == 200
    assert len(response.data["results"]) == 25
    assert len(queries) <= 7
