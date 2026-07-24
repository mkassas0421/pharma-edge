"""Alembic migration script template."""
revision: str
down_revision: str | None
branch_labels: str | list[str] | None = None
depends_on: str | list[str] | None = None


def upgrade() -> None:
    """Upgrade to this revision."""
    pass


def downgrade() -> None:
    """Revert to the previous revision."""
    pass
