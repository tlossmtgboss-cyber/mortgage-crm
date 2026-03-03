"""
Add organization_id to social_tokens table for multi-tenant isolation.

Changes:
1. ADD COLUMN organization_id INTEGER
2. Backfill NULLs from default organization
3. SET NOT NULL
4. DROP old UNIQUE on (platform)
5. CREATE new UNIQUE INDEX on (platform, organization_id)
6. CREATE INDEX on organization_id
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Add organization_id to social_tokens for tenant isolation."""
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'social_tokens' AND column_name = 'organization_id'
        """))
        if result.fetchone():
            logger.info("social_tokens.organization_id already exists, skipping migration")
            return

        # Check if table exists at all
        result = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'social_tokens'
        """))
        if not result.fetchone():
            logger.info("social_tokens table does not exist, skipping migration")
            return

        logger.info("Adding organization_id to social_tokens...")

        # 1. Add nullable column
        conn.execute(text("""
            ALTER TABLE social_tokens ADD COLUMN organization_id INTEGER
        """))

        # 2. Backfill from the first organization
        conn.execute(text("""
            UPDATE social_tokens
            SET organization_id = (SELECT id FROM organizations ORDER BY id LIMIT 1)
            WHERE organization_id IS NULL
        """))

        # 3. Set NOT NULL
        conn.execute(text("""
            ALTER TABLE social_tokens ALTER COLUMN organization_id SET NOT NULL
        """))

        # 4. Drop old unique constraint on (platform) if it exists
        conn.execute(text("""
            DO $$
            BEGIN
                -- Drop any unique constraint/index on just (platform)
                IF EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE tablename = 'social_tokens'
                    AND indexdef LIKE '%UNIQUE%'
                    AND indexdef LIKE '%platform%'
                    AND indexdef NOT LIKE '%organization_id%'
                ) THEN
                    EXECUTE (
                        SELECT 'DROP INDEX ' || indexname
                        FROM pg_indexes
                        WHERE tablename = 'social_tokens'
                        AND indexdef LIKE '%UNIQUE%'
                        AND indexdef LIKE '%platform%'
                        AND indexdef NOT LIKE '%organization_id%'
                        LIMIT 1
                    );
                END IF;
            END $$;
        """))

        # 5. Create new unique index on (platform, organization_id)
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_social_tokens_platform_org
            ON social_tokens (platform, organization_id)
        """))

        # 6. Create index on organization_id
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_social_tokens_org_id
            ON social_tokens (organization_id)
        """))

        conn.commit()
        logger.info("social_tokens.organization_id migration complete")
