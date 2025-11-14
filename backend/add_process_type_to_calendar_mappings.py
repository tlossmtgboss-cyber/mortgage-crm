"""
Database Migration: Add process_type to calendar_mappings
Allows calendar mappings for Lead, Loan, and MUM stages
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
    """Add process_type column to calendar_mappings table"""
    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            trans = conn.begin()

            try:
                logger.info("=" * 60)
                logger.info("Adding process_type to calendar_mappings...")
                logger.info("=" * 60)

                # Add process_type column
                conn.execute(text("""
                    ALTER TABLE calendar_mappings
                    ADD COLUMN IF NOT EXISTS process_type VARCHAR DEFAULT 'lead'
                """))

                # Set existing mappings to 'lead' (backward compatibility)
                conn.execute(text("""
                    UPDATE calendar_mappings
                    SET process_type = 'lead'
                    WHERE process_type IS NULL
                """))

                trans.commit()

                logger.info("✅ Migration completed successfully!")
                logger.info("   - Added process_type column")
                logger.info("   - Set existing mappings to 'lead'")
                logger.info("=" * 60)

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
