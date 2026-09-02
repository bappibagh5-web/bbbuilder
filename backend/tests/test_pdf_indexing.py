import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pymupdf
import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents.models import (
    Document,
    DocumentPage,
    DocumentRevision,
    DrawingSheet,
    FileAsset,
    ProjectFile,
)
from apps.documents.pdf_indexing import (
    ParsedPage,
    PdfIndexingFailure,
    extract_sheet_candidate,
    normalize_page_label,
    parse_pdf_job,
    persist_page_index,
)
from apps.documents.storage import ObjectStorageError
from apps.documents.uploads import upload_new_document
from apps.organizations.models import Membership, Organization
from apps.processing.models import ProcessingJob
from apps.processing.services import (
    dispatch_processing_job,
    execute_processing_job,
    request_pdf_indexing,
    request_source_verification,
    retry_processing_job,
)
from apps.projects.models import AuditEvent, Project

pytestmark = pytest.mark.django_db


def make_pdf(page_specs, *, encrypted=False, page_label_prefix=None):
    document = pymupdf.open()
    for spec in page_specs:
        page = document.new_page(
            width=spec.get("width", 612),
            height=spec.get("height", 792),
        )
        if spec.get("text"):
            page.insert_text((36, 72), spec["text"])
        if spec.get("rotation"):
            page.set_rotation(spec["rotation"])
    if page_label_prefix is not None:
        document.set_page_labels(
            [{"startpage": 0, "prefix": page_label_prefix, "style": "D", "firstpagenum": 1}]
        )
    options = {}
    if encrypted:
        options = {
            "encryption": pymupdf.PDF_ENCRYPT_AES_256,
            "owner_pw": "owner-test-password",
            "user_pw": "user-test-password",
        }
    content = document.tobytes(**options)
    document.close()
    return content


PDF_BYTES = make_pdf(
    [
        {"text": "SHEET NO: A1.01\nSHEET TITLE: FLOOR PLAN"},
        {"width": 842, "height": 595, "rotation": 90},
    ]
)


class MemoryStorage:
    def __init__(self, content=PDF_BYTES, unavailable=False):
        self.content = content
        self.unavailable = unavailable

    def open(self, key):
        if self.unavailable:
            raise ObjectStorageError("private storage detail")
        return io.BytesIO(self.content) if self.content is not None else None


class FailingStoredFile(io.BytesIO):
    def __init__(self, content, *, fail_read_after=None, fail_close=False):
        super().__init__(content)
        self.fail_read_after = fail_read_after
        self.fail_close = fail_close
        self.read_count = 0

    def read(self, size=-1):
        self.read_count += 1
        if self.fail_read_after is not None and self.read_count > self.fail_read_after:
            raise OSError("simulated private-storage read failure")
        return super().read(size)

    def close(self):
        if self.fail_close:
            self.fail_close = False
            raise OSError("simulated private-storage close failure")
        return super().close()


class StoredFileStorage:
    def __init__(self, stored_file):
        self.stored_file = stored_file

    def open(self, key):
        return self.stored_file


class UploadAndReadStorage:
    def __init__(self):
        self.objects = {}

    def save(self, key, uploaded_file, expected_size):
        uploaded_file.seek(0)
        content = b"".join(uploaded_file.chunks())
        assert len(content) == expected_size
        self.objects[key] = content
        uploaded_file.seek(0)
        return key

    def open(self, key):
        content = self.objects.get(key)
        return io.BytesIO(content) if content is not None else None

    def delete(self, key):
        self.objects.pop(key, None)


@pytest.fixture
def project(organization, user):
    return Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-PDF-001",
        name="PDF Index Test",
        project_timezone="America/Vancouver",
        status=Project.Status.DOCUMENTS_UPLOADED,
    )


