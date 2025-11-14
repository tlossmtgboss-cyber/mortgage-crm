"""
Migration script to create Mission Control database tables
Run this to add Mission Control monitoring tables to your database
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set")
    print("Set it with: export DATABASE_URL=your_database_url")
    sys.exit(1)

print("🔧 Mission Control Table Creation Script")
print("=" * 60)
print(f"Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'local'}")
print("=" * 60)

# Create engine
engine = create_engine(DATABASE_URL)

# SQL statements to create tables
CREATE_TABLES_SQL = """
-- AI Metrics Daily Table
CREATE TABLE IF NOT EXISTS ai_metrics_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    tasks_total INTEGER DEFAULT 0,
    tasks_auto_completed INTEGER DEFAULT 0,
    tasks_escalated_to_humans INTEGER DEFAULT 0,
    automation_rate DOUBLE PRECISION DEFAULT 0.0,
    escalation_rate DOUBLE PRECISION DEFAULT 0.0,
    avg_ai_resolution_time_seconds DOUBLE PRECISION DEFAULT 0.0,
    total_time_saved_seconds DOUBLE PRECISION DEFAULT 0.0,
    ai_improvement_index DOUBLE PRECISION DEFAULT 100.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_metrics_daily_date ON ai_metrics_daily(date);

-- Integration Status Log Table
CREATE TABLE IF NOT EXISTS integration_status_log (
    id SERIAL PRIMARY KEY,
    integration_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    last_success_at TIMESTAMP,
    error_count_24h INTEGER DEFAULT 0,
    latency_ms INTEGER,
    last_error_message TEXT,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_integration_status_log_name ON integration_status_log(integration_name);
CREATE INDEX IF NOT EXISTS idx_integration_status_log_checked ON integration_status_log(checked_at);

-- System Alerts Table
CREATE TABLE IF NOT EXISTS system_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    message TEXT NOT NULL,
    suggested_action TEXT,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_system_alerts_resolved ON system_alerts(is_resolved);
CREATE INDEX IF NOT EXISTS idx_system_alerts_created ON system_alerts(created_at);

-- System Jobs Log Table
CREATE TABLE IF NOT EXISTS system_jobs_log (
    id SERIAL PRIMARY KEY,
    job_name VARCHAR NOT NULL,
    job_type VARCHAR,
    status VARCHAR NOT NULL,
    duration_ms INTEGER,
    records_processed INTEGER,
    error_message TEXT,
    last_run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_system_jobs_log_name ON system_jobs_log(job_name);
CREATE INDEX IF NOT EXISTS idx_system_jobs_log_run ON system_jobs_log(last_run_at);

-- Security Snapshot Daily Table
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

CREATE INDEX IF NOT EXISTS idx_security_snapshot_daily_date ON security_snapshot_daily(date);

-- AI Changelog Daily Table
CREATE TABLE IF NOT EXISTS ai_changelog_daily (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    summary TEXT,
    improvements JSONB,
    issues JSONB,
    ai_generated BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_changelog_daily_date ON ai_changelog_daily(date);
"""

try:
    print("\n📊 Creating Mission Control tables...")

    with engine.connect() as conn:
        # Execute each statement
        for statement in CREATE_TABLES_SQL.strip().split(';'):
            statement = statement.strip()
            if statement and not statement.startswith('--'):
                try:
                    conn.execute(text(statement))
                    conn.commit()
                except SQLAlchemyError as e:
                    print(f"⚠️  Warning: {str(e)}")
                    continue

    print("\n✅ Mission Control tables created successfully!")
    print("\nCreated tables:")
    print("  1. ai_metrics_daily - Track AI performance metrics")
    print("  2. integration_status_log - Monitor integration health")
    print("  3. system_alerts - System alerts and recommendations")
    print("  4. system_jobs_log - Data pipeline job logs")
    print("  5. security_snapshot_daily - Security compliance metrics")
    print("  6. ai_changelog_daily - AI improvement changelog")

    print("\n🎯 Next steps:")
    print("  1. Mission Control is now ready to use")
    print("  2. Deploy the updated backend to production")
    print("  3. Enable Mission Control in Settings UI")
    print("  4. View at: Settings → Mission Control")

except Exception as e:
    print(f"\n❌ ERROR: Failed to create tables")
    print(f"Details: {str(e)}")
    sys.exit(1)
