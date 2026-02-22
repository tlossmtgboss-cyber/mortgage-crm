"""
Migration: Convert Float columns to Numeric for financial precision.

Dollar amounts: Float → NUMERIC(18,2)
Rates/percentages: Float → NUMERIC(8,4)

Run: python -m migrations.convert_float_to_numeric
"""
import os
import sys
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# Column definitions: (table, column, target_type)
DOLLAR_COLUMNS = [
    # leads table
    ("leads", "preapproval_amount"),
    ("leads", "property_value"),
    ("leads", "down_payment"),
    ("leads", "annual_income"),
    ("leads", "monthly_debts"),
    ("leads", "loan_amount"),
    ("leads", "target_payment"),
    ("leads", "appraisal_value"),
    ("leads", "monthly_payment"),
    ("leads", "property_tax"),
    ("leads", "hazard_insurance"),
    ("leads", "mortgage_insurance"),
    ("leads", "hoa_amount"),
    ("leads", "origination_fee"),
    ("leads", "estimated_prepaid_interest"),
    ("leads", "second_loan_amount"),
    ("leads", "second_loan_payment"),
    ("leads", "present_housing_expense"),
    ("leads", "proposed_housing_expense"),
    ("leads", "present_monthly_payment"),
    ("leads", "proposed_monthly_payment"),
    # loans table
    ("loans", "amount"),
    ("loans", "purchase_price"),
    ("loans", "down_payment"),
    ("loans", "appraisal_value"),
    ("loans", "extension_cost_estimate"),
    ("loans", "monthly_payment"),
    ("loans", "property_tax"),
    ("loans", "hazard_insurance"),
    ("loans", "mortgage_insurance"),
    ("loans", "hoa_amount"),
    ("loans", "origination_fee"),
    ("loans", "estimated_prepaid_interest"),
    ("loans", "second_loan_amount"),
    ("loans", "second_loan_payment"),
    ("loans", "present_housing_expense"),
    ("loans", "proposed_housing_expense"),
    ("loans", "present_monthly_payment"),
    ("loans", "proposed_monthly_payment"),
    # mum_clients table
    ("mum_clients", "original_loan_amount"),
    ("mum_clients", "current_loan_amount"),
    ("mum_clients", "appraisal_value_at_closing"),
    ("mum_clients", "current_property_value"),
    ("mum_clients", "loan_balance"),
    ("mum_clients", "estimated_savings"),
    ("mum_clients", "estimated_equity"),
    # referral_partners table
    ("referral_partners", "volume"),
    # subscription_plans table
    ("subscription_plans", "price_monthly"),
    ("subscription_plans", "price_yearly"),
    # promo_codes table
    ("promo_codes", "discount_value"),
    # borrower_applications table
    ("borrower_applications", "prequalification_amount"),
    ("borrower_applications", "prequalification_monthly_payment"),
]

RATE_COLUMNS = [
    # leads table
    ("leads", "debt_to_income"),
    ("leads", "interest_rate"),
    ("leads", "apr"),
    ("leads", "points"),
    ("leads", "ltv"),
    ("leads", "cltv"),
    ("leads", "dti"),
    ("leads", "dti_front"),
    ("leads", "dti_back"),
    ("leads", "index_rate"),
    ("leads", "margin"),
    ("leads", "second_loan_rate"),
    # loans table
    ("loans", "rate"),
    ("loans", "points"),
    ("loans", "index_rate"),
    ("loans", "margin"),
    ("loans", "ltv"),
    ("loans", "cltv"),
    ("loans", "second_loan_rate"),
    # mum_clients table
    ("mum_clients", "original_rate"),
    ("mum_clients", "current_rate"),
    ("mum_clients", "interest_rate"),
    ("mum_clients", "current_ltv"),
    # borrower_applications table
    ("borrower_applications", "prequalification_rate"),
]


def run_migration():
    """Execute the Float→Numeric migration."""
    from sqlalchemy import create_engine, text

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if database_url.startswith("sqlite"):
        logger.info("SQLite does not enforce column types — skipping migration")
        return True

    engine = create_engine(database_url)

    converted = 0
    skipped = 0
    errors = 0

    with engine.connect() as conn:
        # Process dollar amount columns → NUMERIC(18,2)
        for table, column in DOLLAR_COLUMNS:
            try:
                # Check if column exists and current type
                result = conn.execute(text("""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = :table AND column_name = :column
                """), {"table": table, "column": column})
                row = result.fetchone()
                if not row:
                    logger.warning(f"  SKIP {table}.{column} — column not found")
                    skipped += 1
                    continue
                if row[0] == 'numeric':
                    logger.info(f"  SKIP {table}.{column} — already NUMERIC")
                    skipped += 1
                    continue

                conn.execute(text(f"""
                    ALTER TABLE {table}
                    ALTER COLUMN {column}
                    TYPE NUMERIC(18,2)
                    USING {column}::numeric(18,2)
                """))
                logger.info(f"  OK   {table}.{column} → NUMERIC(18,2)")
                converted += 1
            except Exception as e:
                logger.error(f"  FAIL {table}.{column}: {e}")
                errors += 1

        # Process rate/percentage columns → NUMERIC(8,4)
        for table, column in RATE_COLUMNS:
            try:
                result = conn.execute(text("""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = :table AND column_name = :column
                """), {"table": table, "column": column})
                row = result.fetchone()
                if not row:
                    logger.warning(f"  SKIP {table}.{column} — column not found")
                    skipped += 1
                    continue
                if row[0] == 'numeric':
                    logger.info(f"  SKIP {table}.{column} — already NUMERIC")
                    skipped += 1
                    continue

                conn.execute(text(f"""
                    ALTER TABLE {table}
                    ALTER COLUMN {column}
                    TYPE NUMERIC(8,4)
                    USING {column}::numeric(8,4)
                """))
                logger.info(f"  OK   {table}.{column} → NUMERIC(8,4)")
                converted += 1
            except Exception as e:
                logger.error(f"  FAIL {table}.{column}: {e}")
                errors += 1

        conn.commit()

    logger.info(f"\nMigration complete: {converted} converted, {skipped} skipped, {errors} errors")
    return errors == 0


if __name__ == "__main__":
    logger.info(f"Float→Numeric migration started at {datetime.now().isoformat()}")
    success = run_migration()
    sys.exit(0 if success else 1)
