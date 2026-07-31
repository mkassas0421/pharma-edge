"""Federal Register scraper — official FDA advisory committee meetings.

The Federal Register API (https://www.federalregister.gov/api/v1/documents)
is a free, key-less, structured JSON endpoint published by the US government.

We pull FDA "Notice of Meeting" documents (published 15+ days before each
advisory committee meeting per FACA). The meeting date lives in the DATES
section of the document body, and the sponsor/drug names appear in the body
text — so each document is fetched as XML, tag-stripped, and matched against
the tracked ticker aliases.

Every event carries ``source_url`` pointing at the official Federal Register
document page and is marked ``verified``.
"""

import datetime
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.models.database import SessionLocal, Ticker, TickerAlias, CatalystEvent
from app.utils.dates import parse_date as _parse_date

logger = logging.getLogger(__name__)

FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/documents"
LOOKBACK_DAYS = 90
MAX_DOCS = 50
REQUEST_DELAY_S = 1.0  # the API is free; stay polite

# DATES section of a Federal Register notice. The section ends at the next
# all-caps section heading (ADDRESSES, FOR FURTHER INFORMATION CONTACT, …).
_DATES_SECTION_RE = re.compile(
    r"\bDATES[:]?\s*(.*?)(?=\bADDRESSES\b|\bFOR FURTHER INFORMATION CONTACT\b|\bSUPPLEMENTARY INFORMATION\b|\Z)",
    re.S | re.I,
)
# First date mentioned inside the DATES section ("July 30, 2026", "7/30/2026").
_DATE_IN_TEXT_RE = re.compile(
    r"([A-Z][a-z]{2,8}\s+\d{1,2},?\s*\d{4})|(\d{1,2}/\d{1,2}/\d{4})"
)

_PAGE_FIELDS = [
    "document_number",
    "title",
    "abstract",
    "html_url",
    "full_text_xml_url",
    "publication_date",
]


def _extract_meeting_date(text: str) -> datetime.datetime | None:
    """Find the meeting date in a notice's DATES section."""
    if not text:
        return None
    m = _DATES_SECTION_RE.search(text)
    section = m.group(1) if m else text
    dm = _DATE_IN_TEXT_RE.search(section)
    if not dm:
        return None
    candidate = dm.group(1) or dm.group(2)
    return _parse_date(candidate)


def _fetch_documents() -> list[dict]:
    """Fetch FDA 'Notice of Meeting' documents from the last LOOKBACK_DAYS."""
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=LOOKBACK_DAYS)).strftime("%m/%d/%Y")
    params = {
        "conditions[agencies][]": "food-and-drug-administration",
        "conditions[type][]": "NOTICE",
        "conditions[term]": "notice of meeting",
        "conditions[publication_date][gte]": since,
        "per_page": MAX_DOCS,
        "order": "newest",
        "fields[]": _PAGE_FIELDS,  # httpx encodes lists as repeated fields[]=... params
    }
    all_docs: list[dict] = []
    try:
        with httpx.Client(timeout=25) as client:
            resp = client.get(FEDERAL_REGISTER_API, params=params)
            resp.raise_for_status()
            all_docs = resp.json().get("results", [])
    except Exception as exc:
        logger.warning("Federal Register fetch failed: %s", exc)
    return all_docs


