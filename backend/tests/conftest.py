import pytest
from django.contrib.auth import get_user_model

from apps.organizations.models import Membership, Organization


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        email="estimator@example.com",
        password="valid-pass",
        first_name="Alex",
        last_name="Morgan",
    )


@pytest.fixture
def organization():
    return Organization.objects.create(name="BB Builders Ltd.", slug="bb-builders")


@pytest.fixture
def membership(user, organization):
    return Membership.objects.create(
        user=user,
        organization=organization,
        role=Membership.Role.ESTIMATOR_OPERATOR,
    )
