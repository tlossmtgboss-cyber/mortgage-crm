"""
Migration: Fix Access Certifications Table Schema
Purpose: Drop and recreate access_certifications with correct schema
"""

from sqlalchemy import create_engine, text
import os

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def upgrade():
    """Drop and recreate access_certifications table with correct schema"""
    engine = create_engine(get_database_url())

    migration_sql = """
    -- Drop existing table if it exists
    DROP TABLE IF EXISTS access_certifications CASCADE;

    -- Create table with correct schema
    CREATE TABLE access_certifications (
        id SERIAL PRIMARY KEY,
        employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        certification_period VARCHAR(20) NOT NULL,
        due_date DATE NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',

        certified_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        certified_at TIMESTAMP,
        certification_notes TEXT,

        permissions_snapshot JSONB,
        permissions_changed JSONB,

        reminder_sent_30d BOOLEAN DEFAULT FALSE,
        reminder_sent_7d BOOLEAN DEFAULT FALSE,
        reminder_sent_overdue BOOLEAN DEFAULT FALSE,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Create indexes
    CREATE INDEX idx_certifications_employee ON access_certifications(employee_id);
    CREATE INDEX idx_certifications_due_date ON access_certifications(due_date);
    CREATE INDEX idx_certifications_status ON access_certifications(status);
    CREATE INDEX idx_certifications_period ON access_certifications(certification_period);
    """

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()

    print("✅ Access certifications table recreated with correct schema")

if __name__ == "__main__":
    print("⬆️  Fixing access certifications table schema...")
    upgrade()
    print("Done!")
