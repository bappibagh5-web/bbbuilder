import json

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError
from django.test import Client

pytestmark = pytest.mark.django_db


def test_email_is_unique_and_case_insensitive_for_authentication():
    user_model = get_user_model()
    user_model.objects.create_user(email="Estimator@Example.com", password="valid-pass")

    assert authenticate(email="ESTIMATOR@example.com", password="valid-pass") is not None
    with pytest.raises(IntegrityError):
        user_model.objects.create_user(email="estimator@example.com", password="other-pass")


def test_inactive_user_cannot_authenticate():
    user = get_user_model().objects.create_user(
        email="inactive@example.com", password="valid-pass", is_active=False
    )

    assert authenticate(email=user.email, password="valid-pass") is None


def test_inactive_user_cannot_login():
    get_user_model().objects.create_user(
        email="inactive-login@example.com", password="valid-pass", is_active=False
    )
    client, token = csrf_client()
    response = client.post(
        "/api/v1/auth/login/",
        data=json.dumps({"email": "inactive-login@example.com", "password": "valid-pass"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 401


def csrf_client():
    client = Client(enforce_csrf_checks=True)
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 200
    assert "csrftoken" in response.cookies
    assert response.cookies["csrftoken"]["httponly"] == ""
    token = response.json()["csrfToken"]
    assert token
    return client, token


def test_login_requires_csrf_and_rejects_invalid_credentials():
    get_user_model().objects.create_user(email="user@example.com", password="valid-pass")
    client = Client(enforce_csrf_checks=True)

    assert client.post("/api/v1/auth/login/", data={}).status_code == 403

    client, token = csrf_client()
    response = client.post(
        "/api/v1/auth/login/",
        data=json.dumps({"email": "user@example.com", "password": "wrong"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 401


def test_session_login_me_and_logout(organization, membership, user):
    client, token = csrf_client()
    response = client.post(
        "/api/v1/auth/login/",
        data=json.dumps({"email": user.email, "password": "valid-pass"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    assert response.json()["user"]["memberships"][0]["organization"]["slug"] == organization.slug
    assert client.get("/api/v1/auth/me/").status_code == 200

    token = client.cookies["csrftoken"].value
    assert client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code == 200
    assert client.get("/api/v1/auth/me/").status_code == 401


def test_logout_requires_csrf(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post("/api/v1/auth/logout/").status_code == 403


def test_me_rejects_unauthenticated_user():
    assert Client().get("/api/v1/auth/me/").status_code == 401
