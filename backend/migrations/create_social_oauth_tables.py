"""
Create social_oauth_states and social_tokens tables.

social_oauth_states: stores OAuth CSRF state tokens for Facebook/LinkedIn callbacks
social_tokens: stores access tokens for social platform integrations

Both tables are referenced by recruit_social_routes.py but were never created.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Create social_oauth_states and social_tokens tables if they don't exist."""
    with engine.connect() as conn:
        # 1. Create social_oauth_states table
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'social_oauth_states'
        """))
        if not result.fetchone():
            logger.info("Creating social_oauth_states table...")
            conn.execute(text("""
                CREATE TABLE social_oauth_states (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    platform VARCHAR(50) NOT NULL,
                    state VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_social_oauth_state UNIQUE (user_id, platform, state)
                )
            """))
            conn.execute(text("""
                CREATE INDEX ix_social_oauth_states_user_platform
                ON social_oauth_states (user_id, platform)
            """))
            # Auto-cleanup: states older than 1 hour are stale
            logger.info("social_oauth_states table created")
        else:
            logger.info("social_oauth_states already exists, skipping")

        # 2. Create social_tokens table (if not exists)
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'social_tokens'
        """))
        if not result.fetchone():
            logger.info("Creating social_tokens table...")
            conn.execute(text("""
                CREATE TABLE social_tokens (
                    id SERIAL PRIMARY KEY,
                    platform VARCHAR(50) NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at TIMESTAMP,
                    organization_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT uq_social_tokens_platform_org UNIQUE (platform, organization_id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX ix_social_tokens_org_id
                ON social_tokens (organization_id)
            """))
            logger.info("social_tokens table created")
        else:
            logger.info("social_tokens already exists, skipping")

        conn.commit()
        logger.info("Social OAuth tables migration complete")
