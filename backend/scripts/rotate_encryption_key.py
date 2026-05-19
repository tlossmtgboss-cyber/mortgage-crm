#!/usr/bin/env python3
"""
Encryption Key Rotation Script

Re-encrypts all EncryptedString column values from the old key to the new key.

Prerequisites:
  1. Set DATA_ENCRYPTION_KEY to the NEW Fernet key in the environment.
  2. Set DATA_ENCRYPTION_KEY_PREVIOUS to the OLD Fernet key in the environment.

Usage:
  # Dry run (default) — reports what would be re-encrypted, changes nothing
  python scripts/rotate_encryption_key.py

  # Execute — actually re-encrypts values in the database
  python scripts/rotate_encryption_key.py --execute

  # Custom batch size
  python scripts/rotate_encryption_key.py --execute --batch-size 50

How it works:
  1. Connects to the database using DATABASE_URL.
  2. Iterates over all known models that use EncryptedString columns.
  3. For each row, tries to decrypt each encrypted column with the NEW key.
     - If it succeeds, the value is already encrypted with the new key — skip.
     - If it fails, decrypts with the OLD key, re-encrypts with the NEW key.
  4. Batch-commits every N rows to limit memory usage.

Safety:
  - Dry-run mode by default. Pass --execute to actually write.
  - Batch processing (100 rows at a time) to avoid memory spikes.
  - Each batch is committed independently so partial progress is saved.
  - Idempotent: running twice is safe (already-rotated values are skipped).
"""

import argparse
import logging
import os
import sys
import time

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# Model registry: (table_name, primary_key_column, [encrypted_column_names])
#
# These are all the models that use EncryptedString from encryption_utils.py
# (DATA_ENCRYPTION_KEY). Models using services/encryption.py (ENCRYPTION_KEY)
# have a different key derivation and are NOT covered here.
# ============================================================================

ENCRYPTED_MODELS = [
    # database/models/lead_loan.py - Lead
    ("leads", "id", [
        "co_applicant_name", "co_applicant_email", "co_applicant_phone",
        "address", "city", "state", "zip_code", "property_address",
    ]),
    # database/models/lead_loan.py - Loan
    ("loans", "id", [
        "borrower_email", "borrower_phone",
        "coborrower_name", "co_borrower_email", "co_borrower_phone",
        "property_address", "property_city", "property_state", "property_zip",
    ]),
    # database/models/core.py - User
    ("users", "id", [
        "first_name", "last_name", "phone", "business_address", "mfa_secret",
    ]),
    # database/models/core.py - Branch (EmailSignature contact fields)
    ("email_signatures", "id", [
        "email", "office_phone", "cell_phone", "fax", "address",
    ]),
    # database/models/borrower.py - BorrowerProfile
    ("borrower_profiles", "id", [
        "first_name", "last_name", "consent_ip_address",
    ]),
    # database/models/borrower.py - BorrowerAuthEvent
    ("borrower_auth_events", "id", [
        "ip_address",
    ]),
    # database/models/borrower.py - BorrowerApplication
    ("borrower_applications", "id", [
        "borrower_first_name", "borrower_last_name", "borrower_phone",
        "coborrower_email", "credit_auth_ip_address", "credit_auth_ssn_last4",
        "ssn_encrypted", "co_ssn_encrypted",
    ]),
    # database/models/borrower.py - CoborrowerInvitation
    ("coborrower_invitations", "id", [
        "email", "first_name", "last_name", "phone",
        "credit_auth_ip_address",
    ]),
    # database/models/borrower.py - ApplicationEvent
    ("application_events", "id", [
        "actor_email", "ip_address",
    ]),
    # database/models/borrower.py - ApplicationNotification
    ("application_notifications", "id", [
        "recipient_email", "recipient_phone",
    ]),
    # database/models/borrower.py - ApplicationSession
    ("application_sessions", "id", [
        "device_fingerprint", "ip_address",
    ]),
    # database/models/borrower.py - VoiceApplicationSession
    ("voice_application_sessions", "id", [
        "phone_number",
    ]),
    # database/models/communication.py - SMSMessage
    ("sms_messages", "id", [
        "to_number", "from_number",
    ]),
    # database/models/communication.py - SMSConversation
    ("sms_conversations", "id", [
        "contact_name",
    ]),
    # database/models/communication.py - EmailMessage
    ("email_messages", "id", [
        "to_email", "from_email",
    ]),
    # database/models/communication.py - Email (fetched from Graph)
    ("emails", "id", [
        "sender_name",
    ]),
    # database/models/communication.py - EmailDraft
    ("email_drafts", "id", [
        "recipient_name",
    ]),
    # database/models/communication.py - EmailVerificationToken
    ("email_verification_tokens", "id", [
        "email",
    ]),
    # database/models/communication.py - TeamsMessage
    ("teams_messages", "id", [
        "to_user", "from_user",
    ]),
    # database/models/communication.py - VoicemailDrop
    ("voicemail_drops", "id", [
        "contact_name", "phone_number", "contact_email",
    ]),
    # database/models/communication.py - IntegrationCredential
    ("integration_credentials", "id", [
        "api_key", "refresh_token", "access_token",
    ]),
]


