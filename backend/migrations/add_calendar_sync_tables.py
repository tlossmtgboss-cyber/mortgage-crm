"""
Migration: Add Calendar Sync Tables
Creates tables for CRM ↔ Salesforce ↔ Outlook calendar synchronization

Tables:
- crm_calendar_events: CRM calendar events
- calendar_event_sync_map: Mapping between CRM and Salesforce events
- calendar_sync_log: Audit log for sync operations
- calendar_sync_settings: Sync configuration settings

Run with: python -m migrations.add_calendar_sync_tables
"""
import os
import sys
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine, SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run the calendar sync tables migration"""
    db = SessionLocal()

    try:
        logger.info("Starting calendar sync tables migration...")

        # ====================================================================
        # Table: crm_calendar_events
        # ====================================================================
        logger.info("Creating crm_calendar_events table...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS crm_calendar_events (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                start_at TIMESTAMP NOT NULL,
                end_at TIMESTAMP NOT NULL,
                timezone VARCHAR(50) DEFAULT 'America/New_York',
                all_day BOOLEAN DEFAULT FALSE,
                location VARCHAR(500),
                notes TEXT,
                owner_user_id INTEGER NOT NULL,
                attendees JSONB DEFAULT '[]',
                related_entity_type VARCHAR(50),
                related_entity_id INTEGER,
                status VARCHAR(20) DEFAULT 'scheduled',
                source_system VARCHAR(20) DEFAULT 'crm',
                last_modified_by_system VARCHAR(20) DEFAULT 'crm',
                last_modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_synced_at TIMESTAMP,
                sync_status VARCHAR(20) DEFAULT 'pending',
                sync_error TEXT,
                fingerprint_hash VARCHAR(64),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create indexes for crm_calendar_events
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_calendar_owner_start
            ON crm_calendar_events(owner_user_id, start_at)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_calendar_sync_status
            ON crm_calendar_events(sync_status)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_calendar_fingerprint
            ON crm_calendar_events(fingerprint_hash)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_calendar_start_at
            ON crm_calendar_events(start_at)
        """))

        logger.info("Created crm_calendar_events table and indexes")

        # ====================================================================
        # Table: calendar_event_sync_map
        # ====================================================================
        logger.info("Creating calendar_event_sync_map table...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS calendar_event_sync_map (
                id SERIAL PRIMARY KEY,
                crm_event_id VARCHAR(36) NOT NULL UNIQUE,
                salesforce_event_id VARCHAR(18) UNIQUE,
                fingerprint_hash VARCHAR(64),
                last_pushed_at TIMESTAMP,
                last_pulled_at TIMESTAMP,
                last_seen_sf_modified_at TIMESTAMP,
                sync_version INTEGER DEFAULT 1,
                lock_token VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_sync_map_event
                    FOREIGN KEY (crm_event_id)
                    REFERENCES crm_calendar_events(id)
                    ON DELETE CASCADE
            )
        """))

        # Create indexes for calendar_event_sync_map
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sync_map_sf_event
            ON calendar_event_sync_map(salesforce_event_id)
        """))

        logger.info("Created calendar_event_sync_map table and indexes")

        # ====================================================================
        # Table: calendar_sync_log
        # ====================================================================
        logger.info("Creating calendar_sync_log table...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS calendar_sync_log (
                id SERIAL PRIMARY KEY,
                crm_event_id VARCHAR(36),
                salesforce_event_id VARCHAR(18),
                user_id INTEGER,
                direction VARCHAR(10) NOT NULL,
                operation VARCHAR(20) NOT NULL,
                fingerprint_before VARCHAR(64),
                fingerprint_after VARCHAR(64),
                result VARCHAR(20) NOT NULL,
                error_message TEXT,
                duration_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create indexes for calendar_sync_log
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sync_log_user
            ON calendar_sync_log(user_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sync_log_created
            ON calendar_sync_log(created_at)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sync_log_crm_event
            ON calendar_sync_log(crm_event_id)
        """))

        logger.info("Created calendar_sync_log table and indexes")

        # ====================================================================
        # Table: calendar_sync_settings
        # ====================================================================
        logger.info("Creating calendar_sync_settings table...")
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS calendar_sync_settings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE,
                calendar_sync_mode VARCHAR(30) DEFAULT 'crm_only',
                conflict_policy VARCHAR(30) DEFAULT 'last_write_wins',
                echo_ignore_window_seconds INTEGER DEFAULT 60,
                sync_sla_seconds INTEGER DEFAULT 60,
                delete_policy VARCHAR(20) DEFAULT 'soft_cancel',
                polling_enabled BOOLEAN DEFAULT FALSE,
                polling_interval_seconds INTEGER DEFAULT 300,
                cdc_enabled BOOLEAN DEFAULT TRUE,
                batch_size INTEGER DEFAULT 200,
                sync_enabled BOOLEAN DEFAULT TRUE,
                sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                default_event_duration_minutes INTEGER DEFAULT 30,
                last_poll_watermark TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Create index for calendar_sync_settings
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_sync_settings_user
            ON calendar_sync_settings(user_id)
        """))

        logger.info("Created calendar_sync_settings table and indexes")

        # ====================================================================
        # Insert default global settings
        # ====================================================================
        logger.info("Inserting default global settings...")
        db.execute(text("""
            INSERT INTO calendar_sync_settings (user_id, calendar_sync_mode, conflict_policy)
            VALUES (NULL, 'crm_only', 'last_write_wins')
            ON CONFLICT DO NOTHING
        """))

        db.commit()
        logger.info("Calendar sync tables migration completed successfully!")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise

    finally:
        db.close()


def rollback_migration():
    """Rollback the calendar sync tables migration"""
    db = SessionLocal()

    try:
        logger.info("Rolling back calendar sync tables...")

        # Drop tables in reverse order (respecting foreign keys)
        db.execute(text("DROP TABLE IF EXISTS calendar_sync_log CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS calendar_sync_settings CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS calendar_event_sync_map CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS crm_calendar_events CASCADE"))

        db.commit()
        logger.info("Rollback completed successfully!")

    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        db.rollback()
        raise

    finally:
        db.close()


def check_migration_status():
    """Check if migration has been applied"""
    db = SessionLocal()

    try:
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'crm_calendar_events'
            )
        """))
        exists = result.scalar()

        if exists:
            # Count records
            event_count = db.execute(text("SELECT COUNT(*) FROM crm_calendar_events")).scalar()
            sync_map_count = db.execute(text("SELECT COUNT(*) FROM calendar_event_sync_map")).scalar()
            log_count = db.execute(text("SELECT COUNT(*) FROM calendar_sync_log")).scalar()

            logger.info("Migration status: APPLIED")
            logger.info(f"  - crm_calendar_events: {event_count} records")
            logger.info(f"  - calendar_event_sync_map: {sync_map_count} records")
            logger.info(f"  - calendar_sync_log: {log_count} records")
            return True
        else:
            logger.info("Migration status: NOT APPLIED")
            return False

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Calendar sync tables migration")
    parser.add_argument(
        "action",
        choices=["up", "down", "status"],
        help="Migration action: up (apply), down (rollback), status (check)"
    )

    args = parser.parse_args()

    if args.action == "up":
        run_migration()
    elif args.action == "down":
        rollback_migration()
    elif args.action == "status":
        check_migration_status()
