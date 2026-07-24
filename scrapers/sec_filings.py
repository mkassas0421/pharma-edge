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

import datetime
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx

from app.models.database import SessionLocal, Ticker

logger = logging.getLogger(__name__)

# SEC endpoint base
SEC_BASE = "https://www.sec.gov"
SEC_ATOM = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={form}&output=atom"

H = {"User-Agent": "PharmaCatalystAlert/1.0 (admin@pharma-edge.com)"}

# Delay between feed requests to avoid SEC rate limiting
_SEC_FEED_DELAY = 3  # seconds

# Which form types to monitor, with human labels
FORM_TYPES = {
    "8-K": "8-K (Current Report)",
    "6-K": "6-K (Foreign Report)",
    "13D": "13D (Activist / >5% Ownership)",
    "13G": "13G (Passive Institutional)",
    "S-1": "S-1 (New Registration / IPO)",
    "S-3": "S-3 (Shelf Registration)",
}

# Keywords that make an 8-K especially interesting for biotech
_HIGH_IMPACT_KEYWORDS = [
    "clinical trial", "phase", "PDUFA", "fda", "nda", "bla",
    "approval", "efficacy", "top-line", "topline", "data readout",
    "biologics license", "supplement", "label expansion",
]

# Cache of seen accession numbers to avoid re-sending duplicates
_seen_filings: set[str] = set()


def _fetch_feed(form: str) -> list[dict]:
    """Fetch the Atom feed for *form* and return list of recent entries."""
    url = SEC_ATOM.format(form=form)
    try:
        with httpx.Client(timeout=20, headers=H) as cl:
            resp = cl.get(url)
            resp.raise_for_status()
    except Exception as exc:
        logger.debug("SEC feed %s: %s", form, exc)
        return []

    entries = []
    try:
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            link = entry.find("atom:link", ns)
            if title is None or summary is None:
                continue
            title_text = (title.text or "").strip()
            summary_text = (summary.text or "").strip()
            link_href = link.attrib.get("href", "") if link is not None else ""

            # Extract CIK and ticker from title like "ACCELERON PHARMA INC (CIK 0001035755) (Ticker: XLRN)"
            cik_m = re.search(r"CIK\s+(\d{10})", title_text)
            ticker_m = re.search(r"Ticker:\s*([A-Z]{2,5})", title_text)

            # Extract accession number from summary
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


def _is_biotech_8k(summary: str, ticker: str, tracked_set: set[str]) -> tuple[bool, str]:
    """Check if an 8-K filing is relevant for biotech tracking.

    Returns (is_relevant, reason).
    """
    if ticker and ticker in tracked_set:
        # It's one of our tracked tickers → relevant
        # Check if it mentions high-impact keywords
        summary_lower = summary.lower()
        for kw in _HIGH_IMPACT_KEYWORDS:
            if kw in summary_lower:
                return True, f"High-impact 8-K: mentions '{kw}'"
        return True, "Tracked ticker 8-K"

    return False, ""


def _check_cik_match(entry_cik: str | None, tracked_by_cik: dict[str, str]) -> str | None:
    """If the filing has a CIK, check if it matches a tracked ticker."""
    if entry_cik and entry_cik in tracked_by_cik:
        return tracked_by_cik[entry_cik]
    return None


def run_sec_feed():
    """Check all SEC form feeds for filings matching tracked tickers.

    New (unseen) matches are sent to the ``#sec-filings-live`` Discord channel.
    Runs every 30 minutes via the scheduler.
    """
    from app.models.database import Ticker as TickerModel

    db = SessionLocal()
    try:
        tickers = db.query(TickerModel).all()
        if not tickers:
            return

        tracked_set = {t.ticker.upper() for t in tickers}
        # Build CIK → ticker map from company names (approximate)
        # SEC feeds include the CIK number which we can match against company names
        # For now, ticker-based matching is more reliable

        total_matches = 0
        matches = []

        import time
        for i, form in enumerate(FORM_TYPES):
            # Rate-limit: 3s delay between feeds (SEC requires polite polling)
            if i > 0:
                time.sleep(_SEC_FEED_DELAY)
            entries = _fetch_feed(form)
            for entry in entries:
                if entry["accession"] and entry["accession"] in _seen_filings:
                    continue

                # Mark as seen regardless so we don't reprocess
                if entry["accession"]:
                    _seen_filings.add(entry["accession"])

                # 1. Try direct ticker match from feed
                ticker_match = None
                reason = ""
                if entry["ticker"] and entry["ticker"] in tracked_set:
                    ticker_match = entry["ticker"]
                    reason = "SEC ticker match"

                # 2. If no ticker in feed, try company name match
                if not ticker_match:
                    name_lower = entry["title"].lower()
                    for t in tickers:
                        if t.company_name.lower() in name_lower:
                            ticker_match = t.ticker
                            reason = "Company name match"
                            break
                        # Also search by ticker symbol in title
                        if f"({t.ticker})" in entry["title"]:
                            ticker_match = t.ticker
                            reason = "Ticker in title match"
                            break

                if ticker_match and ticker_match in tracked_set:
                    total_matches += 1
                    matches.append((ticker_match, entry, reason))

        # ── Send to Discord ──
        if matches and hasattr(__import__("app.services.notifier"), "send_sec_filing"):
            from app.services.notifier import send_sec_filing

            for ticker, entry, reason in matches:
                company = next((t.company_name for t in tickers if t.ticker == ticker), ticker)
                filing_url = urljoin(SEC_BASE, entry["url"]) if entry["url"] else ""

                # Truncate summary to a useful snippet
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

    except Exception as exc:
        logger.error("SEC feed error: %s", exc)
    finally:
        db.close()
