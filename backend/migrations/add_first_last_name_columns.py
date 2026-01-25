"""
Migration: Add first_name and last_name columns to users table
Migrates existing full_name data to first_name/last_name

Run with: python migrations/add_first_last_name_columns.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def get_database_url():
    """Get database URL from environment."""
    return os.getenv("DATABASE_URL", "sqlite:///mortgage_crm.db")


def run_migration():
    """Add first_name and last_name columns and migrate data."""
    database_url = get_database_url()
    engine = create_engine(database_url)

    print("=" * 60)
    print("Migration: Add first_name and last_name to users table")
    print("=" * 60)

    with engine.connect() as conn:
        # Check if columns already exist
        if database_url.startswith("sqlite"):
            result = conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result.fetchall()]
        else:
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users'
            """))
            columns = [row[0] for row in result.fetchall()]

        # Add first_name column if not exists
        if 'first_name' not in columns:
            print("Adding first_name column...")
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR(100)"))
                conn.commit()
                print("  ✓ first_name column added")
            except OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print("  - first_name column already exists")
                else:
                    raise
        else:
            print("  - first_name column already exists")

        # Add last_name column if not exists
        if 'last_name' not in columns:
            print("Adding last_name column...")
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR(100)"))
                conn.commit()
                print("  ✓ last_name column added")
            except OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print("  - last_name column already exists")
                else:
                    raise
        else:
            print("  - last_name column already exists")

        # Migrate existing full_name data
        if 'full_name' in columns:
            print("\nMigrating existing full_name data...")

            # Get users with full_name but without first_name/last_name
            result = conn.execute(text("""
                SELECT id, full_name
                FROM users
                WHERE full_name IS NOT NULL
                  AND full_name != ''
                  AND (first_name IS NULL OR first_name = '')
            """))
            users_to_migrate = result.fetchall()

            migrated = 0
            for user_id, full_name in users_to_migrate:
                if full_name:
                    parts = full_name.strip().split(' ', 1)
                    first_name = parts[0] if parts else ''
                    last_name = parts[1] if len(parts) > 1 else ''

                    conn.execute(text("""
                        UPDATE users
                        SET first_name = :first_name, last_name = :last_name
                        WHERE id = :id
                    """), {
                        "id": user_id,
                        "first_name": first_name,
                        "last_name": last_name
                    })
                    migrated += 1

            conn.commit()
            print(f"  ✓ Migrated {migrated} users from full_name to first_name/last_name")

        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    run_migration()
