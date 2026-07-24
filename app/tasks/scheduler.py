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
    "ABBV": 259.0,
    "BMY": 62.24,
    "JNJ": 262.86,
    "LLY": 1201.93,
    "MRK": 131.16,
    "NVS": 155.38,
    "NVO": 48.98,
    "PFE": 24.64,
    "SNY": 43.36,
    "TAK": 17.26,
    "ACAD": 24.71,
    "ACIU": 2.22,
    "ADMA": 8.2,
    "ADPT": 22.27,
    "ALEC": 1.5,
    "ALKS": 52.93,
    "ALLO": 1.79,
    "ALNY": 275.17,
    "ALT": 2.8,
    "AMLX": 17.93,
    "ANAB": 53.81,
    "ANNX": 5.29,
    "ARDX": 5.05,
    "ARQT": 27.46,
    "ARVN": 8.08,
    "ARWR": 85.76,
    "ATRA": 8.09,
    "ATYR": 0.48,
    "AUPH": 15.32,
    "AVIR": 4.81,
    "AXSM": 240.69,
    "BBIO": 84.73,
    "BCAB": 3.25,
    "BCRX": 9.43,
    "BCYC": 3.95,
    "BEAM": 25.58,
    "BHVN": 14.35,
    "BIIB": 202.68,
    "BMRN": 59.28,
    "BTAI": 0.86,
    "CAPR": 19.47,
    "CGEM": 17.43,
    "CGEN": 2.29,
    "CGON": 69.89,
    "CHRS": 1.42,
    "CLDX": 35.15,
    "CMPX": 2.13,
    "CORT": 95.1,
    "CRBU": 1.61,
    "CRIS": 4.95,
    "CRSP": 46.88,
    "CRVS": 13.28,
    "CTMX": 3.21,
    "CYTK": 81.5,
    "DNLI": 22.93,
    "DNTH": 104.36,
    "DYN": 24.5,
    "EDIT": 2.67,
    "ELVN": 53.36,
    "ENTA": 12.89,
    "ERAS": 19.53,
    "EWTX": 40.61,
    "EXEL": 55.49,
    "EYPT": 12.26,
    "FATE": 2.45,
    "FDMT": 10.21,
    "FHTX": 4.91,
    "FULC": 3.76,
    "GERN": 1.44,
    "GILD": 130.02,
    "GMAB": 28.8,
    "GPCR": 49.81,
    "HALO": 82.13,
    "HCM": 11.01,
    "HRMY": 35.32,
    "HRTX": 0.46,
    "IBRX": 7.18,
    "IDYA": 35.94,
    "IMCR": 35.01,
    "IMNM": 22.24,
    "IMTX": 9.12,
    "INCY": 118.06,
    "INO": 0.97,
    "INSM": 106.57,
    "IONS": 57.15,
    "IOVA": 5.07,
    "IRON": 75.14,
    "JANX": 15.34,
    "JAZZ": 255.0,
    "KALA": 0.66,
    "KNSA": 62.96,
    "KOD": 42.22,
    "KPTI": 7.26,
    "KRYS": 335.04,
    "KURA": 10.21,
    "KYMR": 111.19,
    "LCTX": 1.05,
    "LGND": 300.73,
    "LPCN": 2.17,
    "LXRX": 2.32,
    "LYEL": 12.65,
    "MCRB": 5.09,
    "MDGL": 546.05,
    "MESO": 15.36,
    "MGTX": 11.91,
    "MIRM": 113.13,
    "MLYS": 26.9,
    "MRKR": 1.31,
    "MRNA": 54.48,
    "NAMS": 30.68,
    "NBIX": 176.01,
    "NKTR": 71.3,
    "NMRA": 1.52,
    "NRXP": 3.87,
    "NTLA": 10.95,
    "NVAX": 7.53,
    "OCEA": 0.0,
    "OCGN": 1.24,
    "OCUL": 8.62,
    "OLMA": 11.77,
    "OMER": 10.04,
    "ONCO": 0.87,
    "ONCY": 0.82,
    "OPK": 1.23,
    "ORIC": 12.32,
    "ORMP": 4.08,
    "PASG": 4.8,
    "PBYI": 8.08,
    "PCRX": 25.83,
    "PDSB": 0.69,
    "PEPG": 2.07,
    "PGEN": 5.43,
    "PHAR": 12.57,
    "PHAT": 11.5,
    "PHVS": 33.97,
    "PLRX": 1.1,
    "PLX": 2.37,
    "PMVP": 1.24,
    "PRLD": 3.88,
    "PRME": 2.99,
    "PROK": 1.54,
    "PRQR": 1.73,
    "PRTA": 8.76,
    "PTCT": 78.14,
    "PTGX": 136.29,
    "PYXS": 2.71,
    "QTTB": 15.28,
    "QURE": 38.5,
    "RARE": 26.93,
    "RCKT": 3.24,
    "RCUS": 28.86,
    "REGN": 665.67,
    "REPL": 10.0,
    "RGNX": 9.76,
    "RLAY": 18.58,
    "RLMD": 5.14,
    "RLYB": 16.27,
    "RNA": 11.76,
    "RNAC": 7.96,
    "ROIV": 35.37,
    "RVMD": 189.74,
    "RXRX": 3.02,
    "RYTM": 104.46,
    "RZLT": 5.01,
    "SABS": 3.52,
    "SANA": 3.2,
    "SIGA": 3.12,
    "SLDB": 7.93,
    "SLGL": 80.9,
    "SLN": 11.12,
    "SMMT": 13.84,
    "SNGX": 0.37,
    "SPRB": 43.93,
    "SPRY": 5.96,
    "SRPT": 15.8,
    "SRRK": 48.97,
    "STOK": 29.57,
    "STRO": 22.34,
    "SUPN": 46.58,
    "SVRA": 5.64,
    "SYBX": 0.67,
    "SYRE": 102.54,
    "TARA": 4.05,
    "TARS": 58.24,
    "TBPH": 16.85,
    "TCRX": 0.81,
    "TGTX": 55.32,
    "TIL": 7.13,
    "TNGX": 26.78,
    "TNYA": 0.77,
    "TPST": 0.89,
    "TRDA": 6.01,
    "TRVI": 17.41,
    "TSHA": 5.55,
    "TVTX": 57.0,
    "TYRA": 30.77,
    "UNCY": 5.4,
    "URGN": 41.73,
    "UTHR": 531.97,
    "VCEL": 45.01,
    "VCNX": 0.83,
    "VCYT": 57.05,
    "VERA": 35.88,
    "VERU": 2.27,
    "VIR": 8.77,
    "VKTX": 35.04,
    "VNDA": 5.21,
    "VOR": 19.61,
    "VRCA": 5.31,
    "VRDN": 19.34,
    "VSTM": 6.03,
    "VTGN": 0.22,
    "VTRS": 17.24,
    "VXRT": 0.46,
    "WVE": 5.82,
    "XBIT": 2.27,
    "XENE": 65.09,
    "XERS": 8.32,
    "XFOR": 3.84,
    "XNCR": 19.65,
    "ZLAB": 19.26,
    "ZNTL": 4.35,
    "ZURA": 5.26,
    "ZVRA": 9.51,
    "ZYME": 22.99,
    "VRTX": 480.0,
    "AMGN": 376.95,
    "AZN": 168.98,
}


