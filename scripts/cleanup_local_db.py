"""One-off: migrate + clean + backfill the LOCAL SQLite dev database.

The .env points at the production PostgreSQL, so this script explicitly
overrides DATABASE_URL (BEFORE importing the app, since app.config reads it
at import time) to run the same cleanup on the local dev file:
    data/pharma_alerts.db

Usage:
    python scripts/cleanup_local_db.py
"""

import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./data/pharma_alerts.db"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.models.database import init_db  # noqa: E402
from scripts.cleanup_fabricated_events import cleanup  # noqa: E402
from scripts.backfill_source_urls import backfill  # noqa: E402


def main():
    init_db()  # inline migration adds source_url / verified (SQLite)
    print("Local DB migrated (source_url/verified columns added).")
    cleaned = cleanup()
    print(f"Deleted {cleaned} fabricated event(s).")
    touched = backfill()
    print(f"Backfilled source_url/verified for {touched} event(s).")


if __name__ == "__main__":
    main()
