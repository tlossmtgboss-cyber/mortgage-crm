"""
Migration: Add Access Certifications Table
Purpose: Quarterly manager certification of employee permissions
"""

from sqlalchemy import create_engine, text
import os
from datetime import datetime

def get_database_url():
    """Get database URL from environment"""
    return os.getenv('DATABASE_URL')

def upgrade():
    """Create access_certifications table"""
    engine = create_engine(get_database_url())

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS access_certifications (
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

    CREATE INDEX IF NOT EXISTS idx_certifications_employee ON access_certifications(employee_id);
    CREATE INDEX IF NOT EXISTS idx_certifications_due_date ON access_certifications(due_date);
    CREATE INDEX IF NOT EXISTS idx_certifications_status ON access_certifications(status);
    CREATE INDEX IF NOT EXISTS idx_certifications_period ON access_certifications(certification_period);
    """

    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()

    print(f"✓ Created access_certifications table with indexes")

def downgrade():
    """Drop access_certifications table"""
    engine = create_engine(get_database_url())

    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS access_certifications CASCADE;"))
        conn.commit()

    print(f"✓ Dropped access_certifications table")

if __name__ == "__main__":
    print("Running access certifications migration...")
    upgrade()
    print("Migration complete!")
