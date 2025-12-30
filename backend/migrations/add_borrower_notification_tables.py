"""
Migration: Add Borrower Notification Tables
Creates tables for borrower notification management:
- borrower_notifications: Individual notifications
- borrower_notification_preferences: User notification settings
- borrower_loan_subscriptions: Loan-specific subscriptions

Run with: python migrations/add_borrower_notification_tables.py
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
    """Create borrower notification tables."""
    from sqlalchemy import create_engine, text, inspect

    database_url = get_database_url()
    is_pg = is_postgresql(database_url)

    logger.info(f"Database: {'PostgreSQL' if is_pg else 'SQLite'}")

    engine = create_engine(database_url)

    # Define SQL for both PostgreSQL and SQLite
    if is_pg:
        sql_commands = [
            # Borrower Notifications Table
            """
            CREATE TABLE IF NOT EXISTS borrower_notifications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                borrower_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                category VARCHAR(50) DEFAULT 'general',
                channel VARCHAR(20) DEFAULT 'in_app',
                priority VARCHAR(20) DEFAULT 'medium',
                action_url TEXT,
                metadata JSONB DEFAULT '{}',
                read_at TIMESTAMP WITH TIME ZONE,
                clicked_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT valid_category CHECK (category IN ('general', 'status_update', 'document', 'milestone', 'marketing', 'system')),
                CONSTRAINT valid_channel CHECK (channel IN ('email', 'sms', 'push', 'in_app')),
                CONSTRAINT valid_priority CHECK (priority IN ('critical', 'high', 'medium', 'low', 'info'))
            );
            """,

            # Notification Preferences Table
            """
            CREATE TABLE IF NOT EXISTS borrower_notification_preferences (
                id SERIAL PRIMARY KEY,
                borrower_id INTEGER NOT NULL UNIQUE,
                email_enabled BOOLEAN DEFAULT TRUE,
                sms_enabled BOOLEAN DEFAULT TRUE,
                push_enabled BOOLEAN DEFAULT TRUE,
                status_updates BOOLEAN DEFAULT TRUE,
                document_requests BOOLEAN DEFAULT TRUE,
                milestone_updates BOOLEAN DEFAULT TRUE,
                marketing_updates BOOLEAN DEFAULT FALSE,
                quiet_hours_start VARCHAR(5) DEFAULT '21:00',
                quiet_hours_end VARCHAR(5) DEFAULT '08:00',
                digest_frequency VARCHAR(20) DEFAULT 'immediate',
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT valid_digest_frequency CHECK (digest_frequency IN ('immediate', 'daily', 'weekly'))
            );
            """,

            # Loan Subscriptions Table
            """
            CREATE TABLE IF NOT EXISTS borrower_loan_subscriptions (
                id SERIAL PRIMARY KEY,
                borrower_id INTEGER NOT NULL,
                loan_id INTEGER NOT NULL,
                channel VARCHAR(20) DEFAULT 'all',
                subscribed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                unsubscribed_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT unique_borrower_loan_channel UNIQUE(borrower_id, loan_id, channel)
            );
            """,

            # Indices for performance
            "CREATE INDEX IF NOT EXISTS idx_borrower_notifications_borrower ON borrower_notifications(borrower_id);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_notifications_unread ON borrower_notifications(borrower_id, read_at) WHERE read_at IS NULL;",
            "CREATE INDEX IF NOT EXISTS idx_borrower_notifications_category ON borrower_notifications(category);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_notifications_created ON borrower_notifications(created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_prefs_borrower ON borrower_notification_preferences(borrower_id);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_subs_borrower ON borrower_loan_subscriptions(borrower_id);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_subs_loan ON borrower_loan_subscriptions(loan_id);",
        ]
    else:
        # SQLite version
        sql_commands = [
            """
            CREATE TABLE IF NOT EXISTS borrower_notifications (
                id TEXT PRIMARY KEY,
                borrower_id INTEGER NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                category VARCHAR(50) DEFAULT 'general',
                channel VARCHAR(20) DEFAULT 'in_app',
                priority VARCHAR(20) DEFAULT 'medium',
                action_url TEXT,
                metadata TEXT DEFAULT '{}',
                read_at TIMESTAMP,
                clicked_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            """
            CREATE TABLE IF NOT EXISTS borrower_notification_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                borrower_id INTEGER NOT NULL UNIQUE,
                email_enabled BOOLEAN DEFAULT 1,
                sms_enabled BOOLEAN DEFAULT 1,
                push_enabled BOOLEAN DEFAULT 1,
                status_updates BOOLEAN DEFAULT 1,
                document_requests BOOLEAN DEFAULT 1,
                milestone_updates BOOLEAN DEFAULT 1,
                marketing_updates BOOLEAN DEFAULT 0,
                quiet_hours_start VARCHAR(5) DEFAULT '21:00',
                quiet_hours_end VARCHAR(5) DEFAULT '08:00',
                digest_frequency VARCHAR(20) DEFAULT 'immediate',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            """
            CREATE TABLE IF NOT EXISTS borrower_loan_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                borrower_id INTEGER NOT NULL,
                loan_id INTEGER NOT NULL,
                channel VARCHAR(20) DEFAULT 'all',
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unsubscribed_at TIMESTAMP,
                UNIQUE(borrower_id, loan_id, channel)
            );
            """,

            "CREATE INDEX IF NOT EXISTS idx_borrower_notifications_borrower ON borrower_notifications(borrower_id);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_notifications_category ON borrower_notifications(category);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_notifications_created ON borrower_notifications(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_prefs_borrower ON borrower_notification_preferences(borrower_id);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_subs_borrower ON borrower_loan_subscriptions(borrower_id);",
            "CREATE INDEX IF NOT EXISTS idx_borrower_subs_loan ON borrower_loan_subscriptions(loan_id);",
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
                    logger.info(f"⏭️ Command {i}: Table/index already exists")
                    success_count += 1
                else:
                    logger.error(f"❌ Command {i} failed: {e}")
                    error_count += 1

    logger.info(f"\n{'='*60}")
    logger.info(f"BORROWER NOTIFICATION TABLES MIGRATION COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"✅ Successful: {success_count}")
    logger.info(f"❌ Errors: {error_count}")

    return error_count == 0


if __name__ == "__main__":
    logger.info("Starting Borrower Notification Tables Migration...")
    success = run_migration()
    sys.exit(0 if success else 1)
