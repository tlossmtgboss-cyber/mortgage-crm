"""
Migration: Enable PostgreSQL Row-Level Security (RLS) on all tenant-scoped tables.

Auto-discovers every table with an organization_id column and creates a
tenant_isolation policy that filters rows by the session variable
app.current_tenant (set by db.py's get_db() on each request).

Safety:
- Fail-closed: if app.current_tenant is not set or empty, the policy
  evaluates to NULL = organization_id, which is FALSE for all rows.
  No tenant context = zero rows returned (not all rows).
- FORCE ROW LEVEL SECURITY ensures even table owners are subject to RLS.
- Skips tables that already have RLS enabled.
- Wraps all DDL in a single transaction (atomic apply/rollback).

Usage:
    # Dry run — prints SQL without executing
    python -m migrations.enable_row_level_security --dry-run

    # Apply RLS policies
    python -m migrations.enable_row_level_security

    # Rollback — disable RLS on all tables
    python -m migrations.enable_row_level_security --rollback

    # Rollback dry run
    python -m migrations.enable_row_level_security --rollback --dry-run
"""
import os
import sys
import argparse
import logging

# Add parent directory to path so `python -m migrations.enable_row_level_security` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL templates
# ---------------------------------------------------------------------------

# The USING clause is the read filter; WITH CHECK is the write filter.
# NULLIF(current_setting('app.current_tenant', true), '') handles three cases:
#   1. Variable set to a valid integer string  -> cast succeeds, policy filters
#   2. Variable set to ''  (empty)             -> NULLIF returns NULL, comparison
#      NULL = organization_id is FALSE -> zero rows (fail-closed)
#   3. Variable not set at all                 -> current_setting returns NULL
#      (the `true` second arg prevents an error), NULL cast is still NULL,
#      NULL = organization_id is FALSE -> zero rows (fail-closed)
POLICY_SQL = """
CREATE POLICY tenant_isolation ON {table}
    FOR ALL
    USING (
        organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
    )
    WITH CHECK (
        organization_id = NULLIF(current_setting('app.current_tenant', true), '')::integer
    );
"""


