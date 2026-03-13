"""
Database Migration: Create IRS Transcript Request Table

Creates the irs_transcript_requests table for tracking IRS 4506-C
transcript requests, imports, and income verification comparisons.

Run with: python -m migrations.add_irs_transcript_table

Idempotent - safe to run multiple times.
"""

import os
import sys
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text

logger = logging.getLogger(__name__)

TABLE_NAME = "irs_transcript_requests"

INDEXES = [
    ("ix_irs_transcript_org_loan", TABLE_NAME, "organization_id, loan_id"),
    ("ix_irs_transcript_status", TABLE_NAME, "status"),
    ("ix_irs_transcript_borrower", TABLE_NAME, "borrower_id"),
]


def check_table_exists(engine) -> bool:
    """Check if the irs_transcript_requests table already exists."""
    inspector = inspect(engine)
    return TABLE_NAME in inspector.get_table_names()


def create_table(engine):
    """Create the irs_transcript_requests table."""
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                loan_id INTEGER NOT NULL,
                borrower_id INTEGER NOT NULL,
                tax_years JSONB NOT NULL,
                transcript_type VARCHAR(20) NOT NULL DEFAULT 'tax_return',
                status VARCHAR(20) NOT NULL DEFAULT 'requested',
                vendor VARCHAR(50),
                transcript_data JSONB,
                comparison_result JSONB,
                comparison_passed BOOLEAN,
                requested_by_user_id INTEGER,
                requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                received_at TIMESTAMP WITH TIME ZONE,
                compared_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        conn.commit()
    print(f"  Table '{TABLE_NAME}' created (or already exists)")


def create_indexes(engine):
    """Create indexes for the irs_transcript_requests table."""
    with engine.connect() as conn:
        for index_name, table_name, columns in INDEXES:
            try:
                # Check if index already exists (PostgreSQL)
                result = conn.execute(text(
                    "SELECT 1 FROM pg_indexes WHERE indexname = :idx_name"
                ), {"idx_name": index_name})
                if result.fetchone():
                    print(f"  Index '{index_name}' already exists, skipping...")
                    continue

                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"
                ))
                print(f"  Created index '{index_name}'")
            except Exception as e:
                # Fallback for SQLite or other databases
                try:
                    conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"
                    ))
                    print(f"  Created index '{index_name}'")
                except Exception as e2:
                    print(f"  Warning: Could not create index '{index_name}': {e2}")

        conn.commit()


def run_migration(engine=None):
    """Run the complete migration."""
    if engine is None:
        from database import DATABASE_URL
        print(f"Connecting to database...")
        print(f"Database URL: {DATABASE_URL[:50]}...")
        engine = create_engine(DATABASE_URL)

    # Check current state
    exists = check_table_exists(engine)
    if exists:
        print(f"Table '{TABLE_NAME}' already exists, verifying indexes...")
    else:
        print(f"Creating table '{TABLE_NAME}'...")
        create_table(engine)

    print("Creating indexes...")
    create_indexes(engine)

    # Verify
    if check_table_exists(engine):
        print(f"Migration complete: '{TABLE_NAME}' table ready")
    else:
        print(f"Warning: '{TABLE_NAME}' table creation may have failed")


if __name__ == "__main__":
    run_migration()
