"""
Migration: Add import_history table for tracking data imports
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_connection():
    """Get database connection"""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url)


def run_migration():
    """Run the migration to add import_history table"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Create import_history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS import_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,

                -- File Information
                file_name TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_type TEXT,

                -- Import Statistics
                records_imported INTEGER NOT NULL DEFAULT 0,
                records_total INTEGER NOT NULL DEFAULT 0,
                records_failed INTEGER NOT NULL DEFAULT 0,
                mapping_confidence INTEGER,

                -- Import Details
                table_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('completed', 'partial', 'failed')),
                details JSONB,

                -- Metadata
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_history_user_id
            ON import_history(user_id);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_history_created_at
            ON import_history(created_at DESC);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_history_status
            ON import_history(status);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_import_history_table_name
            ON import_history(table_name);
        """)

        # Create updated_at trigger function if it doesn't exist
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_import_history_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)

        # Create trigger
        cursor.execute("""
            DROP TRIGGER IF EXISTS update_import_history_updated_at ON import_history;
            CREATE TRIGGER update_import_history_updated_at
                BEFORE UPDATE ON import_history
                FOR EACH ROW
                EXECUTE FUNCTION update_import_history_updated_at();
        """)

        # Create summary view
        cursor.execute("""
            CREATE OR REPLACE VIEW import_summary AS
            SELECT
                user_id,
                table_name,
                COUNT(*) as total_imports,
                SUM(records_imported) as total_records_imported,
                SUM(records_failed) as total_records_failed,
                AVG(mapping_confidence) as avg_mapping_confidence,
                MAX(created_at) as last_import_at
            FROM import_history
            WHERE created_at > NOW() - INTERVAL '30 days'
            GROUP BY user_id, table_name;
        """)

        # Add comments
        cursor.execute("""
            COMMENT ON TABLE import_history IS
            'Tracks all data imports with detailed metadata for auditing and analysis';
        """)

        cursor.execute("""
            COMMENT ON COLUMN import_history.details IS
            'Full JSON result including mappings, warnings, and errors from the import process';
        """)

        cursor.execute("""
            COMMENT ON COLUMN import_history.mapping_confidence IS
            'Average confidence percentage of automatic field mappings (0-100)';
        """)

        conn.commit()
        print("Migration completed successfully: import_history table created")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def rollback_migration():
    """Rollback the migration"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("DROP VIEW IF EXISTS import_summary;")
        cursor.execute("DROP TRIGGER IF EXISTS update_import_history_updated_at ON import_history;")
        cursor.execute("DROP FUNCTION IF EXISTS update_import_history_updated_at();")
        cursor.execute("DROP TABLE IF EXISTS import_history;")

        conn.commit()
        print("Rollback completed successfully")

    except Exception as e:
        conn.rollback()
        print(f"Rollback failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migration()
    else:
        run_migration()
