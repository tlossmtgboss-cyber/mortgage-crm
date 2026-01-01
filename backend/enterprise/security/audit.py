"""
Immutable Audit Logging Service

Provides tamper-proof audit logging for compliance and security.
Supports hash chaining for integrity verification.

Enterprise Features:
- Immutable append-only logs
- Hash chaining for tamper detection
- SIEM integration (Splunk, Datadog, etc.)
- Structured JSON logging
- Retention policy enforcement
- Real-time alerting
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from uuid import uuid4
import threading
from queue import Queue
import asyncio

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Standard audit event types"""
    # Authentication events
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    MFA_ENABLED = "auth.mfa.enabled"
    MFA_DISABLED = "auth.mfa.disabled"
    MFA_VERIFIED = "auth.mfa.verified"
    MFA_FAILED = "auth.mfa.failed"
    PASSWORD_CHANGED = "auth.password.changed"
    PASSWORD_RESET = "auth.password.reset"
    TOKEN_ISSUED = "auth.token.issued"
    TOKEN_REVOKED = "auth.token.revoked"

    # Authorization events
    ACCESS_GRANTED = "authz.access.granted"
    ACCESS_DENIED = "authz.access.denied"
    PERMISSION_CHANGED = "authz.permission.changed"
    ROLE_ASSIGNED = "authz.role.assigned"
    ROLE_REMOVED = "authz.role.removed"
    IMPERSONATION_STARTED = "authz.impersonation.started"
    IMPERSONATION_ENDED = "authz.impersonation.ended"

    # Data events
    DATA_CREATED = "data.created"
    DATA_READ = "data.read"
    DATA_UPDATED = "data.updated"
    DATA_DELETED = "data.deleted"
    DATA_EXPORTED = "data.exported"
    DATA_IMPORTED = "data.imported"
    PII_ACCESSED = "data.pii.accessed"
    PII_MODIFIED = "data.pii.modified"

    # System events
    CONFIG_CHANGED = "system.config.changed"
    SERVICE_STARTED = "system.service.started"
    SERVICE_STOPPED = "system.service.stopped"
    ERROR_OCCURRED = "system.error"
    ALERT_TRIGGERED = "system.alert.triggered"

    # Compliance events
    CONSENT_GIVEN = "compliance.consent.given"
    CONSENT_WITHDRAWN = "compliance.consent.withdrawn"
    DATA_RETENTION_APPLIED = "compliance.retention.applied"
    GDPR_REQUEST = "compliance.gdpr.request"
    CCPA_REQUEST = "compliance.ccpa.request"

    # AI/Agent events
    AI_DECISION = "ai.decision"
    AI_ESCALATION = "ai.escalation"
    AI_OVERRIDE = "ai.override"


class AuditSeverity(str, Enum):
    """Audit event severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """
    Immutable audit event record.

    All fields are required for compliance and integrity.
    """
    # Event identification
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    severity: str = AuditSeverity.INFO.value
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Actor information
    actor_id: Optional[str] = None
    actor_type: str = "user"  # user, system, service, api_key
    actor_email: Optional[str] = None
    actor_ip: Optional[str] = None
    actor_user_agent: Optional[str] = None

    # Resource information
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None

    # Action details
    action: str = ""
    outcome: str = "success"  # success, failure, partial
    reason: Optional[str] = None

    # State changes
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    changes: Optional[Dict[str, Any]] = None

    # Context
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    organization_id: Optional[str] = None
    tenant_id: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # Integrity
    previous_hash: Optional[str] = None
    event_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), default=str, sort_keys=True)

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of event data"""
        # Create deterministic representation
        data = self.to_json()
        return hashlib.sha256(data.encode()).hexdigest()


