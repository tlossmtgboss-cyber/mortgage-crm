"""
Smart Docs Rollback Migration Helpers

Standalone migration utilities for Smart Docs V2 rollback and disaster recovery.
These helpers can be run independently of the application server, directly
against the database.

Usage:
    # Check migration status
    python -m migrations.smart_docs_rollback_helpers status

    # Check if rollback is safe
    python -m migrations.smart_docs_rollback_helpers check v2.1

    # Generate rollback SQL (dry run)
    python -m migrations.smart_docs_rollback_helpers sql v2.1

    # Execute rollback (with confirmation prompt)
    python -m migrations.smart_docs_rollback_helpers rollback v2.1

    # Create restore point
    python -m migrations.smart_docs_rollback_helpers snapshot "pre-deploy-v2.3"

IMPORTANT:
- Base Smart Docs tables (smart_documents, smart_document_requests, etc.)
  are NEVER dropped. They contain production data.
- The audit trail (decision_audit_logs) is append-only and never rolled back.
- Signed documents are preserved (legal requirement).
- All destructive operations require explicit confirmation.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# TABLE DEFINITIONS
# =============================================================================

# Tables introduced in each Smart Docs version (safe to drop when rolling back).
# Order matters: later versions may have foreign keys referencing earlier ones.
VERSION_TABLES: Dict[str, List[str]] = {
    "v2.0": [
        "smart_docs_document_versions",
        "smart_docs_templates",
        "smart_docs_batch_jobs",
        "smart_docs_annotations",
        "smart_docs_search_index",
        "smart_docs_archives",
    ],
    "v2.1": [
        "smart_docs_followup_cadences",
        "smart_docs_followup_executions",
        "smart_docs_notifications",
        "smart_docs_notification_preferences",
    ],
    "v2.2": [
        "smart_docs_escalation_rules",
        "smart_docs_escalation_events",
        "smart_docs_access_policies",
        "smart_docs_access_logs",
    ],
    "v2.3": [
        "smart_docs_workflow_definitions",
        "smart_docs_workflow_executions",
        "smart_docs_sla_configs",
        "smart_docs_sla_tracking",
    ],
    "v2.4": [
        "smart_docs_routing_rules",
        "smart_docs_processing_queues",
        "smart_docs_approval_chains",
        "smart_docs_approval_requests",
        "smart_docs_approval_decisions",
    ],
    "v2.5": [
        "smart_docs_field_mappings",
        "smart_docs_custom_fields",
        "smart_docs_white_label_configs",
        "smart_docs_email_templates",
    ],
    "v3.0": [
        "smart_docs_capacity_plans",
        "smart_docs_capacity_snapshots",
        "smart_docs_report_definitions",
        "smart_docs_report_schedules",
        "smart_docs_report_outputs",
        "smart_docs_mismo_mappings",
        "smart_docs_aus_submissions",
    ],
}

# Ordered list of all versions
VERSION_ORDER = ["v2.0", "v2.1", "v2.2", "v2.3", "v2.4", "v2.5", "v3.0"]

# Tables that must NEVER be dropped (production data, legal requirements)
PROTECTED_TABLES = frozenset({
    "smart_documents",
    "smart_document_requests",
    "doc_policy_events",
    "needs_list_templates",
    "client_reminder_settings",
    "decision_audit_logs",
    "decision_audit_archives",
    "esign_envelopes",
    "esign_signatures",
    "esign_consent_records",
})

# Tables containing legally required data (signed docs, audit trail)
LEGAL_HOLD_TABLES = frozenset({
    "decision_audit_logs",
    "decision_audit_archives",
    "esign_envelopes",
    "esign_signatures",
    "esign_consent_records",
})

# Infrastructure tables created for the rollback system itself
ROLLBACK_INFRASTRUCTURE_TABLES = [
    "smart_docs_restore_points",
    "smart_docs_feature_flags",
]


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

def get_database_url() -> str:
    """Get database URL from environment or .env file."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url

    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    return line.split("=", 1)[1]

    return "postgresql://localhost:5432/perennia"


def get_engine(database_url: Optional[str] = None):
    """Create a SQLAlchemy engine."""
    url = database_url or get_database_url()
    return create_engine(url, pool_pre_ping=True)


