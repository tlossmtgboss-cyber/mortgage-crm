"""
Migration: Add Stage History Table
Created: 2025-12-03

This migration creates the stage_history table to track all stage/status changes
for leads and loans with timestamps throughout the file process.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create the stage_history table"""
    with engine.connect() as conn:
        # Check if table already exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'stage_history'
            );
        """))
        if result.scalar():
            print("Table 'stage_history' already exists, skipping creation...")
            return

        # Create stage_history table
        conn.execute(text("""
            CREATE TABLE stage_history (
                id SERIAL PRIMARY KEY,
                entity_type VARCHAR NOT NULL,
                entity_id INTEGER NOT NULL,
                lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,
                from_stage VARCHAR,
                to_stage VARCHAR NOT NULL,
                changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                changed_by_id INTEGER REFERENCES users(id),
                notes TEXT,
                duration_in_previous_stage INTEGER
            );
        """))
        print("Created stage_history table")

        # Create indexes
        conn.execute(text("""
            CREATE INDEX ix_stage_history_lead_id ON stage_history(lead_id);
        """))
        conn.execute(text("""
            CREATE INDEX ix_stage_history_loan_id ON stage_history(loan_id);
        """))
        conn.execute(text("""
            CREATE INDEX ix_stage_history_changed_at ON stage_history(changed_at);
        """))
        conn.execute(text("""
            CREATE INDEX ix_stage_history_entity ON stage_history(entity_type, entity_id);
        """))
        print("Created indexes on stage_history table")

        # Add stage_changed_at column to loans table if not exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'loans' AND column_name = 'stage_changed_at'
            );
        """))
        if not result.scalar():
            conn.execute(text("""
                ALTER TABLE loans ADD COLUMN stage_changed_at TIMESTAMP WITH TIME ZONE;
            """))
            print("Added stage_changed_at column to loans table")
        else:
            print("Column 'stage_changed_at' already exists in loans table")

        conn.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
