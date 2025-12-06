-- Email Response Training System
-- Extends reconciliation for email handling with AI learning
-- Allows AI to learn when to auto-respond based on user approvals

-- =============================================================================
-- 1. EMAIL RESPONSE PATTERNS - Tracks learned response behaviors
-- =============================================================================

CREATE TABLE IF NOT EXISTS email_response_patterns (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),

    -- Pattern identification
    pattern_type VARCHAR(50) NOT NULL,  -- 'sender_domain', 'subject_pattern', 'email_intent', 'sender_email'
    pattern_value VARCHAR(500) NOT NULL,  -- The actual pattern (e.g., 'titlecompany.com', 'Clear to Close')

    -- Response behavior
    response_type VARCHAR(50) NOT NULL,  -- 'auto_reply', 'create_task', 'update_status', 'forward', 'archive', 'ignore'
    response_template_id INTEGER REFERENCES email_templates(id),  -- For auto-reply
    response_config JSONB,  -- Additional config: forward_to, task_type, status_value, etc.

    -- Confidence tracking
    approval_count INTEGER DEFAULT 1,
    rejection_count INTEGER DEFAULT 0,
    confidence_score NUMERIC(3,2) DEFAULT 0.50,  -- Calculated from approvals

    -- Auto-execution settings
    is_active BOOLEAN DEFAULT FALSE,  -- User must explicitly enable
    auto_execute_threshold NUMERIC(3,2) DEFAULT 0.85,  -- Min confidence to auto-execute
    requires_entity_match BOOLEAN DEFAULT TRUE,  -- Must match a lead/loan

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_matched_at TIMESTAMP WITH TIME ZONE,
    last_approved_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_response_patterns_user ON email_response_patterns(user_id);
CREATE INDEX IF NOT EXISTS idx_email_response_patterns_type ON email_response_patterns(pattern_type, pattern_value);
CREATE INDEX IF NOT EXISTS idx_email_response_patterns_active ON email_response_patterns(is_active, confidence_score);
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_response_patterns_unique
    ON email_response_patterns(user_id, pattern_type, pattern_value, response_type);


-- =============================================================================
-- 2. EMAIL RESPONSE LOG - Tracks all email response actions
-- =============================================================================

CREATE TABLE IF NOT EXISTS email_response_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),

    -- Email reference
    email_id VARCHAR(500) NOT NULL,  -- Graph message ID
    extracted_data_id INTEGER REFERENCES extracted_data(id),
    incoming_event_id INTEGER REFERENCES incoming_data_events(id),

    -- Email metadata for pattern matching
    sender_email VARCHAR(255),
    sender_domain VARCHAR(255),
    subject VARCHAR(500),
    email_intent VARCHAR(100),
    matched_entity_type VARCHAR(50),
    matched_entity_id INTEGER,

    -- Response details
    response_type VARCHAR(50) NOT NULL,  -- What was done
    response_pattern_id INTEGER REFERENCES email_response_patterns(id),  -- Which pattern matched
    was_auto_executed BOOLEAN DEFAULT FALSE,  -- Did AI do this automatically?

    -- AI recommendation
    ai_recommended_action VARCHAR(50),
    ai_confidence NUMERIC(3,2),
    ai_reasoning TEXT,

    -- User decision
    user_action VARCHAR(50),  -- 'approved', 'rejected', 'modified', 'manual'
    user_modifications JSONB,  -- What did user change?

    -- Result
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    responded_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_email_response_log_user ON email_response_log(user_id);
CREATE INDEX IF NOT EXISTS idx_email_response_log_email ON email_response_log(email_id);
CREATE INDEX IF NOT EXISTS idx_email_response_log_sender ON email_response_log(sender_domain);
CREATE INDEX IF NOT EXISTS idx_email_response_log_created ON email_response_log(created_at);


-- =============================================================================
-- 3. EMAIL RESPONSE QUEUE - Pending responses awaiting review
-- =============================================================================

