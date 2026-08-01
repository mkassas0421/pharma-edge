"""API-key authentication for mutating API endpoints.

Read-only endpoints (GET) stay public — the dashboard is meant to be
viewed by anyone with the link. Creating/deleting tickers and events
requires the ``X-API-Key`` header.

If the server has no ``API_KEY`` configured, mutating endpoints are
disabled entirely (fail closed) rather than silently left open.
"""

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings

_PROTECTED_METHODS = {"POST", "DELETE", "PUT", "PATCH"}
_PROTECTED_PREFIXES = ("/api/tickers", "/api/events", "/api/test-notify")


async def api_key_middleware(request: Request, call_next):
    """Reject mutating API calls without a valid API key."""
    if request.method in _PROTECTED_METHODS and request.url.path.startswith(_PROTECTED_PREFIXES):
        if not settings.api_key:
            return JSONResponse(
                status_code=503,
                content={"detail": "API_KEY not configured on the server — mutating endpoints are disabled."},
            )
        key = request.headers.get("X-API-Key", "")
        if not key or not secrets.compare_digest(key, settings.api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid API key. Provide the X-API-Key header."},
            )
    return await call_next(request)
