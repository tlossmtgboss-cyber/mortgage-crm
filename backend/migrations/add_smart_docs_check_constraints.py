"""
Migration: Add CHECK constraints on Smart Docs enum columns.

Enforces valid status/type values at the database level (defense-in-depth).
The ORM @validates decorator catches invalid values at the Python layer;
these constraints catch direct SQL updates or bulk imports.

Tables covered:
  - smart_documents.status
  - smart_document_requests.status
  - document_access_logs.access_type
  - document_retention_policies.action_on_expiry
  - smart_docs_sla_tracking.status

Idempotent — safe to run multiple times.

Run standalone:
    python -m migrations.add_smart_docs_check_constraints

Or import and call:
    from migrations.add_smart_docs_check_constraints import run_migration
    run_migration()
"""

from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constraint definitions
# Each entry: (constraint_name, table_name, column_name, allowed_values)
# ---------------------------------------------------------------------------

_CONSTRAINTS: list[tuple[str, str, str, list[str]]] = [
    (
        "chk_smart_documents_status",
        "smart_documents",
        "status",
        [
            "UPLOADED",
            "PROCESSING",
            "CLASSIFIED",
            "PENDING_REVIEW",
            "APPROVED",
            "REJECTED",
            "SUPERSEDED",
            "DELETED",
            "EXPIRED",
        ],
    ),
    (
        "chk_smart_document_requests_status",
        "smart_document_requests",
        "status",
        [
            "OPEN",
            "UPLOADED",
            "ACCEPTED",
            "REJECTED",
            "WAIVED",
            "EXPIRED",
            "CANCELLED",
        ],
    ),
    (
        "chk_document_access_logs_access_type",
        "document_access_logs",
        "access_type",
        [
            "VIEW",
            "DOWNLOAD",
            "PRINT",
            "PREVIEW",
            "SHARE",
            "EDIT",
            "DELETE",
            "SIGN",
            "VERIFY",
            "EXPORT",
            "EMAIL_FORWARD",
        ],
    ),
    (
        "chk_document_retention_policies_action_on_expiry",
        "document_retention_policies",
        "action_on_expiry",
        [
            "DELETE",
            "ARCHIVE",
            "ANONYMIZE",
            "NOTIFY_ADMIN",
        ],
    ),
    (
        "chk_smart_docs_sla_tracking_status",
        "smart_docs_sla_tracking",
        "status",
        [
            "ACTIVE",
            "MET",
            "BREACHED",
            "PAUSED",
            "CANCELLED",
        ],
    ),
]


def _build_check_sql(constraint_name: str, table_name: str, column_name: str, values: list[str]) -> str:
    """Return a DO $$ ... END $$ block that adds the constraint idempotently."""
    values_sql = ", ".join(f"'{v}'" for v in values)
    return f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}'
    ) THEN
        IF EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name   = '{table_name}'
        ) THEN
            ALTER TABLE {table_name}
                ADD CONSTRAINT {constraint_name}
                CHECK ({column_name} IN ({values_sql}));
            RAISE NOTICE 'Added constraint {constraint_name}';
        ELSE
            RAISE NOTICE 'Table {table_name} does not exist — skipping {constraint_name}';
        END IF;
    ELSE
        RAISE NOTICE 'Constraint {constraint_name} already exists — skipping';
    END IF;
END $$;
""".strip()


def run_migration() -> bool:
    """Add CHECK constraints on Smart Docs enum columns."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return False

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if database_url.startswith("sqlite"):
        logger.info("SQLite does not support ALTER TABLE ADD CONSTRAINT — skipping")
        return True

    engine = create_engine(database_url)

    with engine.connect() as conn:
        for constraint_name, table_name, column_name, values in _CONSTRAINTS:
            sql = _build_check_sql(constraint_name, table_name, column_name, values)
            try:
                conn.execute(text(sql))
                logger.info(
                    "Processed constraint %s on %s.%s (%d values)",
                    constraint_name,
                    table_name,
                    column_name,
                    len(values),
                )
            except Exception as exc:
                logger.error(
                    "Failed to process constraint %s on %s.%s: %s",
                    constraint_name,
                    table_name,
                    column_name,
                    exc,
                )
                conn.rollback()
                return False

        conn.commit()

    logger.info("Migration complete: Smart Docs CHECK constraints applied")
    return True


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
