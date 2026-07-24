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

logger = logging.getLogger(__name__)

SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
SEC_SEARCH = "https://efts.sec.gov/LATEST/search-index"
H = {"User-Agent": "PharmaCatalystAlert/1.0 (research@example.com)"}

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


def _parse_date(s: str) -> datetime.datetime | None:
    s = s.strip().replace(",", "")
    for fmt in ("%B %d %Y", "%b %d %Y", "%B %Y"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _extract_drug(text: str) -> str:
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


def _get_files(cik: str, adsh: str) -> list[dict]:
    ac = adsh.replace("-", "")
    try:
        with httpx.Client(timeout=15, headers=H) as cl:
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
    try:
        with httpx.Client(timeout=15, headers=H) as cl:
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


def process_one(ticker: str, tid: int, cik: str, adsh: str, db, now):
    files = _get_files(cik, adsh)
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
            title = f"PDUFA date — {r['drug']}" if r['drug'] != "Unknown" else f"PDUFA date — {ticker}"
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
            ))
            return 1, 0
    return 0, 0


def run_catchup(db, ticker_map, now):
    """Broad SEC search + per-ticker fallback."""
    total_n = 0
    total_u = 0
    found_in_broad = set()

    for page in range(1, 11):
        params = {"q": "PDUFA", "dateRange": "2y", "page": page, "r": 100}
        try:
            with httpx.Client(timeout=25, headers=H) as cl:
                resp = cl.get(SEC_SEARCH, params=params)
                if resp.status_code != 200:
                    continue
                body = resp.json()
        except Exception:
            continue
        for hit in body.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            adsh = src.get("adsh", ""); ciks = src.get("ciks", [])
            if not adsh or not ciks:
                continue
            display = " ".join(src.get("display_names", []))
            ticker = next((t for t in ticker_map if t in display), None)
            if not ticker:
                continue
            found_in_broad.add(ticker)
            n, u = process_one(ticker, ticker_map[ticker], ciks[0], adsh, db, now)
            total_n += n; total_u += u

    # Per-ticker fallback for missed tickers
    missed = set(ticker_map.keys()) - found_in_broad
    for ticker in missed:
        params = {"q": f"PDUFA AND {ticker}", "dateRange": "2y", "page": 1, "r": 5}
        try:
            with httpx.Client(timeout=20, headers=H) as cl:
                resp = cl.get(SEC_SEARCH, params=params)
                if resp.status_code != 200:
                    continue
                body = resp.json()
        except Exception:
            continue
        for hit in body.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            adsh = src.get("adsh", ""); ciks = src.get("ciks", [])
            if not adsh or not ciks:
                continue
            if ticker not in " ".join(src.get("display_names", [])):
                continue
            n, u = process_one(ticker, ticker_map[ticker], ciks[0], adsh, db, now)
            total_n += n; total_u += u

    return total_n, total_u, len(found_in_broad)


def run_feed(db, ticker_map, now):
    """Check Atom feed for both 8-K and 6-K filings."""
    total_n = 0
    total_u = 0

    for feed_type in ('8-K', '6-K'):
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={feed_type}&output=atom"
        try:
            with httpx.Client(timeout=20, headers=H) as cl:
                resp = cl.get(url)
                resp.raise_for_status()
        except Exception:
            continue

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
            if not cik_m or not tk_m or tk_m.group(1) not in ticker_map:
                continue
            accn_m = re.search(r"AccNo:\s*(\S+)", summary)
            if not accn_m:
                continue
            n, u = process_one(tk_m.group(1), ticker_map[tk_m.group(1)], cik_m.group(1), accn_m.group(1), db, now)
            total_n += n; total_u += u

    return total_n, total_u


def run_pipeline():
    global _CATCHUP_DONE
    db = SessionLocal()
    try:
        tm = {t.ticker: t.id for t in db.query(Ticker).all()}
        if not tm:
            return
        now = datetime.datetime.utcnow()
        tn, tu = 0, 0

        if not _CATCHUP_DONE:
            n, u, matched = run_catchup(db, tm, now)
            tn, tu = n, u
            _CATCHUP_DONE = True
            if n or u:
                db.commit()
            logger.info("Catch-up: %d new, %d updated (matched %d tickers)", n, u, matched)

        n, u = run_feed(db, tm, now)
        tn += n; tu += u
        if n or u:
            db.commit()
        logger.debug("PDUFA: +%d/-%d this run", tn, tu)

    except Exception as exc:
        logger.error("PDUFA: %s", exc)
        db.rollback()
    finally:
        db.close()


run_pdufa_pipeline = run_pipeline
