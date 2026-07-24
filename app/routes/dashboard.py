"""Dashboard API routes — returns the main dashboard by reading from PriceSnapshot.

No on-demand yfinance calls — prices come from the background scheduler's cache.
"""

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import get_db, Ticker, CatalystEvent, PriceSnapshot
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    """Return the dashboard: every ticker with its cached price and next catalyst event."""
    tickers = db.query(Ticker).order_by(Ticker.ticker).all()
    # Read all snapshots at once (one query, not N+1)
    snapshots = {
        s.ticker: s
        for s in db.query(PriceSnapshot).all()
    }
    now = datetime.datetime.utcnow()

    rows: list[dict] = []
    for t in tickers:
        snap = snapshots.get(t.ticker)

        next_event = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.ticker == t.ticker,
                CatalystEvent.event_date >= now,
            )
            .order_by(CatalystEvent.event_date)
            .first()
        )

        days_until = None
        if next_event:
            delta = next_event.event_date - now
            days_until = delta.days

        rows.append({
            "ticker": t.ticker,
            "company_name": t.company_name,
            "current_price": snap.price if snap else None,
            "price_change_pct": snap.change_percent if snap else None,
            "next_event_id": next_event.id if next_event else None,
            "next_event_title": next_event.title if next_event else None,
            "next_event_date": next_event.event_date.isoformat() if next_event else None,
            "next_event_type": next_event.event_type if next_event else None,
            "impact_level": next_event.impact_level if next_event else None,
            "days_until_event": days_until,
            "next_event_description": next_event.description if next_event else None,
        })

    return {"rows": rows, "generated_at": now.isoformat()}


@router.get("/dashboard/stats")
def get_stats(db: Session = Depends(get_db)):
    """Return summary statistics for the dashboard header."""
    now = datetime.datetime.utcnow()
    alert_window = now + datetime.timedelta(days=settings.alert_days_before)

    total = db.query(func.count(Ticker.id)).scalar() or 0
    upcoming = (
        db.query(func.count(CatalystEvent.id))
        .filter(CatalystEvent.event_date >= now)
        .scalar()
        or 0
    )
    alerting = (
        db.query(func.count(CatalystEvent.id))
        .filter(
            CatalystEvent.event_date >= now,
            CatalystEvent.event_date <= alert_window,
        )
        .scalar()
        or 0
    )

    return {
        "total_tickers": total,
        "upcoming_events": upcoming,
        "alerting_events": alerting,
    }


@router.post("/test-notify")
def test_notification(
    ticker: str = "VRTX",
    title: str = "TEST: FDA Advisory Committee — VX-548 (pain)",
    days: int = 5,
    impact: str = "High",
    db: Session = Depends(get_db),
):
    """Send a test alert to verify Telegram/Discord configuration."""
    from app.services.notifier import send_alert
    from app.models.database import Ticker as TickerModel

    ticker_obj = db.query(TickerModel).filter(TickerModel.ticker == ticker.upper()).first()
    company = ticker_obj.company_name if ticker_obj else ticker.upper()
    now = datetime.datetime.utcnow()

    ok = send_alert(
        ticker=ticker.upper(),
        company=company,
        title=title,
        event_type="TEST",
        event_date=(now + datetime.timedelta(days=days)).strftime("%b %d, %Y"),
        days_until=days,
        impact=impact,
        description=f"This is a test alert for {ticker}. If you receive this, your notification channel is configured correctly.",
    )

    if not ok:
        raise HTTPException(
            status_code=400,
            detail="No notification channel configured. Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID or DISCORD_WEBHOOK_URL in .env",
        )

    return {"status": "sent", "channel": "telegram/discord"}


@router.get("/notify-status")
def notify_status():
    """Return which notification channels are configured."""
    return {
        "telegram": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "discord_legacy": bool(settings.discord_webhook_url),
        "high_impact": bool(settings.discord_webhook_high_impact),
        "sec_live": bool(settings.discord_webhook_sec_live),
        "briefing": bool(settings.discord_webhook_briefing),
        "clinical": bool(settings.discord_webhook_clinical),
        "news_feed": bool(settings.discord_webhook_news),
    }
