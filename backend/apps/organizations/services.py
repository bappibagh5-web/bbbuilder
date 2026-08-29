from django.db.models import Q
from django.utils import timezone

from .models import Membership, Organization


def active_memberships_for_user(user):
    if not user.is_authenticated or not user.is_active:
        return Membership.objects.none()
    now = timezone.now()
    return (
        Membership.objects.select_related("organization")
        .filter(
            user=user,
            is_active=True,
            organization__status=Organization.Status.ACTIVE,
            starts_at__lte=now,
        )
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .order_by("organization__name")
    )


def active_membership(user, organization):
    return active_memberships_for_user(user).filter(organization=organization).first()
