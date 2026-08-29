import os
from pathlib import Path

import environ

BACKEND_DIR = Path(__file__).resolve().parents[2]
environ.Env.read_env(BACKEND_DIR / ".env")

os.environ.setdefault("DJANGO_SECRET_KEY", "unsafe-local-development-key-change-me")
os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://bb_builders:bb_builders@localhost:5432/bb_builders",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_BUCKET", "bb-builders-local")
os.environ.setdefault("S3_ACCESS_KEY", "bb-builders-local")
os.environ.setdefault("S3_SECRET_KEY", "bb-builders-local")
os.environ.setdefault("S3_REGION", "us-east-1")
os.environ.setdefault("FRONTEND_ORIGIN", "http://127.0.0.1:3000")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:3000")
os.environ.setdefault("CSRF_TRUSTED_ORIGINS", "http://127.0.0.1:3000")

from .base import *  # noqa: E402,F403
