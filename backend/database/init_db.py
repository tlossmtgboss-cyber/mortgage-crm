"""
Database Initialization & Schema Migrations

Extracted from inline_legacy_routes.py.
Handles table creation, schema migrations (ALTER TABLE ADD COLUMN),
enum type updates, and sample data creation.
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
            logger.info("ℹ️ Skipping Base.metadata.create_all() in production - use Alembic migrations")
        else:
            _Base.metadata.create_all(bind=_engine)
            logger.info("✅ Database tables created successfully")

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
                            except Exception:
                                pass
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
                            twilio_sid VARCHAR,
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
                    logger.info("✅ Telephony tables created/verified")

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

        # Run comprehensive column migration for all missing columns
        try:
            from migrations.add_all_missing_columns import run_migration
            run_migration()
            logger.info("✅ Comprehensive column migration completed")
        except Exception as e:
            logger.warning(f"⚠️ Comprehensive migration note: {e}")

        return True
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False

def create_sample_data(db: Session):
    """Create sample data for testing"""
    # Lazy imports to avoid circular dependencies
    from database.models import User, Branch, Lead, Loan, AITask, MUMClient
    from database.enums import LeadStage, LoanStage
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    def get_password_hash(password):
        return pwd_context.hash(password)

    try:
        # Check if data already exists - check for both demo and admin users
        existing_demo = db.query(User).filter(User.email == "admin@perenniaai.com").first()
        existing_admin = db.query(User).filter(User.email == "admin@perenniaai.com").first()

        if existing_demo or existing_admin:
            logger.info("Sample data already exists")
            return

        # Create demo branch
        branch = Branch(
            name="Main Office",
            company="Demo Mortgage Company",
            nmls_id="123456"
        )
        db.add(branch)
        db.commit()

        # Create demo user
        demo_user = User(
            email="admin@perenniaai.com",
            hashed_password=get_password_hash(os.getenv("DEMO_USER_PASSWORD", "demo123")),
            full_name="Demo User",
            role="loan_officer",
            branch_id=branch.id
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
                ai_score=78,
                sentiment="positive",
                next_action="Send pre-qualification letter"
            ),
            Lead(
                name="Mike Williams",
                email="mike.w@email.com",
                phone="555-0103",
                stage=LeadStage.Application,
                source="Zillow",
                loan_type="Purchase",
                preapproval_amount=525000,
                credit_score=680,
                debt_to_income=0.42,
                owner_id=demo_user.id,
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
                name="Previous Borrower 1",
                loan_number="L2023-045",
                original_close_date=datetime.now(timezone.utc) - timedelta(days=365),
                days_since_funding=365,
                original_rate=7.5,
                current_rate=6.875,
                loan_balance=380000,
                refinance_opportunity=True,
                estimated_savings=2375,
                status="opportunity"
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
