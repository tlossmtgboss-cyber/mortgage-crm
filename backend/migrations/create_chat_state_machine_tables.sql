-- Chat State Machine Tables
-- Creates the core tables for the phase-based chat system
--
-- Tables:
-- - chat_sessions: Session tracking with phase state, intent scoring
-- - chat_messages: Individual messages within sessions
-- - call_requests: Click-to-call and callback tracking

-- =============================================================================
-- CHAT SESSIONS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Visitor/User identification
    visitor_id VARCHAR(255) NOT NULL,
    user_id UUID,

    -- Microsite context
    microsite_id INTEGER,
    loan_officer_id INTEGER,

    -- State machine tracking
    current_phase INTEGER NOT NULL DEFAULT 1 CHECK (current_phase BETWEEN 1 AND 4),
    turn_count INTEGER NOT NULL DEFAULT 0,

    -- Intent scoring
    intent_score INTEGER NOT NULL DEFAULT 0 CHECK (intent_score BETWEEN 0 AND 100),
    urgency VARCHAR(10) NOT NULL DEFAULT 'low',

    -- Intent signals (JSONB array)
    intent_signals JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- CTA tracking
    cta_offered VARCHAR(20),
    cta_declined_count INTEGER NOT NULL DEFAULT 0,
    cta_accepted BOOLEAN DEFAULT FALSE,
    cta_accepted_at TIMESTAMPTZ,

    -- Session metadata
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source_url VARCHAR(500),
    referrer VARCHAR(500),
    user_agent VARCHAR(500),
    ip_address VARCHAR(45),

    -- Contact info collected during chat
    contact_name VARCHAR(200),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(20),

    -- Lead conversion tracking
    converted_to_lead BOOLEAN DEFAULT FALSE,
    lead_id INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_message_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ
);

-- Basic indexes for chat_sessions
CREATE INDEX IF NOT EXISTS ix_chat_sessions_visitor_id ON chat_sessions(visitor_id);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_microsite_id ON chat_sessions(microsite_id);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_active ON chat_sessions(is_active);

-- =============================================================================
-- CHAT MESSAGES TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Session link
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,

    -- Message content
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,

    -- Turn tracking
    turn_number INTEGER NOT NULL DEFAULT 0,

    -- Phase at time of message
    phase_at_message INTEGER,

    -- Intent analysis results (for user messages)
    detected_intents JSONB,
    sentiment VARCHAR(20),

    -- CTA interaction (for assistant messages)
    cta_presented VARCHAR(20),
    cta_response VARCHAR(20),

    -- AI model info (for assistant messages)
    model_used VARCHAR(50),
    tokens_used INTEGER,
    response_time_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Basic indexes for chat_messages
CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS ix_chat_messages_created_at ON chat_messages(created_at);

-- =============================================================================
-- CALL REQUESTS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS call_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Session link
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,

    -- Loan officer assignment
    loan_officer_id INTEGER,

    -- Call type and direction
    direction VARCHAR(20) NOT NULL DEFAULT 'inbound',

    -- Contact info
    caller_phone VARCHAR(20) NOT NULL,
    caller_name VARCHAR(200),
    destination_phone VARCHAR(20),

    -- Scheduling
    is_immediate BOOLEAN NOT NULL DEFAULT TRUE,
    scheduled_at TIMESTAMPTZ,
    preferred_time_slot VARCHAR(50),

    -- Call status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending',

    -- Twilio integration
    twilio_call_sid VARCHAR(50),
    twilio_conference_sid VARCHAR(50),

    -- Call metadata
    whisper_message TEXT,
    call_duration_seconds INTEGER,
    recording_url VARCHAR(500),
    recording_sid VARCHAR(50),

    -- Intent context passed to LO
    intent_summary TEXT,
    intent_signals_snapshot JSONB,

    -- Outcome tracking
    outcome VARCHAR(50),
    outcome_notes TEXT,

    -- Lead conversion
    converted_to_lead BOOLEAN DEFAULT FALSE,
    lead_id INTEGER,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    initiated_at TIMESTAMPTZ,
    connected_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ
);

-- Basic indexes for call_requests
CREATE INDEX IF NOT EXISTS ix_call_requests_session_id ON call_requests(session_id);
CREATE INDEX IF NOT EXISTS ix_call_requests_status ON call_requests(status);
CREATE INDEX IF NOT EXISTS ix_call_requests_loan_officer_id ON call_requests(loan_officer_id);
CREATE INDEX IF NOT EXISTS ix_call_requests_scheduled_at ON call_requests(scheduled_at);

-- =============================================================================
-- TRIGGER FOR updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER update_chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_call_requests_updated_at ON call_requests;
CREATE TRIGGER update_call_requests_updated_at
    BEFORE UPDATE ON call_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- VERIFICATION
-- =============================================================================

SELECT 'Tables created successfully' as status;
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('chat_sessions', 'chat_messages', 'call_requests');
