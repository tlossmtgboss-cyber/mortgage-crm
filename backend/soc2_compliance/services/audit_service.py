"""
Audit Service — Core audit trail logging.
SOC 2 Criteria: CC2 (Communication), CC4 (Monitoring), PI1 (Processing Integrity)

This service provides the primary interface for recording audit events throughout
the Perennia AI platform. Every significant action — data access, modifications,
authentication events, and system operations — should be logged through this service.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..constants import AuditAction, SeverityLevel, DataClassification, PII_FIELDS

logger = logging.getLogger("soc2.audit")


class AuditService:
    """
    Central audit logging service.

    Usage:
        audit = AuditService(db_session)
        audit.log(
            action=AuditAction.UPDATE,
            resource_type="loan_application",
            resource_id="LA-12345",
            description="Updated loan amount",
            user_id=current_user.id,
            old_values={"loan_amount": 250000},
            new_values={"loan_amount": 275000}
        )
    """

    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        description: Optional[str] = None,
        user_id: Optional[UUID] = None,
        user_email: Optional[str] = None,
        user_role: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        fields_accessed: Optional[List[str]] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        request_id: Optional[UUID] = None,
        session_id: Optional[str] = None,
        status_code: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        severity: str = SeverityLevel.LOW,
        data_classification: str = DataClassification.INTERNAL,
    ) -> Optional[int]:
        """
        Record an audit log entry.

        Returns the ID of the created audit log entry.
        """
        # Auto-detect PII involvement
        contains_pii = self._check_pii_involvement(
            fields_accessed, old_values, new_values
        )

        # Sanitize PII from stored values
        sanitized_old = self._sanitize_values(old_values) if old_values else None
        sanitized_new = self._sanitize_values(new_values) if new_values else None

        # Auto-escalate severity for PII access
        if contains_pii and severity == SeverityLevel.LOW:
            severity = SeverityLevel.MEDIUM

        try:
            result = self.db.execute(
                text("""
                    INSERT INTO soc2_audit_log (
                        timestamp, user_id, user_email, user_role, tenant_id,
                        action, resource_type, resource_id, description,
                        fields_accessed, old_values, new_values,
                        ip_address, user_agent, request_method, request_path,
                        request_id, session_id, status_code, success,
                        error_message, severity, data_classification, contains_pii
                    ) VALUES (
                        :timestamp, :user_id, :user_email, :user_role, :tenant_id,
                        :action, :resource_type, :resource_id, :description,
                        :fields_accessed, :old_values::jsonb, :new_values::jsonb,
                        :ip_address::inet, :user_agent, :request_method, :request_path,
                        :request_id, :session_id, :status_code, :success,
                        :error_message, :severity, :data_classification, :contains_pii
                    ) RETURNING id
                """),
                {
                    "timestamp": datetime.now(timezone.utc),
                    "user_id": str(user_id) if user_id else None,
                    "user_email": user_email,
                    "user_role": user_role,
                    "tenant_id": str(tenant_id) if tenant_id else None,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": str(resource_id) if resource_id else None,
                    "description": description,
                    "fields_accessed": fields_accessed,
                    "old_values": json.dumps(sanitized_old) if sanitized_old else None,
                    "new_values": json.dumps(sanitized_new) if sanitized_new else None,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "request_method": request_method,
                    "request_path": request_path,
                    "request_id": str(request_id) if request_id else str(uuid4()),
                    "session_id": session_id,
                    "status_code": status_code,
                    "success": success,
                    "error_message": error_message,
                    "severity": severity,
                    "data_classification": data_classification,
                    "contains_pii": contains_pii,
                }
            )
            # Flush to write the row without committing — let the caller manage the transaction.
            # The audit middleware's background thread commits its own session separately.
            self.db.flush()
            row = result.fetchone()
            log_id = row[0] if row else None
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            return None

        # Also emit structured log for SIEM integration
        logger.info(
            "audit_event",
            extra={
                "audit_id": log_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "user_id": str(user_id) if user_id else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "severity": severity,
                "success": success,
                "contains_pii": contains_pii,
                "ip_address": ip_address,
            }
        )

        # DataDog metrics forwarding (best-effort, never blocks)
        try:
            from datadog import statsd
            tags = [
                f"action:{action}",
                f"severity:{severity}",
                f"success:{success}",
                f"contains_pii:{contains_pii}",
            ]
            if resource_type:
                tags.append(f"resource_type:{resource_type}")
            statsd.increment("soc2.audit_events", tags=tags)

            if severity in (SeverityLevel.HIGH, SeverityLevel.CRITICAL):
                statsd.event(
                    title=f"SOC2 High-Severity Audit Event: {action}",
                    text=description or f"{action} on {resource_type}/{resource_id}",
                    alert_type="warning" if severity == SeverityLevel.HIGH else "error",
                    tags=tags,
                )
        except Exception as _exc:  # noqa: BLE001
            pass  # DataDog unavailable — non-blocking

        return log_id

    def log_data_access(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: str,
        action: str = AuditAction.READ,
        fields_accessed: Optional[List[str]] = None,
        tenant_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[int]:
        """Convenience method for logging data access events."""
        return self.log(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=f"{action} on {resource_type}/{resource_id}",
            user_id=user_id,
            tenant_id=tenant_id,
            fields_accessed=fields_accessed,
            ip_address=ip_address,
            data_classification=(
                DataClassification.RESTRICTED
                if fields_accessed and any(f in PII_FIELDS for f in fields_accessed)
                else DataClassification.CONFIDENTIAL
            ),
        )

    def log_data_modification(
        self,
        user_id: UUID,
        resource_type: str,
        resource_id: str,
        action: str,
        old_values: Optional[Dict] = None,
        new_values: Optional[Dict] = None,
        description: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[int]:
        """Convenience method for logging data modifications with before/after values."""
        fields = list(set(
            list(old_values.keys() if old_values else []) +
            list(new_values.keys() if new_values else [])
        ))
        return self.log(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description or f"{action} on {resource_type}/{resource_id}",
            user_id=user_id,
            tenant_id=tenant_id,
            fields_accessed=fields,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            severity=SeverityLevel.MEDIUM if action == AuditAction.DELETE else SeverityLevel.LOW,
        )

    def query_logs(
        self,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        severity: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Query audit logs with filters. Used for compliance reporting and investigation."""
        conditions = []
        params: Dict[str, Any] = {"limit": limit, "offset": offset}

        if tenant_id:
            conditions.append("tenant_id = :tenant_id")
            params["tenant_id"] = str(tenant_id)
        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = str(user_id)
        if action:
            conditions.append("action = :action")
            params["action"] = action
        if resource_type:
            conditions.append("resource_type = :resource_type")
            params["resource_type"] = resource_type
        if resource_id:
            conditions.append("resource_id = :resource_id")
            params["resource_id"] = resource_id
        if severity:
            conditions.append("severity = :severity")
            params["severity"] = severity
        if start_time:
            conditions.append("timestamp >= :start_time")
            params["start_time"] = start_time
        if end_time:
            conditions.append("timestamp <= :end_time")
            params["end_time"] = end_time

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        result = self.db.execute(
            text(f"""
                SELECT id, timestamp, user_id, user_email, action,
                       resource_type, resource_id, description,
                       ip_address, status_code, success, severity, contains_pii
                FROM soc2_audit_log
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT :limit OFFSET :offset
            """),
            params
        )

        return [dict(row._mapping) for row in result.fetchall()]

    def get_audit_summary(
        self,
        tenant_id: UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """Generate audit summary for compliance reporting."""
        result = self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_events,
                    COUNT(*) FILTER (WHERE success = FALSE) as failed_events,
                    COUNT(*) FILTER (WHERE contains_pii = TRUE) as pii_access_events,
                    COUNT(*) FILTER (WHERE severity IN ('high', 'critical')) as high_severity_events,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(DISTINCT resource_type) as resource_types_accessed
                FROM soc2_audit_log
                WHERE tenant_id = :tenant_id
                  AND timestamp BETWEEN :start_time AND :end_time
            """),
            {
                "tenant_id": str(tenant_id),
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        row = result.fetchone()
        return dict(row._mapping) if row else {}

    def _check_pii_involvement(
        self,
        fields_accessed: Optional[List[str]],
        old_values: Optional[Dict],
        new_values: Optional[Dict],
    ) -> bool:
        """Check if any PII fields are involved in this operation."""
        all_fields: set = set()
        if fields_accessed:
            all_fields.update(fields_accessed)
        if old_values:
            all_fields.update(old_values.keys())
        if new_values:
            all_fields.update(new_values.keys())
        # Normalize to lowercase for case-insensitive matching against PII_FIELDS
        all_fields = {f.lower() for f in all_fields}
        return bool(all_fields & PII_FIELDS)

    def _sanitize_values(self, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Redact PII values before storing in audit log.
        We log THAT a field was changed, but not the actual PII value.
        Full redaction — no partial values leaked.
        """
        sanitized = {}
        for key, value in values.items():
            if key.lower() in PII_FIELDS:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value
        return sanitized
