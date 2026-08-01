"""Persistent deduplication for notification-only scrapers.

SEC filings and news articles are pushed to Discord but never stored as
events, so their in-memory markers vanished on restart and already-posted
items were re-notified. The ``scraper_dedup`` table survives restarts;
the caller's ``BoundedSet`` is kept as a fast-path cache on top of it.
"""

import datetime
import logging

from sqlalchemy.orm import Session

from app.models.database import ScraperDedup

logger = logging.getLogger(__name__)

# Keep markers long enough that a scraper won't re-process an old item
# after a restart, but not forever — feeds only surface recent entries.
PRUNE_AFTER_DAYS = 90


def is_seen(db: Session, source: str, identifier: str, cache) -> bool:
    """Return True if *identifier* was already processed for *source*.

    Checks the in-memory *cache* first (a ``BoundedSet``); on a miss it
    falls back to the persistent ``scraper_dedup`` table and warms the
    cache so subsequent lookups stay in memory.
    """
    if identifier in cache:
        return True
    row = (
        db.query(ScraperDedup.id)
        .filter(
            ScraperDedup.source == source,
            ScraperDedup.identifier == identifier,
        )
        .first()
    )
    if row is not None:
        cache.add(identifier)
        return True
    return False


def mark_seen(db: Session, source: str, identifier: str, cache) -> None:
    """Record *identifier* as processed for *source*.

    Committed by the caller's transaction. Check-then-insert is safe here:
    the scheduler runs one scraper job at a time, and ``is_seen`` already
    checked both cache and DB before this is called. The unique constraint
    is a backstop for any unexpected race.
    """
    cache.add(identifier)
    row = (
        db.query(ScraperDedup.id)
        .filter(
            ScraperDedup.source == source,
            ScraperDedup.identifier == identifier,
        )
        .first()
    )
    if row is None:
        db.add(ScraperDedup(source=source, identifier=identifier))


def prune_old(db: Session, source: str) -> None:
    """Delete markers older than ``PRUNE_AFTER_DAYS`` (bounded growth).

    Cheap — a single DELETE over an indexed source column, run once per
    scraper invocation.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=PRUNE_AFTER_DAYS)
    deleted = (
        db.query(ScraperDedup)
        .filter(ScraperDedup.source == source, ScraperDedup.seen_at < cutoff)
        .delete(synchronize_session=False)
    )
    if deleted:
        logger.info("Pruned %d old %s dedup marker(s)", deleted, source)
