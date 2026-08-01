"""API CRUD: tickers and events, with API key + validation behaviour."""

import datetime

from app.models.database import CatalystEvent, PriceSnapshot, Ticker, TickerAlias


# ── Tickers ────────────────────────────────────────────────────────────────

def test_create_ticker(seed_tickers, client, auth_headers):
    r = client.post("/api/tickers", headers=auth_headers, json={
        "ticker": "NEWT", "company_name": "NewT Corp.", "sector": "Biotech",
    })
    assert r.status_code == 201
    assert r.json()["ticker"] == "NEWT"


def test_create_duplicate_ticker_409(seed_tickers, client, auth_headers):
    r = client.post("/api/tickers", headers=auth_headers, json={
        "ticker": "ABBV", "company_name": "AbbVie Inc.", "sector": "Biotech",
    })
    assert r.status_code == 409


def test_delete_ticker_cascades(seed_tickers, db, client, auth_headers):
    ticker = db.query(Ticker).filter_by(ticker="LLY").first()
    db.add(CatalystEvent(ticker_id=ticker.id, ticker="LLY", title="E",
                         event_type="PDUFA",
                         event_date=datetime.datetime.utcnow() + datetime.timedelta(days=5),
                         impact_level="High", verified=True))
    db.add(PriceSnapshot(ticker="LLY", price=700.0, change_percent=0.0,
                         updated_at=datetime.datetime.utcnow()))
    db.add(TickerAlias(ticker_id=ticker.id, alias="Eli Lilly and Company"))
    db.commit()

    r = client.delete("/api/tickers/LLY", headers=auth_headers)
    assert r.status_code == 204
    assert db.query(Ticker).filter_by(ticker="LLY").count() == 0
    assert db.query(CatalystEvent).filter_by(ticker="LLY").count() == 0
    assert db.query(PriceSnapshot).filter_by(ticker="LLY").count() == 0


def test_delete_missing_ticker_404(seed_tickers, client, auth_headers):
    assert client.delete("/api/tickers/ZZZZ", headers=auth_headers).status_code == 404


def test_list_tickers(seed_tickers, client):
    r = client.get("/api/tickers")
    assert r.status_code == 200
    symbols = {t["ticker"] for t in r.json()}
    assert {"ABBV", "LLY", "CRIS", "BMY"} <= symbols


# ── Events ─────────────────────────────────────────────────────────────────

def test_create_event(seed_tickers, client, auth_headers):
    r = client.post("/api/events", headers=auth_headers, json={
        "ticker": "LLY", "title": "PDUFA for new drug", "event_type": "PDUFA",
        "event_date": (datetime.datetime.utcnow() + datetime.timedelta(days=15)).isoformat(),
        "impact_level": "High",
    })
    assert r.status_code == 201
    assert r.json()["ticker"] == "LLY"


def test_create_event_unknown_ticker_404(seed_tickers, client, auth_headers):
    r = client.post("/api/events", headers=auth_headers, json={
        "ticker": "NOPE", "title": "X", "event_type": "PDUFA",
        "event_date": (datetime.datetime.utcnow() + datetime.timedelta(days=15)).isoformat(),
    })
    assert r.status_code == 404


def test_delete_event(seed_tickers, db, client, auth_headers):
    ticker = db.query(Ticker).filter_by(ticker="ABBV").first()
    ev = CatalystEvent(ticker_id=ticker.id, ticker="ABBV", title="To delete",
                       event_type="PDUFA",
                       event_date=datetime.datetime.utcnow() + datetime.timedelta(days=5),
                       impact_level="High", verified=True)
    db.add(ev)
    db.commit()

    r = client.delete(f"/api/events/{ev.id}", headers=auth_headers)
    assert r.status_code == 204
    assert db.query(CatalystEvent).filter_by(id=ev.id).count() == 0


def test_delete_missing_event_404(seed_tickers, client, auth_headers):
    assert client.delete("/api/events/999999", headers=auth_headers).status_code == 404


def test_list_events_upcoming_filter(seed_tickers, db, client):
    ticker = db.query(Ticker).filter_by(ticker="ABBV").first()
    now = datetime.datetime.utcnow()
    db.add_all([
        CatalystEvent(ticker_id=ticker.id, ticker="ABBV", title="Upcoming",
                      event_type="PDUFA", event_date=now + datetime.timedelta(days=5),
                      impact_level="High", verified=True),
        CatalystEvent(ticker_id=ticker.id, ticker="ABBV", title="Past",
                      event_type="PHASE2_READOUT", event_date=now - datetime.timedelta(days=10),
                      impact_level="Medium", verified=True),
    ])
    db.commit()

    upcoming = client.get("/api/events").json()
    assert [e["title"] for e in upcoming] == ["Upcoming"]
    all_events = client.get("/api/events?upcoming_only=false").json()
    assert {e["title"] for e in all_events} == {"Upcoming", "Past"}


# ── Auth on mutating endpoints ─────────────────────────────────────────────

def test_mutating_endpoints_require_key(seed_tickers, client):
    assert client.post("/api/tickers", json={}).status_code == 401
    assert client.post("/api/events", json={}).status_code == 401
    assert client.delete("/api/tickers/ABBV").status_code == 401
