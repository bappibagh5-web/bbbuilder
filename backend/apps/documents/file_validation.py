import hashlib
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePath

from django.conf import settings
from django.core.exceptions import ValidationError

ALLOWED_UPLOAD_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".doc": {"application/msword", "application/octet-stream"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
    ".csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"},
    ".txt": {"text/plain"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
}

DETECTED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@dataclass(frozen=True)
class ValidatedUpload:
    original_filename: str
    extension: str
    declared_mime_type: str
    detected_mime_type: str
    byte_size: int
    checksum: str


def safe_original_filename(name: str) -> str:
    normalized = name.replace("\\", "/")
    filename = PurePath(normalized).name.strip()
    if (
        not filename
        or filename in {".", ".."}
        or len(filename) > 500
        or re.search(r"[\x00-\x1f\x7f]", filename)
    ):
        raise ValidationError({"file": "The uploaded filename is not valid."})
    return filename


def _read_head(uploaded_file, size=8192):
    uploaded_file.seek(0)
    head = uploaded_file.read(size)
    uploaded_file.seek(0)
    return head


def _ooxml_kind(uploaded_file):
    try:
        uploaded_file.seek(0)
        with zipfile.ZipFile(uploaded_file) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names:
                return None
            if any(name.startswith("word/") for name in names):
                return ".docx"
            if any(name.startswith("xl/") for name in names):
                return ".xlsx"
    except (OSError, zipfile.BadZipFile):
        return None
    finally:
        uploaded_file.seek(0)
    return None


def detect_mime_type(uploaded_file, extension: str) -> str:
    head = _read_head(uploaded_file)
    if head.startswith(b"%PDF-"):
        detected_extension = ".pdf"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_extension = ".png"
    elif head.startswith(b"\xff\xd8\xff"):
        detected_extension = ".jpg"
    elif head.startswith(b"PK\x03\x04"):
        detected_extension = _ooxml_kind(uploaded_file)
    elif head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        detected_extension = extension if extension in {".doc", ".xls"} else None
    else:
        detected_extension = None

    if detected_extension is not None:
        normalized_detected = ".jpg" if detected_extension == ".jpeg" else detected_extension
        normalized_extension = ".jpg" if extension == ".jpeg" else extension
        if normalized_detected != normalized_extension:
            raise ValidationError(
                {"file": "The file contents do not match the filename extension."}
            )
        return DETECTED_MIME_TYPES[detected_extension]

    if extension in DETECTED_MIME_TYPES:
        raise ValidationError({"file": "The file signature does not match the selected file type."})
    return ""


def validate_uploaded_file(uploaded_file) -> ValidatedUpload:
    if uploaded_file is None:
        raise ValidationError({"file": "Select a file to upload."})

    filename = safe_original_filename(uploaded_file.name)
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED_UPLOAD_TYPES:
        raise ValidationError({"file": "This file type is not supported."})

    byte_size = uploaded_file.size
    if byte_size <= 0:
        raise ValidationError({"file": "The uploaded file is empty."})
    if byte_size > settings.DOCUMENT_UPLOAD_MAX_BYTES:
        raise ValidationError(
            {
                "file": (
                    "The uploaded file exceeds the configured maximum size of "
                    f"{settings.DOCUMENT_UPLOAD_MAX_BYTES // (1024 * 1024)} MiB."
                )
            }
        )

    declared_mime_type = (uploaded_file.content_type or "").lower().split(";", 1)[0]
    if declared_mime_type not in ALLOWED_UPLOAD_TYPES[extension]:
        expected = mimetypes.guess_type(filename)[0] or "the expected type"
        raise ValidationError(
            {"file": f"The declared file type is not plausible for {extension} ({expected})."}
        )

    detected_mime_type = detect_mime_type(uploaded_file, extension)
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)

    return ValidatedUpload(
        original_filename=filename,
        extension=extension,
        declared_mime_type=declared_mime_type,
        detected_mime_type=detected_mime_type,
        byte_size=byte_size,
        checksum=digest.hexdigest(),
    )
