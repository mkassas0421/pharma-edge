"""Add unique index on catalyst_events (external_id, ticker).

Guards against duplicate events from any scraper path: the check-then-insert
dedup is not atomic and was blind within a session (autoflush=False), which
let one SEC 8-K filing insert several rows with the same external_id.

Partial index: manual events (external_id NULL) are exempt. PostgreSQL only
(kwarg ignored on SQLite, where NULLs are also distinct in unique indexes).

Revises: 003_event_reactions
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_unique_external_id"
down_revision: Union[str, None] = "003_event_reactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_catalyst_events_external_id_ticker",
        "catalyst_events",
        ["external_id", "ticker"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_catalyst_events_external_id_ticker", table_name="catalyst_events")
