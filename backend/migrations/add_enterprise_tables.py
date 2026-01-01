"""
Enterprise Readiness Database Migration

This migration adds tables required for enterprise features:
- MFA (Multi-Factor Authentication)
- Audit logging with hash chain
- Data subject requests (GDPR/CCPA)
- User consents
- Secret management metadata

Run with: python -c "from migrations.add_enterprise_tables import run_migration; run_migration()"
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# SQL statements for creating enterprise tables
ENTERPRISE_TABLES_SQL = """
-- ============================================================================
-- MFA TABLES
-- ============================================================================

-- MFA setup in progress (temporary storage during setup)
CREATE TABLE IF NOT EXISTS user_mfa_setup (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    totp_secret_pending VARCHAR(64),
    backup_codes_pending TEXT,
    setup_started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    setup_expires_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(user_id)
);

-- MFA verification log for security auditing
CREATE TABLE IF NOT EXISTS mfa_verification_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    method VARCHAR(20) NOT NULL,
    success BOOLEAN NOT NULL,
    device_fingerprint VARCHAR(256),
    ip_address VARCHAR(45),
    user_agent TEXT,
    verified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mfa_verification_user_id ON mfa_verification_log(user_id);
CREATE INDEX IF NOT EXISTS idx_mfa_verification_verified_at ON mfa_verification_log(verified_at);

-- Add MFA columns to users table if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'mfa_enabled') THEN
        ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'mfa_method') THEN
        ALTER TABLE users ADD COLUMN mfa_method VARCHAR(20);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'totp_secret') THEN
        ALTER TABLE users ADD COLUMN totp_secret VARCHAR(64);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'backup_codes') THEN
        ALTER TABLE users ADD COLUMN backup_codes TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'mfa_enabled_at') THEN
        ALTER TABLE users ADD COLUMN mfa_enabled_at TIMESTAMP WITH TIME ZONE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'mfa_disabled_at') THEN
        ALTER TABLE users ADD COLUMN mfa_disabled_at TIMESTAMP WITH TIME ZONE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'deleted_at') THEN
        ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- ============================================================================
