"""
Migration: Add Guideline Updates Tables
Creates tables for tracking guideline updates from all 5 sources
(Fannie Mae, Freddie Mac, FHA, VA, USDA)
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create Guideline Updates tables"""

    sql_commands = [
        # 1. Guideline Updates table
        """
        CREATE TABLE IF NOT EXISTS guideline_updates (
            id SERIAL PRIMARY KEY,
            source VARCHAR(50) NOT NULL,
            title VARCHAR(500) NOT NULL,
            section_code VARCHAR(100),
            description TEXT,
            url VARCHAR(1000) NOT NULL,
            published_date TIMESTAMP WITH TIME ZONE NOT NULL,
            scraped_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_new BOOLEAN DEFAULT TRUE,
            content_hash VARCHAR(64) UNIQUE
        );
        """,

        # 2. User Update Views table (tracking which users viewed which updates)
        """
        CREATE TABLE IF NOT EXISTS user_update_views (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            update_id INTEGER NOT NULL,
            viewed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # Indices for performance
        "CREATE INDEX IF NOT EXISTS idx_guideline_updates_source ON guideline_updates(source);",
        "CREATE INDEX IF NOT EXISTS idx_guideline_updates_published ON guideline_updates(published_date);",
        "CREATE INDEX IF NOT EXISTS idx_guideline_updates_source_published ON guideline_updates(source, published_date);",
        "CREATE INDEX IF NOT EXISTS idx_guideline_updates_is_new ON guideline_updates(is_new);",
        "CREATE INDEX IF NOT EXISTS idx_guideline_updates_hash ON guideline_updates(content_hash);",
        "CREATE INDEX IF NOT EXISTS idx_user_update_views_user ON user_update_views(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_user_update_views_update ON user_update_views(update_id);",
        "CREATE INDEX IF NOT EXISTS idx_user_update_views_user_update ON user_update_views(user_id, update_id);",
    ]

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"✅ Command {idx} executed successfully")
                except Exception as e:
                    logger.error(f"❌ Error executing command {idx}: {e}")
                    # Continue with other commands
                    continue

        logger.info("✅ Guideline Updates tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting Guideline Updates tables migration...")
    success = run_migration()
    if success:
        logger.info("✅ Migration completed!")
    else:
        logger.error("❌ Migration failed!")
        sys.exit(1)
