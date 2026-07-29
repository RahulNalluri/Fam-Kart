from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.realtime_channels import household_event_channel


def test_household_event_channel_has_expected_format() -> None:
    household_id = uuid4()
    config = Settings(environment="development")

    channel = household_event_channel(household_id, config)

    assert channel == f"familykart:development:households:{household_id}:events"


def test_same_household_always_uses_same_channel() -> None:
    household_id = uuid4()
    config = Settings(environment="testing")

    first_channel = household_event_channel(household_id, config)
    second_channel = household_event_channel(household_id, config)

    assert first_channel == second_channel


def test_different_households_use_different_channels() -> None:
    config = Settings(environment="testing")

    first_channel = household_event_channel(uuid4(), config)
    second_channel = household_event_channel(uuid4(), config)

    assert first_channel != second_channel


def test_environments_use_different_channels() -> None:
    household_id = uuid4()

    development_channel = household_event_channel(
        household_id,
        Settings(environment="development"),
    )
    production_channel = household_event_channel(
        household_id,
        Settings(environment="production"),
    )

    assert development_channel != production_channel


def test_configured_prefix_is_used() -> None:
    household_id = uuid4()
    config = Settings(
        environment="testing",
        redis_channel_prefix="familykart-test",
    )

    channel = household_event_channel(household_id, config)

    assert channel.startswith("familykart-test:testing:")


@pytest.mark.parametrize(
    "prefix",
    ["FamilyKart", "family_kart", "1familykart", "familykart:"],
)
def test_invalid_channel_prefix_is_rejected(prefix: str) -> None:
    with pytest.raises(ValidationError):
        Settings(redis_channel_prefix=prefix)
