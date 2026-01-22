"""
Migration: Add Phase 3 Tables
Creates tables for:
- Call compliance tracking (consent records, DNC list, violations)
- Webhook automation (endpoints, deliveries)
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

# Detect database type
is_sqlite = DATABASE_URL.startswith("sqlite")


def get_sql_commands():
    """Get SQL commands appropriate for the database type."""

    if is_sqlite:
        # SQLite-compatible syntax
        return [
            # 1. Call Consent Records
            """
            CREATE TABLE IF NOT EXISTS call_consent_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id VARCHAR(100) NOT NULL,
                phone_number VARCHAR(20) NOT NULL,
                state VARCHAR(2) NOT NULL,
                consent_type VARCHAR(20) NOT NULL,
                consent_status VARCHAR(20) NOT NULL,
                disclosure_played BOOLEAN DEFAULT FALSE,
                disclosure_timestamp TIMESTAMP,
                consent_timestamp TIMESTAMP,
                verbal_acknowledgment BOOLEAN DEFAULT FALSE,
                recording_started BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 2. Do-Not-Call List
            """
            CREATE TABLE IF NOT EXISTS do_not_call_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number VARCHAR(20) NOT NULL UNIQUE,
                reason VARCHAR(100),
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                added_by_user_id INTEGER
            );
            """,

            # 3. Compliance Violations
            """
            CREATE TABLE IF NOT EXISTS compliance_violations (
                id VARCHAR(20) PRIMARY KEY,
                violation_type VARCHAR(50) NOT NULL,
                call_id VARCHAR(100),
                phone_number VARCHAR(20),
                description TEXT,
                severity VARCHAR(20),
                state VARCHAR(2),
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE,
                resolution_notes TEXT,
                resolved_at TIMESTAMP,
                resolved_by_user_id INTEGER
            );
            """,

            # 4. Webhook Endpoints
            """
            CREATE TABLE IF NOT EXISTS webhook_endpoints (
                id VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                url TEXT NOT NULL,
                events JSON NOT NULL,
                secret VARCHAR(100),
                status VARCHAR(20) DEFAULT 'active',
                headers JSON,
                organization_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_triggered_at TIMESTAMP,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0
            );
            """,

            # 5. Webhook Deliveries
            """
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id VARCHAR(20) PRIMARY KEY,
                endpoint_id VARCHAR(20) NOT NULL,
                event VARCHAR(50) NOT NULL,
                payload JSON,
                status VARCHAR(20) NOT NULL,
                attempt_count INTEGER DEFAULT 0,
                response_code INTEGER,
                response_body TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                delivered_at TIMESTAMP,
                FOREIGN KEY (endpoint_id) REFERENCES webhook_endpoints(id) ON DELETE CASCADE
            );
            """,

            # Indices
            "CREATE INDEX IF NOT EXISTS idx_consent_call ON call_consent_records(call_id);",
            "CREATE INDEX IF NOT EXISTS idx_consent_phone ON call_consent_records(phone_number);",
            "CREATE INDEX IF NOT EXISTS idx_consent_created ON call_consent_records(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_dnc_phone ON do_not_call_list(phone_number);",
            "CREATE INDEX IF NOT EXISTS idx_violations_type ON compliance_violations(violation_type);",
            "CREATE INDEX IF NOT EXISTS idx_violations_date ON compliance_violations(detected_at);",
            "CREATE INDEX IF NOT EXISTS idx_webhook_endpoint_status ON webhook_endpoints(status);",
            "CREATE INDEX IF NOT EXISTS idx_webhook_delivery_endpoint ON webhook_deliveries(endpoint_id);",
            "CREATE INDEX IF NOT EXISTS idx_webhook_delivery_status ON webhook_deliveries(status);",
            "CREATE INDEX IF NOT EXISTS idx_webhook_delivery_event ON webhook_deliveries(event);",
        ]
    else:
        # PostgreSQL syntax
        return [
            # 1. Call Consent Records
            """
            CREATE TABLE IF NOT EXISTS call_consent_records (
                id SERIAL PRIMARY KEY,
                call_id VARCHAR(100) NOT NULL,
                phone_number VARCHAR(20) NOT NULL,
                state VARCHAR(2) NOT NULL,
                consent_type VARCHAR(20) NOT NULL,
                consent_status VARCHAR(20) NOT NULL,
                disclosure_played BOOLEAN DEFAULT FALSE,
                disclosure_timestamp TIMESTAMP WITH TIME ZONE,
                consent_timestamp TIMESTAMP WITH TIME ZONE,
                verbal_acknowledgment BOOLEAN DEFAULT FALSE,
                recording_started BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 2. Do-Not-Call List
            """
            CREATE TABLE IF NOT EXISTS do_not_call_list (
                id SERIAL PRIMARY KEY,
                phone_number VARCHAR(20) NOT NULL UNIQUE,
                reason VARCHAR(100),
                added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP WITH TIME ZONE,
                added_by_user_id INTEGER REFERENCES users(id)
            );
            """,

            # 3. Compliance Violations
            """
            CREATE TABLE IF NOT EXISTS compliance_violations (
                id VARCHAR(20) PRIMARY KEY,
                violation_type VARCHAR(50) NOT NULL,
                call_id VARCHAR(100),
                phone_number VARCHAR(20),
                description TEXT,
                severity VARCHAR(20),
                state VARCHAR(2),
                detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                resolved BOOLEAN DEFAULT FALSE,
                resolution_notes TEXT,
                resolved_at TIMESTAMP WITH TIME ZONE,
                resolved_by_user_id INTEGER REFERENCES users(id)
            );
            """,

            # 4. Webhook Endpoints
            """
            CREATE TABLE IF NOT EXISTS webhook_endpoints (
                id VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                url TEXT NOT NULL,
                events JSONB NOT NULL,
                secret VARCHAR(100),
                status VARCHAR(20) DEFAULT 'active',
                headers JSONB,
                organization_id INTEGER,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_triggered_at TIMESTAMP WITH TIME ZONE,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0
            );
            """,

            # 5. Webhook Deliveries
            """
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id VARCHAR(20) PRIMARY KEY,
                endpoint_id VARCHAR(20) NOT NULL REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
                event VARCHAR(50) NOT NULL,
                payload JSONB,
                status VARCHAR(20) NOT NULL,
                attempt_count INTEGER DEFAULT 0,
                response_code INTEGER,
                response_body TEXT,
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                delivered_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # Indices
            "CREATE INDEX IF NOT EXISTS idx_consent_call ON call_consent_records(call_id);",
            "CREATE INDEX IF NOT EXISTS idx_consent_phone ON call_consent_records(phone_number);",
            "CREATE INDEX IF NOT EXISTS idx_consent_created ON call_consent_records(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_dnc_phone ON do_not_call_list(phone_number);",
            "CREATE INDEX IF NOT EXISTS idx_violations_type ON compliance_violations(violation_type);",
            "CREATE INDEX IF NOT EXISTS idx_violations_date ON compliance_violations(detected_at);",
            "CREATE INDEX IF NOT EXISTS idx_webhook_endpoint_status ON webhook_endpoints(status);",
            "CREATE INDEX IF NOT EXISTS idx_webhook_delivery_endpoint ON webhook_deliveries(endpoint_id);",
            "CREATE INDEX IF NOT EXISTS idx_webhook_delivery_status ON webhook_deliveries(status);",
            "CREATE INDEX IF NOT EXISTS idx_webhook_delivery_event ON webhook_deliveries(event);",
        ]


def run_migration():
    """Create Phase 3 tables"""
    sql_commands = get_sql_commands()

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"✅ Command {idx} executed successfully")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info(f"⏭️ Command {idx} skipped (already exists)")
                    else:
                        logger.error(f"❌ Error executing command {idx}: {e}")
                    continue

        logger.info("✅ Phase 3 tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  PHASE 3 DATABASE MIGRATION")
    logger.info("  Tables: Compliance, Webhooks")
    logger.info("=" * 60)
    logger.info(f"Database: {'SQLite' if is_sqlite else 'PostgreSQL'}")
    logger.info("")

    success = run_migration()

    if success:
        logger.info("")
        logger.info("=" * 60)
        logger.info("  MIGRATION COMPLETE")
        logger.info("=" * 60)
        logger.info("Tables created:")
        logger.info("  - call_consent_records")
        logger.info("  - do_not_call_list")
        logger.info("  - compliance_violations")
        logger.info("  - webhook_endpoints")
        logger.info("  - webhook_deliveries")
        logger.info("")
    else:
        logger.error("Migration failed!")
        sys.exit(1)
