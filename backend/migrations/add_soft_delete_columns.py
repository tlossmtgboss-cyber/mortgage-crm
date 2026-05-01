"""
Add Soft Delete Columns to Scheduler Tables

Adds soft delete columns (is_deleted, deleted_at, deleted_by) to:
  - scheduler_appointments
  - scheduler_booking_links

Existing rows default to is_deleted = False (active).

This migration supports the compliance requirement to never physically delete
appointment or booking link records in a regulated mortgage environment.

Usage:
    python -m migrations.add_soft_delete_columns
    # or
    from migrations.add_soft_delete_columns import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


TABLES_AND_COLUMNS = {
    "scheduler_appointments": [
        ("is_deleted", "BOOLEAN", "FALSE"),
        ("deleted_at", "TIMESTAMP", None),
        ("deleted_by", "VARCHAR(36)", None),
    ],
    "scheduler_booking_links": [
        ("is_deleted", "BOOLEAN", "FALSE"),
        ("deleted_at", "TIMESTAMP", None),
        ("deleted_by", "VARCHAR(36)", None),
    ],
    "leads": [
        ("deleted_at", "TIMESTAMP", None),
    ],
    "loans": [
        ("deleted_at", "TIMESTAMP", None),
    ],
    "borrower_applications": [
        ("deleted_at", "TIMESTAMP", None),
    ],
}


def run_migration():
    """Add soft delete columns to scheduler_appointments and scheduler_booking_links."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        total_added = 0
        total_skipped = 0

        for table_name, columns in TABLES_AND_COLUMNS.items():
            logger.info(f"Adding soft delete columns to {table_name}...")

            for col_name, col_type, default_value in columns:
                try:
                    default_clause = ""
                    if default_value is not None:
                        default_clause = f" DEFAULT {default_value}"

                    if is_sqlite:
                        conn.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}{default_clause}"
                        ))
                    else:
                        conn.execute(text(
                            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default_clause}"
                        ))
                    total_added += 1
                    logger.info(f"  Added {col_name} to {table_name}")
                except Exception as e:
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        total_skipped += 1
                        logger.info(f"  {col_name} already exists on {table_name}, skipping")
                    else:
                        logger.error(f"  Failed to add {col_name} to {table_name}: {e}")

            # Ensure is_deleted defaults are set for existing rows
            try:
                conn.execute(text(
                    f"UPDATE {table_name} SET is_deleted = FALSE WHERE is_deleted IS NULL"
                ))
                logger.info(f"  Set is_deleted = FALSE for existing NULL rows in {table_name}")
            except Exception as e:
                logger.warning(f"  Could not update NULL is_deleted values in {table_name}: {e}")

            # Add NOT NULL constraint on is_deleted if PostgreSQL
            if not is_sqlite:
                try:
                    conn.execute(text(
                        f"ALTER TABLE {table_name} ALTER COLUMN is_deleted SET NOT NULL"
                    ))
                    logger.info(f"  Set NOT NULL on is_deleted for {table_name}")
                except Exception as e:
                    logger.debug(f"  Could not set NOT NULL on is_deleted for {table_name}: {e}")

            # Create index on is_deleted for query performance
            index_name = f"ix_{table_name}_is_deleted"
            try:
                if is_sqlite:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} (is_deleted)"
                    ))
                else:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} (is_deleted)"
                    ))
                logger.info(f"  Created index {index_name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"  Index {index_name} already exists")
                else:
                    logger.warning(f"  Could not create index {index_name}: {e}")

        conn.commit()

    logger.info(f"Soft delete migration complete: {total_added} columns added, {total_skipped} skipped")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("Soft delete migration completed successfully")
    else:
        print("Soft delete migration failed")
        exit(1)
