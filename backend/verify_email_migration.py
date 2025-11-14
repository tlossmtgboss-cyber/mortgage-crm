"""
Verify Email Auto-Delete Migration
Checks if the email deletion columns were added successfully
"""
import os
import sys
from sqlalchemy import create_engine, inspect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def verify_migration():
    """Check if migration columns exist"""
    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)

        logger.info("=" * 60)
        logger.info("MIGRATION VERIFICATION")
        logger.info("=" * 60)

        # Check microsoft_oauth_tokens table
        logger.info("\n1️⃣  Checking microsoft_oauth_tokens table...")
        if 'microsoft_oauth_tokens' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('microsoft_oauth_tokens')]

            if 'auto_delete_imported_emails' in columns:
                logger.info("   ✅ auto_delete_imported_emails column EXISTS")
                has_auto_delete = True
            else:
                logger.error("   ❌ auto_delete_imported_emails column MISSING")
                has_auto_delete = False
        else:
            logger.error("   ❌ microsoft_oauth_tokens table NOT FOUND")
            has_auto_delete = False

        # Check incoming_data_events table
        logger.info("\n2️⃣  Checking incoming_data_events table...")
        if 'incoming_data_events' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('incoming_data_events')]

            if 'microsoft_message_id' in columns:
                logger.info("   ✅ microsoft_message_id column EXISTS")
                has_message_id = True
            else:
                logger.error("   ❌ microsoft_message_id column MISSING")
                has_message_id = False
        else:
            logger.error("   ❌ incoming_data_events table NOT FOUND")
            has_message_id = False

        # Final result
        logger.info("\n" + "=" * 60)
        if has_auto_delete and has_message_id:
            logger.info("✅ MIGRATION COMPLETE - All columns exist!")
            logger.info("=" * 60)
            return True
        else:
            logger.error("❌ MIGRATION INCOMPLETE - Missing columns")
            logger.info("=" * 60)
            logger.info("\nTo fix, run:")
            logger.info("  python backend/add_email_deletion_columns.py")
            return False

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = verify_migration()
    sys.exit(0 if success else 1)
