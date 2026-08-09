from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "广金大师兄"
    app_subtitle: str = "读懂校园信息，帮你把事情办明白。"
    environment: str = "development"
    api_prefix: str = "/api"
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'gduf_web.db').as_posix()}"
    jwt_secret: str = "development-jwt-secret-change-before-production"
    refresh_token_secret: str = "development-refresh-secret-change-before-production"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking_enabled: bool = True
    deepseek_reasoning_effort: str = "high"
    llm_connect_timeout_seconds: float = 10.0
    llm_read_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    llm_history_messages: int = 20
    amap_webservice_key: str = ""
    amap_security_code: str = ""
    amap_api_base_url: str = "https://restapi.amap.com"
    amap_request_timeout_seconds: float = 12.0
    admin_bootstrap_email: str = ""
    admin_bootstrap_password: str = ""
    data_root: Path = PROJECT_ROOT / "data"
    max_upload_bytes: int = 5 * 1024 * 1024
    auto_create_schema: bool = True
    seed_demo_data: bool = True

    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return str(value or "development").strip().lower()

    @field_validator("cookie_samesite")
    @classmethod
    def validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict or none")
        return normalized

    @field_validator("deepseek_reasoning_effort")
    @classmethod
    def validate_reasoning_effort(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"high", "max"}:
            raise ValueError("DEEPSEEK_REASONING_EFFORT must be high or max")
        return normalized

    @model_validator(mode="after")
    def enforce_production_secrets(self) -> "Settings":
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        if self.environment == "production":
            weak = (
                self.jwt_secret.startswith("development-")
                or self.refresh_token_secret.startswith("development-")
                or len(self.jwt_secret) < 32
                or len(self.refresh_token_secret) < 32
            )
            if weak:
                raise ValueError("Production requires strong JWT_SECRET and REFRESH_TOKEN_SECRET")
            if not self.cookie_secure:
                raise ValueError("Production requires COOKIE_SECURE=true")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip().rstrip("/") for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
