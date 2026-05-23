"""Create briefing_threads, briefing_tasks, and briefing_audit_log tables.
Run: python migrations/create_briefing_thread_tables.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect

from db import Base
from database.models.briefing_thread import BriefingThread, BriefingTask, BriefingAuditLog


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    existing = inspector.get_table_names()

    for table in [
        BriefingThread.__table__,
        BriefingTask.__table__,
        BriefingAuditLog.__table__,
    ]:
        if table.name in existing:
            print(f"  Table '{table.name}' already exists, skipping.")
        else:
            try:
                table.create(engine, checkfirst=True)
                print(f"  Created table '{table.name}'.")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  Table '{table.name}' already exists (index conflict), skipping.")
                else:
                    raise
    print("Migration complete.")


if __name__ == "__main__":
    run_migration()
