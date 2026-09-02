from datetime import date

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory
from django.urls import reverse
from rest_framework.test import APIClient

from apps.documents.admin import DocumentAdmin, DocumentRevisionAdmin, FileAssetAdmin
from apps.documents.models import Document, DocumentRevision, FileAsset, ProjectFile
from apps.documents.services import set_current_revision
from apps.organizations.models import Membership, Organization
from apps.projects.models import AuditEvent, Project

pytestmark = pytest.mark.django_db


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-DOC-001",
        name="Document Test Project",
        project_timezone="America/Vancouver",
    )


def create_file_asset(organization, user, suffix="a", **overrides):
    values = {
        "organization": organization,
        "storage_backend": FileAsset.StorageBackend.S3,
        "bucket": "bb-builders-local",
        "storage_key": f"projects/test/{suffix}.pdf",
        "original_filename": f"drawings-{suffix}.pdf",
        "declared_mime_type": "application/pdf",
        "detected_mime_type": "application/pdf",
        "byte_size": 1024,
        "checksum_algorithm": FileAsset.ChecksumAlgorithm.SHA256,
        "checksum": suffix[0] * 64,
        "created_by": user,
    }
    values.update(overrides)
    return FileAsset.objects.create(**values)


def create_revision(project, user, suffix="a", document=None, **overrides):
    asset = create_file_asset(project.organization, user, suffix)
    project_file = ProjectFile.objects.create(
        project=project,
        file_asset=asset,
        display_name=asset.original_filename,
        created_by=user,
    )
    document = document or Document.objects.create(
        project=project,
        title="Architectural Drawing Set",
        category=Document.Category.DRAWINGS,
        discipline=Document.Discipline.ARCHITECTURAL,
        created_by=user,
    )
    values = {
        "document": document,
        "project_file": project_file,
        "revision_label": suffix.upper(),
        "issued_date": date(2026, 8, 29),
        "source_filename": asset.original_filename,
        "created_by": user,
    }
    values.update(overrides)
    return DocumentRevision.objects.create(**values)


def documents_url(project, organization=None):
    return reverse(
        "document-list",
        kwargs={
            "organization_slug": (organization or project.organization).slug,
            "project_pk": project.pk,
        },
    )


def document_url(document, organization=None, project=None):
    return reverse(
        "document-detail",
        kwargs={
            "organization_slug": (organization or document.project.organization).slug,
            "project_pk": (project or document.project).pk,
            "pk": document.pk,
        },
    )


def revisions_url(document, organization=None, project=None):
    return reverse(
        "document-revision-list",
        kwargs={
            "organization_slug": (organization or document.project.organization).slug,
            "project_pk": (project or document.project).pk,
            "document_pk": document.pk,
        },
    )


def revision_url(revision, organization=None, project=None, document=None):
    return reverse(
        "document-revision-detail",
        kwargs={
            "organization_slug": (organization or revision.document.project.organization).slug,
            "project_pk": (project or revision.document.project).pk,
            "document_pk": (document or revision.document).pk,
            "pk": revision.pk,
        },
    )


def test_file_asset_records_backend_neutral_immutable_metadata(organization, user):
    asset = create_file_asset(organization, user)

    assert asset.storage_backend == FileAsset.StorageBackend.S3
    assert asset.bucket == "bb-builders-local"
    assert asset.byte_size == 1024
    assert asset.checksum == "a" * 64
    assert asset.created_at is not None


@pytest.mark.parametrize(
    ("algorithm", "checksum"),
    [
        (FileAsset.ChecksumAlgorithm.SHA256, "a" * 63),
        (FileAsset.ChecksumAlgorithm.SHA256, "z" * 64),
        (FileAsset.ChecksumAlgorithm.SHA512, "a" * 127),
    ],
)
def test_file_asset_rejects_invalid_checksums(organization, user, algorithm, checksum):
    with pytest.raises(ValidationError):
        create_file_asset(
            organization,
            user,
            checksum=checksum,
            checksum_algorithm=algorithm,
        )


def test_file_asset_rejects_empty_binary_and_duplicate_storage_key(organization, user):
    with pytest.raises(ValidationError):
        create_file_asset(organization, user, byte_size=0)

    create_file_asset(organization, user)
    with pytest.raises(ValidationError):
        create_file_asset(organization, user, suffix="b", storage_key="projects/test/a.pdf")


@pytest.mark.parametrize("field", ["bucket", "storage_key", "original_filename", "checksum"])
def test_file_asset_required_metadata(organization, user, field):
    with pytest.raises(ValidationError):
        create_file_asset(organization, user, **{field: ""})


@pytest.mark.parametrize("field", ["storage_key", "checksum", "byte_size", "organization_id"])
def test_file_asset_identity_is_immutable(organization, user, field):
    asset = create_file_asset(organization, user)
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    replacements = {
        "storage_key": "replacement/key.pdf",
        "checksum": "b" * 64,
        "byte_size": 2048,
        "organization_id": other.pk,
    }
    setattr(asset, field, replacements[field])
    with pytest.raises(ValidationError):
        asset.save()