def create_revision(project, user, content=PDF_BYTES, *, mime_type="application/pdf", key=None):
    key = key or (
        f"organizations/{project.organization_id}/projects/{project.pk}/"
        f"{hashlib.sha256(content).hexdigest()}.pdf"
    )
    asset = FileAsset.objects.create(
        organization=project.organization,
        storage_backend=FileAsset.StorageBackend.S3,
        bucket="private-test",
        storage_key=key,
        original_filename="drawing.pdf" if mime_type == "application/pdf" else "notes.txt",
        declared_mime_type=mime_type,
        detected_mime_type=mime_type,
        byte_size=len(content),
        checksum_algorithm=FileAsset.ChecksumAlgorithm.SHA256,
        checksum=hashlib.sha256(content).hexdigest(),
        created_by=user,
    )
    project_file = ProjectFile.objects.create(
        project=project,
        file_asset=asset,
        display_name=asset.original_filename,
        created_by=user,
    )
    document = Document.objects.create(
        project=project,
        title="Drawing Set",
        category=Document.Category.DRAWINGS,
        created_by=user,
    )
    return DocumentRevision.objects.create(
        document=document,
        project_file=project_file,
        revision_label="R1",
        source_filename=asset.original_filename,
        created_by=user,
    )


@pytest.fixture
def revision(project, user):
    return create_revision(project, user)


def mark_source_verified(revision, user):
    job = ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.SOURCE_VERIFICATION,
    )
    ProcessingJob.objects.filter(pk=job.pk).update(
        status=ProcessingJob.Status.SUCCEEDED,
        finished_at=timezone.now(),
        result_metadata={"checksum_match": True},
    )
    return job


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def context_kwargs(revision, organization=None, project=None):
    return {
        "organization_slug": (organization or revision.document.project.organization).slug,
        "project_pk": (project or revision.document.project).pk,
        "document_pk": revision.document_id,
        "revision_pk": revision.pk,
    }


def index_url(revision, organization=None, project=None):
    return reverse(
        "revision-request-pdf-indexing",
        kwargs=context_kwargs(revision, organization, project),
    )


def pages_url(revision, organization=None, project=None):
    return reverse(
        "revision-page-list",
        kwargs=context_kwargs(revision, organization, project),
    )


def page_detail_url(revision, page, organization=None, project=None):
    return reverse(
        "revision-page-detail",
        kwargs={
            **context_kwargs(revision, organization, project),
            "page_pk": page.pk,
        },
    )


def test_document_page_model_owns_exact_revision_and_validates_fields(revision):
    page = DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        page_label="A0.01",
        width_points=612,
        height_points=792,
        native_text="Floor Plan\n",
        native_text_char_count=11,
        has_native_text=True,
        parser_name="PyMuPDF",
        parser_version=pymupdf.VersionBind,
    )
    assert page.document_revision == revision
    page.page_number = 0
    with pytest.raises(ValidationError):
        page.full_clean()
    page.page_number = 1
    page.native_text_char_count = 1
    with pytest.raises(ValidationError):
        page.full_clean()


def test_page_number_unique_per_revision_and_historical_indexes_are_isolated(
    revision, project, user
):
    values = {
        "page_number": 1,
        "width_points": 612,
        "height_points": 792,
        "native_text": "",
        "native_text_char_count": 0,
        "has_native_text": False,
        "parser_name": "PyMuPDF",
        "parser_version": pymupdf.VersionBind,
    }
    DocumentPage.objects.create(document_revision=revision, **values)
    with pytest.raises(IntegrityError), transaction.atomic():
        DocumentPage.objects.bulk_create([DocumentPage(document_revision=revision, **values)])
    other = create_revision(project, user, content=make_pdf([{}]), key="other-revision.pdf")
    assert DocumentPage.objects.create(document_revision=other, **values).pk


