"""
Migration: Add PII Audit Log Table

Creates the pii_audit_logs table for tracking access to sensitive data.
Required for GLBA, GDPR, and CCPA compliance.

Run manually or during startup.
"""

import os
import logging
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def run_migration():
    """Create the PII audit log table."""
    try:
        engine = create_engine(DATABASE_URL)
        is_sqlite = DATABASE_URL.startswith("sqlite")
        is_postgres = "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL

        with engine.connect() as conn:
            trans = conn.begin()

            try:
                logger.info("Creating pii_audit_logs table...")

                # Check if table exists (database-agnostic)
                if is_sqlite:
                    result = conn.execute(text("""
                        SELECT name FROM sqlite_master
                        WHERE type='table' AND name='pii_audit_logs'
                    """))
                    exists = result.fetchone() is not None
                else:
                    result = conn.execute(text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = 'pii_audit_logs'
                        )
                    """))
                    exists = result.scalar()

                if exists:
                    logger.info("Table pii_audit_logs already exists, skipping creation")
                    trans.commit()
                    return True

                # Create the table (database-specific SQL)
                if is_sqlite:
                    conn.execute(text("""
                        CREATE TABLE pii_audit_logs (
                            id TEXT PRIMARY KEY,
                            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            user_id INTEGER,
                            user_email TEXT,
                            ip_address TEXT,
                            session_id TEXT,
                            entity_type TEXT NOT NULL,
                            entity_id TEXT NOT NULL,
                            access_type TEXT NOT NULL,
                            fields_accessed TEXT NOT NULL,
                            reason TEXT,
                            request_id TEXT,
                            organization_id TEXT,
                            success INTEGER DEFAULT 1,
                            metadata TEXT
                        )
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE pii_audit_logs (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            user_id INTEGER,
                            user_email VARCHAR(255),
                            ip_address VARCHAR(45),
                            session_id VARCHAR(255),
                            entity_type VARCHAR(50) NOT NULL,
                            entity_id VARCHAR(255) NOT NULL,
                            access_type VARCHAR(20) NOT NULL,
                            fields_accessed TEXT[] NOT NULL,
                            reason TEXT,
                            request_id VARCHAR(255),
                            organization_id VARCHAR(255),
                            success BOOLEAN DEFAULT TRUE,
                            metadata JSONB
                        )
                    """))

                logger.info("Creating indexes...")

                # Create indexes for compliance queries (same syntax for both DBs)
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_pii_audit_entity ON pii_audit_logs(entity_type, entity_id)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_pii_audit_user ON pii_audit_logs(user_id, timestamp)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_pii_audit_time ON pii_audit_logs(timestamp, access_type)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_pii_audit_org_time ON pii_audit_logs(organization_id, timestamp)
                """))

                trans.commit()
                logger.info("✅ PII audit log table created successfully")
                return True

            except Exception as e:
                trans.rollback()
                logger.error(f"Migration failed: {e}")
                raise

    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


if __name__ == "__main__":
    success = run_migration()
    exit(0 if success else 1)
