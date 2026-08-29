import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def run_django_with_environment(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )


def production_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.production",
            "DJANGO_SECRET_KEY": "production-test-key-that-is-not-a-local-default",
            "DJANGO_DEBUG": "false",
            "DJANGO_ALLOWED_HOSTS": "api.example.test",
            "DATABASE_URL": "postgresql://user:password@localhost:5432/database",
            "REDIS_URL": "redis://localhost:6379/0",
            "FRONTEND_ORIGIN": "https://app.example.test",
            "S3_ENDPOINT_URL": "https://storage.example.test",
            "S3_BUCKET": "production-test-bucket",
            "S3_ACCESS_KEY": "production-test-access-key",
            "S3_SECRET_KEY": "production-test-secret-key",
        }
    )
    return environment


def test_backend_test_configuration_loads():
    assert settings.ROOT_URLCONF == "config.urls"
    assert settings.CELERY_TASK_ALWAYS_EAGER is True
    assert "127.0.0.1" in settings.ALLOWED_HOSTS


def test_production_configuration_loads_with_explicit_secure_values():
    result = run_django_with_environment(production_environment())

    assert result.returncode == 0, result.stderr


def test_production_configuration_rejects_debug():
    environment = production_environment()
    environment["DJANGO_DEBUG"] = "true"

    result = run_django_with_environment(environment)

    assert result.returncode != 0
    assert "DJANGO_DEBUG must be false in production" in result.stderr


def test_production_configuration_requires_secret_key():
    environment = production_environment()
    environment.pop("DJANGO_SECRET_KEY")

    result = run_django_with_environment(environment)

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr
