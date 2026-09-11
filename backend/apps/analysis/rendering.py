import base64
import gc
import io
import logging
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

import pymupdf
from django.conf import settings

from apps.documents.image_indexing import image_data_url, is_image_asset
from apps.documents.presentation_indexing import (
    DRAWING_NS,
    OFFICE_REL_NS,
    RELATIONSHIPS_NS,
    _safe_xml,
    _slide_dimensions,
    _slide_order,
    is_presentation_asset,
)
from apps.documents.storage import ObjectStorageError, get_object_storage

logger = logging.getLogger(__name__)


class PageRenderFailure(Exception):
    code = "page_render_failed"
    safe_message = "The source page could not be rendered safely for analysis."


PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
MAX_PRESENTATION_IMAGE_BYTES = 20 * 1024 * 1024


def _resolve_archive_member(base_name, target):
    parts = []
    for part in (PurePosixPath(base_name).parent / PurePosixPath(target)).parts:
        if part == "..":
            if not parts:
                raise PageRenderFailure()
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def _presentation_slide_pixmap(source_bytes, slide_number):
    try:
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
            presentation, slide_names = _slide_order(archive)
            if slide_number < 1 or slide_number > len(slide_names):
                raise PageRenderFailure()
            slide_name = slide_names[slide_number - 1]
            slide = _safe_xml(archive, slide_name)
            relationships_name = str(
                PurePosixPath(slide_name).parent
                / "_rels"
                / f"{PurePosixPath(slide_name).name}.rels"
            )
            relationships = _safe_xml(archive, relationships_name)
            targets = {
                item.attrib.get("Id", ""): item.attrib.get("Target", "")
                for item in relationships.findall(f"{{{RELATIONSHIPS_NS}}}Relationship")
                if item.attrib.get("Type", "").endswith("/image")
            }
            width, height = _slide_dimensions(presentation)
            output = pymupdf.open()
            try:
                output_page = output.new_page(width=width, height=height)
                for picture in slide.findall(f".//{{{PRESENTATION_NS}}}pic"):
                    blip = picture.find(f".//{{{DRAWING_NS}}}blip")
                    transform = picture.find(f".//{{{DRAWING_NS}}}xfrm")
                    if blip is None or transform is None:
                        continue
                    relationship_id = blip.attrib.get(f"{{{OFFICE_REL_NS}}}embed", "")
                    target = targets.get(relationship_id)
                    offset = transform.find(f"{{{DRAWING_NS}}}off")
                    extent = transform.find(f"{{{DRAWING_NS}}}ext")
                    if not target or offset is None or extent is None:
                        continue
                    if (
                        transform.attrib.get("rot")
                        or transform.attrib.get("flipH")
                        or transform.attrib.get("flipV")
                    ):
                        raise PageRenderFailure()
                    crop = picture.find(f".//{{{DRAWING_NS}}}srcRect")
                    if crop is not None and any(int(value or 0) for value in crop.attrib.values()):
                        raise PageRenderFailure()
                    member_name = _resolve_archive_member(slide_name, target)
                    member = archive.getinfo(member_name)
                    if member.file_size > MAX_PRESENTATION_IMAGE_BYTES:
                        raise PageRenderFailure()
                    x = int(offset.attrib["x"]) / 12700
                    y = int(offset.attrib["y"]) / 12700
                    cx = int(extent.attrib["cx"]) / 12700
                    cy = int(extent.attrib["cy"]) / 12700
                    output_page.insert_image(
                        pymupdf.Rect(x, y, x + cx, y + cy),
                        stream=archive.read(member),
                        keep_proportion=False,
                        overlay=True,
                    )
                longest = max(output_page.rect.width, output_page.rect.height)
                scale = min(settings.AI_RENDER_MAX_DIMENSION / max(longest, 1), 3.0)
                return output_page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            finally:
                output.close()
    except PageRenderFailure:
        raise
    except (KeyError, TypeError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        raise PageRenderFailure() from error


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
    if is_image_asset(asset):
        try:
            return image_data_url(asset), {
                "render_width": round(page.width_points),
                "render_height": round(page.height_points),
                "render_format": asset.detected_mime_type.split("/")[1],
            }
        except Exception as error:
            raise PageRenderFailure() from error
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
        if is_presentation_asset(asset):
            pixmap = _presentation_slide_pixmap(Path(pdf_path).read_bytes(), page.page_number)
            encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
            return f"data:image/png;base64,{encoded}", {
                "render_width": pixmap.width,
                "render_height": pixmap.height,
                "render_format": "png",
            }
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
