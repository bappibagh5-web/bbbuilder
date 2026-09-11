import base64

import pymupdf
from django.db import transaction
from django.utils import timezone

from .models import DocumentPage
from .storage import get_object_storage

IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}


class ImagePreparationFailure(Exception):
    safe_message = "The source image could not be prepared safely."


def is_image_asset(asset):
    return asset.detected_mime_type.lower() in IMAGE_MIME_TYPES


def read_image_bytes(asset):
    source = get_object_storage().open(asset.storage_key)
    if source is None:
        raise ImagePreparationFailure()
    try:
        return source.read()
    finally:
        source.close()


def image_data_url(asset):
    if not is_image_asset(asset):
        raise ImagePreparationFailure()
    encoded = base64.b64encode(read_image_bytes(asset)).decode("ascii")
    return f"data:{asset.detected_mime_type.lower()};base64,{encoded}"


@transaction.atomic
def persist_image_page(job):
    revision = job.document_revision
    asset = revision.project_file.file_asset
    if not is_image_asset(asset):
        return {}
    image_bytes = read_image_bytes(asset)
    try:
        image = pymupdf.open(stream=image_bytes, filetype=asset.detected_mime_type.split("/")[1])
        try:
            page = image.load_page(0)
            width = max(float(page.rect.width), 1.0)
            height = max(float(page.rect.height), 1.0)
        finally:
            image.close()
    except Exception as error:
        raise ImagePreparationFailure() from error

    existing = DocumentPage.objects.filter(document_revision=revision).first()
    if existing:
        return {
            "page_count": 1,
            "pages_with_native_text": 0,
            "pages_without_native_text": 1,
            "parser_name": existing.parser_name,
            "parser_version": existing.parser_version,
            "ocr_requested": False,
        }
    DocumentPage.objects.create(
        document_revision=revision,
        page_number=1,
        page_label="Image 1",
        width_points=width,
        height_points=height,
        rotation_degrees=0,
        native_text="",
        native_text_char_count=0,
        has_native_text=False,
        parser_name="PyMuPDF image metadata",
        parser_version=pymupdf.VersionBind,
        indexed_at=timezone.now(),
    )
    return {
        "page_count": 1,
        "pages_with_native_text": 0,
        "pages_without_native_text": 1,
        "parser_name": "PyMuPDF image metadata",
        "parser_version": pymupdf.VersionBind,
        "ocr_requested": False,
    }
