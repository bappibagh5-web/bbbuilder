from django.urls import path

from .views import (
    BatchCreateView,
    BatchDeliveryView,
    CampaignCreateView,
    CampaignRFQPreviewView,
    MessageRetryView,
    OutreachWorkspaceView,
    RecipientCreateView,
)

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/outreach-batches/<int:batch_pk>/delivery/<str:action>/",
        BatchDeliveryView.as_view(),
        name="outreach-batch-delivery",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/outreach-messages/<int:message_pk>/retry/",
        MessageRetryView.as_view(),
        name="outreach-message-retry",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/outreach/",
        OutreachWorkspaceView.as_view(),
        name="outreach-workspace",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/outreach-campaigns/",
        CampaignCreateView.as_view(),
        name="outreach-campaign-create",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/outreach-campaigns/<int:campaign_pk>/batches/",
        BatchCreateView.as_view(),
        name="outreach-batch-create",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/outreach-batches/<int:batch_pk>/recipients/",
        RecipientCreateView.as_view(),
        name="outreach-recipient-create",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/outreach-campaigns/<int:campaign_pk>/rfq-preview/",
        CampaignRFQPreviewView.as_view(),
        name="outreach-campaign-rfq-preview",
    ),
]