def validate_keys():
    """Validate that both encryption keys are set and are valid Fernet keys."""
    from cryptography.fernet import Fernet

    current_raw = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    previous_raw = os.getenv("DATA_ENCRYPTION_KEY_PREVIOUS", "").strip()

    if not current_raw:
        logger.error("DATA_ENCRYPTION_KEY is not set. This should be the NEW key.")
        return None, None
    if not previous_raw:
        logger.error("DATA_ENCRYPTION_KEY_PREVIOUS is not set. This should be the OLD key.")
        return None, None

    try:
        current_key = current_raw.encode()
        Fernet(current_key)
    except Exception as e:
        logger.error(f"DATA_ENCRYPTION_KEY is not a valid Fernet key: {e}")
        return None, None

    try:
        previous_key = previous_raw.encode()
        Fernet(previous_key)
    except Exception as e:
        logger.error(f"DATA_ENCRYPTION_KEY_PREVIOUS is not a valid Fernet key: {e}")
        return None, None

    if current_key == previous_key:
        logger.error("DATA_ENCRYPTION_KEY and DATA_ENCRYPTION_KEY_PREVIOUS are identical. Nothing to rotate.")
        return None, None

    return Fernet(current_key), Fernet(previous_key)


def is_fernet_token(value: str) -> bool:
    """Heuristic check whether a string looks like a Fernet token."""
    import base64
    if not value or len(value) < 50:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value.encode("utf-8"))
        return decoded[0:1] == b"\x80"
    except Exception as _exc:  # noqa: BLE001
        return False


def rotate_table(engine, table_name, pk_col, encrypted_cols, new_fernet, old_fernet, batch_size, dry_run):
    """Re-encrypt all EncryptedString columns in a single table.

    Returns:
        (total_rows, rotated_values, skipped_values, error_values)
    """
    from sqlalchemy import text

    total_rows = 0
    rotated_values = 0
    skipped_values = 0
    error_values = 0

    # Check if table exists
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
        ), {"t": table_name})
        if not result.scalar():
            logger.info(f"  Table {table_name} does not exist — skipping")
            return 0, 0, 0, 0

        # Check which encrypted columns actually exist in the table
        existing_cols = []
        for col in encrypted_cols:
            result = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c)"
            ), {"t": table_name, "c": col})
            if result.scalar():
                existing_cols.append(col)
            else:
                logger.debug(f"  Column {table_name}.{col} does not exist — skipping")

        if not existing_cols:
            logger.info(f"  Table {table_name} has no encrypted columns present — skipping")
            return 0, 0, 0, 0

    # Process in batches
    col_list = ", ".join([pk_col] + existing_cols)
    offset = 0

    while True:
        with engine.connect() as conn:
            rows = conn.execute(text(
                f"SELECT {col_list} FROM {table_name} ORDER BY {pk_col} LIMIT :limit OFFSET :offset"
            ), {"limit": batch_size, "offset": offset}).fetchall()

        if not rows:
            break

        updates = []
        for row in rows:
            total_rows += 1
            row_dict = dict(row._mapping)
            pk_value = row_dict[pk_col]
            changed = False

            for col in existing_cols:
                value = row_dict.get(col)
                if not value or not is_fernet_token(value):
                    skipped_values += 1
                    continue

                # Try decrypting with new key — if it works, already rotated
                try:
                    new_fernet.decrypt(value.encode("utf-8"))
                    skipped_values += 1
                    continue
                except Exception as _exc:  # noqa: BLE001
                    pass

                # Try decrypting with old key and re-encrypting
                try:
                    plaintext = old_fernet.decrypt(value.encode("utf-8"))
                    new_ciphertext = new_fernet.encrypt(plaintext).decode("utf-8")
                    updates.append((pk_value, col, new_ciphertext))
                    rotated_values += 1
                    changed = True
                except Exception as e:
                    error_values += 1
                    logger.warning(
                        f"  Cannot decrypt {table_name}.{col} (pk={pk_value}): {e} — "
                        "may be legacy plaintext or corrupted"
                    )

        # Apply updates for this batch
        if updates and not dry_run:
            with engine.begin() as conn:
                for pk_value, col, new_ciphertext in updates:
                    conn.execute(text(
                        f"UPDATE {table_name} SET {col} = :val WHERE {pk_col} = :pk"
                    ), {"val": new_ciphertext, "pk": pk_value})

        offset += batch_size

        if total_rows % 1000 == 0 and total_rows > 0:
            logger.info(f"  ... processed {total_rows} rows")

    return total_rows, rotated_values, skipped_values, error_values


