"""Run Alembic database migrations.

Usage:
    python scripts/migrate.py          # upgrade to latest
    python scripts/migrate.py --check  # dry-run / check pending
    python scripts/migrate.py --downgrade  # revert one step
"""

import sys
import os

# Ensure the project root is on sys.path so app.* imports resolve
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from alembic.config import Config
from alembic import command


def main():
    argv = sys.argv[1:]

    alembic_cfg = Config(os.path.join(PROJECT_ROOT, "alembic.ini"))

    if "--check" in argv:
        print("[CHECK] Checking for pending migrations...")
        command.check(alembic_cfg)
        print("[OK] No pending migrations (or the check passed).")
    elif "--downgrade" in argv:
        print("[DOWNGRADE] Reverting one migration step...")
        command.downgrade(alembic_cfg, "-1")
        print("[OK] Downgrade complete.")
    elif "--history" in argv:
        print("[HISTORY] Migration history:")
        command.history(alembic_cfg)
    else:
        print("[UPGRADE] Running Alembic migrations...")
        command.upgrade(alembic_cfg, "head")
        print("[OK] Migrations up-to-date.")


if __name__ == "__main__":
    main()
