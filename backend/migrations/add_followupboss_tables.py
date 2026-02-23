"""
Follow Up Boss Integration Tables Migration
Perennia AI - Mortgage CRM

Creates tables for FUB integration:
- fub_user_connections: Per-user API connections
- fub_lead_mappings: FUB person <-> CRM lead mapping
- fub_sync_events: Sync audit log
- fub_stage_mappings: Stage name mappings
"""

import os
import logging
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def run_migration():
    """Run the Follow Up Boss tables migration."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    # Detect database type
    is_sqlite = "sqlite" in database_url.lower()
    is_postgres = "postgresql" in database_url.lower() or "postgres" in database_url.lower()

    logger.info(f"Running FUB migration on {'SQLite' if is_sqlite else 'PostgreSQL'}")

    engine = create_engine(database_url)

    # Define migrations based on database type
    if is_sqlite:
        migrations = get_sqlite_migrations()
    else:
        migrations = get_postgres_migrations()

    success_count = 0
    error_count = 0

    with engine.begin() as connection:
        for name, sql in migrations:
            try:
                connection.execute(text(sql))
                logger.info(f"✅ {name}")
                success_count += 1
            except SQLAlchemyError as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    logger.info(f"⏭️  {name} (already exists)")
                    success_count += 1
                else:
                    logger.error(f"❌ {name}: {e}")
                    error_count += 1

    logger.info(f"Migration complete: {success_count} successful, {error_count} errors")
    return error_count == 0


def get_postgres_migrations():
    """Get PostgreSQL-specific migrations."""
    return [
        ("Create fub_user_connections table", """
            CREATE TABLE IF NOT EXISTS fub_user_connections (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                api_key_encrypted TEXT NOT NULL,
                fub_user_id INTEGER,
                fub_user_email VARCHAR(255),
                fub_user_name VARCHAR(255),
                webhook_secret VARCHAR(64),
                webhook_url VARCHAR(500),
                sync_enabled BOOLEAN DEFAULT TRUE,
                sync_notes BOOLEAN DEFAULT TRUE,
                sync_stages BOOLEAN DEFAULT TRUE,
                sync_lead_updates BOOLEAN DEFAULT TRUE,
                last_sync_at TIMESTAMP WITH TIME ZONE,
                last_sync_status VARCHAR(50),
                last_error TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(user_id)
            )
        """),

        ("Create fub_user_connections index", """
            CREATE INDEX IF NOT EXISTS ix_fub_connections_user_id
            ON fub_user_connections(user_id)
        """),

        ("Create fub_lead_mappings table", """
            CREATE TABLE IF NOT EXISTS fub_lead_mappings (
                id SERIAL PRIMARY KEY,
                connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                fub_person_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                sync_hash VARCHAR(64),
                last_synced_at TIMESTAMP WITH TIME ZONE,
                sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                fub_stage VARCHAR(100),
                fub_assigned_to VARCHAR(255),
                fub_updated_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """),

        ("Create fub_lead_mappings indexes", """
            CREATE INDEX IF NOT EXISTS ix_fub_mappings_connection_person
            ON fub_lead_mappings(connection_id, fub_person_id)
        """),

        ("Create fub_lead_mappings lead index", """
            CREATE INDEX IF NOT EXISTS ix_fub_mappings_lead
            ON fub_lead_mappings(lead_id)
        """),

        ("Create fub_lead_mappings fub_person index", """
            CREATE INDEX IF NOT EXISTS ix_fub_mappings_fub_person
            ON fub_lead_mappings(fub_person_id)
        """),

        ("Create fub_sync_events table", """
            CREATE TABLE IF NOT EXISTS fub_sync_events (
                id SERIAL PRIMARY KEY,
                connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                event_type VARCHAR(50) NOT NULL,
                direction VARCHAR(20) NOT NULL,
                fub_entity_type VARCHAR(50),
                fub_entity_id INTEGER,
                crm_entity_type VARCHAR(50),
                crm_entity_id INTEGER,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                error_message TEXT,
                request_payload JSONB,
                response_payload JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                completed_at TIMESTAMP WITH TIME ZONE
            )
        """),

        ("Create fub_sync_events indexes", """
            CREATE INDEX IF NOT EXISTS ix_fub_events_connection_created
            ON fub_sync_events(connection_id, created_at DESC)
        """),

        ("Create fub_sync_events status index", """
            CREATE INDEX IF NOT EXISTS ix_fub_events_status
            ON fub_sync_events(status)
        """),

        ("Create fub_stage_mappings table", """
            CREATE TABLE IF NOT EXISTS fub_stage_mappings (
                id SERIAL PRIMARY KEY,
                connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                fub_stage_name VARCHAR(100) NOT NULL,
                fub_stage_id INTEGER,
                crm_stage VARCHAR(50) NOT NULL,
                is_auto_mapped BOOLEAN DEFAULT TRUE,
                confidence_score INTEGER DEFAULT 100,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """),

        ("Create fub_stage_mappings index", """
            CREATE INDEX IF NOT EXISTS ix_fub_stages_connection_fub
            ON fub_stage_mappings(connection_id, fub_stage_name)
        """),

        # Add FUB tracking columns to leads table if not exists
        ("Add fub_person_id to leads", """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'leads' AND column_name = 'fub_person_id'
                ) THEN
                    ALTER TABLE leads ADD COLUMN fub_person_id INTEGER;
                END IF;
            END $$;
        """),

        ("Add fub_last_synced_at to leads", """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'leads' AND column_name = 'fub_last_synced_at'
                ) THEN
                    ALTER TABLE leads ADD COLUMN fub_last_synced_at TIMESTAMP WITH TIME ZONE;
                END IF;
            END $$;
        """),

        ("Create leads fub_person_id index", """
            CREATE INDEX IF NOT EXISTS ix_leads_fub_person_id
            ON leads(fub_person_id) WHERE fub_person_id IS NOT NULL
        """),

        ("Add unique constraint on fub_lead_mappings (connection_id, fub_person_id)", """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_fub_mappings_connection_person'
                ) THEN
                    ALTER TABLE fub_lead_mappings
                    ADD CONSTRAINT uq_fub_mappings_connection_person
                    UNIQUE (connection_id, fub_person_id);
                END IF;
            END $$;
        """),
    ]


def get_sqlite_migrations():
    """Get SQLite-specific migrations."""
    return [
        ("Create fub_user_connections table", """
            CREATE TABLE IF NOT EXISTS fub_user_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                api_key_encrypted TEXT NOT NULL,
                fub_user_id INTEGER,
                fub_user_email TEXT,
                fub_user_name TEXT,
                webhook_secret TEXT,
                webhook_url TEXT,
                sync_enabled INTEGER DEFAULT 1,
                sync_notes INTEGER DEFAULT 1,
                sync_stages INTEGER DEFAULT 1,
                sync_lead_updates INTEGER DEFAULT 1,
                last_sync_at TEXT,
                last_sync_status TEXT,
                last_error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """),

        ("Create fub_user_connections index", """
            CREATE INDEX IF NOT EXISTS ix_fub_connections_user_id
            ON fub_user_connections(user_id)
        """),

        ("Create fub_lead_mappings table", """
            CREATE TABLE IF NOT EXISTS fub_lead_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                fub_person_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                sync_hash TEXT,
                last_synced_at TEXT,
                sync_direction TEXT DEFAULT 'bidirectional',
                fub_stage TEXT,
                fub_assigned_to TEXT,
                fub_updated_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """),

        ("Create fub_lead_mappings indexes", """
            CREATE INDEX IF NOT EXISTS ix_fub_mappings_connection_person
            ON fub_lead_mappings(connection_id, fub_person_id)
        """),

        ("Create fub_lead_mappings lead index", """
            CREATE INDEX IF NOT EXISTS ix_fub_mappings_lead
            ON fub_lead_mappings(lead_id)
        """),

        ("Create fub_sync_events table", """
            CREATE TABLE IF NOT EXISTS fub_sync_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                fub_entity_type TEXT,
                fub_entity_id INTEGER,
                crm_entity_type TEXT,
                crm_entity_id INTEGER,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                request_payload TEXT,
                response_payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
        """),

        ("Create fub_sync_events indexes", """
            CREATE INDEX IF NOT EXISTS ix_fub_events_connection_created
            ON fub_sync_events(connection_id, created_at)
        """),

        ("Create fub_stage_mappings table", """
            CREATE TABLE IF NOT EXISTS fub_stage_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                fub_stage_name TEXT NOT NULL,
                fub_stage_id INTEGER,
                crm_stage TEXT NOT NULL,
                is_auto_mapped INTEGER DEFAULT 1,
                confidence_score INTEGER DEFAULT 100,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """),

        ("Create fub_stage_mappings index", """
            CREATE INDEX IF NOT EXISTS ix_fub_stages_connection_fub
            ON fub_stage_mappings(connection_id, fub_stage_name)
        """),
    ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_migration()
    exit(0 if success else 1)
