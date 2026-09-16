"""Explicit PDF-native-text quote extraction proposal; never financial authority."""

import re

import pymupdf
from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.analysis.providers import OpenAIAnalysisProvider, ProviderFailure
from apps.analysis.sanitization import sanitize_provider_value
from apps.documents.storage import get_object_storage
from apps.projects.audit import record_event

from .bid_revisions import decimal_money
from .models import BidAttachment, BidExtractionRun

MAX_AI_QUOTE_BYTES = 20 * 1024 * 1024
MAX_AI_QUOTE_TEXT = 100_000
BID_EXTRACTION_SCHEMA_VERSION = 3
EXTRACTION_KINDS = {
    "base_bid",
    "tax",
    "currency",
    "alternate",
    "allowance",
    "fee",
    "exclusion",
    "condition",
    "validity",
    "schedule",
    "scope_coverage",
}
COMMERCIAL_TREATMENTS = {
    "add",
    "deduct",
    "no_cost",
    "price_on_request",
    "included",
    "excluded",
    "extra",
    "allowance",
    "not_stated",
}
FEE_SUBJECT_PATTERN = re.compile(
    r"\b(permits?|inspection fees?|bonds?|freight|delivery|duties|fees?|charges?)\b",
    re.IGNORECASE,
)
LEAD_TIME_PATTERN = re.compile(
    r"\b(lead[\s-]?time|procurement duration|manufacturing duration|delivery duration)\b",
    re.IGNORECASE,
)
INCLUDED_IN_BASE_PATTERN = re.compile(
    r"\b(included in (?:the )?base bid|included in base price)\b", re.IGNORECASE
)
EXCLUDED_FROM_BASE_PATTERN = re.compile(
    r"\b(not included in (?:the )?base bid|excluded from (?:the )?base bid)\b",
    re.IGNORECASE,
)


def commercial_treatment(value, evidence):
    """Map explicit quote wording to the controlled commercial vocabulary."""
    text = " ".join(part for part in (value or "", evidence or "") if part).lower()
    if re.search(r"\b(not stated|needs? confirmation|to be confirmed|tbc)\b", text):
        return "not_stated"
    if re.search(r"\b(allowance|allowances)\b", text):
        return "allowance"
    if re.search(r"\b(excluded|exclude|by others)\b", text):
        return "excluded"
    if re.search(r"\b(extra|additional charge|add(?:ed)? cost)\b", text):
        return "extra"
    if re.search(r"\b(included|include|includes)\b", text):
        return "included"
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in COMMERCIAL_TREATMENTS else "not_stated"


def normalize_candidate(raw):
    """Normalize commercial classifications without changing source evidence."""
    candidate = dict(raw)
    evidence = " ".join(
        str(candidate.get(field) or "") for field in ("title", "description", "excerpt")
    )
    if candidate.get("kind") == "scope_coverage" and FEE_SUBJECT_PATTERN.search(evidence):
        candidate["kind"] = "fee"
    if candidate.get("kind") == "schedule" and LEAD_TIME_PATTERN.search(evidence):
        candidate["kind"] = "condition"
    if candidate.get("kind") == "allowance":
        if EXCLUDED_FROM_BASE_PATTERN.search(evidence):
            candidate["included_in_base_bid"] = False
        elif INCLUDED_IN_BASE_PATTERN.search(evidence):
            candidate["included_in_base_bid"] = True
    else:
        candidate["included_in_base_bid"] = None
    if candidate.get("kind") in {"fee", "tax"}:
        candidate["treatment"] = commercial_treatment(candidate.get("treatment"), evidence)
    elif candidate.get("kind") == "alternate" and candidate.get("treatment"):
        candidate["treatment"] = commercial_treatment(candidate["treatment"], evidence)
    return candidate


def extraction_schema():
    candidate = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "kind": {
                "type": "string",
                "enum": [
                    "base_bid",
                    "tax",
                    "currency",
                    "alternate",
                    "allowance",
                    "fee",
                    "exclusion",
                    "condition",
                    "validity",
                    "schedule",
                    "scope_coverage",
                ],
            },
            "title": {"type": "string"},
            "description": {"type": "string"},
            "amount": {"type": ["string", "null"]},
            "currency": {"type": ["string", "null"]},
            "treatment": {
                "type": ["string", "null"],
                "enum": [*sorted(COMMERCIAL_TREATMENTS), None],
            },
            "scope_item_id": {"type": ["integer", "null"]},
            "included_in_base_bid": {"type": ["boolean", "null"]},
            "page_number": {"type": "integer"},
            "excerpt": {"type": "string"},
        },
        "required": [
            "kind",
            "title",
            "description",
            "amount",
            "currency",
            "treatment",
            "scope_item_id",
            "included_in_base_bid",
            "page_number",
            "excerpt",
        ],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {"candidates": {"type": "array", "items": candidate}},
        "required": ["candidates"],
    }


