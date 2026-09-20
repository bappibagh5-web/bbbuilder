from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Organization
from apps.organizations.permissions import ActiveOrganizationMember
from apps.outreach.models import BidComparison, BidHumanReview, InvitationCampaign
from apps.proposals.models import ProjectAward, Proposal, ProposalPdfArtifact, ProposalVersion


class ProcurementDirectoryPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def response(self, data, *, summary, filters):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "results": data,
                "summary": summary,
                "filters": filters,
            }
        )


class OrganizationDirectoryMixin:
    organization = None
    permission_classes = (ActiveOrganizationMember,)
    http_method_names = ("get", "head", "options")

    def get_organization(self):
        if self.organization is None:
            self.organization = get_object_or_404(
                Organization, slug=self.kwargs["organization_slug"]
            )
        return self.organization


class CampaignDirectoryView(OrganizationDirectoryMixin, APIView):
    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        base = InvitationCampaign.objects.filter(organization=organization)
        queryset = base.select_related("project", "scope_package", "scope_version").annotate(
            recipient_count=Count("batches__recipients", distinct=True),
            invited_count=Count(
                "batches__recipients",
                filter=Q(batches__recipients__messages__attempts__status="succeeded"),
                distinct=True,
            ),
            delivered_count=Count(
                "batches__recipients",
                filter=Q(batches__recipients__delivery_state="delivered"),
                distinct=True,
            ),
            responded_count=Count(
                "batches__recipients",
                filter=Q(batches__recipients__response_state="responded"),
                distinct=True,
            ),
            qualified_count=Count(
                "batches__recipients",
                filter=Q(batches__recipients__qualification_state="qualified"),
                distinct=True,
            ),
            not_reviewed_count=Count(
                "batches__recipients",
                filter=Q(batches__recipients__qualification_state="not_reviewed"),
                distinct=True,
            ),
            bid_count=Count("batches__recipients__bidsubmission", distinct=True),
        )
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(project__project_number__icontains=search)
                | Q(project__name__icontains=search)
                | Q(trade_category__icontains=search)
            )
        trade = request.query_params.get("trade", "").strip()
        if trade:
            queryset = queryset.filter(trade_key=trade)
        campaign_status = request.query_params.get("status", "").strip()
        if campaign_status:
            queryset = queryset.filter(status=campaign_status)
        queryset = queryset.order_by("-created_at", "-id")

        paginator = ProcurementDirectoryPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = [
            {
                "id": item.pk,
                "project_id": item.project_id,
                "project_number": item.project.project_number,
                "project_name": item.project.name,
                "trade_key": item.trade_key,
                "trade": item.trade_category,
                "scope_version_id": item.scope_version_id,
                "status": item.status,
                "recipient_count": item.recipient_count,
                "invited_count": item.invited_count,
                "delivered_count": item.delivered_count,
                "responded_count": item.responded_count,
                "qualified_count": item.qualified_count,
                "not_reviewed_count": item.not_reviewed_count,
                "bid_count": item.bid_count,
                "created_at": item.created_at,
                "project_url": f"/projects/{item.project_id}/outreach?campaign={item.pk}",
            }
            for item in page
        ]
        return paginator.response(
            rows,
            summary={
                "total": base.count(),
                "draft": base.filter(status=InvitationCampaign.Status.DRAFT).count(),
                "prepared": base.filter(status=InvitationCampaign.Status.PREPARED).count(),
                "closed": base.filter(status=InvitationCampaign.Status.CLOSED).count(),
            },
            filters={
                "trades": list(
                    base.order_by("trade_category").values("trade_key", "trade_category").distinct()
                ),
                "statuses": [
                    {"value": value, "label": label}
                    for value, label in InvitationCampaign.Status.choices
                ],
            },
        )


class ComparisonDirectoryView(OrganizationDirectoryMixin, APIView):
    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        latest_review = BidHumanReview.objects.filter(comparison_id=OuterRef("pk")).order_by(
            "-sequence", "-id"
        )
        base = BidComparison.objects.filter(organization=organization)
        queryset = base.select_related("project", "scope_package", "scope_version").annotate(
            bidder_count=Count("entries", distinct=True),
            human_review_id=Subquery(latest_review.values("id")[:1]),
            human_review_status=Subquery(latest_review.values("status")[:1]),
            human_review_version=Subquery(latest_review.values("sequence")[:1]),
            human_review_outcome=Subquery(latest_review.values("outcome")[:1]),
        )
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(project__project_number__icontains=search)
                | Q(project__name__icontains=search)
                | Q(scope_package__trade_category__icontains=search)
            )
        trade = request.query_params.get("trade", "").strip()
        if trade:
            queryset = queryset.filter(scope_package__trade_key=trade)
        comparison_status = request.query_params.get("status", "").strip()
        if comparison_status:
            queryset = queryset.filter(status=comparison_status)
        review_status = request.query_params.get("review_status", "").strip()
        if review_status == "not_started":
            queryset = queryset.filter(human_review_id__isnull=True)
        elif review_status:
            queryset = queryset.filter(human_review_status=review_status)
        queryset = queryset.order_by("-created_at", "-id")

        paginator = ProcurementDirectoryPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        rows = []
        for item in page:
            selected = (
                item.human_review_status == BidHumanReview.Status.FINALIZED
                and item.human_review_outcome == BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL
            )
            rows.append(
                {
                    "id": item.pk,
                    "project_id": item.project_id,
                    "project_number": item.project.project_number,
                    "project_name": item.project.name,
                    "trade_key": item.scope_package.trade_key,
                    "trade": item.scope_package.trade_category,
                    "scope_version_id": item.scope_version_id,
                    "status": item.status,
                    "bidder_count": item.bidder_count,
                    "human_review_id": item.human_review_id,
                    "human_review_version": item.human_review_version,
                    "human_review_status": item.human_review_status or "not_started",
                    "selected_for_proposal": selected,
                    "created_at": item.created_at,
                    "project_url": (
                        f"/projects/{item.project_id}/comparisons?comparison={item.pk}"
                    ),
                }
            )
        return paginator.response(
            rows,
            summary={
                "total": base.count(),
                "draft": base.filter(status=BidComparison.Status.DRAFT).count(),
                "ready": base.filter(status=BidComparison.Status.READY).count(),
                "selected_for_proposal": base.filter(
                    human_reviews__status=BidHumanReview.Status.FINALIZED,
                    human_reviews__outcome=BidHumanReview.Outcome.SELECTED_FOR_PROPOSAL,
                )
                .distinct()
                .count(),
            },
            filters={
                "trades": list(
                    base.order_by("scope_package__trade_category")
                    .values("scope_package__trade_key", "scope_package__trade_category")
                    .distinct()
                ),
                "statuses": [
                    {"value": value, "label": label}
                    for value, label in BidComparison.Status.choices
                ],
            },
        )


