"""ClinicalTrials.gov scraper — discovers & refreshes catalyst events for tracked companies.

Uses the official API v2 (no API key required). Company matching is driven by
the alias list in the ``ticker_aliases`` table.

The pipeline both INSERTS new studies and UPDATES existing ones (date, title,
phase, description) on every run so data stays current.
"""

import datetime
import logging
import re

import httpx

from app.models.database import SessionLocal, Ticker, CatalystEvent
from scrapers.company_map import search_terms, matches_ticker

logger = logging.getLogger(__name__)

CLINICAL_TRIALS_API = "https://clinicaltrials.gov/api/v2/studies"

PHASE_MAP = {
    "PHASE3": ("PHASE3_READOUT", "High"),
    "PHASE2": ("PHASE2_READOUT", "Medium"),
    "PHASE1": ("PHASE1_READOUT", "Low"),
    "PHASE4": ("REGULATORY", "Medium"),
    "EARLY_PHASE1": ("PHASE1_READOUT", "Low"),
}


def _parse_date(s: str | None) -> datetime.datetime | None:
    if not s:
        return None
    s = s.strip()[:10]
    if len(s) == 7 and s[4] == "-":
        s = f"{s}-01"
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def _best_date(status_mod: dict) -> datetime.datetime | None:
    for key in ("primaryCompletionDateStruct", "completionDateStruct", "startDateStruct"):
        struct = status_mod.get(key)
        if isinstance(struct, dict):
            d = _parse_date(struct.get("date"))
        elif isinstance(struct, str):
            d = _parse_date(struct)
        else:
            continue
        if d:
            return d
    return None


def _extract_drug_name(title: str, interventions: list[dict]) -> str:
    """Extract a drug/compound name from the trial title or interventions."""
    for inv in interventions:
        name = (inv.get("name") or "").strip()
        if name and len(name) < 80:
            return name

    title_clean = title.strip()
    patterns = [
        r"\b(of|for|with)\s+([A-Z][A-Za-z0-9À-ɏ·\-]+(?:\([^)]+\))?)",
        r"\b(?:Study|Trial)\s+(?:Evaluating|of|to\s+Evaluate)\s+([A-Z][A-Za-z0-9À-ɏ·\-]+)",
        r"([A-Z][A-Za-z0-9À-ɏ·\-]+)\s+(?:in|for|versus|vs|compared|combination|administered)",
    ]
    skip_words = {"the","this","with","for","safety","efficacy","study","patients",
                  "treatment","effect","open","label","dose","phase","evaluate",
                  "evaluating","single","part","multiple","trial","human"}

    for pat in patterns:
        m = re.search(pat, title_clean)
        if m:
            cand = m.group(1).strip(".,;:()[]{}\"'")
            if cand.lower() not in skip_words and len(cand) > 1:
                return cand

    for word in title_clean.split():
        w = word.strip(".,;:()[]{}\"'")
        if len(w) > 2 and w[0].isupper() and not w.isupper():
            return w

    return "Investigational"


def _scrape_company(ticker: str, ticker_id: int) -> list[dict]:
    """Fetch recent/future Phase 2+ studies for a single company."""
    terms = search_terms(ticker)
    if not terms:
        return []

    seen_ncts: set[str] = set()
    events: list[dict] = []

    for term in terms:
        params = {
            "query.term": term,
            "pageSize": 30,
            "format": "json",
            "sort": "LastUpdatePostDate",
        }

        try:
            with httpx.Client(timeout=25) as client:
                resp = client.get(CLINICAL_TRIALS_API, params=params)
                if resp.status_code == 429:
                    logger.warning("Rate-limited on %s (term=%s)", ticker, term)
                    continue
                resp.raise_for_status()
                body = resp.json()
        except Exception as exc:
            logger.debug("scrape(%s, term=%s): %s", ticker, term, exc)
            continue

        for study in body.get("studies", []):
            nct = (
                study.get("protocolSection", {})
                .get("identificationModule", {})
                .get("nctId", "")
            )
            if not nct or nct in seen_ncts:
                continue
            seen_ncts.add(nct)

            ev = _study_to_event(study, ticker, ticker_id)
            if ev:
                events.append(ev)

    if events:
        logger.info("Found %d candidate(s) for %s", len(events), ticker)
    return events


