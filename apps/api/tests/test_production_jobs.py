import pytest
from pydantic import ValidationError

from app.config import Settings


PROXY_SECRET = "zhituo-ci-proxy-secret-32-characters-minimum"


def test_production_rejects_inline_jobs() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            demo_mode=False,
            allow_demo_fallback=False,
            data_backend="database",
            job_mode="inline",
            auth_mode="trusted_proxy",
            auth_proxy_secret=PROXY_SECRET,
            database_url="postgresql+psycopg://user:pass@db.internal:5432/zhituo",
            redis_url="redis://redis.internal:6379/0",
        )


def test_production_accepts_explicit_queue_services() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        demo_mode=False,
        allow_demo_fallback=False,
        data_backend="database",
        job_mode="queue",
        auth_mode="trusted_proxy",
        auth_proxy_secret=PROXY_SECRET,
        database_url="postgresql+psycopg://user:pass@db.internal:5432/zhituo",
        redis_url="redis://redis.internal:6379/0",
    )
    assert settings.job_mode == "queue"
    assert settings.data_backend == "database"
    assert settings.auth_mode == "trusted_proxy"
