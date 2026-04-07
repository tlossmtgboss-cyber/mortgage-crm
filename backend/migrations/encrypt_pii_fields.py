"""
Migration: Convert PII columns to TEXT for EncryptedString compatibility.

EncryptedString stores Fernet-encrypted ciphertext which can be longer than
the original value. This migration ensures all affected columns are TEXT type
(no length constraints) so encrypted values fit.

NOTE: This migration only changes column types. Existing plaintext data will
NOT be automatically encrypted. A separate data-migration script
(encrypt_existing_pii.py) should be run to encrypt existing rows.

Run: python -m migrations.encrypt_pii_fields
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

# All PII columns that were changed to EncryptedString, grouped by table.
# Format: (table_name, column_name)
PII_COLUMNS = [
    # borrower_profiles
    ("borrower_profiles", "first_name"),
    ("borrower_profiles", "last_name"),
    ("borrower_profiles", "consent_ip_address"),

    # borrower_auth_events
    ("borrower_auth_events", "ip_address"),

    # borrower_applications
    ("borrower_applications", "borrower_first_name"),
    ("borrower_applications", "borrower_last_name"),
    ("borrower_applications", "borrower_phone"),
    ("borrower_applications", "coborrower_email"),
    ("borrower_applications", "credit_auth_ip_address"),
    ("borrower_applications", "credit_auth_ssn_last4"),

    # coborrower_invitations
    ("coborrower_invitations", "email"),
    ("coborrower_invitations", "first_name"),
    ("coborrower_invitations", "last_name"),
    ("coborrower_invitations", "phone"),
    ("coborrower_invitations", "credit_auth_ip_address"),

    # application_events
    ("application_events", "actor_email"),
    ("application_events", "ip_address"),

    # application_notifications
    ("application_notifications", "recipient_email"),
    ("application_notifications", "recipient_phone"),

    # application_sessions
    ("application_sessions", "device_fingerprint"),
    ("application_sessions", "ip_address"),

    # voice_application_sessions
    ("voice_application_sessions", "phone_number"),

    # leads (co-applicant and address fields only; primary email/phone are indexed)
    ("leads", "co_applicant_name"),
    ("leads", "co_applicant_email"),
    ("leads", "co_applicant_phone"),
    ("leads", "address"),
    ("leads", "city"),
    ("leads", "state"),
    ("leads", "zip_code"),
    ("leads", "property_address"),

    # loans (borrower PII and property address)
    ("loans", "borrower_email"),
    ("loans", "borrower_phone"),
    ("loans", "coborrower_name"),
    ("loans", "co_borrower_email"),
    ("loans", "co_borrower_phone"),
    ("loans", "property_address"),
    ("loans", "property_city"),
    ("loans", "property_state"),
    ("loans", "property_zip"),

    # sms_messages
    ("sms_messages", "to_number"),
    ("sms_messages", "from_number"),

    # sms_conversations
    ("sms_conversations", "contact_name"),

    # email_messages
    ("email_messages", "to_email"),
    ("email_messages", "from_email"),

    # emails
    ("emails", "sender_name"),

    # email_drafts
    ("email_drafts", "recipient_name"),

    # email_verification_tokens
    ("email_verification_tokens", "email"),

    # teams_messages
    ("teams_messages", "to_user"),
    ("teams_messages", "from_user"),

    # voicemail_drops
    ("voicemail_drops", "contact_name"),
    ("voicemail_drops", "phone_number"),
    ("voicemail_drops", "contact_email"),

    # integration_credentials
    ("integration_credentials", "api_key"),
    ("integration_credentials", "refresh_token"),
    ("integration_credentials", "access_token"),

    # users
    ("users", "first_name"),
    ("users", "last_name"),
    ("users", "phone"),
    ("users", "business_address"),
    ("users", "mfa_secret"),

    # email_signatures
    ("email_signatures", "email"),
    ("email_signatures", "office_phone"),
    ("email_signatures", "cell_phone"),
    ("email_signatures", "fax"),
    ("email_signatures", "address"),
]


def run_migration(engine):
    """
    Alter PII columns to TEXT type for EncryptedString compatibility.

    EncryptedString uses String as its impl, which maps to TEXT in PostgreSQL
    when no length is specified. Columns that previously had VARCHAR(N) need
    to be widened to TEXT so Fernet ciphertext (typically 100-200+ chars) fits.

    This is idempotent -- re-running on already-TEXT columns is a no-op in
    PostgreSQL (ALTER TYPE TEXT on a TEXT column succeeds silently).
    """
    migrated = 0
    skipped = 0
    errors = 0

    with engine.begin() as conn:
        for table_name, column_name in PII_COLUMNS:
            try:
                # Check if table exists
                result = conn.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = :table_name)"
                ), {"table_name": table_name})
                if not result.scalar():
                    logger.info(f"  Table {table_name} does not exist, skipping {column_name}")
                    skipped += 1
                    continue

                # Check if column exists
                result = conn.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :table_name AND column_name = :column_name)"
                ), {"table_name": table_name, "column_name": column_name})
                if not result.scalar():
                    logger.info(f"  Column {table_name}.{column_name} does not exist, skipping")
                    skipped += 1
                    continue

                # Alter column type to TEXT (supports unlimited-length encrypted values)
                conn.execute(text(
                    f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE TEXT'
                ))
                migrated += 1
                logger.info(f"  Migrated {table_name}.{column_name} -> TEXT")

            except Exception as e:
                errors += 1
                logger.error(f"  Error migrating {table_name}.{column_name}: {e}")

    logger.info(
        f"PII column migration complete: {migrated} migrated, "
        f"{skipped} skipped, {errors} errors"
    )
    return {"migrated": migrated, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    import sys
    import os

    # Add backend to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== PII Column Type Migration (EncryptedString compatibility) ===")

    from db import engine
    result = run_migration(engine)

    logger.info(f"\nResult: {result}")
