"""
Jungo Custom Byte Mappings - All 33 Date Fields Migration
Adds all date fields from Jungo/Salesforce for SLA workflow automation
"""
import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

# All 33 Jungo date field columns (excluding ones already added)
JUNGO_DATE_COLUMNS = [
    # Lead & Application Phase
    "prospect_date",
    "application_date",
    "le_pending_date",
    "credit_only_date",
    "file_received_date",
    "preapproval_date",

    # Lock Phase
    "lock_date",
    "lock_expiration_date",

    # Processing & Underwriting Phase
    "uw_received_date",
    "conditions_for_review_date",
    "suspended_date",
    "loan_approved_date",
    "approved_not_accepted_date",
    "approval_expires_date",

    # Appraisal Phase
    "appraisal_ordered_date",
    "appraisal_received_date",
    "appraisal_docs_expire_date",

    # Closing Disclosure Phase
    "cd_requested_date",
    "cd_sent_to_borrower_date",
    "cd_acknowledged_date",

    # Clear to Close & Docs Phase
    "clear_to_close_date",
    "docs_ordered_date",
    "docs_out_date",
    "credit_docs_expire_date",

    # Funding Phase
    "scheduled_closing_date",
    "scheduled_funding_date",
    "funds_ordered_date",
    "funds_sent_date",
    "funded_date",
    "closing_date",
    "first_payment_date",

    # Post-Closing
    "investor_purchased_date",

    # Status Changes
    "withdrawn_date",
    "contract_received_date",
]


def run_migration():
    """Add all Jungo date fields to the database."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url.lower()

    tables = ["loans", "portal_loans", "active_loan_profiles"]

    with engine.connect() as conn:
        for table in tables:
            logger.info(f"Adding Jungo date columns to {table}...")
            added = 0
            skipped = 0

            for col_name in JUNGO_DATE_COLUMNS:
                try:
                    if is_sqlite:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} DATE"))
                    else:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} DATE"))
                    added += 1
                except Exception as e:
                    error_str = str(e).lower()
                    if "duplicate column" in error_str or "already exists" in error_str:
                        skipped += 1
                    elif "no such table" in error_str:
                        logger.warning(f"Table {table} does not exist, skipping")
                        break
                    else:
                        logger.warning(f"Could not add {col_name} to {table}: {e}")

            conn.commit()
            logger.info(f"  {table}: {added} added, {skipped} already existed")

        logger.info("Jungo date fields migration completed successfully")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv
    load_dotenv()
    run_migration()