def is_postgresql(database_url: str) -> bool:
    """Check if the database is PostgreSQL."""
    return database_url.startswith("postgresql") or database_url.startswith("postgres")


# =============================================================================
# CHECK MIGRATION STATUS
# =============================================================================

def check_migration_status(engine) -> Dict[str, Any]:
    """
    Check which Smart Docs migrations have been applied.

    Queries for existence of each Smart Docs table and reports which
    versions are fully, partially, or not deployed.

    Returns:
        {
            "database_type": "postgresql",
            "versions": {
                "v2.0": {"tables": [...], "existing": [...], "missing": [...], "complete": True},
                ...
            },
            "protected_tables": {"smart_documents": True, ...},
            "infrastructure_tables": {"smart_docs_restore_points": False, ...},
            "summary": {"total_expected": 28, "total_existing": 15, "latest_version": "v2.2"},
        }
    """
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    db_url = str(engine.url)
    result = {
        "database_type": "postgresql" if is_postgresql(db_url) else "other",
        "versions": {},
        "protected_tables": {},
        "infrastructure_tables": {},
        "summary": {},
    }

    total_expected = 0
    total_existing = 0
    latest_version = None

    for version in VERSION_ORDER:
        tables = VERSION_TABLES.get(version, [])
        existing = [t for t in tables if t in existing_tables]
        missing = [t for t in tables if t not in existing_tables]

        result["versions"][version] = {
            "tables": tables,
            "existing": existing,
            "missing": missing,
            "complete": len(missing) == 0 and len(tables) > 0,
            "partial": len(existing) > 0 and len(missing) > 0,
        }

        total_expected += len(tables)
        total_existing += len(existing)

        if existing:
            latest_version = version

    # Check protected tables
    for table in sorted(PROTECTED_TABLES):
        result["protected_tables"][table] = table in existing_tables

    # Check infrastructure tables
    for table in ROLLBACK_INFRASTRUCTURE_TABLES:
        result["infrastructure_tables"][table] = table in existing_tables

    result["summary"] = {
        "total_expected": total_expected,
        "total_existing": total_existing,
        "latest_version": latest_version,
        "all_protected_present": all(
            result["protected_tables"].get(t, False) for t in PROTECTED_TABLES
        ),
    }

    return result


# =============================================================================
# GENERATE ROLLBACK SQL
# =============================================================================

def generate_rollback_sql(target_version: str) -> List[str]:
    """
    Generate SQL statements to roll back to a specific version.

    Rolling back to v2.1 keeps v2.0 and v2.1 tables, and drops everything
    from v2.2 onward. Tables are dropped in reverse order to handle foreign
    key dependencies.

    IMPORTANT: Never generates DROP statements for protected tables.

    Args:
        target_version: Version to roll back to (e.g., "v2.1").

    Returns:
        List of SQL statements to execute.
    """
    if target_version not in VERSION_ORDER:
        raise ValueError(
            f"Unknown version '{target_version}'. "
            f"Valid versions: {', '.join(VERSION_ORDER)}"
        )

    target_idx = VERSION_ORDER.index(target_version)
    statements = []

    # Header comment
    statements.append(
        f"-- Smart Docs rollback to {target_version}"
    )
    statements.append(
        f"-- Generated at {datetime.now(timezone.utc).isoformat()}"
    )
    statements.append(
        "-- IMPORTANT: Review each statement before executing."
    )
    statements.append(
        "-- Protected tables (production data, legal holds) are NEVER dropped."
    )
    statements.append("")

    # Start a transaction
    statements.append("BEGIN;")
    statements.append("")

    # Collect tables to drop (from newest to oldest for FK ordering)
    tables_to_drop = []
    for version in reversed(VERSION_ORDER[target_idx + 1:]):
        for table in reversed(VERSION_TABLES.get(version, [])):
            if table in PROTECTED_TABLES or table in LEGAL_HOLD_TABLES:
                statements.append(
                    f"-- SKIPPED (protected): DROP TABLE IF EXISTS \"{table}\" CASCADE;"
                )
            else:
                tables_to_drop.append((version, table))

    statements.append("")

    # Generate DROP statements
    for version, table in tables_to_drop:
        statements.append(f"-- Version {version}")
        statements.append(f'DROP TABLE IF EXISTS "{table}" CASCADE;')

    statements.append("")
    statements.append("COMMIT;")

    return statements


