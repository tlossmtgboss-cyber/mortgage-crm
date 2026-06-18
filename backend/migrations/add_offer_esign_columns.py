"""
Migration: add e-signature and background check columns to mm_offers.

New columns:
  E-signature (HelloSign/DocuSign):
    envelope_id, signing_url, signed_at, signed_ip, envelope_status

  Background check (Checkr):
    checkr_report_id, checkr_invitation_url, checkr_status

Run this once; all ALTER TABLE statements are guarded with IF NOT EXISTS.
"""

from sqlalchemy import text
from database import engine
import logging

logger = logging.getLogger(__name__)


def run_migration():
    migration_sql = """
    DO $$
    BEGIN
        -- E-signature columns
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_offers' AND column_name = 'envelope_id'
        ) THEN
            ALTER TABLE mm_offers ADD COLUMN envelope_id VARCHAR(255);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_offers' AND column_name = 'signing_url'
        ) THEN
            ALTER TABLE mm_offers ADD COLUMN signing_url TEXT;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_offers' AND column_name = 'signed_at'
        ) THEN
            ALTER TABLE mm_offers ADD COLUMN signed_at TIMESTAMPTZ;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_offers' AND column_name = 'signed_ip'
        ) THEN
            ALTER TABLE mm_offers ADD COLUMN signed_ip VARCHAR(45);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_offers' AND column_name = 'envelope_status'
        ) THEN
            ALTER TABLE mm_offers ADD COLUMN envelope_status VARCHAR(50);
        END IF;

        -- Background check columns
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_offers' AND column_name = 'checkr_report_id'
        ) THEN
            ALTER TABLE mm_offers ADD COLUMN checkr_report_id VARCHAR(255);
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_offers' AND column_name = 'checkr_invitation_url'
        ) THEN
            ALTER TABLE mm_offers ADD COLUMN checkr_invitation_url TEXT;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'mm_offers' AND column_name = 'checkr_status'
        ) THEN
            ALTER TABLE mm_offers ADD COLUMN checkr_status VARCHAR(50);
        END IF;
    END
    $$;
    """

    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()
    logger.info("add_offer_esign_columns migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