def quote_pages(attachment):
    if attachment.content_type != "application/pdf" or attachment.byte_size > MAX_AI_QUOTE_BYTES:
        raise ValidationError(
            "AI extraction currently supports bounded native-text PDF quotes only."
        )
    stored = get_object_storage().open(attachment.file_asset.storage_key)
    if stored is None:
        raise ValidationError("The private source quote is unavailable; structure it manually.")
    try:
        source = stored.read(MAX_AI_QUOTE_BYTES + 1)
    finally:
        stored.close()
    if len(source) > MAX_AI_QUOTE_BYTES:
        raise ValidationError(
            "This quote is too large for assisted extraction; structure it manually."
        )
    try:
        with pymupdf.open(stream=source, filetype="pdf") as pdf:
            pages = [
                {"page_number": index + 1, "text": page.get_text("text")}
                for index, page in enumerate(pdf)
            ]
    except Exception as error:
        raise ValidationError("This PDF could not be read; structure it manually.") from error
    if not pages or sum(len(page["text"].strip()) for page in pages) < 20:
        raise ValidationError("This quote has no usable native PDF text; structure it manually.")
    if sum(len(page["text"]) for page in pages) > MAX_AI_QUOTE_TEXT:
        raise ValidationError("This quote exceeds assisted text limits; structure it manually.")
    return pages


def validate_candidates(output, pages, scope_item_ids):
    if not isinstance(output, dict) or not isinstance(output.get("candidates"), list):
        raise ValidationError("The AI proposal did not match the expected structure.")
    page_text = {page["page_number"]: page["text"] for page in pages}
    valid = []
    for raw in output["candidates"]:
        if not isinstance(raw, dict) or set(raw) != set(
            extraction_schema()["properties"]["candidates"]["items"]["required"]
        ):
            continue
        raw = normalize_candidate(raw)
        if (
            raw["kind"] not in EXTRACTION_KINDS
            or not isinstance(raw["title"], str)
            or not raw["title"].strip()
            or not isinstance(raw["description"], str)
            or raw["treatment"] is not None
            and not isinstance(raw["treatment"], str)
            or raw["scope_item_id"] is not None
            and (
                not isinstance(raw["scope_item_id"], int) or isinstance(raw["scope_item_id"], bool)
            )
            or raw["included_in_base_bid"] is not None
            and not isinstance(raw["included_in_base_bid"], bool)
        ):
            continue
        page = raw["page_number"]
        excerpt = raw["excerpt"]
        if (
            not isinstance(page, int)
            or page not in page_text
            or not isinstance(excerpt, str)
            or not excerpt.strip()
            or excerpt not in page_text[page]
        ):
            continue
        if raw["scope_item_id"] is not None and raw["scope_item_id"] not in scope_item_ids:
            continue
        if raw["amount"] is not None:
            try:
                amount = decimal_money(raw["amount"])
            except ValidationError:
                continue
            raw["amount"] = str(amount)
        if raw["currency"] is not None and (
            not isinstance(raw["currency"], str)
            or len(raw["currency"]) != 3
            or not raw["currency"].isalpha()
            or raw["currency"] != raw["currency"].upper()
        ):
            continue
        if (
            raw["kind"] == "alternate"
            and raw["treatment"] in ("add", "deduct")
            and raw["amount"] is None
        ):
            continue
        valid.append(sanitize_provider_value(raw))
    return valid


@transaction.atomic
def request_extraction(*, attachment, actor, request_key=None):
    if settings.AI_PROVIDER_CLASS != "apps.analysis.providers.OpenAIAnalysisProvider":
        raise ValidationError("Live bid extraction provider is not configured.")
    attachment = BidAttachment.objects.select_for_update().get(pk=attachment.pk)
    if not attachment.submission.project.is_active:
        raise ValidationError(
            "Archived projects remain readable but cannot extract new bid details."
        )
    # Reject unsupported format before creating provider work.
    if attachment.content_type != "application/pdf":
        raise ValidationError("AI extraction currently supports native-text PDF quotes only.")
    existing = (
        BidExtractionRun.objects.filter(
            submission=attachment.submission, request_key=request_key
        ).first()
        if request_key
        else None
    )
    if existing:
        return existing
    active = BidExtractionRun.objects.filter(
        attachment=attachment, status__in=("queued", "running")
    ).first()
    if active:
        return active
    run = BidExtractionRun.objects.create(
        submission=attachment.submission,
        attachment=attachment,
        requested_by=actor,
        provider="openai",
        model=settings.AI_MODEL,
        schema_version=BID_EXTRACTION_SCHEMA_VERSION,
        request_key=request_key,
    )
    record_event(
        organization=attachment.submission.organization,
        project=attachment.submission.project,
        actor=actor,
        action_code="bid_extraction.started",
        target=run,
        metadata={"submission_id": attachment.submission_id, "attachment_id": attachment.pk},
    )
    transaction.on_commit(lambda: process_bid_extraction.delay(run.pk))
    return run