-- AUDIT LOG TABLE (with hash chain for immutability)
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(36) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Actor information
    actor_id VARCHAR(50),
    actor_type VARCHAR(20) DEFAULT 'user',
    actor_email VARCHAR(255),
    actor_ip VARCHAR(45),
    actor_user_agent TEXT,

    -- Resource information
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    resource_name VARCHAR(255),

    -- Action details
    action TEXT NOT NULL,
    outcome VARCHAR(20) DEFAULT 'success',
    reason TEXT,

    -- State changes (JSONB for PostgreSQL)
    before_state JSONB,
    after_state JSONB,
    changes JSONB,

    -- Context
    request_id VARCHAR(36),
    session_id VARCHAR(36),
    trace_id VARCHAR(36),
    organization_id VARCHAR(50),
    tenant_id VARCHAR(50),

    -- Metadata
    metadata JSONB DEFAULT '{}',
    tags JSONB DEFAULT '[]',

    -- Hash chain for tamper detection
    previous_hash VARCHAR(64),
    event_hash VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_id ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_log_organization ON audit_log(organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_trace_id ON audit_log(trace_id);

-- ============================================================================
-- DATA SUBJECT REQUESTS (GDPR/CCPA)
-- ============================================================================

CREATE TABLE IF NOT EXISTS data_subject_requests (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(36) NOT NULL UNIQUE,
    request_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    user_id VARCHAR(50) NOT NULL,
    user_email VARCHAR(255) NOT NULL,
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_date TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    completed_by INTEGER REFERENCES users(id),
    notes TEXT,
    export_file_path TEXT,
    deletion_summary JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dsr_user_id ON data_subject_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_dsr_status ON data_subject_requests(status);
CREATE INDEX IF NOT EXISTS idx_dsr_request_type ON data_subject_requests(request_type);
CREATE INDEX IF NOT EXISTS idx_dsr_due_date ON data_subject_requests(due_date);

-- ============================================================================
-- USER CONSENTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_consents (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type VARCHAR(50) NOT NULL,
    granted BOOLEAN NOT NULL,
    source VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent TEXT,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_user_consents_user_id ON user_consents(user_id);
CREATE INDEX IF NOT EXISTS idx_user_consents_type ON user_consents(consent_type);
CREATE INDEX IF NOT EXISTS idx_user_consents_recorded_at ON user_consents(recorded_at);

-- ============================================================================
-- SECRET METADATA (for tracking secret access, not storing secrets)
-- ============================================================================

CREATE TABLE IF NOT EXISTS secret_access_log (
    id SERIAL PRIMARY KEY,
    secret_key VARCHAR(255) NOT NULL,
    accessor VARCHAR(100) NOT NULL,
    action VARCHAR(20) NOT NULL,
    success BOOLEAN NOT NULL,
    error TEXT,
    accessed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_secret_access_key ON secret_access_log(secret_key);
CREATE INDEX IF NOT EXISTS idx_secret_access_time ON secret_access_log(accessed_at);

-- ============================================================================
-- DEVICE TRUST TOKENS (for MFA remember device)
-- ============================================================================

CREATE TABLE IF NOT EXISTS trusted_devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_token VARCHAR(64) NOT NULL,
    device_fingerprint VARCHAR(256),
    device_name VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_trusted_devices_user_id ON trusted_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_trusted_devices_token ON trusted_devices(device_token);

-- ============================================================================
-- DATA RETENTION POLICIES
-- ============================================================================

CREATE TABLE IF NOT EXISTS data_retention_policies (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL UNIQUE,
    retention_days INTEGER NOT NULL,
    is_regulatory BOOLEAN DEFAULT FALSE,
    regulatory_reason TEXT,
    last_applied_at TIMESTAMP WITH TIME ZONE,
    records_deleted INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Insert default retention policies
INSERT INTO data_retention_policies (table_name, retention_days, is_regulatory, regulatory_reason) VALUES
    ('activities', 730, FALSE, NULL),
    ('email_interactions', 730, FALSE, NULL),
    ('ai_conversations', 365, FALSE, NULL),
    ('notifications', 90, FALSE, NULL),
    ('loans', 2555, TRUE, 'Financial records must be retained for 7 years per GLBA'),
    ('audit_log', 2555, TRUE, 'Audit records must be retained for 7 years for compliance')
ON CONFLICT (table_name) DO NOTHING;

-- ============================================================================
-- HEALTH CHECK HISTORY
-- ============================================================================

CREATE TABLE IF NOT EXISTS health_check_history (
    id SERIAL PRIMARY KEY,
    overall_status VARCHAR(20) NOT NULL,
    components JSONB NOT NULL,
    uptime_seconds FLOAT,
    checked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_health_check_time ON health_check_history(checked_at);

-- Keep only last 1000 health checks
CREATE OR REPLACE FUNCTION cleanup_health_history() RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM health_check_history
    WHERE id NOT IN (
        SELECT id FROM health_check_history
        ORDER BY checked_at DESC
        LIMIT 1000
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_cleanup_health_history ON health_check_history;
CREATE TRIGGER trigger_cleanup_health_history
    AFTER INSERT ON health_check_history
    FOR EACH STATEMENT
    EXECUTE FUNCTION cleanup_health_history();
"""

# SQLite version (for development)
ENTERPRISE_TABLES_SQLITE_SQL = """
-- MFA setup table
CREATE TABLE IF NOT EXISTS user_mfa_setup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    totp_secret_pending VARCHAR(64),
    backup_codes_pending TEXT,
    setup_started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    setup_expires_at TIMESTAMP,
    UNIQUE(user_id)
);

-- MFA verification log
CREATE TABLE IF NOT EXISTS mfa_verification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    method VARCHAR(20) NOT NULL,
    success BOOLEAN NOT NULL,
    device_fingerprint VARCHAR(256),
    ip_address VARCHAR(45),
    user_agent TEXT,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id VARCHAR(36) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_id VARCHAR(50),
    actor_type VARCHAR(20) DEFAULT 'user',
    actor_email VARCHAR(255),
    actor_ip VARCHAR(45),
    actor_user_agent TEXT,
    resource_type VARCHAR(100),
    resource_id VARCHAR(100),
    resource_name VARCHAR(255),
    action TEXT NOT NULL,
    outcome VARCHAR(20) DEFAULT 'success',
    reason TEXT,
    before_state TEXT,
    after_state TEXT,
    changes TEXT,
    request_id VARCHAR(36),
    session_id VARCHAR(36),
    trace_id VARCHAR(36),
    organization_id VARCHAR(50),
    tenant_id VARCHAR(50),
    metadata TEXT DEFAULT '{}',
    tags TEXT DEFAULT '[]',
    previous_hash VARCHAR(64),
    event_hash VARCHAR(64) NOT NULL
);

-- Data subject requests
CREATE TABLE IF NOT EXISTS data_subject_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id VARCHAR(36) NOT NULL UNIQUE,
    request_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    user_id VARCHAR(50) NOT NULL,
    user_email VARCHAR(255) NOT NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_date TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    completed_by INTEGER REFERENCES users(id),
    notes TEXT,
    export_file_path TEXT,
    deletion_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User consents
CREATE TABLE IF NOT EXISTS user_consents (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type VARCHAR(50) NOT NULL,
    granted BOOLEAN NOT NULL,
    source VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent TEXT,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

-- Trusted devices
CREATE TABLE IF NOT EXISTS trusted_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_token VARCHAR(64) NOT NULL,
    device_fingerprint VARCHAR(256),
    device_name VARCHAR(100),
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- Data retention policies
CREATE TABLE IF NOT EXISTS data_retention_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name VARCHAR(100) NOT NULL UNIQUE,
    retention_days INTEGER NOT NULL,
    is_regulatory BOOLEAN DEFAULT FALSE,
    regulatory_reason TEXT,
    last_applied_at TIMESTAMP,
    records_deleted INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Health check history
CREATE TABLE IF NOT EXISTS health_check_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    overall_status VARCHAR(20) NOT NULL,
    components TEXT NOT NULL,
    uptime_seconds FLOAT,
    checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def run_migration():
    """Run the enterprise tables migration"""
    import os
    from sqlalchemy import create_engine, text

    # Get database URL
    database_url = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Create engine
    if database_url.startswith("sqlite"):
        engine = create_engine(database_url, connect_args={"check_same_thread": False})
        sql = ENTERPRISE_TABLES_SQLITE_SQL
    else:
        engine = create_engine(database_url)
        sql = ENTERPRISE_TABLES_SQL

    # Run migration
    with engine.connect() as conn:
        # Split SQL into statements for SQLite compatibility
        statements = [s.strip() for s in sql.split(';') if s.strip()]

        for statement in statements:
            if statement:
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    # Log but continue on non-critical errors
                    if "already exists" not in str(e).lower():
                        logger.warning(f"Migration statement warning: {e}")

        conn.commit()

    logger.info("Enterprise tables migration completed successfully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