def _study_to_event(study: dict, ticker: str, ticker_id: int) -> dict | None:
    """Convert an API study to a CatalystEvent dict, or None if irrelevant.

    Produces a structured ``description`` so the frontend modal works.
    """
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    sc = proto.get("sponsorCollaboratorsModule", {})
    sm = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    conditions = proto.get("conditionsModule", {}).get("conditions", [])
    interventions = proto.get("armsInterventionsModule", {}).get("interventions", [])

    nct_id = ident.get("nctId", "")
    title = ident.get("briefTitle", "")
    if not nct_id or not title:
        return None

    # ── Sponsor ──
    sponsor_name = (sc.get("leadSponsor") or {}).get("name", "")
    if not sponsor_name or not matches_ticker(ticker, sponsor_name):
        return None

    # ── Phase ──
    phases = design.get("phases", [])
    phase_str = "PHASE1"
    for p in ("PHASE3", "PHASE2", "PHASE4"):
        if p in phases:
            phase_str = p
            break
    # Phase 1/2 combo detected → treat as Phase 2
    if phase_str == "PHASE1" and "PHASE2" in phases:
        phase_str = "PHASE2"

    event_type, impact = PHASE_MAP.get(phase_str, ("PHASE1_READOUT", "Low"))

    # ── Date ──
    ev_date = _best_date(sm)
    if not ev_date:
        return None

    now = datetime.datetime.utcnow()
    if ev_date < now - datetime.timedelta(days=90):
        return None

    # ── Build structured description ──
    drug_name = _extract_drug_name(title, interventions)
    condition_str = conditions[0] if conditions else "Various"
    trial_phase = phase_str.replace("_", " ").title()
    overall_status = sm.get("overallStatus", "")
    milestone = (
        f"{event_type.replace('_', ' ').title()}"
        f" — estimated primary completion {ev_date.strftime('%b %Y')}"
    )
    background = (
        f"Sponsored by {sponsor_name}. This {trial_phase} trial "
        f"({nct_id}) is currently {overall_status.replace('_', ' ').lower()} "
        f"and investigates {drug_name} in {condition_str} patients. "
        f"Primary completion is estimated for {ev_date.strftime('%B %Y')}. "
        f"Source: ClinicalTrials.gov."
    )

    desc_parts = [
        f"💊 Drug: {drug_name}",
        f"⚙️  Mechanism: See trial details on ClinicalTrials.gov",
        f"🔬 Phase: {trial_phase}",
        f"📋 Trial: {nct_id}",
        f"🎯 Milestone: {milestone}",
        "",
        background,
    ]

    return {
        "ticker": ticker,
        "ticker_id": ticker_id,
        "title": title[:200],
        "event_type": event_type,
        "event_date": ev_date,
        "impact_level": impact,
        "description": "\n".join(desc_parts),
        "source": "clinicaltrials_gov",
        "external_id": nct_id,
    }


def run_pipeline():
    """Scrape ClinicalTrials.gov for every tracked company.

    * New studies are INSERTED as new CatalystEvent rows.
    * Existing studies are UPDATED (date, title, description, phase, impact).
      The ``alert_sent`` timestamp is preserved so already-alerted events
      stay alerted.
    * Studies the API no longer returns are left untouched.
    * Status changes (phase upgrades, new completions) are sent to
      ``#clinical-trials-updates`` on Discord.
    """
    db = SessionLocal()
    try:
        tickers = db.query(Ticker).all()
        if not tickers:
            return

        total_new = 0
        total_upd = 0
        changes = []  # collect (ticker, company, drug, change_desc, nct_id)

        for t in tickers:
            candidates = _scrape_company(t.ticker, t.id)
            for ev_data in candidates:
                existing = db.query(CatalystEvent).filter(
                    CatalystEvent.external_id == ev_data["external_id"],
                    CatalystEvent.ticker == ev_data["ticker"],
                ).first()

                if existing:
                    # Detect meaningful changes for the clinical-trials channel
                    _detect_change(existing, ev_data, t, changes)
                    # Refresh fields but keep alert_sent
                    existing.event_date = ev_data["event_date"]
                    existing.title = ev_data["title"]
                    existing.event_type = ev_data["event_type"]
                    existing.impact_level = ev_data["impact_level"]
                    existing.description = ev_data["description"]
                    total_upd += 1
                else:
                    db.add(CatalystEvent(**ev_data))
                    total_new += 1

        if total_new or total_upd:
            db.commit()
            logger.info("Pipeline: %d new, %d updated", total_new, total_upd)
        else:
            logger.debug("Pipeline: no changes")

        # ── Push change notifications ──
        if changes and settings.discord_webhook_clinical:
            _send_clinical_changes(changes)

    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        db.rollback()
    finally:
        db.close()


def _detect_change(existing, ev_data, ticker_obj, changes):
    """Compare old and new event data; append to *changes* if notable."""
    old_type = existing.event_type
    new_type = ev_data["event_type"]
    old_date = existing.event_date
    new_date = ev_data["event_date"]

    # Phase upgrade: e.g. PHASE2_READOUT → PHASE3_READOUT
    upgrade_order = {"PHASE1_READOUT": 1, "PHASE2_READOUT": 2, "PHASE3_READOUT": 3, "PDUFA": 4}
    if old_type in upgrade_order and new_type in upgrade_order and upgrade_order.get(new_type, 0) > upgrade_order.get(old_type, 0):
        # Extract drug name from description
        drug = _extract_drug_from_desc(existing.description)
        changes.append((
            existing.ticker,
            ticker_obj.company_name if ticker_obj else existing.ticker,
            drug,
            f"**Phase Upgrade** — moved from {old_type.replace('_', ' ').title()} → {new_type.replace('_', ' ').title()} for {existing.title[:80]}",
            existing.external_id or "",
        ))
        return

    # Significant date change (slipped more than 30 days)
    if old_date and new_date:
        delta = (new_date - old_date).days
        if abs(delta) > 30:
            direction = "delayed" if delta > 0 else "advanced"
            drug = _extract_drug_from_desc(existing.description)
            changes.append((
                existing.ticker,
                ticker_obj.company_name if ticker_obj else existing.ticker,
                drug,
                f"**Date Change** — {direction} by {abs(delta)} days (was {old_date.strftime('%b %Y')} → {new_date.strftime('%b %Y')}) for {existing.title[:80]}",
                existing.external_id or "",
            ))


def _extract_drug_from_desc(desc: str) -> str:
    """Pull drug name from the structured description field."""
    if not desc:
        return "Unknown"
    for line in desc.split("\n"):
        if line.startswith("💊 Drug:"):
            return line.replace("💊 Drug:", "").strip()
    return "Investigational"


def _send_clinical_changes(changes: list):
    """Send batched clinical trial change notifications to Discord."""
    from app.services.notifier import send_clinical_change
    for ticker, company, drug, change_desc, nct_id in changes:
        send_clinical_change(ticker, company, drug, change_desc, nct_id)
