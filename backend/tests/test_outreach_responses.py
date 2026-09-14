"""M3-05 verified Resend events, real-response evidence, and human decisions."""

import base64
import hashlib
import hmac
import json
import urllib.error
from datetime import timedelta
from io import BytesIO

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.outreach.credentials import encrypt_password
from apps.outreach.delivery import _message_key
from apps.outreach.models import (
    InvitationRecipient,
    OutreachDeliveryAttempt,
    OutreachMessage,
    OutreachProviderEmail,
    OutreachQualificationDecision,
    OutreachResponse,
    OutreachSMTPConfiguration,
    ResendWebhookConfiguration,
    ResendWebhookEvent,
)
from apps.outreach.resend_webhooks import (
    _exact_sent_message,
    _received_details,
    save_webhook_configuration,
    verify_signature,
)
from apps.outreach.responses import decide_qualification, record_manual_response
from apps.outreach.services import add_invitation_recipient, create_invitation_batch

from .test_outreach import campaign_for
from .test_outreach import setup as outreach_setup

pytestmark = pytest.mark.django_db


@pytest.fixture(name="setup")
def response_setup(user, organization, membership):
    return outreach_setup.__wrapped__(user, organization, membership)


KEY = Fernet.generate_key().decode("ascii")
SECRET = "whsec_" + base64.b64encode(b"synthetic-signing-secret-32-bytes!").decode()


def fixture_outreach(setup, user):
    project, _, _, candidate, contact = setup
    batch = create_invitation_batch(campaign=campaign_for(setup, user), actor=user)
    recipient = add_invitation_recipient(
        batch=batch, candidate=candidate, contact=contact, actor=user
    )
    message = OutreachMessage.objects.create(
        recipient=recipient,
        sequence=1,
        kind="invitation",
        from_name="BB Builders",
        from_address="outreach@example.invalid",
        reply_to="reply@example.invalid",
        to_address=recipient.email,
        subject="Synthetic RFQ",
        body="Synthetic scope",
        created_by=user,
    )
    OutreachDeliveryAttempt.objects.create(
        message=message,
        sequence=1,
        provider_key="smtp",
        idempotency_key=_message_key(message),
        status="succeeded",
        completed_at=timezone.now(),
    )
    InvitationRecipient.objects.filter(pk=recipient.pk).update(current_status="invited")
    recipient.refresh_from_db()
    return project, recipient, message


