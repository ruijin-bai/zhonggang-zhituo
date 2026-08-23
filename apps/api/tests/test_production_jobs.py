import pytest
from pydantic import ValidationError

from app.config import Settings


def _production_settings(**overrides):
    values = {
        "_env_file": None,
        "app_env": "production",
        "demo_mode": False,
        "allow_demo_fallback": False,
        "data_backend": "database",
        "job_mode": "queue",
        "database_url": "postgresql+psycopg://user:pass@db.internal:5432/zhituo",
        "redis_url": "redis://redis.internal:6379/0",
        "auth_mode": "trusted_proxy",
        "auth_gateway_secret": "production-gateway-secret-at-least-32-characters",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_rejects_inline_jobs() -> None:
    with pytest.raises(ValidationError):
        _production_settings(job_mode="inline")


def test_production_accepts_explicit_queue_services() -> None:
    settings = _production_settings()
    assert settings.job_mode == "queue"
    assert settings.data_backend == "database"
    assert settings.auth_mode == "trusted_proxy"