def test_page_and_sheet_identity_cannot_be_reassigned(revision, project, user):
    page = DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        width_points=612,
        height_points=792,
        native_text="",
        native_text_char_count=0,
        has_native_text=False,
        parser_name="PyMuPDF",
        parser_version=pymupdf.VersionBind,
    )
    sheet = DrawingSheet.objects.create(
        page=page,
        sheet_number="A1.01",
        extraction_method=DrawingSheet.ExtractionMethod.NATIVE_TEXT,
        quality=DrawingSheet.Quality.HIGH,
    )
    other = create_revision(project, user, content=make_pdf([{}]), key="other-page.pdf")
    other_page = DocumentPage.objects.create(
        document_revision=other,
        page_number=1,
        width_points=612,
        height_points=792,
        native_text="",
        native_text_char_count=0,
        has_native_text=False,
        parser_name="PyMuPDF",
        parser_version=pymupdf.VersionBind,
    )
    page.document_revision = other
    with pytest.raises(ValidationError):
        page.save()
    sheet.page = other_page
    with pytest.raises(ValidationError):
        sheet.save()


def test_drawing_sheet_is_optional_unique_and_controlled(revision):
    page = DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        width_points=612,
        height_points=792,
        native_text="",
        native_text_char_count=0,
        has_native_text=False,
        parser_name="PyMuPDF",
        parser_version=pymupdf.VersionBind,
    )
    assert not hasattr(page, "drawing_sheet")
    sheet = DrawingSheet.objects.create(
        page=page,
        sheet_number="A101",
        extraction_method=DrawingSheet.ExtractionMethod.NATIVE_TEXT,
        quality=DrawingSheet.Quality.HIGH,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        DrawingSheet.objects.bulk_create(
            [
                DrawingSheet(
                    page=page,
                    sheet_number="A102",
                    extraction_method=DrawingSheet.ExtractionMethod.NATIVE_TEXT,
                    quality=DrawingSheet.Quality.MEDIUM,
                )
            ]
        )
    sheet.extraction_method = "ai"
    with pytest.raises(ValidationError):
        sheet.full_clean()


@pytest.mark.parametrize(
    ("page_label", "text", "number", "title", "method", "quality"),
    [
        ("A0.01", "Floor Plan", "A0.01", "", "page_label", "high"),
        (
            "",
            "SHEET NO: E101\nSHEET TITLE: ELECTRICAL POWER PLAN",
            "E101",
            "ELECTRICAL POWER PLAN",
            "native_text",
            "high",
        ),
        ("", "M201\nMECHANICAL PLAN", "M201", "MECHANICAL PLAN", "native_text", "medium"),
    ],
)
def test_conservative_sheet_extraction(page_label, text, number, title, method, quality):
    candidate = extract_sheet_candidate(page_label, text)
    assert candidate is not None
    assert (candidate.sheet_number, candidate.sheet_title) == (number, title)
    assert (candidate.extraction_method, candidate.quality) == (method, quality)


def test_ambiguous_text_and_filename_like_content_are_not_fabricated():
    assert extract_sheet_candidate("1", "Project 2026\nRetail Store") is None
    assert extract_sheet_candidate("", "architectural-drawing-set.pdf") is None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("A1.01", "A1.01"),
        ("  A1.01\t ", "A1.01"),
        (
            "<FEFF005B0031005D0020004A0044002000530050004F005200540053005F"
            "0049004E0054004500520043004900540059005F004F004E005F004D00300030"
            "0020002D002000460052004F004E005400200043004F005600450052002D004D"
            "00300030>",
            "[1] JD SPORTS_INTERCITY_ON_M00 - FRONT COVER-M00",
        ),
        ("<FEFF00GG>", ""),
        ("<FEFFD800>", ""),
        ("", ""),
    ],
)
def test_page_label_normalization_is_readable_complete_and_conservative(source, expected):
    assert normalize_page_label(source) == expected


@pytest.mark.parametrize(
    ("label", "number", "title"),
    [
        ("[1] PROJECT_M00 - FRONT COVER-M00", "M00", "FRONT COVER"),
        ("[5] PROJECT_M03 - SPRINKLER DRAWING-M03", "M03", "SPRINKLER DRAWING"),
        ("[8] PROJECT_M05 - SPECIFICATIONS-M06", "M06", "SPECIFICATIONS"),
    ],
)
def test_structured_page_label_provides_strong_sheet_identity(label, number, title):
    candidate = extract_sheet_candidate(label, "")
    assert candidate.sheet_number == number
    assert candidate.sheet_title == title
    assert candidate.extraction_method == DrawingSheet.ExtractionMethod.PAGE_LABEL
    assert candidate.quality == DrawingSheet.Quality.HIGH