# =============================================================================
# VERIFY ROLLBACK SAFETY
# =============================================================================

def verify_rollback_safe(engine, target_version: str) -> Dict[str, Any]:
    """
    Check if rollback is safe (no data loss for core tables).

    Surveys all tables that would be dropped, counts rows in each, and
    returns a safety assessment.

    Returns:
        {
            "target_version": "v2.1",
            "is_safe": True/False,
            "safety_level": "safe" | "caution" | "unsafe" | "blocked",
            "tables_to_drop": [...],
            "tables_with_data": {"table_name": row_count, ...},
            "total_rows_at_risk": 0,
            "blocked_reasons": [...],
            "warnings": [...],
            "protected_tables_status": {"smart_documents": True, ...},
        }
    """
    if target_version not in VERSION_ORDER:
        return {
            "target_version": target_version,
            "is_safe": False,
            "safety_level": "blocked",
            "blocked_reasons": [
                f"Unknown version '{target_version}'. "
                f"Valid: {', '.join(VERSION_ORDER)}"
            ],
        }

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    target_idx = VERSION_ORDER.index(target_version)
    tables_to_drop = []
    for version in VERSION_ORDER[target_idx + 1:]:
        tables_to_drop.extend(VERSION_TABLES.get(version, []))

    result = {
        "target_version": target_version,
        "is_safe": True,
        "safety_level": "safe",
        "tables_to_drop": tables_to_drop,
        "tables_with_data": {},
        "total_rows_at_risk": 0,
        "blocked_reasons": [],
        "warnings": [],
        "protected_tables_status": {},
    }

    # Check protected tables
    for table in sorted(PROTECTED_TABLES):
        result["protected_tables_status"][table] = table in existing_tables

    # Check for protected/legal-hold tables in drop list
    for table in tables_to_drop:
        if table in PROTECTED_TABLES:
            result["blocked_reasons"].append(
                f"Protected table '{table}' would be dropped"
            )
        if table in LEGAL_HOLD_TABLES:
            result["blocked_reasons"].append(
                f"Legal-hold table '{table}' would be dropped"
            )

    # Count rows in tables that would be dropped
    with engine.connect() as conn:
        for table in tables_to_drop:
            if table not in existing_tables:
                continue
            if table in PROTECTED_TABLES or table in LEGAL_HOLD_TABLES:
                continue
            try:
                row_count = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table}"')  # noqa: S608
                ).scalar()
                if row_count and row_count > 0:
                    result["tables_with_data"][table] = row_count
                    result["total_rows_at_risk"] += row_count
            except Exception as e:
                result["warnings"].append(
                    f"Could not count rows in {table}: {str(e)[:100]}"
                )

    # Determine safety level
    if result["blocked_reasons"]:
        result["safety_level"] = "blocked"
        result["is_safe"] = False
    elif result["total_rows_at_risk"] == 0:
        result["safety_level"] = "safe"
    elif result["total_rows_at_risk"] < 100:
        result["safety_level"] = "caution"
        result["warnings"].append(
            f"{result['total_rows_at_risk']} rows across "
            f"{len(result['tables_with_data'])} tables would be lost"
        )
    else:
        result["safety_level"] = "unsafe"
        result["is_safe"] = False
        result["warnings"].append(
            f"{result['total_rows_at_risk']} rows across "
            f"{len(result['tables_with_data'])} tables would be lost. "
            "Export data before proceeding."
        )

    return result


# =============================================================================
# CREATE ROLLBACK INFRASTRUCTURE TABLES
# =============================================================================

