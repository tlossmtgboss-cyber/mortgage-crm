"""
Migration: Add briefing_preferences JSONB column to users table.

Stores user customization for morning briefings: section toggles,
detection thresholds, and AI narrative tone. NULL = all defaults.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Add briefing_preferences column to users if it doesn't exist."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users'
              AND column_name = 'briefing_preferences'
        """))
        if result.fetchone():
            logger.info("Column briefing_preferences already exists on users, skipping")
            return

        conn.execute(text("""
            ALTER TABLE users ADD COLUMN briefing_preferences JSONB;
        """))
        conn.commit()
        logger.info("Added briefing_preferences JSONB column to users table")
