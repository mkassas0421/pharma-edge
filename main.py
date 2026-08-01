"""Pharma Catalyst Alert System — FastAPI application entry point."""

import datetime
import logging

# Only show WARNING+ from third-party libraries; our app messages stay INFO
logging.basicConfig(level=logging.WARNING)
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
# Suppress noisy HTTP/network libs that yfinance triggers
for noisy in ("urllib3", "requests", "yfinance", "yfinance.utils", "yfinance.data"):
    logging.getLogger(noisy).setLevel(logging.CRITICAL)

logger = logging.getLogger(__name__)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response

from app.config import settings
from app.middleware.auth import api_key_middleware
from app.middleware.rate_limit import rate_limit_middleware
from app.models.database import init_db, SessionLocal
from data.seed_data import seed_database
from scrapers.company_map import seed_aliases
from scripts.cleanup_fabricated_events import cleanup as cleanup_fabricated
from scripts.backfill_source_urls import backfill as backfill_source_urls

from app.routes import dashboard, tickers, events
from app.tasks.scheduler import start_scheduler, stop_scheduler


# ── Lifecycle ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    init_db()

    # Remove any fabricated (AI-generated) events, then seed tickers only —
    # catalyst events now come exclusively from official government sources.
    db = SessionLocal()
    try:
        cleaned = cleanup_fabricated(db)
        if cleaned:
            logger.info("Removed %d fabricated event(s)", cleaned)
        seed_database(db)
        seed_aliases()
    finally:
        db.close()

    # Attach official source links to existing real events (idempotent)
    backfill_source_urls()

    # Start the background scheduler for daily price refresh + alerts
    start_scheduler()

    yield  # app runs here

    stop_scheduler()


# ── Error tracking (Sentry) — only active when SENTRY_DSN is set ───────────

if settings.sentry_dsn:
    import sentry_sdk


    def _before_send(event, hint):
        """Drop expected client-rejection noise (401/429) — not app bugs."""
        exc_info = hint.get("exc_info")
        if exc_info:
            exc = exc_info[1]
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            if status in (401, 429):
                return None
        return event


    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.0,  # errors only — keeps the free tier generous
        environment="production",
        before_send=_before_send,
    )
    logger.info("Sentry error tracking enabled")


# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Pharma Catalyst Alert System",
    version="0.1.0",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="app/templates")

# In Starlette the LAST registered middleware is the OUTERMOST (runs first),
# so auth goes last: unauthenticated mutating calls get 401 before the rate
# limiter can count them toward the shared bucket.
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(api_key_middleware)

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

    # Report when the background jobs are next due — uptime monitors can see
    # whether the scheduler is alive, not just the HTTP layer.
    jobs_info = {}
    try:
        from app.tasks.scheduler import scheduler
        jobs_info = {
            job.id: job.next_run_time.isoformat() if job.next_run_time else None
            for job in scheduler.get_jobs()
        }
    except Exception:
        pass  # scheduler not started yet / introspection unavailable — non-fatal

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "scheduler_jobs": jobs_info,
    }


# ── Favicon ─────────────────────────────────────────────────────────────────

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
