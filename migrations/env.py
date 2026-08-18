"""Alembic environment configuration for DataPulse."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from datapulse.db.base import Base

# Import all models so Alembic knows about them
import datapulse.models  # noqa: F401

# Alembic Config object
config = context.config

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


def get_url():
    """Get database URL from DataPulse config (supports env vars)."""
    from datapulse.config import DATABASE_URL
    return DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without a connection."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