def seed_snapshots():
    """Fill PriceSnapshot for ALL tickers.

    Known tickers (31) get their real fallback price; the rest get $50.00
    as a placeholder so every row shows a number on the dashboard from
    the very first load.  Live prices fill in as yfinance data arrives
    on subsequent 5-minute cycles.
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
                fallback = _FALLBACK_PRICES.get(t.ticker)  # None for delisted/no-data tickers
                db.add(PriceSnapshot(
                    ticker=t.ticker,
                    price=fallback,
                    change_percent=None,
                    updated_at=now,
                ))
                added += 1

        if added:
            db.commit()
            logger.info("Seeded PriceSnapshot with %d entries (fallback for %d)", added, len(_FALLBACK_PRICES))
    except Exception as exc:
        logger.error("Failed to seed PriceSnapshot: %s", exc)
        db.rollback()
    finally:
        db.close()


def refresh_prices():
    """Fetch live prices for all tickers and upsert into PriceSnapshot.

    Runs every 5 minutes.
    A small delay (1 s) between tickers helps avoid Yahoo rate limits on cloud hosts.
    """
    import time

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
    scheduler.add_job(refresh_prices, "interval", minutes=5, id="refresh_prices", replace_existing=True)

    # Alert check at the configured interval
    scheduler.add_job(check_alerts, "interval", hours=settings.refresh_interval_hours, id="check_alerts", replace_existing=True)

    # ClinicalTrials.gov pipeline — once daily
    from scrapers.clinical_trials import run_pipeline as _run_ct
    scheduler.add_job(_run_ct, "interval", hours=24, id="clinical_trials_pipeline", replace_existing=True)

    # PDUFA pipeline — every 60 minutes
    from scrapers.pdufa import run_pdufa_pipeline
    scheduler.add_job(run_pdufa_pipeline, "interval", minutes=60, id="pdufa_pipeline", replace_existing=True)

    # ── Run-once on startup ──
    scheduler.add_job(run_pdufa_pipeline, "date", run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=35), id="pdufa_pipeline_initial", replace_existing=True)
    scheduler.add_job(_run_ct, "date", run_date=datetime.datetime.utcnow() + datetime.timedelta(seconds=30), id="clinical_trials_pipeline_initial", replace_existing=True)

    # ── SEC general filings feed (30 min) ──
    from scrapers.sec_filings import run_sec_feed
    scheduler.add_job(run_sec_feed, "interval", minutes=30, id="sec_feed", replace_existing=True)

    # ── Pharma news feed (15 min) ──
    from scrapers.news_feed import run_news_feed
    scheduler.add_job(run_news_feed, "interval", minutes=15, id="news_feed", replace_existing=True)

    # ── Daily briefings ──
    from app.services.notifier import send_morning_briefing, send_evening_briefing
    if settings.discord_webhook_briefing:
        scheduler.add_job(send_morning_briefing, "cron", hour=8, minute=30, id="morning_briefing", replace_existing=True)
        scheduler.add_job(send_evening_briefing, "cron", hour=21, minute=0, id="evening_briefing", replace_existing=True)
        logger.info("Daily briefings scheduled (08:30 / 21:00 UTC).")

    scheduler.start()
    logger.info("Scheduler started — prices 5m, alerts %dh, briefings daily.", settings.refresh_interval_hours)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
