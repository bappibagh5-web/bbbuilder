from django.urls import path

from .views import (
    AnalysisRunDetailView,
    AnalysisRunTaskListView,
    RetryAnalysisRunView,
    RevisionAnalysisRunListView,
)

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/documents/<int:document_pk>/revisions/<int:revision_pk>/analysis-runs/",
        RevisionAnalysisRunListView.as_view(),
        name="revision-analysis-run-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/analysis-runs/<int:run_pk>/",
        AnalysisRunDetailView.as_view(),
        name="analysis-run-detail",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/analysis-runs/<int:run_pk>/tasks/",
        AnalysisRunTaskListView.as_view(),
        name="analysis-run-task-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/analysis-runs/<int:run_pk>/retry/",
        RetryAnalysisRunView.as_view(),
        name="analysis-run-retry",
    ),
]
