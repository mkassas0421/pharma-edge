"""Backfill ``source_url`` / ``verified`` for events already in the database.

* ClinicalTrials.gov events → link to the official study page
  (``https://clinicaltrials.gov/study/{NCT}``) and mark verified.
* SEC EDGAR PDUFA events → mark verified; the accession number cannot be
  reconstructed into a stable URL from ``external_id`` alone, so no URL.

Idempotent — safe to run repeatedly.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.models.database import SessionLocal, CatalystEvent  # noqa: E402


def backfill() -> int:
    """Backfill source_url/verified for existing real events. Returns rows touched."""
    db = SessionLocal()
    touched = 0
    try:
        ct_events = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.source == "clinicaltrials_gov",
                CatalystEvent.source_url.is_(None),
            )
            .all()
        )
        for ev in ct_events:
            if ev.external_id:
                ev.source_url = f"https://clinicaltrials.gov/study/{ev.external_id}"
                ev.verified = True
                touched += 1

        sec_events = (
            db.query(CatalystEvent)
            .filter(
                CatalystEvent.source == "sec_edgar_pdufa",
                CatalystEvent.verified.is_(False),
            )
            .all()
        )
        for ev in sec_events:
            ev.verified = True
            touched += 1

        db.commit()
        return touched
    finally:
        db.close()


if __name__ == "__main__":
    count = backfill()
    print(f"Backfilled source_url/verified for {count} event(s).")
