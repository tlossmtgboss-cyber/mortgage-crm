"""
Smart Docs SLA Tracking and Client Reminder Settings Migration

Adds:
1. SLA tracking columns to smart_document_requests table:
   - sla_due_at: 3 business days from request creation
   - is_active: For superseding logic
   - superseded_by: FK to replacement request when document expires

2. client_reminder_settings table for per-loan reminder preferences

Run with: python migrations/add_smart_docs_sla.py
"""

import os
import logging
from sqlalchemy import create_engine, text, inspect

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or .env file."""
    # First check environment
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    # Try to load from .env file
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    return line.strip().split('=', 1)[1]

    return "sqlite:///./mortgage_crm.db"


def is_postgresql(database_url):
    """Check if database is PostgreSQL."""
    return database_url.startswith('postgresql') or database_url.startswith('postgres')


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def table_exists(conn, table_name):
    """Check if a table exists."""
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def index_exists(conn, index_name, is_pg=False):
    """Check if an index exists."""
    if is_pg:
        result = conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE indexname = :name"
        ), {"name": index_name})
    else:
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=:name"
        ), {"name": index_name})
    return result.fetchone() is not None


def run_migration():
    """Execute the migration."""
    database_url = get_database_url()
    print(f"Using database: {database_url[:50]}...")  # Truncate for security

    is_pg = is_postgresql(database_url)
    print(f"Database type: {'PostgreSQL' if is_pg else 'SQLite'}")

    engine = create_engine(database_url)

    print("Running Smart Docs SLA migration...")

    with engine.connect() as conn:
        # =========================================================================
        # STEP 1: Add SLA tracking columns to smart_document_requests table
        # =========================================================================

        if not table_exists(conn, 'smart_document_requests'):
            print("WARNING: smart_document_requests table does not exist. Skipping column additions.")
        else:
            # Add sla_due_at column
            if not column_exists(conn, 'smart_document_requests', 'sla_due_at'):
                conn.execute(text(
                    "ALTER TABLE smart_document_requests ADD COLUMN sla_due_at TIMESTAMP"
                ))
                print("  Added sla_due_at column")
            else:
                print("  sla_due_at column already exists")

            # Add is_active column
            if not column_exists(conn, 'smart_document_requests', 'is_active'):
                default_val = "TRUE" if is_pg else "1"
                conn.execute(text(
                    f"ALTER TABLE smart_document_requests ADD COLUMN is_active BOOLEAN DEFAULT {default_val}"
                ))
                print("  Added is_active column")
            else:
                print("  is_active column already exists")

            # Add superseded_by column
            if not column_exists(conn, 'smart_document_requests', 'superseded_by'):
                conn.execute(text(
                    "ALTER TABLE smart_document_requests ADD COLUMN superseded_by INTEGER"
                ))
                print("  Added superseded_by column")
            else:
                print("  superseded_by column already exists")

            # =========================================================================
            # STEP 2: Backfill SLA for existing OPEN/PENDING_REVIEW requests
            # =========================================================================

            # Backfill sla_due_at (5 days from created_at)
            if is_pg:
                backfill_sql = """
                    UPDATE smart_document_requests
                    SET sla_due_at = created_at + INTERVAL '5 days'
                    WHERE sla_due_at IS NULL
                      AND status IN ('OPEN', 'PENDING_REVIEW')
                """
            else:
                backfill_sql = """
                    UPDATE smart_document_requests
                    SET sla_due_at = datetime(created_at, '+5 days')
                    WHERE sla_due_at IS NULL
                      AND status IN ('OPEN', 'PENDING_REVIEW')
                """
            result = conn.execute(text(backfill_sql))
            if result.rowcount > 0:
                print(f"  Backfilled sla_due_at for {result.rowcount} rows")

            # Mark completed requests as inactive
            inactive_val = "FALSE" if is_pg else "0"
            result = conn.execute(text(f"""
                UPDATE smart_document_requests
                SET is_active = {inactive_val}
                WHERE is_active IS NULL
                  AND status IN ('ACCEPTED', 'REJECTED', 'WAIVED')
            """))
            if result.rowcount > 0:
                print(f"  Marked {result.rowcount} completed requests as inactive")

            # Ensure OPEN/PENDING_REVIEW are active
            active_val = "TRUE" if is_pg else "1"
            result = conn.execute(text(f"""
                UPDATE smart_document_requests
                SET is_active = {active_val}
                WHERE is_active IS NULL
                  AND status IN ('OPEN', 'PENDING_REVIEW')
            """))
            if result.rowcount > 0:
                print(f"  Marked {result.rowcount} open requests as active")

        # =========================================================================
        # STEP 3: Create client_reminder_settings table
        # =========================================================================

        if not table_exists(conn, 'client_reminder_settings'):
            if is_pg:
                create_table_sql = """
                    CREATE TABLE client_reminder_settings (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER NOT NULL UNIQUE,
                        reminders_enabled BOOLEAN DEFAULT TRUE,
                        reminder_frequency_hours INTEGER DEFAULT 72,
                        last_reminder_sent_at TIMESTAMP,
                        reminder_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
            else:
                create_table_sql = """
                    CREATE TABLE client_reminder_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        loan_id INTEGER NOT NULL UNIQUE,
                        reminders_enabled BOOLEAN DEFAULT 1,
                        reminder_frequency_hours INTEGER DEFAULT 72,
                        last_reminder_sent_at TIMESTAMP,
                        reminder_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
            conn.execute(text(create_table_sql))
            print("  Created client_reminder_settings table")
        else:
            print("  client_reminder_settings table already exists")

        # =========================================================================
        # STEP 4: Create indexes
        # =========================================================================

        if table_exists(conn, 'smart_document_requests'):
            if not index_exists(conn, 'ix_smart_doc_requests_sla_due', is_pg):
                conn.execute(text(
                    "CREATE INDEX ix_smart_doc_requests_sla_due ON smart_document_requests(sla_due_at)"
                ))
                print("  Created ix_smart_doc_requests_sla_due index")

            if not index_exists(conn, 'ix_smart_doc_requests_is_active', is_pg):
                conn.execute(text(
                    "CREATE INDEX ix_smart_doc_requests_is_active ON smart_document_requests(is_active)"
                ))
                print("  Created ix_smart_doc_requests_is_active index")

        if not index_exists(conn, 'ix_client_reminder_settings_loan_id', is_pg):
            conn.execute(text(
                "CREATE INDEX ix_client_reminder_settings_loan_id ON client_reminder_settings(loan_id)"
            ))
            print("  Created ix_client_reminder_settings_loan_id index")

        if not index_exists(conn, 'ix_client_reminder_due_for_reminder', is_pg):
            conn.execute(text(
                "CREATE INDEX ix_client_reminder_due_for_reminder ON client_reminder_settings(last_reminder_sent_at)"
            ))
            print("  Created ix_client_reminder_due_for_reminder index")

        conn.commit()

    print("\nMigration completed successfully!")
    logger.info("Smart Docs SLA migration completed")


def rollback_migration():
    """Rollback the migration (for development/testing)."""
    database_url = get_database_url()
    engine = create_engine(database_url)

    print("Rolling back Smart Docs SLA migration...")

    with engine.connect() as conn:
        # Drop indexes
        for idx in ['ix_smart_doc_requests_sla_due', 'ix_smart_doc_requests_is_active',
                    'ix_client_reminder_settings_loan_id', 'ix_client_reminder_due_for_reminder']:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))
                print(f"  Dropped index {idx}")
            except Exception as e:
                print(f"  Could not drop index {idx}: {e}")

        # Drop client_reminder_settings table
        conn.execute(text("DROP TABLE IF EXISTS client_reminder_settings"))
        print("  Dropped client_reminder_settings table")

        # Note: SQLite doesn't support DROP COLUMN, would need table recreation
        print("  Note: SLA columns in smart_document_requests cannot be dropped in SQLite")

        conn.commit()

    print("Rollback completed!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        run_migration()
