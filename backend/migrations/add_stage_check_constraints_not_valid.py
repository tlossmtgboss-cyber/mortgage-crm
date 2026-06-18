"""
Migration: Add NOT VALID CHECK constraints for stage columns on leads and loans.

The ORM @validates('stage') decorator only WARNS on invalid values (backward
compat — it does not raise). This migration adds a database-level CHECK
constraint as a second line of defense against direct SQL writes.

The constraints are added with NOT VALID so PostgreSQL does NOT scan or reject
pre-existing rows that may hold legacy/out-of-enum stage values. New INSERTs and
UPDATEs ARE checked, blocking bad data going forward. Operators can later run
`ALTER TABLE ... VALIDATE CONSTRAINT ...` once existing rows are cleaned up.

Valid values are derived directly from the model's _VALID_LEAD_STAGES /
_VALID_LOAN_STAGES frozensets (the LeadStage / LoanStage enums) so this never
drifts from the source of truth.

Run: python -m migrations.add_stage_check_constraints_not_valid
"""
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _valid_stages():
    """Return (lead_stages, loan_stages) sorted lists from the model frozensets."""
    from database.models.lead_loan import Lead, Loan
    return sorted(Lead._VALID_LEAD_STAGES), sorted(Loan._VALID_LOAN_STAGES)


def run_migration():
    """Add NOT VALID CHECK constraints for stage columns."""
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

    lead_stages, loan_stages = _valid_stages()
    engine = create_engine(database_url)

    targets = [
        ("leads", "chk_leads_stage", lead_stages),
        ("loans", "chk_loans_stage", loan_stages),
    ]

    errors = 0
    with engine.connect() as conn:
        for table, name, values in targets:
            try:
                # Drop any prior version (validated or not) so we can re-add as NOT VALID.
                conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"))

                in_list = ", ".join(f"'{v}'" for v in values)
                conn.execute(text(f"""
                    ALTER TABLE {table}
                    ADD CONSTRAINT {name}
                    CHECK (stage IS NULL OR stage IN ({in_list}))
                    NOT VALID
                """))
                logger.info(
                    f"Added NOT VALID CHECK constraint {name} on {table}.stage "
                    f"({len(values)} valid values)"
                )
            except Exception as e:
                logger.error(f"Failed to add {name} on {table}.stage: {e}")
                errors += 1

        conn.commit()

    logger.info(f"Stage NOT VALID CHECK constraint migration complete ({errors} errors)")
    return errors == 0


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