@shared_task(name="outreach.process_bid_extraction")
def process_bid_extraction(run_id):
    with transaction.atomic():
        run = (
            BidExtractionRun.objects.select_for_update()
            .select_related("attachment__file_asset", "submission__scope_version")
            .get(pk=run_id)
        )
        if run.status != BidExtractionRun.Status.QUEUED:
            return
        run.status = BidExtractionRun.Status.RUNNING
        run.started_at = timezone.now()
        run.save()
    try:
        pages = quote_pages(run.attachment)
        scope_items = list(run.submission.scope_version.scope_items.values("id", "title"))
        result = OpenAIAnalysisProvider().analyze(
            model=run.model,
            system_prompt=(
                "Extract only explicitly quoted facts from this single subcontractor quote. "
                "Return evidence as an exact contiguous native-text excerpt and 1-based PDF page. "
                "Amounts are unambiguous unsigned decimal strings with no commas or symbols. "
                "Classify permits, inspection fees, bonds, freight, delivery, duties, and other "
                "commercial charges as kind fee, never scope_coverage. Use only controlled "
                "treatments add, deduct, no_cost, price_on_request, included, excluded, extra, "
                "allowance, or not_stated. Ordinary physical construction obligations remain "
                "scope_coverage. Preserve an explicit allowance statement that it is included "
                "in or excluded from the base bid in included_in_base_bid; otherwise use null. "
                "Classify procurement, equipment, manufacturing, or delivery lead time as a "
                "condition, not schedule. Keep actual work or mobilization duration as schedule. "
                "Do not infer missing amounts, taxes, currency or exclusions from silence. "
                "Do not compare contractors or recommend a winner."
            ),
            input_payload={"quote_pages": pages, "quoted_scope_items": scope_items},
            schema=extraction_schema(),
        )
        with transaction.atomic():
            run = BidExtractionRun.objects.select_for_update().get(pk=run_id)
            run.request_id = result.request_id
            run.usage = sanitize_provider_value(result.usage or {})
            run.save()
        candidates = validate_candidates(
            sanitize_provider_value(result.structured_output),
            pages,
            {item["id"] for item in scope_items},
        )
        with transaction.atomic():
            run = BidExtractionRun.objects.select_for_update().get(pk=run_id)
            run.candidates = candidates
            run.status = BidExtractionRun.Status.SUCCEEDED
            run.completed_at = timezone.now()
            run.save()
            record_event(
                organization=run.submission.organization,
                project=run.submission.project,
                actor=run.requested_by,
                action_code="bid_extraction.completed",
                target=run,
                metadata={"candidate_count": len(candidates)},
            )
    except (ProviderFailure, ValidationError) as error:
        with transaction.atomic():
            run = BidExtractionRun.objects.select_for_update().get(pk=run_id)
            run.status = BidExtractionRun.Status.FAILED
            run.safe_error_code = (
                error.code if isinstance(error, ProviderFailure) else "bid_extraction_unsupported"
            )
            run.safe_error_message = (
                error.safe_message
                if isinstance(error, ProviderFailure)
                else "Assisted extraction could not be completed; structure the quote manually."
            )
            run.completed_at = timezone.now()
            run.save()
            record_event(
                organization=run.submission.organization,
                project=run.submission.project,
                actor=run.requested_by,
                action_code="bid_extraction.failed",
                target=run,
                metadata={"error_code": run.safe_error_code},
            )
    except Exception:
        # Do not leak provider response, source text, or credentials through task errors.
        with transaction.atomic():
            run = BidExtractionRun.objects.select_for_update().get(pk=run_id)
            run.status = BidExtractionRun.Status.FAILED
            run.safe_error_code = "bid_extraction_failed"
            run.safe_error_message = "Assisted extraction failed; structure the quote manually."
            run.completed_at = timezone.now()
            run.save()
            record_event(
                organization=run.submission.organization,
                project=run.submission.project,
                actor=run.requested_by,
                action_code="bid_extraction.failed",
                target=run,
                metadata={"error_code": run.safe_error_code},
            )
