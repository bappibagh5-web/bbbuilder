from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.documents.models import DocumentRevision, ImmutableFieldsMixin


class ProcessingJob(ImmutableFieldsMixin):
    class JobType(models.TextChoices):
        SOURCE_VERIFICATION = "source_verification", "Source verification"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class ErrorCode(models.TextChoices):
        SOURCE_MISSING = "source_missing", "Source missing"
        STORAGE_UNAVAILABLE = "storage_unavailable", "Storage unavailable"
        SIZE_MISMATCH = "size_mismatch", "Size mismatch"
        CHECKSUM_MISMATCH = "checksum_mismatch", "Checksum mismatch"
        PROCESSING_ERROR = "processing_error", "Processing error"
        WORKER_LOST = "worker_lost", "Worker lost"

    document_revision = models.ForeignKey(
        DocumentRevision, on_delete=models.PROTECT, related_name="processing_jobs"
    )
    job_type = models.CharField(max_length=40, choices=JobType, default=JobType.SOURCE_VERIFICATION)
    status = models.CharField(max_length=20, choices=Status, default=Status.QUEUED)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_processing_jobs",
    )
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3, validators=[MinValueValidator(1)])
    queued_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    heartbeat_at = models.DateTimeField(blank=True, null=True)
    lease_expires_at = models.DateTimeField(blank=True, null=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    last_dispatched_at = models.DateTimeField(blank=True, null=True)
    dispatch_attempt_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=40, choices=ErrorCode, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    result_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    immutable_fields = (
        "document_revision_id",
        "job_type",
        "requested_by_id",
        "max_attempts",
        "created_at",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("document_revision", "job_type"),
                condition=Q(status__in=("queued", "running")),
                name="processing_unique_active_revision_job",
            )
        ]
        indexes = [
            models.Index(fields=("status", "last_dispatched_at")),
            models.Index(fields=("status", "lease_expires_at")),
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.result_metadata, dict):
            raise ValidationError({"result_metadata": "Result metadata must be an object."})
        if self.status == self.Status.SUCCEEDED and self.error_code:
            raise ValidationError({"error_code": "A successful job cannot contain an error code."})
        if self.status == self.Status.FAILED and not self.error_code:
            raise ValidationError({"error_code": "A failed job requires a controlled error code."})
        if self.status in {self.Status.QUEUED, self.Status.RUNNING} and self.finished_at:
            raise ValidationError({"finished_at": "An active job cannot have a finish time."})
        if self.status == self.Status.RUNNING and not self.lease_expires_at:
            raise ValidationError({"lease_expires_at": "A running job requires a lease."})

    @property
    def project(self):
        return self.document_revision.document.project

    @property
    def organization(self):
        return self.project.organization

    def lease_until(self, at=None):
        at = at or timezone.now()
        return at + timedelta(seconds=settings.PROCESSING_JOB_LEASE_SECONDS)

    def __str__(self):
        return f"{self.get_job_type_display()} #{self.pk} — {self.get_status_display()}"
