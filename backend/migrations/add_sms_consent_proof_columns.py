"""
Migration: Add TCPA consent proof columns to SMS tracking tables.

Adds consent_record_id, consent_verified_at, and consent_method to:
  - sms_messages (SQLAlchemy model-backed table)
  - sms_delivery_log (raw SQL delivery tracker)
  - sms_queue (raw SQL retry queue)

These columns link each outbound SMS to the sms_consent record that
authorized the send, providing the audit trail required by TCPA.

Safe to re-run: uses ADD COLUMN IF NOT EXISTS (PostgreSQL) or checks
column existence before adding (SQLite).
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Tables that need consent proof columns
TABLES = ["sms_messages", "sms_delivery_log", "sms_queue", "sms_compliance_log"]

# Columns to add (name, postgres_type, sqlite_type)
COLUMNS = [
    ("consent_record_id", "INTEGER", "INTEGER"),
    ("consent_verified_at", "TIMESTAMP WITH TIME ZONE", "TIMESTAMP"),
    ("consent_method", "VARCHAR(50)", "VARCHAR(50)"),
]


def run_migration():
    """Add consent proof columns to SMS tracking tables."""
    engine = create_engine(DATABASE_URL)
    is_postgres = "postgresql" in DATABASE_URL.lower()

    with engine.connect() as conn:
        for table in TABLES:
            # Check if table exists before altering
            if is_postgres:
                exists = conn.execute(
                    text("""
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = :table
                    """),
                    {"table": table},
                ).fetchone()
            else:
                exists = conn.execute(
                    text("""
                        SELECT 1 FROM sqlite_master
                        WHERE type='table' AND name = :table
                    """),
                    {"table": table},
                ).fetchone()

            if not exists:
                print(f"  [SKIP] {table} — table does not exist yet")
                continue

            for col_name, pg_type, sqlite_type in COLUMNS:
                col_type = pg_type if is_postgres else sqlite_type
                try:
                    if is_postgres:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                            f"{col_name} {col_type}"
                        ))
                    else:
                        # SQLite: check if column exists first
                        cols = conn.execute(
                            text(f"PRAGMA table_info({table})")
                        ).fetchall()
                        col_names = [c[1] for c in cols]
                        if col_name not in col_names:
                            conn.execute(text(
                                f"ALTER TABLE {table} ADD COLUMN "
                                f"{col_name} {col_type}"
                            ))
                    print(f"  [OK] {table}.{col_name}")
                except Exception as e:
                    print(f"  [WARN] {table}.{col_name} — {e}")

            # Add index on consent_record_id for audit queries
            idx_name = f"ix_{table}_consent_record_id"
            try:
                if is_postgres:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {idx_name} "
                        f"ON {table}(consent_record_id) "
                        f"WHERE consent_record_id IS NOT NULL"
                    ))
                else:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {idx_name} "
                        f"ON {table}(consent_record_id)"
                    ))
                print(f"  [OK] {idx_name}")
            except Exception as e:
                print(f"  [WARN] {idx_name} — {e}")

        conn.commit()
        print("\nSuccessfully added SMS consent proof columns.")


def rollback_migration():
    """Remove consent proof columns from SMS tracking tables."""
    engine = create_engine(DATABASE_URL)
    is_postgres = "postgresql" in DATABASE_URL.lower()

    if not is_postgres:
        print("SQLite does not support DROP COLUMN. Skipping rollback.")
        return

    with engine.connect() as conn:
        for table in TABLES:
            for col_name, _, _ in COLUMNS:
                try:
                    conn.execute(text(
                        f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col_name}"
                    ))
                    print(f"  [OK] Dropped {table}.{col_name}")
                except Exception as e:
                    print(f"  [WARN] {table}.{col_name} — {e}")

            # Drop index
            idx_name = f"ix_{table}_consent_record_id"
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
                print(f"  [OK] Dropped {idx_name}")
            except Exception as e:
                print(f"  [WARN] {idx_name} — {e}")

        conn.commit()
        print("\nSuccessfully rolled back SMS consent proof columns.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Add TCPA consent proof columns to SMS tracking tables"
    )
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    else:
        run_migration()
