"""Pharma Catalyst Alert System — FastAPI application entry point."""

import datetime
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

# Only show WARNING+ from third-party libraries; our app messages stay INFO
logging.basicConfig(level=logging.WARNING)
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
# Suppress noisy HTTP/network libs that yfinance triggers
for noisy in ("urllib3", "requests", "yfinance", "yfinance.utils", "yfinance.data"):
    logging.getLogger(noisy).setLevel(logging.CRITICAL)

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response

from app.config import settings
from app.models.database import init_db, SessionLocal
from data.seed_data import seed_database
from scrapers.company_map import seed_aliases

from app.routes import dashboard, tickers, events
from app.tasks.scheduler import start_scheduler, stop_scheduler


# ── Lifecycle ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    init_db()

    # Seed tickers + events if the db is empty
    db = SessionLocal()
    try:
        seed_database(db)
        seed_aliases()
    finally:
        db.close()

    # Start the background scheduler for daily price refresh + alerts
    start_scheduler()

    yield  # app runs here

    stop_scheduler()


# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Pharma Catalyst Alert System",
    version="0.1.0",
    lifespan=lifespan,
)

# Templates
templates = Jinja2Templates(directory="app/templates")

# ── Basic rate limiter (in-memory, per IP) ──
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 30     # requests per window for mutating endpoints
_rate_store: dict[str, list[float]] = defaultdict(list)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Only rate-limit mutating endpoints (POST, DELETE)
    if request.method in ("POST", "DELETE") and request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - _RATE_LIMIT_WINDOW
        # Prune old entries and count current window
        _rate_store[client_ip] = [t for t in _rate_store[client_ip] if t > window_start]
        if len(_rate_store[client_ip]) >= _RATE_LIMIT_MAX:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )
        _rate_store[client_ip].append(now)
    return await call_next(request)

# API routes
app.include_router(dashboard.router)
app.include_router(tickers.router)
app.include_router(events.router)


# ── Frontend route ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "refresh_hours": settings.refresh_interval_hours},
    )


@app.get("/health")
def health():
    from sqlalchemy import text
    try:
        from app.models.database import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


# ── Favicon ──────────────────────────────────────────────────────────────────

FAVICON_SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#22d3ee"/>
  </linearGradient></defs>
  <rect width="32" height="32" rx="8" fill="url(#g)"/>
  <text x="16" y="23" font-family="Arial,sans-serif" font-size="20" font-weight="bold" fill="#0f172a" text-anchor="middle">P</text>
</svg>'''

@app.get("/favicon.ico")
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