CREATE TABLE IF NOT EXISTS email_response_queue (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),

    -- Email reference
    email_id VARCHAR(500) NOT NULL,
    incoming_event_id INTEGER REFERENCES incoming_data_events(id),
    extracted_data_id INTEGER REFERENCES extracted_data(id),

    -- Email content
    sender_email VARCHAR(255),
    sender_name VARCHAR(255),
    subject VARCHAR(500),
    body_preview TEXT,
    received_at TIMESTAMP WITH TIME ZONE,

    -- Classification
    email_intent VARCHAR(100),
    intent_confidence NUMERIC(3,2),
    matched_entity_type VARCHAR(50),
    matched_entity_id INTEGER,
    matched_entity_name VARCHAR(255),

    -- AI Recommendation
    recommended_action VARCHAR(50) NOT NULL,  -- 'reply', 'forward', 'create_task', 'update_status', 'archive', 'ignore'
    recommended_response TEXT,  -- Draft response if reply
    recommendation_reasoning TEXT,
    recommendation_confidence NUMERIC(3,2),

    -- Matched pattern (if any)
    matched_pattern_id INTEGER REFERENCES email_response_patterns(id),
    pattern_confidence NUMERIC(3,2),

    -- Status
    status VARCHAR(50) DEFAULT 'pending',  -- 'pending', 'approved', 'rejected', 'auto_executed', 'expired'
    priority VARCHAR(20) DEFAULT 'normal',  -- 'low', 'normal', 'high', 'urgent'

    -- Processing
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    executed_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE  -- For time-sensitive emails
);

CREATE INDEX IF NOT EXISTS idx_email_response_queue_user ON email_response_queue(user_id);
CREATE INDEX IF NOT EXISTS idx_email_response_queue_status ON email_response_queue(status);
CREATE INDEX IF NOT EXISTS idx_email_response_queue_priority ON email_response_queue(priority, created_at);
CREATE INDEX IF NOT EXISTS idx_email_response_queue_email ON email_response_queue(email_id);


-- =============================================================================
-- 4. EMAIL RESPONSE TEMPLATES - User-customizable response templates
-- =============================================================================

-- Add email response templates if not already in email_templates
INSERT INTO email_templates (name, subject, body, is_html, variables, category)
VALUES
    (
        'document_request_followup',
        'Following Up: {documentType} Needed',
        '<p>Hi {firstName},</p><p>Just following up on the documents we requested. We still need your {documentType} to continue processing your loan.</p><p>Please upload or send them at your earliest convenience.</p><p>Thanks,<br/>{loName}</p>',
        TRUE,
        ARRAY['firstName', 'documentType', 'loName'],
        'email_response'
    ),
    (
        'status_update_acknowledgment',
        'Re: {originalSubject}',
        '<p>Hi {senderName},</p><p>Thank you for the update. I''ve noted the information in our system.</p><p>The current status for {borrowerName} is now: <strong>{currentStatus}</strong></p><p>Please let me know if you have any questions.</p><p>Best,<br/>{loName}</p>',
        TRUE,
        ARRAY['senderName', 'originalSubject', 'borrowerName', 'currentStatus', 'loName'],
        'email_response'
    ),
    (
        'vendor_acknowledgment',
        'Re: {originalSubject}',
        '<p>Thank you for this update. I''ve received and logged the information.</p><p>Best,<br/>{loName}</p>',
        TRUE,
        ARRAY['originalSubject', 'loName'],
        'email_response'
    ),
    (
        'client_question_response',
        'Re: {originalSubject}',
        '<p>Hi {firstName},</p><p>Thank you for reaching out!</p><p>{customResponse}</p><p>Please let me know if you have any other questions.</p><p>Best,<br/>{loName}</p>',
        TRUE,
        ARRAY['firstName', 'originalSubject', 'customResponse', 'loName'],
        'email_response'
    )
ON CONFLICT (name) DO NOTHING;


-- =============================================================================
-- 5. EXTEND EXTRACTED_DATA FOR EMAIL ACTIONS
-- =============================================================================

