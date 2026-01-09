"""
Migration: Add Widget Sessions Table
Creates the widget_sessions table for tracking site widget conversations
for lead qualification flows.

Run with: python -m migrations.add_widget_sessions_table

Tables created:
- widget_sessions: Tracks conversational sessions from site widget
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from database import DATABASE_URL


def get_engine():
    """Get database engine."""
    return create_engine(DATABASE_URL)


def is_postgres(engine):
    """Check if database is PostgreSQL."""
    return 'postgresql' in str(engine.url)


def table_exists(engine, table_name: str) -> bool:
    """Check if a table exists."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def run_postgres_migration(conn):
    """Create table for PostgreSQL."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS widget_sessions (
            -- Primary key
            id VARCHAR(36) PRIMARY KEY,

            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Session State
            status VARCHAR(20) DEFAULT 'active',
            current_intent VARCHAR(100),
            qualification_progress VARCHAR(10) DEFAULT '0',

            -- Conversation Data (JSONB for efficient querying)
            conversation_json JSONB DEFAULT '[]'::jsonb,
            extracted_data JSONB DEFAULT '{}'::jsonb,

            -- Attribution
            page_url TEXT,
            utm_source VARCHAR(100),
            utm_campaign VARCHAR(100),
            utm_medium VARCHAR(100),
            utm_term VARCHAR(255),
            utm_content VARCHAR(255),
            referrer TEXT,

            -- Device/Browser Info
            ip_address VARCHAR(45),
            user_agent TEXT,
            device_type VARCHAR(20),
            browser VARCHAR(50),
            os VARCHAR(50),

            -- Dialogflow Reference
            dialogflow_session_id VARCHAR(255),

            -- Conversion Tracking
            lead_id UUID REFERENCES lead_profiles(id),
            converted_at TIMESTAMP,

            -- LO Assignment
            assigned_lo_id VARCHAR(36),

            -- Analytics
            message_count VARCHAR(10) DEFAULT '0',
            fallback_count VARCHAR(10) DEFAULT '0',
            total_duration_seconds VARCHAR(10),
            avg_response_time_ms VARCHAR(10),

            -- Flags
            offered_human_handoff BOOLEAN DEFAULT FALSE,
            human_handoff_requested BOOLEAN DEFAULT FALSE,
            is_test BOOLEAN DEFAULT FALSE
        );
    """))

    # Create indexes for PostgreSQL
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_widget_sessions_status
        ON widget_sessions(status);
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_widget_sessions_created
        ON widget_sessions(created_at DESC);
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_widget_sessions_lead
        ON widget_sessions(lead_id) WHERE lead_id IS NOT NULL;
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_widget_sessions_utm_source
        ON widget_sessions(utm_source) WHERE utm_source IS NOT NULL;
    """))

    # GIN index for JSONB querying
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_widget_sessions_extracted_data
        ON widget_sessions USING GIN (extracted_data);
    """))

    print("  Created PostgreSQL table with JSONB and GIN indexes")


def run_sqlite_migration(conn):
    """Create table for SQLite."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS widget_sessions (
            -- Primary key
            id VARCHAR(36) PRIMARY KEY,

            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Session State
            status VARCHAR(20) DEFAULT 'active',
            current_intent VARCHAR(100),
            qualification_progress VARCHAR(10) DEFAULT '0',

            -- Conversation Data (TEXT for SQLite)
            conversation_json TEXT DEFAULT '[]',
            extracted_data TEXT DEFAULT '{}',

            -- Attribution
            page_url TEXT,
            utm_source VARCHAR(100),
            utm_campaign VARCHAR(100),
            utm_medium VARCHAR(100),
            utm_term VARCHAR(255),
            utm_content VARCHAR(255),
            referrer TEXT,

            -- Device/Browser Info
            ip_address VARCHAR(45),
            user_agent TEXT,
            device_type VARCHAR(20),
            browser VARCHAR(50),
            os VARCHAR(50),

            -- Dialogflow Reference
            dialogflow_session_id VARCHAR(255),

            -- Conversion Tracking
            lead_id VARCHAR(36),
            converted_at TIMESTAMP,

            -- LO Assignment
            assigned_lo_id VARCHAR(36),

            -- Analytics
            message_count VARCHAR(10) DEFAULT '0',
            fallback_count VARCHAR(10) DEFAULT '0',
            total_duration_seconds VARCHAR(10),
            avg_response_time_ms VARCHAR(10),

            -- Flags
            offered_human_handoff BOOLEAN DEFAULT 0,
            human_handoff_requested BOOLEAN DEFAULT 0,
            is_test BOOLEAN DEFAULT 0
        )
    """))

    # Create indexes for SQLite
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_widget_sessions_status
        ON widget_sessions(status)
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_widget_sessions_created
        ON widget_sessions(created_at)
    """))

    print("  Created SQLite table with indexes")


def upgrade():
    """Run the migration."""
    print("\n" + "="*60)
    print("WIDGET SESSIONS TABLE MIGRATION")
    print("="*60 + "\n")

    engine = get_engine()

    # Check if table already exists
    if table_exists(engine, 'widget_sessions'):
        print("Table 'widget_sessions' already exists. Skipping creation.")
        return

    print("Creating widget_sessions table...")

    with engine.begin() as conn:
        if is_postgres(engine):
            run_postgres_migration(conn)
        else:
            run_sqlite_migration(conn)

    print("\n" + "="*60)
    print("MIGRATION COMPLETED SUCCESSFULLY")
    print("="*60 + "\n")


def downgrade():
    """Rollback the migration."""
    print("\n" + "="*60)
    print("ROLLING BACK WIDGET SESSIONS TABLE")
    print("="*60 + "\n")

    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS widget_sessions CASCADE"))

    print("Table 'widget_sessions' dropped successfully.")


def run_migration():
    """Entry point for migration."""
    if len(sys.argv) > 1 and sys.argv[1] == 'downgrade':
        downgrade()
    else:
        upgrade()


if __name__ == '__main__':
    run_migration()
