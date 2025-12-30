"""
Add Flood Insurance and Comprehensive Milestone Dates Migration

Adds:
1. Flood Insurance processing fields to lead_profiles and active_loan_profiles
2. Processing log items (appraisal, title, hazard, flood, credit) with full tracking
3. Comprehensive milestone status dates from loan processing workflow
4. Lock information fields
5. Follow up tracking fields
6. Additional important dates

Run with: python migrations/add_flood_insurance_and_milestone_dates.py
"""

import os
import logging
from sqlalchemy import create_engine, text, inspect

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
                    return line.strip().split('=', 1)[1]

    return "sqlite:///./mortgage_crm.db"


def is_postgresql(database_url):
    """Check if database is PostgreSQL."""
    return database_url.startswith('postgresql') or database_url.startswith('postgres')


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    try:
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def table_exists(conn, table_name):
    """Check if a table exists."""
    inspector = inspect(conn)
    return table_name in inspector.get_table_names()


def add_column_if_not_exists(conn, table_name, column_name, column_type, is_pg=False):
    """Add a column to a table if it doesn't exist."""
    if not column_exists(conn, table_name, column_name):
        try:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
            print(f"    Added {column_name} to {table_name}")
            return True
        except Exception as e:
            print(f"    Warning: Could not add {column_name}: {e}")
            return False
    else:
        return False


