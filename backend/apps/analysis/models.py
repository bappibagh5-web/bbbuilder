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


class ExtractedFinding(ImmutableFieldsMixin):
    class Category(models.TextChoices):
        PROJECT_FACT = "project_fact", "Project fact"
        DATE_DEADLINE = "date_deadline", "Date / deadline"
        BID_CONDITION = "bid_condition", "Bid condition"
        SCOPE_TRADE = "scope_trade", "Scope / trade"
        RESPONSIBILITY = "responsibility", "Responsibility"
        PERMIT_INSPECTION = "permit_inspection", "Permit / inspection"
        LANDLORD_REQUIREMENT = "landlord_requirement", "Landlord requirement"
        OWNER_THIRD_PARTY_ITEM = "owner_third_party_item", "Owner / third-party item"
        COMMERCIAL = "commercial", "Commercial condition"
        SUBMITTAL_CLOSEOUT = "submittal_closeout", "Submittal / closeout"
        OPEN_QUESTION = "open_question", "Open question"

    class Support(models.TextChoices):
        EXPLICIT = "explicit", "Explicit"
        STRONGLY_SUPPORTED = "strongly_supported", "Strongly supported"
        INFERRED = "inferred", "Inferred"
        UNCERTAIN = "uncertain", "Uncertain"

    analysis_run = models.ForeignKey(AnalysisRun, on_delete=models.PROTECT, related_name="findings")
    analysis_task_run = models.ForeignKey(
        AnalysisTaskRun, on_delete=models.PROTECT, related_name="findings"
    )
    document_revision = models.ForeignKey(
        DocumentRevision, on_delete=models.PROTECT, related_name="extracted_findings"
    )
    source_candidate_key = models.CharField(max_length=64)
    semantic_key = models.CharField(max_length=255)
    category = models.CharField(max_length=40, choices=Category)
    subject = models.CharField(max_length=200)
    machine_value = models.TextField(max_length=2000)
    normalized_machine_value = models.CharField(max_length=2000)
    machine_support = models.CharField(max_length=30, choices=Support)
    schema_version = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "analysis_run_id",
        "analysis_task_run_id",
        "document_revision_id",
        "source_candidate_key",
        "semantic_key",
        "category",
        "subject",
        "machine_value",
        "normalized_machine_value",
        "machine_support",
        "schema_version",
        "created_at",
    )

    class Meta:
        ordering = ("analysis_run_id", "category", "subject", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("analysis_run", "source_candidate_key"),
                name="analysis_unique_candidate_per_run",
            )
        ]
        indexes = [models.Index(fields=("analysis_run", "semantic_key"))]

    def clean(self):
        super().clean()
        if self.analysis_task_run.analysis_run_id != self.analysis_run_id:
            raise ValidationError({"analysis_task_run": "The task must belong to the run."})
        if self.document_revision_id != self.analysis_run.document_revision_id:
            raise ValidationError({"document_revision": "The revision must belong to the run."})

    @property
    def effective_review(self):
        return self.reviews.order_by("-created_at", "-id").first()

    @property
    def review_status(self):
        review = self.effective_review
        return review.decision if review else "unreviewed"

    @property
    def effective_value(self):
        review = self.effective_review
        if review and review.decision == FindingReview.Decision.EDITED_ACCEPTED:
            return review.reviewed_value
        if review and review.decision == FindingReview.Decision.ACCEPTED:
            return self.machine_value
        return ""

    def __str__(self):
        return f"Finding #{self.pk} — {self.subject}"


