"""Dashboard: N+1 eliminated (3 bulk queries), TTL cache, invalidation."""

import datetime

from sqlalchemy import event as sa_event

from app.models.database import CatalystEvent, PriceSnapshot, engine


def _query_counter():
    """Count SQL statements executed against the engine."""
    state = {"n": 0}

    @sa_event.listens_for(engine, "before_cursor_execute")
    def _count(_conn, _cursor, _statement, _params, _context, _executemany):
        state["n"] += 1

    def reset():
        state["n"] = 0

    return state, reset


def test_dashboard_uses_3_queries_not_n1(seed_tickers, client):
    _state, reset = _query_counter()
    reset()
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    assert _state["n"] == 3, f"expected 3 queries, got {_state['n']}"
    assert len(r.json()["rows"]) == len(seed_tickers)


def test_dashboard_cached_second_call(seed_tickers, client):
    _state, reset = _query_counter()
    first = client.get("/api/dashboard")
    reset()
    second = client.get("/api/dashboard")
    assert _state["n"] == 0, "second call should come from the TTL cache"
    assert second.json() == first.json()


def test_next_event_is_earliest_future(seed_tickers, db, client):
    now = datetime.datetime.utcnow()
    abbv = db.query(type(seed_tickers[0])).filter_by(ticker="ABBV").first()
    db.add_all([
        CatalystEvent(ticker_id=abbv.id, ticker="ABBV", title="Later event",
                      event_type="PHASE3_READOUT", event_date=now + datetime.timedelta(days=40),
                      impact_level="High", verified=True),
        CatalystEvent(ticker_id=abbv.id, ticker="ABBV", title="Soon event",
                      event_type="PDUFA", event_date=now + datetime.timedelta(days=10),
                      impact_level="High", verified=True),
    ])
    db.commit()

    rows = {row["ticker"]: row for row in client.get("/api/dashboard").json()["rows"]}
    assert rows["ABBV"]["next_event_title"] == "Soon event"
    # The dashboard's "now" is slightly later than the test's, so the
    # truncated day count can be 9 — the important part is it is NOT the
    # 40-day event.
    assert 1 <= rows["ABBV"]["days_until_event"] <= 10


def test_past_event_ignored(seed_tickers, db, client):
    now = datetime.datetime.utcnow()
    lly = db.query(type(seed_tickers[0])).filter_by(ticker="LLY").first()
    db.add(CatalystEvent(ticker_id=lly.id, ticker="LLY", title="Past",
                         event_type="PHASE2_READOUT",
                         event_date=now - datetime.timedelta(days=30),
                         impact_level="Medium", verified=True))
    db.commit()

    rows = {row["ticker"]: row for row in client.get("/api/dashboard").json()["rows"]}
    assert rows["LLY"]["next_event_id"] is None


def test_price_from_snapshot(seed_tickers, db, client):
    db.add(PriceSnapshot(ticker="ABBV", price=150.0, change_percent=1.5,
                         updated_at=datetime.datetime.utcnow()))
    db.commit()
    rows = {row["ticker"]: row for row in client.get("/api/dashboard").json()["rows"]}
    assert rows["ABBV"]["current_price"] == 150.0
    assert rows["ABBV"]["price_change_pct"] == 1.5


def test_mutation_invalidates_cache(seed_tickers, client, auth_headers):
    client.get("/api/dashboard")  # warm the cache
    r = client.post("/api/events", headers=auth_headers, json={
        "ticker": "LLY", "title": "New event", "event_type": "PDUFA",
        "event_date": (datetime.datetime.utcnow() + datetime.timedelta(days=20)).isoformat(),
        "impact_level": "High",
    })
    assert r.status_code == 201
    rows = {row["ticker"]: row for row in client.get("/api/dashboard").json()["rows"]}
    assert rows["LLY"]["next_event_title"] == "New event"


def test_stats_endpoint_cached(seed_tickers, client):
    _state, reset = _query_counter()
    reset()
    first = client.get("/api/dashboard/stats")
    assert first.status_code == 200
    assert first.json()["total_tickers"] == len(seed_tickers)
    reset()
    client.get("/api/dashboard/stats")
    assert _state["n"] == 0, "stats should be cached on second call"
