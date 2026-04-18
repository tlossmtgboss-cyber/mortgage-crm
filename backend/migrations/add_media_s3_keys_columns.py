"""
Migration: Add media_s3_keys column to SMS tables.

MMS media attachments were previously stored on local filesystem (ephemeral on
Railway) or referenced via temporary provider URLs. This migration adds a
media_s3_keys JSONB column to store permanent S3 object keys for each message's
media attachments.

Tables affected:
  - sms_panel_messages    (two-way SMS panel)
  - sms_intelligence_queue (SMS intelligence inbox)

Run: python -m migrations.add_media_s3_keys_columns
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Add media_s3_keys JSONB column to SMS tables."""
    # Add backend to path if needed
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from database import engine
    from sqlalchemy import text

    statements = [
        # sms_panel_messages
        """
        ALTER TABLE sms_panel_messages
        ADD COLUMN IF NOT EXISTS media_s3_keys JSONB DEFAULT '[]'::jsonb
        """,
        # sms_intelligence_queue
        """
        ALTER TABLE sms_intelligence_queue
        ADD COLUMN IF NOT EXISTS media_s3_keys JSONB DEFAULT '[]'::jsonb
        """,
    ]

    with engine.connect() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                logger.info("OK: %s", stmt.strip().split("\n")[1].strip())
            except Exception as e:
                logger.warning("Skipped (may already exist): %s", e)
        conn.commit()

    logger.info("Migration complete: media_s3_keys columns added")


if __name__ == "__main__":
    run_migration()
