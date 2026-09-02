import gc
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.processing.models import ProcessingJob

from .models import DocumentPage, DrawingSheet
from .storage import ObjectStorageError, get_object_storage

logger = logging.getLogger(__name__)

PDF_MIME_TYPE = "application/pdf"
PDF_SIGNATURE = b"%PDF-"
ENCODED_UTF16BE_LABEL_PATTERN = re.compile(r"^<(?P<hex>FEFF(?:[0-9A-Fa-f]{4})*)>$")
SHEET_NUMBER_PATTERN = re.compile(r"^[A-Z]{1,3}[- ]?\d{1,3}(?:\.\d{1,3})?$", re.IGNORECASE)
STRUCTURED_PAGE_LABEL_PATTERN = re.compile(
    r"^\[\d+\]\s+.+?_(?P<context_number>[A-Z]{1,3}[- ]?\d{1,3}(?:\.\d{1,3})?)"
    r"\s+-\s+(?P<title>.+)\s*-\s*"
    r"(?P<terminal_number>[A-Z]{1,3}[- ]?\d{1,3}(?:\.\d{1,3})?)$",
    re.IGNORECASE,
)
LABELED_SHEET_NUMBER_PATTERN = re.compile(
    r"^(?:sheet|drawing)\s*(?:no\.?|number)?\s*[:#-]?\s*"
    r"(?P<number>[A-Z]{1,3}[- ]?\d{1,3}(?:\.\d{1,3})?)\b",
    re.IGNORECASE,
)
LABELED_SHEET_TITLE_PATTERN = re.compile(
    r"^sheet\s*title\s*[:#-]\s*(?P<title>.+)$",
    re.IGNORECASE,
)
CONSERVATIVE_TITLE_PATTERN = re.compile(
    r"\b(?:floor|ceiling|roof|site|mechanical|electrical|plumbing|fire\s+protection|"
    r"lighting|power|demolition|life\s+safety|door|finish|equipment)\b.*"
    r"\b(?:plan|schedule|layout|details?)\b|"
    r"\b(?:plans?|sections?|elevations?|details?|schedules?)\b",
    re.IGNORECASE,
)


class PdfIndexingFailure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class SheetCandidate:
    sheet_number: str
    sheet_title: str
    extraction_method: str
    quality: str


@dataclass(frozen=True)
class ParsedPage:
    page_number: int
    page_label: str
    width_points: float
    height_points: float
    rotation_degrees: int
    native_text: str
    sheet: SheetCandidate | None


def is_pdf_asset(asset):
    return asset.detected_mime_type.lower() == PDF_MIME_TYPE


def normalize_native_text(value):
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


def normalize_sheet_number(value):
    return re.sub(r"\s+", "", value).upper()


def normalize_page_label(value):
    label = value.strip()
    if not label:
        return ""
    if label.upper().startswith("<FEFF"):
        match = ENCODED_UTF16BE_LABEL_PATTERN.fullmatch(label)
        if not match:
            return ""
        try:
            decoded = bytes.fromhex(match.group("hex")).decode("utf-16-be")
        except (UnicodeDecodeError, ValueError):
            return ""
        label = decoded.removeprefix("\ufeff")
    if any(not character.isprintable() and not character.isspace() for character in label):
        return ""
    return " ".join(label.split())


def _safe_lines(native_text):
    return [line.strip() for line in native_text.splitlines() if 0 < len(line.strip()) <= 255]


def _extract_title(lines, number_line_index=None):
    for line in lines:
        match = LABELED_SHEET_TITLE_PATTERN.match(line)
        if match:
            title = match.group("title").strip(" -:|")
            if title:
                return title[:255]
    if number_line_index is not None:
        start = max(0, number_line_index - 3)
        end = min(len(lines), number_line_index + 4)
        for line in lines[start:end]:
            if CONSERVATIVE_TITLE_PATTERN.search(line):
                return line.strip(" -:|")[:255]
    return ""


