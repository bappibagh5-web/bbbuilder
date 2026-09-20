from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import Organization
from apps.organizations.permissions import ActiveOrganizationMember

from .models import AuditEvent, Project

FAMILIES = (
    ("projects", "Projects"),
    ("documents", "Documents"),
    ("reviews", "Project Review"),
    ("scopes", "Trade Scopes"),
    ("contractors", "Contractors"),
    ("outreach", "Outreach"),
    ("bids", "Bids"),
    ("comparisons", "Comparisons"),
    ("proposals", "Proposals"),
    ("awards", "Awards"),
    ("organization", "Organization"),
    ("other", "Other"),
)
FAMILY_LABELS = dict(FAMILIES)
PREFIX_FAMILIES = {
    "projects": ("project", "project_contact"),
    "documents": (
        "document",
        "document_revision",
        "file",
        "processing",
        "pdf_indexing",
        "presentation_indexing",
        "project_document_set",
    ),
    "reviews": (
        "analysis",
        "project_set_analysis",
        "finding",
        "findings",
        "conflict",
        "intelligence_snapshot",
    ),
    "scopes": ("scope_generation", "scope_package"),
    "contractors": ("contractor_candidate", "contractor_contact", "contractor_discovery"),
    "outreach": (
        "outreach_campaign",
        "outreach_batch",
        "outreach_recipient",
        "outreach_message",
        "outreach_delivery",
        "outreach_qualification",
    ),
    "bids": (
        "quote_submission",
        "quote_attachment",
        "manual_quote_uploaded",
        "bid_revision",
        "bid_extraction",
    ),
    "comparisons": ("bid_comparison", "bid_leveling_adjustment", "bid_human_review"),
    "proposals": ("estimate", "proposal"),
    "awards": ("project_award", "trade_award", "awarded_handoff"),
    "organization": ("smtp_configuration", "smtp_connection", "smtp_test_email", "outreach_sender"),
}
ACTION_LABELS = {
    "project.created": "Project created",
    "project.archived": "Project archived",
    "project.reactivated": "Project reactivated",
    "project.updated": "Project details updated",
    "project.status_changed": "Project status changed",
    "project.awarded": "Project transitioned to Awarded",
    "project_document_set.updated": "Estimating document set updated",
    "analysis.requested": "Document review requested",
    "analysis.retry_requested": "Document review retry requested",
    "analysis.completed": "Document review completed",
    "analysis.cancelled": "Document review cancelled",
    "project_set_analysis.requested": "Project-wide review requested",
    "project_set_analysis.reconciled": "Project-wide review reconciled",
    "findings.materialized": "Review findings prepared",
    "intelligence_snapshot.approved": "Project information approved",
    "scope_generation.created": "Trade scopes generated",
    "scope_package.ready": "Trade scope marked Ready",
    "contractor_discovery.completed": "Contractor search completed",
    "contractor_candidate.shortlisted": "Contractor added to shortlist",
    "contractor_candidate.approved_for_outreach": "Contractor approved for outreach",
    "outreach_campaign.created": "Outreach campaign prepared",
    "outreach_batch.created": "Invitation batch prepared",
    "outreach_batch.send_approved": "Invitation batch approved for sending",
    "outreach_delivery.succeeded": "Outreach invitation sent",
    "outreach_delivery.failed": "Outreach delivery failed",
    "outreach_qualification.decided": "Contractor qualification recorded",
    "quote_submission.created": "Bid submitted",
    "manual_quote_uploaded": "Bid uploaded",
    "bid_revision.ready": "Structured bid marked Ready",
    "bid_comparison.created": "Bid comparison created",
    "bid_comparison.ready": "Bid comparison finalized",
    "bid_human_review.finalized": "Human procurement review finalized",
    "proposal.finalized": "Proposal finalized",
    "proposal.pdf_generated": "Proposal PDF generated",
    "project_award.confirmed": "Project award confirmed",
    "trade_award.confirmed": "Trade award confirmed",
    "awarded_handoff.created": "Handoff snapshot created",
}


