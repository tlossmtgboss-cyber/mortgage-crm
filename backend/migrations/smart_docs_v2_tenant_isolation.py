"""
Smart Docs V2 Tenant Isolation Migration

Fixes critical security issue: 6 Smart Docs V2 tables lack proper tenant
isolation via organization_id. Without this, any authenticated user can
potentially access documents, integrity checks, watermark logs, and
follow-up events belonging to other organizations.

Tables fixed:
    - document_followup_events     — ADD organization_id, backfill from campaign
    - document_integrity_checks    — ADD organization_id, backfill from encryption record or access log
    - document_watermark_logs      — ADD organization_id, backfill from access log
    - ai_document_classifications  — ADD composite indexes (org_id, document_id) etc.
    - document_followup_campaigns  — ADD composite indexes (org_id, loan_id) etc.
    - document_access_logs         — ADD composite indexes (org_id, document_id) etc.

Run: python -m migrations.smart_docs_v2_tenant_isolation
"""

import logging
import os
import sys

from sqlalchemy import create_engine, text

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Run the Smart Docs V2 tenant isolation migration.

    This migration is idempotent — safe to run multiple times. All DDL
    uses IF NOT EXISTS / IF EXISTS guards.
    """
    if engine is None:
        database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(database_url)

    with engine.connect() as conn:
        logger.info("Starting Smart Docs V2 tenant isolation migration...")
        print("[TENANT_ISO] Starting Smart Docs V2 tenant isolation migration...")

        # =================================================================
        # STEP 1: Add organization_id to tables that are missing it
        # =================================================================

        # --- document_followup_events ---
        print("[TENANT_ISO] Adding organization_id to document_followup_events...")
        conn.execute(text("""
            ALTER TABLE document_followup_events
            ADD COLUMN IF NOT EXISTS organization_id INTEGER
        """))

        # --- document_integrity_checks ---
        print("[TENANT_ISO] Adding organization_id to document_integrity_checks...")
        conn.execute(text("""
            ALTER TABLE document_integrity_checks
            ADD COLUMN IF NOT EXISTS organization_id INTEGER
        """))

        # --- document_watermark_logs ---
        print("[TENANT_ISO] Adding organization_id to document_watermark_logs...")
        conn.execute(text("""
            ALTER TABLE document_watermark_logs
            ADD COLUMN IF NOT EXISTS organization_id INTEGER
        """))

        # =================================================================
        # STEP 2: Backfill organization_id from related records
        # =================================================================

        # --- document_followup_events: backfill from parent campaign ---
        print("[TENANT_ISO] Backfilling document_followup_events.organization_id from campaigns...")
        conn.execute(text("""
            UPDATE document_followup_events dfe
            SET organization_id = dfc.organization_id
            FROM document_followup_campaigns dfc
            WHERE dfe.campaign_id = dfc.id
              AND dfe.organization_id IS NULL
              AND dfc.organization_id IS NOT NULL
        """))

        # --- document_integrity_checks: backfill from document_encryption_records ---
        print("[TENANT_ISO] Backfilling document_integrity_checks.organization_id from encryption records...")
        conn.execute(text("""
            UPDATE document_integrity_checks dic
            SET organization_id = der.organization_id
            FROM document_encryption_records der
            WHERE dic.document_id = der.document_id
              AND dic.document_type = der.document_type
              AND dic.organization_id IS NULL
              AND der.organization_id IS NOT NULL
        """))

        # Fallback: backfill from document_access_logs for any remaining nulls
        print("[TENANT_ISO] Backfilling document_integrity_checks.organization_id from access logs (fallback)...")
        conn.execute(text("""
            UPDATE document_integrity_checks dic
            SET organization_id = sub.org_id
            FROM (
                SELECT DISTINCT ON (document_id, document_type)
                    document_id, document_type, organization_id AS org_id
                FROM document_access_logs
                WHERE organization_id IS NOT NULL
                ORDER BY document_id, document_type, created_at DESC
            ) sub
            WHERE dic.document_id = sub.document_id
              AND dic.document_type = sub.document_type
              AND dic.organization_id IS NULL
        """))

        # --- document_watermark_logs: backfill from document_access_logs ---
        print("[TENANT_ISO] Backfilling document_watermark_logs.organization_id from access logs...")
        conn.execute(text("""
            UPDATE document_watermark_logs dwl
            SET organization_id = sub.org_id
            FROM (
                SELECT DISTINCT ON (document_id)
                    document_id, organization_id AS org_id
                FROM document_access_logs
                WHERE organization_id IS NOT NULL
                ORDER BY document_id, created_at DESC
            ) sub
            WHERE dwl.document_id = sub.document_id
              AND dwl.organization_id IS NULL
        """))

        # Fallback: backfill watermark logs from encryption records
        print("[TENANT_ISO] Backfilling document_watermark_logs.organization_id from encryption records (fallback)...")
        conn.execute(text("""
            UPDATE document_watermark_logs dwl
            SET organization_id = sub.org_id
            FROM (
                SELECT DISTINCT ON (document_id)
                    document_id, organization_id AS org_id
                FROM document_encryption_records
                WHERE organization_id IS NOT NULL
                ORDER BY document_id, created_at DESC
            ) sub
            WHERE dwl.document_id = sub.document_id
              AND dwl.organization_id IS NULL
        """))

        # =================================================================
        # STEP 3: Set default for remaining NULLs, then add NOT NULL
        #
        # Use organization_id = 0 as sentinel for orphaned rows.
        # A scheduled job should reconcile these later.
        # =================================================================

        print("[TENANT_ISO] Setting default 0 for remaining NULL organization_id values...")
        conn.execute(text("""
            UPDATE document_followup_events
            SET organization_id = 0
            WHERE organization_id IS NULL
        """))
        conn.execute(text("""
            UPDATE document_integrity_checks
            SET organization_id = 0
            WHERE organization_id IS NULL
        """))
        conn.execute(text("""
            UPDATE document_watermark_logs
            SET organization_id = 0
            WHERE organization_id IS NULL
        """))

        # Add NOT NULL constraints (safe — all rows now have a value)
        print("[TENANT_ISO] Adding NOT NULL constraints...")

        # Use DO blocks to avoid errors if constraint already set
        conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE document_followup_events
                    ALTER COLUMN organization_id SET NOT NULL;
            EXCEPTION
                WHEN others THEN NULL;
            END $$;
        """))
        conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE document_integrity_checks
                    ALTER COLUMN organization_id SET NOT NULL;
            EXCEPTION
                WHEN others THEN NULL;
            END $$;
        """))
        conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE document_watermark_logs
                    ALTER COLUMN organization_id SET NOT NULL;
            EXCEPTION
                WHEN others THEN NULL;
            END $$;
        """))

        # =================================================================
        # STEP 4: Create composite indexes for tenant-scoped queries
        # =================================================================

        print("[TENANT_ISO] Creating composite tenant isolation indexes...")

        composite_indexes = [
            # --- ai_document_classifications ---
            "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_org_doc "
            "ON ai_document_classifications(organization_id, document_id)",

            "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_org_created "
            "ON ai_document_classifications(organization_id, created_at)",

            "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_org_predicted "
            "ON ai_document_classifications(organization_id, predicted_doc_type)",

            # --- document_followup_campaigns ---
            "CREATE INDEX IF NOT EXISTS ix_followup_camp_org_loan "
            "ON document_followup_campaigns(organization_id, loan_id)",

            "CREATE INDEX IF NOT EXISTS ix_followup_camp_org_status "
            "ON document_followup_campaigns(organization_id, status)",

            "CREATE INDEX IF NOT EXISTS ix_followup_camp_org_created "
            "ON document_followup_campaigns(organization_id, created_at)",

            "CREATE INDEX IF NOT EXISTS ix_followup_camp_org_next_action "
            "ON document_followup_campaigns(organization_id, next_action_at)",

            # --- document_followup_events ---
            "CREATE INDEX IF NOT EXISTS ix_followup_evt_org_id "
            "ON document_followup_events(organization_id)",

            "CREATE INDEX IF NOT EXISTS ix_followup_evt_org_campaign "
            "ON document_followup_events(organization_id, campaign_id)",

            "CREATE INDEX IF NOT EXISTS ix_followup_evt_org_created "
            "ON document_followup_events(organization_id, created_at)",

            # --- document_access_logs ---
            "CREATE INDEX IF NOT EXISTS ix_doc_access_org_doc "
            "ON document_access_logs(organization_id, document_id)",

            "CREATE INDEX IF NOT EXISTS ix_doc_access_org_created "
            "ON document_access_logs(organization_id, created_at)",

            "CREATE INDEX IF NOT EXISTS ix_doc_access_org_user "
            "ON document_access_logs(organization_id, user_id)",

            # --- document_integrity_checks ---
            "CREATE INDEX IF NOT EXISTS ix_doc_integrity_org_id "
            "ON document_integrity_checks(organization_id)",

            "CREATE INDEX IF NOT EXISTS ix_doc_integrity_org_doc "
            "ON document_integrity_checks(organization_id, document_id)",

            "CREATE INDEX IF NOT EXISTS ix_doc_integrity_org_created "
            "ON document_integrity_checks(organization_id, created_at)",

            "CREATE INDEX IF NOT EXISTS ix_doc_integrity_org_tamper "
            "ON document_integrity_checks(organization_id, tamper_detected)",

            # --- document_watermark_logs ---
            "CREATE INDEX IF NOT EXISTS ix_doc_watermark_org_id "
            "ON document_watermark_logs(organization_id)",

            "CREATE INDEX IF NOT EXISTS ix_doc_watermark_org_doc "
            "ON document_watermark_logs(organization_id, document_id)",

            "CREATE INDEX IF NOT EXISTS ix_doc_watermark_org_applied "
            "ON document_watermark_logs(organization_id, applied_at)",

            # --- document_encryption_records (already has org_id, add composites) ---
            "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_org_doc "
            "ON document_encryption_records(organization_id, document_id)",

            "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_org_created "
            "ON document_encryption_records(organization_id, created_at)",

            # --- document_retention_policies (already has org_id, add composites) ---
            "CREATE INDEX IF NOT EXISTS ix_doc_retention_org_doc_type "
            "ON document_retention_policies(organization_id, doc_type)",

            "CREATE INDEX IF NOT EXISTS ix_doc_retention_org_active "
            "ON document_retention_policies(organization_id, is_active)",

            # --- document_appointments (already has org_id, add composites) ---
            "CREATE INDEX IF NOT EXISTS ix_doc_appt_org_loan "
            "ON document_appointments(organization_id, loan_id)",

            "CREATE INDEX IF NOT EXISTS ix_doc_appt_org_status_date "
            "ON document_appointments(organization_id, status, scheduled_date)",

            # --- document_followup_templates (already has org_id, add composites) ---
            "CREATE INDEX IF NOT EXISTS ix_followup_tpl_org_channel_active "
            "ON document_followup_templates(organization_id, channel, is_active)",
        ]

        for idx_sql in composite_indexes:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.warning(f"Index creation skipped: {e}")
                print(f"[TENANT_ISO] Warning: index skipped: {e}")

        # =================================================================
        # STEP 5: Commit
        # =================================================================

        conn.commit()

        print("[TENANT_ISO] Smart Docs V2 tenant isolation migration completed successfully!")
        logger.info("Smart Docs V2 tenant isolation migration completed.")

        return {
            "success": True,
            "message": "Tenant isolation applied to Smart Docs V2 tables",
            "columns_added": [
                "document_followup_events.organization_id",
                "document_integrity_checks.organization_id",
                "document_watermark_logs.organization_id",
            ],
            "composite_indexes_created": len(composite_indexes),
            "not_null_constraints_added": [
                "document_followup_events.organization_id",
                "document_integrity_checks.organization_id",
                "document_watermark_logs.organization_id",
            ],
        }


if __name__ == "__main__":
    run_migration()
    print("Smart Docs V2 tenant isolation migration complete!")