def sign(event_id, body, timestamp=None):
    timestamp = int(timezone.now().timestamp()) if timestamp is None else timestamp
    key = base64.b64decode(SECRET[6:])
    digest = base64.b64encode(
        hmac.new(key, f"{event_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    ).decode()
    return {
        "HTTP_SVIX_ID": event_id,
        "HTTP_SVIX_TIMESTAMP": str(timestamp),
        "HTTP_SVIX_SIGNATURE": f"v1,{digest}",
    }


def signed_post(config, event_id, event_type, data, *, created_at=None):
    body = json.dumps(
        {"type": event_type, "created_at": (created_at or timezone.now()).isoformat(), "data": data}
    ).encode()
    return APIClient().post(
        reverse("resend-webhook", kwargs={"endpoint_token": config.endpoint_token}),
        data=body,
        content_type="application/json",
        **sign(event_id, body),
    )


@pytest.fixture
def webhook_config(setup, user, membership):
    membership.role = Membership.Role.ADMIN
    membership.save()
    with override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=KEY):
        config = ResendWebhookConfiguration.objects.create(
            organization=setup[0].organization,
            updated_by=user,
            encrypted_signing_secret=encrypt_password(SECRET),
            is_enabled=True,
        )
        yield config


def test_signature_invalid_duplicate_and_replay_safe(webhook_config):
    config = webhook_config
    body = json.dumps(
        {
            "type": "email.sent",
            "created_at": timezone.now().isoformat(),
            "data": {"email_id": "synthetic-1"},
        }
    ).encode()
    url = reverse("resend-webhook", kwargs={"endpoint_token": config.endpoint_token})
    assert APIClient().post(url, data=body, content_type="application/json").status_code == 400
    bad = sign("evt-1", body)
    bad["HTTP_SVIX_SIGNATURE"] = "v1,invalid"
    assert (
        APIClient().post(url, data=body, content_type="application/json", **bad).status_code == 400
    )
    stale = sign("evt-1", body, int(timezone.now().timestamp()) - 600)
    with pytest.raises(ValidationError):
        verify_signature(
            body,
            {
                "svix-id": stale["HTTP_SVIX_ID"],
                "svix-timestamp": stale["HTTP_SVIX_TIMESTAMP"],
                "svix-signature": stale["HTTP_SVIX_SIGNATURE"],
            },
            SECRET,
        )
    first = signed_post(config, "evt-1", "email.sent", {"email_id": "synthetic-1"})
    assert first.status_code == 200 and first.data["created"] is True
    second = signed_post(config, "evt-1", "email.sent", {"email_id": "synthetic-1"})
    assert second.status_code == 200 and second.data["created"] is False
    assert ResendWebhookEvent.objects.count() == 1


def test_provider_events_correlate_by_message_id_and_do_not_imply_response(
    setup, user, webhook_config
):
    _, recipient, message = fixture_outreach(setup, user)
    config = webhook_config
    rfc_id = f"<{_message_key(message)}@example.invalid>"
    data = {"email_id": "outbound-1", "message_id": rfc_id, "to": [recipient.email]}
    assert signed_post(config, "evt-sent", "email.sent", data).status_code == 200
    assert (
        OutreachProviderEmail.objects.get(provider_email_id="outbound-1").message_id == message.pk
    )
    assert signed_post(config, "evt-open", "email.opened", data).status_code == 200
    assert signed_post(config, "evt-click", "email.clicked", data).status_code == 200
    assert signed_post(config, "evt-delivered", "email.delivered", data).status_code == 200
    recipient.refresh_from_db()
    assert recipient.delivery_state == "delivered"
    assert recipient.engagement_state == "clicked"
    assert recipient.response_state == "no_response"
    assert recipient.current_status == "opened"
    assert OutreachResponse.objects.count() == 0
    assert signed_post(config, "evt-late-sent", "email.sent", data).status_code == 200
    recipient.refresh_from_db()
    assert recipient.delivery_state == "delivered"
    assert signed_post(config, "evt-bounce", "email.bounced", data).status_code == 200
    recipient.refresh_from_db()
    assert recipient.delivery_state == "bounced"


def test_rewritten_provider_message_id_reconciles_only_exact_sent_content(
    setup, user, webhook_config, monkeypatch
):
    project, recipient, message = fixture_outreach(setup, user)
    config = webhook_config
    provider_id = "provider-rewritten-1"
    provider_message_id = "<rewritten@email.amazonses.com>"
    data = {"email_id": provider_id, "message_id": provider_message_id}
    monkeypatch.setattr("apps.outreach.resend_webhooks._sent_details", lambda *args: None)
    sent = signed_post(config, "evt-rewritten-sent", "email.sent", data)
    assert sent.status_code == 200 and sent.data["created"] is True
    delivered = signed_post(config, "evt-rewritten-delivered", "email.delivered", data)
    assert delivered.status_code == 200 and delivered.data["created"] is True
    event = ResendWebhookEvent.objects.get(webhook_id="evt-rewritten-sent")
    assert event.message_id is None
    assert ResendWebhookEvent.objects.get(webhook_id="evt-rewritten-delivered").message_id is None
    assert OutreachProviderEmail.objects.count() == 0

    exact = {
        "id": provider_id,
        "message_id": provider_message_id,
        "from": message.from_address,
        "to": [message.to_address],
        "subject": message.subject,
        "text": message.body,
    }
    monkeypatch.setattr("apps.outreach.resend_webhooks._sent_details", lambda *args: exact)
    replay = signed_post(config, "evt-rewritten-sent", "email.sent", data)
    assert replay.status_code == 200 and replay.data["created"] is False
    assert ResendWebhookEvent.objects.count() == 2
    assert ResendWebhookEvent.objects.get(pk=event.pk).message_id is None
    mapping = OutreachProviderEmail.objects.get(provider_email_id=provider_id)
    assert mapping.message_id == message.pk
    assert mapping.rfc_message_id == provider_message_id

    recipient.refresh_from_db()
    assert recipient.delivery_state == "delivered"
    assert recipient.current_status == "delivered"
    duplicate = signed_post(config, "evt-rewritten-delivered", "email.delivered", data)
    assert duplicate.status_code == 200 and duplicate.data["created"] is False
    assert ResendWebhookEvent.objects.count() == 2
    assert recipient.status_events.filter(new_status="delivered").count() == 1

    # A different signed provider event cannot steal this exact mapping.
    unrelated = {**data, "email_id": "different-provider", "message_id": "<other@ses.invalid>"}
    monkeypatch.setattr(
        "apps.outreach.resend_webhooks._sent_details",
        lambda *args: {**exact, "id": "different-provider", "text": "Different content"},
    )
    assert signed_post(config, "evt-unrelated", "email.sent", unrelated).status_code == 200
    assert OutreachProviderEmail.objects.count() == 1
    assert ResendWebhookEvent.objects.get(webhook_id="evt-unrelated").message_id is None
    assert project.pk


def test_pending_send_event_can_be_reconciled_without_subject_or_address_guessing(
    setup, user, webhook_config, monkeypatch
):
    _, recipient, message = fixture_outreach(setup, user)
    OutreachDeliveryAttempt.objects.filter(message=message).update(
        status="pending", completed_at=None
    )
    provider_id = "provider-pending-1"
    rewritten = "<provider-generated@email.amazonses.com>"
    monkeypatch.setattr(
        "apps.outreach.resend_webhooks._sent_details",
        lambda *args: {
            "id": provider_id,
            "message_id": rewritten,
            "from": message.from_address,
            "to": [message.to_address],
            "subject": message.subject,
            "text": message.body,
        },
    )
    data = {"email_id": provider_id, "message_id": rewritten}
    assert signed_post(webhook_config, "pending-send", "email.sent", data).status_code == 200
    assert OutreachProviderEmail.objects.get(provider_email_id=provider_id).message_id == message.pk
    assert recipient.status_events.filter(source="provider").count() == 0


@pytest.mark.parametrize(
    ("provider_text", "should_match"),
    [
        ("Synthetic scope", True),
        ("Synthetic scope\n", True),
        ("Synthetic scope\n\n", False),
        ("Synthetic sc0pe", False),
        ("Synthetic\n scope", False),
    ],
)
def test_sent_content_allows_only_one_transport_added_final_newline(
    setup, user, provider_text, should_match
):
    project, _, message = fixture_outreach(setup, user)
    provider_message_id = "<provider-generated@email.amazonses.com>"
    details = {
        "id": "synthetic-provider-id",
        "message_id": provider_message_id,
        "from": message.from_address,
        "to": [message.to_address],
        "subject": message.subject,
        "text": provider_text,
    }
    result = _exact_sent_message(project.organization, details, provider_message_id)
    assert (result is not None) is should_match
    if should_match:
        assert result.pk == message.pk


def test_received_reply_correlates_only_with_exact_thread_and_sender(
    setup, user, webhook_config, monkeypatch
):
    _, recipient, message = fixture_outreach(setup, user)
    config = webhook_config
    rfc_id = f"<{_message_key(message)}@example.invalid>"
    signed_post(config, "evt-send", "email.sent", {"email_id": "outbound-2", "message_id": rfc_id})
    monkeypatch.setattr(
        "apps.outreach.resend_webhooks._received_details",
        lambda organization, email_id: {
            "headers": {"in-reply-to": rfc_id},
            "from": recipient.email,
            "to": [message.reply_to],
            "text": "Yes, we will price this.",
            "id": email_id,
        },
    )
    inbound = {
        "email_id": "inbound-1",
        "message_id": "<reply-1@example.invalid>",
        "from": recipient.email,
        "to": [message.reply_to],
        "subject": "Re: Synthetic RFQ",
        "attachments": [{"id": "attachment-metadata"}],
    }
    assert signed_post(config, "evt-inbound", "email.received", inbound).status_code == 200
    response = OutreachResponse.objects.get(provider_email_id="inbound-1")
    assert response.recipient_id == recipient.pk and response.project_id == setup[0].pk
    assert response.body_text == "Yes, we will price this."
    assert response.attachment_count == 1
    recipient.refresh_from_db()
    assert recipient.current_status == "responded"
    assert signed_post(config, "evt-inbound", "email.received", inbound).data["created"] is False
    inbound["email_id"] = "inbound-2"
    inbound["from"] = "unknown@example.invalid"
    assert signed_post(config, "evt-unassigned", "email.received", inbound).status_code == 200
    assert OutreachResponse.objects.get(provider_email_id="inbound-2").recipient_id is None


def test_received_lookup_has_user_agent_and_403_is_safe(setup, user, monkeypatch):
    project = setup[0]
    with override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=KEY):
        OutreachSMTPConfiguration.objects.create(
            organization=project.organization,
            host="smtp.resend.com",
            encrypted_password=encrypt_password("synthetic-api-key"),
            updated_by=user,
        )
        seen = []

        class Reply:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self, *_):
                return b'{"id":"existing-inbound","headers":{}}'

        def successful(request, *, timeout):
            seen.append((request.get_header("User-agent"), request.get_header("Accept"), timeout))
            return Reply()

        monkeypatch.setattr("apps.outreach.resend_webhooks.urllib.request.urlopen", successful)
        assert (
            _received_details(project.organization, "existing-inbound")["id"] == "existing-inbound"
        )
        assert seen == [("BB-Builders-Outreach/1.0", "application/json", 10)]

        def denied(request, *, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, BytesIO(b""))

        monkeypatch.setattr("apps.outreach.resend_webhooks.urllib.request.urlopen", denied)
        assert _received_details(project.organization, "existing-inbound") is None


