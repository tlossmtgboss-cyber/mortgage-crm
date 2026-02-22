"""
Retention Service — Data retention and secure disposal.
SOC 2 Criteria: P4 (Privacy — Disposal), C1 (Confidentiality)

Enforces data retention policies, securely disposes of expired data,
and maintains an audit trail of all disposal actions.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import RetentionPolicy, RETENTION_PERIODS, AuditAction
from ..config import SOC2Config

logger = logging.getLogger("soc2.retention")


class RetentionService:
    """
    Data retention policy enforcement.
    
    Usage:
        retention = RetentionService(db)
        
        # Run daily to enforce retention policies
        results = await retention.enforce_retention_policies()
        
        # Check what data would be affected
        preview = await retention.preview_retention_enforcement()
    """

    def __init__(self, db: AsyncSession, config: Optional[SOC2Config] = None):
        self.db = db
        self.config = config or SOC2Config.from_env()

    async def enforce_retention_policies(self) -> Dict[str, int]:
        """
        Enforce all retention policies. Should be run daily.
        Returns count of records disposed per policy.
        """
        results = {}
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
        ]

        for rule in retention_rules:
            cutoff = now - timedelta(days=rule["days"])
            try:
                # Count before deleting
                count_result = await self.db.execute(
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
                        delete_result = await self.db.execute(
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
                        await self.db.commit()

                        if batch_deleted < batch_size:
                            break

                    results[rule["policy"]] = total_deleted

                    logger.info(
                        "retention_enforced",
                        extra={
                            "policy": rule["policy"],
                            "table": rule["table"],
                            "records_deleted": total_deleted,
                            "cutoff_date": cutoff.isoformat(),
                        }
                    )
                else:
                    results[rule["policy"]] = 0

            except Exception as e:
                logger.error(
                    f"Retention enforcement failed for {rule['table']}: {e}"
                )
                results[rule["policy"]] = -1  # Error indicator

        # Log the enforcement run
        await self.db.execute(
            text("""
                INSERT INTO soc2_audit_log (
                    timestamp, action, resource_type, description,
                    severity, success, new_values
                ) VALUES (
                    :now, :action, :resource_type, :description,
                    'low', TRUE, :results::jsonb
                )
            """),
            {
                "now": now,
                "action": "retention_enforcement",
                "resource_type": "system",
                "description": "Automated retention policy enforcement completed",
                "results": str(results).replace("'", '"'),
            }
        )
        await self.db.commit()

        return results

    async def preview_retention_enforcement(self) -> Dict[str, Dict]:
        """Preview what data would be affected by retention enforcement. Non-destructive."""
        now = datetime.now(timezone.utc)
        preview = {}

        tables = [
            ("soc2_audit_log", "timestamp", RETENTION_PERIODS[RetentionPolicy.AUDIT_LOGS]),
            ("soc2_access_event", "timestamp", RETENTION_PERIODS[RetentionPolicy.ACCESS_LOGS]),
        ]

        for table, ts_col, days in tables:
            cutoff = now - timedelta(days=days)
            result = await self.db.execute(
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

        return preview

    async def get_retention_status(self) -> Dict[str, Dict]:
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
            try:
                result = await self.db.execute(
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
