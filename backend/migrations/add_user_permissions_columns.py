"""
Migration: Add missing columns to user_permissions table
Purpose: Add is_temporary, granted_until, revoked_at columns for compliance system
"""

from sqlalchemy import create_engine, text
import os

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def upgrade():
    """Add missing columns to user_permissions table"""
    engine = create_engine(get_database_url())

    migration_sql = """
    -- Add is_temporary column if it doesn't exist
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'user_permissions' AND column_name = 'is_temporary'
        ) THEN
            ALTER TABLE user_permissions ADD COLUMN is_temporary BOOLEAN DEFAULT FALSE;
            RAISE NOTICE 'Added is_temporary column to user_permissions table';
        ELSE
            RAISE NOTICE 'is_temporary column already exists';
        END IF;
    END $$;

    -- Add granted_until column if it doesn't exist
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'user_permissions' AND column_name = 'granted_until'
        ) THEN
            ALTER TABLE user_permissions ADD COLUMN granted_until TIMESTAMP;
            RAISE NOTICE 'Added granted_until column to user_permissions table';
        ELSE
            RAISE NOTICE 'granted_until column already exists';
        END IF;
    END $$;

    -- Add revoked_at column if it doesn't exist
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'user_permissions' AND column_name = 'revoked_at'
        ) THEN
            ALTER TABLE user_permissions ADD COLUMN revoked_at TIMESTAMP;
            CREATE INDEX idx_user_permissions_revoked ON user_permissions(revoked_at) WHERE revoked_at IS NOT NULL;
            RAISE NOTICE 'Added revoked_at column to user_permissions table';
        ELSE
            RAISE NOTICE 'revoked_at column already exists';
        END IF;
    END $$;
    """

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()

    print("✅ User permissions columns migration completed")
    print("   - Added is_temporary column (default: FALSE)")
    print("   - Added granted_until column")
    print("   - Added revoked_at column with index")

if __name__ == "__main__":
    print("⬆️  Adding missing user permissions columns...")
    upgrade()
    print("Done!")
