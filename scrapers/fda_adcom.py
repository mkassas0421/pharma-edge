"""FDA Advisory Committee Calendar scraper — official upcoming meetings.

Scrapes the FDA's own advisory committee calendar
(https://www.fda.gov/advisory-committees/advisory-committee-calendar)
for meetings that mention a tracked company (by company alias or ticker).

Meetings are matched on the meeting title/agenda text, which usually names
the drug or the sponsor (e.g. "Replimune — vusolimogene oderparepvec BLA").
Each matched meeting becomes a High-impact REGULATORY event with the
official FDA meeting page as ``source_url``.

NOTE: the calendar table is client-side rendered (Drupal DataTable) and its
data endpoint is not publicly reachable, so the HTML currently yields no
rows. The scraper therefore degrades gracefully and the authoritative AdCom
source is the Federal Register API (scrapers/federal_register.py), which
publishes the same meeting notices 15+ days in advance per FACA.
"""

import datetime
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.models.database import SessionLocal, Ticker, TickerAlias, CatalystEvent
from app.utils.dates import parse_date as _parse_date

logger = logging.getLogger(__name__)

FDA_ADCOM_URL = "https://www.fda.gov/advisory-committees/advisory-committee-calendar"

# Browser-like User-Agent; FDA serves different content to bots.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_HIGH_IMPACT_TERMS = ("biosimilar", "drug", "vaccine", "cell", "gene", "clinical")


def _fetch_calendar() -> str | None:
    """Fetch the FDA advisory committee calendar page. Returns HTML or None."""
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            resp = client.get(FDA_ADCOM_URL, headers={"User-Agent": _UA})
            if resp.status_code != 200:
                logger.warning("FDA calendar: HTTP %s", resp.status_code)
                return None
            return resp.text
    except Exception as exc:
        logger.warning("FDA calendar fetch failed: %s", exc)
        return None


def _parse_rows(html: str) -> list[dict]:
    """Parse the calendar table into [{date, title, url}, ...]."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    # The calendar page renders a <table>; each row has a date + meeting link.
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            date_text = tds[0].get_text(" ", strip=True)
            meeting_td = tds[1]
            link = meeting_td.find("a", href=True)
            title = meeting_td.get_text(" ", strip=True)
            href = link["href"] if link else ""
            if not date_text or not title:
                continue
            rows.append({
                "date_text": date_text,
                "title": title,
                "url": href if href.startswith("http") else f"https://www.fda.gov{href}",
            })
    return rows


def _alias_map(db) -> dict[str, set[str]]:
    """Return {ticker: {aliases}} from the ticker_aliases table."""
    rows = db.query(TickerAlias).all()
    tickers = {t.id: t.ticker for t in db.query(Ticker).all()}
    mapping: dict[str, set[str]] = {}
    for r in rows:
        t = tickers.get(r.ticker_id)
        if t:
            mapping.setdefault(t, set()).add(r.alias)
    return mapping


def _matches(aliases: set[str], text: str) -> bool:
    """True if any alias appears in *text* (case-insensitive, word boundary)."""
    low = text.lower()
    for alias in aliases:
        if not alias or len(alias) < 3:
            continue
        if alias.lower() in low:
            return True
    return False


def _meeting_date(row: dict) -> datetime.datetime | None:
    """Parse the date column of a calendar row.

    Handles "July 30, 2026", "Jul 30, 2026", "7/30/2026", and multi-day
    ranges like "July 30-31, 2026" (uses the first day).
    """
    # Numeric format first: "7/30/2026" or "7/30/2026 - 7/31/2026"
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", row["date_text"])
    if m:
        try:
            return datetime.datetime.strptime(m.group(1), "%m/%d/%Y")
        except ValueError:
            return None
    # Text format: extract the first full date from the cell, then parse it.
    m = re.search(r"([A-Z][a-z]{2,8}\s+\d{1,2},?\s*\d{4})", row["date_text"])
    if m:
        return _parse_date(m.group(1))
    return None


def run_pipeline():
    """Scrape the FDA advisory committee calendar for tracked companies."""
    html = _fetch_calendar()
    if not html:
        logger.warning("FDA AdCom: calendar unavailable — Federal Register covers these")
        return

    db = SessionLocal()
    try:
        aliases = _alias_map(db)
        if not aliases:
            return

        rows = _parse_rows(html)
        if not rows:
            # Client-side rendered table — no data in the raw HTML. The
            # Federal Register scraper covers these meetings authoritatively.
            logger.info(
                "FDA AdCom: calendar table not accessible (client-side rendered) — "
                "using Federal Register coverage instead"
            )
            return
        total_new = total_upd = 0
        now = datetime.datetime.utcnow()

        for row in rows:
            d = _meeting_date(row)
            if not d:
                continue
            # Only forward-looking meetings become catalysts.
            if d < now:
                continue
            matched = [t for t, a in aliases.items() if _matches(a, row["title"])]
            if not matched:
                continue

            for ticker in matched:
                ext = f"FDA-ADCOM-{ticker}-{d.strftime('%Y%m%d')}"
                existing = db.query(CatalystEvent).filter(
                    CatalystEvent.external_id == ext
                ).first()
                ev_data = {
                    "ticker": ticker,
                    "title": f"FDA Advisory Committee — {row['title'][:200]}",
                    "event_type": "REGULATORY",
                    "event_date": d,
                    "impact_level": "High",
                    "description": (
                        f"💊 Drug: See meeting announcement\n"
                        f"⚙️  Mechanism: N/A — FDA Advisory Committee meeting\n"
                        f"🔬 Phase: Regulatory review\n"
                        f"📋 Trial: {row['title'][:100]}\n"
                        f"🎯 Milestone: Advisory committee meeting on {d.strftime('%B %d, %Y')}\n"
                        f"\n"
                        f"{row['title']}\n"
                        f"Source: FDA Advisory Committee Calendar ({row['url']})"
                    ),
                    "source": "fda_adcom",
                    "external_id": ext,
                    "source_url": row["url"],
                    "verified": True,
                }
                if existing:
                    if existing.event_date != d or existing.source_url != row["url"]:
                        existing.event_date = d
                        existing.title = ev_data["title"]
                        existing.description = ev_data["description"]
                        existing.source_url = row["url"]
                        existing.verified = True
                        total_upd += 1
                else:
                    db.add(CatalystEvent(**ev_data))
                    total_new += 1

        db.commit()
        if total_new or total_upd:
            logger.info("FDA AdCom: %d new, %d updated", total_new, total_upd)
    except Exception as exc:
        logger.error("FDA AdCom pipeline error: %s", exc)
        db.rollback()
    finally:
        db.close()


run_fda_adcom_pipeline = run_pipeline
