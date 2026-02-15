"""
Migration: Add Permission Requests System
Creates tables for user permissions and permission requests
"""

from sqlalchemy import create_engine, text
import os
import sys

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is required")
    sys.exit(1)

# Fix Railway DATABASE_URL format (postgres:// -> postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def upgrade():
    """Create user_permissions and permission_requests tables"""

    print("Creating permission system tables...")

    # SQL statements to create tables
    create_tables_sql = """
    -- Create user_permissions table
    CREATE TABLE IF NOT EXISTS user_permissions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        permission_key VARCHAR(255) NOT NULL,
        granted BOOLEAN DEFAULT FALSE,
        granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        granted_at TIMESTAMP,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_user_permission UNIQUE (user_id, permission_key)
    );

    CREATE INDEX IF NOT EXISTS idx_user_permissions_user ON user_permissions(user_id);
    CREATE INDEX IF NOT EXISTS idx_user_permissions_key ON user_permissions(permission_key);

    -- Create enum types for permission_requests
    DO $$ BEGIN
        CREATE TYPE urgency_enum AS ENUM ('low', 'medium', 'high');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;

    DO $$ BEGIN
        CREATE TYPE request_status_enum AS ENUM ('pending', 'approved', 'denied', 'more_info_needed');
    EXCEPTION
        WHEN duplicate_object THEN null;
    END $$;

    -- Create permission_requests table
    CREATE TABLE IF NOT EXISTS permission_requests (
        id SERIAL PRIMARY KEY,
        employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        permission_key VARCHAR(255) NOT NULL,
        justification TEXT NOT NULL,
        urgency urgency_enum DEFAULT 'medium',
        is_temporary BOOLEAN DEFAULT FALSE,
        duration_days INTEGER,
        status request_status_enum DEFAULT 'pending',
        manager_notes TEXT,
        decided_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        decided_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_permission_requests_employee ON permission_requests(employee_id);
    CREATE INDEX IF NOT EXISTS idx_permission_requests_status ON permission_requests(status);
    CREATE INDEX IF NOT EXISTS idx_permission_requests_created ON permission_requests(created_at DESC);
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(create_tables_sql))
            conn.commit()

        print("✅ Created user_permissions table with indexes")
        print("✅ Created permission_requests table with indexes")
        print("✅ Created enum types: urgency_enum, request_status_enum")
        print("\n🎉 Permission system migration completed successfully!")

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        sys.exit(1)

def downgrade():
    """Drop permission_requests and user_permissions tables"""

    print("Rolling back permission system tables...")

    drop_tables_sql = """
    DROP TABLE IF EXISTS permission_requests CASCADE;
    DROP TABLE IF EXISTS user_permissions CASCADE;
    DROP TYPE IF EXISTS urgency_enum CASCADE;
    DROP TYPE IF EXISTS request_status_enum CASCADE;
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(drop_tables_sql))
            conn.commit()

        print("✅ Dropped permission_requests table")
        print("✅ Dropped user_permissions table")
        print("✅ Dropped enum types")

    except Exception as e:
        print(f"❌ Error during rollback: {e}")
        sys.exit(1)

if __name__ == '__main__':
    print("\n" + "="*60)
    print("PERMISSION SYSTEM MIGRATION")
    print("="*60 + "\n")

    if len(sys.argv) > 1 and sys.argv[1] == 'downgrade':
        downgrade()
    else:
        upgrade()
