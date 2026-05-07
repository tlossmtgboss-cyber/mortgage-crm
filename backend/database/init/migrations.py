"""
Column Migrations - ALTER TABLE statements, enum updates, and data fixups.

Adds missing columns to existing tables and updates PostgreSQL enum types.
All statements are idempotent (IF NOT EXISTS / DO $$ guards).
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_column_migrations(engine, database_url: str):
    """
    Run all column migrations for existing tables.

    Only runs PostgreSQL-specific migrations (skips SQLite).
    """
    if database_url.startswith("sqlite"):
        return

    _migrate_user_columns(engine)
    _migrate_lead_columns(engine)
    _migrate_lead_columns_batch2(engine)
    _migrate_task_columns(engine)
    _migrate_loan_columns(engine)
    _migrate_referral_partner_columns(engine)
    _migrate_workflow_columns(engine)
    _migrate_enum_types(engine)
    _migrate_data_fixups(engine)
    _migrate_mum_client_columns(engine)
    _migrate_enterprise_security_columns(engine)
    _migrate_milestone_columns(engine)
    _migrate_ai_attribution_columns(engine)
    _migrate_audit_log_columns(engine)
    _migrate_subscription_columns(engine)
    _migrate_branding_columns(engine)
    _migrate_branding_consolidation(engine)
    _migrate_loan_state_columns(engine)
    _migrate_workflow_engine_columns(engine)
    _migrate_production_assistant_columns(engine)


def _migrate_user_columns(engine):
    """Add missing columns to users table."""
    try:
        with engine.connect() as conn:
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
            logger.info("User profile columns added/verified")
    except Exception as e:
        logger.warning(f"User profile columns migration: {e}")


def _migrate_lead_columns(engine):
    """Add missing columns to leads table (batch 1 - property, financial, loan details, etc.)."""
    try:
        with engine.connect() as conn:
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
                -- Buying timeline and risk profile
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

            # FUB integration columns
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

            conn.commit()
            logger.info("Lead columns (batch 1) added/verified")
    except Exception as e:
        logger.warning(f"Lead columns (batch 1) migration: {e}")


def _migrate_lead_columns_batch2(engine):
    """Add missing columns to leads table (batch 2 - co-applicant, additional fields)."""
    try:
        with engine.connect() as conn:
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

            conn.commit()
            logger.info("Lead columns (batch 2) added/verified")
    except Exception as e:
        logger.warning(f"Lead columns (batch 2) migration: {e}")


def _migrate_task_columns(engine):
    """Add missing columns to tasks table."""
    try:
        with engine.connect() as conn:
            # email_intake_id for document intake
            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='email_intake_id') THEN
                        ALTER TABLE tasks ADD COLUMN email_intake_id INTEGER;
                    END IF;
                END $$;
            """))

            # SF disposition columns
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

            conn.commit()
            logger.info("Task columns added/verified")
    except Exception as e:
        logger.warning(f"Task columns migration: {e}")


def _migrate_loan_columns(engine):
    """Add missing columns to loans table (appraisal, rate lock, milestone dates, team, etc.)."""
    try:
        with engine.connect() as conn:
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

            conn.commit()
            logger.info("Loan columns added/verified")
    except Exception as e:
        logger.warning(f"Loan columns migration: {e}")


def _migrate_referral_partner_columns(engine):
    """Add missing columns to referral_partners table."""
    try:
        with engine.connect() as conn:
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
            conn.commit()
            logger.info("Referral partner columns added/verified")
    except Exception as e:
        logger.warning(f"Referral partner columns migration: {e}")


