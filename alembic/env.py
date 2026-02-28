import os
import logging
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# Strip any existing search_path query param to avoid configparser % interpolation
# errors, then set search_path via connect_args in run_migrations_online().
_raw_url = os.environ.get("DATABASE_URL", "")
DATABASE_URL = _raw_url.split("?")[0] if "?" in _raw_url else _raw_url

if DATABASE_URL:
    # Escape % for configparser in case the raw URL contains percent-encoded chars.
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

target_metadata = None


def run_migrations_offline() -> None:
    if not DATABASE_URL:
        logger.warning("No DATABASE_URL set -- skipping offline migration")
        return
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if not DATABASE_URL:
        logger.warning("No DATABASE_URL set -- skipping online migration")
        return
    # Set search_path=hr via connect_args so all unqualified DDL lands in hr schema.
    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
        connect_args={"options": "-csearch_path=hr"},
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
