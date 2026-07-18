from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
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

    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: JwtAlgorithm = "HS256"
    jwt_issuer: str = "familykart-api"
    jwt_audience: str = "familykart-mobile"
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_days: int = Field(default=30, gt=0)
    household_invitation_expire_hours: int = Field(default=24, gt=0, le=168)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
