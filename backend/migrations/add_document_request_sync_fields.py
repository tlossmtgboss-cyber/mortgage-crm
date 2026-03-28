"""
Add is_required and fulfilled_at columns to smart_document_requests for PURL sync.

These columns enable the PURL workspace service to:
1. Know which document requests are required vs optional (is_required)
2. Track when a request was fulfilled (fulfilled_at), synced with completed_at

Migration steps:
1. Add is_required BOOLEAN DEFAULT TRUE to smart_document_requests
2. Add fulfilled_at TIMESTAMP to smart_document_requests
3. Backfill: set fulfilled_at = completed_at for rows where completed_at IS NOT NULL
4. Backfill: set is_required = TRUE for all existing rows

This migration is idempotent - safe to run multiple times.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Run the migration to add is_required and fulfilled_at columns."""
    with engine.connect() as conn:
        # Check if table exists first
        table_check = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'smart_document_requests'
            )
        """)).scalar()

        if not table_check:
            logger.info("smart_document_requests table does not exist yet, skipping migration")
            return

        # Add is_required column if not exists
        col_exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'smart_document_requests'
                AND column_name = 'is_required'
            )
        """)).scalar()

        if not col_exists:
            logger.info("Adding is_required column to smart_document_requests")
            conn.execute(text("""
                ALTER TABLE smart_document_requests
                ADD COLUMN is_required BOOLEAN DEFAULT TRUE
            """))
            # Backfill: set is_required = TRUE for all existing rows
            conn.execute(text("""
                UPDATE smart_document_requests
                SET is_required = TRUE
                WHERE is_required IS NULL
            """))
            logger.info("Added and backfilled is_required column")
        else:
            logger.info("is_required column already exists, skipping")

        # Add fulfilled_at column if not exists
        col_exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'smart_document_requests'
                AND column_name = 'fulfilled_at'
            )
        """)).scalar()

        if not col_exists:
            logger.info("Adding fulfilled_at column to smart_document_requests")
            conn.execute(text("""
                ALTER TABLE smart_document_requests
                ADD COLUMN fulfilled_at TIMESTAMP
            """))
            # Backfill: set fulfilled_at = completed_at for rows where completed_at IS NOT NULL
            result = conn.execute(text("""
                UPDATE smart_document_requests
                SET fulfilled_at = completed_at
                WHERE completed_at IS NOT NULL AND fulfilled_at IS NULL
            """))
            logger.info(f"Added fulfilled_at column and backfilled {result.rowcount} rows from completed_at")
        else:
            logger.info("fulfilled_at column already exists, skipping")

        conn.commit()
        logger.info("Migration add_document_request_sync_fields completed successfully")


if __name__ == "__main__":
    import os
    from sqlalchemy import create_engine

    logging.basicConfig(level=logging.INFO)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        exit(1)

    engine = create_engine(database_url)
    run_migration(engine)