class ProposalDirectoryView(OrganizationDirectoryMixin, APIView):
    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        latest_version = ProposalVersion.objects.filter(proposal_id=OuterRef("pk")).order_by(
            "-version", "-id"
        )
        latest_award = ProjectAward.objects.filter(project_id=OuterRef("project_id")).order_by(
            "-sequence", "-id"
        )
        base = Proposal.objects.filter(organization=organization)
        directory = base.select_related("project").annotate(
            latest_version_id=Subquery(latest_version.values("id")[:1]),
            latest_version_number=Subquery(latest_version.values("version")[:1]),
            latest_version_status=Subquery(latest_version.values("status")[:1]),
            latest_award_status=Subquery(latest_award.values("status")[:1]),
        )
        queryset = directory
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(project__project_number__icontains=search)
                | Q(project__name__icontains=search)
                | Q(project__client_name__icontains=search)
                | Q(versions__proposal_number__icontains=search)
            ).distinct()
        proposal_status = request.query_params.get("status", "").strip()
        if proposal_status:
            queryset = queryset.filter(latest_version_status=proposal_status)
        award_status = request.query_params.get("award_status", "").strip()
        if award_status == "none":
            queryset = queryset.filter(latest_award_status__isnull=True)
        elif award_status:
            queryset = queryset.filter(latest_award_status=award_status)
        queryset = queryset.order_by("-created_at", "-id")

        paginator = ProcurementDirectoryPagination()
        page = list(paginator.paginate_queryset(queryset, request, view=self))
        version_ids = [item.latest_version_id for item in page if item.latest_version_id]
        versions = {
            item.pk: item
            for item in ProposalVersion.objects.filter(pk__in=version_ids).select_related(
                "estimate_version"
            )
        }
        pdf_versions = set(
            ProposalPdfArtifact.objects.filter(proposal_version_id__in=version_ids).values_list(
                "proposal_version_id", flat=True
            )
        )
        rows = []
        for item in page:
            version = versions.get(item.latest_version_id)
            snapshot = version.commercial_snapshot if version else {}
            rows.append(
                {
                    "id": item.pk,
                    "project_id": item.project_id,
                    "project_number": item.project.project_number,
                    "project_name": item.project.name,
                    "client_name": item.project.client_name,
                    "proposal_number": version.proposal_number if version else "",
                    "version_id": version.pk if version else None,
                    "version": version.version if version else None,
                    "status": version.status if version else "not_started",
                    "estimate_version_id": version.estimate_version_id if version else None,
                    "estimate_version": (version.estimate_version.version if version else None),
                    "currency": snapshot.get("currency") if version else None,
                    "proposed_amount": snapshot.get("total_amount") if version else None,
                    "pdf_available": version.pk in pdf_versions if version else False,
                    "award_status": item.latest_award_status or "not_awarded",
                    "issue_date": version.issue_date if version else None,
                    "project_url": f"/projects/{item.project_id}/proposal?proposal={item.pk}",
                }
            )
        return paginator.response(
            rows,
            summary={
                "total": base.count(),
                "draft": directory.filter(
                    latest_version_status=ProposalVersion.Status.DRAFT
                ).count(),
                "finalized": directory.filter(
                    latest_version_status=ProposalVersion.Status.FINALIZED
                ).count(),
                "awarded": base.filter(
                    project__project_awards__status=ProjectAward.Status.CONFIRMED
                )
                .distinct()
                .count(),
            },
            filters={
                "statuses": [
                    {"value": value, "label": label}
                    for value, label in ProposalVersion.Status.choices
                ],
                "award_statuses": [
                    {"value": "none", "label": "Not awarded"},
                    *[
                        {"value": value, "label": label}
                        for value, label in ProjectAward.Status.choices
                    ],
                ],
            },
        )
