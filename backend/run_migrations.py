#!/usr/bin/env python3
"""
Migration Runner Script
Perennia AI - Mortgage CRM

This script runs all pending Alembic migrations.
Use this in deployment pipelines: python run_migrations.py

Environment Variables Required:
- DATABASE_URL: PostgreSQL connection string
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_migrations():
    """Run all pending Alembic migrations."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    # Fix postgres:// prefix for SQLAlchemy
    if database_url.startswith("postgres://"):
        os.environ["DATABASE_URL"] = database_url.replace("postgres://", "postgresql://", 1)
        logger.info("Fixed postgres:// prefix to postgresql://")

    try:
        from alembic.config import Config
        from alembic import command

        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_cfg = Config(os.path.join(script_dir, "alembic.ini"))

        # Override the script location to be absolute
        alembic_cfg.set_main_option("script_location", os.path.join(script_dir, "alembic"))

        logger.info("Running database migrations...")

        # Get current revision
        from alembic.runtime.migration import MigrationContext
        from sqlalchemy import create_engine

        engine = create_engine(os.environ["DATABASE_URL"])
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            logger.info(f"Current database revision: {current_rev or 'None (fresh database)'}")

        # Run migrations
        command.upgrade(alembic_cfg, "head")

        # Get new revision
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            new_rev = context.get_current_revision()
            logger.info(f"Database now at revision: {new_rev}")

        if current_rev == new_rev:
            logger.info("No new migrations to apply - database is up to date")
        else:
            logger.info("Migrations completed successfully!")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def check_migration_status():
    """Check current migration status without running migrations."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        return {"error": "DATABASE_URL not set"}

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine

        script_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_cfg = Config(os.path.join(script_dir, "alembic.ini"))
        alembic_cfg.set_main_option("script_location", os.path.join(script_dir, "alembic"))

        script = ScriptDirectory.from_config(alembic_cfg)
        head_revision = script.get_current_head()

        engine = create_engine(database_url)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_revision = context.get_current_revision()

        return {
            "current_revision": current_revision,
            "head_revision": head_revision,
            "is_up_to_date": current_revision == head_revision,
            "pending_migrations": current_revision != head_revision
        }

    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        status = check_migration_status()
        print(f"Migration Status: {status}")
        sys.exit(0 if not status.get("error") else 1)
    else:
        success = run_migrations()
        sys.exit(0 if success else 1)
