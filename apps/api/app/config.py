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

    # Identity: development header, trusted enterprise gateway, or direct OIDC JWT.
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

    # Observability.
    log_level: str = "INFO"
    request_id_header: str = "X-Request-ID"
    correlation_id_header: str = "X-Correlation-ID"

    # HTTP/application security. The ingress must still enforce independent limits.
    max_request_body_bytes: int = 2_000_000
    security_headers_enabled: bool = True
    hsts_max_age_seconds: int = 31_536_000
    authenticated_rate_limit_per_minute: int = 300

    # Database-side tenant isolation.
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
            if "127.0.0.1" in self.database_url or "localhost" in self.database_url:
                raise ValueError("production DATABASE_URL must point to an explicit production database service")
            if "127.0.0.1" in self.redis_url or "localhost" in self.redis_url:
                raise ValueError("production REDIS_URL must point to an explicit production Redis service")
            if self.dev_user_email != "admin@zhituo.local":
                raise ValueError("DEV_USER_EMAIL is a development-only setting")
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
