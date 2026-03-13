"""
Add Document Processing Cache Table

Creates the document_processing_cache table for hash-based AI result caching.
Supports classification, OCR, and review result caching with TTL expiration
and tenant isolation.

Usage:
    python -m migrations.add_document_cache_table
    # or
    from migrations.add_document_cache_table import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


CREATE_TABLE_PG = """
CREATE TABLE IF NOT EXISTS document_processing_cache (
    id VARCHAR(36) PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    document_hash VARCHAR(64) NOT NULL,
    cache_type VARCHAR(20) NOT NULL,
    result_data JSONB NOT NULL,
    model_version VARCHAR(50),
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_doc_cache_org_hash_type UNIQUE (organization_id, document_hash, cache_type)
);

CREATE INDEX IF NOT EXISTS ix_doc_cache_org_id
    ON document_processing_cache (organization_id);

CREATE INDEX IF NOT EXISTS ix_doc_cache_hash
    ON document_processing_cache (document_hash);

CREATE INDEX IF NOT EXISTS ix_doc_cache_expires
    ON document_processing_cache (expires_at);

CREATE INDEX IF NOT EXISTS ix_doc_cache_lookup
    ON document_processing_cache (organization_id, document_hash, cache_type);
"""

CREATE_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS document_processing_cache (
    id VARCHAR(36) PRIMARY KEY,
    organization_id INTEGER NOT NULL,
    document_hash VARCHAR(64) NOT NULL,
    cache_type VARCHAR(20) NOT NULL,
    result_data JSON NOT NULL,
    model_version VARCHAR(50),
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    UNIQUE (organization_id, document_hash, cache_type)
);
"""


def run_migration():
    """Create the document_processing_cache table."""
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    try:
        with engine.connect() as conn:
            if is_sqlite:
                conn.execute(text(CREATE_TABLE_SQLITE))
            else:
                # Execute each statement separately for PostgreSQL
                for stmt in CREATE_TABLE_PG.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(text(stmt))

            conn.commit()
            logger.info("document_processing_cache table created successfully")
            return True

    except Exception as e:
        logger.exception("Migration failed: %s", e)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("Migration completed successfully")
    else:
        print("Migration failed")
