"""Explicit quote intake; immutable files and exact invitation associations."""

import logging
import re
import urllib.request
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.documents.file_validation import validate_uploaded_file
from apps.documents.models import FileAsset
from apps.documents.storage import ObjectStorageError, get_object_storage
from apps.documents.uploads import generate_storage_key
from apps.projects.audit import record_event

from .credentials import decrypt_password
from .models import (
    BidAttachment,
    BidSubmission,
    InvitationRecipient,
    OutreachSMTPConfiguration,
)
from .responses import advance_recipient
from .services import _authorize

logger = logging.getLogger(__name__)
QUOTE_EXTENSIONS = {".pdf", ".xls", ".xlsx", ".doc", ".docx", ".csv", ".png", ".jpg", ".jpeg"}
MAX_QUOTE_FILES = 10
_PROVIDER_ID = re.compile(r"[A-Za-z0-9-]{1,120}")


def _recipient_for_intake(recipient, actor):
    recipient = InvitationRecipient.objects.select_related(
        "batch__campaign", "company", "contact"
    ).get(pk=recipient.pk)
    campaign = recipient.batch.campaign
    _authorize(actor, campaign.organization)
    if recipient.current_status in {"prepared", "cancelled"} or not campaign.project.is_active:
        raise ValidationError("Record a quote only for a sent invitation in an active project.")
    return recipient


def _validated_quote_files(files):
    if not 1 <= len(files) <= MAX_QUOTE_FILES:
        raise ValidationError(f"Attach between 1 and {MAX_QUOTE_FILES} quote files.")
    validated = []
    for uploaded_file, provider_id in files:
        file_info = validate_uploaded_file(uploaded_file)
        if file_info.extension not in QUOTE_EXTENSIONS:
            raise ValidationError("This quote attachment type is not supported.")
        validated.append((uploaded_file, provider_id, file_info))
    return validated


def _store_submission(
    *, recipient, actor, source, received_at, note, files, response=None, request_key=None
):
    campaign = recipient.batch.campaign
    existing = (
        BidSubmission.objects.filter(source_response=response).first()
        if response
        else BidSubmission.objects.filter(
            organization=campaign.organization, request_key=request_key
        ).first()
        if request_key
        else None
    )
    if existing:
        if existing.recipient_id != recipient.pk or existing.source != source:
            raise ValidationError("This request identity belongs to another quote submission.")
        return existing
    validated = _validated_quote_files(files)
    try:
        storage = get_object_storage()
    except ObjectStorageError as error:
        raise ValidationError("Attachment storage failed.") from error
    stored = []
    try:
        for uploaded_file, provider_id, file_info in validated:
            key = generate_storage_key(
                organization_id=campaign.organization_id,
                project_id=campaign.project_id,
                extension=file_info.extension,
            )
            storage.save(key, uploaded_file, file_info.byte_size)
            stored.append((key, provider_id, file_info))
        with transaction.atomic():
            submission = BidSubmission.objects.create(
                organization=campaign.organization,
                project=campaign.project,
                scope_package=campaign.scope_package,
                scope_version=campaign.scope_version,
                campaign=campaign,
                batch=recipient.batch,
                recipient=recipient,
                company=recipient.company,
                contact=recipient.contact,
                source_response=response,
                source=source,
                received_at=received_at,
                recorded_by=actor,
                intake_note=note.strip()[:1000],
                request_key=request_key,
            )
            record_event(
                organization=campaign.organization,
                project=campaign.project,
                actor=actor,
                action_code="quote_submission.created",
                target=submission,
                metadata={
                    "recipient_id": recipient.pk,
                    "source": source,
                    "file_count": len(stored),
                },
            )
            if source == BidSubmission.Source.MANUAL_UPLOAD:
                record_event(
                    organization=campaign.organization,
                    project=campaign.project,
                    actor=actor,
                    action_code="manual_quote_uploaded",
                    target=submission,
                    metadata={"recipient_id": recipient.pk, "file_count": len(stored)},
                )
            for key, provider_id, file_info in stored:
                asset = FileAsset.objects.create(
                    organization=campaign.organization,
                    storage_backend=FileAsset.StorageBackend.S3,
                    bucket=settings.S3_BUCKET,
                    storage_key=key,
                    original_filename=file_info.original_filename,
                    declared_mime_type=file_info.declared_mime_type,
                    detected_mime_type=file_info.detected_mime_type,
                    byte_size=file_info.byte_size,
                    checksum_algorithm=FileAsset.ChecksumAlgorithm.SHA256,
                    checksum=file_info.checksum,
                    created_by=actor,
                )
                attachment = BidAttachment.objects.create(
                    submission=submission,
                    file_asset=asset,
                    original_filename=file_info.original_filename,
                    content_type=file_info.detected_mime_type or file_info.declared_mime_type,
                    byte_size=file_info.byte_size,
                    checksum=file_info.checksum,
                    provider_attachment_id=provider_id,
                )
                record_event(
                    organization=campaign.organization,
                    project=campaign.project,
                    actor=actor,
                    action_code="quote_attachment.stored",
                    target=attachment,
                    metadata={"submission_id": submission.pk, "byte_size": file_info.byte_size},
                )
            # Intake is the human-confirmed boundary; an email with attachments alone is not a bid.
            advance_recipient(
                recipient,
                "bid_submitted",
                actor=actor,
                source="human",
                reason="Quote intake confirmed.",
            )
            return submission
    except Exception as error:
        for key, _, _ in stored:
            try:
                storage.delete(key)
            except Exception:
                logger.warning("Quote upload compensation could not remove an orphaned object.")
        if isinstance(error, IntegrityError) and (response or request_key):
            existing = (
                BidSubmission.objects.filter(source_response=response).first()
                if response
                else BidSubmission.objects.filter(
                    organization=campaign.organization, request_key=request_key
                ).first()
            )
            if existing and existing.recipient_id == recipient.pk and existing.source == source:
                return existing
        if isinstance(error, ObjectStorageError):
            raise ValidationError("Attachment storage failed.") from error
        raise


