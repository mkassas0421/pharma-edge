"""Tests for the event reaction tracker (capture + stats + routes).

yfinance is never called — get_historical_prices is monkeypatched with fake
price dicts and _make_ticker with fake DataFrames, mirroring the scraper tests.
"""

import datetime

import pandas as pd
import pytest

from app.models.database import CatalystEvent, EventReaction
from app.services import price_service, reaction_service


# ── Helpers ────────────────────────────────────────────────────────────────

def _fake_history(prices: list[float], start: str) -> pd.DataFrame:
    """Build a DataFrame that mimics yfinance history() output.

    Trading days only, tz-aware America/New_York index (like real yfinance).
    """
    dates = pd.date_range(start=start, periods=len(prices), freq="B", tz="America/New_York")
    return pd.DataFrame({"Close": prices}, index=dates)


class _FakeTicker:
    """Mimics yfinance Ticker: history(start, end) returns a fixed DataFrame."""

    def __init__(self, df):
        self._df = df

    def history(self, start, end):
        return self._df


def _add_event(db, ticker="LLY", event_date=None, event_type="PDUFA", impact_level="High"):
    event = CatalystEvent(
        ticker_id=1,
        ticker=ticker,
        title=f"{ticker} test event",
        event_type=event_type,
        event_date=event_date or (datetime.datetime.utcnow() - datetime.timedelta(days=30)),
        impact_level=impact_level,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _add_reaction(db, event, status="captured", **kwargs):
    reaction = EventReaction(
        event_id=event.id,
        ticker=event.ticker,
        event_type=event.event_type,
        impact_level=event.impact_level,
        **kwargs,
    )
    reaction.status = status
    if status == "captured":
        reaction.captured_at = datetime.datetime.utcnow()
    db.add(reaction)
    db.commit()
    return reaction


# ── get_historical_prices ──────────────────────────────────────────────────

def test_historical_prices_normal(monkeypatch):
    """Anchors on the event day and offsets by position for T-1/T+1/T+5."""
    df = _fake_history([10, 11, 12, 13, 14, 15, 16, 17, 18, 19], start="2026-08-03")
    monkeypatch.setattr(price_service, "_make_ticker", lambda t: _FakeTicker(df))

    result = price_service.get_historical_prices("LLY", datetime.datetime(2026, 8, 6))
    assert result == {
        "price_before": 12.0,     # Aug 5
        "price_at_event": 13.0,   # Aug 6 (anchor)
        "price_after_1d": 14.0,   # Aug 7
        "price_after_5d": 18.0,   # Aug 13
    }


def test_historical_prices_weekend_event(monkeypatch):
    """A Saturday event anchors on the next trading day (Monday)."""
    df = _fake_history(list(range(10, 22)), start="2026-08-03")
    monkeypatch.setattr(price_service, "_make_ticker", lambda t: _FakeTicker(df))

    # 2026-08-08 is a Saturday — first trading day on/after is Monday Aug 10
    result = price_service.get_historical_prices("LLY", datetime.datetime(2026, 8, 8))
    assert result["price_at_event"] == 15.0     # Aug 10
    assert result["price_before"] == 14.0       # Aug 7 (Friday)
    assert result["price_after_1d"] == 16.0     # Aug 11
    assert result["price_after_5d"] == 20.0     # Aug 17


def test_historical_prices_empty(monkeypatch):
    """Empty DataFrame (delisted / unknown ticker) -> all None."""
    df = _fake_history([], start="2026-08-03")
    monkeypatch.setattr(price_service, "_make_ticker", lambda t: _FakeTicker(df))

    result = price_service.get_historical_prices("DEAD", datetime.datetime(2026, 8, 6))
    assert result == {"price_before": None, "price_at_event": None,
                      "price_after_1d": None, "price_after_5d": None}


def test_historical_prices_too_recent(monkeypatch):
    """Event on the last available trading day -> after prices are None."""
    df = _fake_history([10, 11, 12], start="2026-08-03")
    monkeypatch.setattr(price_service, "_make_ticker", lambda t: _FakeTicker(df))

    # 2026-08-05 is the last trading day in the data — T+1/T+5 not available
    result = price_service.get_historical_prices("LLY", datetime.datetime(2026, 8, 5))
    assert result["price_at_event"] == 12.0
    assert result["price_after_1d"] is None
    assert result["price_after_5d"] is None


def test_historical_prices_yfinance_error(monkeypatch):
    """yfinance raising -> all None, no exception propagates."""
    def boom(ticker):
        raise RuntimeError("rate limited")
    monkeypatch.setattr(price_service, "_make_ticker", boom)

    result = price_service.get_historical_prices("LLY", datetime.datetime(2026, 8, 6))
    assert result == {"price_before": None, "price_at_event": None,
                      "price_after_1d": None, "price_after_5d": None}


# ── capture_reactions_for_matured_events ───────────────────────────────────

def test_capture_captures_matured(db, seed_tickers, monkeypatch):
    """Matured event with full price window -> status captured + correct pct."""
    event = _add_event(db, event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    monkeypatch.setattr(
        reaction_service, "get_historical_prices",
        lambda ticker, event_date: {
            "price_before": 10.0, "price_at_event": 12.0,
            "price_after_1d": 13.0, "price_after_5d": 15.0,
        },
    )

    reaction_service.capture_reactions_for_matured_events()

    reaction = db.query(EventReaction).filter(EventReaction.event_id == event.id).first()
    assert reaction is not None
    assert reaction.status == "captured"
    assert reaction.ticker == "LLY"
    assert reaction.event_type == "PDUFA"
    assert reaction.impact_level == "High"
    assert reaction.price_before == 10.0
    assert reaction.reaction_1d_pct == pytest.approx(0.2)      # 12/10 - 1
    assert reaction.reaction_5d_pct == pytest.approx(0.5)      # 15/10 - 1


def test_capture_skips_future_events(db, seed_tickers, monkeypatch):
    """Event still in the future -> nothing captured."""
    _add_event(db, event_date=datetime.datetime.utcnow() + datetime.timedelta(days=30))
    monkeypatch.setattr(
        reaction_service, "get_historical_prices",
        lambda ticker, event_date: {"price_before": 10.0, "price_at_event": 12.0,
                                    "price_after_1d": 13.0, "price_after_5d": 15.0},
    )

    reaction_service.capture_reactions_for_matured_events()

    assert db.query(EventReaction).count() == 0


def test_capture_marks_failed_on_no_data(db, seed_tickers, monkeypatch):
    """No price data at all (delisted / yfinance down) -> failed, no crash."""
    event = _add_event(db, event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    monkeypatch.setattr(
        reaction_service, "get_historical_prices",
        lambda ticker, event_date: {"price_before": None, "price_at_event": None,
                                    "price_after_1d": None, "price_after_5d": None},
    )

    reaction_service.capture_reactions_for_matured_events()

    reaction = db.query(EventReaction).filter(EventReaction.event_id == event.id).first()
    assert reaction.status == "failed"


def test_capture_stays_pending_when_incomplete(db, seed_tickers, monkeypatch):
    """Only T-1/T available (too recent) -> pending, retried next cycle."""
    event = _add_event(db, event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    monkeypatch.setattr(
        reaction_service, "get_historical_prices",
        lambda ticker, event_date: {"price_before": 10.0, "price_at_event": 12.0,
                                    "price_after_1d": None, "price_after_5d": None},
    )

    reaction_service.capture_reactions_for_matured_events()

    reaction = db.query(EventReaction).filter(EventReaction.event_id == event.id).first()
    assert reaction.status == "pending"


def test_capture_skips_already_captured(db, seed_tickers, monkeypatch):
    """Already-captured events are not re-fetched."""
    event = _add_event(db, event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    _add_reaction(db, event, status="captured", reaction_1d_pct=0.1)
    calls = []

    def fake_fetch(ticker, event_date):
        calls.append(ticker)
        return {"price_before": 10.0, "price_at_event": 12.0,
                "price_after_1d": 13.0, "price_after_5d": 15.0}

    monkeypatch.setattr(reaction_service, "get_historical_prices", fake_fetch)
    reaction_service.capture_reactions_for_matured_events()

    assert calls == []  # no yfinance call attempted


# ── get_reaction_stats ─────────────────────────────────────────────────────

def test_stats_empty(db, seed_tickers):
    stats = reaction_service.get_reaction_stats(db)
    assert stats["n"] == 0
    assert stats["mean_1d_pct"] is None
    assert stats["low_sample_warning"] is True


def test_stats_low_sample_warning(db, seed_tickers):
    for _ in range(2):
        event = _add_event(db, event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
        _add_reaction(db, event, status="captured", reaction_1d_pct=0.05)

    stats = reaction_service.get_reaction_stats(db)
    assert stats["n"] == 2
    assert stats["low_sample_warning"] is True  # 2 < reaction_min_sample_size=5


def test_stats_computes_correctly(db, seed_tickers):
    """Known inputs -> mean/median/stdev/positive_rate verified."""
    import statistics
    values = [0.1, -0.2, 0.5, 0.3, 0.0]
    for v in values:
        event = _add_event(db, event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
        _add_reaction(db, event, status="captured", reaction_1d_pct=v)

    stats = reaction_service.get_reaction_stats(db)
    assert stats["n"] == 5
    assert stats["mean_1d_pct"] == pytest.approx(statistics.mean(values), abs=1e-4)
    assert stats["median_1d_pct"] == pytest.approx(statistics.median(values), abs=1e-4)
    assert stats["stdev_1d_pct"] == pytest.approx(statistics.stdev(values), abs=1e-4)
    assert stats["positive_rate_1d"] == pytest.approx(3 / 5, abs=1e-4)
    assert stats["max_1d_pct"] == 0.5
    assert stats["min_1d_pct"] == -0.2
    assert stats["low_sample_warning"] is False


def test_stats_filters(db, seed_tickers):
    """impact_level filter narrows the sample to matching rows."""
    event_high = _add_event(db, event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    event_low = _add_event(db, ticker="BMY", event_type="PHASE2_READOUT", impact_level="Low",
                           event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    _add_reaction(db, event_high, status="captured", reaction_1d_pct=0.1)
    _add_reaction(db, event_low, status="captured", reaction_1d_pct=-0.3)

    stats = reaction_service.get_reaction_stats(db, impact_level="High")
    assert stats["n"] == 1
    assert stats["mean_1d_pct"] == pytest.approx(0.1, abs=1e-4)


# ── Routes ─────────────────────────────────────────────────────────────────

def test_get_event_reaction_404(client, seed_tickers):
    resp = client.get("/api/events/999999/reaction")
    assert resp.status_code == 404


def test_get_event_reaction_200(client, db, seed_tickers):
    event = _add_event(db)
    _add_reaction(db, event, status="captured", reaction_1d_pct=0.2)

    resp = client.get(f"/api/events/{event.id}/reaction")
    assert resp.status_code == 200
    body = resp.json()
    assert body["event_id"] == event.id
    assert body["status"] == "captured"
    assert body["reaction_1d_pct"] == pytest.approx(0.2, abs=1e-4)


def test_stats_route(client, db, seed_tickers):
    event = _add_event(db)
    _add_reaction(db, event, status="captured", reaction_1d_pct=0.15)

    resp = client.get("/api/reactions/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n"] == 1
    assert body["low_sample_warning"] is True


def test_stats_route_filtered(client, db, seed_tickers):
    event_high = _add_event(db, event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    event_low = _add_event(db, ticker="BMY", impact_level="Low",
                           event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    _add_reaction(db, event_high, status="captured", reaction_1d_pct=0.1)
    _add_reaction(db, event_low, status="captured", reaction_1d_pct=-0.3)

    resp = client.get("/api/reactions/stats?impact_level=High")
    assert resp.status_code == 200
    assert resp.json()["n"] == 1


def test_stats_similar(client, db, seed_tickers):
    """Similar endpoint falls back to the market cohort when the ticker has no data."""
    event = _add_event(db, event_type="PHASE3_READOUT", impact_level="Medium",
                       event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    same = _add_event(db, ticker="CRIS", event_type="PHASE3_READOUT", impact_level="Medium",
                      event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    other = _add_event(db, ticker="BMY", event_type="PDUFA", impact_level="High",
                       event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    _add_reaction(db, same, status="captured", reaction_1d_pct=0.1)
    _add_reaction(db, other, status="captured", reaction_1d_pct=0.9)

    resp = client.get(f"/api/reactions/stats/similar/{event.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n"] == 1
    assert body["mean_1d_pct"] == pytest.approx(0.1, abs=1e-4)
    # No LLY reactions at all → last tier (market cohort) wins
    assert body["sample_source"] == "market_cohort"


def test_stats_similar_ticker_type_priority(client, db, seed_tickers):
    """Same ticker + same event type wins once it has enough samples."""
    event = _add_event(db, event_type="PDUFA", impact_level="High",
                       event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    for i in range(5):
        e = _add_event(db, ticker="LLY", event_type="PDUFA", impact_level="High",
                       event_date=datetime.datetime.utcnow() - datetime.timedelta(days=60 + i))
        _add_reaction(db, e, status="captured", reaction_1d_pct=0.1 + i * 0.01)
    # Different ticker, same type — must NOT leak into the ticker_type cohort
    other = _add_event(db, ticker="CRIS", event_type="PDUFA", impact_level="High",
                       event_date=datetime.datetime.utcnow() - datetime.timedelta(days=60))
    _add_reaction(db, other, status="captured", reaction_1d_pct=0.9)

    resp = client.get(f"/api/reactions/stats/similar/{event.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_source"] == "ticker_type"
    assert body["n"] == 5
    assert body["low_sample_warning"] is False


def test_stats_similar_ticker_fallback(client, db, seed_tickers):
    """Same ticker across types wins when ticker+type has too few samples."""
    event = _add_event(db, event_type="PDUFA", impact_level="High",
                       event_date=datetime.datetime.utcnow() - datetime.timedelta(days=30))
    # 2 PDUFA + 2 PHASE3 + 1 REGULATORY for LLY → 5 total, but only 2 PDUFA
    specs = [
        ("PDUFA", 0.1), ("PDUFA", 0.2),
        ("PHASE3_READOUT", -0.1), ("PHASE3_READOUT", 0.05),
        ("REGULATORY", 0.3),
    ]
    for i, (etype, pct) in enumerate(specs):
        e = _add_event(db, ticker="LLY", event_type=etype, impact_level="High",
                       event_date=datetime.datetime.utcnow() - datetime.timedelta(days=60 + i))
        _add_reaction(db, e, status="captured", reaction_1d_pct=pct)

    resp = client.get(f"/api/reactions/stats/similar/{event.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_source"] == "ticker"
    assert body["n"] == 5


def test_stats_similar_event_not_found(client, seed_tickers):
    resp = client.get("/api/reactions/stats/similar/999999")
    assert resp.status_code == 404
