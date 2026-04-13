"""
Add Mobile Audit Events Table

Creates the mobile_audit_events table for durable storage of iOS security
audit events. Required for SOC 2 compliance — Railway stdout logs rotate
at ~1MB, losing audit history.

Table stores hash-chained entries from the iOS AuditLogger with:
  - Event classification (type, category)
  - Device metadata (model, OS version, app version)
  - Hash chain integrity fields (event_hash, previous_hash, chain_valid)
  - Dual timestamps (device-side event_timestamp, server-side created_at)

Indexes optimized for:
  - Org-scoped queries by event type or date range
  - Per-user event type lookups

90-day retention: Run periodic cleanup —
  DELETE FROM mobile_audit_events WHERE created_at < NOW() - INTERVAL '90 days';

Usage:
    python -m migrations.add_audit_events_table
    # or
    from migrations.add_audit_events_table import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create mobile_audit_events table and indexes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_postgres = "postgresql" in database_url.lower() or "postgres" in database_url.lower()

    with engine.connect() as conn:
        logger.info("Creating mobile_audit_events table...")

        try:
            if is_postgres:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS mobile_audit_events (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER REFERENCES organizations(id),
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        event_type VARCHAR NOT NULL,
                        event_category VARCHAR,
                        details JSONB,
                        device_info JSONB,
                        event_hash VARCHAR(64),
                        previous_hash VARCHAR(64),
                        chain_valid BOOLEAN DEFAULT TRUE,
                        event_timestamp TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                """))
            else:
                # SQLite fallback (tests)
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS mobile_audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER REFERENCES organizations(id),
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        event_type VARCHAR NOT NULL,
                        event_category VARCHAR,
                        details JSON,
                        device_info JSON,
                        event_hash VARCHAR(64),
                        previous_hash VARCHAR(64),
                        chain_valid BOOLEAN DEFAULT 1,
                        event_timestamp TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            conn.commit()
            logger.info("mobile_audit_events table created (or already exists)")
        except Exception as e:
            logger.error("Failed to create mobile_audit_events table: %s", e)
            return False

        # -----------------------------------------------------------------
        # Indexes
        # -----------------------------------------------------------------
        indexes = [
            (
                "ix_mobile_audit_events_organization_id",
                "CREATE INDEX IF NOT EXISTS ix_mobile_audit_events_organization_id "
                "ON mobile_audit_events (organization_id)"
            ),
            (
                "ix_mobile_audit_events_user_id",
                "CREATE INDEX IF NOT EXISTS ix_mobile_audit_events_user_id "
                "ON mobile_audit_events (user_id)"
            ),
            (
                "ix_mobile_audit_events_event_type",
                "CREATE INDEX IF NOT EXISTS ix_mobile_audit_events_event_type "
                "ON mobile_audit_events (event_type)"
            ),
            (
                "ix_mobile_audit_org_event_type",
                "CREATE INDEX IF NOT EXISTS ix_mobile_audit_org_event_type "
                "ON mobile_audit_events (organization_id, event_type)"
            ),
            (
                "ix_mobile_audit_org_created",
                "CREATE INDEX IF NOT EXISTS ix_mobile_audit_org_created "
                "ON mobile_audit_events (organization_id, created_at)"
            ),
            (
                "ix_mobile_audit_user_event_type",
                "CREATE INDEX IF NOT EXISTS ix_mobile_audit_user_event_type "
                "ON mobile_audit_events (user_id, event_type)"
            ),
        ]

        for idx_name, idx_sql in indexes:
            try:
                conn.execute(text(idx_sql))
                conn.commit()
                logger.info("Index %s created (or already exists)", idx_name)
            except Exception as e:
                logger.warning("Failed to create index %s (non-fatal): %s", idx_name, e)

    logger.info("Migration complete: mobile_audit_events table ready")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("Migration succeeded")
    else:
        print("Migration failed")
        exit(1)
