"""
Voice OS Database Migration
Creates the tables required for the Voice OS system.
"""

import logging
import os

logger = logging.getLogger(__name__)


def run_migration():
    """
    Run the Voice OS migration.
    Creates: voice_os_agents, voice_os_phone_numbers, voice_os_call_sessions
    """
    try:
        from database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()

        logger.info("Starting Voice OS migration...")

        # Create voice_os_agents table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS voice_os_agents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL,
                description TEXT,
                status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive')),

                -- Voice Configuration
                voice_id VARCHAR(100) NOT NULL DEFAULT 'alloy',
                voice_stability DECIMAL(3,2) DEFAULT 0.50,
                voice_similarity DECIMAL(3,2) DEFAULT 0.75,
                voice_style DECIMAL(3,2) DEFAULT 0.50,

                -- LLM Configuration
                system_prompt TEXT NOT NULL,
                temperature DECIMAL(3,2) DEFAULT 0.7,
                max_tokens INTEGER DEFAULT 150,

                -- Behavior Settings
                interrupt_enabled BOOLEAN DEFAULT true,
                filler_words_enabled BOOLEAN DEFAULT true,
                backchanneling_enabled BOOLEAN DEFAULT true,
                emotion_detection_enabled BOOLEAN DEFAULT true,

                -- Tools
                tools_allowed JSONB DEFAULT '["get_contact_by_phone", "create_lead", "schedule_appointment"]'::jsonb,

                -- Analytics
                total_calls INTEGER DEFAULT 0,
                successful_calls INTEGER DEFAULT 0,
                avg_duration_seconds INTEGER DEFAULT 0,
                avg_satisfaction DECIMAL(3,2),

                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        logger.info("Created voice_os_agents table")

        # Create index on voice_os_agents
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_os_agents_status
            ON voice_os_agents(status) WHERE status = 'active'
        """))

        # Create voice_os_phone_numbers table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS voice_os_phone_numbers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                e164_number VARCHAR(20) UNIQUE NOT NULL,
                friendly_name VARCHAR(100),
                agent_id UUID REFERENCES voice_os_agents(id) ON DELETE SET NULL,
                enabled BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        logger.info("Created voice_os_phone_numbers table")

        # Create index on voice_os_phone_numbers
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_os_phone_numbers_enabled
            ON voice_os_phone_numbers(enabled) WHERE enabled = true
        """))

        # Create voice_os_call_sessions table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS voice_os_call_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                call_sid VARCHAR(100) UNIQUE NOT NULL,
                agent_id UUID REFERENCES voice_os_agents(id),

                -- Call Info
                direction VARCHAR(10) CHECK (direction IN ('inbound', 'outbound')),
                from_number VARCHAR(20) NOT NULL,
                to_number VARCHAR(20) NOT NULL,

                -- Status & Timing
                status VARCHAR(20) DEFAULT 'ringing',
                start_time TIMESTAMPTZ DEFAULT NOW(),
                answer_time TIMESTAMPTZ,
                end_time TIMESTAMPTZ,
                duration_seconds INTEGER,

                -- Contact Matching
                contact_id UUID,
                contact_name VARCHAR(200),
                contact_email VARCHAR(255),

                -- AI Analysis
                transcript JSONB DEFAULT '[]'::jsonb,
                summary TEXT,
                sentiment VARCHAR(20),
                emotion_detected VARCHAR(50),
                outcome VARCHAR(50),
                intent_detected VARCHAR(100),

                -- Actions Taken
                actions_taken JSONB DEFAULT '[]'::jsonb,

                -- Quality Metrics
                interruptions_count INTEGER DEFAULT 0,
                avg_response_latency_ms INTEGER,
                escalated BOOLEAN DEFAULT false,
                escalation_reason TEXT,

                -- Storage
                recording_url TEXT,

                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        logger.info("Created voice_os_call_sessions table")

        # Create indexes on voice_os_call_sessions
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_status
            ON voice_os_call_sessions(status)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_agent
            ON voice_os_call_sessions(agent_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_contact
            ON voice_os_call_sessions(contact_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_start_time
            ON voice_os_call_sessions(start_time DESC)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_outcome
            ON voice_os_call_sessions(outcome)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_voice_os_call_sessions_from_number
            ON voice_os_call_sessions(from_number)
        """))

        # Create trigger function for auto-updating agent stats
        db.execute(text("""
            CREATE OR REPLACE FUNCTION update_voice_os_agent_stats()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
                    UPDATE voice_os_agents
                    SET
                        total_calls = total_calls + 1,
                        successful_calls = CASE
                            WHEN NEW.outcome IN ('appointment_booked', 'lead_created', 'info_provided')
                            THEN successful_calls + 1
                            ELSE successful_calls
                        END,
                        avg_duration_seconds = (
                            (avg_duration_seconds * total_calls + COALESCE(NEW.duration_seconds, 0)) /
                            (total_calls + 1)
                        ),
                        updated_at = NOW()
                    WHERE id = NEW.agent_id;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        logger.info("Created update_voice_os_agent_stats function")

        # Create trigger
        db.execute(text("""
            DROP TRIGGER IF EXISTS trigger_update_voice_os_agent_stats ON voice_os_call_sessions
        """))
        db.execute(text("""
            CREATE TRIGGER trigger_update_voice_os_agent_stats
            AFTER UPDATE OF status ON voice_os_call_sessions
            FOR EACH ROW
            EXECUTE FUNCTION update_voice_os_agent_stats()
        """))
        logger.info("Created trigger_update_voice_os_agent_stats")

        # Create performance view
        db.execute(text("""
            CREATE OR REPLACE VIEW voice_os_agent_performance AS
            SELECT
                a.id,
                a.name,
                a.status,
                a.total_calls,
                a.successful_calls,
                CASE
                    WHEN a.total_calls > 0
                    THEN ROUND((a.successful_calls::decimal / a.total_calls * 100), 1)
                    ELSE 0
                END as success_rate_percent,
                a.avg_duration_seconds,
                a.avg_satisfaction,
                COUNT(cs.id) FILTER (WHERE cs.status IN ('ringing', 'in_progress')) as active_calls_now
            FROM voice_os_agents a
            LEFT JOIN voice_os_call_sessions cs ON a.id = cs.agent_id
            GROUP BY a.id, a.name, a.status, a.total_calls, a.successful_calls,
                     a.avg_duration_seconds, a.avg_satisfaction
        """))
        logger.info("Created voice_os_agent_performance view")

        # Seed default agent
        db.execute(text("""
            INSERT INTO voice_os_agents (
                name,
                description,
                status,
                voice_id,
                voice_stability,
                voice_similarity,
                system_prompt,
                temperature,
                max_tokens,
                interrupt_enabled,
                filler_words_enabled,
                backchanneling_enabled,
                emotion_detection_enabled,
                tools_allowed
            )
            SELECT
                'Aria - AI Receptionist',
                'Friendly and professional AI receptionist for inbound calls',
                'active',
                'alloy',
                0.50,
                0.75,
                'You are Aria, a friendly and professional AI receptionist for a mortgage company.

Your role is to:
- Greet callers warmly and professionally
- Identify if they are existing clients or new prospects
- Understand their needs (new loan, refinance, loan status, etc.)
- Schedule appointments with loan officers
- Answer basic questions about the mortgage process
- Create leads for new prospects

Guidelines:
- Keep responses concise (under 3 sentences when possible)
- Be empathetic and patient
- If you cannot help, offer to transfer to a human
- Never provide specific rate quotes without proper qualification
- Always confirm important details like names, phone numbers, and appointment times',
                0.7,
                150,
                true,
                true,
                true,
                true,
                '["get_contact_by_phone", "create_lead", "update_lead_stage", "schedule_appointment", "check_availability", "create_task", "log_call_note", "get_loan_status", "escalate_to_human"]'::jsonb
            WHERE NOT EXISTS (
                SELECT 1 FROM voice_os_agents WHERE name = 'Aria - AI Receptionist'
            )
        """))
        logger.info("Seeded default Aria - AI Receptionist agent")

        db.commit()
        db.close()

        logger.info("Voice OS migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Voice OS migration failed: {e}")
        if 'db' in locals():
            db.rollback()
            db.close()
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
