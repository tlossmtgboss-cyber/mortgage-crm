"""
================================================================================
AI SYSTEM DATABASE MIGRATION
================================================================================
Consolidated migration for all AI-related tables.

Creates all tables needed for:
- Smart Docs (document requests, processing, SLA tracking)
- Agent Governance (profiles, tools, executions, gym testing)
- AI Task Automation (authorizations, audit, cost tracking)
- AI Colleague Tracking (actions, learning metrics)

Run with: python migrations/create_ai_system_tables.py

Supports both PostgreSQL and SQLite.
================================================================================
"""

import os
import sys
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or .env file."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    return line.strip().split('=', 1)[1].strip('"').strip("'")

    return "sqlite:///./agentic_crm.db"


def is_postgresql(database_url):
    """Check if database is PostgreSQL."""
    return database_url.startswith('postgresql') or database_url.startswith('postgres')


def get_sql_types(is_pg):
    """Get database-specific SQL types."""
    if is_pg:
        return {
            'serial': 'SERIAL PRIMARY KEY',
            'json': 'JSONB',
            'timestamp_default': 'CURRENT_TIMESTAMP',
            'boolean_true': 'TRUE',
            'boolean_false': 'FALSE',
            'uuid': 'UUID DEFAULT gen_random_uuid()',
        }
    else:
        return {
            'serial': 'INTEGER PRIMARY KEY AUTOINCREMENT',
            'json': 'TEXT',
            'timestamp_default': 'CURRENT_TIMESTAMP',
            'boolean_true': '1',
            'boolean_false': '0',
            'uuid': 'TEXT',
        }


