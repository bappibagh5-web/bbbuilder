from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.views import ProjectDocumentContextMixin
from apps.organizations.permissions import ActiveOrganizationMember, OrganizationOperator
from apps.organizations.services import active_membership
from apps.outreach.models import BidHumanReview
from apps.projects.models import ProjectContact
from apps.projects.views import OrganizationContextMixin

from .awards import (
    confirm_project_award,
    confirm_trade_award,
    create_project_award,
    create_trade_award,
    eligible_trade_reviews,
    transition_project_to_awarded,
)
from .calculations import calculate_estimate_version, calculation_queryset
from .commercial import (
    assemble_selected_reviews,
    eligible_selected_reviews,
    save_allowance,
    save_alternate,
    save_exclusion,
    save_financial_adjustment,
)
from .lifecycle import finalize_proposal, proposal_number, update_draft_content
from .models import (
    AwardedProjectHandoffSnapshot,
    Estimate,
    EstimateAllowance,
    EstimateAlternate,
    EstimateExclusion,
    EstimateFinancialAdjustment,
    EstimateVersion,
    ProjectAward,
    Proposal,
    ProposalPdfArtifact,
    ProposalVersion,
    TradeAward,
)
from .pdf import TEMPLATE_VERSION, download_response, generate_final_pdf
from .services import (
    create_estimate,
    create_estimate_version,
    create_proposal,
    create_proposal_version,
)


def _validation_error(error):
    if hasattr(error, "message_dict"):
        return serializers.ValidationError(error.message_dict)
    return serializers.ValidationError({"detail": error.messages})


def _user_label(user):
    return user.get_full_name() or user.email


def _estimate_version(version):
    return {
        "id": version.id,
        "version": version.version,
        "status": version.status,
        "status_label": version.get_status_display(),
        "supersedes_id": version.supersedes_id,
        "created_by": _user_label(version.created_by),
        "created_at": version.created_at,
        "frozen_at": version.frozen_at,
    }


def _proposal_version(version):
    artifact = next(iter(version.pdf_artifacts.all()), None)
    return {
        "id": version.id,
        "version": version.version,
        "status": version.status,
        "status_label": version.get_status_display(),
        "estimate_version_id": version.estimate_version_id,
        "estimate_version": version.estimate_version.version,
        "supersedes_id": version.supersedes_id,
        "created_by": _user_label(version.created_by),
        "created_at": version.created_at,
        "proposal_number": version.proposal_number or proposal_number(version),
        "issue_date": version.issue_date,
        "introduction": version.introduction,
        "scope_summary": version.scope_summary,
        "commercial_notes": version.commercial_notes,
        "terms_conditions": version.terms_conditions,
        "client_contact_id": version.client_contact_id,
        "client_project_snapshot": version.client_project_snapshot,
        "commercial_snapshot": version.commercial_snapshot,
        "finalized_by": _user_label(version.finalized_by) if version.finalized_by else None,
        "finalized_at": version.finalized_at,
        "pdf_artifact": None
        if artifact is None
        else {
            "id": artifact.pk,
            "filename": artifact.file_asset.original_filename,
            "generated_at": artifact.generated_at,
            "version": artifact.version,
            "template_version": artifact.template_version,
        },
        "pdf_update_available": artifact is not None
        and artifact.template_version != TEMPLATE_VERSION,
    }


def _project_award(item):
    return {
        "id": item.pk,
        "sequence": item.sequence,
        "status": item.status,
        "proposal_version_id": item.proposal_version_id,
        "proposal_number": item.proposal_version.proposal_number,
        "proposal_version": item.proposal_version.version,
        "estimate_version_id": item.estimate_version_id,
        "estimate_version": item.estimate_version.version,
        "award_amount": str(item.award_amount),
        "currency": item.currency,
        "award_date": item.award_date,
        "rationale": item.rationale,
        "client_reference": item.client_reference,
        "created_by": _user_label(item.created_by),
        "created_at": item.created_at,
        "confirmed_by": _user_label(item.confirmed_by) if item.confirmed_by else None,
        "confirmed_at": item.confirmed_at,
    }


def _trade_award(item):
    return {
        "id": item.pk,
        "sequence": item.sequence,
        "status": item.status,
        "review_id": item.human_review_id,
        "trade": item.scope_package.trade_category,
        "scope_version_id": item.scope_version_id,
        "company_id": item.company_id,
        "company_name": item.company.display_name,
        "bid_revision_id": item.bid_revision_id,
        "quoted_base_bid": str(item.quoted_base_bid),
        "evaluated_amount": str(item.evaluated_amount),
        "award_amount": str(item.award_amount),
        "currency": item.currency,
        "award_date": item.award_date,
        "rationale": item.rationale,
        "reference_number": item.reference_number,
        "created_by": _user_label(item.created_by),
        "created_at": item.created_at,
        "confirmed_by": _user_label(item.confirmed_by) if item.confirmed_by else None,
        "confirmed_at": item.confirmed_at,
    }