def test_encoded_structured_label_provides_sheet_number_and_title():
    readable = "[5] GENERAL_PROJECT_CONTEXT_M03 - SPRINKLER DRAWING-M03"
    encoded = "<" + ("\ufeff" + readable).encode("utf-16-be").hex().upper() + ">"
    candidate = extract_sheet_candidate(encoded, "unrelated native text")
    assert candidate.sheet_number == "M03"
    assert candidate.sheet_title == "SPRINKLER DRAWING"
    assert candidate.extraction_method == DrawingSheet.ExtractionMethod.PAGE_LABEL


@pytest.mark.parametrize("label", ["<FEFF00GG>", "<FEFFD800>"])
def test_malformed_encoded_label_cannot_create_sheet_identity(label):
    assert extract_sheet_candidate(label, "") is None


def test_page_label_title_precedes_drawing_register_matches():
    text = "M00\nFRONT COVER\nDRAWING REGISTER\nPLUMBING PLAN\nM00\nM01\nM02"
    candidate = extract_sheet_candidate("[1] PROJECT_M00 - FRONT COVER-M00", text)
    assert candidate.sheet_number == "M00"
    assert candidate.sheet_title == "FRONT COVER"
    assert candidate.extraction_method == DrawingSheet.ExtractionMethod.PAGE_LABEL


def test_drawing_register_without_strong_label_does_not_supply_current_sheet_title():
    text = "M00\nFRONT COVER\nDRAWING REGISTER\nPLUMBING PLAN\nM00\nM01\nM02"
    assert extract_sheet_candidate("", text) is None


def test_parse_pdf_extracts_pages_geometry_rotation_text_and_blank_page(
    revision, user, monkeypatch
):
    job = ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
    )
    monkeypatch.setattr("apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage())
    pages = parse_pdf_job(job, heartbeat_callback=lambda job_id: None)
    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].width_points == pytest.approx(612)
    assert pages[0].height_points == pytest.approx(792)
    assert "SHEET NO" in pages[0].native_text
    assert pages[0].sheet.sheet_number == "A1.01"
    assert pages[1].rotation_degrees == 90
    assert pages[1].native_text == ""


def test_pdf_page_label_is_preserved(revision, user, monkeypatch):
    content = make_pdf([{"text": "Cover"}], page_label_prefix="A0.")
    asset = revision.project_file.file_asset
    FileAsset.objects.filter(pk=asset.pk).update(
        byte_size=len(content), checksum=hashlib.sha256(content).hexdigest()
    )
    job = ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
    )
    monkeypatch.setattr(
        "apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage(content)
    )
    page = parse_pdf_job(job, heartbeat_callback=lambda job_id: None)[0]
    assert page.page_label == "A0.1"
    assert page.sheet.sheet_number == "A0.1"


def test_temporary_pdf_is_removed_after_success_and_failure(revision, user, monkeypatch, tmp_path):
    paths = []
    real_named_temporary_file = __import__("tempfile").NamedTemporaryFile

    def named_temporary_file(*args, **kwargs):
        kwargs["dir"] = tmp_path
        result = real_named_temporary_file(*args, **kwargs)
        paths.append(Path(result.name))
        return result

    monkeypatch.setattr(
        "apps.documents.pdf_indexing.tempfile.NamedTemporaryFile", named_temporary_file
    )
    monkeypatch.setattr("apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage())
    job = ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
    )
    parse_pdf_job(job, heartbeat_callback=lambda job_id: None)
    assert paths and not paths[-1].exists()

    monkeypatch.setattr(
        "apps.documents.pdf_indexing.get_object_storage",
        lambda: MemoryStorage(b"%PDF-not-valid"),
    )
    with pytest.raises(PdfIndexingFailure):
        parse_pdf_job(job, heartbeat_callback=lambda job_id: None)
    assert not paths[-1].exists()


