"""
Migration: Enforce NOT NULL on organization_id for all scheduler tables.

All 8 scheduler models had organization_id as nullable=True, creating a tenant
isolation gap where NULL != NULL in SQL allows records to escape org-scoped queries.

This migration:
1. Backfills any NULL organization_id rows using the user's organization_id
2. Deletes orphaned rows that can't be backfilled
3. Alters each column to NOT NULL

Tables affected:
  - scheduler_configs
  - availability_slots
  - appointment_types
  - scheduler_appointments
  - routing_rules
  - blocked_times
  - booking_links
  - appointment_reminders
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

TABLES_WITH_USER_FK = [
    ("scheduler_configs", "user_id"),
    ("availability_slots", "config_id"),  # Join through config
    ("appointment_types", "config_id"),   # Join through config
    ("scheduler_appointments", "assigned_user_id"),
    ("routing_rules", None),              # No direct user FK
    ("blocked_times", "user_id"),
    ("booking_links", "user_id"),
    ("appointment_reminders", "appointment_id"),  # Join through appointment
]


def run_migration(engine):
    """Run the NOT NULL migration on scheduler organization_id columns."""
    with engine.begin() as conn:
        migrated_counts = {}

        for table, user_col in TABLES_WITH_USER_FK:
            # Check if the table exists
            result = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :table)"
            ), {"table": table})
            if not result.scalar():
                logger.info(f"Table {table} does not exist, skipping")
                continue

            # Check if organization_id column exists
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = :table AND column_name = 'organization_id'
                )
            """), {"table": table})
            if not result.scalar():
                logger.info(f"Table {table} has no organization_id column, skipping")
                continue

            # Count NULL rows before migration
            null_count = conn.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE organization_id IS NULL"
            )).scalar()

            if null_count > 0:
                logger.info(f"{table}: {null_count} rows with NULL organization_id")

                # Strategy 1: Backfill from user's organization_id (direct user FK)
                if user_col and user_col == "user_id":
                    updated = conn.execute(text(f"""
                        UPDATE {table} t
                        SET organization_id = u.organization_id
                        FROM users u
                        WHERE t.{user_col} = u.id
                          AND t.organization_id IS NULL
                          AND u.organization_id IS NOT NULL
                    """)).rowcount
                    logger.info(f"  Backfilled {updated} rows via {user_col} -> users.organization_id")

                elif user_col == "assigned_user_id":
                    updated = conn.execute(text(f"""
                        UPDATE {table} t
                        SET organization_id = u.organization_id
                        FROM users u
                        WHERE t.assigned_user_id = u.id
                          AND t.organization_id IS NULL
                          AND u.organization_id IS NOT NULL
                    """)).rowcount
                    logger.info(f"  Backfilled {updated} rows via assigned_user_id -> users.organization_id")

                elif user_col == "config_id":
                    # Join through scheduler_configs to get org_id
                    updated = conn.execute(text(f"""
                        UPDATE {table} t
                        SET organization_id = sc.organization_id
                        FROM scheduler_configs sc
                        WHERE t.config_id = sc.id
                          AND t.organization_id IS NULL
                          AND sc.organization_id IS NOT NULL
                    """)).rowcount
                    logger.info(f"  Backfilled {updated} rows via config_id -> scheduler_configs.organization_id")

                elif user_col == "appointment_id":
                    # Join through scheduler_appointments to get org_id
                    updated = conn.execute(text(f"""
                        UPDATE {table} t
                        SET organization_id = sa.organization_id
                        FROM scheduler_appointments sa
                        WHERE t.appointment_id = sa.id
                          AND t.organization_id IS NULL
                          AND sa.organization_id IS NOT NULL
                    """)).rowcount
                    logger.info(f"  Backfilled {updated} rows via appointment_id -> scheduler_appointments.organization_id")

                # Strategy 2: For any remaining NULLs, use the first org (single-tenant fallback)
                remaining = conn.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE organization_id IS NULL"
                )).scalar()

                if remaining > 0:
                    # Try to find the default org
                    default_org = conn.execute(text(
                        "SELECT id FROM organizations ORDER BY id LIMIT 1"
                    )).scalar()

                    if default_org:
                        updated = conn.execute(text(f"""
                            UPDATE {table}
                            SET organization_id = :org_id
                            WHERE organization_id IS NULL
                        """), {"org_id": default_org}).rowcount
                        logger.info(f"  Backfilled {updated} remaining rows with default org_id={default_org}")
                    else:
                        # No orgs exist — delete orphaned rows
                        deleted = conn.execute(text(f"""
                            DELETE FROM {table} WHERE organization_id IS NULL
                        """)).rowcount
                        logger.warning(f"  Deleted {deleted} orphaned rows (no organization to assign)")

            # Now set NOT NULL constraint
            # Check if already NOT NULL
            is_nullable = conn.execute(text("""
                SELECT is_nullable FROM information_schema.columns
                WHERE table_name = :table AND column_name = 'organization_id'
            """), {"table": table}).scalar()

            if is_nullable == 'YES':
                conn.execute(text(f"""
                    ALTER TABLE {table}
                    ALTER COLUMN organization_id SET NOT NULL
                """))
                logger.info(f"  SET NOT NULL on {table}.organization_id")
                migrated_counts[table] = null_count
            else:
                logger.info(f"  {table}.organization_id already NOT NULL")

        logger.info(f"Migration complete. Tables modified: {list(migrated_counts.keys())}")
        return migrated_counts


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from sqlalchemy import create_engine
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    engine = create_engine(database_url)
    result = run_migration(engine)
    print(f"\nMigration results: {result}")
