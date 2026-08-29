import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.organizations.models import Membership, Organization
from apps.organizations.permissions import OrganizationReadWritePermission
from apps.organizations.services import active_membership

pytestmark = pytest.mark.django_db


def test_membership_role_relationship_and_uniqueness(user, organization, membership):
    assert membership.user == user
    assert membership.organization == organization
    assert membership.role == Membership.Role.ESTIMATOR_OPERATOR
    with pytest.raises(IntegrityError):
        Membership.objects.create(user=user, organization=organization, role=Membership.Role.VIEWER)


def test_inactive_and_expired_memberships_are_not_active(user, organization, membership):
    membership.is_active = False
    membership.save()
    assert active_membership(user, organization) is None

    membership.is_active = True
    membership.ends_at = timezone.now()
    membership.save()
    assert active_membership(user, organization) is None


class OrganizationView:
    def __init__(self, organization):
        self.organization = organization


@pytest.mark.parametrize(
    ("role", "method", "allowed"),
    [
        (Membership.Role.ADMIN, "post", True),
        (Membership.Role.ESTIMATOR_OPERATOR, "post", True),
        (Membership.Role.VIEWER, "get", True),
        (Membership.Role.VIEWER, "post", False),
    ],
)
def test_role_permissions(user, organization, membership, role, method, allowed):
    membership.role = role
    membership.save()
    request = getattr(APIRequestFactory(), method)("/")
    force_authenticate(request, user=user)

    result = OrganizationReadWritePermission().has_permission(
        Request(request), OrganizationView(organization)
    )
    assert result is allowed


def test_cross_organization_access_is_denied(user, organization, membership):
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    request = APIRequestFactory().get("/")
    force_authenticate(request, user=user)

    assert not OrganizationReadWritePermission().has_permission(
        Request(request), OrganizationView(other)
    )


def test_inactive_user_has_no_active_membership(organization):
    user = get_user_model().objects.create_user(
        email="disabled@example.com", password="pass", is_active=False
    )
    Membership.objects.create(user=user, organization=organization, role=Membership.Role.ADMIN)
    assert active_membership(user, organization) is None
