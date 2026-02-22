"""
Add Encompass LOS Integration Columns to Loans Table

Adds columns for tracking Encompass loan linkage and sync status:
  - encompass_loan_id: The Encompass GUID for the linked loan
  - encompass_last_synced_at: Timestamp of last successful sync
  - encompass_sync_status: Current sync status (synced, pending, error)

Also creates the encompass_configs table for per-org credential storage.

Usage:
    python -m migrations.add_encompass_columns
    # or
    from migrations.add_encompass_columns import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


LOAN_COLUMNS = [
    ("encompass_loan_id", "VARCHAR"),
    ("encompass_last_synced_at", "TIMESTAMP"),
    ("encompass_sync_status", "VARCHAR"),
]


def run_migration():
    """Add Encompass columns to the loans table and create encompass_configs table."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        # -------------------------------------------------------------------
        # 1. Add Encompass columns to loans table
        # -------------------------------------------------------------------
        logger.info("Adding Encompass columns to loans table...")
        added = 0
        skipped = 0

        for col_name, col_type in LOAN_COLUMNS:
            try:
                if is_sqlite:
                    conn.execute(text(
                        f"ALTER TABLE loans ADD COLUMN {col_name} {col_type}"
                    ))
                else:
                    conn.execute(text(
                        f"ALTER TABLE loans ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    ))
                added += 1
            except Exception as e:
                error_str = str(e).lower()
                if "duplicate column" in error_str or "already exists" in error_str:
                    skipped += 1
                elif "no such table" in error_str:
                    logger.warning("loans table does not exist, skipping")
                    break
                else:
                    logger.warning(f"Could not add {col_name} to loans: {e}")

        # Create index on encompass_loan_id
        try:
            if is_sqlite:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_loans_encompass_loan_id "
                    "ON loans (encompass_loan_id)"
                ))
            else:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_loans_encompass_loan_id "
                    "ON loans (encompass_loan_id)"
                ))
            logger.info("  Created index ix_loans_encompass_loan_id")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                pass
            else:
                logger.warning(f"Could not create encompass_loan_id index: {e}")

        conn.commit()
        logger.info(f"  loans: {added} added, {skipped} already existed")

        # -------------------------------------------------------------------
        # 2. Create encompass_configs table
        # -------------------------------------------------------------------
        logger.info("Creating encompass_configs table...")
        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS encompass_configs (
                        id VARCHAR PRIMARY KEY,
                        organization_id INTEGER NOT NULL UNIQUE,
                        instance_id VARCHAR NOT NULL,
                        client_id VARCHAR NOT NULL,
                        client_secret VARCHAR NOT NULL,
                        api_user VARCHAR,
                        webhook_secret VARCHAR,
                        auto_pull_on_webhook BOOLEAN DEFAULT 1,
                        auto_push_on_stage_change BOOLEAN DEFAULT 0,
                        sync_frequency_minutes INTEGER DEFAULT 60,
                        last_sync_at TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (organization_id) REFERENCES organizations(id)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS encompass_configs (
                        id VARCHAR PRIMARY KEY,
                        organization_id INTEGER NOT NULL UNIQUE,
                        instance_id VARCHAR NOT NULL,
                        client_id VARCHAR NOT NULL,
                        client_secret VARCHAR NOT NULL,
                        api_user VARCHAR,
                        webhook_secret VARCHAR,
                        auto_pull_on_webhook BOOLEAN DEFAULT TRUE,
                        auto_push_on_stage_change BOOLEAN DEFAULT FALSE,
                        sync_frequency_minutes INTEGER DEFAULT 60,
                        last_sync_at TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW(),
                        FOREIGN KEY (organization_id) REFERENCES organizations(id)
                    )
                """))

            # Create index on organization_id
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_encompass_configs_org_id "
                "ON encompass_configs (organization_id)"
            ))

            conn.commit()
            logger.info("  encompass_configs table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  encompass_configs table already exists")
            else:
                logger.error(f"Failed to create encompass_configs table: {e}")

    logger.info("Encompass migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
