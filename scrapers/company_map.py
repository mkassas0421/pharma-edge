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
            "JNJ": ["Janssen Research", "Janssen Pharmaceutica", "Janssen Research & Development", "Janssen Biotech"],
            "PFE": ["Wyeth", "Pharmacia", "Hospira"],
            "MRK": ["Merck Sharp & Dohme", "MSD", "Merck Research Laboratories"],
            "NVS": ["Sandoz", "Novartis Institutes", "Novartis Pharma", "Novartis Vaccines"],
            "AZN": ["MedImmune", "Acerta Pharma", "Alexion Pharmaceuticals"],
            "SNY": ["Genzyme", "Sanofi Pasteur", "Sanofi Aventis"],
            "LLY": ["Eli Lilly Research Laboratories", "Lilly Research", "Lilly USA"],
            "BMY": ["Bristol Myers Squibb Research", "Celgene"],
            "ABBV": ["Abbott Laboratories"],  # historical parent
            "AMGN": ["Amgen Research"],
            "GILD": ["Gilead Sciences Inc", "Kite Pharma"],
            "NVO": ["Novo Nordisk Research"],
            "TAK": ["Takeda Development Center", "Takeda Oncology", "Millennium Pharmaceuticals"],
            "REGN": ["Regeneron Genetics Center"],
            "BIIB": ["Biogen Research"],
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
    """Split, strip punctuation, remove noise words.

    The list covers corporate suffixes (Inc, PLC, GmbH…), industry-generic
    words (research, therapeutics, biotech…) and connectors. Without these,
    "Eli Lilly Research Laboratories" would only 50%-overlap "Eli Lilly and
    Company" and legitimately fail to match. Note: "N.V." / "S.A." arrive as
    bare "n v" / "s a" after punctuation stripping, so the single letters
    are noise too.
    """
    noise = {
        # corporate suffixes
        "inc", "inc.", "ltd", "ltd.", "plc", "corp", "corp.", "corporation",
        "sa", "n.v.", "s.a.", "gmbh", "llc", "co.", "limited", "holdings",
        "holding", "group", "company", "international",
        # single letters left over from dotted suffixes
        "n", "v", "s", "a",
        # connectors
        "and", "the", "of", "for", "&",
        # industry-generic descriptors
        "research", "laboratories", "labs", "pharmaceuticals", "therapeutics",
        "biosciences", "bioscience", "biotech", "biotechnology", "biopharma",
        "biopharmaceutical", "pharma", "pharmaceutical", "sciences",
        "healthcare", "medical", "medicine", "oncology",
    }
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

    # 2. Token overlap >= 50%
    # The expanded noise list above removes most industry-generic words, so
    # remaining tokens are distinctive — 50% is enough for a genuine match
    # while staying below the 60% that rejected "Eli Lilly Research Labs".
    name_tokens = _clean_tokens(sponsor_name)
    for alias in aliases:
        alias_tokens = _clean_tokens(alias)
        if not alias_tokens or not name_tokens:
            continue
        matches = sum(1 for w in alias_tokens if w in name_tokens)
        score = (matches / max(len(alias_tokens), len(name_tokens))) * 100
        if score >= 50:
            return True

    return False
