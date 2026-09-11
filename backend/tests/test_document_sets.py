import hashlib

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents.document_sets import project_document_set, set_document_included
from apps.documents.models import (
    Document,
    DocumentPage,
    DocumentRevision,
    FileAsset,
    ProjectDocumentSelection,
    ProjectFile,
)
from apps.organizations.models import Membership
from apps.processing.models import ProcessingJob
from apps.projects.models import AuditEvent, Project

pytestmark = pytest.mark.django_db


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-DOCSET-001",
        name="Document Set Test",
        project_timezone="America/Vancouver",
        status=Project.Status.DOCUMENTS_UPLOADED,
    )


def prepared_document(project, user, *, title, discipline, checksum=None):
    checksum = checksum or hashlib.sha256(title.encode()).hexdigest()
    asset = FileAsset.objects.create(
        organization=project.organization,
        storage_backend=FileAsset.StorageBackend.S3,
        bucket="private-test",
        storage_key=f"document-sets/{project.pk}/{title}.pdf",
        original_filename=f"{title}.pdf",
        declared_mime_type="application/pdf",
        detected_mime_type="application/pdf",
        byte_size=100,
        checksum_algorithm=FileAsset.ChecksumAlgorithm.SHA256,
        checksum=checksum,
        created_by=user,
    )
    project_file = ProjectFile.objects.create(
        project=project, file_asset=asset, display_name=asset.original_filename, created_by=user
    )
    document = Document.objects.create(
        project=project,
        title=title,
        category=Document.Category.DRAWINGS,
        discipline=discipline,
        created_by=user,
    )
    revision = DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="R1",
        source_filename=asset.original_filename,
        created_by=user,
    )
    Document.objects.filter(pk=document.pk).update(current_revision=revision)
    document.refresh_from_db()
    ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
        status=ProcessingJob.Status.SUCCEEDED,
        finished_at=timezone.now(),
        result_metadata={"page_count": 1},
    )
    DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        width_points=612,
        height_points=792,
        native_text="Prepared source text",
        native_text_char_count=20,
        has_native_text=True,
        parser_name="test",
        parser_version="1",
    )
    return document


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def url(project):
    return reverse(
        "project-document-set",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )


def test_prepared_documents_group_by_type_and_discipline_with_duplicate_warning(project, user):
    checksum = "a" * 64
    prepared_document(
        project,
        user,
        title="Mechanical A",
        discipline=Document.Discipline.MECHANICAL,
        checksum=checksum,
    )
    prepared_document(
        project,
        user,
        title="Mechanical duplicate",
        discipline=Document.Discipline.MECHANICAL,
        checksum=checksum,
    )
    state = project_document_set(project)
    assert len(state["groups"]) == 1
    assert state["groups"][0]["category_label"] == "Drawings"
    assert state["groups"][0]["discipline_label"] == "Mechanical"
    assert all(item["page_count"] == 1 for item in state["groups"][0]["documents"])
    assert all(
        item["warnings"][0]["code"] == "duplicate_source"
        for item in state["groups"][0]["documents"]
    )


@pytest.mark.parametrize("role", [Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR])
def test_operator_selection_binds_exact_revision_is_idempotent_and_audited(
    project, user, membership, role
):
    membership.role = role
    membership.save(update_fields=("role",))
    document = prepared_document(
        project, user, title="Mechanical", discipline=Document.Discipline.MECHANICAL
    )
    response = client_for(user).post(
        url(project), {"document_id": document.pk, "included": True}, format="json"
    )
    assert response.status_code == 200
    selection = ProjectDocumentSelection.objects.get(document=document)
    assert selection.selected_revision_id == document.current_revision_id
    assert response.data["source_manifest"] == [
        {
            "document_id": document.pk,
            "document_revision_id": document.current_revision_id,
            "page_count": 1,
            "pages": [
                {
                    "document_page_id": document.current_revision.pages.get().pk,
                    "page_number": 1,
                    "page_label": "",
                }
            ],
        }
    ]
    assert AuditEvent.objects.filter(action_code="project_document_set.updated").count() == 1
    assert (
        client_for(user)
        .post(url(project), {"document_id": document.pk, "included": True}, format="json")
        .status_code
        == 200
    )
    assert AuditEvent.objects.filter(action_code="project_document_set.updated").count() == 1

    excluded = client_for(user).post(
        url(project), {"document_id": document.pk, "included": False}, format="json"
    )
    assert excluded.status_code == 200
    assert excluded.data["included_document_count"] == 0
    assert Document.objects.filter(pk=document.pk, is_active=True).exists()
    assert document.revisions.count() == 1


def test_viewer_is_read_only_and_unprepared_document_cannot_be_included(project, user, membership):
    document = prepared_document(
        project, user, title="Electrical", discipline=Document.Discipline.ELECTRICAL
    )
    ProcessingJob.objects.filter(document_revision=document.current_revision).delete()
    membership.role = Membership.Role.VIEWER
    membership.save(update_fields=("role",))
    assert client_for(user).get(url(project)).status_code == 200
    assert (
        client_for(user)
        .post(url(project), {"document_id": document.pk, "included": True}, format="json")
        .status_code
        == 403
    )
    membership.role = Membership.Role.ESTIMATOR_OPERATOR
    membership.save(update_fields=("role",))
    response = client_for(user).post(
        url(project), {"document_id": document.pk, "included": True}, format="json"
    )
    assert response.status_code == 400
    assert not ProjectDocumentSelection.objects.exists()


def test_coordination_flags_missing_related_disciplines_without_creating_scope(project, user):
    document = prepared_document(
        project, user, title="Mechanical", discipline=Document.Discipline.MECHANICAL
    )
    set_document_included(project=project, document=document, included=True, actor=user)
    state = project_document_set(project)
    codes = {flag["code"] for flag in state["coordination"]["flags"]}
    assert "related_discipline_not_selected" in codes
    assert "responsibility_schedule_not_selected" in codes
    assert {flag.get("related_trade_label") for flag in state["coordination"]["flags"]} >= {
        "Electrical",
        "Plumbing",
        "Fire Protection / Sprinkler",
    }
