#!/usr/bin/env python3
"""
Run the database migration to add external_message_id column
"""
import os
from sqlalchemy import create_engine, text

# Get DATABASE_URL from environment (Railway shell will provide this)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL not found")
    exit(1)

# Fix Railway format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print("🔧 Running database migration...")
print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Unknown'}")
print()

engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'incoming_data_events'
            AND column_name = 'external_message_id'
        """))

        if result.fetchone():
            print("✅ Column 'external_message_id' already exists - no migration needed")
        else:
            print("Adding 'external_message_id' column...")

            # Add column
            conn.execute(text("""
                ALTER TABLE incoming_data_events
                ADD COLUMN external_message_id VARCHAR;
            """))

            # Add index
            conn.execute(text("""
                CREATE INDEX idx_incoming_data_events_external_message_id
                ON incoming_data_events(external_message_id);
            """))

            conn.commit()
            print("✅ Successfully added 'external_message_id' column with index")

        print()
        print("🎉 Migration complete!")
        print()
        print("Next step: Go to your CRM → Reconciliation tab → Click 'Sync Emails Now'")

except Exception as e:
    print(f"❌ Migration failed: {e}")
    exit(1)
