#!/usr/bin/env python3
"""
Run Master Manager Platform migration
Creates tables for Talent & Capacity OS

Execute via: railway run python run_master_manager_migration.py
"""

import os
import asyncio
import asyncpg


async def run_migration():
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return False

    print("Connecting to database...")
    conn = await asyncpg.connect(database_url)

    try:
        # Read migration file
        migration_path = os.path.join(os.path.dirname(__file__), 'migrations', 'add_master_manager_tables.sql')
        with open(migration_path, 'r') as f:
            migration_sql = f.read()

        print("Running Master Manager Platform migration...")
        print("Creating tables: mm_role_definitions, mm_talent_capacity, mm_talent_state,")
        print("                 mm_talent_state_history, mm_talent_performance,")
        print("                 mm_capacity_alerts, mm_coverage_map,")
        print("                 mm_candidates, mm_job_postings")

        # Execute migration
        await conn.execute(migration_sql)

        print("\nMigration completed successfully!")

        # Verify tables were created
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'mm_%'
            ORDER BY table_name
        """)

        print("\nMaster Manager tables created:")
        for table in tables:
            print(f"  - {table['table_name']}")

        # Check role definitions were seeded
        roles = await conn.fetch("""
            SELECT role_name, role_category FROM mm_role_definitions
            ORDER BY role_category, role_name
        """)

        print("\nSeeded role definitions:")
        for role in roles:
            print(f"  - {role['role_name']} ({role['role_category']})")

        return True

    except Exception as e:
        print(f"ERROR: Migration failed - {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await conn.close()


if __name__ == '__main__':
    success = asyncio.run(run_migration())
    exit(0 if success else 1)
