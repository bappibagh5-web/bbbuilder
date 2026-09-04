from rest_framework import serializers

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


class AnalysisTaskRunSerializer(serializers.ModelSerializer):
    document_page = serializers.IntegerField(source="document_page_id", read_only=True)
    page_number = serializers.IntegerField(source="document_page.page_number", read_only=True)
    sheet_number = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisTaskRun
        fields = (
            "id",
            "analysis_run",
            "document_page",
            "page_number",
            "sheet_number",
            "task_type",
            "input_mode",
            "status",
            "attempt_count",
            "max_attempts",
            "provider",
            "model",
            "prompt_version",
            "schema_version",
            "input_metadata",
            "structured_result",
            "usage_metadata",
            "queued_at",
            "started_at",
            "finished_at",
            "error_code",
            "safe_error_message",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_sheet_number(self, obj):
        if not obj.document_page_id:
            return ""
        sheet = getattr(obj.document_page, "drawing_sheet", None)
        return sheet.sheet_number if sheet else ""


class AnalysisRunSerializer(serializers.ModelSerializer):
    document_revision = serializers.IntegerField(source="document_revision_id", read_only=True)
    document = serializers.IntegerField(source="document_revision.document_id", read_only=True)
    requested_by = serializers.CharField(source="requested_by.email", read_only=True)
    predecessor = serializers.IntegerField(source="predecessor_id", read_only=True)
    task_counts = serializers.SerializerMethodField()
    input_manifest = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisRun
        fields = (
            "id",
            "document_revision",
            "document",
            "requested_by",
            "predecessor",
            "status",
            "provider",
            "model",
            "prompt_version",
            "schema_version",
            "analysis_version",
            "input_manifest",
            "result_summary",
            "usage_metadata",
            "task_counts",
            "queued_at",
            "started_at",
            "finished_at",
            "failure_code",
            "safe_failure_message",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_task_counts(self, obj):
        counts = {"total": 0, "queued": 0, "running": 0, "succeeded": 0, "failed": 0}
        for task in obj.task_runs.all():
            counts["total"] += 1
            counts[task.status] += 1
        return counts

    def get_input_manifest(self, obj):
        return {
            "document_revision_id": obj.input_manifest.get("document_revision_id"),
            "page_ids": obj.input_manifest.get("page_ids", []),
            "page_count": obj.input_manifest.get("page_count", 0),
        }


class FindingSourceSerializer(serializers.ModelSerializer):
    document_title = serializers.CharField(
        source="document_revision.document.title", read_only=True
    )
    revision_label = serializers.CharField(
        source="document_revision.revision_label", read_only=True
    )
    page_number = serializers.IntegerField(source="document_page.page_number", read_only=True)
    sheet_number = serializers.CharField(
        source="drawing_sheet.sheet_number", read_only=True, default=""
    )
    sheet_title = serializers.CharField(
        source="drawing_sheet.sheet_title", read_only=True, default=""
    )

    class Meta:
        model = FindingSource
        fields = (
            "id",
            "document_revision",
            "document_page",
            "document_title",
            "revision_label",
            "page_number",
            "drawing_sheet",
            "sheet_number",
            "sheet_title",
            "analysis_task_run",
            "relation",
            "evidence_mode",
            "evidence_excerpt",
            "visual_evidence_description",
            "created_at",
        )
        read_only_fields = fields


class FindingReviewSerializer(serializers.ModelSerializer):
    reviewer = serializers.CharField(source="reviewer.email", read_only=True)

    class Meta:
        model = FindingReview
        fields = (
            "id",
            "finding",
            "reviewer",
            "decision",
            "reviewed_value",
            "review_note",
            "supersedes",
            "created_at",
        )
        read_only_fields = fields


class FindingReviewCreateSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=FindingReview.Decision)
    reviewed_value = serializers.CharField(
        required=False, allow_blank=True, max_length=2000, trim_whitespace=True
    )
    review_note = serializers.CharField(
        required=False, allow_blank=True, max_length=1000, trim_whitespace=True
    )

    def validate(self, attrs):
        value = attrs.get("reviewed_value", "")
        if attrs["decision"] == FindingReview.Decision.EDITED_ACCEPTED and not value:
            raise serializers.ValidationError(
                {"reviewed_value": "Edited / Accepted requires a reviewed value."}
            )
        if attrs["decision"] != FindingReview.Decision.EDITED_ACCEPTED and value:
            raise serializers.ValidationError(
                {"reviewed_value": "Only Edited / Accepted accepts a reviewed value."}
            )
        return attrs


class ExtractedFindingSerializer(serializers.ModelSerializer):
    sources = FindingSourceSerializer(many=True, read_only=True)
    reviews = FindingReviewSerializer(many=True, read_only=True)
    review_status = serializers.CharField(read_only=True)
    effective_value = serializers.CharField(read_only=True)

    class Meta:
        model = ExtractedFinding
        fields = (
            "id",
            "analysis_run",
            "analysis_task_run",
            "document_revision",
            "source_candidate_key",
            "semantic_key",
            "category",
            "subject",
            "machine_value",
            "machine_support",
            "schema_version",
            "review_status",
            "effective_value",
            "sources",
            "reviews",
            "created_at",
        )
        read_only_fields = fields


class IntelligenceConflictSerializer(serializers.ModelSerializer):
    findings = ExtractedFindingSerializer(many=True, read_only=True)
    resolved_by = serializers.CharField(source="resolved_by.email", read_only=True)

    class Meta:
        model = IntelligenceConflict
        fields = (
            "id",
            "analysis_run",
            "semantic_key",
            "participant_key",
            "version",
            "conflict_type",
            "explanation",
            "status",
            "findings",
            "resolved_by",
            "resolution_note",
            "resolved_at",
            "supersedes",
            "created_at",
        )
        read_only_fields = fields


class ConflictResolutionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            IntelligenceConflict.Status.RESOLVED,
            IntelligenceConflict.Status.DISMISSED,
        )
    )
    resolution_note = serializers.CharField(
        required=False, allow_blank=True, max_length=1000, trim_whitespace=True
    )


