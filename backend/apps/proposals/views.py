from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator
from apps.organizations.services import active_membership
from apps.projects.models import ProjectContact

from .models import Estimate, EstimateVersion, Proposal
from .services import (
    create_estimate,
    create_estimate_version,
    create_proposal,
    create_proposal_version,
)


def _validation_error(error):
    if hasattr(error, "message_dict"):
        return serializers.ValidationError(error.message_dict)
    return serializers.ValidationError({"detail": error.messages})


def _user_label(user):
    return user.get_full_name() or user.email


def _estimate_version(version):
    return {
        "id": version.id,
        "version": version.version,
        "status": version.status,
        "status_label": version.get_status_display(),
        "supersedes_id": version.supersedes_id,
        "created_by": _user_label(version.created_by),
        "created_at": version.created_at,
    }


def _proposal_version(version):
    return {
        "id": version.id,
        "version": version.version,
        "status": version.status,
        "status_label": version.get_status_display(),
        "estimate_version_id": version.estimate_version_id,
        "estimate_version": version.estimate_version.version,
        "supersedes_id": version.supersedes_id,
        "created_by": _user_label(version.created_by),
        "created_at": version.created_at,
    }


def proposal_workspace(project, user):
    estimate = (
        Estimate.objects.filter(project=project)
        .select_related("created_by")
        .prefetch_related("versions__created_by")
        .first()
    )
    proposal = (
        Proposal.objects.filter(project=project)
        .select_related("created_by", "client_contact", "estimate")
        .prefetch_related("versions__created_by", "versions__estimate_version")
        .first()
    )
    membership = active_membership(user, project.organization)
    can_edit = bool(
        project.is_active
        and membership
        and membership.role in {membership.Role.ADMIN, membership.Role.ESTIMATOR_OPERATOR}
    )
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "project_number": project.project_number,
            "client_name": project.client_name,
        },
        "can_edit": can_edit,
        "estimate": None
        if estimate is None
        else {
            "id": estimate.id,
            "title": estimate.title,
            "created_by": _user_label(estimate.created_by),
            "created_at": estimate.created_at,
            "versions": [_estimate_version(item) for item in estimate.versions.all()],
        },
        "proposal": None
        if proposal is None
        else {
            "id": proposal.id,
            "title": proposal.title,
            "estimate_id": proposal.estimate_id,
            "client_contact": None
            if proposal.client_contact is None
            else {
                "id": proposal.client_contact.id,
                "name": proposal.client_contact.person_name,
                "company": proposal.client_contact.company_name,
                "email": proposal.client_contact.email,
            },
            "created_by": _user_label(proposal.created_by),
            "created_at": proposal.created_at,
            "versions": [_proposal_version(item) for item in proposal.versions.all()],
        },
    }


class ProposalWorkspaceView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        return Response(proposal_workspace(self.get_project(), request.user))


class EstimateCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["title"] = serializers.CharField(max_length=255, required=False)
        serializer.is_valid(raise_exception=True)
        try:
            create_estimate(
                project=self.get_project(),
                actor=request.user,
                title=serializer.validated_data.get("title"),
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(
            proposal_workspace(self.get_project(), request.user), status=status.HTTP_201_CREATED
        )


class EstimateVersionCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        estimate = get_object_or_404(
            Estimate, pk=self.kwargs["estimate_pk"], project=self.get_project()
        )
        try:
            create_estimate_version(estimate=estimate, actor=request.user)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(
            proposal_workspace(self.get_project(), request.user), status=status.HTTP_201_CREATED
        )


class ProposalCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["estimate_version_id"] = serializers.IntegerField(min_value=1)
        serializer.fields["title"] = serializers.CharField(max_length=255, required=False)
        serializer.fields["client_contact_id"] = serializers.IntegerField(
            min_value=1, required=False, allow_null=True
        )
        serializer.is_valid(raise_exception=True)
        project = self.get_project()
        estimate = get_object_or_404(Estimate, project=project)
        estimate_version = get_object_or_404(
            EstimateVersion,
            pk=serializer.validated_data["estimate_version_id"],
            estimate=estimate,
        )
        contact_id = serializer.validated_data.get("client_contact_id")
        contact = (
            get_object_or_404(ProjectContact, pk=contact_id, project=project)
            if contact_id
            else None
        )
        try:
            create_proposal(
                estimate=estimate,
                estimate_version=estimate_version,
                actor=request.user,
                title=serializer.validated_data.get("title"),
                client_contact=contact,
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user), status=status.HTTP_201_CREATED)


class ProposalVersionCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["estimate_version_id"] = serializers.IntegerField(min_value=1)
        serializer.is_valid(raise_exception=True)
        project = self.get_project()
        proposal = get_object_or_404(Proposal, pk=self.kwargs["proposal_pk"], project=project)
        estimate_version = get_object_or_404(
            EstimateVersion,
            pk=serializer.validated_data["estimate_version_id"],
            estimate=proposal.estimate,
        )
        try:
            create_proposal_version(
                proposal=proposal, estimate_version=estimate_version, actor=request.user
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user), status=status.HTTP_201_CREATED)
