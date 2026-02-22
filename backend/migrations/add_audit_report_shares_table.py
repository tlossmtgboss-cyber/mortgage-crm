"""
Audit Report Shares Database Migration
Creates table for managing shareable links for CRM workflow audit reports.

Tables:
- audit_report_shares: Share tokens and tracking for public audit report access
"""

import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")


def run_migration():
    """Run the audit report shares migration."""
    if DATABASE_URL.startswith("postgres"):
        db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    else:
        db_url = DATABASE_URL

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        is_postgres = "postgresql" in db_url

        if is_postgres:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_report_shares (
                    id SERIAL PRIMARY KEY,
                    share_token VARCHAR(100) UNIQUE NOT NULL,
                    report_data JSONB NOT NULL,
                    report_title VARCHAR(255),
                    environment VARCHAR(50),
                    created_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP WITH TIME ZONE,
                    view_count INTEGER DEFAULT 0,
                    last_viewed_at TIMESTAMP WITH TIME ZONE,
                    is_active BOOLEAN DEFAULT true,
                    last_viewer_ip VARCHAR(45),
                    last_viewer_user_agent TEXT
                )
            """))

            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_report_shares_token
                    ON audit_report_shares(share_token);
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_report_shares_active_expires
                    ON audit_report_shares(is_active, expires_at);
            """))

        else:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_report_shares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    share_token VARCHAR(100) UNIQUE NOT NULL,
                    report_data TEXT NOT NULL,
                    report_title VARCHAR(255),
                    environment VARCHAR(50),
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    view_count INTEGER DEFAULT 0,
                    last_viewed_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    last_viewer_ip VARCHAR(45),
                    last_viewer_user_agent TEXT
                )
            """))

            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_audit_report_shares_token
                    ON audit_report_shares(share_token)
            """))

        session.commit()
        logger.info("Audit report shares migration completed successfully")
        return {"success": True, "message": "audit_report_shares table created"}

    except Exception as e:
        session.rollback()
        logger.error(f"Audit report shares migration failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
