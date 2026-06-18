"""
Recruit Landing Pages Migration

Creates recruit_landing_pages table — stores configurable HTML landing pages
for the recruiting platform (website builder).
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None) -> None:
    if engine is None:
        from db import engine as _engine
        engine = _engine

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_landing_pages (
                id              SERIAL          PRIMARY KEY,
                organization_id INTEGER         NOT NULL,
                title           VARCHAR(255)    NOT NULL,
                slug            VARCHAR(100)    NOT NULL,
                status          VARCHAR(20)     NOT NULL DEFAULT 'draft',
                config          JSONB           NOT NULL DEFAULT '{}'::jsonb,
                view_count      INTEGER         NOT NULL DEFAULT 0,
                submission_count INTEGER        NOT NULL DEFAULT 0,
                created_by      INTEGER,
                created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_recruit_landing_pages_org_slug UNIQUE (organization_id, slug)
            );

            CREATE INDEX IF NOT EXISTS ix_recruit_lp_org
                ON recruit_landing_pages (organization_id);
            CREATE INDEX IF NOT EXISTS ix_recruit_lp_slug
                ON recruit_landing_pages (slug);
            CREATE INDEX IF NOT EXISTS ix_recruit_lp_status
                ON recruit_landing_pages (status);

            ALTER TABLE recruit_landing_pages ENABLE ROW LEVEL SECURITY;
            ALTER TABLE recruit_landing_pages FORCE ROW LEVEL SECURITY;

            DROP POLICY IF EXISTS recruit_lp_tenant_isolation ON recruit_landing_pages;
            CREATE POLICY recruit_lp_tenant_isolation ON recruit_landing_pages
                USING (
                    organization_id = (
                        SELECT id FROM recruit_platform_tenants
                        WHERE org_slug = current_setting('app.current_tenant', TRUE)
                        LIMIT 1
                    )
                );
        """))
        conn.commit()
        logger.info("✅ recruit_landing_pages table ready")
