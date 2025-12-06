-- Perennia AI Email Orchestrator - Database Schema
-- Run this script to create all required tables

-- Email Tracking - Main table for tracking all incoming emails
CREATE TABLE IF NOT EXISTS email_tracking (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) NOT NULL UNIQUE,
    message_id VARCHAR(500),
    conversation_id VARCHAR(255),
    subject TEXT,
    from_email VARCHAR(255) NOT NULL,
    from_name VARCHAR(255),
    to_emails JSONB DEFAULT '[]',
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    has_attachments BOOLEAN DEFAULT FALSE,
    importance VARCHAR(20) DEFAULT 'normal',
    correlation_id VARCHAR(100),
    user_id INTEGER,
    status VARCHAR(50) DEFAULT 'pending', -- pending, processed, failed, no_match
    processors_run INTEGER DEFAULT 0,
    total_time_saved_minutes DECIMAL(10,2) DEFAULT 0,
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_email_tracking_from ON email_tracking(from_email);
CREATE INDEX IF NOT EXISTS idx_email_tracking_received ON email_tracking(received_at);
CREATE INDEX IF NOT EXISTS idx_email_tracking_status ON email_tracking(status);

-- Email Processing Log - Records of each processor run
CREATE TABLE IF NOT EXISTS email_processing_log (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) NOT NULL,
    processor_name VARCHAR(100) NOT NULL,
    action VARCHAR(100),
    success BOOLEAN NOT NULL,
    time_saved_minutes INTEGER DEFAULT 0,
    created_records JSONB DEFAULT '[]',
    sent_emails JSONB DEFAULT '[]',
    created_tasks JSONB DEFAULT '[]',
    error TEXT,
    metadata JSONB DEFAULT '{}',
    correlation_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_processing_log_email ON email_processing_log(email_id);
CREATE INDEX IF NOT EXISTS idx_processing_log_processor ON email_processing_log(processor_name);
CREATE INDEX IF NOT EXISTS idx_processing_log_created ON email_processing_log(created_at);

-- Email Processing Errors - Error tracking
CREATE TABLE IF NOT EXISTS email_processing_errors (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) NOT NULL,
    processor_name VARCHAR(100),
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    correlation_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_processing_errors_email ON email_processing_errors(email_id);
CREATE INDEX IF NOT EXISTS idx_processing_errors_created ON email_processing_errors(created_at);

-- Email Templates - Template storage
CREATE TABLE IF NOT EXISTS email_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    is_html BOOLEAN DEFAULT TRUE,
    variables TEXT[] DEFAULT '{}',
    category VARCHAR(50),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Sent Emails - Log of all emails sent
