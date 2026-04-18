"""
Migration: Add SMS delivery tracking columns.

Adds delivery tracking to three tables so Telnyx delivery webhooks
(message.sent / message.finalized) can update message status:

1. sms_messages: delivery_status, delivered_at
2. bulk_sms_campaigns: delivered_count (was missing from DDL)
3. bulk_sms_sends: index on telnyx_message_id for webhook lookups

Safe to re-run: uses ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Add SMS delivery tracking columns and indexes."""
    engine = create_engine(DATABASE_URL)
    is_postgres = "postgresql" in DATABASE_URL.lower()

    with engine.connect() as conn:
        # ------------------------------------------------------------------
        # 1. sms_messages: add delivery_status and delivered_at
        # ------------------------------------------------------------------
        if is_postgres:
            conn.execute(text("""
                ALTER TABLE sms_messages
                ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(30) DEFAULT 'queued';
            """))
            conn.execute(text("""
                ALTER TABLE sms_messages
                ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP;
            """))
        else:
            # SQLite — check if column exists first
            try:
                conn.execute(text(
                    "ALTER TABLE sms_messages ADD COLUMN delivery_status VARCHAR(30) DEFAULT 'queued'"
                ))
            except Exception:
                pass  # Column already exists
            try:
                conn.execute(text(
                    "ALTER TABLE sms_messages ADD COLUMN delivered_at TIMESTAMP"
                ))
            except Exception:
                pass

        print("  [OK] sms_messages: delivery_status, delivered_at")

        # ------------------------------------------------------------------
        # 2. bulk_sms_campaigns: add delivered_count
        # ------------------------------------------------------------------
        if is_postgres:
            conn.execute(text("""
                ALTER TABLE bulk_sms_campaigns
                ADD COLUMN IF NOT EXISTS delivered_count INTEGER DEFAULT 0;
            """))
        else:
            try:
                conn.execute(text(
                    "ALTER TABLE bulk_sms_campaigns ADD COLUMN delivered_count INTEGER DEFAULT 0"
                ))
            except Exception:
                pass

        print("  [OK] bulk_sms_campaigns: delivered_count")

        # ------------------------------------------------------------------
        # 3. bulk_sms_sends: index on telnyx_message_id for webhook lookups
        # ------------------------------------------------------------------
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bulk_sms_sends_telnyx_msg
            ON bulk_sms_sends (telnyx_message_id);
        """))

        print("  [OK] bulk_sms_sends: ix_bulk_sms_sends_telnyx_msg index")

        conn.commit()
        print("\nSuccessfully added SMS delivery tracking columns.")


def rollback_migration():
    """Remove the delivery tracking columns."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE sms_messages DROP COLUMN IF EXISTS delivery_status;"))
        conn.execute(text("ALTER TABLE sms_messages DROP COLUMN IF EXISTS delivered_at;"))
        conn.execute(text("ALTER TABLE bulk_sms_campaigns DROP COLUMN IF EXISTS delivered_count;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_bulk_sms_sends_telnyx_msg;"))
        conn.commit()
        print("Successfully rolled back SMS delivery tracking columns.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    else:
        run_migration()
