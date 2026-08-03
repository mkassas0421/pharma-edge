"""One-time cleanup of duplicate catalyst events (identical external_id + ticker).

The SEC PDUFA scraper's within-run dedup was blind (autoflush=False), so one
8-K filing could insert several rows sharing the same external_id
(SEC-{ticker}-{date}). This script keeps the EARLIEST row per
(external_id, ticker) group and deletes the rest — including their
EventReaction rows (one per event, no FK cascade; duplicates of the kept
event's own reaction). Manual events (external_id NULL) are never touched.

Usage (from the project root — connects to whatever DATABASE_URL the
environment resolves to, i.e. the production PostgreSQL in prod):
    python scripts/cleanup_duplicate_events.py --dry-run   # report only
    python scripts/cleanup_duplicate_events.py             # delete
"""

import argparse
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import func  # noqa: E402

from app.models.database import SessionLocal, CatalystEvent, EventReaction  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cleanup")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be deleted without deleting anything")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        dupe_groups = (
            db.query(CatalystEvent.external_id, CatalystEvent.ticker, func.count())
            .filter(CatalystEvent.external_id.isnot(None))
            .group_by(CatalystEvent.external_id, CatalystEvent.ticker)
            .having(func.count() > 1)
            .order_by(func.count().desc())
            .all()
        )
        if not dupe_groups:
            logger.info("No duplicate (external_id, ticker) groups found.")
            return

        total_events = total_reactions = 0
        for ext, ticker, n in dupe_groups:
            events = (
                db.query(CatalystEvent)
                .filter(CatalystEvent.external_id == ext, CatalystEvent.ticker == ticker)
                .order_by(CatalystEvent.id.asc())
                .all()
            )
            keep, *dupes = events
            group_reactions = 0
            for ev in dupes:
                reactions = db.query(EventReaction).filter(EventReaction.event_id == ev.id).count()
                if not args.dry_run:
                    db.query(EventReaction).filter(EventReaction.event_id == ev.id).delete()
                    db.delete(ev)
                group_reactions += reactions
                total_events += 1
            total_reactions += group_reactions
            logger.info("%s %s: keep id=%d, delete %d event(s), %d reaction(s)",
                        ticker, ext, keep.id, len(dupes), group_reactions)

        if not args.dry_run:
            db.flush()
            db.commit()
        logger.info("DONE%s: %d duplicate event(s), %d reaction(s)",
                    " (dry-run, nothing deleted)" if args.dry_run else "",
                    total_events, total_reactions)

        # Verify: no duplicate groups should remain
        remaining = (
            db.query(func.count())
            .select_from(
                db.query(CatalystEvent.external_id, CatalystEvent.ticker)
                .filter(CatalystEvent.external_id.isnot(None))
                .group_by(CatalystEvent.external_id, CatalystEvent.ticker)
                .having(func.count() > 1)
                .subquery()
            )
            .scalar()
        )
        logger.info("Remaining duplicate groups: %d", remaining or 0)
    finally:
        db.close()


if __name__ == "__main__":
    main()
