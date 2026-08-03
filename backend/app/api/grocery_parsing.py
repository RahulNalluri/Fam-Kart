from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.ai_prompt_policy import (
    HouseholdAliasPromptError,
    PromptInjectionDetectedError,
)
from app.core.config import settings
from app.core.http import get_http_client
from app.db.session import get_db
from app.models.user import User
from app.repositories.household_grocery_aliases import (
    HouseholdGroceryAliasRepository,
)
from app.repositories.household_members import HouseholdMemberRepository
from app.schemas.grocery_extraction import (
    GroceryExtractionRequest,
    GroceryExtractionResult,
)
from app.services.ai_parsing import (
    AIParsingHouseholdNotFoundError,
    AIParsingService,
    get_household_aliases_for_parsing,
)
from app.services.openrouter_provider import OpenRouterProvider
from app.services.rule_based_grocery_parser import (
    NoRecognizedGroceryItemsError,
    RuleBasedParserError,
)

router = APIRouter(
    prefix="/api/v1/households/{household_id}/grocery-items",
    tags=["grocery parsing"],
)


def get_ai_parsing_service(
    http_client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> AIParsingService:
    return AIParsingService(
        provider=OpenRouterProvider(config=settings, client=http_client),
    )


def get_authorized_household_aliases(
    household_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    try:
        return get_household_aliases_for_parsing(
            household_id,
            current_user,
            HouseholdGroceryAliasRepository(db),
            HouseholdMemberRepository(db),
        )
    except AIParsingHouseholdNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household not found.",
        ) from error


@router.post("/parse", response_model=GroceryExtractionResult)
async def parse_household_grocery_command(
    data: GroceryExtractionRequest,
    household_aliases: Annotated[
        dict[str, str],
        Depends(get_authorized_household_aliases),
    ],
    parsing_service: Annotated[AIParsingService, Depends(get_ai_parsing_service)],
) -> GroceryExtractionResult:
    try:
        outcome = await parsing_service.parse(
            data,
            household_aliases=household_aliases,
        )
    except PromptInjectionDetectedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=("Please enter only grocery items without instructions for the AI."),
        ) from error
    except HouseholdAliasPromptError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Household grocery aliases could not be applied safely.",
        ) from error
    except NoRecognizedGroceryItemsError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="We could not find a supported grocery item in this command.",
        ) from error
    except RuleBasedParserError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "We could not fully understand this grocery command. "
                "Please rephrase it."
            ),
        ) from error
    return outcome.result
