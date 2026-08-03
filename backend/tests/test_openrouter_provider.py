import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from app.core.config import Settings
from app.schemas.grocery_extraction import (
    CanonicalGroceryKey,
    GroceryExtractionRequest,
    GroceryExtractionResult,
    GroceryUnit,
)
from app.services.openrouter_provider import (
    OpenRouterAPIError,
    OpenRouterInputTooLongError,
    OpenRouterNotConfiguredError,
    OpenRouterProvider,
    OpenRouterResponseError,
    OpenRouterTransportError,
)

JWT_SECRET = "test-only-jwt-secret-key-at-least-32-characters"
API_KEY = "sk-or-v1-provider-test-secret"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "jwt_secret_key": JWT_SECRET,
        "openrouter_api_key": API_KEY,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _success_response(
    *,
    items: list[dict[str, object]] | None = None,
) -> httpx.Response:
    content = {
        "items": items
        or [
            {
                "name": "Rice",
                "canonical_key": "rice",
                "quantity": 5,
                "unit": "kg",
            },
        ],
    }
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"content": json.dumps(content)},
                    "finish_reason": "stop",
                },
            ],
        },
    )


async def _extract(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    request: GroceryExtractionRequest | None = None,
    config: Settings | None = None,
) -> GroceryExtractionResult:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenRouterProvider(
            config=config or _settings(),
            client=client,
        )
        return await provider.extract(
            request or GroceryExtractionRequest(text="Rice 5 kg"),
        )


def test_provider_returns_validated_grocery_extraction() -> None:
    result = asyncio.run(_extract(lambda request: _success_response()))

    assert result.items[0].canonical_key is CanonicalGroceryKey.RICE
    assert result.items[0].quantity == 5
    assert result.items[0].unit is GroceryUnit.KILOGRAM


def test_provider_builds_secure_multilingual_structured_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["body"] = json.loads(request.content)
        return _success_response(
            items=[
                {
                    "name": "పాలు",
                    "canonical_key": "milk",
                    "quantity": 2,
                    "unit": "packet",
                },
            ],
        )

    result = asyncio.run(
        _extract(
            handler,
            request=GroceryExtractionRequest(
                text="పాలు రెండు ప్యాకెట్లు తీసుకురా",
                preferred_language="te",
            ),
            config=_settings(
                openrouter_base_url="https://router.example/v1/",
                openrouter_model="provider/grocery-model",
                openrouter_max_output_tokens=768,
                openrouter_http_referer="https://familykart.example",
                openrouter_app_title="FamilyKart Provider Test",
            ),
        ),
    )

    sent_request = captured["request"]
    assert isinstance(sent_request, httpx.Request)
    assert str(sent_request.url) == "https://router.example/v1/chat/completions"
    assert sent_request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert sent_request.headers["HTTP-Referer"] == "https://familykart.example/"
    assert sent_request.headers["X-OpenRouter-Title"] == "FamilyKart Provider Test"

    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "provider/grocery-model"
    assert body["max_tokens"] == 768
    assert body["stream"] is False
    assert body["provider"] == {"require_parameters": True}
    messages = body["messages"]
    assert isinstance(messages, list)
    user_data = json.loads(messages[1]["content"])
    assert user_data == {
        "command": "పాలు రెండు ప్యాకెట్లు తీసుకురా",
        "preferred_language": "te",
    }
    response_format = body["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"]["additionalProperties"] is False
    assert result.items[0].canonical_key is CanonicalGroceryKey.MILK


def test_provider_requires_api_key_before_network_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    with pytest.raises(OpenRouterNotConfiguredError):
        asyncio.run(_extract(handler, config=_settings(openrouter_api_key=None)))

    assert called is False


def test_provider_enforces_configured_input_limit_before_network_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    with pytest.raises(OpenRouterInputTooLongError):
        asyncio.run(
            _extract(
                handler,
                request=GroceryExtractionRequest(text="Rice 5 kg"),
                config=_settings(ai_max_input_characters=5),
            ),
        )

    assert called is False


@pytest.mark.parametrize(
    "network_error",
    [
        httpx.ReadTimeout("Timed out"),
        httpx.ConnectError("Connection failed"),
    ],
)
def test_provider_converts_network_failures(
    network_error: httpx.RequestError,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        network_error.request = request
        raise network_error

    with pytest.raises(OpenRouterTransportError) as captured:
        asyncio.run(_extract(handler))

    assert API_KEY not in str(captured.value)
    assert API_KEY not in repr(captured.value)


def test_provider_preserves_safe_http_error_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": {
                    "code": 401,
                    "message": f"Invalid credential {API_KEY}",
                    "metadata": {"error_type": "authentication"},
                },
            },
        )

    with pytest.raises(OpenRouterAPIError) as captured:
        asyncio.run(_extract(handler))

    error = captured.value
    assert error.status_code == 401
    assert error.error_type == "authentication"
    assert error.retry_after_seconds is None
    assert error.retryable is False
    assert API_KEY not in str(error)
    assert API_KEY not in repr(error)


def test_provider_exposes_retry_information_without_retrying() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "12.5"},
            json={
                "error": {
                    "code": 429,
                    "message": "Rate limited",
                    "metadata": {"error_type": "rate_limit_exceeded"},
                },
            },
        )

    with pytest.raises(OpenRouterAPIError) as captured:
        asyncio.run(_extract(handler))

    assert captured.value.status_code == 429
    assert captured.value.error_type == "rate_limit_exceeded"
    assert captured.value.retry_after_seconds == 12.5
    assert captured.value.retryable is True
    assert calls == 1


def test_provider_handles_error_inside_successful_http_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": {
                    "code": 503,
                    "message": "No provider available",
                    "metadata": {"error_type": "provider_overloaded"},
                },
            },
        )

    with pytest.raises(OpenRouterAPIError) as captured:
        asyncio.run(_extract(handler))

    assert captured.value.status_code == 503
    assert captured.value.error_type == "provider_overloaded"
    assert captured.value.retryable is True


def test_provider_handles_choice_level_generation_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "error",
                        "error": {
                            "code": 502,
                            "message": "Provider disconnected",
                            "metadata": {"error_type": "provider_unavailable"},
                        },
                    },
                ],
            },
        )

    with pytest.raises(OpenRouterAPIError) as captured:
        asyncio.run(_extract(handler))

    assert captured.value.status_code == 502
    assert captured.value.error_type == "provider_unavailable"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": ""}}]},
        ),
        httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "items": [
                                        {
                                            "name": "Bread",
                                            "canonical_key": "bread",
                                            "quantity": None,
                                            "unit": None,
                                        },
                                    ],
                                },
                            ),
                        },
                    },
                ],
            },
        ),
    ],
)
def test_provider_rejects_malformed_or_invalid_success_response(
    response: httpx.Response,
) -> None:
    with pytest.raises(OpenRouterResponseError):
        asyncio.run(_extract(lambda request: response))


def test_provider_handles_finish_error_without_error_details() -> None:
    response = httpx.Response(
        200,
        json={"choices": [{"finish_reason": "error"}]},
    )

    with pytest.raises(OpenRouterAPIError) as captured:
        asyncio.run(_extract(lambda request: response))

    assert captured.value.status_code == 502
    assert captured.value.error_type == "provider_unavailable"


def test_provider_handles_malformed_http_error_body() -> None:
    with pytest.raises(OpenRouterAPIError) as captured:
        asyncio.run(
            _extract(
                lambda request: httpx.Response(503, content=b"invalid-error-body"),
            ),
        )

    assert captured.value.status_code == 503
    assert captured.value.error_type is None
    assert captured.value.retryable is True
