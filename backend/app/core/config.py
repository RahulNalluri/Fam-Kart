from functools import lru_cache
from typing import Literal, Self

from pydantic import (
    Field,
    HttpUrl,
    RedisDsn,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "testing", "production"]
JwtAlgorithm = Literal["HS256"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FamilyKart AI API"
    service_name: str = "familykart-api"
    version: str = "0.1.0"
    environment: Environment = "development"
    debug: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    database_url: str = (
        "postgresql+psycopg://familykart:familykart@localhost:5432/familykart"
    )
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    redis_channel_prefix: str = Field(
        default="familykart",
        pattern=r"^[a-z][a-z0-9-]{0,31}$",
    )
    realtime_reconnect_initial_delay_seconds: float = Field(
        default=0.5,
        gt=0,
        le=60,
    )
    realtime_reconnect_max_delay_seconds: float = Field(
        default=30,
        gt=0,
        le=300,
    )

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: HttpUrl = HttpUrl("https://openrouter.ai/api/v1")
    openrouter_model: str = Field(default="openrouter/free", max_length=200)
    openrouter_timeout_seconds: float = Field(default=30, gt=0, le=120)
    openrouter_max_output_tokens: int = Field(default=512, ge=64, le=4096)
    ai_max_input_characters: int = Field(default=2000, ge=1, le=10000)
    openrouter_http_referer: HttpUrl | None = None
    openrouter_app_title: str = Field(default="FamilyKart AI", max_length=100)
    transcript_simulation_enabled: bool = False

    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: JwtAlgorithm = "HS256"
    jwt_issuer: str = "familykart-api"
    jwt_audience: str = "familykart-mobile"
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_days: int = Field(default=30, gt=0)
    household_invitation_expire_hours: int = Field(default=24, gt=0, le=168)

    @field_validator("openrouter_api_key", mode="before")
    @classmethod
    def normalize_optional_openrouter_key(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("openrouter_http_referer", mode="before")
    @classmethod
    def normalize_optional_openrouter_referer(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("openrouter_base_url")
    @classmethod
    def require_secure_openrouter_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("OpenRouter base URL must use HTTPS.")
        if value.query is not None or value.fragment is not None:
            raise ValueError("OpenRouter base URL cannot include a query or fragment.")
        return value

    @field_validator("openrouter_model", "openrouter_app_title")
    @classmethod
    def normalize_nonblank_openrouter_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("OpenRouter text settings cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def prevent_production_transcript_simulation(self) -> Self:
        if self.environment == "production" and self.transcript_simulation_enabled:
            raise ValueError("Transcript simulation cannot be enabled in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
