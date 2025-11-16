"""
Migration: Add user_job_descriptions table

This migration creates a table to store comprehensive job descriptions for team members
with version tracking and audit capabilities.
"""

import os
import sys
from sqlalchemy import create_engine, text
from datetime import datetime, timezone

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

def run_migration():
    """Create user_job_descriptions table"""
    print("\n" + "="*80)
    print("MIGRATION: Add user_job_descriptions table")
    print("="*80 + "\n")

    with engine.begin() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='user_job_descriptions'
        """))

        if result.fetchone():
            print("✓ Table 'user_job_descriptions' already exists. Skipping creation.")
            return

        # Create the table
        print("Creating user_job_descriptions table...")
        conn.execute(text("""
            CREATE TABLE user_job_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                updated_by_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (updated_by_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """))

        # Create index on user_id for faster lookups
        print("Creating index on user_id...")
        conn.execute(text("""
            CREATE INDEX idx_job_descriptions_user_id ON user_job_descriptions(user_id)
        """))

        # Create index on updated_at for sorting
        print("Creating index on updated_at...")
        conn.execute(text("""
            CREATE INDEX idx_job_descriptions_updated_at ON user_job_descriptions(updated_at)
        """))

        print("\n✓ Migration completed successfully!")
        print("\nCreated:")
        print("  - Table: user_job_descriptions")
        print("  - Index: idx_job_descriptions_user_id")
        print("  - Index: idx_job_descriptions_updated_at")

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)