@pytest.mark.parametrize("reference_only", [False, True])
def test_existing_unassigned_reply_reconciles_once_by_exact_thread(
    setup, user, webhook_config, monkeypatch, reference_only
):
    project, recipient, message = fixture_outreach(setup, user)
    # An earlier identical invitation must not steal this provider-generated ID.
    older_message = OutreachMessage.objects.create(
        recipient=recipient,
        sequence=2,
        kind=message.kind,
        from_name=message.from_name,
        from_address=message.from_address,
        reply_to=message.reply_to,
        to_address=message.to_address,
        subject=message.subject,
        body=message.body,
        created_by=user,
    )
    older_attempt = OutreachDeliveryAttempt.objects.create(
        message=older_message,
        sequence=1,
        provider_key="smtp",
        idempotency_key=_message_key(older_message),
        status="succeeded",
        completed_at=timezone.now() - timedelta(minutes=20),
    )
    OutreachDeliveryAttempt.objects.filter(pk=older_attempt.pk).update(
        attempted_at=timezone.now() - timedelta(minutes=20)
    )
    config = webhook_config
    provider_id = "existing-outbound"
    provider_rfc_id = "<existing-provider@email.amazonses.com>"
    outbound = {"email_id": provider_id, "message_id": provider_rfc_id}
    monkeypatch.setattr("apps.outreach.resend_webhooks._sent_details", lambda *_: None)
    assert signed_post(config, "existing-sent", "email.sent", outbound).status_code == 200
    assert OutreachProviderEmail.objects.count() == 0
    monkeypatch.setattr("apps.outreach.resend_webhooks._received_details", lambda *_: None)
    inbound = {
        "email_id": "existing-inbound",
        "message_id": "<reply@example.invalid>",
        "from": recipient.email,
        "to": [message.reply_to],
        "subject": "Re: Synthetic RFQ",
    }
    assert signed_post(config, "existing-received", "email.received", inbound).status_code == 200
    response = OutreachResponse.objects.get(provider_email_id="existing-inbound")
    assert response.recipient_id is None and response.content_status == "metadata_only"
    assert recipient.qualification_state == "not_reviewed"

    monkeypatch.setattr(
        "apps.outreach.resend_webhooks._sent_details",
        lambda *_: {
            "id": provider_id,
            "message_id": provider_rfc_id,
            "from": message.from_address,
            "to": [message.to_address],
            "subject": message.subject,
            "text": message.body,
            "created_at": timezone.now().isoformat(),
        },
    )
    monkeypatch.setattr(
        "apps.outreach.resend_webhooks._received_details",
        lambda _, email_id: {
            "id": email_id,
            "headers": {"references" if reference_only else "in-reply-to": provider_rfc_id},
            "from": recipient.email,
            "to": [message.reply_to],
            "text": "We will provide a quote.",
        },
    )
    replay = signed_post(config, "existing-received", "email.received", inbound)
    assert replay.status_code == 200 and replay.data["created"] is False
    response.refresh_from_db()
    recipient.refresh_from_db()
    assert response.pk == OutreachResponse.objects.get(provider_email_id="existing-inbound").pk
    assert response.recipient_id == recipient.pk and response.message_id == message.pk
    assert response.content_status == "retrieved"
    assert recipient.current_status == "responded"
    assert recipient.response_state == "responded"
    assert recipient.qualification_state == "not_reviewed"
    assert OutreachProviderEmail.objects.get(provider_email_id=provider_id).message_id == message.pk
    assert (
        signed_post(config, "existing-received", "email.received", inbound).data["created"] is False
    )
    assert OutreachResponse.objects.count() == 1
    assert ResendWebhookEvent.objects.count() == 2
    assert recipient.status_events.filter(new_status="responded").count() == 1
    assert project.pk


