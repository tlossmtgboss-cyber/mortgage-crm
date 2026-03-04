"""
Migration: Add Employee Recruiting to Partner Recruiting System
Adds candidate_category discriminator, employee-specific columns, and assessment dimensions.
Safe to run multiple times (all operations use IF NOT EXISTS).
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Run employee recruiting migration."""
    if engine is None:
        from database import engine as db_engine
        engine = db_engine

    results = []

    with engine.begin() as conn:
        # 1. Add candidate_category discriminator
        conn.execute(text("""
            ALTER TABLE partner_candidates
            ADD COLUMN IF NOT EXISTS candidate_category VARCHAR(20) DEFAULT 'partner'
        """))
        results.append("Added candidate_category column")

        # Backfill existing rows
        conn.execute(text("""
            UPDATE partner_candidates
            SET candidate_category = 'partner'
            WHERE candidate_category IS NULL
        """))
        results.append("Backfilled candidate_category for existing rows")

        # 2. Add employee-specific columns to partner_candidates
        employee_columns = [
            ("employee_role", "VARCHAR(50)"),
            ("nmls_id", "VARCHAR(50)"),
            ("license_states", "JSONB DEFAULT '[]'"),
            ("current_employer", "VARCHAR(255)"),
            ("years_experience", "INTEGER"),
            ("desired_compensation", "VARCHAR(100)"),
            ("hired_at", "TIMESTAMP"),
            ("withdrawn_at", "TIMESTAMP"),
        ]

        for col_name, col_type in employee_columns:
            conn.execute(text(f"""
                ALTER TABLE partner_candidates
                ADD COLUMN IF NOT EXISTS {col_name} {col_type}
            """))
        results.append(f"Added {len(employee_columns)} employee columns to partner_candidates")

        # 3. Add employee assessment dimensions to partner_assessments
        assessment_columns = [
            ("technical_skills_score", "FLOAT"),
            ("experience_score", "FLOAT"),
        ]

        for col_name, col_type in assessment_columns:
            conn.execute(text(f"""
                ALTER TABLE partner_assessments
                ADD COLUMN IF NOT EXISTS {col_name} {col_type}
            """))
        results.append("Added technical_skills_score and experience_score to partner_assessments")

        # 4. Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_partner_candidates_category
            ON partner_candidates(candidate_category)
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_partner_candidates_owner_category
            ON partner_candidates(owner_id, candidate_category)
        """))
        results.append("Created category indexes")

    logger.info(f"Employee recruiting migration complete: {len(results)} steps")
    return {"steps": results, "status": "success"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    print(f"Migration result: {result}")