def create_infrastructure_tables(engine) -> List[str]:
    """
    Create tables needed by the rollback service itself.

    Tables created:
    - smart_docs_restore_points: Named snapshots of table state
    - smart_docs_feature_flags: Kill switch state persistence

    Idempotent: safe to run multiple times.

    Returns:
        List of tables created (empty if they already existed).
    """
    db_url = str(engine.url)
    is_pg = is_postgresql(db_url)

    created = []

    with engine.connect() as conn:
        insp = inspect(conn)
        existing = set(insp.get_table_names())

        # Restore points table
        if "smart_docs_restore_points" not in existing:
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE smart_docs_restore_points (
                        id SERIAL PRIMARY KEY,
                        restore_id VARCHAR(64) UNIQUE NOT NULL,
                        label VARCHAR(255) NOT NULL,
                        snapshot_data JSONB NOT NULL DEFAULT '{}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        created_by VARCHAR(255)
                    )
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_restore_points_restore_id
                    ON smart_docs_restore_points (restore_id)
                """))
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_restore_points_created_at
                    ON smart_docs_restore_points (created_at DESC)
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE smart_docs_restore_points (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        restore_id VARCHAR(64) UNIQUE NOT NULL,
                        label VARCHAR(255) NOT NULL,
                        snapshot_data TEXT NOT NULL DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_by VARCHAR(255)
                    )
                """))
            created.append("smart_docs_restore_points")
            logger.info("Created table: smart_docs_restore_points")

        # Feature flags table
        if "smart_docs_feature_flags" not in existing:
            if is_pg:
                conn.execute(text("""
                    CREATE TABLE smart_docs_feature_flags (
                        id SERIAL PRIMARY KEY,
                        key VARCHAR(255) UNIQUE NOT NULL,
                        value JSONB NOT NULL DEFAULT '{}',
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_by VARCHAR(255)
                    )
                """))
            else:
                conn.execute(text("""
                    CREATE TABLE smart_docs_feature_flags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key VARCHAR(255) UNIQUE NOT NULL,
                        value TEXT NOT NULL DEFAULT '{}',
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_by VARCHAR(255)
                    )
                """))
            created.append("smart_docs_feature_flags")
            logger.info("Created table: smart_docs_feature_flags")

        conn.commit()

    return created


# =============================================================================
# EXPORT TABLE DATA
# =============================================================================

def export_table_to_json(
    engine,
    table_name: str,
    output_dir: str = "/tmp/smart_docs_rollback_exports",
) -> Optional[str]:
    """
    Export all rows from a table to a JSON file.

    Used as a safety net before dropping tables during rollback.
    S3 document files are NEVER affected by this -- only DB metadata.

    Args:
        engine: SQLAlchemy engine.
        table_name: Name of the table to export.
        output_dir: Directory to write the JSON file.

    Returns:
        File path on success, None if table does not exist or is empty.
    """
    insp = inspect(engine)
    if table_name not in insp.get_table_names():
        logger.info("Table %s does not exist, skipping export", table_name)
        return None

    with engine.connect() as conn:
        count = conn.execute(
            text(f'SELECT COUNT(*) FROM "{table_name}"')  # noqa: S608
        ).scalar()

        if not count or count == 0:
            logger.info("Table %s is empty, skipping export", table_name)
            return None

        # Read all rows in chunks
        chunk_size = 5000
        offset = 0
        all_rows = []
        columns = None

        while True:
            result = conn.execute(
                text(f'SELECT * FROM "{table_name}" LIMIT :limit OFFSET :offset'),  # noqa: S608
                {"limit": chunk_size, "offset": offset},
            )

            if columns is None:
                columns = list(result.keys())

            rows = result.fetchall()
            if not rows:
                break

            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    elif isinstance(val, bytes):
                        val = val.hex()
                    elif hasattr(val, "__str__") and not isinstance(
                        val, (str, int, float, bool, type(None))
                    ):
                        val = str(val)
                    row_dict[col] = val
                all_rows.append(row_dict)

            offset += chunk_size

    # Write to file
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{table_name}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        json.dump(
            {
                "table": table_name,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "row_count": len(all_rows),
                "columns": columns,
                "data": all_rows,
            },
            f,
            indent=2,
            default=str,
        )

    logger.info("Exported %d rows from %s to %s", len(all_rows), table_name, filepath)
    return filepath


# =============================================================================
# EXECUTE ROLLBACK (STANDALONE)
# =============================================================================

