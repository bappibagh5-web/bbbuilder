from django.contrib import admin, messages

from .models import ProcessingJob
from .services import dispatch_processing_job, recover_stale_jobs, retry_processing_job


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job_type",
        "status",
        "project_number",
        "document_revision",
        "attempt_count",
        "error_code",
        "updated_at",
    )
    list_filter = ("status", "job_type", "error_code", "created_at")
    search_fields = (
        "document_revision__document__project__project_number",
        "document_revision__document__title",
        "document_revision__source_filename",
    )
    readonly_fields = tuple(field.name for field in ProcessingJob._meta.fields)
    actions = ("redispatch_queued", "retry_failed", "recover_stale")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Project")
    def project_number(self, obj):
        return obj.project.project_number

    @admin.action(description="Redispatch selected queued jobs")
    def redispatch_queued(self, request, queryset):
        count = sum(dispatch_processing_job(job.pk, force=True) for job in queryset)
        self.message_user(request, f"Dispatched {count} queued job(s).", messages.SUCCESS)

    @admin.action(description="Retry selected failed jobs")
    def retry_failed(self, request, queryset):
        count = 0
        for job in queryset.select_related("document_revision"):
            if job.status == ProcessingJob.Status.FAILED:
                retry_processing_job(job=job, requested_by=request.user)
                count += 1
        self.message_user(request, f"Requested {count} retry job(s).", messages.SUCCESS)

    @admin.action(description="Recover stale running jobs")
    def recover_stale(self, request, queryset):
        recovered = recover_stale_jobs(job_ids=list(queryset.values_list("pk", flat=True)))
        self.message_user(request, f"Recovered {len(recovered)} stale job(s).", messages.SUCCESS)
