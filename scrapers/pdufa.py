"""PDUFA date scraper — monitors SEC 8-K AND 6-K filings for FDA decision dates.

Catch-up: searches SEC EDGAR for PDUFA filings from last 2 years across
both 8-K (domestic) and 6-K (foreign) filings.
Ongoing: polls the SEC Atom feed for both form types every 60 minutes.
"""

import datetime
import logging
import re
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from app.models.database import SessionLocal, Ticker, CatalystEvent
from app.utils.dates import parse_date as _parse_date
from app.utils.http import SEC_HEADERS

logger = logging.getLogger(__name__)

SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
SEC_SEARCH = "https://efts.sec.gov/LATEST/search-index"

PDUFA_PATTERNS = [
    r"assigned\s+(?:a\s+)?PDUFA\s+(?:goal\s+)?(?:target\s+)?action\s+date\s+(?:of|is)\s+(\w+\s+\d{1,2},?\s*\d{4})",
    r"PDUFA\s+(?:target\s+)?action\s+date\s+(?:of|is|for|set\s+for)\s+(\w+\s+\d{1,2},?\s*\d{4})",
    r"PDUFA\s+date\s+(?:of|is|set\s+for)\s+(\w+\s+\d{1,2},?\s*\d{4})",
    r"PDUFA\s+goal\s+date\s+(?:of|is)\s+(\w+\s+\d{1,2},?\s*\d{4})",
    r"(?:anticipated|expected)\s+(?:PDUFA\s+)?action\s+date\s+(?:of|is|set\s+for)\s+(\w+\s+\d{1,2},?\s*\d{4})",
    r"FDA\s+(?:has\s+)?set\s+(?:a\s+)?(?:PDUFA\s+)?(?:target\s+)?(?:action\s+)?date\s+(?:of|for)\s+(\w+\s+\d{1,2},?\s*\d{4})",
    r"(?:target|action)\s+date\s+(?:of|is|set\s+for)\s+(\w+\s+\d{1,2},?\s*\d{4})\s+(?:under\s+)?PDUFA",
    r"(?:prescription\s+drug\s+user\s+fee\s+act|PDUFA)\s+(?:target\s+)?date\s+(?:of|is|:)\s+(\w+\s+\d{1,2},?\s*\d{4})",
]

_CATCHUP_DONE = False


def _extract_drug(text: str) -> str:
    """Extract a drug name from text surrounding a PDUFA mention."""
    for p in [
        r"(?:for|of)\s+([A-Z][A-Za-z0-9\-à-ɏ\(\)]+)\s*(?:\(NDA|\(BLA|\(sNDA|,|\.)",
        r"PDUFA\s+date\s+for\s+([A-Z][A-Za-z0-9\-à-ɏ]+)",
    ]:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            c = m.group(1).strip(".,;:()[]{}\"'")
            if len(c) > 2:
                return c
    return "Unknown"


def _get_filing_files(cik: str, adsh: str) -> list[dict]:
    """List .htm filing documents for a given CIK + accession number."""
    ac = adsh.replace("-", "")
    try:
        with httpx.Client(timeout=15, headers=SEC_HEADERS) as cl:
            resp = cl.get(f"{SEC_ARCHIVE}/{cik.lstrip('0')}/{ac}/", follow_redirects=True)
            resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    files = []
    for a in soup.find_all("a", href=True):
        n = a.get_text(strip=True)
        if not n or n in ("Name", "Parent Directory", "..", "."):
            continue
        if n.endswith(".htm"):
            fn = a["href"].split("/")[-1]
            files.append({"name": n, "url": f"{SEC_ARCHIVE}/{cik.lstrip('0')}/{ac}/{fn}"})
    return files


def _check_pdufa(url: str) -> dict | None:
    """Fetch a filing document and search for PDUFA dates."""
    try:
        with httpx.Client(timeout=15, headers=SEC_HEADERS) as cl:
            resp = cl.get(url)
            resp.raise_for_status()
            text = resp.text
    except Exception:
        return None
    if "PDUFA" not in text:
        return None
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"&[a-z]+;", "", clean)
    for p in PDUFA_PATTERNS:
        m = re.search(p, clean, re.IGNORECASE)
        if m:
            dt = _parse_date(m.group(1))
            if dt:
                return {"date": dt, "drug": _extract_drug(clean)}
    return None


def _process_filing(ticker: str, tid: int, cik: str, adsh: str, db, now) -> tuple[int, int]:
    """Process one SEC filing for PDUFA dates. Returns (new_count, updated_count)."""
    files = _get_filing_files(cik, adsh)
    if not files:
        return 0, 0
    urls = []
    for f in files:
        n = f["name"].lower()
        if "ex-99" in n or "ex99" in n or "ex_99" in n:
            urls.insert(0, f["url"])
        elif "ex-10" in n or "ex10" in n:
            continue
        elif f["name"].endswith(".htm"):
            urls.append(f["url"])
    for u in urls:
        r = _check_pdufa(u)
        if r and r["date"] >= now - datetime.timedelta(days=30):
            ext = f"SEC-{ticker}-{r['date'].strftime('%Y%m%d')}"
            title = f"PDUFA date — {r['drug']}" if r["drug"] != "Unknown" else f"PDUFA date — {ticker}"
            exist = db.query(CatalystEvent).filter(CatalystEvent.external_id == ext).first()
            if exist:
                if exist.event_date != r["date"] or exist.title != title:
                    exist.event_date = r["date"]
                    exist.title = title
                    return 0, 1
                return 0, 0
            db.add(CatalystEvent(
                ticker=ticker, ticker_id=tid, title=title,
                event_type="PDUFA", event_date=r["date"], impact_level="High",
                description=f"FDA PDUFA target action date for {r['drug']} ({ticker}). Source: SEC 8-K ({adsh}).",
                source="sec_edgar_pdufa", external_id=ext,
                source_url=f"{SEC_ARCHIVE}/{cik.lstrip('0')}/{adsh.replace('-', '')}/",
                verified=True,
            ))
            return 1, 0
    return 0, 0


