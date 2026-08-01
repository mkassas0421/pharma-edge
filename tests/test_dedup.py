"""Persistent dedup (ScraperDedup + helpers): survives restart, no cross-source bleed."""

import datetime

from app.models.database import ScraperDedup
from app.utils.collections import BoundedSet
from scrapers.dedup import is_seen, mark_seen, prune_old


def test_round_trip(db):
    cache = BoundedSet(maxsize=100)
    assert not is_seen(db, "sec_filings", "ACC-001", cache)
    mark_seen(db, "sec_filings", "ACC-001", cache)
    db.commit()
    assert is_seen(db, "sec_filings", "ACC-001", cache)


def test_survives_restart(db):
    cache = BoundedSet(maxsize=100)
    mark_seen(db, "sec_filings", "ACC-002", cache)
    db.commit()

    fresh_cache = BoundedSet(maxsize=100)  # simulated restart
    assert is_seen(db, "sec_filings", "ACC-002", fresh_cache)


def test_no_cross_source_bleed(db):
    cache_a = BoundedSet(maxsize=100)
    cache_b = BoundedSet(maxsize=100)
    mark_seen(db, "sec_filings", "ACC-003", cache_a)
    db.commit()
    assert not is_seen(db, "news_feed", "ACC-003", cache_b)


def test_unique_constraint_backstop(db):
    """Direct duplicate insert hits the unique constraint (last-line defence)."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    cache = BoundedSet(maxsize=100)
    mark_seen(db, "sec_filings", "ACC-004", cache)
    db.commit()
    db.add(ScraperDedup(source="sec_filings", identifier="ACC-004"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_prune_old_only(db):
    cache = BoundedSet(maxsize=100)
    mark_seen(db, "sec_filings", "RECENT", cache)
    db.add(ScraperDedup(
        source="news_feed", identifier="http://old.example/a",
        seen_at=datetime.datetime.utcnow() - datetime.timedelta(days=200),
    ))
    db.commit()

    prune_old(db, "news_feed")
    db.commit()

    assert db.query(ScraperDedup).filter_by(identifier="http://old.example/a").count() == 0
    assert db.query(ScraperDedup).filter_by(identifier="RECENT").count() == 1


def test_cache_is_warmed_by_db_lookup(db):
    """A DB hit warms the in-memory cache so repeat lookups skip the DB."""
    cache = BoundedSet(maxsize=100)
    mark_seen(db, "sec_filings", "ACC-005", cache)
    db.commit()

    fresh_cache = BoundedSet(maxsize=100)
    assert is_seen(db, "sec_filings", "ACC-005", fresh_cache)  # DB lookup
    assert "ACC-005" in fresh_cache  # warmed
