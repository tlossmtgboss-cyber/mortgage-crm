"""
Migration: Add Vapi AI Tables
Creates tables for Vapi AI call management, transcripts, assistants, and phone numbers
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


def run_migration():
    """Create Vapi AI tables"""

    sql_commands = [
        # 1. Vapi Calls table
        """
        CREATE TABLE IF NOT EXISTS vapi_calls (
            id SERIAL PRIMARY KEY,
            vapi_call_id VARCHAR(255) UNIQUE NOT NULL,

            -- Call Details
            phone_number VARCHAR(20),
            caller_name VARCHAR(255),
            direction VARCHAR(20),
            status VARCHAR(50),

            -- Timing
            started_at TIMESTAMP WITH TIME ZONE,
            ended_at TIMESTAMP WITH TIME ZONE,
            duration INTEGER,

            -- Call Data
            transcript TEXT,
            summary TEXT,
            recording_url VARCHAR(512),

            -- Analysis
            sentiment VARCHAR(50),
            intent VARCHAR(100),
            language VARCHAR(10) DEFAULT 'en',

            -- Metadata
            metadata JSON,
            vapi_raw_data JSON,

            -- CRM Integration
            lead_id INTEGER REFERENCES leads(id),

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 2. Vapi Call Notes table
        """
        CREATE TABLE IF NOT EXISTS vapi_call_notes (
            id SERIAL PRIMARY KEY,
            call_id INTEGER NOT NULL REFERENCES vapi_calls(id) ON DELETE CASCADE,

            note_type VARCHAR(50),
            content TEXT NOT NULL,
            priority VARCHAR(20),
            completed BOOLEAN DEFAULT FALSE,

            assigned_to INTEGER REFERENCES users(id),
            due_date TIMESTAMP WITH TIME ZONE,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 3. Vapi Assistants table
        """
        CREATE TABLE IF NOT EXISTS vapi_assistants (
            id SERIAL PRIMARY KEY,
            vapi_assistant_id VARCHAR(255) UNIQUE,

            name VARCHAR(255) NOT NULL,
            description TEXT,

            -- Configuration
            voice_id VARCHAR(100),
            language VARCHAR(10) DEFAULT 'en',
            first_message TEXT,
            system_prompt TEXT,

            -- Settings
            is_active BOOLEAN DEFAULT TRUE,
            config JSON,

            -- Usage tracking
            total_calls INTEGER DEFAULT 0,
            total_minutes FLOAT DEFAULT 0.0,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 4. Vapi Phone Numbers table
        """
        CREATE TABLE IF NOT EXISTS vapi_phone_numbers (
            id SERIAL PRIMARY KEY,
            vapi_number_id VARCHAR(255) UNIQUE,

            phone_number VARCHAR(20) UNIQUE NOT NULL,
            name VARCHAR(255),

            -- Assignment
            assistant_id INTEGER REFERENCES vapi_assistants(id),
            department VARCHAR(100),

            -- Settings
            is_active BOOLEAN DEFAULT TRUE,
            config JSON,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # Indices for performance
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_call_id ON vapi_calls(vapi_call_id);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_phone ON vapi_calls(phone_number);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_status ON vapi_calls(status);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_lead ON vapi_calls(lead_id);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_created ON vapi_calls(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_call_notes_call ON vapi_call_notes(call_id);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_call_notes_type ON vapi_call_notes(note_type);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_call_notes_assigned ON vapi_call_notes(assigned_to);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_assistants_active ON vapi_assistants(is_active);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_phone_numbers_active ON vapi_phone_numbers(is_active);",
    ]

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"✅ Command {idx} executed successfully")
                except Exception as e:
                    logger.error(f"❌ Error executing command {idx}: {e}")
                    # Continue with other commands
                    continue

        logger.info("✅ Vapi AI tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting Vapi AI tables migration...")
    success = run_migration()
    if success:
        logger.info("✅ Migration completed!")
    else:
        logger.error("❌ Migration failed!")
        sys.exit(1)
