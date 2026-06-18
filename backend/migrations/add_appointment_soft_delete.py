"""
Add soft-delete support to scheduler_appointments.

Adds:
  - deleted_at (TIMESTAMPTZ): NULL = active, non-NULL = soft-deleted
  - Partial index on (organization_id, deleted_at) WHERE deleted_at IS NULL
    for fast "list active appointments" queries.

Rollback support is included — see rollback() below.

Usage:
    python -m migrations.add_appointment_soft_delete
    # or
    from migrations.add_appointment_soft_delete import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Add deleted_at column and partial index to scheduler_appointments."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        # ---------------------------------------------------------------
        # 1. Add deleted_at column
        # ---------------------------------------------------------------
        logger.info("Adding deleted_at column to scheduler_appointments...")
        try:
            if is_sqlite:
                conn.execute(text(
                    "ALTER TABLE scheduler_appointments "
                    "ADD COLUMN deleted_at TIMESTAMP"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE scheduler_appointments "
                    "ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE"
                ))
            logger.info("  deleted_at column added")
        except Exception as e:
            err = str(e).lower()
            if "duplicate column" in err or "already exists" in err:
                logger.info("  deleted_at column already exists, skipping")
            else:
                logger.error(f"  Failed to add deleted_at column: {e}")
                return False

        conn.commit()

        # ---------------------------------------------------------------
        # 2. Create partial index (PostgreSQL-only; SQLite skips WHERE)
        # ---------------------------------------------------------------
        logger.info("Creating partial index idx_appointment_not_deleted...")
        try:
            if is_sqlite:
                # SQLite does not support CONCURRENTLY or partial WHERE on CREATE INDEX
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_appointment_not_deleted "
                    "ON scheduler_appointments (organization_id)"
                ))
                logger.info("  Simple index created (SQLite)")
            else:
                # CONCURRENTLY requires autocommit — handled via raw connection.
                # We commit the current transaction first, then use autocommit.
                raw_conn = conn.connection
                isolation_level = raw_conn.isolation_level
                raw_conn.set_isolation_level(0)  # AUTOCOMMIT
                try:
                    raw_conn.cursor().execute(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_appointment_not_deleted "
                        "ON scheduler_appointments (organization_id, deleted_at) "
                        "WHERE deleted_at IS NULL"
                    )
                    logger.info("  Partial index idx_appointment_not_deleted created")
                finally:
                    raw_conn.set_isolation_level(isolation_level)
        except Exception as e:
            err = str(e).lower()
            if "already exists" in err:
                logger.info("  idx_appointment_not_deleted already exists, skipping")
            else:
                logger.warning(f"  Could not create partial index (non-fatal): {e}")

    logger.info("Soft-delete migration complete")
    return True


def rollback():
    """
    Remove the deleted_at column and partial index from scheduler_appointments.

    WARNING: This is destructive — any rows that were soft-deleted will lose
    their deletion record.  Run only after confirming no soft-deleted rows exist
    or after a full hard-delete pass.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        if not is_sqlite:
            try:
                conn.execute(text(
                    "DROP INDEX IF EXISTS idx_appointment_not_deleted"
                ))
                logger.info("Dropped idx_appointment_not_deleted")
            except Exception as e:
                logger.warning(f"Could not drop index: {e}")

            try:
                conn.execute(text(
                    "ALTER TABLE scheduler_appointments "
                    "DROP COLUMN IF EXISTS deleted_at"
                ))
                logger.info("Dropped deleted_at column from scheduler_appointments")
            except Exception as e:
                logger.warning(f"Could not drop deleted_at column: {e}")

            conn.commit()
        else:
            logger.warning("SQLite does not support DROP COLUMN — rollback skipped")

    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
