from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Membership
from .services import active_membership


def organization_for_view(view):
    if hasattr(view, "get_organization"):
        return view.get_organization()
    return getattr(view, "organization", None)


class ActiveOrganizationMember(BasePermission):
    def has_permission(self, request, view):
        organization = organization_for_view(view)
        return (
            organization is not None and active_membership(request.user, organization) is not None
        )


class OrganizationAdmin(ActiveOrganizationMember):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        membership = active_membership(request.user, organization_for_view(view))
        return membership.role == Membership.Role.ADMIN


class OrganizationOperator(ActiveOrganizationMember):
    allowed_roles = {Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR}

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        membership = active_membership(request.user, organization_for_view(view))
        return membership.role in self.allowed_roles


class OrganizationReadWritePermission(ActiveOrganizationMember):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS:
            return True
        membership = active_membership(request.user, organization_for_view(view))
        return membership.role in {
            Membership.Role.ADMIN,
            Membership.Role.ESTIMATOR_OPERATOR,
        }
