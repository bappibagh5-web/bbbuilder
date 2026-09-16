"""Project-scoped manual bid structuring API. No provider or comparison calls."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import OrganizationOperator, OrganizationReadWritePermission
from apps.scope_packages.models import ScopeItem

from .bid_extraction import request_extraction
from .bid_revisions import (
    add_evidence,
    create_revision,
    decide_candidate,
    mark_ready,
    readiness,
    remove_commercial_item,
    remove_evidence,
    save_commercial_item,
    save_scope_coverage,
    save_summary,
)
from .models import (
    BidAttachment,
    BidCommercialItem,
    BidEvidence,
    BidExtractionRun,
    BidRevision,
    BidScopeCoverage,
    BidSubmission,
)


def validation_error(error):
    return serializers.ValidationError(
        error.message_dict if hasattr(error, "message_dict") else {"detail": error.messages}
    )


def revision_data(revision):
    return {
        "id": revision.pk,
        "sequence": revision.sequence,
        "contractor_label": revision.contractor_label,
        "status": revision.status,
        "supersedes_id": revision.supersedes_id,
        "superseded_by_ids": [item.pk for item in revision.successors.all()],
        "submission_id": revision.submission_id,
        "scope_version_id": revision.scope_version_id,
        "currency": revision.currency,
        "currency_review": revision.currency_review,
        "base_bid": str(revision.base_bid) if revision.base_bid is not None else None,
        "base_bid_review": revision.base_bid_review,
        "tax_treatment": revision.tax_treatment,
        "tax_reviewed": revision.tax_reviewed,
        "commercial_items_reviewed": revision.commercial_items_reviewed,
        "scope_reviewed": revision.scope_reviewed,
        "validity_date": revision.validity_date,
        "validity_days": revision.validity_days,
        "schedule_text": revision.schedule_text,
        "estimator_notes": revision.estimator_notes,
        "created_by_id": revision.created_by_id,
        "reviewed_by_id": revision.reviewed_by_id,
        "created_at": revision.created_at,
        "reviewed_at": revision.reviewed_at,
        "readiness_blockers": readiness(revision) if revision.status == "draft" else [],
        "commercial_items": [
            {
                "id": item.pk,
                "sequence": item.sequence,
                "kind": item.kind,
                "contractor_label": item.contractor_label,
                "title": item.title,
                "description": item.description,
                "category": item.category,
                "treatment": item.treatment,
                "amount": str(item.amount) if item.amount is not None else None,
                "currency": item.currency,
                "included_in_base": item.included_in_base,
                "scope_item_id": item.scope_item_id,
                "estimator_note": item.estimator_note,
            }
            for item in revision.commercial_items.all()
        ],
        "scope_coverage": [
            {
                "id": item.pk,
                "scope_item_id": item.scope_item_id,
                "state": item.state,
                "wording": item.wording,
                "estimator_note": item.estimator_note,
                "reviewed": item.reviewed,
            }
            for item in revision.scope_coverage.all()
        ],
        "evidence": [
            {
                "id": item.pk,
                "attachment_id": item.attachment_id,
                "commercial_item_id": item.commercial_item_id,
                "coverage_id": item.coverage_id,
                "field_key": item.field_key,
                "source": item.source,
                "page_number": item.page_number,
                "excerpt": item.excerpt,
                "note": item.note,
            }
            for item in revision.evidence.all()
        ],
    }


class BidRevisionContext(ProjectDocumentContextMixin):
    def submission(self):
        return get_object_or_404(
            BidSubmission,
            pk=self.kwargs["submission_pk"],
            organization=self.get_organization(),
            project=self.get_project(),
        )

    def revision(self):
        return get_object_or_404(
            BidRevision.objects.select_related("submission", "scope_version").prefetch_related(
                "commercial_items", "scope_coverage", "evidence", "successors"
            ),
            pk=self.kwargs["revision_pk"],
            submission=self.submission(),
        )


class BidRevisionListView(BidRevisionContext, APIView):
    permission_classes = (OrganizationReadWritePermission,)

    def get(self, request, *args, **kwargs):
        submission = self.submission()
        revisions = (
            BidRevision.objects.filter(submission=submission)
            .select_related("scope_version")
            .prefetch_related("commercial_items", "scope_coverage", "evidence", "successors")
        )
        scope_items = ScopeItem.objects.filter(package_version=submission.scope_version)
        return Response(
            {
                "revisions": [revision_data(item) for item in revisions],
                "scope_items": [
                    {"id": item.pk, "title": item.title, "sequence": item.sequence}
                    for item in scope_items
                ],
            }
        )

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["contractor_label"] = serializers.CharField(
            required=False, allow_blank=True, max_length=120
        )
        serializer.fields["supersedes_id"] = serializers.IntegerField(required=False, min_value=1)
        serializer.fields["request_key"] = serializers.UUIDField(required=False)
        serializer.is_valid(raise_exception=True)
        submission = self.submission()
        supersedes = None
        if serializer.validated_data.get("supersedes_id"):
            supersedes = get_object_or_404(
                BidRevision,
                pk=serializer.validated_data["supersedes_id"],
                recipient=submission.recipient,
                scope_version=submission.scope_version,
            )
        try:
            revision = create_revision(
                submission=submission,
                actor=request.user,
                label=serializer.validated_data.get("contractor_label", ""),
                supersedes=supersedes,
                request_key=serializer.validated_data.get("request_key"),
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(revision_data(revision), status=201)


class BidRevisionDetailView(BidRevisionContext, APIView):
    permission_classes = (OrganizationReadWritePermission,)

    def get(self, request, *args, **kwargs):
        return Response(revision_data(self.revision()))

    def patch(self, request, *args, **kwargs):
        try:
            revision = save_summary(
                revision=self.revision(), actor=request.user, values=dict(request.data)
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(revision_data(revision))


class BidRevisionReadyView(BidRevisionContext, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        try:
            revision = mark_ready(revision=self.revision(), actor=request.user)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(revision_data(revision))


class BidCommercialItemView(BidRevisionContext, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        try:
            item = save_commercial_item(
                revision=self.revision(), actor=request.user, values=dict(request.data)
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response({"id": item.pk}, status=201)

    def patch(self, request, *args, **kwargs):
        item = get_object_or_404(
            BidCommercialItem, pk=self.kwargs["item_pk"], revision=self.revision()
        )
        try:
            item = save_commercial_item(
                revision=self.revision(), actor=request.user, values=dict(request.data), item=item
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response({"id": item.pk})

    def delete(self, request, *args, **kwargs):
        item = get_object_or_404(
            BidCommercialItem, pk=self.kwargs["item_pk"], revision=self.revision()
        )
        try:
            remove_commercial_item(revision=self.revision(), actor=request.user, item=item)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(status=204)


class BidScopeCoverageView(BidRevisionContext, APIView):
    permission_classes = (OrganizationReadWritePermission,)

    def put(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["state"] = serializers.ChoiceField(
            choices=(
                "included",
                "excluded",
                "qualified",
                "not_addressed",
                "needs_clarification",
            )
        )
        serializer.fields["wording"] = serializers.CharField(required=False, allow_blank=True)
        serializer.fields["estimator_note"] = serializers.CharField(
            required=False, allow_blank=True, max_length=1000
        )
        serializer.fields["reviewed"] = serializers.BooleanField(required=False)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        scope_item = get_object_or_404(
            ScopeItem,
            pk=self.kwargs["scope_item_pk"],
            package_version=self.submission().scope_version,
        )
        try:
            item = save_scope_coverage(
                revision=self.revision(),
                actor=request.user,
                scope_item=scope_item,
                state=values["state"],
                wording=values.get("wording", ""),
                note=values.get("estimator_note", ""),
                reviewed=values.get("reviewed", False),
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response({"id": item.pk})


class BidEvidenceView(BidRevisionContext, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        revision = self.revision()
        serializer = serializers.Serializer(data=request.data)
        for field in ("attachment_id", "commercial_item_id", "coverage_id", "page_number"):
            serializer.fields[field] = serializers.IntegerField(
                required=False, allow_null=True, min_value=1
            )
        serializer.fields["field_key"] = serializers.CharField(
            required=False, allow_blank=True, max_length=50
        )
        serializer.fields["source"] = serializers.ChoiceField(
            required=False, choices=("quote", "estimator", "contractor")
        )
        serializer.fields["excerpt"] = serializers.CharField(required=False, allow_blank=True)
        serializer.fields["note"] = serializers.CharField(
            required=False, allow_blank=True, max_length=1000
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        attachment = None
        commercial_item = None
        coverage = None
        if values.get("attachment_id"):
            attachment = get_object_or_404(
                BidAttachment, pk=values["attachment_id"], submission=self.submission()
            )
        if values.get("commercial_item_id"):
            commercial_item = get_object_or_404(
                BidCommercialItem, pk=values["commercial_item_id"], revision=revision
            )
        if values.get("coverage_id"):
            coverage = get_object_or_404(
                BidScopeCoverage, pk=values["coverage_id"], revision=revision
            )
        try:
            evidence = add_evidence(
                revision=revision,
                actor=request.user,
                attachment=attachment,
                commercial_item=commercial_item,
                coverage=coverage,
                field_key=values.get("field_key", ""),
                source=values.get("source", "quote"),
                page_number=values.get("page_number"),
                excerpt=values.get("excerpt", ""),
                note=values.get("note", ""),
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response({"id": evidence.pk}, status=201)

    def delete(self, request, *args, **kwargs):
        evidence = get_object_or_404(
            BidEvidence, pk=self.kwargs["evidence_pk"], revision=self.revision()
        )
        try:
            remove_evidence(revision=self.revision(), actor=request.user, evidence=evidence)
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(status=204)


def extraction_data(run):
    return {
        "id": run.pk,
        "attachment_id": run.attachment_id,
        "status": run.status,
        "provider": run.provider,
        "model": run.model,
        "schema_version": run.schema_version,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "candidate_count": len(run.candidates),
        "candidates": run.candidates,
        "decisions": [
            {
                "id": decision.pk,
                "candidate_index": decision.candidate_index,
                "revision_id": decision.revision_id,
                "decision": decision.decision,
            }
            for decision in run.decisions.all()
        ],
        "usage": run.usage,
        "safe_error_code": run.safe_error_code,
        "safe_error_message": run.safe_error_message,
    }


class BidExtractionView(BidRevisionContext, APIView):
    permission_classes = (OrganizationReadWritePermission,)

    def get(self, request, *args, **kwargs):
        runs = BidExtractionRun.objects.filter(submission=self.submission()).prefetch_related(
            "decisions"
        )
        return Response({"runs": [extraction_data(run) for run in runs]})

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["attachment_id"] = serializers.IntegerField(min_value=1)
        serializer.fields["request_key"] = serializers.UUIDField(required=False)
        serializer.is_valid(raise_exception=True)
        attachment = get_object_or_404(
            BidAttachment,
            pk=serializer.validated_data["attachment_id"],
            submission=self.submission(),
        )
        try:
            run = request_extraction(
                attachment=attachment,
                actor=request.user,
                request_key=serializer.validated_data.get("request_key"),
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response(extraction_data(run), status=201)


class BidCandidateDecisionView(BidRevisionContext, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        run = get_object_or_404(
            BidExtractionRun, pk=self.kwargs["run_pk"], submission=self.submission()
        )
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["candidate_index"] = serializers.IntegerField(min_value=0)
        serializer.fields["decision"] = serializers.ChoiceField(
            choices=("accepted", "corrected", "ignored")
        )
        serializer.fields["corrections"] = serializers.DictField(required=False)
        serializer.is_valid(raise_exception=True)
        try:
            decision = decide_candidate(
                run=run,
                revision=self.revision(),
                actor=request.user,
                index=serializer.validated_data["candidate_index"],
                decision=serializer.validated_data["decision"],
                corrections=serializer.validated_data.get("corrections", {}),
            )
        except DjangoValidationError as error:
            raise validation_error(error) from error
        return Response({"id": decision.pk, "decision": decision.decision})
