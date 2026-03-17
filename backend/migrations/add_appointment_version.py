"""
Migration: Add version column to scheduler_appointments table

Adds optimistic locking support via a version column.
All existing rows default to version=1.

Usage:
    python migrations/add_appointment_version.py
"""

import os
import sys
from pathlib import Path

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TABLE_NAME = "scheduler_appointments"
COLUMN_NAME = "version"


def run_migration(database_url: str = None):
    """Add version column to scheduler_appointments if it doesn't exist."""
    if database_url is None:
        database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_engine(database_url)

    with engine.connect() as conn:
        inspector = inspect(engine)

        # Check if table exists
        if TABLE_NAME not in inspector.get_table_names():
            logger.info(f"Table {TABLE_NAME} does not exist yet; skipping migration")
            return

        # Check if column already exists
        existing_columns = {col["name"] for col in inspector.get_columns(TABLE_NAME)}
        if COLUMN_NAME in existing_columns:
            logger.info(f"Column {COLUMN_NAME} already exists on {TABLE_NAME}; skipping")
            return

        # Add the column with default=1
        logger.info(f"Adding {COLUMN_NAME} column to {TABLE_NAME}...")
        conn.execute(text(f"""
            ALTER TABLE {TABLE_NAME}
            ADD COLUMN {COLUMN_NAME} INTEGER NOT NULL DEFAULT 1
        """))

        # Explicitly set existing rows to version 1 (redundant with DEFAULT but explicit)
        result = conn.execute(text(f"""
            UPDATE {TABLE_NAME} SET {COLUMN_NAME} = 1 WHERE {COLUMN_NAME} IS NULL
        """))
        logger.info(f"Updated {result.rowcount} existing rows to version=1")

        conn.commit()
        logger.info(f"Migration complete: {COLUMN_NAME} column added to {TABLE_NAME}")


if __name__ == "__main__":
    run_migration()
