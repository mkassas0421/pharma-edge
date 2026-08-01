"""Shared test fixtures.

IMPORTANT: env vars MUST be set before importing any app module — the
SQLAlchemy engine is created at import time and reads DATABASE_URL.
Tests use a throwaway SQLite DB and never touch production data.
"""

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TEST_DB = Path(__file__).parent / "_ci.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["API_KEY"] = "testkey"

import pytest  # noqa: E402

from app.middleware import rate_limit  # noqa: E402
from app.models.database import Base, engine, SessionLocal  # noqa: E402
from app.utils.cache import dashboard_cache, stats_cache  # noqa: E402

API_KEY = "testkey"


@pytest.fixture(autouse=True)
def clean_state():
    """Fresh tables + caches before every test (no cross-test bleed)."""
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()
    rate_limit._store.clear()
    rate_limit._request_count = 0
    dashboard_cache.invalidate_all()
    stats_cache.invalidate_all()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    """TestClient without context manager -> lifespan (scheduler, network) does not run."""
    from fastapi.testclient import TestClient

    from main import app

    return TestClient(app)


@pytest.fixture
def seed_tickers(db):
    """A few tracked tickers with aliases generated (via seed_aliases)."""
    from app.models.database import Ticker

    rows = [
        Ticker(ticker="ABBV", company_name="AbbVie Inc.", sector="Biotech"),
        Ticker(ticker="LLY", company_name="Eli Lilly and Company", sector="Biotech"),
        Ticker(ticker="CRIS", company_name="Curis Inc.", sector="Biotech"),
        Ticker(ticker="BMY", company_name="Bristol-Myers Squibb", sector="Biotech"),
    ]
    db.add_all(rows)
    db.commit()
    return rows


@pytest.fixture
def auth_headers():
    """Valid API key header for mutating endpoints."""
    return {"X-API-Key": API_KEY}
