import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260807_0010_create_grocery_mutation_idempotency.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "create_grocery_mutation_idempotency_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grocery_mutation_idempotency_migration_revision_chain() -> None:
    migration = load_migration()

    assert migration.revision == "20260807_0010"
    assert migration.down_revision == "20260802_0009"


def test_grocery_mutation_idempotency_migration_defines_atomic_replay_data() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for column in (
        "mutation_id",
        "user_id",
        "household_id",
        "shopping_session_id",
        "operation",
        "request_hash",
        "response_status",
        "response_body",
        "created_at",
    ):
        assert f'"{column}"' in source

    assert "pk_grocery_mutation_idempotency" in source
    assert "ck_grocery_mutation_idempotency_operation_supported" in source
    assert "ck_grocery_mutation_idempotency_request_hash_length" in source
    assert "ix_grocery_mutation_idempotency_household_created_at" in source
    assert 'drop_table("grocery_mutation_idempotency")' in source
