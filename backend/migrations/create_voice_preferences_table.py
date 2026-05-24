"""Create voice_preferences table for VoiceMemory PostgreSQL backup."""
from sqlalchemy import text


def run_migration(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS voice_preferences (
                cache_key VARCHAR(255) PRIMARY KEY,
                preferences JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_prefs_updated
            ON voice_preferences (updated_at)
        """))
