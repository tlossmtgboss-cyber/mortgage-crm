"""
Retention Service — Data retention and secure disposal.
SOC 2 Criteria: P4 (Privacy — Disposal), C1 (Confidentiality)

Enforces data retention policies, securely disposes of expired data,
and maintains an audit trail of all disposal actions.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..constants import RetentionPolicy, RETENTION_PERIODS, AuditAction
from ..config import SOC2Config

logger = logging.getLogger("soc2.retention")

# Whitelist of table names allowed in retention SQL to prevent injection
ALLOWED_TABLES = frozenset({
    "soc2_audit_log",
    "soc2_access_event",
    "soc2_security_incident",
    "soc2_incident_timeline",
    "soc2_change_record",
    "soc2_compliance_check",
})


def _validate_table_name(table: str) -> None:
    """Validate table name against whitelist before use in SQL."""
    if table not in ALLOWED_TABLES:
        raise ValueError(f"Table '{table}' is not in the allowed retention whitelist")


class RetentionService:
    """
    Data retention policy enforcement.

    Usage:
        retention = RetentionService(db)

        # Run daily to enforce retention policies
        results = retention.enforce_retention_policies()

        # Check what data would be affected
        preview = retention.preview_retention_enforcement()
    """

    def __init__(self, db: Session, config: Optional[SOC2Config] = None):
        self.db = db
        self.config = config or SOC2Config.from_env()

    def enforce_retention_policies(self, user_id: Optional[UUID] = None) -> Dict[str, int]:
        """
        Enforce all retention policies. Should be run daily.
        Returns count of records disposed per policy.

        Args:
            user_id: ID of user triggering enforcement (None for scheduled/system runs).
        """
        results: Dict[str, int] = {}
        now = datetime.now(timezone.utc)

        # SOC 2 compliance tables
        retention_rules = [
            {
                "policy": RetentionPolicy.AUDIT_LOGS,
                "table": "soc2_audit_log",
                "timestamp_col": "timestamp",
                "days": RETENTION_PERIODS[RetentionPolicy.AUDIT_LOGS],
            },
            {
                "policy": RetentionPolicy.ACCESS_LOGS,
                "table": "soc2_access_event",
                "timestamp_col": "timestamp",
                "days": RETENTION_PERIODS[RetentionPolicy.ACCESS_LOGS],
            },
            {
                "policy": RetentionPolicy.INCIDENT_RECORDS,
                "table": "soc2_security_incident",
                "timestamp_col": "created_at",
                "days": RETENTION_PERIODS[RetentionPolicy.INCIDENT_RECORDS],
            },
            {
                "policy": RetentionPolicy.CHANGE_RECORDS,
                "table": "soc2_change_record",
                "timestamp_col": "created_at",
                "days": RETENTION_PERIODS[RetentionPolicy.CHANGE_RECORDS],
            },
            {
                "policy": "compliance_checks",
                "table": "soc2_compliance_check",
                "timestamp_col": "run_at",
                "days": 730,
            },
            {
                "policy": "incident_timeline",
                "table": "soc2_incident_timeline",
                "timestamp_col": "timestamp",
                "days": RETENTION_PERIODS[RetentionPolicy.INCIDENT_RECORDS],
            },
        ]

        for rule in retention_rules:
            _validate_table_name(rule["table"])
            cutoff = now - timedelta(days=rule["days"])
            try:
                # Count before deleting
                count_result = self.db.execute(
                    text(f"""
                        SELECT COUNT(*) FROM {rule['table']}
                        WHERE {rule['timestamp_col']} < :cutoff
                    """),
                    {"cutoff": cutoff}
                )
                count = count_result.fetchone()[0]

                if count > 0:
                    # Delete in batches to avoid long locks
                    total_deleted = 0
                    batch_size = 10000

                    while total_deleted < count:
                        delete_result = self.db.execute(
                            text(f"""
                                DELETE FROM {rule['table']}
                                WHERE id IN (
                                    SELECT id FROM {rule['table']}
                                    WHERE {rule['timestamp_col']} < :cutoff
                                    LIMIT :batch_size
                                )
                            """),
                            {"cutoff": cutoff, "batch_size": batch_size}
                        )
                        batch_deleted = delete_result.rowcount
                        total_deleted += batch_deleted
                        self.db.commit()

                        if batch_deleted < batch_size:
                            break

                    policy_key = rule["policy"].value if hasattr(rule["policy"], "value") else str(rule["policy"])
                    results[policy_key] = total_deleted

                    logger.info(
                        "retention_enforced",
                        extra={
                            "policy": policy_key,
                            "table": rule["table"],
                            "records_deleted": total_deleted,
                            "cutoff_date": cutoff.isoformat(),
                        }
                    )
                else:
                    policy_key = rule["policy"].value if hasattr(rule["policy"], "value") else str(rule["policy"])
                    results[policy_key] = 0

            except Exception as e:
                logger.error(
                    f"Retention enforcement failed for {rule['table']}: {e}"
                )
                policy_key = rule["policy"].value if hasattr(rule["policy"], "value") else str(rule["policy"])
                results[policy_key] = -1  # Error indicator

        # Log the enforcement run
        try:
            self.db.execute(
                text("""
                    INSERT INTO soc2_audit_log (
                        timestamp, user_id, action, resource_type, description,
                        severity, success, new_values
                    ) VALUES (
                        :now, :user_id, :action, :resource_type, :description,
                        'low', TRUE, :results::jsonb
                    )
                """),
                {
                    "now": now,
                    "user_id": str(user_id) if user_id else None,
                    "action": "retention_enforcement",
                    "resource_type": "system",
                    "description": "Automated retention policy enforcement completed",
                    "results": json.dumps(results),
                }
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to log retention enforcement: {e}")

        return results

    def preview_retention_enforcement(self) -> Dict[str, Dict]:
        """Preview what data would be affected by retention enforcement. Non-destructive."""
        now = datetime.now(timezone.utc)
        preview = {}

        tables = [
            ("soc2_audit_log", "timestamp", RETENTION_PERIODS[RetentionPolicy.AUDIT_LOGS]),
            ("soc2_access_event", "timestamp", RETENTION_PERIODS[RetentionPolicy.ACCESS_LOGS]),
        ]

        for table, ts_col, days in tables:
            _validate_table_name(table)
            cutoff = now - timedelta(days=days)
            try:
                result = self.db.execute(
                    text(f"""
                        SELECT
                            COUNT(*) as records_to_delete,
                            MIN({ts_col}) as oldest_record,
                            MAX({ts_col}) as newest_affected
                        FROM {table}
                        WHERE {ts_col} < :cutoff
                    """),
                    {"cutoff": cutoff}
                )
                row = result.fetchone()
                preview[table] = {
                    "records_to_delete": row[0],
                    "oldest_record": row[1].isoformat() if row[1] else None,
                    "newest_affected": row[2].isoformat() if row[2] else None,
                    "retention_days": days,
                    "cutoff_date": cutoff.isoformat(),
                }
            except Exception as e:
                preview[table] = {"error": str(e)}

        return preview

    def get_retention_status(self) -> Dict[str, Dict]:
        """Get current data volumes and retention status for all tracked tables."""
        status = {}

        tables = [
            ("soc2_audit_log", "timestamp"),
            ("soc2_access_event", "timestamp"),
            ("soc2_security_incident", "created_at"),
            ("soc2_change_record", "created_at"),
            ("soc2_compliance_check", "run_at"),
        ]

        for table, ts_col in tables:
            _validate_table_name(table)
            try:
                result = self.db.execute(
                    text(f"""
                        SELECT
                            COUNT(*) as total_records,
                            MIN({ts_col}) as oldest_record,
                            MAX({ts_col}) as newest_record,
                            pg_size_pretty(pg_total_relation_size('{table}')) as table_size
                        FROM {table}
                    """)
                )
                row = result.fetchone()
                status[table] = {
                    "total_records": row[0],
                    "oldest_record": row[1].isoformat() if row[1] else None,
                    "newest_record": row[2].isoformat() if row[2] else None,
                    "table_size": row[3],
                }
            except Exception as e:
                status[table] = {"error": str(e)}

        return status