@pytest.mark.parametrize(
    "stored_file",
    [
        FailingStoredFile(PDF_BYTES, fail_read_after=1),
        FailingStoredFile(PDF_BYTES, fail_close=True),
    ],
    ids=("stream-read-failure", "stream-close-failure"),
)
def test_temporary_pdf_is_removed_when_source_stream_fails(
    revision, user, monkeypatch, tmp_path, stored_file
):
    paths = []
    real_named_temporary_file = __import__("tempfile").NamedTemporaryFile

    def named_temporary_file(*args, **kwargs):
        kwargs["dir"] = tmp_path
        result = real_named_temporary_file(*args, **kwargs)
        paths.append(Path(result.name))
        return result

    monkeypatch.setattr(
        "apps.documents.pdf_indexing.tempfile.NamedTemporaryFile", named_temporary_file
    )
    monkeypatch.setattr(
        "apps.documents.pdf_indexing.get_object_storage",
        lambda: StoredFileStorage(stored_file),
    )
    job = ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
    )

    with pytest.raises(ObjectStorageError):
        parse_pdf_job(job, heartbeat_callback=lambda job_id: None)

    assert paths and not paths[-1].exists()


def test_pdf_indexing_requires_verified_pdf(revision, project, user):
    with pytest.raises(ValidationError, match="Source verification"):
        request_pdf_indexing(revision=revision, requested_by=user)
    text_revision = create_revision(
        project,
        user,
        content=b"plain text",
        mime_type="text/plain",
        key="notes.txt",
    )
    mark_source_verified(text_revision, user)
    with pytest.raises(ValidationError, match="eligible validated PDF"):
        request_pdf_indexing(revision=text_revision, requested_by=user)


def test_source_verification_chains_pdf_indexing_but_not_non_pdf(
    revision, project, user, monkeypatch
):
    monkeypatch.setattr("apps.processing.services.get_object_storage", lambda: MemoryStorage())
    source = request_source_verification(revision=revision, requested_by=user)
    assert execute_processing_job(source.pk)["outcome"] == "succeeded"
    assert (
        ProcessingJob.objects.filter(
            document_revision=revision,
            job_type=ProcessingJob.JobType.PDF_INDEXING,
            status=ProcessingJob.Status.QUEUED,
        ).count()
        == 1
    )

    text_revision = create_revision(
        project,
        user,
        content=b"plain text",
        mime_type="text/plain",
        key="non-pdf.txt",
    )
    text_source = request_source_verification(revision=text_revision, requested_by=user)
    monkeypatch.setattr(
        "apps.processing.services.get_object_storage",
        lambda: MemoryStorage(b"plain text"),
    )
    assert execute_processing_job(text_source.pk)["outcome"] == "succeeded"
    assert not ProcessingJob.objects.filter(
        document_revision=text_revision,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
    ).exists()


def test_upload_source_verification_and_pdf_indexing_run_end_to_end(
    project, user, monkeypatch, django_capture_on_commit_callbacks
):
    storage = UploadAndReadStorage()
    monkeypatch.setattr("apps.documents.uploads.get_object_storage", lambda: storage)
    monkeypatch.setattr("apps.processing.services.get_object_storage", lambda: storage)
    monkeypatch.setattr("apps.documents.pdf_indexing.get_object_storage", lambda: storage)
    with django_capture_on_commit_callbacks(execute=False):
        _, uploaded_revision = upload_new_document(
            project=project,
            user=user,
            uploaded_file=SimpleUploadedFile("drawing.pdf", PDF_BYTES, "application/pdf"),
            title="Upload to index integration",
            category=Document.Category.DRAWINGS,
        )

    source_job = ProcessingJob.objects.get(
        document_revision=uploaded_revision,
        job_type=ProcessingJob.JobType.SOURCE_VERIFICATION,
    )
    assert execute_processing_job(source_job.pk)["outcome"] == "succeeded"
    pdf_job = ProcessingJob.objects.get(
        document_revision=uploaded_revision,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
    )
    assert execute_processing_job(pdf_job.pk)["outcome"] == "succeeded"
    assert list(
        DocumentPage.objects.filter(document_revision=uploaded_revision).values_list(
            "page_number", flat=True
        )
    ) == [1, 2]


