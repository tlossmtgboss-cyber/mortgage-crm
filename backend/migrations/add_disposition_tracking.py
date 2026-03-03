"""
Add OFCCP disposition code tracking columns to mm_candidates.

Required for adverse impact analysis and 4/5ths rule reporting.

Columns added:
  - disposition_code   VARCHAR(50)  — reason code (e.g. 'unqualified', 'withdrew', 'position_filled')
  - disposition_date   TIMESTAMP    — when disposition was recorded
  - disposition_by     INTEGER      — user who set the disposition
"""

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)


def run_migration():
    """Add disposition tracking columns to mm_candidates."""
    results = {"added": [], "skipped": [], "errors": []}

    with engine.connect() as conn:
        # Check table exists
        exists = conn.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'mm_candidates' AND table_schema = 'public'
        """)).fetchone()

        if not exists:
            return {"message": "mm_candidates table not found", "skipped": True}

        columns = [
            ("disposition_code", "VARCHAR(50)"),
            ("disposition_date", "TIMESTAMP"),
            ("disposition_by", "INTEGER"),
        ]

        for col_name, col_type in columns:
            try:
                has_col = conn.execute(text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'mm_candidates' AND column_name = :col
                """), {"col": col_name}).fetchone()

                if has_col:
                    results["skipped"].append(col_name)
                    continue

                conn.execute(text(
                    f"ALTER TABLE mm_candidates ADD COLUMN {col_name} {col_type}"
                ))
                results["added"].append(col_name)
                logger.info(f"Added mm_candidates.{col_name}")

            except Exception as e:
                logger.error(f"Error adding {col_name}: {e}")
                results["errors"].append({"column": col_name, "error": str(e)})

        # Index on disposition_code for reporting queries
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_mm_candidates_disposition
                ON mm_candidates (disposition_code)
                WHERE disposition_code IS NOT NULL
            """))
            logger.info("Created disposition index")
        except Exception as e:
            logger.error(f"Error creating index: {e}")
            results["errors"].append({"index": "idx_mm_candidates_disposition", "error": str(e)})

        conn.commit()

    logger.info(f"Disposition tracking migration complete: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    print(result)
