"""
Database Migration: Add Email Auto-Deletion Support
Adds columns to support automatic deletion of emails after import to CRM
"""
import os
import sys
from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_migration():
    """Add auto_delete_imported_emails and microsoft_message_id columns"""
    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()

            try:
                # 1. Add auto_delete_imported_emails column to microsoft_oauth_tokens table
                logger.info("Adding auto_delete_imported_emails column to microsoft_oauth_tokens...")
                conn.execute(text("""
                    ALTER TABLE microsoft_oauth_tokens
                    ADD COLUMN IF NOT EXISTS auto_delete_imported_emails BOOLEAN DEFAULT FALSE
                """))
                logger.info("✅ Added auto_delete_imported_emails column")

                # 2. Add microsoft_message_id column to incoming_data_events table
                logger.info("Adding microsoft_message_id column to incoming_data_events...")
                conn.execute(text("""
                    ALTER TABLE incoming_data_events
                    ADD COLUMN IF NOT EXISTS microsoft_message_id VARCHAR
                """))
                logger.info("✅ Added microsoft_message_id column")

                # Commit transaction
                trans.commit()
                logger.info("✅ Migration completed successfully!")

                return True

            except Exception as e:
                trans.rollback()
                logger.error(f"❌ Migration failed: {e}")
                raise

    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
