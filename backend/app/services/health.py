from typing import cast

from sqlalchemy import text
from sqlalchemy.orm import Session


def is_database_healthy(db: Session) -> bool:
    result = cast(int, db.execute(text("SELECT 1")).scalar_one())
    return result == 1
