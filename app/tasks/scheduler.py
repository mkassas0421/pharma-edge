"""Background scheduler that writes live prices to the PriceSnapshot table.

The dashboard reads from PriceSnapshot exclusively — no on-demand yfinance calls.
"""

import datetime
import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.models.database import SessionLocal, Ticker, CatalystEvent, PriceSnapshot, EventReaction
from app.services.price_service import fetch_price_and_change
from app.utils.cache import dashboard_cache, stats_cache
from data.fallback_prices import FALLBACK_PRICES

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


# ── Price snapshot seeding / refresh ──────────────────────────────────────

def seed_snapshots():
    """Fill PriceSnapshot for ALL tickers.

    Known tickers (with fallback prices) get their real value; the rest get
    ``None`` so live prices fill in as yfinance data arrives on subsequent
    5-minute cycles.
    """
    db = SessionLocal()
    try:
        ticker_rows = db.query(Ticker).all()
        if not ticker_rows:
            return

        existing_tickers = {s.ticker for s in db.query(PriceSnapshot).all()}
        now = datetime.datetime.utcnow()
        added = 0

        for t in ticker_rows:
            if t.ticker not in existing_tickers:
                db.add(PriceSnapshot(
                    ticker=t.ticker,
                    price=FALLBACK_PRICES.get(t.ticker),
                    change_percent=None,
                    updated_at=now,
                ))
                added += 1

        if added:
            db.commit()
            logger.info("Seeded PriceSnapshot with %d entries", added)
    except Exception as exc:
        logger.error("Failed to seed PriceSnapshot: %s", exc)
        db.rollback()
    finally:
        db.close()


def refresh_prices():
    """Fetch live prices for all tickers and upsert into PriceSnapshot.

    Runs every 5 minutes with a small delay between tickers to avoid Yahoo
    rate limits on cloud hosts.
    """
    db = SessionLocal()
    try:
        tickers = [t.ticker for t in db.query(Ticker).all()]
        if not tickers:
            logger.debug("No tickers to refresh.")
            return

        now = datetime.datetime.utcnow()
        updated = 0

        for ticker in tickers:
            price, change = fetch_price_and_change(ticker)

            # If yfinance failed, keep the existing DB value
            if price is None:
                existing = db.query(PriceSnapshot).filter(PriceSnapshot.ticker == ticker).first()
                if existing:
                    continue

            # Upsert: delete existing row then insert fresh
            db.query(PriceSnapshot).filter(PriceSnapshot.ticker == ticker).delete()
            db.add(PriceSnapshot(
                ticker=ticker,
                price=price,
                change_percent=change,
                updated_at=now,
            ))
            updated += 1

            # Short delay between tickers to avoid Yahoo rate limiting
            time.sleep(0.5)

        db.commit()
        if updated:
            dashboard_cache.invalidate_all()  # prices changed — drop cached dashboard
        logger.info("PriceSnapshot refreshed — %d tickers updated", updated)
    except Exception as exc:
        logger.error("Price refresh failed: %s", exc)
        db.rollback()
    finally:
        db.close()


# ── Alert checking ────────────────────────────────────────────────────────

def check_alerts():
    """Find unsent events within the alert window and send push notifications.

    Each event is alerted at most once — the ``alert_sent`` timestamp is set
    after a successful send so subsequent scheduler runs skip it.
    """
    now = datetime.datetime.utcnow()
    window = now + datetime.timedelta(days=settings.alert_days_before)

    db = SessionLocal()
    try:
        events = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.event_date >= now,
                CatalystEvent.event_date <= window,
                CatalystEvent.alert_sent.is_(None),
            )
            .order_by(CatalystEvent.event_date)
            .all()
        )

        if not events:
            return

        from app.services.notifier import send_alert

        logger.info("Found %d unsent event(s) within %d-day alert window", len(events), settings.alert_days_before)

        # Pre-fetch company names in one query (avoids N+1 per event)
        symbols = [ev.ticker for ev in events]
        company_map = {
            t.ticker: t.company_name
            for t in db.query(Ticker).filter(Ticker.ticker.in_(symbols)).all()
        }

        for ev in events:
            company = company_map.get(ev.ticker, ev.ticker)
            days_until = (ev.event_date - now).days

            ok = send_alert(
                ticker=ev.ticker,
                company=company,
                title=ev.title,
                event_type=ev.event_type,
                event_date=ev.event_date.strftime("%b %d, %Y"),
                days_until=days_until,
                impact=ev.impact_level,
                description=ev.description or "",
            )

            if ok:
                ev.alert_sent = now
                logger.info("Alert sent + marked for %s — %s", ev.ticker, ev.title[:50])
            else:
                logger.warning("Alert NOT sent for %s — %s (no channel configured?)", ev.ticker, ev.title[:50])

        db.commit()
    except Exception as exc:
        logger.error("Alert check failed: %s", exc)
        db.rollback()
    finally:
        db.close()


# ── Expired event cleanup ────────────────────────────────────────────────

