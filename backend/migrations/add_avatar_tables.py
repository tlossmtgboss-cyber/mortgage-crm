"""
Migration to add AI Avatar system tables.
Enables users to create AI avatars from training videos for automated video generation.
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment."""
    return os.getenv("DATABASE_URL", "sqlite:///./test_avatar.db")


def run_migration():
    """Run the avatar tables migration."""
    from sqlalchemy import create_engine, text

    database_url = get_database_url()
    is_sqlite = database_url.startswith("sqlite")

    engine = create_engine(database_url)

    # SQL for PostgreSQL
    postgres_sql = """
    -- Avatar profiles table
    CREATE TABLE IF NOT EXISTS video_avatar_profiles (
        id SERIAL PRIMARY KEY,
        organization_id INTEGER,
        user_id INTEGER,
        name VARCHAR(255) NOT NULL,
        description TEXT,

        -- Training video
        training_video_url TEXT,
        training_video_duration_seconds FLOAT,
        training_video_size_bytes BIGINT,

        -- Extracted assets
        reference_image_url TEXT,
        voice_sample_url TEXT,
        voice_model_id VARCHAR(255),

        -- Avatar configuration
        default_background VARCHAR(50) DEFAULT 'transparent',
        default_resolution VARCHAR(20) DEFAULT '1080x1920',
        crop_style VARCHAR(50) DEFAULT 'portrait',

        -- Quality settings
        lip_sync_quality VARCHAR(20) DEFAULT 'high',
        voice_similarity FLOAT DEFAULT 0.85,

        -- Status tracking
        status VARCHAR(50) DEFAULT 'pending',
        training_progress INTEGER DEFAULT 0,
        training_started_at TIMESTAMP,
        training_completed_at TIMESTAMP,
        training_error TEXT,

        -- Metadata
        total_videos_generated INTEGER DEFAULT 0,
        total_duration_generated_seconds FLOAT DEFAULT 0,
        last_used_at TIMESTAMP,

        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );

    -- Avatar generation jobs table
    CREATE TABLE IF NOT EXISTS video_avatar_jobs (
        id SERIAL PRIMARY KEY,
        job_id VARCHAR(50) UNIQUE NOT NULL,
        avatar_id INTEGER REFERENCES video_avatar_profiles(id) ON DELETE CASCADE,
        project_id INTEGER,
        scene_id INTEGER,

        -- Input
        script_text TEXT NOT NULL,
        duration_hint_seconds FLOAT,
        emotion VARCHAR(50) DEFAULT 'neutral',
        speaking_rate FLOAT DEFAULT 1.0,

        -- Output
        audio_url TEXT,
        video_url TEXT,
        duration_seconds FLOAT,

        -- Status
        status VARCHAR(50) DEFAULT 'pending',
        progress INTEGER DEFAULT 0,
        current_step VARCHAR(100),
        error_message TEXT,

        -- Timing
        created_at TIMESTAMP DEFAULT NOW(),
        started_at TIMESTAMP,
        completed_at TIMESTAMP,

        -- Resource usage
        voice_generation_ms INTEGER,
        lip_sync_generation_ms INTEGER
    );

    -- Avatar usage analytics
    CREATE TABLE IF NOT EXISTS video_avatar_analytics (
        id SERIAL PRIMARY KEY,
        avatar_id INTEGER REFERENCES video_avatar_profiles(id) ON DELETE CASCADE,
        event_type VARCHAR(50) NOT NULL,
        event_data JSONB,
        created_at TIMESTAMP DEFAULT NOW()
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_avatar_profiles_user ON video_avatar_profiles(user_id);
    CREATE INDEX IF NOT EXISTS idx_avatar_profiles_org ON video_avatar_profiles(organization_id);
    CREATE INDEX IF NOT EXISTS idx_avatar_profiles_status ON video_avatar_profiles(status);
    CREATE INDEX IF NOT EXISTS idx_avatar_jobs_avatar ON video_avatar_jobs(avatar_id);
    CREATE INDEX IF NOT EXISTS idx_avatar_jobs_status ON video_avatar_jobs(status);
    CREATE INDEX IF NOT EXISTS idx_avatar_jobs_job_id ON video_avatar_jobs(job_id);
    CREATE INDEX IF NOT EXISTS idx_avatar_analytics_avatar ON video_avatar_analytics(avatar_id);
    """

    # SQL for SQLite
    sqlite_sql = """
    -- Avatar profiles table
    CREATE TABLE IF NOT EXISTS video_avatar_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_id INTEGER,
        user_id INTEGER,
        name VARCHAR(255) NOT NULL,
        description TEXT,

        -- Training video
        training_video_url TEXT,
        training_video_duration_seconds REAL,
        training_video_size_bytes INTEGER,

        -- Extracted assets
        reference_image_url TEXT,
        voice_sample_url TEXT,
        voice_model_id VARCHAR(255),

        -- Avatar configuration
        default_background VARCHAR(50) DEFAULT 'transparent',
        default_resolution VARCHAR(20) DEFAULT '1080x1920',
        crop_style VARCHAR(50) DEFAULT 'portrait',

        -- Quality settings
        lip_sync_quality VARCHAR(20) DEFAULT 'high',
        voice_similarity REAL DEFAULT 0.85,

        -- Status tracking
        status VARCHAR(50) DEFAULT 'pending',
        training_progress INTEGER DEFAULT 0,
        training_started_at TIMESTAMP,
        training_completed_at TIMESTAMP,
        training_error TEXT,

        -- Metadata
        total_videos_generated INTEGER DEFAULT 0,
        total_duration_generated_seconds REAL DEFAULT 0,
        last_used_at TIMESTAMP,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Avatar generation jobs table
    CREATE TABLE IF NOT EXISTS video_avatar_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id VARCHAR(50) UNIQUE NOT NULL,
        avatar_id INTEGER REFERENCES video_avatar_profiles(id) ON DELETE CASCADE,
        project_id INTEGER,
        scene_id INTEGER,

        -- Input
        script_text TEXT NOT NULL,
        duration_hint_seconds REAL,
        emotion VARCHAR(50) DEFAULT 'neutral',
        speaking_rate REAL DEFAULT 1.0,

        -- Output
        audio_url TEXT,
        video_url TEXT,
        duration_seconds REAL,

        -- Status
        status VARCHAR(50) DEFAULT 'pending',
        progress INTEGER DEFAULT 0,
        current_step VARCHAR(100),
        error_message TEXT,

        -- Timing
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,

        -- Resource usage
        voice_generation_ms INTEGER,
        lip_sync_generation_ms INTEGER
    );

    -- Avatar usage analytics
    CREATE TABLE IF NOT EXISTS video_avatar_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        avatar_id INTEGER REFERENCES video_avatar_profiles(id) ON DELETE CASCADE,
        event_type VARCHAR(50) NOT NULL,
        event_data TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_avatar_profiles_user ON video_avatar_profiles(user_id);
    CREATE INDEX IF NOT EXISTS idx_avatar_profiles_org ON video_avatar_profiles(organization_id);
    CREATE INDEX IF NOT EXISTS idx_avatar_profiles_status ON video_avatar_profiles(status);
    CREATE INDEX IF NOT EXISTS idx_avatar_jobs_avatar ON video_avatar_jobs(avatar_id);
    CREATE INDEX IF NOT EXISTS idx_avatar_jobs_status ON video_avatar_jobs(status);
    CREATE INDEX IF NOT EXISTS idx_avatar_jobs_job_id ON video_avatar_jobs(job_id);
    CREATE INDEX IF NOT EXISTS idx_avatar_analytics_avatar ON video_avatar_analytics(avatar_id);
    """

    sql = sqlite_sql if is_sqlite else postgres_sql

    try:
        with engine.connect() as conn:
            # Execute each statement separately
            for statement in sql.split(';'):
                statement = statement.strip()
                if statement:
                    conn.execute(text(statement))
            conn.commit()

        logger.info("Avatar tables migration completed successfully")
        return {"success": True, "message": "Avatar tables created"}

    except Exception as e:
        logger.error(f"Avatar migration failed: {e}")
        return {"success": False, "error": "Internal server error"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    print(result)
