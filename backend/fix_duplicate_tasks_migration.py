"""
Migration script to fix duplicate tasks issue by adding external_message_id column
This prevents the email sync from re-processing the same emails over and over
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set")
    print("Set it with: export DATABASE_URL=your_database_url")
    sys.exit(1)

print("🔧 Fix Duplicate Tasks Migration Script")
print("=" * 70)
print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'local'}")
print("=" * 70)

# Create engine
engine = create_engine(DATABASE_URL)

# SQL statements
MIGRATION_SQL = """
-- Add external_message_id column to incoming_data_events table
ALTER TABLE incoming_data_events
ADD COLUMN IF NOT EXISTS external_message_id VARCHAR;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_incoming_data_events_external_message_id
ON incoming_data_events(external_message_id);

-- Add comment explaining the column
COMMENT ON COLUMN incoming_data_events.external_message_id IS
'External message ID from email provider (Microsoft Graph ID, Gmail ID, etc.) for deduplication';
"""

try:
    print("\n📊 Adding external_message_id column to prevent duplicate task creation...")
    print("\nThis will:")
    print("  1. Add external_message_id column to incoming_data_events table")
    print("  2. Create an index for fast duplicate checking")
    print("  3. Prevent email sync from re-creating deleted tasks")

    with engine.connect() as conn:
        # Execute migration
        conn.execute(text(MIGRATION_SQL))
        conn.commit()

    print("\n✅ Migration completed successfully!")
    print("\n📝 What this fixes:")
    print("  • Email sync will now check if an email was already processed")
    print("  • Duplicate emails will be skipped automatically")
    print("  • Deleted tasks won't reappear from re-processed emails")
    print("  • Auto-sync will only process NEW emails going forward")

    print("\n🎯 Next steps:")
    print("  1. Redeploy backend with updated code")
    print("  2. Existing duplicate events will remain but won't be re-created")
    print("  3. You can manually delete duplicate tasks if needed")
    print("  4. Future email syncs will work correctly")

except Exception as e:
    print(f"\n❌ ERROR: Migration failed")
    print(f"Details: {str(e)}")
    sys.exit(1)
