from collections.abc import Mapping
from typing import Final

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.ai_prompt_policy import build_grocery_extraction_messages
from app.core.config import Settings
from app.schemas.grocery_extraction import (
    GroceryExtractionRequest,
    GroceryExtractionResult,
)


class OpenRouterProviderError(RuntimeError):
    pass


class OpenRouterNotConfiguredError(OpenRouterProviderError):
    pass


class OpenRouterInputTooLongError(OpenRouterProviderError):
    pass


class OpenRouterTransportError(OpenRouterProviderError):
    pass


class OpenRouterResponseError(OpenRouterProviderError):
    pass


class OpenRouterAPIError(OpenRouterProviderError):
    RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset(
        {408, 429, 500, 502, 503, 504},
    )

    def __init__(
        self,
        *,
        status_code: int,
        error_type: str | None,
        retry_after_seconds: float | None,
    ) -> None:
        super().__init__(
            "OpenRouter could not complete the grocery extraction request."
        )
        self.status_code = status_code
        self.error_type = error_type
        self.retry_after_seconds = retry_after_seconds

    @property
    def retryable(self) -> bool:
        return self.status_code in self.RETRYABLE_STATUS_CODES


class _OpenRouterError(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: int | str | None = None
    message: str | None = None
    metadata: Mapping[str, object] | None = None

    @property
    def error_type(self) -> str | None:
        if self.metadata is None:
            return None
        value = self.metadata.get("error_type")
        return value if isinstance(value, str) else None


class _OpenRouterMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = None


class _OpenRouterChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: _OpenRouterMessage | None = None
    finish_reason: str | None = None
    error: _OpenRouterError | None = None


class _OpenRouterEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    choices: list[_OpenRouterChoice] | None = None
    error: _OpenRouterError | None = None


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _decode_envelope(response: httpx.Response) -> _OpenRouterEnvelope | None:
    try:
        return _OpenRouterEnvelope.model_validate(response.json())
    except (ValueError, ValidationError):
        return None


def _api_error(
    response: httpx.Response,
    error: _OpenRouterError | None,
) -> OpenRouterAPIError:
    status_code = response.status_code
    if error is not None and isinstance(error.code, int):
        status_code = error.code
    return OpenRouterAPIError(
        status_code=status_code,
        error_type=error.error_type if error is not None else None,
        retry_after_seconds=_retry_after_seconds(response),
    )


class OpenRouterProvider:
    def __init__(self, *, config: Settings, client: httpx.AsyncClient) -> None:
        self._config = config
        self._client = client

    def _headers(self) -> dict[str, str]:
        api_key = self._config.openrouter_api_key
        if api_key is None:
            raise OpenRouterNotConfiguredError(
                "OpenRouter is not configured for this environment.",
            )

        headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": self._config.openrouter_app_title,
        }
        if self._config.openrouter_http_referer is not None:
            headers["HTTP-Referer"] = str(self._config.openrouter_http_referer)
        return headers

    def _request_body(
        self,
        request: GroceryExtractionRequest,
        household_aliases: Mapping[str, str] | None,
    ) -> dict[str, object]:
        if len(request.text) > self._config.ai_max_input_characters:
            raise OpenRouterInputTooLongError(
                "The grocery command is too long for AI extraction.",
            )

        return {
            "model": self._config.openrouter_model,
            "messages": list(
                build_grocery_extraction_messages(
                    request,
                    household_aliases=household_aliases,
                ),
            ),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "grocery_extraction",
                    "strict": True,
                    "schema": GroceryExtractionResult.model_json_schema(
                        mode="serialization",
                    ),
                },
            },
            "provider": {"require_parameters": True},
            "max_tokens": self._config.openrouter_max_output_tokens,
            "stream": False,
        }

    async def extract(
        self,
        request: GroceryExtractionRequest,
        *,
        household_aliases: Mapping[str, str] | None = None,
    ) -> GroceryExtractionResult:
        base_url = str(self._config.openrouter_base_url).rstrip("/")
        endpoint = f"{base_url}/chat/completions"
        try:
            response = await self._client.post(
                endpoint,
                headers=self._headers(),
                json=self._request_body(request, household_aliases),
                timeout=self._config.openrouter_timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise OpenRouterTransportError(
                "OpenRouter did not respond before the configured timeout.",
            ) from error
        except httpx.RequestError as error:
            raise OpenRouterTransportError(
                "OpenRouter could not be reached.",
            ) from error

        envelope = _decode_envelope(response)
        if not response.is_success:
            raise _api_error(response, envelope.error if envelope is not None else None)
        if envelope is None:
            raise OpenRouterResponseError("OpenRouter returned an invalid response.")
        if envelope.error is not None:
            raise _api_error(response, envelope.error)
        if not envelope.choices:
            raise OpenRouterResponseError("OpenRouter returned no completion choices.")

        choice = envelope.choices[0]
        if choice.error is not None:
            raise _api_error(response, choice.error)
        if choice.finish_reason == "error":
            raise OpenRouterAPIError(
                status_code=502,
                error_type="provider_unavailable",
                retry_after_seconds=_retry_after_seconds(response),
            )
        if choice.message is None or not choice.message.content:
            raise OpenRouterResponseError("OpenRouter returned no structured content.")

        try:
            return GroceryExtractionResult.model_validate_json(choice.message.content)
        except (ValueError, ValidationError) as error:
            raise OpenRouterResponseError(
                "OpenRouter returned grocery data that failed validation.",
            ) from error
