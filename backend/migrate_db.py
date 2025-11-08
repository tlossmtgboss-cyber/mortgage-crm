"""
Database Migration Script
Adds missing onboarding_completed column to users table
"""

import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    exit(1)

# Replace postgres:// with postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def add_onboarding_completed_column():
    """Add onboarding_completed column if it doesn't exist"""
    with engine.connect() as conn:
        try:
            # Check if column exists
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='users'
                AND column_name='onboarding_completed'
            """))

            if result.fetchone() is None:
                print("Adding onboarding_completed column...")
                conn.execute(text("""
                    ALTER TABLE users
                    ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE
                """))
                conn.commit()
                print("✓ Column added successfully")
            else:
                print("✓ Column already exists")

        except Exception as e:
            print(f"Error: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    print("Running database migration...")
    add_onboarding_completed_column()
    print("Migration complete!")
