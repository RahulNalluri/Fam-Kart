import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260726_0007_create_grocery_activity_events.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "create_grocery_activity_events_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_activity_event_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_activity_event_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260726_0007"
    assert migration.down_revision == "20260723_0006"


def test_activity_event_migration_has_upgrade_and_downgrade() -> None:
    migration = load_migration()

    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_activity_event_migration_preserves_grocery_history() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    for column in (
        "household_id",
        "shopping_session_id",
        "grocery_item_id",
        "actor_user_id",
        "event_type",
        "item_name",
        "sequence_number",
        "created_at",
    ):
        assert f'"{column}"' in migration_source

    assert migration_source.count('ondelete="CASCADE"') == 2
    assert migration_source.count('ondelete="SET NULL"') == 1
    assert "grocery_items.id" not in migration_source
    assert "ck_grocery_activity_events_sequence_number_positive" in migration_source
    assert "uq_grocery_activity_events_session_sequence" in migration_source
    assert "ix_grocery_activity_events_household_id_created_at" in migration_source
    assert "ix_grocery_activity_events_session_id_created_at" in migration_source
    assert 'drop_table("grocery_activity_events")' in migration_source
    assert "grocery_activity_type.drop(op.get_bind(), checkfirst=True)" in (
        migration_source
    )
