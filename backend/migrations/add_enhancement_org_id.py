"""
Migration: Add organization_id to 9 scheduler enhancement tables + crm_calendar_events.

These tables were created without organization_id, creating a tenant isolation gap.

This migration:
1. Adds organization_id column (nullable initially) to each table
2. Creates indexes on organization_id
3. Backfills from user FK chain or appointment FK chain
4. Falls back to first organization for orphaned rows
5. Sets NOT NULL after backfill

Tables affected:
  - scheduler_resources (user_id → users.organization_id)
  - scheduler_soft_holds (resource_id → scheduler_resources.user_id → users.organization_id)
  - scheduler_reminder_profiles (appointment_type_id → appointment_types.organization_id)
  - scheduler_analytics (resource_id → scheduler_resources.user_id → users.organization_id)
  - scheduler_campaign_bookings (appointment_id → scheduler_appointments.organization_id)
  - scheduler_group_sessions (host_resource_id → scheduler_resources.user_id → users.organization_id)
  - scheduler_series (lead_id → leads.organization_id)
  - scheduler_calendar_sync (user_id → users.organization_id)
  - scheduler_intake_questions (appointment_type_id → appointment_types.organization_id)
  - crm_calendar_events (owner_user_id → users.organization_id)
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# (table_name, backfill_strategy, fk_column)
# Strategies:
#   "direct_user" - table has user_id column, join to users.organization_id
#   "via_resource" - table has resource_id, join through scheduler_resources → users
#   "via_appointment_type" - join through appointment_types.organization_id
#   "via_appointment" - join through scheduler_appointments.organization_id
#   "via_host_resource" - join through scheduler_resources via host_resource_id
#   "via_lead" - join through leads.organization_id
#   "via_owner_user" - join through users via owner_user_id

TABLES = [
    ("scheduler_resources", "direct_user", "user_id"),
    ("scheduler_soft_holds", "via_resource", "resource_id"),
    ("scheduler_reminder_profiles", "via_appointment_type", "appointment_type_id"),
    ("scheduler_analytics", "via_resource", "resource_id"),
    ("scheduler_campaign_bookings", "via_appointment", "appointment_id"),
    ("scheduler_group_sessions", "via_host_resource", "host_resource_id"),
    ("scheduler_series", "via_lead", "lead_id"),
    ("scheduler_calendar_sync", "direct_user", "user_id"),
    ("scheduler_intake_questions", "via_appointment_type", "appointment_type_id"),
    ("crm_calendar_events", "via_owner_user", "owner_user_id"),
]

BACKFILL_SQL = {
    "direct_user": """
        UPDATE {table} t
        SET organization_id = u.organization_id
        FROM users u
        WHERE t.{fk_col} = u.id
          AND t.organization_id IS NULL
          AND u.organization_id IS NOT NULL
    """,
    "via_resource": """
        UPDATE {table} t
        SET organization_id = u.organization_id
        FROM scheduler_resources sr
        JOIN users u ON u.id = sr.user_id
        WHERE t.{fk_col} = sr.id
          AND t.organization_id IS NULL
          AND u.organization_id IS NOT NULL
    """,
    "via_appointment_type": """
        UPDATE {table} t
        SET organization_id = at.organization_id
        FROM appointment_types at
        WHERE t.{fk_col} = at.id
          AND t.organization_id IS NULL
          AND at.organization_id IS NOT NULL
    """,
    "via_appointment": """
        UPDATE {table} t
        SET organization_id = sa.organization_id
        FROM scheduler_appointments sa
        WHERE t.{fk_col} = sa.id
          AND t.organization_id IS NULL
          AND sa.organization_id IS NOT NULL
    """,
    "via_host_resource": """
        UPDATE {table} t
        SET organization_id = u.organization_id
        FROM scheduler_resources sr
        JOIN users u ON u.id = sr.user_id
        WHERE t.{fk_col} = sr.id
          AND t.organization_id IS NULL
          AND u.organization_id IS NOT NULL
    """,
    "via_lead": """
        UPDATE {table} t
        SET organization_id = l.organization_id
        FROM leads l
        WHERE t.{fk_col} = l.id
          AND t.organization_id IS NULL
          AND l.organization_id IS NOT NULL
    """,
    "via_owner_user": """
        UPDATE {table} t
        SET organization_id = u.organization_id
        FROM users u
        WHERE t.{fk_col} = u.id
          AND t.organization_id IS NULL
          AND u.organization_id IS NOT NULL
    """,
}


def run_migration(engine):
    """Add organization_id to enhancement tables and backfill."""
    with engine.begin() as conn:
        migrated_counts = {}

        for table, strategy, fk_col in TABLES:
            # Check if the table exists
            result = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table)"
            ), {"table": table})
            if not result.scalar():
                logger.info(f"Table {table} does not exist, skipping")
                continue

            # Check if organization_id column already exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = :table AND column_name = 'organization_id'
                )
            """), {"table": table})
            col_exists = result.scalar()

            if not col_exists:
                # Add nullable column first
                logger.info(f"Adding organization_id column to {table}")
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN organization_id INTEGER"
                ))

            # Create index if not exists
            idx_name = f"ix_{table}_org_id"
            result = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :idx)"
            ), {"idx": idx_name})
            if not result.scalar():
                logger.info(f"Creating index {idx_name}")
                conn.execute(text(
                    f"CREATE INDEX {idx_name} ON {table} (organization_id)"
                ))

            # Count NULL rows
            null_count = conn.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE organization_id IS NULL"
            )).scalar()

            if null_count > 0:
                logger.info(f"{table}: {null_count} rows with NULL organization_id")

                # Strategy-specific backfill
                backfill_sql = BACKFILL_SQL[strategy].format(table=table, fk_col=fk_col)
                result = conn.execute(text(backfill_sql))
                updated = result.rowcount
                logger.info(f"{table}: backfilled {updated} rows via {strategy}")

                # Remaining NULLs: assign to first organization
                remaining = conn.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE organization_id IS NULL"
                )).scalar()

                if remaining > 0:
                    first_org = conn.execute(text(
                        "SELECT id FROM organizations ORDER BY id LIMIT 1"
                    )).scalar()

                    if first_org:
                        result = conn.execute(text(
                            f"UPDATE {table} SET organization_id = :org_id WHERE organization_id IS NULL"
                        ), {"org_id": first_org})
                        logger.info(f"{table}: assigned {result.rowcount} orphaned rows to org {first_org}")
                    else:
                        # Delete orphaned rows if no organization exists
                        result = conn.execute(text(
                            f"DELETE FROM {table} WHERE organization_id IS NULL"
                        ))
                        logger.warning(f"{table}: deleted {result.rowcount} orphaned rows (no organizations exist)")

            # Now set NOT NULL
            # Check if already NOT NULL
            result = conn.execute(text("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = :table AND column_name = 'organization_id'
            """), {"table": table})
            row = result.fetchone()
            if row and row[0] == 'YES':
                logger.info(f"{table}: setting organization_id to NOT NULL")
                conn.execute(text(
                    f"ALTER TABLE {table} ALTER COLUMN organization_id SET NOT NULL"
                ))

            migrated_counts[table] = null_count

        logger.info(f"Enhancement org_id migration complete: {migrated_counts}")
        return migrated_counts


if __name__ == "__main__":
    import os
    from sqlalchemy import create_engine
    logging.basicConfig(level=logging.INFO)
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
    engine = create_engine(database_url)
    run_migration(engine)
