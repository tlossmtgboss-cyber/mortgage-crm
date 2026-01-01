"""
Migration: Add AI Receptionist Tables

Creates the call_logs, call_events, callback_requests, and voice_messages tables
for the AI Receptionist system.

Run with:
    DATABASE_URL="your_database_url" python -m migrations.add_ai_receptionist_tables
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def run_migration():
    """Run the migration to create AI Receptionist tables."""
    print("Running AI Receptionist tables migration...")

    engine = create_engine(DATABASE_URL)

    # Detect database type
    is_postgres = DATABASE_URL.startswith("postgresql")
    is_sqlite = DATABASE_URL.startswith("sqlite")

    with engine.connect() as conn:
        # Create call_logs table
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS call_logs (
                    id SERIAL PRIMARY KEY,
                    call_sid VARCHAR(64) UNIQUE NOT NULL,
                    from_number VARCHAR(32),
                    to_number VARCHAR(32),
                    direction VARCHAR(16) DEFAULT 'inbound',
                    status VARCHAR(32) DEFAULT 'initiated',
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP WITH TIME ZONE,
                    duration_seconds INTEGER,
                    recording_url TEXT,
                    transcript TEXT,
                    sentiment_score DECIMAL(3,2),
                    caller_id INTEGER,
                    loan_officer_id INTEGER,
                    transferred_to INTEGER,
                    transfer_reason TEXT,
                    outcome VARCHAR(64),
                    notes TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS call_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_sid VARCHAR(64) UNIQUE NOT NULL,
                    from_number VARCHAR(32),
                    to_number VARCHAR(32),
                    direction VARCHAR(16) DEFAULT 'inbound',
                    status VARCHAR(32) DEFAULT 'initiated',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    duration_seconds INTEGER,
                    recording_url TEXT,
                    transcript TEXT,
                    sentiment_score REAL,
                    caller_id INTEGER,
                    loan_officer_id INTEGER,
                    transferred_to INTEGER,
                    transfer_reason TEXT,
                    outcome VARCHAR(64),
                    notes TEXT,
                    metadata TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        print("  - call_logs table created/verified")

        # Create call_events table
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS call_events (
                    id SERIAL PRIMARY KEY,
                    call_log_id INTEGER REFERENCES call_logs(id) ON DELETE CASCADE,
                    event_type VARCHAR(64) NOT NULL,
                    event_data JSONB DEFAULT '{}',
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS call_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_log_id INTEGER REFERENCES call_logs(id) ON DELETE CASCADE,
                    event_type VARCHAR(64) NOT NULL,
                    event_data TEXT DEFAULT '{}',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        print("  - call_events table created/verified")

        # Create callback_requests table
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS callback_requests (
                    id SERIAL PRIMARY KEY,
                    call_log_id INTEGER REFERENCES call_logs(id),
                    caller_name VARCHAR(128),
                    caller_phone VARCHAR(32) NOT NULL,
                    reason TEXT,
                    urgency VARCHAR(16) DEFAULT 'normal',
                    assigned_to INTEGER,
                    status VARCHAR(32) DEFAULT 'pending',
                    scheduled_at TIMESTAMP WITH TIME ZONE,
                    completed_at TIMESTAMP WITH TIME ZONE,
                    notes TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS callback_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_log_id INTEGER REFERENCES call_logs(id),
                    caller_name VARCHAR(128),
                    caller_phone VARCHAR(32) NOT NULL,
                    reason TEXT,
                    urgency VARCHAR(16) DEFAULT 'normal',
                    assigned_to INTEGER,
                    status VARCHAR(32) DEFAULT 'pending',
                    scheduled_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        print("  - callback_requests table created/verified")

        # Create voice_messages table
        if is_postgres:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS voice_messages (
                    id SERIAL PRIMARY KEY,
                    call_log_id INTEGER REFERENCES call_logs(id),
                    from_number VARCHAR(32),
                    to_user_id INTEGER,
                    recording_url TEXT,
                    transcript TEXT,
                    duration_seconds INTEGER,
                    is_urgent BOOLEAN DEFAULT false,
                    is_read BOOLEAN DEFAULT false,
                    read_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
        else:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS voice_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_log_id INTEGER REFERENCES call_logs(id),
                    from_number VARCHAR(32),
                    to_user_id INTEGER,
                    recording_url TEXT,
                    transcript TEXT,
                    duration_seconds INTEGER,
                    is_urgent INTEGER DEFAULT 0,
                    is_read INTEGER DEFAULT 0,
                    read_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        print("  - voice_messages table created/verified")

        # Create indexes (PostgreSQL only for some)
        if is_postgres:
            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_call_logs_call_sid ON call_logs(call_sid)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_call_logs_from_number ON call_logs(from_number)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_call_logs_started_at ON call_logs(started_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_call_logs_status ON call_logs(status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_call_events_call_log_id ON call_events(call_log_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_callback_requests_status ON callback_requests(status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_voice_messages_to_user_id ON voice_messages(to_user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_voice_messages_is_read ON voice_messages(is_read)"))
                print("  - Indexes created/verified")
            except ProgrammingError as e:
                print(f"  - Index creation note: {e}")

        conn.commit()

    print("AI Receptionist tables migration completed successfully!")


if __name__ == "__main__":
    run_migration()
