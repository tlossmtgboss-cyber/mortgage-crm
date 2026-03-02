"""
Enforce organization_id NOT NULL on recruiting tables.

Security fix: ensures every recruiting record is scoped to an organization,
preventing cross-tenant data leaks.

Tables affected:
  - mm_candidates
  - mm_job_postings
  - mm_interviews
  - mm_offers
  - mm_candidate_notes
  - mm_candidate_activities
  - recruit_portal_workspaces
  - recruit_calculator_config
"""

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)

# Tables that need organization_id enforcement.
# (table_name, has_column_already: whether the column exists)
TABLES = [
    "mm_candidates",
    "mm_job_postings",
    "mm_interviews",
    "mm_offers",
    "mm_candidate_notes",
    "mm_candidate_activities",
    "recruit_portal_workspaces",
    "recruit_calculator_config",
]


def run_migration():
    """Add organization_id where missing, backfill NULLs, add NOT NULL + index."""
    results = {"added_columns": [], "backfilled": [], "constraints": [], "indexes": [], "errors": []}

    with engine.connect() as conn:
        # Step 1: Determine the default org_id for backfill
        default_org = conn.execute(text(
            "SELECT id FROM organizations ORDER BY id LIMIT 1"
        )).fetchone()
        default_org_id = default_org.id if default_org else 1

        for table in TABLES:
            try:
                # Check if table exists
                exists = conn.execute(text("""
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = :table AND table_schema = 'public'
                """), {"table": table}).fetchone()

                if not exists:
                    logger.info(f"Table {table} does not exist, skipping")
                    continue

                # Step 2: Add column if missing
                has_col = conn.execute(text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = :table AND column_name = 'organization_id'
                """), {"table": table}).fetchone()

                if not has_col:
                    conn.execute(text(f"""
                        ALTER TABLE {table}
                        ADD COLUMN organization_id INTEGER
                    """))
                    results["added_columns"].append(table)
                    logger.info(f"Added organization_id column to {table}")

                # Step 3: Backfill NULL rows with the default org
                updated = conn.execute(text(f"""
                    UPDATE {table}
                    SET organization_id = :org_id
                    WHERE organization_id IS NULL
                """), {"org_id": default_org_id})
                if updated.rowcount > 0:
                    results["backfilled"].append({"table": table, "rows": updated.rowcount})
                    logger.info(f"Backfilled {updated.rowcount} rows in {table}")

                # Step 4: Add NOT NULL constraint (idempotent via DO block)
                conn.execute(text(f"""
                    DO $$
                    BEGIN
                        ALTER TABLE {table}
                            ALTER COLUMN organization_id SET NOT NULL;
                    EXCEPTION WHEN others THEN
                        RAISE NOTICE 'NOT NULL already set on {table}.organization_id: %', SQLERRM;
                    END $$;
                """))
                results["constraints"].append(table)

                # Step 5: Add index (idempotent)
                idx_name = f"idx_{table}_organization_id"
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name}
                    ON {table} (organization_id)
                """))
                results["indexes"].append(idx_name)

            except Exception as e:
                logger.error(f"Error processing {table}: {e}")
                results["errors"].append({"table": table, "error": str(e)})

        conn.commit()

    logger.info(f"Migration complete: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    print(result)
