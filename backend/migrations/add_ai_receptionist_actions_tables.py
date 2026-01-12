"""
Migration: Add AI Receptionist Actions Tables
Creates tables for appointments, call transfers, and voice messages
scheduled by the AI receptionist.
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(db):
    """Create AI receptionist action tables"""

    migrations = [
        # Appointments table
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            caller_name VARCHAR(255),
            caller_phone VARCHAR(50),
            appointment_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
            reason TEXT,
            status VARCHAR(50) DEFAULT 'scheduled',  -- scheduled, confirmed, cancelled, completed
            assigned_to INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            call_sid VARCHAR(100),
            notes TEXT,
            reminder_sent BOOLEAN DEFAULT FALSE,
            google_calendar_event_id VARCHAR(255),
            outlook_event_id VARCHAR(255)
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_appointments_datetime ON appointments(appointment_datetime);",
        "CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);",
        "CREATE INDEX IF NOT EXISTS idx_appointments_caller_phone ON appointments(caller_phone);",

        # Call transfers table
        """
        CREATE TABLE IF NOT EXISTS call_transfers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            caller_name VARCHAR(255),
            caller_phone VARCHAR(50),
            transfer_reason TEXT,
            urgency VARCHAR(20) DEFAULT 'medium',  -- low, medium, high
            status VARCHAR(50) DEFAULT 'requested',  -- requested, transferred, failed, completed
            transferred_to INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            completed_at TIMESTAMP WITH TIME ZONE,
            call_sid VARCHAR(100),
            transfer_duration_seconds INTEGER
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_call_transfers_status ON call_transfers(status);",
        "CREATE INDEX IF NOT EXISTS idx_call_transfers_created ON call_transfers(created_at);",

        # Voice messages table
        """
        CREATE TABLE IF NOT EXISTS voice_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            caller_name VARCHAR(255),
            caller_phone VARCHAR(50),
            message TEXT NOT NULL,
            callback_urgency VARCHAR(20) DEFAULT 'today',  -- urgent, today, this_week
            status VARCHAR(50) DEFAULT 'new',  -- new, read, callback_scheduled, resolved
            assigned_to INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            read_at TIMESTAMP WITH TIME ZONE,
            resolved_at TIMESTAMP WITH TIME ZONE,
            resolved_by INTEGER REFERENCES users(id),
            call_sid VARCHAR(100),
            transcription TEXT,
            recording_url TEXT
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_voice_messages_status ON voice_messages(status);",
        "CREATE INDEX IF NOT EXISTS idx_voice_messages_urgency ON voice_messages(callback_urgency);",
        "CREATE INDEX IF NOT EXISTS idx_voice_messages_created ON voice_messages(created_at);",
    ]

    for sql in migrations:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception as e:
            logger.warning(f"Migration statement skipped (may already exist): {e}")
            db.rollback()

    logger.info("AI receptionist actions tables migration completed")


if __name__ == "__main__":
    from database import get_db
    db = next(get_db())
    run_migration(db)
    print("Migration completed successfully")
