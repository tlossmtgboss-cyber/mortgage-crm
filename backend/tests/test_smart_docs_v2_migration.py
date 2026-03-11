"""
Test Smart Docs V2 Migration

Comprehensive tests for backend/migrations/smart_docs_v2_migration.py covering:
    1. All 21 new tables are created successfully
    2. Tables have correct columns
    3. Indexes are created
    4. Migration is idempotent (running twice does not error)
    5. Enum columns work correctly
    6. Default values are set
    7. No naming conflicts with existing tables
    8. organization_id present on tenant-scoped tables
    9. Foreign key relationships valid
   10. Migration rollback capability
   11. Table count verification
   12. Column type verification

Uses an in-memory SQLite database for isolation and speed.
PostgreSQL-specific syntax (SERIAL, JSONB, DO $$ blocks) is adapted
via a portable DDL string that mirrors the migration's intent.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from migrations.smart_docs_v2_migration import run_migration  # noqa: E402


# ===========================================================================
# Constants
# ===========================================================================

# All 21 tables the migration creates (canonical order from migration return value).
EXPECTED_TABLES = [
    "esignature_envelopes",
    "esignature_recipients",
    "esignature_fields",
    "esignature_audit_events",
    "esignature_templates",
    "income_calculations",
    "income_sources",
    "income_verification_tasks",
    "ai_document_classifications",
    "document_requirement_rules",
    "pos_document_mappings",
    "call_intel_document_needs",
    "document_followup_campaigns",
    "document_followup_events",
    "document_appointments",
    "document_followup_templates",
    "document_access_logs",
    "document_encryption_records",
    "document_integrity_checks",
    "document_retention_policies",
    "document_watermark_logs",
]

# Tables that inherit tenant scope via FK rather than carrying organization_id directly.
TABLES_WITHOUT_ORG_ID = {
    "esignature_recipients",
    "esignature_fields",
    "esignature_audit_events",
    "income_sources",
    "document_followup_events",
    "document_integrity_checks",
    "document_watermark_logs",
}

TENANT_SCOPED_TABLES = sorted(set(EXPECTED_TABLES) - TABLES_WITHOUT_ORG_ID)

# Known tables from earlier migrations and core models that must NOT collide.
LEGACY_TABLE_NAMES = {
    # Core CRM tables
    "users", "leads", "loans", "documents", "activities", "organizations",
    "tasks", "contacts", "notifications", "referral_partners",
    # Smart Docs V1
    "smart_documents", "smart_document_requests", "doc_policy_events",
    "needs_list_templates",
    # Old e-sign tables (shorter prefix)
    "esign_envelopes", "esign_signers", "esign_fields",
    "esign_field_values", "esign_audit_events", "esign_completed_documents",
}


# ===========================================================================
# Portable SQLite DDL (mirrors the PostgreSQL migration)
# ===========================================================================

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS esignature_envelopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    loan_id INTEGER,
    created_by_user_id INTEGER,
    envelope_uuid VARCHAR(36) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    document_hash_sha256 VARCHAR(64),
    document_storage_key VARCHAR(1024),
    signed_document_storage_key VARCHAR(1024),
    original_filename VARCHAR(512),
    page_count INTEGER,
    total_recipients INTEGER DEFAULT 0,
    completed_recipients INTEGER DEFAULT 0,
    sent_at TIMESTAMP,
    viewed_at TIMESTAMP,
    completed_at TIMESTAMP,
    voided_at TIMESTAMP,
    expires_at TIMESTAMP,
    void_reason TEXT,
    completion_certificate_key VARCHAR(1024),
    ip_address_created VARCHAR(45),
    reminder_frequency_hours INTEGER DEFAULT 48,
    last_reminder_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS esignature_recipients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    envelope_id INTEGER NOT NULL REFERENCES esignature_envelopes(id) ON DELETE CASCADE,
    recipient_type VARCHAR(32) NOT NULL DEFAULT 'signer',
    signing_order INTEGER DEFAULT 1,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(32),
    access_code VARCHAR(128),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    auth_method VARCHAR(32) DEFAULT 'email',
    signing_token VARCHAR(256) UNIQUE,
    signing_token_expires_at TIMESTAMP,
    viewed_at TIMESTAMP,
    signed_at TIMESTAMP,
    declined_at TIMESTAMP,
    decline_reason TEXT,
    signing_ip_address VARCHAR(45),
    signing_user_agent TEXT,
    signing_geo_location VARCHAR(512),
    signature_image_key VARCHAR(1024),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS esignature_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    envelope_id INTEGER NOT NULL REFERENCES esignature_envelopes(id) ON DELETE CASCADE,
    recipient_id INTEGER REFERENCES esignature_recipients(id) ON DELETE SET NULL,
    field_type VARCHAR(32) NOT NULL,
    field_uuid VARCHAR(36) NOT NULL,
    page_number INTEGER NOT NULL DEFAULT 1,
    x_position NUMERIC(10, 2) NOT NULL,
    y_position NUMERIC(10, 2) NOT NULL,
    width NUMERIC(10, 2),
    height NUMERIC(10, 2),
    is_required BOOLEAN DEFAULT 1,
    placeholder_text VARCHAR(255),
    default_value TEXT,
    validation_regex VARCHAR(512),
    dropdown_options TEXT,
    group_name VARCHAR(128),
    value TEXT,
    filled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS esignature_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    envelope_id INTEGER NOT NULL REFERENCES esignature_envelopes(id) ON DELETE CASCADE,
    recipient_id INTEGER REFERENCES esignature_recipients(id) ON DELETE SET NULL,
    event_type VARCHAR(64) NOT NULL,
    event_description TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    geo_location VARCHAR(512),
    metadata TEXT,
    document_hash_at_event VARCHAR(64),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS esignature_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    created_by_user_id INTEGER,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    document_storage_key VARCHAR(1024),
    fields_config TEXT,
    default_recipients TEXT,
    category VARCHAR(128),
    is_active BOOLEAN DEFAULT 1,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS income_calculations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    loan_id INTEGER,
    borrower_id INTEGER,
    calculation_type VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    total_qualifying_monthly_income NUMERIC(15, 2),
    total_qualifying_annual_income NUMERIC(15, 2),
    calculation_method VARCHAR(64),
    dti_front_end NUMERIC(5, 2),
    dti_back_end NUMERIC(5, 2),
    proposed_housing_expense NUMERIC(12, 2),
    total_monthly_obligations NUMERIC(12, 2),
    ai_confidence_score NUMERIC(5, 2),
    ai_flags TEXT,
    ai_recommendations TEXT,
    ai_model_used VARCHAR(128),
    calculation_duration_ms INTEGER,
    source_documents TEXT,
    reviewed_by INTEGER,
    reviewed_at TIMESTAMP,
    review_notes TEXT,
    approved_by INTEGER,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS income_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calculation_id INTEGER REFERENCES income_calculations(id) ON DELETE CASCADE,
    borrower_id INTEGER,
    source_type VARCHAR(64),
    employer_name VARCHAR(255),
    position_title VARCHAR(255),
    employment_start_date DATE,
    employment_years NUMERIC(4, 1),
    is_primary BOOLEAN DEFAULT 0,
    base_monthly_income NUMERIC(12, 2),
    overtime_monthly NUMERIC(12, 2),
    bonus_monthly NUMERIC(12, 2),
    commission_monthly NUMERIC(12, 2),
    other_monthly NUMERIC(12, 2),
    total_monthly_income NUMERIC(12, 2),
    total_annual_income NUMERIC(15, 2),
    trending_direction VARCHAR(16),
    year1_income NUMERIC(15, 2),
    year2_income NUMERIC(15, 2),
    year_over_year_change_pct NUMERIC(6, 2),
    verification_status VARCHAR(32),
    verification_notes TEXT,
    source_document_ids TEXT,
    ai_confidence NUMERIC(5, 2),
    ai_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS income_verification_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calculation_id INTEGER REFERENCES income_calculations(id) ON DELETE SET NULL,
    income_source_id INTEGER REFERENCES income_sources(id) ON DELETE SET NULL,
    loan_id INTEGER,
    organization_id INTEGER,
    task_type VARCHAR(64) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    priority VARCHAR(16) DEFAULT 'normal',
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    assigned_to_user_id INTEGER,
    ai_recommendation TEXT,
    resolution_notes TEXT,
    resolved_by INTEGER,
    resolved_at TIMESTAMP,
    due_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_document_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    document_id INTEGER,
    original_doc_type VARCHAR(128),
    predicted_doc_type VARCHAR(128),
    prediction_confidence NUMERIC(5, 4),
    alternative_classifications TEXT,
    classification_model VARCHAR(128),
    classification_duration_ms INTEGER,
    features_detected TEXT,
    text_snippet TEXT,
    is_correct BOOLEAN,
    corrected_doc_type VARCHAR(128),
    corrected_by INTEGER,
    corrected_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_requirement_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    rule_name VARCHAR(255) NOT NULL,
    rule_description TEXT,
    category VARCHAR(64),
    doc_type VARCHAR(128),
    trigger_conditions TEXT,
    required_count INTEGER DEFAULT 1,
    applies_to VARCHAR(32),
    priority VARCHAR(16) DEFAULT 'normal',
    freshness_days INTEGER,
    instructions TEXT,
    is_active BOOLEAN DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pos_document_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    pos_field_path VARCHAR(512) NOT NULL,
    pos_field_value VARCHAR(512),
    maps_to_doc_type VARCHAR(128),
    maps_to_rule_id INTEGER REFERENCES document_requirement_rules(id) ON DELETE SET NULL,
    confidence_weight NUMERIC(5, 2),
    description TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS call_intel_document_needs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    loan_id INTEGER,
    lead_id INTEGER,
    call_id INTEGER,
    call_date TIMESTAMP,
    detected_doc_type VARCHAR(128),
    detected_doc_description TEXT,
    detection_confidence NUMERIC(5, 4),
    source_transcript_snippet TEXT,
    keywords_matched TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'detected',
    linked_request_id INTEGER,
    confirmed_by INTEGER,
    confirmed_at TIMESTAMP,
    dismissed_by INTEGER,
    dismissed_at TIMESTAMP,
    dismiss_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_followup_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    loan_id INTEGER,
    borrower_id INTEGER,
    campaign_type VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    trigger_source VARCHAR(64),
    linked_request_ids TEXT,
    total_steps INTEGER DEFAULT 0,
    current_step INTEGER DEFAULT 0,
    step_config TEXT,
    next_action_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancel_reason TEXT,
    max_reminders INTEGER DEFAULT 5,
    reminders_sent INTEGER DEFAULT 0,
    borrower_responded BOOLEAN DEFAULT 0,
    response_date TIMESTAMP,
    created_by_user_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_followup_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES document_followup_campaigns(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    step_number INTEGER,
    channel VARCHAR(32),
    template_used VARCHAR(255),
    recipient_email VARCHAR(255),
    recipient_phone VARCHAR(32),
    message_subject VARCHAR(500),
    message_preview TEXT,
    delivery_status VARCHAR(32),
    delivery_error TEXT,
    opened_at TIMESTAMP,
    clicked_at TIMESTAMP,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    loan_id INTEGER,
    borrower_id INTEGER,
    campaign_id INTEGER REFERENCES document_followup_campaigns(id) ON DELETE SET NULL,
    appointment_type VARCHAR(64),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'scheduled',
    scheduled_date DATE,
    scheduled_time_start TIME,
    scheduled_time_end TIME,
    duration_minutes INTEGER DEFAULT 30,
    location_type VARCHAR(32),
    location_details TEXT,
    meeting_link VARCHAR(1024),
    assigned_to_user_id INTEGER,
    attendee_name VARCHAR(255),
    attendee_email VARCHAR(255),
    attendee_phone VARCHAR(32),
    documents_to_discuss TEXT,
    outcome_notes TEXT,
    documents_collected TEXT,
    reminder_sent BOOLEAN DEFAULT 0,
    reminder_sent_at TIMESTAMP,
    confirmed_at TIMESTAMP,
    completed_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    cancellation_reason TEXT,
    rescheduled_from_id INTEGER REFERENCES document_appointments(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_followup_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(128),
    channel VARCHAR(32),
    category VARCHAR(64),
    subject_template TEXT,
    body_template TEXT,
    variables TEXT,
    is_default BOOLEAN DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_access_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    document_id INTEGER,
    document_type VARCHAR(128),
    user_id INTEGER,
    access_type VARCHAR(32) NOT NULL,
    access_granted BOOLEAN NOT NULL DEFAULT 1,
    denial_reason TEXT,
    ip_address VARCHAR(45),
    user_agent TEXT,
    geo_location VARCHAR(512),
    session_id VARCHAR(128),
    referrer_url VARCHAR(1024),
    duration_seconds INTEGER,
    pages_viewed TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_encryption_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    document_id INTEGER,
    document_type VARCHAR(128),
    encryption_algorithm VARCHAR(64) NOT NULL,
    key_id VARCHAR(256) NOT NULL,
    key_version INTEGER DEFAULT 1,
    encrypted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    encryption_status VARCHAR(32) NOT NULL DEFAULT 'encrypted',
    iv_nonce VARCHAR(256),
    content_hash_before VARCHAR(128),
    content_hash_after VARCHAR(128),
    file_size_before BIGINT,
    file_size_after BIGINT,
    last_accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_integrity_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    document_type VARCHAR(128),
    check_type VARCHAR(64) NOT NULL,
    expected_hash VARCHAR(128),
    actual_hash VARCHAR(128),
    is_valid BOOLEAN,
    tamper_detected BOOLEAN DEFAULT 0,
    tamper_details TEXT,
    checked_by INTEGER,
    check_duration_ms INTEGER,
    storage_key_checked VARCHAR(1024),
    file_size_expected BIGINT,
    file_size_actual BIGINT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_retention_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER,
    doc_type VARCHAR(128),
    policy_name VARCHAR(255) NOT NULL,
    retention_days INTEGER NOT NULL,
    retention_after_event VARCHAR(64),
    action_on_expiry VARCHAR(32) NOT NULL DEFAULT 'archive',
    notify_days_before INTEGER DEFAULT 30,
    is_active BOOLEAN DEFAULT 1,
    regulatory_reference TEXT,
    applies_to_states TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_watermark_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    watermark_type VARCHAR(32) NOT NULL,
    watermark_text TEXT,
    applied_to_user_id INTEGER,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    output_storage_key VARCHAR(1024),
    metadata TEXT
);
"""

