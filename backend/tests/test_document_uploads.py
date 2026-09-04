import hashlib
import io
import zipfile
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.documents.models import Document, DocumentRevision, FileAsset, ProjectFile
from apps.documents.storage import ObjectStorage, ObjectStorageError
from apps.documents.uploads import upload_new_document
from apps.organizations.models import Membership, Organization
from apps.projects.models import AuditEvent, Project

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4\n% safe M1-06 test fixture\n%%EOF\n"
PDF_BYTES_2 = b"%PDF-1.4\n% second safe M1-06 fixture\n%%EOF\n"


class FakeObjectStorage:
    def __init__(self, *, fail_save=False, fail_delete=False):
        self.objects = {}
        self.deleted = []
        self.fail_save = fail_save
        self.fail_delete = fail_delete

    def save(self, key, uploaded_file, expected_size):
        if self.fail_save:
            raise ObjectStorageError("save failed")
        uploaded_file.seek(0)
        content = b"".join(uploaded_file.chunks())
        uploaded_file.seek(0)
        assert len(content) == expected_size
        self.objects[key] = content

    def open(self, key):
        content = self.objects.get(key)
        return io.BytesIO(content) if content is not None else None

    def exists(self, key):
        return key in self.objects

    def delete(self, key):
        self.deleted.append(key)
        if self.fail_delete:
            raise ObjectStorageError("delete failed")
        self.objects.pop(key, None)


class FakeDjangoStorage:
    def __init__(self):
        self.objects = {}

    def save(self, key, content):
        content.seek(0)
        self.objects[key] = b"".join(content.chunks())
        content.seek(0)
        return key

    def exists(self, key):
        return key in self.objects

    def size(self, key):
        return len(self.objects[key])

    def open(self, key, mode):
        return io.BytesIO(self.objects[key])

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-UPLOAD-001",
        name="Upload Test Project",
        project_timezone="America/Vancouver",
    )


@pytest.fixture
def fake_storage(monkeypatch):
    storage = FakeObjectStorage()
    monkeypatch.setattr("apps.documents.uploads.get_object_storage", lambda: storage)
    monkeypatch.setattr("apps.documents.views.get_object_storage", lambda: storage)
    return storage


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def set_role(membership, role):
    membership.role = role
    membership.save(update_fields=("role",))


