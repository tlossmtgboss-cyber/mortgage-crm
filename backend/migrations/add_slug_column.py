"""Add missing slug column to users table

This migration adds the 'slug' column that was added to the User model
but was missing from the production database.
"""
import os
import sys
from sqlalchemy import create_engine, text

def run_migration():
    """Run the migration to add slug column"""
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return False

    print(f"Connecting to database...")
    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'slug'
        """))

        if result.fetchone():
            print("✓ Column 'slug' already exists in users table")
        else:
            print("Adding 'slug' column to users table...")
            conn.execute(text("""
                ALTER TABLE users
                ADD COLUMN slug VARCHAR UNIQUE
            """))
            conn.commit()
            print("✓ Successfully added 'slug' column")

        # Create index if not exists
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_users_slug ON users(slug)
            """))
            conn.commit()
            print("✓ Index created/verified")
        except Exception as e:
            print(f"Note: Index may already exist: {e}")

    print("Migration complete!")
    return True

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
