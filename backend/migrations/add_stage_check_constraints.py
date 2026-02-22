"""
Migration: Add CHECK constraints for stage columns on leads and loans tables.

Enforces valid stage values at the database level (defense-in-depth).
The ORM @validates decorator catches invalid values at the Python layer;
this constraint catches direct SQL updates.

Run: python -m migrations.add_stage_check_constraints
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
    "Withdrawn", "Does Not Qualify", "Credit Repair", "Disclosed",
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


def run_migration():
    """Add CHECK constraints for stage columns."""
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
        # Drop existing constraints if they exist (idempotent)
        for name in ["chk_leads_stage", "chk_loans_stage"]:
            try:
                conn.execute(text(f"ALTER TABLE {'leads' if 'leads' in name else 'loans'} DROP CONSTRAINT IF EXISTS {name}"))
            except Exception as e:
                logger.error(f"Error dropping constraint {name}: {e}")

        # Add lead stage constraint
        lead_values = ", ".join(f"'{s}'" for s in VALID_LEAD_STAGES)
        try:
            conn.execute(text(f"""
                ALTER TABLE leads
                ADD CONSTRAINT chk_leads_stage
                CHECK (stage IS NULL OR stage IN ({lead_values}))
            """))
            logger.info(f"Added CHECK constraint on leads.stage ({len(VALID_LEAD_STAGES)} valid values)")
        except Exception as e:
            logger.error(f"Failed to add leads.stage CHECK: {e}")

        # Add loan stage constraint
        loan_values = ", ".join(f"'{s}'" for s in VALID_LOAN_STAGES)
        try:
            conn.execute(text(f"""
                ALTER TABLE loans
                ADD CONSTRAINT chk_loans_stage
                CHECK (stage IS NULL OR stage IN ({loan_values}))
            """))
            logger.info(f"Added CHECK constraint on loans.stage ({len(VALID_LOAN_STAGES)} valid values)")
        except Exception as e:
            logger.error(f"Failed to add loans.stage CHECK: {e}")

        conn.commit()

    logger.info("Stage CHECK constraint migration complete")
    return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
