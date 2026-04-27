"""
Create POS 1003 tables (standalone, no Alembic).

This migration creates five tables for the borrower-facing URLA 1003 application:
  - pos_applications        : URLA application root (one per borrower+loan)
  - pos_application_sections: Per-section JSONB draft data
  - pos_application_pii     : Encrypted SSN and DOB
  - pos_application_audit   : ECOA/TRID compliance audit trail
  - pos_ai_qa_messages      : Aria conversation history per application

All tables are scoped by organization_id and indexed for the access patterns
the POS module uses (lookup by contact_id, status filtering, audit by time).

Idempotent: safe to run multiple times (CREATE TABLE IF NOT EXISTS,
CREATE INDEX IF NOT EXISTS, DO $$ ... EXCEPTION WHEN duplicate_object).

Usage:
    # Standalone
    python migrations/2026_04_25_pos_tables.py

    # From init_db.py
    from migrations.2026_04_25_pos_tables import run_migration
    run_migration(engine)
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(engine=None) -> bool:
    """Create all POS 1003 tables, indexes, and constraints.

    Args:
        engine: SQLAlchemy engine.  If None, one is created from DATABASE_URL.

    Returns:
        True on success, False on failure.
    """
    if engine is None:
        database_url = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(database_url)

    sql_commands = [
        # ----------------------------------------------------------------
        # 1. pos_applications (root table)
        # ----------------------------------------------------------------
        """
        CREATE TABLE IF NOT EXISTS pos_applications (
            id              UUID        PRIMARY KEY,
            organization_id INTEGER     NOT NULL,
            workspace_id    INTEGER     NOT NULL,
            contact_id      INTEGER     NOT NULL,
            loan_id         INTEGER     REFERENCES loans(id) ON DELETE SET NULL,
            status          VARCHAR(32) NOT NULL DEFAULT 'draft',
            current_step    VARCHAR(32) NOT NULL DEFAULT 'personal',
            completion_pct  INTEGER     NOT NULL DEFAULT 0,
            submitted_at    TIMESTAMPTZ,
            submitted_appointment_id INTEGER REFERENCES scheduler_appointments(id) ON DELETE SET NULL,
            source_channel  VARCHAR(64),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,

        # Single-column indexes
        "CREATE INDEX IF NOT EXISTS ix_pos_applications_organization_id ON pos_applications (organization_id);",
        "CREATE INDEX IF NOT EXISTS ix_pos_applications_workspace_id    ON pos_applications (workspace_id);",
        "CREATE INDEX IF NOT EXISTS ix_pos_applications_contact_id      ON pos_applications (contact_id);",
        "CREATE INDEX IF NOT EXISTS ix_pos_applications_loan_id         ON pos_applications (loan_id);",
        "CREATE INDEX IF NOT EXISTS ix_pos_applications_status          ON pos_applications (status);",

        # Composite indexes
        "CREATE INDEX IF NOT EXISTS ix_pos_app_status_updated ON pos_applications (status, updated_at);",
        "CREATE INDEX IF NOT EXISTS ix_pos_app_org_status     ON pos_applications (organization_id, status);",

        # Partial unique index: one active draft per (contact, loan)
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_pos_app_one_active_per_loan
            ON pos_applications (contact_id, loan_id)
            WHERE status = 'draft';
        """,

        # ----------------------------------------------------------------
        # 2. pos_application_sections
        # ----------------------------------------------------------------
        """
        CREATE TABLE IF NOT EXISTS pos_application_sections (
            id              SERIAL      PRIMARY KEY,
            application_id  UUID        NOT NULL REFERENCES pos_applications(id) ON DELETE CASCADE,
            section_key     VARCHAR(32) NOT NULL,
            data            JSONB       NOT NULL DEFAULT '{}'::jsonb,
            is_complete     BOOLEAN     NOT NULL DEFAULT FALSE,
            completed_at    TIMESTAMPTZ,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,

        # Unique constraint: one row per (application, section)
        """
        DO $$ BEGIN
            ALTER TABLE pos_application_sections
                ADD CONSTRAINT uq_pos_section UNIQUE (application_id, section_key);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,

        # ----------------------------------------------------------------
        # 3. pos_application_pii
        # ----------------------------------------------------------------
        """
        CREATE TABLE IF NOT EXISTS pos_application_pii (
            application_id  UUID        PRIMARY KEY REFERENCES pos_applications(id) ON DELETE CASCADE,
            ssn_encrypted   VARCHAR,
            co_ssn_encrypted VARCHAR,
            dob             DATE,
            co_dob          DATE,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,

        # ----------------------------------------------------------------
        # 4. pos_application_audit
        # ----------------------------------------------------------------
        """
        CREATE TABLE IF NOT EXISTS pos_application_audit (
            id              SERIAL      PRIMARY KEY,
            application_id  UUID        NOT NULL REFERENCES pos_applications(id) ON DELETE CASCADE,
            actor_type      VARCHAR(16) NOT NULL,
            actor_id        INTEGER,
            event_type      VARCHAR(64) NOT NULL,
            section_key     VARCHAR(32),
            delta           JSONB,
            ip_address      INET,
            user_agent      TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,

        "CREATE INDEX IF NOT EXISTS ix_pos_audit_app     ON pos_application_audit (application_id);",
        "CREATE INDEX IF NOT EXISTS ix_pos_audit_event   ON pos_application_audit (event_type);",
        "CREATE INDEX IF NOT EXISTS ix_pos_audit_created ON pos_application_audit (created_at);",

        # ----------------------------------------------------------------
        # 5. pos_ai_qa_messages
        # ----------------------------------------------------------------
        """
        CREATE TABLE IF NOT EXISTS pos_ai_qa_messages (
            id              SERIAL      PRIMARY KEY,
            application_id  UUID        NOT NULL REFERENCES pos_applications(id) ON DELETE CASCADE,
            role            VARCHAR(16) NOT NULL,
            content         TEXT        NOT NULL,
            sources         JSONB,
            follow_ups      JSONB,
            latency_ms      INTEGER,
            tokens_used     INTEGER,
            confidence      VARCHAR(16),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """,

        "CREATE INDEX IF NOT EXISTS ix_ai_qa_app_created ON pos_ai_qa_messages (application_id, created_at);",
    ]

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception as e:
                    logger.warning(f"POS migration command {idx}/{len(sql_commands)} note: {e}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass

        logger.info("POS 1003 tables migration completed successfully")
        return True

    except Exception as e:
        logger.error(f"POS 1003 tables migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting POS 1003 tables migration...")
    success = run_migration()
    if success:
        logger.info("Migration completed!")
    else:
        logger.error("Migration failed!")
        sys.exit(1)
