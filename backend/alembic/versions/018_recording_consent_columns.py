"""Recording consent gate columns on call_sessions + organizations.

Revision ID: 018_recording_consent
Revises: 017_baseline_stamp
Create Date: 2026-06-10

The Call Intelligence consent routes (recording_consent_routes.py) and
RecordingConsentService write these columns, but the call_sessions table
created by init_db.py only has the call-monitoring column set, and
migrations/migration_recording_consent.sql was never wired into startup.
This migration is the guaranteed-to-run home for the schema change — it
executes via run_migrations.py in start.py before the app boots, regardless
of the SKIP_LEGACY_MIGRATIONS kill-switch that bypasses init_db()'s raw SQL.

Also drops the CHECK constraints from migration_recording_consent.sql if it
was ever applied manually: its consent_disclosure_method CHECK does not
allow 'browser_local' (written by the browser-mode flow) and its
recording_consent_status CHECK does not allow 'browser_pending'.

All statements are idempotent (IF NOT EXISTS / IF EXISTS).
"""

from alembic import op
import sqlalchemy as sa  # noqa: F401 — required by Alembic scaffold

revision = "018_recording_consent"
down_revision = "017_baseline_stamp"
branch_labels = None
depends_on = None

_CALL_SESSION_COLUMNS = [
    ("call_control_id", "VARCHAR(255)"),
    ("loan_officer_id", "VARCHAR(36)"),
    ("contact_id", "VARCHAR(36)"),
    ("borrower_state", "VARCHAR(2)"),
    ("recording_consent_status", "VARCHAR(20) DEFAULT 'pending'"),
    ("consent_requirement", "VARCHAR(20)"),
    ("consent_disclosed_at", "TIMESTAMPTZ"),
    ("consent_disclosure_method", "VARCHAR(20)"),
    ("is_two_party_state", "BOOLEAN DEFAULT false"),
    ("consent_override_by", "VARCHAR(36)"),
    ("consent_override_at", "TIMESTAMPTZ"),
    ("activated_at", "TIMESTAMPTZ"),
    ("call_ended_at", "TIMESTAMPTZ"),
]


def upgrade():
    for name, ddl_type in _CALL_SESSION_COLUMNS:
        op.execute(
            f"ALTER TABLE call_sessions ADD COLUMN IF NOT EXISTS {name} {ddl_type}"
        )

    # Stale CHECK constraints from the never-wired manual SQL migration —
    # they reject values the application actually writes.
    op.execute(
        "ALTER TABLE call_sessions DROP CONSTRAINT IF EXISTS "
        "call_sessions_recording_consent_status_check"
    )
    op.execute(
        "ALTER TABLE call_sessions DROP CONSTRAINT IF EXISTS "
        "call_sessions_consent_disclosure_method_check"
    )
    op.execute(
        "ALTER TABLE call_sessions DROP CONSTRAINT IF EXISTS "
        "call_sessions_consent_requirement_check"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_call_sessions_consent_status "
        "ON call_sessions (recording_consent_status)"
    )

    op.execute(
        "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS "
        "recording_consent_config JSONB"
    )


def downgrade():
    """Columns are additive and shared with live data — leave in place."""
    pass