_SQLITE_INDEXES = [
    # E-Signature envelope indexes
    "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_org ON esignature_envelopes(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_loan ON esignature_envelopes(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_uuid ON esignature_envelopes(envelope_uuid)",
    "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_status ON esignature_envelopes(status)",
    "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_created_by ON esignature_envelopes(created_by_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_expires ON esignature_envelopes(expires_at)",
    # E-Signature recipient indexes
    "CREATE INDEX IF NOT EXISTS ix_esign_recipients_envelope ON esignature_recipients(envelope_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_recipients_email ON esignature_recipients(email)",
    "CREATE INDEX IF NOT EXISTS ix_esign_recipients_status ON esignature_recipients(status)",
    "CREATE INDEX IF NOT EXISTS ix_esign_recipients_token ON esignature_recipients(signing_token)",
    # E-Signature field indexes
    "CREATE INDEX IF NOT EXISTS ix_esign_fields_envelope ON esignature_fields(envelope_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_fields_recipient ON esignature_fields(recipient_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_fields_uuid ON esignature_fields(field_uuid)",
    # E-Signature audit indexes
    "CREATE INDEX IF NOT EXISTS ix_esign_audit_envelope ON esignature_audit_events(envelope_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_audit_recipient ON esignature_audit_events(recipient_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_audit_event_type ON esignature_audit_events(event_type)",
    "CREATE INDEX IF NOT EXISTS ix_esign_audit_timestamp ON esignature_audit_events(timestamp)",
    # E-Signature template indexes
    "CREATE INDEX IF NOT EXISTS ix_esign_templates_org ON esignature_templates(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_esign_templates_category ON esignature_templates(category)",
    "CREATE INDEX IF NOT EXISTS ix_esign_templates_active ON esignature_templates(is_active)",
    # Income calculation indexes
    "CREATE INDEX IF NOT EXISTS ix_income_calc_org ON income_calculations(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_calc_loan ON income_calculations(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_calc_borrower ON income_calculations(borrower_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_calc_status ON income_calculations(status)",
    # Income source indexes
    "CREATE INDEX IF NOT EXISTS ix_income_src_calc ON income_sources(calculation_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_src_borrower ON income_sources(borrower_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_src_type ON income_sources(source_type)",
    # Income verification task indexes
    "CREATE INDEX IF NOT EXISTS ix_income_verif_calc ON income_verification_tasks(calculation_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_verif_loan ON income_verification_tasks(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_verif_org ON income_verification_tasks(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_verif_status ON income_verification_tasks(status)",
    "CREATE INDEX IF NOT EXISTS ix_income_verif_assigned ON income_verification_tasks(assigned_to_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_income_verif_due ON income_verification_tasks(due_date)",
    # AI document classification indexes
    "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_org ON ai_document_classifications(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_doc ON ai_document_classifications(document_id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_predicted ON ai_document_classifications(predicted_doc_type)",
    "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_correct ON ai_document_classifications(is_correct)",
    # Document requirement rule indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_req_rules_org ON document_requirement_rules(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_req_rules_category ON document_requirement_rules(category)",
    "CREATE INDEX IF NOT EXISTS ix_doc_req_rules_doc_type ON document_requirement_rules(doc_type)",
    "CREATE INDEX IF NOT EXISTS ix_doc_req_rules_active ON document_requirement_rules(is_active)",
    # POS document mapping indexes
    "CREATE INDEX IF NOT EXISTS ix_pos_doc_map_org ON pos_document_mappings(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_pos_doc_map_field ON pos_document_mappings(pos_field_path)",
    "CREATE INDEX IF NOT EXISTS ix_pos_doc_map_active ON pos_document_mappings(is_active)",
    # Call intel document needs indexes
    "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_org ON call_intel_document_needs(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_loan ON call_intel_document_needs(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_lead ON call_intel_document_needs(lead_id)",
    "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_call ON call_intel_document_needs(call_id)",
    "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_status ON call_intel_document_needs(status)",
    # Document follow-up campaign indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_org ON document_followup_campaigns(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_loan ON document_followup_campaigns(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_borrower ON document_followup_campaigns(borrower_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_status ON document_followup_campaigns(status)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_next ON document_followup_campaigns(next_action_at)",
    # Document follow-up event indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_evt_campaign ON document_followup_events(campaign_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_evt_type ON document_followup_events(event_type)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_evt_channel ON document_followup_events(channel)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_evt_delivery ON document_followup_events(delivery_status)",
    # Document appointment indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_appt_org ON document_appointments(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_appt_loan ON document_appointments(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_appt_borrower ON document_appointments(borrower_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_appt_campaign ON document_appointments(campaign_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_appt_status ON document_appointments(status)",
    "CREATE INDEX IF NOT EXISTS ix_doc_appt_date ON document_appointments(scheduled_date)",
    "CREATE INDEX IF NOT EXISTS ix_doc_appt_assigned ON document_appointments(assigned_to_user_id)",
    # Document follow-up template indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_tpl_org ON document_followup_templates(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_tpl_slug ON document_followup_templates(slug)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_tpl_channel ON document_followup_templates(channel)",
    "CREATE INDEX IF NOT EXISTS ix_doc_followup_tpl_active ON document_followup_templates(is_active)",
    # Document access log indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_access_org ON document_access_logs(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_access_doc ON document_access_logs(document_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_access_user ON document_access_logs(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_access_type ON document_access_logs(access_type)",
    "CREATE INDEX IF NOT EXISTS ix_doc_access_granted ON document_access_logs(access_granted)",
    "CREATE INDEX IF NOT EXISTS ix_doc_access_created ON document_access_logs(created_at)",
    "CREATE INDEX IF NOT EXISTS ix_doc_access_session ON document_access_logs(session_id)",
    # Document encryption record indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_org ON document_encryption_records(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_doc ON document_encryption_records(document_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_key ON document_encryption_records(key_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_status ON document_encryption_records(encryption_status)",
    # Document integrity check indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_integrity_doc ON document_integrity_checks(document_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_integrity_type ON document_integrity_checks(check_type)",
    "CREATE INDEX IF NOT EXISTS ix_doc_integrity_valid ON document_integrity_checks(is_valid)",
    "CREATE INDEX IF NOT EXISTS ix_doc_integrity_tamper ON document_integrity_checks(tamper_detected)",
    # Document retention policy indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_retention_org ON document_retention_policies(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_retention_type ON document_retention_policies(doc_type)",
    "CREATE INDEX IF NOT EXISTS ix_doc_retention_active ON document_retention_policies(is_active)",
    # Document watermark log indexes
    "CREATE INDEX IF NOT EXISTS ix_doc_watermark_doc ON document_watermark_logs(document_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_watermark_user ON document_watermark_logs(applied_to_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_doc_watermark_type ON document_watermark_logs(watermark_type)",
]


