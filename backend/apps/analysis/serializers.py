from rest_framework import serializers

from .models import AnalysisRun, AnalysisTaskRun


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
