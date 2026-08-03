import pytest
from pydantic import ValidationError

from app.core.config import Settings

JWT_SECRET = "test-only-jwt-secret-key-at-least-32-characters"


def build_settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key=JWT_SECRET,
        **overrides,
    )


def test_ai_configuration_has_safe_development_defaults() -> None:
    config = build_settings()

    assert config.openrouter_api_key is None
    assert str(config.openrouter_base_url) == "https://openrouter.ai/api/v1"
    assert config.openrouter_model == "openrouter/free"
    assert config.openrouter_timeout_seconds == 30
    assert config.openrouter_max_output_tokens == 512
    assert config.ai_max_input_characters == 2000
    assert config.openrouter_http_referer is None
    assert config.openrouter_app_title == "FamilyKart AI"


def test_ai_configuration_can_be_overridden_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-secret")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://ai.example.com/v1")
    monkeypatch.setenv("OPENROUTER_MODEL", "provider/grocery-model:free")
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OPENROUTER_MAX_OUTPUT_TOKENS", "768")
    monkeypatch.setenv("AI_MAX_INPUT_CHARACTERS", "1500")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://familykart.example")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", " FamilyKart Test ")

    config = build_settings()

    assert config.openrouter_api_key is not None
    assert config.openrouter_api_key.get_secret_value() == "sk-or-v1-test-secret"
    assert str(config.openrouter_base_url) == "https://ai.example.com/v1"
    assert config.openrouter_model == "provider/grocery-model:free"
    assert config.openrouter_timeout_seconds == 45
    assert config.openrouter_max_output_tokens == 768
    assert config.ai_max_input_characters == 1500
    assert str(config.openrouter_http_referer) == "https://familykart.example/"
    assert config.openrouter_app_title == "FamilyKart Test"


def test_openrouter_api_key_is_redacted() -> None:
    secret = "sk-or-v1-super-secret-value"
    config = build_settings(openrouter_api_key=secret)

    assert config.openrouter_api_key is not None
    assert str(config.openrouter_api_key) == "**********"
    assert secret not in repr(config)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_blank_openrouter_api_key_is_treated_as_unconfigured(
    value: str | None,
) -> None:
    config = build_settings(openrouter_api_key=value)

    assert config.openrouter_api_key is None


@pytest.mark.parametrize(
    "url",
    [
        "http://openrouter.ai/api/v1",
        "https://openrouter.ai/api/v1?key=value",
        "https://openrouter.ai/api/v1#fragment",
    ],
)
def test_openrouter_base_url_rejects_unsafe_shapes(url: str) -> None:
    with pytest.raises(ValidationError):
        build_settings(openrouter_base_url=url)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("openrouter_model", "   "),
        ("openrouter_app_title", "   "),
        ("openrouter_timeout_seconds", 0),
        ("openrouter_timeout_seconds", 121),
        ("openrouter_max_output_tokens", 63),
        ("openrouter_max_output_tokens", 4097),
        ("ai_max_input_characters", 0),
        ("ai_max_input_characters", 10001),
    ],
)
def test_ai_configuration_rejects_invalid_safety_limits(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        build_settings(**{field: value})


def test_blank_optional_referer_is_treated_as_unconfigured() -> None:
    config = build_settings(openrouter_http_referer="   ")

    assert config.openrouter_http_referer is None
