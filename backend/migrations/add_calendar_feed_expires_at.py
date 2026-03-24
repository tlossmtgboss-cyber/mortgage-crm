"""
Migration: Add expires_at column to calendar_feed_tokens table.

Feed tokens now expire after 90 days. Legacy tokens without an expires_at
value are treated as expired and will require regeneration.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Add expires_at column to calendar_feed_tokens if it doesn't exist."""
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'calendar_feed_tokens'
              AND column_name = 'expires_at'
        """))
        if result.fetchone():
            logger.info("Column expires_at already exists on calendar_feed_tokens, skipping")
            return

        # Add the column (nullable — legacy rows will have NULL, treated as expired)
        conn.execute(text("""
            ALTER TABLE calendar_feed_tokens
            ADD COLUMN expires_at TIMESTAMPTZ NULL
        """))

        conn.commit()
        logger.info("Added expires_at column to calendar_feed_tokens")


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from db import engine
    run_migration(engine)
    print("Migration complete.")
