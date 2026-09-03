from django.contrib import admin

from .models import AnalysisRun, AnalysisTaskRun


class ImmutableAnalysisAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AnalysisRun)
class AnalysisRunAdmin(ImmutableAnalysisAdmin):
    list_display = (
        "id",
        "project_number",
        "document_revision",
        "status",
        "provider",
        "model",
        "requested_by",
        "created_at",
    )
    list_filter = ("status", "provider", "model", "created_at")
    search_fields = (
        "document_revision__document__project__project_number",
        "document_revision__document__title",
        "requested_by__email",
    )
    readonly_fields = tuple(field.name for field in AnalysisRun._meta.fields)

    @admin.display(description="Project")
    def project_number(self, obj):
        return obj.project.project_number


@admin.register(AnalysisTaskRun)
class AnalysisTaskRunAdmin(ImmutableAnalysisAdmin):
    list_display = (
        "id",
        "analysis_run",
        "task_type",
        "document_page",
        "input_mode",
        "status",
        "attempt_count",
        "error_code",
    )
    list_filter = ("task_type", "input_mode", "status", "error_code", "created_at")
    search_fields = (
        "analysis_run__document_revision__document__project__project_number",
        "analysis_run__document_revision__document__title",
    )
    readonly_fields = tuple(field.name for field in AnalysisTaskRun._meta.fields)
