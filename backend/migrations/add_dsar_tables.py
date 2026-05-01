"""
Add DSAR and Privacy Compliance Tables

Creates:
  - dsar_requests: CCPA/CPRA data subject access request tracking
  - privacy_notice_deliveries: GLBA privacy notice delivery audit trail

Usage:
    python -m migrations.add_dsar_tables
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        # --- dsar_requests ---
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dsar_requests (
                    id VARCHAR(36) PRIMARY KEY,
                    org_id VARCHAR(36) NOT NULL,
                    request_type VARCHAR(20) NOT NULL,
                    requestor_email VARCHAR(255) NOT NULL,
                    requestor_name VARCHAR(255) NOT NULL,
                    requestor_phone VARCHAR(50),
                    identity_verified BOOLEAN DEFAULT FALSE,
                    status VARCHAR(30) NOT NULL DEFAULT 'received',
                    submitted_at TIMESTAMP NOT NULL,
                    deadline TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    response_data TEXT,
                    denial_reason TEXT,
                    processed_by VARCHAR(36),
                    notes TEXT DEFAULT ''
                )
            """))
            logger.info("Created dsar_requests table")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("dsar_requests table already exists")
            else:
                logger.error(f"Failed to create dsar_requests: {e}")

        # --- privacy_notice_deliveries ---
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS privacy_notice_deliveries (
                    id VARCHAR(36) PRIMARY KEY,
                    org_id VARCHAR(36) NOT NULL,
                    borrower_email VARCHAR(255) NOT NULL,
                    notice_version VARCHAR(50) NOT NULL,
                    delivery_method VARCHAR(50) NOT NULL,
                    delivered_at TIMESTAMP NOT NULL
                )
            """))
            logger.info("Created privacy_notice_deliveries table")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("privacy_notice_deliveries table already exists")
            else:
                logger.error(f"Failed to create privacy_notice_deliveries: {e}")

        # --- Indexes ---
        indexes = [
            "CREATE INDEX IF NOT EXISTS ix_dsar_org ON dsar_requests (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_dsar_status ON dsar_requests (status)",
            "CREATE INDEX IF NOT EXISTS ix_dsar_email ON dsar_requests (requestor_email)",
            "CREATE INDEX IF NOT EXISTS ix_dsar_deadline ON dsar_requests (deadline)",
            "CREATE INDEX IF NOT EXISTS ix_pnd_org ON privacy_notice_deliveries (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_pnd_email ON privacy_notice_deliveries (borrower_email)",
        ]
        for idx_sql in indexes:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Index creation issue: {e}")

        conn.commit()

    logger.info("DSAR/privacy migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    if success:
        print("DSAR migration completed successfully")
    else:
        print("DSAR migration failed")
        exit(1)
