"""Background scheduler that writes live prices to the PriceSnapshot table.

The dashboard reads from PriceSnapshot exclusively — no on-demand yfinance calls.
"""

import datetime
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from app.config import settings
from app.models.database import SessionLocal, Ticker, CatalystEvent, PriceSnapshot
from app.services.price_service import fetch_price_and_change

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

# Fallback prices used to seed the snapshot table on first startup
_FALLBACK_PRICES: dict[str, float] = {
    "AMGN": 366.00, "BIIB": 213.00, "GILD": 82.00, "MRNA": 69.00,
    "REGN": 1050.00, "VRTX": 486.00, "SNY": 57.00, "AZN": 78.00,
    "ALKS": 32.00, "BMRN": 82.00, "CRSP": 55.00, "EXEL": 23.00,
    "NTLA": 25.00, "SRPT": 155.00, "UTHR": 335.00, "BGNE": 185.00,
    "ACAD": 18.00, "ALLO": 4.00, "BEAM": 25.00, "EDIT": 3.00,
    "FATE": 4.50, "RXRX": 8.00, "RCKT": 17.00, "VERV": 11.00,
    "CRBU": 5.00, "DNLI": 28.00, "KURA": 20.00, "RCUS": 19.00,
    "KYMR": 43.00, "NBIX": 171.00, "IONS": 42.00,
}


def seed_snapshots():
    """On first startup, fill PriceSnapshot with fallback prices so the dashboard
    never shows empty prices.  Once the first live refresh runs, these get overwritten."""
    db = SessionLocal()
    try:
        existing = db.query(PriceSnapshot).count()
        if existing > 0:
            return  # already seeded

        now = datetime.datetime.utcnow()
        for ticker, price in _FALLBACK_PRICES.items():
            db.add(PriceSnapshot(
                ticker=ticker,
                price=price,
                change_percent=None,
                updated_at=now,
            ))
        db.commit()
        logger.info("Seeded PriceSnapshot with %d fallback prices", len(_FALLBACK_PRICES))
    except Exception as exc:
        logger.error("Failed to seed PriceSnapshot: %s", exc)
        db.rollback()
    finally:
        db.close()


def refresh_prices():
    """Fetch live prices for all tickers and upsert into PriceSnapshot.

    Runs every 5 minutes.  Uses INSERT OR REPLACE to handle the upsert.
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

        db.commit()
        logger.info("PriceSnapshot refreshed — %d tickers updated", updated)
    except Exception as exc:
        logger.error("Price refresh failed: %s", exc)
        db.rollback()
    finally:
        db.close()


def check_alerts():
    """Find unsent events within the alert window and send push notifications.

    Each event is alerted at most once — the ``alert_sent`` timestamp is
    set after a successful send so subsequent scheduler runs skip it.
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
                CatalystEvent.alert_sent.is_(None),          # not yet alerted
            )
            .order_by(CatalystEvent.event_date)
            .all()
        )

        if not events:
            return

        logger.info("Found %d unsent event(s) within %d-day alert window", len(events), settings.alert_days_before)
        from app.services.notifier import send_alert

        for ev in events:
            ticker_obj = db.query(Ticker).filter(Ticker.ticker == ev.ticker).first()
            company = ticker_obj.company_name if ticker_obj else ev.ticker
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


def start_scheduler():
    """Start background jobs."""
    if scheduler.running:
        return

    # Seed fallback prices so the dashboard never shows blanks
    seed_snapshots()

    # Price refresh every 5 minutes
    scheduler.add_job(
        refresh_prices,
        "interval",
        minutes=5,
        id="refresh_prices",
        replace_existing=True,
    )
    # Alert check at the configured interval
    scheduler.add_job(
        check_alerts,
        "interval",
        hours=settings.refresh_interval_hours,
        id="check_alerts",
        replace_existing=True,
    )
    # ClinicalTrials.gov pipeline — once daily
    from scrapers.clinical_trials import run_pipeline
    scheduler.add_job(
        run_pipeline,
        "interval",
        hours=24,
        id="clinical_trials_pipeline",
        replace_existing=True,
    )
    # PDUFA pipeline — every 60 minutes (Atom feed is very lightweight)
    from scrapers.pdufa import run_pdufa_pipeline
    scheduler.add_job(
        run_pdufa_pipeline,
        "interval",
        minutes=60,
        id="pdufa_pipeline",
        replace_existing=True,
    )
    # Run PDUFA once on startup
    scheduler.add_job(
        run_pdufa_pipeline,
        "date",
        run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=35),
        id="pdufa_pipeline_initial",
        replace_existing=True,
    )
    # Run once on startup (30s delay) to catch up on first launch
    scheduler.add_job(
        run_pipeline,
        "date",
        run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=30),
        id="clinical_trials_pipeline_initial",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — prices every 5min, alerts every %dh.", settings.refresh_interval_hours)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
