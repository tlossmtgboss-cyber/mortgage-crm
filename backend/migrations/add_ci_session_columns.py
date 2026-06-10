"""
Migration: Add CI session columns to call_sessions table

The call_sessions table was created for call monitoring (call_sid, user_id, lead_id, provider).
The CI consent routes also use call_sessions but expect additional columns:
  - call_control_id, loan_officer_id, contact_id, borrower_state
  - recording_consent_status, activated_at, consent_override_by, consent_override_at
  - call_ended_at

This migration adds the missing columns so both call monitoring and CI consent
coexist on the same table.

Usage:
    python -m migrations.add_ci_session_columns
"""

import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    if engine is None:
        from db import engine as _engine
        engine = _engine

    columns = [
        ("call_sessions", "call_control_id", "VARCHAR(255)"),
        ("call_sessions", "loan_officer_id", "VARCHAR(255)"),
        ("call_sessions", "contact_id", "VARCHAR(255)"),
        ("call_sessions", "borrower_state", "VARCHAR(50)"),
        ("call_sessions", "recording_consent_status", "VARCHAR(50) DEFAULT 'pending'"),
        ("call_sessions", "activated_at", "TIMESTAMP WITH TIME ZONE"),
        ("call_sessions", "consent_override_by", "VARCHAR(255)"),
        ("call_sessions", "consent_override_at", "TIMESTAMP WITH TIME ZONE"),
        ("call_sessions", "call_ended_at", "TIMESTAMP WITH TIME ZONE"),
        # Written by RecordingConsentService._update_consent — omitting these
        # leaves browser-mode /session/start 500ing on the first UPDATE.
        ("call_sessions", "consent_requirement", "VARCHAR(20)"),
        ("call_sessions", "consent_disclosed_at", "TIMESTAMP WITH TIME ZONE"),
        ("call_sessions", "consent_disclosure_method", "VARCHAR(20)"),
        ("call_sessions", "is_two_party_state", "BOOLEAN DEFAULT false"),
        ("organizations", "recording_consent_config", "JSONB"),
    ]

    with engine.connect() as conn:
        for table, column, col_type in columns:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                ))
                logger.info(f"Added {table}.{column}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.info(f"{table}.{column} already exists")
                else:
                    logger.error(f"Failed to add {table}.{column}: {e}")

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_call_sessions_loan_officer
            ON call_sessions (loan_officer_id)
            WHERE loan_officer_id IS NOT NULL
        """))

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_call_sessions_consent_status
            ON call_sessions (recording_consent_status)
            WHERE recording_consent_status IS NOT NULL
        """))

        conn.commit()
        logger.info("CI session columns migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
