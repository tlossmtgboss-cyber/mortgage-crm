"""
Migration: Add CI Enhancement Columns

Adds columns to call_sessions for:
- P7: telephony_call_id, call_provider (link CI sessions to actual phone calls)
- P2: last_flush_at (track periodic transcript flush timing)

Run with: python -m migrations.add_ci_enhancement_columns
"""

import os
import sys
import logging

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Add CI enhancement columns to call_sessions."""
    from sqlalchemy import text

    if engine is None:
        from db import engine as _engine
        engine = _engine

    columns = [
        # P7: Link to telephony provider call
        ("call_sessions", "telephony_call_id", "VARCHAR(255)", None),
        ("call_sessions", "call_provider", "VARCHAR(50)", None),
        # P2: Track last transcript flush
        ("call_sessions", "last_flush_at", "TIMESTAMP WITH TIME ZONE", None),
    ]

    with engine.connect() as conn:
        for table, column, col_type, default in columns:
            try:
                default_clause = f" DEFAULT {default}" if default else ""
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                    f"{column} {col_type}{default_clause}"
                ))
                logger.info(f"Added column {table}.{column} ({col_type})")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"Column {table}.{column} already exists, skipping")
                else:
                    logger.error(f"Failed to add {table}.{column}: {e}")

        # Add index on telephony_call_id for fast lookups
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_call_sessions_telephony_call_id
                ON call_sessions (telephony_call_id)
                WHERE telephony_call_id IS NOT NULL
            """))
            logger.info("Created index ix_call_sessions_telephony_call_id")
        except Exception as e:
            logger.info(f"Index creation note: {e}")

        # Add index on call_provider for filtering
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_call_sessions_call_provider
                ON call_sessions (call_provider)
                WHERE call_provider IS NOT NULL
            """))
            logger.info("Created index ix_call_sessions_call_provider")
        except Exception as e:
            logger.info(f"Index creation note: {e}")

        conn.commit()
        logger.info("CI enhancement migration complete")


if __name__ == "__main__":
    run_migration()