def pdf_upload(name="architectural-set.pdf", content=PDF_BYTES, content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def upload_url(project, organization=None):
    return reverse(
        "document-upload",
        kwargs={
            "organization_slug": (organization or project.organization).slug,
            "project_pk": project.pk,
        },
    )


def revision_upload_url(document, organization=None, project=None):
    return reverse(
        "document-revision-upload",
        kwargs={
            "organization_slug": (organization or document.project.organization).slug,
            "project_pk": (project or document.project).pk,
            "document_pk": document.pk,
        },
    )


def set_current_url(revision, organization=None, project=None, document=None):
    return reverse(
        "document-revision-set-current",
        kwargs={
            "organization_slug": (organization or revision.document.project.organization).slug,
            "project_pk": (project or revision.document.project).pk,
            "document_pk": (document or revision.document).pk,
            "revision_pk": revision.pk,
        },
    )


def download_url(revision, organization=None, project=None, document=None):
    return reverse(
        "document-revision-download",
        kwargs={
            "organization_slug": (organization or revision.document.project.organization).slug,
            "project_pk": (project or revision.document.project).pk,
            "document_pk": (document or revision.document).pk,
            "revision_pk": revision.pk,
        },
    )


def new_document_payload(file=None, **overrides):
    values = {
        "file": file or pdf_upload(),
        "title": "Architectural Drawing Set",
        "category": Document.Category.DRAWINGS,
        "discipline": Document.Discipline.ARCHITECTURAL,
        "revision_label": "R1",
        "revision_notes": "Initial tender issue",
    }
    values.update(overrides)
    return values


def create_document_via_api(client, project, fake_storage, **overrides):
    response = client.post(
        upload_url(project), new_document_payload(**overrides), format="multipart"
    )
    assert response.status_code == 201, response.data
    return Document.objects.get(pk=response.data["id"])


def test_object_storage_adapter_save_open_exists_and_delete():
    backend = FakeDjangoStorage()
    adapter = ObjectStorage(backend)
    uploaded = pdf_upload()
    adapter.save("safe/key.pdf", uploaded, len(PDF_BYTES))
    assert adapter.exists("safe/key.pdf") is True
    assert adapter.open("safe/key.pdf").read() == PDF_BYTES
    adapter.delete("safe/key.pdf")
    assert adapter.exists("safe/key.pdf") is False


def test_unauthenticated_upload_is_denied(project):
    assert APIClient().post(upload_url(project), new_document_payload()).status_code in {401, 403}


@pytest.mark.parametrize("role", [Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR])
def test_admin_and_estimator_can_upload_new_document(
    organization, user, membership, project, fake_storage, role
):
    set_role(membership, role)
    response = authenticated_client(user).post(
        upload_url(project), new_document_payload(), format="multipart"
    )
    assert response.status_code == 201, response.data

    asset = FileAsset.objects.get()
    project_file = ProjectFile.objects.get()
    document = Document.objects.get()
    revision = DocumentRevision.objects.get()
    assert asset.organization == organization
    assert asset.original_filename == "architectural-set.pdf"
    assert asset.byte_size == len(PDF_BYTES)
    assert asset.checksum == hashlib.sha256(PDF_BYTES).hexdigest()
    assert asset.detected_mime_type == "application/pdf"
    assert asset.storage_key != asset.original_filename
    assert asset.storage_key.startswith(
        f"organizations/{organization.pk}/projects/{project.pk}/files/"
    )
    assert fake_storage.objects[asset.storage_key] == PDF_BYTES
    assert project_file.project == project
    assert project_file.file_asset == asset
    assert revision.document == document
    assert revision.project_file == project_file
    assert revision.revision_label == "R1"
    assert document.current_revision == revision
    assert response.data["current_revision"]["id"] == revision.pk
    assert response.data["revision_count"] == 1


def test_first_upload_audits_records_and_advances_draft_project(
    user, membership, project, fake_storage
):
    create_document_via_api(authenticated_client(user), project, fake_storage)
    project.refresh_from_db()
    assert project.status == Project.Status.DOCUMENTS_UPLOADED
    assert AuditEvent.objects.filter(action_code="file.uploaded", project=project).exists()
    assert AuditEvent.objects.filter(action_code="document.created", project=project).exists()
    assert AuditEvent.objects.filter(
        action_code="document_revision.created", project=project
    ).exists()
    assert AuditEvent.objects.filter(
        action_code="document.current_revision_changed", project=project
    ).exists()
    assert AuditEvent.objects.filter(action_code="project.status_changed", project=project).exists()


def test_upload_does_not_regress_advanced_project_status(user, membership, project, fake_storage):
    project.status = Project.Status.AI_ANALYSIS
    project.save(update_fields=("status",))
    create_document_via_api(authenticated_client(user), project, fake_storage)
    project.refresh_from_db()
    assert project.status == Project.Status.AI_ANALYSIS
    assert not AuditEvent.objects.filter(
        action_code="project.status_changed", project=project
    ).exists()


def test_repeated_filename_creates_unique_objects_and_equal_checksums(
    user, membership, project, fake_storage
):
    client = authenticated_client(user)
    create_document_via_api(client, project, fake_storage)
    create_document_via_api(client, project, fake_storage, title="Second logical document")
    assets = list(FileAsset.objects.order_by("id"))
    assert assets[0].original_filename == assets[1].original_filename
    assert assets[0].checksum == assets[1].checksum
    assert assets[0].storage_key != assets[1].storage_key
    assert len(fake_storage.objects) == 2


def test_viewer_and_inactive_members_cannot_upload(user, membership, project, fake_storage):
    client = authenticated_client(user)
    set_role(membership, Membership.Role.VIEWER)
    assert (
        client.post(upload_url(project), new_document_payload(), format="multipart").status_code
        == 403
    )
    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert (
        client.post(upload_url(project), new_document_payload(), format="multipart").status_code
        == 403
    )


def test_cross_organization_upload_is_denied(user, membership, project, fake_storage):
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    other_project = Project.objects.create(
        organization=other,
        created_by=user,
        project_number="OTHER-001",
        name="Other Project",
        project_timezone="America/Vancouver",
    )
    assert (
        authenticated_client(user)
        .post(upload_url(other_project), new_document_payload(), format="multipart")
        .status_code
        == 403
    )


def test_revision_upload_preserves_history_and_current_by_default(
    user, membership, project, fake_storage
):
    client = authenticated_client(user)
    document = create_document_via_api(client, project, fake_storage)
    first = document.current_revision
    response = client.post(
        revision_upload_url(document),
        {
            "file": pdf_upload("architectural-set-r2.pdf", PDF_BYTES_2),
            "revision_label": "R2",
            "supersedes": first.pk,
            "make_current": "false",
        },
        format="multipart",
    )
    assert response.status_code == 201, response.data
    second = DocumentRevision.objects.get(pk=response.data["id"])
    document.refresh_from_db()
    first.refresh_from_db()
    assert second.supersedes == first
    assert document.current_revision == first
    assert document.revisions.count() == 2
    assert FileAsset.objects.count() == 2
    assert first.project_file.file_asset.storage_key in fake_storage.objects


def test_revision_upload_can_explicitly_make_current(user, membership, project, fake_storage):
    client = authenticated_client(user)
    document = create_document_via_api(client, project, fake_storage)
    response = client.post(
        revision_upload_url(document),
        {
            "file": pdf_upload("architectural-set-r2.pdf", PDF_BYTES_2),
            "revision_label": "R2",
            "make_current": "true",
        },
        format="multipart",
    )
    assert response.status_code == 201
    document.refresh_from_db()
    assert document.current_revision_id == response.data["id"]
    assert AuditEvent.objects.filter(
        action_code="document.current_revision_changed",
        metadata__after_revision_id=response.data["id"],
    ).exists()


def test_set_current_endpoint_is_explicit_and_role_protected(
    user, membership, project, fake_storage
):
    client = authenticated_client(user)
    document = create_document_via_api(client, project, fake_storage)
    first = document.current_revision
    uploaded = client.post(
        revision_upload_url(document),
        {"file": pdf_upload("r2.pdf", PDF_BYTES_2), "revision_label": "R2"},
        format="multipart",
    )
    second = DocumentRevision.objects.get(pk=uploaded.data["id"])
    response = client.post(set_current_url(second), {}, format="json")
    assert response.status_code == 200
    document.refresh_from_db()
    assert document.current_revision == second
    assert DocumentRevision.objects.filter(pk=first.pk).exists()

    set_role(membership, Membership.Role.VIEWER)
    assert client.post(set_current_url(first), {}, format="json").status_code == 403


def test_cross_document_set_current_and_cross_project_revision_upload_are_hidden(
    organization, user, membership, project, fake_storage
):
    client = authenticated_client(user)
    first_document = create_document_via_api(client, project, fake_storage)
    second_document = create_document_via_api(client, project, fake_storage, title="Specifications")
    foreign_revision = second_document.current_revision
    assert (
        client.post(
            set_current_url(foreign_revision, document=first_document), {}, format="json"
        ).status_code
        == 404
    )

    other_project = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-UPLOAD-002",
        name="Other Project",
        project_timezone="America/Vancouver",
    )
    assert (
        client.post(
            revision_upload_url(first_document, project=other_project),
            {"file": pdf_upload("other.pdf")},
            format="multipart",
        ).status_code
        == 404
    )


