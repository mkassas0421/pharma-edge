"""Delete fabricated (AI-generated) catalyst events from the database.

Events with source ``manual``, ``rttnews_fda``, or ``known_pdufa`` were
created by an earlier AI-generated seed list and are not backed by any
official source — many reference drugs that were already approved years
ago, with invented dates.

Only events from official government sources remain: ClinicalTrials.gov,
SEC EDGAR, the Federal Register, and the FDA Advisory Committee Calendar.

Idempotent — safe to run repeatedly (also called at every startup from
``main.py`` before ``seed_database()``).
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.models.database import SessionLocal, CatalystEvent  # noqa: E402

FABRICATED_SOURCES = ("manual", "rttnews_fda", "known_pdufa")


def cleanup(db=None) -> int:
    """Delete all fabricated events. Returns the number of rows deleted."""
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    try:
        deleted = db.query(CatalystEvent).filter(
            CatalystEvent.source.in_(FABRICATED_SOURCES)
        ).delete(synchronize_session="fetch")
        db.commit()
        return deleted
    finally:
        if should_close:
            db.close()


if __name__ == "__main__":
    print(f"Deleting fabricated events (source IN {FABRICATED_SOURCES})...")
    count = cleanup()
    print(f"Deleted {count} fabricated event(s).")
