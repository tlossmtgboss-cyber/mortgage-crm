"""
Add requires_esign column to smart_document_requests table.

Previously the field was accepted by the API but never persisted.

Run with: python migrations/add_requires_esign_column.py
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def get_database_url():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    return line.strip().split('=', 1)[1]
    return None


def run_migration():
    db_url = get_database_url()
    if not db_url:
        logger.error("DATABASE_URL not found")
        return False

    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'smart_document_requests'
            AND column_name = 'requires_esign'
        """))
        if result.fetchone():
            logger.info("requires_esign column already exists — skipping")
            return True

        conn.execute(text("""
            ALTER TABLE smart_document_requests
            ADD COLUMN requires_esign BOOLEAN NOT NULL DEFAULT FALSE
        """))
        conn.commit()
        logger.info("Added requires_esign column to smart_document_requests")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
