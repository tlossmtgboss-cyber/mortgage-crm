"""
Enable Row-Level Security on all Smart Scheduler tables.

This migration ENABLES RLS and creates tenant isolation policies on the 8 core
scheduler tables (plus the audit log).  The add_scheduler_tenant_isolation
migration already added organization_id columns and attempted to create policies
using `app.current_org_id`.  This migration corrects the session variable name
to `app.current_tenant` (the canonical variable set by set_tenant_context in
database/tenant_mixin.py) and applies FORCE ROW LEVEL SECURITY so the owner
role cannot bypass the policy.

Public booking exception
------------------------
The /public/book/{slug} endpoints are unauthenticated — TenantContextMiddleware
never fires, so `app.current_tenant` is unset (empty string or error).
Public booking queries FIRST look up a scheduler_booking_links row by slug to
derive the org_id, THEN use that org_id to query other tables explicitly
(filter by organization_id in Python).  If the RLS policy on
scheduler_booking_links requires app.current_tenant to be set, the initial slug
lookup will fail (no rows returned → 404) for any public visitor.

Solution: scheduler_booking_links and appointment_types (also queried during
the public lookup) get a PERMISSIVE bypass policy for public access.  Rows
marked is_public = true are readable even when app.current_tenant is unset.
All other tables apply the strict tenant policy only.

Policy naming
-------------
All policies are named `{table}_tenant_isolation` to be consistent with what
add_scheduler_tenant_isolation.py created (which used `app.current_org_id` —
wrong variable).  We DROP + recreate so there is exactly one policy per table.

Idempotency
-----------
Safe to run multiple times.  All DDL steps are guarded by existence checks or
use DROP … IF EXISTS / IF NOT EXISTS patterns.  DDL runs outside a transaction
(AUTOCOMMIT) because ALTER TABLE … ENABLE ROW LEVEL SECURITY cannot execute
inside an open transaction block on some PostgreSQL versions.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Table inventory ───────────────────────────────────────────────────────────
# Canonical table names from database/models/scheduler.py:
#
#   SchedulerConfig             → scheduler_configs
#   AvailabilitySlot            → availability_slots        (NOTE: not scheduler_availability_slots)
#   SchedulerAppointmentType    → appointment_types         (NOTE: not scheduler_appointment_types)
#   Appointment                 → scheduler_appointments
#   SchedulerRoutingRule        → scheduler_routing_rules
#   BlockedTime                 → scheduler_blocked_times
#   BookingLink                 → scheduler_booking_links
#   AppointmentReminder         → scheduler_reminders
#   SchedulerAuditLog           → scheduler_audit_log

# Tables that get the strict authenticated-only policy.
STRICT_TABLES = [
    "scheduler_configs",
    "availability_slots",
    "scheduler_appointments",
    "scheduler_routing_rules",
    "scheduler_blocked_times",
    "scheduler_reminders",
    "scheduler_audit_log",
]

# Tables that also need a public-access bypass for unauthenticated booking flows.
# Public booking looks up booking_links by slug without an authenticated session,
# then derives org_id from the returned row and applies it to subsequent queries
# via explicit Python-level filtering.  appointment_types is loaded the same way.
PUBLIC_BYPASS_TABLES = [
    "scheduler_booking_links",
    "appointment_types",
]

ALL_TABLES = STRICT_TABLES + PUBLIC_BYPASS_TABLES

# Also protect slot_holds (SlotHold model) and appointment_status_history if
# they exist — these are related scheduler tables with organization_id.
OPTIONAL_TABLES = [
    "slot_holds",
    "appointment_status_history",
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

    The policy uses NULLIF(…, '') to handle the case where app.current_tenant
    is set to an empty string (rather than a missing GUC entirely).  When the
    GUC is missing, current_setting('app.current_tenant', true) returns NULL,
    and NULLIF(NULL, '') stays NULL, so the USING clause evaluates to FALSE and
    no rows are returned — correct behaviour for unauthenticated requests.
    """
    policy_name = f"{table_name}_tenant_isolation"

    if not _table_exists(conn, table_name):
        logger.info("[SKIP] %s — table does not exist", table_name)
        return

    if not _column_exists(conn, table_name, "organization_id"):
        logger.warning("[SKIP] %s — organization_id column missing; run add_scheduler_tenant_isolation first", table_name)
        return

    # Enable RLS (idempotent in PostgreSQL 9.5+)
    conn.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    logger.info("[RLS] ENABLE ROW LEVEL SECURITY on %s", table_name)

    # FORCE RLS ensures the policy applies even when the session role is the
    # table owner.  Railway PostgreSQL connects as the table owner, so without
    # FORCE, RLS would be silently bypassed for every request.
    conn.execute(text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    logger.info("[RLS] FORCE ROW LEVEL SECURITY on %s", table_name)

    # Drop any existing policy with this name (may have wrong variable name from
    # the previous add_scheduler_tenant_isolation run that used app.current_org_id)
    if _policy_exists(conn, table_name, policy_name):
        conn.execute(text(f"DROP POLICY {policy_name} ON {table_name}"))
        logger.info("[RLS] Dropped old policy %s on %s", policy_name, table_name)

    # Create strict tenant isolation policy.
    # USING: rows are visible only when organization_id matches current tenant.
    # WITH CHECK: inserts/updates must set organization_id to current tenant.
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
    logger.info("[RLS] Created strict tenant isolation policy on %s", table_name)


def _apply_public_bypass_policy(conn, table_name: str) -> None:
    """Enable RLS and create TWO policies for tables accessed by public booking.

    Policy 1 — tenant_isolation: same strict policy as STRICT_TABLES.
    Policy 2 — public_access: permits SELECT of is_public=TRUE rows when
                              app.current_tenant is unset (unauthenticated requests).

    PostgreSQL evaluates PERMISSIVE policies with OR logic: a row is visible if
    ANY permissive policy allows it.  So authenticated tenants see their rows
    via the tenant_isolation policy, and anonymous visitors see only public rows.

    Note: We do NOT apply WITH CHECK to the public_access policy because public
    booking should never INSERT through an unauthenticated session — that path
    uses app.current_tenant set by the booking confirmation handler (the
    booking creation endpoint sets tenant context from the derived link org_id).
    """
    tenant_policy = f"{table_name}_tenant_isolation"
    public_policy = f"{table_name}_public_access"

    if not _table_exists(conn, table_name):
        logger.info("[SKIP] %s — table does not exist", table_name)
        return

    if not _column_exists(conn, table_name, "organization_id"):
        logger.warning("[SKIP] %s — organization_id column missing", table_name)
        return

    # Check for is_public column — needed for the public bypass predicate
    has_is_public = _column_exists(conn, table_name, "is_public")
    has_is_active = _column_exists(conn, table_name, "is_active")

    conn.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    logger.info("[RLS] ENABLE ROW LEVEL SECURITY on %s", table_name)

    conn.execute(text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    logger.info("[RLS] FORCE ROW LEVEL SECURITY on %s", table_name)

    # --- Tenant isolation policy (same as strict tables) ---
    if _policy_exists(conn, table_name, tenant_policy):
        conn.execute(text(f"DROP POLICY {tenant_policy} ON {table_name}"))
        logger.info("[RLS] Dropped old policy %s on %s", tenant_policy, table_name)

    conn.execute(text(f"""
        CREATE POLICY {tenant_policy} ON {table_name}
        FOR ALL
        USING (
            organization_id::text = NULLIF(current_setting('app.current_tenant', true), '')
        )
        WITH CHECK (
            organization_id::text = NULLIF(current_setting('app.current_tenant', true), '')
        )
    """))
    logger.info("[RLS] Created tenant isolation policy on %s", table_name)

    # --- Public access bypass policy (SELECT-only for public rows) ---
    if _policy_exists(conn, table_name, public_policy):
        conn.execute(text(f"DROP POLICY {public_policy} ON {table_name}"))
        logger.info("[RLS] Dropped old public_access policy on %s", table_name)

    # Build USING predicate based on available columns.
    # The key condition: app.current_tenant is unset (NULL or '').
    # We only expose rows that are marked public (is_public=true) and active.
    unset_tenant = "NULLIF(current_setting('app.current_tenant', true), '') IS NULL"
    if has_is_public and has_is_active:
        public_predicate = f"({unset_tenant} AND is_public = true AND is_active = true)"
    elif has_is_public:
        public_predicate = f"({unset_tenant} AND is_public = true)"
    elif has_is_active:
        public_predicate = f"({unset_tenant} AND is_active = true)"
    else:
        # Fallback: allow SELECT from all rows when tenant is unset.
        # The endpoint layer still applies explicit organization_id filters in Python.
        public_predicate = f"({unset_tenant})"

    conn.execute(text(f"""
        CREATE POLICY {public_policy} ON {table_name}
        FOR SELECT
        USING ({public_predicate})
    """))
    logger.info("[RLS] Created public_access bypass policy on %s (predicate: %s)", table_name, public_predicate)


def run_migration(engine=None) -> None:
    """Enable RLS on all scheduler tables.

    Runs outside a transaction (AUTOCOMMIT) because ALTER TABLE … ENABLE ROW
    LEVEL SECURITY is DDL that cannot be issued inside an open transaction
    block on certain PostgreSQL configurations.
    """
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not engine.url.drivername.startswith("postgresql"):
        logger.info("[SKIP] enable_scheduler_rls — not a PostgreSQL database")
        return

    logger.info("Starting enable_scheduler_rls migration...")

    # Use AUTOCOMMIT so each DDL statement is its own implicit transaction.
    # This avoids "cannot run inside a transaction block" errors for DDL.
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        # --- Strict tables (authenticated requests only) ---
        for table in STRICT_TABLES:
            try:
                _apply_strict_policy(conn, table)
            except Exception as e:
                err = str(e).lower()
                if "already exists" in err:
                    logger.info("[SKIP] Policy already exists on %s (race condition)", table)
                else:
                    logger.warning("[WARN] Could not enable RLS on %s: %s", table, e)

        # --- Public-bypass tables (booking links + appointment types) ---
        for table in PUBLIC_BYPASS_TABLES:
            try:
                _apply_public_bypass_policy(conn, table)
            except Exception as e:
                err = str(e).lower()
                if "already exists" in err:
                    logger.info("[SKIP] Policy already exists on %s (race condition)", table)
                else:
                    logger.warning("[WARN] Could not enable RLS on %s: %s", table, e)

        # --- Optional related tables ---
        for table in OPTIONAL_TABLES:
            try:
                _apply_strict_policy(conn, table)
            except Exception as e:
                err = str(e).lower()
                if "does not exist" in err or "already exists" in err:
                    logger.info("[SKIP] %s — %s", table, e)
                else:
                    logger.warning("[WARN] Could not enable RLS on %s: %s", table, e)

    logger.info("enable_scheduler_rls migration complete")
    _log_summary()


def _log_summary() -> None:
    logger.info(
        "RLS summary:\n"
        "  Strict policy (authenticated only): %s\n"
        "  Public-bypass policy (+ SELECT for is_public rows when unauthed): %s\n"
        "  Optional (applied if tables exist): %s",
        ", ".join(STRICT_TABLES),
        ", ".join(PUBLIC_BYPASS_TABLES),
        ", ".join(OPTIONAL_TABLES),
    )


def rollback(engine=None) -> None:
    """Remove all RLS policies and disable RLS on scheduler tables."""
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    if not engine.url.drivername.startswith("postgresql"):
        logger.info("[SKIP] rollback — not PostgreSQL")
        return

    logger.info("Rolling back enable_scheduler_rls...")

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        all_tables = ALL_TABLES + OPTIONAL_TABLES
        for table_name in all_tables:
            try:
                if not _table_exists(conn, table_name):
                    continue

                # Drop all policies created by this migration
                for policy_suffix in ("tenant_isolation", "public_access"):
                    policy_name = f"{table_name}_{policy_suffix}"
                    if _policy_exists(conn, table_name, policy_name):
                        conn.execute(text(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}"))
                        logger.info("[ROLLBACK] Dropped policy %s", policy_name)

                # Disable FORCE and RLS
                conn.execute(text(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY"))
                conn.execute(text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))
                logger.info("[ROLLBACK] Disabled RLS on %s", table_name)
            except Exception as e:
                logger.warning("[ROLLBACK] Could not disable RLS on %s: %s", table_name, e)

    logger.info("enable_scheduler_rls rollback complete")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback()
    else:
        run_migration()
    sys.exit(0)
