#!/usr/bin/env python3
"""
Run Phase 1+2 AI Migration Locally
Connects to Railway PostgreSQL via environment and runs Phase 1+2 schema
"""

import subprocess
import sys

print("=" * 70)
print("🤖 BUILDING AI DATABASE SCHEMA (Phase 1 & 2)")
print("=" * 70)
print()

# Step 1: Get DATABASE_URL from Railway
print("Step 1: Getting DATABASE_URL from Railway...")
result = subprocess.run(
    ["railway", "variables", "--json"],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print("❌ Failed to get Railway variables")
    print("Error:", result.stderr)
    print()
    print("Try running: railway link")
    sys.exit(1)

import json
try:
    variables = json.loads(result.stdout)
    database_url = variables.get("DATABASE_URL")

    if not database_url:
        print("❌ DATABASE_URL not found in Railway variables")
        sys.exit(1)

    print(f"✅ Got DATABASE_URL: {database_url[:50]}...")
except json.JSONDecodeError as e:
    print("❌ Failed to parse Railway variables")
    print("Error:", e)
    sys.exit(1)

print()

# Step 2: Run migration using psql via Railway
print("Step 2: Running Phase 1+2 migration...")
print("-" * 70)

# Use railway run to execute psql with the schema file
result = subprocess.run(
    ["railway", "run", "psql", database_url, "-f", "ai_phase1_2_schema.sql"],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print("❌ Migration failed")
    print("Error:", result.stderr)
    print("Output:", result.stdout)
    sys.exit(1)

print(result.stdout)
print()
print("✅ Migration completed!")
print()

# Step 3: Verify tables were created
print("Step 3: Verifying tables...")
print("-" * 70)

verify_sql = """
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE 'ai_%'
ORDER BY table_name;
"""

result = subprocess.run(
    ["railway", "run", "psql", database_url, "-t", "-c", verify_sql],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    tables = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
    print(f"✅ Found {len(tables)} AI tables:")
    for table in tables:
        print(f"  • {table}")
else:
    print("⚠️  Could not verify tables")

print()
print("=" * 70)
print("🎉 DATABASE SCHEMA BUILT!")
print("=" * 70)
print()
print("Next step: Initialize agents and tools")
print("  curl -X POST 'https://app.perenniaai.com/admin/initialize-ai-system' \\")
print("    -H 'Content-Type: application/json' \\")
print("    -d '{\"secret\": \"migrate-ai-2024\"}'")
print()
