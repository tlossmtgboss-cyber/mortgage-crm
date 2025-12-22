"""
Migration: Add content_json and branding_json columns to microsites table
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)

def run_migration():
    """Add content_json and branding_json columns to microsites table."""

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'microsites'
            AND column_name IN ('content_json', 'branding_json')
        """))
        existing_columns = [row[0] for row in result.fetchall()]

        if 'content_json' not in existing_columns:
            logger.info("Adding content_json column to microsites table...")
            conn.execute(text("""
                ALTER TABLE microsites
                ADD COLUMN content_json JSONB DEFAULT '{}'::jsonb
            """))
            logger.info("content_json column added successfully")
        else:
            logger.info("content_json column already exists")

        if 'branding_json' not in existing_columns:
            logger.info("Adding branding_json column to microsites table...")
            conn.execute(text("""
                ALTER TABLE microsites
                ADD COLUMN branding_json JSONB DEFAULT '{}'::jsonb
            """))
            logger.info("branding_json column added successfully")
        else:
            logger.info("branding_json column already exists")

        conn.commit()
        logger.info("Migration completed successfully")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
