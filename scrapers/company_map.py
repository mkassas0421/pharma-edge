"""Company name aliases — reads from the ``ticker_aliases`` table.

The hardcoded seed data in ``_SEED_ALIASES`` is migrated to the database
on first startup via ``seed_aliases()``. After that the scraper, search,
and matching functions all query the DB so users can add tickers from the
UI and everything Just Works.
"""

import datetime
import logging
import re

from app.models.database import SessionLocal, Ticker, TickerAlias

logger = logging.getLogger(__name__)

# ── Seed data (migrated to DB once on first launch) ─────────────────────────

_SEED_ALIASES: dict[str, list[str]] = {
    "AMGN": ["Amgen", "Amgen Inc.", "Amgen Inc"],
    "BIIB": ["Biogen", "Biogen Inc.", "Biogen Inc"],
    "GILD": ["Gilead Sciences", "Gilead Sciences, Inc.", "Kite, A Gilead Company"],
    "MRNA": ["ModernaTX, Inc.", "Moderna"],
    "REGN": ["Regeneron Pharmaceuticals", "Regeneron"],
    "VRTX": ["Vertex Pharmaceuticals Incorporated", "Vertex Pharmaceuticals"],
    "SNY": ["Sanofi", "Sanofi-Aventis"],
    "AZN": ["AstraZeneca", "AstraZeneca PLC", "Acerta Pharma BV"],
    "ALKS": ["Alkermes, Inc.", "Alkermes"],
    "BMRN": ["BioMarin Pharmaceutical", "BioMarin"],
    "CRSP": ["CRISPR Therapeutics", "CRISPR Therapeutics AG"],
    "EXEL": ["Exelixis, Inc.", "Exelixis"],
    "NTLA": ["Intellia Therapeutics", "Intellia"],
    "SRPT": ["Sarepta Therapeutics, Inc.", "Sarepta Therapeutics"],
    "UTHR": ["United Therapeutics", "United Therapeutics Corporation"],
    "BGNE": ["BeiGene", "BeiGene, Ltd."],
    "ACAD": ["ACADIA Pharmaceuticals Inc.", "ACADIA Pharmaceuticals"],
    "ALLO": ["Allogene Therapeutics", "Allogene"],
    "BEAM": ["Beam Therapeutics", "Beam Therapeutics Inc."],
    "EDIT": ["Editas Medicine, Inc.", "Editas Medicine"],
    "FATE": ["Fate Therapeutics", "Fate Therapeutics, Inc."],
    "RXRX": ["Recursion Pharmaceuticals Inc.", "Recursion Pharmaceuticals"],
    "RCKT": ["Rocket Pharmaceuticals", "Rocket Pharmaceuticals, Inc."],
    "VERV": ["Verve Therapeutics", "Verve"],
    "CRBU": ["Caribou Biosciences", "Caribou"],
    "DNLI": ["Denali Therapeutics", "Denali"],
    "KURA": ["Kura Oncology", "Kura Oncology, Inc."],
    "RCUS": ["Arcus Biosciences", "Arcus Biosciences, Inc."],
    "KYMR": ["Kymera Therapeutics, Inc.", "Kymera Therapeutics"],
    "NBIX": ["Neurocrine Biosciences", "Neurocrine Biosciences, Inc.", "Neurocrine UK Limited"],
    "IONS": ["Ionis Pharmaceuticals, Inc.", "Ionis Pharmaceuticals"],
}


def seed_aliases():
    """Populate the ``ticker_aliases`` table from ``_SEED_ALIASES``. Idempotent."""
    db = SessionLocal()
    try:
        if db.query(TickerAlias).count() > 0:
            return

        now = datetime.datetime.utcnow()
        added = 0
        for ticker_sym, aliases in _SEED_ALIASES.items():
            ticker_obj = db.query(Ticker).filter(Ticker.ticker == ticker_sym).first()
            if not ticker_obj:
                continue
            for alias in aliases:
                db.add(TickerAlias(ticker_id=ticker_obj.id, alias=alias, created_at=now))
                added += 1

        db.commit()
        logger.info("Seeded %d aliases for %d tickers", added, len(_SEED_ALIASES))
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
