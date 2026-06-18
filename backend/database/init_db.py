"""
Database Initialization & Schema Migrations

Extracted from inline_legacy_routes.py.
Handles table creation, schema migrations (ALTER TABLE ADD COLUMN),
enum type updates, and sample data creation.

========================================================================
DEPRECATION NOTICE (2026-05-27)
========================================================================
The raw SQL ALTER TABLE / CREATE TABLE IF NOT EXISTS statements in this
file are LEGACY.  New schema changes MUST go through Alembic migrations
in backend/alembic/versions/.

Set SKIP_LEGACY_MIGRATIONS=true to bypass ALL raw SQL in init_db() once
Alembic is fully managing the schema.  This env-var acts as the kill
switch for the legacy migration path.
========================================================================
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# These are set by init_module() before init_db() is called
_engine = None
_Base = None
_DATABASE_URL = ""
_ENVIRONMENT = ""


def init_module(engine, Base, database_url: str = "", environment: str = ""):
    """Initialize module with database dependencies."""
    global _engine, _Base, _DATABASE_URL, _ENVIRONMENT
    _engine = engine
    _Base = Base
    _DATABASE_URL = database_url
    _ENVIRONMENT = environment


_AUTO_CREATE_TABLES = os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true"


def init_db():
    """
    Initialize database tables.

    In production (_ENVIRONMENT=production), this skips Base.metadata.create_all()
    to prevent accidental schema changes. Use Alembic migrations instead.

    Set _AUTO_CREATE_TABLES=true to force table creation (development only).
    """
    try:
        # Import models to register them with _Base before create_all
        import salesforce_integration_models  # Salesforce integration tables

        # Skip auto-create in production unless explicitly enabled
        if _ENVIRONMENT == "production" and not _AUTO_CREATE_TABLES:
            logger.info("Skipping Base.metadata.create_all() in production - use Alembic migrations")
        else:
            _Base.metadata.create_all(bind=_engine)
            logger.info("Database tables created successfully")

        # ── Legacy migration kill-switch ────────────────────────────────
        # When SKIP_LEGACY_MIGRATIONS=true, all raw SQL below is skipped.
        # Enable this once Alembic fully owns the schema.
        if os.getenv("SKIP_LEGACY_MIGRATIONS", "").lower() in ("true", "1", "yes"):
            logger.info(
                "SKIP_LEGACY_MIGRATIONS is set — skipping all legacy raw SQL migrations in init_db(). "
                "Schema is managed by Alembic (backend/alembic/versions/)."
            )
            return True

        # ================================================================
        # LEGACY RAW SQL MIGRATIONS (deprecated — use Alembic instead)
        # ================================================================

        # Explicitly create Salesforce integration tables if they don't exist
        # Use individual transactions for each table to ensure partial success
        try:
            with _engine.connect() as conn:
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
                logger.info("✅ integration_profiles table created/verified")
        except Exception as e:
            logger.warning(f"integration_profiles table creation: {e}")

        try:
            with _engine.connect() as conn:
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
                logger.info("✅ oauth_states table created/verified")
        except Exception as e:
            logger.warning(f"oauth_states table creation: {e}")

        # Create oauth_pkce_store table for PKCE verifier storage
        try:
            with _engine.connect() as conn:
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
                logger.info("✅ oauth_pkce_store table created/verified")
        except Exception as e:
            logger.warning(f"oauth_pkce_store table creation: {e}")

        # Run schema migrations for existing tables (PostgreSQL only)
        # Note: SQLite tables are already created with all columns via Base.metadata.create_all()
        try:
            # Only run PostgreSQL-specific migrations if using PostgreSQL
            if not _DATABASE_URL.startswith("sqlite"):
                with _engine.connect() as conn:
                    # Add email_verified column if it doesn't exist
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='users' AND column_name='email_verified'
                            ) THEN
                                ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;
                            END IF;
                        END $$;
                    """))

                    # Add title column to users table if it doesn't exist (for job title/position)
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='users' AND column_name='title'
                            ) THEN
                                ALTER TABLE users ADD COLUMN title TEXT;
                            END IF;
                        END $$;
                    """))

                    # Add company_logo_url column to users table if it doesn't exist
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='users' AND column_name='company_logo_url'
                            ) THEN
                                ALTER TABLE users ADD COLUMN company_logo_url TEXT;
                            END IF;
                        END $$;
                    """))

                    # Add headshot_url column to users table if it doesn't exist
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='users' AND column_name='headshot_url'
                            ) THEN
                                ALTER TABLE users ADD COLUMN headshot_url TEXT;
                            END IF;
                        END $$;
                    """))

                    # Add team_name column to users table if it doesn't exist
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='users' AND column_name='team_name'
                            ) THEN
                                ALTER TABLE users ADD COLUMN team_name TEXT;
                            END IF;
                        END $$;
                    """))

                    conn.commit()
                    logger.info("✅ User profile columns added/verified")

                    # Add new Lead columns if they don't exist
                    conn.execute(text("""
                        DO $$
                    BEGIN
                        -- Property Information
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='address') THEN
                            ALTER TABLE leads ADD COLUMN address VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='city') THEN
                            ALTER TABLE leads ADD COLUMN city VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='state') THEN
                            ALTER TABLE leads ADD COLUMN state VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='zip_code') THEN
                            ALTER TABLE leads ADD COLUMN zip_code VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_type') THEN
                            ALTER TABLE leads ADD COLUMN property_type VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_value') THEN
                            ALTER TABLE leads ADD COLUMN property_value FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='down_payment') THEN
                            ALTER TABLE leads ADD COLUMN down_payment FLOAT;
                        END IF;
                        -- Financial Information
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employment_status') THEN
                            ALTER TABLE leads ADD COLUMN employment_status VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='annual_income') THEN
                            ALTER TABLE leads ADD COLUMN annual_income FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='monthly_debts') THEN
                            ALTER TABLE leads ADD COLUMN monthly_debts FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='first_time_buyer') THEN
                            ALTER TABLE leads ADD COLUMN first_time_buyer BOOLEAN DEFAULT FALSE;
                        END IF;
                        -- Loan Information
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_number') THEN
                            ALTER TABLE leads ADD COLUMN loan_number VARCHAR;
                        END IF;
                        -- Loan Details
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_amount') THEN
                            ALTER TABLE leads ADD COLUMN loan_amount FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='interest_rate') THEN
                            ALTER TABLE leads ADD COLUMN interest_rate FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_term') THEN
                            ALTER TABLE leads ADD COLUMN loan_term INTEGER;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='apr') THEN
                            ALTER TABLE leads ADD COLUMN apr FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='points') THEN
                            ALTER TABLE leads ADD COLUMN points FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_date') THEN
                            ALTER TABLE leads ADD COLUMN lock_date TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_expiration') THEN
                            ALTER TABLE leads ADD COLUMN lock_expiration TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='closing_date') THEN
                            ALTER TABLE leads ADD COLUMN closing_date TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lender') THEN
                            ALTER TABLE leads ADD COLUMN lender VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_officer') THEN
                            ALTER TABLE leads ADD COLUMN loan_officer VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='processor') THEN
                            ALTER TABLE leads ADD COLUMN processor VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='underwriter') THEN
                            ALTER TABLE leads ADD COLUMN underwriter VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='appraisal_value') THEN
                            ALTER TABLE leads ADD COLUMN appraisal_value FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='ltv') THEN
                            ALTER TABLE leads ADD COLUMN ltv FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='dti') THEN
                            ALTER TABLE leads ADD COLUMN dti FLOAT;
                        END IF;
                        -- Lead tracking date columns
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='application_started_date') THEN
                            ALTER TABLE leads ADD COLUMN application_started_date TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='application_completed_date') THEN
                            ALTER TABLE leads ADD COLUMN application_completed_date TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='credit_pulled_date') THEN
                            ALTER TABLE leads ADD COLUMN credit_pulled_date TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='preapproval_issued_date') THEN
                            ALTER TABLE leads ADD COLUMN preapproval_issued_date TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_address') THEN
                            ALTER TABLE leads ADD COLUMN property_address VARCHAR;
                        END IF;
                        -- Buying timeline and risk profile (enum as VARCHAR for flexibility)
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='buying_timeline_category') THEN
                            ALTER TABLE leads ADD COLUMN buying_timeline_category VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='borrower_risk_profile') THEN
                            ALTER TABLE leads ADD COLUMN borrower_risk_profile VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='target_payment') THEN
                            ALTER TABLE leads ADD COLUMN target_payment FLOAT;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='expected_purchase_date') THEN
                            ALTER TABLE leads ADD COLUMN expected_purchase_date TIMESTAMP;
                        END IF;
                        -- Referral scoring columns
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='referral_score') THEN
                            ALTER TABLE leads ADD COLUMN referral_score INTEGER DEFAULT 0;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='referral_source_score') THEN
                            ALTER TABLE leads ADD COLUMN referral_source_score INTEGER DEFAULT 0;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employment_referral_flag') THEN
                            ALTER TABLE leads ADD COLUMN employment_referral_flag BOOLEAN DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='manager_flag') THEN
                            ALTER TABLE leads ADD COLUMN manager_flag BOOLEAN DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employees_managed') THEN
                            ALTER TABLE leads ADD COLUMN employees_managed INTEGER;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='leadership_level') THEN
                            ALTER TABLE leads ADD COLUMN leadership_level VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='company_size') THEN
                            ALTER TABLE leads ADD COLUMN company_size VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employer_name') THEN
                            ALTER TABLE leads ADD COLUMN employer_name VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='industry') THEN
                            ALTER TABLE leads ADD COLUMN industry VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='circle_of_cash_flow_map') THEN
                            ALTER TABLE leads ADD COLUMN circle_of_cash_flow_map JSON;
                        END IF;
                        -- Workflow columns
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='current_workflow_id') THEN
                            ALTER TABLE leads ADD COLUMN current_workflow_id INTEGER;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='workflow_day') THEN
                            ALTER TABLE leads ADD COLUMN workflow_day INTEGER DEFAULT 0;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='last_workflow_action') THEN
                            ALTER TABLE leads ADD COLUMN last_workflow_action TIMESTAMP;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='nurture_month') THEN
                            ALTER TABLE leads ADD COLUMN nurture_month INTEGER DEFAULT 0;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='user_metadata') THEN
                            ALTER TABLE leads ADD COLUMN user_metadata JSON;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='initial_consultation_date') THEN
                            ALTER TABLE leads ADD COLUMN initial_consultation_date TIMESTAMP;
                        END IF;
                        -- Salesforce Sync - Financial
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='origination_fee') THEN
                            ALTER TABLE leads ADD COLUMN origination_fee NUMERIC(18,2);
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='estimated_prepaid_interest') THEN
                            ALTER TABLE leads ADD COLUMN estimated_prepaid_interest NUMERIC(18,2);
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='index_rate') THEN
                            ALTER TABLE leads ADD COLUMN index_rate NUMERIC(8,4);
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='margin') THEN
                            ALTER TABLE leads ADD COLUMN margin NUMERIC(8,4);
                        END IF;
                        -- Salesforce Sync - LTV/Purpose
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_purpose') THEN
                            ALTER TABLE leads ADD COLUMN loan_purpose VARCHAR;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='file_state') THEN
                            ALTER TABLE leads ADD COLUMN file_state VARCHAR;
                        END IF;
                        -- Salesforce Sync - 2nd Loan
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='second_loan_amount') THEN
                            ALTER TABLE leads ADD COLUMN second_loan_amount NUMERIC(18,2);
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='second_loan_rate') THEN
                            ALTER TABLE leads ADD COLUMN second_loan_rate NUMERIC(8,4);
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='second_loan_payment') THEN
                            ALTER TABLE leads ADD COLUMN second_loan_payment NUMERIC(18,2);
                        END IF;
                        -- Salesforce Sync - Housing Expenses
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='present_housing_expense') THEN
                            ALTER TABLE leads ADD COLUMN present_housing_expense NUMERIC(18,2);
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='proposed_housing_expense') THEN
                            ALTER TABLE leads ADD COLUMN proposed_housing_expense NUMERIC(18,2);
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='present_monthly_payment') THEN
                            ALTER TABLE leads ADD COLUMN present_monthly_payment NUMERIC(18,2);
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='proposed_monthly_payment') THEN
                            ALTER TABLE leads ADD COLUMN proposed_monthly_payment NUMERIC(18,2);
                        END IF;
                        -- Marketing
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='receive_marketing') THEN
                            ALTER TABLE leads ADD COLUMN receive_marketing BOOLEAN DEFAULT FALSE;
                        END IF;
                    END $$;
                    """))

                    # Add FUB integration columns to leads table
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='fub_person_id') THEN
                                ALTER TABLE leads ADD COLUMN fub_person_id INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='fub_last_synced_at') THEN
                                ALTER TABLE leads ADD COLUMN fub_last_synced_at TIMESTAMP WITH TIME ZONE;
                            END IF;
                        END $$;
                    """))

                    # Add email_intake_id to tasks table for document intake
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='email_intake_id') THEN
                                ALTER TABLE tasks ADD COLUMN email_intake_id INTEGER;
                            END IF;
                        END $$;
                    """))

                    # Add SF disposition columns to tasks table
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='sf_proposed_stage') THEN
                                ALTER TABLE tasks ADD COLUMN sf_proposed_stage VARCHAR(50);
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='sf_current_stage') THEN
                                ALTER TABLE tasks ADD COLUMN sf_current_stage VARCHAR(50);
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='sf_raw_stage') THEN
                                ALTER TABLE tasks ADD COLUMN sf_raw_stage VARCHAR(200);
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='disposition_action') THEN
                                ALTER TABLE tasks ADD COLUMN disposition_action VARCHAR(20);
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='disposition_date') THEN
                                ALTER TABLE tasks ADD COLUMN disposition_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='disposition_by') THEN
                                ALTER TABLE tasks ADD COLUMN disposition_by INTEGER;
                            END IF;
                        END $$;
                    """))

                    # Create email_intakes table for document intake
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

                    # Create attachment_intakes table
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

                    # Create classified_documents table
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

                    # Add new Loan columns for rate lock intelligence, appraisal, etc.
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            -- Appraisal tracking columns
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='appraisal_ordered_date') THEN
                                ALTER TABLE loans ADD COLUMN appraisal_ordered_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='appraisal_scheduled_date') THEN
                                ALTER TABLE loans ADD COLUMN appraisal_scheduled_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='appraisal_completed_date') THEN
                                ALTER TABLE loans ADD COLUMN appraisal_completed_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='appraisal_value') THEN
                                ALTER TABLE loans ADD COLUMN appraisal_value FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_expiration_date') THEN
                                ALTER TABLE loans ADD COLUMN lock_expiration_date TIMESTAMP;
                            END IF;
                            -- Title & Insurance tracking columns
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='title_ordered_date') THEN
                                ALTER TABLE loans ADD COLUMN title_ordered_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='title_received_date') THEN
                                ALTER TABLE loans ADD COLUMN title_received_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='insurance_ordered_date') THEN
                                ALTER TABLE loans ADD COLUMN insurance_ordered_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='insurance_received_date') THEN
                                ALTER TABLE loans ADD COLUMN insurance_received_date TIMESTAMP;
                            END IF;
                            -- Rate Lock Intelligence columns
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='rate_lock_status') THEN
                                ALTER TABLE loans ADD COLUMN rate_lock_status VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='rate_lock_recommendation') THEN
                                ALTER TABLE loans ADD COLUMN rate_lock_recommendation VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_term_days') THEN
                                ALTER TABLE loans ADD COLUMN lock_term_days INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='float_down_available') THEN
                                ALTER TABLE loans ADD COLUMN float_down_available BOOLEAN DEFAULT FALSE;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='float_down_terms') THEN
                                ALTER TABLE loans ADD COLUMN float_down_terms VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='extension_cost_estimate') THEN
                                ALTER TABLE loans ADD COLUMN extension_cost_estimate FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='volatility_score') THEN
                                ALTER TABLE loans ADD COLUMN volatility_score INTEGER DEFAULT 50;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='borrower_risk_profile') THEN
                                ALTER TABLE loans ADD COLUMN borrower_risk_profile VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_score') THEN
                                ALTER TABLE loans ADD COLUMN lock_score INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_decision_date') THEN
                                ALTER TABLE loans ADD COLUMN lock_decision_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lock_decision_notes') THEN
                                ALTER TABLE loans ADD COLUMN lock_decision_notes TEXT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='last_rate_check') THEN
                                ALTER TABLE loans ADD COLUMN last_rate_check TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='rate_lock_history') THEN
                                ALTER TABLE loans ADD COLUMN rate_lock_history JSON;
                            END IF;
                            -- Property and workflow columns
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='property_city') THEN
                                ALTER TABLE loans ADD COLUMN property_city VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='property_state') THEN
                                ALTER TABLE loans ADD COLUMN property_state VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='property_zip') THEN
                                ALTER TABLE loans ADD COLUMN property_zip VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='lender') THEN
                                ALTER TABLE loans ADD COLUMN lender VARCHAR;
                            END IF;
                            -- Milestone dates
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='initial_disclosures_sent_date') THEN
                                ALTER TABLE loans ADD COLUMN initial_disclosures_sent_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='initial_disclosures_signed_date') THEN
                                ALTER TABLE loans ADD COLUMN initial_disclosures_signed_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='cd_received_signed_date') THEN
                                ALTER TABLE loans ADD COLUMN cd_received_signed_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='final_closing_package_sent_date') THEN
                                ALTER TABLE loans ADD COLUMN final_closing_package_sent_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='contract_received_date') THEN
                                ALTER TABLE loans ADD COLUMN contract_received_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='loan_estimate_sent_date') THEN
                                ALTER TABLE loans ADD COLUMN loan_estimate_sent_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='conditional_approval_date') THEN
                                ALTER TABLE loans ADD COLUMN conditional_approval_date TIMESTAMP;
                            END IF;
                            -- AMR tracking
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='last_amr_date') THEN
                                ALTER TABLE loans ADD COLUMN last_amr_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='next_amr_date') THEN
                                ALTER TABLE loans ADD COLUMN next_amr_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='refi_opportunity_score') THEN
                                ALTER TABLE loans ADD COLUMN refi_opportunity_score INTEGER;
                            END IF;
                            -- Workflow columns
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='current_workflow_id') THEN
                                ALTER TABLE loans ADD COLUMN current_workflow_id INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='last_workflow_action') THEN
                                ALTER TABLE loans ADD COLUMN last_workflow_action TIMESTAMP;
                            END IF;
                            -- Team member fields
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='loan_officer_name') THEN
                                ALTER TABLE loans ADD COLUMN loan_officer_name VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='loan_officer_email') THEN
                                ALTER TABLE loans ADD COLUMN loan_officer_email VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='processor_email') THEN
                                ALTER TABLE loans ADD COLUMN processor_email VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='underwriter_email') THEN
                                ALTER TABLE loans ADD COLUMN underwriter_email VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='closer') THEN
                                ALTER TABLE loans ADD COLUMN closer VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loans' AND column_name='closer_email') THEN
                                ALTER TABLE loans ADD COLUMN closer_email VARCHAR;
                            END IF;
                        END $$;
                    """))

                    # Create api_keys table if it doesn't exist
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

                    # Add missing columns to referral_partners table
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='name') THEN
                                ALTER TABLE referral_partners ADD COLUMN name VARCHAR NOT NULL DEFAULT 'Unknown';
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='company') THEN
                                ALTER TABLE referral_partners ADD COLUMN company VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='type') THEN
                                ALTER TABLE referral_partners ADD COLUMN type VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='phone') THEN
                                ALTER TABLE referral_partners ADD COLUMN phone VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='email') THEN
                                ALTER TABLE referral_partners ADD COLUMN email VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='referrals_in') THEN
                                ALTER TABLE referral_partners ADD COLUMN referrals_in INTEGER DEFAULT 0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='referrals_out') THEN
                                ALTER TABLE referral_partners ADD COLUMN referrals_out INTEGER DEFAULT 0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='closed_loans') THEN
                                ALTER TABLE referral_partners ADD COLUMN closed_loans INTEGER DEFAULT 0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='volume') THEN
                                ALTER TABLE referral_partners ADD COLUMN volume FLOAT DEFAULT 0.0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='reciprocity_score') THEN
                                ALTER TABLE referral_partners ADD COLUMN reciprocity_score FLOAT DEFAULT 0.0;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='status') THEN
                                ALTER TABLE referral_partners ADD COLUMN status VARCHAR DEFAULT 'active';
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='loyalty_tier') THEN
                                ALTER TABLE referral_partners ADD COLUMN loyalty_tier VARCHAR DEFAULT 'bronze';
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='last_interaction') THEN
                                ALTER TABLE referral_partners ADD COLUMN last_interaction TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='notes') THEN
                                ALTER TABLE referral_partners ADD COLUMN notes TEXT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='referral_partners' AND column_name='created_at') THEN
                                ALTER TABLE referral_partners ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                            END IF;
                        END $$;
                    """))

                    # Add missing columns to leads table
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='co_applicant_name') THEN
                                ALTER TABLE leads ADD COLUMN co_applicant_name VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='co_applicant_email') THEN
                                ALTER TABLE leads ADD COLUMN co_applicant_email VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='co_applicant_phone') THEN
                                ALTER TABLE leads ADD COLUMN co_applicant_phone VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_officer') THEN
                                ALTER TABLE leads ADD COLUMN loan_officer VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='processor') THEN
                                ALTER TABLE leads ADD COLUMN processor VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='underwriter') THEN
                                ALTER TABLE leads ADD COLUMN underwriter VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_number') THEN
                                ALTER TABLE leads ADD COLUMN loan_number VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lender') THEN
                                ALTER TABLE leads ADD COLUMN lender VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_date') THEN
                                ALTER TABLE leads ADD COLUMN lock_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='lock_expiration') THEN
                                ALTER TABLE leads ADD COLUMN lock_expiration TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='closing_date') THEN
                                ALTER TABLE leads ADD COLUMN closing_date TIMESTAMP;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='apr') THEN
                                ALTER TABLE leads ADD COLUMN apr FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='points') THEN
                                ALTER TABLE leads ADD COLUMN points FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='user_metadata') THEN
                                ALTER TABLE leads ADD COLUMN user_metadata JSON;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='address') THEN
                                ALTER TABLE leads ADD COLUMN address VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='city') THEN
                                ALTER TABLE leads ADD COLUMN city VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='state') THEN
                                ALTER TABLE leads ADD COLUMN state VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='zip_code') THEN
                                ALTER TABLE leads ADD COLUMN zip_code VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_type') THEN
                                ALTER TABLE leads ADD COLUMN property_type VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='property_value') THEN
                                ALTER TABLE leads ADD COLUMN property_value FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='down_payment') THEN
                                ALTER TABLE leads ADD COLUMN down_payment FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='employment_status') THEN
                                ALTER TABLE leads ADD COLUMN employment_status VARCHAR;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='annual_income') THEN
                                ALTER TABLE leads ADD COLUMN annual_income FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='monthly_debts') THEN
                                ALTER TABLE leads ADD COLUMN monthly_debts FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='first_time_buyer') THEN
                                ALTER TABLE leads ADD COLUMN first_time_buyer BOOLEAN DEFAULT FALSE;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_amount') THEN
                                ALTER TABLE leads ADD COLUMN loan_amount FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='interest_rate') THEN
                                ALTER TABLE leads ADD COLUMN interest_rate FLOAT;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='loan_term') THEN
                                ALTER TABLE leads ADD COLUMN loan_term INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='referral_partner_id') THEN
                                ALTER TABLE leads ADD COLUMN referral_partner_id INTEGER;
                            END IF;
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='leads' AND column_name='updated_at') THEN
                                ALTER TABLE leads ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                            END IF;
                        END $$;
                    """))

                    # Create user_permissions table if it doesn't exist
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

                    # Add all missing enum values to loanstage type
                    # Must use raw connection with autocommit - ALTER TYPE ADD VALUE cannot run in a transaction
                    try:
                        raw_conn = _engine.raw_connection()
                        raw_conn.set_isolation_level(0)  # AUTOCOMMIT
                        raw_cursor = raw_conn.cursor()
                        for loanstage_val in [
                            "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
                            "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
                            "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
                            "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
                            "CANCELLED", "DENIED", "DEAD", "NURTURE",
                            "WITHDRAWN", "DOES_NOT_QUALIFY", "Docs Out",
                        ]:
                            try:
                                raw_cursor.execute(f"ALTER TYPE loanstage ADD VALUE IF NOT EXISTS '{loanstage_val}'")
                            except Exception as e:
                                logger.exception(f"Failed to add loanstage enum value '{loanstage_val}': {e}")
                        raw_cursor.close()
                        raw_conn.close()
                        logger.info("✅ Ensured all loanstage enum values exist")
                    except Exception as enum_e:
                        logger.warning(f"⚠️ loanstage enum migration: {enum_e}")

                    # Add role_responsibilities column for dynamic workflow roles
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='workflow_day_configs' AND column_name='role_responsibilities'
                            ) THEN
                                ALTER TABLE workflow_day_configs ADD COLUMN role_responsibilities JSONB DEFAULT '{}'::jsonb;
                            END IF;
                        END $$;
                    """))

                    # Add role_id column to workflow_role_assignments for dynamic roles
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='workflow_role_assignments' AND column_name='role_id'
                            ) THEN
                                ALTER TABLE workflow_role_assignments ADD COLUMN role_id INTEGER REFERENCES onboarding_roles(id);
                            END IF;
                        END $$;
                    """))

                    # Make the legacy 'role' column nullable for dynamic role support
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            ALTER TABLE workflow_role_assignments ALTER COLUMN role DROP NOT NULL;
                        EXCEPTION
                            WHEN others THEN NULL;
                        END $$;
                    """))

                    # Add AM/PM communication method columns for Lead Purchase workflow
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            -- Add phone_am_enabled column
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='workflow_day_configs' AND column_name='phone_am_enabled'
                            ) THEN
                                ALTER TABLE workflow_day_configs ADD COLUMN phone_am_enabled BOOLEAN DEFAULT FALSE;
                            END IF;
                            -- Add phone_pm_enabled column
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='workflow_day_configs' AND column_name='phone_pm_enabled'
                            ) THEN
                                ALTER TABLE workflow_day_configs ADD COLUMN phone_pm_enabled BOOLEAN DEFAULT FALSE;
                            END IF;
                            -- Add text_am_enabled column
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='workflow_day_configs' AND column_name='text_am_enabled'
                            ) THEN
                                ALTER TABLE workflow_day_configs ADD COLUMN text_am_enabled BOOLEAN DEFAULT FALSE;
                            END IF;
                            -- Add text_pm_enabled column
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name='workflow_day_configs' AND column_name='text_pm_enabled'
                            ) THEN
                                ALTER TABLE workflow_day_configs ADD COLUMN text_pm_enabled BOOLEAN DEFAULT FALSE;
                            END IF;
                        END $$;
                    """))

                    conn.commit()
                    logger.info("✅ Schema migrations applied (PostgreSQL)")

                    # Create telephony tables if they don't exist
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
                            organization_id INTEGER,
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
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS organization_id INTEGER;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS referral_partner_id INTEGER;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS mum_client_id INTEGER;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_id INTEGER;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS session_task_id INTEGER;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS caller_id_used VARCHAR;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS start_time TIMESTAMP;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS end_time TIMESTAMP;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS failure_reason VARCHAR;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                        -- Recording fields for call_logs
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_url VARCHAR;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS stereo_recording_url VARCHAR;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_duration_seconds INTEGER;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_status VARCHAR DEFAULT 'none';
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS transcript_text TEXT;
                        ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS transcript_status VARCHAR DEFAULT 'none';

                        -- Migrate old column data if they exist
                        UPDATE call_logs SET start_time = started_at WHERE start_time IS NULL AND started_at IS NOT NULL;
                        UPDATE call_logs SET end_time = ended_at WHERE end_time IS NULL AND ended_at IS NOT NULL;
                    """))
                    conn.commit()
                    logger.info("✅ Telephony tables created/verified")

                    # Add recording/transcript status columns to vapi_calls
                    conn.execute(text("""
                        ALTER TABLE vapi_calls ADD COLUMN IF NOT EXISTS stereo_recording_url VARCHAR(512);
                        ALTER TABLE vapi_calls ADD COLUMN IF NOT EXISTS recording_status VARCHAR(50) DEFAULT 'none';
                        ALTER TABLE vapi_calls ADD COLUMN IF NOT EXISTS transcript_status VARCHAR(50) DEFAULT 'none';
                    """))
                    conn.commit()
                    logger.info("✅ Vapi call recording columns verified")

                    # Add concierge_responsible column to workflow_day_configs
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='workflow_day_configs') THEN
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='concierge_responsible') THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN concierge_responsible BOOLEAN DEFAULT FALSE;
                                END IF;
                            END IF;
                        END $$;
                    """))
                    conn.commit()
                    logger.info("✅ Workflow concierge_responsible column added")

                    # Add weekly task scheduling columns to workflow_day_configs
                    # These support recurring tasks like Monday Weekly Updates
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='workflow_day_configs') THEN
                                -- repeat_weekly: Flag to mark task as weekly recurring
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_weekly') THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN repeat_weekly BOOLEAN DEFAULT FALSE;
                                END IF;
                                -- repeat_day_of_week: Which day to repeat (0=Monday, 6=Sunday)
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_day_of_week') THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN repeat_day_of_week INTEGER;
                                END IF;
                                -- repeat_until_status: JSON array of statuses that stop the recurrence
                                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_until_status') THEN
                                    ALTER TABLE workflow_day_configs ADD COLUMN repeat_until_status JSONB DEFAULT '[]'::jsonb;
                                END IF;
                            END IF;
                        END $$;
                    """))
                    conn.commit()
                    logger.info("✅ Weekly task scheduling columns added to workflow_day_configs")

                    # Add concierge to TaskResponsibility enum type
                    conn.execute(text("""
                        DO $$
                        BEGIN
                            -- Check if taskresponsibility enum type exists and add concierge value
                            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'taskresponsibility') THEN
                                IF NOT EXISTS (
                                    SELECT 1 FROM pg_enum WHERE enumlabel = 'concierge'
                                    AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'taskresponsibility')
                                ) THEN
                                    ALTER TYPE taskresponsibility ADD VALUE IF NOT EXISTS 'concierge';
                                END IF;
                            END IF;
                        EXCEPTION
                            WHEN duplicate_object THEN NULL;
                        END $$;
                    """))
                    conn.commit()
                    logger.info("✅ TaskResponsibility enum updated with concierge")

                    # Fix invalid Application stage values
                    result = conn.execute(text("""
                        UPDATE leads
                        SET stage = 'Application'
                        WHERE stage = 'Application'
                    """))
                    if result.rowcount > 0:
                        logger.info(f"✅ Fixed {result.rowcount} leads with invalid Application stage")

                    # Fix null stages - set to New
                    result2 = conn.execute(text("""
                        UPDATE leads
                        SET stage = 'New'
                        WHERE stage IS NULL
                    """))
                    if result2.rowcount > 0:
                        logger.info(f"✅ Fixed {result2.rowcount} leads with null stage")

                    conn.commit()
        except Exception as e:
            logger.warning(f"⚠️ Schema migration note: {e}")

        # Add valuation/refi columns to mum_clients table
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS term INTEGER DEFAULT 360;
                    ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS maturity_date TIMESTAMP;
                    ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS estimated_equity FLOAT;
                    ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS current_ltv FLOAT;
                    ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS refi_score INTEGER DEFAULT 0;
                    ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS property_state VARCHAR;
                    ALTER TABLE mum_clients ADD COLUMN IF NOT EXISTS property_zip VARCHAR;
                """))
                conn.commit()
                logger.info("✅ MUM client valuation/refi columns added")
        except Exception as e:
            logger.warning(f"⚠️ MUM valuation columns migration note: {e}")

        # Add enterprise security columns to users table (account lockout, MFA, SSO)
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMP;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_failed_login_at TIMESTAMP;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret VARCHAR;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN DEFAULT FALSE;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_backup_codes JSONB;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled_at TIMESTAMP;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_provider VARCHAR;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_subject_id VARCHAR;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP WITH TIME ZONE;
                """))
                conn.execute(text("""
                    ALTER TABLE organizations ADD COLUMN IF NOT EXISTS sso_enforced BOOLEAN DEFAULT FALSE;
                    ALTER TABLE organizations ADD COLUMN IF NOT EXISTS mfa_required BOOLEAN DEFAULT FALSE;
                    ALTER TABLE organizations ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'America/Chicago';
                """))
                conn.execute(text("""
                    ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS scopes JSONB DEFAULT '[]';
                    ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS description VARCHAR;
                    ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;
                """))
                conn.commit()
                logger.info("✅ Enterprise security columns added (users, organizations, api_keys)")
        except Exception as e:
            logger.warning(f"⚠️ Enterprise security columns note: {e}")

        # Add milestone + mum_date columns to loans/leads (required by ORM model)
        # These MUST run before any ORM query on Loan/Lead to avoid
        # "column does not exist" errors that poison DB transactions.
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE loans ADD COLUMN IF NOT EXISTS current_milestone_status VARCHAR(50);
                    ALTER TABLE loans ADD COLUMN IF NOT EXISTS current_milestone_entered_at TIMESTAMPTZ;
                    ALTER TABLE loans ADD COLUMN IF NOT EXISTS mum_date TIMESTAMPTZ;
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_milestone_status VARCHAR(50);
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_milestone_entered_at TIMESTAMPTZ;
                """))
                conn.commit()
                logger.info("✅ Milestone + mum_date columns added (loans, leads)")
        except Exception as e:
            logger.warning(f"⚠️ Milestone columns note: {e}")

        # Add AI content attribution columns to ai_conversation_memory (AI-005)
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE ai_conversation_memory ADD COLUMN IF NOT EXISTS is_ai_generated BOOLEAN DEFAULT FALSE;
                    ALTER TABLE ai_conversation_memory ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50);
                    ALTER TABLE ai_conversation_memory ADD COLUMN IF NOT EXISTS ai_confidence INTEGER;
                """))
                conn.commit()
                logger.info("✅ AI content attribution columns added (ai_conversation_memory)")
        except Exception as e:
            logger.warning(f"⚠️ AI attribution columns note: {e}")

        # Create tenant_email_templates table (WL-003)
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tenant_email_templates (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL,
                        template_type VARCHAR(100) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        subject VARCHAR(500),
                        body_html TEXT,
                        body_text TEXT,
                        cta_text VARCHAR(255),
                        cta_url VARCHAR(500),
                        merge_fields JSONB DEFAULT '[]',
                        category VARCHAR(50) DEFAULT 'transactional',
                        is_active BOOLEAN DEFAULT TRUE,
                        created_by_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(organization_id, template_type)
                    )
                """))
                conn.commit()
                logger.info("✅ tenant_email_templates table created/verified (WL-003)")
        except Exception as e:
            logger.warning(f"⚠️ tenant_email_templates table note: {e}")

        # Create tenant_legal_documents table (WL-007)
        try:
            with _engine.connect() as conn:
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
                logger.info("✅ tenant_legal_documents table created/verified (WL-007)")
        except Exception as e:
            logger.warning(f"⚠️ tenant_legal_documents table note: {e}")

        # Create regulatory_reports table (CMP-008)
        try:
            with _engine.connect() as conn:
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
                logger.info("✅ regulatory_reports table created/verified (CMP-008)")
        except Exception as e:
            logger.warning(f"⚠️ regulatory_reports table note: {e}")

        # Create tenant_storage_usage table (MTR-004)
        try:
            with _engine.connect() as conn:
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
                logger.info("✅ tenant_storage_usage table created/verified (MTR-004)")
        except Exception as e:
            logger.warning(f"⚠️ tenant_storage_usage table note: {e}")

        # Workflow SLA Phase 1: company_holidays table + milestone columns (WF-001)
        try:
            with _engine.connect() as conn:
                # company_holidays table for business day SLA calculations
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

                # Seed 2026 US federal holidays (org_id=0 = system defaults)
                conn.execute(text("""
                    INSERT INTO company_holidays (organization_id, holiday_date, holiday_name, is_recurring)
                    VALUES
                        (0, '2026-01-01', 'New Year''s Day', false),
                        (0, '2026-01-19', 'Martin Luther King Jr. Day', false),
                        (0, '2026-02-16', 'Presidents'' Day', false),
                        (0, '2026-05-25', 'Memorial Day', false),
                        (0, '2026-06-19', 'Juneteenth', false),
                        (0, '2026-07-03', 'Independence Day (Observed)', false),
                        (0, '2026-09-07', 'Labor Day', false),
                        (0, '2026-10-12', 'Columbus Day', false),
                        (0, '2026-11-11', 'Veterans Day', false),
                        (0, '2026-11-26', 'Thanksgiving Day', false),
                        (0, '2026-12-25', 'Christmas Day', false)
                    ON CONFLICT DO NOTHING
                """))

                # Performance indexes for workflow engine queries
                # (columns added earlier in init_db)
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_loans_milestone_status
                        ON loans (current_milestone_status, current_milestone_entered_at)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_leads_milestone_status
                        ON leads (current_milestone_status, current_milestone_entered_at)
                """))

                conn.commit()
                logger.info("✅ Workflow SLA Phase 1: company_holidays + milestone columns (WF-001)")
        except Exception as e:
            logger.warning(f"⚠️ Workflow SLA Phase 1 note: {e}")

        # Workflow engine columns: escalation_level + workflow_instance_id on task instances
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE workflow_task_instances ADD COLUMN IF NOT EXISTS escalation_level INTEGER DEFAULT 0
                """))
                conn.execute(text("""
                    ALTER TABLE workflow_task_instances ADD COLUMN IF NOT EXISTS workflow_instance_id INTEGER
                """))
                conn.commit()
                logger.info("✅ Workflow engine columns added (escalation_level, workflow_instance_id)")
        except Exception as e:
            logger.warning(f"⚠️ Workflow engine columns note: {e}")

        # Loan State Reconciliation: audit log table + raw SF stage column
        try:
            with _engine.connect() as conn:
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
                conn.execute(text("""
                    ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_raw_stage VARCHAR(200)
                """))
                conn.commit()
                logger.info("✅ Loan state reconciliation: audit log table + salesforce_raw_stage column")
        except Exception as e:
            logger.warning(f"⚠️ Loan state reconciliation migration note: {e}")

        # Create call monitoring tables (call_sessions, call_participants, etc.)
        try:
            with _engine.connect() as conn:
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
                logger.info("✅ Call monitoring tables created/verified (call_sessions, call_artifacts, call_risk_flags)")
        except Exception as e:
            logger.warning(f"⚠️ Call monitoring tables note: {e}")

        # Recording consent gate columns (Call Intelligence session lifecycle).
        # migration_recording_consent.sql was never wired into startup, so the
        # call_sessions table created above lacks the columns the consent
        # routes write — apply them inline here (idempotent).
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE call_sessions
                        ADD COLUMN IF NOT EXISTS call_control_id VARCHAR(255),
                        ADD COLUMN IF NOT EXISTS loan_officer_id VARCHAR(36),
                        ADD COLUMN IF NOT EXISTS contact_id VARCHAR(36),
                        ADD COLUMN IF NOT EXISTS borrower_state VARCHAR(2),
                        ADD COLUMN IF NOT EXISTS recording_consent_status VARCHAR(20) DEFAULT 'pending',
                        ADD COLUMN IF NOT EXISTS consent_requirement VARCHAR(20),
                        ADD COLUMN IF NOT EXISTS consent_disclosed_at TIMESTAMPTZ,
                        ADD COLUMN IF NOT EXISTS consent_disclosure_method VARCHAR(20),
                        ADD COLUMN IF NOT EXISTS is_two_party_state BOOLEAN DEFAULT false,
                        ADD COLUMN IF NOT EXISTS consent_override_by VARCHAR(36),
                        ADD COLUMN IF NOT EXISTS consent_override_at TIMESTAMPTZ,
                        ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ,
                        ADD COLUMN IF NOT EXISTS call_ended_at TIMESTAMPTZ
                """))
                # Stale CHECKs from the never-wired manual SQL migration reject
                # values the app writes ('browser_pending', 'browser_local').
                conn.execute(text("""
                    ALTER TABLE call_sessions DROP CONSTRAINT IF EXISTS
                        call_sessions_recording_consent_status_check
                """))
                conn.execute(text("""
                    ALTER TABLE call_sessions DROP CONSTRAINT IF EXISTS
                        call_sessions_consent_disclosure_method_check
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_call_sessions_consent_status
                        ON call_sessions (recording_consent_status)
                """))
                conn.execute(text("""
                    ALTER TABLE organizations
                        ADD COLUMN IF NOT EXISTS recording_consent_config JSONB
                """))
                conn.commit()
                logger.info("✅ Recording consent columns on call_sessions + organizations")
        except Exception as e:
            logger.warning(f"⚠️ Recording consent migration note: {e}")

        # Add organization_id to audit_logs for multi-tenant isolation (ISO-014)
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id);
                    CREATE INDEX IF NOT EXISTS ix_audit_logs_organization_id ON audit_logs(organization_id);
                """))
                conn.commit()
                logger.info("✅ audit_logs: organization_id column added")
        except Exception as e:
            logger.warning(f"⚠️ audit_logs organization_id migration note: {e}")

        # Make audit_logs user_id and changed_by_id nullable for system-level events
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE audit_logs ALTER COLUMN user_id DROP NOT NULL;
                    ALTER TABLE audit_logs ALTER COLUMN changed_by_id DROP NOT NULL;
                """))
                conn.commit()
                logger.info("✅ audit_logs: user_id/changed_by_id made nullable for system events")
        except Exception as e:
            logger.warning(f"⚠️ audit_logs nullable migration note: {e}")

        # Add grace_period_ends_at to subscriptions for payment failure grace period (LIC-006)
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS grace_period_ends_at TIMESTAMP;
                """))
                conn.commit()
                logger.info("✅ subscriptions: grace_period_ends_at column added")
        except Exception as e:
            logger.warning(f"⚠️ subscriptions grace_period migration note: {e}")

        # Create data_subject_requests table for GDPR DSAR (CMP-004)
        try:
            with _engine.connect() as conn:
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
                logger.info("✅ data_subject_requests table created/verified")
        except Exception as e:
            logger.warning(f"⚠️ data_subject_requests table note: {e}")

        # Create scheduled_reports table (Enterprise Readiness Domain 9, Check 9.11)
        try:
            with _engine.connect() as conn:
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
                # Add columns if table already exists without them
                for col_stmt in [
                    "ALTER TABLE scheduled_reports ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
                    "ALTER TABLE scheduled_reports ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ",
                    "ALTER TABLE scheduled_reports ADD COLUMN IF NOT EXISTS last_error TEXT",
                    "ALTER TABLE scheduled_reports ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'active'",
                    "ALTER TABLE scheduled_reports ADD COLUMN IF NOT EXISTS last_generation_ms INTEGER",
                ]:
                    try:
                        conn.execute(text(col_stmt))
                    except Exception:
                        pass  # Column already exists
                conn.commit()
                logger.info("✅ scheduled_reports table created/verified (ER-9.11)")
        except Exception as e:
            logger.warning(f"⚠️ scheduled_reports table note: {e}")

        # Ensure organization_branding table exists before adding columns
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS organization_branding (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL REFERENCES organizations(id),
                        company_name VARCHAR(200),
                        logo_url VARCHAR(500),
                        primary_color VARCHAR(7) DEFAULT '#1a56db',
                        secondary_color VARCHAR(7) DEFAULT '#7c3aed',
                        accent_color VARCHAR(7) DEFAULT '#059669',
                        setting_type VARCHAR(50),
                        settings JSON,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_org_branding_org_id ON organization_branding (organization_id)"))
                conn.commit()
                logger.info("✅ organization_branding table ensured")
        except Exception as e:
            logger.warning(f"⚠️ organization_branding table note: {e}")

        # Add white-label branding columns (Enterprise Readiness Domain 12)
        try:
            with _engine.connect() as conn:
                branding_columns = [
                    ("organization_branding", "favicon_url", "VARCHAR(500)"),
                    ("organization_branding", "font_family", "VARCHAR(200) DEFAULT 'Inter, system-ui, sans-serif'"),
                    ("organization_branding", "sms_sender_id", "VARCHAR(50)"),
                    ("organization_branding", "sms_sender_name", "VARCHAR(100)"),
                    ("organization_branding", "portal_logo_url", "VARCHAR(500)"),
                    ("organization_branding", "portal_title", "VARCHAR(200)"),
                    ("organization_branding", "portal_footer_text", "TEXT"),
                    ("organization_branding", "custom_domain", "VARCHAR(255)"),
                    ("organization_branding", "custom_css", "TEXT"),
                ]
                for table, col, col_type in branding_columns:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
                    ))
                conn.commit()
                logger.info("✅ White-label branding columns added (ER-12)")
        except Exception as e:
            logger.warning(f"⚠️ Branding columns note: {e}")

        # Consolidate branding: add columns from WhiteLabelConfig model to organization_branding
        # Previously these lived on smart_docs_white_label_configs; unified May 2026.
        try:
            with _engine.connect() as conn:
                consolidation_columns = [
                    ("organization_branding", "header_bg_color", "VARCHAR(7) DEFAULT '#ffffff'"),
                    ("organization_branding", "email_from_name", "VARCHAR(200)"),
                    ("organization_branding", "email_from_address", "VARCHAR(255)"),
                    ("organization_branding", "email_reply_to", "VARCHAR(255)"),
                    ("organization_branding", "email_footer_html", "TEXT"),
                    ("organization_branding", "email_footer", "TEXT"),
                    ("organization_branding", "email_signature_template", "TEXT"),
                    ("organization_branding", "company_phone", "VARCHAR(50)"),
                    ("organization_branding", "company_address", "TEXT"),
                    ("organization_branding", "portal_welcome_message", "TEXT"),
                    ("organization_branding", "portal_custom_css", "TEXT"),
                    ("organization_branding", "support_email", "VARCHAR(255)"),
                    ("organization_branding", "support_phone", "VARCHAR(20)"),
                    ("organization_branding", "privacy_policy_url", "VARCHAR(500)"),
                    ("organization_branding", "terms_of_service_url", "VARCHAR(500)"),
                    ("organization_branding", "nmls_number", "VARCHAR(20)"),
                    ("organization_branding", "equal_housing_logo", "BOOLEAN DEFAULT TRUE"),
                    ("organization_branding", "disclaimer_text", "TEXT"),
                    ("organization_branding", "ssl_status", "VARCHAR(20) DEFAULT 'pending'"),
                    ("organization_branding", "domain_verified", "BOOLEAN DEFAULT FALSE"),
                    ("organization_branding", "domain_verification_token", "VARCHAR(100)"),
                    ("organization_branding", "vercel_domain_id", "VARCHAR(100)"),
                    ("organization_branding", "is_active", "BOOLEAN DEFAULT TRUE"),
                ]
                for table, col, col_type in consolidation_columns:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"
                    ))
                conn.commit()
                logger.info("✅ Branding consolidation columns added (ER-12 unified)")
        except Exception as e:
            logger.warning(f"⚠️ Branding consolidation note: {e}")

        # Create organization_settings table (Enterprise Readiness Domain 5)
        try:
            with _engine.connect() as conn:
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
                logger.info("✅ organization_settings table created/verified (ER-5)")
        except Exception as e:
            logger.warning(f"⚠️ organization_settings table note: {e}")

        # Run comprehensive column migration for all missing columns
        try:
            from migrations.add_all_missing_columns import run_migration
            run_migration()
            logger.info("✅ Comprehensive column migration completed")
        except Exception as e:
            logger.warning(f"⚠️ Comprehensive migration note: {e}")

        # Add production_assistant column to leads and loans
        try:
            with _engine.connect() as conn:
                conn.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS production_assistant VARCHAR"))
                conn.execute(text("ALTER TABLE loans ADD COLUMN IF NOT EXISTS production_assistant VARCHAR"))
                conn.commit()
                logger.info("✅ Added production_assistant column to leads and loans")
        except Exception as e:
            logger.warning(f"⚠️ production_assistant column migration note: {e}")

        # Deploy SOC 2 compliance tables (idempotent)
        try:
            from migrations.deploy_soc2_tables import deploy_soc2_tables
            created = deploy_soc2_tables(_engine)
            if created:
                logger.info(f"✅ SOC 2 tables created: {', '.join(created)}")
            else:
                logger.info("✅ SOC 2 tables already exist")
        except Exception as e:
            logger.warning(f"⚠️ SOC 2 table migration note: {e}")

        # Add EEOC demographic + NMLS license tracking fields to mm_candidates
        try:
            from migrations.add_eeoc_nmls_candidate_fields import run_migration as run_eeoc_nmls_migration
            eeoc_result = run_eeoc_nmls_migration()
            logger.info(f"✅ EEOC/NMLS migration: {eeoc_result.get('message', 'done')}")
        except Exception as e:
            logger.warning(f"⚠️ EEOC/NMLS migration note: {e}")

        # C3: Add organization_id to remaining recruiting tables
        try:
            from migrations.add_org_id_recruiting_tables_v2 import run_migration as run_org_id_v2
            org_v2_result = run_org_id_v2()
            logger.info(f"✅ Recruiting org_id v2: {len(org_v2_result.get('processed', []))} tables")
        except Exception as e:
            logger.warning(f"⚠️ Recruiting org_id v2 note: {e}")

        # C4: Add OFCCP disposition tracking columns
        try:
            from migrations.add_disposition_tracking import run_migration as run_disposition
            disp_result = run_disposition()
            logger.info(f"✅ Disposition tracking: {len(disp_result.get('added', []))} columns")
        except Exception as e:
            logger.warning(f"⚠️ Disposition tracking note: {e}")

        # C5: Create AI decision audit log table
        try:
            from migrations.add_recruit_ai_audit_log import run_migration as run_ai_audit
            ai_audit_result = run_ai_audit()
            logger.info(f"✅ AI audit log: created={ai_audit_result.get('created', False)}")
        except Exception as e:
            logger.warning(f"⚠️ AI audit log note: {e}")

        # Create recruiting assessment quiz + portal tables (11 tables)
        try:
            from migrations.add_recruit_assessment_tables import run_migration as run_assessment
            run_assessment()
            logger.info("✅ recruit assessment + portal tables ready")
        except Exception as e:
            logger.warning(f"⚠️ recruit assessment tables note: {e}")

        # Create recruit_social_posts + candidate_linkedin_posts tables
        try:
            from migrations.create_social_recruiting_tables import run_migration as run_social_recruiting
            run_social_recruiting(_engine)
            logger.info("✅ recruit social posts tables ready")
        except Exception as e:
            logger.warning(f"⚠️ recruit social posts tables note: {e}")

        # Create social_oauth_states + social_tokens tables (required by recruit_social_routes)
        try:
            from migrations.create_social_oauth_tables import run_migration as run_social_oauth
            run_social_oauth(_engine)
            logger.info("✅ social_oauth_states + social_tokens tables ready")
        except Exception as e:
            logger.warning(f"⚠️ social oauth tables note: {e}")

        # Create recruit_workflow_config table for per-org workflow customization
        try:
            from migrations.add_recruit_workflow_config import run_migration as run_wf_config
            run_wf_config()
            logger.info("  recruit_workflow_config table ready")
        except Exception as e:
            logger.warning(f"  recruit workflow config note: {e}")

        # Fix 7: Add organization_id to social_tokens for tenant isolation
        try:
            from migrations.add_social_tokens_org_id import run_migration as run_social_tokens_org
            run_social_tokens_org(_engine)
            logger.info("✅ social_tokens org_id migration complete")
        except Exception as e:
            logger.warning(f"⚠️ social_tokens org_id note: {e}")

        # Fix 8: Create ops_sweep_results table (moved from inline DDL in ops_manager_agent)
        try:
            from migrations.create_ops_sweep_results import run_migration as run_ops_sweep
            run_ops_sweep(_engine)
            logger.info("✅ ops_sweep_results migration complete")
        except Exception as e:
            logger.warning(f"⚠️ ops_sweep_results note: {e}")

        # Fix 9: Sync tasktype enum (ensure Python TaskType values exist in DB)
        try:
            from migrations.sync_tasktype_enum import run_migration as run_tasktype_sync
            run_tasktype_sync(_engine)
            logger.info("✅ tasktype enum sync complete")
        except Exception as e:
            logger.warning(f"⚠️ tasktype enum sync note: {e}")

        # Fix 10: Seed campaign email templates
        try:
            from migrations.seed_campaign_templates import run_migration as run_campaign_seed
            run_campaign_seed(_engine)
            logger.info("✅ campaign template seed complete")
        except Exception as e:
            logger.warning(f"⚠️ campaign template seed note: {e}")

        # Recruit Calendar: recruit_interview_details + recruit_milestones tables
        try:
            from migrations.add_recruit_calendar_tables import run_migration as run_recruit_calendar
            run_recruit_calendar(_engine)
            logger.info("✅ recruit_interview_details + recruit_milestones tables ready")
        except Exception as e:
            logger.warning(f"⚠️ recruit calendar tables note: {e}")

        # Add briefing_preferences JSONB column to users
        try:
            from migrations.add_briefing_preferences import run_migration as run_briefing_prefs
            run_briefing_prefs(_engine)
            logger.info("✅ briefing_preferences column ready")
        except Exception as e:
            logger.warning(f"⚠️ briefing_preferences migration note: {e}")

        # Add CI enhancement columns (telephony_call_id, call_provider, last_flush_at)
        try:
            from migrations.add_ci_enhancement_columns import run_migration as run_ci_enhancements
            run_ci_enhancements(_engine)
            logger.info("✅ CI enhancement columns ready")
        except Exception as e:
            logger.warning(f"⚠️ CI enhancement migration note: {e}")

        # Create voice_workflows table
        try:
            from migrations.add_voice_workflows_table import run_migration as run_voice_workflows
            run_voice_workflows(_engine)
            logger.info("✅ voice_workflows table ready")
        except Exception as e:
            logger.warning(f"⚠️ voice_workflows migration note: {e}")

        try:
            from migrations.add_device_tokens_table import run_migration as run_device_tokens
            run_device_tokens()
            logger.info("✅ device_tokens table ready")
        except Exception as e:
            logger.warning(f"⚠️ device_tokens migration note: {e}")

        # SMS pipeline: add missing columns that cause inbound SMS to crash
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE sms_messages ADD COLUMN IF NOT EXISTS provider_message_id VARCHAR;
                    ALTER TABLE sms_messages ADD COLUMN IF NOT EXISTS template_used VARCHAR;
                    ALTER TABLE sms_messages ADD COLUMN IF NOT EXISTS error_message TEXT;
                    ALTER TABLE sms_messages ADD COLUMN IF NOT EXISTS ai_generated BOOLEAN DEFAULT FALSE;
                    ALTER TABLE sms_messages ADD COLUMN IF NOT EXISTS meta_data JSONB;
                    ALTER TABLE sms_messages ADD COLUMN IF NOT EXISTS consent_record_id INTEGER;

                    ALTER TABLE verified_caller_ids ADD COLUMN IF NOT EXISTS organization_id INTEGER;

                    ALTER TABLE agent_telephony_settings ADD COLUMN IF NOT EXISTS organization_id INTEGER;

                    ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS organization_id INTEGER;
                    ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS sender_user_id INTEGER;
                    ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS sender_role VARCHAR;
                    ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS media_urls JSONB DEFAULT '[]';
                    ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS media_s3_keys JSONB DEFAULT '[]';
                    ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS page_type VARCHAR;
                    ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS borrower_type VARCHAR;
                    ALTER TABLE sms_panel_messages ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
                """))
                conn.commit()
                logger.info("✅ SMS pipeline columns added (sms_messages, verified_caller_ids, agent_telephony_settings, sms_panel_messages)")
        except Exception as e:
            logger.warning(f"⚠️ SMS pipeline columns note: {e}")

        # Power dialer session tables: backfill organization_id on legacy DBs.
        # Isolated per-table so a missing table can't abort sibling migrations.
        for _dialer_table in ("dialer_sessions", "dialer_session_tasks"):
            try:
                with _engine.connect() as conn:
                    conn.execute(text(
                        f"ALTER TABLE {_dialer_table} ADD COLUMN IF NOT EXISTS organization_id INTEGER;"
                    ))
                    conn.commit()
            except Exception as e:
                logger.warning(f"⚠️ {_dialer_table} organization_id migration note: {e}")

        # Underwriting guideline platform tables (AI Underwriter / guideline RAG).
        # Production skips Base.metadata.create_all(), so these must be created
        # explicitly here. Schema matches models.call_monitoring_models with
        # INTEGER org/user ids (the app is integer-keyed, not UUID).
        try:
            with _engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
        except Exception as e:
            logger.warning(f"⚠️ pgvector extension note (guidelines): {e}")
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS underwriting_guidelines (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        name VARCHAR(500) NOT NULL,
                        description TEXT,
                        version VARCHAR(50),
                        guideline_type VARCHAR(50) NOT NULL,
                        category VARCHAR(50),
                        loan_program VARCHAR(50) DEFAULT 'all',
                        investor_name VARCHAR(200),
                        source_file_name VARCHAR(500),
                        source_file_path VARCHAR(1000),
                        source_file_type VARCHAR(50),
                        source_file_size INTEGER,
                        full_text TEXT,
                        summary TEXT,
                        key_points JSONB DEFAULT '[]'::jsonb,
                        structured_rules JSONB DEFAULT '{}'::jsonb,
                        tags TEXT[] DEFAULT '{}',
                        keywords TEXT[] DEFAULT '{}',
                        effective_date DATE,
                        expiration_date DATE,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_processed BOOLEAN DEFAULT FALSE,
                        uploaded_by INTEGER,
                        organization_id INTEGER,
                        processing_notes TEXT,
                        last_processed_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        embedding_status VARCHAR(20) DEFAULT 'pending',
                        chunk_count INTEGER DEFAULT 0,
                        overlay_priority INTEGER DEFAULT 4
                    );
                    -- Idempotent column adds for legacy/partial tables
                    ALTER TABLE underwriting_guidelines ADD COLUMN IF NOT EXISTS organization_id INTEGER;
                    ALTER TABLE underwriting_guidelines ADD COLUMN IF NOT EXISTS uploaded_by INTEGER;
                    ALTER TABLE underwriting_guidelines ADD COLUMN IF NOT EXISTS keywords TEXT[] DEFAULT '{}';
                    ALTER TABLE underwriting_guidelines ADD COLUMN IF NOT EXISTS embedding_status VARCHAR(20) DEFAULT 'pending';
                    ALTER TABLE underwriting_guidelines ADD COLUMN IF NOT EXISTS chunk_count INTEGER DEFAULT 0;
                    ALTER TABLE underwriting_guidelines ADD COLUMN IF NOT EXISTS overlay_priority INTEGER DEFAULT 4;
                    CREATE INDEX IF NOT EXISTS ix_uw_guidelines_type ON underwriting_guidelines(guideline_type);
                    CREATE INDEX IF NOT EXISTS ix_uw_guidelines_category ON underwriting_guidelines(category);
                    CREATE INDEX IF NOT EXISTS ix_uw_guidelines_loan_program ON underwriting_guidelines(loan_program);
                    CREATE INDEX IF NOT EXISTS ix_uw_guidelines_active ON underwriting_guidelines(is_active);
                    CREATE INDEX IF NOT EXISTS ix_uw_guidelines_org ON underwriting_guidelines(organization_id);

                    CREATE TABLE IF NOT EXISTS guideline_sections (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        guideline_id UUID NOT NULL REFERENCES underwriting_guidelines(id) ON DELETE CASCADE,
                        section_number VARCHAR(100),
                        section_title VARCHAR(500),
                        parent_section VARCHAR(100),
                        content TEXT NOT NULL,
                        summary TEXT,
                        category VARCHAR(50),
                        topics TEXT[] DEFAULT '{}',
                        embedding_model VARCHAR(50) DEFAULT 'text-embedding-3-small',
                        token_count INTEGER,
                        chunk_hash VARCHAR(64),
                        page_number INTEGER,
                        position_start INTEGER,
                        position_end INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS ix_guideline_sections_guideline ON guideline_sections(guideline_id);
                    CREATE INDEX IF NOT EXISTS ix_guideline_sections_category ON guideline_sections(category);
                """))
                conn.commit()
            # content_embedding column: prefer pgvector, fall back to TEXT so the
            # table stays ORM-queryable even where the extension is unavailable.
            try:
                with _engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE guideline_sections ADD COLUMN IF NOT EXISTS content_embedding vector(1536);"
                    ))
                    conn.commit()
            except Exception:
                with _engine.connect() as conn:
                    conn.execute(text(
                        "ALTER TABLE guideline_sections ADD COLUMN IF NOT EXISTS content_embedding TEXT;"
                    ))
                    conn.commit()
            logger.info("✅ Underwriting guideline tables ready (underwriting_guidelines, guideline_sections)")
        except Exception as e:
            logger.warning(f"⚠️ Underwriting guideline tables note: {e}")

        # SMS auto-responder: create sms_tasks + supporting tables
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS sms_tasks (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL,
                        assigned_user_id INTEGER,
                        lead_id INTEGER,
                        phone_number VARCHAR NOT NULL,
                        contact_name VARCHAR,
                        inbound_message TEXT NOT NULL,
                        inbound_message_id VARCHAR,
                        inbound_received_at TIMESTAMPTZ NOT NULL,
                        status VARCHAR DEFAULT 'pending',
                        priority VARCHAR DEFAULT 'normal',
                        category VARCHAR,
                        ai_recommendation TEXT,
                        ai_confidence FLOAT DEFAULT 0,
                        ai_model_version VARCHAR,
                        ai_reasoning TEXT,
                        ai_generated_at TIMESTAMPTZ,
                        response_text TEXT,
                        response_source VARCHAR,
                        response_sent_at TIMESTAMPTZ,
                        responded_by_user_id INTEGER,
                        lo_feedback VARCHAR,
                        lo_edited_response TEXT,
                        edit_distance INTEGER,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS ix_sms_tasks_org_status ON sms_tasks(organization_id, status);
                    CREATE INDEX IF NOT EXISTS ix_sms_tasks_phone_number ON sms_tasks(phone_number);

                    CREATE TABLE IF NOT EXISTS sms_response_patterns (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL,
                        category VARCHAR NOT NULL,
                        response_template TEXT NOT NULL,
                        usage_count INTEGER DEFAULT 0,
                        success_rate FLOAT DEFAULT 0,
                        avg_edit_distance FLOAT DEFAULT 0,
                        source VARCHAR DEFAULT 'ai',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS ix_sms_patterns_org_cat ON sms_response_patterns(organization_id, category);

                    CREATE TABLE IF NOT EXISTS sms_ai_confidence (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL,
                        user_id INTEGER,
                        category VARCHAR NOT NULL,
                        auto_respond_enabled BOOLEAN DEFAULT FALSE,
                        confidence_threshold FLOAT DEFAULT 0.75,
                        total_suggestions INTEGER DEFAULT 0,
                        accepted_count INTEGER DEFAULT 0,
                        rejected_count INTEGER DEFAULT 0,
                        edited_count INTEGER DEFAULT 0,
                        acceptance_rate FLOAT DEFAULT 0,
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(organization_id, user_id, category)
                    );

                    CREATE TABLE IF NOT EXISTS sms_ai_audit_log (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL,
                        task_id INTEGER,
                        action VARCHAR NOT NULL,
                        details JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """))
                conn.commit()
                logger.info("✅ SMS auto-responder tables created (sms_tasks, sms_response_patterns, sms_ai_confidence, sms_ai_audit_log)")
        except Exception as e:
            logger.warning(f"⚠️ SMS auto-responder tables note: {e}")

        # Seed verified_caller_ids with Telnyx number + org_id
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO verified_caller_ids (phone_number, friendly_name, verification_status, organization_id)
                    SELECT '+18438838956', 'Perennia AI (Telnyx)', 'verified', o.id
                    FROM organizations o
                    WHERE NOT EXISTS (
                        SELECT 1 FROM verified_caller_ids WHERE phone_number = '+18438838956'
                    )
                    LIMIT 1
                """))
                conn.execute(text("""
                    UPDATE verified_caller_ids
                    SET organization_id = (SELECT id FROM organizations LIMIT 1)
                    WHERE phone_number = '+18438838956'
                      AND organization_id IS NULL
                """))
                conn.commit()
                logger.info("✅ Telnyx number seeded in verified_caller_ids")
        except Exception as e:
            logger.warning(f"⚠️ verified_caller_ids seed note: {e}")

        # Create POS 1003 tables (pos_applications, pos_application_sections,
        # pos_application_pii, pos_application_audit, pos_ai_qa_messages)
        try:
            import importlib
            _pos_mod = importlib.import_module("migrations.2026_04_25_pos_tables")
            _pos_mod.run_migration(_engine)
            logger.info("✅ POS 1003 tables ready")
        except Exception as e:
            logger.warning(f"⚠️ POS 1003 tables note: {e}")

        # Add encrypted DOB columns to pos_application_pii (GLBA/CCPA)
        try:
            with _engine.connect() as conn:
                conn.execute(sa_text(
                    "ALTER TABLE pos_application_pii "
                    "ADD COLUMN IF NOT EXISTS dob_encrypted VARCHAR"
                ))
                conn.execute(sa_text(
                    "ALTER TABLE pos_application_pii "
                    "ADD COLUMN IF NOT EXISTS co_dob_encrypted VARCHAR"
                ))
                conn.commit()
            logger.info("✅ Encrypted DOB columns ready on pos_application_pii")
        except Exception as e:
            logger.warning(f"⚠️ Encrypted DOB columns note: {e}")

        # Add partial unique index on sms_ai_conversations (active phone+org)
        try:
            import importlib
            _sms_idx_mod = importlib.import_module("migrations.add_sms_conv_unique_index")
            _sms_idx_mod.run_migration(_engine)
            logger.info("SMS AI conversations unique index ready")
        except Exception as e:
            logger.warning(f"SMS AI conversations unique index note: {e}")

        # Add deleted_at soft-delete column to leads, loans, borrower_profiles
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
                    CREATE INDEX IF NOT EXISTS ix_leads_deleted_at ON leads(deleted_at);
                    ALTER TABLE loans ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
                    CREATE INDEX IF NOT EXISTS ix_loans_deleted_at ON loans(deleted_at);
                    ALTER TABLE borrower_profiles ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
                    CREATE INDEX IF NOT EXISTS ix_borrower_profiles_deleted_at ON borrower_profiles(deleted_at);
                """))
                conn.commit()
                logger.info("✅ deleted_at columns added to leads, loans, borrower_profiles")
        except Exception as e:
            logger.warning(f"⚠️ deleted_at migration note: {e}")

        # POSAIQAMessage — structured_output column (borrower agent)
        try:
            with _engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE pos_ai_qa_messages ADD COLUMN IF NOT EXISTS "
                    "structured_output JSONB"
                ))
                conn.commit()
                logger.info("Added structured_output column to pos_ai_qa_messages")
        except Exception as e:
            logger.debug("structured_output column migration: %s", e)

        # Create pos_borrower_messages table (POS portal internal messaging)
        try:
            with _engine.connect() as conn:
                conn.execute(sa_text("""
                    CREATE TABLE IF NOT EXISTS pos_borrower_messages (
                        id              SERIAL      PRIMARY KEY,
                        application_id  UUID        NOT NULL REFERENCES pos_applications(id) ON DELETE CASCADE,
                        organization_id INTEGER     NOT NULL,
                        sender_user_id  INTEGER,
                        sender_name     VARCHAR(128) NOT NULL,
                        sender_role     VARCHAR(64)  NOT NULL DEFAULT 'Loan Officer',
                        content         TEXT         NOT NULL,
                        read_at         TIMESTAMPTZ,
                        created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
                    )
                """))
                conn.execute(sa_text(
                    "CREATE INDEX IF NOT EXISTS ix_pos_msg_app_created "
                    "ON pos_borrower_messages (application_id, created_at)"
                ))
                conn.execute(sa_text(
                    "CREATE INDEX IF NOT EXISTS ix_pos_msg_app_unread "
                    "ON pos_borrower_messages (application_id, read_at)"
                ))
                conn.commit()
            logger.info("✅ pos_borrower_messages table ready")
        except Exception as e:
            logger.warning(f"⚠️ pos_borrower_messages table note: {e}")

        # Workflow flowchart tables + lead columns + default workflows
        try:
            from migrations.add_workflow_flowchart import run_migration as run_workflow_flowchart
            run_workflow_flowchart()
            logger.info("✅ Workflow flowchart migration complete")
        except Exception as e:
            logger.warning(f"⚠️ Workflow flowchart migration note: {e}")

        # HNSW index on agent_memories.embedding for vector similarity search
        try:
            import importlib
            _hnsw_mod = importlib.import_module("migrations.add_hnsw_index_agent_memories")
            _hnsw_mod.run_migration(_engine)
            logger.info("✅ HNSW index on agent_memories.embedding ready")
        except Exception as e:
            logger.warning(f"⚠️ HNSW index migration note: {e}")

        # Partial unique indexes on agent_memories for dedup enforcement
        try:
            import importlib
            _uniq_mod = importlib.import_module("migrations.add_agent_memory_unique_indexes")
            _uniq_mod.run_migration(_engine)
            logger.info("✅ Agent memory unique indexes ready")
        except Exception as e:
            logger.warning(f"⚠️ Agent memory unique indexes migration note: {e}")

        # Partial index on scheduler_appointments for active (non-terminal) rows.
        try:
            import importlib
            _active_idx_mod = importlib.import_module("migrations.add_appointment_active_partial_index")
            _active_idx_mod.run_migration(_engine)
            logger.info("✅ Appointment active partial index ready")
        except Exception as e:
            logger.warning(f"⚠️ Appointment active partial index migration note: {e}")

        # scheduler_audit_log: immutability trigger + SHA-256 hash chain
        try:
            import importlib
            _sai_mod = importlib.import_module("migrations.add_scheduler_audit_immutability")
            _sai_mod.run_migration(_engine)
            logger.info("✅ scheduler_audit_log immutability + hash-chain ready")
        except Exception as e:
            logger.warning(f"⚠️ scheduler_audit_log immutability migration note: {e}")

        # Enable PostgreSQL RLS on all scheduler tables (FORCE ROW LEVEL SECURITY for owner bypass)
        try:
            import importlib
            _sched_rls_mod = importlib.import_module("migrations.enable_scheduler_rls")
            _sched_rls_mod.run_migration(_engine)
            logger.info("✅ Scheduler RLS policies enabled")
        except Exception as e:
            logger.warning(f"⚠️ Scheduler RLS migration note: {e}")

        # Recruiting: score gate bypass audit log table
        try:
            import importlib
            _sgbl_mod = importlib.import_module("migrations.add_score_gate_bypass_log")
            _sgbl_mod.run_migration(_engine)
            logger.info("✅ mm_score_gate_bypass_log table ready")
        except Exception as e:
            logger.warning(f"⚠️ add_score_gate_bypass_log migration note: {e}")

        # Recruiting: add human sign-off columns to recruit_ai_audit_log
        try:
            import importlib
            _raal_mod = importlib.import_module("migrations.add_recruit_ai_audit_log_fields")
            _raal_mod.run_migration(_engine)
            logger.info("✅ recruit_ai_audit_log human review columns ready")
        except Exception as e:
            logger.warning(f"⚠️ add_recruit_ai_audit_log_fields migration note: {e}")

        # Enable PostgreSQL RLS on all mm_* (recruiting) tables
        try:
            import importlib
            _rec_rls_mod = importlib.import_module("migrations.enable_recruiting_rls")
            _rec_rls_mod.run_migration(_engine)
            logger.info("✅ Recruiting RLS policies enabled")
        except Exception as e:
            logger.warning(f"⚠️ enable_recruiting_rls migration note: {e}")

        # Voicemail tables: add organization_id for multi-tenant isolation
        try:
            with _engine.connect() as conn:
                conn.execute(text("""
                    ALTER TABLE voicemail_drops ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
                    CREATE INDEX IF NOT EXISTS ix_voicemail_drops_organization_id ON voicemail_drops(organization_id);
                    ALTER TABLE voicemail_templates ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
                    CREATE INDEX IF NOT EXISTS ix_voicemail_templates_organization_id ON voicemail_templates(organization_id);
                    ALTER TABLE voicemail_campaigns ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
                    CREATE INDEX IF NOT EXISTS ix_voicemail_campaigns_organization_id ON voicemail_campaigns(organization_id);
                    ALTER TABLE contact_dnc_status ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id);
                    CREATE INDEX IF NOT EXISTS ix_contact_dnc_status_organization_id ON contact_dnc_status(organization_id);
                    ALTER TABLE active_calls ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id);
                    CREATE INDEX IF NOT EXISTS ix_active_calls_organization_id ON active_calls(organization_id);
                """))
                conn.execute(text("""
                    ALTER TABLE voicemail_drops ALTER COLUMN contact_name TYPE TEXT;
                    ALTER TABLE voicemail_drops ALTER COLUMN phone_number TYPE TEXT;
                    ALTER TABLE voicemail_drops ALTER COLUMN contact_email TYPE TEXT;
                """))
                conn.commit()
                logger.info("Voicemail + DNC organization_id columns ready")
        except Exception as e:
            logger.warning(f"Voicemail organization_id migration note: {e}")

        # Ensure tloss@cmgfi.com has full admin permissions
        try:
            with _engine.connect() as conn:
                result = conn.execute(text("""
                    UPDATE users
                    SET permission_role = 'admin', role = 'admin',
                        full_name = CASE WHEN full_name IS NULL OR full_name = 'Demo User' OR full_name = '' THEN 'Tim Loss' ELSE full_name END
                    WHERE email = 'tloss@cmgfi.com'
                """))
                conn.commit()
                if result.rowcount > 0:
                    logger.info("✅ Updated tloss@cmgfi.com to admin permissions")
        except Exception as e:
            logger.warning(f"⚠️ Admin permission fix note: {e}")

        return True
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

def create_sample_data(db: Session):
    """Create sample data for testing"""
    # Lazy imports to avoid circular dependencies
    from database.models import User, Branch, Lead, Loan, AITask, MUMClient, ReferralPartner
    from database.enums import LeadStage, LoanStage, TaskType
    from services.dre_helpers import generate_ai_insights
    import bcrypt as _bcrypt
    def get_password_hash(password):
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

    try:
        # Check if data already exists - check for both demo and admin users
        existing_demo = db.query(User).filter(User.email == "admin@perenniaai.com").first()
        existing_admin = db.query(User).filter(User.email == "admin@perenniaai.com").first()

        if existing_demo or existing_admin:
            logger.info("Sample data already exists")
            return

        # Create demo organization (required for multi-tenant isolation)
        from database.models import Organization
        org = Organization(
            name="Demo Mortgage Company",
            slug="demo-mortgage",
            domain="perenniaai.com",
            subscription_tier="premium",
        )
        db.add(org)
        db.commit()

        # Create demo branch
        branch = Branch(
            name="Main Office",
            company="Demo Mortgage Company",
            nmls_id="123456"
        )
        db.add(branch)
        db.commit()

        # Create demo user
        _demo_pw = os.getenv("DEMO_USER_PASSWORD", "")
        if not _demo_pw:
            raise ValueError("DEMO_USER_PASSWORD env var required")
        demo_user = User(
            email="admin@perenniaai.com",
            hashed_password=get_password_hash(_demo_pw),
            full_name="Admin",
            role="admin",
            permission_role="admin",
            branch_id=branch.id,
            organization_id=org.id,
        )
        db.add(demo_user)
        db.commit()

        # Create sample leads
        sample_leads = [
            Lead(
                name="John Smith",
                email="john.smith@email.com",
                phone="555-0101",
                stage=LeadStage.NEW,
                source="Website",
                loan_type="Purchase",
                preapproval_amount=450000,
                credit_score=750,
                debt_to_income=0.35,
                owner_id=demo_user.id,
                organization_id=org.id,
                ai_score=85,
                sentiment="positive",
                next_action="Schedule initial consultation"
            ),
            Lead(
                name="Sarah Johnson",
                email="sarah.j@email.com",
                phone="555-0102",
                stage=LeadStage.PROSPECT,
                source="Referral",
                loan_type="Refinance",
                preapproval_amount=350000,
                credit_score=720,
                debt_to_income=0.40,
                owner_id=demo_user.id,
                organization_id=org.id,
                ai_score=78,
                sentiment="positive",
                next_action="Send pre-qualification letter"
            ),
            Lead(
                name="Mike Williams",
                email="mike.w@email.com",
                phone="555-0103",
                stage=LeadStage.APPLICATION,
                source="Zillow",
                loan_type="Purchase",
                preapproval_amount=525000,
                credit_score=680,
                debt_to_income=0.42,
                owner_id=demo_user.id,
                organization_id=org.id,
                ai_score=65,
                sentiment="neutral",
                next_action="Collect additional documentation"
            )
        ]

        for lead in sample_leads:
            db.add(lead)
        db.commit()

        # Create sample loans
        sample_loans = [
            Loan(
                loan_number="L2024-001",
                borrower_name="Emily Davis",
                amount=400000,
                stage=LoanStage.PROCESSING,
                program="Conventional",
                loan_type="Purchase",
                rate=6.875,
                term=360,
                property_address="123 Main St, Anytown, CA",
                closing_date=datetime.now(timezone.utc) + timedelta(days=25),
                loan_officer_id=demo_user.id,
                organization_id=org.id,
                processor="Jane Processor",
                days_in_stage=5,
                sla_status="on-track"
            ),
            Loan(
                loan_number="L2024-002",
                borrower_name="Robert Brown",
                amount=550000,
                stage=LoanStage.UW_RECEIVED,
                program="FHA",
                loan_type="Purchase",
                rate=7.125,
                term=360,
                property_address="456 Oak Ave, Somewhere, CA",
                closing_date=datetime.now(timezone.utc) + timedelta(days=18),
                loan_officer_id=demo_user.id,
                organization_id=org.id,
                processor="John Processor",
                underwriter="Sarah UW",
                days_in_stage=3,
                sla_status="on-track"
            )
        ]

        for loan in sample_loans:
            loan.ai_insights = generate_ai_insights(loan)
            db.add(loan)
        db.commit()

        # Create sample tasks
        sample_tasks = [
            AITask(
                title="Review appraisal for L2024-001",
                description="Appraisal came in at $395,000 - need to discuss with borrower",
                type=TaskType.HUMAN_NEEDED,
                category="Documentation",
                priority="high",
                ai_confidence=85,
                borrower_name="Emily Davis",
                loan_id=sample_loans[0].id,
                assigned_to_id=demo_user.id,
                due_date=datetime.now(timezone.utc) + timedelta(days=1)
            ),
            AITask(
                title="Follow up on income verification",
                description="Waiting on 2023 W2 from borrower",
                type=TaskType.IN_PROGRESS,
                category="Documentation",
                priority="medium",
                ai_confidence=92,
                borrower_name="Robert Brown",
                loan_id=sample_loans[1].id,
                assigned_to_id=demo_user.id,
                due_date=datetime.now(timezone.utc) + timedelta(days=3)
            )
        ]

        for task in sample_tasks:
            db.add(task)
        db.commit()

        # Create sample referral partners
        sample_partners = [
            ReferralPartner(
                name="Jane Realtor",
                company="Premier Realty",
                type="Real Estate Agent",
                phone="555-0200",
                email="jane@premierrealty.com",
                referrals_in=15,
                closed_loans=8,
                volume=3200000,
                loyalty_tier="gold",
                status="active"
            ),
            ReferralPartner(
                name="Bob Builder",
                company="Custom Homes Inc",
                type="Builder",
                phone="555-0201",
                email="bob@customhomes.com",
                referrals_in=8,
                closed_loans=5,
                volume=2100000,
                loyalty_tier="silver",
                status="active"
            )
        ]

        for partner in sample_partners:
            db.add(partner)
        db.commit()

        # Create sample MUM clients
        sample_mum = [
            MUMClient(
                client_name="Previous Borrower 1",
                loan_number="L2023-045",
                original_close_date=datetime.now(timezone.utc) - timedelta(days=365),
                closing_date=datetime.now(timezone.utc) - timedelta(days=365),
                first_payment_date=datetime.now(timezone.utc) - timedelta(days=335),
                days_since_funding=365,
                original_rate=7.5,
                current_rate=6.875,
                interest_rate=6.875,
                original_loan_amount=400000,
                current_loan_amount=380000,
                appraisal_value_at_closing=450000,
                current_property_value=465000,
                loan_balance=380000,
                refinance_opportunity=True,
                estimated_savings=2375,
                status="opportunity",
                user_id=demo_user.id,
                organization_id=org.id,
            )
        ]

        for mum in sample_mum:
            db.add(mum)
        db.commit()

        logger.info("✅ Sample data created successfully")
        logger.info(f"   Admin user: admin@perenniaai.com")
        logger.info(f"   Created {len(sample_leads)} leads, {len(sample_loans)} loans, {len(sample_tasks)} tasks")

    except Exception as e:
        logger.error(f"❌ Sample data creation failed: {e}")
        db.rollback()
