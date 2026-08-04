import pytest
from pydantic import ValidationError

from app.core.config import Settings

JWT_SECRET = "test-only-jwt-secret-key-at-least-32-characters"


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key=JWT_SECRET,
        **overrides,
    )


def test_transcript_simulation_is_disabled_by_default() -> None:
    config = _settings()

    assert config.transcript_simulation_enabled is False


@pytest.mark.parametrize("environment", ["development", "testing"])
def test_transcript_simulation_can_be_enabled_outside_production(
    environment: str,
) -> None:
    config = _settings(
        environment=environment,
        transcript_simulation_enabled=True,
    )

    assert config.transcript_simulation_enabled is True


def test_transcript_simulation_cannot_be_enabled_in_production() -> None:
    with pytest.raises(
        ValidationError,
        match="Transcript simulation cannot be enabled in production",
    ):
        _settings(
            environment="production",
            transcript_simulation_enabled=True,
        )
