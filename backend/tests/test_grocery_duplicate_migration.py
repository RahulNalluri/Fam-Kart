import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260727_0008_prevent_pending_grocery_duplicates.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "prevent_pending_grocery_duplicates_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_duplicate_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_duplicate_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260727_0008"
    assert migration.down_revision == "20260726_0007"


def test_duplicate_migration_adds_reversible_pending_name_index() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "uq_grocery_items_session_pending_name" in migration_source
    assert 'sa.text("lower(trim(name))")' in migration_source
    assert "sa.text(\"status = 'pending'\")" in migration_source
    assert "unique=True" in migration_source
    assert "op.drop_index(INDEX_NAME" in migration_source