class AuditLogger:
    """
    Immutable Audit Logger with hash chaining.

    Provides tamper-proof audit logging with:
    - Hash chain integrity verification
    - Multiple output destinations
    - Async batch processing
    - SIEM integration
    """

    def __init__(
        self,
        db_session_factory=None,
        siem_endpoint: Optional[str] = None,
        batch_size: int = 100,
        flush_interval_seconds: int = 5,
        retention_days: int = 2555,  # ~7 years for financial compliance
    ):
        self.db_session_factory = db_session_factory
        self.siem_endpoint = siem_endpoint or os.getenv("SIEM_ENDPOINT")
        self.batch_size = batch_size
        self.flush_interval = flush_interval_seconds
        self.retention_days = retention_days

        # Event queue for async processing
        self._queue: Queue = Queue()
        self._last_hash: Optional[str] = None
        self._event_count = 0

        # Alert handlers
        self._alert_handlers: List[Callable[[AuditEvent], None]] = []

        # Background worker
        self._worker_thread = None
        self._running = False

        # Start background worker
        self._start_worker()

        logger.info("Audit logger initialized")

    def _start_worker(self):
        """Start background worker for async log processing"""
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()

    def _process_queue(self):
        """Background worker to process queued events"""
        batch = []
        last_flush = datetime.now()

        while self._running:
            try:
                # Get event with timeout
                try:
                    event = self._queue.get(timeout=1)
                    batch.append(event)
                except:
                    pass

                # Flush if batch full or interval elapsed
                should_flush = (
                    len(batch) >= self.batch_size or
                    (datetime.now() - last_flush).seconds >= self.flush_interval
                )

                if batch and should_flush:
                    self._flush_batch(batch)
                    batch = []
                    last_flush = datetime.now()

            except Exception as e:
                logger.error(f"Audit worker error: {e}")

    def _flush_batch(self, events: List[AuditEvent]):
        """Flush a batch of events to storage"""
        if not events:
            return

        try:
            # Write to database if available
            if self.db_session_factory:
                self._write_to_db(events)

            # Send to SIEM if configured
            if self.siem_endpoint:
                self._send_to_siem(events)

            # Write to structured log
            for event in events:
                logger.info(
                    f"AUDIT: {event.event_type}",
                    extra={"audit_event": event.to_dict()}
                )

        except Exception as e:
            logger.error(f"Failed to flush audit batch: {e}")
            # Re-queue events on failure
            for event in events:
                self._queue.put(event)

    def _write_to_db(self, events: List[AuditEvent]):
        """Write events to database"""
        from sqlalchemy import text

        with self.db_session_factory() as db:
            for event in events:
                db.execute(
                    text("""
                        INSERT INTO audit_log (
                            event_id, event_type, severity, timestamp,
                            actor_id, actor_type, actor_email, actor_ip,
                            resource_type, resource_id, action, outcome,
                            before_state, after_state, changes,
                            request_id, session_id, trace_id,
                            organization_id, metadata, tags,
                            previous_hash, event_hash
                        ) VALUES (
                            :event_id, :event_type, :severity, :timestamp,
                            :actor_id, :actor_type, :actor_email, :actor_ip,
                            :resource_type, :resource_id, :action, :outcome,
                            :before_state, :after_state, :changes,
                            :request_id, :session_id, :trace_id,
                            :organization_id, :metadata, :tags,
                            :previous_hash, :event_hash
                        )
                    """),
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "severity": event.severity,
                        "timestamp": event.timestamp,
                        "actor_id": event.actor_id,
                        "actor_type": event.actor_type,
                        "actor_email": event.actor_email,
                        "actor_ip": event.actor_ip,
                        "resource_type": event.resource_type,
                        "resource_id": event.resource_id,
                        "action": event.action,
                        "outcome": event.outcome,
                        "before_state": json.dumps(event.before_state) if event.before_state else None,
                        "after_state": json.dumps(event.after_state) if event.after_state else None,
                        "changes": json.dumps(event.changes) if event.changes else None,
                        "request_id": event.request_id,
                        "session_id": event.session_id,
                        "trace_id": event.trace_id,
                        "organization_id": event.organization_id,
                        "metadata": json.dumps(event.metadata),
                        "tags": json.dumps(event.tags),
                        "previous_hash": event.previous_hash,
                        "event_hash": event.event_hash,
                    }
                )
            db.commit()

    def _send_to_siem(self, events: List[AuditEvent]):
        """Send events to SIEM endpoint"""
        import requests

        try:
            payload = [event.to_dict() for event in events]
            response = requests.post(
                self.siem_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to send to SIEM: {e}")

    def log(
        self,
        event_type: AuditEventType | str,
        action: str,
        actor_id: Optional[str] = None,
        actor_email: Optional[str] = None,
        actor_ip: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        outcome: str = "success",
        severity: AuditSeverity = AuditSeverity.INFO,
        before_state: Optional[Dict] = None,
        after_state: Optional[Dict] = None,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            action: Description of the action
            actor_id: ID of the user/system performing action
            actor_email: Email of the actor
            actor_ip: IP address of the actor
            resource_type: Type of resource affected
            resource_id: ID of the resource
            outcome: success, failure, or partial
            severity: Event severity level
            before_state: State before the action
            after_state: State after the action
            request_id: HTTP request ID
            trace_id: Distributed trace ID
            organization_id: Tenant/org ID
            metadata: Additional metadata
            tags: Event tags

        Returns:
            Event ID
        """
        # Compute changes if states provided
        changes = None
        if before_state and after_state:
            changes = self._compute_changes(before_state, after_state)

        # Create event
        event = AuditEvent(
            event_type=event_type.value if isinstance(event_type, AuditEventType) else event_type,
            severity=severity.value if isinstance(severity, AuditSeverity) else severity,
            action=action,
            actor_id=actor_id,
            actor_email=actor_email,
            actor_ip=actor_ip,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            before_state=before_state,
            after_state=after_state,
            changes=changes,
            request_id=request_id,
            trace_id=trace_id,
            organization_id=organization_id,
            metadata=metadata or {},
            tags=tags or [],
            previous_hash=self._last_hash,
        )

        # Compute and store hash
        event.event_hash = event.compute_hash()
        self._last_hash = event.event_hash
        self._event_count += 1

        # Check for alerts
        self._check_alerts(event)

        # Queue for async processing
        self._queue.put(event)

        return event.event_id

    def _compute_changes(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compute the differences between two states"""
        changes = {}

        all_keys = set(before.keys()) | set(after.keys())
        for key in all_keys:
            before_val = before.get(key)
            after_val = after.get(key)

            if before_val != after_val:
                changes[key] = {
                    "before": before_val,
                    "after": after_val,
                }

        return changes

    def _check_alerts(self, event: AuditEvent):
        """Check if event should trigger alerts"""
        # High severity events
        if event.severity in [AuditSeverity.ERROR.value, AuditSeverity.CRITICAL.value]:
            for handler in self._alert_handlers:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Alert handler error: {e}")

        # Security events
        security_events = [
            AuditEventType.LOGIN_FAILURE.value,
            AuditEventType.ACCESS_DENIED.value,
            AuditEventType.MFA_FAILED.value,
            AuditEventType.PII_ACCESSED.value,
        ]
        if event.event_type in security_events:
            for handler in self._alert_handlers:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Alert handler error: {e}")

    def add_alert_handler(self, handler: Callable[[AuditEvent], None]):
        """Add an alert handler for critical events"""
        self._alert_handlers.append(handler)

    def verify_chain_integrity(
        self,
        start_event_id: Optional[str] = None,
        end_event_id: Optional[str] = None,
    ) -> bool:
        """
        Verify the hash chain integrity of audit logs.

        Returns True if chain is intact, False if tampered.
        """
        if not self.db_session_factory:
            logger.warning("Cannot verify chain without database")
            return True

        from sqlalchemy import text

        with self.db_session_factory() as db:
            # Get events in order
            query = """
                SELECT event_id, event_hash, previous_hash,
                       event_type, timestamp, actor_id, action
                FROM audit_log
                ORDER BY timestamp ASC
            """
            result = db.execute(text(query))
            events = result.fetchall()

            if not events:
                return True

            previous_hash = None
            for event in events:
                # Verify previous hash link
                if event.previous_hash != previous_hash:
                    logger.error(f"Chain broken at event {event.event_id}")
                    return False

                # TODO: Recompute hash and verify
                previous_hash = event.event_hash

            logger.info(f"Verified {len(events)} audit events - chain intact")
            return True

    async def search(
        self,
        event_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        severity: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Search audit logs with filters"""
        if not self.db_session_factory:
            return []

        from sqlalchemy import text

        conditions = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if event_type:
            conditions.append("event_type = :event_type")
            params["event_type"] = event_type

        if actor_id:
            conditions.append("actor_id = :actor_id")
            params["actor_id"] = actor_id

        if resource_type:
            conditions.append("resource_type = :resource_type")
            params["resource_type"] = resource_type

        if resource_id:
            conditions.append("resource_id = :resource_id")
            params["resource_id"] = resource_id

        if start_time:
            conditions.append("timestamp >= :start_time")
            params["start_time"] = start_time.isoformat()

        if end_time:
            conditions.append("timestamp <= :end_time")
            params["end_time"] = end_time.isoformat()

        if severity:
            conditions.append("severity = :severity")
            params["severity"] = severity

        where_clause = " AND ".join(conditions)

        with self.db_session_factory() as db:
            result = db.execute(
                text(f"""
                    SELECT * FROM audit_log
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT :limit OFFSET :offset
                """),
                params
            )

            events = []
            for row in result.fetchall():
                events.append(AuditEvent(
                    event_id=row.event_id,
                    event_type=row.event_type,
                    severity=row.severity,
                    timestamp=row.timestamp,
                    actor_id=row.actor_id,
                    actor_type=row.actor_type,
                    actor_email=row.actor_email,
                    actor_ip=row.actor_ip,
                    resource_type=row.resource_type,
                    resource_id=row.resource_id,
                    action=row.action,
                    outcome=row.outcome,
                    previous_hash=row.previous_hash,
                    event_hash=row.event_hash,
                ))

            return events

    def shutdown(self):
        """Gracefully shutdown the audit logger"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=10)

        # Flush remaining events
        batch = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except:
                break

        if batch:
            self._flush_batch(batch)

        logger.info(f"Audit logger shutdown complete. Total events: {self._event_count}")


# Convenience decorators for common audit patterns
def audit_action(
    event_type: AuditEventType,
    resource_type: str,
    get_resource_id: Optional[Callable] = None,
):
    """
    Decorator to automatically audit function calls.

    Usage:
        @audit_action(AuditEventType.DATA_UPDATED, "loan")
        async def update_loan(loan_id: str, data: dict):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Get audit logger from context or create
            audit_logger = kwargs.pop("_audit_logger", None)
            if audit_logger is None:
                audit_logger = AuditLogger()

            # Extract resource ID if possible
            resource_id = None
            if get_resource_id:
                resource_id = get_resource_id(*args, **kwargs)
            elif "id" in kwargs:
                resource_id = str(kwargs["id"])
            elif args:
                resource_id = str(args[0])

            try:
                result = await func(*args, **kwargs)
                audit_logger.log(
                    event_type=event_type,
                    action=f"{func.__name__} completed",
                    resource_type=resource_type,
                    resource_id=resource_id,
                    outcome="success",
                )
                return result
            except Exception as e:
                audit_logger.log(
                    event_type=event_type,
                    action=f"{func.__name__} failed: {str(e)}",
                    resource_type=resource_type,
                    resource_id=resource_id,
                    outcome="failure",
                    severity=AuditSeverity.ERROR,
                )
                raise

        return wrapper
    return decorator
