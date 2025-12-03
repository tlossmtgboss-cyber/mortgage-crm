--=============================================================================
-- PERENNIA AI RECEPTIONIST - DATABASE INITIALIZATION
--=============================================================================
-- Run automatically when PostgreSQL container starts
--=============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--=============================================================================
-- CALL LOGS
--=============================================================================

CREATE TABLE IF NOT EXISTS call_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_sid VARCHAR(100) UNIQUE NOT NULL,
    from_number VARCHAR(20) NOT NULL,
    to_number VARCHAR(20),
    direction VARCHAR(20) DEFAULT 'inbound',
    status VARCHAR(50),
    duration_seconds INTEGER DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    answered_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,

    -- Caller info
    caller_name VARCHAR(255),
    contact_id UUID,
    is_existing_customer BOOLEAN DEFAULT FALSE,

    -- Conversation
    primary_intent VARCHAR(100),
    turn_count INTEGER DEFAULT 0,

    -- Outcomes
    appointment_scheduled BOOLEAN DEFAULT FALSE,
    callback_scheduled BOOLEAN DEFAULT FALSE,
    message_left BOOLEAN DEFAULT FALSE,
    transferred BOOLEAN DEFAULT FALSE,
    transfer_target VARCHAR(100),

    -- Recording
    recording_sid VARCHAR(100),
    recording_url TEXT,
    transcription TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_call_logs_from_number ON call_logs(from_number);
CREATE INDEX IF NOT EXISTS idx_call_logs_started_at ON call_logs(started_at);
CREATE INDEX IF NOT EXISTS idx_call_logs_contact_id ON call_logs(contact_id);

--=============================================================================
-- CONVERSATION TURNS
--=============================================================================

CREATE TABLE IF NOT EXISTS conversation_turns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_log_id UUID REFERENCES call_logs(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL, -- 'caller' or 'receptionist'
    content TEXT NOT NULL,
    intent VARCHAR(100),
    emotion VARCHAR(50),
    tool_calls JSONB DEFAULT '[]',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversation_turns_call_log_id ON conversation_turns(call_log_id);

--=============================================================================
-- CALLBACK REQUESTS
--=============================================================================

CREATE TABLE IF NOT EXISTS callback_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_log_id UUID REFERENCES call_logs(id),
    caller_name VARCHAR(255) NOT NULL,
    caller_phone VARCHAR(20) NOT NULL,
    assigned_to UUID,
    reason TEXT,
    urgency VARCHAR(20) DEFAULT 'normal',
    best_time VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_callback_requests_status ON callback_requests(status);
CREATE INDEX IF NOT EXISTS idx_callback_requests_assigned_to ON callback_requests(assigned_to);

--=============================================================================
-- APPOINTMENTS (from receptionist scheduling)
--=============================================================================

CREATE TABLE IF NOT EXISTS receptionist_appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_log_id UUID REFERENCES call_logs(id),
    contact_name VARCHAR(255) NOT NULL,
    contact_phone VARCHAR(20) NOT NULL,
    contact_email VARCHAR(255),
    assigned_to UUID NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    title VARCHAR(255) DEFAULT 'Phone Consultation',
    notes TEXT,
    status VARCHAR(50) DEFAULT 'scheduled',
    reminder_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_receptionist_appointments_assigned_to ON receptionist_appointments(assigned_to);
CREATE INDEX IF NOT EXISTS idx_receptionist_appointments_start_time ON receptionist_appointments(start_time);

--=============================================================================
-- MESSAGES (voicemail/messages taken by receptionist)
--=============================================================================

CREATE TABLE IF NOT EXISTS receptionist_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_log_id UUID REFERENCES call_logs(id),
    for_user_id UUID NOT NULL,
    from_name VARCHAR(255) NOT NULL,
    from_phone VARCHAR(20),
    message TEXT NOT NULL,
    urgent BOOLEAN DEFAULT FALSE,
    read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_receptionist_messages_for_user_id ON receptionist_messages(for_user_id);
CREATE INDEX IF NOT EXISTS idx_receptionist_messages_read ON receptionist_messages(read);

--=============================================================================
-- ANALYTICS VIEWS
--=============================================================================

-- Daily call summary
CREATE OR REPLACE VIEW v_daily_call_summary AS
SELECT
    DATE(started_at) as call_date,
    COUNT(*) as total_calls,
    COUNT(*) FILTER (WHERE appointment_scheduled) as appointments_scheduled,
    COUNT(*) FILTER (WHERE callback_scheduled) as callbacks_scheduled,
    COUNT(*) FILTER (WHERE message_left) as messages_left,
    COUNT(*) FILTER (WHERE transferred) as calls_transferred,
    AVG(duration_seconds) as avg_duration_seconds,
    AVG(turn_count) as avg_turns
FROM call_logs
GROUP BY DATE(started_at)
ORDER BY call_date DESC;

-- Intent distribution
CREATE OR REPLACE VIEW v_intent_distribution AS
SELECT
    primary_intent,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM call_logs
WHERE primary_intent IS NOT NULL
GROUP BY primary_intent
ORDER BY count DESC;

-- Resolution rate (calls handled without transfer)
CREATE OR REPLACE VIEW v_resolution_rate AS
SELECT
    DATE(started_at) as call_date,
    COUNT(*) as total_calls,
    COUNT(*) FILTER (WHERE NOT transferred) as resolved_calls,
    ROUND(100.0 * COUNT(*) FILTER (WHERE NOT transferred) / COUNT(*), 2) as resolution_rate
FROM call_logs
GROUP BY DATE(started_at)
ORDER BY call_date DESC;

--=============================================================================
-- FUNCTIONS
--=============================================================================

-- Update timestamp function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply to tables
DROP TRIGGER IF EXISTS update_call_logs_updated_at ON call_logs;
CREATE TRIGGER update_call_logs_updated_at
    BEFORE UPDATE ON call_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_callback_requests_updated_at ON callback_requests;
CREATE TRIGGER update_callback_requests_updated_at
    BEFORE UPDATE ON callback_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_receptionist_appointments_updated_at ON receptionist_appointments;
CREATE TRIGGER update_receptionist_appointments_updated_at
    BEFORE UPDATE ON receptionist_appointments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

--=============================================================================
-- SAMPLE DATA (for testing)
--=============================================================================

-- Uncomment to insert sample data
/*
INSERT INTO call_logs (call_sid, from_number, to_number, status, duration_seconds, caller_name, primary_intent, turn_count, appointment_scheduled)
VALUES
    ('CA001', '+15551234567', '+18001234567', 'completed', 180, 'John Smith', 'schedule_appointment', 8, true),
    ('CA002', '+15559876543', '+18001234567', 'completed', 120, 'Jane Doe', 'loan_status', 6, false),
    ('CA003', '+15555555555', '+18001234567', 'completed', 90, NULL, 'speak_to_agent', 4, false);
*/

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO perennia;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO perennia;
