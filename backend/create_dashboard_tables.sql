-- AI Receptionist Dashboard Tables Migration
-- Creates 6 tables for activity tracking, metrics, skills, errors, system health, and conversations

-- 1. Activity table
CREATE TABLE IF NOT EXISTS ai_receptionist_activity (
    id VARCHAR(36) PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    client_id VARCHAR(255),
    client_name VARCHAR(255),
    client_phone VARCHAR(50),
    client_email VARCHAR(255),
    action_type VARCHAR(100) NOT NULL,
    channel VARCHAR(50),
    message_in TEXT,
    message_out TEXT,
    confidence_score FLOAT,
    ai_version VARCHAR(50),
    lead_stage VARCHAR(100),
    assigned_to VARCHAR(255),
    outcome_status VARCHAR(100),
    conversation_id VARCHAR(255),
    transcript_url VARCHAR(500),
    extra_data JSON
);

CREATE INDEX IF NOT EXISTS idx_activity_timestamp_desc ON ai_receptionist_activity(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_client_timestamp ON ai_receptionist_activity(client_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_activity_type_timestamp ON ai_receptionist_activity(action_type, timestamp DESC);

-- 2. Conversations table
CREATE TABLE IF NOT EXISTS ai_receptionist_conversations (
    id VARCHAR(36) PRIMARY KEY,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    client_id VARCHAR(255),
    client_name VARCHAR(255),
    client_phone VARCHAR(50),
    client_email VARCHAR(255),
    channel VARCHAR(50),
    full_transcript TEXT,
    summary TEXT,
    sentiment VARCHAR(50),
    ai_confidence FLOAT,
    lead_id INTEGER,
    user_id INTEGER,
    outcome_status VARCHAR(100),
    recording_url VARCHAR(500),
    extra_data JSON
);

CREATE INDEX IF NOT EXISTS idx_conversation_started_desc ON ai_receptionist_conversations(started_at DESC);

-- 3. Daily metrics table
CREATE TABLE IF NOT EXISTS ai_receptionist_metrics_daily (
    date DATE PRIMARY KEY,
    total_conversations INTEGER DEFAULT 0,
    inbound_calls INTEGER DEFAULT 0,
    inbound_texts INTEGER DEFAULT 0,
    outbound_messages INTEGER DEFAULT 0,
    response_time_avg_seconds FLOAT,
    response_time_p95_seconds FLOAT,
    appointments_scheduled INTEGER DEFAULT 0,
    forms_completed INTEGER DEFAULT 0,
    loan_apps_initiated INTEGER DEFAULT 0,
    lead_updates INTEGER DEFAULT 0,
    task_updates INTEGER DEFAULT 0,
    documents_requested INTEGER DEFAULT 0,
    escalations INTEGER DEFAULT 0,
    ai_confusion_count INTEGER DEFAULT 0,
    successful_resolutions INTEGER DEFAULT 0,
    lead_qualification_rate FLOAT,
    appointment_show_rate FLOAT,
    ai_coverage_percentage FLOAT,
    estimated_revenue_created FLOAT,
    saved_labor_hours FLOAT,
    cost_per_interaction FLOAT,
    avg_confidence_score FLOAT,
    error_rate FLOAT,
    extra_data JSON
);

-- 4. Skills table
CREATE TABLE IF NOT EXISTS ai_receptionist_skills (
    id VARCHAR(36) PRIMARY KEY,
    skill_name VARCHAR(255) NOT NULL UNIQUE,
    skill_category VARCHAR(100),
    description TEXT,
    accuracy_score FLOAT,
    accuracy_score_7day FLOAT,
    accuracy_score_30day FLOAT,
    trend_7day FLOAT,
    trend_30day FLOAT,
    trend_direction VARCHAR(20),
    usage_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    needs_retraining BOOLEAN DEFAULT FALSE,
    last_trained_at TIMESTAMP WITH TIME ZONE,
    last_updated TIMESTAMP WITH TIME ZONE,
    extra_data JSON
);

-- 5. Errors table
CREATE TABLE IF NOT EXISTS ai_receptionist_errors (
    id VARCHAR(36) PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    error_type VARCHAR(100) NOT NULL,
    severity VARCHAR(50),
    context TEXT,
    conversation_snippet TEXT,
    conversation_id VARCHAR(255),
    root_cause TEXT,
    recommended_fix TEXT,
    auto_fix_proposed TEXT,
    needs_human_review BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    resolution_status VARCHAR(50) DEFAULT 'unresolved',
    resolution_notes TEXT,
    trained_into_model BOOLEAN DEFAULT FALSE,
    training_data_id VARCHAR(255),
    extra_data JSON
);

CREATE INDEX IF NOT EXISTS idx_error_timestamp_desc ON ai_receptionist_errors(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_error_type_status ON ai_receptionist_errors(error_type, resolution_status);
CREATE INDEX IF NOT EXISTS idx_error_needs_review ON ai_receptionist_errors(needs_human_review);

-- 6. System health table
CREATE TABLE IF NOT EXISTS ai_receptionist_system_health (
    component_name VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50) NOT NULL DEFAULT 'unknown',
    latency_ms INTEGER,
    error_rate FLOAT,
    uptime_percentage FLOAT,
    last_checked TIMESTAMP WITH TIME ZONE,
    last_success TIMESTAMP WITH TIME ZONE,
    last_failure TIMESTAMP WITH TIME ZONE,
    consecutive_failures INTEGER DEFAULT 0,
    alert_sent BOOLEAN DEFAULT FALSE,
    alert_sent_at TIMESTAMP WITH TIME ZONE,
    notes TEXT,
    endpoint_url VARCHAR(500),
    extra_data JSON
);

-- Done
SELECT 'AI Receptionist Dashboard tables created successfully!' AS status;
