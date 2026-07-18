from app.core.config import Settings


def test_database_url_has_postgresql_psycopg_default() -> None:
    settings = Settings()

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_database_url_can_be_overridden_from_environment(
    monkeypatch,
) -> None:
    database_url = "postgresql+psycopg://test:test@localhost:5432/test_db"
    monkeypatch.setenv("DATABASE_URL", database_url)

    settings = Settings()

    assert settings.database_url == database_url


def test_household_invitation_expiration_defaults_to_24_hours() -> None:
    settings = Settings()

    assert settings.household_invitation_expire_hours == 24
