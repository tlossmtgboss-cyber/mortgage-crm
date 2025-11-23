-- Email Monitor System Migration
-- Creates 12 tables for intelligent email filtering with AI

-- 1. Email Monitor Addresses
CREATE TABLE IF NOT EXISTS email_monitor_addresses (
    id SERIAL PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL,
    description VARCHAR(500),
    monitor_type VARCHAR(20) DEFAULT 'from',
    is_active BOOLEAN DEFAULT TRUE,
    created_by INTEGER NOT NULL REFERENCES employees(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_monitor_addresses_email ON email_monitor_addresses(email_address);
CREATE INDEX IF NOT EXISTS idx_email_monitor_addresses_active ON email_monitor_addresses(is_active);

-- 2. Email Monitor Keywords
CREATE TABLE IF NOT EXISTS email_monitor_keywords (
    id SERIAL PRIMARY KEY,
    keyword_phrase VARCHAR(255) NOT NULL,
    search_location VARCHAR(20) DEFAULT 'both',
    match_type VARCHAR(20) DEFAULT 'contains',
    category VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_by INTEGER NOT NULL REFERENCES employees(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_monitor_keywords_phrase ON email_monitor_keywords(keyword_phrase);
CREATE INDEX IF NOT EXISTS idx_email_monitor_keywords_category ON email_monitor_keywords(category);
CREATE INDEX IF NOT EXISTS idx_email_monitor_keywords_active ON email_monitor_keywords(is_active);

-- 3. Email Monitor Rules
CREATE TABLE IF NOT EXISTS email_monitor_rules (
    id SERIAL PRIMARY KEY,
    rule_name VARCHAR(255) NOT NULL,
    description TEXT,
    match_logic VARCHAR(30) DEFAULT 'address_or_keyword',
    auto_assign_to_loan BOOLEAN DEFAULT FALSE,
    loan_match_strategy VARCHAR(30) DEFAULT 'loan_number',
    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    use_ai_filter BOOLEAN DEFAULT TRUE,
    min_confidence_score NUMERIC(3,2) DEFAULT 0.70,
    allow_spam_check BOOLEAN DEFAULT TRUE,
    require_crm_match BOOLEAN DEFAULT FALSE,
    enabled_providers VARCHAR(50) DEFAULT 'gmail,outlook',
    created_by INTEGER NOT NULL REFERENCES employees(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_monitor_rules_priority ON email_monitor_rules(priority);
CREATE INDEX IF NOT EXISTS idx_email_monitor_rules_active ON email_monitor_rules(is_active);

-- 4. Email Monitor Captured
CREATE TABLE IF NOT EXISTS email_monitor_captured (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES email_monitor_rules(id),
    email_provider VARCHAR(20) DEFAULT 'gmail',
    provider_message_id VARCHAR(255) NOT NULL,
    from_email VARCHAR(255),
    to_email TEXT,
    cc_email TEXT,
    subject TEXT,
    body_preview TEXT,
    received_date TIMESTAMP WITH TIME ZONE,
    matched_addresses JSONB,
    matched_keywords JSONB,
    auto_assigned_loan_id INTEGER REFERENCES loans(id),
    processing_status VARCHAR(30) DEFAULT 'captured',
    processing_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT unique_provider_message UNIQUE (email_provider, provider_message_id)
);
CREATE INDEX IF NOT EXISTS idx_email_monitor_captured_from ON email_monitor_captured(from_email);
CREATE INDEX IF NOT EXISTS idx_email_monitor_captured_received ON email_monitor_captured(received_date);
CREATE INDEX IF NOT EXISTS idx_email_monitor_captured_status ON email_monitor_captured(processing_status);
CREATE INDEX IF NOT EXISTS idx_email_monitor_captured_provider_received ON email_monitor_captured(email_provider, received_date);

-- 5. Email CRM Links
CREATE TABLE IF NOT EXISTS email_crm_links (
    id SERIAL PRIMARY KEY,
    captured_email_id INTEGER NOT NULL REFERENCES email_monitor_captured(id) ON DELETE CASCADE,
    entity_type VARCHAR(30) NOT NULL,
    entity_id INTEGER NOT NULL,
    link_confidence NUMERIC(3,2) DEFAULT 1.00,
    link_method VARCHAR(30) DEFAULT 'email_match',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by INTEGER REFERENCES employees(id),
    CONSTRAINT unique_email_entity_link UNIQUE (captured_email_id, entity_type, entity_id)
);
CREATE INDEX IF NOT EXISTS idx_email_crm_links_captured ON email_crm_links(captured_email_id);
CREATE INDEX IF NOT EXISTS idx_email_crm_links_entity ON email_crm_links(entity_type, entity_id);

-- 6. Email Relevance Analysis
CREATE TABLE IF NOT EXISTS email_relevance_analysis (
    id SERIAL PRIMARY KEY,
    email_provider VARCHAR(20) DEFAULT 'gmail',
    provider_message_id VARCHAR(255) NOT NULL,
    from_email VARCHAR(255),
    subject TEXT,
    is_relevant BOOLEAN,
    relevance_category VARCHAR(100),
    confidence_score NUMERIC(3,2),
    analysis_reason TEXT,
    matched_entities JSONB,
    filter_stage VARCHAR(30) NOT NULL,
    processing_time_ms INTEGER,
    was_captured BOOLEAN DEFAULT FALSE,
    user_feedback VARCHAR(30),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_relevance_analysis_relevant ON email_relevance_analysis(is_relevant);
CREATE INDEX IF NOT EXISTS idx_email_relevance_analysis_category ON email_relevance_analysis(relevance_category);
CREATE INDEX IF NOT EXISTS idx_email_relevance_analysis_created ON email_relevance_analysis(created_at);
CREATE INDEX IF NOT EXISTS idx_email_relevance_analysis_provider_message ON email_relevance_analysis(email_provider, provider_message_id);

-- 7. Email Filter Whitelist
CREATE TABLE IF NOT EXISTS email_filter_whitelist (
    id SERIAL PRIMARY KEY,
    email_pattern VARCHAR(255) NOT NULL,
    description VARCHAR(500),
    whitelist_type VARCHAR(20) DEFAULT 'email',
    auto_assign_category VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_by INTEGER NOT NULL REFERENCES employees(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_filter_whitelist_pattern ON email_filter_whitelist(email_pattern);
CREATE INDEX IF NOT EXISTS idx_email_filter_whitelist_active ON email_filter_whitelist(is_active);

-- 8. Email Filter Blacklist
CREATE TABLE IF NOT EXISTS email_filter_blacklist (
    id SERIAL PRIMARY KEY,
    email_pattern VARCHAR(255) NOT NULL,
    description VARCHAR(500),
    blacklist_type VARCHAR(20) DEFAULT 'email',
    reason VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_by INTEGER NOT NULL REFERENCES employees(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_filter_blacklist_pattern ON email_filter_blacklist(email_pattern);
CREATE INDEX IF NOT EXISTS idx_email_filter_blacklist_active ON email_filter_blacklist(is_active);

-- 9. Email Provider Config
CREATE TABLE IF NOT EXISTS email_provider_config (
    id SERIAL PRIMARY KEY,
    provider_name VARCHAR(20) UNIQUE NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    display_name VARCHAR(100),
    config_json JSONB,
    last_poll_time TIMESTAMP WITH TIME ZONE,
    total_emails_processed INTEGER DEFAULT 0,
    total_emails_captured INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_provider_config_enabled ON email_provider_config(is_enabled);

-- 10. Gmail OAuth Tokens
CREATE TABLE IF NOT EXISTS gmail_oauth_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER DEFAULT 1 UNIQUE,
    token_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- 11. Outlook OAuth Tokens
CREATE TABLE IF NOT EXISTS outlook_oauth_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER DEFAULT 1 UNIQUE,
    token_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- 12. Email Monitor Log
CREATE TABLE IF NOT EXISTS email_monitor_log (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL,
    rule_id INTEGER REFERENCES email_monitor_rules(id),
    captured_email_id INTEGER REFERENCES email_monitor_captured(id),
    details JSONB,
    emails_scanned INTEGER DEFAULT 0,
    emails_captured INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_monitor_log_event ON email_monitor_log(event_type);
CREATE INDEX IF NOT EXISTS idx_email_monitor_log_created ON email_monitor_log(created_at);

-- Seed Data

-- Default rule
INSERT INTO email_monitor_rules (rule_name, description, use_ai_filter, min_confidence_score, created_by)
VALUES ('Default AI Filter', 'Automatic email filtering with AI analysis', TRUE, 0.75, 1)
ON CONFLICT DO NOTHING;

-- Provider configs
INSERT INTO email_provider_config (provider_name, is_enabled, display_name, config_json)
VALUES
    ('gmail', TRUE, 'Gmail / Google Workspace', '{"polling_interval_minutes": 5, "max_results": 100}'),
    ('outlook', TRUE, 'Outlook / Microsoft 365', '{"polling_interval_minutes": 5, "max_results": 100}')
ON CONFLICT (provider_name) DO NOTHING;

-- Default whitelist (trusted vendors)
INSERT INTO email_filter_whitelist (email_pattern, description, whitelist_type, auto_assign_category, created_by)
VALUES
    ('*@docusign.com', 'DocuSign document signing', 'domain', 'CLOSING_DOCS', 1),
    ('*@optimalblue.com', 'Optimal Blue pricing engine', 'domain', 'RATE_LOCK', 1),
    ('*@stewart.com', 'Stewart Title', 'domain', 'THIRD_PARTY_VENDOR', 1),
    ('*@firstam.com', 'First American Title', 'domain', 'THIRD_PARTY_VENDOR', 1),
    ('*@fidelity.com', 'Fidelity National Title', 'domain', 'THIRD_PARTY_VENDOR', 1)
ON CONFLICT DO NOTHING;

-- Default blacklist (spam patterns)
INSERT INTO email_filter_blacklist (email_pattern, description, blacklist_type, reason, created_by)
VALUES
    ('noreply@*', 'No-reply automated emails', 'pattern', 'Automated bulk emails', 1),
    ('newsletter@*', 'Newsletter pattern', 'pattern', 'Marketing newsletters', 1),
    ('*@mailchimp.com', 'Mailchimp marketing', 'domain', 'Marketing platform', 1),
    ('*@constantcontact.com', 'Constant Contact', 'domain', 'Marketing platform', 1)
ON CONFLICT DO NOTHING;

-- Done
SELECT 'Email Monitor tables created successfully' as status;
