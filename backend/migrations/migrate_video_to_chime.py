"""
Migration: Add Amazon Chime SDK columns to video meeting tables

Adds:
- video_meeting_rooms.chime_meeting_id (VARCHAR 255, indexed)
- video_meeting_rooms.chime_media_region (VARCHAR 50, default 'us-east-1')
- meeting_recordings.chime_pipeline_id (VARCHAR 255)
- meeting_recordings.s3_key (VARCHAR 1000)
- Updates meeting_recordings.retention_days default from 90 to 1825 (5 years, TILA/Reg Z)
- Updates existing records with retention_days=90 to 1825

Run: python migrations/migrate_video_to_chime.py
"""

import os
import sys
import logging

# Add parent directory to path so we can import from backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_migration():
    """Run the Chime SDK migration."""
    from sqlalchemy import create_engine, text

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)

    engine = create_engine(database_url)

    migrations = [
        # -- video_meeting_rooms columns --
        {
            "description": "Add chime_meeting_id to video_meeting_rooms",
            "sql": """
                ALTER TABLE video_meeting_rooms
                ADD COLUMN IF NOT EXISTS chime_meeting_id VARCHAR(255);
            """,
        },
        {
            "description": "Add index on chime_meeting_id",
            "sql": """
                CREATE INDEX IF NOT EXISTS ix_video_meeting_rooms_chime_meeting_id
                ON video_meeting_rooms (chime_meeting_id);
            """,
        },
        {
            "description": "Add chime_media_region to video_meeting_rooms",
            "sql": """
                ALTER TABLE video_meeting_rooms
                ADD COLUMN IF NOT EXISTS chime_media_region VARCHAR(50) DEFAULT 'us-east-1';
            """,
        },

        # -- meeting_recordings columns --
        {
            "description": "Add chime_pipeline_id to meeting_recordings",
            "sql": """
                ALTER TABLE meeting_recordings
                ADD COLUMN IF NOT EXISTS chime_pipeline_id VARCHAR(255);
            """,
        },
        {
            "description": "Add s3_key to meeting_recordings",
            "sql": """
                ALTER TABLE meeting_recordings
                ADD COLUMN IF NOT EXISTS s3_key VARCHAR(1000);
            """,
        },

        # -- Update retention_days default --
        {
            "description": "Update retention_days default from 90 to 1825 (5 years)",
            "sql": """
                ALTER TABLE meeting_recordings
                ALTER COLUMN retention_days SET DEFAULT 1825;
            """,
        },
        {
            "description": "Update existing records with retention_days=90 to 1825",
            "sql": """
                UPDATE meeting_recordings
                SET retention_days = 1825
                WHERE retention_days = 90;
            """,
        },
    ]

    with engine.begin() as conn:
        for migration in migrations:
            try:
                logger.info(f"Running: {migration['description']}")
                conn.execute(text(migration["sql"]))
                logger.info(f"  OK: {migration['description']}")
            except Exception as e:
                logger.error(f"  FAILED: {migration['description']}: {e}")
                raise

    logger.info("Migration completed successfully")


if __name__ == "__main__":
    run_migration()
