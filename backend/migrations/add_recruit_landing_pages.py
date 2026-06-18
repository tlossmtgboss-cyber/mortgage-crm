"""Migration: create recruit_landing_pages table with RLS."""
import logging

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    from sqlalchemy import text
    if engine is None:
        from database import engine as _engine
        engine = _engine
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_landing_pages (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                title VARCHAR(200) NOT NULL,
                slug VARCHAR(100) NOT NULL UNIQUE,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                config JSONB NOT NULL DEFAULT '{}',
                view_count INTEGER NOT NULL DEFAULT 0,
                submission_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                created_by INTEGER REFERENCES users(id)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recruit_lp_org ON recruit_landing_pages(organization_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recruit_lp_slug ON recruit_landing_pages(slug)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_recruit_lp_status ON recruit_landing_pages(status)"))
        conn.execute(text("ALTER TABLE recruit_landing_pages ENABLE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE recruit_landing_pages FORCE ROW LEVEL SECURITY"))
        conn.execute(text("""
            DO $$ BEGIN
                DROP POLICY IF EXISTS recruit_landing_pages_tenant ON recruit_landing_pages;
                CREATE POLICY recruit_landing_pages_tenant ON recruit_landing_pages
                    USING (organization_id = (
                        SELECT id FROM organizations
                        WHERE id = current_setting('app.current_tenant', true)::int
                    ));
            EXCEPTION WHEN others THEN NULL;
            END $$
        """))
        conn.commit()
    logger.info("✅ recruit_landing_pages table created/verified")
    return {"created": True}
