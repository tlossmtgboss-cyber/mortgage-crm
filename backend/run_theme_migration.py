#!/usr/bin/env python3
"""
Run the microsite themes migration.
This script can be run via `railway run python run_theme_migration.py`
"""
import os
import psycopg2
from pathlib import Path

def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return False

    # Read the migration file
    migration_path = Path(__file__).parent / "migrations" / "add_microsite_themes.sql"
    if not migration_path.exists():
        print(f"ERROR: Migration file not found at {migration_path}")
        return False

    sql = migration_path.read_text()

    print(f"Connecting to database...")
    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()

        print("Running migration...")
        cursor.execute(sql)

        print("Migration completed successfully!")

        # Verify tables were created
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name IN ('microsite_themes', 'microsites', 'microsite_profiles')
            ORDER BY table_name
        """)
        tables = cursor.fetchall()
        print(f"Verified tables: {[t[0] for t in tables]}")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    exit(0 if success else 1)
