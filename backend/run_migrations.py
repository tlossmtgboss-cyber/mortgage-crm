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
        from sqlalchemy import create_engine, inspect as sa_inspect

        engine = create_engine(os.environ["DATABASE_URL"])
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()
            logger.info(f"Current database revision: {current_rev or 'None (fresh database)'}")

        if current_rev is None:
            # Check if core tables already exist (created by init_db.py)
            inspector = sa_inspect(engine)
            existing_tables = inspector.get_table_names()
            core_tables_exist = all(t in existing_tables for t in ["users", "organizations", "loans"])

            if core_tables_exist:
                # Database was bootstrapped by init_db.py without alembic stamps.
                # Stamp at head so alembic knows all migrations are already applied.
                logger.info("Database has existing tables but no alembic version stamp — stamping at head")
                command.stamp(alembic_cfg, "head")
            else:
                # Truly fresh database — run all migrations
                logger.info("Fresh database — running all migrations")
                command.upgrade(alembic_cfg, "head")
        else:
            # Normal case: run pending migrations
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
        return {"error": "Internal server error"}


def run_sample_data_cleanup():
    """One-time cleanup of sample data. Remove this function after it runs."""
    print("CLEANUP: Function entered", flush=True)
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("CLEANUP: DATABASE_URL not set - skipping", flush=True)
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    try:
        from sqlalchemy import create_engine, text

        print("CLEANUP: Creating database engine...", flush=True)
        engine = create_engine(database_url)
        print("=" * 50, flush=True)
        print("CLEANUP: RUNNING SAMPLE DATA CLEANUP...", flush=True)
        print("=" * 50, flush=True)

        with engine.connect() as conn:
            # Delete all tasks
            r = conn.execute(text('DELETE FROM tasks'))
            logger.info(f"Deleted {r.rowcount} tasks")

            r = conn.execute(text('DELETE FROM task_instances'))
            logger.info(f"Deleted {r.rowcount} task_instances")

            r = conn.execute(text('DELETE FROM purl_tasks'))
            logger.info(f"Deleted {r.rowcount} purl_tasks")

            # Delete team members and profiles
            r = conn.execute(text('DELETE FROM team_members'))
            logger.info(f"Deleted {r.rowcount} team_members")

            r = conn.execute(text('DELETE FROM team_member_profiles'))
            logger.info(f"Deleted {r.rowcount} team_member_profiles")

            # Delete extracted data
            r = conn.execute(text('DELETE FROM extracted_data'))
            logger.info(f"Deleted {r.rowcount} extracted_data records")

            # Delete referral partners
            r = conn.execute(text('DELETE FROM referral_partners'))
            logger.info(f"Deleted {r.rowcount} referral_partners")

            # Delete all users EXCEPT admin@perenniaai.com
            r = conn.execute(text("DELETE FROM users WHERE email != 'admin@perenniaai.com'"))
            logger.info(f"Deleted {r.rowcount} users (kept admin@perenniaai.com)")

            # Delete suspended and cancelled accounts
            r = conn.execute(text("DELETE FROM tenant_accounts WHERE status IN ('suspended', 'canceled')"))
            logger.info(f"Deleted {r.rowcount} suspended/cancelled tenant_accounts")

            conn.commit()

        logger.info("=" * 50)
        logger.info("SAMPLE DATA CLEANUP COMPLETE!")
        logger.info("=" * 50)
        return True

    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("RUN_MIGRATIONS.PY: Starting...", flush=True)
    print("=" * 60, flush=True)

    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        status = check_migration_status()
        print(f"Migration Status: {status}")
        sys.exit(0 if not status.get("error") else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        success = run_sample_data_cleanup()
        sys.exit(0 if success else 1)
    else:
        try:
            print("RUN_MIGRATIONS.PY: Running migrations...", flush=True)
            success = run_migrations()
            print(f"RUN_MIGRATIONS.PY: Migrations completed with success={success}", flush=True)
        except Exception as e:
            print(f"RUN_MIGRATIONS.PY: Migration exception: {e}", flush=True)
            success = False

        print("RUN_MIGRATIONS.PY: All done, exiting...", flush=True)
        sys.exit(0 if success else 1)
