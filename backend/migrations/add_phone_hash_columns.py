"""
Migration: Add phone_hash columns for privacy-preserving phone lookups.

Adds SHA-256 hash columns alongside existing plaintext/encrypted phone columns
so that lookups can use hashes instead of exposing raw phone numbers.  The
original phone columns are preserved for display; the hash columns are indexed
for O(1) equality lookups.

Scope:
  - All tables with plaintext (non-encrypted) phone columns used for lookups
  - Includes a backfill function that hashes existing phone values

Safe to re-run: uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS and
CREATE INDEX IF NOT EXISTS.

Usage:
    python -m migrations.add_phone_hash_columns              # run migration + backfill
    python -m migrations.add_phone_hash_columns --no-backfill  # schema only
    python -m migrations.add_phone_hash_columns --rollback   # drop hash columns
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# ---------------------------------------------------------------------------
# Table → (source_phone_column, hash_column_name) mapping
#
# Only tables with PLAINTEXT phone columns used for lookups are included.
# EncryptedString columns (users.phone, loans.borrower_phone, etc.) are
# excluded because they are already protected at rest; adding hashes to
# those would require decrypting every row, which is a separate effort.
# ---------------------------------------------------------------------------
PHONE_HASH_COLUMNS = [
    # ── Core CRM ──────────────────────────────────────────────────────────
    # leads.phone — primary contact lookup column (String, indexed)
    ("leads", "phone", "phone_hash"),

    # referral_partners.phone — partner contact lookup
    ("referral_partners", "phone", "phone_hash"),

    # loan_team_members.phone — team member lookup
    ("loan_team_members", "phone", "phone_hash"),

    # mum_clients.phone — MUM client lookup
    ("mum_clients", "phone", "phone_hash"),

    # ── SMS & Messaging ──────────────────────────────────────────────────
    # sms_conversations.phone_number — conversation thread lookup
    ("sms_conversations", "phone_number", "phone_number_hash"),

    # sms_opt_outs.phone_number — TCPA opt-out check
    ("sms_opt_outs", "phone_number", "phone_number_hash"),

    # sms_consent.phone_number — TCPA consent check
    ("sms_consent", "phone_number", "phone_number_hash"),

    # sms_compliance_log.phone_number — audit trail
    ("sms_compliance_log", "phone_number", "phone_number_hash"),

    # sms_dead_letters — failed message routing
    ("sms_dead_letters", "to_phone", "to_phone_hash"),
    ("sms_dead_letters", "from_phone", "from_phone_hash"),

    # scheduled_sms_job_records.phone_number — scheduled SMS lookup
    ("scheduled_sms_job_records", "phone_number", "phone_number_hash"),

    # ── TCPA Compliance ──────────────────────────────────────────────────
    # tcpa_consents.phone_number — pre-call consent check
    ("tcpa_consents", "phone_number", "phone_number_hash"),

    # smart_docs_consent_records.phone — doc follow-up consent
    ("smart_docs_consent_records", "phone", "phone_hash"),

    # internal_dnc_entries.phone — DNC check
    ("internal_dnc_entries", "phone", "phone_hash"),

    # smart_docs_outreach_log.phone — frequency limiting
    ("smart_docs_outreach_log", "phone", "phone_hash"),

    # compliance_logs.phone_number — compliance audit (already masked, but hash adds lookup)
    ("compliance_logs", "phone_number", "phone_number_hash"),

    # ── Dialer & Telephony ───────────────────────────────────────────────
    # dialer_session_tasks.contact_phone — dialer contact lookup
    ("dialer_session_tasks", "contact_phone", "contact_phone_hash"),

    # call_logs.contact_phone — call history lookup
    ("call_logs", "contact_phone", "contact_phone_hash"),

    # active_calls.contact_phone — collision prevention lookup
    ("active_calls", "contact_phone", "contact_phone_hash"),

    # contact_dnc_status.phone_number — DNC check
    ("contact_dnc_status", "phone_number", "phone_number_hash"),

    # verified_caller_ids.phone_number — caller ID lookup
    ("verified_caller_ids", "phone_number", "phone_number_hash"),

    # call_dispositions.caller_phone — disposition lookup
    ("call_dispositions", "caller_phone", "caller_phone_hash"),

    # ── Voice & AI ───────────────────────────────────────────────────────
    # voice_workflows.contact_phone — inbound SMS matching
    ("voice_workflows", "contact_phone", "contact_phone_hash"),

    # ai_prospect_conversations.lead_phone — conversation routing
    ("ai_prospect_conversations", "lead_phone", "lead_phone_hash"),

    # live_transfers — transfer routing
    ("live_transfers", "caller_phone", "caller_phone_hash"),
    ("live_transfers", "lo_phone", "lo_phone_hash"),

    # ── Scheduling ───────────────────────────────────────────────────────
    # scheduler_appointments.phone_number — appointment lookup
    ("scheduler_appointments", "phone_number", "phone_number_hash"),

    # scheduler_appointments.attendee_phone — attendee lookup
    ("scheduler_appointments", "attendee_phone", "attendee_phone_hash"),

    # scheduler_slot_holds.held_for_phone — hold lookup
    ("scheduler_slot_holds", "held_for_phone", "held_for_phone_hash"),

    # ── Other ────────────────────────────────────────────────────────────
    # waiting_room_entries.phone — waitlist lookup
    ("waiting_room_entries", "phone", "phone_hash"),

    # esignature_recipients.phone — signer lookup
    ("esignature_recipients", "phone", "phone_hash"),

    # credit_monitoring_enrollments.phone — enrollment lookup
    ("credit_monitoring_enrollments", "phone", "phone_hash"),

    # vendors.contact_phone — vendor lookup
    ("vendors", "contact_phone", "contact_phone_hash"),

    # recovery_opt_outs.phone — opt-out lookup
    ("recovery_opt_outs", "phone", "phone_hash"),

    # document_followup_notifications.recipient_phone
    ("document_followup_notifications", "recipient_phone", "recipient_phone_hash"),

    # followup_cadence_enrollments.borrower_phone
    ("followup_cadence_enrollments", "borrower_phone", "borrower_phone_hash"),

    # document_followup_appointments.attendee_phone
    ("document_followup_appointments", "attendee_phone", "attendee_phone_hash"),

    # reminder_logs.recipient_phone
    ("reminder_logs", "recipient_phone", "recipient_phone_hash"),

    # app_completion_notifications.recipient_phone
    ("app_completion_notifications", "recipient_phone", "recipient_phone_hash"),

    # app_completion_sessions.borrower_phone
    ("app_completion_sessions", "borrower_phone", "borrower_phone_hash"),
]


def run_migration():
    """Add phone_hash columns and indexes to all applicable tables."""
    engine = create_engine(DATABASE_URL)
    is_postgres = "postgresql" in DATABASE_URL.lower()

    if not is_postgres:
        print("WARNING: This migration is designed for PostgreSQL. SQLite support is limited.")

    added = 0
    skipped = 0

    with engine.connect() as conn:
        for table, source_col, hash_col in PHONE_HASH_COLUMNS:
            # Check if table exists first
            if is_postgres:
                result = conn.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = :table)"
                ), {"table": table})
                if not result.scalar():
                    print(f"  [SKIP] {table}.{hash_col} — table does not exist")
                    skipped += 1
                    continue

            try:
                # Add the hash column
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS "
                    f"{hash_col} VARCHAR(64)"
                ))

                # Create index on the hash column
                index_name = f"ix_{table}_{hash_col}"
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {index_name} "
                    f"ON {table}({hash_col})"
                ))

                print(f"  [OK] {table}.{hash_col} (from {source_col})")
                added += 1

            except Exception as e:
                print(f"  [ERR] {table}.{hash_col}: {e}")
                skipped += 1

        conn.commit()

    print(f"\nMigration complete: {added} columns added, {skipped} skipped.")
    return added, skipped


def backfill_hashes():
    """Backfill phone_hash values for all existing rows with non-null phone numbers.

    Uses the phone_hash utility for consistent normalization and hashing.
    Processes in batches of 1000 to avoid locking large tables.
    """
    from utils.phone_hash import hash_phone

    engine = create_engine(DATABASE_URL)
    is_postgres = "postgresql" in DATABASE_URL.lower()

    if not is_postgres:
        print("WARNING: Backfill is designed for PostgreSQL.")

    total_updated = 0

    with engine.connect() as conn:
        for table, source_col, hash_col in PHONE_HASH_COLUMNS:
            # Check if table exists
            result = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :table)"
            ), {"table": table})
            if not result.scalar():
                continue

            # Check if hash column exists
            result = conn.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :col)"
            ), {"table": table, "col": hash_col})
            if not result.scalar():
                print(f"  [SKIP] {table}.{hash_col} — column does not exist, run migration first")
                continue

            # Count rows needing backfill
            result = conn.execute(text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE {source_col} IS NOT NULL AND {hash_col} IS NULL"
            ))
            pending = result.scalar()

            if pending == 0:
                print(f"  [OK] {table}.{hash_col} — already backfilled")
                continue

            print(f"  [BACKFILL] {table}.{hash_col} — {pending} rows to hash...")

            # Fetch and update in batches
            batch_size = 1000
            updated = 0

            # Determine primary key column — assume 'id' for all tables
            while True:
                rows = conn.execute(text(
                    f"SELECT id, {source_col} FROM {table} "
                    f"WHERE {source_col} IS NOT NULL AND {hash_col} IS NULL "
                    f"LIMIT :batch_size"
                ), {"batch_size": batch_size}).fetchall()

                if not rows:
                    break

                for row in rows:
                    row_id = row[0]
                    phone_value = row[1]
                    hashed = hash_phone(phone_value)

                    if hashed:
                        conn.execute(text(
                            f"UPDATE {table} SET {hash_col} = :hash_val "
                            f"WHERE id = :row_id"
                        ), {"hash_val": hashed, "row_id": row_id})
                        updated += 1

                conn.commit()

            print(f"           → {updated} rows updated")
            total_updated += updated

    print(f"\nBackfill complete: {total_updated} total rows updated.")
    return total_updated


def rollback_migration():
    """Drop all phone_hash columns added by this migration."""
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        for table, _source_col, hash_col in PHONE_HASH_COLUMNS:
            try:
                # Drop index first
                index_name = f"ix_{table}_{hash_col}"
                conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                # Drop column
                conn.execute(text(
                    f"ALTER TABLE {table} DROP COLUMN IF EXISTS {hash_col}"
                ))
                print(f"  [OK] Dropped {table}.{hash_col}")
            except Exception as e:
                print(f"  [ERR] {table}.{hash_col}: {e}")

        conn.commit()
        print("\nRollback complete.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Add phone_hash columns for privacy-preserving lookups"
    )
    parser.add_argument(
        "--rollback", action="store_true",
        help="Drop all phone_hash columns"
    )
    parser.add_argument(
        "--no-backfill", action="store_true",
        help="Only add columns/indexes, skip backfilling existing data"
    )
    parser.add_argument(
        "--backfill-only", action="store_true",
        help="Only backfill hashes (columns must already exist)"
    )
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    elif args.backfill_only:
        backfill_hashes()
    else:
        run_migration()
        if not args.no_backfill:
            print("\n--- Backfilling existing phone numbers ---\n")
            backfill_hashes()
