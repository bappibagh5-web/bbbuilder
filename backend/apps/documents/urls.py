from django.urls import path

from .views import DocumentRevisionViewSet, DocumentViewSet

document_collection = DocumentViewSet.as_view({"get": "list"})
document_detail = DocumentViewSet.as_view({"get": "retrieve"})
revision_collection = DocumentRevisionViewSet.as_view({"get": "list"})
revision_detail = DocumentRevisionViewSet.as_view({"get": "retrieve"})

urlpatterns = [
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/documents/",
        document_collection,
        name="document-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/documents/<int:pk>/",
        document_detail,
        name="document-detail",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/documents/<int:document_pk>/revisions/",
        revision_collection,
        name="document-revision-list",
    ),
    path(
        "organizations/<slug:organization_slug>/projects/<int:project_pk>/documents/<int:document_pk>/revisions/<int:pk>/",
        revision_detail,
        name="document-revision-detail",
    ),
]
