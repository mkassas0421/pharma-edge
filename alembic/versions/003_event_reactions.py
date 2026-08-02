"""Add event_reactions table — track price reactions after catalyst events.

Revises: 002_scraper_dedup
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_event_reactions"
down_revision: Union[str, None] = "002_scraper_dedup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_reactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("price_before", sa.Float(), nullable=True),
        sa.Column("price_at_event", sa.Float(), nullable=True),
        sa.Column("price_after_1d", sa.Float(), nullable=True),
        sa.Column("price_after_5d", sa.Float(), nullable=True),
        sa.Column("reaction_1d_pct", sa.Float(), nullable=True),
        sa.Column("reaction_5d_pct", sa.Float(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=True),
        sa.Column("impact_level", sa.String(length=10), nullable=True),
        sa.Column("indication", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending"),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_event_reactions_event_id"),
    )
    op.create_index(op.f("ix_event_reactions_id"), "event_reactions", ["id"])
    op.create_index(op.f("ix_event_reactions_event_id"), "event_reactions", ["event_id"])
    op.create_index(op.f("ix_event_reactions_ticker"), "event_reactions", ["ticker"])
    op.create_index(op.f("ix_event_reactions_event_type"), "event_reactions", ["event_type"])
    op.create_index(op.f("ix_event_reactions_impact_level"), "event_reactions", ["impact_level"])


def downgrade() -> None:
    op.drop_index(op.f("ix_event_reactions_impact_level"), table_name="event_reactions")
    op.drop_index(op.f("ix_event_reactions_event_type"), table_name="event_reactions")
    op.drop_index(op.f("ix_event_reactions_ticker"), table_name="event_reactions")
    op.drop_index(op.f("ix_event_reactions_event_id"), table_name="event_reactions")
    op.drop_index(op.f("ix_event_reactions_id"), table_name="event_reactions")
    op.drop_table("event_reactions")
