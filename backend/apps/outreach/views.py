from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contractors.models import Contact, ScopeContractorCandidate
from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator
from apps.scope_packages.models import ScopePackage, ScopePackageVersion

from .delivery import approve_batch_send, deliver_message, prepare_batch_messages, readiness
from .models import InvitationBatch, InvitationCampaign, OutreachMessage
from .rfq import build_rfq_preview
from .selection import outreach_workspace
from .services import (
    add_invitation_recipient,
    create_invitation_batch,
    create_invitation_campaign,
)


def api_validation_error(error):
    if hasattr(error, "message_dict"):
        return serializers.ValidationError(error.message_dict)
    return serializers.ValidationError({"detail": error.messages})


class OutreachWorkspaceView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        return Response(outreach_workspace(self.get_project()))


class CampaignCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["scope_package_id"] = serializers.IntegerField(min_value=1)
        serializer.fields["scope_version_id"] = serializers.IntegerField(min_value=1)
        serializer.is_valid(raise_exception=True)
        project = self.get_project()
        package = get_object_or_404(
            ScopePackage,
            pk=serializer.validated_data["scope_package_id"],
            project=project,
            lifecycle=ScopePackage.Lifecycle.ACTIVE,
        )
        version = get_object_or_404(
            ScopePackageVersion,
            pk=serializer.validated_data["scope_version_id"],
            package=package,
            status=ScopePackageVersion.Status.READY,
        )
        if package.current_version_id != version.pk:
            raise serializers.ValidationError({"detail": "Select the current Ready scope version."})
        campaign = InvitationCampaign.objects.filter(
            project=project, scope_package=package, scope_version=version
        ).first()
        if campaign is None:
            try:
                campaign = create_invitation_campaign(
                    project=project,
                    scope_package=package,
                    scope_version=version,
                    actor=request.user,
                )
            except DjangoValidationError as error:
                raise api_validation_error(error) from error
        return Response({"id": campaign.pk, "scope_version_id": campaign.scope_version_id})


class BatchCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["sequence"] = serializers.IntegerField(min_value=1)
        serializer.is_valid(raise_exception=True)
        campaign = get_object_or_404(
            InvitationCampaign,
            pk=kwargs["campaign_pk"],
            project=self.get_project(),
            organization=self.get_organization(),
        )
        try:
            batch = create_invitation_batch(
                campaign=campaign,
                actor=request.user,
                sequence=serializer.validated_data["sequence"],
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return Response({"id": batch.pk, "sequence": batch.sequence})


class RecipientCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["candidate_id"] = serializers.IntegerField(min_value=1)
        serializer.fields["contact_id"] = serializers.IntegerField(min_value=1)
        serializer.is_valid(raise_exception=True)
        batch = get_object_or_404(
            InvitationBatch,
            pk=kwargs["batch_pk"],
            campaign__project=self.get_project(),
            campaign__organization=self.get_organization(),
        )
        candidate = get_object_or_404(
            ScopeContractorCandidate,
            pk=serializer.validated_data["candidate_id"],
            project=self.get_project(),
        )
        contact = get_object_or_404(
            Contact, pk=serializer.validated_data["contact_id"], company=candidate.company
        )
        try:
            recipient = add_invitation_recipient(
                batch=batch, candidate=candidate, contact=contact, actor=request.user
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return Response({"id": recipient.pk, "status": recipient.current_status})


class CampaignRFQPreviewView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        campaign = get_object_or_404(
            InvitationCampaign,
            pk=kwargs["campaign_pk"],
            project=self.get_project(),
            organization=self.get_organization(),
        )
        try:
            return Response(build_rfq_preview(campaign=campaign).as_dict())
        except DjangoValidationError as error:
            raise serializers.ValidationError({"detail": error.messages}) from error


class BatchDeliveryView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def _batch(self):
        return get_object_or_404(
            InvitationBatch.objects.select_related(
                "campaign__project", "campaign__scope_package", "campaign__scope_version"
            ),
            pk=self.kwargs["batch_pk"],
            campaign__project=self.get_project(),
            campaign__organization=self.get_organization(),
        )

    def get(self, request, *args, **kwargs):
        return Response(readiness(self._batch()))

    def post(self, request, *args, **kwargs):
        if not OrganizationOperator().has_permission(request, self):
            raise PermissionDenied("Operator access required.")
        batch = self._batch()
        action = kwargs["action"]
        try:
            if action == "approve":
                approval = approve_batch_send(batch=batch, actor=request.user)
                return Response({"approval_id": approval.pk})
            if action == "prepare":
                messages = prepare_batch_messages(batch=batch, actor=request.user)
                return Response({"message_ids": [message.pk for message in messages]})
            if action == "send":
                messages = [
                    recipient.messages.order_by("-sequence").first()
                    for recipient in batch.recipients.filter(current_status="prepared")
                ]
                if not messages or any(message is None for message in messages):
                    raise DjangoValidationError("Prepare invitation messages first.")
                attempts = [
                    deliver_message(message=message, actor=request.user) for message in messages
                ]
                return Response({"attempt_ids": [attempt.pk for attempt in attempts]})
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        raise serializers.ValidationError({"detail": "Unknown delivery action."})


class MessageRetryView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        message = get_object_or_404(
            OutreachMessage,
            pk=kwargs["message_pk"],
            recipient__batch__campaign__project=self.get_project(),
            recipient__batch__campaign__organization=self.get_organization(),
        )
        try:
            attempt = deliver_message(message=message, actor=request.user, retry=True)
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return Response({"attempt_id": attempt.pk, "status": attempt.status})
