"""In-memory per-IP rate limiter for mutating API endpoints."""

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

_WINDOW = 60          # seconds
_MAX_HITS = 30        # max requests per window for POST/DELETE
_CLEANUP_EVERY = 100  # prune stale entries every N requests
_store: dict[str, list[float]] = defaultdict(list)
_request_count = 0


def _client_ip(request: Request) -> str:
    """Return the real client IP.

    Behind Render's reverse proxy ``request.client.host`` is the proxy's
    internal address — every user would share one bucket, so a single
    busy client could exhaust the global limit. Use the first
    ``X-Forwarded-For`` entry instead (Render always sets it); fall back
    to the socket address for local development.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _prune_stale(now: float) -> None:
    """Drop IPs whose every timestamp has expired (bounds memory growth)."""
    cutoff = now - _WINDOW
    for ip in [ip for ip, hits in _store.items() if not any(t > cutoff for t in hits)]:
        del _store[ip]


async def rate_limit_middleware(request: Request, call_next):
    """Reject ``POST`` and ``DELETE`` API calls exceeding the rate limit."""
    global _request_count
    if request.method in ("POST", "DELETE") and request.url.path.startswith("/api/"):
        client_ip = _client_ip(request)
        now = time.time()
        cutoff = now - _WINDOW

        _request_count += 1
        if _request_count % _CLEANUP_EVERY == 0:
            _prune_stale(now)

        _store[client_ip] = [t for t in _store[client_ip] if t > cutoff]
        if len(_store[client_ip]) >= _MAX_HITS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )
        _store[client_ip].append(now)
    return await call_next(request)