def extract_sheet_candidate(page_label, native_text):
    label = normalize_page_label(page_label)
    lines = _safe_lines(native_text)
    structured_match = STRUCTURED_PAGE_LABEL_PATTERN.fullmatch(label)
    if structured_match:
        title = " ".join(structured_match.group("title").split()).strip(" -:|")
        if title:
            return SheetCandidate(
                sheet_number=normalize_sheet_number(structured_match.group("terminal_number")),
                sheet_title=title,
                extraction_method=DrawingSheet.ExtractionMethod.PAGE_LABEL,
                quality=DrawingSheet.Quality.HIGH,
            )
    if label and SHEET_NUMBER_PATTERN.fullmatch(label):
        title = _extract_title(lines)
        return SheetCandidate(
            sheet_number=normalize_sheet_number(label),
            sheet_title=title,
            extraction_method=DrawingSheet.ExtractionMethod.PAGE_LABEL,
            quality=DrawingSheet.Quality.HIGH,
        )

    for index, line in enumerate(lines):
        match = LABELED_SHEET_NUMBER_PATTERN.match(line)
        if match:
            return SheetCandidate(
                sheet_number=normalize_sheet_number(match.group("number")),
                sheet_title=_extract_title(lines, index),
                extraction_method=DrawingSheet.ExtractionMethod.NATIVE_TEXT,
                quality=DrawingSheet.Quality.HIGH,
            )

    standalone_numbers = [
        (index, line) for index, line in enumerate(lines) if SHEET_NUMBER_PATTERN.fullmatch(line)
    ]
    if len(standalone_numbers) == 1:
        index, line = standalone_numbers[0]
        adjacent_lines = lines[max(0, index - 1) : index] + lines[index + 1 : index + 2]
        title = next(
            (
                candidate
                for candidate in adjacent_lines
                if CONSERVATIVE_TITLE_PATTERN.search(candidate)
            ),
            "",
        )
        if title:
            return SheetCandidate(
                sheet_number=normalize_sheet_number(line),
                sheet_title=title.strip(" -:|")[:255],
                extraction_method=DrawingSheet.ExtractionMethod.NATIVE_TEXT,
                quality=DrawingSheet.Quality.MEDIUM,
            )
    return None


def _copy_source_to_temporary_pdf(job, *, heartbeat_callback):
    asset = job.document_revision.project_file.file_asset
    stored_file = get_object_storage().open(asset.storage_key)
    if stored_file is None:
        raise PdfIndexingFailure(
            ProcessingJob.ErrorCode.SOURCE_MISSING,
            "The stored source file could not be found.",
        )
    temporary_path = None
    byte_count = 0
    next_heartbeat = settings.PROCESSING_HEARTBEAT_BYTES
    header = b""
    primary_error = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="bb-builders-pdf-", suffix=".pdf", delete=False
        ) as tmp:
            temporary_path = Path(tmp.name)
            while primary_error is None:
                try:
                    chunk = stored_file.read(settings.PROCESSING_STREAM_CHUNK_BYTES)
                except Exception as error:
                    primary_error = ObjectStorageError(
                        "The source file could not be streamed from private storage."
                    )
                    primary_error.__cause__ = error
                    break
                if not chunk:
                    break
                if len(header) < len(PDF_SIGNATURE):
                    header = (header + chunk)[: len(PDF_SIGNATURE)]
                try:
                    tmp.write(chunk)
                except OSError as error:
                    primary_error = PdfIndexingFailure(
                        ProcessingJob.ErrorCode.INDEXING_ERROR,
                        "The source PDF could not be staged for indexing.",
                    )
                    primary_error.__cause__ = error
                    break
                byte_count += len(chunk)
                if byte_count >= next_heartbeat:
                    heartbeat_callback(job.pk)
                    next_heartbeat += settings.PROCESSING_HEARTBEAT_BYTES
    except OSError as error:
        if primary_error is None:
            primary_error = PdfIndexingFailure(
                ProcessingJob.ErrorCode.INDEXING_ERROR,
                "The source PDF could not be staged for indexing.",
            )
            primary_error.__cause__ = error
    except Exception as error:
        primary_error = primary_error or error
    try:
        stored_file.close()
    except Exception as error:
        if primary_error is None:
            primary_error = ObjectStorageError(
                "The source stream could not be closed safely after staging."
            )
            primary_error.__cause__ = error
        else:
            logger.warning(
                "Source stream close failed while preserving the primary PDF staging error.",
                extra={"processing_job_id": job.pk},
                exc_info=True,
            )
    if primary_error is not None:
        if temporary_path is not None:
            _remove_temporary_file(temporary_path)
        raise primary_error
    if header != PDF_SIGNATURE:
        if temporary_path:
            _remove_temporary_file(temporary_path)
        raise PdfIndexingFailure(
            ProcessingJob.ErrorCode.NOT_PDF,
            "The verified source is not a valid PDF file.",
        )
    return temporary_path


def _remove_temporary_file(path):
    gc.collect()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning(
            "Temporary PDF cleanup failed.",
            extra={"temporary_filename": path.name},
            exc_info=True,
        )


