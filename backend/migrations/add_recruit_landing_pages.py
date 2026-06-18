"""
Recruit Landing Pages Migration

Creates recruit_landing_pages table — stores configurable HTML landing pages
for the recruiting platform (website builder).
"""

import json
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

_CALLCENTER_CONFIG = {
    "page_title": "Careers | CMG Home Loans — South Carolina",
    "company_name": "CMG Home Loans",
    "location_display": "Charleston & Columbia, SC",
    "primary_color": "#6AAA26",
    "primary_color_dark": "#578F1E",
    "primary_color_pale": "#EFF7E1",
    "hero_headline": 'Build a <span class="red">six-figure</span><br>mortgage career<br>from <span class="italic">day one.</span>',
    "hero_subheadline": "No mortgage experience required. CMG Home Loans South Carolina call center is recruiting driven, coachable people ready to earn what they're worth in one of America's most resilient industries.",
    "signing_bonus": "$2,500",
    "signing_bonus_month": "July",
    "signing_bonus_deadline": "July 31st",
    "year1_range": "$65–90K",
    "year2_top": "$120,000+",
    "senior_lo": "$180,000+",
    "team_lead": "$250,000+",
    "stat_1_num": "2,400+", "stat_1_label": "Loans closed in SC last year",
    "stat_2_num": "94%", "stat_2_label": "Employees promoted within 18 months",
    "stat_3_num": "4.97 ★", "stat_3_label": "Tim Loss team borrower rating",
    "stat_4_num": "8 Weeks", "stat_4_label": "Fully paid training program",
    "manager_initials": "TL", "manager_name": "Tim Loss",
    "manager_title": "Branch Manager · CMG Home Loans, Mt. Pleasant SC · NMLS# 187037",
    "manager_nmls": "187037",
    "contact_phone_display": "(843) 834-4997",
    "contact_phone_tel": "+18438344997",
    "branch_address": "975 Johnnie Dodds Blvd. Suite A, Mt. Pleasant, SC 29464",
    "branch_nmls": "1594871",
}


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

            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'recruit_landing_pages'
                      AND constraint_name = 'uq_recruit_landing_pages_org_slug'
                ) THEN
                    ALTER TABLE recruit_landing_pages
                    ADD CONSTRAINT uq_recruit_landing_pages_org_slug
                    UNIQUE (organization_id, slug);
                END IF;
            END $$;

            DROP POLICY IF EXISTS recruit_lp_tenant_isolation ON recruit_landing_pages;
            CREATE POLICY recruit_lp_tenant_isolation ON recruit_landing_pages
                USING (
                    organization_id = (
                        SELECT id FROM organizations
                        WHERE slug = current_setting('app.current_tenant', TRUE)
                        LIMIT 1
                    )
                );

            DROP POLICY IF EXISTS recruit_lp_public_read ON recruit_landing_pages;
            CREATE POLICY recruit_lp_public_read ON recruit_landing_pages
                FOR SELECT
                USING (status = 'published');
        """))

        conn.commit()
        logger.info("✅ recruit_landing_pages table ready")

    # Seed callcenter page for every org. Each INSERT is in its own
    # engine.begin() so FORCE RLS doesn't block us — we set app.current_tenant
    # to the org slug before inserting so the tenant isolation policy passes.
    # ON CONFLICT DO NOTHING makes this idempotent across restarts.
    try:
        with engine.connect() as list_conn:
            orgs = list_conn.execute(
                text("SELECT id, slug FROM organizations")
            ).fetchall()
        for org_id, org_slug in orgs:
            try:
                with engine.begin() as seed_conn:
                    seed_conn.execute(
                        text(f"SET app.current_tenant = '{org_slug}'")
                    )
                    seed_conn.execute(text("""
                        INSERT INTO recruit_landing_pages
                            (organization_id, title, slug, status, config)
                        VALUES (:org_id, :title, :slug, :status, CAST(:config AS jsonb))
                        ON CONFLICT (organization_id, slug) DO NOTHING
                    """), {
                        "org_id": org_id,
                        "title": "Call Center — SC",
                        "slug": "callcenter",
                        "status": "published",
                        "config": json.dumps(_CALLCENTER_CONFIG),
                    })
            except Exception as e:
                logger.warning(f"Could not seed callcenter page for org {org_id}: {e}")
    except Exception as e:
        logger.warning(f"Could not seed callcenter pages: {e}")
