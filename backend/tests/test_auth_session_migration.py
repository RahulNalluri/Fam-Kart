import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260716_0003_create_auth_sessions.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "create_auth_sessions_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_auth_session_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_auth_session_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260716_0003"
    assert migration.down_revision == "20260714_0002"


def test_auth_session_migration_has_upgrade_and_downgrade() -> None:
    migration = load_migration()

    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_auth_session_migration_creates_secure_session_table() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert '"auth_sessions"' in migration_source
    assert '"user_id"' in migration_source
    assert '"refresh_token_hash"' in migration_source
    assert "sa.String(length=64)" in migration_source
    assert 'ondelete="CASCADE"' in migration_source
    assert '"expires_at"' in migration_source
    assert '"revoked_at"' in migration_source
    assert "unique=True" in migration_source
    assert 'drop_table("auth_sessions")' in migration_source
