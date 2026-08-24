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
    assert settings.source_scan_lease_seconds > settings.celery_task_time_limit_seconds
    assert settings.candidate_lease_seconds > settings.celery_task_time_limit_seconds
    assert 0.75 <= settings.candidate_draft_duplicate_threshold <= 0.99


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


def test_source_scan_lease_must_exceed_worker_hard_timeout() -> None:
    values = _production_values()
    values["celery_task_time_limit_seconds"] = 180
    values["source_scan_lease_seconds"] = 180
    with pytest.raises(ValidationError, match="SOURCE_SCAN_LEASE_SECONDS"):
        Settings(**values)


def test_source_scan_minimum_interval_rejects_hot_loop() -> None:
    values = _production_values()
    values["source_scan_min_interval_seconds"] = 30
    with pytest.raises(ValidationError, match="SOURCE_SCAN_MIN_INTERVAL_SECONDS"):
        Settings(**values)


def test_candidate_lease_must_exceed_worker_hard_timeout() -> None:
    values = _production_values()
    values["celery_task_time_limit_seconds"] = 180
    values["candidate_lease_seconds"] = 180
    with pytest.raises(ValidationError, match="CANDIDATE_LEASE_SECONDS"):
        Settings(**values)


def test_candidate_duplicate_threshold_rejects_unsafe_low_value() -> None:
    values = _production_values()
    values["candidate_draft_duplicate_threshold"] = 0.6
    with pytest.raises(ValidationError, match="CANDIDATE_DRAFT_DUPLICATE_THRESHOLD"):
        Settings(**values)


def test_candidate_attempt_limit_is_bounded() -> None:
    values = _production_values()
    values["candidate_max_attempts"] = 0
    with pytest.raises(ValidationError, match="CANDIDATE_MAX_ATTEMPTS"):
        Settings(**values)