@override_settings(PROCESSING_AUTO_DISPATCH=True)
def test_pdf_indexing_dispatches_after_commit_and_broker_failure_stays_queued(
    revision, user, monkeypatch, django_capture_on_commit_callbacks
):
    mark_source_verified(revision, user)
    publish = Mock(side_effect=ConnectionError("redis unavailable"))
    monkeypatch.setattr("apps.processing.tasks.process_processing_job.apply_async", publish)
    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        job = request_pdf_indexing(revision=revision, requested_by=user)
        assert publish.call_count == 0
    job.refresh_from_db()
    assert publish.call_count == 1
    assert job.status == ProcessingJob.Status.QUEUED
    assert job.last_dispatched_at is None


def test_successful_indexing_is_atomic_idempotent_and_preserves_sources(
    revision, user, monkeypatch
):
    mark_source_verified(revision, user)
    job = request_pdf_indexing(revision=revision, requested_by=user)
    monkeypatch.setattr("apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage())
    original_asset = FileAsset.objects.values().get(pk=revision.project_file.file_asset_id)
    original_revision = DocumentRevision.objects.values().get(pk=revision.pk)
    assert execute_processing_job(job.pk)["outcome"] == "succeeded"
    assert execute_processing_job(job.pk)["outcome"] == "noop"
    job.refresh_from_db()
    assert job.result_metadata["page_count"] == 2
    assert job.result_metadata["pages_with_native_text"] == 1
    assert job.result_metadata["pages_without_native_text"] == 1
    assert DocumentPage.objects.filter(document_revision=revision).count() == 2
    assert DrawingSheet.objects.filter(page__document_revision=revision).count() == 1
    assert FileAsset.objects.values().get(pk=revision.project_file.file_asset_id) == original_asset
    assert DocumentRevision.objects.values().get(pk=revision.pk) == original_revision
    assert revision.document.project.status == Project.Status.DOCUMENTS_UPLOADED


def test_decoded_page_label_is_persisted_completely(revision, user):
    job = ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
    )
    decoded = "[1] GENERAL_PROJECT_CONTEXT_M00 - FRONT COVER-M00 " + ("X" * 120)
    persist_page_index(
        job,
        [
            ParsedPage(
                page_number=1,
                page_label=decoded,
                width_points=612,
                height_points=792,
                rotation_degrees=0,
                native_text="",
                sheet=None,
            )
        ],
    )
    assert DocumentPage.objects.get(document_revision=revision).page_label == decoded


