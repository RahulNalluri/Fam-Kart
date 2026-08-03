from collections.abc import Generator, Mapping
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.grocery_parsing import get_ai_parsing_service
from app.core.ai_prompt_policy import (
    HouseholdAliasPromptError,
    PromptInjectionDetectedError,
)
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    GroceryItem,
    Household,
    HouseholdGroceryAlias,
    HouseholdMember,
    HouseholdRole,
    User,
)
from app.schemas.grocery_extraction import (
    CanonicalGroceryKey,
    ExtractedGroceryItem,
    GroceryExtractionRequest,
    GroceryExtractionResult,
    GroceryUnit,
)
from app.services.ai_parsing import (
    AIParsingFallbackReason,
    AIParsingOutcome,
    AIParsingSource,
)
from app.services.rule_based_grocery_parser import (
    NoRecognizedGroceryItemsError,
    UnsupportedGroceryCommandError,
)


def _outcome(
    *,
    source: AIParsingSource = AIParsingSource.OPENROUTER,
) -> AIParsingOutcome:
    return AIParsingOutcome(
        result=GroceryExtractionResult(
            items=[
                ExtractedGroceryItem(
                    name="Maa paalu",
                    canonical_key=CanonicalGroceryKey.MILK,
                    quantity=2,
                    unit=GroceryUnit.PACKET,
                ),
            ],
        ),
        source=source,
        fallback_reason=(
            AIParsingFallbackReason.NOT_CONFIGURED
            if source is AIParsingSource.RULE_BASED
            else None
        ),
    )


