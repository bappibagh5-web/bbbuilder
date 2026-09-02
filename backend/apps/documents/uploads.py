import logging
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.processing.services import request_source_verification
from apps.projects.audit import PROJECT_AUDIT_FIELDS, record_event, snapshot
from apps.projects.models import Project

from .file_validation import validate_uploaded_file
from .models import Document, DocumentRevision, FileAsset, ProjectFile
from .services import set_current_revision
from .storage import get_object_storage

logger = logging.getLogger(__name__)


def generate_storage_key(*, organization_id, project_id, extension):
    return (
        f"organizations/{organization_id}/projects/{project_id}/files/{uuid.uuid4().hex}{extension}"
    )


def _ensure_upload_target(project, document=None):
    if not project.is_active:
        raise ValidationError("Archived projects cannot accept document uploads.")
    if document is not None and not document.is_active:
        raise ValidationError("Archived documents cannot accept new revisions.")


def _store_uploaded_file(*, project, uploaded_file):
    validated = validate_uploaded_file(uploaded_file)
    storage_key = generate_storage_key(
        organization_id=project.organization_id,
        project_id=project.pk,
        extension=validated.extension,
    )
    storage = get_object_storage()
    storage.save(storage_key, uploaded_file, validated.byte_size)
    return storage, storage_key, validated


def _create_file_records(*, project, user, storage_key, validated):
    file_asset = FileAsset.objects.create(
        organization=project.organization,
        storage_backend=FileAsset.StorageBackend.S3,
        bucket=settings.S3_BUCKET,
        storage_key=storage_key,
        original_filename=validated.original_filename,
        declared_mime_type=validated.declared_mime_type,
        detected_mime_type=validated.detected_mime_type,
        byte_size=validated.byte_size,
        checksum_algorithm=FileAsset.ChecksumAlgorithm.SHA256,
        checksum=validated.checksum,
        created_by=user,
    )
    project_file = ProjectFile.objects.create(
        project=project,
        file_asset=file_asset,
        display_name=validated.original_filename,
        created_by=user,
    )
    record_event(
        organization=project.organization,
        project=project,
        actor=user,
        action_code="file.uploaded",
        target=file_asset,
        metadata={
            "project_file_id": project_file.pk,
            "original_filename": validated.original_filename,
            "byte_size": validated.byte_size,
            "checksum_algorithm": FileAsset.ChecksumAlgorithm.SHA256,
            "checksum": validated.checksum,
        },
    )
    return file_asset, project_file


def _record_document_created(document, user):
    record_event(
        organization=document.project.organization,
        project=document.project,
        actor=user,
        action_code="document.created",
        target=document,
        metadata={
            "after": {
                "title": document.title,
                "category": document.category,
                "discipline": document.discipline,
                "description": document.description,
                "is_active": document.is_active,
            }
        },
    )


def _record_revision_created(revision, user):
    record_event(
        organization=revision.document.project.organization,
        project=revision.document.project,
        actor=user,
        action_code="document_revision.created",
        target=revision,
        metadata={
            "document_id": revision.document_id,
            "project_file_id": revision.project_file_id,
            "revision_label": revision.revision_label,
            "supersedes_id": revision.supersedes_id,
        },
    )


def _advance_project_after_first_upload(project, user):
    if project.status != Project.Status.DRAFT:
        return
    before = snapshot(project, PROJECT_AUDIT_FIELDS)
    updated = Project.objects.filter(pk=project.pk, status=Project.Status.DRAFT).update(
        status=Project.Status.DOCUMENTS_UPLOADED
    )
    if not updated:
        project.refresh_from_db(fields=("status",))
        return
    project.status = Project.Status.DOCUMENTS_UPLOADED
    after = snapshot(project, PROJECT_AUDIT_FIELDS)
    record_event(
        organization=project.organization,
        project=project,
        actor=user,
        action_code="project.status_changed",
        target=project,
        metadata={
            "changed_fields": ["status"],
            "before": before,
            "after": after,
            "reason": "first_document_uploaded",
        },
    )


def _compensate(storage, storage_key):
    try:
        storage.delete(storage_key)
    except Exception:
        logger.exception("Failed to remove orphaned upload object after database failure.")


def upload_new_document(
    *,
    project,
    user,
    uploaded_file,
    title,
    category,
    discipline="",
    description="",
    revision_label="",
    issued_date=None,
    revision_notes="",
):
    _ensure_upload_target(project)
    storage, storage_key, validated = _store_uploaded_file(
        project=project, uploaded_file=uploaded_file
    )
    try:
        with transaction.atomic():
            _, project_file = _create_file_records(
                project=project,
                user=user,
                storage_key=storage_key,
                validated=validated,
            )
            document = Document.objects.create(
                project=project,
                title=title,
                category=category,
                discipline=discipline,
                description=description,
                created_by=user,
            )
            _record_document_created(document, user)
            revision = DocumentRevision.objects.create(
                document=document,
                project_file=project_file,
                revision_label=revision_label,
                issued_date=issued_date,
                source_filename=validated.original_filename,
                notes=revision_notes,
                created_by=user,
            )
            _record_revision_created(revision, user)
            request_source_verification(revision=revision, requested_by=user)
            document = set_current_revision(document=document, revision=revision, actor=user)
            _advance_project_after_first_upload(project, user)
        return document, revision
    except Exception:
        _compensate(storage, storage_key)
        raise


def upload_document_revision(
    *,
    document,
    user,
    uploaded_file,
    revision_label="",
    issued_date=None,
    revision_notes="",
    supersedes=None,
    make_current=False,
):
    project = document.project
    _ensure_upload_target(project, document)
    if supersedes is not None and supersedes.document_id != document.pk:
        raise ValidationError("A revision can supersede only a revision of this document.")

    storage, storage_key, validated = _store_uploaded_file(
        project=project, uploaded_file=uploaded_file
    )
    try:
        with transaction.atomic():
            _, project_file = _create_file_records(
                project=project,
                user=user,
                storage_key=storage_key,
                validated=validated,
            )
            revision = DocumentRevision.objects.create(
                document=document,
                project_file=project_file,
                revision_label=revision_label,
                issued_date=issued_date,
                source_filename=validated.original_filename,
                notes=revision_notes,
                supersedes=supersedes,
                created_by=user,
            )
            _record_revision_created(revision, user)
            request_source_verification(revision=revision, requested_by=user)
            if make_current:
                document = set_current_revision(document=document, revision=revision, actor=user)
        return document, revision
    except Exception:
        _compensate(storage, storage_key)
        raise
