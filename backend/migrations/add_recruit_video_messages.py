"""
Migration: Add Recruit Video Messages Table

Creates table for storing video messages from recruiters to candidates.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def run_migration():
    """Run the migration to add recruit video messages table."""

    migration_sql = """
    -- Video messages from recruiters to candidates
    CREATE TABLE IF NOT EXISTS recruit_video_messages (
        id SERIAL PRIMARY KEY,
        candidate_id INTEGER NOT NULL,
        recruiter_id INTEGER,
        video_key VARCHAR(500) NOT NULL,
        video_url TEXT,
        message TEXT,
        duration_seconds INTEGER,
        viewed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT fk_video_candidate FOREIGN KEY (candidate_id)
            REFERENCES mm_candidates(id) ON DELETE CASCADE
    );

    -- Create indexes for video messages
    CREATE INDEX IF NOT EXISTS idx_video_messages_candidate
        ON recruit_video_messages(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_video_messages_recruiter
        ON recruit_video_messages(recruiter_id);
    CREATE INDEX IF NOT EXISTS idx_video_messages_created
        ON recruit_video_messages(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_video_messages_unviewed
        ON recruit_video_messages(candidate_id, viewed_at) WHERE viewed_at IS NULL;

    -- Add metadata column to company updates if not exists
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'recruit_company_updates' AND column_name = 'metadata'
        ) THEN
            ALTER TABLE recruit_company_updates ADD COLUMN metadata JSONB DEFAULT '{}';
        END IF;
    END $$;
    """

    with engine.connect() as conn:
        for statement in migration_sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    print(f"Warning: {e}")

        conn.commit()

    print("Migration completed: Recruit video messages table created")


if __name__ == "__main__":
    run_migration()
