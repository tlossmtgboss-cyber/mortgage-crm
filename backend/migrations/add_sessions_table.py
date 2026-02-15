"""
Migration: Add Sessions Table
Purpose: Store user session tokens for authentication
"""

from sqlalchemy import create_engine, text
import os
from datetime import datetime

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def run_migration():
    """Run the migration - alias for upgrade()"""
    return upgrade()

def upgrade():
    """Create sessions table"""
    engine = create_engine(get_database_url())

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS sessions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token TEXT NOT NULL UNIQUE,
        refresh_token TEXT,
        expires_at TIMESTAMP NOT NULL,
        refresh_expires_at TIMESTAMP,
        ip_address VARCHAR(45),
        user_agent TEXT,
        device_info JSONB,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
    CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
    CREATE INDEX IF NOT EXISTS idx_sessions_is_active ON sessions(is_active);

    -- Index for cleanup queries
    CREATE INDEX IF NOT EXISTS idx_sessions_active_expires ON sessions(is_active, expires_at);
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(create_table_sql))
            conn.commit()

        print(f"✓ Created sessions table with indexes")
        return True
    except Exception as e:
        print(f"✗ Error creating sessions table: {e}")
        return False

def downgrade():
    """Drop sessions table"""
    engine = create_engine(get_database_url())

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS sessions CASCADE;"))
        conn.commit()

    print(f"✓ Dropped sessions table")

if __name__ == "__main__":
    print("Running sessions table migration...")
    upgrade()
    print("Migration complete!")