def _migrate_workflow_columns(engine):
    """Add missing columns to workflow tables (day_configs, role_assignments)."""
    try:
        with engine.connect() as conn:
            # role_responsibilities for dynamic workflow roles
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

            # role_id for dynamic roles
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

            # Make legacy 'role' column nullable
            conn.execute(text("""
                DO $$
                BEGIN
                    ALTER TABLE workflow_role_assignments ALTER COLUMN role DROP NOT NULL;
                EXCEPTION
                    WHEN others THEN NULL;
                END $$;
            """))

            # AM/PM communication method columns for Lead Purchase workflow
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='workflow_day_configs') THEN
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='phone_am_enabled') THEN
                            ALTER TABLE workflow_day_configs ADD COLUMN phone_am_enabled BOOLEAN DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='phone_pm_enabled') THEN
                            ALTER TABLE workflow_day_configs ADD COLUMN phone_pm_enabled BOOLEAN DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='text_am_enabled') THEN
                            ALTER TABLE workflow_day_configs ADD COLUMN text_am_enabled BOOLEAN DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='text_pm_enabled') THEN
                            ALTER TABLE workflow_day_configs ADD COLUMN text_pm_enabled BOOLEAN DEFAULT FALSE;
                        END IF;
                    END IF;
                END $$;
            """))

            conn.commit()
            logger.info("Workflow columns added/verified")
    except Exception as e:
        logger.warning(f"Workflow columns migration: {e}")

    # concierge_responsible column
    try:
        with engine.connect() as conn:
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
            logger.info("Workflow concierge_responsible column added")
    except Exception as e:
        logger.warning(f"Workflow concierge_responsible migration: {e}")

    # Weekly task scheduling columns
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='workflow_day_configs') THEN
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_weekly') THEN
                            ALTER TABLE workflow_day_configs ADD COLUMN repeat_weekly BOOLEAN DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_day_of_week') THEN
                            ALTER TABLE workflow_day_configs ADD COLUMN repeat_day_of_week INTEGER;
                        END IF;
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='workflow_day_configs' AND column_name='repeat_until_status') THEN
                            ALTER TABLE workflow_day_configs ADD COLUMN repeat_until_status JSONB DEFAULT '[]'::jsonb;
                        END IF;
                    END IF;
                END $$;
            """))
            conn.commit()
            logger.info("Weekly task scheduling columns added to workflow_day_configs")
    except Exception as e:
        logger.warning(f"Weekly task scheduling migration: {e}")


def _migrate_enum_types(engine):
    """Update PostgreSQL enum types with missing values."""
    # Add all missing loanstage enum values
    try:
        raw_conn = engine.raw_connection()
        raw_conn.set_isolation_level(0)  # AUTOCOMMIT required for ALTER TYPE ADD VALUE
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
        logger.info("Ensured all loanstage enum values exist")
    except Exception as enum_e:
        logger.warning(f"loanstage enum migration: {enum_e}")

    # Add concierge to TaskResponsibility enum
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                DO $$
                BEGIN
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
            logger.info("TaskResponsibility enum updated with concierge")
    except Exception as e:
        logger.warning(f"TaskResponsibility enum migration: {e}")


def _migrate_data_fixups(engine):
    """Fix invalid data in existing tables."""
    try:
        with engine.connect() as conn:
            # Fix invalid Application stage values
            result = conn.execute(text("""
                UPDATE leads
                SET stage = 'Application'
                WHERE stage = 'Application'
            """))
            if result.rowcount > 0:
                logger.info(f"Fixed {result.rowcount} leads with invalid Application stage")

            # Fix null stages - set to New
            result2 = conn.execute(text("""
                UPDATE leads
                SET stage = 'New'
                WHERE stage IS NULL
            """))
            if result2.rowcount > 0:
                logger.info(f"Fixed {result2.rowcount} leads with null stage")

            conn.commit()
    except Exception as e:
        logger.warning(f"Data fixups migration: {e}")


def _migrate_mum_client_columns(engine):
    """Add valuation/refi columns to mum_clients table."""
    try:
        with engine.connect() as conn:
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
            logger.info("MUM client valuation/refi columns added")
    except Exception as e:
        logger.warning(f"MUM valuation columns migration note: {e}")


