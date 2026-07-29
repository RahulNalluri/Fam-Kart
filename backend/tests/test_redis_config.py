import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_redis_url_has_local_default() -> None:
    config = Settings()

    assert str(config.redis_url) == "redis://localhost:6379/0"


def test_redis_url_can_be_overridden_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/2")

    config = Settings()

    assert str(config.redis_url) == "redis://redis:6379/2"


def test_redis_url_rejects_unsupported_schemes(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "http://localhost:6379/0")

    with pytest.raises(ValidationError):
        Settings()
