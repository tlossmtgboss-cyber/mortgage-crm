"""
Migration: Add telephony status callback tables for webhook processing.

Tables created:
- processed_twilio_events: Idempotency table for webhook de-duplication (legacy table name)
- call_attempts: Tracks individual dial attempts with status and disposition
- call_targets: Tracks who to call with retry logic
- state_recording_rules: State-specific recording disclosure requirements

Run with: python -m migrations.add_twilio_status_callback_tables
"""

import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import SessionLocal, engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Create telephony status callback tables if they don't exist."""
    db = SessionLocal()

    try:
        # Check if tables already exist
        result = db.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN (
                'processed_twilio_events',
                'call_attempts',
                'call_targets',
                'state_recording_rules',
                'event_outbox'
            )
        """))
        existing_tables = [row[0] for row in result.fetchall()]

        # =====================================================================
        # 1. processed_twilio_events - Idempotency table for webhook de-dupe
        # =====================================================================
        if 'processed_twilio_events' not in existing_tables:
            logger.info("Creating processed_twilio_events table...")
            db.execute(text("""
                CREATE TABLE processed_twilio_events (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    call_sid TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    call_status TEXT,
                    recording_sid TEXT,
                    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    raw_payload JSONB,
                    UNIQUE(call_sid, event_type, call_status),
                    UNIQUE(call_sid, event_type, recording_sid)
                )
            """))
            db.execute(text("CREATE INDEX idx_processed_twilio_events_call_sid ON processed_twilio_events(call_sid)"))
            db.execute(text("CREATE INDEX idx_processed_twilio_events_received ON processed_twilio_events(received_at)"))
            logger.info("processed_twilio_events table created")
        else:
            logger.info("processed_twilio_events table already exists")

        # =====================================================================
        # 2. call_targets - Who to call with retry logic
        # =====================================================================
        if 'call_targets' not in existing_tables:
            logger.info("Creating call_targets table...")
            db.execute(text("""
                CREATE TABLE call_targets (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    campaign_id UUID,
                    lead_id INTEGER REFERENCES leads(id),
                    contact_id INTEGER,
                    phone_number VARCHAR(20) NOT NULL,
                    borrower_name VARCHAR(255),
                    priority INTEGER DEFAULT 0,
                    callable BOOLEAN DEFAULT TRUE,
                    not_callable_reason TEXT,
                    disposition VARCHAR(50),
                    attempt_count INTEGER DEFAULT 0,
                    max_attempts INTEGER DEFAULT 3,
                    last_attempt_at TIMESTAMPTZ,
                    next_attempt_after TIMESTAMPTZ,
                    timezone VARCHAR(50) DEFAULT 'America/New_York',
                    best_time_start TIME,
                    best_time_end TIME,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX idx_call_targets_campaign ON call_targets(campaign_id)"))
            db.execute(text("CREATE INDEX idx_call_targets_lead ON call_targets(lead_id)"))
            db.execute(text("CREATE INDEX idx_call_targets_phone ON call_targets(phone_number)"))
            db.execute(text("CREATE INDEX idx_call_targets_callable ON call_targets(callable, next_attempt_after)"))
            db.execute(text("CREATE INDEX idx_call_targets_disposition ON call_targets(disposition)"))
            logger.info("call_targets table created")
        else:
            logger.info("call_targets table already exists")

        # =====================================================================
        # 3. call_attempts - Each dial attempt + outcome
        # =====================================================================
        if 'call_attempts' not in existing_tables:
            logger.info("Creating call_attempts table...")
            db.execute(text("""
                CREATE TABLE call_attempts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    call_target_id UUID REFERENCES call_targets(id) ON DELETE SET NULL,
                    campaign_id UUID,
                    provider_call_id VARCHAR(100) UNIQUE,
                    from_number VARCHAR(20) NOT NULL,
                    to_number VARCHAR(20) NOT NULL,
                    direction VARCHAR(20) DEFAULT 'outbound-api',
                    status VARCHAR(50) DEFAULT 'queued',
                    disposition VARCHAR(50),
                    started_at TIMESTAMPTZ,
                    answered_at TIMESTAMPTZ,
                    ended_at TIMESTAMPTZ,
                    duration_seconds INTEGER,
                    recording_url TEXT,
                    recording_sid VARCHAR(100),
                    recording_duration INTEGER,
                    sip_response_code VARCHAR(10),
                    error_code VARCHAR(50),
                    error_message TEXT,
                    agent_outcome VARCHAR(50),
                    agent_notes TEXT,
                    scorecard JSONB DEFAULT '{}',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX idx_call_attempts_provider_call ON call_attempts(provider_call_id)"))
            db.execute(text("CREATE INDEX idx_call_attempts_target ON call_attempts(call_target_id)"))
            db.execute(text("CREATE INDEX idx_call_attempts_campaign ON call_attempts(campaign_id)"))
            db.execute(text("CREATE INDEX idx_call_attempts_status ON call_attempts(status)"))
            db.execute(text("CREATE INDEX idx_call_attempts_disposition ON call_attempts(disposition)"))
            db.execute(text("CREATE INDEX idx_call_attempts_created ON call_attempts(created_at)"))
            logger.info("call_attempts table created")
        else:
            logger.info("call_attempts table already exists")

        # =====================================================================
        # 4. state_recording_rules - State-specific recording disclosure rules
        # =====================================================================
        if 'state_recording_rules' not in existing_tables:
            logger.info("Creating state_recording_rules table...")
            db.execute(text("""
                CREATE TABLE state_recording_rules (
                    state CHAR(2) PRIMARY KEY,
                    recording_required BOOLEAN NOT NULL DEFAULT FALSE,
                    requires_verbal_ack BOOLEAN NOT NULL DEFAULT FALSE,
                    disclosure_script TEXT NOT NULL,
                    consent_type VARCHAR(20) DEFAULT 'one-party',
                    notes TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))

            # Seed with common states
            db.execute(text("""
                INSERT INTO state_recording_rules(state, recording_required, requires_verbal_ack, disclosure_script, consent_type, notes)
                VALUES
                ('SC', true, false, 'Just so you know, this call may be recorded for quality.', 'one-party', 'South Carolina - one-party consent'),
                ('NC', true, false, 'Just so you know, this call may be recorded for quality.', 'one-party', 'North Carolina - one-party consent'),
                ('GA', true, false, 'Just so you know, this call may be recorded for quality.', 'one-party', 'Georgia - one-party consent'),
                ('FL', true, false, 'Just so you know, this call may be recorded for quality.', 'all-party', 'Florida - all-party consent state'),
                ('CA', true, true, 'This call is being recorded for quality and training purposes. Is that okay with you?', 'all-party', 'California - all-party consent, requires acknowledgment'),
                ('CT', true, true, 'I need to let you know this call is being recorded. Do I have your permission to continue?', 'all-party', 'Connecticut - all-party consent'),
                ('IL', true, true, 'This call may be recorded. Do you consent to the recording?', 'all-party', 'Illinois - all-party consent'),
                ('MD', true, true, 'This call is being recorded for quality purposes. Is that alright?', 'all-party', 'Maryland - all-party consent'),
                ('MA', true, true, 'I want to let you know this call is being recorded. Is that okay?', 'all-party', 'Massachusetts - all-party consent'),
                ('MT', true, true, 'This call may be monitored or recorded. Do you consent?', 'all-party', 'Montana - all-party consent'),
                ('NH', true, true, 'This call is being recorded for quality. Do I have your permission?', 'all-party', 'New Hampshire - all-party consent'),
                ('PA', true, true, 'This call may be recorded. Is that okay with you?', 'all-party', 'Pennsylvania - all-party consent'),
                ('WA', true, true, 'Just so you know, this call is being recorded. Do you consent?', 'all-party', 'Washington - all-party consent')
                ON CONFLICT (state) DO NOTHING
            """))
            logger.info("state_recording_rules table created with seed data")
        else:
            logger.info("state_recording_rules table already exists")

        # =====================================================================
        # 5. event_outbox - For emitting events on call completion
        # =====================================================================
        if 'event_outbox' not in existing_tables:
            logger.info("Creating event_outbox table...")
            db.execute(text("""
                CREATE TABLE event_outbox (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    event_type VARCHAR(100) NOT NULL,
                    aggregate_type VARCHAR(100),
                    aggregate_id VARCHAR(255),
                    payload JSONB NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    last_error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    processed_at TIMESTAMPTZ
                )
            """))
            db.execute(text("CREATE INDEX idx_event_outbox_status ON event_outbox(status, created_at)"))
            db.execute(text("CREATE INDEX idx_event_outbox_type ON event_outbox(event_type)"))
            db.execute(text("CREATE INDEX idx_event_outbox_aggregate ON event_outbox(aggregate_type, aggregate_id)"))
            logger.info("event_outbox table created")
        else:
            logger.info("event_outbox table already exists")

        db.commit()
        logger.info("Telephony status callback migration completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def rollback_migration():
    """Drop telephony status callback tables (use with caution)."""
    db = SessionLocal()

    try:
        logger.warning("Rolling back telephony status callback tables...")
        db.execute(text("DROP TABLE IF EXISTS call_attempts CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS call_targets CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS processed_twilio_events CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS state_recording_rules CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS event_outbox CASCADE"))
        db.commit()
        logger.info("Rollback completed")
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        run_migration()
