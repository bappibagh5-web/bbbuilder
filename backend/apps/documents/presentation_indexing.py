import logging
import platform
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from django.db import transaction
from django.utils import timezone

from apps.processing.models import ProcessingJob

from .models import DocumentPage, DrawingSheet
from .storage import get_object_storage

logger = logging.getLogger(__name__)

PRESENTATION_MIME_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
EMU_PER_POINT = 12700
DEFAULT_SLIDE_WIDTH_POINTS = 720.0
DEFAULT_SLIDE_HEIGHT_POINTS = 540.0
MAX_XML_MEMBER_BYTES = 5 * 1024 * 1024
MAX_TOTAL_TEXT_CHARACTERS = 5_000_000


class PresentationIndexingFailure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class ParsedSlide:
    slide_number: int
    native_text: str
    width_points: float
    height_points: float


def is_presentation_asset(asset):
    return asset.detected_mime_type.lower() == PRESENTATION_MIME_TYPE


def _safe_xml(archive, name):
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.PRESENTATION_CORRUPT,
            "The presentation structure is incomplete or damaged.",
        ) from error
    if info.file_size > MAX_XML_MEMBER_BYTES:
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.PRESENTATION_CORRUPT,
            "A presentation component is too large to process safely.",
        )
    try:
        return ElementTree.fromstring(archive.read(info))
    except (ElementTree.ParseError, OSError, RuntimeError) as error:
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.PRESENTATION_CORRUPT,
            "The presentation structure is damaged and cannot be indexed.",
        ) from error


def _slide_order(archive):
    presentation = _safe_xml(archive, "ppt/presentation.xml")
    relationships = _safe_xml(archive, "ppt/_rels/presentation.xml.rels")
    targets = {
        item.attrib["Id"]: item.attrib.get("Target", "")
        for item in relationships.findall(f"{{{RELATIONSHIPS_NS}}}Relationship")
        if item.attrib.get("Id")
    }
    ordered = []
    for item in presentation.findall(f".//{{{PRESENTATION_NS}}}sldId"):
        relationship_id = item.attrib.get(f"{{{OFFICE_REL_NS}}}id", "")
        target = targets.get(relationship_id, "")
        if target:
            normalized = str(PurePosixPath("ppt") / PurePosixPath(target))
            normalized = str(PurePosixPath(normalized))
            while "/../" in f"/{normalized}/":
                parts = []
                for part in PurePosixPath(normalized).parts:
                    if part == "..":
                        if parts:
                            parts.pop()
                    elif part != ".":
                        parts.append(part)
                normalized = "/".join(parts)
            ordered.append(normalized)
    if not ordered:
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.PRESENTATION_CORRUPT,
            "The presentation does not contain any readable slides.",
        )
    return presentation, ordered


def _slide_dimensions(presentation):
    size = presentation.find(f"{{{PRESENTATION_NS}}}sldSz")
    if size is None:
        return DEFAULT_SLIDE_WIDTH_POINTS, DEFAULT_SLIDE_HEIGHT_POINTS
    try:
        return int(size.attrib["cx"]) / EMU_PER_POINT, int(size.attrib["cy"]) / EMU_PER_POINT
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return DEFAULT_SLIDE_WIDTH_POINTS, DEFAULT_SLIDE_HEIGHT_POINTS


def _slide_text(slide):
    paragraphs = []
    for paragraph in slide.findall(f".//{{{DRAWING_NS}}}p"):
        runs = [node.text or "" for node in paragraph.findall(f".//{{{DRAWING_NS}}}t")]
        text = "".join(runs).replace("\x00", "").strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _stage_presentation(job, heartbeat_callback):
    asset = job.document_revision.project_file.file_asset
    stored_file = get_object_storage().open(asset.storage_key)
    if stored_file is None:
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.SOURCE_MISSING,
            "The stored source file could not be found.",
        )
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="bb-builders-pptx-", suffix=".pptx", delete=False
        ) as tmp:
            path = Path(tmp.name)
            while True:
                chunk = stored_file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
                heartbeat_callback(job.pk)
        return path
    except OSError as error:
        if path:
            path.unlink(missing_ok=True)
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.INDEXING_ERROR,
            "The presentation could not be staged for indexing.",
        ) from error
    finally:
        try:
            stored_file.close()
        except Exception:
            logger.warning("Presentation source stream could not be closed cleanly.")


def parse_presentation_job(job, *, heartbeat_callback):
    if not is_presentation_asset(job.document_revision.project_file.file_asset):
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.NOT_PRESENTATION,
            "This source is not an eligible PowerPoint presentation.",
        )
    path = _stage_presentation(job, heartbeat_callback)
    try:
        with zipfile.ZipFile(path) as archive:
            presentation, slide_names = _slide_order(archive)
            width, height = _slide_dimensions(presentation)
            slides = []
            total_characters = 0
            for index, slide_name in enumerate(slide_names, start=1):
                text = _slide_text(_safe_xml(archive, slide_name))
                total_characters += len(text)
                if total_characters > MAX_TOTAL_TEXT_CHARACTERS:
                    raise PresentationIndexingFailure(
                        ProcessingJob.ErrorCode.PRESENTATION_CORRUPT,
                        "The presentation contains too much expanded text to process safely.",
                    )
                slides.append(ParsedSlide(index, text, width, height))
                heartbeat_callback(job.pk)
            return slides
    except zipfile.BadZipFile as error:
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.PRESENTATION_CORRUPT,
            "The presentation is damaged and cannot be opened safely.",
        ) from error
    finally:
        path.unlink(missing_ok=True)


@transaction.atomic
def persist_slide_index(job, parsed_slides):
    revision = job.document_revision
    completed = ProcessingJob.objects.filter(
        document_revision=revision,
        job_type=ProcessingJob.JobType.PRESENTATION_INDEXING,
        status=ProcessingJob.Status.SUCCEEDED,
    ).exclude(pk=job.pk)
    if completed.exists():
        raise PresentationIndexingFailure(
            ProcessingJob.ErrorCode.INDEXING_ERROR,
            "This revision already has a completed presentation index.",
        )
    DrawingSheet.objects.filter(page__document_revision=revision).delete()
    DocumentPage.objects.filter(document_revision=revision).delete()
    indexed_at = timezone.now()
    pages = DocumentPage.objects.bulk_create(
        [
            DocumentPage(
                document_revision=revision,
                page_number=slide.slide_number,
                page_label=f"Slide {slide.slide_number}",
                width_points=slide.width_points,
                height_points=slide.height_points,
                rotation_degrees=0,
                native_text=slide.native_text,
                native_text_char_count=len(slide.native_text),
                has_native_text=bool(slide.native_text.strip()),
                parser_name="OOXML Presentation",
                parser_version=platform.python_version(),
                indexed_at=indexed_at,
            )
            for slide in parsed_slides
        ]
    )
    return {
        "page_count": len(pages),
        "slide_count": len(pages),
        "pages_with_native_text": sum(page.has_native_text for page in pages),
        "pages_without_native_text": sum(not page.has_native_text for page in pages),
        "ocr_requested": False,
        "parser_name": "OOXML Presentation",
        "parser_version": platform.python_version(),
        "indexed_at": indexed_at.isoformat(),
    }
