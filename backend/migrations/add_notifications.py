"""
Migration: Add Notifications System
Creates notifications table for in-app notifications
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
    """Create notifications table"""

    print("Creating notifications table...")

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS notifications (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        type VARCHAR(50) NOT NULL,
        title VARCHAR(255) NOT NULL,
        message TEXT NOT NULL,
        link VARCHAR(500),
        is_read BOOLEAN DEFAULT FALSE,
        read_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
    CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
    CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_read) WHERE is_read = FALSE;
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(create_table_sql))
            conn.commit()

        print("✅ Created notifications table with indexes")
        print("✅ Created index for unread notifications")
        print("\n🎉 Notifications system migration completed successfully!")

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        sys.exit(1)

def downgrade():
    """Drop notifications table"""

    print("Rolling back notifications table...")

    drop_table_sql = """
    DROP TABLE IF EXISTS notifications CASCADE;
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(drop_table_sql))
            conn.commit()

        print("✅ Dropped notifications table")

    except Exception as e:
        print(f"❌ Error during rollback: {e}")
        sys.exit(1)

if __name__ == '__main__':
    print("\n" + "="*60)
    print("NOTIFICATIONS SYSTEM MIGRATION")
    print("="*60 + "\n")

    if len(sys.argv) > 1 and sys.argv[1] == 'downgrade':
        downgrade()
    else:
        upgrade()
