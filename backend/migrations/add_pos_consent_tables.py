"""
Migration: POS Consent Tables + PENDING_CONSENT Status
======================================================
Creates credit_authorizations and econsent_agreements tables for the
voice-complete consent flow, and adds PENDING_CONSENT to the
applicationstatus PostgreSQL enum.

Run:
    python -m migrations.add_pos_consent_tables
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def run_migration():
    from sqlalchemy import text
    from db import engine

    with engine.connect() as conn:
        # Add PENDING_CONSENT to the applicationstatus enum (both cases)
        for val in ['pending_consent', 'PENDING_CONSENT']:
            try:
                conn.execute(text(
                    f"ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS '{val}'"
                ))
                conn.commit()
                logger.info("Added '%s' to applicationstatus enum", val)
            except Exception as e:
                logger.info("applicationstatus enum update skipped for '%s': %s", val, e)
                conn.rollback()

        # Convert borrower_applications.status from enum to VARCHAR (same pattern as leads/loans)
        try:
            conn.execute(text("""
                ALTER TABLE borrower_applications
                ALTER COLUMN status TYPE VARCHAR(50) USING status::text
            """))
            conn.commit()
            logger.info("Converted borrower_applications.status to VARCHAR")
        except Exception as e:
            logger.info("borrower_applications.status conversion skipped: %s", e)
            conn.rollback()

        # Create credit_authorizations table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS credit_authorizations (
                id SERIAL PRIMARY KEY,
                uuid VARCHAR(36) UNIQUE NOT NULL,
                application_id INTEGER NOT NULL REFERENCES borrower_applications(id),
                organization_id INTEGER REFERENCES organizations(id),
                authorized BOOLEAN NOT NULL DEFAULT FALSE,
                consent_text_version VARCHAR(50) NOT NULL,
                consent_text_hash VARCHAR(64) NOT NULL,
                typed_full_name VARCHAR(255) NOT NULL,
                ip_address VARCHAR(512) NOT NULL,
                user_agent VARCHAR(512) NOT NULL,
                authorized_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_credit_auth_application_id
            ON credit_authorizations (application_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_credit_auth_organization_id
            ON credit_authorizations (organization_id)
        """))
        conn.commit()
        logger.info("Created credit_authorizations table")

        # Create econsent_agreements table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS econsent_agreements (
                id SERIAL PRIMARY KEY,
                uuid VARCHAR(36) UNIQUE NOT NULL,
                application_id INTEGER NOT NULL REFERENCES borrower_applications(id),
                organization_id INTEGER REFERENCES organizations(id),
                consented BOOLEAN NOT NULL DEFAULT FALSE,
                consent_text_version VARCHAR(50) NOT NULL,
                consent_text_hash VARCHAR(64) NOT NULL,
                typed_full_name VARCHAR(255) NOT NULL,
                hardware_software_requirements_shown TEXT NOT NULL,
                right_to_withdraw_shown TEXT NOT NULL,
                paper_copy_info_shown TEXT NOT NULL,
                ip_address VARCHAR(512) NOT NULL,
                user_agent VARCHAR(512) NOT NULL,
                consented_at TIMESTAMP WITH TIME ZONE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_econsent_application_id
            ON econsent_agreements (application_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_econsent_organization_id
            ON econsent_agreements (organization_id)
        """))
        conn.commit()
        logger.info("Created econsent_agreements table")

        # Add all missing columns to borrower_applications
        missing_cols = [
            ("voice_completed_at", "TIMESTAMP WITH TIME ZONE"),
            ("voice_loan_id", "VARCHAR(255)"),
            ("consent_sms_sent_at", "TIMESTAMP WITH TIME ZONE"),
            ("consent_reminder_count", "INTEGER DEFAULT 0"),
            ("ssn_encrypted", "TEXT"),
            ("co_ssn_encrypted", "TEXT"),
            ("prequalification_data", "JSON"),
            ("device_info", "JSON"),
            ("applicant_ethnicity", "TEXT"),
            ("applicant_race", "TEXT"),
            ("applicant_sex", "TEXT"),
            ("applicant_age", "INTEGER"),
            ("co_applicant_ethnicity", "TEXT"),
            ("co_applicant_race", "TEXT"),
            ("co_applicant_sex", "TEXT"),
            ("co_applicant_age", "INTEGER"),
            ("gmi_collection_method", "VARCHAR"),
            ("gmi_collected_at", "TIMESTAMP WITH TIME ZONE"),
        ]
        for col_name, col_type in missing_cols:
            try:
                conn.execute(text(
                    f"ALTER TABLE borrower_applications ADD COLUMN IF NOT EXISTS "
                    f"{col_name} {col_type}"
                ))
            except Exception:
                pass
        conn.commit()
        logger.info("Added missing columns to borrower_applications")

        # Widen scope CHECK constraint on purl_access_tokens to include voice_review_submit
        try:
            conn.execute(text(
                "ALTER TABLE purl_access_tokens DROP CONSTRAINT IF EXISTS purl_access_tokens_scope_check"
            ))
            conn.execute(text(
                "ALTER TABLE purl_access_tokens ADD CONSTRAINT purl_access_tokens_scope_check "
                "CHECK (scope IN ('read', 'write', 'full', 'voice_review_submit'))"
            ))
            conn.commit()
            logger.info("Updated purl_access_tokens scope constraint")
        except Exception as e:
            logger.info("purl_access_tokens scope constraint update skipped: %s", e)
            conn.rollback()

    logger.info("POS consent migration complete")


if __name__ == "__main__":
    run_migration()
