#!/usr/bin/env python3
"""
Migration: Add external_message_id column to incoming_data_events table
This column is needed for email deduplication
"""

import os
import sys
from sqlalchemy import create_engine, text

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

# Fix Railway DATABASE_URL format
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print(f"Connecting to database...")
engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'incoming_data_events'
            AND column_name = 'external_message_id'
        """))

        if result.fetchone():
            print("✅ Column 'external_message_id' already exists")
        else:
            print("Adding 'external_message_id' column...")

            # Add the column
            conn.execute(text("""
                ALTER TABLE incoming_data_events
                ADD COLUMN external_message_id VARCHAR;
            """))

            # Add index for performance
            conn.execute(text("""
                CREATE INDEX idx_incoming_data_events_external_message_id
                ON incoming_data_events(external_message_id);
            """))

            conn.commit()
            print("✅ Successfully added 'external_message_id' column with index")

        # Verify the column exists
        result = conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'incoming_data_events'
            AND column_name = 'external_message_id'
        """))

        column_info = result.fetchone()
        if column_info:
            print(f"\n✅ Column verified:")
            print(f"   Name: {column_info[0]}")
            print(f"   Type: {column_info[1]}")
            print(f"   Nullable: {column_info[2]}")

        print("\n🎉 Migration completed successfully!")

except Exception as e:
    print(f"\n❌ Migration failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
