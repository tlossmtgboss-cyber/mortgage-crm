-- ============================================================================
-- SOC 2 Type II Compliance Tables — Perennia AI
-- Run: psql $DATABASE_URL -f migrations/soc2_tables.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. AUDIT LOG — Core audit trail for all system actions
-- Maps to: CC2 (Communication), CC4 (Monitoring), PI1 (Processing Integrity)
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Who
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    user_email      VARCHAR(255),
    user_role       VARCHAR(100),
    tenant_id       UUID,  -- Multi-tenant isolation
    
    -- What
    action          VARCHAR(50) NOT NULL,  -- AuditAction enum
    resource_type   VARCHAR(100),          -- e.g., 'loan_application', 'borrower', 'user'
    resource_id     VARCHAR(255),          -- ID of the affected resource
    
    -- Details
    description     TEXT,
    fields_accessed TEXT[],                -- Which fields were read/modified
    old_values      JSONB,                 -- Previous values (for updates)
    new_values      JSONB,                 -- New values (for creates/updates)
    
    -- Context
    ip_address      INET,
    user_agent      TEXT,
    request_method  VARCHAR(10),
    request_path    TEXT,
    request_id      UUID,                  -- Correlation ID
    session_id      VARCHAR(255),
    
    -- Result
    status_code     INTEGER,
    success         BOOLEAN DEFAULT TRUE,
    error_message   TEXT,
    
    -- Classification
    severity        VARCHAR(20) DEFAULT 'low',
    data_classification VARCHAR(20) DEFAULT 'internal',
    contains_pii    BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_audit_log_timestamp ON soc2_audit_log(timestamp DESC);
CREATE INDEX idx_audit_log_user_id ON soc2_audit_log(user_id);
CREATE INDEX idx_audit_log_tenant_id ON soc2_audit_log(tenant_id);
CREATE INDEX idx_audit_log_action ON soc2_audit_log(action);
CREATE INDEX idx_audit_log_resource ON soc2_audit_log(resource_type, resource_id);
CREATE INDEX idx_audit_log_severity ON soc2_audit_log(severity) WHERE severity IN ('high', 'critical');
CREATE INDEX idx_audit_log_request_id ON soc2_audit_log(request_id);

-- Partition by month for performance (optional, recommended for high-volume)
-- CREATE TABLE soc2_audit_log_y2025m01 PARTITION OF soc2_audit_log
--     FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');


-- ============================================================================
-- 2. ACCESS EVENTS — Authentication & authorization tracking
-- Maps to: CC6 (Access Controls)
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_access_event (
    id                  BIGSERIAL PRIMARY KEY,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Who
    user_id             UUID REFERENCES users(id) ON DELETE SET NULL,
    attempted_email     VARCHAR(255),
    tenant_id           UUID,
    
    -- What
    event_type          VARCHAR(50) NOT NULL,  -- login, logout, login_failed, mfa_challenge, etc.
    success             BOOLEAN NOT NULL,
    failure_reason      VARCHAR(255),
    
    -- Auth details
    auth_method         VARCHAR(50),  -- password, oauth, api_key, mfa
    mfa_method          VARCHAR(50),  -- totp, sms, email
    session_id          VARCHAR(255),
    token_id            VARCHAR(255),
    
    -- Context
    ip_address          INET,
    user_agent          TEXT,
    geo_location        VARCHAR(255),
    device_fingerprint  VARCHAR(255),
    
    -- Anomaly detection
    is_anomalous        BOOLEAN DEFAULT FALSE,
    anomaly_reason      TEXT,
    risk_score          INTEGER DEFAULT 0  -- 0-100
);

CREATE INDEX idx_access_event_timestamp ON soc2_access_event(timestamp DESC);
CREATE INDEX idx_access_event_user_id ON soc2_access_event(user_id);
CREATE INDEX idx_access_event_ip ON soc2_access_event(ip_address);
CREATE INDEX idx_access_event_type ON soc2_access_event(event_type);
CREATE INDEX idx_access_event_failed ON soc2_access_event(ip_address, timestamp)
    WHERE success = FALSE;
CREATE INDEX idx_access_event_anomalous ON soc2_access_event(timestamp)
    WHERE is_anomalous = TRUE;


