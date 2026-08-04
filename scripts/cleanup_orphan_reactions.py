"""One-time cleanup of orphan EventReaction rows (their event is already gone).

The reaction table has no FK to catalyst_events (codebase convention), so
reaction rows survive event deletion by design. When the daily pruner's old
365-day rule wiped the whole historical backfill (2026-08-04, since fixed),
thousands of reaction rows were left pointing at events that no longer
exist. Before re-importing the historical backfill, those orphans must go:
the re-imported events get NEW ids, so without this cleanup the same
catalyst would be double-counted in the reaction stats.

Usage (from the project root — connects to whatever DATABASE_URL the
environment resolves to, i.e. the production PostgreSQL in prod):
    python scripts/cleanup_orphan_reactions.py --dry-run   # report only
    python scripts/cleanup_orphan_reactions.py             # delete
"""

import argparse
import logging
import os
import sys
from collections import Counter

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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
        live_ids = db.query(CatalystEvent.id).scalar_subquery()
        orphans = (
            db.query(EventReaction)
            .filter(~EventReaction.event_id.in_(live_ids))
            .all()
        )
        if not orphans:
            logger.info("No orphan reactions — every EventReaction points at a live event.")
            return

        by_status = Counter(r.status for r in orphans)
        by_ticker = Counter(r.ticker for r in orphans)
        logger.info("%d orphan reaction row(s) (event deleted):", len(orphans))
        logger.info("  by status: %s", dict(by_status))
        for ticker, n in by_ticker.most_common(15):
            logger.info("  %s: %d", ticker, n)
        if len(by_ticker) > 15:
            logger.info("  ... plus %d more ticker(s)", len(by_ticker) - 15)

        if args.dry_run:
            logger.info("DRY RUN — nothing deleted. Re-run without --dry-run to delete.")
            return

        for r in orphans:
            db.delete(r)
        db.commit()
        logger.info("Deleted %d orphan reaction row(s).", len(orphans))
    finally:
        db.close()


if __name__ == "__main__":
    main()
