import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.projects.models import AuditEvent

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def members_url(organization):
    return f"/api/v1/organizations/{organization.slug}/memberships/"


def member_url(organization, membership):
    return f"{members_url(organization)}{membership.pk}/"


def make_user(email):
    return get_user_model().objects.create_user(email=email, password="valid-pass")


def test_active_members_can_read_safe_organization_settings(user, organization, membership):
    response = client_for(user).get(f"/api/v1/organizations/{organization.slug}/settings/")

    assert response.status_code == 200
    assert response.data["organization"]["name"] == organization.name
    assert response.data["access"]["role"] == Membership.Role.ESTIMATOR_OPERATOR
    assert response.data["access"]["can_manage_members"] is False


def test_admin_adds_only_an_existing_user_and_action_is_audited(user, organization, membership):
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=["role"])
    added_user = make_user("viewer@example.com")

    response = client_for(user).post(
        members_url(organization),
        {"email": " Viewer@Example.com ", "role": Membership.Role.VIEWER},
        format="json",
    )

    assert response.status_code == 201
    added = Membership.objects.get(organization=organization, user=added_user)
    assert added.role == Membership.Role.VIEWER
    event = AuditEvent.objects.get(action_code="organization_membership.added")
    assert event.actor == user
    assert event.metadata == {
        "membership_id": added.pk,
        "user_id": added_user.pk,
        "role": Membership.Role.VIEWER,
    }

    unknown = client_for(user).post(
        members_url(organization),
        {"email": "unknown@example.com", "role": Membership.Role.VIEWER},
        format="json",
    )
    assert unknown.status_code == 400
    assert "invitations are not implemented" in str(unknown.data).lower()


def test_admin_changes_role_and_deactivates_then_reactivates_without_deleting_history(
    user, organization, membership
):
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=["role"])
    target_user = make_user("operator@example.com")
    target = Membership.objects.create(
        organization=organization,
        user=target_user,
        role=Membership.Role.VIEWER,
    )

    role_response = client_for(user).patch(
        member_url(organization, target),
        {"role": Membership.Role.ESTIMATOR_OPERATOR},
        format="json",
    )
    assert role_response.status_code == 200
    target.refresh_from_db()
    assert target.role == Membership.Role.ESTIMATOR_OPERATOR

    inactive = client_for(user).patch(
        member_url(organization, target), {"is_active": False}, format="json"
    )
    assert inactive.status_code == 200
    target.refresh_from_db()
    assert target.is_active is False
    assert target.ends_at is not None

    active = client_for(user).patch(
        member_url(organization, target), {"is_active": True}, format="json"
    )
    assert active.status_code == 200
    target.refresh_from_db()
    assert target.is_active is True
    assert target.ends_at is None
    assert Membership.objects.filter(pk=target.pk).count() == 1
    assert set(
        AuditEvent.objects.filter(target_id=str(target.pk)).values_list("action_code", flat=True)
    ) == {
        "organization_membership.role_changed",
        "organization_membership.deactivated",
        "organization_membership.reactivated",
    }


def test_admin_cannot_lock_out_self_or_remove_last_active_admin(user, organization, membership):
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=["role"])

    self_demote = client_for(user).patch(
        member_url(organization, membership),
        {"role": Membership.Role.VIEWER},
        format="json",
    )
    self_deactivate = client_for(user).patch(
        member_url(organization, membership), {"is_active": False}, format="json"
    )

    assert self_demote.status_code == 400
    assert self_deactivate.status_code == 400
    membership.refresh_from_db()
    assert membership.role == Membership.Role.ADMIN
    assert membership.is_active is True


@pytest.mark.parametrize("role", [Membership.Role.ESTIMATOR_OPERATOR, Membership.Role.VIEWER])
def test_non_admin_cannot_mutate_memberships(user, organization, membership, role):
    membership.role = role
    membership.save(update_fields=["role"])
    existing_user = make_user(f"{role}@example.com")

    response = client_for(user).post(
        members_url(organization),
        {"email": existing_user.email, "role": Membership.Role.VIEWER},
        format="json",
    )

    assert response.status_code == 403
    assert not Membership.objects.filter(organization=organization, user=existing_user).exists()


def test_cross_organization_membership_is_not_visible_or_mutable(user, organization, membership):
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=["role"])
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    other_member = Membership.objects.create(
        organization=other,
        user=make_user("other@example.com"),
        role=Membership.Role.ADMIN,
    )

    listing = client_for(user).get(members_url(organization))
    mutation = client_for(user).patch(
        member_url(organization, other_member), {"is_active": False}, format="json"
    )

    assert listing.status_code == 200
    assert [item["id"] for item in listing.data["results"]] == [membership.pk]
    assert mutation.status_code == 404
    other_member.refresh_from_db()
    assert other_member.is_active is True


def test_membership_delete_endpoint_does_not_exist(user, organization, membership):
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=["role"])
    assert client_for(user).delete(member_url(organization, membership)).status_code == 405