def _fetch_body_xml(xml_url: str) -> str | None:
    """Fetch and tag-strip a document body. Returns plain text or None."""
    if not xml_url:
        return None
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            resp = client.get(xml_url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    except Exception as exc:
        logger.warning("FR body fetch failed (%s): %s", xml_url, exc)
        return None


# First tokens that are too generic to match on alone ("United Therapeutics").
_TOKEN_STOPLIST = {
    "united", "international", "global", "holding", "holdings", "group",
    "company", "corporation", "sciences", "laboratory", "laboratories",
    "research", "development", "clinical", "biotech", "biotechnology",
    "applied", "structure", "solid", "wave", "compass", "scholar",
    "general", "first", "second", "future",
}
# Applicant-context markers: a first-token match only counts when it appears
# near one of these (e.g. "...BLA 125842 From Capricor, Inc. for Deramiocel...").
_APPLICANT_CTX = re.compile(
    r"\b(BLA|NDA|sNDA|sBLA|IND|application|submitted\s+by|sponsor|applicant|From)\b",
    re.I,
)


def _first_token_in_applicant_context(first: str, low: str) -> bool:
    """True if *first* (the company's first word) appears near an applicant
    marker — e.g. "From Capricor, Inc." — so generic English words like
    "applied" or "compass" don't produce false positives."""
    for m in re.finditer(rf"\b{re.escape(first)}\b", low):
        window = low[max(0, m.start() - 120):m.end() + 120]
        if _APPLICANT_CTX.search(window):
            return True
    return False


def _matches_any(text: str, aliases_by_ticker: dict) -> list[str]:
    """Return tracked tickers whose company name appears in *text*.

    Both passes use word boundaries (no substring false positives like
    "Allogene" inside "allogeneic"):
      1. the full alias ("Biogen Inc.", "Capricor Therapeutics")
      2. the first word of the alias ("Capricor" for "Capricor, Inc."), only
         for distinctive first tokens (>= 6 chars, not in the stoplist) that
         occur in applicant context.
    """
    if not text:
        return []
    low = text.lower()
    hits = []
    for ticker, aliases in aliases_by_ticker.items():
        matched = False
        for alias in aliases:
            if not alias or len(alias) < 4:
                continue
            if re.search(rf"\b{re.escape(alias)}\b", low):
                matched = True
                break
        if not matched:
            for alias in aliases:
                first = (alias or "").split()[0].lower()
                if len(first) >= 6 and first not in _TOKEN_STOPLIST:
                    if _first_token_in_applicant_context(first, low):
                        matched = True
                        break
        if matched:
            hits.append(ticker)
    return hits


def _doc_to_events(doc: dict, body_text: str, aliases_by_ticker: dict) -> list[dict]:
    """Convert a meeting-notice document into event dicts (one per ticker)."""
    title = doc.get("title", "")
    abstract = doc.get("abstract", "")
    html_url = doc.get("html_url", "")
    doc_number = doc.get("document_number", "")
    if not title or not doc_number:
        return []

    # Meeting date from the DATES section of the body (fallback: abstract).
    meeting_date = _extract_meeting_date(body_text or "") or _extract_meeting_date(abstract or "")
    if not meeting_date:
        logger.debug("FR %s: no meeting date found", doc_number)
        return []

    # Only forward-looking meetings become catalysts.
    if meeting_date < datetime.datetime.utcnow():
        return []

    # Match tickers — prefer title/abstract (strong signal), else full body.
    tickers = _matches_any(f"{title} {abstract}", aliases_by_ticker)
    if not tickers:
        tickers = _matches_any(body_text or "", aliases_by_ticker)
    if not tickers:
        return []

    events = []
    for ticker in tickers:
        events.append({
            "ticker": ticker,
            "title": f"FDA Advisory Committee — {title[:200]}",
            "event_type": "REGULATORY",
            "event_date": meeting_date,
            "impact_level": "High",
            "description": (
                f"💊 Drug: See official notice\n"
                f"⚙️  Mechanism: N/A — FDA Advisory Committee meeting\n"
                f"🔬 Phase: Regulatory review\n"
                f"📋 Trial: {doc_number}\n"
                f"🎯 Milestone: Advisory committee meeting on {meeting_date.strftime('%B %d, %Y')}\n"
                f"\n"
                f"{abstract or 'No abstract.'}\n"
                f"Source: Federal Register ({html_url})"
            ),
            "source": "federal_register",
            "external_id": f"FR-{doc_number}",
            "source_url": html_url or None,
            "verified": True,
        })
    return events


def run_pipeline():
    """Fetch recent FDA advisory committee notices and upsert events."""
    db = SessionLocal()
    try:
        tickers = db.query(Ticker).all()
        if not tickers:
            return

        alias_rows = db.query(TickerAlias).all()
        ticker_by_id = {t.id: t.ticker for t in tickers}
        aliases_by_ticker: dict = {}
        for row in alias_rows:
            t = ticker_by_id.get(row.ticker_id)
            if t:
                aliases_by_ticker.setdefault(t, []).append(row.alias)

        docs = _fetch_documents()
        if not docs:
            logger.warning("Federal Register: no documents fetched")
            return

        total_new = total_upd = 0
        for i, doc in enumerate(docs):
            body_text = _fetch_body_xml(doc.get("full_text_xml_url"))
            for ev_data in _doc_to_events(doc, body_text, aliases_by_ticker):
                # The original notice and its amendments produce multiple FR
                # documents for one meeting — keep one event per (ticker, date).
                same_meeting = db.query(CatalystEvent).filter(
                    CatalystEvent.source == "federal_register",
                    CatalystEvent.ticker == ev_data["ticker"],
                    CatalystEvent.event_date == ev_data["event_date"],
                ).first()
                if same_meeting:
                    continue
                existing = db.query(CatalystEvent).filter(
                    CatalystEvent.external_id == ev_data["external_id"],
                ).first()
                if existing:
                    if existing.event_date != ev_data["event_date"]:
                        existing.event_date = ev_data["event_date"]
                        existing.title = ev_data["title"]
                        existing.description = ev_data["description"]
                        existing.source_url = ev_data["source_url"]
                        existing.verified = True
                        total_upd += 1
                else:
                    db.add(CatalystEvent(**ev_data))
                    total_new += 1
            if i < len(docs) - 1:
                import time
                time.sleep(REQUEST_DELAY_S)

        db.commit()
        if total_new or total_upd:
            logger.info("Federal Register: %d new, %d updated", total_new, total_upd)
        else:
            logger.debug("Federal Register: no changes")
    except Exception as exc:
        logger.error("Federal Register pipeline error: %s", exc)
        db.rollback()
    finally:
        db.close()


run_federal_register_pipeline = run_pipeline
