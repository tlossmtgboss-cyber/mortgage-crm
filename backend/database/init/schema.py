"""
Schema Creation - CREATE TABLE statements for standalone tables.

Tables created here are those not managed by SQLAlchemy's Base.metadata.create_all(),
either because they were added ad-hoc or need to exist regardless of ORM model registration.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_schema_creation(engine, Base, database_url: str, environment: str, auto_create: bool):
    """
    Create database tables.

    In production, skips Base.metadata.create_all() unless auto_create is True.
    Then creates standalone tables that are defined via raw DDL.
    """
    # Import models to register them with Base before create_all
    try:
        import salesforce_integration_models  # noqa: F401
    except Exception:
        pass

    # Skip auto-create in production unless explicitly enabled
    if environment == "production" and not auto_create:
        logger.info("Skipping Base.metadata.create_all() in production - use Alembic migrations")
    else:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")

    # Only create standalone tables if using PostgreSQL
    if database_url.startswith("sqlite"):
        return

    _create_integration_tables(engine)
    _create_document_intake_tables(engine)
    _create_api_keys_table(engine)
    _create_user_permissions_table(engine)
    _create_telephony_tables(engine)
    _create_call_monitoring_tables(engine)
    _create_tenant_tables(engine)
    _create_compliance_tables(engine)
    _create_workflow_tables(engine)
    _create_enterprise_tables(engine)


def _create_integration_tables(engine):
    """Create Salesforce integration tables (integration_profiles, oauth_states, oauth_pkce_store)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS integration_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL DEFAULT 'salesforce',
                    status VARCHAR(50) NOT NULL DEFAULT 'disconnected',
                    access_token_encrypted TEXT,
                    refresh_token_encrypted TEXT,
                    instance_url TEXT,
                    sf_org_id VARCHAR(100),
                    sf_user_id VARCHAR(100),
                    sf_username VARCHAR(255),
                    connected_at TIMESTAMP,
                    last_sync_at TIMESTAMP,
                    last_error TEXT,
                    field_map_version INTEGER DEFAULT 1,
                    sync_enabled BOOLEAN DEFAULT TRUE,
                    sync_interval_minutes INTEGER DEFAULT 15,
                    sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, provider)
                )
            """))
            conn.commit()
            logger.info("integration_profiles table created/verified")
    except Exception as e:
        logger.warning(f"integration_profiles table creation: {e}")

    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS oauth_states (
                    id SERIAL PRIMARY KEY,
                    state_token VARCHAR(255) UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    return_url TEXT,
                    state_metadata JSONB
                )
            """))
            conn.commit()
            logger.info("oauth_states table created/verified")
    except Exception as e:
        logger.warning(f"oauth_states table creation: {e}")

    # PKCE verifier storage
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS oauth_pkce_store (
                    id SERIAL PRIMARY KEY,
                    state VARCHAR(255) UNIQUE NOT NULL,
                    code_verifier TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            """))
            conn.commit()
            logger.info("oauth_pkce_store table created/verified")
    except Exception as e:
        logger.warning(f"oauth_pkce_store table creation: {e}")


def _create_document_intake_tables(engine):
    """Create email_intakes, attachment_intakes, classified_documents tables."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_intakes (
                    id SERIAL PRIMARY KEY,
                    message_id VARCHAR UNIQUE,
                    from_address VARCHAR NOT NULL,
                    from_name VARCHAR,
                    subject VARCHAR,
                    body_preview TEXT,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    matched_loan_id INTEGER REFERENCES loans(id),
                    matched_lead_id INTEGER REFERENCES leads(id),
                    match_status VARCHAR DEFAULT 'pending',
                    match_confidence FLOAT,
                    match_method VARCHAR,
                    matched_by_user_id INTEGER REFERENCES users(id),
                    matched_at TIMESTAMP,
                    processing_status VARCHAR DEFAULT 'pending',
                    processing_started_at TIMESTAMP,
                    processing_completed_at TIMESTAMP,
                    processing_error TEXT,
                    raw_email_data JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_email_intakes_match_status ON email_intakes(match_status);
                CREATE INDEX IF NOT EXISTS ix_email_intakes_received_at ON email_intakes(received_at);
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS attachment_intakes (
                    id SERIAL PRIMARY KEY,
                    email_intake_id INTEGER NOT NULL REFERENCES email_intakes(id),
                    filename VARCHAR NOT NULL,
                    content_type VARCHAR,
                    file_size INTEGER,
                    storage_path VARCHAR,
                    storage_url VARCHAR,
                    classification VARCHAR,
                    classification_confidence FLOAT,
                    extracted_data JSON,
                    processing_status VARCHAR DEFAULT 'pending',
                    processing_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_attachment_intakes_email_intake_id ON attachment_intakes(email_intake_id);
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS classified_documents (
                    id SERIAL PRIMARY KEY,
                    loan_id INTEGER REFERENCES loans(id),
                    lead_id INTEGER REFERENCES leads(id),
                    category VARCHAR NOT NULL,
                    sub_category VARCHAR,
                    document_name VARCHAR NOT NULL,
                    file_path VARCHAR,
                    file_url VARCHAR,
                    file_size INTEGER,
                    mime_type VARCHAR,
                    upload_source VARCHAR DEFAULT 'manual',
                    source_email_intake_id INTEGER REFERENCES email_intakes(id),
                    source_attachment_id INTEGER REFERENCES attachment_intakes(id),
                    extracted_data JSON,
                    ai_classification_confidence FLOAT,
                    verified_by_user_id INTEGER REFERENCES users(id),
                    verified_at TIMESTAMP,
                    expiration_date DATE,
                    notes TEXT,
                    version INTEGER DEFAULT 1,
                    is_current BOOLEAN DEFAULT TRUE,
                    created_by_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_classified_documents_loan_id ON classified_documents(loan_id);
                CREATE INDEX IF NOT EXISTS ix_classified_documents_category ON classified_documents(category);
            """))

            conn.commit()
            logger.info("Document intake tables created/verified")
    except Exception as e:
        logger.warning(f"Document intake tables creation: {e}")


def _create_api_keys_table(engine):
    """Create api_keys table."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR UNIQUE NOT NULL,
                    name VARCHAR NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP
                );
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_api_keys_key ON api_keys(key);
            """))
            conn.commit()
            logger.info("api_keys table created/verified")
    except Exception as e:
        logger.warning(f"api_keys table creation: {e}")


def _create_user_permissions_table(engine):
    """Create user_permissions table."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_permissions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    permission_key VARCHAR(255) NOT NULL,
                    granted BOOLEAN DEFAULT TRUE,
                    granted_by INTEGER REFERENCES users(id),
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_user_permission UNIQUE (user_id, permission_key)
                );
                CREATE INDEX IF NOT EXISTS idx_user_permissions_user ON user_permissions(user_id);
                CREATE INDEX IF NOT EXISTS idx_user_permissions_composite ON user_permissions(user_id, permission_key, granted);
            """))
            conn.commit()
            logger.info("user_permissions table created/verified")
    except Exception as e:
        logger.warning(f"user_permissions table creation: {e}")


def _create_telephony_tables(engine):
    """Create telephony tables (agent_telephony_settings, verified_caller_ids, etc.)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_telephony_settings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
                    cell_phone VARCHAR,
                    business_caller_id VARCHAR,
                    dialer_enabled BOOLEAN DEFAULT TRUE,
                    max_calls_per_day INTEGER DEFAULT 200,
                    max_concurrent_sessions INTEGER DEFAULT 1,
                    auto_advance BOOLEAN DEFAULT TRUE,
                    pause_between_calls INTEGER DEFAULT 3,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS verified_caller_ids (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR UNIQUE NOT NULL,
                    friendly_name VARCHAR,
                    verification_status VARCHAR DEFAULT 'pending',
                    provider_sid VARCHAR,
                    user_id INTEGER REFERENCES users(id),
                    verified_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS contact_dnc_status (
                    id SERIAL PRIMARY KEY,
                    phone_number VARCHAR UNIQUE NOT NULL,
                    reason VARCHAR,
                    added_by_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_dnc_phone ON contact_dnc_status(phone_number);

                DROP TABLE IF EXISTS active_calls;
                CREATE TABLE IF NOT EXISTS active_calls (
                    id SERIAL PRIMARY KEY,
                    contact_phone VARCHAR NOT NULL,
                    agent_id INTEGER REFERENCES users(id),
                    call_sid VARCHAR,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_active_calls_phone ON active_calls(contact_phone);

                CREATE TABLE IF NOT EXISTS call_logs (
                    id SERIAL PRIMARY KEY,
                    agent_id INTEGER REFERENCES users(id),
                    contact_phone VARCHAR NOT NULL,
                    contact_name VARCHAR,
                    lead_id INTEGER,
                    loan_id INTEGER,
                    referral_partner_id INTEGER,
                    mum_client_id INTEGER,
                    session_id INTEGER,
                    session_task_id INTEGER,
                    call_sid VARCHAR,
                    caller_id_used VARCHAR,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER,
                    outcome VARCHAR,
                    failure_reason VARCHAR,
                    disposition VARCHAR,
                    notes TEXT,
                    ai_note_summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Add missing columns to existing call_logs table
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS referral_partner_id INTEGER;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS mum_client_id INTEGER;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_id INTEGER;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_task_id INTEGER;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS caller_id_used VARCHAR;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS start_time TIMESTAMP;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS end_time TIMESTAMP;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS failure_reason VARCHAR;
                ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

                -- Migrate old column data if they exist
                UPDATE call_logs SET start_time = started_at WHERE start_time IS NULL AND started_at IS NOT NULL;
                UPDATE call_logs SET end_time = ended_at WHERE end_time IS NULL AND ended_at IS NOT NULL;
            """))
            conn.commit()
            logger.info("Telephony tables created/verified")
    except Exception as e:
        logger.warning(f"Telephony tables creation: {e}")


def _create_call_monitoring_tables(engine):
    """Create call monitoring tables (call_sessions, call_artifacts, call_risk_flags)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS call_sessions (
                    id VARCHAR(36) PRIMARY KEY,
                    organization_id INTEGER,
                    call_sid VARCHAR(255),
                    provider VARCHAR(50) DEFAULT 'telnyx',
                    capture_mode VARCHAR(50),
                    status VARCHAR(50) DEFAULT 'active',
                    direction VARCHAR(20),
                    from_number VARCHAR(50),
                    to_number VARCHAR(50),
                    lead_id INTEGER,
                    loan_id INTEGER,
                    user_id INTEGER,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    duration_seconds INTEGER,
                    recording_url TEXT,
                    transcript TEXT,
                    summary TEXT,
                    metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS call_artifacts (
                    id VARCHAR(36) PRIMARY KEY,
                    organization_id INTEGER,
                    call_session_id VARCHAR(36),
                    artifact_type VARCHAR(100),
                    agent_role VARCHAR(100),
                    content JSONB,
                    approval_status VARCHAR(50) DEFAULT 'pending',
                    approved_by INTEGER,
                    approved_at TIMESTAMP,
                    model_version VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS call_risk_flags (
                    id VARCHAR(36) PRIMARY KEY,
                    organization_id INTEGER,
                    call_session_id VARCHAR(36),
                    category VARCHAR(100),
                    severity VARCHAR(20),
                    description TEXT,
                    source_agent VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("Call monitoring tables created/verified (call_sessions, call_artifacts, call_risk_flags)")
    except Exception as e:
        logger.warning(f"Call monitoring tables note: {e}")


def _create_tenant_tables(engine):
    """Create tenant-related tables (email templates, legal docs, storage, org settings)."""
    # tenant_email_templates (WL-003)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tenant_email_templates (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    template_key VARCHAR(100) NOT NULL,
                    template_name VARCHAR(255) NOT NULL,
                    subject VARCHAR(500),
                    html_body TEXT,
                    text_body TEXT,
                    merge_fields JSONB DEFAULT '[]',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by INTEGER,
                    updated_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(organization_id, template_key)
                )
            """))
            conn.commit()
            logger.info("tenant_email_templates table created/verified (WL-003)")
    except Exception as e:
        logger.warning(f"tenant_email_templates table note: {e}")

    # tenant_legal_documents (WL-007)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tenant_legal_documents (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    document_type VARCHAR(100) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    content TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    is_published BOOLEAN DEFAULT FALSE,
                    published_at TIMESTAMP,
                    published_by INTEGER,
                    created_by INTEGER,
                    updated_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("tenant_legal_documents table created/verified (WL-007)")
    except Exception as e:
        logger.warning(f"tenant_legal_documents table note: {e}")

    # tenant_storage_usage (MTR-004)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tenant_storage_usage (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    storage_key VARCHAR(500) UNIQUE NOT NULL,
                    file_size_bytes BIGINT NOT NULL DEFAULT 0,
                    file_type VARCHAR(50) DEFAULT 'document',
                    uploaded_by_id INTEGER,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_tenant_storage_org
                    ON tenant_storage_usage (organization_id, is_deleted)
            """))
            conn.commit()
            logger.info("tenant_storage_usage table created/verified (MTR-004)")
    except Exception as e:
        logger.warning(f"tenant_storage_usage table note: {e}")

    # organization_settings (ER-5)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS organization_settings (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    setting_key VARCHAR(100) NOT NULL,
                    setting_value TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(organization_id, setting_key)
                )
            """))
            conn.commit()
            logger.info("organization_settings table created/verified (ER-5)")
    except Exception as e:
        logger.warning(f"organization_settings table note: {e}")


def _create_compliance_tables(engine):
    """Create compliance-related tables (regulatory_reports, data_subject_requests)."""
    # regulatory_reports (CMP-008)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS regulatory_reports (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    report_type VARCHAR(50) NOT NULL,
                    report_name VARCHAR(255) NOT NULL,
                    parameters JSONB DEFAULT '{}',
                    file_content TEXT,
                    file_format VARCHAR(20) DEFAULT 'csv',
                    record_count INTEGER DEFAULT 0,
                    status VARCHAR(50) DEFAULT 'generated',
                    generated_by INTEGER,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            logger.info("regulatory_reports table created/verified (CMP-008)")
    except Exception as e:
        logger.warning(f"regulatory_reports table note: {e}")

    # data_subject_requests (CMP-004 / GDPR DSAR)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS data_subject_requests (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER REFERENCES organizations(id),
                    request_type VARCHAR(50) NOT NULL DEFAULT 'access',
                    requestor_email VARCHAR(255) NOT NULL,
                    requestor_name VARCHAR(255),
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    due_date TIMESTAMP,
                    handled_by_id INTEGER REFERENCES users(id),
                    handled_at TIMESTAMP,
                    notes TEXT,
                    result_summary TEXT,
                    identity_verified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ix_dsr_org_id ON data_subject_requests(organization_id);
                CREATE INDEX IF NOT EXISTS ix_dsr_status ON data_subject_requests(status);
                CREATE INDEX IF NOT EXISTS ix_dsr_email ON data_subject_requests(requestor_email);
            """))
            conn.commit()
            logger.info("data_subject_requests table created/verified")
    except Exception as e:
        logger.warning(f"data_subject_requests table note: {e}")


def _create_workflow_tables(engine):
    """Create workflow-related tables (company_holidays, loan_state_audit_log)."""
    # company_holidays (WF-001)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS company_holidays (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL DEFAULT 0,
                    holiday_date DATE NOT NULL,
                    holiday_name VARCHAR(100),
                    is_recurring BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT uq_holiday UNIQUE (organization_id, holiday_date)
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_holidays_lookup
                    ON company_holidays (organization_id, holiday_date)
            """))
            conn.commit()
            logger.info("company_holidays table created/verified (WF-001)")
    except Exception as e:
        logger.warning(f"company_holidays table note: {e}")

    # loan_state_audit_log
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS loan_state_audit_log (
                    id SERIAL PRIMARY KEY,
                    loan_id INTEGER NOT NULL,
                    from_stage VARCHAR(100),
                    to_stage VARCHAR(100),
                    salesforce_raw_stage VARCHAR(200),
                    action VARCHAR(50) NOT NULL,
                    is_backward_movement BOOLEAN DEFAULT FALSE,
                    warnings JSONB DEFAULT '[]'::jsonb,
                    admin_review_reason TEXT,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_loan_state_audit_loan_id
                    ON loan_state_audit_log (loan_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_loan_state_audit_created
                    ON loan_state_audit_log (created_at)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_loan_state_audit_action
                    ON loan_state_audit_log (action)
            """))
            conn.commit()
            logger.info("loan_state_audit_log table created/verified")
    except Exception as e:
        logger.warning(f"loan_state_audit_log table note: {e}")


def _create_enterprise_tables(engine):
    """Create enterprise tables (scheduled_reports)."""
    # scheduled_reports (ER-9.11)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS scheduled_reports (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL,
                    created_by_id INTEGER NOT NULL,
                    report_type VARCHAR(50) NOT NULL,
                    export_format VARCHAR(20) NOT NULL DEFAULT 'pdf',
                    frequency VARCHAR(20) NOT NULL DEFAULT 'weekly',
                    recipients JSONB NOT NULL DEFAULT '[]',
                    title VARCHAR(255),
                    day_of_week INTEGER,
                    day_of_month INTEGER,
                    hour_utc INTEGER NOT NULL DEFAULT 8,
                    is_active BOOLEAN DEFAULT TRUE,
                    last_sent_at TIMESTAMPTZ,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TIMESTAMPTZ,
                    last_error TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    last_generation_ms INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_scheduled_reports_org
                    ON scheduled_reports (organization_id, is_active)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_scheduled_reports_retry
                    ON scheduled_reports (status, next_retry_at)
                    WHERE status = 'retrying'
            """))
            conn.commit()
            logger.info("scheduled_reports table created/verified (ER-9.11)")
    except Exception as e:
        logger.warning(f"scheduled_reports table note: {e}")
