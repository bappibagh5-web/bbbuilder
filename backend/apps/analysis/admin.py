from django.contrib import admin

from .models import (
    AnalysisRun,
    AnalysisTaskRun,
    ExtractedFinding,
    FindingReview,
    FindingSource,
    IntelligenceConflict,
    ProjectIntelligenceApproval,
    ProjectIntelligenceSnapshot,
    ProjectIntelligenceSnapshotEntry,
    ProjectIntelligenceSnapshotProvenance,
    ProjectIntelligenceSnapshotSource,
)


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


@admin.register(ExtractedFinding)
class ExtractedFindingAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "analysis_run", "category", "subject", "machine_support")
    list_filter = ("category", "machine_support", "created_at")
    search_fields = ("subject", "machine_value", "semantic_key")
    readonly_fields = tuple(field.name for field in ExtractedFinding._meta.fields)


@admin.register(FindingSource)
class FindingSourceAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "finding", "document_revision", "document_page", "evidence_mode")
    list_filter = ("evidence_mode", "relation", "created_at")
    readonly_fields = tuple(field.name for field in FindingSource._meta.fields)


@admin.register(FindingReview)
class FindingReviewAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "finding", "decision", "reviewer", "created_at")
    list_filter = ("decision", "created_at")
    search_fields = ("finding__subject", "reviewer__email")
    readonly_fields = tuple(field.name for field in FindingReview._meta.fields)


@admin.register(IntelligenceConflict)
class IntelligenceConflictAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "project", "semantic_key", "version", "status", "created_at")
    list_filter = ("status", "conflict_type", "created_at")
    search_fields = ("semantic_key", "explanation", "project__project_number")
    readonly_fields = tuple(field.name for field in IntelligenceConflict._meta.fields)


@admin.register(ProjectIntelligenceSnapshot)
class ProjectIntelligenceSnapshotAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "project", "version", "fingerprint", "created_by", "created_at")
    search_fields = ("project__project_number", "fingerprint", "created_by__email")
    readonly_fields = tuple(field.name for field in ProjectIntelligenceSnapshot._meta.fields)


@admin.register(ProjectIntelligenceSnapshotSource)
class ProjectIntelligenceSnapshotSourceAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "snapshot", "analysis_run", "document_revision")
    readonly_fields = tuple(field.name for field in ProjectIntelligenceSnapshotSource._meta.fields)


@admin.register(ProjectIntelligenceSnapshotEntry)
class ProjectIntelligenceSnapshotEntryAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "snapshot", "finding", "decision", "included_in_intelligence")
    list_filter = ("decision", "included_in_intelligence", "category")
    readonly_fields = tuple(field.name for field in ProjectIntelligenceSnapshotEntry._meta.fields)


@admin.register(ProjectIntelligenceSnapshotProvenance)
class ProjectIntelligenceSnapshotProvenanceAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "snapshot_entry", "finding_source", "document_page")
    readonly_fields = tuple(
        field.name for field in ProjectIntelligenceSnapshotProvenance._meta.fields
    )


@admin.register(ProjectIntelligenceApproval)
class ProjectIntelligenceApprovalAdmin(ImmutableAnalysisAdmin):
    list_display = ("id", "project", "snapshot", "approver", "approved_at")
    search_fields = ("project__project_number", "approver__email", "snapshot__fingerprint")
    readonly_fields = tuple(field.name for field in ProjectIntelligenceApproval._meta.fields)
