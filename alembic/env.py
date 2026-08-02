"""Alembic environment configuration — reads DATABASE_URL from app settings.

Supports both SQLite (development) and PostgreSQL (production).
"""

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic Config object
config = context.config

# Set up Python loggers from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the declarative Base so Alembic can detect model changes
from app.models.database import Base  # noqa: E402

# Import ALL models so they register on Base.metadata
from app.models.database import (  # noqa: E402, F401
    Ticker,
    CatalystEvent,
    PriceSnapshot,
    TickerAlias,
    EventReaction,
)

target_metadata = Base.metadata

# ── Override sqlalchemy.url from the app's DATABASE_URL ───────────────────────
from app.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.database_url)

logger = logging.getLogger("alembic.env")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without connecting."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,       # detect column type changes
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
