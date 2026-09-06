from rest_framework import serializers

from .models import Company, DiscoveryRequest, ScopeContractorCandidate


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = (
            "id",
            "display_name",
            "website",
            "phone",
            "email",
            "address",
            "city",
            "province",
            "country",
            "source_type",
            "external_provider",
            "is_active",
        )
        read_only_fields = fields


class CandidateSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)

    class Meta:
        model = ScopeContractorCandidate
        fields = ("id", "scope_package", "status", "company", "created_at", "updated_at")
        read_only_fields = fields


class DiscoveryRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiscoveryRequest
        fields = (
            "id",
            "scope_package",
            "scope_version",
            "trade_key",
            "city",
            "province",
            "radius_km",
            "keywords",
            "search_terms",
            "provider",
            "requested_at",
            "result_count",
            "provider_metadata",
        )
        read_only_fields = fields


class SearchSerializer(serializers.Serializer):
    scope_package_id = serializers.IntegerField(min_value=1)
    city = serializers.CharField(max_length=120)
    province = serializers.CharField(max_length=80)
    country = serializers.CharField(max_length=80, required=False, default="Canada")
    radius_km = serializers.IntegerField(
        min_value=1, max_value=500, required=False, allow_null=True
    )
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, max_length=20
    )


class CandidateStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ScopeContractorCandidate.Status)
