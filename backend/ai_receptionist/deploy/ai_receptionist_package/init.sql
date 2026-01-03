-- =============================================================================
-- PERENNIA AI RECEPTIONIST - DATABASE INITIALIZATION
-- =============================================================================

-- Call Logs Table
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
    caller_id INTEGER REFERENCES contacts(id),
    loan_officer_id INTEGER REFERENCES users(id),
    transferred_to INTEGER REFERENCES users(id),
    transfer_reason TEXT,
    outcome VARCHAR(64),
    notes TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Call Events Table (for detailed call tracking)
CREATE TABLE IF NOT EXISTS call_events (
    id SERIAL PRIMARY KEY,
    call_log_id INTEGER REFERENCES call_logs(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    event_data JSONB DEFAULT '{}',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Callback Requests Table
CREATE TABLE IF NOT EXISTS callback_requests (
    id SERIAL PRIMARY KEY,
    call_log_id INTEGER REFERENCES call_logs(id),
    caller_name VARCHAR(128),
    caller_phone VARCHAR(32) NOT NULL,
    reason TEXT,
    urgency VARCHAR(16) DEFAULT 'normal',
    assigned_to INTEGER REFERENCES users(id),
    status VARCHAR(32) DEFAULT 'pending',
    scheduled_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Voice Messages Table
CREATE TABLE IF NOT EXISTS voice_messages (
    id SERIAL PRIMARY KEY,
    call_log_id INTEGER REFERENCES call_logs(id),
    from_number VARCHAR(32),
    to_user_id INTEGER REFERENCES users(id),
    recording_url TEXT,
    transcript TEXT,
    duration_seconds INTEGER,
    is_urgent BOOLEAN DEFAULT false,
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_call_logs_call_sid ON call_logs(call_sid);
CREATE INDEX IF NOT EXISTS idx_call_logs_from_number ON call_logs(from_number);
CREATE INDEX IF NOT EXISTS idx_call_logs_started_at ON call_logs(started_at);
CREATE INDEX IF NOT EXISTS idx_call_logs_status ON call_logs(status);
CREATE INDEX IF NOT EXISTS idx_call_events_call_log_id ON call_events(call_log_id);
CREATE INDEX IF NOT EXISTS idx_callback_requests_status ON callback_requests(status);
CREATE INDEX IF NOT EXISTS idx_voice_messages_to_user_id ON voice_messages(to_user_id);
CREATE INDEX IF NOT EXISTS idx_voice_messages_is_read ON voice_messages(is_read);

-- Updated at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers
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

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO perennia;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO perennia;

COMMIT;
