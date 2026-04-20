"""
Comprehensive migration to add all missing columns to User, Lead, and Loan tables.
This migration ensures all model columns exist in the production PostgreSQL database.

Run with: python -m migrations.add_all_missing_columns
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")


def run_migration():
    """Run the comprehensive column migration."""
    engine = create_engine(DATABASE_URL)

    print(f"[{datetime.now()}] Starting comprehensive column migration...")
    print(f"Database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")

    with engine.connect() as conn:
        # ================================================================
        # USER TABLE COLUMNS
        # ================================================================
        print("\n=== USER TABLE ===")

        user_columns = [
            ("timezone", "VARCHAR(100)", "'America/New_York'"),
            ("company_logo_url", "TEXT", None),
            ("headshot_url", "TEXT", None),
            ("title", "TEXT", None),
            ("team_name", "TEXT", None),
            ("nmls_id", "VARCHAR(50)", None),
            ("last_activity_at", "TIMESTAMP", None),
            # Account lockout (enterprise security - Check 4.4)
            ("failed_login_attempts", "INTEGER", "0"),
            ("locked_until", "TIMESTAMP", None),
            ("last_failed_login_at", "TIMESTAMP", None),
            # MFA (enterprise security - Check 4.6)
            ("mfa_secret", "VARCHAR", None),
            ("mfa_enabled", "BOOLEAN", "FALSE"),
            ("mfa_backup_codes", "JSONB", None),
            ("mfa_enabled_at", "TIMESTAMP", None),
            # SSO provisioning (Enterprise Check 5.11)
            ("sso_provider", "VARCHAR", None),
            ("sso_subject_id", "VARCHAR", None),
            # Password change tracking (session revocation after password reset)
            ("password_changed_at", "TIMESTAMP WITH TIME ZONE", None),
        ]

        for col_name, col_type, default in user_columns:
            add_column_if_not_exists(conn, "users", col_name, col_type, default)

        # ================================================================
        # ORGANIZATION TABLE COLUMNS
        # ================================================================
        print("\n=== ORGANIZATION TABLE ===")

        org_columns = [
            ("sso_enforced", "BOOLEAN", "FALSE"),
            ("mfa_required", "BOOLEAN", "FALSE"),
        ]

        for col_name, col_type, default in org_columns:
            add_column_if_not_exists(conn, "organizations", col_name, col_type, default)

        # ================================================================
        # API KEYS TABLE COLUMNS
        # ================================================================
        print("\n=== API KEYS TABLE ===")

        api_key_columns = [
            ("scopes", "JSONB", "'[]'"),
            ("description", "VARCHAR", None),
            ("expires_at", "TIMESTAMP", None),
        ]

        for col_name, col_type, default in api_key_columns:
            add_column_if_not_exists(conn, "api_keys", col_name, col_type, default)

        # ================================================================
        # LEAD TABLE COLUMNS
        # ================================================================
        print("\n=== LEAD TABLE ===")

        # SLA Milestone Dates
        lead_datetime_columns = [
            "lead_received_date",
            "first_contact_attempt_date",
            "first_contact_successful_date",
            "lead_qualification_date",
            "application_link_sent_date",
            "application_started_date",
            "application_completed_date",
            "credit_pulled_date",
            "preapproval_submission_date",
            "preapproval_issued_date",
            "preapproval_expiration_date",
            "realtor_referral_date",
            "rate_watch_enrollment_date",
            "initial_consultation_date",
            "expected_purchase_date",
            "last_workflow_action",
            "stage_changed_at",
        ]

        for col_name in lead_datetime_columns:
            add_column_if_not_exists(conn, "leads", col_name, "TIMESTAMP", None)

        # PRD 4.1 - Rate Lock Intelligence fields (enum stored as varchar)
        add_column_if_not_exists(conn, "leads", "buying_timeline_category", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "leads", "borrower_risk_profile", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "leads", "target_payment", "FLOAT", None)

        # PRD 4.3 - Referral Intelligence fields
        add_column_if_not_exists(conn, "leads", "referral_score", "INTEGER", "0")
        add_column_if_not_exists(conn, "leads", "referral_source_score", "INTEGER", "0")
        add_column_if_not_exists(conn, "leads", "employment_referral_flag", "BOOLEAN", "FALSE")
        add_column_if_not_exists(conn, "leads", "manager_flag", "BOOLEAN", "FALSE")
        add_column_if_not_exists(conn, "leads", "employees_managed", "INTEGER", "0")
        add_column_if_not_exists(conn, "leads", "leadership_level", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "leads", "company_size", "INTEGER", None)
        add_column_if_not_exists(conn, "leads", "employer_name", "VARCHAR(255)", None)
        add_column_if_not_exists(conn, "leads", "industry", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "leads", "circle_of_cash_flow_map", "JSONB", None)

        # Workflow tracking
        add_column_if_not_exists(conn, "leads", "current_workflow_id", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "leads", "workflow_day", "INTEGER", "0")
        add_column_if_not_exists(conn, "leads", "nurture_month", "INTEGER", "0")

        # Salesforce Sync Fields - Property
        add_column_if_not_exists(conn, "leads", "occupancy_type", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "leads", "property_county", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "leads", "property_ownership_type", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "leads", "property_units", "INTEGER", None)

        # Salesforce Sync Fields - Financial
        add_column_if_not_exists(conn, "leads", "rate_type", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "leads", "monthly_payment", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "property_tax", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "hazard_insurance", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "mortgage_insurance", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "hoa_amount", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "origination_fee", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "estimated_prepaid_interest", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "index_rate", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "margin", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "loan_purpose", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "leads", "file_state", "VARCHAR(50)", None)

        # Salesforce Sync Fields - 2nd Loan
        add_column_if_not_exists(conn, "leads", "second_loan_amount", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "second_loan_rate", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "second_loan_payment", "FLOAT", None)

        # Salesforce Sync Fields - Housing Expense
        add_column_if_not_exists(conn, "leads", "present_housing_expense", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "proposed_housing_expense", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "present_monthly_payment", "FLOAT", None)
        add_column_if_not_exists(conn, "leads", "proposed_monthly_payment", "FLOAT", None)

        # ================================================================
        # LOAN TABLE COLUMNS
        # ================================================================
        print("\n=== LOAN TABLE ===")

        # PRD 4.2 - Rate Lock Intelligence (enums as varchar)
        add_column_if_not_exists(conn, "loans", "rate_lock_status", "VARCHAR(50)", "'not_eligible'")
        add_column_if_not_exists(conn, "loans", "rate_lock_recommendation", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "loans", "lock_term_days", "INTEGER", None)
        add_column_if_not_exists(conn, "loans", "float_down_available", "BOOLEAN", "FALSE")
        add_column_if_not_exists(conn, "loans", "float_down_terms", "VARCHAR(500)", None)
        add_column_if_not_exists(conn, "loans", "extension_cost_estimate", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "volatility_score", "INTEGER", "50")
        add_column_if_not_exists(conn, "loans", "borrower_risk_profile", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "loans", "lock_score", "INTEGER", None)
        add_column_if_not_exists(conn, "loans", "lock_decision_date", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "lock_decision_notes", "TEXT", None)
        add_column_if_not_exists(conn, "loans", "last_rate_check", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "rate_lock_history", "JSONB", None)

        # Property details
        add_column_if_not_exists(conn, "loans", "property_city", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "loans", "property_state", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "loans", "property_zip", "VARCHAR(20)", None)
        add_column_if_not_exists(conn, "loans", "lender", "VARCHAR(255)", None)

        # Disclosure milestone dates
        add_column_if_not_exists(conn, "loans", "initial_disclosures_sent_date", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "initial_disclosures_signed_date", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "cd_received_signed_date", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "final_closing_package_sent_date", "TIMESTAMP", None)

        # Contract/workflow dates
        add_column_if_not_exists(conn, "loans", "contract_received_date", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "loan_estimate_sent_date", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "conditional_approval_date", "TIMESTAMP", None)

        # AMR (Annual Mortgage Review)
        add_column_if_not_exists(conn, "loans", "last_amr_date", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "next_amr_date", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "refi_opportunity_score", "INTEGER", "0")

        # Workflow tracking
        add_column_if_not_exists(conn, "loans", "current_workflow_id", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "loans", "last_workflow_action", "TIMESTAMP", None)
        add_column_if_not_exists(conn, "loans", "stage_changed_at", "TIMESTAMP", None)

        # Team member fields
        add_column_if_not_exists(conn, "loans", "loan_officer_name", "VARCHAR(255)", None)
        add_column_if_not_exists(conn, "loans", "loan_officer_email", "VARCHAR(255)", None)
        add_column_if_not_exists(conn, "loans", "processor_email", "VARCHAR(255)", None)
        add_column_if_not_exists(conn, "loans", "underwriter_email", "VARCHAR(255)", None)
        add_column_if_not_exists(conn, "loans", "closer", "VARCHAR(255)", None)
        add_column_if_not_exists(conn, "loans", "closer_email", "VARCHAR(255)", None)

        # SLA Date Fields (Jungo mappings) - using DATE type
        loan_date_columns = [
            "prospect_date",
            "application_date",
            "le_pending_date",
            "credit_only_date",
            "file_received_date",
            "preapproval_date",
            "uw_received_date",
            "conditions_for_review_date",
            "suspended_date",
            "loan_approved_date",
            "approved_not_accepted_date",
            "approval_expires_date",
            "appraisal_received_date",
            "appraisal_docs_expire_date",
            "cd_requested_date",
            "cd_sent_to_borrower_date",
            "cd_acknowledged_date",
            "clear_to_close_date",
            "docs_ordered_date",
            "docs_out_date",
            "credit_docs_expire_date",
            "scheduled_closing_date",
            "scheduled_funding_date",
            "funds_ordered_date",
            "funds_sent_date",
            "first_payment_date",
            "investor_purchased_date",
            "withdrawn_date",
        ]

        for col_name in loan_date_columns:
            add_column_if_not_exists(conn, "loans", col_name, "DATE", None)

        # Salesforce Sync Fields - Property
        add_column_if_not_exists(conn, "loans", "property_type", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "loans", "occupancy_type", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "loans", "property_county", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "loans", "property_ownership_type", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "loans", "property_units", "INTEGER", None)

        # Salesforce Sync Fields - Financial
        add_column_if_not_exists(conn, "loans", "rate_type", "VARCHAR(50)", None)
        add_column_if_not_exists(conn, "loans", "monthly_payment", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "property_tax", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "hazard_insurance", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "mortgage_insurance", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "hoa_amount", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "origination_fee", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "estimated_prepaid_interest", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "points", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "index_rate", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "margin", "FLOAT", None)

        # Salesforce Sync Fields - LTV
        add_column_if_not_exists(conn, "loans", "ltv", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "cltv", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "loan_purpose", "VARCHAR(100)", None)
        add_column_if_not_exists(conn, "loans", "file_state", "VARCHAR(50)", None)

        # Salesforce Sync Fields - 2nd Loan
        add_column_if_not_exists(conn, "loans", "second_loan_amount", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "second_loan_rate", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "second_loan_payment", "FLOAT", None)

        # Salesforce Sync Fields - Housing Expense
        add_column_if_not_exists(conn, "loans", "present_housing_expense", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "proposed_housing_expense", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "present_monthly_payment", "FLOAT", None)
        add_column_if_not_exists(conn, "loans", "proposed_monthly_payment", "FLOAT", None)

        conn.commit()

    print(f"\n[{datetime.now()}] Migration completed successfully!")
    return True


def add_column_if_not_exists(conn, table: str, column: str, col_type: str, default):
    """Add a column to a table if it doesn't already exist."""
    try:
        # Check if column exists
        result = conn.execute(text(f"""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
        """), {"table": table, "column": column})

        if result.fetchone() is None:
            # Column doesn't exist, add it
            default_clause = f" DEFAULT {default}" if default else ""
            sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"
            conn.execute(text(sql))
            print(f"  + Added {table}.{column} ({col_type})")
        else:
            print(f"  - {table}.{column} already exists")

    except Exception as e:
        print(f"  ! Error adding {table}.{column}: {e}")


if __name__ == "__main__":
    try:
        success = run_migration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)