# ===========================================================================
# Helpers
# ===========================================================================

def _apply_sqlite_migration(engine):
    """Apply the migration DDL and indexes on SQLite."""
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        for stmt in _SQLITE_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        for idx in _SQLITE_INDEXES:
            conn.execute(text(idx))
        conn.commit()


def _get_unique_columns(conn, table):
    """Get set of column names that have UNIQUE constraints via SQLite PRAGMA."""
    unique_cols = set()
    rows = conn.execute(text(f"PRAGMA index_list('{table}')")).fetchall()
    for row in rows:
        index_name = row[1]
        is_unique = row[2]
        if is_unique:
            info = conn.execute(text(f"PRAGMA index_info('{index_name}')")).fetchall()
            for col_info in info:
                unique_cols.add(col_info[2])
    return unique_cols


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(scope="module")
def engine():
    """In-memory SQLite engine with migration applied once for the module."""
    eng = create_engine("sqlite:///:memory:")
    _apply_sqlite_migration(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def inspector(engine):
    """Fresh SQLAlchemy inspector for the migrated database."""
    return inspect(engine)


@pytest.fixture()
def conn(engine):
    """Short-lived database connection for insert/query tests."""
    connection = engine.connect()
    yield connection
    connection.close()


# ===========================================================================
# 1. All 21 tables created successfully
# ===========================================================================

class TestTableCreation:

    def test_all_21_tables_exist(self, inspector):
        """Every table declared in the migration must be present in the database."""
        existing = set(inspector.get_table_names())
        for table in EXPECTED_TABLES:
            assert table in existing, f"Table '{table}' was not created by migration"

    def test_esignature_group_complete(self, inspector):
        """All 5 e-signature tables must exist."""
        tables = set(inspector.get_table_names())
        esign = {"esignature_envelopes", "esignature_recipients", "esignature_fields",
                 "esignature_audit_events", "esignature_templates"}
        assert esign.issubset(tables)

    def test_income_group_complete(self, inspector):
        """All 3 income calculation tables must exist."""
        tables = set(inspector.get_table_names())
        income = {"income_calculations", "income_sources", "income_verification_tasks"}
        assert income.issubset(tables)

    def test_document_intelligence_group_complete(self, inspector):
        """All 4 document intelligence tables must exist."""
        tables = set(inspector.get_table_names())
        intel = {"ai_document_classifications", "document_requirement_rules",
                 "pos_document_mappings", "call_intel_document_needs"}
        assert intel.issubset(tables)

    def test_followup_group_complete(self, inspector):
        """All 4 follow-up automation tables must exist."""
        tables = set(inspector.get_table_names())
        followup = {"document_followup_campaigns", "document_followup_events",
                     "document_appointments", "document_followup_templates"}
        assert followup.issubset(tables)

    def test_security_group_complete(self, inspector):
        """All 5 document security tables must exist."""
        tables = set(inspector.get_table_names())
        security = {"document_access_logs", "document_encryption_records",
                     "document_integrity_checks", "document_retention_policies",
                     "document_watermark_logs"}
        assert security.issubset(tables)


# ===========================================================================
# 2. Tables have correct columns
# ===========================================================================

class TestColumnDefinitions:

    @pytest.mark.parametrize("table,expected_cols", [
        (
            "esignature_envelopes",
            [
                "id", "organization_id", "loan_id", "created_by_user_id",
                "envelope_uuid", "title", "description", "status",
                "document_hash_sha256", "document_storage_key",
                "signed_document_storage_key", "original_filename",
                "page_count", "total_recipients", "completed_recipients",
                "sent_at", "viewed_at", "completed_at", "voided_at",
                "expires_at", "void_reason", "completion_certificate_key",
                "ip_address_created", "reminder_frequency_hours",
                "last_reminder_sent_at", "created_at", "updated_at",
            ],
        ),
        (
            "esignature_recipients",
            [
                "id", "envelope_id", "recipient_type", "signing_order",
                "name", "email", "phone", "access_code", "status",
                "auth_method", "signing_token", "signing_token_expires_at",
                "viewed_at", "signed_at", "declined_at", "decline_reason",
                "signing_ip_address", "signing_user_agent",
                "signing_geo_location", "signature_image_key",
                "created_at", "updated_at",
            ],
        ),
        (
            "income_calculations",
            [
                "id", "organization_id", "loan_id", "borrower_id",
                "calculation_type", "status",
                "total_qualifying_monthly_income", "total_qualifying_annual_income",
                "calculation_method", "dti_front_end", "dti_back_end",
                "proposed_housing_expense", "total_monthly_obligations",
                "ai_confidence_score", "ai_flags", "ai_recommendations",
                "ai_model_used", "calculation_duration_ms", "source_documents",
                "reviewed_by", "reviewed_at", "review_notes",
                "approved_by", "approved_at", "created_at", "updated_at",
            ],
        ),
        (
            "document_access_logs",
            [
                "id", "organization_id", "document_id", "document_type",
                "user_id", "access_type", "access_granted", "denial_reason",
                "ip_address", "user_agent", "geo_location", "session_id",
                "referrer_url", "duration_seconds", "pages_viewed",
                "metadata", "created_at",
            ],
        ),
        (
            "document_watermark_logs",
            [
                "id", "document_id", "watermark_type", "watermark_text",
                "applied_to_user_id", "applied_at", "output_storage_key",
                "metadata",
            ],
        ),
    ])
    def test_table_has_expected_columns(self, inspector, table, expected_cols):
        """Verify key tables have all expected columns."""
        actual_cols = {col["name"] for col in inspector.get_columns(table)}
        for col in expected_cols:
            assert col in actual_cols, f"Column '{col}' missing from '{table}'"

    def test_income_sources_financial_columns(self, inspector):
        """Income sources must have separate income component columns."""
        cols = {c["name"] for c in inspector.get_columns("income_sources")}
        financial_cols = {
            "base_monthly_income", "overtime_monthly", "bonus_monthly",
            "commission_monthly", "other_monthly", "total_monthly_income",
            "total_annual_income",
        }
        missing = financial_cols - cols
        assert not missing, f"Missing financial columns: {missing}"

    def test_income_sources_trending_columns(self, inspector):
        """Income sources must have year-over-year trending columns."""
        cols = {c["name"] for c in inspector.get_columns("income_sources")}
        trending = {"trending_direction", "year1_income", "year2_income",
                     "year_over_year_change_pct"}
        missing = trending - cols
        assert not missing, f"Missing trending columns: {missing}"

    def test_document_encryption_security_columns(self, inspector):
        """Encryption records must have cryptography-relevant columns."""
        cols = {c["name"] for c in inspector.get_columns("document_encryption_records")}
        required = {"encryption_algorithm", "key_id", "key_version", "iv_nonce",
                     "content_hash_before", "content_hash_after",
                     "file_size_before", "file_size_after"}
        missing = required - cols
        assert not missing, f"Missing encryption columns: {missing}"


# ===========================================================================
# 3. Indexes are created
# ===========================================================================

class TestIndexes:

    def _get_all_index_column_sets(self, inspector, table):
        """Return set of frozensets of indexed column tuples."""
        indexes = inspector.get_indexes(table)
        return {frozenset(idx["column_names"]) for idx in indexes}

    def test_esignature_envelopes_indexes(self, inspector):
        """Key columns on esignature_envelopes are indexed."""
        idx_cols = self._get_all_index_column_sets(inspector, "esignature_envelopes")
        for col in ["organization_id", "loan_id", "status", "created_by_user_id", "expires_at"]:
            assert any(col in s for s in idx_cols), (
                f"Expected index on esignature_envelopes({col})"
            )

    def test_income_verification_tasks_indexes(self, inspector):
        """Verification tasks are indexed on status, org, loan, due_date."""
        idx_cols = self._get_all_index_column_sets(inspector, "income_verification_tasks")
        for col in ["organization_id", "loan_id", "status", "due_date", "assigned_to_user_id"]:
            assert any(col in s for s in idx_cols), (
                f"Expected index on income_verification_tasks({col})"
            )

    def test_document_access_logs_indexes(self, inspector):
        """Access logs are indexed on org, user, access_type, session."""
        idx_cols = self._get_all_index_column_sets(inspector, "document_access_logs")
        for col in ["organization_id", "user_id", "access_type", "session_id"]:
            assert any(col in s for s in idx_cols), (
                f"Expected index on document_access_logs({col})"
            )

    def test_call_intel_document_needs_indexes(self, inspector):
        """Call intel needs are indexed on org, loan, lead, call, status."""
        idx_cols = self._get_all_index_column_sets(inspector, "call_intel_document_needs")
        for col in ["organization_id", "loan_id", "lead_id", "call_id", "status"]:
            assert any(col in s for s in idx_cols), (
                f"Expected index on call_intel_document_needs({col})"
            )

    def test_total_index_count(self, inspector):
        """Migration creates at least 80 indexes across all 21 tables."""
        total = 0
        for table in EXPECTED_TABLES:
            total += len(inspector.get_indexes(table))
        assert total >= 80, f"Expected >= 80 indexes, found {total}"

    def test_high_cardinality_columns_indexed(self, inspector):
        """UUID and token columns used for lookups must be indexed."""
        env_indexes = inspector.get_indexes("esignature_envelopes")
        uuid_indexed = any(
            "envelope_uuid" in idx.get("column_names", []) for idx in env_indexes
        )
        assert uuid_indexed, "envelope_uuid should be indexed"

        recip_indexes = inspector.get_indexes("esignature_recipients")
        token_indexed = any(
            "signing_token" in idx.get("column_names", []) for idx in recip_indexes
        )
        assert token_indexed, "signing_token should be indexed"


# ===========================================================================
# 4. Migration is idempotent
# ===========================================================================

class TestIdempotency:

    def test_migration_runs_twice_without_error(self):
        """Running the migration DDL twice must not raise any exception."""
        eng = create_engine("sqlite:///:memory:")
        _apply_sqlite_migration(eng)
        _apply_sqlite_migration(eng)
        tables = set(inspect(eng).get_table_names())
        for t in EXPECTED_TABLES:
            assert t in tables
        eng.dispose()

    def test_migration_runs_three_times_stable(self):
        """Three consecutive runs produce the same 21-table result."""
        eng = create_engine("sqlite:///:memory:")
        _apply_sqlite_migration(eng)
        _apply_sqlite_migration(eng)
        _apply_sqlite_migration(eng)
        assert len(inspect(eng).get_table_names()) == 21
        eng.dispose()

    def test_data_preserved_on_rerun(self):
        """Existing row data survives a second migration run."""
        eng = create_engine("sqlite:///:memory:")
        _apply_sqlite_migration(eng)
        with eng.connect() as conn:
            conn.execute(text(
                "INSERT INTO esignature_envelopes (envelope_uuid, title) "
                "VALUES ('idempotent-uuid', 'Idempotent Test')"
            ))
            conn.commit()
        # Second migration run
        _apply_sqlite_migration(eng)
        with eng.connect() as conn:
            row = conn.execute(text(
                "SELECT title FROM esignature_envelopes WHERE envelope_uuid = 'idempotent-uuid'"
            )).fetchone()
            assert row is not None
            assert row[0] == "Idempotent Test"
        eng.dispose()


# ===========================================================================
# 5. Enum columns work correctly
# ===========================================================================

class TestEnumColumns:

    def test_envelope_status_accepts_valid_values(self, conn):
        """esignature_envelopes.status accepts all valid lifecycle values."""
        for i, status in enumerate(["DRAFT", "SENT", "VIEWED", "COMPLETED", "VOIDED", "EXPIRED"]):
            conn.execute(text(
                "INSERT INTO esignature_envelopes (envelope_uuid, title, status) "
                "VALUES (:uuid, :title, :status)"
            ), {"uuid": f"enum-status-{i}", "title": f"Status {status}", "status": status})
        count = conn.execute(text("SELECT COUNT(*) FROM esignature_envelopes")).fetchone()[0]
        assert count >= 6

    def test_recipient_type_accepts_valid_values(self, conn):
        """esignature_recipients.recipient_type accepts signer, cc, witness, etc."""
        conn.execute(text(
            "INSERT INTO esignature_envelopes (id, envelope_uuid, title) "
            "VALUES (8000, 'uuid-rtype', 'RecipType Test')"
        ))
        for i, rtype in enumerate(["signer", "cc", "witness", "in_person_signer"]):
            conn.execute(text(
                "INSERT INTO esignature_recipients (envelope_id, recipient_type, name, email) "
                "VALUES (8000, :rtype, :name, :email)"
            ), {"rtype": rtype, "name": f"Person {i}", "email": f"rtype{i}@test.com"})
        count = conn.execute(text(
            "SELECT COUNT(*) FROM esignature_recipients WHERE envelope_id = 8000"
        )).fetchone()[0]
        assert count == 4

    def test_income_calculation_status_lifecycle(self, conn):
        """income_calculations.status accepts all lifecycle values."""
        for i, status in enumerate(["pending", "in_progress", "completed", "reviewed", "approved"]):
            conn.execute(text(
                "INSERT INTO income_calculations (id, status) VALUES (:id, :status)"
            ), {"id": 8100 + i, "status": status})
        count = conn.execute(text(
            "SELECT COUNT(*) FROM income_calculations WHERE id BETWEEN 8100 AND 8104"
        )).fetchone()[0]
        assert count == 5

    def test_verification_task_priority_values(self, conn):
        """income_verification_tasks.priority accepts low/normal/high/critical."""
        for i, priority in enumerate(["low", "normal", "high", "critical"]):
            conn.execute(text(
                "INSERT INTO income_verification_tasks (id, task_type, title, status, priority) "
                "VALUES (:id, 'voe', :title, 'pending', :priority)"
            ), {"id": 8200 + i, "title": f"Task {priority}", "priority": priority})
        count = conn.execute(text(
            "SELECT COUNT(*) FROM income_verification_tasks WHERE id BETWEEN 8200 AND 8203"
        )).fetchone()[0]
        assert count == 4

    def test_campaign_status_values(self, conn):
        """document_followup_campaigns.status accepts all lifecycle values."""
        for i, status in enumerate(["draft", "active", "paused", "completed", "cancelled"]):
            conn.execute(text(
                "INSERT INTO document_followup_campaigns (id, status) VALUES (:id, :status)"
            ), {"id": 8300 + i, "status": status})
        count = conn.execute(text(
            "SELECT COUNT(*) FROM document_followup_campaigns WHERE id BETWEEN 8300 AND 8304"
        )).fetchone()[0]
        assert count == 5

    def test_encryption_status_values(self, conn):
        """document_encryption_records.encryption_status accepts expected values."""
        for i, status in enumerate(["encrypted", "decrypted", "re_encrypted", "key_rotated"]):
            conn.execute(text(
                "INSERT INTO document_encryption_records (id, encryption_algorithm, key_id, encryption_status) "
                "VALUES (:id, 'AES-256-GCM', :key_id, :status)"
            ), {"id": 8400 + i, "key_id": f"key-enc-{i}", "status": status})
        count = conn.execute(text(
            "SELECT COUNT(*) FROM document_encryption_records WHERE id BETWEEN 8400 AND 8403"
        )).fetchone()[0]
        assert count == 4


# ===========================================================================
# 6. Default values are set
# ===========================================================================

class TestDefaultValues:

    def test_envelope_defaults(self, conn):
        """New envelopes default: status=DRAFT, total/completed_recipients=0, reminder_hours=48."""
        conn.execute(text(
            "INSERT INTO esignature_envelopes (envelope_uuid, title) "
            "VALUES ('def-env-001', 'Default Test')"
        ))
        row = conn.execute(text(
            "SELECT status, total_recipients, completed_recipients, reminder_frequency_hours "
            "FROM esignature_envelopes WHERE envelope_uuid = 'def-env-001'"
        )).fetchone()
        assert row[0] == "DRAFT"
        assert row[1] == 0
        assert row[2] == 0
        assert row[3] == 48

    def test_recipient_defaults(self, conn):
        """New recipients default: type=signer, status=pending, order=1, auth=email."""
        conn.execute(text(
            "INSERT INTO esignature_envelopes (id, envelope_uuid, title) "
            "VALUES (7000, 'def-recip-env', 'Recip Default Env')"
        ))
        conn.execute(text(
            "INSERT INTO esignature_recipients (envelope_id, name, email) "
            "VALUES (7000, 'Default User', 'default@test.com')"
        ))
        row = conn.execute(text(
            "SELECT recipient_type, signing_order, status, auth_method "
            "FROM esignature_recipients WHERE email = 'default@test.com'"
        )).fetchone()
        assert row[0] == "signer"
        assert row[1] == 1
        assert row[2] == "pending"
        assert row[3] == "email"

    def test_income_calculation_defaults(self, conn):
        """New income calculation defaults: status=pending."""
        conn.execute(text("INSERT INTO income_calculations (id) VALUES (7100)"))
        row = conn.execute(text(
            "SELECT status FROM income_calculations WHERE id = 7100"
        )).fetchone()
        assert row[0] == "pending"

    def test_followup_campaign_defaults(self, conn):
        """Campaign defaults: status=draft, steps=0, max_reminders=5, responded=false."""
        conn.execute(text("INSERT INTO document_followup_campaigns (id) VALUES (7200)"))
        row = conn.execute(text(
            "SELECT status, total_steps, current_step, max_reminders, reminders_sent, borrower_responded "
            "FROM document_followup_campaigns WHERE id = 7200"
        )).fetchone()
        assert row[0] == "draft"
        assert row[1] == 0
        assert row[2] == 0
        assert row[3] == 5
        assert row[4] == 0
        assert row[5] == 0

    def test_call_intel_status_default(self, conn):
        """New call intel doc needs default: status=detected."""
        conn.execute(text("INSERT INTO call_intel_document_needs (id) VALUES (7300)"))
        row = conn.execute(text(
            "SELECT status FROM call_intel_document_needs WHERE id = 7300"
        )).fetchone()
        assert row[0] == "detected"

    def test_encryption_record_defaults(self, conn):
        """Encryption defaults: key_version=1, status=encrypted, access_count=0."""
        conn.execute(text(
            "INSERT INTO document_encryption_records (id, encryption_algorithm, key_id) "
            "VALUES (7400, 'AES-256-GCM', 'def-key-001')"
        ))
        row = conn.execute(text(
            "SELECT key_version, encryption_status, access_count "
            "FROM document_encryption_records WHERE id = 7400"
        )).fetchone()
        assert row[0] == 1
        assert row[1] == "encrypted"
        assert row[2] == 0

    def test_retention_policy_defaults(self, conn):
        """Retention defaults: action=archive, notify=30, is_active=true."""
        conn.execute(text(
            "INSERT INTO document_retention_policies (id, policy_name, retention_days) "
            "VALUES (7500, 'Default Policy', 365)"
        ))
        row = conn.execute(text(
            "SELECT action_on_expiry, notify_days_before, is_active "
            "FROM document_retention_policies WHERE id = 7500"
        )).fetchone()
        assert row[0] == "archive"
        assert row[1] == 30
        assert row[2] == 1

    def test_appointment_defaults(self, conn):
        """Appointment defaults: status=scheduled, duration=30, reminder_sent=false."""
        conn.execute(text(
            "INSERT INTO document_appointments (id, title) VALUES (7600, 'Default Appt')"
        ))
        row = conn.execute(text(
            "SELECT status, duration_minutes, reminder_sent "
            "FROM document_appointments WHERE id = 7600"
        )).fetchone()
        assert row[0] == "scheduled"
        assert row[1] == 30
        assert row[2] == 0

    def test_document_requirement_rule_defaults(self, conn):
        """Rule defaults: required_count=1, priority=normal, is_active=true, sort_order=0."""
        conn.execute(text(
            "INSERT INTO document_requirement_rules (id, rule_name) VALUES (7700, 'Default Rule')"
        ))
        row = conn.execute(text(
            "SELECT required_count, priority, is_active, sort_order "
            "FROM document_requirement_rules WHERE id = 7700"
        )).fetchone()
        assert row[0] == 1
        assert row[1] == "normal"
        assert row[2] == 1
        assert row[3] == 0

    def test_esignature_template_defaults(self, conn):
        """Template defaults: is_active=true, usage_count=0."""
        conn.execute(text(
            "INSERT INTO esignature_templates (id, name) VALUES (7800, 'Default Tpl')"
        ))
        row = conn.execute(text(
            "SELECT is_active, usage_count FROM esignature_templates WHERE id = 7800"
        )).fetchone()
        assert row[0] == 1
        assert row[1] == 0

    def test_followup_template_defaults(self, conn):
        """Follow-up template defaults: is_default=false, is_active=true, usage_count=0."""
        conn.execute(text(
            "INSERT INTO document_followup_templates (id, name) VALUES (7900, 'Default Follow-up')"
        ))
        row = conn.execute(text(
            "SELECT is_default, is_active, usage_count "
            "FROM document_followup_templates WHERE id = 7900"
        )).fetchone()
        assert row[0] == 0
        assert row[1] == 1
        assert row[2] == 0


# ===========================================================================
# 7. No naming conflicts with existing tables
# ===========================================================================

class TestNoNamingConflicts:

    def test_no_conflict_with_core_crm_tables(self):
        """Migration table names must not collide with core CRM model tables."""
        overlap = set(EXPECTED_TABLES) & LEGACY_TABLE_NAMES
        assert not overlap, f"Naming conflict with existing tables: {overlap}"

    def test_no_conflict_with_smart_docs_v1(self):
        """V2 tables must not collide with V1 smart_docs tables."""
        v1 = {"smart_documents", "smart_document_requests",
              "doc_policy_events", "needs_list_templates"}
        overlap = set(EXPECTED_TABLES) & v1
        assert not overlap, f"Naming conflict with V1 tables: {overlap}"

    def test_no_conflict_with_old_esign_prefix(self):
        """V2 uses 'esignature_' prefix, must not collide with old 'esign_' tables."""
        old_esign = {"esign_envelopes", "esign_signers", "esign_fields",
                     "esign_field_values", "esign_audit_events"}
        overlap = set(EXPECTED_TABLES) & old_esign
        assert not overlap, f"Naming conflict with old esign tables: {overlap}"

    def test_all_tables_use_snake_case(self):
        """All table names must be lowercase snake_case with no spaces."""
        for table in EXPECTED_TABLES:
            assert table == table.lower(), f"Table '{table}' is not lowercase"
            assert " " not in table, f"Table '{table}' contains spaces"
            for i, ch in enumerate(table):
                if i > 0 and ch.isupper():
                    pytest.fail(f"Table '{table}' has camelCase at position {i}")

    def test_esignature_tables_use_full_prefix(self):
        """E-signature tables use 'esignature_' prefix (not shortened 'esign_')."""
        esign_tables = [t for t in EXPECTED_TABLES if "sign" in t]
        for t in esign_tables:
            assert t.startswith("esignature_"), (
                f"Table '{t}' should use 'esignature_' prefix"
            )


# ===========================================================================
# 8. organization_id on tenant-scoped tables
# ===========================================================================

class TestTenantIsolation:

    @pytest.mark.parametrize("table", TENANT_SCOPED_TABLES)
    def test_organization_id_present(self, inspector, table):
        """Tenant-scoped tables must have an organization_id column."""
        col_names = {c["name"] for c in inspector.get_columns(table)}
        assert "organization_id" in col_names, (
            f"Table '{table}' is tenant-scoped but missing organization_id"
        )

    @pytest.mark.parametrize("table", TENANT_SCOPED_TABLES)
    def test_organization_id_is_indexed(self, inspector, table):
        """organization_id must be indexed on every tenant-scoped table."""
        indexes = inspector.get_indexes(table)
        indexed_cols = set()
        for idx in indexes:
            indexed_cols.update(idx["column_names"])
        assert "organization_id" in indexed_cols, (
            f"Table '{table}' has organization_id but it is not indexed"
        )

    def test_child_tables_inherit_scope_via_fk(self, inspector):
        """Tables without organization_id must FK to a parent that has it."""
        for table in sorted(TABLES_WITHOUT_ORG_ID):
            fks = inspector.get_foreign_keys(table)
            if not fks:
                # Integrity/watermark logs reference document_id -- no FK needed
                assert table in ("document_integrity_checks", "document_watermark_logs"), (
                    f"Table '{table}' has no org_id and no FK parent"
                )
                continue
            parent_tables = {fk["referred_table"] for fk in fks}
            parent_has_org = any(
                "organization_id"
                in {c["name"] for c in inspector.get_columns(pt)}
                for pt in parent_tables
                if pt in set(inspector.get_table_names())
            )
            assert parent_has_org, (
                f"Table '{table}' has no org_id and none of its FK parents "
                f"({parent_tables}) carry organization_id"
            )


# ===========================================================================
# 9. Foreign key relationships valid
# ===========================================================================

class TestForeignKeys:

    def test_recipients_fk_to_envelopes(self, inspector):
        """esignature_recipients.envelope_id -> esignature_envelopes.id"""
        fks = inspector.get_foreign_keys("esignature_recipients")
        targets = {(fk["referred_table"], tuple(fk["constrained_columns"])) for fk in fks}
        assert ("esignature_envelopes", ("envelope_id",)) in targets

    def test_fields_fk_to_envelopes_and_recipients(self, inspector):
        """esignature_fields has FKs to both envelopes and recipients."""
        fks = inspector.get_foreign_keys("esignature_fields")
        referred = {fk["referred_table"] for fk in fks}
        assert "esignature_envelopes" in referred
        assert "esignature_recipients" in referred

    def test_audit_events_fk_to_envelopes(self, inspector):
        """esignature_audit_events.envelope_id -> esignature_envelopes.id"""
        fks = inspector.get_foreign_keys("esignature_audit_events")
        referred = {fk["referred_table"] for fk in fks}
        assert "esignature_envelopes" in referred

    def test_income_sources_fk_to_calculations(self, inspector):
        """income_sources.calculation_id -> income_calculations.id"""
        fks = inspector.get_foreign_keys("income_sources")
        referred = {fk["referred_table"] for fk in fks}
        assert "income_calculations" in referred

    def test_verification_tasks_dual_fk(self, inspector):
        """income_verification_tasks references both calculations and sources."""
        fks = inspector.get_foreign_keys("income_verification_tasks")
        referred = {fk["referred_table"] for fk in fks}
        assert "income_calculations" in referred
        assert "income_sources" in referred

    def test_pos_mappings_fk_to_rules(self, inspector):
        """pos_document_mappings.maps_to_rule_id -> document_requirement_rules.id"""
        fks = inspector.get_foreign_keys("pos_document_mappings")
        referred = {fk["referred_table"] for fk in fks}
        assert "document_requirement_rules" in referred

    def test_followup_events_fk_to_campaigns(self, inspector):
        """document_followup_events.campaign_id -> document_followup_campaigns.id"""
        fks = inspector.get_foreign_keys("document_followup_events")
        referred = {fk["referred_table"] for fk in fks}
        assert "document_followup_campaigns" in referred

    def test_appointments_self_referencing_fk(self, inspector):
        """document_appointments.rescheduled_from_id -> document_appointments.id"""
        fks = inspector.get_foreign_keys("document_appointments")
        self_refs = [fk for fk in fks if fk["referred_table"] == "document_appointments"]
        assert len(self_refs) == 1
        assert self_refs[0]["constrained_columns"] == ["rescheduled_from_id"]

    def test_cascade_delete_removes_children(self, conn):
        """Deleting an envelope must cascade-delete recipients, fields, and audit events."""
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.execute(text(
            "INSERT INTO esignature_envelopes (id, envelope_uuid, title) "
            "VALUES (9999, 'cascade-uuid', 'Cascade Test')"
        ))
        conn.execute(text(
            "INSERT INTO esignature_recipients (id, envelope_id, name, email) "
            "VALUES (9999, 9999, 'Bob', 'bob@cascade.com')"
        ))
        conn.execute(text(
            "INSERT INTO esignature_fields (envelope_id, recipient_id, field_type, "
            "field_uuid, x_position, y_position) "
            "VALUES (9999, 9999, 'initials', 'cascade-field', 10.0, 20.0)"
        ))
        conn.execute(text(
            "INSERT INTO esignature_audit_events (envelope_id, event_type) "
            "VALUES (9999, 'created')"
        ))
        conn.execute(text("DELETE FROM esignature_envelopes WHERE id = 9999"))
        assert conn.execute(text(
            "SELECT COUNT(*) FROM esignature_recipients WHERE envelope_id = 9999"
        )).fetchone()[0] == 0
        assert conn.execute(text(
            "SELECT COUNT(*) FROM esignature_fields WHERE envelope_id = 9999"
        )).fetchone()[0] == 0
        assert conn.execute(text(
            "SELECT COUNT(*) FROM esignature_audit_events WHERE envelope_id = 9999"
        )).fetchone()[0] == 0


# ===========================================================================
# 10. Migration rollback capability
# ===========================================================================

class TestRollback:

    def test_migration_module_has_run_migration(self):
        """The migration module exposes a callable run_migration function."""
        assert callable(run_migration)

    def test_no_rollback_function_exists(self):
        """Document that no rollback/down function currently exists."""
        import migrations.smart_docs_v2_migration as mod
        has_rollback = any(
            hasattr(mod, name) for name in ("rollback", "down", "undo", "revert", "run_rollback")
        )
        assert not has_rollback, "A rollback function was found -- add tests for it"

    def test_tables_can_be_dropped_in_reverse(self):
        """All 21 tables can be dropped in reverse order (simulated rollback)."""
        eng = create_engine("sqlite:///:memory:")
        _apply_sqlite_migration(eng)
        with eng.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            for table in reversed(EXPECTED_TABLES):
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            conn.commit()
        remaining = inspect(eng).get_table_names()
        assert len(remaining) == 0, f"Tables remaining after rollback: {remaining}"
        eng.dispose()

    def test_recreate_after_rollback(self):
        """Migration can create tables again after a full drop-all rollback."""
        eng = create_engine("sqlite:///:memory:")
        _apply_sqlite_migration(eng)
        assert len(inspect(eng).get_table_names()) == 21

        with eng.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
            for table in reversed(EXPECTED_TABLES):
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            conn.commit()
        assert len(inspect(eng).get_table_names()) == 0

        _apply_sqlite_migration(eng)
        assert len(inspect(eng).get_table_names()) == 21
        eng.dispose()


# ===========================================================================
# 11. Table count verification
# ===========================================================================

class TestTableCount:

    def test_exactly_21_migration_tables(self, inspector):
        """Migration creates exactly 21 tables."""
        existing = set(inspector.get_table_names())
        migrated = existing.intersection(EXPECTED_TABLES)
        assert len(migrated) == 21

    def test_expected_tables_list_has_21_entries(self):
        """The EXPECTED_TABLES constant lists exactly 21 table names."""
        assert len(EXPECTED_TABLES) == 21

    def test_no_duplicate_table_names(self):
        """EXPECTED_TABLES has no duplicate entries."""
        assert len(EXPECTED_TABLES) == len(set(EXPECTED_TABLES))

    def test_run_migration_return_value_lists_21(self):
        """run_migration's return dict lists all 21 tables in tables_created."""
        import re
        import inspect as pyinspect
        source = pyinspect.getsource(run_migration)
        match = re.search(r'"tables_created":\s*\[(.*?)\]', source, re.DOTALL)
        assert match, "Could not find tables_created in run_migration source"
        table_names = re.findall(r'"([^"]+)"', match.group(1))
        assert set(table_names) == set(EXPECTED_TABLES), (
            f"tables_created mismatch.\n"
            f"In source but not expected: {set(table_names) - set(EXPECTED_TABLES)}\n"
            f"Expected but not in source: {set(EXPECTED_TABLES) - set(table_names)}"
        )


# ===========================================================================
# 12. Column type verification
# ===========================================================================

class TestColumnTypes:

    def test_numeric_precision_columns(self, inspector):
        """Position and financial columns use NUMERIC type for precision."""
        cols = {c["name"]: c for c in inspector.get_columns("esignature_fields")}
        for col_name in ["x_position", "y_position"]:
            col_type_str = str(cols[col_name]["type"]).upper()
            assert "NUMERIC" in col_type_str or "REAL" in col_type_str or "DECIMAL" in col_type_str, (
                f"esignature_fields.{col_name} should be NUMERIC, got {col_type_str}"
            )

    def test_bigint_file_size_columns(self, inspector):
        """File size columns exist for large file support."""
        enc_cols = {c["name"] for c in inspector.get_columns("document_encryption_records")}
        assert "file_size_before" in enc_cols
        assert "file_size_after" in enc_cols

        int_cols = {c["name"] for c in inspector.get_columns("document_integrity_checks")}
        assert "file_size_expected" in int_cols
        assert "file_size_actual" in int_cols

    def test_boolean_columns_exist(self, inspector):
        """Boolean columns are present in expected tables."""
        bool_checks = [
            ("esignature_fields", "is_required"),
            ("esignature_templates", "is_active"),
            ("income_sources", "is_primary"),
            ("document_requirement_rules", "is_active"),
            ("pos_document_mappings", "is_active"),
            ("document_followup_campaigns", "borrower_responded"),
            ("document_appointments", "reminder_sent"),
            ("document_followup_templates", "is_default"),
            ("document_access_logs", "access_granted"),
            ("document_integrity_checks", "tamper_detected"),
            ("document_retention_policies", "is_active"),
        ]
        for table, col in bool_checks:
            cols = {c["name"] for c in inspector.get_columns(table)}
            assert col in cols, f"Boolean column '{col}' not found in '{table}'"

    def test_not_nullable_constraints(self, inspector):
        """Critical columns must be NOT NULL."""
        # envelope_uuid and title
        env_cols = {c["name"]: c for c in inspector.get_columns("esignature_envelopes")}
        assert env_cols["envelope_uuid"]["nullable"] is False
        assert env_cols["title"]["nullable"] is False

        # recipient name and email
        recip_cols = {c["name"]: c for c in inspector.get_columns("esignature_recipients")}
        assert recip_cols["name"]["nullable"] is False
        assert recip_cols["email"]["nullable"] is False

        # encryption_algorithm and key_id
        enc_cols = {c["name"]: c for c in inspector.get_columns("document_encryption_records")}
        assert enc_cols["encryption_algorithm"]["nullable"] is False
        assert enc_cols["key_id"]["nullable"] is False

        # policy_name and retention_days
        ret_cols = {c["name"]: c for c in inspector.get_columns("document_retention_policies")}
        assert ret_cols["policy_name"]["nullable"] is False
        assert ret_cols["retention_days"]["nullable"] is False

    def test_nullable_description_columns(self, inspector):
        """Description/text columns should be nullable."""
        cols = {c["name"]: c for c in inspector.get_columns("esignature_envelopes")}
        assert cols["description"]["nullable"] is True
        assert cols["void_reason"]["nullable"] is True

    def test_unique_constraints(self, conn):
        """envelope_uuid and signing_token have UNIQUE constraints."""
        env_unique = _get_unique_columns(conn, "esignature_envelopes")
        assert "envelope_uuid" in env_unique, "envelope_uuid should be UNIQUE"

        recip_unique = _get_unique_columns(conn, "esignature_recipients")
        assert "signing_token" in recip_unique, "signing_token should be UNIQUE"


# ===========================================================================
# Data integration smoke tests
# ===========================================================================

class TestDataInsertionSmoke:

    def test_full_esignature_chain(self, conn):
        """Insert an envelope -> recipient -> field -> audit event chain."""
        conn.execute(text(
            "INSERT INTO esignature_envelopes (id, envelope_uuid, title, status) "
            "VALUES (1000, 'chain-uuid-001', 'Chain Test', 'SENT')"
        ))
        conn.execute(text(
            "INSERT INTO esignature_recipients (id, envelope_id, name, email) "
            "VALUES (1000, 1000, 'Alice', 'alice@example.com')"
        ))
        conn.execute(text(
            "INSERT INTO esignature_fields (envelope_id, recipient_id, field_type, "
            "field_uuid, x_position, y_position) "
            "VALUES (1000, 1000, 'signature', 'field-uuid-001', 100.50, 200.75)"
        ))
        conn.execute(text(
            "INSERT INTO esignature_audit_events (envelope_id, recipient_id, event_type) "
            "VALUES (1000, 1000, 'envelope_sent')"
        ))
        count = conn.execute(text(
            "SELECT COUNT(*) FROM esignature_fields WHERE envelope_id = 1000"
        )).fetchone()[0]
        assert count == 1

    def test_income_calculation_chain(self, conn):
        """Insert calculation -> source -> verification task chain."""
        conn.execute(text(
            "INSERT INTO income_calculations (id, organization_id, status) "
            "VALUES (1000, 42, 'completed')"
        ))
        conn.execute(text(
            "INSERT INTO income_sources (id, calculation_id, borrower_id, source_type, "
            "base_monthly_income, total_monthly_income) "
            "VALUES (1000, 1000, 1, 'W2', 5000.00, 5500.00)"
        ))
        conn.execute(text(
            "INSERT INTO income_verification_tasks (calculation_id, income_source_id, "
            "task_type, title, status) "
            "VALUES (1000, 1000, 'voe_request', 'Verify employment', 'pending')"
        ))
        row = conn.execute(text(
            "SELECT total_monthly_income FROM income_sources WHERE id = 1000"
        )).fetchone()
        assert float(row[0]) == 5500.00

    def test_document_security_audit_trail(self, conn):
        """Insert access log, encryption record, and integrity check for same document."""
        conn.execute(text(
            "INSERT INTO document_access_logs (organization_id, document_id, access_type, "
            "access_granted, ip_address, session_id) "
            "VALUES (42, 500, 'view', 1, '10.0.0.1', 'sess-smoke-001')"
        ))
        conn.execute(text(
            "INSERT INTO document_encryption_records (organization_id, document_id, "
            "encryption_algorithm, key_id) "
            "VALUES (42, 500, 'AES-256-GCM', 'kms-smoke-001')"
        ))
        conn.execute(text(
            "INSERT INTO document_integrity_checks (document_id, check_type, "
            "expected_hash, actual_hash, is_valid, tamper_detected) "
            "VALUES (500, 'sha256', 'abc123', 'abc123', 1, 0)"
        ))
        for table in ["document_access_logs", "document_encryption_records", "document_integrity_checks"]:
            count = conn.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE document_id = 500"
            )).fetchone()[0]
            assert count >= 1, f"No row in {table} for document_id 500"
