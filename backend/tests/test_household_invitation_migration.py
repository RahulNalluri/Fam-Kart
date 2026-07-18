import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path(
    "alembic/versions/20260718_0004_create_household_invitations.py",
)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "create_household_invitations_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_household_invitation_migration_file_exists() -> None:
    assert MIGRATION_PATH.is_file()


def test_household_invitation_migration_revision_metadata() -> None:
    migration = load_migration()

    assert migration.revision == "20260718_0004"
    assert migration.down_revision == "20260716_0003"


def test_household_invitation_migration_has_upgrade_and_downgrade() -> None:
    migration = load_migration()

    assert callable(migration.upgrade)
    assert callable(migration.downgrade)


def test_household_invitation_migration_has_secure_lifecycle_columns() -> None:
    migration_source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert '"household_invitations"' in migration_source
    assert '"household_id"' in migration_source
    assert '"created_by_user_id"' in migration_source
    assert '"code_hash"' in migration_source
    assert "sa.String(length=64)" in migration_source
    assert '"expires_at"' in migration_source
    assert '"used_at"' in migration_source
    assert '"used_by_user_id"' in migration_source
    assert '"revoked_at"' in migration_source
    assert 'ondelete="CASCADE"' in migration_source
    assert 'ondelete="SET NULL"' in migration_source
    assert "unique=True" in migration_source
    assert 'drop_table("household_invitations")' in migration_source
