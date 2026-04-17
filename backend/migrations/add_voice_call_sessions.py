"""
Migration: Add Voice Call Sessions Table

Creates the voice_call_sessions table for persisting Aria in-app voice
conversation data — transcripts, summaries, analytics, and compliance audit.

Run with: python -m migrations.add_voice_call_sessions
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import engine
from sqlalchemy import text


def run_migration():
    """Run the voice call sessions migration."""
    print("=" * 60)
    print("Voice Call Sessions Migration")
    print("=" * 60)

    sql = """
    CREATE TABLE IF NOT EXISTS voice_call_sessions (
        id SERIAL PRIMARY KEY,
        session_uuid VARCHAR(100) UNIQUE NOT NULL,

        -- Ownership
        organization_id INTEGER REFERENCES organizations(id),
        user_id INTEGER NOT NULL REFERENCES users(id),

        -- Session metadata
        direction VARCHAR(20) DEFAULT 'inbound',
        status VARCHAR(30) NOT NULL DEFAULT 'active',
        voice_mode VARCHAR(20) DEFAULT 'websocket',

        -- Timing
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ended_at TIMESTAMPTZ,
        duration_seconds INTEGER,

        -- AI-generated post-call data
        summary TEXT,
        sentiment VARCHAR(20),
        outcome VARCHAR(50),

        -- Tool usage
        tools_executed JSONB,
        tool_count INTEGER DEFAULT 0,

        -- Transcript
        transcript JSONB,
        message_count INTEGER DEFAULT 0,

        -- Voice provider info
        stt_provider VARCHAR(30),
        tts_provider VARCHAR(30),
        tts_voice_id VARCHAR(100),

        -- CRM context
        lead_id INTEGER REFERENCES leads(id),
        loan_id INTEGER REFERENCES loans(id),

        -- Error tracking
        error_message TEXT,

        -- Timestamps
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS ix_voice_call_sessions_session_uuid
        ON voice_call_sessions(session_uuid);
    CREATE INDEX IF NOT EXISTS ix_voice_call_sessions_user_id
        ON voice_call_sessions(user_id);
    CREATE INDEX IF NOT EXISTS ix_voice_call_sessions_user_started
        ON voice_call_sessions(user_id, started_at);
    CREATE INDEX IF NOT EXISTS ix_voice_call_sessions_org_started
        ON voice_call_sessions(organization_id, started_at);
    CREATE INDEX IF NOT EXISTS ix_voice_call_sessions_status
        ON voice_call_sessions(status);
    """

    with engine.connect() as conn:
        for statement in sql.strip().split(";"):
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(text(statement))
                    # Print first line of statement for progress
                    first_line = statement.split("\n")[0].strip()
                    print(f"  OK: {first_line[:70]}")
                except Exception as e:
                    print(f"  SKIP: {e}")
        conn.commit()

    print("\nMigration complete.")


if __name__ == "__main__":
    run_migration()
