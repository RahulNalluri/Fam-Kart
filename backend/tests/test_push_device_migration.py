import importlib.util
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = Path("alembic/versions/20260808_0011_create_push_devices.py")


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "push_device_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_push_device_migration_revision_chain() -> None:
    migration = load_migration()
    assert migration.revision == "20260808_0011"
    assert migration.down_revision == "20260807_0010"


def test_push_device_migration_enforces_identity_and_ownership() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert '"push_devices"' in source
    assert '"installation_id"' in source
    assert '"expo_push_token"' in source
    assert "unique=True" in source
    assert 'ondelete="CASCADE"' in source
    assert 'sa.Enum("android", "ios", name="push_platform")' in source
    assert 'drop_table("push_devices")' in source
