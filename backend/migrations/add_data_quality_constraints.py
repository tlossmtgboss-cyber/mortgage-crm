"""
Migration: Add data quality CHECK constraints for leads and loans tables.

Adds:
  1. Lead.stage must be in the valid LeadStage enum values
  2. Loan.stage must be in the valid LoanStage enum values
  3. Financial fields must be >= 0 (loan_amount, purchase_price, down_payment,
     annual_income, property_value, appraisal_value on leads;
     amount, purchase_price, down_payment on loans)

These constraints are defense-in-depth — the ORM @validates decorators
catch issues at the Python layer; these constraints catch direct SQL updates
and third-party integrations writing directly to the database.

Idempotent: drops existing constraints before re-creating them.

Run: python -m migrations.add_data_quality_constraints
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Valid lead stages (from database.enums.LeadStage)
VALID_LEAD_STAGES = [
    "New", "Attempted Contact", "Prospect", "Application",
    "APPLICATION_STARTED", "Document Fulfillment",
    "Pre-Qualified", "Pre-Approved", "Under Contract",
    "Long-Term Nurture", "Closed", "AMR", "Referral Source",
    "Withdrawn", "Does Not Qualify", "Credit Repair", "Do Not Call",
    "Disclosed", "Funded",
]

# Valid loan stages (from database.enums.LoanStage)
VALID_LOAN_STAGES = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL",
    "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE",
    "CLOSING", "DOCS", "DOCS_OUT", "FUNDED",
    "CANCELLED", "DENIED", "DEAD", "NURTURE",
    "WITHDRAWN", "DOES_NOT_QUALIFY",
]

# Financial columns that must be >= 0 (table, column_name, constraint_name)
LEAD_FINANCIAL_CONSTRAINTS = [
    ("leads", "loan_amount", "ck_leads_loan_amount_nonneg"),
    ("leads", "preapproval_amount", "ck_leads_preapproval_amount_nonneg"),
    ("leads", "property_value", "ck_leads_property_value_nonneg"),
    ("leads", "down_payment", "ck_leads_down_payment_nonneg"),
    ("leads", "annual_income", "ck_leads_annual_income_nonneg"),
    ("leads", "appraisal_value", "ck_leads_appraisal_value_nonneg"),
    ("leads", "monthly_debts", "ck_leads_monthly_debts_nonneg"),
    ("leads", "target_payment", "ck_leads_target_payment_nonneg"),
]

LOAN_FINANCIAL_CONSTRAINTS = [
    ("loans", "amount", "ck_loans_amount_nonneg"),
    ("loans", "purchase_price", "ck_loans_purchase_price_nonneg"),
    ("loans", "down_payment", "ck_loans_down_payment_nonneg"),
    ("loans", "appraisal_value", "ck_loans_appraisal_value_nonneg"),
    ("loans", "monthly_payment", "ck_loans_monthly_payment_nonneg"),
    ("loans", "origination_fee", "ck_loans_origination_fee_nonneg"),
]


def run_migration():
    """Add CHECK constraints for stage values and financial field non-negativity."""
    from sqlalchemy import create_engine, text

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if database_url.startswith("sqlite"):
        logger.info("SQLite does not support ALTER TABLE ADD CONSTRAINT — skipping")
        return True

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # ==================================================================
        # 1. Stage CHECK constraints
        # ==================================================================

        # Drop existing stage constraints (idempotent)
        for cname, tname in [
            ("chk_leads_stage_dq", "leads"),
            ("chk_loans_stage_dq", "loans"),
        ]:
            try:
                conn.execute(text(
                    f"ALTER TABLE {tname} DROP CONSTRAINT IF EXISTS {cname}"
                ))
            except Exception as e:
                logger.debug("Drop %s: %s", cname, e)

        # Lead stage constraint
        lead_values = ", ".join(f"'{s}'" for s in VALID_LEAD_STAGES)
        try:
            conn.execute(text(f"""
                ALTER TABLE leads
                ADD CONSTRAINT chk_leads_stage_dq
                CHECK (stage IS NULL OR stage IN ({lead_values}))
            """))
            logger.info("Added CHECK constraint chk_leads_stage_dq (%d valid values)", len(VALID_LEAD_STAGES))
        except Exception as e:
            logger.error("Failed to add leads.stage CHECK: %s", e)

        # Loan stage constraint
        loan_values = ", ".join(f"'{s}'" for s in VALID_LOAN_STAGES)
        try:
            conn.execute(text(f"""
                ALTER TABLE loans
                ADD CONSTRAINT chk_loans_stage_dq
                CHECK (stage IS NULL OR stage IN ({loan_values}))
            """))
            logger.info("Added CHECK constraint chk_loans_stage_dq (%d valid values)", len(VALID_LOAN_STAGES))
        except Exception as e:
            logger.error("Failed to add loans.stage CHECK: %s", e)

        # ==================================================================
        # 2. Financial non-negativity constraints
        # ==================================================================

        all_financial = LEAD_FINANCIAL_CONSTRAINTS + LOAN_FINANCIAL_CONSTRAINTS
        for table_name, col_name, constraint_name in all_financial:
            # Drop if exists
            try:
                conn.execute(text(
                    f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}"
                ))
            except Exception as e:
                logger.debug("Drop %s: %s", constraint_name, e)

            # Add constraint: column IS NULL OR column >= 0
            try:
                conn.execute(text(f"""
                    ALTER TABLE {table_name}
                    ADD CONSTRAINT {constraint_name}
                    CHECK ({col_name} IS NULL OR {col_name} >= 0)
                """))
                logger.info("Added CHECK constraint %s on %s.%s", constraint_name, table_name, col_name)
            except Exception as e:
                logger.error("Failed to add %s: %s", constraint_name, e)

        conn.commit()

    logger.info("Data quality CHECK constraint migration complete")
    return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
