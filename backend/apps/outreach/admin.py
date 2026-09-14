from django.contrib import admin

from .models import (
    InvitationBatch,
    InvitationCampaign,
    InvitationRecipient,
    InvitationRecipientStatusEvent,
    OutreachMessage,
    OutreachProviderEmail,
    OutreachQualificationDecision,
    OutreachResponse,
    ResendWebhookEvent,
)


class InspectionOnlyAdmin(admin.ModelAdmin):
    """Preparation is service-only; Admin cannot rewrite historical evidence."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(InvitationCampaign)
class InvitationCampaignAdmin(InspectionOnlyAdmin):
    list_display = ("id", "project", "scope_package", "scope_version", "status", "created_at")


@admin.register(InvitationBatch)
class InvitationBatchAdmin(InspectionOnlyAdmin):
    list_display = ("id", "campaign", "sequence", "status", "created_at")


@admin.register(InvitationRecipient)
class InvitationRecipientAdmin(InspectionOnlyAdmin):
    list_display = ("id", "batch", "candidate", "company_name", "current_status", "created_at")


@admin.register(InvitationRecipientStatusEvent)
class InvitationRecipientStatusEventAdmin(InspectionOnlyAdmin):
    list_display = ("id", "recipient", "previous_status", "new_status", "occurred_at")


@admin.register(OutreachMessage)
class OutreachMessageAdmin(InspectionOnlyAdmin):
    list_display = ("id", "recipient", "sequence", "kind", "created_at")


@admin.register(ResendWebhookEvent)
class ResendWebhookEventAdmin(InspectionOnlyAdmin):
    list_display = ("id", "organization", "event_type", "message", "occurred_at")


@admin.register(OutreachProviderEmail)
class OutreachProviderEmailAdmin(InspectionOnlyAdmin):
    list_display = ("id", "organization", "message", "created_at")


@admin.register(OutreachResponse)
class OutreachResponseAdmin(InspectionOnlyAdmin):
    list_display = ("id", "organization", "recipient", "channel", "occurred_at")


@admin.register(OutreachQualificationDecision)
class OutreachQualificationDecisionAdmin(InspectionOnlyAdmin):
    list_display = ("id", "recipient", "state", "occurred_at")
