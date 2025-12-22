#!/usr/bin/env python3
"""
Test Production Database Connection

Usage: Set DATABASE_URL environment variable before running.
"""
import os
import sys
from sqlalchemy import create_engine, text


def main():
    # Production database URL from environment variable
    PROD_DB_URL = os.getenv("DATABASE_URL") or os.getenv("PROD_DATABASE_URL")

    if not PROD_DB_URL:
        print("❌ ERROR: DATABASE_URL or PROD_DATABASE_URL environment variable not set")
        print("Set it with: export DATABASE_URL='postgresql://...'")
        sys.exit(1)

    print("="*70)
    print("TESTING PRODUCTION DATABASE CONNECTION")
    print("="*70)
    print("Using DATABASE_URL from environment")
    print()

    try:
        print("Creating engine...")
        engine = create_engine(PROD_DB_URL)

        print("Connecting to database...")
        with engine.connect() as conn:
            print("✅ Connection successful!")

            # Test query
            print("\nTesting query...")
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"✅ PostgreSQL Version: {version}")

            # Count tables
            print("\nCounting tables...")
            result = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """))
            table_count = result.scalar()
            print(f"✅ Total tables in public schema: {table_count}")

            # List some tables
            print("\nListing tables...")
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                LIMIT 10
            """))
            tables = result.fetchall()
            for table in tables:
                print(f"  - {table[0]}")

            print("\n" + "="*70)
            print("✅ ALL CONNECTION TESTS PASSED!")
            print("="*70)

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
