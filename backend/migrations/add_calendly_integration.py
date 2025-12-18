"""
Database migration for Calendly integration tables.

Creates:
- calendly_integrations: Stores OAuth tokens and integration settings
- calendly_bookings: Tracks bookings made through Calendly

Run: python backend/migrations/add_calendly_integration.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        # Try local SQLite for development
        db_url = "sqlite:///mortgage_crm.db"
    return db_url


def run_migration():
    """Run the Calendly integration migration"""
    db_url = get_database_url()
    engine = create_engine(db_url)

    logger.info("Starting Calendly integration migration...")

    with engine.connect() as conn:
        # Check if tables already exist
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Create calendly_integrations table
        if "calendly_integrations" not in existing_tables:
            logger.info("Creating calendly_integrations table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS calendly_integrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,

                    -- OAuth tokens (encrypted)
                    access_token_encrypted TEXT,
                    refresh_token_encrypted TEXT,
                    token_expires_at TIMESTAMP,

                    -- Calendly user info
                    calendly_user_uri VARCHAR(255),
                    calendly_user_name VARCHAR(255),
                    calendly_user_email VARCHAR(255),
                    calendly_organization_uri VARCHAR(255),

                    -- Integration settings
                    is_connected BOOLEAN DEFAULT FALSE,
                    selected_event_type_uri VARCHAR(255),
                    selected_event_type_name VARCHAR(255),

                    -- Webhook
                    webhook_subscription_uri VARCHAR(255),

                    -- Calendar sync settings
                    sync_to_smart_scheduler BOOLEAN DEFAULT TRUE,
                    auto_create_contacts BOOLEAN DEFAULT TRUE,

                    -- Timestamps
                    connected_at TIMESTAMP,
                    last_sync_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Create index
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_calendly_integrations_user_id
                ON calendly_integrations(user_id)
            """))

            logger.info("calendly_integrations table created")
        else:
            logger.info("calendly_integrations table already exists")

        # Create calendly_bookings table
        if "calendly_bookings" not in existing_tables:
            logger.info("Creating calendly_bookings table...")
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS calendly_bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,

                    -- Calendly event info
                    calendly_event_uri VARCHAR(255) UNIQUE,
                    calendly_event_type_uri VARCHAR(255),

                    -- Event details
                    event_name VARCHAR(255),
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NOT NULL,
                    status VARCHAR(50) DEFAULT 'active',

                    -- Invitee info
                    invitee_name VARCHAR(255),
                    invitee_email VARCHAR(255),
                    invitee_timezone VARCHAR(100),

                    -- Location
                    location_type VARCHAR(50),
                    location_details TEXT,

                    -- Link to Smart Scheduler
                    smart_scheduler_appointment_id VARCHAR(50),

                    -- Tracking
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    canceled_at TIMESTAMP,
                    cancellation_reason TEXT,

                    -- Foreign keys
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))

            # Create indexes
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_calendly_bookings_user_id
                ON calendly_bookings(user_id)
            """))

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_calendly_bookings_event_uri
                ON calendly_bookings(calendly_event_uri)
            """))

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_calendly_bookings_start_time
                ON calendly_bookings(start_time)
            """))

            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_calendly_bookings_smart_scheduler
                ON calendly_bookings(smart_scheduler_appointment_id)
            """))

            logger.info("calendly_bookings table created")
        else:
            logger.info("calendly_bookings table already exists")

        conn.commit()

    logger.info("Calendly integration migration completed successfully!")


# PostgreSQL version for production
POSTGRES_MIGRATION = """
-- Calendly Integration Tables for PostgreSQL
-- Run this migration on your production PostgreSQL database

-- Create calendly_integrations table
CREATE TABLE IF NOT EXISTS calendly_integrations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE,

    -- OAuth tokens (encrypted)
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,

    -- Calendly user info
    calendly_user_uri VARCHAR(255),
    calendly_user_name VARCHAR(255),
    calendly_user_email VARCHAR(255),
    calendly_organization_uri VARCHAR(255),

    -- Integration settings
    is_connected BOOLEAN DEFAULT FALSE,
    selected_event_type_uri VARCHAR(255),
    selected_event_type_name VARCHAR(255),

    -- Webhook
    webhook_subscription_uri VARCHAR(255),

    -- Calendar sync settings
    sync_to_smart_scheduler BOOLEAN DEFAULT TRUE,
    auto_create_contacts BOOLEAN DEFAULT TRUE,

    -- Timestamps
    connected_at TIMESTAMP WITH TIME ZONE,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key
    CONSTRAINT fk_calendly_integrations_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_calendly_integrations_user_id ON calendly_integrations(user_id);

-- Create calendly_bookings table
CREATE TABLE IF NOT EXISTS calendly_bookings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,

    -- Calendly event info
    calendly_event_uri VARCHAR(255) UNIQUE,
    calendly_event_type_uri VARCHAR(255),

    -- Event details
    event_name VARCHAR(255),
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(50) DEFAULT 'active',

    -- Invitee info
    invitee_name VARCHAR(255),
    invitee_email VARCHAR(255),
    invitee_timezone VARCHAR(100),

    -- Location
    location_type VARCHAR(50),
    location_details TEXT,

    -- Link to Smart Scheduler
    smart_scheduler_appointment_id VARCHAR(50),

    -- Tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    canceled_at TIMESTAMP WITH TIME ZONE,
    cancellation_reason TEXT,

    -- Foreign key
    CONSTRAINT fk_calendly_bookings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_calendly_bookings_user_id ON calendly_bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_calendly_bookings_event_uri ON calendly_bookings(calendly_event_uri);
CREATE INDEX IF NOT EXISTS idx_calendly_bookings_start_time ON calendly_bookings(start_time);
CREATE INDEX IF NOT EXISTS idx_calendly_bookings_smart_scheduler ON calendly_bookings(smart_scheduler_appointment_id);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_calendly_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add triggers for updated_at
DROP TRIGGER IF EXISTS calendly_integrations_updated_at ON calendly_integrations;
CREATE TRIGGER calendly_integrations_updated_at
    BEFORE UPDATE ON calendly_integrations
    FOR EACH ROW
    EXECUTE FUNCTION update_calendly_updated_at();

DROP TRIGGER IF EXISTS calendly_bookings_updated_at ON calendly_bookings;
CREATE TRIGGER calendly_bookings_updated_at
    BEFORE UPDATE ON calendly_bookings
    FOR EACH ROW
    EXECUTE FUNCTION update_calendly_updated_at();
"""


def get_postgres_migration_sql():
    """Return the PostgreSQL migration SQL"""
    return POSTGRES_MIGRATION


if __name__ == "__main__":
    run_migration()