def test_successful_retry_replaces_incomplete_rows_without_duplicates(revision, user, monkeypatch):
    mark_source_verified(revision, user)
    failed = request_pdf_indexing(revision=revision, requested_by=user)
    ProcessingJob.objects.filter(pk=failed.pk).update(
        status=ProcessingJob.Status.FAILED,
        error_code=ProcessingJob.ErrorCode.INDEXING_ERROR,
        error_message="A previous indexing attempt was incomplete.",
        finished_at=timezone.now(),
    )
    failed.refresh_from_db()
    DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        width_points=100,
        height_points=100,
        native_text="incomplete",
        native_text_char_count=10,
        has_native_text=True,
        parser_name="interrupted",
        parser_version="0",
    )
    retry = retry_processing_job(job=failed, requested_by=user)
    monkeypatch.setattr("apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage())

    assert execute_processing_job(retry.pk)["outcome"] == "succeeded"
    pages = DocumentPage.objects.filter(document_revision=revision)
    assert list(pages.values_list("page_number", flat=True)) == [1, 2]
    assert pages.filter(parser_name="interrupted").count() == 0


def test_later_revision_index_does_not_replace_historical_revision_pages(
    revision, project, user, monkeypatch
):
    later = create_revision(
        project,
        user,
        content=make_pdf([{"text": "SHEET NO: E101\nSHEET TITLE: POWER PLAN"}]),
        key="historical-isolation.pdf",
    )
    monkeypatch.setattr("apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage())
    mark_source_verified(revision, user)
    first_job = request_pdf_indexing(revision=revision, requested_by=user)
    assert execute_processing_job(first_job.pk)["outcome"] == "succeeded"
    first_page_ids = list(revision.pages.values_list("pk", flat=True))

    later_content = make_pdf([{"text": "SHEET NO: E101\nSHEET TITLE: POWER PLAN"}])
    monkeypatch.setattr(
        "apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage(later_content)
    )
    mark_source_verified(later, user)
    later_job = request_pdf_indexing(revision=later, requested_by=user)
    assert execute_processing_job(later_job.pk)["outcome"] == "succeeded"

    assert list(revision.pages.values_list("pk", flat=True)) == first_page_ids
    assert later.pages.count() == 1
    assert not later.pages.filter(pk__in=first_page_ids).exists()


@pytest.mark.parametrize(
    ("content", "expected_code"),
    [
        (None, "source_missing"),
        (b"not a pdf", "not_pdf"),
        (b"%PDF-not-valid", "pdf_corrupt"),
        (make_pdf([{"text": "Protected"}], encrypted=True), "pdf_encrypted"),
    ],
)
def test_pdf_indexing_terminal_failures_are_safe(
    revision, user, monkeypatch, content, expected_code
):
    mark_source_verified(revision, user)
    job = request_pdf_indexing(revision=revision, requested_by=user)
    monkeypatch.setattr(
        "apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage(content)
    )
    assert execute_processing_job(job.pk)["outcome"] == "failed"
    job.refresh_from_db()
    assert job.error_code == expected_code
    assert "private-test" not in job.error_message
    assert not DocumentPage.objects.filter(document_revision=revision).exists()


def test_pdf_indexing_storage_outage_retries_boundedly(revision, user, monkeypatch):
    mark_source_verified(revision, user)
    job = request_pdf_indexing(revision=revision, requested_by=user)
    monkeypatch.setattr(
        "apps.documents.pdf_indexing.get_object_storage",
        lambda: MemoryStorage(unavailable=True),
    )
    assert execute_processing_job(job.pk)["outcome"] == "retry"
    assert execute_processing_job(job.pk)["outcome"] == "retry"
    assert execute_processing_job(job.pk)["outcome"] == "failed"
    job.refresh_from_db()
    assert job.error_code == ProcessingJob.ErrorCode.STORAGE_UNAVAILABLE
    assert "private storage detail" not in job.error_message


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (Membership.Role.ADMIN, True),
        (Membership.Role.ESTIMATOR_OPERATOR, True),
        (Membership.Role.VIEWER, False),
    ],
)
def test_pdf_indexing_api_roles_and_safe_page_metadata(
    revision, user, membership, role, allowed, monkeypatch
):
    membership.role = role
    membership.save(update_fields=("role",))
    mark_source_verified(revision, user)
    client = client_for(user)
    response = client.post(index_url(revision), {}, format="json")
    assert response.status_code == (201 if allowed else 403)
    if allowed:
        job = ProcessingJob.objects.get(pk=response.data["id"])
        monkeypatch.setattr(
            "apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage()
        )
        assert execute_processing_job(job.pk)["outcome"] == "succeeded"
    page_response = client.get(pages_url(revision))
    assert page_response.status_code == 200
    if page_response.data:
        assert "native_text" not in page_response.data[0]
        assert "storage_key" not in str(page_response.data)


