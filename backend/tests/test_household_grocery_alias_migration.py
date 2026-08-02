import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260802_0009_create_household_grocery_aliases.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "create_household_grocery_aliases_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_household_grocery_alias_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_household_grocery_alias_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260802_0009"
    assert migration.down_revision == "20260727_0008"


def test_household_grocery_alias_migration_has_upgrade_and_downgrade() -> None:
    migration = load_migration()

    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_household_grocery_alias_migration_defines_scoped_integrity() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    for column in (
        "household_id",
        "alias",
        "normalized_alias",
        "canonical_key",
        "created_by_user_id",
        "created_at",
        "updated_at",
    ):
        assert f'"{column}"' in migration_source

    assert 'ondelete="CASCADE"' in migration_source
    assert 'ondelete="SET NULL"' in migration_source
    assert "ck_household_grocery_aliases_alias_not_blank" in migration_source
    assert "ck_household_grocery_aliases_normalized_alias_not_blank" in migration_source
    assert "ck_household_grocery_aliases_canonical_key_not_blank" in migration_source
    assert "uq_household_grocery_aliases_household_normalized_alias" in migration_source
    assert "ix_household_grocery_aliases_household_canonical_key" in migration_source
    assert "ix_household_grocery_aliases_created_by_user_id" in migration_source
    assert 'drop_table("household_grocery_aliases")' in migration_source
