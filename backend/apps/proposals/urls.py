from django.urls import path

from .views import (
    EstimateAssemblyView,
    EstimateCommercialView,
    EstimateCreateView,
    EstimateVersionCreateView,
    ProposalCreateView,
    ProposalVersionCreateView,
    ProposalWorkspaceView,
)

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/proposal-workspace/",
        ProposalWorkspaceView.as_view(),
        name="proposal-workspace",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/estimates/",
        EstimateCreateView.as_view(),
        name="estimate-create",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/estimates/<int:estimate_pk>/versions/",
        EstimateVersionCreateView.as_view(),
        name="estimate-version-create",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/estimate-versions/<int:version_pk>/assemble/",
        EstimateAssemblyView.as_view(),
        name="estimate-version-assemble",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/estimate-versions/<int:version_pk>/<str:kind>/",
        EstimateCommercialView.as_view(),
        name="estimate-commercial-create",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/estimate-versions/<int:version_pk>/<str:kind>/<int:item_pk>/",
        EstimateCommercialView.as_view(),
        name="estimate-commercial-detail",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/proposals/",
        ProposalCreateView.as_view(),
        name="proposal-create",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/proposals/<int:proposal_pk>/versions/",
        ProposalVersionCreateView.as_view(),
        name="proposal-version-create",
    ),
]
