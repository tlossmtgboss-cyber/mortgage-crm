"""
Migration: Create audit_events table for SOC 2 compliance

Run: python migrations/create_audit_events_table.py

Creates the audit_events table with indexes for efficient querying
by actor, resource, timeframe, and metadata. Append-only by design.
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from db import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    with engine.connect() as conn:
        # Ensure pgcrypto is available for gen_random_uuid()
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

        # Check if table already exists
        result = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_events')"
        ))
        if result.scalar():
            logger.info("audit_events table already exists, skipping creation")
            conn.commit()
            return

        conn.execute(text("""
            CREATE TABLE audit_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                event_type VARCHAR(64) NOT NULL,
                outcome VARCHAR(16) NOT NULL DEFAULT 'success',
                actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
                actor_email VARCHAR(320),
                actor_role VARCHAR(32),
                org_id UUID,
                resource_type VARCHAR(64),
                resource_id VARCHAR(128),
                ip INET,
                user_agent TEXT,
                request_id VARCHAR(64),
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
        """))

        # Create indexes
        conn.execute(text("CREATE INDEX ix_audit_occurred_at ON audit_events (occurred_at)"))
        conn.execute(text("CREATE INDEX ix_audit_event_type ON audit_events (event_type)"))
        conn.execute(text("CREATE INDEX ix_audit_actor_id ON audit_events (actor_id)"))
        conn.execute(text("CREATE INDEX ix_audit_org_id ON audit_events (org_id)"))
        conn.execute(text("CREATE INDEX ix_audit_resource_id ON audit_events (resource_id)"))
        conn.execute(text("CREATE INDEX ix_audit_actor_occurred ON audit_events (actor_id, occurred_at)"))
        conn.execute(text(
            "CREATE INDEX ix_audit_resource ON audit_events (resource_type, resource_id, occurred_at)"
        ))
        conn.execute(text(
            "CREATE INDEX ix_audit_metadata_gin ON audit_events USING gin (metadata)"
        ))

        conn.commit()
        logger.info("audit_events table created successfully with all indexes")


if __name__ == "__main__":
    run_migration()
