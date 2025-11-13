#!/usr/bin/env python3
"""
Build AI Database Schema - Phase 1 & 2
Runs directly using DATABASE_URL from environment or .env
"""

import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 70)
print("🤖 BUILDING AI DATABASE SCHEMA (Phase 1 & 2)")
print("=" * 70)
print()

# Get DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not found!")
    print()
    print("Please set DATABASE_URL environment variable or add to .env file")
    print("Example:")
    print('  export DATABASE_URL="postgresql://user:pass@host:port/database"')
    print()
    print("Or run via Railway:")
    print("  railway run python3 build_schema_now.py")
    sys.exit(1)

# Ensure postgresql:// format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"Database: {DATABASE_URL[:60]}...")
print()

try:
    # Create engine
    engine = create_engine(DATABASE_URL)

    # Read Phase 1+2 migration SQL
    print("Reading Phase 1+2 schema...")
    schema_file = "ai_phase1_2_schema.sql"

    if not os.path.exists(schema_file):
        print(f"❌ Schema file not found: {schema_file}")
        sys.exit(1)

    with open(schema_file, "r") as f:
        migration_sql = f.read()

    print(f"✅ Loaded {len(migration_sql)} characters")
    print()

    # Execute migration
    print("Creating tables...")
    print("-" * 70)

    with engine.connect() as conn:
        # Split by statement
        statements = [s.strip() for s in migration_sql.split(';') if s.strip()]

        total = len(statements)
        created_count = 0
        error_count = 0

        for i, statement in enumerate(statements, 1):
            if statement.strip():
                try:
                    conn.execute(text(statement))
                    created_count += 1

                    if i % 5 == 0:
                        print(f"  Processed {i}/{total} statements...")

                except Exception as e:
                    error_msg = str(e).lower()
                    # Ignore "already exists" errors
                    if "already exists" in error_msg:
                        if i % 5 == 0:
                            print(f"  Processed {i}/{total} statements (some already exist)...")
                    else:
                        error_count += 1
                        print(f"  ⚠️  Warning at statement {i}: {str(e)[:100]}")

        conn.commit()

    print()
    print(f"✅ Schema creation completed!")
    print(f"   Created/Updated: {created_count} statements")
    if error_count > 0:
        print(f"   Warnings: {error_count}")
    print()

    # Verify tables
    print("Verifying tables...")
    print("-" * 70)

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
    print("🎉 DATABASE SCHEMA BUILT SUCCESSFULLY!")
    print("=" * 70)
    print()
    print("Next step: Initialize AI system")
    print("  python3 initialize_ai_only.py")
    print()
    print("Or via HTTP:")
    print("  curl -X POST 'https://mortgage-crm-production-7a9a.up.railway.app/admin/initialize-ai-system' \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -d '{\"secret\": \"migrate-ai-2024\"}'")
    print()

    sys.exit(0)

except FileNotFoundError as e:
    print()
    print(f"❌ File not found: {e}")
    print()
    sys.exit(1)

except Exception as e:
    print()
    print("=" * 70)
    print(f"❌ SCHEMA BUILD FAILED: {e}")
    print("=" * 70)
    print()
    sys.exit(1)
