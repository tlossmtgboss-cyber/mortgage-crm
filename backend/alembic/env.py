"""
Alembic Environment Configuration
Perennia AI - Mortgage CRM

This module configures Alembic to:
1. Read DATABASE_URL from environment (never hardcoded)
2. Import all SQLAlchemy models so autogenerate can diff them
3. Support both online and offline migrations
4. Handle PostgreSQL-specific features (postgres:// -> postgresql://)
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add parent directory (backend/) to path so that `from database import Base`
# and `import database.models` resolve correctly regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Alembic Config object (reads alembic.ini)
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import models for autogenerate support
# ---------------------------------------------------------------------------
# Base comes from db.py via database/__init__.py.
# Importing database.models triggers all model module imports, which registers
# every table on Base.metadata so that `--autogenerate` can diff them.
from database import Base
import database.models  # noqa: F401 — registers all model classes with Base
import engine.models  # noqa: F401 — registers CIE tables with Base

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Database URL helper
# ---------------------------------------------------------------------------
def get_url() -> str:
    """Get database URL from the DATABASE_URL environment variable.

    Applies the postgres:// -> postgresql:// fix needed by Railway/Heroku
    URLs that use the older prefix unsupported by SQLAlchemy 1.4+.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL environment variable is not set. "
            "Set it before running Alembic commands."
        )

    # Fix for Railway/Heroku postgres:// prefix
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    return url


# ---------------------------------------------------------------------------
# Tables / types to exclude from autogenerate diffs
# ---------------------------------------------------------------------------
def include_object(object, name, type_, reflected, compare_to):
    """Filter objects from autogenerate comparison.

    Excludes:
    - The alembic_version table itself
    - Any spatial/PostGIS internal tables if they appear
    """
    if type_ == "table" and name == "alembic_version":
        return False
    return True


# ---------------------------------------------------------------------------
# Offline migrations (emit SQL without connecting)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL. Calls to context.execute()
    emit SQL strings to the script output — useful for generating SQL
    scripts to be applied by a DBA.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (connect to DB and run)
# ---------------------------------------------------------------------------
def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine, connects to the database, and runs migration
    operations inside a transaction.
    """
    # Override the placeholder sqlalchemy.url from alembic.ini with the
    # real URL from the environment variable.
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Don't pool — migrations are short-lived
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,             # Detect column type changes
            compare_server_default=True,   # Detect server default changes
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
