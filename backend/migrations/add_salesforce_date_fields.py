"""
Salesforce Date Fields Migration
Adds additional date fields from Jungo Custom Byte Mappings to support workflow automation
"""
import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def run_migration():
    """Add Salesforce date fields to the database."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    engine = create_engine(database_url)

    # Detect database type
    is_sqlite = "sqlite" in database_url.lower()

    # Column additions for loans/portal_loans table
    # These map to Jungo Custom Byte Mappings:
    # - Appraisal Ordered Date, Appraisal Received Date (already exist)
    # - CD Acknowledged Date, First Payment Date, Prospect Date, LE Pending Date (new)

    loan_table_columns = [
        ("cd_acknowledged_date", "DATE"),
        ("first_payment_date", "DATE"),
        ("prospect_date", "DATE"),
        ("le_pending_date", "DATE"),
    ]

    # Column additions for active_loan_profiles table
    active_loan_columns = [
        ("cd_acknowledged_date", "DATE"),
        ("first_payment_date", "DATE"),
        ("prospect_date", "DATE"),
        ("le_pending_date", "DATE"),
    ]

    with engine.connect() as conn:
        # Add columns to loans table
        for col_name, col_type in loan_table_columns:
            try:
                if is_sqlite:
                    conn.execute(text(f"ALTER TABLE loans ADD COLUMN {col_name} {col_type}"))
                else:
                    conn.execute(text(f"ALTER TABLE loans ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                logger.info(f"Added column {col_name} to loans table")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(f"Column {col_name} already exists in loans table")
                else:
                    logger.warning(f"Could not add {col_name} to loans: {e}")

        # Add columns to portal_loans table
        for col_name, col_type in loan_table_columns:
            try:
                if is_sqlite:
                    conn.execute(text(f"ALTER TABLE portal_loans ADD COLUMN {col_name} {col_type}"))
                else:
                    conn.execute(text(f"ALTER TABLE portal_loans ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                logger.info(f"Added column {col_name} to portal_loans table")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(f"Column {col_name} already exists in portal_loans table")
                else:
                    logger.warning(f"Could not add {col_name} to portal_loans: {e}")

        # Add columns to active_loan_profiles table
        for col_name, col_type in active_loan_columns:
            try:
                if is_sqlite:
                    conn.execute(text(f"ALTER TABLE active_loan_profiles ADD COLUMN {col_name} {col_type}"))
                else:
                    conn.execute(text(f"ALTER TABLE active_loan_profiles ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                logger.info(f"Added column {col_name} to active_loan_profiles table")
            except Exception as e:
                if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                    logger.info(f"Column {col_name} already exists in active_loan_profiles table")
                else:
                    logger.warning(f"Could not add {col_name} to active_loan_profiles: {e}")

        conn.commit()
        logger.info("Salesforce date fields migration completed successfully")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
