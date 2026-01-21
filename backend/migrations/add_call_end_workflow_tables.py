"""
Migration: Add Voice-to-Application Workflow Tables

Adds tables required for the Voice-to-Application feature:
- portal_access_tokens: Magic links for borrower portal access
- portal_document_requirements: Document requirements pushed to borrower portal

The Voice-to-Application workflow converts phone conversations into
complete loan applications automatically.

Run with: python -m migrations.add_call_end_workflow_tables
"""

import os
import logging
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")


def run_migration():
    """Run the migration."""
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set")
        return

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # Check if tables already exist
        result = conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('portal_access_tokens', 'portal_document_requirements')
        """))
        existing_tables = [row[0] for row in result]

        # Create portal_access_tokens table
        if 'portal_access_tokens' not in existing_tables:
            logger.info("Creating portal_access_tokens table...")
            conn.execute(text("""
                CREATE TABLE portal_access_tokens (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    portal_loan_id UUID,
                    borrower_email VARCHAR(255),
                    token VARCHAR(255) UNIQUE NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE,
                    is_used BOOLEAN DEFAULT FALSE,
                    used_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    CONSTRAINT uq_borrower_email UNIQUE (borrower_email)
                )
            """))
            conn.execute(text("""
                CREATE INDEX idx_portal_access_tokens_token ON portal_access_tokens(token)
            """))
            conn.execute(text("""
                CREATE INDEX idx_portal_access_tokens_email ON portal_access_tokens(borrower_email)
            """))
            logger.info("Created portal_access_tokens table")
        else:
            logger.info("portal_access_tokens table already exists")

        # Create portal_document_requirements table
        if 'portal_document_requirements' not in existing_tables:
            logger.info("Creating portal_document_requirements table...")
            conn.execute(text("""
                CREATE TABLE portal_document_requirements (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    portal_loan_id UUID,
                    loan_id UUID,
                    document_type VARCHAR(100) NOT NULL,
                    category VARCHAR(50),
                    description TEXT,
                    instructions TEXT,
                    status VARCHAR(50) DEFAULT 'pending',
                    priority VARCHAR(20) DEFAULT 'medium',
                    source VARCHAR(50),
                    source_id VARCHAR(255),
                    due_date DATE,
                    uploaded_at TIMESTAMP WITH TIME ZONE,
                    approved_at TIMESTAMP WITH TIME ZONE,
                    approved_by UUID,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX idx_portal_doc_reqs_loan ON portal_document_requirements(portal_loan_id)
            """))
            conn.execute(text("""
                CREATE INDEX idx_portal_doc_reqs_status ON portal_document_requirements(status)
            """))
            logger.info("Created portal_document_requirements table")
        else:
            logger.info("portal_document_requirements table already exists")

        # Add completeness columns to call_sessions if not exists
        logger.info("Adding completeness columns to call_sessions...")
        try:
            conn.execute(text("""
                ALTER TABLE call_sessions
                ADD COLUMN IF NOT EXISTS completeness_score DECIMAL(5,4),
                ADD COLUMN IF NOT EXISTS workflow_status VARCHAR(50),
                ADD COLUMN IF NOT EXISTS portal_created_at TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS notifications_sent_at TIMESTAMP WITH TIME ZONE
            """))
            logger.info("Added completeness columns to call_sessions")
        except Exception as e:
            logger.warning(f"Could not add columns (may already exist): {e}")

        # Add source columns to loans if not exists
        logger.info("Adding source columns to loans...")
        try:
            conn.execute(text("""
                ALTER TABLE loans
                ADD COLUMN IF NOT EXISTS source VARCHAR(50),
                ADD COLUMN IF NOT EXISTS source_id VARCHAR(255)
            """))
            logger.info("Added source columns to loans")
        except Exception as e:
            logger.warning(f"Could not add columns (may already exist): {e}")

        # Add category column to tasks if not exists
        logger.info("Adding category column to tasks...")
        try:
            conn.execute(text("""
                ALTER TABLE tasks
                ADD COLUMN IF NOT EXISTS category VARCHAR(50),
                ADD COLUMN IF NOT EXISTS source VARCHAR(50),
                ADD COLUMN IF NOT EXISTS source_id VARCHAR(255)
            """))
            logger.info("Added category column to tasks")
        except Exception as e:
            logger.warning(f"Could not add columns (may already exist): {e}")

        conn.commit()
        logger.info("Migration completed successfully")


if __name__ == "__main__":
    run_migration()
