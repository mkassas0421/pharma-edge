"""Company name aliases — reads from the ``ticker_aliases`` table.

Aliases are auto-generated from the company name on first startup via
``seed_aliases()``. After that the scraper, search, and matching functions
all query the DB so users can add tickers from the UI and everything Just Works.
"""

import datetime
import logging
import re

from app.models.database import SessionLocal, Ticker, TickerAlias

logger = logging.getLogger(__name__)


def seed_aliases():
    """Auto-generate ClinicalTrials.gov aliases for every tracked ticker.

    For each ticker that has zero aliases, creates aliases from the company
    name with common suffix/prefix cleanups so the CT.gov scraper can find
    relevant studies.

    Large pharma companies also get subsidiary aliases so that studies run
    under subsidiary names (e.g. Janssen, Genzyme) are attributed correctly.
    """
    db = SessionLocal()
    try:
        tickers = db.query(Ticker).all()
        now = datetime.datetime.utcnow()
        added = 0

        # ── Extra subsidiary aliases for large pharma ──
        # Only added if the subsidiary itself is NOT a tracked ticker (avoid dupes)
        _EXTRA_ALIASES: dict[str, list[str]] = {
            "JNJ": ["Janssen Research", "Janssen Pharmaceutica", "Janssen Research & Development"],
            "PFE": ["Wyeth", "Pharmacia", "Hospira"],
            "MRK": ["Merck Sharp & Dohme", "MSD"],
            "NVS": ["Sandoz", "Novartis Institutes"],
            "AZN": ["MedImmune", "Acerta Pharma"],
            "SNY": ["Genzyme", "Sanofi Pasteur"],
        }

        for t in tickers:
            existing = db.query(TickerAlias).filter(TickerAlias.ticker_id == t.id).count()
            if existing > 0:
                # Still add extra aliases if any are missing
                extra = _EXTRA_ALIASES.get(t.ticker, [])
                for alias in extra:
                    already = db.query(TickerAlias).filter(
                        TickerAlias.ticker_id == t.id, TickerAlias.alias == alias
                    ).first()
                    if not already:
                        db.add(TickerAlias(ticker_id=t.id, alias=alias, created_at=now))
                        added += 1
                continue

            base = t.company_name
            aliases = list(dict.fromkeys([  # deduplicate preserving order
                base,
                re.sub(r"\s+(Inc\.?|PLC|Ltd\.?|Corp\.?|S\.?A\.?|N\.?V\.?|GmbH|LLC)\s*$", "", base).strip(),
                base.replace(",", ""),
            ]))
            # Add extra subsidiary aliases
            extra = _EXTRA_ALIASES.get(t.ticker, [])
            aliases.extend(a for a in extra if a not in aliases)
            for alias in aliases:
                if alias and len(alias) > 1:
                    db.add(TickerAlias(ticker_id=t.id, alias=alias, created_at=now))
                    added += 1

        if added:
            db.commit()
            logger.info("Auto-seeded %d aliases for %d tickers", added, len(tickers))
    except Exception as exc:
        logger.error("seed_aliases failed: %s", exc)
        db.rollback()
    finally:
        db.close()


# ── Internal helpers ────────────────────────────────────────────────────────

def _get_aliases(ticker: str) -> list[str]:
    db = SessionLocal()
    try:
        ticker_obj = db.query(Ticker).filter(Ticker.ticker == ticker.upper()).first()
        if not ticker_obj:
            return []
        rows = db.query(TickerAlias).filter(TickerAlias.ticker_id == ticker_obj.id).all()
        return [r.alias for r in rows]
    finally:
        db.close()


def _clean_tokens(text: str) -> list[str]:
    """Split, strip punctuation, remove noise words."""
    noise = {"inc", "inc.", "ltd", "ltd.", "plc", "corp", "corp.",
             "corporation", "sa", "n.v.", "s.a.", "gmbh", "llc", "co."}
    stripped = re.sub(r"[^\w\s]", " ", text)
    return [w for w in stripped.lower().split() if w not in noise]


# ── Public API ──────────────────────────────────────────────────────────────

def search_terms(ticker: str) -> list[str]:
    """Return the best quoted search terms for a ticker."""
    aliases = _get_aliases(ticker)
    return [f'"{a}"' for a in aliases[:2]]


def matches_ticker(ticker: str, sponsor_name: str) -> bool:
    """Check if *sponsor_name* (from ClinicalTrials.gov) belongs to *ticker*."""
    if not sponsor_name:
        return False

    name_lower = sponsor_name.lower()
    aliases = _get_aliases(ticker)
    if not aliases:
        return False

    # 1. Normalised exact match (strip punctuation, extra spaces)
    norm_name = re.sub(r"[^\w\s]", "", name_lower).strip()
    for alias in aliases:
        norm_alias = re.sub(r"[^\w\s]", "", alias.lower()).strip()
        if norm_alias == norm_name:
            return True

    # 2. Token overlap >= 60%
    name_tokens = _clean_tokens(sponsor_name)
    for alias in aliases:
        alias_tokens = _clean_tokens(alias)
        if not alias_tokens or not name_tokens:
            continue
        matches = sum(1 for w in alias_tokens if w in name_tokens)
        score = (matches / max(len(alias_tokens), len(name_tokens))) * 100
        if score >= 60:
            return True

    return False
