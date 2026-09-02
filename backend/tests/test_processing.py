import hashlib
import io
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents.models import Document, DocumentRevision, FileAsset, ProjectFile
from apps.documents.storage import ObjectStorageError
from apps.documents.uploads import upload_document_revision, upload_new_document
from apps.organizations.models import Membership, Organization
from apps.processing.models import ProcessingJob
from apps.processing.services import (
    claim_processing_job,
    dispatch_processing_job,
    execute_processing_job,
    recover_stale_jobs,
    request_source_verification,
    retry_processing_job,
)
from apps.projects.models import AuditEvent, Project

pytestmark = pytest.mark.django_db

SOURCE = b"%PDF-1.4\nM1-07 durable source verification\n%%EOF\n"


class MemoryStorage:
    def __init__(self, content=SOURCE, unavailable=False):
        self.content = content
        self.unavailable = unavailable
        self.saved = {}

    def open(self, key):
        if self.unavailable:
            raise ObjectStorageError("private storage detail")
        return io.BytesIO(self.content) if self.content is not None else None

    def save(self, key, uploaded_file, expected_size):
        uploaded_file.seek(0)
        content = b"".join(uploaded_file.chunks())
        uploaded_file.seek(0)
        assert len(content) == expected_size
        self.saved[key] = content

    def delete(self, key):
        self.saved.pop(key, None)


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-PROCESS-001",
        name="Processing Test",
        project_timezone="America/Vancouver",
    )


@pytest.fixture
def revision(project, user):
    asset = FileAsset.objects.create(
        organization=project.organization,
        storage_backend=FileAsset.StorageBackend.S3,
        bucket="private-test",
        storage_key="organizations/1/projects/1/files/source.pdf",
        original_filename="source.pdf",
        declared_mime_type="application/pdf",
        detected_mime_type="application/pdf",
        byte_size=len(SOURCE),
        checksum_algorithm=FileAsset.ChecksumAlgorithm.SHA256,
        checksum=hashlib.sha256(SOURCE).hexdigest(),
        created_by=user,
    )
    project_file = ProjectFile.objects.create(
        project=project,
        file_asset=asset,
        display_name="source.pdf",
        created_by=user,
    )
    document = Document.objects.create(
        project=project,
        title="Source",
        category=Document.Category.DRAWINGS,
        created_by=user,
    )
    return DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="R1",
        source_filename="source.pdf",
        created_by=user,
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def list_url(revision, organization=None, project=None):
    return reverse(
        "revision-processing-job-list",
        kwargs={
            "organization_slug": (organization or revision.document.project.organization).slug,
            "project_pk": (project or revision.document.project).pk,
            "document_pk": revision.document_id,
            "revision_pk": revision.pk,
        },
    )


def process_url(revision, organization=None, project=None):
    return reverse(
        "revision-request-processing",
        kwargs={
            "organization_slug": (organization or revision.document.project.organization).slug,
            "project_pk": (project or revision.document.project).pk,
            "document_pk": revision.document_id,
            "revision_pk": revision.pk,
        },
    )


def retry_url(job, organization=None, project=None):
    return reverse(
        "processing-job-retry",
        kwargs={
            "organization_slug": (organization or job.organization).slug,
            "project_pk": (project or job.project).pk,
            "job_pk": job.pk,
        },
    )


def test_processing_job_defaults_target_and_controlled_values(revision, user):
    job = ProcessingJob.objects.create(document_revision=revision, requested_by=user)
    assert job.job_type == ProcessingJob.JobType.SOURCE_VERIFICATION
    assert job.status == ProcessingJob.Status.QUEUED
    assert job.attempt_count == 0
    assert job.max_attempts == 3
    assert job.project == revision.document.project
    assert job.organization == revision.document.project.organization

    job.status = "forged"
    with pytest.raises(ValidationError):
        job.full_clean()
    job.status = ProcessingJob.Status.QUEUED
    job.job_type = "arbitrary"
    with pytest.raises(ValidationError):
        job.full_clean()
    job.job_type = ProcessingJob.JobType.SOURCE_VERIFICATION
    job.result_metadata = []
    with pytest.raises(ValidationError):
        job.full_clean()


