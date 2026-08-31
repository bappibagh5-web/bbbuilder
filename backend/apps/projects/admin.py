from django.contrib import admin

from .audit import (
    CONTACT_AUDIT_FIELDS,
    PROJECT_AUDIT_FIELDS,
    record_event,
    snapshot,
    update_action,
)
from .models import AuditEvent, Project, ProjectContact


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "project_number",
        "name",
        "organization",
        "client_name",
        "status",
        "is_active",
        "bid_deadline",
        "updated_at",
    )
    list_filter = ("organization", "status", "project_type", "is_active")
    search_fields = ("project_number", "name", "client_name", "city")
    autocomplete_fields = ("organization", "created_by")
    readonly_fields = ("created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        before = snapshot(Project.objects.get(pk=obj.pk), PROJECT_AUDIT_FIELDS) if change else None
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        after = snapshot(obj, PROJECT_AUDIT_FIELDS)
        record_event(
            organization=obj.organization,
            project=obj,
            actor=request.user,
            action_code=(
                update_action(target_type="project", before=before, after=after)
                if before
                else "project.created"
            ),
            target=obj,
            metadata=(
                {
                    "changed_fields": [
                        name for name in PROJECT_AUDIT_FIELDS if before[name] != after[name]
                    ],
                    "before": before,
                    "after": after,
                }
                if before
                else {"after": after}
            ),
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProjectContact)
class ProjectContactAdmin(admin.ModelAdmin):
    list_display = (
        "person_name",
        "company_name",
        "project",
        "contact_role",
        "email",
        "is_active",
    )
    list_filter = ("contact_role", "is_active", "project__organization")
    search_fields = ("person_name", "company_name", "email", "project__project_number")
    autocomplete_fields = ("project",)

    def save_model(self, request, obj, form, change):
        before = (
            snapshot(ProjectContact.objects.get(pk=obj.pk), CONTACT_AUDIT_FIELDS)
            if change
            else None
        )

        super().save_model(request, obj, form, change)
        after = snapshot(obj, CONTACT_AUDIT_FIELDS)
        record_event(
            organization=obj.project.organization,
            project=obj.project,
            actor=request.user,
            action_code=(
                update_action(target_type="project_contact", before=before, after=after)
                if before
                else "project_contact.created"
            ),
            target=obj,
            metadata=(
                {
                    "changed_fields": [
                        name for name in CONTACT_AUDIT_FIELDS if before[name] != after[name]
                    ],
                    "before": before,
                    "after": after,
                }
                if before
                else {"after": after}
            ),
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "action_code",
        "organization",
        "project",
        "actor",
        "target_type",
        "target_id",
    )
    list_filter = ("organization", "action_code", "target_type")
    search_fields = ("action_code", "target_type", "target_id", "actor__email")
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
