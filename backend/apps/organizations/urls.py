from django.urls import path

from .views import MembershipDetailView, MembershipListView, OrganizationSettingsView

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/settings/",
        OrganizationSettingsView.as_view(),
        name="organization-settings",
    ),
    path(
        "organizations/<slug:organization_slug>/memberships/",
        MembershipListView.as_view(),
        name="organization-memberships",
    ),
    path(
        "organizations/<slug:organization_slug>/memberships/<int:membership_pk>/",
        MembershipDetailView.as_view(),
        name="organization-membership-detail",
    ),
]
