import pytest
from pydantic import ValidationError

from app.config import Settings


PROXY_SECRET = "zhituo-ci-proxy-secret-32-characters-minimum"


def _production_values() -> dict:
    return {
        "_env_file": None,
        "app_env": "production",
        "demo_mode": False,
        "allow_demo_fallback": False,
        "data_backend": "database",
        "job_mode": "queue",
        "auth_mode": "trusted_proxy",
        "auth_proxy_secret": PROXY_SECRET,
        "database_url": "postgresql+psycopg://user:pass@db.internal:5432/zhituo",
        "redis_url": "redis://redis.internal:6379/0",
        "document_store_backend": "s3",
        "document_store_s3_bucket": "zhituo-production-documents",
    }


def test_production_rejects_inline_jobs() -> None:
    values = _production_values()
    values["job_mode"] = "inline"
    with pytest.raises(ValidationError):
        Settings(**values)


def test_production_accepts_explicit_queue_services() -> None:
    settings = Settings(**_production_values())
    assert settings.job_mode == "queue"
    assert settings.data_backend == "database"
    assert settings.auth_mode == "trusted_proxy"
    assert settings.document_store_backend == "s3"


def test_production_rejects_local_document_storage() -> None:
    values = _production_values()
    values["document_store_backend"] = "local"
    with pytest.raises(ValidationError, match="DOCUMENT_STORE_BACKEND=s3"):
        Settings(**values)


def test_production_rejects_insecure_custom_s3_endpoint() -> None:
    values = _production_values()
    values["document_store_s3_endpoint_url"] = "http://object-store.internal:9000"
    with pytest.raises(ValidationError, match="custom S3 endpoint must use HTTPS"):
        Settings(**values)
