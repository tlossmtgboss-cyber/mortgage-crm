#!/usr/bin/env python3
"""Check if access_certifications table exists in production database"""

from sqlalchemy import create_engine, text
import os

def check_table():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not set")
        return

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Check if table exists
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
            AND table_name='access_certifications'
        """))
        tables = [row[0] for row in result]

        if 'access_certifications' in tables:
            print('✅ access_certifications table EXISTS in production')

            # Get column info
            result = conn.execute(text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name='access_certifications'
                ORDER BY ordinal_position
            """))
            print('\n📋 Table structure:')
            for row in result:
                print(f'  - {row[0]}: {row[1]}')

            # Get count
            result = conn.execute(text('SELECT COUNT(*) FROM access_certifications'))
            count = result.fetchone()[0]
            print(f'\n📊 Current certification records: {count}')

            # Get indexes
            result = conn.execute(text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename='access_certifications'
            """))
            print('\n🔍 Indexes:')
            for row in result:
                print(f'  - {row[0]}')
        else:
            print('❌ access_certifications table does NOT exist')
            print('Available tables:', ', '.join(tables))

if __name__ == '__main__':
    check_table()
