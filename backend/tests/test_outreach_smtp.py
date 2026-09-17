"""SMTP setup tests use synthetic credentials and a mocked socket boundary only."""

import smtplib

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.models import Membership, Organization
from apps.outreach.credentials import decrypt_password
from apps.outreach.models import (
    BatchSendApproval,
    InvitationCampaign,
    OutreachDeliveryAttempt,
    OutreachMessage,
    OutreachSenderSettings,
    OutreachSMTPConfiguration,
)
from apps.outreach.smtp import provider_status
from apps.outreach.smtp_setup import run_connection_test, run_test_email, save_smtp_configuration
from apps.projects.models import AuditEvent

pytestmark = pytest.mark.django_db
TEST_KEY = Fernet.generate_key().decode("ascii")


@pytest.fixture
def admin(user, organization, membership):
    membership.role = Membership.Role.ADMIN
    membership.save()
    with override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=TEST_KEY):
        yield user, organization


def save_config(organization, actor, **overrides):
    values = dict(
        host="smtp.example.invalid",
        port=587,
        username="synthetic-user",
        password="synthetic-password",
        clear_password=False,
        security="starttls",
        timeout_seconds=20,
        enabled=True,
    )
    values.update(overrides)
    return save_smtp_configuration(organization=organization, actor=actor, **values)


class StubSMTP:
    sent = []
    connections = 0
    starttls_calls = 0
    fail_login = False

    def __init__(self, *args, **kwargs):
        type(self).connections += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def close(self):
        return None

    def starttls(self, **kwargs):
        type(self).starttls_calls += 1

    def login(self, username, password):
        assert username == "synthetic-user"
        assert password == "synthetic-password"
        if type(self).fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"private diagnostics")

    def send_message(self, email):
        type(self).sent.append(email)
        return {}


def test_encrypted_storage_update_clear_and_missing_key(admin):
    user, organization = admin
    with override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=""), pytest.raises(ValidationError):
        save_config(organization, user)
    assert OutreachSMTPConfiguration.objects.count() == 0
    config = save_config(organization, user)
    assert "synthetic-password" not in config.encrypted_password
    assert decrypt_password(config.encrypted_password) == "synthetic-password"
    with (
        override_settings(OUTREACH_CREDENTIAL_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii")),
        pytest.raises(ValidationError),
    ):
        decrypt_password(config.encrypted_password)
    original = config.encrypted_password
    config = save_config(organization, user, password="", host="other.example.invalid")
    assert config.encrypted_password == original
    config = save_config(organization, user, password="replacement", enabled=False)
    assert decrypt_password(config.encrypted_password) == "replacement"
    config = save_config(organization, user, password="", clear_password=True, enabled=False)
    assert config.encrypted_password == ""
    assert provider_status(organization)["state"] == "disabled"


def test_security_and_permissions(admin):
    user, organization = admin
    with pytest.raises(ValidationError):
        save_config(organization, user, security="none")
    config = save_config(organization, user, security="ssl", port=465)
    assert config.security == "ssl"
    estimator = get_user_model().objects.create_user(
        email="smtp-estimator@example.invalid", password="test"
    )
    Membership.objects.create(
        user=estimator, organization=organization, role=Membership.Role.ESTIMATOR_OPERATOR
    )
    viewer = get_user_model().objects.create_user(
        email="smtp-viewer@example.invalid", password="test"
    )
    Membership.objects.create(user=viewer, organization=organization, role=Membership.Role.VIEWER)
    for actor in (estimator, viewer):
        with pytest.raises(PermissionDenied):
            save_config(organization, actor)


def test_api_never_returns_secret_and_cross_org_isolation(admin):
    user, organization = admin
    save_config(organization, user)
    url = reverse("outreach-smtp-settings", kwargs={"organization_slug": organization.slug})
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(url)
    assert response.status_code == 200
    assert response.data["password_saved"] is True
    assert "password" not in response.data
    assert "encrypted_password" not in response.data
    assert "synthetic-password" not in str(response.data)
    other = Organization.objects.create(name="Other", slug="other-smtp-org")
    wrong = reverse("outreach-smtp-settings", kwargs={"organization_slug": other.slug})
    assert client.get(wrong).status_code == 403
    assert client.put(wrong, {}).status_code == 403
    viewer = get_user_model().objects.create_user(
        email="safe-viewer@example.invalid", password="test"
    )
    Membership.objects.create(user=viewer, organization=organization, role=Membership.Role.VIEWER)
    client.force_authenticate(viewer)
    safe = client.get(url)
    assert safe.status_code == 200
    assert set(safe.data) == {"provider"}
    assert client.put(url, {}).status_code == 403
    assert (
        client.post(
            reverse(
                "outreach-smtp-test-connection", kwargs={"organization_slug": organization.slug}
            ),
            {},
        ).status_code
        == 403
    )


def test_connection_only_and_test_email_are_explicit_and_audited(admin, monkeypatch):
    user, organization = admin
    save_config(organization, user)
    OutreachSenderSettings.objects.create(
        organization=organization,
        display_name="BB Builders",
        from_address="from@example.invalid",
        reply_to="reply@example.invalid",
        updated_by=user,
    )
    StubSMTP.sent = []
    StubSMTP.connections = 0
    StubSMTP.starttls_calls = 0
    StubSMTP.fail_login = False
    monkeypatch.setattr(smtplib, "SMTP", StubSMTP)
    assert provider_status(organization)["state"] == "configured"
    assert StubSMTP.connections == 0
    connected = run_connection_test(organization=organization, actor=user)
    assert connected["success"] is True
    assert StubSMTP.connections == 1
    assert StubSMTP.starttls_calls == 1
    assert StubSMTP.sent == []
    result = run_test_email(
        organization=organization, actor=user, recipient_email="controlled@example.invalid"
    )
    assert result["success"] is True
    assert len(StubSMTP.sent) == 1
    assert StubSMTP.sent[0]["Subject"] == "BB Builders Email Delivery Test"
    assert StubSMTP.sent[0]["To"] == "controlled@example.invalid"
    assert InvitationCampaign.objects.count() == 0
    assert OutreachMessage.objects.count() == 0
    assert BatchSendApproval.objects.count() == 0
    assert OutreachDeliveryAttempt.objects.count() == 0
    assert AuditEvent.objects.filter(action_code="smtp_connection.tested").count() == 1
    assert AuditEvent.objects.filter(action_code="smtp_test_email.sent").count() == 1
    assert "synthetic-password" not in str(
        list(AuditEvent.objects.values_list("metadata", flat=True))
    )
    StubSMTP.fail_login = True
    failed = run_connection_test(organization=organization, actor=user)
    assert failed["success"] is False
    assert failed["code"] == "smtp_authentication"
    assert "private diagnostics" not in failed["message"]
    # Diagnostic failure is retained, but it is not a permanent send gate.
    assert provider_status(organization)["state"] == "configured"
    config = OutreachSMTPConfiguration.objects.get(organization=organization)
    assert config.last_test_status == "smtp_authentication"
    # A failed diagnostic test does not permanently block an otherwise valid test send.
    StubSMTP.fail_login = False
    assert (
        run_test_email(
            organization=organization, actor=user, recipient_email="controlled@example.invalid"
        )["success"]
        is True
    )
    StubSMTP.fail_login = True
    failure = run_test_email(
        organization=organization, actor=user, recipient_email="controlled@example.invalid"
    )
    assert failure["success"] is False
    assert failure["code"] == "smtp_authentication"
    assert AuditEvent.objects.filter(action_code="smtp_test_email.failed").count() == 1
    assert len(StubSMTP.sent) == 2
