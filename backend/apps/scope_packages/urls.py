from django.urls import path

from .views import (
    ScopePackageDetailView,
    ScopePackageGenerateView,
    ScopePackageListView,
    ScopePackageReadyView,
)

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/scope-packages/",
        ScopePackageListView.as_view(),
        name="scope-package-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/scope-packages/generate/",
        ScopePackageGenerateView.as_view(),
        name="scope-package-generate",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/scope-packages/<int:package_pk>/",
        ScopePackageDetailView.as_view(),
        name="scope-package-detail",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/scope-packages/<int:package_pk>/ready/",
        ScopePackageReadyView.as_view(),
        name="scope-package-ready",
    ),
]