def _search_sec_pdufa(query: str, page: int = 1, page_size: int = 100) -> list[dict]:
    """Query the SEC search index for PDUFA-related filings."""
    params = {"q": query, "dateRange": "2y", "page": page, "r": page_size}
    try:
        with httpx.Client(timeout=25, headers=SEC_HEADERS) as cl:
            resp = cl.get(SEC_SEARCH, params=params)
            if resp.status_code != 200:
                return []
            return resp.json().get("hits", {}).get("hits", [])
    except Exception:
        return []


def run_catchup(db, ticker_map, now):
    """Broad SEC search + per-ticker fallback for historical PDUFA filings."""
    total_n = total_u = 0
    found_in_broad = set()

    for page in range(1, 11):
        hits = _search_sec_pdufa("PDUFA", page=page)
        for hit in hits:
            src = hit.get("_source", {})
            adsh = src.get("adsh", "")
            ciks = src.get("ciks", [])
            if not adsh or not ciks:
                continue
            display = " ".join(src.get("display_names", []))
            ticker = next((t for t in ticker_map if t in display), None)
            if not ticker:
                continue
            found_in_broad.add(ticker)
            n, u = _process_filing(ticker, ticker_map[ticker], ciks[0], adsh, db, now)
            total_n += n
            total_u += u

    # Per-ticker fallback for tickers not caught in the broad search
    missed = set(ticker_map.keys()) - found_in_broad
    for ticker in missed:
        hits = _search_sec_pdufa(f"PDUFA AND {ticker}", page=1, page_size=5)
        for hit in hits:
            src = hit.get("_source", {})
            adsh = src.get("adsh", "")
            ciks = src.get("ciks", [])
            if not adsh or not ciks:
                continue
            if ticker not in " ".join(src.get("display_names", [])):
                continue
            n, u = _process_filing(ticker, ticker_map[ticker], ciks[0], adsh, db, now)
            total_n += n
            total_u += u

    return total_n, total_u, len(found_in_broad)


def _parse_atom_feed(feed_type: str) -> list[dict]:
    """Parse SEC Atom feed for *feed_type* (8-K or 6-K) and return entries matching tracked tickers."""
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={feed_type}&output=atom"
    try:
        with httpx.Client(timeout=20, headers=SEC_HEADERS) as cl:
            resp = cl.get(url)
            resp.raise_for_status()
    except Exception:
        return []

    entries = []
    root = ET.fromstring(resp.text)
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        se = entry.find("{http://www.w3.org/2005/Atom}summary")
        te = entry.find("{http://www.w3.org/2005/Atom}title")
        if se is None or te is None:
            continue
        title = te.text or ""
        summary = se.text or ""
        cik_m = re.search(r"(\d{10})", title)
        tk_m = re.search(r"\(([A-Z]{2,5})\)\s*\(Filer\)", title)
        accn_m = re.search(r"AccNo:\s*(\S+)", summary)
        if cik_m and tk_m and accn_m:
            entries.append({
                "ticker": tk_m.group(1),
                "cik": cik_m.group(1),
                "accession": accn_m.group(1),
            })
    return entries


def run_feed(db, ticker_map, now):
    """Check Atom feed for both 8-K and 6-K PDUFA filings."""
    total_n = total_u = 0
    for feed_type in ("8-K", "6-K"):
        entries = _parse_atom_feed(feed_type)
        for e in entries:
            if e["ticker"] not in ticker_map:
                continue
            n, u = _process_filing(e["ticker"], ticker_map[e["ticker"]], e["cik"], e["accession"], db, now)
            total_n += n
            total_u += u
    return total_n, total_u


def run_pipeline():
    """Main PDUFA pipeline — catch-up once, then feed polling."""
    global _CATCHUP_DONE
    db = SessionLocal()
    try:
        tm = {t.ticker: t.id for t in db.query(Ticker).all()}
        if not tm:
            return
        now = datetime.datetime.utcnow()
        tn = tu = 0

        if not _CATCHUP_DONE:
            n, u, matched = run_catchup(db, tm, now)
            tn, tu = n, u
            _CATCHUP_DONE = True
            if n or u:
                db.commit()
            logger.info("Catch-up: %d new, %d updated (matched %d tickers)", n, u, matched)

        n, u = run_feed(db, tm, now)
        tn += n
        tu += u
        if n or u:
            db.commit()
        logger.debug("PDUFA: +%d/-%d this run", tn, tu)

    except Exception as exc:
        logger.error("PDUFA: %s", exc)
        db.rollback()
    finally:
        db.close()


run_pdufa_pipeline = run_pipeline