def main():
    parser = argparse.ArgumentParser(
        description="Re-encrypt all EncryptedString columns with the new DATA_ENCRYPTION_KEY."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the re-encryption. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of rows to process per batch (default: 100).",
    )
    args = parser.parse_args()

    dry_run = not args.execute
    if dry_run:
        logger.info("=== DRY RUN MODE (pass --execute to actually re-encrypt) ===")
    else:
        logger.info("=== EXECUTE MODE — re-encrypting values in the database ===")

    # Validate keys
    new_fernet, old_fernet = validate_keys()
    if not new_fernet or not old_fernet:
        sys.exit(1)

    logger.info("Both encryption keys validated successfully.")

    # Connect to database
    from db import engine as db_engine
    logger.info(f"Connected to database.")

    # Process each model
    grand_total_rows = 0
    grand_rotated = 0
    grand_skipped = 0
    grand_errors = 0
    start_time = time.time()

    for table_name, pk_col, encrypted_cols in ENCRYPTED_MODELS:
        logger.info(f"Processing {table_name} ({len(encrypted_cols)} encrypted columns)...")
        rows, rotated, skipped, errors = rotate_table(
            db_engine, table_name, pk_col, encrypted_cols,
            new_fernet, old_fernet, args.batch_size, dry_run,
        )
        grand_total_rows += rows
        grand_rotated += rotated
        grand_skipped += skipped
        grand_errors += errors

        if rows > 0:
            logger.info(
                f"  {table_name}: {rows} rows, "
                f"{rotated} values rotated, {skipped} skipped, {errors} errors"
            )

    elapsed = time.time() - start_time

    # Summary
    logger.info("=" * 60)
    logger.info("ROTATION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Mode:             {'DRY RUN' if dry_run else 'EXECUTED'}")
    logger.info(f"Tables processed: {len(ENCRYPTED_MODELS)}")
    logger.info(f"Total rows:       {grand_total_rows}")
    logger.info(f"Values rotated:   {grand_rotated}")
    logger.info(f"Values skipped:   {grand_skipped} (already on new key or not encrypted)")
    logger.info(f"Errors:           {grand_errors}")
    logger.info(f"Elapsed:          {elapsed:.1f}s")

    if dry_run and grand_rotated > 0:
        logger.info("")
        logger.info(
            f"Found {grand_rotated} values that need re-encryption. "
            "Run with --execute to apply changes."
        )

    if grand_errors > 0:
        logger.warning(
            f"{grand_errors} values could not be decrypted with either key. "
            "These may be legacy plaintext values or corrupted data."
        )

    sys.exit(0 if grand_errors == 0 else 1)


if __name__ == "__main__":
    main()