class FindingSource(ImmutableFieldsMixin):
    class Relation(models.TextChoices):
        SUPPORTS = "supports", "Supports"
        CONTRADICTS = "contradicts", "Contradicts"
        QUALIFIES = "qualifies", "Qualifies"

    class EvidenceMode(models.TextChoices):
        NATIVE_TEXT = "native_text", "Native text"
        VISUAL = "visual", "Visual"
        PAGE_LABEL = "page_label", "Page label"
        OTHER = "other", "Other"

    finding = models.ForeignKey(ExtractedFinding, on_delete=models.PROTECT, related_name="sources")
    document_revision = models.ForeignKey(
        DocumentRevision, on_delete=models.PROTECT, related_name="finding_sources"
    )
    document_page = models.ForeignKey(
        DocumentPage, on_delete=models.PROTECT, related_name="finding_sources"
    )
    drawing_sheet = models.ForeignKey(
        "documents.DrawingSheet",
        on_delete=models.PROTECT,
        related_name="finding_sources",
        null=True,
        blank=True,
    )
    analysis_task_run = models.ForeignKey(
        AnalysisTaskRun, on_delete=models.PROTECT, related_name="finding_sources"
    )
    source_key = models.CharField(max_length=64)
    relation = models.CharField(max_length=20, choices=Relation, default=Relation.SUPPORTS)
    evidence_mode = models.CharField(max_length=20, choices=EvidenceMode)
    evidence_excerpt = models.CharField(max_length=500, blank=True)
    visual_evidence_description = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "finding_id",
        "document_revision_id",
        "document_page_id",
        "drawing_sheet_id",
        "analysis_task_run_id",
        "source_key",
        "relation",
        "evidence_mode",
        "evidence_excerpt",
        "visual_evidence_description",
        "created_at",
    )

    class Meta:
        ordering = ("finding_id", "document_page__page_number", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("finding", "source_key"),
                name="analysis_unique_source_per_finding",
            )
        ]

    def clean(self):
        super().clean()
        run = self.finding.analysis_run
        if self.document_revision_id != run.document_revision_id:
            raise ValidationError({"document_revision": "Source revision must match the run."})
        if self.document_page.document_revision_id != self.document_revision_id:
            raise ValidationError({"document_page": "Source page must belong to the revision."})
        if self.analysis_task_run.analysis_run_id != run.pk:
            raise ValidationError({"analysis_task_run": "Source task must belong to the run."})
        if self.analysis_task_run.document_page_id != self.document_page_id:
            raise ValidationError({"analysis_task_run": "Source task must target the source page."})
        if self.drawing_sheet_id and self.drawing_sheet.page_id != self.document_page_id:
            raise ValidationError({"drawing_sheet": "Sheet must belong to the source page."})
        if self.evidence_mode == self.EvidenceMode.NATIVE_TEXT:
            if not self.evidence_excerpt:
                raise ValidationError({"evidence_excerpt": "Native-text evidence is required."})
            if self.evidence_excerpt not in self.document_page.native_text:
                raise ValidationError(
                    {"evidence_excerpt": "Excerpt must occur in the indexed page text."}
                )
        if self.evidence_mode == self.EvidenceMode.VISUAL and self.evidence_excerpt:
            raise ValidationError(
                {"evidence_excerpt": "Visual evidence cannot contain a text excerpt."}
            )


class FindingReview(ImmutableFieldsMixin):
    class Decision(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        EDITED_ACCEPTED = "edited_accepted", "Edited / Accepted"
        REJECTED = "rejected", "Rejected"
        NEEDS_CLARIFICATION = "needs_clarification", "Needs clarification"

    finding = models.ForeignKey(ExtractedFinding, on_delete=models.PROTECT, related_name="reviews")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="finding_reviews"
    )
    decision = models.CharField(max_length=30, choices=Decision)
    reviewed_value = models.TextField(max_length=2000, blank=True)
    review_note = models.CharField(max_length=1000, blank=True)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="superseded_by",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "finding_id",
        "reviewer_id",
        "decision",
        "reviewed_value",
        "review_note",
        "supersedes_id",
        "created_at",
    )

    class Meta:
        ordering = ("finding_id", "created_at", "id")

    def clean(self):
        super().clean()
        if self.decision == self.Decision.EDITED_ACCEPTED and not self.reviewed_value.strip():
            raise ValidationError(
                {"reviewed_value": "Edited / Accepted requires a reviewed value."}
            )
        if self.decision != self.Decision.EDITED_ACCEPTED and self.reviewed_value:
            raise ValidationError(
                {"reviewed_value": "Only Edited / Accepted stores a reviewed value."}
            )
        if self.supersedes_id and self.supersedes.finding_id != self.finding_id:
            raise ValidationError({"supersedes": "Review must supersede the same finding."})


class IntelligenceConflict(ImmutableFieldsMixin):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="intelligence_conflicts"
    )
    analysis_run = models.ForeignKey(
        AnalysisRun, on_delete=models.PROTECT, related_name="intelligence_conflicts"
    )
    semantic_key = models.CharField(max_length=255)
    participant_key = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    conflict_type = models.CharField(max_length=40, default="value_mismatch")
    explanation = models.CharField(max_length=1000)
    status = models.CharField(max_length=20, choices=Status, default=Status.OPEN)
    findings = models.ManyToManyField(ExtractedFinding, related_name="conflicts")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="resolved_intelligence_conflicts",
        null=True,
        blank=True,
    )
    resolution_note = models.CharField(max_length=1000, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="superseded_by",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    immutable_fields = (
        "project_id",
        "analysis_run_id",
        "semantic_key",
        "participant_key",
        "version",
        "conflict_type",
        "explanation",
        "status",
        "resolved_by_id",
        "resolution_note",
        "resolved_at",
        "supersedes_id",
        "created_at",
    )

    class Meta:
        ordering = ("status", "semantic_key", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("analysis_run", "participant_key", "version"),
                name="analysis_unique_conflict_version",
            )
        ]

    def clean(self):
        super().clean()
        if self.analysis_run.project.pk != self.project_id:
            raise ValidationError({"project": "Conflict project must match the run."})
        if self.status == self.Status.OPEN and (
            self.resolved_by_id or self.resolved_at or self.resolution_note
        ):
            raise ValidationError("Open conflicts cannot contain resolution fields.")
        if self.status != self.Status.OPEN and not self.resolved_by_id:
            raise ValidationError({"resolved_by": "Resolved conflicts require an actor."})
        if self.supersedes_id and (
            self.supersedes.analysis_run_id != self.analysis_run_id
            or self.supersedes.participant_key != self.participant_key
            or self.version != self.supersedes.version + 1
        ):
            raise ValidationError({"supersedes": "Conflict versions must form one chain."})