class StubParsingService:
    def __init__(
        self,
        *,
        outcome: AIParsingOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self.outcome = outcome or _outcome()
        self.error = error
        self.calls: list[tuple[GroceryExtractionRequest, Mapping[str, str] | None]] = []

    async def parse(
        self,
        request: GroceryExtractionRequest,
        *,
        household_aliases: Mapping[str, str] | None = None,
    ) -> AIParsingOutcome:
        self.calls.append((request, household_aliases))
        if self.error is not None:
            raise self.error
        return self.outcome


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with test_session() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def parsing_service() -> StubParsingService:
    return StubParsingService()


@pytest.fixture
def client(
    db_session: Session,
    parsing_service: StubParsingService,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_ai_parsing_service] = lambda: parsing_service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def _create_user(db: Session, *, email: str, language: str = "en") -> User:
    user = User(
        email=email,
        display_name="Parsing API User",
        password_hash=hash_password("familykart123"),
        preferred_language=language,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_household(db: Session, *, name: str) -> Household:
    household = Household(name=name)
    db.add(household)
    db.commit()
    db.refresh(household)
    return household


def _add_member(
    db: Session,
    *,
    household: Household,
    user: User,
    role: HouseholdRole = HouseholdRole.MEMBER,
) -> None:
    db.add(
        HouseholdMember(
            household_id=household.id,
            user_id=user.id,
            role=role,
        ),
    )
    db.commit()


def _add_alias(
    db: Session,
    *,
    household: Household,
    user: User,
    alias: str,
    canonical_key: str,
) -> None:
    db.add(
        HouseholdGroceryAlias(
            household_id=household.id,
            alias=alias,
            normalized_alias=alias.casefold(),
            canonical_key=canonical_key,
            created_by_user_id=user.id,
        ),
    )
    db.commit()


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_household_member_can_parse_command_without_creating_items(
    client: TestClient,
    db_session: Session,
    parsing_service: StubParsingService,
    role: HouseholdRole,
) -> None:
    user = _create_user(
        db_session,
        email=f"parse-{role.value}@example.com",
        language="te",
    )
    household = _create_household(db_session, name="Parsing Family")
    hidden_household = _create_household(db_session, name="Hidden Family")
    _add_member(db_session, household=household, user=user, role=role)
    _add_alias(
        db_session,
        household=household,
        user=user,
        alias="Maa paalu",
        canonical_key="milk",
    )
    _add_alias(
        db_session,
        household=hidden_household,
        user=user,
        alias="Hidden rice",
        canonical_key="rice",
    )

    response = client.post(
        f"/api/v1/households/{household.id}/grocery-items/parse",
        headers=_auth(user),
        json={
            "text": "  Maa   paalu rendu packets  ",
            "preferred_language": "te",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "name": "Maa paalu",
                "canonical_key": "milk",
                "quantity": "2",
                "unit": "packet",
            },
        ],
    }
    request, aliases = parsing_service.calls[0]
    assert request.text == "Maa paalu rendu packets"
    assert request.preferred_language == "te"
    assert aliases == {"Maa paalu": "milk"}
    item_count = db_session.scalar(select(func.count()).select_from(GroceryItem))
    assert item_count == 0


def test_rule_based_fallback_result_uses_same_public_response_contract(
    client: TestClient,
    db_session: Session,
    parsing_service: StubParsingService,
) -> None:
    user = _create_user(db_session, email="parse-fallback@example.com")
    household = _create_household(db_session, name="Fallback Family")
    _add_member(db_session, household=household, user=user)
    parsing_service.outcome = _outcome(source=AIParsingSource.RULE_BASED)

    response = client.post(
        f"/api/v1/households/{household.id}/grocery-items/parse",
        headers=_auth(user),
        json={"text": "Palu rendu packets"},
    )

    assert response.status_code == 200
    assert set(response.json()) == {"items"}


def test_outsider_cannot_parse_or_discover_household_aliases(
    client: TestClient,
    db_session: Session,
    parsing_service: StubParsingService,
) -> None:
    outsider = _create_user(db_session, email="parse-outsider@example.com")
    owner = _create_user(db_session, email="parse-owner@example.com")
    household = _create_household(db_session, name="Private Parsing Family")
    _add_member(db_session, household=household, user=owner, role=HouseholdRole.OWNER)
    _add_alias(
        db_session,
        household=household,
        user=owner,
        alias="Private milk",
        canonical_key="milk",
    )

    response = client.post(
        f"/api/v1/households/{household.id}/grocery-items/parse",
        headers=_auth(outsider),
        json={"text": "Private milk"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Household not found."
    assert parsing_service.calls == []


def test_parsing_endpoint_requires_authentication(
    client: TestClient,
    parsing_service: StubParsingService,
) -> None:
    response = client.post(
        f"/api/v1/households/{uuid4()}/grocery-items/parse",
        json={"text": "Rice"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Please log in again to continue."
    assert parsing_service.calls == []


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (
            PromptInjectionDetectedError(reason_code="instruction_override"),
            "Please enter only grocery items without instructions for the AI.",
        ),
        (
            HouseholdAliasPromptError(reason_code="standard_term_conflict"),
            "Household grocery aliases could not be applied safely.",
        ),
        (
            NoRecognizedGroceryItemsError(),
            "We could not find a supported grocery item in this command.",
        ),
        (
            UnsupportedGroceryCommandError(),
            "We could not fully understand this grocery command. Please rephrase it.",
        ),
    ],
)
def test_parsing_endpoint_returns_understandable_input_errors(
    client: TestClient,
    db_session: Session,
    parsing_service: StubParsingService,
    error: Exception,
    expected_message: str,
) -> None:
    user = _create_user(
        db_session,
        email=f"parse-error-{type(error).__name__}@example.com",
    )
    household = _create_household(db_session, name="Parsing Error Family")
    _add_member(db_session, household=household, user=user)
    parsing_service.error = error

    response = client.post(
        f"/api/v1/households/{household.id}/grocery-items/parse",
        headers=_auth(user),
        json={"text": "Unclear command"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == expected_message


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": "   "},
        {"text": "Rice", "preferred_language": "hi"},
        {"text": "Rice", "unexpected": True},
    ],
)
def test_parsing_endpoint_rejects_invalid_request_payload(
    client: TestClient,
    db_session: Session,
    parsing_service: StubParsingService,
    payload: dict[str, object],
) -> None:
    user = _create_user(
        db_session,
        email=f"parse-validation-{len(str(payload))}@example.com",
    )
    household = _create_household(db_session, name="Validation Family")
    _add_member(db_session, household=household, user=user)

    response = client.post(
        f"/api/v1/households/{household.id}/grocery-items/parse",
        headers=_auth(user),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Request validation failed."
    assert parsing_service.calls == []
