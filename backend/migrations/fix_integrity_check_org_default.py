"""
Migration: Fix organization_id default=0 on document_integrity_checks.

Steps performed (all idempotent):

1. Back-fill any rows where organization_id = 0 by walking up the join chain:
       document_integrity_checks -> smart_documents -> loans -> organization_id
   Rows whose loan has no organization_id are left at 0 so the later NOT NULL
   step does not silently discard orphaned records — they will surface as a
   constraint violation that the team can investigate.

2. DROP DEFAULT on document_integrity_checks.organization_id so future inserts
   cannot accidentally inherit a 0.

3. SET NOT NULL on the column (skipped if it is already NOT NULL).

Idempotent — safe to run multiple times.

Run standalone:
    python -m migrations.fix_integrity_check_org_default

Or import and call:
    from migrations.fix_integrity_check_org_default import run_migration
    run_migration()
"""

from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

# Step 1 — back-fill organization_id = 0 from the associated loan.
# We join through smart_documents to reach loans.organization_id.
# Rows that cannot be resolved (no document, no loan, or loan has NULL
# organization_id) are left untouched; they will be caught in step 3.
_BACKFILL_SQL = """
UPDATE document_integrity_checks dic
SET    organization_id = l.organization_id
FROM   smart_documents  sd
JOIN   loans             l  ON l.id = sd.loan_id
WHERE  dic.document_id  = sd.id
  AND  dic.organization_id = 0
  AND  l.organization_id IS NOT NULL
  AND  l.organization_id <> 0;
"""

# Step 2 — remove the column default so future inserts must supply a value.
# DROP DEFAULT is a no-op if no default exists, so this is inherently idempotent.
_DROP_DEFAULT_SQL = """
ALTER TABLE document_integrity_checks
    ALTER COLUMN organization_id DROP DEFAULT;
"""

# Step 3 — set NOT NULL only if the column is currently nullable.
# Wrapped in a DO block so it is skipped rather than erroring when the
# constraint is already present.
_SET_NOT_NULL_SQL = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM   information_schema.columns
        WHERE  table_schema = 'public'
          AND  table_name   = 'document_integrity_checks'
          AND  column_name  = 'organization_id'
          AND  is_nullable  = 'YES'
    ) THEN
        ALTER TABLE document_integrity_checks
            ALTER COLUMN organization_id SET NOT NULL;
        RAISE NOTICE 'Set organization_id NOT NULL on document_integrity_checks';
    ELSE
        RAISE NOTICE 'organization_id is already NOT NULL — skipping';
    END IF;
END $$;
"""


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table_name},
    ).fetchone()
    return row is not None


def run_migration() -> bool:
    """Fix organization_id default=0 on document_integrity_checks."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if database_url.startswith("sqlite"):
        logger.info("SQLite detected — skipping PostgreSQL-specific migration")
        return True

    engine = create_engine(database_url)

    with engine.connect() as conn:
        # Guard: skip entirely if the table does not exist yet.
        if not _table_exists(conn, "document_integrity_checks"):
            logger.info(
                "Table document_integrity_checks does not exist — skipping migration"
            )
            return True

        # ----------------------------------------------------------------
        # Step 1: back-fill rows where organization_id = 0
        # ----------------------------------------------------------------
        try:
            result = conn.execute(text(_BACKFILL_SQL))
            updated = result.rowcount
            if updated:
                logger.info(
                    "Back-filled organization_id on %d row(s) in document_integrity_checks",
                    updated,
                )
            else:
                logger.info(
                    "No rows with organization_id = 0 needed back-filling"
                )
        except Exception as exc:
            logger.error("Back-fill step failed: %s", exc)
            conn.rollback()
            return False

        # Report any remaining zeros so the team is aware before NOT NULL lands.
        try:
            remaining = conn.execute(
                text(
                    "SELECT COUNT(*) AS n FROM document_integrity_checks "
                    "WHERE organization_id = 0 OR organization_id IS NULL"
                )
            ).scalar()
            if remaining:
                logger.warning(
                    "%d row(s) in document_integrity_checks still have "
                    "organization_id = 0 or NULL (could not be resolved from loan). "
                    "These will violate the NOT NULL constraint — investigate before "
                    "the migration enforces it.",
                    remaining,
                )
        except Exception as exc:
            logger.warning("Could not count remaining zero rows: %s", exc)

        # ----------------------------------------------------------------
        # Step 2: drop the column default
        # ----------------------------------------------------------------
        try:
            conn.execute(text(_DROP_DEFAULT_SQL))
            logger.info(
                "Dropped DEFAULT on document_integrity_checks.organization_id"
            )
        except Exception as exc:
            logger.error("DROP DEFAULT step failed: %s", exc)
            conn.rollback()
            return False

        # ----------------------------------------------------------------
        # Step 3: set NOT NULL (only if no unresolved zeros remain)
        # ----------------------------------------------------------------
        try:
            remaining_check = conn.execute(
                text(
                    "SELECT COUNT(*) AS n FROM document_integrity_checks "
                    "WHERE organization_id = 0 OR organization_id IS NULL"
                )
            ).scalar()
        except Exception as exc:
            logger.warning("Pre-NOT-NULL check failed: %s — proceeding anyway", exc)
            remaining_check = 0

        if remaining_check and remaining_check > 0:
            logger.warning(
                "Skipping SET NOT NULL because %d unresolved row(s) remain. "
                "Fix those rows manually and re-run this migration.",
                remaining_check,
            )
        else:
            try:
                conn.execute(text(_SET_NOT_NULL_SQL))
                logger.info(
                    "SET NOT NULL applied to document_integrity_checks.organization_id"
                )
            except Exception as exc:
                logger.error("SET NOT NULL step failed: %s", exc)
                conn.rollback()
                return False

        conn.commit()

    logger.info("Migration complete: fix_integrity_check_org_default")
    return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
