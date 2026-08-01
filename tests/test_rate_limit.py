"""Rate limiter: 30 POST/DELETE per 60s per real IP (X-Forwarded-For)."""


def test_429_after_30_valid_posts(client, auth_headers):
    codes = set()
    for _ in range(32):
        r = client.post("/api/tickers", json={"ticker": "X1", "company_name": "X"}, headers=auth_headers)
        codes.add(r.status_code)
    assert 429 in codes


def test_x_forwarded_for_fresh_bucket(client, auth_headers):
    # Fill the bucket for the default (socket) IP
    for _ in range(32):
        client.post("/api/tickers", json={"ticker": "X2", "company_name": "X"}, headers=auth_headers)
    # A different X-Forwarded-For IP has its own bucket
    r = client.post(
        "/api/tickers",
        json={"ticker": "X3", "company_name": "X"},
        headers={**auth_headers, "X-Forwarded-For": "203.0.113.99"},
    )
    assert r.status_code == 201


def test_get_requests_not_limited(client):
    for _ in range(50):
        r = client.get("/api/tickers")
        assert r.status_code == 200


def test_same_ip_shares_bucket(client, auth_headers):
    """Two requests from the same forwarded IP count toward one bucket."""
    headers = {**auth_headers, "X-Forwarded-For": "198.51.100.7"}
    codes = set()
    for _ in range(31):
        r = client.post("/api/tickers", json={"ticker": "X4", "company_name": "X"}, headers=headers)
        codes.add(r.status_code)
    assert 429 in codes
