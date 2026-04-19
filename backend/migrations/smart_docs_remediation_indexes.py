"""
Smart Docs remediation: indexes, constraints, tables.
Run: python -m migrations.smart_docs_remediation_indexes
"""
import logging
from database import SessionLocal
from sqlalchemy import text

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

STATEMENTS = [
    # M5: Compound indexes
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_smart_documents_request_status ON smart_documents (request_id, status)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_smart_documents_borrower_status ON smart_documents (borrower_id, status)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_smart_documents_loan_created ON smart_documents (loan_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_document_requests_loan_status ON document_requests (loan_id, status)",
    # M11: file_hash column + index
    "ALTER TABLE smart_documents ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_smart_documents_file_hash ON smart_documents (file_hash) WHERE file_hash IS NOT NULL",
    # M4: Partial unique index for concurrent upload dedup
    "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_smart_documents_request_hash_active ON smart_documents (request_id, file_hash) WHERE status NOT IN ('deleted', 'rejected') AND file_hash IS NOT NULL",
    # L2: Server-side timestamp defaults
    "ALTER TABLE smart_documents ALTER COLUMN created_at SET DEFAULT NOW(), ALTER COLUMN updated_at SET DEFAULT NOW()",
    "ALTER TABLE document_requests ALTER COLUMN created_at SET DEFAULT NOW(), ALTER COLUMN updated_at SET DEFAULT NOW()",
    # H4: Upload rate limit tracking table
    """CREATE TABLE IF NOT EXISTS upload_rate_events (
        id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        organization_id INTEGER NOT NULL,
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        bytes_uploaded BIGINT NOT NULL DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS ix_upload_rate_user_time ON upload_rate_events (user_id, occurred_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_upload_rate_org_time ON upload_rate_events (organization_id, occurred_at DESC)",
    # H3: E-sign audit log (append-only, hash-chained)
    """CREATE TABLE IF NOT EXISTS esign_audit_log (
        id BIGSERIAL PRIMARY KEY,
        envelope_id VARCHAR(64) NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        actor_id INTEGER,
        actor_email VARCHAR(255),
        actor_ip INET,
        event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
        event_hash VARCHAR(64) NOT NULL,
        prev_hash VARCHAR(64),
        occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        organization_id INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_esign_audit_envelope ON esign_audit_log (envelope_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS ix_esign_audit_org_time ON esign_audit_log (organization_id, occurred_at DESC)",
]


def run():
    db = SessionLocal()
    try:
        for stmt in STATEMENTS:
            try:
                # CONCURRENTLY indexes can't run inside a transaction
                if "CONCURRENTLY" in stmt:
                    db.execute(text("COMMIT"))
                    db.execute(text(stmt))
                else:
                    db.execute(text(stmt))
                    db.commit()
                logger.info("OK: %s", stmt[:80])
            except Exception as e:
                db.rollback()
                logger.warning("SKIP (may already exist): %s — %s", stmt[:80], e)
    finally:
        db.close()
    logger.info("Migration complete")


if __name__ == "__main__":
    run()
