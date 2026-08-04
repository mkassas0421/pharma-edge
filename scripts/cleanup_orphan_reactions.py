"""One-time cleanup of orphan EventReaction rows (their event is already gone).

The reaction table has no FK to catalyst_events (codebase convention), so
reaction rows survive event deletion by design. When the daily pruner's old
365-day rule wiped the whole historical backfill (2026-08-04, since fixed),
thousands of reaction rows were left pointing at events that no longer
exist. Before re-importing the historical backfill, those orphans must go:
the re-imported events get NEW ids, so without this cleanup the same
catalyst would be double-counted in the reaction stats.

The delete is a single bulk DELETE (no per-row ORM round trips — the first
version took too long on the production DB and had to be interrupted).

Usage (from the project root — connects to whatever DATABASE_URL the
environment resolves to, i.e. the production PostgreSQL in prod):
    python scripts/cleanup_orphan_reactions.py --dry-run   # report only
    python scripts/cleanup_orphan_reactions.py             # delete
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
        live_ids = db.query(CatalystEvent.id).scalar_subquery()
        orphan_filter = ~EventReaction.event_id.in_(live_ids)

        n = db.query(EventReaction).filter(orphan_filter).count()
        if not n:
            logger.info("No orphan reactions — every EventReaction points at a live event.")
            return

        by_status = dict(
            db.query(EventReaction.status, func.count())
            .filter(orphan_filter)
            .group_by(EventReaction.status)
            .all()
        )
        by_ticker = (
            db.query(EventReaction.ticker, func.count())
            .filter(orphan_filter)
            .group_by(EventReaction.ticker)
            .order_by(func.count().desc())
            .limit(15)
            .all()
        )
        n_tickers = (
            db.query(func.count(func.distinct(EventReaction.ticker)))
            .filter(orphan_filter)
            .scalar()
        )

        logger.info("%d orphan reaction row(s) (event deleted):", n)
        logger.info("  by status: %s", by_status)
        for ticker, cnt in by_ticker:
            logger.info("  %s: %d", ticker, cnt)
        if n_tickers > len(by_ticker):
            logger.info("  ... plus %d more ticker(s)", n_tickers - len(by_ticker))

        if args.dry_run:
            logger.info("DRY RUN — nothing deleted. Re-run without --dry-run to delete.")
            return

        deleted = (
            db.query(EventReaction)
            .filter(orphan_filter)
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info("Deleted %d orphan reaction row(s).", deleted)
    finally:
        db.close()


if __name__ == "__main__":
    main()
