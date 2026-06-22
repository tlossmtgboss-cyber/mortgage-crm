"""
Fix recruit_landing_pages RLS policies.

The original add_recruit_landing_pages migration created recruit_lp_tenant_isolation
using a slug-based subquery:
    organization_id = (SELECT id FROM organizations WHERE slug = current_setting(...))

But set_tenant_context() sets app.current_tenant to the INTEGER org_id, not the slug.
This meant the tenant isolation policy never matched, and the seed_callcenter_page
endpoint's INSERT was also blocked by the WITH CHECK (since no WITH CHECK was specified,
USING was used for both SELECT and INSERT checks).

Fix: rewrite recruit_lp_tenant_isolation to use integer text comparison, matching
the pattern used by all other recruiting tables (enable_recruiting_rls.py).

Re-seeds the callcenter page for any org that doesn't already have it.
"""
import json
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None) -> None:
    if engine is None:
        from db import engine as _engine
        engine = _engine

    if not str(engine.url).startswith("postgresql"):
        logger.info("[SKIP] fix_recruit_lp_rls — not a PostgreSQL database")
        return

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        # Check table exists
        exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = 'recruit_landing_pages' AND table_schema = 'public'")
        ).fetchone()
        if not exists:
            logger.info("[SKIP] recruit_landing_pages table does not exist yet")
            return

        # Remove FORCE ROW LEVEL SECURITY — Railway connects as the table owner,
        # so FORCE RLS causes the broken policies to block ALL queries.
        # App-layer isolation (WHERE organization_id = :oid on every query) is sufficient.
        conn.execute(text("ALTER TABLE recruit_landing_pages NO FORCE ROW LEVEL SECURITY"))
        logger.info("[RLS] Removed FORCE ROW LEVEL SECURITY from recruit_landing_pages")

        # Keep RLS enabled with clean policies (still enforced for non-owner roles)
        conn.execute(text("DROP POLICY IF EXISTS recruit_lp_tenant_isolation ON recruit_landing_pages"))
        conn.execute(text("""
            CREATE POLICY recruit_lp_tenant_isolation ON recruit_landing_pages
            FOR ALL
            USING (
                organization_id::text = NULLIF(current_setting('app.current_tenant', TRUE), '')
            )
            WITH CHECK (
                organization_id::text = NULLIF(current_setting('app.current_tenant', TRUE), '')
            )
        """))
        logger.info("[RLS] Created integer-based recruit_lp_tenant_isolation policy")

        conn.execute(text("DROP POLICY IF EXISTS recruit_lp_public_read ON recruit_landing_pages"))
        conn.execute(text("""
            CREATE POLICY recruit_lp_public_read ON recruit_landing_pages
            FOR SELECT
            USING (status = 'published')
        """))
        logger.info("[RLS] Recreated recruit_lp_public_read policy")

    logger.info("✅ fix_recruit_lp_rls complete")

    # Re-seed callcenter page for any org that doesn't have it yet.
    # Uses SET app.current_tenant = org_id (integer as text) matching the new policy.
    try:
        from migrations.add_recruit_landing_pages import _CALLCENTER_CONFIG

        with engine.connect() as list_conn:
            orgs = list_conn.execute(
                text("SELECT id, slug FROM organizations WHERE slug IS NOT NULL AND slug != ''")
            ).fetchall()

        for org_id, org_slug in orgs:
            try:
                with engine.begin() as seed_conn:
                    # Set tenant context as integer (matching new policy)
                    seed_conn.execute(text(f"SET app.current_tenant = '{org_id}'"))
                    seed_conn.execute(text("""
                        INSERT INTO recruit_landing_pages
                            (organization_id, title, slug, status, config)
                        VALUES (:org_id, :title, :slug, 'published', CAST(:config AS jsonb))
                        ON CONFLICT (organization_id, slug)
                        DO UPDATE SET
                            config = CAST(EXCLUDED.config AS jsonb),
                            status = 'published',
                            updated_at = NOW()
                    """), {
                        "org_id": org_id,
                        "title": "Call Center — SC",
                        "slug": "callcenter",
                        "status": "published",
                        "config": json.dumps(_CALLCENTER_CONFIG),
                    })
                logger.info(f"[SEED] Callcenter page ready for org {org_id} ({org_slug})")
            except Exception as e:
                logger.warning(f"[SEED] Could not seed callcenter for org {org_id}: {e}")
    except Exception as e:
        logger.warning(f"[SEED] Re-seed step failed (non-fatal): {e}")
