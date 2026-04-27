"""
Migration: Application Events Table + Missing SMS Columns
==========================================================
Creates application_events table for the consent flow audit trail,
and adds missing columns to sms_messages that cause INSERT failures.

Run:
    python -m migrations.add_application_events_table
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def run_migration():
    from sqlalchemy import text
    from db import engine

    with engine.connect() as conn:
        # ── application_events table ──────────────────────────────
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS application_events (
                id SERIAL PRIMARY KEY,
                application_id INTEGER NOT NULL REFERENCES borrower_applications(id) ON DELETE CASCADE,
                event_type VARCHAR NOT NULL,
                event_data JSONB DEFAULT '{}',
                actor_type VARCHAR,
                actor_email VARCHAR,
                step VARCHAR,
                ip_address VARCHAR,
                user_agent VARCHAR,
                device_type VARCHAR,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_app_event_application
            ON application_events (application_id, created_at)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_app_event_type
            ON application_events (event_type)
        """))
        conn.commit()
        logger.info("Created application_events table")

        # ── Missing columns on sms_messages ───────────────────────
        sms_cols = [
            ("consent_record_id", "INTEGER"),
            ("consent_verified_at", "TIMESTAMP WITH TIME ZONE"),
            ("consent_method", "VARCHAR(50)"),
            ("delivery_status", "VARCHAR(30) DEFAULT 'queued'"),
        ]
        for col_name, col_type in sms_cols:
            try:
                conn.execute(text(
                    f"ALTER TABLE sms_messages ADD COLUMN IF NOT EXISTS "
                    f"{col_name} {col_type}"
                ))
            except Exception as e:
                logger.info("sms_messages.%s skipped: %s", col_name, e)
                conn.rollback()
        conn.commit()
        logger.info("Added missing columns to sms_messages")

        # ── Missing notifications.organization_id ─────────────────
        try:
            conn.execute(text(
                "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS "
                "organization_id INTEGER"
            ))
            conn.commit()
            logger.info("Added notifications.organization_id")
        except Exception as e:
            logger.info("notifications.organization_id skipped: %s", e)
            conn.rollback()

    logger.info("Migration complete")


if __name__ == "__main__":
    run_migration()
