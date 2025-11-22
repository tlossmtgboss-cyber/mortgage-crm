#!/usr/bin/env python3
"""
Run AI Task Automation migration
Execute via: railway run python run_ai_migration.py
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
        migration_path = os.path.join(os.path.dirname(__file__), 'migrations', 'add_ai_task_automation.sql')
        with open(migration_path, 'r') as f:
            migration_sql = f.read()

        print("Running AI Task Automation migration...")

        # Execute migration
        await conn.execute(migration_sql)

        print("Migration completed successfully!")

        # Verify tables were created
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'ai_%'
            ORDER BY table_name
        """)

        print("\nAI tables created:")
        for table in tables:
            print(f"  - {table['table_name']}")

        # Check tasks table columns
        columns = await conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'tasks'
            AND column_name LIKE 'ai_%'
            ORDER BY column_name
        """)

        print("\nAI columns added to tasks table:")
        for col in columns:
            print(f"  - {col['column_name']}")

        return True

    except Exception as e:
        print(f"ERROR: Migration failed - {str(e)}")
        return False
    finally:
        await conn.close()

if __name__ == '__main__':
    success = asyncio.run(run_migration())
    exit(0 if success else 1)
