from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "test", "production"] = "development"
    data_backend: Literal["auto", "database", "json"] = "auto"
    database_url: str = "postgresql+psycopg://zhituo:zhituo@127.0.0.1:5432/zhituo"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    demo_mode: bool = True
    allow_demo_fallback: bool = True

    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str | None = None
    ai_model_extraction: str = ""
    ai_model_analysis: str = ""
    ai_timeout_seconds: float = 45.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def production_guardrails(self):
        if self.app_env == "production":
            if self.data_backend != "database":
                raise ValueError("production requires DATA_BACKEND=database")
            if self.demo_mode:
                raise ValueError("production requires DEMO_MODE=false")
            if self.allow_demo_fallback:
                raise ValueError("production requires ALLOW_DEMO_FALLBACK=false")
            if "127.0.0.1" in self.database_url or "localhost" in self.database_url:
                raise ValueError("production DATABASE_URL must point to an explicit production database service")
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
