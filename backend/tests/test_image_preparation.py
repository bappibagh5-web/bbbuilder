import base64
import hashlib
import io
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.analysis.rendering import render_page_data_url
from apps.analysis.services import _eligible_pages
from apps.documents.document_sets import project_document_set, set_document_included
from apps.documents.models import Document, DocumentRevision, FileAsset, ProjectFile
from apps.processing.models import ProcessingJob
from apps.processing.services import execute_processing_job
from apps.projects.models import Project

pytestmark = pytest.mark.django_db

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.fixture
def image_revision(organization, user):
    project = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-IMAGE-001",
        name="Image Preparation Test",
        project_timezone="America/Vancouver",
        status=Project.Status.DOCUMENTS_UPLOADED,
    )
    asset = FileAsset.objects.create(
        organization=organization,
        bucket="private-test",
        storage_key="images/gripple.png",
        original_filename="Gripple Attachments 047 273.png",
        declared_mime_type="image/png",
        detected_mime_type="image/png",
        byte_size=len(PNG_BYTES),
        checksum=hashlib.sha256(PNG_BYTES).hexdigest(),
        created_by=user,
    )
    project_file = ProjectFile.objects.create(project=project, file_asset=asset, created_by=user)
    document = Document.objects.create(
        project=project,
        title="Gripple Attachments 047 273",
        category=Document.Category.IMAGE_REFERENCE,
        discipline=Document.Discipline.MECHANICAL,
        created_by=user,
    )
    revision = DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        source_filename=asset.original_filename,
        revision_label="R1",
        created_by=user,
    )
    Document.objects.filter(pk=document.pk).update(current_revision=revision)
    document.refresh_from_db()
    job = ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.SOURCE_VERIFICATION,
    )
    return project, document, revision, job


def storage_with_image():
    storage = type("Storage", (), {})()
    storage.open = lambda _key: io.BytesIO(PNG_BYTES)
    return storage


def test_verified_image_becomes_one_prepared_selectable_page(image_revision, user):
    project, document, revision, job = image_revision
    with (
        patch(
            "apps.documents.image_indexing.get_object_storage", return_value=storage_with_image()
        ),
        patch("apps.processing.services.get_object_storage", return_value=storage_with_image()),
    ):
        assert execute_processing_job(job.pk)["outcome"] == "succeeded"

    job.refresh_from_db()
    page = revision.pages.get()
    assert job.result_metadata["page_count"] == 1
    assert job.result_metadata["ocr_requested"] is False
    assert page.page_number == 1
    assert page.page_label == "Image 1"
    assert page.native_text == ""
    assert page.has_native_text is False

    state = project_document_set(project)
    entry = state["groups"][0]["documents"][0]
    assert entry["preparation_status"] == "prepared"
    assert entry["page_count"] == 1
    selection, created = set_document_included(
        project=project, document=document, included=True, actor=user
    )
    assert created is True
    assert selection.selected_revision_id == revision.pk


def test_image_page_is_vision_eligible_and_renders_original_source(image_revision):
    _, _, revision, job = image_revision
    job.status = ProcessingJob.Status.SUCCEEDED
    job.finished_at = timezone.now()
    job.result_metadata = {"page_count": 1, "ocr_requested": False}
    job.save()
    from apps.documents.image_indexing import persist_image_page

    with patch(
        "apps.documents.image_indexing.get_object_storage", return_value=storage_with_image()
    ):
        persist_image_page(job)
        page = _eligible_pages(revision)[0]
        data_url, metadata = render_page_data_url(page)

    assert data_url.startswith("data:image/png;base64,")
    assert base64.b64decode(data_url.split(",", 1)[1]) == PNG_BYTES
    assert metadata["render_format"] == "png"
    assert page.has_native_text is False
