from django.contrib import admin, messages

from apps.projects.audit import record_event

from .models import Document, DocumentRevision, FileAsset, ProjectFile
from .services import set_current_revision


class NoDeleteAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FileAsset)
class FileAssetAdmin(NoDeleteAdmin):
    list_display = (
        "original_filename",
        "organization",
        "storage_backend",
        "byte_size",
        "checksum_algorithm",
        "created_at",
    )
    list_filter = ("organization", "storage_backend", "checksum_algorithm")
    search_fields = ("original_filename", "storage_key", "checksum")
    autocomplete_fields = ("organization", "created_by")

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return tuple(field.name for field in FileAsset._meta.fields)
        return ("created_at",)


@admin.register(ProjectFile)
class ProjectFileAdmin(NoDeleteAdmin):
    list_display = ("display_name", "project", "file_asset", "created_at")
    list_filter = ("project__organization",)
    search_fields = (
        "display_name",
        "project__project_number",
        "file_asset__original_filename",
    )
    autocomplete_fields = ("project", "file_asset", "created_by")
    readonly_fields = ("created_at",)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj:
            fields.extend(("project", "file_asset", "created_by"))
        return tuple(fields)


@admin.register(Document)
class DocumentAdmin(NoDeleteAdmin):
    list_display = (
        "title",
        "project",
        "category",
        "discipline",
        "current_revision",
        "is_active",
        "updated_at",
    )
    list_filter = ("project__organization", "category", "discipline", "is_active")
    search_fields = ("title", "project__project_number", "project__name")
    autocomplete_fields = ("project", "created_by")
    readonly_fields = ("current_revision", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj:
            fields.extend(("project", "created_by"))
        return tuple(fields)

    def save_model(self, request, obj, form, change):
        before = None
        if change:
            original = Document.objects.get(pk=obj.pk)
            before = {
                "title": original.title,
                "category": original.category,
                "discipline": original.discipline,
                "description": original.description,
                "is_active": original.is_active,
            }
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        after = {
            "title": obj.title,
            "category": obj.category,
            "discipline": obj.discipline,
            "description": obj.description,
            "is_active": obj.is_active,
        }
        changed = [field for field in after if before and before[field] != after[field]]
        if not change or changed:
            action_code = "document.created" if not change else "document.updated"
            if before and before["is_active"] != after["is_active"]:
                action_code = "document.reactivated" if after["is_active"] else "document.archived"
            record_event(
                organization=obj.project.organization,
                project=obj.project,
                actor=request.user,
                action_code=action_code,
                target=obj,
                metadata={"changed_fields": changed, "before": before, "after": after},
            )


@admin.register(DocumentRevision)
class DocumentRevisionAdmin(NoDeleteAdmin):
    list_display = (
        "document",
        "revision_label",
        "source_filename",
        "issued_date",
        "received_at",
        "created_at",
    )
    list_filter = ("document__project__organization", "document__category")
    search_fields = (
        "document__title",
        "document__project__project_number",
        "source_filename",
        "revision_label",
    )
    autocomplete_fields = ("document", "project_file", "supersedes", "created_by")
    readonly_fields = ("created_at",)
    actions = ("make_current_revision",)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return tuple(field.name for field in DocumentRevision._meta.fields)
        return super().get_readonly_fields(request, obj)

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        record_event(
            organization=obj.document.project.organization,
            project=obj.document.project,
            actor=request.user,
            action_code="document_revision.created",
            target=obj,
            metadata={
                "document_id": obj.document_id,
                "project_file_id": obj.project_file_id,
                "revision_label": obj.revision_label,
            },
        )

    @admin.action(description="Set selected revision as its document's current revision")
    def make_current_revision(self, request, queryset):
        count = 0
        for revision in queryset.select_related("document__project__organization"):
            set_current_revision(document=revision.document, revision=revision, actor=request.user)
            count += 1
        self.message_user(request, f"Updated {count} document(s).", messages.SUCCESS)
