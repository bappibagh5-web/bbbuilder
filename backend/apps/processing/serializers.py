from rest_framework import serializers

from .models import ProcessingJob


class ProcessingJobSerializer(serializers.ModelSerializer):
    document_revision = serializers.IntegerField(source="document_revision_id", read_only=True)

    class Meta:
        model = ProcessingJob
        fields = (
            "id",
            "document_revision",
            "job_type",
            "status",
            "attempt_count",
            "max_attempts",
            "queued_at",
            "started_at",
            "finished_at",
            "heartbeat_at",
            "error_code",
            "error_message",
            "result_metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
