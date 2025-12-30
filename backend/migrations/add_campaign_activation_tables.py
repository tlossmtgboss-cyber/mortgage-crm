"""
Migration: Add Campaign Activation Tables
Creates tables needed for campaign activation:
- campaign_sequence_links: Links acquisition campaigns to outreach sequences
- dialer_queues: Campaign-specific dialer queue configuration
- campaign_tracking: Funnel URL and UTM tracking

Run with: python migrations/add_campaign_activation_tables.py
"""

import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url
    return "sqlite:///./mortgage_crm.db"


def is_postgresql(database_url):
    return database_url.startswith('postgresql') or database_url.startswith('postgres')


def run_migration():
    """Create campaign activation tables."""
    from sqlalchemy import create_engine, text

    database_url = get_database_url()
    is_pg = is_postgresql(database_url)

    logger.info(f"Database: {'PostgreSQL' if is_pg else 'SQLite'}")

    engine = create_engine(database_url)

    if is_pg:
        sql_commands = [
            # Campaign Sequence Links Table
            """
            CREATE TABLE IF NOT EXISTS campaign_sequence_links (
                id SERIAL PRIMARY KEY,
                acquisition_campaign_id VARCHAR(36) NOT NULL,
                outreach_campaign_id VARCHAR(36) NOT NULL,
                sequence_type VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT unique_campaign_sequence UNIQUE(acquisition_campaign_id, outreach_campaign_id, sequence_type),
                CONSTRAINT valid_sequence_type CHECK (sequence_type IN ('sms', 'email', 'voice'))
            );
            """,

            # Dialer Queues Table
            """
            CREATE TABLE IF NOT EXISTS dialer_queues (
                id VARCHAR(36) PRIMARY KEY,
                campaign_id VARCHAR(36) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                priority INTEGER DEFAULT 5,
                max_attempts INTEGER DEFAULT 3,
                call_window_start VARCHAR(5) DEFAULT '09:00',
                call_window_end VARCHAR(5) DEFAULT '20:00',
                status VARCHAR(20) DEFAULT 'active',
                leads_queued INTEGER DEFAULT 0,
                calls_made INTEGER DEFAULT 0,
                connections INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT valid_queue_status CHECK (status IN ('active', 'paused', 'completed', 'archived'))
            );
            """,

            # Campaign Tracking Table
            """
            CREATE TABLE IF NOT EXISTS campaign_tracking (
                id SERIAL PRIMARY KEY,
                campaign_id VARCHAR(36) NOT NULL UNIQUE,
                tracking_code VARCHAR(20) NOT NULL,
                funnel_url TEXT NOT NULL,
                utm_source VARCHAR(100),
                utm_medium VARCHAR(100),
                utm_campaign VARCHAR(255),
                utm_term VARCHAR(255),
                utm_content VARCHAR(255),
                clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # Indices
            "CREATE INDEX IF NOT EXISTS idx_campaign_seq_links_acq ON campaign_sequence_links(acquisition_campaign_id);",
            "CREATE INDEX IF NOT EXISTS idx_campaign_seq_links_out ON campaign_sequence_links(outreach_campaign_id);",
            "CREATE INDEX IF NOT EXISTS idx_dialer_queues_status ON dialer_queues(status);",
            "CREATE INDEX IF NOT EXISTS idx_campaign_tracking_code ON campaign_tracking(tracking_code);",
        ]
    else:
        # SQLite version
        sql_commands = [
            """
            CREATE TABLE IF NOT EXISTS campaign_sequence_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acquisition_campaign_id VARCHAR(36) NOT NULL,
                outreach_campaign_id VARCHAR(36) NOT NULL,
                sequence_type VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(acquisition_campaign_id, outreach_campaign_id, sequence_type)
            );
            """,

            """
            CREATE TABLE IF NOT EXISTS dialer_queues (
                id VARCHAR(36) PRIMARY KEY,
                campaign_id VARCHAR(36) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                priority INTEGER DEFAULT 5,
                max_attempts INTEGER DEFAULT 3,
                call_window_start VARCHAR(5) DEFAULT '09:00',
                call_window_end VARCHAR(5) DEFAULT '20:00',
                status VARCHAR(20) DEFAULT 'active',
                leads_queued INTEGER DEFAULT 0,
                calls_made INTEGER DEFAULT 0,
                connections INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            );
            """,

            """
            CREATE TABLE IF NOT EXISTS campaign_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id VARCHAR(36) NOT NULL UNIQUE,
                tracking_code VARCHAR(20) NOT NULL,
                funnel_url TEXT NOT NULL,
                utm_source VARCHAR(100),
                utm_medium VARCHAR(100),
                utm_campaign VARCHAR(255),
                utm_term VARCHAR(255),
                utm_content VARCHAR(255),
                clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            );
            """,

            "CREATE INDEX IF NOT EXISTS idx_campaign_seq_links_acq ON campaign_sequence_links(acquisition_campaign_id);",
            "CREATE INDEX IF NOT EXISTS idx_campaign_seq_links_out ON campaign_sequence_links(outreach_campaign_id);",
            "CREATE INDEX IF NOT EXISTS idx_dialer_queues_status ON dialer_queues(status);",
            "CREATE INDEX IF NOT EXISTS idx_campaign_tracking_code ON campaign_tracking(tracking_code);",
        ]

    success_count = 0
    error_count = 0

    with engine.connect() as conn:
        for i, sql in enumerate(sql_commands, 1):
            try:
                conn.execute(text(sql))
                conn.commit()
                success_count += 1
                logger.info(f"✅ Command {i}/{len(sql_commands)} executed successfully")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.info(f"⏭️ Command {i}: Already exists")
                    success_count += 1
                else:
                    logger.error(f"❌ Command {i} failed: {e}")
                    error_count += 1

    logger.info(f"\n{'='*60}")
    logger.info(f"CAMPAIGN ACTIVATION TABLES MIGRATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"✅ Successful: {success_count}")
    logger.info(f"❌ Errors: {error_count}")

    return error_count == 0


if __name__ == "__main__":
    logger.info("Starting Campaign Activation Tables Migration...")
    success = run_migration()
    sys.exit(0 if success else 1)
