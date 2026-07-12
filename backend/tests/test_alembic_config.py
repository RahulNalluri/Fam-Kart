from pathlib import Path

from alembic.config import Config

from app.db.base import Base
from app.models import Household, HouseholdMember, User


def test_alembic_config_points_to_migration_directory() -> None:
    config = Config("alembic.ini")

    assert config.get_main_option("script_location") == "alembic"


def test_alembic_files_exist() -> None:
    assert Path("alembic/env.py").is_file()
    assert Path("alembic/script.py.mako").is_file()
    assert Path("alembic/versions").is_dir()


def test_model_metadata_is_available_for_migrations() -> None:
    assert User.__tablename__ in Base.metadata.tables
    assert Household.__tablename__ in Base.metadata.tables
    assert HouseholdMember.__tablename__ in Base.metadata.tables