-- ============================================================================
-- 3. SECURITY INCIDENTS — Incident response tracking
-- Maps to: CC7 (System Operations), CC2 (Communication)
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_security_incident (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Classification
    title           VARCHAR(500) NOT NULL,
    description     TEXT NOT NULL,
    category        VARCHAR(50) NOT NULL,   -- IncidentCategory enum
    severity        VARCHAR(20) NOT NULL,   -- SeverityLevel enum
    
    -- Status
    status          VARCHAR(30) NOT NULL DEFAULT 'open',  -- IncidentStatus enum
    
    -- People
    reported_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_to     UUID REFERENCES users(id) ON DELETE SET NULL,
    tenant_id       UUID,
    
    -- Impact
    affected_systems    TEXT[],
    affected_users      INTEGER DEFAULT 0,
    affected_records    INTEGER DEFAULT 0,
    data_compromised    BOOLEAN DEFAULT FALSE,
    pii_involved        BOOLEAN DEFAULT FALSE,
    
    -- Timeline
    detected_at         TIMESTAMPTZ,
    contained_at        TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    closed_at           TIMESTAMPTZ,
    
    -- Response
    root_cause          TEXT,
    remediation_steps   TEXT,
    preventive_measures TEXT,
    lessons_learned     TEXT,
    
    -- External reporting
    requires_notification   BOOLEAN DEFAULT FALSE,
    notification_sent_at    TIMESTAMPTZ,
    regulatory_reported     BOOLEAN DEFAULT FALSE,
    
    -- Evidence
    evidence_urls       TEXT[],
    related_audit_ids   BIGINT[],
    
    -- Post-mortem
    post_mortem_url     TEXT,
    post_mortem_completed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_incident_status ON soc2_security_incident(status);
CREATE INDEX idx_incident_severity ON soc2_security_incident(severity);
CREATE INDEX idx_incident_created ON soc2_security_incident(created_at DESC);
CREATE INDEX idx_incident_tenant ON soc2_security_incident(tenant_id);


-- ============================================================================
-- 4. INCIDENT TIMELINE — Detailed timeline entries for each incident
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_incident_timeline (
    id              BIGSERIAL PRIMARY KEY,
    incident_id     UUID NOT NULL REFERENCES soc2_security_incident(id) ON DELETE CASCADE,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    action          VARCHAR(100) NOT NULL,  -- e.g., 'status_change', 'assigned', 'note_added'
    actor_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    description     TEXT NOT NULL,
    
    old_value       TEXT,
    new_value       TEXT,
    
    is_automated    BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_incident_timeline_incident ON soc2_incident_timeline(incident_id, timestamp);


-- ============================================================================
-- 5. CHANGE RECORDS — Change management tracking
-- Maps to: CC8 (Change Management)
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_change_record (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- What
    title           VARCHAR(500) NOT NULL,
    description     TEXT NOT NULL,
    change_type     VARCHAR(50) NOT NULL,   -- ChangeType enum
    status          VARCHAR(30) NOT NULL DEFAULT 'requested',  -- ChangeStatus enum
    
    -- Who
    requested_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    approved_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    implemented_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    tenant_id       UUID,
    
    -- Details
    affected_systems    TEXT[],
    risk_level          VARCHAR(20) DEFAULT 'low',
    rollback_plan       TEXT,
    testing_evidence    TEXT,
    
    -- Timing
    scheduled_at        TIMESTAMPTZ,
    approved_at         TIMESTAMPTZ,
    implemented_at      TIMESTAMPTZ,
    verified_at         TIMESTAMPTZ,
    
    -- Git/deploy reference
    git_commit          VARCHAR(40),
    git_branch          VARCHAR(255),
    pull_request_url    TEXT,
    deployment_id       VARCHAR(255),
    
    -- Outcome
    success             BOOLEAN,
    post_implementation_notes TEXT
);

CREATE INDEX idx_change_record_status ON soc2_change_record(status);
CREATE INDEX idx_change_record_type ON soc2_change_record(change_type);
CREATE INDEX idx_change_record_created ON soc2_change_record(created_at DESC);


-- ============================================================================
-- 6. DATA CLASSIFICATION REGISTRY — Track sensitive data locations
-- Maps to: C1 (Confidentiality), P1-P8 (Privacy)
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_data_classification (
    id                  SERIAL PRIMARY KEY,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- What data
    table_name          VARCHAR(255) NOT NULL,
    column_name         VARCHAR(255) NOT NULL,
    
    -- Classification
    classification      VARCHAR(20) NOT NULL,  -- DataClassification enum
    is_pii              BOOLEAN DEFAULT FALSE,
    is_financial        BOOLEAN DEFAULT FALSE,
    is_encrypted        BOOLEAN DEFAULT FALSE,
    
    -- Access
    access_restricted   BOOLEAN DEFAULT TRUE,
    authorized_roles    TEXT[],
    
    -- Retention
    retention_policy    VARCHAR(50),
    retention_days      INTEGER,
    
    -- Notes
    description         TEXT,
    regulatory_basis    TEXT,  -- e.g., 'TRID', 'RESPA', 'CCPA', 'GLBA'
    
    UNIQUE(table_name, column_name)
);


-- ============================================================================
-- 7. COMPLIANCE CHECKS — Automated control testing results
-- Maps to: CC3 (Risk Assessment), CC4 (Monitoring)
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_compliance_check (
    id              BIGSERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Check info
    check_name      VARCHAR(255) NOT NULL,
    check_category  VARCHAR(100) NOT NULL,  -- e.g., 'CC6_access_controls', 'C1_encryption'
    description     TEXT,
    
    -- Result
    status          VARCHAR(20) NOT NULL,  -- ComplianceCheckStatus enum
    details         TEXT,
    evidence        JSONB,
    
    -- SOC 2 mapping
    trust_criteria  VARCHAR(10),   -- CC1-CC9, A1, PI1, C1, P1-P8
    control_id      VARCHAR(50),   -- Organization's internal control ID
    
    -- Remediation
    remediation_required    BOOLEAN DEFAULT FALSE,
    remediation_notes       TEXT,
    remediation_deadline    TIMESTAMPTZ,
    remediated_at           TIMESTAMPTZ
);

CREATE INDEX idx_compliance_check_run ON soc2_compliance_check(run_at DESC);
CREATE INDEX idx_compliance_check_status ON soc2_compliance_check(status) WHERE status != 'pass';
CREATE INDEX idx_compliance_check_category ON soc2_compliance_check(check_category);


-- ============================================================================
-- 8. SESSION TRACKING — Active session management
-- Maps to: CC6 (Access Controls)
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_active_session (
    id              VARCHAR(255) PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id       UUID,
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    
    ip_address      INET,
    user_agent      TEXT,
    device_fingerprint VARCHAR(255),
    
    is_active       BOOLEAN DEFAULT TRUE,
    terminated_reason VARCHAR(100)  -- expired, logout, forced, suspicious
);

CREATE INDEX idx_session_user ON soc2_active_session(user_id) WHERE is_active = TRUE;
CREATE INDEX idx_session_expires ON soc2_active_session(expires_at) WHERE is_active = TRUE;


-- ============================================================================
-- 9. API KEY REGISTRY — Track all API keys/service accounts
-- Maps to: CC6 (Access Controls)
-- ============================================================================
CREATE TABLE IF NOT EXISTS soc2_api_key_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Owner
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    tenant_id       UUID,
    
    -- Key info (store hash, never plaintext)
    key_hash        VARCHAR(255) NOT NULL,
    key_prefix      VARCHAR(10) NOT NULL,  -- First few chars for identification
    
    -- Permissions
    scopes          TEXT[] NOT NULL,
    
    -- Status
    is_active       BOOLEAN DEFAULT TRUE,
    expires_at      TIMESTAMPTZ,
    last_used_at    TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    revoked_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    revoke_reason   TEXT
);

CREATE INDEX idx_api_key_active ON soc2_api_key_registry(is_active) WHERE is_active = TRUE;


-- ============================================================================
-- TRIGGERS — Auto-update timestamps
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_incident_timestamp
    BEFORE UPDATE ON soc2_security_incident
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_change_record_timestamp
    BEFORE UPDATE ON soc2_change_record
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_data_classification_timestamp
    BEFORE UPDATE ON soc2_data_classification
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- ROW-LEVEL SECURITY — Multi-tenant isolation
-- ============================================================================
ALTER TABLE soc2_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE soc2_access_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE soc2_security_incident ENABLE ROW LEVEL SECURITY;
ALTER TABLE soc2_change_record ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only see their own tenant's data
-- Adjust the role name and session variable to match your auth setup
CREATE POLICY tenant_isolation_audit ON soc2_audit_log
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

CREATE POLICY tenant_isolation_access ON soc2_access_event
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

CREATE POLICY tenant_isolation_incident ON soc2_security_incident
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

CREATE POLICY tenant_isolation_change ON soc2_change_record
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);


COMMIT;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
DO $$
DECLARE
    tbl TEXT;
    tables TEXT[] := ARRAY[
        'soc2_audit_log', 'soc2_access_event', 'soc2_security_incident',
        'soc2_incident_timeline', 'soc2_change_record', 'soc2_data_classification',
        'soc2_compliance_check', 'soc2_active_session', 'soc2_api_key_registry'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables LOOP
        IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = tbl) THEN
            RAISE EXCEPTION 'Table % was not created', tbl;
        END IF;
    END LOOP;
    RAISE NOTICE 'All SOC 2 compliance tables created successfully.';
END $$;
