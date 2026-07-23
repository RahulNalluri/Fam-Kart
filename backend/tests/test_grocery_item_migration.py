import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260723_0006_create_grocery_items.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "create_grocery_items_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grocery_item_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_grocery_item_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260723_0006"
    assert migration.down_revision == "20260721_0005"


def test_grocery_item_migration_has_upgrade_and_downgrade() -> None:
    migration = load_migration()

    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_grocery_item_migration_defines_item_lifecycle_and_integrity() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    for column in (
        "shopping_session_id",
        "name",
        "quantity",
        "unit",
        "notes",
        "status",
        "created_by_user_id",
        "assigned_to_user_id",
        "completed_by_user_id",
        "created_at",
        "updated_at",
        "completed_at",
    ):
        assert f'"{column}"' in migration_source

    assert 'ondelete="CASCADE"' in migration_source
    assert migration_source.count('ondelete="SET NULL"') == 3
    assert "ck_grocery_items_name_not_blank" in migration_source
    assert "ck_grocery_items_quantity_positive" in migration_source
    assert "ck_grocery_items_status_completion_consistent" in migration_source
    assert "ix_grocery_items_shopping_session_id_status" in migration_source
    assert 'drop_table("grocery_items")' in migration_source
    assert "grocery_item_status.drop(op.get_bind(), checkfirst=True)" in (
        migration_source
    )
