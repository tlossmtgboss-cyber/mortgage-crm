"""
Backup Verification Service
Enterprise Readiness - Domain 8: Disaster Recovery (Check 8.3)

Provides backup verification, integrity checking, RPO compliance monitoring,
and backup history tracking for Railway PostgreSQL deployments.
"""

import os
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# RPO/RTO configuration (configurable via environment)
RPO_TARGET_HOURS = float(os.getenv("DR_RPO_TARGET_HOURS", "1"))
RTO_TARGET_HOURS = float(os.getenv("DR_RTO_TARGET_HOURS", "4"))
BACKUP_WARN_THRESHOLD_HOURS = float(os.getenv("BACKUP_WARN_THRESHOLD_HOURS", "0.75"))

# Key tables to verify during backup integrity checks
KEY_TABLES = [
    "users",
    "organizations",
    "leads",
    "loans",
    "audit_logs",
]


class BackupVerificationService:
    """
    Verifies database backup status, integrity, and RPO compliance.

    Designed for Railway PostgreSQL which provides automatic daily backups
    with point-in-time recovery. This service adds verification and monitoring
    on top of the platform-provided backup infrastructure.
    """

    def __init__(self, db: Session):
        self.db = db

    def verify_latest_backup(self) -> Dict[str, Any]:
        """
        Check that a recent backup exists by querying PostgreSQL WAL
        and replication status. On Railway, backups are WAL-based, so we
        check WAL archiving status and the last checkpoint time.

        Returns:
            Dict with backup status, last backup time, and compliance info.
        """
        result = {
            "status": "unknown",
            "last_checkpoint": None,
            "wal_archiving": None,
            "rpo_compliant": False,
            "rpo_target_hours": RPO_TARGET_HOURS,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Check last checkpoint time from pg_control_checkpoint()
            checkpoint = self.db.execute(text(
                "SELECT checkpoint_time, timeline_id "
                "FROM pg_control_checkpoint()"
            )).fetchone()

            if checkpoint:
                checkpoint_time = checkpoint[0]
                if checkpoint_time.tzinfo is None:
                    checkpoint_time = checkpoint_time.replace(tzinfo=timezone.utc)

                result["last_checkpoint"] = checkpoint_time.isoformat()
                result["timeline_id"] = checkpoint[1]

                age_hours = (
                    datetime.now(timezone.utc) - checkpoint_time
                ).total_seconds() / 3600

                result["hours_since_checkpoint"] = round(age_hours, 2)
                result["rpo_compliant"] = age_hours <= RPO_TARGET_HOURS

                if age_hours <= RPO_TARGET_HOURS:
                    result["status"] = "healthy"
                elif age_hours <= RPO_TARGET_HOURS * 2:
                    result["status"] = "warning"
                else:
                    result["status"] = "critical"

        except Exception as e:
            # pg_control_checkpoint may not be available on all setups;
            # fall back to pg_stat_activity for approximate timing
            logger.warning(f"pg_control_checkpoint not available: {e}")
            try:
                self.db.rollback()
                activity = self.db.execute(text(
                    "SELECT now() AS current_time, "
                    "pg_postmaster_start_time() AS server_start"
                )).fetchone()

                if activity:
                    result["server_time"] = activity[0].isoformat() if activity[0] else None
                    result["server_start"] = activity[1].isoformat() if activity[1] else None
                    result["status"] = "partial"
                    result["note"] = (
                        "pg_control_checkpoint() not available; "
                        "using server uptime as proxy"
                    )
            except Exception as inner_e:
                logger.error(f"Backup verification fallback failed: {inner_e}")
                self.db.rollback()
                result["status"] = "error"
                result["error"] = "Could not query backup status"

        # Check WAL archiving status if available
        try:
            wal_status = self.db.execute(text(
                "SELECT archived_count, failed_count, "
                "last_archived_wal, last_archived_time "
                "FROM pg_stat_archiver"
            )).fetchone()

            if wal_status:
                result["wal_archiving"] = {
                    "archived_count": wal_status[0],
                    "failed_count": wal_status[1],
                    "last_archived_wal": wal_status[2],
                    "last_archived_time": (
                        wal_status[3].isoformat() if wal_status[3] else None
                    ),
                }
                if wal_status[1] and wal_status[1] > 0:
                    result["wal_archiving"]["has_failures"] = True
        except Exception as e:
            logger.debug(f"WAL archiver stats not available: {e}")
            self.db.rollback()

        return result

    def verify_backup_integrity(self, backup_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify backup integrity by checking row counts and computing
        checksums on key tables. This provides a snapshot of data state
        that can be compared against a restored backup.

        Args:
            backup_id: Optional identifier for the backup to verify.
                       If None, verifies current database state.

        Returns:
            Dict with table checksums, row counts, and integrity status.
        """
        result = {
            "backup_id": backup_id or "current",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "tables": {},
            "integrity_status": "pass",
            "total_rows": 0,
        }

        for table_name in KEY_TABLES:
            table_result = {
                "status": "unknown",
                "row_count": 0,
                "checksum": None,
            }

            try:
                # Check if table exists
                exists = self.db.execute(text(
                    "SELECT EXISTS ("
                    "  SELECT FROM information_schema.tables "
                    "  WHERE table_name = :table_name"
                    ")"
                ), {"table_name": table_name}).scalar()

                if not exists:
                    table_result["status"] = "missing"
                    result["integrity_status"] = "warning"
                    result["tables"][table_name] = table_result
                    continue

                # Get row count
                count = self.db.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
                ).scalar()
                table_result["row_count"] = count
                result["total_rows"] += count

                # Compute a lightweight checksum using count + max id
                try:
                    max_id = self.db.execute(
                        text(f"SELECT MAX(id) FROM {table_name}")  # noqa: S608
                    ).scalar()

                    checksum_input = f"{table_name}:{count}:{max_id}"
                    table_result["checksum"] = hashlib.sha256(
                        checksum_input.encode()
                    ).hexdigest()[:16]
                    table_result["max_id"] = max_id
                except Exception:
                    # Table may not have 'id' column
                    table_result["checksum"] = hashlib.sha256(
                        f"{table_name}:{count}".encode()
                    ).hexdigest()[:16]

                table_result["status"] = "verified"

            except Exception as e:
                logger.warning(f"Integrity check failed for {table_name}: {e}")
                self.db.rollback()
                table_result["status"] = "error"
                table_result["error"] = str(e)
                result["integrity_status"] = "partial"

            result["tables"][table_name] = table_result

        return result

    def get_backup_history(self, limit: int = 20) -> Dict[str, Any]:
        """
        List recent backup verification records. Since Railway does not
        expose a backup list API directly, we track verifications in the
        backup_verifications table (created on first use).

        Args:
            limit: Maximum number of records to return.

        Returns:
            Dict with backup history and summary stats.
        """
        self._ensure_verification_table()

        try:
            records = self.db.execute(text(
                "SELECT id, verified_at, status, total_rows, "
                "integrity_status, rpo_compliant, details "
                "FROM backup_verifications "
                "ORDER BY verified_at DESC "
                "LIMIT :limit"
            ), {"limit": limit}).fetchall()

            history = []
            for r in records:
                history.append({
                    "id": r[0],
                    "verified_at": r[1].isoformat() if r[1] else None,
                    "status": r[2],
                    "total_rows": r[3],
                    "integrity_status": r[4],
                    "rpo_compliant": r[5],
                })

            return {
                "total_records": len(history),
                "history": history,
            }

        except Exception as e:
            logger.error(f"Error fetching backup history: {e}")
            self.db.rollback()
            return {"total_records": 0, "history": [], "error": str(e)}

    def calculate_rpo_compliance(self) -> Dict[str, Any]:
        """
        Check if RPO target is being met based on backup frequency
        and the most recent verification.

        Returns:
            Dict with RPO compliance status, metrics, and recommendations.
        """
        result = {
            "rpo_target_hours": RPO_TARGET_HOURS,
            "rto_target_hours": RTO_TARGET_HOURS,
            "is_compliant": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "recommendations": [],
        }

        # Get latest backup verification
        backup_status = self.verify_latest_backup()
        result["backup_status"] = backup_status.get("status")
        result["hours_since_checkpoint"] = backup_status.get(
            "hours_since_checkpoint"
        )

        if backup_status.get("rpo_compliant"):
            result["is_compliant"] = True
            result["compliance_status"] = "met"
        else:
            result["compliance_status"] = "at_risk"
            hours_since = backup_status.get("hours_since_checkpoint")
            if hours_since:
                result["recommendations"].append(
                    f"Last checkpoint was {hours_since:.1f} hours ago "
                    f"(target: {RPO_TARGET_HOURS}h). "
                    "Consider increasing WAL archiving frequency."
                )

        # Check WAL archiving health
        wal = backup_status.get("wal_archiving")
        if wal and wal.get("has_failures"):
            result["recommendations"].append(
                f"WAL archiving has {wal['failed_count']} failures. "
                "Investigate archiving configuration."
            )
            result["compliance_status"] = "degraded"

        # Warn if approaching threshold
        hours_since = backup_status.get("hours_since_checkpoint")
        warn_threshold = RPO_TARGET_HOURS * BACKUP_WARN_THRESHOLD_HOURS
        if hours_since and hours_since > warn_threshold and result["is_compliant"]:
            result["recommendations"].append(
                f"Approaching RPO threshold ({hours_since:.1f}h of "
                f"{RPO_TARGET_HOURS}h). Monitor closely."
            )

        return result

    def record_verification(
        self,
        backup_status: Dict[str, Any],
        integrity: Dict[str, Any],
    ) -> Optional[int]:
        """
        Record a backup verification result for audit history.

        Args:
            backup_status: Result from verify_latest_backup()
            integrity: Result from verify_backup_integrity()

        Returns:
            ID of the created record, or None on failure.
        """
        self._ensure_verification_table()

        try:
            import json

            result = self.db.execute(text(
                "INSERT INTO backup_verifications "
                "(verified_at, status, total_rows, integrity_status, "
                "rpo_compliant, details) "
                "VALUES (:verified_at, :status, :total_rows, "
                ":integrity_status, :rpo_compliant, :details) "
                "RETURNING id"
            ), {
                "verified_at": datetime.now(timezone.utc),
                "status": backup_status.get("status", "unknown"),
                "total_rows": integrity.get("total_rows", 0),
                "integrity_status": integrity.get("integrity_status", "unknown"),
                "rpo_compliant": backup_status.get("rpo_compliant", False),
                "details": json.dumps({
                    "backup": backup_status,
                    "integrity": integrity,
                }),
            })
            self.db.commit()

            row = result.fetchone()
            return row[0] if row else None

        except Exception as e:
            logger.error(f"Failed to record backup verification: {e}")
            self.db.rollback()
            return None

    def _ensure_verification_table(self):
        """Create the backup_verifications table if it does not exist."""
        try:
            self.db.execute(text("""
                CREATE TABLE IF NOT EXISTS backup_verifications (
                    id SERIAL PRIMARY KEY,
                    verified_at TIMESTAMP WITH TIME ZONE NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
                    total_rows INTEGER DEFAULT 0,
                    integrity_status VARCHAR(20) DEFAULT 'unknown',
                    rpo_compliant BOOLEAN DEFAULT FALSE,
                    details JSONB,
                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP
                )
            """))
            self.db.commit()
        except Exception as e:
            logger.warning(f"Could not ensure backup_verifications table: {e}")
            self.db.rollback()


def get_dr_status_summary(db: Session) -> Dict[str, Any]:
    """
    Get an overall DR readiness dashboard summarizing backup status,
    RPO/RTO compliance, and replication health.

    Args:
        db: Database session.

    Returns:
        Comprehensive DR status dictionary.
    """
    service = BackupVerificationService(db)

    backup_status = service.verify_latest_backup()
    rpo_compliance = service.calculate_rpo_compliance()
    integrity = service.verify_backup_integrity()

    # Determine overall DR readiness
    issues = []
    if backup_status.get("status") in ("critical", "error"):
        issues.append("Backup status is critical or errored")
    if not rpo_compliance.get("is_compliant"):
        issues.append("RPO target not being met")
    if integrity.get("integrity_status") not in ("pass",):
        issues.append(
            f"Data integrity check: {integrity.get('integrity_status')}"
        )

    if not issues:
        overall_status = "ready"
    elif len(issues) == 1 and "integrity" in issues[0].lower():
        overall_status = "degraded"
    else:
        overall_status = "at_risk"

    return {
        "overall_status": overall_status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "rpo": {
            "target_hours": RPO_TARGET_HOURS,
            "compliant": rpo_compliance.get("is_compliant", False),
            "status": rpo_compliance.get("compliance_status", "unknown"),
        },
        "rto": {
            "target_hours": RTO_TARGET_HOURS,
            "note": "RTO validated during DR drills",
        },
        "backup": {
            "status": backup_status.get("status"),
            "last_checkpoint": backup_status.get("last_checkpoint"),
            "hours_since_checkpoint": backup_status.get(
                "hours_since_checkpoint"
            ),
            "wal_archiving": backup_status.get("wal_archiving"),
        },
        "integrity": {
            "status": integrity.get("integrity_status"),
            "total_rows": integrity.get("total_rows"),
            "tables_checked": len(integrity.get("tables", {})),
        },
        "issues": issues,
        "recommendations": rpo_compliance.get("recommendations", []),
    }
