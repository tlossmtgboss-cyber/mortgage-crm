"""
Migration: Create sms_ai_conversations and sms_ai_conversation_messages tables.

These tables support Aria-initiated two-way SMS conversations (scheduling,
qualification, follow-up) with AI-generated responses.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    if engine is None:
        from db import engine as _engine
        engine = _engine

    with engine.connect() as conn:
        # sms_ai_conversations
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sms_ai_conversations (
                id VARCHAR PRIMARY KEY,
                phone_number VARCHAR NOT NULL,
                lead_id INTEGER REFERENCES leads(id),
                organization_id INTEGER REFERENCES organizations(id),
                status VARCHAR DEFAULT 'active',
                current_stage VARCHAR DEFAULT 'greeting',
                context_data JSONB DEFAULT '{}',
                close_reason VARCHAR,
                last_message_at TIMESTAMP WITH TIME ZONE,
                message_count INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_sms_ai_conv_phone_org
            ON sms_ai_conversations(phone_number, organization_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_sms_ai_conv_status
            ON sms_ai_conversations(status)
        """))

        # sms_ai_conversation_messages
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sms_ai_conversation_messages (
                id VARCHAR PRIMARY KEY,
                conversation_id VARCHAR NOT NULL REFERENCES sms_ai_conversations(id),
                direction VARCHAR NOT NULL,
                content TEXT NOT NULL,
                intent VARCHAR,
                confidence FLOAT,
                intent_method VARCHAR,
                entities JSONB DEFAULT '{}',
                ai_generated BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_sms_ai_conv_msg_conv_id
            ON sms_ai_conversation_messages(conversation_id)
        """))

        conn.commit()
        logger.info("[SMS_AI_CONV] sms_ai_conversations tables created/verified")