def prune_expired_events():
    """Delete dead-weight catalyst events — everything with a reaction stays.

    Every event that ever received an EventReaction row (pending, failed or
    captured) is kept forever: the historical backfill and the per-ticker
    reaction history ARE the product, and the denormalised reaction row
    exists so stats survive even though the event row itself is the record.
    Only events older than a year that never got a reaction (import
    artefacts yfinance could not price, or events the capture job never
    reached) are dead weight and get deleted. Runs daily; old events never
    re-alert (alert_sent is set on send).
    """
    ANCIENT_AFTER_DAYS = 365
    ancient_cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=ANCIENT_AFTER_DAYS)

    db = SessionLocal()
    try:
        reacted_ids = (
            db.query(EventReaction.event_id)
            .subquery()
        )
        deleted = (
            db.query(CatalystEvent)
            .filter(CatalystEvent.event_date < ancient_cutoff)
            .filter(~CatalystEvent.id.in_(reacted_ids))
            .delete(synchronize_session="fetch")
        )
        db.commit()
        if deleted:
            dashboard_cache.invalidate_all()
            stats_cache.invalidate_all()
            logger.info("Pruned %d dead-weight event(s) (older than %d days, no reaction)", deleted, ANCIENT_AFTER_DAYS)
    except Exception as exc:
        logger.error("Event pruning failed: %s", exc)
        db.rollback()
    finally:
        db.close()


# ── Scheduler lifecycle ───────────────────────────────────────────────────

def start_scheduler():
    """Start background jobs."""
    if scheduler.running:
        return

    # Seed fallback prices so the dashboard never shows blanks
    seed_snapshots()

    # Price refresh every 5 minutes
    scheduler.add_job(refresh_prices, "interval", minutes=5, id="refresh_prices", replace_existing=True)

    # Alert check at the configured interval
    scheduler.add_job(check_alerts, "interval", hours=settings.refresh_interval_hours, id="check_alerts", replace_existing=True)

    # Scrapers — imported here to avoid circular imports at module level
    from scrapers.clinical_trials import run_pipeline as ct_pipeline
    from scrapers.pdufa import run_pdufa_pipeline
    from scrapers.sec_filings import run_sec_feed
    from scrapers.news_feed import run_news_feed
    from scrapers.federal_register import run_federal_register_pipeline
    from scrapers.fda_adcom import run_fda_adcom_pipeline
    from app.services.notifier import send_morning_briefing, send_evening_briefing
    from app.services.reaction_service import capture_reactions_for_matured_events

    scheduler.add_job(ct_pipeline, "interval", hours=24, id="clinical_trials_pipeline", replace_existing=True)
    scheduler.add_job(run_pdufa_pipeline, "interval", minutes=60, id="pdufa_pipeline", replace_existing=True)
    scheduler.add_job(run_sec_feed, "interval", minutes=30, id="sec_feed", replace_existing=True)
    scheduler.add_job(run_news_feed, "interval", minutes=60, id="news_feed", replace_existing=True)
    scheduler.add_job(run_federal_register_pipeline, "interval", hours=12, id="federal_register_pipeline", replace_existing=True)
    scheduler.add_job(run_fda_adcom_pipeline, "interval", hours=24, id="fda_adcom_pipeline", replace_existing=True)
    scheduler.add_job(prune_expired_events, "interval", hours=24, id="prune_events", replace_existing=True)
    scheduler.add_job(capture_reactions_for_matured_events, "interval", hours=24, id="capture_event_reactions", replace_existing=True)

    # ── Run-once on startup (with slight delays to spread load) ──
    scheduler.add_job(run_pdufa_pipeline, "date", run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=35), id="pdufa_pipeline_initial", replace_existing=True)
    scheduler.add_job(ct_pipeline, "date", run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=30), id="clinical_trials_pipeline_initial", replace_existing=True)
    scheduler.add_job(run_federal_register_pipeline, "date", run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=45), id="federal_register_pipeline_initial", replace_existing=True)
    scheduler.add_job(run_fda_adcom_pipeline, "date", run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=55), id="fda_adcom_pipeline_initial", replace_existing=True)
    # Reaction capture runs after the above — the first backfill (~600 events)
    # must not collide with the startup pipelines
    scheduler.add_job(capture_reactions_for_matured_events, "date", run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=65), id="capture_event_reactions_initial", replace_existing=True)

    # ── Daily briefings ──
    if settings.discord_webhook_briefing:
        try:
            import pytz  # type: ignore
            tz = pytz.timezone(settings.timezone)
        except Exception:
            tz = None
        scheduler.add_job(send_morning_briefing, "cron", hour=8, minute=30, timezone=tz, id="morning_briefing", replace_existing=True)
        scheduler.add_job(send_evening_briefing, "cron", hour=21, minute=0, timezone=tz, id="evening_briefing", replace_existing=True)
        logger.info("Daily briefings scheduled (08:30 / 21:00 %s).", settings.timezone if tz else "UTC")

    scheduler.start()
    logger.info("Scheduler started — prices 5m, alerts %dh, briefings daily.", settings.refresh_interval_hours)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