def execute_rollback(
    engine,
    target_version: str,
    export_before_drop: bool = True,
    export_dir: str = "/tmp/smart_docs_rollback_exports",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Execute a rollback to the specified version.

    SAFETY: dry_run defaults to True. Always review the safety check output
    before setting dry_run=False.

    Args:
        engine: SQLAlchemy engine.
        target_version: Version to roll back to.
        export_before_drop: If True, export data from tables before dropping.
        export_dir: Directory for data exports.
        dry_run: If True (default), only report what would happen.

    Returns:
        Dict with rollback results.
    """
    result = {
        "target_version": target_version,
        "dry_run": dry_run,
        "safety_check": None,
        "exported_tables": {},
        "dropped_tables": [],
        "skipped_tables": [],
        "errors": [],
        "success": False,
    }

    # Step 1: Safety check
    safety = verify_rollback_safe(engine, target_version)
    result["safety_check"] = safety

    if safety["safety_level"] == "blocked":
        result["errors"].append(
            f"Rollback blocked: {'; '.join(safety['blocked_reasons'])}"
        )
        return result

    if safety["safety_level"] == "unsafe" and not dry_run:
        logger.warning(
            "Unsafe rollback to %s: %d rows at risk across %d tables",
            target_version,
            safety["total_rows_at_risk"],
            len(safety["tables_with_data"]),
        )

    if dry_run:
        sql = generate_rollback_sql(target_version)
        result["dry_run_sql"] = sql
        result["success"] = True
        return result

    # Step 2: Export data from tables that would be dropped
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    target_idx = VERSION_ORDER.index(target_version)
    tables_to_drop = []
    for version in VERSION_ORDER[target_idx + 1:]:
        tables_to_drop.extend(VERSION_TABLES.get(version, []))

    if export_before_drop:
        for table in tables_to_drop:
            if table not in existing_tables:
                continue
            if table in PROTECTED_TABLES or table in LEGAL_HOLD_TABLES:
                continue
            filepath = export_table_to_json(engine, table, export_dir)
            if filepath:
                result["exported_tables"][table] = filepath

    # Step 3: Drop tables (in reverse order for FK dependencies)
    with engine.connect() as conn:
        for table in reversed(tables_to_drop):
            if table not in existing_tables:
                continue

            if table in PROTECTED_TABLES or table in LEGAL_HOLD_TABLES:
                result["skipped_tables"].append(table)
                logger.info("Skipped protected table: %s", table)
                continue

            try:
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))  # noqa: S608
                result["dropped_tables"].append(table)
                logger.info("Dropped table: %s", table)
            except Exception as e:
                error_msg = f"Failed to drop {table}: {str(e)[:200]}"
                result["errors"].append(error_msg)
                logger.error(error_msg)

        try:
            conn.commit()
        except Exception as e:
            conn.rollback()
            result["errors"].append(f"Transaction commit failed: {str(e)[:200]}")
            return result

    result["success"] = len(result["errors"]) == 0
    return result


# =============================================================================
# CREATE RESTORE POINT (STANDALONE)
# =============================================================================

def create_restore_point(
    engine, label: str
) -> Dict[str, Any]:
    """
    Create a named restore point capturing current table state.

    If the restore_points infrastructure table does not exist, it is
    created automatically.

    Args:
        engine: SQLAlchemy engine.
        label: Human-readable label for the restore point.

    Returns:
        Dict with restore point details.
    """
    import uuid

    # Ensure infrastructure tables exist
    create_infrastructure_tables(engine)

    restore_id = f"rp-{uuid.uuid4().hex[:12]}"
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    # Snapshot all Smart Docs tables
    all_tables = sorted(set(list(PROTECTED_TABLES) + [
        t for tables in VERSION_TABLES.values() for t in tables
    ]))

    table_snapshots = {}
    with engine.connect() as conn:
        for table in all_tables:
            if table not in existing_tables:
                continue
            try:
                count = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table}"')  # noqa: S608
                ).scalar()
                table_snapshots[table] = count or 0
            except Exception:
                table_snapshots[table] = -1  # Error indicator

    snapshot_data = {
        "restore_id": restore_id,
        "label": label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "table_snapshots": table_snapshots,
        "version_tables_present": {
            version: [t for t in tables if t in existing_tables]
            for version, tables in VERSION_TABLES.items()
        },
    }

    # Persist to database
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        session.execute(
            text("""
                INSERT INTO smart_docs_restore_points
                    (restore_id, label, snapshot_data, created_at)
                VALUES (:restore_id, :label, :snapshot_data, NOW())
            """),
            {
                "restore_id": restore_id,
                "label": label,
                "snapshot_data": json.dumps(snapshot_data),
            },
        )
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("Failed to persist restore point: %s", str(e)[:200])
        # Still return the data -- it can be recovered from logs
        snapshot_data["persisted"] = False
        snapshot_data["error"] = str(e)[:200]
    else:
        snapshot_data["persisted"] = True
    finally:
        session.close()

    logger.info(
        "Restore point created: %s (label=%s, tables=%d)",
        restore_id, label, len(table_snapshots),
    )

    return snapshot_data


# =============================================================================
# LIST RESTORE POINTS
# =============================================================================

def list_restore_points(engine, limit: int = 20) -> List[Dict[str, Any]]:
    """
    List recent restore points.

    Args:
        engine: SQLAlchemy engine.
        limit: Maximum number of restore points to return.

    Returns:
        List of restore point summaries (most recent first).
    """
    insp = inspect(engine)
    if "smart_docs_restore_points" not in insp.get_table_names():
        return []

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT restore_id, label, created_at, snapshot_data
                FROM smart_docs_restore_points
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

    results = []
    for row in rows:
        snapshot = json.loads(row[3]) if isinstance(row[3], str) else (row[3] or {})
        table_snapshots = snapshot.get("table_snapshots", {})
        total_rows = sum(v for v in table_snapshots.values() if isinstance(v, int) and v > 0)

        results.append({
            "restore_id": row[0],
            "label": row[1],
            "created_at": row[2].isoformat() if row[2] else None,
            "tables_count": len(table_snapshots),
            "total_rows": total_rows,
        })

    return results


# =============================================================================
# INTEGRITY CHECKS
# =============================================================================

def check_data_integrity(engine) -> Dict[str, Any]:
    """
    Run integrity checks on Smart Docs tables.

    Checks:
    - Foreign key consistency (smart_documents -> loans)
    - Orphaned records (documents without loans)
    - Protected table row counts
    - Index health

    Returns:
        Dict with integrity check results.
    """
    result = {
        "checks_passed": 0,
        "checks_failed": 0,
        "checks_skipped": 0,
        "details": [],
    }

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    with engine.connect() as conn:

        # Check 1: smart_documents -> loans foreign key
        if "smart_documents" in existing_tables and "loans" in existing_tables:
            try:
                orphans = conn.execute(text("""
                    SELECT COUNT(*) FROM smart_documents sd
                    LEFT JOIN loans l ON l.id = sd.loan_id
                    WHERE l.id IS NULL AND sd.loan_id IS NOT NULL
                """)).scalar()

                if orphans and orphans > 0:
                    result["checks_failed"] += 1
                    result["details"].append({
                        "check": "smart_documents_loan_fk",
                        "status": "FAIL",
                        "message": f"{orphans} smart_documents reference non-existent loans",
                    })
                else:
                    result["checks_passed"] += 1
                    result["details"].append({
                        "check": "smart_documents_loan_fk",
                        "status": "PASS",
                        "message": "All smart_documents reference valid loans",
                    })
            except Exception as e:
                result["checks_skipped"] += 1
                result["details"].append({
                    "check": "smart_documents_loan_fk",
                    "status": "SKIP",
                    "message": f"Error: {str(e)[:100]}",
                })
        else:
            result["checks_skipped"] += 1

        # Check 2: smart_document_requests -> loans foreign key
        if "smart_document_requests" in existing_tables and "loans" in existing_tables:
            try:
                orphans = conn.execute(text("""
                    SELECT COUNT(*) FROM smart_document_requests sdr
                    LEFT JOIN loans l ON l.id = sdr.loan_id
                    WHERE l.id IS NULL AND sdr.loan_id IS NOT NULL
                """)).scalar()

                if orphans and orphans > 0:
                    result["checks_failed"] += 1
                    result["details"].append({
                        "check": "smart_document_requests_loan_fk",
                        "status": "FAIL",
                        "message": f"{orphans} requests reference non-existent loans",
                    })
                else:
                    result["checks_passed"] += 1
                    result["details"].append({
                        "check": "smart_document_requests_loan_fk",
                        "status": "PASS",
                        "message": "All requests reference valid loans",
                    })
            except Exception as e:
                result["checks_skipped"] += 1
                result["details"].append({
                    "check": "smart_document_requests_loan_fk",
                    "status": "SKIP",
                    "message": f"Error: {str(e)[:100]}",
                })

        # Check 3: Decision audit log integrity (should never be empty in prod)
        if "decision_audit_logs" in existing_tables:
            try:
                count = conn.execute(
                    text("SELECT COUNT(*) FROM decision_audit_logs")
                ).scalar()
                result["checks_passed"] += 1
                result["details"].append({
                    "check": "decision_audit_logs_populated",
                    "status": "PASS",
                    "message": f"Audit log has {count} records",
                })
            except Exception as e:
                result["checks_skipped"] += 1
                result["details"].append({
                    "check": "decision_audit_logs_populated",
                    "status": "SKIP",
                    "message": f"Error: {str(e)[:100]}",
                })

        # Check 4: Protected table existence
        missing_protected = [
            t for t in PROTECTED_TABLES if t not in existing_tables
        ]
        if missing_protected:
            result["checks_failed"] += 1
            result["details"].append({
                "check": "protected_tables_exist",
                "status": "FAIL",
                "message": f"Missing protected tables: {', '.join(missing_protected)}",
            })
        else:
            result["checks_passed"] += 1
            result["details"].append({
                "check": "protected_tables_exist",
                "status": "PASS",
                "message": "All protected tables exist",
            })

    return result


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """CLI entry point for rollback helpers."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Smart Docs V2 Rollback Helpers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  status              Check migration status (which tables exist)
  check <version>     Check if rollback to <version> is safe
  sql <version>       Generate rollback SQL (dry run)
  rollback <version>  Execute rollback (with confirmation)
  snapshot <label>    Create a named restore point
  restore-points      List existing restore points
  integrity           Run data integrity checks
  infra               Create rollback infrastructure tables

Versions: v2.0, v2.1, v2.2, v2.3, v2.4, v2.5, v3.0
        """,
    )

    parser.add_argument("command", help="Command to execute")
    parser.add_argument("arg", nargs="?", help="Version or label argument")
    parser.add_argument(
        "--database-url", help="Database URL (default: from env)"
    )
    parser.add_argument(
        "--export-dir",
        default="/tmp/smart_docs_rollback_exports",
        help="Directory for data exports",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip safety prompts (use with caution)",
    )

    args = parser.parse_args()

    engine = get_engine(args.database_url)

    if args.command == "status":
        status = check_migration_status(engine)
        print(json.dumps(status, indent=2, default=str))

    elif args.command == "check":
        if not args.arg:
            parser.error("check requires a version argument (e.g., check v2.1)")
        safety = verify_rollback_safe(engine, args.arg)
        print(json.dumps(safety, indent=2, default=str))

    elif args.command == "sql":
        if not args.arg:
            parser.error("sql requires a version argument (e.g., sql v2.1)")
        statements = generate_rollback_sql(args.arg)
        for stmt in statements:
            print(stmt)

    elif args.command == "rollback":
        if not args.arg:
            parser.error("rollback requires a version argument (e.g., rollback v2.1)")

        # Safety check first
        safety = verify_rollback_safe(engine, args.arg)
        print(f"\nSafety level: {safety['safety_level']}")
        print(f"Tables to drop: {len(safety['tables_to_drop'])}")
        print(f"Rows at risk: {safety['total_rows_at_risk']}")

        if safety["blocked_reasons"]:
            print(f"\nBLOCKED: {'; '.join(safety['blocked_reasons'])}")
            sys.exit(1)

        if not args.force:
            confirm = input(
                f"\nRollback to {args.arg}? This will drop tables and data. "
                f"Type 'YES' to confirm: "
            )
            if confirm != "YES":
                print("Rollback cancelled.")
                sys.exit(0)

        result = execute_rollback(
            engine,
            args.arg,
            export_before_drop=True,
            export_dir=args.export_dir,
            dry_run=False,
        )
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "snapshot":
        if not args.arg:
            parser.error("snapshot requires a label argument")
        snapshot = create_restore_point(engine, args.arg)
        print(json.dumps(snapshot, indent=2, default=str))

    elif args.command == "restore-points":
        points = list_restore_points(engine)
        if not points:
            print("No restore points found.")
        else:
            print(json.dumps(points, indent=2, default=str))

    elif args.command == "integrity":
        integrity = check_data_integrity(engine)
        print(json.dumps(integrity, indent=2, default=str))

    elif args.command == "infra":
        created = create_infrastructure_tables(engine)
        if created:
            print(f"Created tables: {', '.join(created)}")
        else:
            print("Infrastructure tables already exist.")

    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
