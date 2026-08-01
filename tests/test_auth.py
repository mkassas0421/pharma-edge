"""API-key middleware: mutating endpoints require X-API-Key, GET stays public."""

from app.config import settings


def test_no_key_gets_401(client):
    r = client.post("/api/tickers", json={"ticker": "TEST", "company_name": "Test Inc."})
    assert r.status_code == 401


def test_wrong_key_gets_401(client):
    r = client.post("/api/tickers", json={}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_correct_key_reaches_route(client, auth_headers):
    r = client.post(
        "/api/tickers",
        json={"ticker": "TEST", "company_name": "Test Inc."},
        headers=auth_headers,
    )
    assert r.status_code == 201


def test_get_endpoints_stay_public(client):
    assert client.get("/api/tickers").status_code == 200
    assert client.get("/api/dashboard").status_code == 200
    assert client.get("/health").status_code == 200


def test_unauth_flood_never_429(client):
    """Auth runs before the rate limiter: 35 unauth'd POSTs must all be 401."""
    statuses = {client.post("/api/tickers", json={}).status_code for _ in range(35)}
    assert statuses == {401}


def test_fail_closed_when_key_unset(client, monkeypatch):
    """No API_KEY configured -> mutating endpoints disabled (503)."""
    monkeypatch.setattr(settings, "api_key", "")
    r = client.post("/api/tickers", json={"ticker": "TEST", "company_name": "X"})
    assert r.status_code == 503
