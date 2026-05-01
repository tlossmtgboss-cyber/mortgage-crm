"""Fix SMS multi-tenant isolation gaps.

The original sms_compliance_tables migration created these tables without
proper tenant isolation:
  - sms_consent: no organization_id column at all
  - sms_compliance_log: no organization_id column at all
  - sms_opt_outs: organization_id exists but nullable, phone UNIQUE is global
  - sms_delivery_log: organization_id exists but no FK constraint

The ORM models (database/models/sms_compliance.py, sms_delivery.py) already
define the correct schema with organization_id NOT NULL, FK constraints, and
composite unique indexes.  This migration brings the live database in line.

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
        # 1. sms_consent — add organization_id, backfill, set NOT NULL,
        #    replace global UNIQUE(phone_number) with composite UNIQUE
        # ==================================================================
        logger.info("Step 1: sms_consent — add organization_id column")
        db.execute(sa_text("""
            ALTER TABLE sms_consent
            ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)
        """))

        # Backfill existing rows to org 1 so we can set NOT NULL
        db.execute(sa_text("""
            UPDATE sms_consent SET organization_id = 1 WHERE organization_id IS NULL
        """))

        db.execute(sa_text("""
            ALTER TABLE sms_consent ALTER COLUMN organization_id SET NOT NULL
        """))

        # Index on organization_id for RLS filtering
        db.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS ix_sms_consent_org_id
            ON sms_consent(organization_id)
        """))

        # Drop old global unique on phone_number (name varies by how table was created)
        db.execute(sa_text("""
            ALTER TABLE sms_consent DROP CONSTRAINT IF EXISTS sms_consent_phone_number_key
        """))
        db.execute(sa_text("""
            ALTER TABLE sms_consent DROP CONSTRAINT IF EXISTS uq_sms_consent_phone_number
        """))
        # Drop index variant too (some PG versions create an index instead of constraint)
        db.execute(sa_text("""
            DROP INDEX IF EXISTS sms_consent_phone_number_key
        """))

        # Composite unique: one consent record per org+phone
        db.execute(sa_text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_sms_consent_org_phone
            ON sms_consent (organization_id, phone_number)
        """))

        logger.info("  [OK] sms_consent — organization_id added, composite unique set")

        # ==================================================================
        # 2. sms_compliance_log — add organization_id, backfill, set NOT NULL
        # ==================================================================
        logger.info("Step 2: sms_compliance_log — add organization_id column")
        db.execute(sa_text("""
            ALTER TABLE sms_compliance_log
            ADD COLUMN IF NOT EXISTS organization_id INTEGER REFERENCES organizations(id)
        """))

        db.execute(sa_text("""
            UPDATE sms_compliance_log SET organization_id = 1 WHERE organization_id IS NULL
        """))

        db.execute(sa_text("""
            ALTER TABLE sms_compliance_log ALTER COLUMN organization_id SET NOT NULL
        """))

        db.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS ix_sms_compliance_log_org_id
            ON sms_compliance_log(organization_id)
        """))

        # Also add the consent proof columns that the ORM model defines
        db.execute(sa_text("""
            ALTER TABLE sms_compliance_log
            ADD COLUMN IF NOT EXISTS consent_record_id INTEGER
        """))
        db.execute(sa_text("""
            ALTER TABLE sms_compliance_log
            ADD COLUMN IF NOT EXISTS consent_method VARCHAR(50)
        """))

        logger.info("  [OK] sms_compliance_log — organization_id added")

        # ==================================================================
        # 3. sms_opt_outs — make organization_id NOT NULL (column exists
        #    but is nullable from original migration)
        # ==================================================================
        logger.info("Step 3: sms_opt_outs — enforce NOT NULL on organization_id")

        # Backfill any NULLs first
        db.execute(sa_text("""
            UPDATE sms_opt_outs SET organization_id = 1 WHERE organization_id IS NULL
        """))

        db.execute(sa_text("""
            ALTER TABLE sms_opt_outs ALTER COLUMN organization_id SET NOT NULL
        """))

        # Drop old global unique on phone_number
        db.execute(sa_text("""
            ALTER TABLE sms_opt_outs DROP CONSTRAINT IF EXISTS sms_opt_outs_phone_number_key
        """))
        db.execute(sa_text("""
            ALTER TABLE sms_opt_outs DROP CONSTRAINT IF EXISTS uq_sms_opt_outs_phone_number
        """))
        db.execute(sa_text("""
            DROP INDEX IF EXISTS sms_opt_outs_phone_number_key
        """))

        # Composite unique: one opt-out record per org+phone
        db.execute(sa_text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_sms_opt_out_org_phone
            ON sms_opt_outs (organization_id, phone_number)
        """))

        logger.info("  [OK] sms_opt_outs — organization_id NOT NULL, composite unique set")

        # ==================================================================
        # 4. sms_delivery_log — add FK constraint on organization_id
        #    (column exists but original SQL had no REFERENCES clause)
        # ==================================================================
        logger.info("Step 4: sms_delivery_log — add FK on organization_id")

        # PostgreSQL: add FK only if it doesn't already exist
        db.execute(sa_text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_sms_delivery_log_org_id'
                      AND table_name = 'sms_delivery_log'
                ) THEN
                    ALTER TABLE sms_delivery_log
                    ADD CONSTRAINT fk_sms_delivery_log_org_id
                    FOREIGN KEY (organization_id) REFERENCES organizations(id);
                END IF;
            END
            $$;
        """))

        logger.info("  [OK] sms_delivery_log — FK constraint added")

        # ==================================================================
        # Commit all changes
        # ==================================================================
        db.commit()
        logger.info("SMS multi-tenant migration complete — all 4 steps applied")

    except Exception as e:
        db.rollback()
        logger.error("SMS multi-tenant migration failed: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
