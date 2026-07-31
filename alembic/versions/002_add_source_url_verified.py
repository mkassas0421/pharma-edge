"""Add source_url and verified columns to catalyst_events.

Every catalyst event now carries a link to its official government source
document (ClinicalTrials.gov, SEC EDGAR, Federal Register, FDA) so that
events are verifiable — no more unverifiable curated data.

Revises: 001_initial
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_add_source_url_verified"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "catalyst_events",
        sa.Column("source_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "catalyst_events",
        sa.Column("verified", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("catalyst_events", "verified")
    op.drop_column("catalyst_events", "source_url")
