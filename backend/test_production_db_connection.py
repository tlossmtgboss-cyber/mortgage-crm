#!/usr/bin/env python3
"""
Test Production Database Connection
"""
import sys
from sqlalchemy import create_engine, text

# Production database URL
# Note: The @ symbol was missing in the original URL
from urllib.parse import quote_plus

password = "RzXRIwJsZINuRwMQybDbZYqfFoHBaXRw"
encoded_password = quote_plus(password)
PROD_DB_URL = f"postgresql://postgres:{encoded_password}@d3svitchback.proxy.rlwy.net:38467/railway"

print("="*70)
print("TESTING PRODUCTION DATABASE CONNECTION")
print("="*70)
print(f"Host: d3svitchback.proxy.rlwy.net:38467")
print(f"Database: railway")
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