def test_identical_sent_content_without_unique_attempt_window_stays_unassigned(setup, user):
    project, recipient, message = fixture_outreach(setup, user)
    duplicate = OutreachMessage.objects.create(
        recipient=recipient,
        sequence=2,
        kind=message.kind,
        from_name=message.from_name,
        from_address=message.from_address,
        reply_to=message.reply_to,
        to_address=message.to_address,
        subject=message.subject,
        body=message.body,
        created_by=user,
    )
    OutreachDeliveryAttempt.objects.create(
        message=duplicate,
        sequence=1,
        provider_key="smtp",
        idempotency_key=_message_key(duplicate),
        status="succeeded",
        completed_at=timezone.now(),
    )
    details = {
        "message_id": "<provider@email.amazonses.com>",
        "from": message.from_address,
        "to": [message.to_address],
        "subject": message.subject,
        "text": message.body,
        "created_at": timezone.now().isoformat(),
    }
    assert _exact_sent_message(project.organization, details, details["message_id"]) is None
    details.pop("created_at")
    assert _exact_sent_message(project.organization, details, details["message_id"]) is None


def test_manual_response_and_qualification_are_append_only_and_authorized(setup, user, membership):
    project, recipient, _ = fixture_outreach(setup, user)
    first = record_manual_response(
        recipient=recipient, actor=user, outcome="responded", channel="phone", note="Will quote."
    )
    second = record_manual_response(
        recipient=recipient,
        actor=user,
        outcome="declined",
        channel="email",
        note="Capacity unavailable.",
    )
    assert [first.pk, second.pk] == list(OutreachResponse.objects.values_list("id", flat=True))
    recipient.refresh_from_db()
    assert recipient.response_state == "declined"
    with pytest.raises(ValidationError):
        decide_qualification(recipient=recipient, actor=user, state="not_qualified")
    decision = decide_qualification(
        recipient=recipient, actor=user, state="not_qualified", note="Trade capacity unavailable."
    )
    assert OutreachQualificationDecision.objects.get(pk=decision.pk).note
    membership.role = Membership.Role.VIEWER
    membership.save()
    with pytest.raises(PermissionDenied):
        record_manual_response(
            recipient=recipient, actor=user, outcome="responded", channel="phone", note="No"
        )
    with pytest.raises(PermissionDenied):
        decide_qualification(recipient=recipient, actor=user, state="qualified")
    client = APIClient()
    client.force_authenticate(user)
    url = reverse(
        "outreach-recipient-response",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk,
            "recipient_pk": recipient.pk,
        },
    )
    assert (
        client.post(url, {"outcome": "responded", "channel": "phone", "note": "No"}).status_code
        == 403
    )