def run_migration():
    """Execute the migration."""
    database_url = get_database_url()
    print(f"Using database: {database_url[:50]}...")

    is_pg = is_postgresql(database_url)
    print(f"Database type: {'PostgreSQL' if is_pg else 'SQLite'}")

    engine = create_engine(database_url)

    print("\nRunning Flood Insurance and Milestone Dates migration...")

    # Column definitions for both tables
    # Format: (column_name, pg_type, sqlite_type)
    processing_log_columns = [
        # Appraisal Processing
        ("appraisal_ordered_date", "DATE", "DATE"),
        ("appraisal_due_date", "DATE", "DATE"),
        ("appraisal_received_date", "DATE", "DATE"),
        ("appraisal_submitted_date", "DATE", "DATE"),
        ("appraisal_cleared_date", "DATE", "DATE"),
        ("appraisal_days", "INTEGER", "INTEGER"),
        ("appraisal_expiration_date", "DATE", "DATE"),
        ("appraisal_scheduled_date", "DATE", "DATE"),
        ("appraisal_completed_date", "DATE", "DATE"),

        # Title Processing
        ("title_ordered_date", "DATE", "DATE"),
        ("title_due_date", "DATE", "DATE"),
        ("title_received_date", "DATE", "DATE"),
        ("title_submitted_date", "DATE", "DATE"),
        ("title_cleared_date", "DATE", "DATE"),
        ("title_days", "INTEGER", "INTEGER"),
        ("title_expiration_date", "DATE", "DATE"),

        # Hazard Insurance Processing
        ("hazard_insurance_ordered_date", "DATE", "DATE"),
        ("hazard_insurance_due_date", "DATE", "DATE"),
        ("hazard_insurance_received_date", "DATE", "DATE"),
        ("hazard_insurance_submitted_date", "DATE", "DATE"),
        ("hazard_insurance_cleared_date", "DATE", "DATE"),
        ("hazard_insurance_days", "INTEGER", "INTEGER"),
        ("hazard_insurance_expiration_date", "DATE", "DATE"),

        # Flood Insurance Processing (NEW)
        ("flood_insurance_ordered_date", "DATE", "DATE"),
        ("flood_insurance_due_date", "DATE", "DATE"),
        ("flood_insurance_received_date", "DATE", "DATE"),
        ("flood_insurance_submitted_date", "DATE", "DATE"),
        ("flood_insurance_cleared_date", "DATE", "DATE"),
        ("flood_insurance_days", "INTEGER", "INTEGER"),
        ("flood_insurance_expiration_date", "DATE", "DATE"),

        # Credit Processing
        ("credit_ordered_date", "DATE", "DATE"),
        ("credit_due_date", "DATE", "DATE"),
        ("credit_received_date", "DATE", "DATE"),
        ("credit_submitted_date", "DATE", "DATE"),
        ("credit_cleared_date", "DATE", "DATE"),
        ("credit_days", "INTEGER", "INTEGER"),
        ("credit_expiration_date", "DATE", "DATE"),
    ]

    important_dates_columns = [
        ("date_file_created", "TIMESTAMP", "TIMESTAMP"),
        ("preapproval_application_date", "DATE", "DATE"),
        ("application_date", "DATE", "DATE"),
        ("scheduled_approval_date", "DATE", "DATE"),
        ("signing_appt_confirmed", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
        ("signing_location", "VARCHAR(255)", "VARCHAR(255)"),
        ("signing_date", "DATE", "DATE"),
        ("signing_time", "VARCHAR(20)", "VARCHAR(20)"),
        ("scheduled_closing_date", "DATE", "DATE"),
        ("scheduled_funding_date", "DATE", "DATE"),
        ("approval_expires_date", "DATE", "DATE"),
        ("credit_docs_expire_date", "DATE", "DATE"),
        ("appraisal_docs_expire_date", "DATE", "DATE"),
    ]

    milestone_status_columns = [
        ("registered_date", "DATE", "DATE"),
        ("advance_lock_date", "DATE", "DATE"),
        ("prospect_date", "DATE", "DATE"),
        ("le_pending_date", "DATE", "DATE"),
        ("credit_only_date", "DATE", "DATE"),
        ("disclosed_date", "DATE", "DATE"),
        ("file_received_date", "DATE", "DATE"),
        ("canceled_for_incompleteness_date", "DATE", "DATE"),
        ("corr_incomplete_submission_date", "DATE", "DATE"),
        ("uw_received_date", "DATE", "DATE"),
        ("pre_approved_date", "DATE", "DATE"),
        ("withdrawn_date", "DATE", "DATE"),
        ("approved_date", "DATE", "DATE"),
        ("approved_not_accepted_date", "DATE", "DATE"),
        ("corr_credit_audit_in_process_date", "DATE", "DATE"),
        ("corr_credit_only_completed_date", "DATE", "DATE"),
        ("corr_legal_audit_in_process_date", "DATE", "DATE"),
        ("suspended_date", "DATE", "DATE"),
        ("corr_audit_complete_conditions_date", "DATE", "DATE"),
        ("conditions_for_review_date", "DATE", "DATE"),
        ("clear_to_close_date", "DATE", "DATE"),
        ("docs_ordered_date", "DATE", "DATE"),
        ("docs_out_date", "DATE", "DATE"),
        ("docs_back_date", "DATE", "DATE"),
        ("corr_ready_for_purchase_date", "DATE", "DATE"),
        ("funds_ordered_date", "DATE", "DATE"),
        ("funds_sent_date", "DATE", "DATE"),
        ("funded_date", "DATE", "DATE"),
        ("purchased_date", "DATE", "DATE"),
        ("investor_purchased_date", "DATE", "DATE"),
        ("shipped_date", "DATE", "DATE"),
        ("post_closing_completed_date", "DATE", "DATE"),
        ("changes_to_uw_date", "DATE", "DATE"),
        ("loan_restructure_date", "DATE", "DATE"),
        ("msr_date", "DATE", "DATE"),
        ("private_loan_funded_date", "DATE", "DATE"),
        ("asset_loan_date", "DATE", "DATE"),
        ("lock_and_list_date", "DATE", "DATE"),
        ("sandbox_date", "DATE", "DATE"),
        ("declined_date", "DATE", "DATE"),
    ]

    follow_up_columns = [
        ("follow_up_date", "DATE", "DATE"),
        ("follow_up_flag", "VARCHAR(100)", "VARCHAR(100)"),
        ("exclude_from_custom_reports", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
    ]

    lock_info_columns = [
        ("lock_days", "INTEGER", "INTEGER"),
        ("lock_ext_1_date", "DATE", "DATE"),
        ("lock_ext_2_date", "DATE", "DATE"),
        ("lock_ext_3_date", "DATE", "DATE"),
        ("date_locked", "TIMESTAMP", "TIMESTAMP"),
        ("lock_exp_date", "DATE", "DATE"),
        ("floating", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
        ("date_canceled", "DATE", "DATE"),
    ]

    additional_dates_columns = [
        ("cd_requested_date", "DATE", "DATE"),
        ("original_approved_date", "DATE", "DATE"),
        ("le_pending_details", "VARCHAR(255)", "VARCHAR(255)"),
        ("disbursement_date", "DATE", "DATE"),
        ("commitment_date", "DATE", "DATE"),
        ("commitment_date_met", "DATE", "DATE"),
        ("original_disclosed_date", "DATE", "DATE"),
        ("has_six_app_data_points", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
        ("cancelled_denied_coronavirus", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
    ]

    legacy_milestone_columns = [
        ("contract_received_date", "DATE", "DATE"),
        ("insurance_ordered_date", "DATE", "DATE"),
        ("insurance_received_date", "DATE", "DATE"),
        ("initial_disclosures_sent_date", "DATE", "DATE"),
        ("initial_disclosures_signed_date", "DATE", "DATE"),
        ("processor_submission_date", "DATE", "DATE"),
        ("underwriting_submission_date", "DATE", "DATE"),
        ("conditional_approval_date", "DATE", "DATE"),
        ("conditions_sent_date", "DATE", "DATE"),
        ("conditions_received_date", "DATE", "DATE"),
        ("resubmission_date", "DATE", "DATE"),
        ("rate_lock_date", "DATE", "DATE"),
        ("rate_lock_expiration_date", "DATE", "DATE"),
        ("rate_lock_extension_date", "DATE", "DATE"),
        ("float_down_trigger_date", "DATE", "DATE"),
        ("closing_disclosure_sent_date", "DATE", "DATE"),
        ("cd_received_signed_date", "DATE", "DATE"),
        ("cd_delivered_date", "DATE", "DATE"),
        ("final_cd_issue_date", "DATE", "DATE"),
        ("final_closing_package_sent_date", "DATE", "DATE"),
        ("closing_scheduled_date", "DATE", "DATE"),
        ("funding_date", "DATE", "DATE"),
    ]

    # Combine all columns
    all_columns = (
        processing_log_columns +
        important_dates_columns +
        milestone_status_columns +
        follow_up_columns +
        lock_info_columns +
        additional_dates_columns +
        legacy_milestone_columns
    )

    with engine.connect() as conn:
        # Process both tables
        for table_name in ['lead_profiles', 'active_loan_profiles']:
            if not table_exists(conn, table_name):
                print(f"\nWARNING: {table_name} table does not exist. Skipping.")
                continue

            print(f"\n  Processing {table_name}...")
            added_count = 0

            for column_name, pg_type, sqlite_type in all_columns:
                col_type = pg_type if is_pg else sqlite_type
                if add_column_if_not_exists(conn, table_name, column_name, col_type, is_pg):
                    added_count += 1

            print(f"    Added {added_count} new columns to {table_name}")

        conn.commit()

    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
    print("\nNew fields added:")
    print("  - Flood Insurance: ordered, due, received, submitted, cleared, days, expiration")
    print("  - Processing Log: appraisal, title, hazard, flood, credit tracking")
    print("  - Milestone Status: 40+ workflow milestone dates")
    print("  - Lock Information: lock days, extensions, floating status")
    print("  - Follow Up: date, flag, exclude from reports")
    print("  - Additional: CD requested, disbursement, commitment dates")
    logger.info("Flood Insurance and Milestone Dates migration completed")


def rollback_migration():
    """Rollback information (columns cannot be easily dropped in SQLite)."""
    print("Rollback information:")
    print("  - SQLite does not support DROP COLUMN directly")
    print("  - For PostgreSQL, you would need to manually drop each column")
    print("  - It's recommended to restore from backup if rollback is needed")
    print("\nTo rollback in PostgreSQL, run:")
    print("  ALTER TABLE lead_profiles DROP COLUMN flood_insurance_ordered_date;")
    print("  ... (repeat for each column)")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        run_migration()
