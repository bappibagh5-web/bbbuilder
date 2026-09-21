from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.projects.audit import record_event

from .models import Membership
from .services import active_membership

UNKNOWN_USER_MESSAGE = (
    "No existing user has this email. Account invitations are not implemented yet."
)


def _authorize_admin(actor, organization):
    membership = active_membership(actor, organization)
    if membership is None or membership.role != Membership.Role.ADMIN:
        raise ValidationError("Only an organization Admin can manage Users & Access.")
    return membership


def _currently_active_query(now=None):
    now = now or timezone.now()
    return Q(is_active=True, starts_at__lte=now) & (Q(ends_at__isnull=True) | Q(ends_at__gt=now))


def _active_admin_count(organization):
    return Membership.objects.filter(
        _currently_active_query(),
        organization=organization,
        role=Membership.Role.ADMIN,
        user__is_active=True,
    ).count()


def member_payload(membership, actor=None):
    is_self = actor is not None and membership.user_id == actor.pk
    currently_active = (
        membership.is_active
        and membership.starts_at <= timezone.now()
        and (membership.ends_at is None or membership.ends_at > timezone.now())
        and membership.user.is_active
    )
    can_manage = False
    if actor is not None:
        actor_membership = active_membership(actor, membership.organization)
        can_manage = bool(actor_membership and actor_membership.role == Membership.Role.ADMIN)
    return {
        "id": membership.pk,
        "user_id": membership.user_id,
        "email": membership.user.email,
        "first_name": membership.user.first_name,
        "last_name": membership.user.last_name,
        "display_name": membership.user.get_full_name() or membership.user.email,
        "role": membership.role,
        "role_label": membership.get_role_display(),
        "is_active": currently_active,
        "membership_enabled": membership.is_active,
        "starts_at": membership.starts_at,
        "ends_at": membership.ends_at,
        "created_at": membership.created_at,
        "date_joined": membership.user.date_joined,
        "last_login": membership.user.last_login,
        "can_change_role": can_manage and not is_self,
        "can_deactivate": can_manage and currently_active and not is_self,
        "can_reactivate": can_manage and not currently_active and membership.user.is_active,
    }


@transaction.atomic
def add_existing_user(*, organization, actor, email, role):
    _authorize_admin(actor, organization)
    normalized = get_user_model().objects.normalize_email(str(email).strip()).lower()
    if not normalized:
        raise ValidationError({"email": "Enter an existing user's email address."})
    if role not in Membership.Role.values:
        raise ValidationError({"role": "Choose a valid organization role."})
    user = get_user_model().objects.filter(email__iexact=normalized).first()
    if user is None:
        raise ValidationError({"email": UNKNOWN_USER_MESSAGE})
    if not user.is_active:
        raise ValidationError({"email": "This user account is inactive."})
    if Membership.objects.filter(organization=organization, user=user).exists():
        raise ValidationError({"email": "This user already belongs to the organization."})
    membership = Membership.objects.create(
        organization=organization,
        user=user,
        role=role,
    )
    record_event(
        organization=organization,
        project=None,
        actor=actor,
        action_code="organization_membership.added",
        target=membership,
        metadata={"membership_id": membership.pk, "user_id": user.pk, "role": role},
    )
    return membership


@transaction.atomic
def update_membership(*, organization, actor, membership_id, role=None, is_active=None):
    _authorize_admin(actor, organization)
    membership = (
        Membership.objects.select_for_update()
        .select_related("user", "organization")
        .get(pk=membership_id, organization=organization)
    )
    # Lock all Admin rows so simultaneous changes cannot remove the final active Admin.
    list(
        Membership.objects.select_for_update()
        .filter(organization=organization, role=Membership.Role.ADMIN)
        .values_list("pk", flat=True)
    )
    if membership.user_id == actor.pk and (
        (role is not None and role != Membership.Role.ADMIN) or is_active is False
    ):
        raise ValidationError("You cannot demote or deactivate your own active membership.")
    if role is not None and role not in Membership.Role.values:
        raise ValidationError({"role": "Choose a valid organization role."})

    is_current_admin = (
        membership.role == Membership.Role.ADMIN
        and membership.is_active
        and membership.user.is_active
        and membership.starts_at <= timezone.now()
        and (membership.ends_at is None or membership.ends_at > timezone.now())
    )
    removes_admin = is_current_admin and (
        (role is not None and role != Membership.Role.ADMIN) or is_active is False
    )
    if removes_admin and _active_admin_count(organization) <= 1:
        raise ValidationError("The last active Admin cannot be demoted or deactivated.")

    changed = []
    save_fields = []
    old_role = membership.role
    if role is not None and role != membership.role:
        membership.role = role
        changed.append("role")
        save_fields.append("role")
    currently_active = (
        membership.is_active
        and membership.starts_at <= timezone.now()
        and (membership.ends_at is None or membership.ends_at > timezone.now())
    )
    if is_active is not None and is_active != currently_active:
        membership.is_active = is_active
        membership.ends_at = None if is_active else timezone.now()
        changed.append("status")
        save_fields.extend(["is_active", "ends_at"])
    if not changed:
        return membership
    membership.save(update_fields=[*save_fields, "updated_at"])
    if "role" in changed:
        record_event(
            organization=organization,
            project=None,
            actor=actor,
            action_code="organization_membership.role_changed",
            target=membership,
            metadata={
                "membership_id": membership.pk,
                "user_id": membership.user_id,
                "old_role": old_role,
                "new_role": membership.role,
            },
        )
    if "status" in changed:
        record_event(
            organization=organization,
            project=None,
            actor=actor,
            action_code=(
                "organization_membership.reactivated"
                if membership.is_active
                else "organization_membership.deactivated"
            ),
            target=membership,
            metadata={"membership_id": membership.pk, "user_id": membership.user_id},
        )
    return membership
