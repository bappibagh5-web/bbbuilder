"""Project-scoped M3-08 bid comparison API; no provider or winner selection."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import OrganizationOperator, OrganizationReadWritePermission
from apps.scope_packages.models import ScopeItem, ScopePackageVersion

from .comparisons import (
    add_entry,
    comparison_queryset,
    create_comparison,
    detail_data,
    detail_queryset,
    eligible_ready_revisions,
    mark_comparison_ready,
    remove_adjustment,
    remove_entry,
    save_adjustment,
    save_comparison_notes,
    summary_data,
)
from .models import (
    BidCommercialItem,
    BidComparison,
    BidComparisonEntry,
    BidLevelingAdjustment,
    BidRevision,
)


def validation_error(error):
    return serializers.ValidationError(
        error.message_dict if hasattr(error, "message_dict") else {"detail": error.messages}
    )


class ComparisonContext(ProjectDocumentContextMixin):
    def comparison(self):
        return get_object_or_404(
            detail_queryset(self.get_project()),
            pk=self.kwargs["comparison_pk"],
            organization=self.get_organization(),
        )


class BidComparisonListView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationReadWritePermission,)

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        return Response(
            {
                "comparisons": [summary_data(item) for item in comparison_queryset(project)],
                "ready_revisions": eligible_ready_revisions(project),
            }
        )

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["scope_version_id"] = serializers.IntegerField(min_value=1)
        serializer.fields["notes"] = serializers.CharField(
            required=False, allow_blank=True, max_length=5000
        )
        serializer.fields["supersedes_id"] = serializers.IntegerField(
            required=False, allow_null=True, min_value=1
        )
        serializer.is_valid(raise_exception=True)
        project = self.get_project()
        version = get_object_or_404(
            ScopePackageVersion.objects.select_related("package"),
            pk=serializer.validated_data["scope_version_id"],
            package__project=project,
            package__organization=self.get_organization(),
        )
        supersedes = None
        if serializer.validated_data.get("supersedes_id"):
            supersedes = get_object_or_404(
                BidComparison,
                pk=serializer.validated_data["supersedes_id"],
                project=project,
                organization=self.get_organization(),
            )
        try:
            comparison = create_comparison(
                project=project,
                scope_version=version,
                actor=request.user,
                notes=serializer.validated_data.get("notes", ""),
                supersedes=supersedes,
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(detail_data(detail_queryset(project).get(pk=comparison.pk)), status=201)


class BidComparisonDetailView(ComparisonContext, APIView):
    permission_classes = (OrganizationReadWritePermission,)

    def get(self, request, *args, **kwargs):
        return Response(detail_data(self.comparison()))

    def patch(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["notes"] = serializers.CharField(allow_blank=True, max_length=5000)
        serializer.is_valid(raise_exception=True)
        try:
            comparison = save_comparison_notes(
                comparison=self.comparison(),
                actor=request.user,
                notes=serializer.validated_data["notes"],
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(detail_data(detail_queryset(self.get_project()).get(pk=comparison.pk)))


class BidComparisonEntryListView(ComparisonContext, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["revision_id"] = serializers.IntegerField(min_value=1)
        serializer.is_valid(raise_exception=True)
        revision = get_object_or_404(
            BidRevision,
            pk=serializer.validated_data["revision_id"],
            project=self.get_project(),
            organization=self.get_organization(),
        )
        try:
            entry = add_entry(comparison=self.comparison(), revision=revision, actor=request.user)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(
            detail_data(detail_queryset(self.get_project()).get(pk=entry.comparison_id)),
            status=201,
        )


class BidComparisonEntryDetailView(ComparisonContext, APIView):
    permission_classes = (OrganizationOperator,)

    def delete(self, request, *args, **kwargs):
        comparison = self.comparison()
        entry = get_object_or_404(
            BidComparisonEntry, pk=self.kwargs["entry_pk"], comparison=comparison
        )
        try:
            remove_entry(entry=entry, actor=request.user)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(status=204)


class BidComparisonAdjustmentListView(ComparisonContext, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        comparison = self.comparison()
        entry = get_object_or_404(
            BidComparisonEntry, pk=self.kwargs["entry_pk"], comparison=comparison
        )
        values = self._values(request, entry)
        try:
            save_adjustment(entry=entry, actor=request.user, values=values)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(
            detail_data(detail_queryset(self.get_project()).get(pk=comparison.pk)), status=201
        )

    def _values(self, request, entry):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["direction"] = serializers.ChoiceField(choices=("add", "deduct"))
        serializer.fields["amount"] = serializers.RegexField(
            r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?$"
        )
        serializer.fields["currency"] = serializers.RegexField(r"^[A-Z]{3}$")
        serializer.fields["category"] = serializers.ChoiceField(
            choices=BidLevelingAdjustment.Category.values
        )
        serializer.fields["description"] = serializers.CharField(max_length=500)
        serializer.fields["scope_item_id"] = serializers.IntegerField(
            required=False, allow_null=True, min_value=1
        )
        serializer.fields["source_commercial_item_id"] = serializers.IntegerField(
            required=False, allow_null=True, min_value=1
        )
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values["scope_item"] = None
        values["source_commercial_item"] = None
        if values.pop("scope_item_id", None):
            values["scope_item"] = get_object_or_404(
                ScopeItem,
                pk=serializer.validated_data["scope_item_id"],
                package_version=entry.comparison.scope_version,
            )
        if values.pop("source_commercial_item_id", None):
            values["source_commercial_item"] = get_object_or_404(
                BidCommercialItem,
                pk=serializer.validated_data["source_commercial_item_id"],
                revision=entry.revision,
            )
        return values


class BidComparisonAdjustmentDetailView(BidComparisonAdjustmentListView):
    def patch(self, request, *args, **kwargs):
        comparison = self.comparison()
        entry = get_object_or_404(
            BidComparisonEntry, pk=self.kwargs["entry_pk"], comparison=comparison
        )
        adjustment = get_object_or_404(
            BidLevelingAdjustment, pk=self.kwargs["adjustment_pk"], entry=entry
        )
        values = self._values(request, entry)
        try:
            save_adjustment(entry=entry, actor=request.user, values=values, adjustment=adjustment)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(detail_data(detail_queryset(self.get_project()).get(pk=comparison.pk)))

    def delete(self, request, *args, **kwargs):
        comparison = self.comparison()
        adjustment = get_object_or_404(
            BidLevelingAdjustment,
            pk=self.kwargs["adjustment_pk"],
            entry__pk=self.kwargs["entry_pk"],
            entry__comparison=comparison,
        )
        try:
            remove_adjustment(adjustment=adjustment, actor=request.user)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(status=204)


class BidComparisonReadyView(ComparisonContext, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        try:
            comparison = mark_comparison_ready(comparison=self.comparison(), actor=request.user)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(detail_data(detail_queryset(self.get_project()).get(pk=comparison.pk)))
