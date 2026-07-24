"""Pharma Catalyst Alert System — FastAPI application entry point."""

import datetime
import logging
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
    return {"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat()}


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