@pytest.mark.parametrize("archive_target", ["project", "document"])
def test_archived_project_or_document_rejects_revision_upload(
    user, membership, project, fake_storage, archive_target
):
    client = authenticated_client(user)
    document = create_document_via_api(client, project, fake_storage)
    target = project if archive_target == "project" else document
    target.is_active = False
    target.save(update_fields=("is_active",))
    response = client.post(
        revision_upload_url(document),
        {"file": pdf_upload("r2.pdf", PDF_BYTES_2)},
        format="multipart",
    )
    assert response.status_code == 400
    assert DocumentRevision.objects.filter(document=document).count() == 1


def test_archived_project_rejects_new_document_upload(user, membership, project, fake_storage):
    project.is_active = False
    project.save(update_fields=("is_active",))
    response = authenticated_client(user).post(
        upload_url(project), new_document_payload(), format="multipart"
    )
    assert response.status_code == 400
    assert not Document.objects.exists()


@pytest.mark.parametrize(
    ("uploaded_file", "expected_message"),
    [
        (SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf"), "empty"),
        (
            SimpleUploadedFile("script.exe", b"MZ", content_type="application/octet-stream"),
            "supported",
        ),
        (SimpleUploadedFile("fake.pdf", b"not a pdf", content_type="application/pdf"), "signature"),
        (SimpleUploadedFile("image.png", PDF_BYTES, content_type="image/png"), "contents"),
    ],
)
def test_upload_validation_rejects_unsafe_files(
    user, membership, project, fake_storage, uploaded_file, expected_message
):
    response = authenticated_client(user).post(
        upload_url(project),
        new_document_payload(file=uploaded_file),
        format="multipart",
    )
    assert response.status_code == 400
    assert expected_message in str(response.data).lower()
    assert not FileAsset.objects.exists()
    assert not fake_storage.objects


@override_settings(DOCUMENT_UPLOAD_MAX_BYTES=10)
def test_oversized_upload_is_rejected(user, membership, project, fake_storage):
    response = authenticated_client(user).post(
        upload_url(project), new_document_payload(), format="multipart"
    )
    assert response.status_code == 400
    assert "maximum" in str(response.data).lower()


def test_valid_ooxml_document_is_accepted(user, membership, project, fake_storage):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
    upload = SimpleUploadedFile(
        "scope.docx",
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response = authenticated_client(user).post(
        upload_url(project), new_document_payload(file=upload), format="multipart"
    )
    assert response.status_code == 201, response.data
    assert FileAsset.objects.get().detected_mime_type.endswith("wordprocessingml.document")


def test_user_filename_cannot_control_storage_key(user, membership, project, fake_storage):
    response = authenticated_client(user).post(
        upload_url(project),
        new_document_payload(file=pdf_upload("../../unsafe-name.pdf")),
        format="multipart",
    )
    assert response.status_code == 201
    asset = FileAsset.objects.get()
    assert ".." not in asset.storage_key
    assert "unsafe-name" not in asset.storage_key


def test_storage_failure_creates_no_business_records(user, membership, project, monkeypatch):
    storage = FakeObjectStorage(fail_save=True)
    monkeypatch.setattr("apps.documents.uploads.get_object_storage", lambda: storage)
    response = authenticated_client(user).post(
        upload_url(project), new_document_payload(), format="multipart"
    )
    assert response.status_code == 503
    assert not FileAsset.objects.exists()
    assert not ProjectFile.objects.exists()
    assert not Document.objects.exists()
    assert not DocumentRevision.objects.exists()


def test_database_failure_after_storage_write_compensates(user, project, monkeypatch):
    storage = FakeObjectStorage()
    monkeypatch.setattr("apps.documents.uploads.get_object_storage", lambda: storage)
    with (
        patch(
            "apps.documents.uploads.FileAsset.objects.create",
            side_effect=IntegrityError("db failed"),
        ),
        pytest.raises(IntegrityError),
    ):
        upload_new_document(
            project=project,
            user=user,
            uploaded_file=pdf_upload(),
            title="Drawings",
            category=Document.Category.DRAWINGS,
        )
    assert len(storage.deleted) == 1
    assert not storage.objects
    assert not FileAsset.objects.exists()


def test_cleanup_failure_is_logged_and_original_error_survives(user, project, monkeypatch, caplog):
    storage = FakeObjectStorage(fail_delete=True)
    monkeypatch.setattr("apps.documents.uploads.get_object_storage", lambda: storage)
    with (
        patch(
            "apps.documents.uploads.FileAsset.objects.create",
            side_effect=IntegrityError("db failed"),
        ),
        pytest.raises(IntegrityError, match="db failed"),
    ):
        upload_new_document(
            project=project,
            user=user,
            uploaded_file=pdf_upload(),
            title="Drawings",
            category=Document.Category.DRAWINGS,
        )
    assert "Failed to remove orphaned upload object" in caplog.text


@pytest.mark.parametrize(
    "role",
    [Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR, Membership.Role.VIEWER],
)
def test_authorized_members_receive_streaming_download(
    user, membership, project, fake_storage, role
):
    client = authenticated_client(user)
    document = create_document_via_api(client, project, fake_storage)
    revision = document.current_revision
    set_role(membership, role)
    response = client.get(download_url(revision))
    assert response.status_code == 200
    assert response.streaming is True
    assert b"".join(response.streaming_content) == PDF_BYTES
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    assert "architectural-set.pdf" in response["Content-Disposition"]
    assert "storage_key" not in response.headers
    assert "bucket" not in response.headers


def test_download_authentication_and_scope_isolation(
    organization, user, membership, project, fake_storage
):
    client = authenticated_client(user)
    document = create_document_via_api(client, project, fake_storage)
    revision = document.current_revision
    assert APIClient().get(download_url(revision)).status_code in {401, 403}

    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    assert client.get(download_url(revision, organization=other)).status_code == 403

    other_project = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-UPLOAD-002",
        name="Other Project",
        project_timezone="America/Vancouver",
    )
    assert client.get(download_url(revision, project=other_project)).status_code == 404


def test_missing_historical_object_returns_controlled_404(user, membership, project, fake_storage):
    document = create_document_via_api(authenticated_client(user), project, fake_storage)
    revision = document.current_revision
    fake_storage.objects.clear()
    response = authenticated_client(user).get(download_url(revision))
    assert response.status_code == 404
    assert "historical revision" in response.data["detail"].lower()
    assert "storage_key" not in str(response.data)


def test_download_storage_outage_returns_controlled_503(
    user, membership, project, fake_storage, monkeypatch
):
    document = create_document_via_api(authenticated_client(user), project, fake_storage)
    revision = document.current_revision

    class UnavailableStorage:
        def open(self, key):
            raise ObjectStorageError("storage unavailable")

    monkeypatch.setattr("apps.documents.views.get_object_storage", lambda: UnavailableStorage())
    response = authenticated_client(user).get(download_url(revision))
    assert response.status_code == 503
    assert response.data["detail"] == "Object storage is currently unavailable. Try again shortly."
    assert "storage unavailable" not in str(response.data).lower()


def test_document_metadata_permissions_archive_and_audit(user, membership, project, fake_storage):
    client = authenticated_client(user)
    document = create_document_via_api(client, project, fake_storage)
    detail_url = reverse(
        "document-detail",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "pk": document.pk,
        },
    )
    response = client.patch(
        detail_url,
        {
            "title": "Updated Drawings",
            "current_revision": 999999,
            "project": 999999,
        },
        format="json",
    )
    assert response.status_code == 200
    document.refresh_from_db()
    assert document.title == "Updated Drawings"
    assert document.is_active is True
    assert document.project == project
    assert document.current_revision is not None
    assert AuditEvent.objects.filter(action_code="document.updated").exists()
    assert client.delete(detail_url).status_code == 405

    set_role(membership, Membership.Role.VIEWER)
    assert client.patch(detail_url, {"title": "No"}, format="json").status_code == 403


