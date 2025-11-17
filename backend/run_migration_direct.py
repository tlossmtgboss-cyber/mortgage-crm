#!/usr/bin/env python3
"""
Direct migration script to add MUM client fields
Run this via: railway run python backend/run_migration_direct.py
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def run_migration():
    """Run the MUM client fields migration directly on the database"""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("❌ DATABASE_URL not found in environment")
        sys.exit(1)

    print("🔧 Connecting to database...")

    # Create engine and session
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("🔧 Running MUM client fields migration...")
        print("")

        columns_to_add = [
            ("mum_clients", "email", "VARCHAR"),
            ("mum_clients", "phone", "VARCHAR"),
            ("mum_clients", "close_date", "TIMESTAMP"),
            ("mum_clients", "notes", "TEXT"),
            ("mum_clients", "next_touchpoint", "TIMESTAMP"),
            ("mum_clients", "referrals_sent", "INTEGER DEFAULT 0"),
            ("mum_clients", "opportunity_notes", "TEXT"),
            ("mum_clients", "loan_officer", "VARCHAR"),
            ("mum_clients", "loan_officer_email", "VARCHAR"),
            ("mum_clients", "processor", "VARCHAR"),
            ("mum_clients", "processor_email", "VARCHAR"),
            ("mum_clients", "underwriter", "VARCHAR"),
            ("mum_clients", "underwriter_email", "VARCHAR"),
            ("mum_clients", "closer", "VARCHAR"),
            ("mum_clients", "closer_email", "VARCHAR"),
            ("mum_clients", "user_id", "INTEGER REFERENCES users(id)"),
            ("activities", "mum_client_id", "INTEGER REFERENCES mum_clients(id)")
        ]

        added_columns = []
        existing_columns = []

        for table_name, column_name, column_type in columns_to_add:
            # Check if column already exists
            result = session.execute(text(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                AND column_name = '{column_name}'
            """))

            if result.fetchone():
                existing_columns.append(f"{table_name}.{column_name}")
                print(f"⏭️  Column already exists: {table_name}.{column_name}")
            else:
                # Add the column
                session.execute(text(f"""
                    ALTER TABLE {table_name}
                    ADD COLUMN {column_name} {column_type};
                """))
                added_columns.append(f"{table_name}.{column_name}")
                print(f"✅ Added column: {table_name}.{column_name}")

        session.commit()

        print("")
        print("=" * 60)
        print(f"✅ Migration completed successfully!")
        print(f"   Added: {len(added_columns)} columns")
        print(f"   Already existed: {len(existing_columns)} columns")
        print("=" * 60)

        if added_columns:
            print("\n📝 Added columns:")
            for col in added_columns:
                print(f"   - {col}")

        if existing_columns:
            print("\n📋 Existing columns (skipped):")
            for col in existing_columns:
                print(f"   - {col}")

        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
