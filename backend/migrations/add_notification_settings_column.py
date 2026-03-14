"""
Migration: Add notification_settings JSONB column to scheduler_configs table.

The notification_settings column stores per-user calendar notification preferences
(email/SMS reminders, quiet hours, booking/cancellation/reschedule alerts) as JSON.

Run with: python -m migrations.add_notification_settings_column
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Add notification_settings JSONB column to scheduler_configs if it doesn't exist."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Check if the table exists
        result = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'scheduler_configs')"
        ))
        if not result.scalar():
            logger.info("Table scheduler_configs does not exist, skipping")
            return False

        # Check if column already exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'scheduler_configs'
                  AND column_name = 'notification_settings'
            )
        """))
        col_exists = result.scalar()

        if col_exists:
            logger.info("Column notification_settings already exists on scheduler_configs")
            return True

        logger.info("Adding notification_settings JSONB column to scheduler_configs")
        conn.execute(text(
            "ALTER TABLE scheduler_configs "
            "ADD COLUMN notification_settings JSONB DEFAULT '{}'::jsonb"
        ))
        conn.commit()
        logger.info("Successfully added notification_settings column to scheduler_configs")

    return True


def rollback_migration():
    """Remove the notification_settings column from scheduler_configs."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'scheduler_configs'
                  AND column_name = 'notification_settings'
            )
        """))
        if not result.scalar():
            logger.info("Column notification_settings does not exist, nothing to rollback")
            return True

        logger.info("Dropping notification_settings column from scheduler_configs")
        conn.execute(text(
            "ALTER TABLE scheduler_configs DROP COLUMN notification_settings"
        ))
        conn.commit()
        logger.info("Rollback completed successfully")

    return True


def check_migration_status():
    """Check if the migration has been applied."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)

    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'scheduler_configs'
                  AND column_name = 'notification_settings'
            )
        """))
        exists = result.scalar()

        if exists:
            logger.info("Migration status: APPLIED - notification_settings column exists")
        else:
            logger.info("Migration status: NOT APPLIED")

        return exists


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Add notification_settings column to scheduler_configs"
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="up",
        choices=["up", "down", "status"],
        help="Migration action: up (apply), down (rollback), status (check)"
    )

    args = parser.parse_args()

    if args.action == "up":
        success = run_migration()
        sys.exit(0 if success else 1)
    elif args.action == "down":
        success = rollback_migration()
        sys.exit(0 if success else 1)
    elif args.action == "status":
        exists = check_migration_status()
        sys.exit(0 if exists else 1)
