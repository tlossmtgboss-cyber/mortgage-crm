"""
Migration: Add lead_conditions table for tracking document/condition needs list.

This table stores conditions (documents needed) for each lead, which mirrors
to the client portal's Needs List.
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")

def run_migration():
    """Create the lead_conditions table."""
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Create lead_conditions table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS lead_conditions (
                id SERIAL PRIMARY KEY,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(100) DEFAULT 'other',
                priority VARCHAR(50) DEFAULT 'required',
                due_date DATE,
                status VARCHAR(50) DEFAULT 'pending',
                is_new BOOLEAN DEFAULT true,
                created_by_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """))

        # Create indexes for efficient queries
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_lead_conditions_lead_id ON lead_conditions(lead_id);
        """))

        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_lead_conditions_status ON lead_conditions(status);
        """))

        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_lead_conditions_category ON lead_conditions(category);
        """))

        session.commit()
        print("Successfully created lead_conditions table and indexes")
        return True

    except Exception as e:
        session.rollback()
        print(f"Error creating lead_conditions table: {e}")
        return False
    finally:
        session.close()


def check_table_exists():
    """Check if the table already exists."""
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        result = session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'lead_conditions'
            );
        """))
        return result.scalar()
    finally:
        session.close()


if __name__ == "__main__":
    if check_table_exists():
        print("lead_conditions table already exists")
    else:
        run_migration()