def parse_pdf_job(job, *, heartbeat_callback):
    asset = job.document_revision.project_file.file_asset
    if not is_pdf_asset(asset):
        raise PdfIndexingFailure(
            ProcessingJob.ErrorCode.NOT_PDF,
            "This source is not an eligible PDF file.",
        )
    temporary_path = _copy_source_to_temporary_pdf(job, heartbeat_callback=heartbeat_callback)
    try:
        open_failed = False
        try:
            document = pymupdf.open(temporary_path)
        except Exception:
            open_failed = True
        if open_failed:
            gc.collect()
            raise PdfIndexingFailure(
                ProcessingJob.ErrorCode.PDF_CORRUPT,
                "The PDF is damaged or cannot be opened safely.",
            ) from None
        with document:
            if not document.is_pdf:
                raise PdfIndexingFailure(
                    ProcessingJob.ErrorCode.NOT_PDF,
                    "The verified source is not a valid PDF file.",
                )
            if document.needs_pass:
                raise PdfIndexingFailure(
                    ProcessingJob.ErrorCode.PDF_ENCRYPTED,
                    "The PDF is password protected and cannot be indexed.",
                )
            if document.page_count < 1:
                raise PdfIndexingFailure(
                    ProcessingJob.ErrorCode.PDF_CORRUPT,
                    "The PDF does not contain any readable pages.",
                )
            parsed_pages = []
            for index in range(document.page_count):
                page = document.load_page(index)
                native_text = normalize_native_text(page.get_text("text", sort=False))
                cropbox = page.cropbox
                page_label = normalize_page_label(page.get_label() or "")
                parsed_pages.append(
                    ParsedPage(
                        page_number=index + 1,
                        page_label=page_label,
                        width_points=float(cropbox.width),
                        height_points=float(cropbox.height),
                        rotation_degrees=int(page.rotation),
                        native_text=native_text,
                        sheet=extract_sheet_candidate(page_label, native_text),
                    )
                )
                heartbeat_callback(job.pk)
            return parsed_pages
    except PdfIndexingFailure:
        raise
    except Exception as error:
        raise PdfIndexingFailure(
            ProcessingJob.ErrorCode.PDF_CORRUPT,
            "The PDF is damaged or cannot be indexed safely.",
        ) from error
    finally:
        _remove_temporary_file(temporary_path)


@transaction.atomic
def persist_page_index(job, parsed_pages):
    revision = job.document_revision
    has_completed_index = ProcessingJob.objects.filter(
        document_revision=revision,
        job_type=ProcessingJob.JobType.PDF_INDEXING,
        status=ProcessingJob.Status.SUCCEEDED,
    ).exclude(pk=job.pk)
    if has_completed_index.exists():
        raise PdfIndexingFailure(
            ProcessingJob.ErrorCode.INDEXING_ERROR,
            "This revision already has a completed PDF page index.",
        )

    DrawingSheet.objects.filter(page__document_revision=revision).delete()
    DocumentPage.objects.filter(document_revision=revision).delete()
    indexed_at = timezone.now()
    pages = DocumentPage.objects.bulk_create(
        [
            DocumentPage(
                document_revision=revision,
                page_number=item.page_number,
                page_label=item.page_label,
                width_points=item.width_points,
                height_points=item.height_points,
                rotation_degrees=item.rotation_degrees,
                native_text=item.native_text,
                native_text_char_count=len(item.native_text),
                has_native_text=bool(item.native_text.strip()),
                parser_name="PyMuPDF",
                parser_version=pymupdf.VersionBind,
                indexed_at=indexed_at,
            )
            for item in parsed_pages
        ]
    )
    DrawingSheet.objects.bulk_create(
        [
            DrawingSheet(
                page=page,
                sheet_number=item.sheet.sheet_number,
                sheet_title=item.sheet.sheet_title,
                extraction_method=item.sheet.extraction_method,
                quality=item.sheet.quality,
            )
            for page, item in zip(pages, parsed_pages, strict=True)
            if item.sheet is not None
        ]
    )
    return {
        "page_count": len(pages),
        "pages_with_native_text": sum(page.has_native_text for page in pages),
        "pages_without_native_text": sum(not page.has_native_text for page in pages),
        "drawing_sheet_candidates": sum(item.sheet is not None for item in parsed_pages),
        "parser_name": "PyMuPDF",
        "parser_version": pymupdf.VersionBind,
        "indexed_at": indexed_at.isoformat(),
    }
