"""
Scheduler Tenant Isolation Migration

Adds organization_id to all 8 smart scheduler tables for multi-tenant isolation.
Steps:
1. Add organization_id columns (nullable for backward compat)
2. Create indexes for tenant-scoped queries
3. Backfill org_id from user relationships
4. Convert global unique constraints to per-org composite
5. Enable RLS policies

Idempotent — safe to run multiple times.
"""

import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)

# All scheduler tables (including audit log and webhook events)
SCHEDULER_TABLES = [
    "scheduler_configs",
    "availability_slots",
    "appointment_types",
    "scheduler_appointments",
    "scheduler_routing_rules",
    "scheduler_blocked_times",
    "scheduler_booking_links",
    "scheduler_reminders",
    "scheduler_audit_log",
    "scheduler_webhook_events",
]


def _table_exists(engine, table_name: str) -> bool:
    insp = inspect(engine)
    return table_name in insp.get_table_names()


def _column_exists(engine, table_name: str, column_name: str) -> bool:
    insp = inspect(engine)
    if table_name not in insp.get_table_names():
        return False
    cols = {c["name"] for c in insp.get_columns(table_name)}
    return column_name in cols


def _index_exists(conn, index_name: str) -> bool:
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {"name": index_name})
    return result.fetchone() is not None


def _constraint_exists(conn, constraint_name: str) -> bool:
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = :name"
    ), {"name": constraint_name})
    return result.fetchone() is not None


