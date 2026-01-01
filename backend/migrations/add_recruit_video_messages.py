"""
Migration: Add recruit_video_messages table

Creates table for storing video messages sent by recruiters to candidates.

Run with:
    DATABASE_URL="your_database_url" python -m migrations.add_recruit_video_messages
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def run_migration():
    """Run the migration to create recruit_video_messages table."""
    print("Running recruit_video_messages migration...")

    engine = create_engine(DATABASE_URL)

    # Detect database type
    is_postgres = DATABASE_URL.startswith("postgresql")
    is_sqlite = DATABASE_URL.startswith("sqlite")

    with engine.connect() as conn:
        # Create recruit_video_messages table
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS recruit_video_messages (
                    id SERIAL PRIMARY KEY,
                    candidate_id INTEGER NOT NULL,
                    recruiter_id INTEGER,
                    video_key VARCHAR(500),
                    video_url TEXT,
                    message TEXT,
                    duration_seconds INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    viewed_at TIMESTAMP WITH TIME ZONE
                )
            """))
            print("Created recruit_video_messages table")

            # Create indexes
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_recruit_video_messages_candidate
                ON recruit_video_messages(candidate_id)
            """))
            print("Created candidate index")

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_recruit_video_messages_recruiter
                ON recruit_video_messages(recruiter_id)
            """))
            print("Created recruiter index")

        else:
            # SQLite
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS recruit_video_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER NOT NULL,
                    recruiter_id INTEGER,
                    video_key VARCHAR(500),
                    video_url TEXT,
                    message TEXT,
                    duration_seconds INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    viewed_at TIMESTAMP
                )
            """))
            print("Created recruit_video_messages table (SQLite)")

        conn.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    run_migration()