def record_manual_quote(*, recipient, actor, files, received_at, note="", request_key=None):
    recipient = _recipient_for_intake(recipient, actor)
    if received_at > timezone.now() + timedelta(minutes=5):
        raise ValidationError("Quote received time cannot be in the future.")
    return _store_submission(
        recipient=recipient,
        actor=actor,
        source=BidSubmission.Source.MANUAL_UPLOAD,
        received_at=received_at,
        note=note,
        files=[(file, "") for file in files],
        request_key=request_key,
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValidationError("Quote attachment download redirected unexpectedly.")


def _fetch_resend_attachment(organization, email_id, attachment_id):
    """Fetch one provider-identified attachment; never follow an arbitrary signed URL."""
    if not _PROVIDER_ID.fullmatch(email_id) or not _PROVIDER_ID.fullmatch(attachment_id):
        raise ValidationError("Invalid provider attachment identifier.")
    config = OutreachSMTPConfiguration.objects.filter(organization=organization).first()
    if not config or config.host.lower() != "smtp.resend.com" or not config.encrypted_password:
        raise ValidationError("Resend attachment retrieval is not configured.")
    key = decrypt_password(config.encrypted_password)
    request = urllib.request.Request(
        f"https://api.resend.com/emails/receiving/{email_id}/attachments/{attachment_id}",
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "BB-Builders-Outreach/1.0",
        },
    )
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=10) as response:
            metadata_bytes = response.read(8193)
        if len(metadata_bytes) > 8192:
            raise ValidationError("Provider attachment metadata exceeds the safety limit.")
        import json

        metadata = json.loads(metadata_bytes)
        url = metadata.get("download_url", "")
        parsed = urlparse(url)
        if (
            metadata.get("id") != attachment_id
            or parsed.scheme != "https"
            or parsed.hostname not in {"inbound-cdn.resend.com", "cdn.resend.app"}
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or not parsed.path.endswith(f"/{email_id}/attachments/{attachment_id}")
            or not parsed.query
        ):
            raise ValidationError("Provider attachment location is not trusted.")
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(
            urllib.request.Request(url, headers={"User-Agent": "BB-Builders-Outreach/1.0"}),
            timeout=20,
        ) as response:
            content = response.read(settings.DOCUMENT_UPLOAD_MAX_BYTES + 1)
        if len(content) > settings.DOCUMENT_UPLOAD_MAX_BYTES or len(content) != metadata.get(
            "size"
        ):
            raise ValidationError("Provider attachment size is invalid.")
        return SimpleUploadedFile(
            metadata.get("filename", ""), content, content_type=metadata.get("content_type", "")
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValidationError("The provider attachment could not be retrieved.") from error


def import_inbound_quote(*, response, actor):
    if response.recipient_id is None or response.channel != "inbound_email":
        raise ValidationError("Only an exactly correlated inbound reply can become a quote.")
    recipient = _recipient_for_intake(response.recipient, actor)
    existing = BidSubmission.objects.filter(source_response=response).first()
    if existing:
        return existing
    from .resend_webhooks import _received_details

    details = _received_details(response.organization, response.provider_email_id)
    if not details or details.get("id") != response.provider_email_id:
        raise ValidationError("The received email is currently unavailable.")
    attachments = details.get("attachments")
    if not isinstance(attachments, list) or not 1 <= len(attachments) <= MAX_QUOTE_FILES:
        raise ValidationError("The received email has no supported quote attachments.")
    if any(not isinstance(item, dict) or not item.get("id") for item in attachments):
        raise ValidationError("The provider attachment list is invalid.")
    files = [
        (
            _fetch_resend_attachment(response.organization, response.provider_email_id, item["id"]),
            item["id"],
        )
        for item in attachments
    ]
    return _store_submission(
        recipient=recipient,
        actor=actor,
        source=BidSubmission.Source.INBOUND_EMAIL,
        received_at=response.occurred_at,
        note="",
        files=files,
        response=response,
    )
