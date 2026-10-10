import base64

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import Membership
from apps.outreach.models import (
    OutreachSMTPConfiguration,
    ResendWebhookConfiguration,
    ResendWebhookEvent,
)
from apps.outreach.resend_webhooks import save_webhook_configuration
from apps.outreach.setup import save_sender_settings
from apps.outreach.smtp_setup import save_smtp_configuration

pytestmark = pytest.mark.django_db

KEY = Fernet.generate_key().decode()
SECRET = "whsec_" + base64.b64encode(b"resend-webhook-signing-key-value").decode()


def admin(membership):
    membership.role = Membership.Role.ADMIN
    membership.save(update_fields=("role",))


def endpoint(organization):
    return reverse(
        "resend-webhook-settings",
        kwargs={"organization_slug": organization.slug},
    )


@override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=KEY)
def test_resend_preset_uses_canonical_smtp_and_blank_password_preserves_secret(
    organization, user, membership
):
    admin(membership)
    first = save_smtp_configuration(
        organization=organization,
        actor=user,
        host="smtp.resend.com",
        port=587,
        username="resend",
        password="re_test_api_key",
        clear_password=False,
        security="starttls",
        timeout_seconds=20,
        enabled=True,
    )
    encrypted = first.encrypted_password
    second = save_smtp_configuration(
        organization=organization,
        actor=user,
        host="smtp.resend.com",
        port=587,
        username="resend",
        password="",
        clear_password=False,
        security="starttls",
        timeout_seconds=20,
        enabled=True,
    )
    assert OutreachSMTPConfiguration.objects.count() == 1
    assert second.encrypted_password == encrypted


@override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=KEY)
def test_webhook_health_is_safe_and_reports_last_verified_event(organization, user, membership):
    admin(membership)
    config = save_webhook_configuration(
        organization=organization,
        actor=user,
        signing_secret=SECRET,
        enabled=True,
    )
    ResendWebhookEvent.objects.create(
        configuration=config,
        organization=organization,
        webhook_id="verified-health-event",
        event_type="email.delivered",
        provider_email_id="provider-health-email",
        occurred_at=timezone.now(),
    )
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(endpoint(organization), HTTP_HOST="127.0.0.1:8000")
    assert response.status_code == 200
    assert response.data["provider_events_received"] is True
    assert response.data["last_event_type"] == "email.delivered"
    assert response.data["integration_state"] == "tracking_active"
    assert response.data["endpoint_public_https"] is False
    assert response.data["endpoint_url"].startswith("http://127.0.0.1:8000/")
    serialized = str(response.data)
    assert SECRET not in serialized
    assert "encrypted_signing_secret" not in response.data


@override_settings(
    OUTREACH_CREDENTIAL_ENCRYPTION_KEY=KEY,
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    USE_X_FORWARDED_HOST=True,
    ALLOWED_HOSTS=["app.bbuildersltd.com"],
)
def test_webhook_endpoint_honors_forwarded_production_https(organization, user, membership):
    admin(membership)
    save_webhook_configuration(
        organization=organization,
        actor=user,
        signing_secret=SECRET,
        enabled=True,
    )
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(
        endpoint(organization),
        HTTP_HOST="internal:8000",
        HTTP_X_FORWARDED_HOST="app.bbuildersltd.com",
        HTTP_X_FORWARDED_PROTO="https",
    )
    assert response.status_code == 200
    assert response.data["endpoint_url"].startswith(
        "https://app.bbuildersltd.com/api/v1/webhooks/resend/"
    )
    assert response.data["endpoint_public_https"] is True


@override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=KEY)
def test_same_sender_and_smtp_configuration_power_integration_readiness(
    organization, user, membership
):
    admin(membership)
    save_smtp_configuration(
        organization=organization,
        actor=user,
        host="smtp.resend.com",
        port=587,
        username="resend",
        password="re_shared_key",
        clear_password=False,
        security="starttls",
        timeout_seconds=20,
        enabled=True,
    )
    save_sender_settings(
        organization=organization,
        actor=user,
        display_name="BB Builders",
        from_address="outreach@example.com",
        reply_to="replies@example.com",
        enabled=True,
    )
    ResendWebhookConfiguration.objects.create(organization=organization, updated_by=user)
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(endpoint(organization), HTTP_HOST="127.0.0.1:8000")
    assert response.data["smtp"]["state"] == "configured"
    assert response.data["sender_configured"] is True
    assert response.data["email_sending_ready"] is True
