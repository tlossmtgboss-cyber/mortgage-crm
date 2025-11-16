#!/usr/bin/env python3
"""
Run AI Delegated Tasks Migration
Connects to Railway PostgreSQL and creates the ai_delegated_tasks table
"""

import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment variables")
    print("Please set DATABASE_URL or run with Railway CLI:")
    print("  railway run python3 run_ai_delegated_tasks_migration.py")
    sys.exit(1)

# Ensure postgresql:// format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print("=" * 70)
print("🤖 AI DELEGATED TASKS MIGRATION")
print("=" * 70)
print()
print(f"Database: {DATABASE_URL[:50]}...")
print()

try:
    # Create engine
    engine = create_engine(DATABASE_URL)

    # Read migration SQL
    print("Reading migration SQL...")
    with open("ai_delegated_tasks_schema.sql", "r") as f:
        migration_sql = f.read()

    print(f"✅ Loaded {len(migration_sql)} characters of SQL")
    print()

    # Execute migration
    print("Running migration...")
    print("-" * 70)

    with engine.begin() as conn:
        # Execute the migration
        conn.execute(text(migration_sql))

    print("-" * 70)
    print()
    print("✅ Migration completed successfully!")
    print()

    # Verify table exists
    print("Verifying table creation...")
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'ai_delegated_tasks'
            );
        """))
        exists = result.scalar()

        if exists:
            print("✅ ai_delegated_tasks table created successfully")

            # Check for any existing records
            count_result = conn.execute(text("SELECT COUNT(*) FROM ai_delegated_tasks"))
            count = count_result.scalar()
            print(f"📊 Current records: {count}")
        else:
            print("❌ Table creation failed")
            sys.exit(1)

    print()
    print("=" * 70)
    print("🎉 MIGRATION COMPLETE")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Restart your backend server to pick up the new table")
    print("2. Test the AI delegation feature in Reconciliation Center")
    print()

except Exception as e:
    print()
    print("❌ Migration failed!")
    print(f"Error: {e}")
    print()
    sys.exit(1)
