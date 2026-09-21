from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .access import add_existing_user, member_payload, update_membership
from .models import Membership, Organization
from .permissions import ActiveOrganizationMember, OrganizationAdmin


def _safe_validation(error):
    if hasattr(error, "message_dict"):
        raise ValidationError(error.message_dict) from error
    raise ValidationError(error.messages) from error


class OrganizationContextMixin:
    organization = None

    def get_organization(self):
        if self.organization is None:
            self.organization = get_object_or_404(
                Organization, slug=self.kwargs["organization_slug"]
            )
        return self.organization


class OrganizationSettingsView(OrganizationContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)
    http_method_names = ("get", "head", "options")

    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        membership = Membership.objects.get(organization=organization, user=request.user)
        return Response(
            {
                "organization": {
                    "id": organization.pk,
                    "name": organization.name,
                    "legal_name": organization.legal_name,
                    "slug": organization.slug,
                    "status": organization.status,
                    "status_label": organization.get_status_display(),
                    "default_timezone": organization.default_timezone,
                    "created_at": organization.created_at,
                },
                "access": {
                    "role": membership.role,
                    "role_label": membership.get_role_display(),
                    "can_manage_members": membership.role == Membership.Role.ADMIN,
                },
            }
        )


class MembershipListView(OrganizationContextMixin, APIView):
    http_method_names = ("get", "post", "head", "options")

    def get_permissions(self):
        classes = (
            (OrganizationAdmin,) if self.request.method == "POST" else (ActiveOrganizationMember,)
        )
        return [permission() for permission in classes]

    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        actor_membership = Membership.objects.get(organization=organization, user=request.user)
        memberships = (
            Membership.objects.filter(organization=organization)
            .select_related("user", "organization")
            .order_by("user__email", "id")
        )
        return Response(
            {
                "can_manage_members": actor_membership.role == Membership.Role.ADMIN,
                "results": [member_payload(item, request.user) for item in memberships],
                "roles": [
                    {"value": value, "label": label} for value, label in Membership.Role.choices
                ],
            }
        )

    def post(self, request, *args, **kwargs):
        try:
            membership = add_existing_user(
                organization=self.get_organization(),
                actor=request.user,
                email=request.data.get("email", ""),
                role=request.data.get("role", ""),
            )
        except DjangoValidationError as error:
            _safe_validation(error)
        membership = Membership.objects.select_related("user", "organization").get(pk=membership.pk)
        return Response(member_payload(membership, request.user), status=status.HTTP_201_CREATED)


class MembershipDetailView(OrganizationContextMixin, APIView):
    permission_classes = (OrganizationAdmin,)
    http_method_names = ("patch", "head", "options")

    def patch(self, request, membership_pk, *args, **kwargs):
        supplied_role = "role" in request.data
        supplied_active = "is_active" in request.data
        if not supplied_role and not supplied_active:
            raise ValidationError("Provide a role or membership status change.")
        is_active = request.data.get("is_active") if supplied_active else None
        if supplied_active and not isinstance(is_active, bool):
            raise ValidationError({"is_active": "Use true or false."})
        try:
            membership = update_membership(
                organization=self.get_organization(),
                actor=request.user,
                membership_id=membership_pk,
                role=request.data.get("role") if supplied_role else None,
                is_active=is_active,
            )
        except ObjectDoesNotExist as error:
            raise NotFound("Membership not found in this organization.") from error
        except DjangoValidationError as error:
            _safe_validation(error)
        membership = Membership.objects.select_related("user", "organization").get(pk=membership.pk)
        return Response(member_payload(membership, request.user))
