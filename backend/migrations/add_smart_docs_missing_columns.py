"""
Smart Docs Missing Columns Migration

Adds missing columns to smart_documents table:
1. uploaded_at: When document was uploaded (defaults to created_at)
2. original_filename: Original filename from upload

Run with: python migrations/add_smart_docs_missing_columns.py
"""

import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, text, inspect

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or .env file."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

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


def table_exists(conn, table_name):
    """Check if a table exists."""
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    if not table_exists(conn, table_name):
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def run_migration():
    """Run the migration to add missing columns."""
    database_url = get_database_url()
    print(f"Database URL: {database_url[:30]}...")

    engine = create_engine(database_url)

    with engine.connect() as conn:
        is_pg = is_postgresql(database_url)

        # Check if smart_documents table exists
        if not table_exists(conn, 'smart_documents'):
            print("smart_documents table does not exist, skipping migration")
            return

        # Add uploaded_at column
        if not column_exists(conn, 'smart_documents', 'uploaded_at'):
            print("Adding uploaded_at column to smart_documents...")
            if is_pg:
                conn.execute(text("""
                    ALTER TABLE smart_documents
                    ADD COLUMN uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                """))
                # Copy created_at values to uploaded_at for existing rows
                conn.execute(text("""
                    UPDATE smart_documents
                    SET uploaded_at = created_at
                    WHERE uploaded_at IS NULL
                """))
            else:
                conn.execute(text("""
                    ALTER TABLE smart_documents
                    ADD COLUMN uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
                """))
                conn.execute(text("""
                    UPDATE smart_documents
                    SET uploaded_at = created_at
                    WHERE uploaded_at IS NULL
                """))
            print("  Added uploaded_at column")
        else:
            print("uploaded_at column already exists")

        # Add original_filename column
        if not column_exists(conn, 'smart_documents', 'original_filename'):
            print("Adding original_filename column to smart_documents...")
            if is_pg:
                conn.execute(text("""
                    ALTER TABLE smart_documents
                    ADD COLUMN original_filename VARCHAR(512)
                """))
                # Copy file_name values to original_filename for existing rows
                conn.execute(text("""
                    UPDATE smart_documents
                    SET original_filename = file_name
                    WHERE original_filename IS NULL
                """))
            else:
                conn.execute(text("""
                    ALTER TABLE smart_documents
                    ADD COLUMN original_filename VARCHAR(512)
                """))
                conn.execute(text("""
                    UPDATE smart_documents
                    SET original_filename = file_name
                    WHERE original_filename IS NULL
                """))
            print("  Added original_filename column")
        else:
            print("original_filename column already exists")

        conn.commit()
        print("\nMigration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
