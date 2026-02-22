"""
Migration: Add call screening tables for spam filtering.

Tables created:
- phone_blocklist: Blocked phone numbers
- phone_whitelist: Known good callers
- call_screening_log: Screening decision audit log
- phone_lookup_cache: Phone Lookup API result cache

Run with: python -m migrations.add_call_screening_tables
"""

import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import SessionLocal, engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Create call screening tables if they don't exist."""
    db = SessionLocal()

    try:
        # Check if tables already exist
        result = db.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('phone_blocklist', 'phone_whitelist', 'call_screening_log', 'phone_lookup_cache')
        """))
        existing_tables = [row[0] for row in result.fetchall()]

        # Create phone_blocklist table
        if 'phone_blocklist' not in existing_tables:
            logger.info("Creating phone_blocklist table...")
            db.execute(text("""
                CREATE TABLE phone_blocklist (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR(20) UNIQUE NOT NULL,
                    reason VARCHAR(100) NOT NULL,
                    source VARCHAR(50) NOT NULL,
                    spam_score INTEGER,
                    blocked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    blocked_by INTEGER REFERENCES users(id),
                    expires_at TIMESTAMP WITH TIME ZONE,
                    is_active BOOLEAN DEFAULT TRUE,
                    call_attempts_since_block INTEGER DEFAULT 0,
                    extra_data JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX idx_blocklist_phone ON phone_blocklist(phone_number)"))
            db.execute(text("CREATE INDEX idx_blocklist_active_expires ON phone_blocklist(is_active, expires_at)"))
            logger.info("phone_blocklist table created")
        else:
            logger.info("phone_blocklist table already exists")

        # Create phone_whitelist table
        if 'phone_whitelist' not in existing_tables:
            logger.info("Creating phone_whitelist table...")
            db.execute(text("""
                CREATE TABLE phone_whitelist (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR(20) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    category VARCHAR(50) NOT NULL,
                    source VARCHAR(50) NOT NULL,
                    lead_id INTEGER REFERENCES leads(id),
                    user_id INTEGER REFERENCES users(id),
                    added_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    added_by INTEGER REFERENCES users(id),
                    notes TEXT,
                    priority INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX idx_whitelist_phone ON phone_whitelist(phone_number)"))
            db.execute(text("CREATE INDEX idx_whitelist_category ON phone_whitelist(category)"))
            logger.info("phone_whitelist table created")
        else:
            logger.info("phone_whitelist table already exists")

        # Create call_screening_log table
        if 'call_screening_log' not in existing_tables:
            logger.info("Creating call_screening_log table...")
            db.execute(text("""
                CREATE TABLE call_screening_log (
                    id SERIAL PRIMARY KEY,
                    call_sid VARCHAR(100) NOT NULL,
                    phone_number VARCHAR(20) NOT NULL,
                    screening_decision VARCHAR(20) NOT NULL,
                    decision_reason VARCHAR(255),
                    lookup_performed BOOLEAN DEFAULT FALSE,
                    lookup_result JSONB,
                    lookup_cost_cents INTEGER,
                    screening_duration_ms INTEGER,
                    caller_stated_name VARCHAR(255),
                    caller_stated_reason TEXT,
                    connected_to_ai BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX idx_screening_call_sid ON call_screening_log(call_sid)"))
            db.execute(text("CREATE INDEX idx_screening_phone ON call_screening_log(phone_number)"))
            db.execute(text("CREATE INDEX idx_screening_decision_date ON call_screening_log(screening_decision, created_at)"))
            db.execute(text("CREATE INDEX idx_screening_created_at ON call_screening_log(created_at)"))
            logger.info("call_screening_log table created")
        else:
            logger.info("call_screening_log table already exists")

        # Create phone_lookup_cache table
        if 'phone_lookup_cache' not in existing_tables:
            logger.info("Creating phone_lookup_cache table...")
            db.execute(text("""
                CREATE TABLE phone_lookup_cache (
                    phone_number VARCHAR(20) PRIMARY KEY,
                    carrier_name VARCHAR(255),
                    carrier_type VARCHAR(50),
                    line_type VARCHAR(50),
                    caller_name VARCHAR(255),
                    caller_type VARCHAR(50),
                    country_code VARCHAR(5),
                    spam_score INTEGER,
                    risk_level VARCHAR(20),
                    lookup_provider VARCHAR(50) DEFAULT 'twilio',
                    lookup_data JSONB,
                    cached_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
            """))
            db.execute(text("CREATE INDEX idx_lookup_cache_expires ON phone_lookup_cache(expires_at)"))
            logger.info("phone_lookup_cache table created")
        else:
            logger.info("phone_lookup_cache table already exists")

        db.commit()
        logger.info("Call screening migration completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def rollback_migration():
    """Drop call screening tables (use with caution)."""
    db = SessionLocal()

    try:
        logger.warning("Rolling back call screening tables...")
        db.execute(text("DROP TABLE IF EXISTS call_screening_log CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS phone_lookup_cache CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS phone_whitelist CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS phone_blocklist CASCADE"))
        db.commit()
        logger.info("Rollback completed")
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        run_migration()