def test_target_and_request_identity_are_immutable(revision, user):
    job = ProcessingJob.objects.create(document_revision=revision, requested_by=user)
    job.requested_by_id = user.pk + 999
    with pytest.raises(ValidationError):
        job.save()


def test_duplicate_active_job_is_database_rejected(revision, user):
    ProcessingJob.objects.create(document_revision=revision, requested_by=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProcessingJob.objects.bulk_create(
            [ProcessingJob(document_revision=revision, requested_by=user)]
        )


def test_completed_or_failed_history_allows_new_job(revision, user):
    first = ProcessingJob.objects.create(document_revision=revision, requested_by=user)
    ProcessingJob.objects.filter(pk=first.pk).update(
        status=ProcessingJob.Status.FAILED,
        error_code=ProcessingJob.ErrorCode.SOURCE_MISSING,
        error_message="Missing.",
        finished_at=timezone.now(),
    )
    second = ProcessingJob.objects.create(document_revision=revision, requested_by=user)
    assert second.pk != first.pk


def test_request_creates_durable_job_and_audit(revision, user):
    job = request_source_verification(revision=revision, requested_by=user)
    assert job.status == ProcessingJob.Status.QUEUED
    event = AuditEvent.objects.get(action_code="processing.requested")
    assert event.actor == user
    assert event.project == revision.document.project
    assert event.target_id == str(job.pk)


@override_settings(PROCESSING_AUTO_DISPATCH=True)
def test_dispatch_occurs_only_after_commit(
    revision, user, monkeypatch, django_capture_on_commit_callbacks
):
    dispatched = []
    monkeypatch.setattr(
        "apps.processing.services.dispatch_processing_job_safely", dispatched.append
    )
    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        job = request_source_verification(revision=revision, requested_by=user)
        assert dispatched == []
    assert dispatched == [job.pk]


@override_settings(PROCESSING_AUTO_DISPATCH=True)
def test_rollback_does_not_dispatch_or_persist(revision, user, monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        "apps.processing.services.dispatch_processing_job_safely", dispatched.append
    )
    with pytest.raises(RuntimeError), transaction.atomic():
        request_source_verification(revision=revision, requested_by=user)
        raise RuntimeError("rollback")
    assert dispatched == []
    assert not ProcessingJob.objects.exists()


def test_broker_failure_leaves_job_durably_queued(revision, user, monkeypatch):
    job = request_source_verification(revision=revision, requested_by=user)
    monkeypatch.setattr(
        "apps.processing.tasks.process_processing_job.apply_async",
        Mock(side_effect=ConnectionError("redis unavailable")),
    )
    assert dispatch_processing_job(job.pk, force=True) is False
    job.refresh_from_db()
    assert job.status == ProcessingJob.Status.QUEUED
    assert job.last_dispatched_at is None


def test_dispatch_records_delivery_identity_and_command_is_idempotent(
    revision, user, monkeypatch, capsys
):
    job = request_source_verification(revision=revision, requested_by=user)
    publish = Mock(return_value=SimpleNamespace(id="safe-task-id"))
    monkeypatch.setattr("apps.processing.tasks.process_processing_job.apply_async", publish)
    assert dispatch_processing_job(job.pk) is True
    assert dispatch_processing_job(job.pk) is False
    job.refresh_from_db()
    assert job.celery_task_id == "safe-task-id"
    assert job.dispatch_attempt_count == 1
    call_command("dispatch_queued_processing_jobs")
    assert "dispatched 0" in capsys.readouterr().out.lower()


def test_source_verification_streams_and_succeeds(revision, user, monkeypatch):
    job = request_source_verification(revision=revision, requested_by=user)
    monkeypatch.setattr("apps.processing.services.get_object_storage", lambda: MemoryStorage())
    original_asset = FileAsset.objects.values().get(pk=revision.project_file.file_asset_id)
    original_revision = DocumentRevision.objects.values().get(pk=revision.pk)
    assert execute_processing_job(job.pk)["outcome"] == "succeeded"
    job.refresh_from_db()
    assert job.status == ProcessingJob.Status.SUCCEEDED
    assert job.attempt_count == 1
    assert job.result_metadata["verified_byte_size"] == len(SOURCE)
    assert job.result_metadata["verified_checksum_algorithm"] == "sha256"
    assert job.result_metadata["checksum_match"] is True
    assert FileAsset.objects.values().get(pk=revision.project_file.file_asset_id) == original_asset
    assert DocumentRevision.objects.values().get(pk=revision.pk) == original_revision


@pytest.mark.parametrize(
    ("content", "asset_size", "asset_checksum", "expected_code"),
    [
        (None, len(SOURCE), hashlib.sha256(SOURCE).hexdigest(), "source_missing"),
        (SOURCE + b"x", len(SOURCE), hashlib.sha256(SOURCE).hexdigest(), "size_mismatch"),
        (SOURCE, len(SOURCE), "0" * 64, "checksum_mismatch"),
    ],
)
def test_terminal_source_failures_are_safe(
    revision, user, monkeypatch, content, asset_size, asset_checksum, expected_code
):
    asset = revision.project_file.file_asset
    FileAsset.objects.filter(pk=asset.pk).update(
        byte_size=asset_size,
        checksum=asset_checksum,
    )
    job = request_source_verification(revision=revision, requested_by=user)
    monkeypatch.setattr(
        "apps.processing.services.get_object_storage", lambda: MemoryStorage(content)
    )
    assert execute_processing_job(job.pk)["outcome"] == "failed"
    job.refresh_from_db()
    assert job.status == ProcessingJob.Status.FAILED
    assert job.error_code == expected_code
    assert "storage_key" not in job.error_message


def test_storage_outage_retries_boundedly_then_fails_safely(revision, user, monkeypatch):
    job = request_source_verification(revision=revision, requested_by=user)
    monkeypatch.setattr(
        "apps.processing.services.get_object_storage",
        lambda: MemoryStorage(unavailable=True),
    )
    assert execute_processing_job(job.pk)["outcome"] == "retry"
    assert execute_processing_job(job.pk)["outcome"] == "retry"
    assert execute_processing_job(job.pk)["outcome"] == "failed"
    job.refresh_from_db()
    assert job.attempt_count == 3
    assert job.error_code == ProcessingJob.ErrorCode.STORAGE_UNAVAILABLE
    assert "private storage detail" not in job.error_message


def test_duplicate_delivery_and_non_stale_claim_are_noops(revision, user, monkeypatch):
    job = request_source_verification(revision=revision, requested_by=user)
    monkeypatch.setattr("apps.processing.services.get_object_storage", lambda: MemoryStorage())
    claimed = claim_processing_job(job.pk)
    assert claimed is not None
    assert claim_processing_job(job.pk) is None
    ProcessingJob.objects.filter(pk=job.pk).update(
        status=ProcessingJob.Status.SUCCEEDED,
        finished_at=timezone.now(),
        lease_expires_at=None,
    )
    assert execute_processing_job(job.pk)["outcome"] == "noop"


def test_stale_recovery_preserves_non_stale_running_job(revision, user):
    stale = request_source_verification(revision=revision, requested_by=user)
    ProcessingJob.objects.filter(pk=stale.pk).update(
        status=ProcessingJob.Status.RUNNING,
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    other_asset = revision.project_file.file_asset
    other_project_file = ProjectFile.objects.create(
        project=revision.document.project,
        file_asset=FileAsset.objects.create(
            organization=other_asset.organization,
            storage_backend=other_asset.storage_backend,
            bucket=other_asset.bucket,
            storage_key="organizations/1/projects/1/files/other.pdf",
            original_filename="other.pdf",
            declared_mime_type="application/pdf",
            detected_mime_type="application/pdf",
            byte_size=other_asset.byte_size,
            checksum_algorithm=other_asset.checksum_algorithm,
            checksum=other_asset.checksum,
            created_by=user,
        ),
        created_by=user,
    )
    other_revision = DocumentRevision.objects.create(
        document=revision.document,
        project_file=other_project_file,
        source_filename="other.pdf",
        created_by=user,
    )
    current = request_source_verification(revision=other_revision, requested_by=user)
    ProcessingJob.objects.filter(pk=current.pk).update(
        status=ProcessingJob.Status.RUNNING,
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )
    assert recover_stale_jobs(dispatch=False) == [stale.pk]
    stale.refresh_from_db()
    current.refresh_from_db()
    assert stale.status == ProcessingJob.Status.QUEUED
    assert stale.error_code == ProcessingJob.ErrorCode.WORKER_LOST
    assert current.status == ProcessingJob.Status.RUNNING
    assert recover_stale_jobs(dispatch=False) == []


def test_uploads_create_one_durable_job_per_new_revision(
    project, user, monkeypatch, django_capture_on_commit_callbacks
):
    storage = MemoryStorage()
    monkeypatch.setattr("apps.documents.uploads.get_object_storage", lambda: storage)
    from django.core.files.uploadedfile import SimpleUploadedFile

    with django_capture_on_commit_callbacks(execute=False):
        document, first = upload_new_document(
            project=project,
            user=user,
            uploaded_file=SimpleUploadedFile("first.pdf", SOURCE, "application/pdf"),
            title="Upload integration",
            category=Document.Category.DRAWINGS,
        )
        _, second = upload_document_revision(
            document=document,
            user=user,
            uploaded_file=SimpleUploadedFile("second.pdf", SOURCE, "application/pdf"),
        )
    assert ProcessingJob.objects.filter(document_revision=first).count() == 1
    assert ProcessingJob.objects.filter(document_revision=second).count() == 1
    assert DocumentRevision.objects.filter(document=document).count() == 2
    assert FileAsset.objects.count() == 2


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (Membership.Role.ADMIN, True),
        (Membership.Role.ESTIMATOR_OPERATOR, True),
        (Membership.Role.VIEWER, False),
    ],
)
def test_processing_api_permissions(revision, user, membership, role, allowed):
    membership.role = role
    membership.save(update_fields=("role",))
    client = client_for(user)
    assert client.get(list_url(revision)).status_code == 200
    response = client.post(process_url(revision), {}, format="json")
    assert response.status_code == (201 if allowed else 403)
    if allowed:
        assert response.data["document_revision"] == revision.pk
        assert "celery_task_id" not in response.data
        assert "storage_key" not in str(response.data)