class SnapshotProvenanceSerializer(serializers.ModelSerializer):
    page_number = serializers.IntegerField(source="document_page.page_number", read_only=True)
    sheet_number = serializers.CharField(
        source="drawing_sheet.sheet_number", read_only=True, default=""
    )
    sheet_title = serializers.CharField(
        source="drawing_sheet.sheet_title", read_only=True, default=""
    )
    evidence_excerpt = serializers.CharField(
        source="finding_source.evidence_excerpt", read_only=True
    )
    visual_evidence_description = serializers.CharField(
        source="finding_source.visual_evidence_description", read_only=True
    )

    class Meta:
        model = ProjectIntelligenceSnapshotProvenance
        fields = (
            "id",
            "finding_source",
            "document_revision",
            "document_page",
            "page_number",
            "drawing_sheet",
            "sheet_number",
            "sheet_title",
            "analysis_task_run",
            "evidence_excerpt",
            "visual_evidence_description",
        )
        read_only_fields = fields


class SnapshotEntrySerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="finding.subject", read_only=True)
    machine_value = serializers.CharField(source="finding.machine_value", read_only=True)
    provenance = SnapshotProvenanceSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectIntelligenceSnapshotEntry
        fields = (
            "id",
            "finding",
            "finding_review",
            "decision",
            "effective_value",
            "semantic_key",
            "category",
            "subject",
            "machine_value",
            "included_in_intelligence",
            "provenance",
        )
        read_only_fields = fields


class SnapshotSourceSerializer(serializers.ModelSerializer):
    document = serializers.IntegerField(source="document_revision.document_id", read_only=True)
    document_title = serializers.CharField(
        source="document_revision.document.title", read_only=True
    )
    revision_label = serializers.CharField(
        source="document_revision.revision_label", read_only=True
    )
    document_is_active = serializers.BooleanField(
        source="document_revision.document.is_active", read_only=True
    )
    entries = SnapshotEntrySerializer(many=True, read_only=True)

    class Meta:
        model = ProjectIntelligenceSnapshotSource
        fields = (
            "id",
            "analysis_run",
            "document",
            "document_title",
            "document_revision",
            "revision_label",
            "document_is_active",
            "entries",
        )
        read_only_fields = fields


class IntelligenceApprovalSerializer(serializers.ModelSerializer):
    approver = serializers.CharField(source="approver.email", read_only=True)

    class Meta:
        model = ProjectIntelligenceApproval
        fields = (
            "id",
            "project",
            "snapshot",
            "approver",
            "approved_at",
            "approval_note",
            "readiness_result",
        )
        read_only_fields = fields


class IntelligenceSnapshotSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.email", read_only=True)
    sources = SnapshotSourceSerializer(many=True, read_only=True)
    approval = serializers.SerializerMethodField()
    is_stale = serializers.SerializerMethodField()
    approval_blockers = serializers.SerializerMethodField()

    class Meta:
        model = ProjectIntelligenceSnapshot
        fields = (
            "id",
            "project",
            "version",
            "fingerprint",
            "schema_version",
            "summary_counts",
            "created_by",
            "created_at",
            "sources",
            "approval",
            "is_stale",
            "approval_blockers",
        )
        read_only_fields = fields

    def get_approval(self, obj):
        try:
            approval = obj.approval
        except ProjectIntelligenceApproval.DoesNotExist:
            return None
        return IntelligenceApprovalSerializer(approval).data

    def get_is_stale(self, obj):
        return self.context.get("stale_by_id", {}).get(obj.pk, False)

    def get_approval_blockers(self, obj):
        return self.context.get("approval_blockers_by_id", {}).get(obj.pk, [])


class IntelligenceSnapshotCreateSerializer(serializers.Serializer):
    analysis_run_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=100
    )

    def validate_analysis_run_ids(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("Analysis run IDs must be unique.")
        return values


class IntelligenceReadinessSerializer(IntelligenceSnapshotCreateSerializer):
    pass


class IntelligenceApprovalCreateSerializer(serializers.Serializer):
    approval_note = serializers.CharField(
        required=False, allow_blank=True, max_length=1000, trim_whitespace=True
    )
