from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contractors.models import Contact, ScopeContractorCandidate
from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.models import Organization
from apps.organizations.permissions import (
    ActiveOrganizationMember,
    OrganizationAdmin,
    OrganizationOperator,
)
from apps.scope_packages.models import ScopePackage, ScopePackageVersion

from .delivery import approve_batch_send, deliver_message, prepare_batch_messages, readiness
from .models import (
    InvitationBatch,
    InvitationCampaign,
    OutreachMessage,
    OutreachSenderSettings,
    OutreachSMTPConfiguration,
)
from .rfq import build_rfq_preview
from .selection import outreach_workspace
from .services import (
    add_invitation_recipient,
    create_invitation_batch,
    create_invitation_campaign,
)
from .setup import format_project_local, save_campaign_setup, save_sender_settings
from .smtp import provider_status
from .smtp_setup import run_connection_test, run_test_email, save_smtp_configuration


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


class CampaignSetupView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def _campaign(self):
        return get_object_or_404(
            InvitationCampaign.objects.select_related("project"),
            pk=self.kwargs["campaign_pk"],
            project=self.get_project(),
            organization=self.get_organization(),
        )

    def get(self, request, *args, **kwargs):
        campaign = self._campaign()
        zone = campaign.project.project_timezone
        return Response(
            {
                "bid_due_local": format_project_local(campaign.bid_deadline, zone),
                "questions_due_local": format_project_local(campaign.questions_deadline, zone),
                "project_timezone": zone,
                "setup_version": campaign.setup_version,
            }
        )

    def put(self, request, *args, **kwargs):
        if not OrganizationOperator().has_permission(request, self):
            raise PermissionDenied("Operator access required.")
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["bid_due_local"] = serializers.CharField(allow_blank=True)
        serializer.fields["questions_due_local"] = serializers.CharField(allow_blank=True)
        serializer.is_valid(raise_exception=True)
        try:
            save_campaign_setup(
                campaign=self._campaign(),
                actor=request.user,
                bid_local=serializer.validated_data["bid_due_local"],
                questions_local=serializer.validated_data["questions_due_local"],
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return self.get(request, *args, **kwargs)


class OutreachSenderSettingsView(APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get_organization(self):
        return get_object_or_404(Organization, slug=self.kwargs["organization_slug"])

    def get(self, request, *args, **kwargs):
        sender = OutreachSenderSettings.objects.filter(organization=self.get_organization()).first()
        return Response(
            {
                "display_name": sender.display_name if sender else "",
                "from_address": sender.from_address if sender else "",
                "reply_to": sender.reply_to if sender else "",
                "is_enabled": sender.is_enabled if sender else False,
                "provider": provider_status(self.get_organization()),
            }
        )

    def put(self, request, *args, **kwargs):
        from apps.organizations.permissions import OrganizationAdmin

        if not OrganizationAdmin().has_permission(request, self):
            raise PermissionDenied("Organization Admin access required.")
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["display_name"] = serializers.CharField(max_length=255)
        serializer.fields["from_address"] = serializers.EmailField()
        serializer.fields["reply_to"] = serializers.EmailField()
        serializer.fields["is_enabled"] = serializers.BooleanField()
        serializer.is_valid(raise_exception=True)
        try:
            save_sender_settings(
                organization=self.get_organization(),
                actor=request.user,
                display_name=serializer.validated_data["display_name"],
                from_address=serializer.validated_data["from_address"],
                reply_to=serializer.validated_data["reply_to"],
                enabled=serializer.validated_data["is_enabled"],
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return self.get(request, *args, **kwargs)


class OutreachSMTPSettingsView(APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get_organization(self):
        return get_object_or_404(Organization, slug=self.kwargs["organization_slug"])

    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        status = provider_status(organization)
        if not OrganizationAdmin().has_permission(request, self):
            return Response({"provider": status})
        config = OutreachSMTPConfiguration.objects.filter(organization=organization).first()
        return Response(
            {
                "provider": status,
                "host": config.host if config else "",
                "port": config.port if config else 587,
                "username": config.username if config else "",
                "password_saved": bool(config and config.encrypted_password),
                "security": config.security if config else "starttls",
                "timeout_seconds": config.timeout_seconds if config else 20,
                "is_enabled": config.is_enabled if config else False,
                "last_test_status": config.last_test_status if config else "",
            }
        )

    def put(self, request, *args, **kwargs):
        if not OrganizationAdmin().has_permission(request, self):
            raise PermissionDenied("Organization Admin access required.")
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["host"] = serializers.CharField(max_length=255, allow_blank=True)
        serializer.fields["port"] = serializers.IntegerField(min_value=1, max_value=65535)
        serializer.fields["username"] = serializers.CharField(max_length=255, allow_blank=True)
        serializer.fields["password"] = serializers.CharField(allow_blank=True, write_only=True)
        serializer.fields["clear_password"] = serializers.BooleanField(default=False)
        serializer.fields["security"] = serializers.ChoiceField(choices=("starttls", "ssl", "none"))
        serializer.fields["timeout_seconds"] = serializers.IntegerField(min_value=1, max_value=120)
        serializer.fields["is_enabled"] = serializers.BooleanField()
        serializer.is_valid(raise_exception=True)
        try:
            save_smtp_configuration(
                organization=self.get_organization(),
                actor=request.user,
                host=serializer.validated_data["host"],
                port=serializer.validated_data["port"],
                username=serializer.validated_data["username"],
                password=serializer.validated_data["password"],
                clear_password=serializer.validated_data["clear_password"],
                security=serializer.validated_data["security"],
                timeout_seconds=serializer.validated_data["timeout_seconds"],
                enabled=serializer.validated_data["is_enabled"],
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error
        return self.get(request, *args, **kwargs)


class OutreachSMTPConnectionTestView(OutreachSMTPSettingsView):
    def post(self, request, *args, **kwargs):
        if not OrganizationAdmin().has_permission(request, self):
            raise PermissionDenied("Organization Admin access required.")
        try:
            return Response(
                run_connection_test(organization=self.get_organization(), actor=request.user)
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error


class OutreachSMTPTestEmailView(OutreachSMTPSettingsView):
    def post(self, request, *args, **kwargs):
        if not OrganizationAdmin().has_permission(request, self):
            raise PermissionDenied("Organization Admin access required.")
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["recipient_email"] = serializers.EmailField()
        serializer.fields["confirmed"] = serializers.BooleanField()
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data["confirmed"]:
            raise serializers.ValidationError({"detail": "Confirm the controlled test recipient."})
        try:
            return Response(
                run_test_email(
                    organization=self.get_organization(),
                    actor=request.user,
                    recipient_email=serializer.validated_data["recipient_email"],
                )
            )
        except DjangoValidationError as error:
            raise api_validation_error(error) from error


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
