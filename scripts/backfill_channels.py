"""Backfill Discord channels with historical events from the last 14 days.

Usage:
    python scripts/backfill_channels.py

Sends:
  - #high-impact-catalysts: PDUFA + Phase 2/3 events (last 14 days)
  - #clinical-trials-updates: CT.gov events with phase/date changes (last 14 days)
  - #sec-filings-live: SEC-sourced events (last 14 days)

Respects alert_sent — doesn't re-send already-alerted events.
"""

import datetime
import sys
import os
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.models.database import SessionLocal, CatalystEvent, Ticker
from app.config import settings
from app.services.notifier import send_high_impact_alert, send_clinical_change, send_sec_filing


def main():
    db = SessionLocal()
    now = datetime.datetime.utcnow()
    backfill_since = now - datetime.timedelta(days=14)

    # ── 1. High-impact: PDUFA + Phase 2/3 from last 14d ──
    print("\n=== #high-impact-catalysts (14-day backfill) ===")
    if not settings.discord_webhook_high_impact:
        print("  SKIP — DISCORD_WEBHOOK_HIGH_IMPACT not configured")
    else:
        high_events = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.event_date >= backfill_since,
                CatalystEvent.event_date <= now + datetime.timedelta(days=30),
                CatalystEvent.alert_sent.is_(None),
                CatalystEvent.impact_level == "High",
            )
            .order_by(CatalystEvent.event_date)
            .all()
        )
        print(f"  Found {len(high_events)} unalerted High-impact events")
        for ev in high_events:
            ticker_obj = db.query(Ticker).filter(Ticker.ticker == ev.ticker).first()
            company = ticker_obj.company_name if ticker_obj else ev.ticker
            days_until = (ev.event_date - now).days
            ok = send_high_impact_alert(
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
                print(f"    SENT: {ev.ticker} — {ev.title[:60]}")
                time.sleep(0.5)  # Discord rate limit
            else:
                print(f"    FAIL: {ev.ticker} — webhook error, skipping")
        db.commit()

    # ── 2. SEC filings: SEC-sourced events from last 14d ──
    print("\n=== #sec-filings-live (14-day backfill) ===")
    if not settings.discord_webhook_sec_live:
        print("  SKIP — DISCORD_WEBHOOK_SEC_LIVE not configured")
    else:
        sec_events = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.created_at >= backfill_since,
                CatalystEvent.source == "sec_edgar_pdufa",
                CatalystEvent.alert_sent.is_(None),
            )
            .order_by(CatalystEvent.created_at.desc())
            .all()
        )
        print(f"  Found {len(sec_events)} SEC-sourced events")
        for ev in sec_events:
            ticker_obj = db.query(Ticker).filter(Ticker.ticker == ev.ticker).first()
            company = ticker_obj.company_name if ticker_obj else ev.ticker
            ok = send_sec_filing(
                ticker=ev.ticker,
                company=company,
                form_type="8-K / 6-K (PDUFA)",
                description=ev.description or ev.title,
            )
            if ok:
                ev.alert_sent = now
                print(f"    SENT: {ev.ticker} — {ev.title[:60]}")
                time.sleep(0.5)
            else:
                print(f"    FAIL: {ev.ticker} — webhook error")
        db.commit()

    # ── 3. Clinical trials: CT.gov events created/updated in last 14d ──
    print("\n=== #clinical-trials-updates (14-day backfill) ===")
    if not settings.discord_webhook_clinical:
        print("  SKIP — DISCORD_WEBHOOK_CLINICAL not configured")
    else:
        ct_events = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.created_at >= backfill_since,
                CatalystEvent.source == "clinicaltrials_gov",
                CatalystEvent.alert_sent.is_(None),
            )
            .order_by(CatalystEvent.created_at.desc())
            .limit(30)  # don't spam too many
            .all()
        )
        print(f"  Found {len(ct_events)} CT.gov events (capped at 30)")
        for ev in ct_events:
            ticker_obj = db.query(Ticker).filter(Ticker.ticker == ev.ticker).first()
            company = ticker_obj.company_name if ticker_obj else ev.ticker
            drug = _extract_drug(ev)
            ok = send_clinical_change(
                ticker=ev.ticker,
                company=company,
                drug=drug,
                change_desc=f"New trial added: **{ev.title[:80]}** (Phase: {ev.event_type.replace('_', ' ').title()})",
                nct_id=ev.external_id or "",
            )
            if ok:
                ev.alert_sent = now
                print(f"    SENT: {ev.ticker} — {ev.title[:60]}")
                time.sleep(0.5)
            else:
                print(f"    FAIL: {ev.ticker} — webhook error")
        db.commit()

    db.close()
    print("\n=== Backfill complete ===")


def _extract_drug(ev) -> str:
    """Pull drug name from description field."""
    if not ev.description:
        return "Investigational"
    for line in ev.description.split("\n"):
        if line.startswith("💊 Drug:"):
            return line.replace("💊 Drug:", "").strip()
    return "Investigational"


if __name__ == "__main__":
    main()
