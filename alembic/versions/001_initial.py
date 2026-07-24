"""Initial migration — create all tables.

Revises: None (base migration)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tickers ─────────────────────────────────────────────────────────────
    op.create_table(
        "tickers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("sector", sa.String(length=100), server_default="Biotechnology"),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tickers_ticker"), "tickers", ["ticker"], unique=True)
    op.create_index(op.f("ix_tickers_id"), "tickers", ["id"])

    # ── catalyst_events ─────────────────────────────────────────────────────
    op.create_table(
        "catalyst_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("event_date", sa.DateTime(), nullable=False),
        sa.Column("impact_level", sa.String(length=10), server_default="High"),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("alert_sent", sa.DateTime(), nullable=True),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=50), server_default="manual"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalyst_events_id"), "catalyst_events", ["id"])
    op.create_index(op.f("ix_catalyst_events_ticker"), "catalyst_events", ["ticker"])
    op.create_index(op.f("ix_catalyst_events_ticker_id"), "catalyst_events", ["ticker_id"])
    op.create_index(op.f("ix_catalyst_events_event_date"), "catalyst_events", ["event_date"])
    op.create_index(op.f("ix_catalyst_events_external_id"), "catalyst_events", ["external_id"])

    # ── price_snapshots ─────────────────────────────────────────────────────
    op.create_table(
        "price_snapshots",
        sa.Column("ticker", sa.String(length=10), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("change_percent", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("ticker"),
    )

    # ── ticker_aliases ──────────────────────────────────────────────────────
    op.create_table(
        "ticker_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticker_aliases_id"), "ticker_aliases", ["id"])
    op.create_index(op.f("ix_ticker_aliases_ticker_id"), "ticker_aliases", ["ticker_id"])


def downgrade() -> None:
    op.drop_table("ticker_aliases")
    op.drop_table("price_snapshots")
    op.drop_table("catalyst_events")
    op.drop_table("tickers")
