from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.core.ai_prompt_policy import validate_grocery_prompt_input
from app.models.user import User
from app.repositories.household_grocery_aliases import (
    HouseholdGroceryAliasRepository,
)
from app.repositories.household_members import HouseholdMemberRepository
from app.schemas.grocery_extraction import (
    GroceryExtractionRequest,
    GroceryExtractionResult,
)
from app.services.openrouter_provider import (
    OpenRouterAPIError,
    OpenRouterInputTooLongError,
    OpenRouterNotConfiguredError,
    OpenRouterResponseError,
    OpenRouterTransportError,
)
from app.services.rule_based_grocery_parser import parse_grocery_command


class AIParsingSource(StrEnum):
    OPENROUTER = "openrouter"
    RULE_BASED = "rule_based"


class AIParsingFallbackReason(StrEnum):
    NOT_CONFIGURED = "not_configured"
    INPUT_LIMIT = "input_limit"
    TRANSPORT_ERROR = "transport_error"
    PROVIDER_ERROR = "provider_error"
    INVALID_RESPONSE = "invalid_response"


class AIParsingHouseholdNotFoundError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AIParsingOutcome:
    result: GroceryExtractionResult
    source: AIParsingSource
    fallback_reason: AIParsingFallbackReason | None


class GroceryExtractionProvider(Protocol):
    async def extract(
        self,
        request: GroceryExtractionRequest,
    ) -> GroceryExtractionResult: ...


class GroceryFallbackParser(Protocol):
    def __call__(
        self,
        request: GroceryExtractionRequest,
        *,
        household_aliases: Mapping[str, str] | None = None,
    ) -> GroceryExtractionResult: ...


class AIParsingService:
    def __init__(
        self,
        *,
        provider: GroceryExtractionProvider,
        fallback_parser: GroceryFallbackParser = parse_grocery_command,
    ) -> None:
        self._provider = provider
        self._fallback_parser = fallback_parser

    async def parse(
        self,
        request: GroceryExtractionRequest,
        *,
        household_aliases: Mapping[str, str] | None = None,
    ) -> AIParsingOutcome:
        validate_grocery_prompt_input(request)
        try:
            result = await self._provider.extract(request)
        except OpenRouterNotConfiguredError:
            fallback_reason = AIParsingFallbackReason.NOT_CONFIGURED
        except OpenRouterInputTooLongError:
            fallback_reason = AIParsingFallbackReason.INPUT_LIMIT
        except OpenRouterTransportError:
            fallback_reason = AIParsingFallbackReason.TRANSPORT_ERROR
        except OpenRouterAPIError:
            fallback_reason = AIParsingFallbackReason.PROVIDER_ERROR
        except OpenRouterResponseError:
            fallback_reason = AIParsingFallbackReason.INVALID_RESPONSE
        else:
            return AIParsingOutcome(
                result=result,
                source=AIParsingSource.OPENROUTER,
                fallback_reason=None,
            )

        fallback_result = self._fallback_parser(
            request,
            household_aliases=household_aliases,
        )
        return AIParsingOutcome(
            result=fallback_result,
            source=AIParsingSource.RULE_BASED,
            fallback_reason=fallback_reason,
        )


def get_household_aliases_for_parsing(
    household_id: UUID,
    user: User,
    alias_repository: HouseholdGroceryAliasRepository,
    member_repository: HouseholdMemberRepository,
) -> dict[str, str]:
    membership = member_repository.get_for_user_and_household(
        household_id=household_id,
        user_id=user.id,
    )
    if membership is None:
        raise AIParsingHouseholdNotFoundError

    aliases = alias_repository.list_for_household(household_id)
    return {alias.alias: alias.canonical_key for alias in aliases}
