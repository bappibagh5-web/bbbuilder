from django.db.models import F
from rest_framework import serializers

from .models import Company, Contact, DiscoveryRequest, ScopeContractorCandidate, TradeCapability
from .ranking import rank_candidate
from .services import contact_is_ready


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
            "latitude",
            "longitude",
            "is_active",
        )
        read_only_fields = fields


class CandidateSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    match_score = serializers.SerializerMethodField()
    match_reasons = serializers.SerializerMethodField()
    google_rating = serializers.SerializerMethodField()
    google_review_count = serializers.SerializerMethodField()
    distance_miles = serializers.SerializerMethodField()

    @staticmethod
    def ranking(candidate):
        if not hasattr(candidate, "_candidate_ranking"):
            candidate._candidate_ranking = rank_candidate(candidate)
        return candidate._candidate_ranking

    def get_match_score(self, candidate):
        return self.ranking(candidate).score

    def get_match_reasons(self, candidate):
        return self.ranking(candidate).reasons

    def get_google_rating(self, candidate):
        return self.ranking(candidate).google_rating

    def get_google_review_count(self, candidate):
        return self.ranking(candidate).google_review_count

    def get_distance_miles(self, candidate):
        return self.ranking(candidate).distance_miles

    class Meta:
        model = ScopeContractorCandidate
        fields = (
            "id",
            "scope_package",
            "scope_version",
            "status",
            "company",
            "match_score",
            "match_reasons",
            "google_rating",
            "google_review_count",
            "distance_miles",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = (
            "id",
            "name",
            "title",
            "email",
            "phone",
            "is_primary",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ContactWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not self.partial and not attrs.get("name", "").strip():
            raise serializers.ValidationError({"name": "This field is required."})
        return attrs


class TradeCapabilitySerializer(serializers.ModelSerializer):
    trade_label = serializers.CharField(source="get_trade_key_display", read_only=True)

    class Meta:
        model = TradeCapability
        fields = (
            "id",
            "trade_key",
            "trade_label",
            "keywords",
            "service_cities",
            "province",
            "is_active",
        )
        read_only_fields = fields


class CompanyProfileSerializer(CompanySerializer):
    trade_capabilities = TradeCapabilitySerializer(many=True, read_only=True)
    contacts = ContactSerializer(many=True, read_only=True)
    contact_ready = serializers.SerializerMethodField()
    shortlist_statuses = serializers.SerializerMethodField()
    google_rating = serializers.SerializerMethodField()
    google_review_count = serializers.SerializerMethodField()

    def get_contact_ready(self, company):
        return contact_is_ready(company)

    def get_shortlist_statuses(self, company):
        project = self.context["project"]
        return [
            {
                "scope_package": candidate.scope_package_id,
                "trade_category": candidate.scope_package.trade_category,
                "status": candidate.status,
            }
            for candidate in company.project_candidates.filter(
                project=project,
                scope_package__lifecycle="active",
                scope_version=F("scope_package__current_version"),
            ).select_related("scope_package")
        ]

    @staticmethod
    def google_quality(company):
        ratings = []
        reviews = []
        for capability in company.trade_capabilities.all():
            metadata = (
                capability.source_metadata if isinstance(capability.source_metadata, dict) else {}
            )
            rating = metadata.get("rating")
            review_count = metadata.get("review_count")
            if isinstance(rating, (int, float)) and not isinstance(rating, bool):
                ratings.append(float(rating))
            if isinstance(review_count, int) and not isinstance(review_count, bool):
                reviews.append(review_count)
        return max(ratings, default=None), max(reviews, default=None)

    def get_google_rating(self, company):
        return self.google_quality(company)[0]

    def get_google_review_count(self, company):
        return self.google_quality(company)[1]

    class Meta(CompanySerializer.Meta):
        fields = CompanySerializer.Meta.fields + (
            "trade_capabilities",
            "contacts",
            "contact_ready",
            "shortlist_statuses",
            "google_rating",
            "google_review_count",
        )


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
            "radius_miles",
            "center_reference",
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
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, max_length=20
    )


class CandidateStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ScopeContractorCandidate.Status)
