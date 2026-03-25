"""
Migration: Add timezone column to organizations table.

Adds an org-level default timezone so individual users inherit their
organization's timezone unless they explicitly override on User.timezone.

Run:
    python migrations/add_organization_timezone.py

Safe to re-run (uses IF NOT EXISTS).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not set — skipping migration")
        return

    engine = create_engine(database_url)
    with engine.connect() as conn:
        # Add timezone column to organizations
        conn.execute(text("""
            ALTER TABLE organizations
            ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'America/Chicago'
        """))
        conn.commit()
        print("OK: organizations.timezone column added (or already exists)")


if __name__ == "__main__":
    run_migration()
