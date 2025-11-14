#!/usr/bin/env python3
"""
Migrate Production Database on Railway
Adds missing columns to users table
"""

import os
import psycopg2
from urllib.parse import urlparse

# Railway PostgreSQL URL
# Get from: railway variables | grep DATABASE_URL
# Or from Railway dashboard: Settings > Variables
DATABASE_URL = os.getenv("DATABASE_URL") or input("Enter Railway DATABASE_URL: ")

def migrate_database():
    """Add missing columns to production database"""

    print("\n🔧 Migrating Production Database on Railway")
    print("="*60)

    try:
        # Parse database URL
        result = urlparse(DATABASE_URL)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port

        print(f"\n📡 Connecting to Railway PostgreSQL...")
        print(f"   Host: {hostname}")
        print(f"   Database: {database}")

        # Connect to database
        conn = psycopg2.connect(
            database=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        cursor = conn.cursor()

        print(f"✅ Connected successfully!")

        # Check if columns exist
        print(f"\n🔍 Checking for missing columns...")

        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users'
        """)

        existing_columns = [row[0] for row in cursor.fetchall()]
        print(f"   Found {len(existing_columns)} columns in users table")

        # Add is_admin column if missing
        if 'is_admin' not in existing_columns:
            print(f"\n➕ Adding is_admin column...")
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN is_admin BOOLEAN DEFAULT TRUE
            """)
            conn.commit()
            print(f"   ✅ is_admin column added")
        else:
            print(f"   ℹ️  is_admin column already exists")

        # Add parent_user_id column if missing
        if 'parent_user_id' not in existing_columns:
            print(f"\n➕ Adding parent_user_id column...")
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN parent_user_id INTEGER REFERENCES users(id)
            """)
            conn.commit()
            print(f"   ✅ parent_user_id column added")
        else:
            print(f"   ℹ️  parent_user_id column already exists")

        # Verify changes
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users'
            ORDER BY ordinal_position
        """)

        all_columns = [row[0] for row in cursor.fetchall()]
        print(f"\n📋 Users table now has {len(all_columns)} columns:")
        for col in all_columns:
            print(f"   - {col}")

        cursor.close()
        conn.close()

        print(f"\n✅ Migration completed successfully!")
        print(f"\n📝 Next steps:")
        print(f"   1. Wait for Railway to restart (if it auto-restarts)")
        print(f"   2. Run: python3 create_production_user.py")
        print(f"   3. Test login at: https://mortgage-crm-production-7a9a.up.railway.app/docs")

        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print(f"\n💡 Tips:")
        print(f"   - Make sure DATABASE_URL is correct")
        print(f"   - Check Railway dashboard for database credentials")
        print(f"   - Verify your IP is allowed in Railway's network settings")
        return False

def main():
    """Main function"""

    print("\n" + "="*60)
    print("PRODUCTION DATABASE MIGRATION - RAILWAY")
    print("="*60)
    print("\n⚠️  This will modify the production database!")
    print("   Make sure you have a backup if needed.")

    response = input("\nContinue? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("❌ Migration cancelled")
        return

    success = migrate_database()

    if not success:
        print("\n❌ Migration failed. Please fix the errors and try again.")

if __name__ == "__main__":
    main()
