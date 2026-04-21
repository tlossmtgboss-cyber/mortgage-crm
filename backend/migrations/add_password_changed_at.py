"""
Add password_changed_at Column to Users Table

Adds a timezone-aware timestamp column for tracking when a user last changed
their password. Used to:
  - Invalidate password reset tokens after use (single-use enforcement)
  - Revoke pre-existing sessions after a password change (HIGH-02 / HIGH-03)

Usage:
    python -m migrations.add_password_changed_at
    # or
    from migrations.add_password_changed_at import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Add password_changed_at column to the users table."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        try:
            if is_sqlite:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ"
                ))
            conn.commit()
            logger.info("Added password_changed_at column to users table")
        except Exception as e:
            error_str = str(e).lower()
            if "duplicate column" in error_str or "already exists" in error_str:
                logger.info("password_changed_at column already exists on users table")
            elif "no such table" in error_str:
                logger.warning("users table does not exist, skipping")
            else:
                logger.error(f"Failed to add password_changed_at column: {e}")
                return False

    logger.info("password_changed_at migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