def _migrate_enterprise_security_columns(engine):
    """Add enterprise security columns (account lockout, MFA, SSO) to users, organizations, api_keys."""
    try:
        with engine.connect() as conn:
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
            """))
            conn.execute(text("""
                ALTER TABLE organizations ADD COLUMN IF NOT EXISTS sso_enforced BOOLEAN DEFAULT FALSE;
                ALTER TABLE organizations ADD COLUMN IF NOT EXISTS mfa_required BOOLEAN DEFAULT FALSE;
            """))
            conn.execute(text("""
                ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS scopes JSONB DEFAULT '[]';
                ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS description VARCHAR;
                ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;
            """))
            conn.commit()
            logger.info("Enterprise security columns added (users, organizations, api_keys)")
    except Exception as e:
        logger.warning(f"Enterprise security columns note: {e}")


def _migrate_milestone_columns(engine):
    """Add milestone + mum_date columns to loans/leads (required by ORM model)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE loans ADD COLUMN IF NOT EXISTS current_milestone_status VARCHAR(50);
                ALTER TABLE loans ADD COLUMN IF NOT EXISTS current_milestone_entered_at TIMESTAMPTZ;
                ALTER TABLE loans ADD COLUMN IF NOT EXISTS mum_date TIMESTAMPTZ;
                ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_milestone_status VARCHAR(50);
                ALTER TABLE leads ADD COLUMN IF NOT EXISTS current_milestone_entered_at TIMESTAMPTZ;
            """))
            conn.commit()
            logger.info("Milestone + mum_date columns added (loans, leads)")
    except Exception as e:
        logger.warning(f"Milestone columns note: {e}")


def _migrate_ai_attribution_columns(engine):
    """Add AI content attribution columns to ai_conversation_memory (AI-005)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE ai_conversation_memory ADD COLUMN IF NOT EXISTS is_ai_generated BOOLEAN DEFAULT FALSE;
                ALTER TABLE ai_conversation_memory ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50);
                ALTER TABLE ai_conversation_memory ADD COLUMN IF NOT EXISTS ai_confidence INTEGER;
            """))
            conn.commit()
            logger.info("AI content attribution columns added (ai_conversation_memory)")
    except Exception as e:
        logger.warning(f"AI attribution columns note: {e}")


def _migrate_audit_log_columns(engine):
    """Add organization_id and make user_id nullable on audit_logs."""
    # Add organization_id (ISO-014)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id);
                CREATE INDEX IF NOT EXISTS ix_audit_logs_organization_id ON audit_logs(organization_id);
            """))
            conn.commit()
            logger.info("audit_logs: organization_id column added")
    except Exception as e:
        logger.warning(f"audit_logs organization_id migration note: {e}")

    # Make user_id and changed_by_id nullable for system-level events
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE audit_logs ALTER COLUMN user_id DROP NOT NULL;
                ALTER TABLE audit_logs ALTER COLUMN changed_by_id DROP NOT NULL;
            """))
            conn.commit()
            logger.info("audit_logs: user_id/changed_by_id made nullable for system events")
    except Exception as e:
        logger.warning(f"audit_logs nullable migration note: {e}")


def _migrate_subscription_columns(engine):
    """Add grace_period_ends_at to subscriptions (LIC-006)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS grace_period_ends_at TIMESTAMP;
            """))
            conn.commit()
            logger.info("subscriptions: grace_period_ends_at column added")
    except Exception as e:
        logger.warning(f"subscriptions grace_period migration note: {e}")


def _migrate_branding_columns(engine):
    """Add white-label branding columns (Enterprise Readiness Domain 12)."""
    try:
        with engine.connect() as conn:
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
            logger.info("White-label branding columns added (ER-12)")
    except Exception as e:
        logger.warning(f"Branding columns note: {e}")


def _migrate_branding_consolidation(engine):
    """Add columns from WhiteLabelConfig model to organization_branding (ER-12 unified).

    Previously branding data lived in two tables: organization_branding (flat
    columns for service layer) and smart_docs_white_label_configs (ORM model).
    Consolidated May 2026 into organization_branding as single source of truth.
    """
    try:
        with engine.connect() as conn:
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
            logger.info("Branding consolidation columns added (ER-12 unified)")
    except Exception as e:
        logger.warning(f"Branding consolidation note: {e}")


def _migrate_loan_state_columns(engine):
    """Add salesforce_raw_stage to loans table."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_raw_stage VARCHAR(200)
            """))
            conn.commit()
            logger.info("Loan state reconciliation: salesforce_raw_stage column added")
    except Exception as e:
        logger.warning(f"Loan state reconciliation migration note: {e}")


def _migrate_workflow_engine_columns(engine):
    """Add escalation_level and workflow_instance_id to workflow_task_instances."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE workflow_task_instances ADD COLUMN IF NOT EXISTS escalation_level INTEGER DEFAULT 0
            """))
            conn.execute(text("""
                ALTER TABLE workflow_task_instances ADD COLUMN IF NOT EXISTS workflow_instance_id INTEGER
            """))
            conn.commit()
            logger.info("Workflow engine columns added (escalation_level, workflow_instance_id)")
    except Exception as e:
        logger.warning(f"Workflow engine columns note: {e}")


def _migrate_production_assistant_columns(engine):
    """Add production_assistant column to leads and loans."""
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE leads ADD COLUMN IF NOT EXISTS production_assistant VARCHAR"))
            conn.execute(text("ALTER TABLE loans ADD COLUMN IF NOT EXISTS production_assistant VARCHAR"))
            conn.commit()
            logger.info("Added production_assistant column to leads and loans")
    except Exception as e:
        logger.warning(f"production_assistant column migration note: {e}")
