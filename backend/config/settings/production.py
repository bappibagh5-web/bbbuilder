import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

if DEBUG:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_DEBUG must be false in production.")

if SECRET_KEY.startswith("unsafe-"):  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must not use a development value.")

if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS is required in production.")

if not CORS_ALLOWED_ORIGINS or "*" in CORS_ALLOWED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS must contain exact production origins.")

if not CSRF_TRUSTED_ORIGINS or "*" in CSRF_TRUSTED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured("CSRF_TRUSTED_ORIGINS must contain exact production origins.")

required_environment = (
    "FRONTEND_ORIGIN",
    "S3_ACCESS_KEY",
    "S3_BUCKET",
    "S3_ENDPOINT_URL",
    "S3_SECRET_KEY",
)
missing_environment = [name for name in required_environment if not os.environ.get(name)]
if missing_environment:
    missing = ", ".join(missing_environment)
    raise ImproperlyConfigured(f"Missing required production environment variables: {missing}")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
