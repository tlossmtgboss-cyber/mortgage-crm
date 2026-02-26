"""
Add production_assistant column to leads and loans tables.

Usage:
    python migrations/add_production_assistant_column.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text


def run_migration():
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        # Add production_assistant to leads
        conn.execute(text("""
            ALTER TABLE leads
            ADD COLUMN IF NOT EXISTS production_assistant VARCHAR;
        """))
        print("Added production_assistant column to leads table")

        # Add production_assistant to loans
        conn.execute(text("""
            ALTER TABLE loans
            ADD COLUMN IF NOT EXISTS production_assistant VARCHAR;
        """))
        print("Added production_assistant column to loans table")

    print("Migration complete.")


if __name__ == "__main__":
    run_migration()
