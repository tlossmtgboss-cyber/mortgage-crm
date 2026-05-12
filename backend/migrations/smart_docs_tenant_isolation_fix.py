"""Fix Smart Docs tenant isolation gaps.

1. DocumentRequest (smart_document_requests) — add organization_id column,
   backfill from the related loan's organization_id, set NOT NULL, add FK.

2. SmartDocument (smart_documents) — backfill any NULL organization_id rows
   from the related loan, set NOT NULL, add FK constraint.

All operations are idempotent — safe to re-run.
"""
from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def run_migration():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from sqlalchemy import text as sa_text
    from db import SessionLocal

    db = SessionLocal()
    try:
        # ==================================================================
        # 1. smart_document_requests — add organization_id column
        # ==================================================================
        logger.info("Step 1: smart_document_requests — add organization_id column")

        # Check if table exists first
        table_exists = db.execute(sa_text(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_name = 'smart_document_requests')"
        )).scalar()

        if not table_exists:
            logger.info("  smart_document_requests table does not exist yet — skipping")
        else:
            # Add organization_id column (nullable initially for backfill)
            db.execute(sa_text("""
                ALTER TABLE smart_document_requests
                ADD COLUMN IF NOT EXISTS organization_id INTEGER
            """))
            db.commit()

            # Backfill from loans table
            logger.info("  Backfilling organization_id from loans table")
            updated = db.execute(sa_text("""
                UPDATE smart_document_requests sdr
                SET organization_id = l.organization_id
                FROM loans l
                WHERE sdr.loan_id = l.id
                  AND sdr.organization_id IS NULL
                  AND l.organization_id IS NOT NULL
            """))
            db.commit()
            logger.info("  Backfilled %d rows from loans", updated.rowcount)

            # For any remaining NULLs (orphaned requests), default to org 1
            remaining = db.execute(sa_text("""
                UPDATE smart_document_requests
                SET organization_id = 1
                WHERE organization_id IS NULL
            """))
            db.commit()
            if remaining.rowcount > 0:
                logger.warning(
                    "  Defaulted %d orphaned requests to org 1", remaining.rowcount
                )

            # Set NOT NULL
            logger.info("  Setting organization_id NOT NULL")
            db.execute(sa_text("""
                ALTER TABLE smart_document_requests
                ALTER COLUMN organization_id SET NOT NULL
            """))

            # Add FK constraint (idempotent via DO $$ block)
            db.execute(sa_text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE constraint_name = 'fk_smart_doc_requests_org_id'
                          AND table_name = 'smart_document_requests'
                    ) THEN
                        ALTER TABLE smart_document_requests
                        ADD CONSTRAINT fk_smart_doc_requests_org_id
                        FOREIGN KEY (organization_id) REFERENCES organizations(id);
                    END IF;
                END
                $$;
            """))

            # Add index
            db.execute(sa_text("""
                CREATE INDEX IF NOT EXISTS ix_smart_doc_requests_organization_id
                ON smart_document_requests(organization_id)
            """))

            db.commit()
            logger.info("  [OK] smart_document_requests — organization_id added and enforced")

        # ==================================================================
        # 2. smart_documents — backfill NULL organization_id, set NOT NULL,
        #    add FK constraint
        # ==================================================================
        logger.info("Step 2: smart_documents — enforce organization_id NOT NULL + FK")

        sd_table_exists = db.execute(sa_text(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_name = 'smart_documents')"
        )).scalar()

        if not sd_table_exists:
            logger.info("  smart_documents table does not exist yet — skipping")
        else:
            # Backfill any NULL organization_id from loans
            updated_sd = db.execute(sa_text("""
                UPDATE smart_documents sd
                SET organization_id = l.organization_id
                FROM loans l
                WHERE sd.loan_id = l.id
                  AND sd.organization_id IS NULL
                  AND l.organization_id IS NOT NULL
            """))
            db.commit()
            logger.info("  Backfilled %d smart_documents rows from loans", updated_sd.rowcount)

            # Default remaining NULLs to org 1
            remaining_sd = db.execute(sa_text("""
                UPDATE smart_documents
                SET organization_id = 1
                WHERE organization_id IS NULL
            """))
            db.commit()
            if remaining_sd.rowcount > 0:
                logger.warning(
                    "  Defaulted %d orphaned smart_documents to org 1", remaining_sd.rowcount
                )

            # Set NOT NULL
            logger.info("  Setting organization_id NOT NULL")
            db.execute(sa_text("""
                ALTER TABLE smart_documents
                ALTER COLUMN organization_id SET NOT NULL
            """))

            # Add FK constraint
            db.execute(sa_text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.table_constraints
                        WHERE constraint_name = 'fk_smart_documents_org_id'
                          AND table_name = 'smart_documents'
                    ) THEN
                        ALTER TABLE smart_documents
                        ADD CONSTRAINT fk_smart_documents_org_id
                        FOREIGN KEY (organization_id) REFERENCES organizations(id);
                    END IF;
                END
                $$;
            """))

            db.commit()
            logger.info("  [OK] smart_documents — organization_id NOT NULL + FK enforced")

        logger.info("Smart Docs tenant isolation migration complete")

    except Exception as e:
        db.rollback()
        logger.error("Smart Docs tenant isolation migration failed: %s", e)
        raise
    finally:
        db.close()


def rollback():
    """Rollback migration — make columns nullable again and drop FK constraints."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from sqlalchemy import text as sa_text
    from db import SessionLocal

    db = SessionLocal()
    try:
        # smart_document_requests — drop FK, make nullable
        logger.info("Rolling back smart_document_requests changes")
        db.execute(sa_text("""
            ALTER TABLE smart_document_requests
            DROP CONSTRAINT IF EXISTS fk_smart_doc_requests_org_id
        """))
        db.execute(sa_text("""
            ALTER TABLE smart_document_requests
            ALTER COLUMN organization_id DROP NOT NULL
        """))
        db.commit()

        # smart_documents — drop FK, make nullable
        logger.info("Rolling back smart_documents changes")
        db.execute(sa_text("""
            ALTER TABLE smart_documents
            DROP CONSTRAINT IF EXISTS fk_smart_documents_org_id
        """))
        db.execute(sa_text("""
            ALTER TABLE smart_documents
            ALTER COLUMN organization_id DROP NOT NULL
        """))
        db.commit()

        logger.info("Rollback complete")

    except Exception as e:
        db.rollback()
        logger.error("Rollback failed: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Smart Docs tenant isolation migration")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        rollback()
    else:
        run_migration()
