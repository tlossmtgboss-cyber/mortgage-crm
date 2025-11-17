-- Voicemail System Database Migration
-- Creates all tables needed for the built-in voicemail drop feature

-- 1. Voicemail drops table
CREATE TABLE IF NOT EXISTS voicemail_drops (
    id SERIAL PRIMARY KEY,

    -- References
    lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
    loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    campaign_id INTEGER REFERENCES voicemail_campaigns(id) ON DELETE SET NULL,
    template_id INTEGER REFERENCES voicemail_templates(id) ON DELETE SET NULL,

    -- Contact info (denormalized for history)
    contact_name VARCHAR(255),
    contact_phone VARCHAR(20) NOT NULL,
    contact_email VARCHAR(255),

    -- Message content
    message_text TEXT NOT NULL,
    message_variables JSONB,
    audio_url VARCHAR(500),

    -- Vapi call details
    vapi_call_id VARCHAR(255),
    vapi_assistant_id VARCHAR(255),

    -- Delivery status
    status VARCHAR(50) DEFAULT 'pending',
    -- Values: 'pending', 'queued', 'calling', 'delivered', 'failed', 'no_voicemail', 'human_answered'

    delivery_attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMP,
    delivered_at TIMESTAMP,

    -- Call metadata
    call_duration INTEGER,
    call_cost DECIMAL(10, 4),
    carrier VARCHAR(50),

    -- Analytics
    voicemail_listened BOOLEAN DEFAULT FALSE,
    listened_at TIMESTAMP,
    callback_received BOOLEAN DEFAULT FALSE,
    callback_at TIMESTAMP,
    callback_notes TEXT,

    -- Error handling
    error_code VARCHAR(50),
    error_message TEXT,
    retry_scheduled_at TIMESTAMP,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. Templates table
CREATE TABLE IF NOT EXISTS voicemail_templates (
    id SERIAL PRIMARY KEY,

    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    name VARCHAR(255) NOT NULL,
    category VARCHAR(100), -- 'closing', 'follow_up', 'urgent', 'scheduling', 'status_update'

    message_text TEXT NOT NULL,
    variables JSONB, -- ["contact_name", "loan_officer", "appointment_date"]

    -- Usage tracking
    times_used INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,

    -- Template settings
    is_active BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 3. Campaigns table
CREATE TABLE IF NOT EXISTS voicemail_campaigns (
    id SERIAL PRIMARY KEY,

    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    name VARCHAR(255) NOT NULL,
    description TEXT,
    template_id INTEGER REFERENCES voicemail_templates(id) ON DELETE SET NULL,

    -- Target contacts
    contact_filter JSONB,
    total_contacts INTEGER,

    -- Campaign status
    status VARCHAR(50) DEFAULT 'draft',
    -- Values: 'draft', 'scheduled', 'running', 'paused', 'completed', 'cancelled'

    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    paused_at TIMESTAMP,

    -- Throttling
    throttle_rate INTEGER DEFAULT 100, -- calls per hour

    -- Results
    sent_count INTEGER DEFAULT 0,
    delivered_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    callback_count INTEGER DEFAULT 0,

    -- Cost tracking
    total_cost DECIMAL(10, 4) DEFAULT 0,

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 4. Analytics events table
CREATE TABLE IF NOT EXISTS voicemail_events (
    id SERIAL PRIMARY KEY,

    voicemail_drop_id INTEGER REFERENCES voicemail_drops(id) ON DELETE CASCADE,

    event_type VARCHAR(50) NOT NULL,
    -- Values: 'queued', 'calling', 'delivered', 'failed', 'listened', 'callback', 'deleted'

    event_data JSONB,
    event_timestamp TIMESTAMP DEFAULT NOW(),

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_voicemail_drops_lead ON voicemail_drops(lead_id);
CREATE INDEX IF NOT EXISTS idx_voicemail_drops_loan ON voicemail_drops(loan_id);
CREATE INDEX IF NOT EXISTS idx_voicemail_drops_user ON voicemail_drops(user_id);
CREATE INDEX IF NOT EXISTS idx_voicemail_drops_campaign ON voicemail_drops(campaign_id);
CREATE INDEX IF NOT EXISTS idx_voicemail_drops_status ON voicemail_drops(status);
CREATE INDEX IF NOT EXISTS idx_voicemail_drops_delivered_at ON voicemail_drops(delivered_at);
CREATE INDEX IF NOT EXISTS idx_voicemail_drops_created_at ON voicemail_drops(created_at);
CREATE INDEX IF NOT EXISTS idx_voicemail_drops_vapi_call ON voicemail_drops(vapi_call_id);

CREATE INDEX IF NOT EXISTS idx_voicemail_templates_user ON voicemail_templates(user_id);
CREATE INDEX IF NOT EXISTS idx_voicemail_templates_category ON voicemail_templates(category);
CREATE INDEX IF NOT EXISTS idx_voicemail_templates_active ON voicemail_templates(is_active);

CREATE INDEX IF NOT EXISTS idx_voicemail_campaigns_user ON voicemail_campaigns(user_id);
CREATE INDEX IF NOT EXISTS idx_voicemail_campaigns_status ON voicemail_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_voicemail_campaigns_scheduled ON voicemail_campaigns(scheduled_at);

CREATE INDEX IF NOT EXISTS idx_voicemail_events_drop ON voicemail_events(voicemail_drop_id);
CREATE INDEX IF NOT EXISTS idx_voicemail_events_type ON voicemail_events(event_type);
CREATE INDEX IF NOT EXISTS idx_voicemail_events_timestamp ON voicemail_events(event_timestamp);

-- Insert default templates
INSERT INTO voicemail_templates (name, category, message_text, variables, is_default) VALUES
('Closing Disclosure Ready', 'closing', 'Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. I wanted to let you know that your closing disclosures are ready for review. They''ve been sent to your email. Please review and sign them at your earliest convenience. If you have any questions, feel free to call me back. Thanks!', '["contact_name", "loan_officer"]', true),
('Document Request', 'follow_up', 'Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. We need a few additional documents to move your loan application forward. I''ve sent you an email with the complete list. Please upload them to your secure portal when you get a chance. If you need any help, just give me a call. Thank you!', '["contact_name", "loan_officer"]', true),
('Rate Lock Expiration', 'urgent', 'Hi {{contact_name}}, this is {{loan_officer}}. I wanted to give you a heads up that your rate lock expires soon. We need to take action to secure your current rate. Please call me back as soon as possible so we can discuss your options. Thanks!', '["contact_name", "loan_officer"]', true),
('Application Status Update', 'status_update', 'Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. I wanted to give you a quick update on your loan application. Everything is moving along smoothly. I''ll keep you posted on any developments. If you have questions, feel free to reach out. Have a great day!', '["contact_name", "loan_officer"]', true),
('Appointment Reminder', 'scheduling', 'Hi {{contact_name}}, this is {{loan_officer}} from the Tim Loss Team. Just a friendly reminder about our appointment tomorrow. I''m looking forward to speaking with you. If you need to reschedule, just give me a call. See you soon!', '["contact_name", "loan_officer"]', true);
