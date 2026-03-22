"""
Add SMS Persistence Tables

Creates database tables for persistent SMS campaign and scheduled job state:
  - sms_campaign_records: Stores campaign config, status, and stats
  - scheduled_sms_job_records: Stores scheduled SMS jobs with execution state

These back the in-memory dicts in sms_campaign_manager.py and sms_scheduler.py.

Usage:
    python -m migrations.add_sms_persistence_tables
    # or
    from migrations.add_sms_persistence_tables import run_migration
    run_migration()
"""

import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Create sms_campaign_records and scheduled_sms_job_records tables."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    with engine.connect() as conn:
        # -------------------------------------------------------------------
        # 1. Create sms_campaign_records table
        # -------------------------------------------------------------------
        logger.info("Creating sms_campaign_records table...")
        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS sms_campaign_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        campaign_id VARCHAR(100) NOT NULL UNIQUE,
                        organization_id INTEGER,
                        user_id INTEGER,
                        name VARCHAR(255),
                        status VARCHAR(50) DEFAULT 'active',
                        campaign_config TEXT,
                        total_recipients INTEGER DEFAULT 0,
                        sent_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        FOREIGN KEY (organization_id) REFERENCES organizations(id),
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS sms_campaign_records (
                        id SERIAL PRIMARY KEY,
                        campaign_id VARCHAR(100) NOT NULL UNIQUE,
                        organization_id INTEGER REFERENCES organizations(id),
                        user_id INTEGER REFERENCES users(id),
                        name VARCHAR(255),
                        status VARCHAR(50) DEFAULT 'active',
                        campaign_config JSONB,
                        total_recipients INTEGER DEFAULT 0,
                        sent_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        completed_at TIMESTAMPTZ
                    )
                """))

            # Create indexes
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_campaign_records_campaign_id "
                "ON sms_campaign_records (campaign_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_campaign_records_organization_id "
                "ON sms_campaign_records (organization_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_sms_campaign_records_status "
                "ON sms_campaign_records (status)"
            ))

            conn.commit()
            logger.info("  sms_campaign_records table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  sms_campaign_records table already exists")
            else:
                logger.error(f"Failed to create sms_campaign_records table: {e}")

        # -------------------------------------------------------------------
        # 2. Create scheduled_sms_job_records table
        # -------------------------------------------------------------------
        logger.info("Creating scheduled_sms_job_records table...")
        try:
            if is_sqlite:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS scheduled_sms_job_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id VARCHAR(100) NOT NULL UNIQUE,
                        organization_id INTEGER,
                        user_id INTEGER,
                        phone_number VARCHAR(20),
                        message TEXT,
                        status VARCHAR(50) DEFAULT 'pending',
                        scheduled_for TIMESTAMP,
                        job_config TEXT,
                        result TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        executed_at TIMESTAMP,
                        FOREIGN KEY (organization_id) REFERENCES organizations(id),
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS scheduled_sms_job_records (
                        id SERIAL PRIMARY KEY,
                        job_id VARCHAR(100) NOT NULL UNIQUE,
                        organization_id INTEGER REFERENCES organizations(id),
                        user_id INTEGER REFERENCES users(id),
                        phone_number VARCHAR(20),
                        message TEXT,
                        status VARCHAR(50) DEFAULT 'pending',
                        scheduled_for TIMESTAMPTZ,
                        job_config JSONB,
                        result JSONB,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        executed_at TIMESTAMPTZ
                    )
                """))

            # Create indexes
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scheduled_sms_job_records_job_id "
                "ON scheduled_sms_job_records (job_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scheduled_sms_job_records_organization_id "
                "ON scheduled_sms_job_records (organization_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_scheduled_sms_job_records_status "
                "ON scheduled_sms_job_records (status)"
            ))

            conn.commit()
            logger.info("  scheduled_sms_job_records table created successfully")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str:
                logger.info("  scheduled_sms_job_records table already exists")
            else:
                logger.error(f"Failed to create scheduled_sms_job_records table: {e}")

    logger.info("SMS persistence migration complete")
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