@pytest.mark.parametrize("role", [Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR])
def test_scoped_document_archive_and_restore_are_idempotent_and_preserve_history(
    user, membership, project, fake_storage, role
):
    set_role(membership, role)
    client = authenticated_client(user)
    document = create_document_via_api(client, project, fake_storage)
    revision_id = document.current_revision_id
    object_keys = set(fake_storage.objects)
    archive_url = reverse(
        "document-archive",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "document_pk": document.pk,
        },
    )
    restore_url = reverse(
        "document-reactivate",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "document_pk": document.pk,
        },
    )

    assert client.post(archive_url, {}, format="json").status_code == 200
    assert client.post(archive_url, {}, format="json").status_code == 200
    document.refresh_from_db()
    assert document.is_active is False
    assert document.current_revision_id == revision_id
    assert document.revisions.filter(pk=revision_id).exists()
    assert set(fake_storage.objects) == object_keys
    assert (
        AuditEvent.objects.filter(
            action_code="document.archived", target_id=str(document.pk)
        ).count()
        == 1
    )

    assert client.post(restore_url, {}, format="json").status_code == 200
    assert client.post(restore_url, {}, format="json").status_code == 200
    document.refresh_from_db()
    assert document.is_active is True
    assert document.current_revision_id == revision_id
    assert set(fake_storage.objects) == object_keys
    assert (
        AuditEvent.objects.filter(
            action_code="document.reactivated", target_id=str(document.pk)
        ).count()
        == 1
    )


