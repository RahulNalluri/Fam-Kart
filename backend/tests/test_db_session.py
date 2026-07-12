from sqlalchemy.orm import Session

from app.db.base import NAMING_CONVENTION, Base
from app.db.session import SessionLocal, engine, get_db


def test_base_metadata_uses_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_engine_uses_configured_postgresql_driver() -> None:
    assert engine.url.drivername == "postgresql+psycopg"


def test_session_factory_creates_bound_session() -> None:
    db = SessionLocal()
    try:
        assert isinstance(db, Session)
        assert db.bind is engine
    finally:
        db.close()


def test_get_db_yields_bound_session() -> None:
    db_generator = get_db()
    db = next(db_generator)
    try:
        assert isinstance(db, Session)
        assert db.bind is engine
    finally:
        db_generator.close()
