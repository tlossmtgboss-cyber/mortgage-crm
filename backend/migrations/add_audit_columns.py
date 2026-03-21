"""
Migration: Add extended columns to ai_audit_log table.

Adds request_id, tools_used, actions_taken, processing_time_ms,
data_quality, and errors columns for the enhanced audit trail.

Run: python migrations/add_audit_columns.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set, skipping migration")
        return

    engine = create_engine(database_url)

    columns = [
        ("request_id", "VARCHAR(64)"),
        ("tools_used", "TEXT"),  # JSON array of tool names
        ("actions_taken", "TEXT"),  # JSON array of actions
        ("processing_time_ms", "FLOAT"),
        ("data_quality", "VARCHAR(32)"),
        ("errors", "TEXT"),  # JSON array of error strings
    ]

    with engine.connect() as conn:
        for col_name, col_type in columns:
            try:
                conn.execute(text(
                    f"ALTER TABLE ai_audit_log ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                print(f"  Added column: {col_name} ({col_type})")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"  Column {col_name} already exists")
                else:
                    print(f"  Error adding {col_name}: {e}")

        # Add index on request_id for correlation lookups
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_audit_request_id ON ai_audit_log (request_id)"
            ))
            print("  Created index: idx_audit_request_id")
        except Exception as e:
            print(f"  Index error: {e}")

        conn.commit()

    print("Migration complete.")


if __name__ == "__main__":
    run_migration()