def _award_state(project):
    project_awards = list(
        ProjectAward.objects.filter(project=project).select_related(
            "proposal_version", "estimate_version", "created_by", "confirmed_by"
        )
    )
    trade_awards = list(
        TradeAward.objects.filter(project=project).select_related(
            "scope_package",
            "scope_version",
            "company",
            "bid_revision",
            "created_by",
            "confirmed_by",
        )
    )
    awarded_review_ids = {item.human_review_id for item in trade_awards}
    eligible = []
    for item in eligible_trade_reviews(project):
        eligible.append(
            {
                "review_id": item["review"].pk,
                "trade": item["trade"],
                "scope_version_id": item["review"].scope_version_id,
                "company_id": item["entry"].company_id,
                "company_name": item["company"],
                "bid_revision_id": item["entry"].revision_id,
                "quoted_base_bid": str(item["base_bid"]),
                "currency": item["currency"],
                "evaluated_amount": str(item["evaluated_amount"]),
                "has_award": item["review"].pk in awarded_review_ids,
            }
        )
    handoff = AwardedProjectHandoffSnapshot.objects.filter(project=project).first()
    return {
        "project_status": project.status,
        "project_awards": [_project_award(item) for item in project_awards],
        "trade_awards": [_trade_award(item) for item in trade_awards],
        "eligible_trade_awards": eligible,
        "handoff": None
        if handoff is None
        else {
            "id": handoff.pk,
            "sequence": handoff.sequence,
            "project_award_id": handoff.project_award_id,
            "created_by": _user_label(handoff.created_by),
            "created_at": handoff.created_at,
            "fingerprint": handoff.fingerprint,
        },
    }


def _money(value):
    return str(value) if value is not None else None


def _estimate_detail(version, project):
    lines = list(
        version.source_lines.select_related(
            "source_human_review",
            "source_comparison_entry",
            "source_bid_revision",
            "source_scope_version",
            "source_company",
            "source_leveling_adjustment",
        ).all()
    )
    allowances = list(version.allowances.all())
    alternates = list(version.alternates.all())
    exclusions = list(version.exclusions.all())
    adjustments = list(version.financial_adjustments.all())
    return {
        "id": version.pk,
        "version": version.version,
        "status": version.status,
        "frozen_at": version.frozen_at,
        "calculation": calculate_estimate_version(version).as_dict(),
        "eligible_selected_reviews": eligible_selected_reviews(project, version),
        "source_lines": [
            {
                "id": item.pk,
                "line_type": item.line_type,
                "description": item.description,
                "amount": _money(item.amount),
                "currency": item.currency,
                "direction": item.direction,
                "sequence": item.sequence,
                "review_id": item.source_human_review_id,
                "comparison_entry_id": item.source_comparison_entry_id,
                "bid_revision_id": item.source_bid_revision_id,
                "scope_version_id": item.source_scope_version_id,
                "company_id": item.source_company_id,
                "company_name": item.company_name_snapshot,
                "trade": item.trade_snapshot,
                "source_category": item.source_category_snapshot,
                "leveling_adjustment_id": item.source_leveling_adjustment_id,
            }
            for item in lines
        ],
        "allowances": [
            {
                "id": item.pk,
                "description": item.description,
                "amount": _money(item.amount),
                "currency": item.currency,
                "treatment": item.treatment,
                "sequence": item.sequence,
            }
            for item in allowances
        ],
        "alternates": [
            {
                "id": item.pk,
                "description": item.description,
                "direction": item.direction,
                "amount": _money(item.amount),
                "currency": item.currency,
                "included_in_estimate": item.included_in_estimate,
                "sequence": item.sequence,
            }
            for item in alternates
        ],
        "exclusions": [
            {"id": item.pk, "description": item.description, "sequence": item.sequence}
            for item in exclusions
        ],
        "financial_adjustments": [
            {
                "id": item.pk,
                "category": item.category,
                "description": item.description,
                "method": item.method,
                "basis": item.basis,
                "fixed_amount": _money(item.fixed_amount),
                "percentage_rate": str(item.percentage_rate)
                if item.percentage_rate is not None
                else None,
                "calculated_amount": _money(item.calculated_amount),
                "currency": item.currency,
                "sequence": item.sequence,
            }
            for item in adjustments
        ],
    }


