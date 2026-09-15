"""M3-06 exact quote intake and private immutable attachment storage."""

import json
from datetime import timedelta
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.documents.models import FileAsset
from apps.organizations.models import Membership
from apps.outreach.bid_intake import (
    _fetch_resend_attachment,
    import_inbound_quote,
    record_manual_quote,
)
from apps.outreach.models import (
    BidAttachment,
    BidSubmission,
    OutreachResponse,
    OutreachSMTPConfiguration,
)

from .test_document_uploads import FakeObjectStorage
from .test_outreach import setup as outreach_setup
from .test_outreach_responses import fixture_outreach

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n% synthetic quote\n%%EOF\n"


@pytest.fixture
def setup(user, organization, membership):
    return outreach_setup.__wrapped__(user, organization, membership)


@pytest.fixture
def storage(monkeypatch):
    fake = FakeObjectStorage()
    monkeypatch.setattr("apps.outreach.bid_intake.get_object_storage", lambda: fake)
    monkeypatch.setattr("apps.outreach.views.get_object_storage", lambda: fake)
    return fake


def pdf(name="quote.pdf"):
    return SimpleUploadedFile(name, PDF, content_type="application/pdf")


def test_manual_multifile_quote_exact_binding_history_and_idempotency(setup, user, storage):
    project, recipient, _ = fixture_outreach(setup, user)
    key = "d7b957cd-f81c-4b66-8601-eed35fd4f9ed"
    received = timezone.now() - timedelta(hours=1)
    first = record_manual_quote(
        recipient=recipient,
        actor=user,
        files=[pdf("one.pdf"), pdf("two.pdf")],
        received_at=received,
        note="Forwarded quote",
        request_key=key,
    )
    assert first.project_id == project.pk
    assert first.scope_version_id == recipient.batch.campaign.scope_version_id
    assert first.campaign_id == recipient.batch.campaign_id
    assert first.batch_id == recipient.batch_id
    assert first.company_id == recipient.company_id and first.contact_id == recipient.contact_id
    assert first.attachments.count() == 2
    assert all(x.checksum == x.file_asset.checksum for x in first.attachments.all())
    recipient.refresh_from_db()
    assert recipient.current_status == "bid_submitted"
    assert recipient.qualification_state == "not_reviewed"
    again = record_manual_quote(
        recipient=recipient,
        actor=user,
        files=[pdf()],
        received_at=received,
        request_key=key,
    )
    assert again.pk == first.pk and BidSubmission.objects.count() == 1
    assert recipient.status_events.filter(new_status="bid_submitted").count() == 1
    second = record_manual_quote(
        recipient=recipient,
        actor=user,
        files=[pdf("later.pdf")],
        received_at=timezone.now(),
    )
    assert second.pk != first.pk and BidSubmission.objects.count() == 2
    attachment = first.attachments.first()
    attachment.original_filename = "rewritten.pdf"
    with pytest.raises(ValidationError):
        attachment.save()
    assert len(storage.objects) == 3


def test_invalid_and_zero_byte_quotes_rejected_without_storage(setup, user, storage):
    _, recipient, _ = fixture_outreach(setup, user)
    for upload in [
        SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf"),
        SimpleUploadedFile("script.exe", b"MZ", content_type="application/octet-stream"),
        SimpleUploadedFile("wrong.pdf", b"not pdf", content_type="application/pdf"),
    ]:
        with pytest.raises(ValidationError):
            record_manual_quote(
                recipient=recipient,
                actor=user,
                files=[upload],
                received_at=timezone.now(),
            )
    assert BidSubmission.objects.count() == 0 and not storage.objects


def test_inactive_project_and_mismatched_history_are_rejected(setup, user, storage):
    project, recipient, _ = fixture_outreach(setup, user)
    project.is_active = False
    project.save(update_fields=["is_active"])
    with pytest.raises(ValidationError):
        record_manual_quote(
            recipient=recipient, actor=user, files=[pdf()], received_at=timezone.now()
        )
    assert BidSubmission.objects.count() == 0 and not storage.objects
    project.is_active = True
    project.save(update_fields=["is_active"])
    submission = record_manual_quote(
        recipient=recipient, actor=user, files=[pdf()], received_at=timezone.now()
    )
    submission.project_id = project.pk + 999
    with pytest.raises(ValidationError):
        submission.full_clean()


