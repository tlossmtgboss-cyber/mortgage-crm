"""
Smart Docs Enterprise Migration (Wave 3)

Creates all new tables for enterprise document management features:
- Plaid VOA/VOI connections
- AUS (Automated Underwriting System) submissions
- eClosing / RON sessions
- IRS Transcript requests
- Business rule configs (extended)
- Document processing cache
- Decision audit logs
- Audit retention configs
- TCPA consent records
- Internal DNC entries

All tables include organization_id with appropriate indexes for
multi-tenant isolation.  Migration is idempotent -- safe to run
multiple times.

Run standalone:
    python -m migrations.smart_docs_enterprise_migration

Or via the registration module:
    from migrations.smart_docs_enterprise_migration import run_migration
    run_migration(engine)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Dict, Optional

from sqlalchemy import create_engine, text

# Ensure parent is on sys.path for standalone execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# ============================================================================
# Table definitions
# ============================================================================

# Each entry is (table_name, CREATE TABLE DDL).  DDL uses PostgreSQL syntax
# (SERIAL, JSONB, TIMESTAMP DEFAULT NOW()).  The caller must supply a
# PostgreSQL-compatible engine.

_TABLE_DDLS: list[tuple[str, str]] = [
    # ------------------------------------------------------------------
    # Plaid VOA / VOI connections
    # ------------------------------------------------------------------
    ("plaid_connections", """
        CREATE TABLE IF NOT EXISTS plaid_connections (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            loan_id         INTEGER,
            borrower_id     INTEGER,
            plaid_item_id   VARCHAR(256),
            plaid_access_token_encrypted TEXT,
            institution_id  VARCHAR(128),
            institution_name VARCHAR(255),
            connection_type VARCHAR(32) NOT NULL DEFAULT 'voa',
            status          VARCHAR(32) NOT NULL DEFAULT 'pending',
            accounts_json   JSONB,
            last_refreshed_at TIMESTAMP,
            error_code      VARCHAR(128),
            error_message   TEXT,
            consent_given_at TIMESTAMP,
            expires_at      TIMESTAMP,
            created_by_user_id INTEGER,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """),

    # ------------------------------------------------------------------
    # AUS submissions (DU / LP / GUS)
    # ------------------------------------------------------------------
    ("aus_submissions", """
        CREATE TABLE IF NOT EXISTS aus_submissions (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            loan_id         INTEGER NOT NULL,
            submission_uuid VARCHAR(36) UNIQUE NOT NULL,
            aus_type        VARCHAR(32) NOT NULL DEFAULT 'du',
            status          VARCHAR(32) NOT NULL DEFAULT 'pending',
            request_payload JSONB,
            response_payload JSONB,
            recommendation  VARCHAR(64),
            risk_class      VARCHAR(64),
            conditions      JSONB,
            findings_count  INTEGER DEFAULT 0,
            submitted_at    TIMESTAMP,
            completed_at    TIMESTAMP,
            error_code      VARCHAR(128),
            error_message   TEXT,
            submitted_by_user_id INTEGER,
            mismo_version   VARCHAR(16),
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """),

    # ------------------------------------------------------------------
    # eClosing / RON sessions
    # ------------------------------------------------------------------
    ("eclosing_sessions", """
        CREATE TABLE IF NOT EXISTS eclosing_sessions (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            loan_id         INTEGER NOT NULL,
            session_uuid    VARCHAR(36) UNIQUE NOT NULL,
            closing_type    VARCHAR(32) NOT NULL DEFAULT 'hybrid',
            status          VARCHAR(32) NOT NULL DEFAULT 'draft',
            notary_id       INTEGER,
            notary_name     VARCHAR(255),
            notary_commission_state VARCHAR(2),
            scheduled_at    TIMESTAMP,
            started_at      TIMESTAMP,
            completed_at    TIMESTAMP,
            cancelled_at    TIMESTAMP,
            cancel_reason   TEXT,
            recording_url   VARCHAR(1024),
            recording_storage_key VARCHAR(1024),
            documents_json  JSONB,
            participants_json JSONB,
            audit_log_json  JSONB,
            kba_passed      BOOLEAN,
            credential_analysis_passed BOOLEAN,
            tamper_sealed   BOOLEAN DEFAULT FALSE,
            platform_provider VARCHAR(64),
            platform_session_id VARCHAR(256),
            created_by_user_id INTEGER,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """),

    # ------------------------------------------------------------------
    # IRS transcript requests (4506-C)
    # ------------------------------------------------------------------
    ("irs_transcript_requests", """
        CREATE TABLE IF NOT EXISTS irs_transcript_requests (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            loan_id         INTEGER NOT NULL,
            borrower_id     INTEGER,
            request_uuid    VARCHAR(36) UNIQUE NOT NULL,
            transcript_type VARCHAR(32) NOT NULL DEFAULT 'tax_return',
            tax_years       JSONB NOT NULL,
            status          VARCHAR(32) NOT NULL DEFAULT 'pending',
            provider        VARCHAR(64) DEFAULT 'irs_direct',
            provider_reference_id VARCHAR(256),
            submitted_at    TIMESTAMP,
            received_at     TIMESTAMP,
            reviewed_at     TIMESTAMP,
            reviewed_by     INTEGER,
            income_match    BOOLEAN,
            income_variance_pct NUMERIC(6, 2),
            findings        JSONB,
            raw_response_key VARCHAR(1024),
            parsed_data     JSONB,
            error_code      VARCHAR(128),
            error_message   TEXT,
            retry_count     INTEGER DEFAULT 0,
            created_by_user_id INTEGER,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """),

    # ------------------------------------------------------------------
    # Business rule configs (enterprise extension)
    # ------------------------------------------------------------------
    ("business_rule_configs", """
        CREATE TABLE IF NOT EXISTS business_rule_configs (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            rule_category   VARCHAR(50) NOT NULL,
            rule_key        VARCHAR(100) NOT NULL,
            rule_value      TEXT NOT NULL,
            value_type      VARCHAR(20) NOT NULL DEFAULT 'integer',
            description     TEXT,
            effective_date  DATE NOT NULL,
            expiration_date DATE,
            source          VARCHAR(100),
            is_active       BOOLEAN DEFAULT TRUE,
            created_by      INTEGER,
            updated_by      INTEGER,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW(),
            UNIQUE(organization_id, rule_key, effective_date)
        )
    """),

    # ------------------------------------------------------------------
    # Document processing cache (dedup / speed)
    # ------------------------------------------------------------------
    ("document_processing_cache", """
        CREATE TABLE IF NOT EXISTS document_processing_cache (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            document_hash   VARCHAR(128) NOT NULL,
            processing_type VARCHAR(64) NOT NULL,
            result_json     JSONB,
            model_version   VARCHAR(64),
            hit_count       INTEGER DEFAULT 1,
            first_seen_at   TIMESTAMP DEFAULT NOW(),
            last_hit_at     TIMESTAMP DEFAULT NOW(),
            expires_at      TIMESTAMP,
            UNIQUE(organization_id, document_hash, processing_type)
        )
    """),

    # ------------------------------------------------------------------
    # Decision audit logs (SOC 2 / compliance)
    # ------------------------------------------------------------------
    ("decision_audit_logs", """
        CREATE TABLE IF NOT EXISTS decision_audit_logs (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            loan_id         INTEGER,
            document_id     INTEGER,
            decision_type   VARCHAR(64) NOT NULL,
            decision_result VARCHAR(64) NOT NULL,
            decision_reason TEXT,
            input_summary   JSONB,
            output_summary  JSONB,
            model_used      VARCHAR(128),
            confidence      NUMERIC(5, 4),
            overridden      BOOLEAN DEFAULT FALSE,
            overridden_by   INTEGER,
            override_reason TEXT,
            overridden_at   TIMESTAMP,
            ip_address      VARCHAR(45),
            user_id         INTEGER,
            trace_id        VARCHAR(64),
            created_at      TIMESTAMP DEFAULT NOW()
        )
    """),

    # ------------------------------------------------------------------
    # Audit retention configs
    # ------------------------------------------------------------------
    ("audit_retention_configs", """
        CREATE TABLE IF NOT EXISTS audit_retention_configs (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            record_type     VARCHAR(64) NOT NULL,
            retention_days  INTEGER NOT NULL DEFAULT 2555,
            archive_after_days INTEGER,
            delete_after_days INTEGER,
            regulatory_basis TEXT,
            is_active       BOOLEAN DEFAULT TRUE,
            created_by      INTEGER,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW(),
            UNIQUE(organization_id, record_type)
        )
    """),

    # ------------------------------------------------------------------
    # TCPA consent records
    # ------------------------------------------------------------------
    ("smart_docs_consent_records", """
        CREATE TABLE IF NOT EXISTS smart_docs_consent_records (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            borrower_id     INTEGER,
            borrower_email  VARCHAR(255),
            borrower_phone  VARCHAR(32),
            consent_type    VARCHAR(64) NOT NULL,
            consent_given   BOOLEAN NOT NULL DEFAULT FALSE,
            consent_text    TEXT,
            consent_method  VARCHAR(32) NOT NULL DEFAULT 'electronic',
            ip_address      VARCHAR(45),
            user_agent      TEXT,
            given_at        TIMESTAMP,
            revoked_at      TIMESTAMP,
            revoked_reason  TEXT,
            document_id     INTEGER,
            loan_id         INTEGER,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """),

    # ------------------------------------------------------------------
    # Internal DNC entries
    # ------------------------------------------------------------------
    ("internal_dnc_entries", """
        CREATE TABLE IF NOT EXISTS internal_dnc_entries (
            id              SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            phone           VARCHAR(32),
            email           VARCHAR(255),
            source          VARCHAR(64) NOT NULL DEFAULT 'manual',
            reason          TEXT,
            added_by_user_id INTEGER,
            removed_at      TIMESTAMP,
            removed_by_user_id INTEGER,
            removal_reason  TEXT,
            is_active       BOOLEAN DEFAULT TRUE,
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """),
]

# ============================================================================
# Indexes
# ============================================================================

_INDEXES: list[str] = [
    # -- plaid_connections --
    "CREATE INDEX IF NOT EXISTS ix_plaid_conn_org ON plaid_connections(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_plaid_conn_loan ON plaid_connections(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_plaid_conn_borrower ON plaid_connections(borrower_id)",
    "CREATE INDEX IF NOT EXISTS ix_plaid_conn_status ON plaid_connections(status)",
    "CREATE INDEX IF NOT EXISTS ix_plaid_conn_item ON plaid_connections(plaid_item_id)",

    # -- aus_submissions --
    "CREATE INDEX IF NOT EXISTS ix_aus_sub_org ON aus_submissions(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_aus_sub_loan ON aus_submissions(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_aus_sub_uuid ON aus_submissions(submission_uuid)",
    "CREATE INDEX IF NOT EXISTS ix_aus_sub_status ON aus_submissions(status)",
    "CREATE INDEX IF NOT EXISTS ix_aus_sub_type ON aus_submissions(aus_type)",

    # -- eclosing_sessions --
    "CREATE INDEX IF NOT EXISTS ix_eclosing_org ON eclosing_sessions(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_eclosing_loan ON eclosing_sessions(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_eclosing_uuid ON eclosing_sessions(session_uuid)",
    "CREATE INDEX IF NOT EXISTS ix_eclosing_status ON eclosing_sessions(status)",
    "CREATE INDEX IF NOT EXISTS ix_eclosing_scheduled ON eclosing_sessions(scheduled_at)",

    # -- irs_transcript_requests --
    "CREATE INDEX IF NOT EXISTS ix_irs_tr_org ON irs_transcript_requests(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_irs_tr_loan ON irs_transcript_requests(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_irs_tr_borrower ON irs_transcript_requests(borrower_id)",
    "CREATE INDEX IF NOT EXISTS ix_irs_tr_uuid ON irs_transcript_requests(request_uuid)",
    "CREATE INDEX IF NOT EXISTS ix_irs_tr_status ON irs_transcript_requests(status)",

    # -- business_rule_configs --
    "CREATE INDEX IF NOT EXISTS ix_brc_org ON business_rule_configs(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_brc_category ON business_rule_configs(rule_category)",
    "CREATE INDEX IF NOT EXISTS ix_brc_key ON business_rule_configs(rule_key)",
    "CREATE INDEX IF NOT EXISTS ix_brc_active ON business_rule_configs(is_active)",

    # -- document_processing_cache --
    "CREATE INDEX IF NOT EXISTS ix_dpc_org ON document_processing_cache(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_dpc_hash ON document_processing_cache(document_hash)",
    "CREATE INDEX IF NOT EXISTS ix_dpc_expires ON document_processing_cache(expires_at)",

    # -- decision_audit_logs --
    "CREATE INDEX IF NOT EXISTS ix_dal_org ON decision_audit_logs(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_dal_loan ON decision_audit_logs(loan_id)",
    "CREATE INDEX IF NOT EXISTS ix_dal_doc ON decision_audit_logs(document_id)",
    "CREATE INDEX IF NOT EXISTS ix_dal_type ON decision_audit_logs(decision_type)",
    "CREATE INDEX IF NOT EXISTS ix_dal_trace ON decision_audit_logs(trace_id)",
    "CREATE INDEX IF NOT EXISTS ix_dal_created ON decision_audit_logs(created_at)",

    # -- audit_retention_configs --
    "CREATE INDEX IF NOT EXISTS ix_arc_org ON audit_retention_configs(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_arc_type ON audit_retention_configs(record_type)",

    # -- smart_docs_consent_records --
    "CREATE INDEX IF NOT EXISTS ix_consent_org ON smart_docs_consent_records(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_consent_borrower ON smart_docs_consent_records(borrower_id)",
    "CREATE INDEX IF NOT EXISTS ix_consent_email ON smart_docs_consent_records(borrower_email)",
    "CREATE INDEX IF NOT EXISTS ix_consent_phone ON smart_docs_consent_records(borrower_phone)",
    "CREATE INDEX IF NOT EXISTS ix_consent_type ON smart_docs_consent_records(consent_type)",
    "CREATE INDEX IF NOT EXISTS ix_consent_loan ON smart_docs_consent_records(loan_id)",

    # -- internal_dnc_entries --
    "CREATE INDEX IF NOT EXISTS ix_dnc_org ON internal_dnc_entries(organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_dnc_phone ON internal_dnc_entries(phone)",
    "CREATE INDEX IF NOT EXISTS ix_dnc_email ON internal_dnc_entries(email)",
    "CREATE INDEX IF NOT EXISTS ix_dnc_active ON internal_dnc_entries(is_active)",
]


# ============================================================================
# Public API
# ============================================================================

def run_migration(engine=None) -> Optional[Dict]:
    """
    Create all enterprise tables and indexes.

    Args:
        engine: SQLAlchemy engine.  If ``None`` a new engine is created
                from the ``DATABASE_URL`` environment variable.

    Returns:
        Dict with ``success`` flag and list of table names, or ``None``
        on early exit.
    """
    if engine is None:
        database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(database_url)

    tables_created: list[str] = []

    with engine.connect() as conn:
        logger.info("Starting Smart Docs Enterprise migration...")
        print("[SMART_DOCS_ENTERPRISE] Starting enterprise migration...")

        # ---- Tables ----
        for table_name, ddl in _TABLE_DDLS:
            try:
                print(f"[SMART_DOCS_ENTERPRISE] Ensuring table: {table_name}")
                conn.execute(text(ddl))
                tables_created.append(table_name)
            except Exception as e:
                logger.warning(
                    f"[SMART_DOCS_ENTERPRISE] Table {table_name} skipped: {e}"
                )

        # ---- Indexes ----
        print("[SMART_DOCS_ENTERPRISE] Creating indexes...")
        for idx_sql in _INDEXES:
            try:
                conn.execute(text(idx_sql))
            except Exception as e:
                logger.warning(f"[SMART_DOCS_ENTERPRISE] Index skipped: {e}")

        conn.commit()

        print(
            f"[SMART_DOCS_ENTERPRISE] Migration complete: "
            f"{len(tables_created)} tables ensured."
        )
        logger.info(
            f"Smart Docs Enterprise migration complete: "
            f"{len(tables_created)} tables ensured."
        )

    return {
        "success": True,
        "message": "Smart Docs Enterprise tables created successfully",
        "tables_created": tables_created,
    }


# ============================================================================
# Standalone execution
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migration()
    if result and result.get("success"):
        print("Smart Docs Enterprise migration complete!")
    else:
        print("Migration encountered issues -- check logs.")
        sys.exit(1)
