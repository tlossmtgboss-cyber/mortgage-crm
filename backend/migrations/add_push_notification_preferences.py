"""
Migration: Add push notification preferences table and new device_tokens columns.

Adds:
- push_notification_preferences table (per-user category opt-in/out, mute, quiet hours)
- device_tokens.organization_id column (tenant isolation)
- device_tokens.device_name column
- device_tokens.app_version column
- device_tokens.last_used_at column
- device_tokens.failure_count column

Run manually:
    python migrations/add_push_notification_preferences.py

Or it will be applied automatically by _register_auth_security.py table creation.
"""
import os
import sys
import logging

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_migration():
    from sqlalchemy import text
    from db import engine

    with engine.connect() as conn:
        # ---------------------------------------------------------------
        # 1. Add new columns to device_tokens (if not already present)
        # ---------------------------------------------------------------
        new_columns = [
            ("organization_id", "INTEGER REFERENCES organizations(id) ON DELETE CASCADE"),
            ("device_name", "VARCHAR(200)"),
            ("app_version", "VARCHAR(50)"),
            ("last_used_at", "TIMESTAMP WITH TIME ZONE"),
            ("failure_count", "INTEGER DEFAULT 0"),
        ]

        for col_name, col_type in new_columns:
            try:
                conn.execute(text(
                    f"ALTER TABLE device_tokens ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                logger.info("Added column device_tokens.%s", col_name)
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    logger.info("Column device_tokens.%s already exists", col_name)
                else:
                    logger.warning("Could not add device_tokens.%s: %s", col_name, e)

        # Add index on organization_id
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_device_tokens_org_id ON device_tokens(organization_id)"
            ))
            logger.info("Created index idx_device_tokens_org_id")
        except Exception as e:
            logger.debug("Index creation skipped: %s", e)

        # ---------------------------------------------------------------
        # 2. Create push_notification_preferences table
        # ---------------------------------------------------------------
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS push_notification_preferences (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                    categories JSONB DEFAULT '{}',
                    muted BOOLEAN DEFAULT FALSE,
                    quiet_hours_start VARCHAR(5),
                    quiet_hours_end VARCHAR(5),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    CONSTRAINT uq_push_pref_user_id UNIQUE (user_id)
                )
            """))
            logger.info("Created push_notification_preferences table")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("push_notification_preferences table already exists")
            else:
                logger.warning("Could not create push_notification_preferences: %s", e)

        # Add indexes
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_push_pref_user_id ON push_notification_preferences(user_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_push_pref_org_id ON push_notification_preferences(organization_id)"
            ))
        except Exception as e:
            logger.debug("Index creation skipped: %s", e)

        conn.commit()
        logger.info("Push notification migration complete.")


if __name__ == "__main__":
    run_migration()