def test_correlated_inbound_import_reuses_response_and_provider_attachment(
    setup, user, storage, monkeypatch
):
    project, recipient, message = fixture_outreach(setup, user)
    response = OutreachResponse.objects.create(
        organization=project.organization,
        project=project,
        recipient=recipient,
        message=message,
        channel="inbound_email",
        outcome="responded",
        provider_email_id="inbound-synthetic",
        from_address=recipient.email,
        to_address=message.reply_to,
        attachment_count=1,
        occurred_at=timezone.now(),
    )
    monkeypatch.setattr(
        "apps.outreach.resend_webhooks._received_details",
        lambda *args: {"id": "inbound-synthetic", "attachments": [{"id": "attachment-one"}]},
    )
    monkeypatch.setattr(
        "apps.outreach.bid_intake._fetch_resend_attachment", lambda *args: pdf("email-quote.pdf")
    )
    first = import_inbound_quote(response=response, actor=user)
    assert first.source == "inbound_email" and first.source_response_id == response.pk
    assert first.attachments.get().provider_attachment_id == "attachment-one"
    assert first.recipient_id == recipient.pk
    second = import_inbound_quote(response=response, actor=user)
    assert second.pk == first.pk
    assert (
        BidSubmission.objects.count()
        == BidAttachment.objects.count()
        == FileAsset.objects.count()
        == 1
    )
    assert recipient.status_events.filter(new_status="bid_submitted").count() == 1
    assert len(storage.objects) == 1


def test_unassigned_inbound_rejected_and_no_auto_import(setup, user, storage):
    project, recipient, _ = fixture_outreach(setup, user)
    OutreachResponse.objects.create(
        organization=project.organization,
        channel="inbound_email",
        provider_email_id="unassigned",
        attachment_count=1,
        occurred_at=timezone.now(),
    )
    unassigned = OutreachResponse.objects.get(provider_email_id="unassigned")
    with pytest.raises(ValidationError):
        import_inbound_quote(response=unassigned, actor=user)
    assert BidSubmission.objects.count() == 0 and not storage.objects
    recipient.refresh_from_db()
    assert recipient.qualification_state == "not_reviewed"


def test_provider_attachment_fetch_is_bounded_and_uses_only_trusted_url(
    organization, user, monkeypatch
):
    OutreachSMTPConfiguration.objects.create(
        organization=organization,
        updated_by=user,
        host="smtp.resend.com",
        encrypted_password="synthetic-ciphertext",
    )
    monkeypatch.setattr("apps.outreach.bid_intake.decrypt_password", lambda _: "synthetic-key")
    metadata = {
        "id": "attachment-one",
        "filename": "received.pdf",
        "size": len(PDF),
        "content_type": "application/pdf",
        "download_url": (
            "https://inbound-cdn.resend.com/existing-email/attachments/attachment-one"
            "?signed=synthetic"
        ),
    }
    requests = []

    class FakeOpener:
        def open(self, request, timeout):
            requests.append((request.full_url, timeout, dict(request.header_items())))
            return BytesIO(json.dumps(metadata).encode() if len(requests) == 1 else PDF)

    monkeypatch.setattr(
        "apps.outreach.bid_intake.urllib.request.build_opener", lambda *args: FakeOpener()
    )
    fetched = _fetch_resend_attachment(organization, "existing-email", "attachment-one")
    assert fetched.read() == PDF and fetched.name == "received.pdf"
    assert requests[0][0].endswith("/emails/receiving/existing-email/attachments/attachment-one")
    assert requests[0][1] == 10 and requests[1][1] == 20
    assert all("User-agent" in headers for _, _, headers in requests)
    metadata["download_url"] = (
        "https://cdn.resend.app/existing-email/attachments/attachment-one?token=synthetic"
    )
    requests.clear()
    assert _fetch_resend_attachment(organization, "existing-email", "attachment-one").read() == PDF
    assert len(requests) == 2
    metadata["download_url"] = (
        "https://cdn.resend.app:444/existing-email/attachments/attachment-one?token=synthetic"
    )
    requests.clear()
    with pytest.raises(ValidationError):
        _fetch_resend_attachment(organization, "existing-email", "attachment-one")
    assert len(requests) == 1
    metadata["download_url"] = (
        "https://cdn.resend.app/other-email/attachments/attachment-one?token=synthetic"
    )
    requests.clear()
    with pytest.raises(ValidationError):
        _fetch_resend_attachment(organization, "existing-email", "attachment-one")
    assert len(requests) == 1


