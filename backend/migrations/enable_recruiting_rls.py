"""
Enable Row Level Security on all mm_* (recruiting) tables.
Uses app.current_tenant GUC (set by get_db() in db.py).
FORCE ROW LEVEL SECURITY handles Railway's table-owner connection.

Tables covered
--------------
From add_master_manager_tables.py:
  mm_role_definitions, mm_talent_capacity, mm_talent_state,
  mm_talent_state_history, mm_talent_performance, mm_capacity_alerts,
  mm_coverage_map, mm_candidates, mm_job_postings

From add_recruiting_tables.py:
  mm_interviews, mm_offers, mm_candidate_activities, mm_candidate_notes

From add_candidate_grading_system.py:
  mm_candidate_assessments, mm_assessment_history

From add_score_gate_bypass_log.py (new Task 2 table):
  mm_score_gate_bypass_log

From recruit_ai_audit_log (no mm_ prefix but recruiting-related):
  recruit_ai_audit_log

Tables without organization_id (lookup/config tables — skipped):
  mm_role_definitions  ← no org column; shared config
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Tables that store tenant data and must be isolated.
# All must have an organization_id column; the migration skips any that don't.
STRICT_TABLES = [
    "mm_candidates",
    "mm_job_postings",
    "mm_interviews",
    "mm_offers",
    "mm_candidate_activities",
    "mm_candidate_notes",
    "mm_candidate_assessments",
    "mm_assessment_history",
    "mm_talent_capacity",
    "mm_talent_state",
    "mm_talent_state_history",
    "mm_talent_performance",
    "mm_capacity_alerts",
    "mm_coverage_map",
    "mm_score_gate_bypass_log",
    "recruit_ai_audit_log",
]


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM information_schema.tables WHERE table_name = :t AND table_schema = 'public'"),
        {"t": table_name},
    )
    return result.fetchone() is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    result = conn.execute(
        text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c AND table_schema = 'public'
        """),
        {"t": table_name, "c": column_name},
    )
    return result.fetchone() is not None


def _policy_exists(conn, table_name: str, policy_name: str) -> bool:
    result = conn.execute(
        text("SELECT 1 FROM pg_policies WHERE tablename = :t AND policyname = :p"),
        {"t": table_name, "p": policy_name},
    )
    return result.fetchone() is not None


def _apply_strict_policy(conn, table_name: str) -> None:
    """Enable RLS + FORCE RLS and create the tenant isolation policy.

    Uses NULLIF(current_setting('app.current_tenant', true), '') so that an
    unset GUC (NULL or '') prevents row access — correct for unauthenticated
    requests and requests where set_tenant_context() was not called.
    """
    policy_name = f"{table_name}_tenant_isolation"

    if not _table_exists(conn, table_name):
        logger.info("[SKIP] %s — table does not exist", table_name)
        return

    if not _column_exists(conn, table_name, "organization_id"):
        logger.warning(
            "[SKIP] %s — organization_id column missing; add it before enabling RLS",
            table_name,
        )
        return

    conn.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    logger.info("[RLS] ENABLE ROW LEVEL SECURITY on %s", table_name)

    # FORCE RLS ensures policy applies even when the session role is the table
    # owner.  Railway PostgreSQL connects as the table owner, so without FORCE,
    # RLS is silently bypassed for every request.
    conn.execute(text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    logger.info("[RLS] FORCE ROW LEVEL SECURITY on %s", table_name)

    # Drop any stale policy (e.g. from a previous run that used app.current_org_id)
    if _policy_exists(conn, table_name, policy_name):
        conn.execute(text(f"DROP POLICY {policy_name} ON {table_name}"))
        logger.info("[RLS] Dropped old policy %s on %s", policy_name, table_name)

    conn.execute(text(f"""
        CREATE POLICY {policy_name} ON {table_name}
        FOR ALL
        USING (
            organization_id::text = NULLIF(current_setting('app.current_tenant', true), '')
        )
        WITH CHECK (
            organization_id::text = NULLIF(current_setting('app.current_tenant', true), '')
        )
    """))
    logger.info("[RLS] Created tenant isolation policy on %s", table_name)


def run_migration(engine=None) -> None:
    """Enable RLS on all mm_* recruiting tables.

    Runs in AUTOCOMMIT mode because ALTER TABLE … ENABLE ROW LEVEL SECURITY
    is DDL that cannot run inside an open transaction block on certain
    PostgreSQL configurations.
    """
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not engine.url.drivername.startswith("postgresql"):
        logger.info("[SKIP] enable_recruiting_rls — not a PostgreSQL database")
        return

    logger.info("Starting enable_recruiting_rls migration...")

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        for table in STRICT_TABLES:
            try:
                _apply_strict_policy(conn, table)
            except Exception as e:
                err = str(e).lower()
                if "already exists" in err:
                    logger.info("[SKIP] Policy already exists on %s", table)
                else:
                    logger.warning("[WARN] Could not enable RLS on %s: %s", table, e)

    logger.info(
        "enable_recruiting_rls complete. Tables processed: %s",
        ", ".join(STRICT_TABLES),
    )


def rollback(engine=None) -> None:
    """Remove all RLS policies created by this migration and disable RLS."""
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not engine.url.drivername.startswith("postgresql"):
        logger.info("[SKIP] rollback — not PostgreSQL")
        return

    logger.info("Rolling back enable_recruiting_rls...")

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        for table_name in STRICT_TABLES:
            try:
                if not _table_exists(conn, table_name):
                    continue

                policy_name = f"{table_name}_tenant_isolation"
                if _policy_exists(conn, table_name, policy_name):
                    conn.execute(text(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"))
                    logger.info("[ROLLBACK] Dropped policy %s", policy_name)

                conn.execute(text(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY"))
                conn.execute(text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))
                logger.info("[ROLLBACK] Disabled RLS on %s", table_name)
            except Exception as e:
                logger.warning("[ROLLBACK] Could not disable RLS on %s: %s", table_name, e)

    logger.info("enable_recruiting_rls rollback complete")


if __name__ == "__main__":
    import sys
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        run_migration()
    sys.exit(0)
