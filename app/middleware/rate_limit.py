"""In-memory per-IP rate limiter for mutating API endpoints."""

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

_WINDOW = 60       # seconds
_MAX_HITS = 30     # max requests per window for POST/DELETE
_store: dict[str, list[float]] = defaultdict(list)


async def rate_limit_middleware(request: Request, call_next):
    """Reject ``POST`` and ``DELETE`` API calls exceeding the rate limit."""
    if request.method in ("POST", "DELETE") and request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - _WINDOW
        _store[client_ip] = [t for t in _store[client_ip] if t > cutoff]
        if len(_store[client_ip]) >= _MAX_HITS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )
        _store[client_ip].append(now)
    return await call_next(request)