def run_migration(engine=None):
    """Run the scheduler tenant isolation migration."""
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    logger.info("Starting scheduler tenant isolation migration...")

    with engine.begin() as conn:
        # =====================================================================
        # Step 1: Add organization_id column to all tables
        # =====================================================================
        for table_name in SCHEDULER_TABLES:
            if not _table_exists(engine, table_name):
                logger.info(f"Table {table_name} does not exist, skipping")
                continue

            if not _column_exists(engine, table_name, "organization_id"):
                logger.info(f"Adding organization_id to {table_name}")
                conn.execute(text(f"""
                    ALTER TABLE {table_name}
                    ADD COLUMN organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE
                """))
            else:
                logger.info(f"organization_id already exists on {table_name}")

        # =====================================================================
        # Step 2: Create indexes
        # =====================================================================
        index_specs = [
            ("ix_scheduler_configs_org_id", "scheduler_configs", "organization_id"),
            ("ix_availability_slots_org_id", "availability_slots", "organization_id"),
            ("ix_appointment_types_org_id", "appointment_types", "organization_id"),
            ("ix_appointment_org_id", "scheduler_appointments", "organization_id"),
            ("ix_routing_rules_org_id", "scheduler_routing_rules", "organization_id"),
            ("ix_blocked_times_org_id", "scheduler_blocked_times", "organization_id"),
            ("ix_booking_links_org_id", "scheduler_booking_links", "organization_id"),
            ("ix_reminders_org_id", "scheduler_reminders", "organization_id"),
        ]

        for idx_name, table_name, col_name in index_specs:
            if not _table_exists(engine, table_name):
                continue
            if not _index_exists(conn, idx_name):
                logger.info(f"Creating index {idx_name}")
                conn.execute(text(f"CREATE INDEX {idx_name} ON {table_name}({col_name})"))

        # Composite index for appointment lookups
        if _table_exists(engine, "scheduler_appointments"):
            if not _index_exists(conn, "ix_appointment_org_user_start"):
                conn.execute(text(
                    "CREATE INDEX ix_appointment_org_user_start "
                    "ON scheduler_appointments(organization_id, assigned_user_id, scheduled_start)"
                ))

        # =====================================================================
        # Step 3: Convert global UNIQUE constraints to per-org composite
        # =====================================================================

        # BookingLink.slug: drop global unique, add (org_id, slug) unique
        if _table_exists(engine, "scheduler_booking_links"):
            # Find and drop any existing unique constraint on slug alone
            slug_constraints = conn.execute(text("""
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                WHERE rel.relname = 'scheduler_booking_links'
                  AND con.contype = 'u'
                  AND array_length(con.conkey, 1) = 1
                  AND EXISTS (
                    SELECT 1 FROM pg_attribute att
                    WHERE att.attrelid = rel.oid
                      AND att.attnum = ANY(con.conkey)
                      AND att.attname = 'slug'
                  )
            """)).fetchall()

            for row in slug_constraints:
                logger.info(f"Dropping global unique constraint {row[0]} on scheduler_booking_links.slug")
                conn.execute(text(f"ALTER TABLE scheduler_booking_links DROP CONSTRAINT {row[0]}"))

            # Also drop unique index on slug if it exists
            slug_indexes = conn.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'scheduler_booking_links'
                  AND indexdef LIKE '%UNIQUE%'
                  AND indexdef LIKE '%slug%'
                  AND indexdef NOT LIKE '%organization_id%'
            """)).fetchall()

            for row in slug_indexes:
                logger.info(f"Dropping global unique index {row[0]} on scheduler_booking_links.slug")
                conn.execute(text(f"DROP INDEX IF EXISTS {row[0]}"))

            # Add per-org unique constraint
            if not _constraint_exists(conn, "uq_booking_link_org_slug"):
                logger.info("Creating per-org unique constraint on scheduler_booking_links(organization_id, slug)")
                conn.execute(text(
                    "ALTER TABLE scheduler_booking_links "
                    "ADD CONSTRAINT uq_booking_link_org_slug UNIQUE(organization_id, slug)"
                ))

        # AppointmentType.public_slug: drop global unique, add (org_id, public_slug) unique
        if _table_exists(engine, "appointment_types"):
            slug_constraints = conn.execute(text("""
                SELECT con.conname
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                WHERE rel.relname = 'appointment_types'
                  AND con.contype = 'u'
                  AND array_length(con.conkey, 1) = 1
                  AND EXISTS (
                    SELECT 1 FROM pg_attribute att
                    WHERE att.attrelid = rel.oid
                      AND att.attnum = ANY(con.conkey)
                      AND att.attname = 'public_slug'
                  )
            """)).fetchall()

            for row in slug_constraints:
                logger.info(f"Dropping global unique constraint {row[0]} on appointment_types.public_slug")
                conn.execute(text(f"ALTER TABLE appointment_types DROP CONSTRAINT {row[0]}"))

            slug_indexes = conn.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'appointment_types'
                  AND indexdef LIKE '%UNIQUE%'
                  AND indexdef LIKE '%public_slug%'
                  AND indexdef NOT LIKE '%organization_id%'
            """)).fetchall()

            for row in slug_indexes:
                logger.info(f"Dropping global unique index {row[0]} on appointment_types.public_slug")
                conn.execute(text(f"DROP INDEX IF EXISTS {row[0]}"))

            if not _constraint_exists(conn, "uq_appointment_type_org_slug"):
                logger.info("Creating per-org unique constraint on appointment_types(organization_id, public_slug)")
                conn.execute(text(
                    "ALTER TABLE appointment_types "
                    "ADD CONSTRAINT uq_appointment_type_org_slug UNIQUE(organization_id, public_slug)"
                ))

        # =====================================================================
        # Step 4: Backfill organization_id from user relationships
        # =====================================================================

        # scheduler_configs: from users.organization_id via user_id
        if _table_exists(engine, "scheduler_configs"):
            updated = conn.execute(text("""
                UPDATE scheduler_configs sc
                SET organization_id = u.organization_id
                FROM users u
                WHERE sc.user_id = u.id
                  AND sc.organization_id IS NULL
                  AND u.organization_id IS NOT NULL
            """))
            logger.info(f"Backfilled {updated.rowcount} scheduler_configs rows")

        # availability_slots: from scheduler_configs.organization_id via config_id
        if _table_exists(engine, "availability_slots"):
            updated = conn.execute(text("""
                UPDATE availability_slots a
                SET organization_id = sc.organization_id
                FROM scheduler_configs sc
                WHERE a.config_id = sc.id
                  AND a.organization_id IS NULL
                  AND sc.organization_id IS NOT NULL
            """))
            logger.info(f"Backfilled {updated.rowcount} availability_slots rows")

        # appointment_types: from scheduler_configs.organization_id via config_id
        if _table_exists(engine, "appointment_types"):
            updated = conn.execute(text("""
                UPDATE appointment_types at
                SET organization_id = sc.organization_id
                FROM scheduler_configs sc
                WHERE at.config_id = sc.id
                  AND at.organization_id IS NULL
                  AND sc.organization_id IS NOT NULL
            """))
            logger.info(f"Backfilled {updated.rowcount} appointment_types rows")

        # scheduler_appointments: from users.organization_id via assigned_user_id
        if _table_exists(engine, "scheduler_appointments"):
            updated = conn.execute(text("""
                UPDATE scheduler_appointments sa
                SET organization_id = u.organization_id
                FROM users u
                WHERE sa.assigned_user_id = u.id
                  AND sa.organization_id IS NULL
                  AND u.organization_id IS NOT NULL
            """))
            logger.info(f"Backfilled {updated.rowcount} scheduler_appointments rows")

        # scheduler_blocked_times: from users.organization_id via user_id
        if _table_exists(engine, "scheduler_blocked_times"):
            updated = conn.execute(text("""
                UPDATE scheduler_blocked_times bt
                SET organization_id = u.organization_id
                FROM users u
                WHERE bt.user_id = u.id
                  AND bt.organization_id IS NULL
                  AND u.organization_id IS NOT NULL
            """))
            logger.info(f"Backfilled {updated.rowcount} scheduler_blocked_times rows")

        # scheduler_booking_links: from users.organization_id via user_id
        if _table_exists(engine, "scheduler_booking_links"):
            updated = conn.execute(text("""
                UPDATE scheduler_booking_links bl
                SET organization_id = u.organization_id
                FROM users u
                WHERE bl.user_id = u.id
                  AND bl.organization_id IS NULL
                  AND u.organization_id IS NOT NULL
            """))
            logger.info(f"Backfilled {updated.rowcount} scheduler_booking_links rows")

        # scheduler_reminders: from scheduler_appointments.organization_id via appointment_id
        if _table_exists(engine, "scheduler_reminders"):
            updated = conn.execute(text("""
                UPDATE scheduler_reminders sr
                SET organization_id = sa.organization_id
                FROM scheduler_appointments sa
                WHERE sr.appointment_id = sa.id
                  AND sr.organization_id IS NULL
                  AND sa.organization_id IS NOT NULL
            """))
            logger.info(f"Backfilled {updated.rowcount} scheduler_reminders rows")

        # scheduler_routing_rules: from appointment_types.organization_id via appointment_type_id
        if _table_exists(engine, "scheduler_routing_rules"):
            updated = conn.execute(text("""
                UPDATE scheduler_routing_rules rr
                SET organization_id = at.organization_id
                FROM appointment_types at
                WHERE rr.appointment_type_id = at.id
                  AND rr.organization_id IS NULL
                  AND at.organization_id IS NOT NULL
            """))
            logger.info(f"Backfilled {updated.rowcount} scheduler_routing_rules rows")

        # =====================================================================
        # Step 5: Enable RLS policies (restrictive — no NULL org_id bypass)
        # =====================================================================
        for table_name in SCHEDULER_TABLES:
            if not _table_exists(engine, table_name):
                continue

            policy_name = f"{table_name}_tenant_isolation"

            # Drop old permissive policy if it exists, then create restrictive one
            existing = conn.execute(text(
                "SELECT 1 FROM pg_policies WHERE tablename = :table AND policyname = :policy"
            ), {"table": table_name, "policy": policy_name}).fetchone()

            if existing:
                try:
                    conn.execute(text(f"DROP POLICY {policy_name} ON {table_name}"))
                    logger.info(f"Dropped old RLS policy {policy_name}")
                except Exception as e:
                    logger.warning(f"Could not drop old RLS policy {policy_name}: {e}")

            try:
                conn.execute(text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
                # Restrictive policy: must match org_id, deny when session var unset
                conn.execute(text(f"""
                    CREATE POLICY {policy_name} ON {table_name}
                    FOR ALL
                    USING (
                        organization_id = current_setting('app.current_org_id', true)::integer
                    )
                    WITH CHECK (
                        organization_id = current_setting('app.current_org_id', true)::integer
                    )
                """))
                logger.info(f"Created RLS policy {policy_name} with WITH CHECK clause")
            except Exception as e:
                logger.warning(f"Could not create RLS policy for {table_name}: {e}")

        # =====================================================================
        # Step 6: Set organization_id NOT NULL after backfill
        # =====================================================================
        for table_name in SCHEDULER_TABLES:
            if not _table_exists(engine, table_name):
                continue
            if not _column_exists(engine, table_name, "organization_id"):
                continue

            # Check if any NULL rows remain
            null_count = conn.execute(text(
                f"SELECT COUNT(*) FROM {table_name} WHERE organization_id IS NULL"
            )).scalar()

            if null_count == 0:
                # Safe to set NOT NULL
                try:
                    # Check if already NOT NULL
                    is_nullable = conn.execute(text("""
                        SELECT is_nullable FROM information_schema.columns
                        WHERE table_name = :table AND column_name = 'organization_id'
                    """), {"table": table_name}).scalar()

                    if is_nullable == 'YES':
                        conn.execute(text(
                            f"ALTER TABLE {table_name} ALTER COLUMN organization_id SET NOT NULL"
                        ))
                        logger.info(f"Set organization_id NOT NULL on {table_name}")
                    else:
                        logger.info(f"organization_id already NOT NULL on {table_name}")
                except Exception as e:
                    logger.warning(f"Could not set NOT NULL on {table_name}: {e}")
            else:
                logger.warning(
                    f"Skipping NOT NULL on {table_name}: {null_count} rows still have NULL organization_id"
                )

        # =====================================================================
        # Step 7: Add double-booking exclusion constraint
        # =====================================================================
        if _table_exists(engine, "scheduler_appointments"):
            # Enable btree_gist extension (needed for exclusion constraints on integers)
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
                logger.info("btree_gist extension enabled")
            except Exception as e:
                logger.warning(f"Could not enable btree_gist: {e}")

            # Add exclusion constraint to prevent double-booking
            if not _constraint_exists(conn, "excl_no_double_booking"):
                try:
                    conn.execute(text("""
                        ALTER TABLE scheduler_appointments
                        ADD CONSTRAINT excl_no_double_booking
                        EXCLUDE USING gist (
                            assigned_user_id WITH =,
                            tsrange(scheduled_start, scheduled_end) WITH &&
                        )
                        WHERE (status NOT IN ('cancelled', 'rescheduled'))
                    """))
                    logger.info("Created double-booking exclusion constraint")
                except Exception as e:
                    logger.warning(f"Could not create exclusion constraint: {e}")

        # =====================================================================
        # Step 8: Create audit log and webhook event tables
        # =====================================================================
        if not _table_exists(engine, "scheduler_audit_log"):
            try:
                conn.execute(text("""
                    CREATE TABLE scheduler_audit_log (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                        user_id INTEGER REFERENCES users(id),
                        user_email VARCHAR(255),
                        ip_address VARCHAR(45),
                        action VARCHAR(50) NOT NULL,
                        entity_type VARCHAR(50) NOT NULL,
                        entity_id INTEGER NOT NULL,
                        changes JSONB,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                conn.execute(text("CREATE INDEX ix_audit_log_org_id ON scheduler_audit_log(organization_id)"))
                conn.execute(text("CREATE INDEX ix_audit_log_entity ON scheduler_audit_log(entity_type, entity_id)"))
                conn.execute(text("CREATE INDEX ix_audit_log_created ON scheduler_audit_log(created_at)"))
                logger.info("Created scheduler_audit_log table")
            except Exception as e:
                logger.warning(f"Could not create audit log table: {e}")

        if not _table_exists(engine, "scheduler_webhook_events"):
            try:
                conn.execute(text("""
                    CREATE TABLE scheduler_webhook_events (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                        event_type VARCHAR(50) NOT NULL,
                        entity_type VARCHAR(50) NOT NULL,
                        entity_id INTEGER NOT NULL,
                        payload JSONB NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        attempts INTEGER DEFAULT 0,
                        last_attempt_at TIMESTAMP,
                        delivered_at TIMESTAMP,
                        error TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                conn.execute(text("CREATE INDEX ix_webhook_events_org_id ON scheduler_webhook_events(organization_id)"))
                conn.execute(text("CREATE INDEX ix_webhook_events_status ON scheduler_webhook_events(status)"))
                logger.info("Created scheduler_webhook_events table")
            except Exception as e:
                logger.warning(f"Could not create webhook events table: {e}")

        # =====================================================================
        # Step 9: Add ICS tracking columns to scheduler_appointments
        # =====================================================================
        if _table_exists(engine, "scheduler_appointments"):
            for col_name, col_def in [
                ("ics_sequence", "INTEGER DEFAULT 0"),
                ("ics_uid", "VARCHAR(255)"),
                ("created_by_ip", "VARCHAR(45)"),
                ("last_modified_by_id", "INTEGER REFERENCES users(id)"),
                ("consent_given_at", "TIMESTAMP"),
                ("consent_ip", "VARCHAR(45)"),
                ("consent_text_version", "VARCHAR(20)"),
            ]:
                if not _column_exists(engine, "scheduler_appointments", col_name):
                    try:
                        conn.execute(text(
                            f"ALTER TABLE scheduler_appointments ADD COLUMN {col_name} {col_def}"
                        ))
                        logger.info(f"Added {col_name} to scheduler_appointments")
                    except Exception as e:
                        logger.warning(f"Could not add {col_name}: {e}")

        # Add indexes on frequently-queried columns
        if _table_exists(engine, "scheduler_appointments"):
            for idx_name, idx_def in [
                ("ix_appointment_attendee_email", "scheduler_appointments(attendee_email)"),
                ("ix_appointment_lead_id", "scheduler_appointments(lead_id)"),
                ("ix_appointment_loan_id", "scheduler_appointments(loan_id)"),
            ]:
                if not _index_exists(conn, idx_name):
                    try:
                        conn.execute(text(f"CREATE INDEX {idx_name} ON {idx_def}"))
                        logger.info(f"Created index {idx_name}")
                    except Exception as e:
                        logger.warning(f"Could not create index {idx_name}: {e}")

    logger.info("Scheduler tenant isolation migration complete")


if __name__ == "__main__":
    run_migration()