def test_project_file_enforces_organization_ownership(organization, user, project):
    other = Organization.objects.create(name="Other Builder", slug="other-builder")
    asset = create_file_asset(other, user)
    binding = ProjectFile(project=project, file_asset=asset, created_by=user)

    with pytest.raises(ValidationError):
        binding.save()


def test_file_asset_can_bind_to_only_one_project_file(organization, user, project):
    asset = create_file_asset(organization, user)
    ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)

    with pytest.raises((ValidationError, IntegrityError)), transaction.atomic():
        ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)


@pytest.mark.parametrize(
    ("field", "value"),
    [("category", "invoice"), ("discipline", "plumbing_trade")],
)
def test_document_rejects_uncontrolled_classification(project, user, field, value):
    document = Document(
        project=project,
        title="Source Document",
        created_by=user,
        **{field: value},
    )
    with pytest.raises(ValidationError):
        document.save()


def test_document_defaults_allow_unclassified_intake(project, user):
    document = Document.objects.create(
        project=project,
        title="Unclassified source",
        created_by=user,
    )

    assert document.category == Document.Category.UNKNOWN
    assert document.discipline == ""
    assert document.current_revision is None
    assert document.is_active is True


def test_document_project_identity_is_immutable(organization, user, project):
    document = Document.objects.create(project=project, title="Scope", created_by=user)
    other = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-DOC-002",
        name="Other Project",
        project_timezone="America/Vancouver",
    )
    document.project = other
    with pytest.raises(ValidationError):
        document.save()


def test_archived_document_is_preserved(project, user):
    document = Document.objects.create(project=project, title="Scope", created_by=user)
    document.is_active = False
    document.save()
    document.refresh_from_db()

    assert document.is_active is False
    assert Document.objects.filter(pk=document.pk).exists()


def test_document_revision_enforces_same_project(organization, user, project):
    document = Document.objects.create(project=project, title="Drawings", created_by=user)
    other = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-DOC-002",
        name="Other Project",
        project_timezone="America/Vancouver",
    )
    asset = create_file_asset(organization, user)
    project_file = ProjectFile.objects.create(project=other, file_asset=asset, created_by=user)

    with pytest.raises(ValidationError):
        DocumentRevision.objects.create(
            document=document,
            project_file=project_file,
            source_filename=asset.original_filename,
            created_by=user,
        )


def test_revision_can_supersede_only_same_document(project, user):
    first = create_revision(project, user, "a")
    other = create_revision(project, user, "b")
    third = create_revision(project, user, "c", document=first.document, supersedes=first)
    assert third.supersedes == first

    with pytest.raises(ValidationError):
        create_revision(project, user, "d", document=first.document, supersedes=other)


@pytest.mark.parametrize("field", ["document_id", "project_file_id", "revision_label", "notes"])
def test_document_revision_is_immutable(project, user, field):
    revision = create_revision(project, user)
    other = create_revision(project, user, "b")
    replacements = {
        "document_id": other.document_id,
        "project_file_id": other.project_file_id,
        "revision_label": "Replacement",
        "notes": "Changed",
    }
    setattr(revision, field, replacements[field])
    with pytest.raises(ValidationError):
        revision.save()


def test_current_revision_is_nullable_and_not_selected_by_upload_order(project, user):
    first = create_revision(project, user, "a")
    create_revision(project, user, "b", document=first.document)
    first.document.refresh_from_db()

    assert first.document.current_revision is None


def test_current_revision_transition_is_explicit_validated_and_audited(project, user):
    first = create_revision(project, user, "a")
    second = create_revision(project, user, "b", document=first.document)

    changed = set_current_revision(document=first.document, revision=first, actor=user)
    assert changed.current_revision_id == first.pk
    changed = set_current_revision(document=changed, revision=second, actor=user)
    assert changed.current_revision_id == second.pk
    assert list(first.document.revisions.values_list("pk", flat=True)) == [second.pk, first.pk]
    event = AuditEvent.objects.filter(
        action_code="document.current_revision_changed", project=project
    ).latest("occurred_at")
    assert event.actor == user
    assert event.metadata == {
        "before_revision_id": first.pk,
        "after_revision_id": second.pk,
    }

    other = create_revision(project, user, "c")
    with pytest.raises(ValidationError):
        set_current_revision(document=first.document, revision=other, actor=user)


def test_document_model_rejects_foreign_current_revision(project, user):
    first = create_revision(project, user, "a")
    other = create_revision(project, user, "b")
    first.document.current_revision = other
    with pytest.raises(ValidationError):
        first.document.save()


def test_current_revision_cannot_bypass_transition_service(project, user):
    revision = create_revision(project, user)
    revision.document.current_revision = revision

    with pytest.raises(ValidationError):
        revision.document.save()


