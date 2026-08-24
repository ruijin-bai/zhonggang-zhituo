from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "test", "production"] = "development"
    data_backend: Literal["auto", "database", "json"] = "auto"
    database_url: str = "postgresql+psycopg://zhituo:zhituo@127.0.0.1:5432/zhituo"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    demo_mode: bool = True
    allow_demo_fallback: bool = True
    dev_user_email: str = "admin@zhituo.local"

    auth_mode: Literal["development_header", "trusted_proxy", "oidc"] = "development_header"
    auth_proxy_secret: str | None = None
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_email_claim: str = "email"

    job_mode: Literal["inline", "queue"] = "inline"
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_result_expires_seconds: int = 86400
    celery_task_soft_time_limit_seconds: int = 90
    celery_task_time_limit_seconds: int = 120
    idempotency_ttl_seconds: int = 86400
    job_stuck_after_seconds: int = 300

    document_store_backend: Literal["local", "s3"] = "local"
    document_store_local_path: str = "./data/objects"
    document_store_s3_bucket: str = ""
    document_store_s3_region: str = "us-east-1"
    document_store_s3_endpoint_url: str = ""
    document_store_s3_force_path_style: bool = False
    document_store_s3_sse: Literal["", "AES256", "aws:kms"] = ""
    document_store_s3_kms_key_id: str = ""

    # Scheduled source monitoring. Beat only dispatches due work; each subscription scan runs
    # as its own worker task and owns a durable lease/health record in PostgreSQL.
    source_scan_dispatch_interval_seconds: int = 60
    source_scan_min_interval_seconds: int = 300
    source_scan_lease_seconds: int = 300
    source_scan_max_backoff_seconds: int = 86_400
    source_scan_auto_pause_failures: int = 8
    source_scan_dispatch_batch_size: int = 50

    # Candidate processing is a second durable queue after document archival. Source ingestion
    # never depends on Redis availability; Beat later claims pending candidate rows and workers
    # turn normalized documents into human-reviewable OpportunityDraft records.
    candidate_dispatch_interval_seconds: int = 30
    candidate_lease_seconds: int = 300
    candidate_max_attempts: int = 5
    candidate_max_backoff_seconds: int = 3_600
    candidate_dispatch_batch_size: int = 50
    candidate_draft_duplicate_threshold: float = 0.88

    # Pursuit reminders are durable in-product facts. External mail/Teams/WeCom delivery can be
    # attached later without changing the reminder or escalation semantics.
    pursuit_reminder_reconcile_interval_seconds: int = 300
    pursuit_due_soon_hours: int = 48
    pursuit_overdue_escalation_hours: int = 72
    pursuit_blocked_escalation_hours: int = 24
    pursuit_review_escalation_hours: int = 48

    log_level: str = "INFO"
    request_id_header: str = "X-Request-ID"
    correlation_id_header: str = "X-Correlation-ID"
    metrics_enabled: bool = False
    metrics_token: str | None = None

    max_request_body_bytes: int = 2_000_000
    security_headers_enabled: bool = True
    hsts_max_age_seconds: int = 31_536_000
    authenticated_rate_limit_per_minute: int = 300

    database_rls_enabled: bool = True

    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str | None = None
    ai_model_extraction: str = ""
    ai_model_analysis: str = ""
    ai_timeout_seconds: float = 45.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @staticmethod
    def _is_https_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.netloc)

    @model_validator(mode="after")
    def production_guardrails(self):
        if self.idempotency_ttl_seconds < 60:
            raise ValueError("IDEMPOTENCY_TTL_SECONDS must be at least 60")
        if self.max_request_body_bytes < 64_000 or self.max_request_body_bytes > 20_000_000:
            raise ValueError("MAX_REQUEST_BODY_BYTES must be between 64000 and 20000000")
        if self.authenticated_rate_limit_per_minute < 0:
            raise ValueError("AUTHENTICATED_RATE_LIMIT_PER_MINUTE cannot be negative")
        if self.job_stuck_after_seconds <= self.celery_task_time_limit_seconds:
            raise ValueError("JOB_STUCK_AFTER_SECONDS must exceed CELERY_TASK_TIME_LIMIT_SECONDS")
        if self.document_store_s3_sse == "aws:kms" and not self.document_store_s3_kms_key_id:
            raise ValueError("aws:kms document storage requires DOCUMENT_STORE_S3_KMS_KEY_ID")
        if self.source_scan_dispatch_interval_seconds < 10:
            raise ValueError("SOURCE_SCAN_DISPATCH_INTERVAL_SECONDS must be at least 10")
        if self.source_scan_min_interval_seconds < 60:
            raise ValueError("SOURCE_SCAN_MIN_INTERVAL_SECONDS must be at least 60")
        if self.source_scan_lease_seconds <= self.celery_task_time_limit_seconds:
            raise ValueError("SOURCE_SCAN_LEASE_SECONDS must exceed CELERY_TASK_TIME_LIMIT_SECONDS")
        if self.source_scan_max_backoff_seconds < self.source_scan_min_interval_seconds:
            raise ValueError("SOURCE_SCAN_MAX_BACKOFF_SECONDS must not be below minimum interval")
        if self.source_scan_auto_pause_failures < 1:
            raise ValueError("SOURCE_SCAN_AUTO_PAUSE_FAILURES must be at least 1")
        if not 1 <= self.source_scan_dispatch_batch_size <= 500:
            raise ValueError("SOURCE_SCAN_DISPATCH_BATCH_SIZE must be between 1 and 500")
        if self.candidate_dispatch_interval_seconds < 10:
            raise ValueError("CANDIDATE_DISPATCH_INTERVAL_SECONDS must be at least 10")
        if self.candidate_lease_seconds <= self.celery_task_time_limit_seconds:
            raise ValueError("CANDIDATE_LEASE_SECONDS must exceed CELERY_TASK_TIME_LIMIT_SECONDS")
        if not 1 <= self.candidate_max_attempts <= 20:
            raise ValueError("CANDIDATE_MAX_ATTEMPTS must be between 1 and 20")
        if self.candidate_max_backoff_seconds < self.candidate_dispatch_interval_seconds:
            raise ValueError("CANDIDATE_MAX_BACKOFF_SECONDS must not be below dispatch interval")
        if not 1 <= self.candidate_dispatch_batch_size <= 500:
            raise ValueError("CANDIDATE_DISPATCH_BATCH_SIZE must be between 1 and 500")
        if not 0.75 <= self.candidate_draft_duplicate_threshold <= 0.99:
            raise ValueError("CANDIDATE_DRAFT_DUPLICATE_THRESHOLD must be between 0.75 and 0.99")
        if self.pursuit_reminder_reconcile_interval_seconds < 30:
            raise ValueError("PURSUIT_REMINDER_RECONCILE_INTERVAL_SECONDS must be at least 30")
        if not 1 <= self.pursuit_due_soon_hours <= 720:
            raise ValueError("PURSUIT_DUE_SOON_HOURS must be between 1 and 720")
        if not 1 <= self.pursuit_overdue_escalation_hours <= 2160:
            raise ValueError("PURSUIT_OVERDUE_ESCALATION_HOURS must be between 1 and 2160")
        if not 1 <= self.pursuit_blocked_escalation_hours <= 2160:
            raise ValueError("PURSUIT_BLOCKED_ESCALATION_HOURS must be between 1 and 2160")
        if not 1 <= self.pursuit_review_escalation_hours <= 2160:
            raise ValueError("PURSUIT_REVIEW_ESCALATION_HOURS must be between 1 and 2160")

        if self.app_env == "production":
            if self.data_backend != "database":
                raise ValueError("production requires DATA_BACKEND=database")
            if self.demo_mode:
                raise ValueError("production requires DEMO_MODE=false")
            if self.allow_demo_fallback:
                raise ValueError("production requires ALLOW_DEMO_FALLBACK=false")
            if self.job_mode != "queue":
                raise ValueError("production requires JOB_MODE=queue")
            if self.auth_mode == "development_header":
                raise ValueError("production requires AUTH_MODE=trusted_proxy or oidc")
            if self.auth_mode == "trusted_proxy":
                if not self.auth_proxy_secret or len(self.auth_proxy_secret) < 32:
                    raise ValueError("trusted_proxy requires AUTH_PROXY_SECRET with at least 32 characters")
            if self.auth_mode == "oidc":
                if not self.oidc_issuer or not self._is_https_url(self.oidc_issuer):
                    raise ValueError("oidc production mode requires HTTPS OIDC_ISSUER")
                if not self.oidc_audience:
                    raise ValueError("oidc production mode requires OIDC_AUDIENCE")
                if not self.oidc_jwks_url or not self._is_https_url(self.oidc_jwks_url):
                    raise ValueError("oidc production mode requires HTTPS OIDC_JWKS_URL")
            if not self.database_rls_enabled:
                raise ValueError("production requires DATABASE_RLS_ENABLED=true")
            if self.authenticated_rate_limit_per_minute <= 0:
                raise ValueError("production requires AUTHENTICATED_RATE_LIMIT_PER_MINUTE > 0")
            if self.metrics_enabled and (not self.metrics_token or len(self.metrics_token) < 32):
                raise ValueError("production metrics require METRICS_TOKEN with at least 32 characters")
            if "127.0.0.1" in self.database_url or "localhost" in self.database_url:
                raise ValueError("production DATABASE_URL must point to an explicit production database service")
            if "127.0.0.1" in self.redis_url or "localhost" in self.redis_url:
                raise ValueError("production REDIS_URL must point to an explicit production Redis service")
            if self.dev_user_email != "admin@zhituo.local":
                raise ValueError("DEV_USER_EMAIL is a development-only setting")
            if self.document_store_backend != "s3":
                raise ValueError("production requires DOCUMENT_STORE_BACKEND=s3")
            if not self.document_store_s3_bucket:
                raise ValueError("production S3 document storage requires DOCUMENT_STORE_S3_BUCKET")
            if self.document_store_s3_endpoint_url and not self._is_https_url(
                self.document_store_s3_endpoint_url
            ):
                raise ValueError("production custom S3 endpoint must use HTTPS")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def ai_extraction_enabled(self) -> bool:
        return bool(self.ai_api_key and self.ai_model_extraction)

    @property
    def ai_analysis_enabled(self) -> bool:
        return bool(self.ai_api_key and self.ai_model_analysis)

    @property
    def ai_enabled(self) -> bool:
        return self.ai_extraction_enabled or self.ai_analysis_enabled


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