def test_inbound_metadata_only_does_not_guess_assignment(setup, user, webhook_config, monkeypatch):
    config = webhook_config
    monkeypatch.setattr("apps.outreach.resend_webhooks._received_details", lambda *_: None)
    result = signed_post(
        config,
        "evt-metadata",
        "email.received",
        {
            "email_id": "inbound-meta",
            "from": "unknown@example.invalid",
            "to": ["reply@example.invalid"],
            "subject": "Quote",
        },
    )
    assert result.status_code == 200
    response = OutreachResponse.objects.get(provider_email_id="inbound-meta")
    assert response.content_status == "metadata_only" and response.recipient_id is None
    assert response.body_text == ""


def test_webhook_settings_encrypt_secret_and_deny_viewer_mutation(setup, user, membership):
    project = setup[0]
    membership.role = Membership.Role.ADMIN
    membership.save()
    with override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=KEY):
        config = save_webhook_configuration(
            organization=project.organization, actor=user, signing_secret=SECRET, enabled=True
        )
        assert SECRET not in config.encrypted_signing_secret
        client = APIClient()
        client.force_authenticate(user)
        url = reverse(
            "resend-webhook-settings", kwargs={"organization_slug": project.organization.slug}
        )
        result = client.get(url)
        assert result.status_code == 200
        assert result.data["enabled"] is True
        assert result.data["signing_secret_saved"] is True
        assert "encrypted_signing_secret" not in result.data
        assert SECRET not in str(result.data)
        membership.role = Membership.Role.VIEWER
        membership.save()
        assert client.put(url, {"signing_secret": "", "enabled": False}).status_code == 403


def test_manual_response_is_project_scoped(setup, user):
    project, recipient, _ = fixture_outreach(setup, user)
    client = APIClient()
    client.force_authenticate(user)
    other = reverse(
        "outreach-recipient-response",
        kwargs={
            "organization_slug": project.organization.slug,
            "project_pk": project.pk + 1000,
            "recipient_pk": recipient.pk,
        },
    )
    assert (
        client.post(
            other, {"outcome": "responded", "channel": "phone", "note": "Synthetic note"}
        ).status_code
        == 404
    )
    assert OutreachResponse.objects.count() == 0
