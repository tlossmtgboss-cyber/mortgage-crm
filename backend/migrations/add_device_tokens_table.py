"""
Migration: Add device_tokens table for push notifications

This table stores device tokens (APNs for iOS, FCM for Android) for push notifications.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def run_migration():
    """Create the device_tokens table."""
    engine = create_engine(DATABASE_URL)
    is_postgres = 'postgresql' in DATABASE_URL.lower()

    with engine.connect() as conn:
        # Check if table already exists
        if is_postgres:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'device_tokens'
                );
            """))
            exists = result.scalar()
        else:
            # SQLite
            result = conn.execute(text("""
                SELECT name FROM sqlite_master WHERE type='table' AND name='device_tokens';
            """))
            exists = result.fetchone() is not None

        if exists:
            print("Table 'device_tokens' already exists. Skipping creation.")
            return

        # Create the table
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE device_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    device_token VARCHAR(500) NOT NULL,
                    platform VARCHAR(20) NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    CONSTRAINT uq_user_device_token UNIQUE (user_id, device_token)
                );

                CREATE INDEX idx_device_tokens_user_id ON device_tokens(user_id);
                CREATE INDEX idx_device_tokens_active ON device_tokens(is_active) WHERE is_active = TRUE;
            """))
        else:
            # SQLite compatible
            conn.execute(text("""
                CREATE TABLE device_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    device_token VARCHAR(500) NOT NULL,
                    platform VARCHAR(20) NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, device_token)
                )
            """))
            conn.execute(text("CREATE INDEX idx_device_tokens_user_id ON device_tokens(user_id);"))
        conn.commit()

        print("Successfully created 'device_tokens' table.")

def rollback_migration():
    """Drop the device_tokens table."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS device_tokens CASCADE;"))
        conn.commit()
        print("Successfully dropped 'device_tokens' table.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    else:
        run_migration()
