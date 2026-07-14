"""Alembic environment.

Reads the DB URL from `TRADER_DB_URL` (env) or the `alembic.ini` default and
runs migrations against SQLAlchemy 2.0 metadata.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make src importable when running alembic from the repo root.
_root = Path(__file__).resolve().parents[1]
_src = _root / "src"
if str(_src) not in os.sys.path:
    os.sys.path.insert(0, str(_src))

from trader.storage.models import Base  # noqa: E402


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_url() -> str:
    env_url = os.environ.get("TRADER_DB_URL")
    if env_url:
        # Alembic uses sync drivers; strip the +aiosqlite / +asyncpg suffix.
        return env_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
    return config.get_main_option("sqlalchemy.url", "sqlite:///./trader.db")


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
