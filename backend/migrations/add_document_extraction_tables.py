"""
Migration: Add Document Extraction Tables

Creates:
- document_extractions table for storing AI extraction results
- Adds display_name and assigned_owner columns to smart_documents
"""

import logging
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def run_migration(engine):
    """Run the document extraction migration."""

    with engine.connect() as conn:
        # Check if we're using SQLite or PostgreSQL
        dialect = engine.dialect.name
        is_sqlite = dialect == 'sqlite'

        logger.info(f"Running document extraction migration on {dialect}")

        # Create smart_document_extractions table
        if is_sqlite:
            create_extractions_sql = """
                CREATE TABLE IF NOT EXISTS smart_document_extractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    extracted_fields JSON,
                    confidence_scores JSON,
                    provenance JSON,
                    mappable_fields JSON,
                    field_categories JSON,
                    detected_owner VARCHAR(20) DEFAULT 'UNKNOWN',
                    owner_confidence INTEGER,
                    owner_match_details JSON,
                    overall_confidence INTEGER,
                    extraction_model VARCHAR(64),
                    extraction_duration_ms INTEGER,
                    review_status VARCHAR(20) DEFAULT 'PENDING',
                    reviewed_by VARCHAR(100),
                    reviewed_at TIMESTAMP,
                    applied_fields JSON,
                    applied_to_profile_type VARCHAR(20),
                    applied_to_profile_id INTEGER,
                    applied_at TIMESTAMP,
                    extraction_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
        else:
            create_extractions_sql = """
                CREATE TABLE IF NOT EXISTS smart_document_extractions (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    extracted_fields JSONB,
                    confidence_scores JSONB,
                    provenance JSONB,
                    mappable_fields JSONB,
                    field_categories JSONB,
                    detected_owner VARCHAR(20) DEFAULT 'UNKNOWN',
                    owner_confidence INTEGER,
                    owner_match_details JSONB,
                    overall_confidence INTEGER,
                    extraction_model VARCHAR(64),
                    extraction_duration_ms INTEGER,
                    review_status VARCHAR(20) DEFAULT 'PENDING',
                    reviewed_by VARCHAR(100),
                    reviewed_at TIMESTAMP,
                    applied_fields JSONB,
                    applied_to_profile_type VARCHAR(20),
                    applied_to_profile_id INTEGER,
                    applied_at TIMESTAMP,
                    extraction_error TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """

        try:
            conn.execute(text(create_extractions_sql))
            logger.info("Created smart_document_extractions table")
        except Exception as e:
            logger.warning(f"smart_document_extractions table may already exist: {e}")

        # Create indexes for smart_document_extractions
        indexes = [
            ("ix_smart_doc_extractions_document_id", "document_id"),
            ("ix_smart_doc_extractions_review_status", "review_status"),
            ("ix_smart_doc_extractions_detected_owner", "detected_owner"),
            ("ix_smart_doc_extractions_created_at", "created_at"),
        ]

        for index_name, column in indexes:
            try:
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {index_name}
                    ON smart_document_extractions({column})
                """))
                logger.info(f"Created index {index_name}")
            except Exception as e:
                logger.warning(f"Index {index_name} may already exist: {e}")

        # Add columns to smart_documents table if they don't exist
        columns_to_add = [
            ("display_name", "VARCHAR(255)"),
            ("assigned_owner", "VARCHAR(20)"),
        ]

        for col_name, col_type in columns_to_add:
            try:
                # Check if column exists
                if is_sqlite:
                    result = conn.execute(text(
                        "PRAGMA table_info(smart_documents)"
                    ))
                    columns = [row[1] for row in result.fetchall()]
                    if col_name not in columns:
                        conn.execute(text(f"""
                            ALTER TABLE smart_documents
                            ADD COLUMN {col_name} {col_type}
                        """))
                        logger.info(f"Added column {col_name} to smart_documents")
                else:
                    conn.execute(text(f"""
                        ALTER TABLE smart_documents
                        ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                    """))
                    logger.info(f"Added column {col_name} to smart_documents")
            except Exception as e:
                logger.warning(f"Column {col_name} may already exist: {e}")

        conn.commit()
        logger.info("Document extraction migration completed successfully")


if __name__ == "__main__":
    import os
    import sys

    # Add parent directory to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from database import engine

    logging.basicConfig(level=logging.INFO)
    run_migration(engine)