def test_retry_permissions_and_state(revision, user, membership):
    job = request_source_verification(revision=revision, requested_by=user)
    ProcessingJob.objects.filter(pk=job.pk).update(
        status=ProcessingJob.Status.FAILED,
        error_code=ProcessingJob.ErrorCode.SOURCE_MISSING,
        error_message="The stored source file could not be found.",
        finished_at=timezone.now(),
    )
    client = client_for(user)
    response = client.post(retry_url(job), {}, format="json")
    assert response.status_code == 201
    assert response.data["document_revision"] == revision.pk
    assert AuditEvent.objects.filter(action_code="processing.retry_requested").exists()

    retry = ProcessingJob.objects.get(pk=response.data["id"])
    with pytest.raises(ValidationError):
        retry_processing_job(job=retry, requested_by=user)


def test_inactive_unauthenticated_and_cross_tenant_access_denied(revision, user, membership):
    assert APIClient().get(list_url(revision)).status_code in {401, 403}
    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert client_for(user).get(list_url(revision)).status_code == 403
    membership.is_active = True
    membership.save(update_fields=("is_active",))
    other = Organization.objects.create(name="Other", slug="other")
    assert client_for(user).get(list_url(revision, organization=other)).status_code == 403
    other_project = Project.objects.create(
        organization=revision.document.project.organization,
        created_by=user,
        project_number="BB-OTHER",
        name="Other",
        project_timezone="America/Vancouver",
    )
    assert client_for(user).get(list_url(revision, project=other_project)).status_code == 404


def test_api_does_not_offer_status_mutation_or_delete(revision, user, membership):
    client = client_for(user)
    job = request_source_verification(revision=revision, requested_by=user)
    assert (
        client.patch(list_url(revision), {"status": "succeeded"}, format="json").status_code == 405
    )
    assert client.delete(list_url(revision)).status_code == 405
    assert client.delete(retry_url(job)).status_code == 405
