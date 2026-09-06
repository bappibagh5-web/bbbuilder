from django.urls import path

from .views import CandidateListView, CandidateStatusView, DiscoverySearchView

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contractor-candidates/",
        CandidateListView.as_view(),
        name="contractor-candidate-list",
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
