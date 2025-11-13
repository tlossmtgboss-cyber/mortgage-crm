#!/usr/bin/env python3
"""
Run AI Architecture Migration
Connects to Railway PostgreSQL and runs the migration
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
    print("  railway run python3 run_ai_migration.py")
    sys.exit(1)

# Ensure postgresql:// format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print("=" * 70)
print("🤖 AI ARCHITECTURE MIGRATION")
print("=" * 70)
print()
print(f"Database: {DATABASE_URL[:50]}...")
print()

try:
    # Create engine
    engine = create_engine(DATABASE_URL)

    # Read migration SQL
    print("Reading migration SQL...")
    with open("ai_architecture_schema.sql", "r") as f:
        migration_sql = f.read()

    print(f"✅ Loaded {len(migration_sql)} characters of SQL")
    print()

    # Execute migration
    print("Running migration...")
    print("-" * 70)

    with engine.connect() as conn:
        # Split by statement (simple approach)
        statements = [s.strip() for s in migration_sql.split(';') if s.strip()]

        total = len(statements)
        for i, statement in enumerate(statements, 1):
            if statement.strip():
                try:
                    conn.execute(text(statement))
                    if i % 10 == 0:
                        print(f"  Executed {i}/{total} statements...")
                except Exception as e:
                    # Some statements might fail if tables exist - that's ok
                    if "already exists" not in str(e).lower():
                        print(f"  Warning: {e}")

        conn.commit()

    print()
    print("✅ Migration completed!")
    print()

    # Verify tables
    print("Verifying tables...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'ai_%'
            ORDER BY table_name
        """))

        tables = [row[0] for row in result.fetchall()]

        if tables:
            print(f"✅ Found {len(tables)} AI tables:")
            for table in tables:
                print(f"  • {table}")
        else:
            print("⚠️  No AI tables found - migration may have failed")

    print()
    print("=" * 70)
    print("🎉 MIGRATION COMPLETE!")
    print("=" * 70)
    print()
    print("Next step: Run initialize_ai_system.py")
    print()

    sys.exit(0)

except Exception as e:
    print()
    print("=" * 70)
    print(f"❌ MIGRATION FAILED: {e}")
    print("=" * 70)
    print()
    sys.exit(1)
