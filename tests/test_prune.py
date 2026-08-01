"""prune_expired_events: 90-day cutoff, recent/future events kept."""

import datetime

from app.models.database import CatalystEvent, Ticker
from app.tasks.scheduler import prune_expired_events


def _make_event(db, title, days):
    ticker = db.query(Ticker).filter_by(ticker="ABBV").first()
    db.add(CatalystEvent(
        ticker_id=ticker.id, ticker="ABBV", title=title, event_type="PDUFA",
        event_date=datetime.datetime.utcnow() + datetime.timedelta(days=days),
        impact_level="High", verified=True,
    ))
    db.commit()


def test_prune_removes_old_keeps_recent(seed_tickers, db):
    _make_event(db, "Old 120d", -120)
    _make_event(db, "Borderline 91d", -91)
    _make_event(db, "Recent 10d", -10)
    _make_event(db, "Future 30d", 30)

    prune_expired_events()

    titles = {e.title for e in db.query(CatalystEvent).all()}
    assert "Old 120d" not in titles
    assert "Borderline 91d" not in titles
    assert "Recent 10d" in titles
    assert "Future 30d" in titles


def test_prune_empty_db_ok(seed_tickers, db):
    """No events -> no crash, nothing deleted."""
    prune_expired_events()
    assert db.query(CatalystEvent).count() == 0
