"""
Migration: Add Compliance-Related Columns to Users Table
Purpose: Add account_status and department columns for compliance system
"""

from sqlalchemy import create_engine, text
import os

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def upgrade():
    """Add account_status and department columns to users table"""
    engine = create_engine(get_database_url())

    migration_sql = """
    -- Add account_status column if it doesn't exist
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'account_status'
        ) THEN
            ALTER TABLE users ADD COLUMN account_status VARCHAR(20) DEFAULT 'active';
            CREATE INDEX idx_users_account_status ON users(account_status);

            -- Update existing users to 'active'
            UPDATE users SET account_status = 'active' WHERE account_status IS NULL;

            RAISE NOTICE 'Added account_status column to users table';
        ELSE
            RAISE NOTICE 'account_status column already exists';
        END IF;
    END $$;

    -- Add department column if it doesn't exist
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'department'
        ) THEN
            ALTER TABLE users ADD COLUMN department VARCHAR(100);
            CREATE INDEX idx_users_department ON users(department);

            -- Set default department based on role
            UPDATE users
            SET department = CASE
                WHEN role IN ('sales', 'loan_officer') THEN 'Sales'
                WHEN role = 'operations' THEN 'Operations'
                WHEN role IN ('manager', 'management') THEN 'Management'
                WHEN role = 'admin' THEN 'Administration'
                ELSE 'General'
            END
            WHERE department IS NULL;

            RAISE NOTICE 'Added department column to users table';
        ELSE
            RAISE NOTICE 'department column already exists';
        END IF;
    END $$;

    -- Add full_name column if it doesn't exist (some queries use this)
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'users' AND column_name = 'full_name'
        ) THEN
            ALTER TABLE users ADD COLUMN full_name VARCHAR(255);

            -- Copy from name column if it exists
            UPDATE users SET full_name = name WHERE full_name IS NULL AND name IS NOT NULL;

            RAISE NOTICE 'Added full_name column to users table';
        ELSE
            RAISE NOTICE 'full_name column already exists';
        END IF;
    END $$;
    """

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()

    print("✅ Migration completed successfully")
    print("   - Added account_status column (default: 'active')")
    print("   - Added department column (auto-populated based on role)")
    print("   - Added full_name column (copied from name)")

def downgrade():
    """Remove compliance columns from users table"""
    engine = create_engine(get_database_url())

    rollback_sql = """
    DROP INDEX IF EXISTS idx_users_account_status;
    DROP INDEX IF EXISTS idx_users_department;

    ALTER TABLE users DROP COLUMN IF EXISTS account_status;
    ALTER TABLE users DROP COLUMN IF EXISTS department;
    ALTER TABLE users DROP COLUMN IF EXISTS full_name;
    """

    with engine.connect() as conn:
        conn.execute(text(rollback_sql))
        conn.commit()

    print("✅ Rollback completed - removed compliance columns")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        print("🔄 Rolling back user compliance columns migration...")
        downgrade()
    else:
        print("⬆️  Running user compliance columns migration...")
        upgrade()

    print("Done!")
