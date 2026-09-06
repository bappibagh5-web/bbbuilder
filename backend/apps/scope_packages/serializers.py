from rest_framework import serializers

from .models import ScopePackage, ScopePackageSource, ScopePackageVersion


class ScopePackageSourceSerializer(serializers.ModelSerializer):
    finding_id = serializers.IntegerField(source="snapshot_entry.finding_id", read_only=True)
    subject = serializers.CharField(source="snapshot_entry.finding.subject", read_only=True)
    category = serializers.CharField(source="snapshot_entry.category", read_only=True)
    provenance_count = serializers.IntegerField(
        source="snapshot_entry.provenance.count", read_only=True
    )

    class Meta:
        model = ScopePackageSource
        fields = ("id", "snapshot_entry", "finding_id", "subject", "category", "provenance_count")
        read_only_fields = fields


class ScopePackageVersionSerializer(serializers.ModelSerializer):
    created_by = serializers.EmailField(source="created_by.email", read_only=True)
    sources = ScopePackageSourceSerializer(many=True, read_only=True)

    class Meta:
        model = ScopePackageVersion
        fields = (
            "id",
            "version",
            "title",
            "description",
            "inclusions",
            "exclusions",
            "clarifications",
            "status",
            "created_by",
            "created_at",
            "sources",
        )
        read_only_fields = fields


class ScopePackageSerializer(serializers.ModelSerializer):
    source_snapshot_version = serializers.IntegerField(
        source="source_snapshot.version", read_only=True
    )
    source_approval_id = serializers.IntegerField(
        source="source_snapshot.approval.id", read_only=True
    )
    current_version = ScopePackageVersionSerializer(read_only=True)
    versions = ScopePackageVersionSerializer(many=True, read_only=True)
    created_by = serializers.EmailField(source="created_by.email", read_only=True)
    updated_by = serializers.EmailField(source="updated_by.email", read_only=True)

    class Meta:
        model = ScopePackage
        fields = (
            "id",
            "project",
            "trade_key",
            "trade_category",
            "generation_rule_version",
            "lifecycle",
            "source_snapshot",
            "source_snapshot_version",
            "source_approval_id",
            "current_version",
            "versions",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ScopePackageGenerateSerializer(serializers.Serializer):
    snapshot_id = serializers.IntegerField(min_value=1)


class ScopePackageEditSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, max_length=255, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    inclusions = serializers.ListField(
        child=serializers.CharField(max_length=2000, trim_whitespace=True),
        required=False,
        max_length=500,
    )
    exclusions = serializers.ListField(
        child=serializers.CharField(max_length=2000, trim_whitespace=True),
        required=False,
        max_length=500,
    )
    clarifications = serializers.ListField(
        child=serializers.CharField(max_length=2000, trim_whitespace=True),
        required=False,
        max_length=500,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs
