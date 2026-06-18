"""Reconcile startup_migrations.py schema changes with Alembic.

All operations are idempotent (IF NOT EXISTS / existence checks).
Safe to run against databases that already have all columns — will be a no-op.

This migration captures the schema changes applied by startup_migrations.py
(both _run_critical_schema_migrations and the individual migration modules)
that Alembic did not previously track.  It fills the gap between the
018_recording_consent baseline and the schema as built by the legacy
startup path.

Sources reconciled:
  - startup_migrations._run_critical_schema_migrations (lines 643–1469)
  - migrations/hash_api_keys.py
  - migrations/add_tcpa_consents_table.py (model-based, no raw SQL here)
  - migrations/enterprise_challenge_tables.py
  - migrations/add_pos_consent_tables.py
  - migrations/add_application_events_table.py
  - migrations/add_autonomous_agent_runs.py
  - migrations/add_ai_autonomy_tables.py (model-based, tables not listed)
  - migrations/consolidate_oauth_tokens.py
  - migrations/add_call_intelligence_columns.py
  - migrations/add_voice_workflows_table.py
  - migrations/add_encompass_columns.py
  - Early inline blocks in run_all_startup_migrations (scheduler_appointments,
    compliance_alerts, encompass_configs, agent_actions)

Revision: 019_reconcile
"""

from alembic import op

revision = "019_reconcile"
down_revision = "018_recording_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # SECTION 1 — loans table columns
    # Source: _run_critical_schema_migrations (Fix 1)
    # =========================================================================
    _loans_columns = [
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
    for col_name, col_type in _loans_columns:
        op.execute(
            f"ALTER TABLE loans ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # Index on encompass_loan_id
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_loans_encompass_loan_id "
        "ON loans (encompass_loan_id)"
    )

    # =========================================================================
    # SECTION 2 — leads table columns
    # Source: _run_critical_schema_migrations (Fix 2)
    # =========================================================================
    _leads_columns = [
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
    for col_name, col_type in _leads_columns:
        op.execute(
            f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 3 — leads.stage and loans.stage enum → VARCHAR conversions
    # Source: _run_critical_schema_migrations (Fix 3a / 3b)
    # Only converts if the column is still a PostgreSQL USER-DEFINED enum type.
    # =========================================================================
    op.execute("""
        DO $$
        DECLARE
            col_udt TEXT;
        BEGIN
            SELECT udt_name INTO col_udt
            FROM information_schema.columns
            WHERE table_name = 'leads' AND column_name = 'stage';
            IF col_udt = 'leadstage' THEN
                ALTER TABLE leads ALTER COLUMN stage TYPE VARCHAR USING stage::text;
            END IF;
        END $$;
    """)

    op.execute("""
        DO $$
        DECLARE
            col_udt TEXT;
        BEGIN
            SELECT udt_name INTO col_udt
            FROM information_schema.columns
            WHERE table_name = 'loans' AND column_name = 'stage';
            IF col_udt = 'loanstage' THEN
                ALTER TABLE loans ALTER COLUMN stage TYPE VARCHAR USING stage::text;
            END IF;
        END $$;
    """)

    # =========================================================================
    # SECTION 4 — users table columns
    # Source: _run_critical_schema_migrations (Fix N)
    # =========================================================================
    _users_columns = [
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
        # "current_role" intentionally quoted to match the startup migration pattern
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
        ("password_changed_at", "TIMESTAMP WITH TIME ZONE"),
    ]
    for col_name, col_type in _users_columns:
        op.execute(
            f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 5 — scheduler_appointments early columns
    # Source: run_all_startup_migrations inline block (lines 77-99)
    # =========================================================================
    _sched_appt_early_cols = [
        ("recovery_step", "INTEGER DEFAULT 0"),
        ("recovery_started_at", "TIMESTAMP"),
        ("recovery_completed_at", "TIMESTAMP"),
        ("recovery_opted_out", "BOOLEAN DEFAULT false"),
        ("communication_consent_at", "TIMESTAMP"),
        ("communication_consent_source", "VARCHAR(50)"),
        ("booking_attribution", "JSONB"),
    ]
    for col_name, col_type in _sched_appt_early_cols:
        op.execute(
            f"ALTER TABLE scheduler_appointments ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 6 — scheduler_booking_links columns
    # Source: _run_critical_schema_migrations (Fix N+1)
    # =========================================================================
    _sbl_columns = [
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
    ]
    for col_name, col_type in _sbl_columns:
        op.execute(
            f"ALTER TABLE scheduler_booking_links ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 7 — scheduler_configs columns
    # Source: _run_critical_schema_migrations (Fix N+1)
    # =========================================================================
    _sc_columns = [
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
    ]
    for col_name, col_type in _sc_columns:
        op.execute(
            f"ALTER TABLE scheduler_configs ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 8 — appointment_types columns
    # Source: _run_critical_schema_migrations (Fix N+1)
    # =========================================================================
    _at_columns = [
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
    ]
    for col_name, col_type in _at_columns:
        op.execute(
            f"ALTER TABLE appointment_types ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 9 — scheduler_blocked_times columns
    # Source: _run_critical_schema_migrations (Fix N+1)
    # =========================================================================
    _sbt_columns = [
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
    ]
    for col_name, col_type in _sbt_columns:
        op.execute(
            f"ALTER TABLE scheduler_blocked_times ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 10 — scheduler_appointments full column set
    # Source: _run_critical_schema_migrations (Fix N+1)
    # =========================================================================
    _sa_columns = [
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
        ("created_at", "TIMESTAMP DEFAULT NOW()"),
        ("updated_at", "TIMESTAMP DEFAULT NOW()"),
    ]
    for col_name, col_type in _sa_columns:
        op.execute(
            f"ALTER TABLE scheduler_appointments ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 11 — scheduler ENUM → VARCHAR conversions
    # Source: _run_critical_schema_migrations (Fix N+2)
    # =========================================================================
    for _tbl, _col in [
        ("scheduler_appointments", "status"),
        ("scheduler_appointments", "meeting_type"),
        ("scheduler_appointments", "meeting_mode"),
    ]:
        op.execute(f"""
            DO $$
            DECLARE
                col_data_type TEXT;
            BEGIN
                SELECT data_type INTO col_data_type
                FROM information_schema.columns
                WHERE table_name = '{_tbl}' AND column_name = '{_col}';
                IF col_data_type = 'USER-DEFINED' THEN
                    ALTER TABLE {_tbl}
                    ALTER COLUMN {_col} TYPE VARCHAR(50)
                    USING {_col}::text;
                END IF;
            END $$;
        """)

    # =========================================================================
    # SECTION 12 — Missing scheduler tables
    # Source: _run_critical_schema_migrations (Fix N+3)
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_slot_holds (
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
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS recurring_availability (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER,
            user_id INTEGER,
            day_of_week INTEGER NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS availability_exceptions (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER,
            user_id INTEGER,
            exception_date DATE NOT NULL,
            start_time TIME,
            end_time TIME,
            is_available BOOLEAN DEFAULT FALSE,
            reason VARCHAR(255),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # =========================================================================
    # SECTION 13 — compliance_alerts table
    # Source: run_all_startup_migrations inline block (lines 587-620)
    # =========================================================================
    op.execute("""
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
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_alerts_loan_id "
        "ON compliance_alerts (loan_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_alerts_org_id "
        "ON compliance_alerts (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_alerts_status "
        "ON compliance_alerts (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_alerts_loan_status "
        "ON compliance_alerts (loan_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_alerts_org_severity "
        "ON compliance_alerts (organization_id, severity)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_alerts_org_type "
        "ON compliance_alerts (organization_id, alert_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_compliance_alerts_deadline "
        "ON compliance_alerts (deadline_date)"
    )

    # =========================================================================
    # SECTION 14 — encompass_configs table + missing columns
    # Source: migrations/add_encompass_columns.py + inline block (lines 622-638)
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS encompass_configs (
            id VARCHAR PRIMARY KEY,
            organization_id INTEGER NOT NULL UNIQUE,
            instance_id VARCHAR NOT NULL,
            client_id VARCHAR NOT NULL,
            client_secret VARCHAR NOT NULL,
            api_user VARCHAR,
            webhook_secret VARCHAR,
            auto_pull_on_webhook BOOLEAN DEFAULT TRUE,
            auto_push_on_stage_change BOOLEAN DEFAULT FALSE,
            sync_frequency_minutes INTEGER DEFAULT 60,
            last_sync_at TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_encompass_configs_org_id "
        "ON encompass_configs (organization_id)"
    )
    # Additional columns added after initial table creation
    op.execute(
        "ALTER TABLE IF EXISTS encompass_configs "
        "ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE IF EXISTS encompass_configs "
        "ADD COLUMN IF NOT EXISTS consecutive_auth_failures INTEGER DEFAULT 0"
    )

    # =========================================================================
    # SECTION 15 — agent_actions columns
    # Source: run_all_startup_migrations inline blocks (lines 169-212)
    # =========================================================================
    # Make execution_id nullable — wrapped in DO block so it's safe if already nullable
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'agent_actions'
            ) THEN
                ALTER TABLE agent_actions ALTER COLUMN execution_id DROP NOT NULL;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)
    # Use DO block for the conditional index (conditional CREATE INDEX)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'agent_actions'
            ) THEN
                CREATE INDEX IF NOT EXISTS ix_agentact_org_status
                ON agent_actions (organization_id, status);
            END IF;
        END $$;
    """)
    op.execute(
        "ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS rejected_by INTEGER"
    )
    op.execute(
        "ALTER TABLE agent_actions ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ"
    )

    # =========================================================================
    # SECTION 16 — api_keys table columns
    # Source: migrations/hash_api_keys.py
    # =========================================================================
    op.execute(
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_hash VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_prefix VARCHAR(12)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash "
        "ON api_keys (key_hash) WHERE key_hash IS NOT NULL"
    )
    # Make key column nullable (was NOT NULL before hash migration)
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE api_keys ALTER COLUMN key DROP NOT NULL;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)
    # Drop the unique constraint on the plaintext key column if it still exists
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS api_keys_key_key;
        EXCEPTION WHEN undefined_object THEN
            NULL;
        END $$;
    """)

    # =========================================================================
    # SECTION 17 — enterprise challenge tables (D1, D2, D6, D8, governance)
    # Source: migrations/enterprise_challenge_tables.py
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS loan_file_collaborators (
            id              SERIAL PRIMARY KEY,
            loan_id         INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            role            VARCHAR(50) NOT NULL DEFAULT 'read_only',
            permissions_override JSONB DEFAULT '{}',
            is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
            notify          BOOLEAN NOT NULL DEFAULT TRUE,
            assigned_by     INTEGER REFERENCES users(id),
            assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            removed_at      TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_loan_file_collab_active UNIQUE (loan_id, user_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lfc_loan_id ON loan_file_collaborators (loan_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lfc_user_id ON loan_file_collaborators (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lfc_org_id ON loan_file_collaborators (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lfc_org_loan ON loan_file_collaborators (organization_id, loan_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS user_onboarding_state (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            step            VARCHAR(100) NOT NULL,
            step_order      INTEGER NOT NULL DEFAULT 1,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending',
            completed_at    TIMESTAMPTZ,
            error_message   TEXT,
            agent_run_id    UUID,
            step_metadata   JSONB DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_user_onboarding_step UNIQUE (user_id, step)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_uos_user_id ON user_onboarding_state (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_uos_org_id ON user_onboarding_state (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_uos_status ON user_onboarding_state (status)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS file_communications (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            loan_id         INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            direction       VARCHAR(10) NOT NULL,
            channel         VARCHAR(20) NOT NULL,
            subject         TEXT,
            body            TEXT NOT NULL,
            body_html       TEXT,
            from_party      VARCHAR(320) NOT NULL,
            to_party        VARCHAR(320),
            ai_summary      TEXT,
            ai_draft_reply  TEXT,
            sentiment       VARCHAR(20),
            attachments     JSONB DEFAULT '[]',
            external_id     VARCHAR(255),
            thread_id       VARCHAR(255),
            read_by         JSONB DEFAULT '[]',
            call_duration   INTEGER,
            recording_url   TEXT,
            transcript      TEXT,
            is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fc_loan_id ON file_communications (loan_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fc_org_id ON file_communications (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fc_channel ON file_communications (channel)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fc_created ON file_communications (created_at)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS communication_participants (
            id              SERIAL PRIMARY KEY,
            loan_id         INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            notify          BOOLEAN NOT NULL DEFAULT TRUE,
            notify_sms      BOOLEAN NOT NULL DEFAULT TRUE,
            notify_email    BOOLEAN NOT NULL DEFAULT TRUE,
            notify_push     BOOLEAN NOT NULL DEFAULT TRUE,
            last_read_at    TIMESTAMPTZ,
            unread_count    INTEGER NOT NULL DEFAULT 0,
            role            VARCHAR(50),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_comm_participant UNIQUE (loan_id, user_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cp_loan_id ON communication_participants (loan_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cp_user_id ON communication_participants (user_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS vendors (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name            VARCHAR(255) NOT NULL,
            vendor_type     VARCHAR(50) NOT NULL,
            contact_name    VARCHAR(255),
            contact_email   VARCHAR(320),
            contact_phone   VARCHAR(20),
            website         VARCHAR(512),
            address_line1   VARCHAR(255),
            address_line2   VARCHAR(255),
            city            VARCHAR(100),
            state           VARCHAR(2),
            zip_code        VARCHAR(10),
            avg_turnaround_days NUMERIC(6,2),
            on_time_pct     NUMERIC(5,2),
            total_orders    INTEGER NOT NULL DEFAULT 0,
            total_completed INTEGER NOT NULL DEFAULT 0,
            total_late      INTEGER NOT NULL DEFAULT 0,
            quality_rating  NUMERIC(3,2),
            is_preferred    BOOLEAN NOT NULL DEFAULT FALSE,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            license_number  VARCHAR(100),
            license_expiry  DATE,
            insurance_expiry DATE,
            internal_notes  TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_vendor_org_name_type UNIQUE (organization_id, name, vendor_type)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vendors_org_id ON vendors (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vendors_type ON vendors (vendor_type)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS vendor_orders (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            vendor_id       INTEGER NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
            loan_id         INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
            order_type      VARCHAR(50) NOT NULL,
            order_number    VARCHAR(100),
            status          VARCHAR(30) NOT NULL DEFAULT 'ordered',
            ordered_by      INTEGER REFERENCES users(id),
            ordered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            due_date        DATE,
            received_at     TIMESTAMPTZ,
            is_late         BOOLEAN NOT NULL DEFAULT FALSE,
            turnaround_days NUMERIC(6,2),
            fee             NUMERIC(10,2),
            paid            BOOLEAN NOT NULL DEFAULT FALSE,
            paid_at         TIMESTAMPTZ,
            result_summary  TEXT,
            result_document_id INTEGER,
            revision_count  INTEGER NOT NULL DEFAULT 0,
            internal_notes  TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vo_org_id ON vendor_orders (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vo_loan_id ON vendor_orders (loan_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_context_store (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scope           TEXT NOT NULL,
            scope_id        TEXT NOT NULL,
            context_key     TEXT NOT NULL,
            context_value   JSONB NOT NULL,
            source          TEXT NOT NULL,
            confidence      NUMERIC(4,3),
            version         INTEGER NOT NULL DEFAULT 1,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_agent_ctx_scope_key UNIQUE (scope, scope_id, context_key)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_context_events (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id        TEXT NOT NULL,
            user_id         INTEGER REFERENCES users(id),
            organization_id INTEGER REFERENCES organizations(id),
            loan_id         INTEGER REFERENCES loans(id),
            event_type      TEXT NOT NULL,
            original_output JSONB,
            corrected_value JSONB,
            rationale       TEXT,
            agent_run_id    UUID,
            processed       BOOLEAN NOT NULL DEFAULT FALSE,
            processed_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ace_agent ON agent_context_events (agent_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ace_unprocessed ON agent_context_events (processed, created_at) WHERE processed = FALSE"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS context_change_audit (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scope           TEXT NOT NULL,
            scope_id        TEXT NOT NULL,
            context_key     TEXT,
            previous_value  JSONB,
            new_value       JSONB,
            change_source   TEXT NOT NULL,
            triggered_by    TEXT,
            from_version    INTEGER,
            to_version      INTEGER,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS harness_change_proposals (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id        TEXT NOT NULL,
            analysis_summary JSONB NOT NULL,
            proposed_changes JSONB NOT NULL,
            status          VARCHAR(30) NOT NULL DEFAULT 'pending_review',
            reviewed_by     INTEGER REFERENCES users(id),
            reviewed_at     TIMESTAMPTZ,
            review_notes    TEXT,
            gym_tested      BOOLEAN NOT NULL DEFAULT FALSE,
            gym_passed      BOOLEAN,
            gym_scores      JSONB,
            gym_tested_at   TIMESTAMPTZ,
            deployed_at     TIMESTAMPTZ,
            deployed_version VARCHAR(20),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_registry (
            agent_id            TEXT PRIMARY KEY,
            display_name        TEXT NOT NULL,
            version             TEXT NOT NULL DEFAULT '1.0.0',
            category            TEXT NOT NULL,
            capabilities        TEXT[] NOT NULL DEFAULT '{}',
            required_permissions TEXT[] NOT NULL DEFAULT '{}',
            trigger_events      TEXT[] DEFAULT '{}',
            max_retries         INTEGER NOT NULL DEFAULT 3,
            timeout_seconds     INTEGER NOT NULL DEFAULT 90,
            fallback_behavior   TEXT NOT NULL DEFAULT 'escalate',
            langgraph_graph     TEXT,
            is_active           BOOLEAN NOT NULL DEFAULT TRUE,
            gym_tested          BOOLEAN NOT NULL DEFAULT FALSE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ar_category ON agent_registry (category)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ar_active ON agent_registry (is_active)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_run_log (
            run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id        TEXT NOT NULL,
            loan_id         INTEGER REFERENCES loans(id),
            user_id         INTEGER REFERENCES users(id),
            organization_id INTEGER REFERENCES organizations(id),
            trigger_event   TEXT,
            input_snapshot  JSONB,
            output_snapshot JSONB,
            findings        JSONB,
            status          TEXT NOT NULL DEFAULT 'running',
            latency_ms      INTEGER,
            input_tokens    INTEGER,
            output_tokens   INTEGER,
            error_message   TEXT,
            retry_count     INTEGER NOT NULL DEFAULT 0,
            started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at    TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_arl_agent ON agent_run_log (agent_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_arl_org ON agent_run_log (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_arl_started ON agent_run_log (started_at)"
    )

    # =========================================================================
    # SECTION 18 — POS consent tables (credit_authorizations, econsent_agreements)
    # Source: migrations/add_pos_consent_tables.py
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS credit_authorizations (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(36) UNIQUE NOT NULL,
            application_id INTEGER NOT NULL REFERENCES borrower_applications(id),
            organization_id INTEGER REFERENCES organizations(id),
            authorized BOOLEAN NOT NULL DEFAULT FALSE,
            consent_text_version VARCHAR(50) NOT NULL,
            consent_text_hash VARCHAR(64) NOT NULL,
            typed_full_name VARCHAR(255) NOT NULL,
            ip_address VARCHAR(512) NOT NULL,
            user_agent VARCHAR(512) NOT NULL,
            authorized_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_credit_auth_application_id "
        "ON credit_authorizations (application_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_credit_auth_organization_id "
        "ON credit_authorizations (organization_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS econsent_agreements (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(36) UNIQUE NOT NULL,
            application_id INTEGER NOT NULL REFERENCES borrower_applications(id),
            organization_id INTEGER REFERENCES organizations(id),
            consented BOOLEAN NOT NULL DEFAULT FALSE,
            consent_text_version VARCHAR(50) NOT NULL,
            consent_text_hash VARCHAR(64) NOT NULL,
            typed_full_name VARCHAR(255) NOT NULL,
            hardware_software_requirements_shown TEXT NOT NULL,
            right_to_withdraw_shown TEXT NOT NULL,
            paper_copy_info_shown TEXT NOT NULL,
            ip_address VARCHAR(512) NOT NULL,
            user_agent VARCHAR(512) NOT NULL,
            consented_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_econsent_application_id "
        "ON econsent_agreements (application_id)"
    )

    # borrower_applications missing columns from POS consent migration
    _ba_columns = [
        ("voice_completed_at", "TIMESTAMP WITH TIME ZONE"),
        ("voice_loan_id", "VARCHAR(255)"),
        ("consent_sms_sent_at", "TIMESTAMP WITH TIME ZONE"),
        ("consent_reminder_count", "INTEGER DEFAULT 0"),
        ("ssn_encrypted", "TEXT"),
        ("co_ssn_encrypted", "TEXT"),
        ("prequalification_data", "JSON"),
        ("device_info", "JSON"),
        ("applicant_ethnicity", "TEXT"),
        ("applicant_race", "TEXT"),
        ("applicant_sex", "TEXT"),
        ("applicant_age", "INTEGER"),
        ("co_applicant_ethnicity", "TEXT"),
        ("co_applicant_race", "TEXT"),
        ("co_applicant_sex", "TEXT"),
        ("co_applicant_age", "INTEGER"),
        ("gmi_collection_method", "VARCHAR"),
        ("gmi_collected_at", "TIMESTAMP WITH TIME ZONE"),
    ]
    for col_name, col_type in _ba_columns:
        op.execute(
            f"ALTER TABLE borrower_applications ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    # =========================================================================
    # SECTION 19 — application_events table + sms_messages / notifications cols
    # Source: migrations/add_application_events_table.py
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS application_events (
            id SERIAL PRIMARY KEY,
            application_id INTEGER NOT NULL REFERENCES borrower_applications(id) ON DELETE CASCADE,
            event_type VARCHAR NOT NULL,
            event_data JSONB DEFAULT '{}',
            actor_type VARCHAR,
            actor_email VARCHAR,
            step VARCHAR,
            ip_address VARCHAR,
            user_agent VARCHAR,
            device_type VARCHAR,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_app_event_application "
        "ON application_events (application_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_app_event_type "
        "ON application_events (event_type)"
    )

    _sms_msg_columns = [
        ("consent_record_id", "INTEGER"),
        ("consent_verified_at", "TIMESTAMP WITH TIME ZONE"),
        ("consent_method", "VARCHAR(50)"),
        ("delivery_status", "VARCHAR(30) DEFAULT 'queued'"),
    ]
    for col_name, col_type in _sms_msg_columns:
        op.execute(
            f"ALTER TABLE sms_messages ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    op.execute(
        "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS organization_id INTEGER"
    )

    # =========================================================================
    # SECTION 20 — autonomous_agent_runs table
    # Source: migrations/add_autonomous_agent_runs.py
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_agent_runs (
            id SERIAL PRIMARY KEY,
            agent_name VARCHAR(100) NOT NULL,
            organization_id INTEGER REFERENCES organizations(id),
            started_at TIMESTAMP WITH TIME ZONE NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            success BOOLEAN DEFAULT FALSE,
            actions_taken INTEGER DEFAULT 0,
            notifications_sent INTEGER DEFAULT 0,
            error TEXT,
            summary TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_name_org "
        "ON autonomous_agent_runs (agent_name, organization_id, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_started "
        "ON autonomous_agent_runs (started_at DESC)"
    )

    # =========================================================================
    # SECTION 21 — oauth_tokens unified table
    # Source: migrations/consolidate_oauth_tokens.py
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL,
            access_token TEXT,
            refresh_token TEXT,
            token_expires_at TIMESTAMP WITH TIME ZONE,
            scopes VARCHAR(1000),
            email_address VARCHAR(255),
            instance_url VARCHAR(500),
            external_org_id VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE,
            status VARCHAR(50) DEFAULT 'connected',
            last_error TEXT,
            sync_enabled BOOLEAN DEFAULT TRUE,
            sync_folder VARCHAR(255),
            sync_frequency_minutes INTEGER DEFAULT 15,
            last_sync_at TIMESTAMP WITH TIME ZONE,
            provider_config JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_oauth_user_org_provider "
        "ON oauth_tokens (user_id, organization_id, provider)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_oauth_user_provider "
        "ON oauth_tokens (user_id, provider)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_oauth_org_provider "
        "ON oauth_tokens (organization_id, provider)"
    )

    # =========================================================================
    # SECTION 22 — call_intelligence_results + application_audit_logs tables
    # Source: migrations/add_call_intelligence_columns.py
    # =========================================================================
    # vapi_calls CI columns
    _vapi_ci_columns = [
        ("ci_processed", "BOOLEAN DEFAULT FALSE"),
        ("ci_extractions_count", "INTEGER DEFAULT 0"),
        ("ci_tasks_created", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in _vapi_ci_columns:
        op.execute(
            f"ALTER TABLE vapi_calls ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    op.execute("""
        CREATE TABLE IF NOT EXISTS call_intelligence_results (
            id SERIAL PRIMARY KEY,
            call_id VARCHAR(255) UNIQUE NOT NULL,
            loan_id INTEGER,
            organization_id INTEGER NOT NULL,
            extractions JSONB DEFAULT '{}',
            total_extractions INTEGER DEFAULT 0,
            high_confidence_count INTEGER DEFAULT 0,
            low_confidence_count INTEGER DEFAULT 0,
            processing_time_ms INTEGER,
            application_status VARCHAR(50),
            application_completion FLOAT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ci_results_call_id "
        "ON call_intelligence_results (call_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ci_results_org "
        "ON call_intelligence_results (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ci_results_loan "
        "ON call_intelligence_results (loan_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS application_audit_logs (
            id SERIAL PRIMARY KEY,
            loan_id INTEGER,
            overall_status VARCHAR(50),
            overall_completion FLOAT,
            total_fields INTEGER DEFAULT 0,
            complete_fields INTEGER DEFAULT 0,
            missing_fields INTEGER DEFAULT 0,
            tasks_generated INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # =========================================================================
    # SECTION 23 — voice_workflows table
    # Source: migrations/add_voice_workflows_table.py
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS voice_workflows (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            workflow_type VARCHAR(50) NOT NULL,
            state VARCHAR(30) NOT NULL DEFAULT 'initiated',
            contact_name VARCHAR(255),
            contact_phone VARCHAR(20),
            contact_email VARCHAR(255),
            lead_id INTEGER,
            meeting_type VARCHAR(50) DEFAULT 'discovery_call',
            meeting_duration_minutes INTEGER DEFAULT 30,
            message_context TEXT,
            conversation_history JSONB NOT NULL DEFAULT '[]',
            turn_count INTEGER DEFAULT 0,
            max_turns INTEGER DEFAULT 8,
            confirmed_datetime TIMESTAMP,
            appointment_id INTEGER,
            proposed_slots JSONB DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT,
            last_sms_sent_at TIMESTAMP,
            last_sms_received_at TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_organization_id "
        "ON voice_workflows (organization_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_user_id "
        "ON voice_workflows (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_voice_workflows_contact_phone "
        "ON voice_workflows (contact_phone)"
    )

    # =========================================================================
    # SECTION 24 — sms_ai_confidence columns
    # Source: _run_critical_schema_migrations (inline alters)
    # =========================================================================
    _sms_conf_columns = [
        ("total_recommendations", "INTEGER DEFAULT 0"),
        ("confidence_score", "FLOAT DEFAULT 20.0"),
        ("auto_respond_threshold", "FLOAT DEFAULT 80.0"),
        ("created_at", "TIMESTAMPTZ DEFAULT NOW()"),
        ("user_id", "INTEGER"),
        ("accepted_count", "INTEGER DEFAULT 0"),
        ("edited_count", "INTEGER DEFAULT 0"),
        ("rejected_count", "INTEGER DEFAULT 0"),
        ("auto_respond_enabled", "BOOLEAN DEFAULT FALSE"),
        ("updated_at", "TIMESTAMPTZ DEFAULT NOW()"),
    ]
    for col_name, col_type in _sms_conf_columns:
        op.execute(
            f"ALTER TABLE sms_ai_confidence ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sms_ai_conf_org_user_cat
        ON sms_ai_confidence (organization_id, COALESCE(user_id, 0), category)
    """)

    # =========================================================================
    # SECTION 25 — sms_response_patterns columns
    # Source: _run_critical_schema_migrations (inline alters)
    # =========================================================================
    _srp_columns = [
        ("times_used", "INTEGER DEFAULT 1"),
        ("times_accepted", "INTEGER DEFAULT 0"),
        ("times_edited", "INTEGER DEFAULT 0"),
        ("times_rejected", "INTEGER DEFAULT 0"),
        ("message_keywords", "JSONB"),
        ("last_used_at", "TIMESTAMPTZ"),
        ("created_by_user_id", "INTEGER"),
    ]
    for col_name, col_type in _srp_columns:
        op.execute(
            f"ALTER TABLE sms_response_patterns ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sms_patterns_org_cat_template
        ON sms_response_patterns (organization_id, category, md5(response_template))
    """)

    # =========================================================================
    # SECTION 26 — workflow_task_instances retry columns + health_status conversion
    # Source: _run_critical_schema_migrations (inline alters)
    # =========================================================================
    op.execute(
        "ALTER TABLE workflow_task_instances "
        "ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE workflow_task_instances "
        "ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMP"
    )
    # Convert health_status enum → VARCHAR if it's USER-DEFINED
    op.execute("""
        DO $$
        DECLARE
            col_data_type TEXT;
        BEGIN
            SELECT data_type INTO col_data_type
            FROM information_schema.columns
            WHERE table_name = 'workflow_task_instances'
              AND column_name = 'health_status';
            IF col_data_type = 'USER-DEFINED' THEN
                ALTER TABLE workflow_task_instances
                ALTER COLUMN health_status TYPE VARCHAR(50)
                USING health_status::text;
            END IF;
        END $$;
    """)

    # =========================================================================
    # SECTION 27 — workflow_task_alerts table
    # Source: _run_critical_schema_migrations (inline CREATE TABLE)
    # =========================================================================
    op.execute("""
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
    """)

    # =========================================================================
    # SECTION 28 — SOC2 table tenant_id type conversions
    # Source: _run_critical_schema_migrations (inline alters)
    # These convert UUID → VARCHAR(50) if the column is currently UUID type.
    # =========================================================================
    for _soc2_table in [
        "soc2_audit_log",
        "soc2_auth_events",
        "soc2_security_incident",
        "soc2_data_access_log",
        "soc2_change_management",
    ]:
        op.execute(f"""
            DO $$
            DECLARE
                col_data_type TEXT;
            BEGIN
                SELECT data_type INTO col_data_type
                FROM information_schema.columns
                WHERE table_name = '{_soc2_table}'
                  AND column_name = 'tenant_id';
                IF col_data_type = 'uuid' THEN
                    ALTER TABLE {_soc2_table}
                    ALTER COLUMN tenant_id TYPE VARCHAR(50)
                    USING tenant_id::text;
                END IF;
            END $$;
        """)

    # =========================================================================
    # SECTION 29 — ai_colleague_actions organization_id column
    # Source: _run_critical_schema_migrations (inline alter)
    # =========================================================================
    op.execute(
        "ALTER TABLE ai_colleague_actions "
        "ADD COLUMN IF NOT EXISTS organization_id INTEGER"
    )

    # =========================================================================
    # SECTION 30 — verified_caller_ids + agent_telephony_settings + call_logs
    # Source: _run_critical_schema_migrations (inline alters)
    # =========================================================================
    _vcid_columns = [
        ("provider_sid", "VARCHAR"),
        ("verified_at", "TIMESTAMP"),
        ("organization_id", "INTEGER"),
        ("user_id", "INTEGER REFERENCES users(id)"),
    ]
    for col_name, col_type in _vcid_columns:
        op.execute(
            f"ALTER TABLE verified_caller_ids ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
        )

    op.execute(
        "ALTER TABLE agent_telephony_settings "
        "ADD COLUMN IF NOT EXISTS organization_id INTEGER"
    )

    op.execute(
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS organization_id INTEGER"
    )

    # =========================================================================
    # SECTION 31 — video_meeting_rooms and meeting_recordings Chime columns
    # Source: _run_critical_schema_migrations (Chime SDK migration)
    # =========================================================================
    op.execute(
        "ALTER TABLE video_meeting_rooms "
        "ADD COLUMN IF NOT EXISTS chime_meeting_id VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE video_meeting_rooms "
        "ADD COLUMN IF NOT EXISTS chime_media_region VARCHAR(50) DEFAULT 'us-east-1'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_video_meeting_rooms_chime_meeting_id "
        "ON video_meeting_rooms (chime_meeting_id)"
    )
    op.execute(
        "ALTER TABLE meeting_recordings "
        "ADD COLUMN IF NOT EXISTS chime_pipeline_id VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE meeting_recordings "
        "ADD COLUMN IF NOT EXISTS s3_key VARCHAR(1000)"
    )

    # =========================================================================
    # SECTION 32 — vapi_calls table (if not already created by 001 migration)
    # Source: migrations/add_vapi_tables.py — the base vapi_calls table
    # The 001_telephony_tables Alembic migration may already handle this;
    # CREATE TABLE IF NOT EXISTS is safe either way.
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS vapi_calls (
            id SERIAL PRIMARY KEY,
            vapi_call_id VARCHAR(255) UNIQUE NOT NULL,
            phone_number VARCHAR(20),
            caller_name VARCHAR(255),
            direction VARCHAR(20),
            status VARCHAR(50),
            started_at TIMESTAMP WITH TIME ZONE,
            ended_at TIMESTAMP WITH TIME ZONE,
            duration INTEGER,
            transcript TEXT,
            summary TEXT,
            recording_url VARCHAR(512),
            sentiment VARCHAR(50),
            intent VARCHAR(100),
            language VARCHAR(10) DEFAULT 'en',
            call_metadata JSON,
            vapi_raw_data JSON,
            lead_id INTEGER REFERENCES leads(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)


def downgrade() -> None:
    # These are all additive migrations; downgrade is intentionally a no-op.
    # Removing columns from production is a separate, manual decision.
    pass
