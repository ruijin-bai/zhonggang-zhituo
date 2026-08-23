import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_inline_jobs() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            demo_mode=False,
            allow_demo_fallback=False,
            data_backend="database",
            job_mode="inline",
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
        database_url="postgresql+psycopg://user:pass@db.internal:5432/zhituo",
        redis_url="redis://redis.internal:6379/0",
    )
    assert settings.job_mode == "queue"
    assert settings.data_backend == "database"
