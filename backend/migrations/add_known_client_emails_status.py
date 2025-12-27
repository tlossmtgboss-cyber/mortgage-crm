"""Add status column to known_client_emails table

This migration adds the 'status' column that is expected by queries
but was missing from the table definition.

Status values: 'active', 'inactive', 'bounced', 'unsubscribed'
"""
import os
import sys
from sqlalchemy import create_engine, text


def run_migration():
    """Run the migration to add status column to known_client_emails"""
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return False

    print("Connecting to database...")
    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Check if table exists
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'known_client_emails'
        """))

        if not result.fetchone():
            print("Table 'known_client_emails' does not exist - skipping migration")
            return True

        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'known_client_emails' AND column_name = 'status'
        """))

        if result.fetchone():
            print("✓ Column 'status' already exists in known_client_emails table")
        else:
            print("Adding 'status' column to known_client_emails table...")
            conn.execute(text("""
                ALTER TABLE known_client_emails
                ADD COLUMN status VARCHAR(50) DEFAULT 'active'
            """))
            conn.commit()
            print("✓ Successfully added 'status' column")

        # Create index if not exists
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_known_client_emails_status
                ON known_client_emails(status)
            """))
            conn.commit()
            print("✓ Index created/verified")
        except Exception as e:
            print(f"Note: Index may already exist: {e}")

        # Update any NULL values to 'active'
        try:
            conn.execute(text("""
                UPDATE known_client_emails
                SET status = 'active'
                WHERE status IS NULL
            """))
            conn.commit()
            print("✓ Updated NULL status values to 'active'")
        except Exception as e:
            print(f"Note: Update may not be needed: {e}")

    print("Migration complete!")
    return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
