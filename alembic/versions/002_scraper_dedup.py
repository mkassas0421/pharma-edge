"""Add scraper_dedup table — persistent dedup for notification-only scrapers.

Revises: 002_add_source_url_verified
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_scraper_dedup"
down_revision: Union[str, None] = "002_add_source_url_verified"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scraper_dedup",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("identifier", sa.String(length=500), nullable=False),
        sa.Column("seen_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "identifier", name="uq_scraper_dedup_source_identifier"),
    )
    op.create_index(op.f("ix_scraper_dedup_id"), "scraper_dedup", ["id"])
    op.create_index(op.f("ix_scraper_dedup_source"), "scraper_dedup", ["source"])


def downgrade() -> None:
    op.drop_index(op.f("ix_scraper_dedup_source"), table_name="scraper_dedup")
    op.drop_index(op.f("ix_scraper_dedup_id"), table_name="scraper_dedup")
    op.drop_table("scraper_dedup")
