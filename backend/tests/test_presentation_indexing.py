import hashlib
import io
import zipfile

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.documents.models import Document, DocumentPage, DocumentRevision, FileAsset, ProjectFile
from apps.documents.presentation_indexing import parse_presentation_job, persist_slide_index
from apps.processing.models import ProcessingJob
from apps.processing.services import (
    chain_page_indexing_after_source_verification,
    execute_processing_job,
    request_presentation_indexing,
)
from apps.projects.models import Project

pytestmark = pytest.mark.django_db

PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def make_pptx(first_text="Plinth layout first"):
    content_types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types" />'
    presentation = """<p:presentation
      xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:sldIdLst><p:sldId id="257" r:id="rId2"/><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
      <p:sldSz cx="12192000" cy="6858000"/>
    </p:presentation>"""
    relationships = """<Relationships
      xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Target="slides/slide1.xml"/>
      <Relationship Id="rId2" Target="slides/slide2.xml"/>
    </Relationships>"""

    def slide(text):
        return f"""<p:sld
          xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p>
          </p:txBody></p:sp></p:spTree></p:cSld>
        </p:sld>"""

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/_rels/presentation.xml.rels", relationships)
        archive.writestr("ppt/slides/slide1.xml", slide("Second in presentation order"))
        archive.writestr("ppt/slides/slide2.xml", slide(first_text))
    return stream.getvalue()


class MemoryStorage:
    def __init__(self, content):
        self.content = content

    def open(self, key):
        return io.BytesIO(self.content)


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-PPTX-001",
        name="Presentation Index Test",
        project_timezone="America/Vancouver",
        status=Project.Status.DOCUMENTS_UPLOADED,
    )


@pytest.fixture
def revision(project, user):
    content = make_pptx()
    asset = FileAsset.objects.create(
        organization=project.organization,
        storage_backend=FileAsset.StorageBackend.S3,
        bucket="private-test",
        storage_key="presentations/plinth-layout.pptx",
        original_filename="Plinth Layout - INCTY.pptx",
        declared_mime_type=PPTX_MIME,
        detected_mime_type=PPTX_MIME,
        byte_size=len(content),
        checksum_algorithm=FileAsset.ChecksumAlgorithm.SHA256,
        checksum=hashlib.sha256(content).hexdigest(),
        created_by=user,
    )
    project_file = ProjectFile.objects.create(
        project=project, file_asset=asset, display_name=asset.original_filename, created_by=user
    )
    document = Document.objects.create(
        project=project,
        title="Plinth Layout - INCTY",
        category=Document.Category.OTHER,
        discipline=Document.Discipline.ARCHITECTURAL,
        created_by=user,
    )
    revision = DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="R1",
        source_filename=asset.original_filename,
        created_by=user,
    )
    return revision


def verified_job(revision, user):
    return ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.SOURCE_VERIFICATION,
        status=ProcessingJob.Status.SUCCEEDED,
        finished_at=timezone.now(),
        result_metadata={"checksum_match": True},
    )


def test_pptx_text_is_indexed_in_true_slide_order_without_ocr(revision, user, monkeypatch):
    content = make_pptx()
    monkeypatch.setattr(
        "apps.documents.presentation_indexing.get_object_storage", lambda: MemoryStorage(content)
    )
    verified_job(revision, user)
    job = request_presentation_indexing(revision=revision, requested_by=user, dispatch=False)
    slides = parse_presentation_job(job, heartbeat_callback=lambda *_: None)
    assert [slide.native_text for slide in slides] == [
        "Plinth layout first",
        "Second in presentation order",
    ]
    result = persist_slide_index(job, slides)
    pages = list(DocumentPage.objects.filter(document_revision=revision))
    assert [page.page_number for page in pages] == [1, 2]
    assert [page.page_label for page in pages] == ["Slide 1", "Slide 2"]
    assert pages[0].native_text == "Plinth layout first"
    assert result["ocr_requested"] is False
    assert result["pages_with_native_text"] == 2


def test_blank_slide_is_preserved_without_triggering_ocr(revision, user, monkeypatch):
    content = make_pptx("")
    monkeypatch.setattr(
        "apps.documents.presentation_indexing.get_object_storage", lambda: MemoryStorage(content)
    )
    verified_job(revision, user)
    job = request_presentation_indexing(revision=revision, requested_by=user, dispatch=False)
    slides = parse_presentation_job(job, heartbeat_callback=lambda *_: None)
    result = persist_slide_index(job, slides)
    assert (
        DocumentPage.objects.get(document_revision=revision, page_number=1).has_native_text is False
    )
    assert result["pages_without_native_text"] == 1
    assert result["ocr_requested"] is False


@override_settings(PROCESSING_AUTO_DISPATCH=False)
def test_source_verification_chains_durable_presentation_indexing(revision, user):
    source = verified_job(revision, user)
    chained = chain_page_indexing_after_source_verification(source)
    assert chained.job_type == ProcessingJob.JobType.PRESENTATION_INDEXING
    assert chained.status == ProcessingJob.Status.QUEUED


def test_presentation_job_executes_and_retry_path_remains_typed(revision, user, monkeypatch):
    content = make_pptx()
    monkeypatch.setattr(
        "apps.documents.presentation_indexing.get_object_storage", lambda: MemoryStorage(content)
    )
    verified_job(revision, user)
    job = request_presentation_indexing(revision=revision, requested_by=user, dispatch=False)
    assert execute_processing_job(job.pk)["outcome"] == "succeeded"
    job.refresh_from_db()
    assert job.status == ProcessingJob.Status.SUCCEEDED
    assert job.result_metadata["slide_count"] == 2
