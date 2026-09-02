from django.urls import path

from .views import (
    RequestSourceVerificationView,
    RetryProcessingJobView,
    RevisionProcessingJobListView,
)

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/documents/<int:document_pk>/revisions/<int:revision_pk>/processing-jobs/",
        RevisionProcessingJobListView.as_view(),
        name="revision-processing-job-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/documents/<int:document_pk>/revisions/<int:revision_pk>/process/",
        RequestSourceVerificationView.as_view(),
        name="revision-request-processing",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/processing-jobs/<int:job_pk>/retry/",
        RetryProcessingJobView.as_view(),
        name="processing-job-retry",
    ),
]