def test_real_style_correlated_import_stores_once_and_failure_rolls_back(
    setup, user, storage, monkeypatch
):
    project, recipient, message = fixture_outreach(setup, user)
    response = OutreachResponse.objects.create(
        organization=project.organization,
        project=project,
        recipient=recipient,
        message=message,
        channel="inbound_email",
        outcome="responded",
        provider_email_id="existing-email",
        from_address=recipient.email,
        to_address=message.reply_to,
        attachment_count=1,
        occurred_at=timezone.now(),
    )
    OutreachSMTPConfiguration.objects.create(
        organization=project.organization,
        updated_by=user,
        host="smtp.resend.com",
        encrypted_password="synthetic-ciphertext",
    )
    monkeypatch.setattr("apps.outreach.bid_intake.decrypt_password", lambda _: "synthetic-key")
    monkeypatch.setattr(
        "apps.outreach.resend_webhooks._received_details",
        lambda *_: {"id": "existing-email", "attachments": [{"id": "attachment-one"}]},
    )
    metadata = {
        "id": "attachment-one",
        "filename": "received.pdf",
        "size": len(PDF),
        "content_type": "application/pdf",
        "download_url": (
            "https://cdn.resend.app/existing-email/attachments/attachment-one?token=synthetic"
        ),
    }
    requests = []

    class FakeOpener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            return BytesIO(json.dumps(metadata).encode() if len(requests) % 2 else PDF)

    monkeypatch.setattr(
        "apps.outreach.bid_intake.urllib.request.build_opener", lambda *args: FakeOpener()
    )
    original_url = metadata["download_url"]
    metadata["download_url"] = (
        "https://untrusted.example/existing-email/attachments/attachment-one?token=synthetic"
    )
    with pytest.raises(ValidationError, match="location is not trusted"):
        import_inbound_quote(response=response, actor=user)
    assert BidSubmission.objects.count() == BidAttachment.objects.count() == 0
    metadata["download_url"] = original_url
    requests.clear()
    storage.fail_save = True
    with pytest.raises(ValidationError, match="Attachment storage failed"):
        import_inbound_quote(response=response, actor=user)
    assert BidSubmission.objects.count() == BidAttachment.objects.count() == 0
    assert FileAsset.objects.count() == 0 and not storage.objects
    storage.fail_save = False
    first = import_inbound_quote(response=response, actor=user)
    second = import_inbound_quote(response=response, actor=user)
    assert first.pk == second.pk
    assert first.attachments.count() == 1
    assert first.attachments.get().provider_attachment_id == "attachment-one"
    assert len(storage.objects) == 1
    recipient.refresh_from_db()
    assert recipient.qualification_state == "not_reviewed"


def test_quote_api_operator_viewer_and_secure_download(setup, user, membership, storage):
    project, recipient, _ = fixture_outreach(setup, user)
    client = APIClient()
    client.force_authenticate(user)
    list_url = reverse(
        "bid-submission-list",
        kwargs={"organization_slug": project.organization.slug, "project_pk": project.pk},
    )
    assert client.get(list_url).data["submissions"] == []
    assert client.get(list_url).data["recipient_choices"] == [
        {
            "id": recipient.pk,
            "label": (
                f"{recipient.batch.campaign.trade_category} · {recipient.company_name}"
                f" · Batch {recipient.batch.sequence}"
            ),
        }
    ]
    result = client.post(
        list_url,
        {"recipient_id": recipient.pk, "received_at": timezone.now().isoformat(), "files": [pdf()]},
        format="multipart",
    )
    assert result.status_code == 200
    submission = BidSubmission.objects.get(pk=result.data["id"])
    attachment = submission.attachments.get()
    download_url = reverse(
        "bid-attachment-download",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "submission_pk": submission.pk,
            "attachment_pk": attachment.pk,
        },
    )
    download = client.get(download_url)
    assert download.status_code == 200 and b"".join(download.streaming_content) == PDF
    assert "attachment" in download["Content-Disposition"]
    assert attachment.file_asset.storage_key not in str(result.data)
    membership.role = Membership.Role.VIEWER
    membership.save()
    assert client.get(list_url).status_code == 200
    assert client.get(download_url).status_code == 200
    assert (
        client.post(list_url, {"recipient_id": recipient.pk}, format="multipart").status_code == 403
    )
    assert (
        client.post(
            reverse(
                "inbound-bid-import",
                kwargs={
                    "organization_slug": project.organization.slug,
                    "project_pk": project.pk,
                    "response_pk": 999999,
                },
            ),
            {},
            format="json",
        ).status_code
        == 403
    )
