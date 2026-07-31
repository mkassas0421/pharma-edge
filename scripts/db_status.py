"""Diagnostic: show DB activity, locks, and event source counts.

Run from the project root:
    python scripts/db_status.py

Uses a short connect/statement timeout so it never hangs.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text  # noqa: E402
from app.models.database import SessionLocal  # noqa: E402


def main():
    db = SessionLocal()
    try:
        # Make sure we never hang on a blocked query
        db.execute(text("SET statement_timeout = 5000"))

        print("=== alembic_version ===")
        try:
            for r in db.execute(text("SELECT version_num FROM alembic_version")).fetchall():
                print(" ", r[0])
        except Exception as exc:
            print("  error:", exc)

        print("\n=== active PG connections / locks (non-idle) ===")
        rows = db.execute(text(
            "SELECT pid, state, wait_event_type, wait_event, "
            "left(query, 70) AS query "
            "FROM pg_stat_activity "
            "WHERE datname = current_database() AND state <> 'idle' "
            "ORDER BY state"
        )).fetchall()
        if not rows:
            print("  (none)")
        for r in rows:
            print(" ", r)

        print("\n=== events by source ===")
        for r in db.execute(text(
            "SELECT source, COUNT(*) FROM catalyst_events GROUP BY source ORDER BY 2 DESC"
        )).fetchall():
            print(" ", r)

        print("\n=== source_url / verified columns present? ===")
        cols = [r[0] for r in db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'catalyst_events'"
        )).fetchall()]
        print("  source_url:", "source_url" in cols, "| verified:", "verified" in cols)
    finally:
        db.close()


if __name__ == "__main__":
    main()