def run_migration():
    """Run the full AI system migration."""
    from sqlalchemy import create_engine, text, inspect

    database_url = get_database_url()
    is_pg = is_postgresql(database_url)

    print(f"Database: {'PostgreSQL' if is_pg else 'SQLite'}")
    print(f"URL: {database_url[:50]}...")

    engine = create_engine(database_url)
    types = get_sql_types(is_pg)

    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = inspector.get_table_names()

        # =====================================================================
        # 1. SMART DOCS TABLES
        # =====================================================================
        print("\n1. Creating Smart Docs tables...")

        if 'smart_document_requests' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE smart_document_requests (
                    id {types['serial']},
                    loan_id INTEGER NOT NULL,
                    borrower_id INTEGER,
                    doc_type VARCHAR(100) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    description TEXT,
                    instructions TEXT,
                    required_count INTEGER DEFAULT 1,
                    applies_to VARCHAR(50) DEFAULT 'BORROWER',
                    priority VARCHAR(50) DEFAULT 'NORMAL',
                    freshness_days INTEGER,
                    auto_renew BOOLEAN DEFAULT {types['boolean_false']},
                    next_expected_available_at TIMESTAMP,
                    payroll_frequency VARCHAR(50),
                    status VARCHAR(50) DEFAULT 'OPEN',
                    due_date TIMESTAMP,
                    completed_at TIMESTAMP,
                    sla_due_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT {types['boolean_true']},
                    superseded_by INTEGER,
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    updated_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_smart_doc_requests_loan_id ON smart_document_requests(loan_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_smart_doc_requests_status ON smart_document_requests(status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_smart_doc_requests_sla_due ON smart_document_requests(sla_due_at)"))
            print("   Created: smart_document_requests")
        else:
            print("   Exists: smart_document_requests")

        if 'smart_documents' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE smart_documents (
                    id {types['serial']},
                    request_id INTEGER,
                    loan_id INTEGER,
                    borrower_id INTEGER NOT NULL,
                    file_name VARCHAR(512) NOT NULL,
                    original_filename VARCHAR(512),
                    mime_type VARCHAR(128) NOT NULL,
                    file_size INTEGER NOT NULL,
                    storage_key VARCHAR(1024) NOT NULL,
                    page_count INTEGER,
                    uploaded_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    doc_type VARCHAR(100),
                    detected_doc_type VARCHAR(64),
                    detected_is_screenshot BOOLEAN DEFAULT {types['boolean_false']},
                    screenshot_confidence REAL,
                    screenshot_reasons {types['json']},
                    extracted_dates {types['json']},
                    extracted_names {types['json']},
                    extracted_employer VARCHAR(255),
                    extracted_account_number VARCHAR(64),
                    extracted_amount DECIMAL(15, 2),
                    extraction_confidence REAL,
                    ocr_text TEXT,
                    doc_date TIMESTAMP,
                    doc_expires_at TIMESTAMP,
                    is_expired BOOLEAN DEFAULT {types['boolean_false']},
                    days_until_expiration INTEGER,
                    status VARCHAR(32) DEFAULT 'UPLOADED',
                    decision VARCHAR(50),
                    decision_reasons {types['json']},
                    rejection_reason TEXT,
                    rejection_category VARCHAR(50),
                    fix_instructions TEXT,
                    reviewed_at TIMESTAMP,
                    reviewed_by VARCHAR(64),
                    upload_source VARCHAR(32),
                    user_agent VARCHAR(512),
                    ip_address VARCHAR(45),
                    display_name VARCHAR(255),
                    assigned_owner VARCHAR(20),
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    updated_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_smart_documents_request_id ON smart_documents(request_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_smart_documents_loan_id ON smart_documents(loan_id)"))
            print("   Created: smart_documents")
        else:
            print("   Exists: smart_documents")

        if 'doc_policy_events' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE doc_policy_events (
                    id {types['serial']},
                    loan_id INTEGER NOT NULL,
                    request_id INTEGER,
                    document_id INTEGER,
                    event_type VARCHAR(100),
                    description TEXT,
                    metadata {types['json']},
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    created_by INTEGER
                )
            """))
            print("   Created: doc_policy_events")
        else:
            print("   Exists: doc_policy_events")

        if 'needs_list_templates' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE needs_list_templates (
                    id {types['serial']},
                    slug VARCHAR(100) UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    loan_types {types['json']},
                    property_types {types['json']},
                    occupancy_types {types['json']},
                    items {types['json']},
                    is_active BOOLEAN DEFAULT {types['boolean_true']},
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    updated_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            print("   Created: needs_list_templates")
        else:
            print("   Exists: needs_list_templates")

        if 'client_reminder_settings' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE client_reminder_settings (
                    id {types['serial']},
                    loan_id INTEGER UNIQUE NOT NULL,
                    reminder_enabled BOOLEAN DEFAULT {types['boolean_true']},
                    reminder_frequency_hours INTEGER DEFAULT 24,
                    max_reminders INTEGER DEFAULT 3,
                    reminder_channels {types['json']},
                    quiet_hours_start VARCHAR(10),
                    quiet_hours_end VARCHAR(10),
                    timezone VARCHAR(50) DEFAULT 'America/New_York',
                    next_reminder_at TIMESTAMP,
                    reminders_sent INTEGER DEFAULT 0,
                    last_reminder_at TIMESTAMP,
                    escalation_enabled BOOLEAN DEFAULT {types['boolean_true']},
                    escalation_after_hours INTEGER DEFAULT 72,
                    escalated_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    updated_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_client_reminder_loan_id ON client_reminder_settings(loan_id)"))
            print("   Created: client_reminder_settings")
        else:
            print("   Exists: client_reminder_settings")

        # =====================================================================
        # 2. AGENT GOVERNANCE TABLES
        # =====================================================================
        print("\n2. Creating Agent Governance tables...")

        if 'agent_profiles' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE agent_profiles (
                    id {types['serial']},
                    name VARCHAR(100) UNIQUE NOT NULL,
                    display_name VARCHAR(200),
                    description TEXT,
                    role VARCHAR(100),
                    capabilities {types['json']},
                    system_prompt TEXT,
                    model_config {types['json']},
                    is_active BOOLEAN DEFAULT {types['boolean_true']},
                    version INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    updated_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            print("   Created: agent_profiles")
        else:
            print("   Exists: agent_profiles")

        if 'agent_tools' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE agent_tools (
                    id {types['serial']},
                    agent_id INTEGER NOT NULL,
                    tool_name VARCHAR(100) NOT NULL,
                    tool_description TEXT,
                    parameters_schema {types['json']},
                    is_enabled BOOLEAN DEFAULT {types['boolean_true']},
                    requires_approval BOOLEAN DEFAULT {types['boolean_false']},
                    approval_levels {types['json']},
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_tools_agent_id ON agent_tools(agent_id)"))
            print("   Created: agent_tools")
        else:
            print("   Exists: agent_tools")

        if 'agent_executions' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE agent_executions (
                    id {types['serial']},
                    agent_id INTEGER NOT NULL,
                    session_id VARCHAR(100),
                    user_id VARCHAR(100),
                    input_text TEXT,
                    output_text TEXT,
                    tools_used {types['json']},
                    tokens_used INTEGER,
                    latency_ms INTEGER,
                    status VARCHAR(50) DEFAULT 'completed',
                    error_message TEXT,
                    metadata {types['json']},
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_executions_agent_id ON agent_executions(agent_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_executions_session_id ON agent_executions(session_id)"))
            print("   Created: agent_executions")
        else:
            print("   Exists: agent_executions")

        if 'gym_test_scenarios' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE gym_test_scenarios (
                    id {types['serial']},
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    agent_id INTEGER NOT NULL,
                    category VARCHAR(100),
                    difficulty VARCHAR(50) DEFAULT 'medium',
                    input_prompt TEXT NOT NULL,
                    expected_behaviors {types['json']},
                    success_criteria {types['json']},
                    is_active BOOLEAN DEFAULT {types['boolean_true']},
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    updated_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            print("   Created: gym_test_scenarios")
        else:
            print("   Exists: gym_test_scenarios")

        if 'gym_test_runs' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE gym_test_runs (
                    id {types['serial']},
                    scenario_id INTEGER NOT NULL,
                    agent_version VARCHAR(50),
                    status VARCHAR(50) DEFAULT 'pending',
                    passed BOOLEAN,
                    score REAL,
                    execution_time_ms INTEGER,
                    results {types['json']},
                    error_message TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_gym_test_runs_scenario_id ON gym_test_runs(scenario_id)"))
            print("   Created: gym_test_runs")
        else:
            print("   Exists: gym_test_runs")

        if 'agent_alerts' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE agent_alerts (
                    id {types['serial']},
                    agent_id INTEGER NOT NULL,
                    alert_type VARCHAR(100) NOT NULL,
                    severity VARCHAR(50) DEFAULT 'warning',
                    title VARCHAR(255),
                    message TEXT,
                    metadata {types['json']},
                    is_resolved BOOLEAN DEFAULT {types['boolean_false']},
                    resolved_at TIMESTAMP,
                    resolved_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_agent_alerts_agent_id ON agent_alerts(agent_id)"))
            print("   Created: agent_alerts")
        else:
            print("   Exists: agent_alerts")

        # =====================================================================
        # 3. AI TASK AUTOMATION TABLES
        # =====================================================================
        print("\n3. Creating AI Task Automation tables...")

        if 'ai_task_type_authorizations' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE ai_task_type_authorizations (
                    id {types['serial']},
                    user_id INTEGER NOT NULL,
                    task_type VARCHAR(100) NOT NULL,
                    is_authorized BOOLEAN DEFAULT {types['boolean_false']},
                    auto_execute BOOLEAN DEFAULT {types['boolean_false']},
                    requires_confirmation BOOLEAN DEFAULT {types['boolean_true']},
                    max_daily_executions INTEGER,
                    last_authorized_at TIMESTAMP,
                    authorized_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    updated_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_task_auth_user ON ai_task_type_authorizations(user_id)"))
            print("   Created: ai_task_type_authorizations")
        else:
            print("   Exists: ai_task_type_authorizations")

        if 'ai_audit_log' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE ai_audit_log (
                    id {types['serial']},
                    agent_id VARCHAR(100),
                    action_type VARCHAR(100) NOT NULL,
                    target_type VARCHAR(100),
                    target_id VARCHAR(100),
                    user_id VARCHAR(100),
                    input_data {types['json']},
                    output_data {types['json']},
                    status VARCHAR(50) DEFAULT 'success',
                    error_message TEXT,
                    execution_time_ms INTEGER,
                    ip_address VARCHAR(45),
                    user_agent VARCHAR(512),
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_audit_log_agent ON ai_audit_log(agent_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_audit_log_action ON ai_audit_log(action_type)"))
            print("   Created: ai_audit_log")
        else:
            print("   Exists: ai_audit_log")

        if 'ai_cost_tracking' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE ai_cost_tracking (
                    id {types['serial']},
                    agent_id VARCHAR(100),
                    model_name VARCHAR(100),
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    estimated_cost DECIMAL(10, 6),
                    request_id VARCHAR(100),
                    user_id VARCHAR(100),
                    metadata {types['json']},
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_cost_agent ON ai_cost_tracking(agent_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_cost_user ON ai_cost_tracking(user_id)"))
            print("   Created: ai_cost_tracking")
        else:
            print("   Exists: ai_cost_tracking")

        if 'ai_rollback_states' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE ai_rollback_states (
                    id {types['serial']},
                    execution_id INTEGER,
                    target_type VARCHAR(100) NOT NULL,
                    target_id VARCHAR(100) NOT NULL,
                    previous_state {types['json']},
                    new_state {types['json']},
                    rollback_sql TEXT,
                    is_rolled_back BOOLEAN DEFAULT {types['boolean_false']},
                    rolled_back_at TIMESTAMP,
                    rolled_back_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            print("   Created: ai_rollback_states")
        else:
            print("   Exists: ai_rollback_states")

        # =====================================================================
        # 4. AI COLLEAGUE TRACKING TABLES
        # =====================================================================
        print("\n4. Creating AI Colleague Tracking tables...")

        if 'ai_colleague_actions' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE ai_colleague_actions (
                    id {types['serial']},
                    agent_name VARCHAR(100) NOT NULL,
                    action_type VARCHAR(100) NOT NULL,
                    entity_type VARCHAR(100),
                    entity_id INTEGER,
                    user_id VARCHAR(100),
                    description TEXT,
                    input_context {types['json']},
                    output_result {types['json']},
                    confidence_score REAL,
                    was_approved BOOLEAN,
                    approved_by VARCHAR(100),
                    execution_time_ms INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_colleague_agent ON ai_colleague_actions(agent_name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_colleague_entity ON ai_colleague_actions(entity_type, entity_id)"))
            print("   Created: ai_colleague_actions")
        else:
            print("   Exists: ai_colleague_actions")

        if 'ai_colleague_learning_metrics' not in existing_tables:
            conn.execute(text(f"""
                CREATE TABLE ai_colleague_learning_metrics (
                    id {types['serial']},
                    agent_name VARCHAR(100) NOT NULL,
                    metric_date DATE NOT NULL,
                    total_actions INTEGER DEFAULT 0,
                    successful_actions INTEGER DEFAULT 0,
                    failed_actions INTEGER DEFAULT 0,
                    approved_actions INTEGER DEFAULT 0,
                    rejected_actions INTEGER DEFAULT 0,
                    avg_confidence REAL,
                    avg_execution_time_ms INTEGER,
                    unique_users INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT {types['timestamp_default']},
                    updated_at TIMESTAMP DEFAULT {types['timestamp_default']}
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_learning_agent_date ON ai_colleague_learning_metrics(agent_name, metric_date)"))
            print("   Created: ai_colleague_learning_metrics")
        else:
            print("   Exists: ai_colleague_learning_metrics")

        # Commit all changes
        conn.commit()

        print("\n" + "=" * 60)
        print("AI System Database Migration Complete!")
        print("=" * 60)

        # Summary
        inspector = inspect(conn)
        final_tables = inspector.get_table_names()
        ai_tables = [t for t in final_tables if any(x in t for x in ['smart_', 'agent_', 'ai_', 'doc_', 'gym_', 'needs_'])]
        print(f"\nAI-related tables: {len(ai_tables)}")
        for table in sorted(ai_tables):
            print(f"  - {table}")


if __name__ == "__main__":
    run_migration()
