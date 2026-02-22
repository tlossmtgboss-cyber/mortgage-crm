"""
Incident Service — Security incident response workflow.
SOC 2 Criteria: CC7 (System Operations), CC2 (Communication)

Manages the full lifecycle of security incidents: creation, investigation,
containment, resolution, and post-mortem documentation.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import IncidentStatus, IncidentCategory, SeverityLevel

logger = logging.getLogger("soc2.incidents")


class IncidentService:
    """
    Security incident management.
    
    Usage:
        incidents = IncidentService(db)
        
        incident_id = await incidents.create(
            title="Unauthorized API access detected",
            description="Multiple failed auth attempts from IP 1.2.3.4",
            category=IncidentCategory.UNAUTHORIZED_ACCESS,
            severity=SeverityLevel.HIGH,
            reported_by=admin_user_id,
        )
        
        await incidents.update_status(incident_id, IncidentStatus.INVESTIGATING, admin_user_id)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        title: str,
        description: str,
        category: str,
        severity: str,
        reported_by: Optional[UUID] = None,
        assigned_to: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        affected_systems: Optional[List[str]] = None,
        detected_at: Optional[datetime] = None,
    ) -> UUID:
        """Create a new security incident."""
        incident_id = uuid4()
        now = datetime.now(timezone.utc)

        await self.db.execute(
            text("""
                INSERT INTO soc2_security_incident (
                    id, created_at, updated_at, title, description,
                    category, severity, status, reported_by, assigned_to,
                    tenant_id, affected_systems, detected_at
                ) VALUES (
                    :id, :now, :now, :title, :description,
                    :category, :severity, :status, :reported_by, :assigned_to,
                    :tenant_id, :affected_systems, :detected_at
                )
            """),
            {
                "id": str(incident_id),
                "now": now,
                "title": title,
                "description": description,
                "category": category,
                "severity": severity,
                "status": IncidentStatus.OPEN,
                "reported_by": str(reported_by) if reported_by else None,
                "assigned_to": str(assigned_to) if assigned_to else None,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "affected_systems": affected_systems,
                "detected_at": detected_at or now,
            }
        )

        # Add timeline entry
        await self._add_timeline(
            incident_id=incident_id,
            action="incident_created",
            actor_id=reported_by,
            description=f"Incident created: {title}",
        )

        await self.db.commit()

        logger.warning(
            "security_incident_created",
            extra={
                "incident_id": str(incident_id),
                "title": title,
                "category": category,
                "severity": severity,
            }
        )

        return incident_id

    async def update_status(
        self,
        incident_id: UUID,
        new_status: str,
        actor_id: Optional[UUID] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Update incident status with timeline tracking."""
        # Get current status
        result = await self.db.execute(
            text("SELECT status FROM soc2_security_incident WHERE id = :id"),
            {"id": str(incident_id)}
        )
        row = result.fetchone()
        if not row:
            return False

        old_status = row[0]
        now = datetime.now(timezone.utc)

        # Update timestamp fields based on status
        timestamp_updates = ""
        if new_status == IncidentStatus.CONTAINED:
            timestamp_updates = ", contained_at = :now"
        elif new_status == IncidentStatus.RESOLVED:
            timestamp_updates = ", resolved_at = :now"
        elif new_status == IncidentStatus.CLOSED:
            timestamp_updates = ", closed_at = :now"

        await self.db.execute(
            text(f"""
                UPDATE soc2_security_incident
                SET status = :new_status, updated_at = :now {timestamp_updates}
                WHERE id = :id
            """),
            {"id": str(incident_id), "new_status": new_status, "now": now}
        )

        await self._add_timeline(
            incident_id=incident_id,
            action="status_change",
            actor_id=actor_id,
            description=notes or f"Status changed from {old_status} to {new_status}",
            old_value=old_status,
            new_value=new_status,
        )

        await self.db.commit()
        return True

    async def add_note(
        self,
        incident_id: UUID,
        note: str,
        actor_id: Optional[UUID] = None,
    ) -> None:
        """Add a note to an incident's timeline."""
        await self._add_timeline(
            incident_id=incident_id,
            action="note_added",
            actor_id=actor_id,
            description=note,
        )
        await self.db.commit()

    async def set_root_cause(
        self,
        incident_id: UUID,
        root_cause: str,
        remediation_steps: str,
        preventive_measures: str,
        actor_id: Optional[UUID] = None,
    ) -> None:
        """Record root cause analysis and remediation."""
        await self.db.execute(
            text("""
                UPDATE soc2_security_incident
                SET root_cause = :root_cause,
                    remediation_steps = :remediation_steps,
                    preventive_measures = :preventive_measures,
                    updated_at = :now
                WHERE id = :id
            """),
            {
                "id": str(incident_id),
                "root_cause": root_cause,
                "remediation_steps": remediation_steps,
                "preventive_measures": preventive_measures,
                "now": datetime.now(timezone.utc),
            }
        )

        await self._add_timeline(
            incident_id=incident_id,
            action="root_cause_documented",
            actor_id=actor_id,
            description="Root cause analysis and remediation plan documented",
        )
        await self.db.commit()

    async def get_incident(self, incident_id: UUID) -> Optional[Dict]:
        """Get full incident details with timeline."""
        result = await self.db.execute(
            text("SELECT * FROM soc2_security_incident WHERE id = :id"),
            {"id": str(incident_id)}
        )
        incident = result.fetchone()
        if not incident:
            return None

        timeline_result = await self.db.execute(
            text("""
                SELECT * FROM soc2_incident_timeline
                WHERE incident_id = :id ORDER BY timestamp ASC
            """),
            {"id": str(incident_id)}
        )

        return {
            "incident": dict(incident._mapping),
            "timeline": [dict(row._mapping) for row in timeline_result.fetchall()],
        }

    async def list_incidents(
        self,
        tenant_id: Optional[UUID] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """List incidents with filters."""
        conditions = []
        params = {"limit": limit}

        if tenant_id:
            conditions.append("tenant_id = :tenant_id")
            params["tenant_id"] = str(tenant_id)
        if status:
            conditions.append("status = :status")
            params["status"] = status
        if severity:
            conditions.append("severity = :severity")
            params["severity"] = severity
        if start_time:
            conditions.append("created_at >= :start_time")
            params["start_time"] = start_time
        if end_time:
            conditions.append("created_at <= :end_time")
            params["end_time"] = end_time

        where = " AND ".join(conditions) if conditions else "TRUE"

        result = await self.db.execute(
            text(f"""
                SELECT id, created_at, title, category, severity, status,
                       affected_users, data_compromised, pii_involved
                FROM soc2_security_incident
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            params
        )
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_incident_metrics(
        self,
        tenant_id: UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """Generate incident metrics for compliance reporting."""
        result = await self.db.execute(
            text("""
                SELECT
                    COUNT(*) as total_incidents,
                    COUNT(*) FILTER (WHERE severity = 'critical') as critical_incidents,
                    COUNT(*) FILTER (WHERE severity = 'high') as high_incidents,
                    COUNT(*) FILTER (WHERE data_compromised = TRUE) as data_breaches,
                    COUNT(*) FILTER (WHERE pii_involved = TRUE) as pii_incidents,
                    COUNT(*) FILTER (WHERE status = 'closed') as closed_incidents,
                    AVG(EXTRACT(EPOCH FROM (contained_at - detected_at))/3600)
                        FILTER (WHERE contained_at IS NOT NULL) as avg_containment_hours,
                    AVG(EXTRACT(EPOCH FROM (resolved_at - detected_at))/3600)
                        FILTER (WHERE resolved_at IS NOT NULL) as avg_resolution_hours
                FROM soc2_security_incident
                WHERE tenant_id = :tenant_id
                  AND created_at BETWEEN :start_time AND :end_time
            """),
            {
                "tenant_id": str(tenant_id),
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        row = result.fetchone()
        return dict(row._mapping) if row else {}

    async def _add_timeline(
        self,
        incident_id: UUID,
        action: str,
        description: str,
        actor_id: Optional[UUID] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        is_automated: bool = False,
    ) -> None:
        """Add a timeline entry to an incident."""
        await self.db.execute(
            text("""
                INSERT INTO soc2_incident_timeline (
                    incident_id, timestamp, action, actor_id,
                    description, old_value, new_value, is_automated
                ) VALUES (
                    :incident_id, :timestamp, :action, :actor_id,
                    :description, :old_value, :new_value, :is_automated
                )
            """),
            {
                "incident_id": str(incident_id),
                "timestamp": datetime.now(timezone.utc),
                "action": action,
                "actor_id": str(actor_id) if actor_id else None,
                "description": description,
                "old_value": old_value,
                "new_value": new_value,
                "is_automated": is_automated,
            }
        )
