"""Backfill historical FDA Advisory Committee meetings (one-time).

The forward Federal Register scraper only creates events for UPCOMING
meetings (and was additionally broken until the ticker_id fix), so past
AdCom meetings — e.g. the CTGTAC meeting for Capricor's deramiocel BLA on
2026-07-29 — never entered the database. This script re-uses the scraper's
own document query and matching logic with ``allow_past=True``, importing
every FDA "Notice of Meeting" published 2020-01-01 → 2026-07-31 that names
a tracked company, and records each event's price reaction immediately
(yfinance), exactly like the ClinicalTrials.gov backfill.

Idempotent: the same-meeting dedup (source + ticker + event_date) and the
external_id check skip what the forward scraper already created, and
re-running only fills gaps.

Usage (from the project root — connects to whatever DATABASE_URL the
environment resolves to, i.e. the production PostgreSQL in prod):
    python scripts/backfill_historical_adcom.py                    # full run (~922 docs)
    python scripts/backfill_historical_adcom.py --only-doc 2026-13096   # single-doc smoke test
    python scripts/backfill_historical_adcom.py --resume-from 2024-01-01
    python scripts/backfill_historical_adcom.py --limit 20
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

from app.models.database import SessionLocal, Ticker, TickerAlias, CatalystEvent  # noqa: E402
from app.services.price_service import get_historical_prices  # noqa: E402
from app.services.reaction_service import _capture_one  # noqa: E402
from scrapers.federal_register import (  # noqa: E402
    FEDERAL_REGISTER_API,
    _PAGE_FIELDS,
    _doc_to_events,
    _extract_meeting_date,
    _fetch_body_xml,
    _fetch_documents,
    REQUEST_DELAY_S,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_adcom")

BACKFILL_START = datetime.datetime(2020, 1, 1)
BACKFILL_END = datetime.datetime(2026, 7, 31)  # publication-date window
PAGE_SIZE = 100
YF_SLEEP = 0.5  # Yahoo Finance rate limit between price fetches


def _load_alias_maps(db) -> tuple[dict, dict]:
    """Return ({ticker: [aliases]}, {ticker: ticker_id}) — mirrors run_pipeline."""
    tickers = db.query(Ticker).all()
    alias_rows = db.query(TickerAlias).all()
    ticker_by_id = {t.id: t.ticker for t in tickers}
    aliases_by_ticker: dict = {}
    for row in alias_rows:
        t = ticker_by_id.get(row.ticker_id)
        if t:
            aliases_by_ticker.setdefault(t, []).append(row.alias)
    ticker_id_by_ticker = {t.ticker: t.id for t in tickers}
    return aliases_by_ticker, ticker_id_by_ticker


def _fetch_document(doc_number: str) -> dict | None:
    """Fetch a single document by its number ({API}/{doc_number}.json)."""
    try:
        with httpx.Client(timeout=25) as client:
            resp = client.get(f"{FEDERAL_REGISTER_API}/{doc_number}", params={f"fields[]": _PAGE_FIELDS})
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("FR fetch %s failed: %s", doc_number, exc)
        return None


def _fetch_all_docs() -> list[dict]:
    """Fetch all FDA AdCom notices in the backfill window (oldest first)."""
    docs: list[dict] = []
    page = 1
    while True:
        batch, total_pages = _fetch_documents(
            since=BACKFILL_START.strftime("%m/%d/%Y"),
            until=BACKFILL_END.strftime("%m/%d/%Y"),
            page=page, per_page=PAGE_SIZE, order="oldest",
        )
        docs.extend(batch)
        if not batch or page >= total_pages:
            break
        page += 1
        time.sleep(REQUEST_DELAY_S)
    return docs


def _import_one(db, ev_data, ticker_id_by_ticker, stats) -> None:
    """Dedup → insert → flush → immediate reaction capture."""
    # Same meeting already tracked (notice + amendment pairs, forward-created rows)
    same_meeting = db.query(CatalystEvent).filter(
        CatalystEvent.source == "federal_register",
        CatalystEvent.ticker == ev_data["ticker"],
        CatalystEvent.event_date == ev_data["event_date"],
    ).first()
    if same_meeting:
        stats["dupes"] += 1
        return
    existing = db.query(CatalystEvent).filter(
        CatalystEvent.external_id == ev_data["external_id"],
        CatalystEvent.ticker == ev_data["ticker"],
    ).first()
    if existing:
        stats["dupes"] += 1
        return

    ev_data["ticker_id"] = ticker_id_by_ticker[ev_data["ticker"]]  # NOT NULL column
    event = CatalystEvent(**ev_data)
    db.add(event)
    db.flush()  # autoflush=False; event.id is needed for the reaction row
    prices = get_historical_prices(event.ticker, event.event_date)
    status = _capture_one(db, event, prices)
    stats["events"] += 1
    stats[status] += 1
    time.sleep(YF_SLEEP)


def _process_document(db, doc, aliases_by_ticker, ticker_id_by_ticker, stats) -> None:
    """Convert one FR document into events and import them."""
    doc_number = doc.get("document_number", "")
    body_text = _fetch_body_xml(doc.get("full_text_xml_url"))
    if not body_text:
        stats["body_fail"] += 1
    meeting_date = _extract_meeting_date(body_text or "") or _extract_meeting_date(doc.get("abstract") or "")
    if meeting_date is None:
        stats["no_date"] += 1  # non-AdCom notices, amendments without DATES, numeric dates
        return
    events = _doc_to_events(doc, body_text, aliases_by_ticker, allow_past=True)
    if not events:
        stats["no_match"] += 1  # parsed a date, but no tracked ticker in the text
        return
    for ev in events:
        if ev["event_date"] < BACKFILL_START:
            stats["pre_window"] += 1
        elif ev["event_date"] > datetime.datetime.utcnow():
            stats["future"] += 1  # the forward scraper owns upcoming meetings
        else:
            _import_one(db, ev, ticker_id_by_ticker, stats)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-from", help="skip documents published before this date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=None,
                        help="only process the first N documents (after the resume filter)")
    parser.add_argument("--only-doc", help="process a single Federal Register document number")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        aliases_by_ticker, ticker_id_by_ticker = _load_alias_maps(db)
        if not aliases_by_ticker:
            logger.info("No ticker aliases — nothing to match")
            return
        docs = [_fetch_document(args.only_doc)] if args.only_doc else _fetch_all_docs()
        docs = [d for d in docs if d]
        if not docs:
            logger.warning("No documents fetched")
            return

        stats = {"events": 0, "captured": 0, "failed": 0, "pending": 0,
                 "dupes": 0, "no_date": 0, "no_match": 0, "body_fail": 0,
                 "future": 0, "pre_window": 0, "errors": 0}
        processed = 0
        t0 = time.time()

        for doc in docs:
            pub = doc.get("publication_date", "")  # ISO date — lexicographic compare works
            if args.resume_from and pub < args.resume_from:
                continue
            if args.limit is not None and processed >= args.limit:
                break
            processed += 1
            try:
                _process_document(db, doc, aliases_by_ticker, ticker_id_by_ticker, stats)
                db.commit()  # per-document commit → safe to interrupt and resume
            except Exception as exc:
                db.rollback()
                stats["errors"] += 1
                logger.error("doc %s failed: %s", doc.get("document_number", "?"), exc)
            if processed % 50 == 0:
                logger.info("Progress %d/%d docs | events=%d captured=%d failed=%d (%.0fs)",
                            processed, len(docs), stats["events"], stats["captured"],
                            stats["failed"], time.time() - t0)

        logger.info(
            "DONE in %.0fs: docs=%d events=%d captured=%d failed=%d pending=%d "
            "dupes=%d no_date=%d no_match=%d future=%d pre_window=%d errors=%d",
            time.time() - t0, processed, stats["events"], stats["captured"],
            stats["failed"], stats["pending"], stats["dupes"], stats["no_date"],
            stats["no_match"], stats["future"], stats["pre_window"], stats["errors"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
