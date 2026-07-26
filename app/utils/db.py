"""Database session context manager — replaces repeated try/finally/close patterns."""
from collections.abc import Generator
from contextlib import contextmanager

from app.models.database import SessionLocal


@contextmanager
def db_session() -> Generator:
    """Yield a SQLAlchemy session and ensure it's closed afterward.

    Usage:
        with db_session() as db:
            rows = db.query(...).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
