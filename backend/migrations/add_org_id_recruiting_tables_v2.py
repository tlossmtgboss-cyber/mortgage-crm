"""
Add organization_id to remaining recruiting tables (Phase 2).

Covers tables missed in enforce_recruiting_org_id.py:
  - recruit_quiz_templates      (new column)
  - recruiting_call_history     (new column, backfill via mm_candidates)
  - recruit_company_updates     (new column)
  - recruit_video_messages      (new column, backfill via mm_candidates)
  - recruiting_tasks            (has column w/ DEFAULT 1 — normalize)
  - recruit_calculator_config   (has nullable column — tighten)
"""

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)


def run_migration():
    """Add/enforce organization_id on 6 recruiting tables."""
    results = {"processed": [], "skipped": [], "errors": []}

    with engine.connect() as conn:
        # Determine default org_id for backfill
        default_org = conn.execute(text(
            "SELECT id FROM organizations ORDER BY id LIMIT 1"
        )).fetchone()
        default_org_id = default_org.id if default_org else 1

        # ── Tables that need a brand-new column ──────────────────────────
        new_column_tables = [
            {
                "table": "recruit_quiz_templates",
                "backfill_strategy": "default",  # no FK to candidates
            },
            {
                "table": "recruiting_call_history",
                "backfill_strategy": "candidate",  # JOIN mm_candidates
                "fk_col": "candidate_id",
            },
            {
                "table": "recruit_company_updates",
                "backfill_strategy": "default",
            },
            {
                "table": "recruit_video_messages",
                "backfill_strategy": "candidate",
                "fk_col": "candidate_id",
            },
        ]

        for spec in new_column_tables:
            table = spec["table"]
            try:
                # Check table exists
                exists = conn.execute(text("""
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = :table AND table_schema = 'public'
                """), {"table": table}).fetchone()

                if not exists:
                    results["skipped"].append(f"{table} (table not found)")
                    continue

                # Add column if missing
                has_col = conn.execute(text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = :table AND column_name = 'organization_id'
                """), {"table": table}).fetchone()

                if not has_col:
                    conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN organization_id INTEGER"
                    ))
                    logger.info(f"Added organization_id to {table}")

                # Backfill NULLs
                if spec["backfill_strategy"] == "candidate":
                    fk_col = spec["fk_col"]
                    conn.execute(text(f"""
                        UPDATE {table} t
                        SET organization_id = COALESCE(
                            (SELECT mc.organization_id FROM mm_candidates mc
                             WHERE mc.id = t.{fk_col} LIMIT 1),
                            :default_org
                        )
                        WHERE t.organization_id IS NULL
                    """), {"default_org": default_org_id})
                else:
                    conn.execute(text(f"""
                        UPDATE {table}
                        SET organization_id = :default_org
                        WHERE organization_id IS NULL
                    """), {"default_org": default_org_id})

                # SET NOT NULL
                conn.execute(text(f"""
                    DO $$
                    BEGIN
                        ALTER TABLE {table} ALTER COLUMN organization_id SET NOT NULL;
                    EXCEPTION WHEN others THEN
                        RAISE NOTICE 'NOT NULL already set on {table}.organization_id';
                    END $$;
                """))

                # CREATE INDEX
                idx_name = f"idx_{table}_organization_id"
                conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name} ON {table} (organization_id)
                """))

                results["processed"].append(table)
                logger.info(f"Completed {table}")

            except Exception as e:
                logger.error(f"Error processing {table}: {e}")
                results["errors"].append({"table": table, "error": str(e)})

        # ── recruiting_tasks: has DEFAULT 1, normalize ───────────────────
        try:
            exists = conn.execute(text("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'recruiting_tasks' AND table_schema = 'public'
            """)).fetchone()

            if exists:
                # Backfill NULLs
                conn.execute(text("""
                    UPDATE recruiting_tasks
                    SET organization_id = :default_org
                    WHERE organization_id IS NULL
                """), {"default_org": default_org_id})

                # Drop DEFAULT, SET NOT NULL
                conn.execute(text("""
                    DO $$
                    BEGIN
                        ALTER TABLE recruiting_tasks ALTER COLUMN organization_id DROP DEFAULT;
                        ALTER TABLE recruiting_tasks ALTER COLUMN organization_id SET NOT NULL;
                    EXCEPTION WHEN others THEN
                        RAISE NOTICE 'recruiting_tasks.organization_id already normalized';
                    END $$;
                """))

                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_recruiting_tasks_organization_id
                    ON recruiting_tasks (organization_id)
                """))

                results["processed"].append("recruiting_tasks")
            else:
                results["skipped"].append("recruiting_tasks (table not found)")

        except Exception as e:
            logger.error(f"Error processing recruiting_tasks: {e}")
            results["errors"].append({"table": "recruiting_tasks", "error": str(e)})

        # ── recruit_calculator_config: tighten nullable + unique ─────────
        try:
            exists = conn.execute(text("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'recruit_calculator_config' AND table_schema = 'public'
            """)).fetchone()

            if exists:
                # Backfill NULLs
                conn.execute(text("""
                    UPDATE recruit_calculator_config
                    SET organization_id = :default_org
                    WHERE organization_id IS NULL
                """), {"default_org": default_org_id})

                # SET NOT NULL
                conn.execute(text("""
                    DO $$
                    BEGIN
                        ALTER TABLE recruit_calculator_config
                            ALTER COLUMN organization_id SET NOT NULL;
                    EXCEPTION WHEN others THEN
                        RAISE NOTICE 'recruit_calculator_config.organization_id already NOT NULL';
                    END $$;
                """))

                # Add UNIQUE constraint (one config per org)
                conn.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_recruit_calculator_config_org_unique
                    ON recruit_calculator_config (organization_id)
                """))

                results["processed"].append("recruit_calculator_config")
            else:
                results["skipped"].append("recruit_calculator_config (table not found)")

        except Exception as e:
            logger.error(f"Error processing recruit_calculator_config: {e}")
            results["errors"].append({"table": "recruit_calculator_config", "error": str(e)})

        conn.commit()

    logger.info(f"org_id migration v2 complete: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    print(result)