def _get_database_url() -> str:
    """Resolve DATABASE_URL from environment, fixing the postgres:// prefix."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        logger.error("DATABASE_URL environment variable is not set")
        sys.exit(1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url.startswith("postgresql"):
        logger.error("RLS migration requires PostgreSQL (got non-PostgreSQL URL)")
        sys.exit(1)
    return url


def _discover_tables(conn) -> list[str]:
    """Return a sorted list of tables in the public schema that have an organization_id column."""
    from sqlalchemy import text

    result = conn.execute(text("""
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_name = 'organization_id'
        ORDER BY table_name
    """))
    tables = [row[0] for row in result.fetchall()]
    logger.info(f"Discovered {len(tables)} table(s) with organization_id column")
    return tables


def _tables_with_rls_enabled(conn) -> set[str]:
    """Return the set of table names that already have RLS enabled."""
    from sqlalchemy import text

    result = conn.execute(text("""
        SELECT relname
        FROM pg_class
        WHERE relrowsecurity = true
          AND relnamespace = 'public'::regnamespace
    """))
    return {row[0] for row in result.fetchall()}


def _existing_policies(conn, table: str) -> list[str]:
    """Return policy names currently defined on a table."""
    from sqlalchemy import text

    result = conn.execute(text("""
        SELECT polname
        FROM pg_policy
        JOIN pg_class ON pg_class.oid = pg_policy.polrelid
        WHERE pg_class.relname = :table_name
          AND pg_class.relnamespace = 'public'::regnamespace
    """), {"table_name": table})
    return [row[0] for row in result.fetchall()]


# ---------------------------------------------------------------------------
# Forward migration: enable RLS
# ---------------------------------------------------------------------------

def enable_rls(dry_run: bool = False) -> None:
    """Enable RLS and create tenant_isolation policy on every eligible table."""
    from sqlalchemy import create_engine, text

    database_url = _get_database_url()
    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Start an explicit transaction so everything is atomic
        trans = conn.begin()
        try:
            all_tables = _discover_tables(conn)
            already_enabled = _tables_with_rls_enabled(conn)

            if not all_tables:
                logger.warning("No tables with organization_id found. Nothing to do.")
                trans.rollback()
                return

            applied = 0
            skipped = 0

            for table in all_tables:
                # Skip if RLS is already enabled AND our policy already exists
                if table in already_enabled:
                    policies = _existing_policies(conn, table)
                    if "tenant_isolation" in policies:
                        logger.info(f"SKIP  {table:40s} — RLS already enabled with tenant_isolation policy")
                        skipped += 1
                        continue
                    else:
                        # RLS enabled but our policy is missing — add it
                        logger.info(f"ADD   {table:40s} — RLS enabled but tenant_isolation policy missing")

                # --- Build the DDL statements for this table ---
                stmts = []

                if table not in already_enabled:
                    stmts.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
                    stmts.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

                # Drop any pre-existing policy with the same name (idempotent)
                stmts.append(f"DROP POLICY IF EXISTS tenant_isolation ON {table};")
                stmts.append(POLICY_SQL.format(table=table).strip())

                for stmt in stmts:
                    if dry_run:
                        logger.info(f"[DRY RUN] {stmt}")
                    else:
                        conn.execute(text(stmt))
                        logger.info(f"EXEC  {stmt[:120]}")

                applied += 1

            # --- Create/replace helper functions (same as alembic 006 migration) ---
            helper_functions = [
                """
                CREATE OR REPLACE FUNCTION set_tenant_context(tenant_id integer)
                RETURNS void AS $$
                BEGIN
                    PERFORM set_config('app.current_tenant', tenant_id::text, true);
                END;
                $$ LANGUAGE plpgsql;
                """,
                """
                CREATE OR REPLACE FUNCTION get_current_tenant()
                RETURNS integer AS $$
                BEGIN
                    RETURN NULLIF(current_setting('app.current_tenant', true), '')::integer;
                END;
                $$ LANGUAGE plpgsql;
                """,
                """
                CREATE OR REPLACE FUNCTION clear_tenant_context()
                RETURNS void AS $$
                BEGIN
                    PERFORM set_config('app.current_tenant', '', true);
                END;
                $$ LANGUAGE plpgsql;
                """,
            ]

            for func_sql in helper_functions:
                if dry_run:
                    logger.info(f"[DRY RUN] {func_sql.strip()[:100]}...")
                else:
                    conn.execute(text(func_sql))

            if dry_run:
                logger.info(f"\n{'='*60}")
                logger.info(f"DRY RUN COMPLETE: {applied} table(s) would be modified, {skipped} already configured")
                logger.info(f"{'='*60}")
                trans.rollback()
            else:
                trans.commit()
                logger.info(f"\n{'='*60}")
                logger.info(f"RLS ENABLED: {applied} table(s) modified, {skipped} already configured")
                logger.info(f"{'='*60}")

        except Exception:
            trans.rollback()
            logger.exception("RLS migration failed — transaction rolled back")
            raise

    engine.dispose()


# ---------------------------------------------------------------------------
# Rollback: disable RLS
# ---------------------------------------------------------------------------

def rollback_rls(dry_run: bool = False) -> None:
    """Disable RLS and drop tenant_isolation policies on all tables."""
    from sqlalchemy import create_engine, text

    database_url = _get_database_url()
    engine = create_engine(database_url)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            all_tables = _discover_tables(conn)
            enabled = _tables_with_rls_enabled(conn)

            rolled_back = 0
            skipped = 0

            for table in all_tables:
                if table not in enabled:
                    logger.info(f"SKIP  {table:40s} — RLS not enabled")
                    skipped += 1
                    continue

                stmts = [
                    f"DROP POLICY IF EXISTS tenant_isolation ON {table};",
                    f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;",
                    f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;",
                ]

                for stmt in stmts:
                    if dry_run:
                        logger.info(f"[DRY RUN] {stmt}")
                    else:
                        conn.execute(text(stmt))
                        logger.info(f"EXEC  {stmt}")

                rolled_back += 1

            # Drop helper functions
            drop_funcs = [
                "DROP FUNCTION IF EXISTS set_tenant_context(integer);",
                "DROP FUNCTION IF EXISTS get_current_tenant();",
                "DROP FUNCTION IF EXISTS clear_tenant_context();",
            ]
            for stmt in drop_funcs:
                if dry_run:
                    logger.info(f"[DRY RUN] {stmt}")
                else:
                    conn.execute(text(stmt))
                    logger.info(f"EXEC  {stmt}")

            if dry_run:
                logger.info(f"\n{'='*60}")
                logger.info(f"DRY RUN COMPLETE: {rolled_back} table(s) would be rolled back, {skipped} not enabled")
                logger.info(f"{'='*60}")
                trans.rollback()
            else:
                trans.commit()
                logger.info(f"\n{'='*60}")
                logger.info(f"RLS ROLLED BACK: {rolled_back} table(s) modified, {skipped} were not enabled")
                logger.info(f"{'='*60}")

        except Exception:
            trans.rollback()
            logger.exception("RLS rollback failed — transaction rolled back")
            raise

    engine.dispose()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Enable PostgreSQL Row-Level Security (RLS) on all tenant-scoped tables",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the SQL that would be executed without making changes",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Disable RLS and remove tenant_isolation policies from all tables",
    )
    args = parser.parse_args()

    if args.rollback:
        logger.info("Starting RLS ROLLBACK%s", " (dry run)" if args.dry_run else "")
        rollback_rls(dry_run=args.dry_run)
    else:
        logger.info("Starting RLS ENABLE%s", " (dry run)" if args.dry_run else "")
        enable_rls(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
