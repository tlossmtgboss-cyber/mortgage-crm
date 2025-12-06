-- Email Webhook Tables Migration
-- Tables for Microsoft Graph email webhook processing
-- Integrates with Email Orchestrator for real-time email automation

-- 1. Email Webhook Log - tracks incoming webhook notifications
CREATE TABLE IF NOT EXISTS email_webhook_log (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(500) UNIQUE NOT NULL,
    change_type VARCHAR(50),
    tenant_id VARCHAR(100),
    resource VARCHAR(500),
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_email_webhook_log_email_id ON email_webhook_log(email_id);
CREATE INDEX IF NOT EXISTS idx_email_webhook_log_received ON email_webhook_log(received_at);
CREATE INDEX IF NOT EXISTS idx_email_webhook_log_processed ON email_webhook_log(processed);

-- 2. Email Tracking - stores processed email details
CREATE TABLE IF NOT EXISTS email_tracking (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(500) UNIQUE NOT NULL,
    subject TEXT,
    from_email VARCHAR(255),
    from_name VARCHAR(255),
    to_email TEXT,
    body_preview TEXT,
    received_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'pending',
    email_type VARCHAR(50),
    has_attachments BOOLEAN DEFAULT FALSE,
    importance VARCHAR(20) DEFAULT 'normal',
    processing_results JSONB,
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Linking fields
    linked_lead_id INTEGER REFERENCES leads(id),
    linked_loan_id INTEGER REFERENCES loans(id),
    linked_contact_id INTEGER REFERENCES contacts(id),
    user_id INTEGER REFERENCES users(id),
    -- Time savings tracking
    time_saved_minutes INTEGER DEFAULT 0,
    automated_actions JSONB
);
CREATE INDEX IF NOT EXISTS idx_email_tracking_email_id ON email_tracking(email_id);
CREATE INDEX IF NOT EXISTS idx_email_tracking_from ON email_tracking(from_email);
CREATE INDEX IF NOT EXISTS idx_email_tracking_received ON email_tracking(received_at);
CREATE INDEX IF NOT EXISTS idx_email_tracking_status ON email_tracking(status);
CREATE INDEX IF NOT EXISTS idx_email_tracking_type ON email_tracking(email_type);
CREATE INDEX IF NOT EXISTS idx_email_tracking_lead ON email_tracking(linked_lead_id);
CREATE INDEX IF NOT EXISTS idx_email_tracking_loan ON email_tracking(linked_loan_id);

-- 3. Email Processing Log - processor execution history
CREATE TABLE IF NOT EXISTS email_processing_log (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(500) NOT NULL,
    processor_name VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL,
    action_taken VARCHAR(255),
    time_saved_minutes INTEGER DEFAULT 0,
    metadata JSONB,
    error_message TEXT,
    processing_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_processing_log_email ON email_processing_log(email_id);
CREATE INDEX IF NOT EXISTS idx_email_processing_log_processor ON email_processing_log(processor_name);
CREATE INDEX IF NOT EXISTS idx_email_processing_log_created ON email_processing_log(created_at);

-- 4. Email Templates - for auto-responses
CREATE TABLE IF NOT EXISTS email_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    is_html BOOLEAN DEFAULT TRUE,
    variables TEXT[], -- placeholders like {firstName}, {loanNumber}
    category VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_templates_name ON email_templates(name);
CREATE INDEX IF NOT EXISTS idx_email_templates_category ON email_templates(category);

-- 5. Email Response Tracking - SLA monitoring
CREATE TABLE IF NOT EXISTS email_response_tracking (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(500) NOT NULL,
    sla_priority VARCHAR(20) DEFAULT 'medium', -- low, medium, high, critical
    sla_target_minutes INTEGER,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    first_response_at TIMESTAMP WITH TIME ZONE,
    response_time_minutes INTEGER,
    sla_status VARCHAR(20) DEFAULT 'pending', -- pending, ok, warning, breached
    assigned_to INTEGER REFERENCES users(id),
    escalated BOOLEAN DEFAULT FALSE,
    escalated_at TIMESTAMP WITH TIME ZONE,
    escalated_to INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_response_tracking_email ON email_response_tracking(email_id);
CREATE INDEX IF NOT EXISTS idx_email_response_tracking_status ON email_response_tracking(sla_status);
CREATE INDEX IF NOT EXISTS idx_email_response_tracking_assigned ON email_response_tracking(assigned_to);

-- 6. Graph Webhook Subscriptions - manage active subscriptions
CREATE TABLE IF NOT EXISTS graph_webhook_subscriptions (
    id SERIAL PRIMARY KEY,
    subscription_id VARCHAR(255) UNIQUE,
    resource VARCHAR(255) NOT NULL,
    change_types TEXT[] DEFAULT ARRAY['created'],
    notification_url TEXT NOT NULL,
    expiration_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    client_state VARCHAR(255),
    user_id INTEGER REFERENCES users(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_renewed_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_graph_subscriptions_active ON graph_webhook_subscriptions(is_active);
CREATE INDEX IF NOT EXISTS idx_graph_subscriptions_expiration ON graph_webhook_subscriptions(expiration_datetime);

-- 7. Automation Time Savings - track efficiency gains
CREATE TABLE IF NOT EXISTS automation_time_savings (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(500),
    processor_name VARCHAR(100) NOT NULL,
    action_type VARCHAR(100) NOT NULL, -- auto_response, lead_creation, document_classification, etc.
    time_saved_minutes INTEGER NOT NULL,
    details JSONB,
    triggered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_automation_time_savings_processor ON automation_time_savings(processor_name);
CREATE INDEX IF NOT EXISTS idx_automation_time_savings_triggered ON automation_time_savings(triggered_at);

-- Seed Data: Default Email Templates

INSERT INTO email_templates (name, subject, body, is_html, variables, category)
VALUES
    (
        'loan_application_received',
        'Your Loan Application Has Been Received',
        '<p>Dear {firstName},</p><p>Thank you for submitting your loan application. We have received your information and a loan officer will be in touch within 24 hours.</p><p>Your reference number is: <strong>{loanNumber}</strong></p><p>If you have any questions, please don''t hesitate to contact us.</p><p>Best regards,<br/>The Perennia Team</p>',
        TRUE,
        ARRAY['firstName', 'loanNumber'],
        'loan_application'
    ),
    (
        'document_received',
        'Documents Received - {documentType}',
        '<p>Dear {firstName},</p><p>We have received your {documentType}. Our team will review them shortly.</p><p>If we need any additional information, we will contact you.</p><p>Thank you for your prompt response.</p><p>Best regards,<br/>The Perennia Team</p>',
        TRUE,
        ARRAY['firstName', 'documentType'],
        'document'
    ),
    (
        'inquiry_auto_response',
        'Re: {originalSubject}',
        '<p>Dear {firstName},</p><p>Thank you for your inquiry. We have received your message and will respond within 24 hours.</p><p>If this is urgent, please call us at {phoneNumber}.</p><p>Best regards,<br/>The Perennia Team</p>',
        TRUE,
        ARRAY['firstName', 'originalSubject', 'phoneNumber'],
        'inquiry'
    ),
    (
        'sla_warning',
        'Action Required: Email Awaiting Response',
        '<p>Hi {loName},</p><p>The following email requires your attention and is approaching its SLA deadline:</p><ul><li><strong>From:</strong> {fromEmail}</li><li><strong>Subject:</strong> {subject}</li><li><strong>Received:</strong> {receivedAt}</li><li><strong>SLA Deadline:</strong> {slaDeadline}</li></ul><p>Please respond as soon as possible.</p>',
        TRUE,
        ARRAY['loName', 'fromEmail', 'subject', 'receivedAt', 'slaDeadline'],
        'sla'
    )
ON CONFLICT (name) DO NOTHING;

-- View: Email Processing Summary
CREATE OR REPLACE VIEW email_processing_summary AS
SELECT
    DATE(received_at) as date,
    COUNT(*) as total_emails,
    COUNT(CASE WHEN status = 'processed' THEN 1 END) as processed,
    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
    COUNT(CASE WHEN email_type = 'loan_application' THEN 1 END) as loan_applications,
    COUNT(CASE WHEN email_type = 'document_submission' THEN 1 END) as document_submissions,
    COUNT(CASE WHEN email_type = 'client_inquiry' THEN 1 END) as client_inquiries,
    SUM(COALESCE(time_saved_minutes, 0)) as total_time_saved_minutes
FROM email_tracking
WHERE received_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(received_at)
ORDER BY date DESC;

-- View: Processor Performance
CREATE OR REPLACE VIEW processor_performance_view AS
SELECT
    processor_name,
    COUNT(*) as total_runs,
    COUNT(CASE WHEN success THEN 1 END) as success_count,
    COUNT(CASE WHEN NOT success THEN 1 END) as failure_count,
    ROUND(100.0 * COUNT(CASE WHEN success THEN 1 END) / NULLIF(COUNT(*), 0), 2) as success_rate,
    SUM(COALESCE(time_saved_minutes, 0)) as total_time_saved,
    AVG(processing_time_ms) as avg_processing_time_ms
FROM email_processing_log
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY processor_name
ORDER BY total_runs DESC;

-- View: Daily Time Savings
CREATE OR REPLACE VIEW daily_time_savings AS
SELECT
    DATE(triggered_at) as date,
    processor_name,
    action_type,
    SUM(time_saved_minutes) as total_minutes,
    COUNT(*) as action_count
FROM automation_time_savings
WHERE triggered_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(triggered_at), processor_name, action_type
ORDER BY date DESC, total_minutes DESC;

SELECT 'Email webhook tables created successfully' as status;
