from rest_framework import serializers

from .models import Document, DocumentRevision, FileAsset, ProjectFile


class FileAssetMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileAsset
        fields = (
            "id",
            "storage_backend",
            "original_filename",
            "declared_mime_type",
            "detected_mime_type",
            "byte_size",
            "checksum_algorithm",
            "checksum",
            "created_at",
        )


class ProjectFileMetadataSerializer(serializers.ModelSerializer):
    file_asset = FileAssetMetadataSerializer(read_only=True)

    class Meta:
        model = ProjectFile
        fields = ("id", "display_name", "file_asset", "created_at")


class DocumentRevisionSerializer(serializers.ModelSerializer):
    project_file = ProjectFileMetadataSerializer(read_only=True)

    class Meta:
        model = DocumentRevision
        fields = (
            "id",
            "document",
            "project_file",
            "revision_label",
            "issued_date",
            "received_at",
            "source_filename",
            "notes",
            "supersedes",
            "created_by",
            "created_at",
        )
        read_only_fields = fields


class DocumentSerializer(serializers.ModelSerializer):
    current_revision = DocumentRevisionSerializer(read_only=True)
    revision_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Document
        fields = (
            "id",
            "project",
            "title",
            "category",
            "discipline",
            "description",
            "is_active",
            "current_revision",
            "revision_count",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields
