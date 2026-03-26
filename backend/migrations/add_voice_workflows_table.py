"""
Migration: Add Voice Workflows Table
Creates the voice_workflows table for persistent state machine tracking
of multi-step voice command workflows (e.g., schedule-via-SMS).
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Create the voice_workflows table with all columns and indexes."""

    if engine is None:
        database_url = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(database_url)

    sql_commands = [
        # 1. Create the voice_workflows table
        """
        CREATE TABLE IF NOT EXISTS voice_workflows (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,

            -- Workflow type and state (VARCHAR, not PG enum)
            workflow_type VARCHAR(50) NOT NULL,
            state VARCHAR(30) NOT NULL DEFAULT 'initiated',

            -- Contact info
            contact_name VARCHAR(255),
            contact_phone VARCHAR(20),
            contact_email VARCHAR(255),
            lead_id INTEGER,

            -- Scheduling context
            meeting_type VARCHAR(50) DEFAULT 'discovery_call',
            meeting_duration_minutes INTEGER DEFAULT 30,
            message_context TEXT,

            -- Conversation tracking
            -- Schema: [{"role": "system"|"user"|"assistant"|"contact", "content": str, "timestamp": str (ISO 8601)}]
            conversation_history JSONB NOT NULL DEFAULT '[]'::jsonb,
            turn_count INTEGER DEFAULT 0,
            max_turns INTEGER DEFAULT 8,

            -- Confirmed scheduling details
            confirmed_datetime TIMESTAMP,
            appointment_id INTEGER,  -- references smart_scheduler appointments (no FK: UUID PK, may not exist)

            -- Slot proposals sent to contact
            proposed_slots JSONB DEFAULT '[]'::jsonb,

            -- Lifecycle
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            completed_at TIMESTAMP,

            -- Error tracking
            error_message TEXT,
            last_sms_sent_at TIMESTAMP,
            last_sms_received_at TIMESTAMP
        );
        """,

        # 2. Single-column indexes (matching model's index=True declarations)
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_organization_id ON voice_workflows(organization_id);",
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_user_id ON voice_workflows(user_id);",
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_contact_phone ON voice_workflows(contact_phone);",

        # 3. Composite and named indexes (from __table_args__)
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_phone_state ON voice_workflows(contact_phone, state);",
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_org_user ON voice_workflows(organization_id, user_id);",
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_expires ON voice_workflows(expires_at);",

        # 4. FK constraint: organization_id -> organizations(id) (idempotent)
        """
        DO $$ BEGIN
            ALTER TABLE voice_workflows ADD CONSTRAINT fk_voice_workflows_organization
                FOREIGN KEY (organization_id) REFERENCES organizations(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,

        # 5. FK constraint: user_id -> users(id) (idempotent)
        """
        DO $$ BEGIN
            ALTER TABLE voice_workflows ADD CONSTRAINT fk_voice_workflows_user
                FOREIGN KEY (user_id) REFERENCES users(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,

        # 6. FK constraint: lead_id -> leads(id) (idempotent)
        """
        DO $$ BEGIN
            ALTER TABLE voice_workflows ADD CONSTRAINT fk_voice_workflows_lead
                FOREIGN KEY (lead_id) REFERENCES leads(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,

        # 7. CHECK constraint on state column (idempotent)
        """
        DO $$ BEGIN
            ALTER TABLE voice_workflows ADD CONSTRAINT ck_voice_workflows_state
                CHECK (state IN ('initiated', 'contact_found', 'sms_sent', 'awaiting_reply', 'negotiating',
                    'time_confirmed', 'appointment_booked', 'completed', 'expired', 'cancelled', 'failed'));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,

        # 8. Ensure conversation_history is NOT NULL with default (for existing tables)
        """
        ALTER TABLE voice_workflows
            ALTER COLUMN conversation_history SET NOT NULL,
            ALTER COLUMN conversation_history SET DEFAULT '[]'::jsonb;
        """,
    ]

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Command {idx} executed successfully")
                except Exception as e:
                    logger.error(f"Error executing command {idx}: {e}")
                    # Continue with other commands
                    continue

        logger.info("Voice workflows table migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting voice_workflows table migration...")
    success = run_migration()
    if success:
        logger.info("Migration completed!")
    else:
        logger.error("Migration failed!")
        sys.exit(1)
