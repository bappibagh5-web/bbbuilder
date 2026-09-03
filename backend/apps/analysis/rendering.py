import base64
import gc
import logging
import tempfile
from pathlib import Path

import pymupdf
from django.conf import settings

from apps.documents.storage import ObjectStorageError, get_object_storage

logger = logging.getLogger(__name__)


class PageRenderFailure(Exception):
    code = "page_render_failed"
    safe_message = "The source page could not be rendered safely for analysis."


def _remove(path):
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        logger.warning(
            "Temporary analysis artifact cleanup failed.",
            extra={"artifact_name": Path(path).name},
        )


def render_page_data_url(page):
    asset = page.document_revision.project_file.file_asset
    source = None
    pdf_path = None
    image_path = None
    try:
        source = get_object_storage().open(asset.storage_key)
        if source is None:
            raise PageRenderFailure()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as pdf_file:
            pdf_path = pdf_file.name
            while chunk := source.read(settings.PROCESSING_STREAM_CHUNK_BYTES):
                pdf_file.write(chunk)
        # Open from copied bytes so a failed parse cannot retain a Windows file
        # handle that prevents deterministic cleanup of the temporary source.
        document = pymupdf.open(stream=Path(pdf_path).read_bytes(), filetype="pdf")
        try:
            if document.needs_pass or page.page_number > document.page_count:
                raise PageRenderFailure()
            pdf_page = document.load_page(page.page_number - 1)
            longest = max(pdf_page.rect.width, pdf_page.rect.height)
            scale = min(settings.AI_RENDER_MAX_DIMENSION / max(longest, 1), 3.0)
            pixmap = pdf_page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image_file:
                image_path = image_file.name
            pixmap.save(image_path)
            encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            return f"data:image/png;base64,{encoded}", {
                "render_width": pixmap.width,
                "render_height": pixmap.height,
                "render_format": "png",
            }
        finally:
            document.close()
    except PageRenderFailure:
        raise
    except ObjectStorageError as error:
        raise PageRenderFailure() from error
    except Exception as error:
        # PyMuPDF can retain a failed-open file handle until collection on Windows.
        gc.collect()
        raise PageRenderFailure() from error
    finally:
        if source is not None:
            try:
                source.close()
            except Exception:
                logger.warning("Source stream cleanup failed during analysis rendering.")
        _remove(image_path)
        _remove(pdf_path)
