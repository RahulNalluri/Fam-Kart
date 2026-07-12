import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260712_0001_create_user_household_tables.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "initial_family_models_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_initial_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260712_0001"
    assert migration.down_revision is None


def test_initial_migration_has_upgrade_and_downgrade() -> None:
    migration = load_migration()

    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_initial_migration_defines_core_tables() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert '"users"' in migration_source
    assert '"households"' in migration_source
    assert '"household_members"' in migration_source
    assert '"household_role"' in migration_source
