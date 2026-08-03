"""Backfill results-first-posted dates for ClinicalTrials.gov events (one-time).

The historical CT.gov backfill used the primary COMPLETION date as the
event date, but the real market catalyst is the DATA RELEASE — the official
"results first posted" date (``statusModule.resultsFirstPostDateStruct``),
which can be months after completion. This script re-fetches each event's
study, moves ``event_date`` to the results-first-posted date where one
exists, and re-records the price reaction around the new date (updating the
existing EventReaction row in place).

PDUFA / SEC / Federal Register events are never touched — only
``clinicaltrials_gov`` sources are processed.

Usage (from the project root — connects to whatever DATABASE_URL the
environment resolves to, i.e. the production PostgreSQL in prod):
    python scripts/backfill_results_dates.py
    python scripts/backfill_results_dates.py --resume-from NCT03569293
    python scripts/backfill_results_dates.py --limit 10
"""

import argparse
import datetime
import logging
import os
import sys
import time

import httpx

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.models.database import SessionLocal, CatalystEvent  # noqa: E402
from app.services.price_service import get_historical_prices  # noqa: E402
from app.services.reaction_service import _capture_one  # noqa: E402
from scrapers.clinical_trials import CLINICAL_TRIALS_API  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_dates")

API_SLEEP = 1.0   # ClinicalTrials.gov polite rate limit
YF_SLEEP = 0.5    # Yahoo Finance rate limit between price fetches


def _fetch_study(nct: str) -> dict | None:
    """Fetch one study JSON by NCT id."""
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{CLINICAL_TRIALS_API}/{nct}", params={"format": "json"})
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("fetch(%s) failed: %s", nct, exc)
        return None


def _results_date(study: dict) -> datetime.datetime | None:
    """Extract the official 'results first posted' date from a study JSON."""
    sm = (study.get("protocolSection") or {}).get("statusModule") or {}
    rfp = sm.get("resultsFirstPostDateStruct")
    if not isinstance(rfp, dict) or not rfp.get("date"):
        return None
    d = rfp["date"]
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.datetime.strptime(d, fmt)
        except ValueError:
            continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-from", help="skip events before this NCT id (lexicographic order)")
    parser.add_argument("--limit", type=int, default=None, help="only process the first N events")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        events = (
            db.query(CatalystEvent)
            .filter(CatalystEvent.source == "clinicaltrials_gov")
            .order_by(CatalystEvent.external_id)
            .all()
        )
        logger.info("clinicaltrials_gov events: %d", len(events))

        stats = {"updated": 0, "unchanged": 0, "no_results": 0, "fetch_fail": 0,
                 "captured": 0, "failed": 0, "pending": 0, "errors": 0}
        processed = 0
        t0 = time.time()
        started = args.resume_from is None

        for ev in events:
            nct = ev.external_id or ""
            if not started:
                if nct == args.resume_from:
                    started = True
                else:
                    continue
            if args.limit is not None and processed >= args.limit:
                break
            processed += 1
            try:
                study = _fetch_study(nct)
                if not study:
                    stats["fetch_fail"] += 1
                    continue
                rd = _results_date(study)
                if rd is None:
                    stats["no_results"] += 1
                    continue
                if rd == ev.event_date:
                    stats["unchanged"] += 1
                    continue
                # Move the event to the real data-release day and re-record
                # the reaction around it (updates the existing reaction row).
                ev.event_date = rd
                prices = get_historical_prices(ev.ticker, rd)
                status = _capture_one(db, ev, prices)
                stats["updated"] += 1
                stats[status] += 1
                logger.info("%s: %s → %s (%s)", nct, ev.ticker, rd.date(), status)
                time.sleep(YF_SLEEP)
            except Exception as exc:
                db.rollback()
                stats["errors"] += 1
                logger.error("%s failed: %s", nct, exc)
            finally:
                db.commit()  # per-event commit → safe to interrupt and resume
                time.sleep(API_SLEEP)
            if processed % 100 == 0:
                logger.info("Progress %d/%d | updated=%d (%.0fs)",
                            processed, len(events), stats["updated"], time.time() - t0)

        logger.info(
            "DONE in %.0fs: events=%d updated=%d unchanged=%d no_results=%d "
            "fetch_fail=%d captured=%d failed=%d pending=%d errors=%d",
            time.time() - t0, processed, stats["updated"], stats["unchanged"],
            stats["no_results"], stats["fetch_fail"], stats["captured"],
            stats["failed"], stats["pending"], stats["errors"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
