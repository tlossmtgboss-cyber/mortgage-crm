"""
Migration: Add dead_letter_at column to webhook_delivery_logs table.

Tracks when a failed webhook delivery entered the dead-letter queue,
enabling dead-letter queue queries and retry workflows.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Add dead_letter_at column to webhook_delivery_logs if it doesn't exist."""
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'webhook_delivery_logs'
              AND column_name = 'dead_letter_at'
        """))
        if result.fetchone():
            logger.info("Column dead_letter_at already exists on webhook_delivery_logs, skipping")
            return

        # Add the column
        conn.execute(text("""
            ALTER TABLE webhook_delivery_logs
            ADD COLUMN dead_letter_at TIMESTAMPTZ NULL
        """))

        # Add index for dead-letter queue queries
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_webhook_log_dead_letter
            ON webhook_delivery_logs (dead_letter_at)
            WHERE dead_letter_at IS NOT NULL
        """))

        conn.commit()
        logger.info("Added dead_letter_at column and partial index to webhook_delivery_logs")


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from db import engine
    run_migration(engine)
    print("Migration complete.")
