import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260721_0005_create_shopping_sessions.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "create_shopping_sessions_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shopping_session_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_shopping_session_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260721_0005"
    assert migration.down_revision == "20260718_0004"


def test_shopping_session_migration_has_upgrade_and_downgrade() -> None:
    migration = load_migration()

    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_shopping_session_migration_defines_lifecycle_and_foreign_keys() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert '"shopping_sessions"' in migration_source
    assert '"household_id"' in migration_source
    assert '"created_by_user_id"' in migration_source
    assert '"active"' in migration_source
    assert '"completed"' in migration_source
    assert '"created_at"' in migration_source
    assert '"completed_at"' in migration_source
    assert 'ondelete="CASCADE"' in migration_source
    assert 'ondelete="SET NULL"' in migration_source
    assert 'drop_table("shopping_sessions")' in migration_source
    assert "shopping_session_status.drop(op.get_bind(), checkfirst=True)" in (
        migration_source
    )
