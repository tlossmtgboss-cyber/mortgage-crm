"""
Add eClosing Sessions Table

Creates the eclosing_sessions table for tracking closing sessions with
external eClosing providers (Snapdocs, Pavaso, NotaryCam).

Usage:
    python -m migrations.add_eclosing_table
    # or
    from migrations.add_eclosing_table import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS eclosing_sessions (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    loan_id INTEGER NOT NULL,
    provider VARCHAR(20) NOT NULL DEFAULT 'internal',
    session_id VARCHAR(100),
    closing_type VARCHAR(20) NOT NULL DEFAULT 'hybrid',
    closing_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'created',
    signing_url TEXT,
    notary_type VARCHAR(20),
    notary_scheduled_at TIMESTAMP,
    notary_name VARCHAR(255),
    notary_commission_id VARCHAR(100),
    documents_package JSONB,
    enote_mers_min VARCHAR(18),
    enote_status JSONB,
    completed_at TIMESTAMP,
    completion_notes TEXT,
    recording_number VARCHAR(100),
    recording_date DATE,
    signed_documents_key VARCHAR(1024),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_eclosing_sessions_org_loan ON eclosing_sessions (organization_id, loan_id);",
    "CREATE INDEX IF NOT EXISTS ix_eclosing_sessions_session_id ON eclosing_sessions (session_id);",
    "CREATE INDEX IF NOT EXISTS ix_eclosing_sessions_status ON eclosing_sessions (status);",
    "CREATE INDEX IF NOT EXISTS ix_eclosing_sessions_provider ON eclosing_sessions (provider);",
    "CREATE INDEX IF NOT EXISTS ix_eclosing_sessions_closing_date ON eclosing_sessions (closing_date);",
]


def run_migration(engine=None):
    """Create the eclosing_sessions table and indexes.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, creates one
                from DATABASE_URL environment variable.

    Returns:
        True if migration succeeded, False otherwise.
    """
    if engine is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.error("DATABASE_URL not set")
            return False
        engine = create_engine(database_url)

    is_sqlite = "sqlite" in str(engine.url).lower()

    try:
        with engine.connect() as conn:
            # Create table
            if is_sqlite:
                # SQLite-compatible version (no SERIAL, no JSONB, no IF NOT EXISTS on index)
                sqlite_sql = CREATE_TABLE_SQL.replace("SERIAL", "INTEGER").replace("JSONB", "TEXT")
                conn.execute(text(sqlite_sql))
            else:
                conn.execute(text(CREATE_TABLE_SQL))

            # Create indexes
            for idx_sql in CREATE_INDEXES_SQL:
                try:
                    if is_sqlite:
                        # SQLite uses different IF NOT EXISTS syntax
                        idx_sql = idx_sql.replace("IF NOT EXISTS ", "")
                    conn.execute(text(idx_sql))
                except Exception as e:
                    # Index may already exist
                    logger.debug("Index creation skipped (may already exist): %s", e)

            conn.commit()

        logger.info("eClosing migration complete: eclosing_sessions table created")
        return True

    except Exception as e:
        logger.exception("eClosing migration failed: %s", e)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("Migration successful: eclosing_sessions table created")
    else:
        print("Migration failed -- check logs")