@pytest.mark.parametrize(
    "role",
    [Membership.Role.ADMIN, Membership.Role.ESTIMATOR_OPERATOR, Membership.Role.VIEWER],
)
def test_active_members_can_read_document_and_revision_metadata(user, membership, project, role):
    membership.role = role
    membership.save(update_fields=("role",))
    revision = create_revision(project, user)
    set_current_revision(document=revision.document, revision=revision, actor=user)
    client = authenticated_client(user)

    listing = client.get(documents_url(project))
    assert listing.status_code == 200
    assert listing.data["results"][0]["revision_count"] == 1
    assert listing.data["results"][0]["current_revision"]["id"] == revision.pk
    assert client.get(document_url(revision.document)).status_code == 200
    assert client.get(revisions_url(revision.document)).status_code == 200
    detail = client.get(revision_url(revision))
    assert detail.status_code == 200
    assert detail.data["project_file"]["file_asset"]["checksum"] == "a" * 64
    assert "bucket" not in detail.data["project_file"]["file_asset"]
    assert "storage_key" not in detail.data["project_file"]["file_asset"]


def test_revision_apis_remain_read_only_and_document_delete_is_unavailable(
    user, membership, project
):
    revision = create_revision(project, user)
    client = authenticated_client(user)

    assert client.post(documents_url(project), {"title": "No"}, format="json").status_code == 405
    assert client.delete(document_url(revision.document)).status_code == 405
    assert client.post(revisions_url(revision.document), {}, format="json").status_code == 405
    assert client.patch(revision_url(revision), {}, format="json").status_code == 405
    assert client.delete(revision_url(revision)).status_code == 405


def test_document_metadata_patch_is_narrow_and_cannot_forge_current_revision(
    user, membership, project
):
    revision = create_revision(project, user)
    response = authenticated_client(user).patch(
        document_url(revision.document),
        {
            "title": "Updated title",
            "description": "Reviewed metadata",
            "current_revision": revision.pk,
            "project": 999999,
        },
        format="json",
    )
    assert response.status_code == 200
    revision.document.refresh_from_db()
    assert revision.document.title == "Updated title"
    assert revision.document.description == "Reviewed metadata"
    assert revision.document.current_revision is None
    assert revision.document.project == project


def test_unauthenticated_and_inactive_members_are_denied(user, membership, project):
    assert APIClient().get(documents_url(project)).status_code in {401, 403}
    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert authenticated_client(user).get(documents_url(project)).status_code == 403


def test_document_api_is_scoped_to_organization_project_and_document(
    organization, user, membership, project
):
    revision = create_revision(project, user)
    other_org = Organization.objects.create(name="Other Builder", slug="other-builder")
    other_project = Project.objects.create(
        organization=other_org,
        created_by=user,
        project_number="OTHER-001",
        name="Other Project",
        project_timezone="America/Vancouver",
    )
    other_revision = create_revision(other_project, user, "b")
    client = authenticated_client(user)

    assert client.get(documents_url(other_project)).status_code == 403
    assert (
        client.get(document_url(other_revision.document, organization, project)).status_code == 404
    )
    assert (
        client.get(
            revision_url(other_revision, organization, project, revision.document)
        ).status_code
        == 404
    )
    ids = [item["id"] for item in client.get(documents_url(project)).data["results"]]
    assert revision.document_id in ids
    assert other_revision.document_id not in ids


def test_admin_protects_immutable_asset_and_revision_fields(organization, user, project):
    asset = create_file_asset(organization, user)
    revision = create_revision(project, user, "b")
    asset_admin = FileAssetAdmin(FileAsset, admin.site)
    revision_admin = DocumentRevisionAdmin(DocumentRevision, admin.site)

    assert set(asset_admin.get_readonly_fields(None, asset)) == {
        field.name for field in FileAsset._meta.fields
    }
    assert set(revision_admin.get_readonly_fields(None, revision)) == {
        field.name for field in DocumentRevision._meta.fields
    }
    assert asset_admin.has_delete_permission(None, asset) is False
    assert revision_admin.has_delete_permission(None, revision) is False


def test_admin_document_mutations_and_revision_creation_are_audited(organization, user, project):
    request = RequestFactory().post("/admin/")
    request.user = user
    document_admin = DocumentAdmin(Document, admin.site)
    document = Document(project=project, title="Admin Document", created_by=user)
    document_admin.save_model(request, document, form=None, change=False)
    assert AuditEvent.objects.filter(
        action_code="document.created", target_id=str(document.pk), actor=user
    ).exists()

    document.is_active = False
    document_admin.save_model(request, document, form=None, change=True)
    assert AuditEvent.objects.filter(
        action_code="document.archived", target_id=str(document.pk), actor=user
    ).exists()

    asset = create_file_asset(organization, user, "c")
    project_file = ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)
    revision = DocumentRevision(
        document=document,
        project_file=project_file,
        source_filename=asset.original_filename,
        created_by=user,
    )
    revision_admin = DocumentRevisionAdmin(DocumentRevision, admin.site)
    revision_admin.save_model(request, revision, form=None, change=False)
    assert AuditEvent.objects.filter(
        action_code="document_revision.created", target_id=str(revision.pk), actor=user
    ).exists()
