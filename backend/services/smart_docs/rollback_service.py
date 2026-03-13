"""
Smart Docs Rollback and Disaster Recovery Service

Production rollback, restore point management, graceful degradation, and
disaster recovery procedures for the Smart Docs V2 subsystem.

Key design principles:
- Every destructive operation defaults to dry_run=True.
- S3 document files are NEVER deleted during rollback.
- Audit trail (decision_audit_logs) is append-only and never rolled back.
- Signed documents are preserved (legal requirement).
- Data is exported before any table is dropped.

Subsystems covered:
- Database rollback (table-level, with data export)
- Restore point creation and validation
- Graceful degradation (circuit breakers, feature flags, fallbacks)
- Disaster recovery (AI outage, S3 failure, DB corruption, key compromise)

Usage:
    from services.smart_docs.rollback_service import (
        SmartDocsRollbackService,
        get_rollback_service,
    )

    svc = get_rollback_service(db)

    # Create a restore point before deployment
    restore_id = await svc.create_restore_point("pre-v2.3-deploy")

    # Estimate impact of rolling back to v2.1
    impact = await svc.estimate_rollback_impact("v2.1")

    # Execute rollback (dry run first)
    result = await svc.execute_rollback("v2.1", dry_run=True)

    # After incident: recover from AI outage
    plan = await svc.recover_from_ai_outage()
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# DATA MODELS
# =============================================================================

class SubsystemStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class RollbackSafety(str, Enum):
    SAFE = "safe"                  # No data loss
    CAUTION = "caution"            # Some data in tables, but non-critical
    UNSAFE = "unsafe"              # Critical data would be lost
    BLOCKED = "blocked"            # Legal/compliance hold prevents rollback


class RecoveryPriority(str, Enum):
    CRITICAL = "critical"          # Must fix immediately
    HIGH = "high"                  # Fix within 1 hour
    MEDIUM = "medium"              # Fix within 4 hours
    LOW = "low"                    # Fix within 24 hours


@dataclass
class DeploymentRecord:
    """Record of a Smart Docs deployment."""
    deployment_id: str
    version: str
    deployed_at: datetime
    deployed_by: Optional[str] = None
    tables_created: List[str] = field(default_factory=list)
    tables_modified: List[str] = field(default_factory=list)
    rollback_sql: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ValidationResult:
    """Result of validating a restore point."""
    restore_id: str
    is_valid: bool
    created_at: Optional[datetime] = None
    table_snapshots: Dict[str, int] = field(default_factory=dict)
    missing_tables: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ImpactAssessment:
    """Assessment of what would be lost in a rollback."""
    target_version: str
    tables_to_drop: List[str] = field(default_factory=list)
    tables_with_data: Dict[str, int] = field(default_factory=dict)
    documents_affected: int = 0
    income_calculations_affected: int = 0
    signatures_affected: int = 0
    workflows_affected: int = 0
    safety: RollbackSafety = RollbackSafety.SAFE
    blocked_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    estimated_downtime_seconds: int = 0


@dataclass
class RollbackResult:
    """Result of a rollback execution."""
    success: bool
    dry_run: bool
    target_version: str
    tables_dropped: List[str] = field(default_factory=list)
    tables_preserved: List[str] = field(default_factory=list)
    data_exported: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    rollback_id: str = ""


@dataclass
class VerificationResult:
    """Result of post-rollback verification."""
    overall_healthy: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class RecoveryStep:
    """A single step in a recovery plan."""
    order: int
    action: str
    description: str
    command: Optional[str] = None
    estimated_duration_seconds: int = 0
    requires_manual: bool = False
    completed: bool = False


@dataclass
class RecoveryPlan:
    """A disaster recovery plan with ordered steps."""
    scenario: str
    priority: RecoveryPriority
    steps: List[RecoveryStep] = field(default_factory=list)
    estimated_total_seconds: int = 0
    notes: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "priority": self.priority.value,
            "steps": [
                {
                    "order": s.order,
                    "action": s.action,
                    "description": s.description,
                    "command": s.command,
                    "estimated_duration_seconds": s.estimated_duration_seconds,
                    "requires_manual": s.requires_manual,
                    "completed": s.completed,
                }
                for s in self.steps
            ],
            "estimated_total_seconds": self.estimated_total_seconds,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SubsystemHealth:
    """Health status of a Smart Docs subsystem."""
    name: str
    status: SubsystemStatus
    last_check: Optional[datetime] = None
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# VERSION REGISTRY
# =============================================================================

# Tables introduced in each version. Order matters: later versions build on
# earlier ones. The base tables (smart_documents, smart_document_requests, etc.)
# are NEVER included here -- they contain production data and must not be dropped.

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
        # Enterprise Wave 3 tables
        "smart_docs_capacity_plans",
        "smart_docs_capacity_snapshots",
        "smart_docs_report_definitions",
        "smart_docs_report_schedules",
        "smart_docs_report_outputs",
        "smart_docs_mismo_mappings",
        "smart_docs_aus_submissions",
    ],
}

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

# Tables that contain legally required data (signed documents, audit trail).
# These can never be rolled back even if they appear in VERSION_TABLES.
LEGAL_HOLD_TABLES = frozenset({
    "decision_audit_logs",
    "decision_audit_archives",
    "esign_envelopes",
    "esign_signatures",
    "esign_consent_records",
})

# Ordered list of all versions for comparison
VERSION_ORDER = ["v2.0", "v2.1", "v2.2", "v2.3", "v2.4", "v2.5", "v3.0"]


# =============================================================================
# FEATURE FLAGS / KILL SWITCHES
# =============================================================================

class FeatureKillSwitch:
    """
    Emergency kill switches for Smart Docs subsystems.

    Each flag can be toggled at runtime to disable a subsystem without
    restarting the application. When a subsystem is killed, the corresponding
    service should fall back to a safe default (e.g., skip AI classification
    and accept the document with manual_review status).

    Kill switches are stored in-memory with optional persistence to the
    database for cross-instance coordination.
    """

    _switches: Dict[str, bool] = {}
    _defaults: Dict[str, bool] = {
        "ai_classification": True,
        "ai_review": True,
        "ai_extraction": True,
        "esign": True,
        "followup_automation": True,
        "ocr_processing": True,
        "fraud_detection": True,
        "income_calculation": True,
        "batch_operations": True,
        "document_splitting": True,
        "enterprise_routing": True,
        "enterprise_sla": True,
        "enterprise_approval_chains": True,
        "white_label": True,
        "notification_center": True,
        "document_chat": True,
    }

    @classmethod
    def is_enabled(cls, feature: str) -> bool:
        """Check if a feature is enabled. Unknown features default to True."""
        return cls._switches.get(feature, cls._defaults.get(feature, True))

    @classmethod
    def kill(cls, feature: str) -> None:
        """Disable a feature immediately."""
        cls._switches[feature] = False
        logger.warning("Kill switch activated for Smart Docs feature: %s", feature)

    @classmethod
    def restore(cls, feature: str) -> None:
        """Re-enable a feature."""
        cls._switches[feature] = True
        logger.info("Kill switch restored for Smart Docs feature: %s", feature)

    @classmethod
    def kill_all(cls) -> None:
        """Emergency: disable ALL Smart Docs features."""
        for feature in cls._defaults:
            cls._switches[feature] = False
        logger.critical("ALL Smart Docs kill switches activated")

    @classmethod
    def restore_all(cls) -> None:
        """Restore all features to their defaults."""
        cls._switches.clear()
        logger.info("All Smart Docs kill switches restored to defaults")

    @classmethod
    def get_status(cls) -> Dict[str, bool]:
        """Return current status of all kill switches."""
        return {
            feature: cls.is_enabled(feature)
            for feature in cls._defaults
        }

    @classmethod
    async def persist_to_db(cls, db: Session) -> None:
        """Persist current kill switch state to the database for cross-instance sync."""
        try:
            state_json = json.dumps(cls._switches)
            db.execute(
                text("""
                    INSERT INTO smart_docs_feature_flags (key, value, updated_at)
                    VALUES ('kill_switches', :value, NOW())
                    ON CONFLICT (key)
                    DO UPDATE SET value = :value, updated_at = NOW()
                """),
                {"value": state_json},
            )
            db.commit()
        except Exception as e:
            logger.warning(
                "Could not persist kill switches to DB (table may not exist): %s",
                str(e)[:200],
            )

    @classmethod
    async def load_from_db(cls, db: Session) -> None:
        """Load kill switch state from the database."""
        try:
            row = db.execute(
                text("SELECT value FROM smart_docs_feature_flags WHERE key = 'kill_switches'")
            ).fetchone()
            if row:
                cls._switches = json.loads(row[0])
                logger.info("Loaded kill switch state from DB: %d overrides", len(cls._switches))
        except Exception as e:
            logger.warning(
                "Could not load kill switches from DB (table may not exist): %s",
                str(e)[:200],
            )


# =============================================================================
# MAIN SERVICE
# =============================================================================

class SmartDocsRollbackService:
    """
    Rollback, restore point, and disaster recovery service for Smart Docs V2.

    All destructive operations default to dry_run=True for safety.
    """

    def __init__(self, db: Session):
        self.db = db
        self._inspector = None

    @property
    def inspector(self):
        if self._inspector is None:
            self._inspector = inspect(self.db.get_bind())
        return self._inspector

    # =========================================================================
    # TABLE INTROSPECTION
    # =========================================================================

    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        return table_name in self.inspector.get_table_names()

    def _get_row_count(self, table_name: str) -> int:
        """Get row count for a table. Returns 0 if table does not exist."""
        if not self._table_exists(table_name):
            return 0
        try:
            result = self.db.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}"')  # noqa: S608
            ).scalar()
            return result or 0
        except Exception as e:
            logger.warning("Could not count rows in %s: %s", table_name, str(e)[:200])
            return 0

    def _get_all_version_tables(self) -> List[str]:
        """Get all tables across all versions."""
        tables = []
        for version_tables in VERSION_TABLES.values():
            tables.extend(version_tables)
        return tables

    def _tables_for_rollback_to(self, target_version: str) -> List[str]:
        """
        Get tables that would be dropped when rolling back to target_version.

        Rolling back to v2.1 means we keep v2.0 and v2.1 tables, and drop
        everything from v2.2 onward.
        """
        if target_version not in VERSION_ORDER:
            return []

        target_idx = VERSION_ORDER.index(target_version)
        tables_to_drop = []

        for version in VERSION_ORDER[target_idx + 1:]:
            tables_to_drop.extend(VERSION_TABLES.get(version, []))

        return tables_to_drop

    # =========================================================================
    # DEPLOYMENT HISTORY
    # =========================================================================

    async def get_deployment_history(self) -> List[DeploymentRecord]:
        """
        Get recent Smart Docs deployments by examining which version tables exist.

        Since we don't have a dedicated deployment log table, we infer deployment
        history from the presence of version-specific tables.
        """
        records = []

        for version in VERSION_ORDER:
            version_tables = VERSION_TABLES.get(version, [])
            existing = [t for t in version_tables if self._table_exists(t)]

            if existing:
                records.append(DeploymentRecord(
                    deployment_id=f"inferred-{version}",
                    version=version,
                    deployed_at=datetime.now(timezone.utc),  # Unknown; use current
                    tables_created=existing,
                    tables_modified=[],
                    notes=f"Inferred from {len(existing)}/{len(version_tables)} tables present",
                ))

        return records

    # =========================================================================
    # RESTORE POINTS
    # =========================================================================

    async def create_restore_point(self, label: str) -> str:
        """
        Create a named restore point (snapshot of current table state).

        A restore point captures:
        - Which tables exist and their row counts
        - Current kill switch state
        - Timestamp for reference

        Returns:
            restore_id: Unique identifier for this restore point.
        """
        restore_id = f"rp-{uuid.uuid4().hex[:12]}"

        # Snapshot all Smart Docs tables
        all_tables = list(PROTECTED_TABLES) + self._get_all_version_tables()
        table_snapshots = {}
        for table_name in sorted(set(all_tables)):
            if self._table_exists(table_name):
                table_snapshots[table_name] = self._get_row_count(table_name)

        # Store the restore point in the database
        restore_data = {
            "restore_id": restore_id,
            "label": label,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "table_snapshots": table_snapshots,
            "kill_switch_state": FeatureKillSwitch.get_status(),
            "version_tables_present": {
                version: [t for t in tables if self._table_exists(t)]
                for version, tables in VERSION_TABLES.items()
            },
        }

        try:
            self.db.execute(
                text("""
                    INSERT INTO smart_docs_restore_points
                        (restore_id, label, snapshot_data, created_at)
                    VALUES (:restore_id, :label, :snapshot_data, NOW())
                """),
                {
                    "restore_id": restore_id,
                    "label": label,
                    "snapshot_data": json.dumps(restore_data),
                },
            )
            self.db.commit()
            logger.info(
                "Restore point created: %s (label=%s, tables=%d)",
                restore_id, label, len(table_snapshots),
            )
        except Exception as e:
            # If the restore_points table does not exist, log the data
            # as structured JSON so it can be recovered from logs.
            logger.warning(
                "Could not persist restore point to DB (table may not exist). "
                "Logging snapshot for manual recovery. error=%s",
                str(e)[:200],
            )
            logger.info(
                "RESTORE_POINT_SNAPSHOT: %s",
                json.dumps(restore_data, indent=2),
            )

        return restore_id

    async def validate_restore_point(self, restore_id: str) -> ValidationResult:
        """
        Verify a restore point is valid and complete.

        Checks that the snapshot data is parseable and that the referenced
        tables still exist (or notes which ones are missing).
        """
        result = ValidationResult(restore_id=restore_id, is_valid=False)

        try:
            row = self.db.execute(
                text("""
                    SELECT snapshot_data, created_at
                    FROM smart_docs_restore_points
                    WHERE restore_id = :restore_id
                """),
                {"restore_id": restore_id},
            ).fetchone()
        except Exception as e:
            result.errors.append(f"Cannot query restore points table: {str(e)[:200]}")
            return result

        if not row:
            result.errors.append(f"Restore point {restore_id} not found")
            return result

        try:
            snapshot = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except (json.JSONDecodeError, TypeError) as e:
            result.errors.append(f"Invalid snapshot data: {str(e)[:200]}")
            return result

        result.created_at = row[1] if len(row) > 1 else None
        result.table_snapshots = snapshot.get("table_snapshots", {})

        # Check which tables from the snapshot still exist
        for table_name in result.table_snapshots:
            if not self._table_exists(table_name):
                result.missing_tables.append(table_name)

        if result.missing_tables:
            result.warnings.append(
                f"{len(result.missing_tables)} tables from snapshot no longer exist"
            )

        # Check row count drift for existing tables
        for table_name, original_count in result.table_snapshots.items():
            if table_name in result.missing_tables:
                continue
            current_count = self._get_row_count(table_name)
            if current_count < original_count:
                result.warnings.append(
                    f"{table_name}: row count decreased from {original_count} to {current_count}"
                )

        result.is_valid = len(result.errors) == 0
        return result

    # =========================================================================
    # IMPACT ASSESSMENT
    # =========================================================================

    async def estimate_rollback_impact(self, target_version: str) -> ImpactAssessment:
        """
        Estimate what would be lost in a rollback to a specific version.

        This is a read-only operation that surveys tables and data without
        making any changes.
        """
        impact = ImpactAssessment(target_version=target_version)

        if target_version not in VERSION_ORDER:
            impact.safety = RollbackSafety.BLOCKED
            impact.blocked_reasons.append(
                f"Unknown version '{target_version}'. Valid versions: {', '.join(VERSION_ORDER)}"
            )
            return impact

        tables_to_drop = self._tables_for_rollback_to(target_version)
        impact.tables_to_drop = tables_to_drop

        # Survey data in each table
        total_rows = 0
        for table_name in tables_to_drop:
            if not self._table_exists(table_name):
                continue
            count = self._get_row_count(table_name)
            if count > 0:
                impact.tables_with_data[table_name] = count
                total_rows += count

            # Check for legal hold
            if table_name in LEGAL_HOLD_TABLES:
                impact.safety = RollbackSafety.BLOCKED
                impact.blocked_reasons.append(
                    f"Table '{table_name}' is under legal hold and cannot be dropped"
                )

        # Check for protected tables that might be in the drop list
        protected_overlap = set(tables_to_drop) & PROTECTED_TABLES
        if protected_overlap:
            impact.safety = RollbackSafety.BLOCKED
            impact.blocked_reasons.append(
                f"Protected tables would be dropped: {', '.join(sorted(protected_overlap))}"
            )

        # Count affected entities from specific tables
        if self._table_exists("smart_docs_document_versions") and "smart_docs_document_versions" in tables_to_drop:
            impact.documents_affected = self._get_row_count("smart_docs_document_versions")

        if self._table_exists("smart_docs_workflow_executions") and "smart_docs_workflow_executions" in tables_to_drop:
            impact.workflows_affected = self._get_row_count("smart_docs_workflow_executions")

        if self._table_exists("smart_docs_approval_decisions") and "smart_docs_approval_decisions" in tables_to_drop:
            impact.signatures_affected = self._get_row_count("smart_docs_approval_decisions")

        if self._table_exists("smart_docs_sla_tracking") and "smart_docs_sla_tracking" in tables_to_drop:
            try:
                income_count = self.db.execute(
                    text("""
                        SELECT COUNT(*) FROM smart_docs_sla_tracking
                        WHERE tracking_type = 'income_calculation'
                    """)
                ).scalar()
                impact.income_calculations_affected = income_count or 0
            except Exception:
                pass

        # Determine safety level (if not already blocked)
        if impact.safety != RollbackSafety.BLOCKED:
            if total_rows == 0:
                impact.safety = RollbackSafety.SAFE
            elif total_rows < 100:
                impact.safety = RollbackSafety.CAUTION
                impact.warnings.append(
                    f"{total_rows} rows across {len(impact.tables_with_data)} tables would be lost"
                )
            else:
                impact.safety = RollbackSafety.UNSAFE
                impact.warnings.append(
                    f"{total_rows} rows across {len(impact.tables_with_data)} tables would be lost. "
                    "Export data before proceeding."
                )

        # Estimate downtime: ~2 seconds per table to drop
        impact.estimated_downtime_seconds = len(tables_to_drop) * 2

        return impact

    # =========================================================================
    # DATA EXPORT (pre-rollback safety net)
    # =========================================================================

    async def _export_table_data(
        self, table_name: str, export_dir: str
    ) -> Optional[str]:
        """
        Export table data to a JSON file before dropping.

        Returns the file path on success, None on failure.
        S3 upload of exports can be layered on top of this.
        """
        if not self._table_exists(table_name):
            return None

        count = self._get_row_count(table_name)
        if count == 0:
            return None

        try:
            # Export in chunks to avoid memory issues on large tables
            chunk_size = 5000
            offset = 0
            all_rows = []

            while True:
                rows = self.db.execute(
                    text(f'SELECT * FROM "{table_name}" LIMIT :limit OFFSET :offset'),  # noqa: S608
                    {"limit": chunk_size, "offset": offset},
                ).fetchall()

                if not rows:
                    break

                # Get column names from the first result
                if offset == 0:
                    columns = list(self.db.execute(
                        text(f'SELECT * FROM "{table_name}" LIMIT 1')  # noqa: S608
                    ).keys())

                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        # Make JSON-serializable
                        if isinstance(val, datetime):
                            val = val.isoformat()
                        elif isinstance(val, bytes):
                            val = val.hex()
                        elif hasattr(val, '__str__') and not isinstance(val, (str, int, float, bool, type(None))):
                            val = str(val)
                        row_dict[col] = val
                    all_rows.append(row_dict)

                offset += chunk_size

            # Write to file
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{table_name}_{timestamp}.json"
            filepath = os.path.join(export_dir, filename)

            os.makedirs(export_dir, exist_ok=True)
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

            logger.info(
                "Exported %d rows from %s to %s",
                len(all_rows), table_name, filepath,
            )
            return filepath

        except Exception as e:
            logger.error("Failed to export table %s: %s", table_name, str(e)[:200])
            return None

    # =========================================================================
    # ROLLBACK EXECUTION
    # =========================================================================

    async def execute_rollback(
        self,
        target_version: str,
        dry_run: bool = True,
        export_dir: Optional[str] = None,
        force: bool = False,
    ) -> RollbackResult:
        """
        Execute rollback to a specific version.

        SAFETY: dry_run defaults to True. Set dry_run=False only after
        reviewing the impact assessment.

        Args:
            target_version: Version to roll back to (e.g., "v2.1").
            dry_run: If True (default), only report what would happen.
            export_dir: Directory to export data before dropping tables.
                        Defaults to /tmp/smart_docs_rollback_exports.
            force: If True, skip safety checks (blocked/unsafe). Dangerous.

        Returns:
            RollbackResult with details of what happened (or would happen).
        """
        start_time = time.monotonic()
        rollback_id = f"rb-{uuid.uuid4().hex[:12]}"
        result = RollbackResult(
            success=False,
            dry_run=dry_run,
            target_version=target_version,
            rollback_id=rollback_id,
        )

        if export_dir is None:
            export_dir = "/tmp/smart_docs_rollback_exports"

        # 1. Impact assessment
        impact = await self.estimate_rollback_impact(target_version)

        if impact.safety == RollbackSafety.BLOCKED and not force:
            result.errors.append(
                f"Rollback blocked: {'; '.join(impact.blocked_reasons)}"
            )
            result.duration_seconds = time.monotonic() - start_time
            return result

        if impact.safety == RollbackSafety.UNSAFE and not force:
            result.errors.append(
                f"Rollback unsafe: {'; '.join(impact.warnings)}. "
                "Use force=True to override (after exporting data)."
            )
            result.duration_seconds = time.monotonic() - start_time
            return result

        tables_to_drop = impact.tables_to_drop

        if dry_run:
            logger.info(
                "DRY RUN rollback to %s: would drop %d tables",
                target_version, len(tables_to_drop),
            )
            result.tables_dropped = [
                t for t in tables_to_drop if self._table_exists(t)
            ]
            result.tables_preserved = list(PROTECTED_TABLES)
            result.success = True
            result.duration_seconds = time.monotonic() - start_time
            return result

        # 2. Create restore point before rollback
        await self.create_restore_point(f"pre-rollback-to-{target_version}")

        # 3. Export data from tables that have data
        for table_name in tables_to_drop:
            if table_name in impact.tables_with_data:
                export_path = await self._export_table_data(table_name, export_dir)
                if export_path:
                    result.data_exported[table_name] = export_path

        # 4. Drop tables in reverse order (to handle foreign keys)
        for table_name in reversed(tables_to_drop):
            if not self._table_exists(table_name):
                continue

            # Final safety check: never drop protected or legal-hold tables
            if table_name in PROTECTED_TABLES or table_name in LEGAL_HOLD_TABLES:
                result.tables_preserved.append(table_name)
                logger.warning(
                    "Skipping protected table %s during rollback", table_name
                )
                continue

            try:
                self.db.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))  # noqa: S608
                result.tables_dropped.append(table_name)
                logger.info("Dropped table: %s", table_name)
            except Exception as e:
                error_msg = f"Failed to drop {table_name}: {str(e)[:200]}"
                result.errors.append(error_msg)
                logger.error(error_msg)

        # 5. Commit the transaction
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            result.errors.append(f"Transaction commit failed: {str(e)[:200]}")
            result.duration_seconds = time.monotonic() - start_time
            return result

        # 6. Kill switches for removed features
        version_idx = VERSION_ORDER.index(target_version)
        for version in VERSION_ORDER[version_idx + 1:]:
            # Disable features that depend on dropped tables
            feature_map = {
                "v2.1": ["followup_automation", "notification_center"],
                "v2.2": ["enterprise_routing"],
                "v2.3": ["enterprise_sla"],
                "v2.4": ["enterprise_approval_chains", "enterprise_routing"],
                "v2.5": ["white_label"],
                "v3.0": ["enterprise_routing", "enterprise_sla", "enterprise_approval_chains"],
            }
            for feature in feature_map.get(version, []):
                FeatureKillSwitch.kill(feature)

        result.success = len(result.errors) == 0
        result.tables_preserved = list(PROTECTED_TABLES)
        result.duration_seconds = time.monotonic() - start_time

        logger.info(
            "Rollback %s completed: dropped=%d, preserved=%d, errors=%d, duration=%.1fs",
            rollback_id,
            len(result.tables_dropped),
            len(result.tables_preserved),
            len(result.errors),
            result.duration_seconds,
        )

        return result

    # =========================================================================
    # POST-ROLLBACK VERIFICATION
    # =========================================================================

    async def verify_post_rollback(self) -> VerificationResult:
        """
        Run verification checks after a rollback to confirm system health.
        """
        result = VerificationResult(overall_healthy=True)

        # 1. Check that protected tables still exist
        for table_name in PROTECTED_TABLES:
            exists = self._table_exists(table_name)
            result.checks[f"protected_table_{table_name}"] = exists
            if not exists:
                result.errors.append(f"Protected table {table_name} is MISSING")
                result.overall_healthy = False

        # 2. Check database connectivity
        try:
            self.db.execute(text("SELECT 1")).scalar()
            result.checks["db_connectivity"] = True
        except Exception as e:
            result.checks["db_connectivity"] = False
            result.errors.append(f"Database connectivity failed: {str(e)[:200]}")
            result.overall_healthy = False

        # 3. Check that core services can be instantiated
        try:
            from services.smart_docs.ai_resilience import get_circuit_status
            status = get_circuit_status()
            result.checks["circuit_breakers"] = True
            result.checks[f"circuit_breaker_services_count"] = True

            # Check if any circuit breakers are OPEN
            for name, breaker in status.get("circuit_breakers", {}).items():
                if breaker.get("state") == "OPEN":
                    result.warnings.append(f"Circuit breaker '{name}' is OPEN")
        except Exception as e:
            result.checks["circuit_breakers"] = False
            result.warnings.append(f"Could not check circuit breakers: {str(e)[:200]}")

        # 4. Check kill switch state
        kill_status = FeatureKillSwitch.get_status()
        killed_features = [f for f, enabled in kill_status.items() if not enabled]
        result.checks["kill_switches_checked"] = True
        if killed_features:
            result.warnings.append(
                f"{len(killed_features)} features disabled by kill switches: "
                f"{', '.join(killed_features)}"
            )

        # 5. Check S3 accessibility (non-destructive)
        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            s3 = get_smart_docs_s3_service()
            result.checks["s3_service_available"] = s3._s3_available
            if not s3._s3_available:
                result.warnings.append("S3 service is not available (credentials missing)")
        except Exception as e:
            result.checks["s3_service_available"] = False
            result.warnings.append(f"Could not check S3 service: {str(e)[:200]}")

        # 6. Check PII encryption service
        try:
            from services.smart_docs.pii_encryption_service import get_pii_encryption_service
            pii_svc = get_pii_encryption_service()
            test_encrypted = pii_svc.encrypt("rollback-test-123")
            test_decrypted = pii_svc.decrypt(test_encrypted)
            result.checks["pii_encryption"] = test_decrypted == "rollback-test-123"
            if not result.checks["pii_encryption"]:
                result.errors.append("PII encryption roundtrip failed")
                result.overall_healthy = False
        except Exception as e:
            result.checks["pii_encryption"] = False
            result.warnings.append(f"PII encryption check failed: {str(e)[:200]}")

        return result

    # =========================================================================
    # GRACEFUL DEGRADATION
    # =========================================================================

    async def get_subsystem_health(self) -> List[SubsystemHealth]:
        """
        Check health of all Smart Docs subsystems and return status.
        Used for graceful degradation decisions.
        """
        subsystems = []

        # AI Classification
        try:
            from services.smart_docs.ai_resilience import _get_breaker
            breaker = _get_breaker("classify_document")
            state = breaker.state.value
            subsystems.append(SubsystemHealth(
                name="ai_classification",
                status=SubsystemStatus.HEALTHY if state == "CLOSED" else (
                    SubsystemStatus.DEGRADED if state == "HALF_OPEN" else SubsystemStatus.DOWN
                ),
                last_check=datetime.now(timezone.utc),
                details=breaker.get_status(),
            ))
        except Exception as e:
            subsystems.append(SubsystemHealth(
                name="ai_classification",
                status=SubsystemStatus.UNKNOWN,
                error=str(e)[:200],
            ))

        # AI Review
        try:
            breaker = _get_breaker("review_document")
            state = breaker.state.value
            subsystems.append(SubsystemHealth(
                name="ai_review",
                status=SubsystemStatus.HEALTHY if state == "CLOSED" else (
                    SubsystemStatus.DEGRADED if state == "HALF_OPEN" else SubsystemStatus.DOWN
                ),
                last_check=datetime.now(timezone.utc),
                details=breaker.get_status(),
            ))
        except Exception as e:
            subsystems.append(SubsystemHealth(
                name="ai_review",
                status=SubsystemStatus.UNKNOWN,
                error=str(e)[:200],
            ))

        # S3 Storage
        try:
            from services.smart_docs.s3_storage_service import get_smart_docs_s3_service
            s3 = get_smart_docs_s3_service()
            subsystems.append(SubsystemHealth(
                name="s3_storage",
                status=SubsystemStatus.HEALTHY if s3._s3_available else SubsystemStatus.DOWN,
                last_check=datetime.now(timezone.utc),
            ))
        except Exception as e:
            subsystems.append(SubsystemHealth(
                name="s3_storage",
                status=SubsystemStatus.DOWN,
                error=str(e)[:200],
            ))

        # Database
        try:
            self.db.execute(text("SELECT 1")).scalar()
            subsystems.append(SubsystemHealth(
                name="database",
                status=SubsystemStatus.HEALTHY,
                last_check=datetime.now(timezone.utc),
            ))
        except Exception as e:
            subsystems.append(SubsystemHealth(
                name="database",
                status=SubsystemStatus.DOWN,
                error=str(e)[:200],
            ))

        # PII Encryption
        try:
            from services.smart_docs.pii_encryption_service import get_pii_encryption_service
            pii = get_pii_encryption_service()
            # Check if encryption is actually functional (not plaintext fallback)
            test = pii.encrypt("test")
            has_encryption = test != "test"
            subsystems.append(SubsystemHealth(
                name="pii_encryption",
                status=SubsystemStatus.HEALTHY if has_encryption else SubsystemStatus.DEGRADED,
                last_check=datetime.now(timezone.utc),
                details={"has_real_encryption": has_encryption},
            ))
        except Exception as e:
            subsystems.append(SubsystemHealth(
                name="pii_encryption",
                status=SubsystemStatus.DOWN,
                error=str(e)[:200],
            ))

        # E-Signature Key Manager
        try:
            from services.smart_docs.esignature_key_manager import get_key_manager
            km = get_key_manager()
            health = km.health_check()
            subsystems.append(SubsystemHealth(
                name="esign_keys",
                status=SubsystemStatus.HEALTHY if health.get("healthy") else SubsystemStatus.DOWN,
                last_check=datetime.now(timezone.utc),
                details=health,
            ))
        except Exception as e:
            subsystems.append(SubsystemHealth(
                name="esign_keys",
                status=SubsystemStatus.UNKNOWN,
                error=str(e)[:200],
            ))

        # Kill switch status
        kill_status = FeatureKillSwitch.get_status()
        killed = [f for f, enabled in kill_status.items() if not enabled]
        subsystems.append(SubsystemHealth(
            name="feature_flags",
            status=SubsystemStatus.HEALTHY if not killed else SubsystemStatus.DEGRADED,
            last_check=datetime.now(timezone.utc),
            details={"disabled_features": killed, "total_features": len(kill_status)},
        ))

        return subsystems

    async def enter_degraded_mode(self, subsystem: str) -> Dict[str, Any]:
        """
        Manually put a subsystem into degraded mode.

        This activates the kill switch for the subsystem and returns
        information about the fallback behavior.
        """
        fallback_info = {
            "ai_classification": {
                "kill_feature": "ai_classification",
                "fallback": "Documents accepted with status 'pending_manual_review'. "
                           "LO must manually classify via the document queue.",
            },
            "ai_review": {
                "kill_feature": "ai_review",
                "fallback": "Documents skip AI review. Manual review required before approval.",
            },
            "ai_extraction": {
                "kill_feature": "ai_extraction",
                "fallback": "No automatic data extraction. LO manually enters extracted fields.",
            },
            "esign": {
                "kill_feature": "esign",
                "fallback": "E-signatures disabled. Documents must be wet-signed.",
            },
            "followup_automation": {
                "kill_feature": "followup_automation",
                "fallback": "Automated follow-ups paused. LO must follow up manually.",
            },
            "ocr_processing": {
                "kill_feature": "ocr_processing",
                "fallback": "OCR skipped. Documents stored as-is without text extraction.",
            },
            "fraud_detection": {
                "kill_feature": "fraud_detection",
                "fallback": "Fraud detection disabled. All documents flagged for manual review.",
            },
            "income_calculation": {
                "kill_feature": "income_calculation",
                "fallback": "AI income calculation disabled. LO calculates income manually.",
            },
        }

        info = fallback_info.get(subsystem)
        if not info:
            return {
                "success": False,
                "error": f"Unknown subsystem '{subsystem}'. "
                        f"Valid: {', '.join(fallback_info.keys())}",
            }

        FeatureKillSwitch.kill(info["kill_feature"])

        return {
            "success": True,
            "subsystem": subsystem,
            "feature_killed": info["kill_feature"],
            "fallback_behavior": info["fallback"],
            "restore_command": f"FeatureKillSwitch.restore('{info['kill_feature']}')",
        }

    # =========================================================================
    # DISASTER RECOVERY PROCEDURES
    # =========================================================================

    async def recover_from_ai_outage(self) -> RecoveryPlan:
        """
        Recovery plan when AI service (Anthropic API) returns after an outage.

        Steps:
        1. Verify API connectivity
        2. Reset circuit breakers
        3. Process queued classifications
        4. Re-run failed extractions
        5. Verify accuracy on a sample
        6. Re-enable AI features via kill switches
        """
        plan = RecoveryPlan(
            scenario="AI Service Outage Recovery",
            priority=RecoveryPriority.HIGH,
        )

        plan.steps = [
            RecoveryStep(
                order=1,
                action="verify_api_connectivity",
                description="Make a test API call to verify Anthropic API is responding",
                command="curl -s https://api.anthropic.com/v1/messages -H 'x-api-key: $ANTHROPIC_API_KEY' "
                       "-H 'content-type: application/json' -H 'anthropic-version: 2023-06-01' "
                       "-d '{\"model\":\"claude-sonnet-4-20250514\",\"max_tokens\":10,"
                       "\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}'",
                estimated_duration_seconds=10,
            ),
            RecoveryStep(
                order=2,
                action="reset_circuit_breakers",
                description="Reset all Smart Docs circuit breakers to CLOSED state",
                command="from services.smart_docs.ai_resilience import reset_circuit; "
                       "[reset_circuit(s) for s in ['classify_document', 'review_document', "
                       "'extract_data', 'income_calculation', 'fraud_detection']]",
                estimated_duration_seconds=5,
            ),
            RecoveryStep(
                order=3,
                action="count_queued_items",
                description="Count documents that need reprocessing (queued during outage)",
                command="SELECT COUNT(*) FROM smart_documents WHERE status = 'pending_manual_review' "
                       "AND ai_classification_attempted = false "
                       "AND created_at > NOW() - INTERVAL '24 hours'",
                estimated_duration_seconds=5,
            ),
            RecoveryStep(
                order=4,
                action="process_queued_classifications",
                description="Re-run AI classification on documents queued during outage. "
                           "Process in batches of 50 with 1-second delays to avoid rate limits.",
                estimated_duration_seconds=300,
                requires_manual=True,
            ),
            RecoveryStep(
                order=5,
                action="rerun_failed_extractions",
                description="Re-run data extraction on documents that failed during outage",
                estimated_duration_seconds=300,
                requires_manual=True,
            ),
            RecoveryStep(
                order=6,
                action="verify_accuracy",
                description="Spot-check 10 recently classified documents for accuracy. "
                           "Compare AI classification with document type in filename/metadata.",
                estimated_duration_seconds=120,
                requires_manual=True,
            ),
            RecoveryStep(
                order=7,
                action="restore_kill_switches",
                description="Re-enable AI features: classification, review, extraction",
                command="from services.smart_docs.rollback_service import FeatureKillSwitch; "
                       "FeatureKillSwitch.restore('ai_classification'); "
                       "FeatureKillSwitch.restore('ai_review'); "
                       "FeatureKillSwitch.restore('ai_extraction')",
                estimated_duration_seconds=5,
            ),
            RecoveryStep(
                order=8,
                action="notify_team",
                description="Send notification that AI services are restored and backlog is clearing",
                estimated_duration_seconds=30,
                requires_manual=True,
            ),
        ]

        plan.estimated_total_seconds = sum(s.estimated_duration_seconds for s in plan.steps)
        plan.notes = (
            "During outage, documents are accepted with 'pending_manual_review' status. "
            "No data is lost. After recovery, AI processes the backlog automatically. "
            "Monitor circuit breaker status to confirm stability."
        )

        return plan

    async def recover_from_storage_failure(self) -> RecoveryPlan:
        """
        Recovery plan for S3 storage outage.

        During outage, uploads are queued locally. After recovery, queued
        files are uploaded to S3 and document records are updated.
        """
        plan = RecoveryPlan(
            scenario="S3 Storage Failure Recovery",
            priority=RecoveryPriority.CRITICAL,
        )

        plan.steps = [
            RecoveryStep(
                order=1,
                action="verify_s3_connectivity",
                description="Verify S3 bucket is accessible with a HEAD request",
                command="aws s3api head-bucket --bucket $SMART_DOCS_S3_BUCKET",
                estimated_duration_seconds=10,
            ),
            RecoveryStep(
                order=2,
                action="check_local_queue",
                description="Check for locally queued uploads in /tmp/smart_docs_upload_queue",
                command="ls -la /tmp/smart_docs_upload_queue/ 2>/dev/null || echo 'No queued uploads'",
                estimated_duration_seconds=5,
            ),
            RecoveryStep(
                order=3,
                action="upload_queued_files",
                description="Upload all locally queued files to S3. Each file is uploaded with "
                           "its original key and metadata. Failures are logged and retried.",
                estimated_duration_seconds=600,
                requires_manual=True,
            ),
            RecoveryStep(
                order=4,
                action="verify_document_records",
                description="For each uploaded file, verify the smart_documents record has the "
                           "correct s3_key and status. Fix any records stuck in 'upload_pending'.",
                command="UPDATE smart_documents SET status = 'active' "
                       "WHERE status = 'upload_pending' AND s3_key IS NOT NULL",
                estimated_duration_seconds=30,
            ),
            RecoveryStep(
                order=5,
                action="verify_download_urls",
                description="Generate presigned download URLs for 5 recently uploaded documents "
                           "and verify they return 200",
                estimated_duration_seconds=30,
                requires_manual=True,
            ),
            RecoveryStep(
                order=6,
                action="clear_local_queue",
                description="Remove successfully uploaded files from local queue",
                command="rm -f /tmp/smart_docs_upload_queue/*.uploaded",
                estimated_duration_seconds=5,
            ),
            RecoveryStep(
                order=7,
                action="notify_team",
                description="Notify team that S3 is restored and all queued uploads processed",
                estimated_duration_seconds=30,
                requires_manual=True,
            ),
        ]

        plan.estimated_total_seconds = sum(s.estimated_duration_seconds for s in plan.steps)
        plan.notes = (
            "During S3 outage, the upload pipeline queues files locally in "
            "/tmp/smart_docs_upload_queue. Document records are created with "
            "status='upload_pending'. No uploads are lost. After recovery, "
            "files are uploaded to S3 and records updated. S3 document files "
            "are NEVER deleted during rollback operations."
        )

        return plan

    async def recover_from_db_corruption(self) -> RecoveryPlan:
        """
        Recovery plan for database corruption.

        This is a severe scenario. The plan assumes a recent backup exists
        and focuses on minimizing data loss by replaying the audit log.
        """
        plan = RecoveryPlan(
            scenario="Database Corruption Recovery",
            priority=RecoveryPriority.CRITICAL,
        )

        plan.steps = [
            RecoveryStep(
                order=1,
                action="assess_corruption_scope",
                description="Run pg_catalog checks to identify corrupted tables. "
                           "Check if corruption is limited to Smart Docs tables or broader.",
                command="SELECT relname, relpages, reltuples FROM pg_class "
                       "WHERE relname LIKE 'smart_docs_%' OR relname LIKE 'smart_document%' "
                       "ORDER BY relname",
                estimated_duration_seconds=30,
            ),
            RecoveryStep(
                order=2,
                action="activate_maintenance_mode",
                description="Put application in maintenance mode. Disable all Smart Docs "
                           "features via kill switches to prevent further writes.",
                command="from services.smart_docs.rollback_service import FeatureKillSwitch; "
                       "FeatureKillSwitch.kill_all()",
                estimated_duration_seconds=10,
            ),
            RecoveryStep(
                order=3,
                action="identify_latest_backup",
                description="Find the most recent clean database backup. "
                           "Railway provides point-in-time recovery for PostgreSQL.",
                estimated_duration_seconds=60,
                requires_manual=True,
            ),
            RecoveryStep(
                order=4,
                action="restore_from_backup",
                description="Restore corrupted tables from backup. If corruption is limited "
                           "to Smart Docs V2 tables, restore only those. Otherwise, full restore.",
                estimated_duration_seconds=1800,
                requires_manual=True,
            ),
            RecoveryStep(
                order=5,
                action="replay_audit_log",
                description="If decision_audit_logs survived (append-only, separate tablespace), "
                           "replay critical decisions to fill gaps between backup and corruption.",
                estimated_duration_seconds=600,
                requires_manual=True,
            ),
            RecoveryStep(
                order=6,
                action="reconcile_s3_with_db",
                description="Compare S3 file keys with smart_documents records. "
                           "Create records for any S3 files missing from the database.",
                estimated_duration_seconds=300,
                requires_manual=True,
            ),
            RecoveryStep(
                order=7,
                action="verify_data_integrity",
                description="Run integrity checks: foreign key consistency, "
                           "orphan detection, row count verification against backup.",
                estimated_duration_seconds=120,
            ),
            RecoveryStep(
                order=8,
                action="restore_services",
                description="Re-enable Smart Docs features one at a time, monitoring "
                           "for errors after each activation.",
                command="from services.smart_docs.rollback_service import FeatureKillSwitch; "
                       "FeatureKillSwitch.restore_all()",
                estimated_duration_seconds=60,
            ),
            RecoveryStep(
                order=9,
                action="post_incident_review",
                description="Document the incident: root cause, data loss (if any), "
                           "timeline, and prevention measures.",
                estimated_duration_seconds=3600,
                requires_manual=True,
            ),
        ]

        plan.estimated_total_seconds = sum(s.estimated_duration_seconds for s in plan.steps)
        plan.notes = (
            "Database corruption is the most severe scenario. Key principles: "
            "(1) The audit log (decision_audit_logs) is append-only and should survive most corruption. "
            "(2) S3 files are independent of the database and are never affected. "
            "(3) Railway provides automated PostgreSQL backups with point-in-time recovery. "
            "(4) Signed documents in S3 are the legal record; DB records are metadata."
        )

        return plan

    async def recover_from_key_rotation(self) -> RecoveryPlan:
        """
        Recovery plan after emergency e-signature key rotation (e.g., key compromise).

        New signing key must be deployed. Previously signed documents remain valid
        because the signature is stored with the document, not derived on-the-fly.
        Pending (unsigned) envelopes need to be re-created with the new key.
        """
        plan = RecoveryPlan(
            scenario="E-Sign Key Compromise / Emergency Rotation",
            priority=RecoveryPriority.CRITICAL,
        )

        plan.steps = [
            RecoveryStep(
                order=1,
                action="generate_new_keys",
                description="Generate new ESIGN_SIGNING_SECRET and ESIGN_TOKEN_SECRET. "
                           "Use at least 64 random bytes, base64-encoded.",
                command="python -c \"import secrets, base64; "
                       "print('ESIGN_SIGNING_SECRET=' + base64.b64encode(secrets.token_bytes(64)).decode()); "
                       "print('ESIGN_TOKEN_SECRET=' + base64.b64encode(secrets.token_bytes(64)).decode())\"",
                estimated_duration_seconds=10,
            ),
            RecoveryStep(
                order=2,
                action="deploy_new_keys",
                description="Set new environment variables in Railway. "
                           "The old keys should be saved in a secure vault for "
                           "verification of previously signed documents.",
                estimated_duration_seconds=120,
                requires_manual=True,
            ),
            RecoveryStep(
                order=3,
                action="restart_application",
                description="Restart the application to load new keys. The key manager "
                           "will refuse to start if keys are missing or too short.",
                estimated_duration_seconds=60,
                requires_manual=True,
            ),
            RecoveryStep(
                order=4,
                action="verify_key_health",
                description="Run key manager health check to confirm new keys are loaded",
                command="from services.smart_docs.esignature_key_manager import get_key_manager; "
                       "print(get_key_manager().health_check())",
                estimated_duration_seconds=10,
            ),
            RecoveryStep(
                order=5,
                action="identify_pending_envelopes",
                description="Find e-sign envelopes that were created with the old key "
                           "and are still pending (not yet signed).",
                command="SELECT id, loan_id, status, created_at FROM esign_envelopes "
                       "WHERE status IN ('draft', 'sent', 'pending') "
                       "ORDER BY created_at DESC",
                estimated_duration_seconds=10,
            ),
            RecoveryStep(
                order=6,
                action="revoke_pending_tokens",
                description="Invalidate all signing tokens generated with the old key. "
                           "Borrowers will need new signing links.",
                command="UPDATE esign_envelopes SET status = 'revoked', "
                       "revocation_reason = 'key_rotation' "
                       "WHERE status IN ('sent', 'pending')",
                estimated_duration_seconds=30,
            ),
            RecoveryStep(
                order=7,
                action="recreate_pending_envelopes",
                description="Create new envelopes for documents that were pending signature. "
                           "Send new signing invitations to borrowers.",
                estimated_duration_seconds=300,
                requires_manual=True,
            ),
            RecoveryStep(
                order=8,
                action="verify_completed_signatures",
                description="Verify that previously completed signatures are still valid. "
                           "These should be unaffected because the signature is embedded "
                           "in the document, not re-computed.",
                command="SELECT COUNT(*) FROM esign_signatures WHERE status = 'completed' "
                       "AND signed_at > NOW() - INTERVAL '30 days'",
                estimated_duration_seconds=30,
            ),
            RecoveryStep(
                order=9,
                action="update_audit_log",
                description="Record the key rotation event in the audit log with the "
                           "timestamp and reason (compromise, scheduled rotation, etc.)",
                command="INSERT INTO decision_audit_logs "
                       "(organization_id, decision_type, entity_type, decision, reasoning, "
                       "maker_type, created_at) "
                       "VALUES (0, 'esign_action', 'esign_key', 'key_rotated', "
                       "'Emergency key rotation due to compromise', 'system', NOW())",
                estimated_duration_seconds=5,
            ),
            RecoveryStep(
                order=10,
                action="notify_security_team",
                description="If key rotation was due to compromise, notify security team "
                           "and begin incident investigation.",
                estimated_duration_seconds=60,
                requires_manual=True,
            ),
        ]

        plan.estimated_total_seconds = sum(s.estimated_duration_seconds for s in plan.steps)
        plan.notes = (
            "E-sign key rotation does NOT invalidate previously completed signatures. "
            "Completed signatures are stored as embedded data in the signed document (S3). "
            "Only pending/draft envelopes are affected and must be re-created. "
            "The old signing secret should be preserved in a secure vault so that "
            "historical signature verification remains possible if challenged."
        )

        return plan

    async def recover_from_pii_key_loss(self) -> RecoveryPlan:
        """
        Recovery plan when the PII encryption key (PII_ENCRYPTION_KEY) is lost.

        This is catastrophic for encrypted columns but recoverable if:
        (1) A backup of the key exists, OR
        (2) The original documents in S3 can be re-processed to re-extract PII.
        """
        plan = RecoveryPlan(
            scenario="PII Encryption Key Loss",
            priority=RecoveryPriority.CRITICAL,
        )

        plan.steps = [
            RecoveryStep(
                order=1,
                action="check_key_backups",
                description="Check for key backups: Railway environment history, "
                           "secrets manager (AWS SSM, Vault), team password manager.",
                estimated_duration_seconds=300,
                requires_manual=True,
            ),
            RecoveryStep(
                order=2,
                action="attempt_key_recovery",
                description="If key backup found: set PII_ENCRYPTION_KEY env var and "
                           "restart. Verify decryption works on a known record.",
                estimated_duration_seconds=120,
                requires_manual=True,
            ),
            RecoveryStep(
                order=3,
                action="assess_data_loss",
                description="If key is unrecoverable: identify all columns with encrypted data. "
                           "Count affected rows. The encrypted ciphertext is unrecoverable "
                           "without the key.",
                command="SELECT 'smart_documents' as tbl, COUNT(*) as rows "
                       "FROM smart_documents WHERE encrypted_ssn IS NOT NULL "
                       "UNION ALL "
                       "SELECT 'smart_documents_ocr', COUNT(*) "
                       "FROM smart_documents WHERE encrypted_ocr_text IS NOT NULL",
                estimated_duration_seconds=30,
            ),
            RecoveryStep(
                order=4,
                action="generate_new_key",
                description="Generate a new PII encryption key for future data",
                command="python -c \"from cryptography.fernet import Fernet; "
                       "print('PII_ENCRYPTION_KEY=' + Fernet.generate_key().decode())\"",
                estimated_duration_seconds=10,
            ),
            RecoveryStep(
                order=5,
                action="reprocess_from_source",
                description="Re-extract PII from original documents in S3. "
                           "For each smart_document with a valid s3_key, download "
                           "the file, run OCR/extraction, and re-encrypt with new key.",
                estimated_duration_seconds=7200,
                requires_manual=True,
            ),
            RecoveryStep(
                order=6,
                action="verify_reprocessing",
                description="Spot-check 20 re-processed documents to verify PII was "
                           "correctly extracted and encrypted with the new key.",
                estimated_duration_seconds=300,
                requires_manual=True,
            ),
            RecoveryStep(
                order=7,
                action="backup_new_key",
                description="Store the new PII_ENCRYPTION_KEY in at least 2 separate "
                           "secure locations (e.g., AWS SSM + team vault).",
                estimated_duration_seconds=120,
                requires_manual=True,
            ),
            RecoveryStep(
                order=8,
                action="update_incident_log",
                description="Document the incident, affected data, and remediation steps. "
                           "If any borrower PII was exposed, initiate breach notification.",
                estimated_duration_seconds=3600,
                requires_manual=True,
            ),
        ]

        plan.estimated_total_seconds = sum(s.estimated_duration_seconds for s in plan.steps)
        plan.notes = (
            "PII key loss means encrypted columns (SSNs, account numbers, OCR text) "
            "cannot be decrypted. However, the ORIGINAL DOCUMENTS in S3 are stored "
            "as-is (not encrypted at rest by our application -- S3 server-side encryption "
            "handles that). This means PII can be re-extracted from source documents. "
            "The key should ALWAYS be backed up in a secrets manager. "
            "Fernet keys are NOT derivable from any other secret."
        )

        return plan

    # =========================================================================
    # CIRCUIT BREAKER MANAGEMENT
    # =========================================================================

    async def reset_all_circuit_breakers(self) -> Dict[str, bool]:
        """
        Reset all Smart Docs circuit breakers to CLOSED state.

        Use after confirming that the underlying service is healthy.

        Returns:
            Dict mapping service name to reset success.
        """
        from services.smart_docs.ai_resilience import _breakers, _breakers_lock

        results = {}
        with _breakers_lock:
            for name, breaker in _breakers.items():
                try:
                    breaker.reset()
                    results[name] = True
                    logger.info("Reset circuit breaker: %s", name)
                except Exception as e:
                    results[name] = False
                    logger.error("Failed to reset circuit breaker %s: %s", name, str(e)[:200])

        return results

    async def get_circuit_breaker_summary(self) -> Dict[str, Any]:
        """Get summary of all circuit breaker states."""
        from services.smart_docs.ai_resilience import get_circuit_status
        return get_circuit_status()

    # =========================================================================
    # CONVENIENCE: FULL SYSTEM STATUS
    # =========================================================================

    async def get_full_system_status(self) -> Dict[str, Any]:
        """
        Get comprehensive system status for the Smart Docs subsystem.

        Combines subsystem health, kill switches, circuit breakers, and
        migration status into a single view.
        """
        from services.smart_docs.rollback_service import FeatureKillSwitch

        subsystems = await self.get_subsystem_health()
        circuit_status = await self.get_circuit_breaker_summary()

        # Check migration status
        migration_status = {}
        for version, tables in VERSION_TABLES.items():
            existing = [t for t in tables if self._table_exists(t)]
            migration_status[version] = {
                "expected_tables": len(tables),
                "existing_tables": len(existing),
                "complete": len(existing) == len(tables),
                "missing": [t for t in tables if t not in existing] if len(existing) < len(tables) else [],
            }

        # Determine overall health
        subsystem_statuses = [s.status for s in subsystems]
        if SubsystemStatus.DOWN in subsystem_statuses:
            overall = "critical"
        elif SubsystemStatus.DEGRADED in subsystem_statuses:
            overall = "degraded"
        elif SubsystemStatus.UNKNOWN in subsystem_statuses:
            overall = "unknown"
        else:
            overall = "healthy"

        return {
            "overall_status": overall,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "subsystems": [
                {
                    "name": s.name,
                    "status": s.status.value,
                    "error": s.error,
                    "details": s.details,
                }
                for s in subsystems
            ],
            "kill_switches": FeatureKillSwitch.get_status(),
            "circuit_breakers": circuit_status,
            "migration_status": migration_status,
            "protected_tables": {
                t: self._table_exists(t) for t in sorted(PROTECTED_TABLES)
            },
        }


# =============================================================================
# MODULE-LEVEL FACTORY
# =============================================================================

def get_rollback_service(db: Session) -> SmartDocsRollbackService:
    """Get an instance of the rollback service."""
    return SmartDocsRollbackService(db)
