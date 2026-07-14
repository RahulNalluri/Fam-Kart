import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260714_0002_add_user_password_hash.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "add_user_password_hash_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_password_hash_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_password_hash_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260714_0002"
    assert migration.down_revision == "20260712_0001"


def test_password_hash_migration_has_upgrade_and_downgrade() -> None:
    migration = load_migration()

    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_password_hash_migration_adds_required_user_column() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert '"users"' in migration_source
    assert '"password_hash"' in migration_source
    assert "sa.String(length=255)" in migration_source
    assert "UPDATE users SET password_hash = '!'" in migration_source
    assert "nullable=False" in migration_source
    assert "drop_column" in migration_source
