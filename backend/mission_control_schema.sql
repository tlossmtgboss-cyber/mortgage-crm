-- ============================================================================
-- MISSION CONTROL SYSTEM HEALTH DATABASE SCHEMA
-- ============================================================================

-- Integration Status Log
CREATE TABLE IF NOT EXISTS integration_status_log (
    id SERIAL PRIMARY KEY,
    integration_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL, -- 'healthy', 'degraded', 'down'
    latency_ms INTEGER,
    error_count_24h INTEGER DEFAULT 0,
    last_success_at TIMESTAMP,
    last_error_message TEXT,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

CREATE INDEX idx_integration_status_name ON integration_status_log(integration_name);
CREATE INDEX idx_integration_status_checked ON integration_status_log(checked_at DESC);

-- AI Metrics Daily Snapshots
CREATE TABLE IF NOT EXISTS ai_metrics_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    tasks_total INTEGER DEFAULT 0,
    tasks_auto_completed INTEGER DEFAULT 0,
    tasks_escalated_to_humans INTEGER DEFAULT 0,
    avg_ai_resolution_time_seconds DECIMAL(10,2),
    avg_human_resolution_time_seconds DECIMAL(10,2),
    automation_rate DECIMAL(5,2),
    escalation_rate DECIMAL(5,2),
    time_saved_per_task_seconds DECIMAL(10,2),
    total_time_saved_seconds DECIMAL(10,2),
    ai_improvement_index DECIMAL(10,2),
    errors_or_reopens INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_metrics_date ON ai_metrics_daily(date DESC);

-- System Jobs Log
CREATE TABLE IF NOT EXISTS system_jobs_log (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR NOT NULL,
    job_type VARCHAR, -- 'backup', 'etl', 'sync', 'cleanup'
    last_run_at TIMESTAMP,
    status VARCHAR, -- 'success', 'failed', 'running'
    duration_ms INTEGER,
    error_message TEXT,
    records_processed INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_system_jobs_name ON system_jobs_log(job_name);
CREATE INDEX idx_system_jobs_run ON system_jobs_log(last_run_at DESC);

-- Security Snapshot Daily
CREATE TABLE IF NOT EXISTS security_snapshot_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    active_users_with_2fa INTEGER DEFAULT 0,
    active_users_total INTEGER DEFAULT 0,
    high_privilege_actions_24h INTEGER DEFAULT 0,
    failed_login_attempts_24h INTEGER DEFAULT 0,
    password_changes_24h INTEGER DEFAULT 0,
    last_permission_change_user VARCHAR,
    last_permission_change_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_security_snapshot_date ON security_snapshot_daily(date DESC);

-- AI Changelog Daily
CREATE TABLE IF NOT EXISTS ai_changelog_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    summary TEXT,
    improvements JSONB, -- Array of improvement details
    issues JSONB, -- Array of issues detected
    ai_generated BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_changelog_date ON ai_changelog_daily(date DESC);

-- System Alerts
CREATE TABLE IF NOT EXISTS system_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR NOT NULL, -- 'integration', 'ai_performance', 'security', 'job_failure'
    severity VARCHAR NOT NULL, -- 'critical', 'warning', 'info'
    title VARCHAR NOT NULL,
    message TEXT NOT NULL,
    suggested_action TEXT,
    metadata JSONB,
    is_resolved BOOLEAN DEFAULT false,
    resolved_at TIMESTAMP,
    resolved_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_system_alerts_severity ON system_alerts(severity);
CREATE INDEX idx_system_alerts_resolved ON system_alerts(is_resolved, created_at DESC);
CREATE INDEX idx_system_alerts_type ON system_alerts(alert_type);
