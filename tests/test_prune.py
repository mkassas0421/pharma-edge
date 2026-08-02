"""prune_expired_events: 90-day cutoff once reactions settle, ancient rows go.

Policy: a past event is deleted when (a) its EventReaction is final
(captured/failed) and the event is past the 90-day cutoff, or (b) it is older
than a year with no reaction at all (dead weight). Events without a reaction
younger than a year are KEPT so the capture job still gets to them — this
protects the historical backfill from the pruner.
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
    _make_event(db, "Old 120d no reaction", -120)   # kept — capture may still run
    _make_event(db, "Ancient 400d", -400)           # no reaction, >365d — dead weight
    _make_event(db, "Borderline 91d", -91)          # past cutoff, no reaction — kept
    _make_event(db, "Recent 10d", -10)
    _make_event(db, "Future 30d", 30)

    prune_expired_events()

    titles = {e.title for e in db.query(CatalystEvent).all()}
    assert "Old 120d reacted" not in titles
    assert "Old 120d no reaction" in titles
    assert "Ancient 400d" not in titles
    assert "Borderline 91d" in titles
    assert "Recent 10d" in titles
    assert "Future 30d" in titles


def test_prune_empty_db_ok(seed_tickers, db):
    """No events -> no crash, nothing deleted."""
    prune_expired_events()
    assert db.query(CatalystEvent).count() == 0
