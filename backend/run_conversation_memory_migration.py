#!/usr/bin/env python3
"""
Run conversation_memory table migration for AI Memory System
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_migration():
    """Run the conversation_memory table migration"""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ Error: DATABASE_URL environment variable not set")
        sys.exit(1)

    # Replace postgres:// with postgresql:// for psycopg2
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    print("🔄 Connecting to database...")

    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()

        print("✅ Connected to database")
        print("🔄 Running conversation_memory migration...")

        # Read migration SQL file
        migration_file = os.path.join(os.path.dirname(__file__), 'migrations', 'add_conversation_memory.sql')
        with open(migration_file, 'r') as f:
            migration_sql = f.read()

        # Execute migration
        cursor.execute(migration_sql)
        conn.commit()

        print("✅ Migration completed successfully!")

        # Verify table exists
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'conversation_memory'
        """)

        result = cursor.fetchone()
        if result:
            print(f"✅ Verified: conversation_memory table exists")

            # Count rows
            cursor.execute("SELECT COUNT(*) FROM conversation_memory")
            count = cursor.fetchone()[0]
            print(f"📊 Current row count: {count}")
        else:
            print("⚠️  Warning: Could not verify table creation")

        cursor.close()
        conn.close()

        print("\n🎉 AI Memory System database migration complete!")
        print("\nNext steps:")
        print("1. Set PINECONE_API_KEY in Railway environment variables")
        print("2. Set OPENAI_API_KEY in Railway environment variables (for embeddings)")
        print("3. Redeploy the backend service")
        print("4. Test the Smart AI Chat in the Lead Detail page")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 60)
    print("AI Memory System - Database Migration")
    print("=" * 60)
    print()

    run_migration()
