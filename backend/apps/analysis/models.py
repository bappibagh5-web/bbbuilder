from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.documents.models import DocumentPage, DocumentRevision, ImmutableFieldsMixin


class AnalysisRun(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class ErrorCode(models.TextChoices):
        SOURCE_NOT_VERIFIED = "source_not_verified", "Source not verified"
        PDF_NOT_INDEXED = "pdf_not_indexed", "PDF not indexed"
        UNSUPPORTED_DOCUMENT = "unsupported_document", "Unsupported document"
        AI_CONFIGURATION_MISSING = "ai_configuration_missing", "AI configuration missing"
        PROVIDER_UNAVAILABLE = "provider_unavailable", "Provider unavailable"
        PROVIDER_RATE_LIMITED = "provider_rate_limited", "Provider rate limited"
        PROVIDER_TIMEOUT = "provider_timeout", "Provider timeout"
        INVALID_STRUCTURED_RESPONSE = (
            "invalid_structured_response",
            "Invalid structured response",
        )
        PAGE_RENDER_FAILED = "page_render_failed", "Page render failed"
        ANALYSIS_FAILED = "analysis_failed", "Analysis failed"
        WORKER_LOST = "worker_lost", "Worker lost"

    document_revision = models.ForeignKey(
        DocumentRevision, on_delete=models.PROTECT, related_name="analysis_runs"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_analysis_runs",
    )
    predecessor = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="successors", null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=Status, default=Status.QUEUED)
    provider = models.CharField(max_length=80)
    model = models.CharField(max_length=160)
    prompt_version = models.CharField(max_length=80)
    schema_version = models.CharField(max_length=80)
    analysis_version = models.CharField(max_length=80)
    input_manifest = models.JSONField(default=dict)
    result_summary = models.JSONField(default=dict, blank=True)
    usage_metadata = models.JSONField(default=dict, blank=True)
    queued_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    last_dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatch_attempt_count = models.PositiveIntegerField(default=0)
    failure_code = models.CharField(max_length=50, choices=ErrorCode, blank=True)
    safe_failure_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    immutable_fields = (
        "document_revision_id",
        "requested_by_id",
        "predecessor_id",
        "provider",
        "model",
        "prompt_version",
        "schema_version",
        "analysis_version",
        "input_manifest",
        "created_at",
    )

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("document_revision",),
                condition=Q(status__in=("queued", "running")),
                name="analysis_unique_active_revision_run",
            )
        ]
        indexes = [models.Index(fields=("status", "lease_expires_at"))]

    @property
    def project(self):
        return self.document_revision.document.project

    @property
    def organization(self):
        return self.project.organization

    def lease_until(self, at=None):
        return (at or timezone.now()) + timedelta(seconds=settings.AI_RUN_LEASE_SECONDS)

    def clean(self):
        super().clean()
        for field in ("input_manifest", "result_summary", "usage_metadata"):
            if not isinstance(getattr(self, field), dict):
                raise ValidationError({field: "This value must be an object."})
        if (
            self.predecessor_id
            and self.predecessor.document_revision_id != self.document_revision_id
        ):
            raise ValidationError({"predecessor": "A predecessor must target the same revision."})
        if self.status == self.Status.SUCCEEDED and self.failure_code:
            raise ValidationError({"failure_code": "A successful run cannot contain a failure."})

    def __str__(self):
        return f"Analysis #{self.pk} — {self.document_revision} — {self.status}"


class AnalysisTaskRun(ImmutableFieldsMixin):
    class TaskType(models.TextChoices):
        PAGE_ANALYSIS = "page_analysis", "Page analysis"
        DOCUMENT_SYNTHESIS = "document_synthesis", "Document synthesis"

    class InputMode(models.TextChoices):
        NATIVE_TEXT = "native_text", "Native text"
        NATIVE_TEXT_VISION = "native_text_vision", "Native text and vision"
        VISION = "vision", "Vision"
        STRUCTURED_PAGE_RESULTS = "structured_page_results", "Structured page results"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    analysis_run = models.ForeignKey(
        AnalysisRun, on_delete=models.PROTECT, related_name="task_runs"
    )
    document_page = models.ForeignKey(
        DocumentPage,
        on_delete=models.PROTECT,
        related_name="analysis_task_runs",
        null=True,
        blank=True,
    )
    task_type = models.CharField(max_length=40, choices=TaskType)
    input_mode = models.CharField(max_length=40, choices=InputMode)
    status = models.CharField(max_length=20, choices=Status, default=Status.QUEUED)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3, validators=[MinValueValidator(1)])
    provider = models.CharField(max_length=80)
    model = models.CharField(max_length=160)
    prompt_version = models.CharField(max_length=80)
    schema_version = models.CharField(max_length=80)
    input_metadata = models.JSONField(default=dict)
    structured_result = models.JSONField(default=dict, blank=True)
    provider_request_id = models.CharField(max_length=255, blank=True)
    usage_metadata = models.JSONField(default=dict, blank=True)
    queued_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=50, choices=AnalysisRun.ErrorCode, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    immutable_fields = (
        "analysis_run_id",
        "document_page_id",
        "task_type",
        "input_mode",
        "max_attempts",
        "provider",
        "model",
        "prompt_version",
        "schema_version",
        "input_metadata",
        "created_at",
    )

    class Meta:
        ordering = ("analysis_run_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("analysis_run", "document_page", "task_type"),
                name="analysis_unique_page_task_per_run",
            ),
            models.UniqueConstraint(
                fields=("analysis_run", "task_type"),
                condition=Q(document_page__isnull=True),
                name="analysis_unique_document_task_per_run",
            ),
        ]

    def clean(self):
        super().clean()
        if self.task_type == self.TaskType.PAGE_ANALYSIS and not self.document_page_id:
            raise ValidationError({"document_page": "Page analysis requires an exact page."})
        if self.task_type == self.TaskType.DOCUMENT_SYNTHESIS and self.document_page_id:
            raise ValidationError({"document_page": "Document synthesis is not page scoped."})
        if (
            self.document_page_id
            and self.document_page.document_revision_id != self.analysis_run.document_revision_id
        ):
            raise ValidationError({"document_page": "The page must belong to the run revision."})
        for field in ("input_metadata", "structured_result", "usage_metadata"):
            if not isinstance(getattr(self, field), dict):
                raise ValidationError({field: "This value must be an object."})

    def __str__(self):
        return f"{self.get_task_type_display()} #{self.pk} — {self.status}"
