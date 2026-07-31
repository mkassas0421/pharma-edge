"""Database setup and ORM models for the Pharma Catalyst Alert System.

Supports both SQLite (development, fallback) and PostgreSQL (production).
The driver is selected automatically based on the DATABASE_URL prefix.
"""

import datetime
import logging
from urllib.parse import urlparse

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings


def _is_postgres(url: str) -> bool:
    """Return True if the URL points to a PostgreSQL database."""
    return urlparse(url).scheme in ("postgresql", "postgres", "postgresql+psycopg2")


# ── Engine ────────────────────────────────────────────────────────────────────

_connect_args: dict = {}
if _is_postgres(settings.database_url):
    _connect_args = {}
else:
    # SQLite needs check_same_thread=False for multi-thread access
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,         # verify connections before use (important for PG)
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── ORM Models ──────────────────────────────────────────────────────────────

class Ticker(Base):
    """A tracked pharma/biotech stock ticker."""

    __tablename__ = "tickers"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), unique=True, nullable=False, index=True)
    company_name = Column(String(200), nullable=False)
    sector = Column(String(100), default="Biotechnology")        # e.g. Large-cap Biotech, Micro-cap Pharma
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class CatalystEvent(Base):
    """An upcoming catalyst event for a tracked ticker."""

    __tablename__ = "catalyst_events"

    id = Column(Integer, primary_key=True, index=True)
    ticker_id = Column(Integer, nullable=False, index=True)      # FK to tickers.id
    ticker = Column(String(10), nullable=False, index=True)      # denormalised for quick lookups
    title = Column(String(300), nullable=False)                  # e.g. "PDUFA date for Alzheimer's drug"
    event_type = Column(String(50), nullable=False)              # PDUFA, PHASE3_READOUT, PHASE2_READOUT, etc.
    event_date = Column(DateTime, nullable=False, index=True)
    impact_level = Column(String(10), default="High")            # High / Medium / Low
    description = Column(Text, default="")
    alert_sent = Column(DateTime, nullable=True, default=None)   # when the alert was last sent (None = not sent)
    external_id = Column(String(100), nullable=True, index=True) # e.g. NCT number from ClinicalTrials.gov
    source = Column(String(50), default="manual")                # manual, clinicaltrials_gov, fda
    source_url = Column(String(1000), nullable=True)             # URL of the official source document
    verified = Column(Boolean, default=False)                    # confirmed against an official source
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class PriceSnapshot(Base):
    """Cached stock price written by the background scheduler."""

    __tablename__ = "price_snapshots"

    ticker = Column(String(10), primary_key=True)
    price = Column(Float, nullable=True)
    change_percent = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class TickerAlias(Base):
    """ClinicalTrials.gov sponsor-name alias for a tracked ticker.

    The scraper uses these to search for and identify studies.
    Auto-populated when a ticker is added; manageable via the API.
    """

    __tablename__ = "ticker_aliases"

    id = Column(Integer, primary_key=True, index=True)
    ticker_id = Column(Integer, nullable=False, index=True)
    alias = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_db():
    """FastAPI dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables / run migrations on startup.

    * PostgreSQL (production) — runs ``alembic upgrade head``.
    * SQLite (development)   — uses ``Base.metadata.create_all()`` + stamps
      the Alembic revision so the migration chain stays consistent.
    """
    if _is_postgres(settings.database_url):
        _run_alembic_upgrade()
    else:
        Base.metadata.create_all(bind=engine)
        _stamp_alembic()
        _run_inline_migrations()


def _find_alembic_cfg():
    """Locate and return an Alembic Config, or None if not found."""
    import os
    try:
        from alembic.config import Config
    except ImportError:
        return None
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    path = os.path.join(root, "alembic.ini")
    return Config(path) if os.path.isfile(path) else None


def _run_alembic_upgrade():
    """Run ``alembic upgrade head`` — intended for production (PostgreSQL)."""
    cfg = _find_alembic_cfg()
    if cfg is None:
        logger = logging.getLogger(__name__)
        logger.warning("alembic.ini not found — skipping migrations")
        return
    try:
        from alembic import command
        command.upgrade(cfg, "head")
        logger = logging.getLogger(__name__)
        logger.info("Alembic upgrade to head completed.")
    except Exception as exc:
        logger = logging.getLogger(__name__)
        logger.error("Alembic upgrade failed: %s", exc)
        raise


def _stamp_alembic():
    """Stamp the latest Alembic revision if the version table is missing."""
    cfg = _find_alembic_cfg()
    if cfg is None:
        return
    try:
        from alembic import command
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(cfg)

        with engine.connect() as conn:
            has_version = inspect(conn).has_table("alembic_version")
            if not has_version:
                head = script.get_current_head()
                if head:
                    command.stamp(cfg, head)
                    logger = logging.getLogger(__name__)
                    logger.info("Stamped Alembic revision: %s", head)
    except Exception:
        pass  # non-critical — create_all is sufficient for dev


def _run_inline_migrations():
    """Run lightweight ALTER TABLE migrations (SQLite dev only).

    These legacy migrations handle columns added after the initial launch.
    On PostgreSQL, Alembic handles all schema changes instead.
    """
    _MIGRATIONS = {
        "catalyst_events": [
            ("alert_sent", "DATETIME"),
            ("external_id", "VARCHAR(100)"),
            ("source", "VARCHAR(50) DEFAULT 'manual'"),
            ("source_url", "VARCHAR(1000)"),
            ("verified", "BOOLEAN DEFAULT 0"),
        ],
    }
    try:
        with engine.connect() as conn:
            inspector = inspect(conn)
            for table, cols in _MIGRATIONS.items():
                existing = {c["name"] for c in inspector.get_columns(table)}
                for col_name, col_type in cols:
                    if col_name not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        logger = logging.getLogger(__name__)
                        logger.info("Migration: added %s.%s", table, col_name)
    except Exception:
        pass  # table may not exist yet on first run