def test_pdf_page_api_is_scoped_read_only_and_inactive_members_are_denied(
    revision, project, user, membership, organization
):
    mark_source_verified(revision, user)
    client = client_for(user)
    assert client.patch(pages_url(revision), {}, format="json").status_code == 405
    assert client.delete(pages_url(revision)).status_code == 405
    assert APIClient().get(pages_url(revision)).status_code in {401, 403}
    membership.is_active = False
    membership.save(update_fields=("is_active",))
    assert client.get(pages_url(revision)).status_code == 403
    membership.is_active = True
    membership.save(update_fields=("is_active",))
    other_organization = Organization.objects.create(name="Other", slug="other")
    assert client.get(pages_url(revision, organization=other_organization)).status_code == 403
    other_project = Project.objects.create(
        organization=organization,
        created_by=user,
        project_number="BB-PDF-OTHER",
        name="Other",
        project_timezone="America/Vancouver",
    )
    assert client.get(pages_url(revision, project=other_project)).status_code == 404


def test_page_detail_is_revision_scoped_and_rejects_mutation(revision, project, user, membership):
    page = DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        page_label="[1] GENERAL_PROJECT_CONTEXT_M00 - FRONT COVER-M00",
        width_points=612,
        height_points=792,
        native_text="private full native text",
        native_text_char_count=24,
        has_native_text=True,
        parser_name="PyMuPDF",
        parser_version=pymupdf.VersionBind,
    )
    other_revision = create_revision(project, user, content=make_pdf([{}]), key="detail-other.pdf")
    client = client_for(user)

    response = client.get(page_detail_url(revision, page))
    assert response.status_code == 200
    assert response.data["page_label"] == "[1] GENERAL_PROJECT_CONTEXT_M00 - FRONT COVER-M00"
    assert "native_text" not in response.data
    assert client.patch(page_detail_url(revision, page), {}, format="json").status_code == 405
    assert client.delete(page_detail_url(revision, page)).status_code == 405
    assert client.get(page_detail_url(other_revision, page)).status_code == 404


def test_retry_preserves_pdf_target_and_emits_specific_audit(
    revision, user, membership, monkeypatch
):
    mark_source_verified(revision, user)
    job = request_pdf_indexing(revision=revision, requested_by=user)
    monkeypatch.setattr(
        "apps.documents.pdf_indexing.get_object_storage", lambda: MemoryStorage(b"not a pdf")
    )
    assert execute_processing_job(job.pk)["outcome"] == "failed"
    retry_url = reverse(
        "processing-job-retry",
        kwargs={
            "organization_slug": revision.document.project.organization.slug,
            "project_pk": revision.document.project_id,
            "job_pk": job.pk,
        },
    )
    response = client_for(user).post(retry_url, {}, format="json")
    assert response.status_code == 201
    retry = ProcessingJob.objects.get(pk=response.data["id"])
    assert retry.job_type == ProcessingJob.JobType.PDF_INDEXING
    assert retry.document_revision == revision
    assert AuditEvent.objects.filter(action_code="pdf_indexing.retry_requested").exists()


def test_completed_pdf_index_prevents_casual_reindex(revision, user):
    mark_source_verified(revision, user)
    completed = ProcessingJob.objects.create(
        document_revision=revision,
        requested_by=user,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
    )
    ProcessingJob.objects.filter(pk=completed.pk).update(
        status=ProcessingJob.Status.SUCCEEDED,
        finished_at=timezone.now(),
    )
    with pytest.raises(ValidationError, match="already has a completed"):
        request_pdf_indexing(revision=revision, requested_by=user)


def test_dispatch_identity_contains_only_durable_job_id(revision, user, monkeypatch):
    mark_source_verified(revision, user)
    job = request_pdf_indexing(revision=revision, requested_by=user)
    publish = Mock(return_value=SimpleNamespace(id="pdf-task-id"))
    monkeypatch.setattr("apps.processing.tasks.process_processing_job.apply_async", publish)
    assert dispatch_processing_job(job.pk) is True
    publish.assert_called_once_with(args=(job.pk,))
