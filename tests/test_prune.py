"""prune_expired_events: only dead-weight rows (old + never reacted) go.

Policy: an event is deleted only when it is older than a year AND never
received an EventReaction row (import artefact / capture never ran).
Everything with a reaction row — pending, failed or captured — is kept
forever: the historical backfill and the per-ticker reaction history ARE
the product. (Prior policy pruned any >365-day event, wiping the whole
historical backfill on the first daily run — fixed 2026-08-04.)
"""

import datetime

from app.models.database import CatalystEvent, EventReaction, Ticker
from app.tasks.scheduler import prune_expired_events


def _make_event(db, title, days):
    ticker = db.query(Ticker).filter_by(ticker="ABBV").first()
    event = CatalystEvent(
        ticker_id=ticker.id, ticker="ABBV", title=title, event_type="PDUFA",
        event_date=datetime.datetime.utcnow() + datetime.timedelta(days=days),
        impact_level="High", verified=True,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _make_reaction(db, event, status="captured"):
    db.add(EventReaction(
        event_id=event.id, ticker=event.ticker, event_type=event.event_type,
        impact_level=event.impact_level, status=status,
        captured_at=datetime.datetime.utcnow() if status == "captured" else None,
    ))
    db.commit()


def test_prune_removes_old_keeps_recent(seed_tickers, db):
    old_reacted = _make_event(db, "Old 120d reacted", -120)
    _make_reaction(db, old_reacted, status="captured")
    old_pending = _make_event(db, "Old 120d pending", -120)
    _make_reaction(db, old_pending, status="pending")
    _make_event(db, "Old 120d no reaction", -120)   # kept — capture may still run
    ancient_reacted = _make_event(db, "Ancient 400d reacted", -400)
    _make_reaction(db, ancient_reacted, status="captured")
    _make_event(db, "Ancient 400d", -400)           # no reaction, >365d — dead weight
    _make_event(db, "Borderline 91d", -91)          # old, no reaction — kept
    _make_event(db, "Recent 10d", -10)
    _make_event(db, "Future 30d", 30)

    prune_expired_events()

    titles = {e.title for e in db.query(CatalystEvent).all()}
    assert "Old 120d reacted" in titles     # reacted events stay forever
    assert "Old 120d pending" in titles     # …pending ones too
    assert "Old 120d no reaction" in titles
    assert "Ancient 400d reacted" in titles
    assert "Ancient 400d" not in titles     # only dead weight (old + never reacted) goes
    assert "Borderline 91d" in titles
    assert "Recent 10d" in titles
    assert "Future 30d" in titles


def test_prune_empty_db_ok(seed_tickers, db):
    """No events -> no crash, nothing deleted."""
    prune_expired_events()
    assert db.query(CatalystEvent).count() == 0