def proposal_workspace(project, user):
    estimate = (
        Estimate.objects.filter(project=project)
        .select_related("created_by")
        .prefetch_related("versions__created_by")
        .first()
    )
    proposal = (
        Proposal.objects.filter(project=project)
        .select_related("created_by", "client_contact", "estimate")
        .prefetch_related(
            "versions__created_by",
            "versions__estimate_version",
            "versions__finalized_by",
            "versions__pdf_artifacts__file_asset",
        )
        .first()
    )
    membership = active_membership(user, project.organization)
    can_edit = bool(
        project.is_active
        and membership
        and membership.role in {membership.Role.ADMIN, membership.Role.ESTIMATOR_OPERATOR}
    )
    current_estimate_version = None
    if estimate is not None:
        latest = estimate.versions.order_by("-version").first()
        if latest is not None:
            latest = calculation_queryset().get(pk=latest.pk)
            current_estimate_version = _estimate_detail(latest, project)
    bound_proposal_estimate = None
    if proposal is not None:
        latest_proposal = proposal.versions.order_by("-version").first()
        if latest_proposal is not None:
            exact_version = calculation_queryset().get(pk=latest_proposal.estimate_version_id)
            bound_proposal_estimate = {
                "proposal_version_id": latest_proposal.pk,
                "estimate_version_id": exact_version.pk,
                "estimate_version": exact_version.version,
                "calculation": calculate_estimate_version(exact_version).as_dict(),
            }
    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "project_number": project.project_number,
            "client_name": project.client_name,
        },
        "can_edit": can_edit,
        "client_contacts": [
            {
                "id": item.pk,
                "name": item.person_name,
                "company": item.company_name,
                "email": item.email,
            }
            for item in project.contacts.filter(is_active=True)
        ],
        "current_estimate_version": current_estimate_version,
        "bound_proposal_estimate": bound_proposal_estimate,
        "awards": _award_state(project),
        "estimate": None
        if estimate is None
        else {
            "id": estimate.id,
            "title": estimate.title,
            "created_by": _user_label(estimate.created_by),
            "created_at": estimate.created_at,
            "versions": [_estimate_version(item) for item in estimate.versions.all()],
        },
        "proposal": None
        if proposal is None
        else {
            "id": proposal.id,
            "title": proposal.title,
            "estimate_id": proposal.estimate_id,
            "client_contact": None
            if proposal.client_contact is None
            else {
                "id": proposal.client_contact.id,
                "name": proposal.client_contact.person_name,
                "company": proposal.client_contact.company_name,
                "email": proposal.client_contact.email,
            },
            "created_by": _user_label(proposal.created_by),
            "created_at": proposal.created_at,
            "versions": [_proposal_version(item) for item in proposal.versions.all()],
            "current_version": _proposal_version(proposal.versions.order_by("-version").first()),
        },
    }


class ProposalWorkspaceView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        return Response(proposal_workspace(self.get_project(), request.user))


class EstimateCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["title"] = serializers.CharField(max_length=255, required=False)
        serializer.is_valid(raise_exception=True)
        try:
            create_estimate(
                project=self.get_project(),
                actor=request.user,
                title=serializer.validated_data.get("title"),
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(
            proposal_workspace(self.get_project(), request.user), status=status.HTTP_201_CREATED
        )


class EstimateVersionCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        estimate = get_object_or_404(
            Estimate, pk=self.kwargs["estimate_pk"], project=self.get_project()
        )
        try:
            create_estimate_version(estimate=estimate, actor=request.user)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(
            proposal_workspace(self.get_project(), request.user), status=status.HTTP_201_CREATED
        )


class ProposalCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["estimate_version_id"] = serializers.IntegerField(min_value=1)
        serializer.fields["title"] = serializers.CharField(max_length=255, required=False)
        serializer.fields["client_contact_id"] = serializers.IntegerField(
            min_value=1, required=False, allow_null=True
        )
        serializer.is_valid(raise_exception=True)
        project = self.get_project()
        estimate = get_object_or_404(Estimate, project=project)
        estimate_version = get_object_or_404(
            EstimateVersion,
            pk=serializer.validated_data["estimate_version_id"],
            estimate=estimate,
        )
        contact_id = serializer.validated_data.get("client_contact_id")
        contact = (
            get_object_or_404(ProjectContact, pk=contact_id, project=project)
            if contact_id
            else None
        )
        try:
            create_proposal(
                estimate=estimate,
                estimate_version=estimate_version,
                actor=request.user,
                title=serializer.validated_data.get("title"),
                client_contact=contact,
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user), status=status.HTTP_201_CREATED)


class ProposalVersionCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["estimate_version_id"] = serializers.IntegerField(min_value=1)
        serializer.is_valid(raise_exception=True)
        project = self.get_project()
        proposal = get_object_or_404(Proposal, pk=self.kwargs["proposal_pk"], project=project)
        estimate_version = get_object_or_404(
            EstimateVersion,
            pk=serializer.validated_data["estimate_version_id"],
            estimate=proposal.estimate,
        )
        try:
            create_proposal_version(
                proposal=proposal, estimate_version=estimate_version, actor=request.user
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user), status=status.HTTP_201_CREATED)


class ProposalVersionContentView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def patch(self, request, *args, **kwargs):
        project = self.get_project()
        version = get_object_or_404(
            ProposalVersion.objects.select_related("proposal__organization", "proposal__project"),
            pk=self.kwargs["version_pk"],
            proposal__project=project,
        )
        serializer = serializers.Serializer(data=request.data, partial=True)
        serializer.fields["issue_date"] = serializers.DateField(required=False, allow_null=True)
        for field in ("introduction", "scope_summary", "commercial_notes", "terms_conditions"):
            serializer.fields[field] = serializers.CharField(required=False, allow_blank=True)
        serializer.fields["client_contact_id"] = serializers.IntegerField(
            required=False, allow_null=True, min_value=1
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "client_contact_id" in data:
            contact_id = data.pop("client_contact_id")
            data["client_contact"] = (
                None
                if contact_id is None
                else get_object_or_404(ProjectContact, pk=contact_id, project=project)
            )
        try:
            update_draft_content(version=version, actor=request.user, data=data)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user))


class ProposalFinalizeView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        version = get_object_or_404(
            ProposalVersion, pk=self.kwargs["version_pk"], proposal__project=project
        )
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["note"] = serializers.CharField(
            required=False, allow_blank=True, max_length=2000
        )
        serializer.is_valid(raise_exception=True)
        try:
            finalize_proposal(
                version=version, actor=request.user, note=serializer.validated_data.get("note", "")
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user))


class ProposalPdfGenerateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        version = get_object_or_404(
            ProposalVersion, pk=self.kwargs["version_pk"], proposal__project=project
        )
        try:
            _, created = generate_final_pdf(version=version, actor=request.user)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(
            proposal_workspace(project, request.user),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProposalPdfDownloadView(ProjectDocumentContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        artifact = get_object_or_404(
            ProposalPdfArtifact.objects.select_related("file_asset", "proposal_version__proposal"),
            pk=self.kwargs["artifact_pk"],
            proposal_version__proposal__project=self.get_project(),
        )
        try:
            return download_response(artifact)
        except DjangoValidationError as error:
            raise _validation_error(error) from error


class AwardInputSerializer(serializers.Serializer):
    award_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    award_date = serializers.DateField()
    rationale = serializers.CharField(max_length=4000)
    client_reference = serializers.CharField(required=False, allow_blank=True, max_length=255)
    reference_number = serializers.CharField(required=False, allow_blank=True, max_length=255)
    acceptance_evidence_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class ProjectAwardCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        serializer = AwardInputSerializer(data=request.data)
        serializer.fields["proposal_version_id"] = serializers.IntegerField(min_value=1)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        version = get_object_or_404(
            ProposalVersion, pk=data.pop("proposal_version_id"), proposal__project=project
        )
        evidence_id = data.pop("acceptance_evidence_id", None)
        if evidence_id:
            from apps.documents.models import FileAsset

            data["acceptance_evidence"] = get_object_or_404(
                FileAsset, pk=evidence_id, organization=project.organization
            )
        try:
            create_project_award(
                project=project, proposal_version=version, actor=request.user, data=data
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user), status=status.HTTP_201_CREATED)


class ProjectAwardConfirmView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        award = get_object_or_404(ProjectAward, pk=self.kwargs["award_pk"], project=project)
        try:
            confirm_project_award(award=award, actor=request.user)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user))


class TradeAwardCreateView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        serializer = AwardInputSerializer(data=request.data)
        serializer.fields["review_id"] = serializers.IntegerField(min_value=1)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        review = get_object_or_404(BidHumanReview, pk=data.pop("review_id"), project=project)
        data.pop("client_reference", None)
        data.pop("acceptance_evidence_id", None)
        try:
            create_trade_award(project=project, review=review, actor=request.user, data=data)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user), status=status.HTTP_201_CREATED)