CREATE TABLE IF NOT EXISTS sent_emails (
    id SERIAL PRIMARY KEY,
    template_name VARCHAR(100),
    to_emails TEXT[] NOT NULL,
    cc_emails TEXT[],
    subject TEXT NOT NULL,
    variables JSONB DEFAULT '{}',
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sent_emails_sent ON sent_emails(sent_at);

-- Email Processing Queue - For batch processing
CREATE TABLE IF NOT EXISTS email_processing_queue (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) NOT NULL UNIQUE,
    message_id VARCHAR(500),
    priority INTEGER DEFAULT 50,
    status VARCHAR(20) DEFAULT 'pending', -- pending, processing, completed, failed, retry
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON email_processing_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_priority ON email_processing_queue(priority DESC);

-- Email Response Tracking - SLA monitoring
CREATE TABLE IF NOT EXISTS email_response_tracking (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) NOT NULL UNIQUE,
    from_email VARCHAR(255) NOT NULL,
    subject TEXT,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sla_priority VARCHAR(20) NOT NULL, -- critical, high, medium, low
    sla_deadline TIMESTAMP WITH TIME ZONE NOT NULL,
    sla_status VARCHAR(20) DEFAULT 'pending', -- pending, warning, breached, ok
    responded_at TIMESTAMP WITH TIME ZONE,
    response_time_minutes INTEGER,
    assigned_to INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_response_tracking_status ON email_response_tracking(sla_status);
CREATE INDEX IF NOT EXISTS idx_response_tracking_deadline ON email_response_tracking(sla_deadline);
CREATE INDEX IF NOT EXISTS idx_response_tracking_from ON email_response_tracking(from_email);

-- SLA Breaches - Record of all SLA breaches
CREATE TABLE IF NOT EXISTS sla_breaches (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) NOT NULL,
    from_email VARCHAR(255),
    subject TEXT,
    assigned_to INTEGER,
    breach_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    hours_overdue DECIMAL(10,2),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_sla_breaches_time ON sla_breaches(breach_time);

-- Automation Time Savings - Track time saved
CREATE TABLE IF NOT EXISTS automation_time_savings (
    id SERIAL PRIMARY KEY,
    processor_name VARCHAR(100) NOT NULL,
    email_id VARCHAR(255),
    time_saved_minutes INTEGER NOT NULL,
    action VARCHAR(100),
    triggered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time_savings_triggered ON automation_time_savings(triggered_at);
CREATE INDEX IF NOT EXISTS idx_time_savings_processor ON automation_time_savings(processor_name);

-- Email Processing Summary - Daily aggregates
CREATE TABLE IF NOT EXISTS email_processing_summary (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    total_received INTEGER DEFAULT 0,
    total_processed INTEGER DEFAULT 0,
    total_auto_responded INTEGER DEFAULT 0,
    time_saved_minutes DECIMAL(10,2) DEFAULT 0,
    sla_compliance_rate DECIMAL(5,2) DEFAULT 100,
    pending_count INTEGER DEFAULT 0,
    processor_stats JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Client Inquiries - Track inquiry patterns
CREATE TABLE IF NOT EXISTS client_inquiries (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) NOT NULL,
    from_email VARCHAR(255) NOT NULL,
    inquiry_type VARCHAR(50), -- status, document, rate, general, complaint
    urgency VARCHAR(20), -- low, medium, high, critical
    sentiment VARCHAR(20), -- positive, neutral, negative
    summary TEXT,
    auto_responded BOOLEAN DEFAULT FALSE,
    lead_id INTEGER,
    loan_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_client_inquiries_type ON client_inquiries(inquiry_type);
CREATE INDEX IF NOT EXISTS idx_client_inquiries_from ON client_inquiries(from_email);

-- Invoices - Invoice tracking
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    vendor_name VARCHAR(255) NOT NULL,
    vendor_email VARCHAR(255),
    invoice_number VARCHAR(100),
    amount DECIMAL(12,2),
    due_date DATE,
    category VARCHAR(50), -- appraisal, title, credit, legal, other
    loan_id INTEGER,
    status VARCHAR(50) DEFAULT 'pending', -- pending, approved, paid, rejected
    received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    approved_by INTEGER,
    approved_at TIMESTAMP WITH TIME ZONE,
    paid_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_loan ON invoices(loan_id);

-- Document Receipts - Track document uploads via email
CREATE TABLE IF NOT EXISTS document_receipts (
    id SERIAL PRIMARY KEY,
    email_id VARCHAR(255) NOT NULL,
    from_email VARCHAR(255) NOT NULL,
    document_type VARCHAR(100),
    category VARCHAR(50), -- income, asset, property, identity, credit, other
    lead_id INTEGER,
    loan_id INTEGER,
    attachment_count INTEGER DEFAULT 0,
    extracted_data JSONB DEFAULT '{}',
    received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_by INTEGER,
    status VARCHAR(50) DEFAULT 'pending' -- pending, reviewed, approved, rejected
);

CREATE INDEX IF NOT EXISTS idx_doc_receipts_lead ON document_receipts(lead_id);
CREATE INDEX IF NOT EXISTS idx_doc_receipts_loan ON document_receipts(loan_id);

-- Processor Performance - Track processor metrics
CREATE TABLE IF NOT EXISTS processor_performance (
    id SERIAL PRIMARY KEY,
    processor_name VARCHAR(100) NOT NULL,
    date DATE NOT NULL,
    total_runs INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    avg_processing_time_ms INTEGER DEFAULT 0,
    time_saved_minutes INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(processor_name, date)
);

-- Webhook Subscriptions - Track Graph API subscriptions
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id SERIAL PRIMARY KEY,
    subscription_id VARCHAR(255) NOT NULL UNIQUE,
    resource VARCHAR(255) NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    notification_url TEXT NOT NULL,
    expiration_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    client_state VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    renewed_at TIMESTAMP WITH TIME ZONE
);

-- Default Email Templates
INSERT INTO email_templates (name, subject, body, is_html, variables, category) VALUES
(
    'loan_application_received',
    'Application Received - We''ll Be In Touch Soon!',
    '<p>Dear {borrowerName},</p>
<p>Thank you for submitting your {loanType} loan application. We have successfully received your information and our team is reviewing it now.</p>
<p><strong>What happens next?</strong></p>
<ul>
<li>A loan officer will contact you within 24 hours</li>
<li>We may request additional documentation</li>
<li>Once complete, we''ll provide you with loan options</li>
</ul>
<p>If you have any questions in the meantime, please don''t hesitate to reach out.</p>
<p>Best regards,<br>The Perennia AI Team</p>',
    TRUE,
    ARRAY['borrowerName', 'loanType', 'timestamp'],
    'application'
),
(
    'document_received',
    'Documents Received - Thank You!',
    '<p>Hi {firstName},</p>
<p>We''ve received your {documentType}. Our team will review them and let you know if we need anything else.</p>
<p>Thank you for your prompt response!</p>
<p>Best regards,<br>The Perennia AI Team</p>',
    TRUE,
    ARRAY['firstName', 'documentType'],
    'document'
),
(
    'sla_warning',
    'Action Required: Pending Response',
    '<p>Hi {assigneeName},</p>
<p>The following email requires your response:</p>
<p><strong>From:</strong> {fromEmail}<br>
<strong>Subject:</strong> {subject}<br>
<strong>Received:</strong> {receivedAt}<br>
<strong>SLA Deadline:</strong> {deadline}</p>
<p>Please respond as soon as possible to maintain our response time standards.</p>',
    TRUE,
    ARRAY['assigneeName', 'fromEmail', 'subject', 'receivedAt', 'deadline'],
    'sla'
)
ON CONFLICT (name) DO NOTHING;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name IN ('email_tracking', 'email_processing_queue', 'email_response_tracking',
                          'email_processing_summary', 'processor_performance')
    LOOP
        EXECUTE format('
            DROP TRIGGER IF EXISTS update_%I_updated_at ON %I;
            CREATE TRIGGER update_%I_updated_at
            BEFORE UPDATE ON %I
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        ', t, t, t, t);
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_app_user;

COMMENT ON TABLE email_tracking IS 'Main table tracking all incoming emails processed by the orchestrator';
COMMENT ON TABLE email_processing_log IS 'Detailed log of each processor run on emails';
COMMENT ON TABLE email_response_tracking IS 'SLA monitoring for emails requiring responses';
COMMENT ON TABLE automation_time_savings IS 'Tracks time saved through automation for ROI reporting';