def test_document_archive_permissions_and_scope(user, membership, project, fake_storage):
    document = create_document_via_api(authenticated_client(user), project, fake_storage)
    url = reverse(
        "document-archive",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "document_pk": document.pk,
        },
    )
    set_role(membership, Membership.Role.VIEWER)
    assert authenticated_client(user).post(url, {}, format="json").status_code == 403
    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert authenticated_client(user).post(url, {}, format="json").status_code == 403

    membership.is_active = True
    membership.role = Membership.Role.ESTIMATOR_OPERATOR
    membership.save(update_fields=("is_active", "role"))

    other_project = Project.objects.create(
        organization=project.organization,
        created_by=user,
        project_number="BB-ARCHIVE-SCOPE",
        name="Archive Scope",
        project_timezone="America/Vancouver",
    )
    wrong_url = reverse(
        "document-archive",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": other_project.pk,
            "document_pk": document.pk,
        },
    )
    assert authenticated_client(user).post(wrong_url, {}, format="json").status_code == 404

    other_organization = Organization.objects.create(name="Other Builder", slug="other-builder")
    cross_org_url = reverse(
        "document-archive",
        kwargs={
            "organization_slug": other_organization.slug,
            "project_pk": project.pk,
            "document_pk": document.pk,
        },
    )
    assert authenticated_client(user).post(cross_org_url, {}, format="json").status_code == 403


def test_document_archive_is_available_for_cleanup_inside_archived_project(
    user, membership, project, fake_storage
):
    document = create_document_via_api(authenticated_client(user), project, fake_storage)
    project.is_active = False
    project.save(update_fields=("is_active", "updated_at"))
    url = reverse(
        "document-archive",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "document_pk": document.pk,
        },
    )
    assert authenticated_client(user).post(url, {}, format="json").status_code == 200
    document.refresh_from_db()
    assert document.is_active is False