class TradeAwardConfirmView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        award = get_object_or_404(TradeAward, pk=self.kwargs["award_pk"], project=project)
        try:
            confirm_trade_award(award=award, actor=request.user)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user))


class ProjectAwardTransitionView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        award = get_object_or_404(ProjectAward, pk=self.kwargs["award_pk"], project=project)
        try:
            transition_project_to_awarded(award=award, actor=request.user)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        project.refresh_from_db()
        return Response(proposal_workspace(project, request.user))


class AwardedProjectsView(OrganizationContextMixin, APIView):
    permission_classes = (ActiveOrganizationMember,)

    def get(self, request, *args, **kwargs):
        awards = (
            ProjectAward.objects.filter(
                organization=self.get_organization(),
                status=ProjectAward.Status.CONFIRMED,
                project__status="awarded",
            )
            .select_related("project", "proposal_version", "estimate_version", "confirmed_by")
            .prefetch_related(
                "project__trade_awards__company",
                "project__trade_awards__scope_package",
                "project__award_handoffs",
            )
            .order_by("-award_date", "project__project_number")[:100]
        )
        return Response(
            {
                "results": [
                    {
                        "project_id": item.project_id,
                        "project_number": item.project.project_number,
                        "project_name": item.project.name,
                        "client_name": item.project.client_name,
                        "award_date": item.award_date,
                        "award_amount": str(item.award_amount),
                        "currency": item.currency,
                        "client_reference": item.client_reference,
                        "proposal_number": item.proposal_version.proposal_number,
                        "proposal_version": item.proposal_version.version,
                        "trade_awards": [
                            {
                                "trade": award.scope_package.trade_category,
                                "company": award.company.display_name,
                                "award_amount": str(award.award_amount),
                                "currency": award.currency,
                            }
                            for award in item.project.trade_awards.all()
                            if award.status == TradeAward.Status.CONFIRMED
                        ],
                        "handoff_ready": bool(list(item.project.award_handoffs.all())),
                    }
                    for item in awards
                ]
            }
        )


class EstimateAssemblyView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def post(self, request, *args, **kwargs):
        serializer = serializers.Serializer(data=request.data)
        serializer.fields["review_ids"] = serializers.ListField(
            child=serializers.IntegerField(min_value=1), allow_empty=False
        )
        serializer.is_valid(raise_exception=True)
        project = self.get_project()
        version = get_object_or_404(
            EstimateVersion,
            pk=self.kwargs["version_pk"],
            estimate__project=project,
        )
        try:
            assemble_selected_reviews(
                version=version,
                review_ids=serializer.validated_data["review_ids"],
                actor=request.user,
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user))


class CommercialInputSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=500, required=False)
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    treatment = serializers.CharField(max_length=20, required=False)
    direction = serializers.CharField(max_length=10, required=False)
    included_in_estimate = serializers.BooleanField(required=False)
    category = serializers.CharField(max_length=20, required=False)
    method = serializers.CharField(max_length=20, required=False)
    basis = serializers.CharField(max_length=30, required=False)
    fixed_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    percentage_rate = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )


COMMERCIAL_TYPES = {
    "allowances": (EstimateAllowance, save_allowance),
    "alternates": (EstimateAlternate, save_alternate),
    "exclusions": (EstimateExclusion, save_exclusion),
    "adjustments": (EstimateFinancialAdjustment, save_financial_adjustment),
}


class EstimateCommercialView(ProjectDocumentContextMixin, APIView):
    permission_classes = (OrganizationOperator,)

    def _context(self):
        project = self.get_project()
        version = get_object_or_404(
            EstimateVersion,
            pk=self.kwargs["version_pk"],
            estimate__project=project,
        )
        model_service = COMMERCIAL_TYPES.get(self.kwargs["kind"])
        if model_service is None:
            raise serializers.ValidationError({"detail": "Unknown commercial item type."})
        return project, version, model_service

    def post(self, request, *args, **kwargs):
        project, version, (_, service) = self._context()
        serializer = CommercialInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            service(version=version, data=serializer.validated_data, actor=request.user)
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user), status=status.HTTP_201_CREATED)

    def patch(self, request, *args, **kwargs):
        project, version, (model, service) = self._context()
        instance = get_object_or_404(model, pk=self.kwargs["item_pk"], estimate_version=version)
        serializer = CommercialInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            service(
                version=version,
                data=serializer.validated_data,
                actor=request.user,
                instance=instance,
            )
        except DjangoValidationError as error:
            raise _validation_error(error) from error
        return Response(proposal_workspace(project, request.user))
