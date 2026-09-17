"""Project-scoped M3-09 human bid review API."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.permissions import OrganizationOperator, OrganizationReadWritePermission

from .bid_selection import (
    create_review,
    finalize_review,
    review_data,
    review_queryset,
    save_bidder_decision,
    save_outcome,
)
from .comparison_views import ComparisonContext, validation_error
from .models import BidComparisonEntry, BidHumanDecision, BidHumanReview


class HumanReviewContext(ComparisonContext):
    def review(self):
        return get_object_or_404(review_queryset(self.comparison()), pk=self.kwargs["review_pk"])

    def fresh(self, review):
        return review_queryset(self.comparison()).get(pk=review.pk)


class BidHumanReviewListView(HumanReviewContext, APIView):
    permission_classes = (OrganizationReadWritePermission,)

    def get(self, request, *args, **kwargs):
        reviews = list(review_queryset(self.comparison()))
        return Response(
            {
                "reviews": [review_data(item) for item in reviews],
                "current": review_data(reviews[0]) if reviews else None,
            }
        )

    def post(self, request, *args, **kwargs):
        try:
            review, created = create_review(comparison=self.comparison(), actor=request.user)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(review_data(self.fresh(review)), status=201 if created else 200)


class BidHumanReviewDetailView(HumanReviewContext, APIView):
    permission_classes = (OrganizationReadWritePermission,)

    def get(self, request, *args, **kwargs):
        return Response(review_data(self.review()))

    def patch(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["outcome"] = serializers.ChoiceField(
            choices=("", *BidHumanReview.Outcome.values), allow_blank=True
        )
        serializer.fields["selected_entry_id"] = serializers.IntegerField(
            required=False, allow_null=True, min_value=1
        )
        serializer.fields["rationale"] = serializers.CharField(
            required=False, allow_blank=True, max_length=10000
        )
        serializer.is_valid(raise_exception=True)
        selected = None
        if serializer.validated_data.get("selected_entry_id"):
            selected = get_object_or_404(
                BidComparisonEntry,
                pk=serializer.validated_data["selected_entry_id"],
                comparison=self.comparison(),
            )
        try:
            review = save_outcome(
                review=self.review(),
                actor=request.user,
                outcome=serializer.validated_data["outcome"],
                selected_entry=selected,
                rationale=serializer.validated_data.get("rationale", ""),
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(review_data(self.fresh(review)))


class BidHumanDecisionView(HumanReviewContext, APIView):
    permission_classes = (OrganizationOperator,)

    def patch(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["state"] = serializers.ChoiceField(choices=BidHumanDecision.State.values)
        serializer.fields["note"] = serializers.CharField(
            required=False, allow_blank=True, max_length=5000
        )
        serializer.is_valid(raise_exception=True)
        decision = get_object_or_404(
            BidHumanDecision,
            pk=self.kwargs["decision_pk"],
            review=self.review(),
            comparison_entry__comparison=self.comparison(),
        )
        try:
            review = save_bidder_decision(
                decision=decision,
                actor=request.user,
                state=serializer.validated_data["state"],
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(review_data(self.fresh(review)))


class BidHumanReviewFinalizeView(HumanReviewContext, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        try:
            review = finalize_review(review=self.review(), actor=request.user)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(review_data(self.fresh(review)))
