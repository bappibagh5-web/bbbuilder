from django.urls import path

from .views import (
    CandidateListView,
    CandidateStatusView,
    CompanyProfileView,
    ContactDetailView,
    ContactEnrichmentView,
    ContactListCreateView,
    DiscoverySearchView,
    TradeCoverageView,
)

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-candidates/",
        CandidateListView.as_view(),
        name="contractor-candidate-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-coverage/",
        TradeCoverageView.as_view(),
        name="contractor-trade-coverage",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-companies/<int:company_pk>/",
        CompanyProfileView.as_view(),
        name="contractor-company-profile",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-companies/<int:company_pk>/contact-enrichment/",
        ContactEnrichmentView.as_view(),
        name="contractor-contact-enrichment",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-companies/<int:company_pk>/contacts/",
        ContactListCreateView.as_view(),
        name="contractor-contact-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-companies/<int:company_pk>/contacts/<int:contact_pk>/",
        ContactDetailView.as_view(),
        name="contractor-contact-detail",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-discovery/search/",
        DiscoverySearchView.as_view(),
        name="contractor-discovery-search",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-candidates/<int:candidate_pk>/",
        CandidateStatusView.as_view(),
        name="contractor-candidate-status",
    ),
]
