"""
Migration: Add organization_id to calendly_integrations and calendly_bookings tables.

Follows same pattern as enforce_scheduler_org_id_not_null.py:
1. ADD COLUMN IF NOT EXISTS (nullable initially)
2. CREATE INDEX
3. Backfill from users table via user_id FK
4. DELETE orphans with no org
5. SET NOT NULL

Run: python migrations/add_calendly_org_id.py
"""

import os
import sys
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

TABLES = [
    {
        "table": "calendly_integrations",
        "backfill_sql": """
            UPDATE calendly_integrations ci
            SET organization_id = u.organization_id
            FROM users u
            WHERE ci.user_id = u.id
              AND ci.organization_id IS NULL
              AND u.organization_id IS NOT NULL
        """,
    },
    {
        "table": "calendly_bookings",
        "backfill_sql": """
            UPDATE calendly_bookings cb
            SET organization_id = u.organization_id
            FROM users u
            WHERE cb.user_id = u.id
              AND cb.organization_id IS NULL
              AND u.organization_id IS NOT NULL
        """,
    },
]


def run_migration():
    with engine.begin() as conn:
        for spec in TABLES:
            table = spec["table"]

            # Check if table exists
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
            ), {"t": table}).first()
            if not exists:
                print(f"  SKIP {table} — table does not exist")
                continue

            # 1. Add column if not exists
            col_exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'organization_id'"
            ), {"t": table}).first()

            if not col_exists:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN organization_id INTEGER"
                ))
                print(f"  ADD COLUMN {table}.organization_id")
            else:
                print(f"  EXISTS {table}.organization_id")

            # 2. Create index
            idx_name = f"ix_{table}_org_id"
            idx_exists = conn.execute(text(
                "SELECT 1 FROM pg_indexes WHERE indexname = :idx"
            ), {"idx": idx_name}).first()
            if not idx_exists:
                conn.execute(text(
                    f"CREATE INDEX {idx_name} ON {table} (organization_id)"
                ))
                print(f"  CREATE INDEX {idx_name}")

            # 3. Backfill
            result = conn.execute(text(spec["backfill_sql"]))
            print(f"  BACKFILL {table}: {result.rowcount} rows updated")

            # 4. Delete orphans with NULL org_id
            orphan_result = conn.execute(text(
                f"DELETE FROM {table} WHERE organization_id IS NULL"
            ))
            if orphan_result.rowcount > 0:
                print(f"  DELETE {table}: {orphan_result.rowcount} orphan rows")

            # 5. Set NOT NULL
            conn.execute(text(
                f"ALTER TABLE {table} ALTER COLUMN organization_id SET NOT NULL"
            ))
            print(f"  SET NOT NULL {table}.organization_id")

    print("\nMigration complete: calendly_integrations + calendly_bookings")


if __name__ == "__main__":
    run_migration()
