"""Startup migration calls extracted from main.py.

All migrations use try/except so individual failures don't crash the app.
Each migration module exposes run_migration() that is idempotent (IF NOT EXISTS).

========================================================================
DEPRECATION NOTICE (2026-05-27)
========================================================================
These inline migrations are LEGACY.  New schema changes MUST go through
Alembic migrations in backend/alembic/versions/.

Set SKIP_LEGACY_MIGRATIONS=true to bypass all raw SQL when Alembic is
fully managing the schema.
========================================================================
"""
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def run_all_startup_migrations(engine: Any) -> None:
    """Execute all inline migrations during app startup.

    Args:
        engine: SQLAlchemy engine instance (from database module).
    """
    if os.getenv("SKIP_LEGACY_MIGRATIONS", "").lower() in ("true", "1", "yes"):
        logger.info(
            "SKIP_LEGACY_MIGRATIONS is set — skipping all legacy startup migrations. "
            "Schema is managed by Alembic (backend/alembic/versions/)."
        )
        return

    # Initialize migration tracker (records which migrations have run, prevents duplicates)
    run_tracked: Optional[Callable] = None
    try:
        from migrations.migration_tracker import ensure_tracker_table, run_tracked as _run_tracked
        ensure_tracker_table(engine)
        run_tracked = _run_tracked
        logger.info("Migration tracker initialized")
    except Exception as e:
        logger.warning(f"Migration tracker init failed, migrations will run untracked: {e}")

    # ========================================================================
    # EARLY MIGRATIONS — Required before services start
    # ========================================================================

    # Run API key hash migration (adds key_hash/key_prefix columns, migrates plaintext keys)
    try:
        from migrations.hash_api_keys import run_migration as _run_api_key_hash_migration
        if run_tracked:
            run_tracked(engine, "hash_api_keys", _run_api_key_hash_migration)
        else:
            _run_api_key_hash_migration(engine)
    except Exception as e:
        logger.error(f"API key hash migration FAILED: {e}", exc_info=True)

    # Ensure tcpa_consents table exists (needed for SMS opt-in form)
    try:
        from migrations.add_tcpa_consents_table import run_migration as _run_tcpa_migration
        _run_tcpa_migration()
    except Exception as e:
        logger.error(f"TCPA consents table migration FAILED: {e}", exc_info=True)

    # Create enterprise challenge tables (file collaborator, timeline, vendor, campaigns, learning)
    try:
        from migrations.enterprise_challenge_tables import run_migration as _run_enterprise_migration
        if run_tracked:
            run_tracked(engine, "enterprise_challenge_tables", _run_enterprise_migration)
        else:
            _run_enterprise_migration(engine)
    except Exception as e:
        logger.error(f"Enterprise migration FAILED: {e}", exc_info=True)

    # POS consent tables + voice-complete columns on borrower_applications
    try:
        from migrations.add_pos_consent_tables import run_migration as _run_pos_consent_migration
        _run_pos_consent_migration()
    except Exception as e:
        logger.error(f"POS consent migration FAILED: {e}", exc_info=True)

    # Application events table + missing sms_messages/notifications columns
    try:
        from migrations.add_application_events_table import run_migration as _run_app_events_migration
        _run_app_events_migration()
    except Exception as e:
        logger.error(f"Application events migration FAILED: {e}", exc_info=True)

    # Run critical schema migrations (missing columns that break page loads)
    try:
        _run_critical_schema_migrations()
    except Exception as e:
        logger.error(f"Critical schema migrations failed: {e}")

    # Autonomous agent runs table (required before agent registration)
    try:
        from migrations.add_autonomous_agent_runs import run_migration as _run_agent_runs_migration
        if run_tracked:
            run_tracked(engine, "add_autonomous_agent_runs", _run_agent_runs_migration)
        else:
            _run_agent_runs_migration(engine)
    except Exception as e:
        logger.warning(f"Autonomous agent runs migration: {e}")

    # Create all AI autonomy tables (autonomous_tasks, agent_feedback, learning,
    # agent_memory, agent_metrics, webhook_idempotency)
    try:
        from migrations.add_ai_autonomy_tables import run_migration as _run_ai_autonomy_migration
        if run_tracked:
            run_tracked(engine, "add_ai_autonomy_tables", _run_ai_autonomy_migration)
        else:
            _run_ai_autonomy_migration(engine)
    except Exception as e:
        logger.error(f"AI autonomy table creation FAILED: {e}", exc_info=True)

    # Fix agent_actions.execution_id nullable + add approval queue index
    try:
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            # Check table exists before ALTER
            exists = conn.execute(_text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_actions' LIMIT 1"
            )).fetchone()
            if exists:
                conn.execute(_text("""
                    ALTER TABLE agent_actions
                    ALTER COLUMN execution_id DROP NOT NULL
                """))
                conn.execute(_text("""
                    CREATE INDEX IF NOT EXISTS ix_agentact_org_status
                    ON agent_actions (organization_id, status)
                """))
                conn.commit()
                logger.info("agent_actions: execution_id nullable fix + org_status index applied")
            else:
                logger.info("agent_actions table not found — skipping ALTER")
    except Exception as e:
        if "already" not in str(e).lower() and "does not exist" not in str(e).lower():
            logger.warning(f"agent_actions schema fix: {e}")

    # Add rejection audit trail columns to agent_actions
    try:
        from sqlalchemy import text as _text_rej
        with engine.connect() as conn:
            exists = conn.execute(_text_rej(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_actions' LIMIT 1"
            )).fetchone()
            if exists:
                conn.execute(_text_rej("""
                    ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS rejected_by INTEGER
                """))
                conn.execute(_text_rej("""
                    ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ
                """))
                conn.commit()
                logger.info("agent_actions: rejected_by/rejected_at columns ensured")
    except Exception as e:
        if "does not exist" not in str(e).lower():
            logger.warning(f"agent_actions rejection columns: {e}")

    # Webhook idempotency table (separate from AI autonomy)
    try:
        from database.models.webhook_idempotency import create_tables_if_needed as _create_webhook_tables
        _create_webhook_tables(engine)
        logger.info("Webhook idempotency table verified")
    except Exception as e:
        logger.error(f"Webhook idempotency table creation FAILED: {e}", exc_info=True)

    # Consolidate OAuth tokens into unified table
    try:
        from migrations.consolidate_oauth_tokens import run_migration as _run_oauth_migration
        if run_tracked:
            run_tracked(engine, "consolidate_oauth_tokens", _run_oauth_migration)
        else:
            _run_oauth_migration(engine)
    except Exception as e:
        logger.error(f"OAuth token consolidation FAILED: {e}", exc_info=True)

    # Ensure call intelligence columns and tables exist
    try:
        from migrations.add_call_intelligence_columns import run_migration as _run_ci_migration
        if run_tracked:
            run_tracked(engine, "add_call_intelligence_columns", _run_ci_migration)
        else:
            _run_ci_migration(engine)
    except Exception as e:
        logger.error(f"Call intelligence migration FAILED: {e}", exc_info=True)

    # ========================================================================
    # CRITICAL TABLE MIGRATIONS — Tables required by active SQLAlchemy models
    # Without these, any query touching these models raises ProgrammingError.
    # All use CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS (idempotent).
    # ========================================================================

    # --- Voice & Telephony ---
    try:
        from migrations.add_voice_workflows_table import run_migration as _run_voice_wf
        if run_tracked:
            run_tracked(engine, "add_voice_workflows_table", _run_voice_wf)
        else:
            _run_voice_wf(engine)
    except Exception as e:
        logger.warning(f"Voice workflows migration: {e}")

    try:
        from migrations.add_vapi_tables import run_migration as _run_vapi
        _run_vapi()
    except Exception as e:
        logger.warning(f"Vapi tables migration: {e}")

    try:
        from migrations.add_engagement_tables import run_migration as _run_engagement
        _run_engagement()
    except Exception as e:
        logger.warning(f"Engagement tables migration: {e}")

    try:
        from migrations.add_call_monitoring_system import run_migration as _run_call_monitor
        _run_call_monitor()
    except Exception as e:
        logger.warning(f"Call monitoring system migration: {e}")

    try:
        from migrations.add_call_intelligence_expansion import run_migration as _run_ci_expand
        _run_ci_expand()
    except Exception as e:
        logger.warning(f"Call intelligence expansion migration: {e}")

    try:
        from migrations.add_ci_enhancement_columns import run_migration as _run_ci_enhance
        if run_tracked:
            run_tracked(engine, "add_ci_enhancement_columns", _run_ci_enhance)
        else:
            _run_ci_enhance(engine)
    except Exception as e:
        logger.warning(f"CI enhancement columns migration: {e}")

    # --- SMS & Notifications ---
    try:
        from migrations.add_sms_persistence_tables import run_migration as _run_sms_persist
        _run_sms_persist()
    except Exception as e:
        logger.warning(f"SMS persistence tables migration: {e}")

    try:
        from migrations.add_sms_compliance_tables import run_migration as _run_sms_compliance
        _run_sms_compliance()
    except Exception as e:
        logger.warning(f"SMS compliance tables migration: {e}")

    try:
        from migrations.add_sms_consent_proof_columns import run_migration as _run_consent_proof
        _run_consent_proof()
    except Exception as e:
        logger.warning(f"SMS consent proof columns migration: {e}")

    try:
        from migrations.add_sms_delivery_tracking import run_migration as _run_delivery_tracking
        _run_delivery_tracking()
    except Exception as e:
        logger.warning(f"SMS delivery tracking migration: {e}")

    try:
        from migrations.add_sms_ai_conversations import run_migration as _run_sms_ai_conv
        _run_sms_ai_conv()
    except Exception as e:
        logger.warning(f"SMS AI conversations migration: {e}")

    try:
        from migrations.add_sms_task_tables import run_migration as _run_sms_task
        _run_sms_task(engine)
    except Exception as e:
        logger.warning(f"SMS task tables migration: {e}")

    try:
        from migrations.add_voicemail_sms_followup_columns import run_migration as _run_vm_followup
        _run_vm_followup()
    except Exception as e:
        logger.warning(f"Voicemail SMS followup columns migration: {e}")

    try:
        from migrations.add_media_s3_keys_columns import run_migration as _run_media_s3_keys
        _run_media_s3_keys()
    except Exception as e:
        logger.warning(f"Media S3 keys columns migration: {e}")

    try:
        from migrations.add_device_tokens_table import run_migration as _run_device_tokens
        _run_device_tokens()
    except Exception as e:
        logger.warning(f"Device tokens migration: {e}")

    try:
        from migrations.add_push_notification_preferences import run_migration as _run_push_prefs
        _run_push_prefs()
    except Exception as e:
        logger.warning(f"Push notification preferences migration: {e}")

    # --- AI Agents & Orchestration ---
    try:
        from migrations.add_agent_memory_tables import run_migration as _run_agent_mem
        _run_agent_mem()
    except Exception as e:
        logger.warning(f"Agent memory tables migration: {e}")

    try:
        from migrations.add_training_instructions_table import run_migration as _run_training_instr
        _run_training_instr()
    except Exception as e:
        logger.warning(f"Training instructions table migration: {e}")

    try:
        from migrations.add_morning_briefings import run_migration as _run_briefings
        _run_briefings()
    except Exception as e:
        logger.warning(f"Morning briefings migration: {e}")

    try:
        from migrations.create_briefing_thread_tables import run_migration as _run_briefing_threads
        _run_briefing_threads()
    except Exception as e:
        logger.warning(f"Briefing thread tables migration: {e}")

    try:
        from migrations.add_ai_benchmark_tables import run_migration as _run_ai_bench
        if run_tracked:
            run_tracked(engine, "add_ai_benchmark_tables", _run_ai_bench)
        else:
            _run_ai_bench(engine)
    except Exception as e:
        logger.warning(f"AI benchmark tables migration: {e}")

    # --- Lead & Loan Pipeline ---
    try:
        from migrations.add_stage_history_table import run_migration as _run_stage_hist
        _run_stage_hist()
    except Exception as e:
        logger.warning(f"Stage history table migration: {e}")

    try:
        from migrations.add_lead_assignment_tables import run_migration as _run_lead_assign
        _run_lead_assign()
    except Exception as e:
        logger.warning(f"Lead assignment tables migration: {e}")

    try:
        from migrations.add_app_completion_tables import run_migration as _run_app_complete
        if run_tracked:
            run_tracked(engine, "add_app_completion_tables", _run_app_complete)
        else:
            _run_app_complete(engine)
    except Exception as e:
        logger.warning(f"App completion tables migration: {e}")

    try:
        from migrations.add_post_closing_workflow import run_migration as _run_post_close
        _run_post_close()
    except Exception as e:
        logger.warning(f"Post-closing workflow migration: {e}")

    try:
        from migrations.add_business_rules_table import run_migration as _run_biz_rules
        _run_biz_rules()
    except Exception as e:
        logger.warning(f"Business rules table migration: {e}")

    # --- Compliance & Audit ---
    try:
        from migrations.add_compliance_decision_log import run_migration as _run_compliance_log
        _run_compliance_log()
    except Exception as e:
        logger.warning(f"Compliance decision log migration: {e}")

    try:
        from migrations.add_decision_audit_tables import run_migration as _run_decision_audit
        _run_decision_audit()
    except Exception as e:
        logger.warning(f"Decision audit tables migration: {e}")

    try:
        from migrations.add_pii_audit_log_table import run_migration as _run_pii_audit
        _run_pii_audit()
    except Exception as e:
        logger.warning(f"PII audit log migration: {e}")

    try:
        from migrations.add_security_training_table import run_migration as _run_sec_training
        _run_sec_training()
    except Exception as e:
        logger.warning(f"Security training table migration: {e}")

    # --- Smart Docs ---
    try:
        from migrations.add_document_cache_table import run_migration as _run_doc_cache
        _run_doc_cache()
    except Exception as e:
        logger.warning(f"Document cache table migration: {e}")

    try:
        from migrations.add_document_extraction_tables import run_migration as _run_doc_extract
        if run_tracked:
            run_tracked(engine, "add_document_extraction_tables", _run_doc_extract)
        else:
            _run_doc_extract(engine)
    except Exception as e:
        logger.warning(f"Document extraction tables migration: {e}")

    try:
        from migrations.add_smart_docs_sla import run_migration as _run_smart_sla
        _run_smart_sla()
    except Exception as e:
        logger.warning(f"Smart docs SLA migration: {e}")

    try:
        from migrations.add_smart_docs_missing_columns import run_migration as _run_smart_cols
        _run_smart_cols()
    except Exception as e:
        logger.warning(f"Smart docs missing columns migration: {e}")

    try:
        from migrations.fix_smart_docs_requests_schema import run_migration as _run_smart_schema
        _run_smart_schema()
    except Exception as e:
        logger.warning(f"Smart docs schema fix migration: {e}")

    # --- E-Signature & E-Closing ---
    try:
        from migrations.add_esign_tables import run_migration as _run_esign
        _run_esign()
    except Exception as e:
        logger.warning(f"E-signature tables migration: {e}")

    try:
        from migrations.add_eclosing_table import run_migration as _run_eclose
        if run_tracked:
            run_tracked(engine, "add_eclosing_table", _run_eclose)
        else:
            _run_eclose(engine)
    except Exception as e:
        logger.warning(f"E-closing table migration: {e}")

    # --- Underwriting & Income ---
    try:
        from migrations.add_aus_submission_table import run_migration as _run_aus
        if run_tracked:
            run_tracked(engine, "add_aus_submission_table", _run_aus)
        else:
            _run_aus(engine)
    except Exception as e:
        logger.warning(f"AUS submission table migration: {e}")

    try:
        from migrations.add_guideline_updates_tables import run_migration as _run_guidelines
        _run_guidelines()
    except Exception as e:
        logger.warning(f"Guideline updates tables migration: {e}")

    try:
        from migrations.add_guideline_vector_columns import run_migration as _run_guideline_vector
        _run_guideline_vector(engine)
        logger.info("Guideline vector columns migration complete")
    except Exception as e:
        logger.warning("Guideline vector columns migration skipped: %s", e)

    # --- Billing & Subscriptions ---
    try:
        from migrations.add_accounting_tables import run_migration as _run_accounting
        _run_accounting()
    except Exception as e:
        logger.warning(f"Accounting tables migration: {e}")

    try:
        from migrations.add_subscription_modules import run_migration as _run_sub_modules
        if run_tracked:
            run_tracked(engine, "add_subscription_modules", _run_sub_modules)
        else:
            _run_sub_modules(engine)
    except Exception as e:
        logger.warning(f"Subscription modules migration: {e}")

    # --- Workflow Flowchart ---
    try:
        from migrations.add_workflow_flowchart import run_migration as _run_workflow_flowchart
        if run_tracked:
            run_tracked(engine, "add_workflow_flowchart", _run_workflow_flowchart)
        else:
            _run_workflow_flowchart()
    except Exception as e:
        logger.warning(f"Workflow flowchart migration: {e}")

    # --- Encompass LOS Integration ---
    try:
        from migrations.add_encompass_columns import run_migration as _run_encompass
        _run_encompass()
    except Exception as e:
        logger.warning(f"Encompass columns migration: {e}")

    # --- Content Marketing ---
    try:
        from migrations.add_content_marketing_tables import run_migration as _run_content_mktg
        _run_content_mktg()
    except Exception as e:
        logger.warning(f"Content marketing tables migration: {e}")

    # --- Performance Indexes (HIGH priority) ---
    try:
        from migrations.add_performance_indexes import run_migration as _run_perf_idx
        if run_tracked:
            run_tracked(engine, "add_performance_indexes", _run_perf_idx)
        else:
            _run_perf_idx(engine)
    except Exception as e:
        logger.warning(f"Performance indexes migration: {e}")

    try:
        from migrations.add_scheduler_indexes import run_migration as _run_sched_idx
        if run_tracked:
            run_tracked(engine, "add_scheduler_indexes", _run_sched_idx)
        else:
            _run_sched_idx(engine)
    except Exception as e:
        logger.warning(f"Scheduler indexes migration: {e}")

    # Trigram indexes for ILIKE search performance on leads/loans
    try:
        from migrations.add_trigram_indexes import run_migration as _run_trgm_idx
        if run_tracked:
            run_tracked(engine, "add_trigram_indexes", _run_trgm_idx)
        else:
            _run_trgm_idx(engine)
    except Exception as e:
        logger.warning(f"Trigram indexes migration: {e}")

    # --- Compliance Alerts table (ComplianceAlert model) ---
    try:
        from sqlalchemy import text as _text_ca
        with engine.connect() as conn:
            conn.execute(_text_ca("""
                CREATE TABLE IF NOT EXISTS compliance_alerts (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                    loan_id INTEGER REFERENCES loans(id) ON DELETE CASCADE,
                    lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
                    alert_type VARCHAR NOT NULL,
                    severity VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    description TEXT,
                    deadline_date DATE,
                    days_remaining INTEGER,
                    status VARCHAR DEFAULT 'open',
                    resolved_at TIMESTAMP,
                    resolved_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    resolution_notes TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            conn.execute(_text_ca("CREATE INDEX IF NOT EXISTS ix_compliance_alerts_loan_id ON compliance_alerts (loan_id)"))
            conn.execute(_text_ca("CREATE INDEX IF NOT EXISTS ix_compliance_alerts_org_id ON compliance_alerts (organization_id)"))
            conn.execute(_text_ca("CREATE INDEX IF NOT EXISTS ix_compliance_alerts_status ON compliance_alerts (status)"))
            conn.execute(_text_ca("CREATE INDEX IF NOT EXISTS ix_compliance_alerts_loan_status ON compliance_alerts (loan_id, status)"))
            conn.execute(_text_ca("CREATE INDEX IF NOT EXISTS ix_compliance_alerts_org_severity ON compliance_alerts (organization_id, severity)"))
            conn.execute(_text_ca("CREATE INDEX IF NOT EXISTS ix_compliance_alerts_org_type ON compliance_alerts (organization_id, alert_type)"))
            conn.execute(_text_ca("CREATE INDEX IF NOT EXISTS ix_compliance_alerts_deadline ON compliance_alerts (deadline_date)"))
            conn.commit()
        logger.info("compliance_alerts table ensured")
    except Exception as e:
        logger.warning(f"compliance_alerts table migration: {e}")

    # --- EncompassConfig missing columns (last_failed_at, consecutive_auth_failures) ---
    try:
        from sqlalchemy import text as _text_ec
        with engine.connect() as conn:
            conn.execute(_text_ec("""
                ALTER TABLE IF EXISTS encompass_configs
                ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ
            """))
            conn.execute(_text_ec("""
                ALTER TABLE IF EXISTS encompass_configs
                ADD COLUMN IF NOT EXISTS consecutive_auth_failures INTEGER DEFAULT 0
            """))
            conn.commit()
        logger.info("encompass_configs: last_failed_at/consecutive_auth_failures columns ensured")
    except Exception as e:
        if "does not exist" not in str(e).lower():
            logger.warning(f"encompass_configs missing columns migration: {e}")

    logger.info("All startup migrations complete")


def _run_critical_schema_migrations():
    """Run critical schema migrations at startup.

    These fix missing columns or type mismatches that cause 500 errors on page loads.
    All operations use IF NOT EXISTS / IF EXISTS to be idempotent.
    """
    from sqlalchemy import text as sa_text
    from db import SessionLocal

    success_count = 0
    skip_count = 0
    fail_count = 0

    db = SessionLocal()
    try:
        # Fix 1: Add ALL missing columns to loans table
        # Model defines columns that may not exist in production DB
        # (init_db.py handles some, but not all — especially Salesforce sync columns)
        loan_columns = [
            # Encompass LOS integration
            ("encompass_loan_id", "VARCHAR"),
            ("encompass_last_synced_at", "TIMESTAMP"),
            ("encompass_sync_status", "VARCHAR(50)"),
            # Salesforce Sync - Property
            ("property_type", "VARCHAR"),
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            ("file_state", "VARCHAR"),
            ("loan_purpose", "VARCHAR"),
            ("rate_type", "VARCHAR"),
            # Salesforce Sync - Financials
            ("monthly_payment", "NUMERIC(18,2)"),
            ("property_tax", "NUMERIC(18,2)"),
            ("hazard_insurance", "NUMERIC(18,2)"),
            ("mortgage_insurance", "NUMERIC(18,2)"),
            ("hoa_amount", "NUMERIC(18,2)"),
            ("origination_fee", "NUMERIC(18,2)"),
            ("estimated_prepaid_interest", "NUMERIC(18,2)"),
            ("points", "NUMERIC(8,4)"),
            ("index_rate", "NUMERIC(8,4)"),
            ("margin", "NUMERIC(8,4)"),
            ("ltv", "NUMERIC(8,4)"),
            ("cltv", "NUMERIC(8,4)"),
            # Salesforce Sync - 2nd Loan
            ("second_loan_amount", "NUMERIC(18,2)"),
            ("second_loan_rate", "NUMERIC(8,4)"),
            ("second_loan_payment", "NUMERIC(18,2)"),
            # Salesforce Sync - Housing Expenses
            ("present_housing_expense", "NUMERIC(18,2)"),
            ("proposed_housing_expense", "NUMERIC(18,2)"),
            ("present_monthly_payment", "NUMERIC(18,2)"),
            ("proposed_monthly_payment", "NUMERIC(18,2)"),
            # Missing date columns
            ("appraisal_received_date", "TIMESTAMP"),
            ("appraisal_docs_expire_date", "TIMESTAMP"),
            ("credit_docs_expire_date", "TIMESTAMP"),
            ("cd_sent_to_borrower_date", "TIMESTAMP"),
            ("cd_acknowledged_date", "TIMESTAMP"),
            # Borrower info
            ("coborrower_name", "VARCHAR"),
            ("co_borrower_email", "VARCHAR"),
            ("preferred_communication", "VARCHAR"),
            # SLA tracking
            ("days_in_stage", "INTEGER DEFAULT 0"),
            ("sla_status", "VARCHAR DEFAULT 'on-track'"),
            ("milestones", "JSONB"),
            ("ai_insights", "TEXT"),
            ("predicted_close_date", "TIMESTAMP"),
            ("risk_score", "INTEGER DEFAULT 0"),
            ("user_metadata", "JSONB"),
            # Stage tracking
            ("stage_changed_at", "TIMESTAMP"),
            # COMP-001: AI modification tracking
            ("last_modified_by_ai", "BOOLEAN DEFAULT FALSE"),
        ]
        added = 0
        for col_name, col_type in loan_columns:
            try:
                alter_sql = "ALTER TABLE loans ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                db.execute(sa_text(alter_sql))
                db.commit()
                added += 1
                success_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"loans.{col_name} migration FAILED: {e}", exc_info=True)
        if added:
            logger.info(f"Ensured {added} loan columns exist")

        # Create index on encompass_loan_id if it doesn't exist
        try:
            db.execute(sa_text("""
                CREATE INDEX IF NOT EXISTS ix_loans_encompass_loan_id
                ON loans (encompass_loan_id)
            """))
            db.commit()
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"encompass_loan_id index creation FAILED: {e}", exc_info=True)

        # Fix 2: Add missing columns to leads table
        lead_columns = [
            # Co-applicant
            ("co_applicant_name", "VARCHAR"),
            ("co_applicant_email", "VARCHAR"),
            ("co_applicant_phone", "VARCHAR"),
            ("preferred_communication", "VARCHAR"),
            ("organization_code", "VARCHAR"),
            # Financial
            ("debt_to_income", "NUMERIC(8,4)"),
            ("property_value", "NUMERIC(18,2)"),
            ("down_payment", "NUMERIC(18,2)"),
            ("employment_status", "VARCHAR"),
            ("annual_income", "NUMERIC(18,2)"),
            ("monthly_debts", "NUMERIC(18,2)"),
            ("first_time_buyer", "BOOLEAN DEFAULT FALSE"),
            # Loan Details
            ("loan_amount", "NUMERIC(18,2)"),
            ("interest_rate", "NUMERIC(8,4)"),
            ("loan_term", "INTEGER"),
            ("apr", "NUMERIC(8,4)"),
            ("points", "NUMERIC(8,4)"),
            ("lock_date", "TIMESTAMP"),
            ("lock_expiration", "TIMESTAMP"),
            ("closing_date", "TIMESTAMP"),
            ("lender", "VARCHAR"),
            ("loan_officer", "VARCHAR"),
            ("processor", "VARCHAR"),
            ("underwriter", "VARCHAR"),
            ("appraisal_value", "NUMERIC(18,2)"),
            ("ltv", "NUMERIC(8,4)"),
            ("cltv", "NUMERIC(8,4)"),
            ("dti", "NUMERIC(8,4)"),
            ("dti_front", "NUMERIC(8,4)"),
            ("dti_back", "NUMERIC(8,4)"),
            ("program", "VARCHAR"),
            ("status_date", "TIMESTAMP"),
            # SLA Milestone Dates
            ("lead_received_date", "TIMESTAMP"),
            ("first_contact_attempt_date", "TIMESTAMP"),
            ("first_contact_successful_date", "TIMESTAMP"),
            ("lead_qualification_date", "TIMESTAMP"),
            ("application_link_sent_date", "TIMESTAMP"),
            ("application_started_date", "TIMESTAMP"),
            ("application_completed_date", "TIMESTAMP"),
            ("credit_pulled_date", "TIMESTAMP"),
            ("preapproval_submission_date", "TIMESTAMP"),
            ("preapproval_issued_date", "TIMESTAMP"),
            ("preapproval_expiration_date", "TIMESTAMP"),
            ("realtor_referral_date", "TIMESTAMP"),
            ("rate_watch_enrollment_date", "TIMESTAMP"),
            ("initial_consultation_date", "TIMESTAMP"),
            ("property_address", "VARCHAR"),
            ("expected_purchase_date", "TIMESTAMP"),
            ("target_payment", "NUMERIC(18,2)"),
            # Referral fields
            ("referral_score", "INTEGER DEFAULT 0"),
            ("referral_source_score", "INTEGER DEFAULT 0"),
            ("employment_referral_flag", "BOOLEAN DEFAULT FALSE"),
            ("manager_flag", "BOOLEAN DEFAULT FALSE"),
            ("employees_managed", "INTEGER DEFAULT 0"),
            ("leadership_level", "VARCHAR"),
            ("company_size", "INTEGER"),
            ("employer_name", "VARCHAR"),
            ("industry", "VARCHAR"),
            ("circle_of_cash_flow_map", "JSONB"),
            # Workflow tracking
            ("current_workflow_id", "VARCHAR"),
            ("workflow_day", "INTEGER DEFAULT 0"),
            ("last_workflow_action", "TIMESTAMP"),
            ("nurture_month", "INTEGER DEFAULT 0"),
            ("stage_changed_at", "TIMESTAMP"),
            ("current_milestone_status", "VARCHAR(50)"),
            ("current_milestone_entered_at", "TIMESTAMP"),
            # Salesforce Sync - Property
            ("occupancy_type", "VARCHAR"),
            ("property_county", "VARCHAR"),
            ("property_ownership_type", "VARCHAR"),
            ("property_units", "INTEGER"),
            # Salesforce Sync - Financial
            ("rate_type", "VARCHAR"),
            ("monthly_payment", "NUMERIC(18,2)"),
            ("property_tax", "NUMERIC(18,2)"),
            ("hazard_insurance", "NUMERIC(18,2)"),
            ("mortgage_insurance", "NUMERIC(18,2)"),
            ("hoa_amount", "NUMERIC(18,2)"),
            ("origination_fee", "NUMERIC(18,2)"),
            ("estimated_prepaid_interest", "NUMERIC(18,2)"),
            ("index_rate", "NUMERIC(8,4)"),
            ("margin", "NUMERIC(8,4)"),
            ("loan_purpose", "VARCHAR"),
            ("file_state", "VARCHAR"),
            # Salesforce Sync - 2nd Loan
            ("second_loan_amount", "NUMERIC(18,2)"),
            ("second_loan_rate", "NUMERIC(8,4)"),
            ("second_loan_payment", "NUMERIC(18,2)"),
            # Salesforce Sync - Housing Expenses
            ("present_housing_expense", "NUMERIC(18,2)"),
            ("proposed_housing_expense", "NUMERIC(18,2)"),
            ("present_monthly_payment", "NUMERIC(18,2)"),
            ("proposed_monthly_payment", "NUMERIC(18,2)"),
            # Metadata
            ("salesforce_id", "VARCHAR"),
            ("meta_data", "JSONB"),
            ("user_metadata", "JSONB"),
            # COMP-001: AI modification tracking
            ("last_modified_by_ai", "BOOLEAN DEFAULT FALSE"),
            # COMP-004: GDPR PII retention with automated expiry
            ("data_retention_expires_at", "TIMESTAMP"),
        ]
        leads_added = 0
        for col_name, col_type in lead_columns:
            try:
                alter_sql = "ALTER TABLE leads ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                db.execute(sa_text(alter_sql))
                db.commit()
                leads_added += 1
                success_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"leads.{col_name} migration FAILED: {e}", exc_info=True)
        if leads_added:
            logger.info(f"Ensured {leads_added} lead columns exist")

        # Fix 3a: Convert leads.stage from PostgreSQL ENUM to VARCHAR if needed
        # The model defines Column(String) but the DB may have a leadstage enum type
        try:
            result = db.execute(sa_text("""
                SELECT data_type, udt_name FROM information_schema.columns
                WHERE table_name = 'leads' AND column_name = 'stage'
            """)).fetchone()
            if result and result[1] == 'leadstage':
                logger.info("Converting leads.stage from enum to varchar...")
                db.execute(sa_text("ALTER TABLE leads ALTER COLUMN stage TYPE VARCHAR USING stage::text"))
                db.commit()
                logger.info("leads.stage converted from enum to varchar")
                success_count += 1
            else:
                skip_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"leads.stage type migration FAILED: {e}", exc_info=True)

        # Fix 3b: Convert loans.stage from PostgreSQL ENUM to VARCHAR if needed
        try:
            result = db.execute(sa_text("""
                SELECT data_type, udt_name FROM information_schema.columns
                WHERE table_name = 'loans' AND column_name = 'stage'
            """)).fetchone()
            if result and result[1] == 'loanstage':
                logger.info("Converting loans.stage from enum to varchar...")
                db.execute(sa_text("ALTER TABLE loans ALTER COLUMN stage TYPE VARCHAR USING stage::text"))
                db.commit()
                logger.info("loans.stage converted from enum to varchar")
                success_count += 1
            else:
                skip_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"loans.stage type migration FAILED: {e}", exc_info=True)

        # Fix 4: Backfill MUM client names from leads (replace "Client - XXX" with real names)
        try:
            result = db.execute(sa_text("""
                UPDATE mum_clients m
                SET client_name = TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')),
                    updated_at = CURRENT_TIMESTAMP
                FROM leads le
                WHERE m.client_name LIKE 'Client - %'
                  AND (
                      (le.loan_number = m.loan_number AND le.loan_number IS NOT NULL)
                      OR (le.email = m.email AND le.email IS NOT NULL)
                  )
                  AND TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')) != ''
            """))
            db.commit()
            if result.rowcount > 0:
                logger.info(f"Backfilled {result.rowcount} MUM client names from leads")
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"MUM name backfill FAILED: {e}", exc_info=True)

        # Chime SDK migration: add columns for video meeting Chime integration
        chime_columns = {
            "video_meeting_rooms": [
                ("chime_meeting_id", "VARCHAR(255)"),
                ("chime_media_region", "VARCHAR(50) DEFAULT 'us-east-1'"),
            ],
            "meeting_recordings": [
                ("chime_pipeline_id", "VARCHAR(255)"),
                ("s3_key", "VARCHAR(1000)"),
            ],
        }
        for table, cols in chime_columns.items():
            for col_name, col_type in cols:
                try:
                    alter_sql = "ALTER TABLE " + table + " ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                    db.execute(sa_text(alter_sql))
                    db.commit()
                    success_count += 1
                except Exception as e:
                    db.rollback()
                    fail_count += 1
                    logger.error(f"{table}.{col_name} migration FAILED: {e}", exc_info=True)
        try:
            db.execute(sa_text("CREATE INDEX IF NOT EXISTS ix_video_meeting_rooms_chime_meeting_id ON video_meeting_rooms (chime_meeting_id)"))
            db.commit()
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"chime_meeting_id index creation FAILED: {e}", exc_info=True)
        try:
            db.execute(sa_text("ALTER TABLE meeting_recordings ALTER COLUMN retention_days SET DEFAULT 1825"))
            db.commit()
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"retention_days default migration FAILED: {e}", exc_info=True)
        try:
            result = db.execute(sa_text("UPDATE meeting_recordings SET retention_days = 1825 WHERE retention_days = 90"))
            db.commit()
            if result.rowcount > 0:
                logger.info(f"Updated {result.rowcount} recording retention periods to 5 years")
            success_count += 1
        except Exception as e:
            db.rollback()
            fail_count += 1
            logger.error(f"retention_days update FAILED: {e}", exc_info=True)

        # Fix N: Add missing columns to users table
        # The User model defines columns that may not exist in the production table,
        # causing ProgrammingError on any query that SELECTs all User columns.
        users_columns = [
            ("manager_id", "INTEGER"),
            ("briefing_enabled", "BOOLEAN DEFAULT TRUE"),
            ("briefing_hour", "INTEGER DEFAULT 7"),
            ("briefing_preferences", "JSONB"),
            ("email_verified", "BOOLEAN DEFAULT FALSE"),
            ("onboarding_completed", "BOOLEAN DEFAULT FALSE"),
            ("user_metadata", "JSON"),
            ("phone", "VARCHAR(50)"),
            ("nmls_number", "VARCHAR(50)"),
            ("business_address", "VARCHAR(500)"),
            ('"current_role"', "VARCHAR(100)"),
            ("business_hours", "JSON"),
            ("email_verified_at", "TIMESTAMP"),
            ("phone_verified_at", "TIMESTAMP"),
            ("slug", "VARCHAR(255)"),
            ("company_logo_url", "TEXT"),
            ("headshot_url", "TEXT"),
            ("title", "TEXT"),
            ("team_name", "TEXT"),
            ("nmls_id", "VARCHAR(50)"),
            ("timezone", "VARCHAR(100) DEFAULT 'America/Chicago'"),
            ("last_activity_at", "TIMESTAMP"),
            ("failed_login_attempts", "INTEGER DEFAULT 0"),
            ("locked_until", "TIMESTAMP"),
            ("last_failed_login_at", "TIMESTAMP"),
            ("mfa_secret", "VARCHAR(255)"),
            ("mfa_enabled", "BOOLEAN DEFAULT FALSE"),
            ("mfa_backup_codes", "JSON"),
            ("mfa_enabled_at", "TIMESTAMP"),
            ("sso_provider", "VARCHAR(50)"),
            ("sso_subject_id", "VARCHAR(255)"),
        ]
        u_added = 0
        for col_name, col_type in users_columns:
            try:
                alter_sql = "ALTER TABLE users ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                db.execute(sa_text(alter_sql))
                db.commit()
                u_added += 1
                success_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"users.{col_name} migration FAILED: {e}", exc_info=True)
        if u_added:
            logger.info(f"Ensured {u_added} users columns exist")

        # Fix N+1: Add missing columns to scheduler tables
        # The BookingLink model defines columns (organization_id, etc.) that may not
        # exist in the production table, causing 503 on public booking endpoints.
        scheduler_table_migrations = {
            "scheduler_booking_links": [
                ("organization_id", "INTEGER"),
                ("user_id", "INTEGER"),
                ("single_appointment_type_id", "INTEGER"),
                ("requires_authentication", "BOOLEAN DEFAULT FALSE"),
                ("password_protected", "BOOLEAN DEFAULT FALSE"),
                ("password_hash", "VARCHAR(255)"),
                ("custom_title", "VARCHAR(255)"),
                ("custom_description", "TEXT"),
                ("custom_logo_url", "VARCHAR(500)"),
                ("custom_color", "VARCHAR(20)"),
                ("max_bookings", "INTEGER"),
                ("current_bookings", "INTEGER DEFAULT 0"),
                ("max_per_person", "INTEGER"),
                ("available_from", "TIMESTAMP"),
                ("available_until", "TIMESTAMP"),
                ("routing_strategy", "VARCHAR(50) DEFAULT 'relationship'"),
                ("assigned_users", "JSONB"),
                ("view_count", "INTEGER DEFAULT 0"),
                ("booking_count", "INTEGER DEFAULT 0"),
                ("last_booked_at", "TIMESTAMP"),
                ("default_utm_source", "VARCHAR(100)"),
                ("default_utm_medium", "VARCHAR(100)"),
                ("default_utm_campaign", "VARCHAR(100)"),
                ("expires_at", "TIMESTAMP"),
            ],
            "scheduler_configs": [
                ("organization_id", "INTEGER"),
                ("user_id", "INTEGER"),
                ("working_hours", "JSONB"),
                ("min_notice_hours", "INTEGER DEFAULT 2"),
                ("max_advance_days", "INTEGER DEFAULT 30"),
                ("buffer_before_minutes", "INTEGER DEFAULT 5"),
                ("buffer_after_minutes", "INTEGER DEFAULT 5"),
                ("max_meetings_per_day", "INTEGER DEFAULT 8"),
                ("ai_scheduling_config", "JSON"),
                ("notification_settings", "JSON"),
                ("setup_completed", "BOOLEAN DEFAULT FALSE"),
                ("setup_progress", "JSON"),
                ("feature_toggles", "JSON"),
            ],
            "appointment_types": [
                ("organization_id", "INTEGER"),
                ("config_id", "INTEGER"),
                ("type_key", "VARCHAR(100)"),
                ("allowed_durations", "JSONB"),
                ("meeting_type", "VARCHAR(50)"),
                ("default_mode", "VARCHAR(20)"),
                ("color", "VARCHAR(20)"),
                ("icon", "VARCHAR(50)"),
                ("intake_questions", "JSONB"),
                ("requires_confirmation", "BOOLEAN DEFAULT FALSE"),
                ("buffer_before_minutes", "INTEGER DEFAULT 5"),
                ("buffer_after_minutes", "INTEGER DEFAULT 5"),
            ],
            "scheduler_blocked_times": [
                ("organization_id", "INTEGER"),
                ("user_id", "INTEGER"),
                ("title", "VARCHAR(255)"),
                ("description", "TEXT"),
                ("block_type", "VARCHAR(50) DEFAULT 'custom'"),
                ("start_datetime", "TIMESTAMP"),
                ("end_datetime", "TIMESTAMP"),
                ("all_day", "BOOLEAN DEFAULT FALSE"),
                ("is_recurring", "BOOLEAN DEFAULT FALSE"),
                ("recurrence_pattern", "JSON"),
                ("recurrence_end_date", "DATE"),
                ("applies_to_all_users", "BOOLEAN DEFAULT FALSE"),
                ("applies_to_teams", "JSON"),
                ("is_active", "BOOLEAN DEFAULT TRUE"),
                ("created_at", "TIMESTAMP DEFAULT NOW()"),
                ("updated_at", "TIMESTAMP DEFAULT NOW()"),
                ("created_by_id", "INTEGER"),
            ],
            "scheduler_appointments": [
                ("organization_id", "INTEGER"),
                ("appointment_type_id", "INTEGER"),
                ("assigned_user_id", "INTEGER"),
                ("created_by_user_id", "INTEGER"),
                ("lead_id", "INTEGER"),
                ("loan_id", "INTEGER"),
                ("contact_id", "INTEGER"),
                ("idempotency_key", "VARCHAR(64)"),
                ("external_id", "VARCHAR(100)"),
                ("external_source", "VARCHAR(50)"),
                ("title", "VARCHAR(255)"),
                ("description", "TEXT"),
                ("meeting_type", "VARCHAR(50)"),
                ("meeting_mode", "VARCHAR(50)"),
                ("scheduled_start", "TIMESTAMP"),
                ("scheduled_end", "TIMESTAMP"),
                ("duration_minutes", "INTEGER"),
                ("timezone", "VARCHAR(50) DEFAULT 'America/Chicago'"),
                ("location", "VARCHAR(255)"),
                ("video_link", "VARCHAR(500)"),
                ("phone_number", "VARCHAR(20)"),
                ("dial_in_info", "TEXT"),
                ("attendee_name", "VARCHAR(255)"),
                ("attendee_email", "VARCHAR(255)"),
                ("attendee_phone", "VARCHAR(20)"),
                ("attendee_notes", "TEXT"),
                ("intake_responses", "JSON"),
                ("status", "VARCHAR(50) DEFAULT 'booked'"),
                ("status_changed_at", "TIMESTAMP"),
                ("status_changed_by", "INTEGER"),
                ("completed_at", "TIMESTAMP"),
                ("no_show_at", "TIMESTAMP"),
                ("cancelled_at", "TIMESTAMP"),
                ("cancellation_reason", "TEXT"),
                ("rescheduled_from_id", "INTEGER"),
                ("reschedule_count", "INTEGER DEFAULT 0"),
                ("booked_by_ai", "BOOLEAN DEFAULT FALSE"),
                ("ai_booking_context", "JSON"),
                ("auto_confirmed", "BOOLEAN DEFAULT FALSE"),
                ("google_calendar_event_id", "VARCHAR(255)"),
                ("outlook_event_id", "VARCHAR(255)"),
                ("last_synced_at", "TIMESTAMP"),
                ("internal_notes", "TEXT"),
                ("meeting_notes", "TEXT"),
                ("version", "INTEGER DEFAULT 1"),
                ("recovery_step", "INTEGER DEFAULT 0"),
                ("recovery_started_at", "TIMESTAMP"),
                ("recovery_completed_at", "TIMESTAMP"),
                ("recovery_opted_out", "BOOLEAN DEFAULT FALSE"),
                ("communication_consent_at", "TIMESTAMP"),
                ("communication_consent_source", "VARCHAR(50)"),
                ("booking_attribution", "JSON"),
                ("created_at", "TIMESTAMP DEFAULT NOW()"),
                ("updated_at", "TIMESTAMP DEFAULT NOW()"),
            ],
        }
        for table_name, columns in scheduler_table_migrations.items():
            tbl_added = 0
            for col_name, col_type in columns:
                try:
                    alter_sql = "ALTER TABLE " + table_name + " ADD COLUMN IF NOT EXISTS " + col_name + " " + col_type
                    db.execute(sa_text(alter_sql))
                    db.commit()
                    tbl_added += 1
                    success_count += 1
                except Exception as e:
                    db.rollback()
                    fail_count += 1
                    logger.error(f"{table_name}.{col_name} migration FAILED: {e}", exc_info=True)
            if tbl_added:
                logger.info(f"Ensured {tbl_added} {table_name} columns exist")

        # Fix N+2: Convert scheduler ENUM columns to VARCHAR
        # Same pattern as Lead.stage and Loan.stage — the production DB has a
        # PostgreSQL ENUM type that doesn't include newer status values (CONFIRMED,
        # REMINDED, CHECKED_IN). Converting to VARCHAR lets any string value work.
        enum_to_varchar_conversions = [
            ("scheduler_appointments", "status", "appointmentstatus"),
            ("scheduler_appointments", "meeting_type", "meetingtype"),
            ("scheduler_appointments", "meeting_mode", "meetingmode"),
        ]
        for table, col, enum_type in enum_to_varchar_conversions:
            try:
                # Check if column is currently an enum type
                col_info = db.execute(sa_text(
                    "SELECT data_type, udt_name FROM information_schema.columns "
                    "WHERE table_name = :tbl AND column_name = :col"
                ), {"tbl": table, "col": col}).fetchone()
                if col_info and col_info[0] == 'USER-DEFINED':
                    alter_col_sql = "ALTER TABLE " + table + " ALTER COLUMN " + col + " TYPE VARCHAR(50) USING " + col + "::text"
                    db.execute(sa_text(alter_col_sql))
                    db.commit()
                    logger.info(f"Converted {table}.{col} from enum to VARCHAR")
                    success_count += 1
                    # Drop the old enum type if it's no longer used
                    try:
                        drop_type_sql = "DROP TYPE IF EXISTS " + enum_type
                        db.execute(sa_text(drop_type_sql))
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Failed to drop enum type {enum_type}: {e}", exc_info=True)
                else:
                    skip_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"Enum conversion {table}.{col} FAILED: {e}", exc_info=True)

        # Fix N+3: Create missing scheduler tables if they don't exist
        missing_tables_sql = [
            """CREATE TABLE IF NOT EXISTS scheduler_slot_holds (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                appointment_type_id INTEGER,
                user_id INTEGER,
                slot_start TIMESTAMP NOT NULL,
                slot_end TIMESTAMP NOT NULL,
                hold_token VARCHAR(64) UNIQUE,
                held_by_email VARCHAR(255),
                held_by_session VARCHAR(255),
                expires_at TIMESTAMP NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                converted_to_appointment_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS recurring_availability (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                user_id INTEGER,
                day_of_week INTEGER NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS availability_exceptions (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                user_id INTEGER,
                exception_date DATE NOT NULL,
                start_time TIME,
                end_time TIME,
                is_available BOOLEAN DEFAULT FALSE,
                reason VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW()
            )""",
        ]
        for create_sql in missing_tables_sql:
            try:
                db.execute(sa_text(create_sql))
                db.commit()
                success_count += 1
            except Exception as e:
                db.rollback()
                fail_count += 1
                logger.error(f"Table creation FAILED: {e}", exc_info=True)

        # --- SMS AI confidence: align model columns with SQL migration schema ---
        sms_conf_alters = [
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS total_recommendations INTEGER DEFAULT 0",
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS confidence_score FLOAT DEFAULT 20.0",
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS auto_respond_threshold FLOAT DEFAULT 80.0",
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS user_id INTEGER",
        ]
        for alter in sms_conf_alters:
            try:
                db.execute(sa_text(alter))
                db.commit()
            except Exception:
                db.rollback()

        # Copy data from old column names if they exist
        try:
            db.execute(sa_text("""
                UPDATE sms_ai_confidence
                SET total_recommendations = total_suggestions
                WHERE total_recommendations = 0 AND total_suggestions > 0
            """))
            db.commit()
        except Exception:
            db.rollback()

        # Unique index with COALESCE for nullable user_id (matches engine UPSERT)
        try:
            db.execute(sa_text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sms_ai_conf_org_user_cat
                ON sms_ai_confidence (organization_id, COALESCE(user_id, 0), category)
            """))
            db.commit()
        except Exception:
            db.rollback()

        # --- SMS AI confidence: additional model columns not in original migration ---
        sms_conf_extra_alters = [
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS accepted_count INTEGER DEFAULT 0",
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS edited_count INTEGER DEFAULT 0",
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS rejected_count INTEGER DEFAULT 0",
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS auto_respond_enabled BOOLEAN DEFAULT FALSE",
            "ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        ]
        for alter in sms_conf_extra_alters:
            try:
                db.execute(sa_text(alter))
                db.commit()
            except Exception:
                db.rollback()

        # --- SMS response patterns: align model columns with table schema ---
        sms_patterns_alters = [
            "ALTER TABLE sms_response_patterns ADD COLUMN IF NOT EXISTS times_used INTEGER DEFAULT 1",
            "ALTER TABLE sms_response_patterns ADD COLUMN IF NOT EXISTS times_accepted INTEGER DEFAULT 0",
            "ALTER TABLE sms_response_patterns ADD COLUMN IF NOT EXISTS times_edited INTEGER DEFAULT 0",
            "ALTER TABLE sms_response_patterns ADD COLUMN IF NOT EXISTS times_rejected INTEGER DEFAULT 0",
            "ALTER TABLE sms_response_patterns ADD COLUMN IF NOT EXISTS message_keywords JSONB",
            "ALTER TABLE sms_response_patterns ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ",
            "ALTER TABLE sms_response_patterns ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER",
        ]
        for alter in sms_patterns_alters:
            try:
                db.execute(sa_text(alter))
                db.commit()
            except Exception:
                db.rollback()

        # Unique constraint for ON CONFLICT UPSERT in pattern recording
        try:
            db.execute(sa_text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sms_patterns_org_cat_template
                ON sms_response_patterns (organization_id, category, md5(response_template))
            """))
            db.commit()
        except Exception:
            db.rollback()

        # --- workflow_task_instances: add retry tracking columns if missing ---
        wti_retry_alters = [
            "ALTER TABLE workflow_task_instances ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE workflow_task_instances ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMP",
        ]
        for alter in wti_retry_alters:
            try:
                db.execute(sa_text(alter))
                db.commit()
            except Exception:
                db.rollback()

        # --- Convert health_status from enum to VARCHAR (same pattern as leads.stage) ---
        try:
            db.execute(sa_text("""
                ALTER TABLE workflow_task_instances
                ALTER COLUMN health_status TYPE VARCHAR(50)
                USING health_status::text
            """))
            db.commit()
        except Exception:
            db.rollback()

        # --- Convert SOC2 tables tenant_id from UUID to VARCHAR(50) ---
        # Organization IDs are integers, not UUIDs
        for soc2_table in [
            "soc2_audit_log", "soc2_auth_events", "soc2_security_incident",
            "soc2_data_access_log", "soc2_change_management",
        ]:
            try:
                db.execute(sa_text(f"""
                    ALTER TABLE {soc2_table}
                    ALTER COLUMN tenant_id TYPE VARCHAR(50)
                    USING tenant_id::text
                """))
                db.commit()
            except Exception:
                db.rollback()

        # --- Add organization_id to ai_colleague_actions if missing ---
        try:
            db.execute(sa_text("""
                ALTER TABLE ai_colleague_actions
                ADD COLUMN IF NOT EXISTS organization_id INTEGER
            """))
            db.commit()
        except Exception:
            db.rollback()

        # --- Create workflow_task_alerts if missing ---
        try:
            db.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS workflow_task_alerts (
                    id SERIAL PRIMARY KEY,
                    task_instance_id INTEGER REFERENCES workflow_task_instances(id) ON DELETE CASCADE,
                    alert_type VARCHAR(100) NOT NULL,
                    severity VARCHAR(20) NOT NULL DEFAULT 'medium',
                    message TEXT,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    acknowledged_by INTEGER REFERENCES users(id),
                    acknowledged_at TIMESTAMPTZ,
                    organization_id INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            db.commit()
        except Exception:
            db.rollback()

        # --- Add missing columns to verified_caller_ids ---
        vcid_columns = [
            ("provider_sid", "VARCHAR"),
            ("verified_at", "TIMESTAMP"),
            ("organization_id", "INTEGER"),
            ("user_id", "INTEGER REFERENCES users(id)"),
        ]
        for col_name, col_type in vcid_columns:
            try:
                db.execute(sa_text(
                    f"ALTER TABLE verified_caller_ids ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                db.commit()
                success_count += 1
            except Exception:
                db.rollback()

        # --- Add missing columns to agent_telephony_settings ---
        ats_columns = [
            ("organization_id", "INTEGER"),
        ]
        for col_name, col_type in ats_columns:
            try:
                db.execute(sa_text(
                    f"ALTER TABLE agent_telephony_settings ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                ))
                db.commit()
                success_count += 1
            except Exception:
                db.rollback()

        logger.info(f"Schema migrations: {success_count} applied, {skip_count} skipped, {fail_count} FAILED")
        if fail_count > 0:
            logger.error(f"Schema migrations completed with {fail_count} FAILURES — check logs above for details")
    finally:
        db.close()
