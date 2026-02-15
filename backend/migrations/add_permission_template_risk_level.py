"""
Migration: Add risk_level column to permission_templates table
Purpose: Add risk classification for permissions (low, medium, high, critical)
"""

from sqlalchemy import create_engine, text
import os

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def upgrade():
    """Add risk_level column to permission_templates table"""
    engine = create_engine(get_database_url())

    migration_sql = """
    -- Add risk_level column if it doesn't exist
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'permission_templates' AND column_name = 'risk_level'
        ) THEN
            ALTER TABLE permission_templates ADD COLUMN risk_level VARCHAR(20) DEFAULT 'medium';
            CREATE INDEX idx_permission_templates_risk ON permission_templates(risk_level);
            RAISE NOTICE 'Added risk_level column to permission_templates table';
        ELSE
            RAISE NOTICE 'risk_level column already exists';
        END IF;
    END $$;
    """

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()

    print("✅ Permission templates risk_level column migration completed")
    print("   - Added risk_level column (default: 'medium')")
    print("   - Created index on risk_level")

if __name__ == "__main__":
    print("⬆️  Adding risk_level column to permission_templates...")
    upgrade()
    print("Done!")