-- Add columns to extracted_data if they don't exist
DO $$
BEGIN
    -- Email action recommendation
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'extracted_data' AND column_name = 'email_action_type') THEN
        ALTER TABLE extracted_data ADD COLUMN email_action_type VARCHAR(50);
    END IF;

    -- Draft response
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'extracted_data' AND column_name = 'draft_response') THEN
        ALTER TABLE extracted_data ADD COLUMN draft_response TEXT;
    END IF;

    -- Response template used
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'extracted_data' AND column_name = 'response_template_id') THEN
        ALTER TABLE extracted_data ADD COLUMN response_template_id INTEGER REFERENCES email_templates(id);
    END IF;

    -- Email sent flag
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'extracted_data' AND column_name = 'response_sent') THEN
        ALTER TABLE extracted_data ADD COLUMN response_sent BOOLEAN DEFAULT FALSE;
    END IF;

    -- Response sent timestamp
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'extracted_data' AND column_name = 'response_sent_at') THEN
        ALTER TABLE extracted_data ADD COLUMN response_sent_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;


-- =============================================================================
-- 6. VIEWS FOR ANALYTICS
-- =============================================================================

-- Response pattern effectiveness
CREATE OR REPLACE VIEW email_pattern_effectiveness AS
SELECT
    erp.id,
    erp.user_id,
    erp.pattern_type,
    erp.pattern_value,
    erp.response_type,
    erp.approval_count,
    erp.rejection_count,
    erp.confidence_score,
    erp.is_active,
    CASE
        WHEN (erp.approval_count + erp.rejection_count) > 0
        THEN ROUND(erp.approval_count::NUMERIC / (erp.approval_count + erp.rejection_count) * 100, 1)
        ELSE 0
    END as approval_rate,
    erp.last_approved_at,
    erp.created_at
FROM email_response_patterns erp
ORDER BY erp.confidence_score DESC;


-- User email response stats
CREATE OR REPLACE VIEW user_email_response_stats AS
SELECT
    erl.user_id,
    DATE(erl.created_at) as date,
    COUNT(*) as total_emails,
    COUNT(CASE WHEN erl.user_action = 'approved' THEN 1 END) as approved,
    COUNT(CASE WHEN erl.user_action = 'rejected' THEN 1 END) as rejected,
    COUNT(CASE WHEN erl.was_auto_executed THEN 1 END) as auto_executed,
    AVG(erl.ai_confidence) as avg_ai_confidence
FROM email_response_log erl
WHERE erl.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY erl.user_id, DATE(erl.created_at)
ORDER BY date DESC;


-- Pending responses by user
CREATE OR REPLACE VIEW pending_email_responses AS
SELECT
    erq.user_id,
    u.email as user_email,
    COUNT(*) as pending_count,
    COUNT(CASE WHEN erq.priority = 'urgent' THEN 1 END) as urgent_count,
    COUNT(CASE WHEN erq.priority = 'high' THEN 1 END) as high_count,
    MIN(erq.created_at) as oldest_pending
FROM email_response_queue erq
JOIN users u ON u.id = erq.user_id
WHERE erq.status = 'pending'
GROUP BY erq.user_id, u.email;


-- =============================================================================
-- 7. FUNCTIONS FOR CONFIDENCE CALCULATION
-- =============================================================================

CREATE OR REPLACE FUNCTION update_pattern_confidence()
RETURNS TRIGGER AS $$
BEGIN
    -- Recalculate confidence when approval/rejection counts change
    NEW.confidence_score := CASE
        WHEN (NEW.approval_count + NEW.rejection_count) > 0
        THEN ROUND(
            (NEW.approval_count::NUMERIC / (NEW.approval_count + NEW.rejection_count)) *
            LEAST(1.0, (NEW.approval_count::NUMERIC / 10.0)),  -- Scale up with more approvals
            2
        )
        ELSE 0.50
    END;

    -- Auto-activate if confidence exceeds threshold and enough approvals
    IF NEW.confidence_score >= NEW.auto_execute_threshold
       AND NEW.approval_count >= 5
       AND NEW.rejection_count = 0 THEN
        -- Don't auto-activate, but set confidence high
        -- User must explicitly enable is_active
        NULL;
    END IF;

    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_pattern_confidence ON email_response_patterns;
CREATE TRIGGER trigger_update_pattern_confidence
    BEFORE UPDATE OF approval_count, rejection_count ON email_response_patterns
    FOR EACH ROW
    EXECUTE FUNCTION update_pattern_confidence();


SELECT 'Email response training tables created successfully' as status;
