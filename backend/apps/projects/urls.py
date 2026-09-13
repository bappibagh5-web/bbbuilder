from django.urls import path

from .views import (
    DashboardActivityView,
    DashboardSummaryView,
    ProjectAuditEventViewSet,
    ProjectContactViewSet,
    ProjectViewSet,
)

project_collection = ProjectViewSet.as_view({"get": "list", "post": "create"})
project_detail = ProjectViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update"}
)
contact_collection = ProjectContactViewSet.as_view({"get": "list", "post": "create"})
contact_detail = ProjectContactViewSet.as_view(
    {"get": "retrieve", "put": "update", "patch": "partial_update"}
)
audit_event_collection = ProjectAuditEventViewSet.as_view({"get": "list"})

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/dashboard/",
        DashboardSummaryView.as_view(),
        name="dashboard-summary",
    ),
    path(
        "organizations/<slug:organization_slug>/dashboard/activity/",
        DashboardActivityView.as_view(),
        name="dashboard-activity",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/",
        project_collection,
        name="project-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:pk>/",
        project_detail,
        name="project-detail",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contacts/",
        contact_collection,
        name="project-contact-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/contacts/<int:pk>/",
        contact_detail,
        name="project-contact-detail",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/audit-events/",
        audit_event_collection,
        name="project-audit-event-list",
    ),
]