def activity_family(action):
    prefix = action.split(".", 1)[0]
    return next(
        (family for family, prefixes in PREFIX_FAMILIES.items() if prefix in prefixes), "other"
    )


def activity_label(action):
    if action in ACTION_LABELS:
        return ACTION_LABELS[action]
    family = activity_family(action)
    subjects = {
        "projects": "Project",
        "documents": "Document",
        "reviews": "Project review",
        "scopes": "Trade scope",
        "contractors": "Contractor",
        "outreach": "Outreach",
        "bids": "Bid",
        "comparisons": "Comparison",
        "proposals": "Proposal",
        "awards": "Award",
        "organization": "Organization settings",
        "other": "Activity",
    }
    return "Activity recorded" if family == "other" else f"{subjects[family]} activity recorded"


def activity_route(event, family):
    if not event.project_id:
        return None
    suffix = {
        "projects": "",
        "documents": "/documents",
        "reviews": "/ai-review",
        "scopes": "/scopes",
        "contractors": "/contractors",
        "outreach": "/outreach",
        "bids": "/bids",
        "comparisons": "/comparisons",
        "proposals": "/proposal",
        "awards": "/proposal",
    }.get(family)
    return f"/projects/{event.project_id}{suffix}" if suffix is not None else None


def family_query(family):
    prefixes = PREFIX_FAMILIES.get(family)
    if prefixes is None:
        query = Q()
        for values in PREFIX_FAMILIES.values():
            for prefix in values:
                query |= Q(action_code__startswith=f"{prefix}.")
        return ~query
    query = Q()
    for prefix in prefixes:
        query |= Q(action_code__startswith=f"{prefix}.")
    return query


class ActivityPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 50


class ActivityDirectoryView(APIView):
    permission_classes = (ActiveOrganizationMember,)
    http_method_names = ("get", "head", "options")
    organization = None

    def get_organization(self):
        if self.organization is None:
            self.organization = get_object_or_404(
                Organization, slug=self.kwargs["organization_slug"]
            )
        return self.organization

    def get(self, request, *args, **kwargs):
        organization = self.get_organization()
        queryset = AuditEvent.objects.filter(organization=organization).select_related(
            "actor", "project"
        )
        project_id = request.query_params.get("project", "").strip()
        if project_id:
            if not project_id.isdigit():
                raise ValidationError({"project": "Choose a valid project."})
            queryset = queryset.filter(project_id=project_id)
        family = request.query_params.get("family", "").strip()
        if family:
            if family not in FAMILY_LABELS:
                raise ValidationError({"family": "Choose a valid activity type."})
            queryset = queryset.filter(family_query(family))
        paginator = ActivityPagination()
        page = paginator.paginate_queryset(
            queryset.order_by("-occurred_at", "-id"), request, view=self
        )
        results = []
        for event in page:
            event_family = activity_family(event.action_code)
            results.append(
                {
                    "id": event.pk,
                    "timestamp": event.occurred_at,
                    "actor": (event.actor.get_full_name() or event.actor.email)
                    if event.actor
                    else "System",
                    "project": (
                        {
                            "id": event.project_id,
                            "project_number": event.project.project_number,
                            "name": event.project.name,
                        }
                        if event.project_id
                        else None
                    ),
                    "family": event_family,
                    "family_label": FAMILY_LABELS[event_family],
                    "label": activity_label(event.action_code),
                    "target_type": event.target_type,
                    "target_reference": event.target_id if event.project_id else None,
                    "route": activity_route(event, event_family),
                }
            )
        return Response(
            {
                "count": paginator.page.paginator.count,
                "next": paginator.get_next_link(),
                "previous": paginator.get_previous_link(),
                "page": paginator.page.number,
                "page_size": paginator.get_page_size(request),
                "results": results,
                "filters": {
                    "projects": list(
                        Project.objects.filter(
                            organization=organization, audit_events__isnull=False
                        )
                        .order_by("project_number", "id")
                        .values("id", "project_number", "name")
                        .distinct()
                    ),
                    "families": [{"value": value, "label": label} for value, label in FAMILIES],
                },
            }
        )
