import os

import pytest
from pydantic import ValidationError

from app.config import Settings


def _production_settings(**overrides):
    values = {
        "app_env": "production",
        "data_backend": "database",
        "database_url": "postgresql+psycopg://user:pass@db.internal:5432/zhituo",
        "cors_origins": "https://zhituo.example.com",
        "demo_mode": False,
        "allow_demo_fallback": False,
        "dev_user_email": "admin@zhituo.local",
        "auth_mode": "trusted_proxy",
        "auth_proxy_secret": "x" * 32,
        "job_mode": "queue",
        "redis_url": "redis://redis.internal:6379/0",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_requires_trusted_proxy_authentication() -> None:
    with pytest.raises(ValidationError):
        _production_settings(auth_mode="development_header")


def test_production_rejects_short_gateway_secret() -> None:
    with pytest.raises(ValidationError):
        _production_settings(auth_proxy_secret="too-short")


def test_production_accepts_safe_runtime_baseline() -> None:
    settings = _production_settings()
    assert settings.auth_mode == "trusted_proxy"
    assert settings.job_mode == "queue"
    assert settings.data_backend == "database"
