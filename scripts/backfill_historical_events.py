"""Backfill historical catalyst events from ClinicalTrials.gov (one-time).

The forward-looking scraper discards studies whose completion date is more
than 90 days in the past. This script goes further back (2020-01-01 →
2026-03-31) so the reaction tracker has per-ticker history to aggregate —
"how did THIS stock react to the same kind of catalyst before?"

It reuses the scraper's study→event conversion and the reaction service's
capture logic: every imported event gets its price reaction recorded
immediately (yfinance), so the pruner can later drop the event row safely
(the denormalised EventReaction row carries the data forward).

Idempotent: events are skipped when an event with the same external_id +
ticker already exists, so re-running only fills the gaps.

Usage (from the project root — connects to whatever DATABASE_URL the
environment resolves to, i.e. the production PostgreSQL in prod):
    python scripts/backfill_historical_events.py
    python scripts/backfill_historical_events.py --resume-from CRIS
    python scripts/backfill_historical_events.py --limit 5   # smoke test
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

from app.models.database import SessionLocal, Ticker, CatalystEvent  # noqa: E402
from app.services.price_service import get_historical_prices  # noqa: E402
from app.services.reaction_service import _capture_one  # noqa: E402
from scrapers.clinical_trials import CLINICAL_TRIALS_API, _study_to_event  # noqa: E402
from scrapers.company_map import search_terms  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill")

BACKFILL_START = datetime.datetime(2020, 1, 1)
BACKFILL_END = datetime.datetime(2026, 3, 31)  # stops before the forward window
MAX_PAGES_PER_TERM = 3      # 100 studies per page
MAX_EVENTS_PER_TICKER = 150
API_SLEEP = 1.0             # ClinicalTrials.gov polite rate limit
YF_SLEEP = 0.5              # Yahoo Finance rate limit between price fetches


def _date_range_expr() -> str:
    """CompletionDate range filter for the API v2 expression syntax."""
    return "AREA[CompletionDate]RANGE[{s:%m/%d/%Y}, {e:%m/%d/%Y}]".format(
        s=BACKFILL_START, e=BACKFILL_END
    )


def _fetch_studies(ticker: str, terms: list[str]) -> list[dict]:
    """Fetch all studies for a company completed within the backfill window."""
    seen_ncts: set[str] = set()
    studies: list[dict] = []
    for term in terms:
        page_token = None
        for _ in range(MAX_PAGES_PER_TERM):
            params = {
                "query.term": term,
                "query.cond": _date_range_expr(),
                "pageSize": 100,
                "format": "json",
                "sort": "LastUpdatePostDate",
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.get(CLINICAL_TRIALS_API, params=params)
                    if resp.status_code == 429:
                        logger.warning("Rate-limited on %s (term=%s); backing off", ticker, term)
                        time.sleep(10)
                        continue
                    resp.raise_for_status()
                    body = resp.json()
            except Exception as exc:
                logger.warning("fetch(%s, term=%s) failed: %s", ticker, term, exc)
                break
            for study in body.get("studies", []):
                nct = (
                    study.get("protocolSection", {})
                    .get("identificationModule", {})
                    .get("nctId", "")
                )
                if nct and nct not in seen_ncts:
                    seen_ncts.add(nct)
                    studies.append(study)
            page_token = body.get("nextPageToken")
            if not page_token:
                break
            time.sleep(API_SLEEP)
        time.sleep(API_SLEEP)
    return studies


def _backfill_ticker(db, ticker_obj, stats: dict) -> int:
    """Import + capture reactions for one company. Returns events imported."""
    terms = search_terms(ticker_obj.ticker)
    if not terms:
        stats["no_terms"] += 1
        return 0

    imported = 0
    for study in _fetch_studies(ticker_obj.ticker, terms):
        if imported >= MAX_EVENTS_PER_TICKER:
            break
        ev_data = _study_to_event(
            study, ticker_obj.ticker, ticker_obj.id, min_event_date=BACKFILL_START
        )
        if not ev_data or ev_data["event_date"] > BACKFILL_END:
            continue
        existing = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.external_id == ev_data["external_id"],
                CatalystEvent.ticker == ev_data["ticker"],
            )
            .first()
        )
        if existing:
            stats["dupes"] += 1
            continue

        event = CatalystEvent(**ev_data)
        db.add(event)
        db.flush()  # event.id is needed for the reaction row
        prices = get_historical_prices(event.ticker, event.event_date)
        status = _capture_one(db, event, prices)
        stats["events"] += 1
        stats[status] += 1
        imported += 1
        time.sleep(YF_SLEEP)

    if imported:
        logger.info(
            "%s: %d event(s) imported (captured=%d failed=%d pending=%d)",
            ticker_obj.ticker, imported, stats["captured"], stats["failed"], stats["pending"],
        )
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-from", help="skip tickers until this one (alphabetical order)")
    parser.add_argument("--limit", type=int, default=None, help="only process the first N tickers")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tickers = db.query(Ticker).order_by(Ticker.ticker).all()
        stats = {"events": 0, "captured": 0, "failed": 0, "pending": 0,
                 "dupes": 0, "no_terms": 0}
        started = args.resume_from is None
        processed = 0
        t0 = time.time()

        for t in tickers:
            if not started:
                if t.ticker == args.resume_from:
                    started = True
                else:
                    continue
            if args.limit is not None and processed >= args.limit:
                break
            processed += 1
            _backfill_ticker(db, t, stats)
            db.commit()
            if processed % 10 == 0:
                logger.info(
                    "Progress %d/%d tickers | events=%d captured=%d failed=%d (%.0fs)",
                    processed, len(tickers), stats["events"],
                    stats["captured"], stats["failed"], time.time() - t0,
                )

        logger.info(
            "DONE in %.0fs: %d tickers processed, %d events imported "
            "(captured=%d failed=%d pending=%d), %d skipped as duplicates, %d without search terms",
            time.time() - t0, processed, stats["events"], stats["captured"],
            stats["failed"], stats["pending"], stats["dupes"], stats["no_terms"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
