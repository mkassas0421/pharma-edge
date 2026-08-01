"""SEC EDGAR general filing monitor — watches 8-K, 13D/13G, S-1/S-3 filings.

For each tracked ticker, checks the SEC Atom feeds for new filings and
sends relevant matches to the ``#sec-filings-live`` Discord channel.

Form types monitored:
  - **8-K**  — material events (clinical results, FDA updates, leadership)
  - **13D**  — activist / >5% beneficial ownership (accumulation signal)
  - **13G**  — passive institutional >5% ownership
  - **S-1**  — IPO / new share registration (dilution signal)
  - **S-3**  — shelf registration (future dilution)
  - **6-K**  — foreign private issuer equivalent of 8-K
"""

import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx

from app.models.database import SessionLocal, Ticker
from app.utils.collections import BoundedSet
from app.utils.http import SEC_HEADERS

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

SEC_BASE = "https://www.sec.gov"
SEC_ATOM = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}&output=atom"
SEC_FEED_DELAY = 3  # seconds between feed requests to avoid rate limiting

FORM_TYPES = {
    "8-K": "8-K (Current Report)",
    "6-K": "6-K (Foreign Report)",
    "13D": "13D (Activist / >5% Ownership)",
    "13G": "13G (Passive Institutional)",
    "S-1": "S-1 (New Registration / IPO)",
    "S-3": "S-3 (Shelf Registration)",
}

_HIGH_IMPACT_KEYWORDS = [
    "clinical trial", "phase", "PDUFA", "fda", "nda", "bla",
    "approval", "efficacy", "top-line", "topline", "data readout",
    "biologics license", "supplement", "label expansion",
]

# Fast-path cache for seen accession numbers; the persistent source of
# truth is the scraper_dedup table (survives restarts).
_seen_filings = BoundedSet(maxsize=5000)
_DEDUP_SOURCE = "sec_filings"


def _fetch_feed(form: str) -> list[dict]:
    """Fetch the Atom feed for *form* and return list of recent entries."""
    url = SEC_ATOM.format(form=form)
    try:
        with httpx.Client(timeout=20, headers=SEC_HEADERS) as client:
            resp = client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        logger.debug("SEC feed %s: %s", form, exc)
        return []

    entries = []
    try:
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            link_el = entry.find("atom:link", ns)
            if title_el is None or summary_el is None:
                continue
            title_text = (title_el.text or "").strip()
            summary_text = (summary_el.text or "").strip()
            link_href = link_el.attrib.get("href", "") if link_el is not None else ""

            cik_m = re.search(r"CIK\s+(\d{10})", title_text)
            ticker_m = re.search(r"Ticker:\s*([A-Z]{2,5})", title_text)
            accn_m = re.search(r"AccNo:\s*(\S+)", summary_text)

            entries.append({
                "title": title_text,
                "summary": summary_text,
                "url": link_href,
                "cik": cik_m.group(1) if cik_m else None,
                "ticker": ticker_m.group(1) if ticker_m else None,
                "accession": accn_m.group(1) if accn_m else None,
                "form": form,
            })
    except Exception as exc:
        logger.debug("SEC feed parse %s: %s", form, exc)

    return entries


def run_sec_feed():
    """Check all SEC form feeds for filings matching tracked tickers.

    New (unseen) matches are sent to the ``#sec-filings-live`` Discord channel.
    Runs every 30 minutes via the scheduler.
    """
    from scrapers.dedup import is_seen, mark_seen, prune_old

    db = SessionLocal()
    try:
        tickers = db.query(Ticker).all()
        if not tickers:
            return

        tracked_set = {t.ticker.upper() for t in tickers}
        total_matches = 0
        matches: list[tuple[str, dict, str]] = []

        for i, form in enumerate(FORM_TYPES):
            if i > 0:
                time.sleep(SEC_FEED_DELAY)
            entries = _fetch_feed(form)
            for entry in entries:
                if entry["accession"] and is_seen(db, _DEDUP_SOURCE, entry["accession"], _seen_filings):
                    continue
                if entry["accession"]:
                    mark_seen(db, _DEDUP_SOURCE, entry["accession"], _seen_filings)

                ticker_match = None
                reason = ""

                # 1. Direct ticker match from feed
                if entry["ticker"] and entry["ticker"] in tracked_set:
                    ticker_match = entry["ticker"]
                    reason = "SEC ticker match"

                # 2. Company name / ticker-in-title match
                if not ticker_match:
                    name_lower = entry["title"].lower()
                    for t in tickers:
                        if t.company_name.lower() in name_lower:
                            ticker_match = t.ticker
                            reason = "Company name match"
                            break
                        if f"({t.ticker})" in entry["title"]:
                            ticker_match = t.ticker
                            reason = "Ticker in title match"
                            break

                if ticker_match and ticker_match in tracked_set:
                    total_matches += 1
                    matches.append((ticker_match, entry, reason))

        # ── Send to Discord ──
        if matches:
            from app.services.notifier import send_sec_filing

            for ticker, entry, reason in matches:
                company = next((t.company_name for t in tickers if t.ticker == ticker), ticker)
                filing_url = urljoin(SEC_BASE, entry["url"]) if entry["url"] else ""
                snippet = entry["summary"][:300] if entry["summary"] else ""

                ok = send_sec_filing(
                    ticker=ticker,
                    company=company,
                    form_type=entry["form"],
                    description=f"**{reason}**\n{snippet}",
                    url=filing_url,
                )
                if ok:
                    logger.info("SEC filing sent: %s — %s", ticker, entry["form"])

        if total_matches:
            logger.info("SEC feed: %d new filing(s) across %d form type(s)", total_matches, len(FORM_TYPES))

        # Persist dedup markers + prune old ones (single transaction)
        prune_old(db, _DEDUP_SOURCE)
        db.commit()
    except Exception as exc:
        logger.error("SEC feed error: %s", exc)
        db.rollback()
    finally:
        db.close()
