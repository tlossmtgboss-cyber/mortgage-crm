"""
Calendar Audit Service — Comprehensive Compliance-Grade Audit Logging

Provides structured audit trail for all calendar/scheduler operations,
designed for mortgage industry compliance requirements.

Features:
- Automatic change detection (compute_changes)
- Actor attribution (user, system, AI agent, webhook, public)
- Severity classification (info, warning, critical)
- Suspicious activity detection (mass cancellations, off-hours access, etc.)
- Entity history retrieval with pagination
- User activity timeline

Usage:
    from services.calendar_audit_service import CalendarAuditService

    # Log an event
    await CalendarAuditService.log(
        db=db,
        event_type="appointment.created",
        entity_type="appointment",
        entity_id=str(appointment.id),
        actor_id=str(user.id),
        actor_type="user",
        organization_id=org_id,
        changes={"title": {"old": None, "new": "Discovery Call"}},
        request=request,
    )

    # Get entity history
    history = await CalendarAuditService.get_entity_history(
        db, entity_type="appointment", entity_id="42", limit=50
    )
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Union

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, or_, text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

# Booking events
EVENT_APPOINTMENT_CREATED = "appointment.created"
EVENT_APPOINTMENT_UPDATED = "appointment.updated"
EVENT_APPOINTMENT_CANCELLED = "appointment.cancelled"
EVENT_APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
EVENT_APPOINTMENT_CONFIRMED = "appointment.confirmed"
EVENT_APPOINTMENT_COMPLETED = "appointment.completed"
EVENT_APPOINTMENT_NO_SHOW = "appointment.no_show"
EVENT_APPOINTMENT_CHECKED_IN = "appointment.checked_in"

# Booking link events
EVENT_BOOKING_LINK_CREATED = "booking_link.created"
EVENT_BOOKING_LINK_UPDATED = "booking_link.updated"
EVENT_BOOKING_LINK_DELETED = "booking_link.deleted"
EVENT_BOOKING_LINK_ACCESSED = "booking_link.accessed"

# Blocked time events
EVENT_BLOCKED_TIME_CREATED = "blocked_time.created"
EVENT_BLOCKED_TIME_UPDATED = "blocked_time.updated"
EVENT_BLOCKED_TIME_DELETED = "blocked_time.deleted"

# Config / settings events
EVENT_CONFIG_CREATED = "config.created"
EVENT_CONFIG_UPDATED = "config.updated"

# Availability events
EVENT_AVAILABILITY_CREATED = "availability.created"
EVENT_AVAILABILITY_UPDATED = "availability.updated"
EVENT_AVAILABILITY_DELETED = "availability.deleted"

# Export events
EVENT_DATA_EXPORTED = "data.exported"

# Compliance events
EVENT_COMPLIANCE_ALERT = "compliance.alert"

# Category mappings
EVENT_CATEGORIES = {
    "appointment.created": "booking",
    "appointment.updated": "modification",
    "appointment.cancelled": "modification",
    "appointment.rescheduled": "modification",
    "appointment.confirmed": "booking",
    "appointment.completed": "booking",
    "appointment.no_show": "booking",
    "appointment.checked_in": "booking",
    "booking_link.created": "settings",
    "booking_link.updated": "settings",
    "booking_link.deleted": "settings",
    "booking_link.accessed": "access",
    "blocked_time.created": "settings",
    "blocked_time.updated": "settings",
    "blocked_time.deleted": "settings",
    "config.created": "settings",
    "config.updated": "settings",
    "availability.created": "settings",
    "availability.updated": "settings",
    "availability.deleted": "settings",
    "data.exported": "export",
    "compliance.alert": "compliance",
}

# Events that warrant elevated severity
WARNING_EVENTS = frozenset({
    "appointment.no_show",
    "appointment.rescheduled",
})
CRITICAL_EVENTS = frozenset({
    "compliance.alert",
})

# Suspicious activity thresholds
MASS_CANCELLATION_THRESHOLD = 5  # cancellations within window
MASS_CANCELLATION_WINDOW_HOURS = 1
OFF_HOURS_START = 22  # 10 PM
OFF_HOURS_END = 6  # 6 AM


class CalendarAuditService:
    """Service for comprehensive calendar audit logging and compliance queries."""

    # Reference to model class — set via init() to avoid circular imports
    _CalendarAuditLog = None

    @classmethod
    def init(cls, calendar_audit_log_model):
        """Initialize with the CalendarAuditLog model class.

        Called once during app startup after models are created.
        """
        cls._CalendarAuditLog = calendar_audit_log_model

    @classmethod
    def _get_model(cls):
        """Get the CalendarAuditLog model, raising if not initialized."""
        if cls._CalendarAuditLog is None:
            raise RuntimeError(
                "CalendarAuditService not initialized. Call CalendarAuditService.init(model) first."
            )
        return cls._CalendarAuditLog

    # ------------------------------------------------------------------
    # Core logging
    # ------------------------------------------------------------------

    @staticmethod
    async def log(
        db: Session,
        event_type: str,
        entity_type: str,
        entity_id: Optional[str],
        actor_id: Optional[str],
        organization_id: int,
        actor_type: str = "user",
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        request=None,
        severity: Optional[str] = None,
        event_category: Optional[str] = None,
    ) -> Optional[int]:
        """Create an audit log entry.

        Args:
            db: SQLAlchemy session.
            event_type: Dotted event name, e.g. "appointment.created".
            entity_type: Type of entity affected.
            entity_id: ID of the entity (as string).
            actor_id: ID of the actor (user ID, "system", "ai", etc.).
            organization_id: Tenant organization ID.
            actor_type: One of "user", "system", "ai_agent", "webhook", "public".
            changes: Dict of field changes: {"field": {"old": x, "new": y}}.
            metadata: Additional context dict.
            request: FastAPI/Starlette Request for IP/UA extraction.
            severity: Override severity ("info", "warning", "critical").
            event_category: Override category.

        Returns:
            The ID of the created audit log entry, or None on failure.
        """
        CalendarAuditLog = CalendarAuditService._get_model()

        # Auto-determine severity if not provided
        if severity is None:
            if event_type in CRITICAL_EVENTS:
                severity = "critical"
            elif event_type in WARNING_EVENTS:
                severity = "warning"
            else:
                severity = "info"

        # Auto-determine category if not provided
        if event_category is None:
            event_category = EVENT_CATEGORIES.get(event_type, "other")

        # Extract request context
        actor_ip = None
        actor_user_agent = None
        if request:
            try:
                actor_ip = request.client.host if request.client else None
            except Exception:
                pass
            try:
                actor_user_agent = str(request.headers.get("user-agent", ""))[:500]
            except Exception:
                pass

        try:
            entry = CalendarAuditLog(
                organization_id=organization_id,
                event_type=event_type,
                event_category=event_category,
                severity=severity,
                actor_id=str(actor_id) if actor_id is not None else None,
                actor_type=actor_type,
                actor_ip=actor_ip,
                actor_user_agent=actor_user_agent,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                changes=changes,
                extra_metadata=metadata,
            )
            db.add(entry)
            # Do NOT commit — let the caller's transaction include this
            db.flush()
            return entry.id
        except Exception as e:
            logger.warning(f"Failed to write calendar audit log: {e}")
            return None

    # ------------------------------------------------------------------
    # Convenience: log with legacy _audit_log signature
    # ------------------------------------------------------------------

    @staticmethod
    async def log_legacy(
        db: Session,
        org_id: int,
        user_id: int,
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        changes: Optional[dict] = None,
        request=None,
    ) -> Optional[int]:
        """Bridge method matching the existing _audit_log() signature.

        Maps the legacy (action, entity_type) to the new (event_type, entity_type) format
        and writes to the CalendarAuditLog table.
        """
        event_type = f"{entity_type}.{action}"
        return await CalendarAuditService.log(
            db=db,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            actor_id=str(user_id) if user_id else None,
            organization_id=org_id,
            actor_type="user",
            changes=changes,
            request=request,
        )

    # ------------------------------------------------------------------
    # Change tracking
    # ------------------------------------------------------------------

    @staticmethod
    def compute_changes(
        old_dict: Dict[str, Any],
        new_dict: Dict[str, Any],
        fields: Optional[Set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Compute diff between old and new state.

        Args:
            old_dict: Previous state as a dict.
            new_dict: New state as a dict.
            fields: Optional set of fields to check. If None, checks all keys.

        Returns:
            Dict of changed fields: {"field_name": {"old": x, "new": y}}
        """
        changes = {}
        check_fields = fields or (set(old_dict.keys()) | set(new_dict.keys()))
        for field in check_fields:
            old_val = old_dict.get(field)
            new_val = new_dict.get(field)
            # Normalize for comparison: convert datetimes to ISO strings
            old_cmp = _normalize_for_comparison(old_val)
            new_cmp = _normalize_for_comparison(new_val)
            if old_cmp != new_cmp:
                changes[field] = {
                    "old": _serialize_value(old_val),
                    "new": _serialize_value(new_val),
                }
        return changes

    @staticmethod
    def entity_to_dict(
        entity,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Convert a SQLAlchemy model instance to a dict for change tracking.

        Args:
            entity: SQLAlchemy model instance.
            fields: Optional list of field names to include.

        Returns:
            Dict representation of the entity.
        """
        if entity is None:
            return {}
        result = {}
        if fields:
            for f in fields:
                result[f] = getattr(entity, f, None)
        else:
            # Use __table__.columns for consistent column extraction
            try:
                for col in entity.__table__.columns:
                    result[col.name] = getattr(entity, col.name, None)
            except Exception:
                # Fallback: use __dict__ minus SQLAlchemy internals
                for k, v in entity.__dict__.items():
                    if not k.startswith("_"):
                        result[k] = v
        return result

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    @staticmethod
    async def get_entity_history(
        db: Session,
        entity_type: str,
        entity_id: str,
        organization_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get audit trail for a specific entity.

        Args:
            db: SQLAlchemy session.
            entity_type: Type of entity (e.g. "appointment").
            entity_id: ID of the entity.
            organization_id: Optional org filter for tenant isolation.
            limit: Max number of entries.
            offset: Pagination offset.

        Returns:
            List of audit log entries as dicts.
        """
        CalendarAuditLog = CalendarAuditService._get_model()

        filters = [
            CalendarAuditLog.entity_type == entity_type,
            CalendarAuditLog.entity_id == str(entity_id),
        ]
        if organization_id:
            filters.append(CalendarAuditLog.organization_id == organization_id)

        entries = (
            db.query(CalendarAuditLog)
            .filter(and_(*filters))
            .order_by(desc(CalendarAuditLog.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [_entry_to_dict(e) for e in entries]

    @staticmethod
    async def get_user_activity(
        db: Session,
        user_id: str,
        organization_id: Optional[int] = None,
        days: int = 30,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get all audit entries for a user within a time window.

        Args:
            db: SQLAlchemy session.
            user_id: User ID to query.
            organization_id: Optional org filter.
            days: Number of days to look back.
            limit: Max entries.
            offset: Pagination offset.

        Returns:
            List of audit log entries as dicts.
        """
        CalendarAuditLog = CalendarAuditService._get_model()

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        filters = [
            CalendarAuditLog.actor_id == str(user_id),
            CalendarAuditLog.created_at >= cutoff,
        ]
        if organization_id:
            filters.append(CalendarAuditLog.organization_id == organization_id)

        entries = (
            db.query(CalendarAuditLog)
            .filter(and_(*filters))
            .order_by(desc(CalendarAuditLog.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [_entry_to_dict(e) for e in entries]

    @staticmethod
    async def search_audit_logs(
        db: Session,
        organization_id: int,
        event_type: Optional[str] = None,
        event_category: Optional[str] = None,
        severity: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search audit logs with multiple filter criteria.

        Returns:
            Dict with "entries" list and "total" count.
        """
        CalendarAuditLog = CalendarAuditService._get_model()

        filters = [CalendarAuditLog.organization_id == organization_id]

        if event_type:
            filters.append(CalendarAuditLog.event_type == event_type)
        if event_category:
            filters.append(CalendarAuditLog.event_category == event_category)
        if severity:
            filters.append(CalendarAuditLog.severity == severity)
        if actor_id:
            filters.append(CalendarAuditLog.actor_id == str(actor_id))
        if actor_type:
            filters.append(CalendarAuditLog.actor_type == actor_type)
        if entity_type:
            filters.append(CalendarAuditLog.entity_type == entity_type)
        if entity_id:
            filters.append(CalendarAuditLog.entity_id == str(entity_id))
        if start_date:
            filters.append(CalendarAuditLog.created_at >= start_date)
        if end_date:
            filters.append(CalendarAuditLog.created_at <= end_date)

        base_query = db.query(CalendarAuditLog).filter(and_(*filters))

        total = base_query.count()
        entries = (
            base_query
            .order_by(desc(CalendarAuditLog.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "entries": [_entry_to_dict(e) for e in entries],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    async def get_suspicious_activity(
        db: Session,
        organization_id: int,
        days: int = 7,
    ) -> Dict[str, Any]:
        """Detect suspicious patterns in audit logs.

        Checks for:
        1. Mass cancellations (many cancellations by one actor in a short window)
        2. Off-hours access (operations during unusual hours)
        3. Unusual actor types (webhook/public doing sensitive operations)
        4. High severity event clusters

        Args:
            db: SQLAlchemy session.
            organization_id: Tenant org ID.
            days: Lookback window.

        Returns:
            Dict with categorized suspicious activity findings.
        """
        CalendarAuditLog = CalendarAuditService._get_model()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        findings = {
            "mass_cancellations": [],
            "off_hours_access": [],
            "unusual_actors": [],
            "critical_events": [],
            "summary": {
                "total_findings": 0,
                "period_days": days,
            },
        }

        # 1. Mass cancellations: actors with >= MASS_CANCELLATION_THRESHOLD cancellations
        try:
            cancel_counts = (
                db.query(
                    CalendarAuditLog.actor_id,
                    func.count(CalendarAuditLog.id).label("cancel_count"),
                )
                .filter(
                    CalendarAuditLog.organization_id == organization_id,
                    CalendarAuditLog.event_type == "appointment.cancelled",
                    CalendarAuditLog.created_at >= cutoff,
                )
                .group_by(CalendarAuditLog.actor_id)
                .having(func.count(CalendarAuditLog.id) >= MASS_CANCELLATION_THRESHOLD)
                .all()
            )
            for actor_id, count in cancel_counts:
                findings["mass_cancellations"].append({
                    "actor_id": actor_id,
                    "cancellation_count": count,
                    "period_days": days,
                    "threshold": MASS_CANCELLATION_THRESHOLD,
                })
        except Exception as e:
            logger.warning(f"Mass cancellation detection failed: {e}")

        # 2. Off-hours access
        try:
            off_hours_entries = (
                db.query(CalendarAuditLog)
                .filter(
                    CalendarAuditLog.organization_id == organization_id,
                    CalendarAuditLog.created_at >= cutoff,
                    CalendarAuditLog.event_category.in_(["booking", "modification", "settings"]),
                    or_(
                        func.extract("hour", CalendarAuditLog.created_at) >= OFF_HOURS_START,
                        func.extract("hour", CalendarAuditLog.created_at) < OFF_HOURS_END,
                    ),
                )
                .order_by(desc(CalendarAuditLog.created_at))
                .limit(20)
                .all()
            )
            for entry in off_hours_entries:
                findings["off_hours_access"].append({
                    "id": entry.id,
                    "event_type": entry.event_type,
                    "actor_id": entry.actor_id,
                    "actor_type": entry.actor_type,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "actor_ip": entry.actor_ip,
                })
        except Exception as e:
            logger.warning(f"Off-hours access detection failed: {e}")

        # 3. Unusual actor types performing sensitive operations
        try:
            unusual = (
                db.query(CalendarAuditLog)
                .filter(
                    CalendarAuditLog.organization_id == organization_id,
                    CalendarAuditLog.created_at >= cutoff,
                    CalendarAuditLog.actor_type.in_(["webhook", "public"]),
                    CalendarAuditLog.event_category.in_(["modification", "settings"]),
                )
                .order_by(desc(CalendarAuditLog.created_at))
                .limit(20)
                .all()
            )
            for entry in unusual:
                findings["unusual_actors"].append({
                    "id": entry.id,
                    "event_type": entry.event_type,
                    "actor_type": entry.actor_type,
                    "actor_ip": entry.actor_ip,
                    "entity_type": entry.entity_type,
                    "entity_id": entry.entity_id,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                })
        except Exception as e:
            logger.warning(f"Unusual actor detection failed: {e}")

        # 4. Critical events
        try:
            critical = (
                db.query(CalendarAuditLog)
                .filter(
                    CalendarAuditLog.organization_id == organization_id,
                    CalendarAuditLog.created_at >= cutoff,
                    CalendarAuditLog.severity == "critical",
                )
                .order_by(desc(CalendarAuditLog.created_at))
                .limit(20)
                .all()
            )
            for entry in critical:
                findings["critical_events"].append(_entry_to_dict(entry))
        except Exception as e:
            logger.warning(f"Critical event detection failed: {e}")

        findings["summary"]["total_findings"] = (
            len(findings["mass_cancellations"])
            + len(findings["off_hours_access"])
            + len(findings["unusual_actors"])
            + len(findings["critical_events"])
        )

        return findings

    # ------------------------------------------------------------------
    # Aggregate / stats
    # ------------------------------------------------------------------

    @staticmethod
    async def get_audit_stats(
        db: Session,
        organization_id: int,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get aggregate audit statistics for an organization.

        Returns:
            Dict with event counts by type, category, severity, and actor_type.
        """
        CalendarAuditLog = CalendarAuditService._get_model()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        base_filter = and_(
            CalendarAuditLog.organization_id == organization_id,
            CalendarAuditLog.created_at >= cutoff,
        )

        total = db.query(func.count(CalendarAuditLog.id)).filter(base_filter).scalar() or 0

        # By event type
        by_event_type = (
            db.query(
                CalendarAuditLog.event_type,
                func.count(CalendarAuditLog.id).label("count"),
            )
            .filter(base_filter)
            .group_by(CalendarAuditLog.event_type)
            .order_by(desc("count"))
            .all()
        )

        # By severity
        by_severity = (
            db.query(
                CalendarAuditLog.severity,
                func.count(CalendarAuditLog.id).label("count"),
            )
            .filter(base_filter)
            .group_by(CalendarAuditLog.severity)
            .all()
        )

        # By actor type
        by_actor_type = (
            db.query(
                CalendarAuditLog.actor_type,
                func.count(CalendarAuditLog.id).label("count"),
            )
            .filter(base_filter)
            .group_by(CalendarAuditLog.actor_type)
            .all()
        )

        return {
            "period_days": days,
            "total_entries": total,
            "by_event_type": {row[0]: row[1] for row in by_event_type},
            "by_severity": {row[0]: row[1] for row in by_severity},
            "by_actor_type": {row[0]: row[1] for row in by_actor_type},
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _entry_to_dict(entry) -> Dict[str, Any]:
    """Convert a CalendarAuditLog ORM instance to a JSON-safe dict."""
    return {
        "id": entry.id,
        "organization_id": entry.organization_id,
        "event_type": entry.event_type,
        "event_category": entry.event_category,
        "severity": entry.severity,
        "actor_id": entry.actor_id,
        "actor_type": entry.actor_type,
        "actor_ip": entry.actor_ip,
        "actor_user_agent": entry.actor_user_agent,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "changes": entry.changes,
        "metadata": entry.extra_metadata,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def _normalize_for_comparison(val: Any) -> Any:
    """Normalize a value for comparison purposes."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (list, dict)):
        return str(val)
    return val


def _serialize_value(val: Any) -> Any:
    """Make a value JSON-serializable."""
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (list, dict)):
        return val
    return str(val)
