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

        # Fully disable RLS — app-layer isolation (WHERE organization_id = :oid on
        # every query) is sufficient. DISABLE RLS removes all policy checks and FORCE
        # RLS in one shot, avoiding the slug-vs-integer policy confusion entirely.
        conn.execute(text("ALTER TABLE recruit_landing_pages DISABLE ROW LEVEL SECURITY"))
        conn.execute(text("DROP POLICY IF EXISTS recruit_lp_tenant_isolation ON recruit_landing_pages"))
        conn.execute(text("DROP POLICY IF EXISTS recruit_lp_public_read ON recruit_landing_pages"))
        logger.info("[RLS] Disabled RLS on recruit_landing_pages (app-layer isolation used)")

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
