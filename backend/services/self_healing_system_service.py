"""
Self-Healing System Service

Provides automatic error detection and recovery:
- Health monitoring for all components
- Automatic error detection and classification
- Self-healing actions for common issues
- Circuit breakers and fallback mechanisms
- Incident tracking and escalation
- Recovery playbooks
- Post-incident analysis
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import asyncio
from collections import deque
import traceback
import uuid

logger = logging.getLogger(__name__)


class ComponentType(str, Enum):
    """Types of system components."""
    API = "api"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    EXTERNAL_API = "external_api"
    AI_SERVICE = "ai_service"
    STORAGE = "storage"
    SCHEDULER = "scheduler"
    WEBSOCKET = "websocket"


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class IncidentSeverity(str, Enum):
    """Incident severity levels."""
    CRITICAL = "critical"  # System down
    HIGH = "high"          # Major feature broken
    MEDIUM = "medium"      # Minor feature impacted
    LOW = "low"            # No user impact
    INFO = "info"          # Informational


class IncidentStatus(str, Enum):
    """Incident status."""
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    HEALING = "healing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    MONITORING = "monitoring"


class HealingActionType(str, Enum):
    """Types of healing actions."""
    RESTART = "restart"
    RETRY = "retry"
    FAILOVER = "failover"
    SCALE = "scale"
    CLEAR_CACHE = "clear_cache"
    RECONNECT = "reconnect"
    RATE_LIMIT = "rate_limit"
    CIRCUIT_BREAK = "circuit_break"
    ROLLBACK = "rollback"
    NOTIFY = "notify"


@dataclass
class HealthCheck:
    """Health check result for a component."""
    component_id: str
    component_type: ComponentType
    status: HealthStatus
    message: str = ""

    # Metrics
    response_time_ms: float = 0.0
    error_rate: float = 0.0
    last_error: Optional[str] = None

    # Details
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Incident:
    """Represents a system incident."""
    id: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus

    # Affected components
    affected_components: List[str] = field(default_factory=list)

    # Error details
    error_type: str = ""
    error_message: str = ""
    stack_trace: str = ""

    # Tracking
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    # Healing
    healing_attempts: int = 0
    healing_actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    auto_healed: bool = False

    # Escalation
    escalated_to: Optional[str] = None
    escalated_at: Optional[datetime] = None

    # Resolution
    resolution: str = ""
    root_cause: str = ""


@dataclass
class HealingAction:
    """A healing action to be taken."""
    id: str
    action_type: HealingActionType
    target_component: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Status
    status: str = "pending"  # pending, executing, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CircuitBreaker:
    """Circuit breaker for a component."""
    component_id: str
    state: str = "closed"  # closed, open, half-open
    failure_count: int = 0
    success_count: int = 0
    last_failure_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    half_open_at: Optional[datetime] = None

    # Configuration
    failure_threshold: int = 5
    recovery_timeout_seconds: int = 60
    success_threshold: int = 3


@dataclass
class HealingPlaybook:
    """Playbook for healing specific issues."""
    id: str
    name: str
    description: str

    # Trigger conditions
    trigger_error_types: List[str] = field(default_factory=list)
    trigger_component_types: List[ComponentType] = field(default_factory=list)

    # Actions
    actions: List[Dict[str, Any]] = field(default_factory=list)

    # Settings
    max_retries: int = 3
    retry_delay_seconds: int = 10
    escalate_on_failure: bool = True


class SelfHealingSystemService:
    """
    Self-healing system for automatic error detection and recovery.

    Features:
    - Continuous health monitoring
    - Automatic error classification
    - Self-healing with configurable playbooks
    - Circuit breakers for failing components
    - Incident tracking and management
    - Escalation and notification
    - Post-incident analysis
    """

    def __init__(self, db_session=None):
        self.db = db_session

        # Component registry
        self._components: Dict[str, Dict[str, Any]] = {}

        # Health checks
        self._health_history: Dict[str, deque] = {}  # component_id -> recent health checks
        self._health_check_interval_seconds = 30

        # Incidents
        self._active_incidents: Dict[str, Incident] = {}
        self._resolved_incidents: List[Incident] = []

        # Circuit breakers
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Healing playbooks
        self._playbooks: Dict[str, HealingPlaybook] = {}

        # Healing handlers
        self._healing_handlers: Dict[HealingActionType, Callable] = {}

        # Error patterns (for classification)
        self._error_patterns: Dict[str, Dict[str, Any]] = {}

        # Metrics
        self._metrics = {
            "total_incidents": 0,
            "auto_healed": 0,
            "escalated": 0,
            "mean_time_to_detect": 0.0,
            "mean_time_to_heal": 0.0
        }

        # Initialize default playbooks and handlers
        self._initialize_defaults()

        logger.info("SelfHealingSystemService initialized")

    def _initialize_defaults(self):
        """Initialize default playbooks and handlers."""
        # Register default healing handlers
        self.register_healing_handler(HealingActionType.RETRY, self._handler_retry)
        self.register_healing_handler(HealingActionType.RESTART, self._handler_restart)
        self.register_healing_handler(HealingActionType.CLEAR_CACHE, self._handler_clear_cache)
        self.register_healing_handler(HealingActionType.RECONNECT, self._handler_reconnect)
        self.register_healing_handler(HealingActionType.CIRCUIT_BREAK, self._handler_circuit_break)
        self.register_healing_handler(HealingActionType.RATE_LIMIT, self._handler_rate_limit)
        self.register_healing_handler(HealingActionType.NOTIFY, self._handler_notify)

        # Default playbooks
        self._playbooks["db_connection_failure"] = HealingPlaybook(
            id="db_connection_failure",
            name="Database Connection Failure",
            description="Handle database connection failures",
            trigger_error_types=["ConnectionError", "OperationalError", "TimeoutError"],
            trigger_component_types=[ComponentType.DATABASE],
            actions=[
                {"type": "retry", "params": {"max_attempts": 3, "delay": 2}},
                {"type": "reconnect", "params": {}},
                {"type": "circuit_break", "params": {"duration": 30}}
            ],
            max_retries=3,
            escalate_on_failure=True
        )

        self._playbooks["api_rate_limit"] = HealingPlaybook(
            id="api_rate_limit",
            name="API Rate Limit Exceeded",
            description="Handle rate limiting from external APIs",
            trigger_error_types=["RateLimitError", "TooManyRequests"],
            trigger_component_types=[ComponentType.EXTERNAL_API],
            actions=[
                {"type": "rate_limit", "params": {"reduce_by": 50}},
                {"type": "retry", "params": {"delay": 60}}
            ],
            max_retries=5
        )

        self._playbooks["cache_failure"] = HealingPlaybook(
            id="cache_failure",
            name="Cache Failure",
            description="Handle cache failures",
            trigger_error_types=["CacheError", "ConnectionRefusedError"],
            trigger_component_types=[ComponentType.CACHE],
            actions=[
                {"type": "reconnect", "params": {}},
                {"type": "clear_cache", "params": {"pattern": "*"}},
                {"type": "circuit_break", "params": {"duration": 60}}
            ]
        )

        self._playbooks["ai_service_failure"] = HealingPlaybook(
            id="ai_service_failure",
            name="AI Service Failure",
            description="Handle AI service failures",
            trigger_error_types=["APIError", "ServiceUnavailable"],
            trigger_component_types=[ComponentType.AI_SERVICE],
            actions=[
                {"type": "retry", "params": {"max_attempts": 2, "delay": 5}},
                {"type": "failover", "params": {"fallback": "secondary_ai"}},
                {"type": "notify", "params": {"channel": "ops"}}
            ],
            escalate_on_failure=True
        )

    # =========================================================================
    # Component Registration
    # =========================================================================

    def register_component(
        self,
        component_id: str,
        component_type: ComponentType,
        name: str,
        health_check_fn: Callable = None,
        critical: bool = False,
        dependencies: List[str] = None
    ):
        """Register a component for health monitoring."""
        self._components[component_id] = {
            "id": component_id,
            "type": component_type,
            "name": name,
            "health_check_fn": health_check_fn,
            "critical": critical,
            "dependencies": dependencies or [],
            "registered_at": datetime.now(timezone.utc)
        }

        self._health_history[component_id] = deque(maxlen=100)
        self._circuit_breakers[component_id] = CircuitBreaker(component_id=component_id)

        logger.info(f"Registered component: {component_id} ({component_type.value})")

    def unregister_component(self, component_id: str):
        """Unregister a component."""
        if component_id in self._components:
            del self._components[component_id]
            if component_id in self._health_history:
                del self._health_history[component_id]
            if component_id in self._circuit_breakers:
                del self._circuit_breakers[component_id]
            logger.info(f"Unregistered component: {component_id}")

    # =========================================================================
    # Health Monitoring
    # =========================================================================

    async def check_health(self, component_id: str = None) -> Dict[str, HealthCheck]:
        """Check health of component(s)."""
        results = {}

        components = (
            {component_id: self._components[component_id]}
            if component_id and component_id in self._components
            else self._components
        )

        for cid, component in components.items():
            try:
                health = await self._perform_health_check(cid, component)
                results[cid] = health
                self._health_history[cid].append(health)

                # Check for incidents
                if health.status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
                    await self._handle_unhealthy_component(cid, health)

            except Exception as e:
                health = HealthCheck(
                    component_id=cid,
                    component_type=component["type"],
                    status=HealthStatus.UNKNOWN,
                    message=f"Health check failed: {str(e)}",
                    last_error=str(e)
                )
                results[cid] = health

        return results

    async def _perform_health_check(
        self,
        component_id: str,
        component: Dict[str, Any]
    ) -> HealthCheck:
        """Perform health check for a component."""
        start_time = datetime.now(timezone.utc)

        # Check circuit breaker
        cb = self._circuit_breakers.get(component_id)
        if cb and cb.state == "open":
            # Check if ready to try again
            if cb.opened_at:
                elapsed = (datetime.now(timezone.utc) - cb.opened_at).total_seconds()
                if elapsed >= cb.recovery_timeout_seconds:
                    cb.state = "half-open"
                    cb.half_open_at = datetime.now(timezone.utc)
                else:
                    return HealthCheck(
                        component_id=component_id,
                        component_type=component["type"],
                        status=HealthStatus.UNHEALTHY,
                        message="Circuit breaker open"
                    )

        try:
            # Execute health check function if provided
            if component.get("health_check_fn"):
                result = await component["health_check_fn"]()
                status = HealthStatus.HEALTHY if result.get("healthy", True) else HealthStatus.DEGRADED
                message = result.get("message", "")
                details = result.get("details", {})
            else:
                # Default health check (component exists)
                status = HealthStatus.HEALTHY
                message = "Component registered"
                details = {}

            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            # Update circuit breaker on success
            if cb and cb.state == "half-open":
                cb.success_count += 1
                if cb.success_count >= cb.success_threshold:
                    cb.state = "closed"
                    cb.failure_count = 0
                    cb.success_count = 0

            return HealthCheck(
                component_id=component_id,
                component_type=component["type"],
                status=status,
                message=message,
                response_time_ms=response_time,
                details=details
            )

        except Exception as e:
            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            # Update circuit breaker on failure
            if cb:
                cb.failure_count += 1
                cb.last_failure_at = datetime.now(timezone.utc)
                if cb.failure_count >= cb.failure_threshold:
                    cb.state = "open"
                    cb.opened_at = datetime.now(timezone.utc)

            return HealthCheck(
                component_id=component_id,
                component_type=component["type"],
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                response_time_ms=response_time,
                last_error=str(e)
            )

    async def _handle_unhealthy_component(
        self,
        component_id: str,
        health: HealthCheck
    ):
        """Handle an unhealthy component."""
        # Check if incident already exists
        existing_incident = self._find_incident_for_component(component_id)
        if existing_incident:
            return  # Already being handled

        # Create incident
        await self.report_error(
            component_id=component_id,
            error_type="HealthCheckFailure",
            error_message=health.message,
            details=health.details
        )

    def _find_incident_for_component(self, component_id: str) -> Optional[Incident]:
        """Find active incident for a component."""
        for incident in self._active_incidents.values():
            if component_id in incident.affected_components:
                return incident
        return None

    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
        component_statuses = {}
        overall_status = HealthStatus.HEALTHY

        for cid, history in self._health_history.items():
            if history:
                latest = history[-1]
                component_statuses[cid] = {
                    "status": latest.status.value,
                    "message": latest.message,
                    "last_checked": latest.checked_at.isoformat()
                }

                if latest.status == HealthStatus.CRITICAL:
                    overall_status = HealthStatus.CRITICAL
                elif latest.status == HealthStatus.UNHEALTHY and overall_status != HealthStatus.CRITICAL:
                    overall_status = HealthStatus.UNHEALTHY
                elif latest.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED

        return {
            "overall_status": overall_status.value,
            "components": component_statuses,
            "active_incidents": len(self._active_incidents),
            "circuit_breakers_open": len([
                cb for cb in self._circuit_breakers.values()
                if cb.state == "open"
            ]),
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    # =========================================================================
    # Error Handling & Incidents
    # =========================================================================

    async def report_error(
        self,
        component_id: str,
        error_type: str,
        error_message: str,
        stack_trace: str = "",
        details: Dict[str, Any] = None,
        severity: IncidentSeverity = None
    ) -> Incident:
        """Report an error and create an incident."""
        # Classify severity if not provided
        if severity is None:
            severity = self._classify_severity(component_id, error_type, error_message)

        incident_id = f"inc_{uuid.uuid4().hex[:12]}"

        component = self._components.get(component_id, {})
        component_type = component.get("type", ComponentType.API)

        incident = Incident(
            id=incident_id,
            title=f"{component_type.value} error: {error_type}",
            description=error_message,
            severity=severity,
            status=IncidentStatus.DETECTED,
            affected_components=[component_id],
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace
        )

        self._active_incidents[incident_id] = incident
        self._metrics["total_incidents"] += 1

        logger.warning(f"Incident created: {incident_id} - {error_type}")

        # Attempt auto-healing
        asyncio.create_task(self._attempt_healing(incident))

        return incident

    def _classify_severity(
        self,
        component_id: str,
        error_type: str,
        error_message: str
    ) -> IncidentSeverity:
        """Classify incident severity based on error details."""
        component = self._components.get(component_id, {})

        # Critical components get higher severity
        if component.get("critical", False):
            return IncidentSeverity.CRITICAL

        # Pattern-based classification
        critical_patterns = ["OutOfMemory", "DiskFull", "SystemCrash", "DataCorruption"]
        high_patterns = ["ConnectionError", "AuthenticationError", "DatabaseError"]
        medium_patterns = ["TimeoutError", "RateLimitError", "ValidationError"]

        error_lower = error_type.lower()

        if any(p.lower() in error_lower for p in critical_patterns):
            return IncidentSeverity.CRITICAL
        if any(p.lower() in error_lower for p in high_patterns):
            return IncidentSeverity.HIGH
        if any(p.lower() in error_lower for p in medium_patterns):
            return IncidentSeverity.MEDIUM

        return IncidentSeverity.LOW

    async def _attempt_healing(self, incident: Incident):
        """Attempt to automatically heal an incident."""
        incident.status = IncidentStatus.HEALING

        # Find applicable playbook
        playbook = self._find_playbook(incident)

        if not playbook:
            logger.info(f"No playbook found for incident: {incident.id}")
            incident.status = IncidentStatus.ESCALATED
            await self._escalate_incident(incident, "No healing playbook available")
            return

        logger.info(f"Applying playbook '{playbook.name}' to incident {incident.id}")

        # Execute playbook actions
        for action_config in playbook.actions:
            action_type = HealingActionType(action_config["type"])
            params = action_config.get("params", {})

            for component_id in incident.affected_components:
                action = HealingAction(
                    id=f"heal_{uuid.uuid4().hex[:8]}",
                    action_type=action_type,
                    target_component=component_id,
                    parameters=params
                )

                success = await self._execute_healing_action(action)

                incident.healing_actions_taken.append({
                    "action_id": action.id,
                    "action_type": action_type.value,
                    "success": success,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

                if success:
                    # Verify health
                    health_result = await self.check_health(component_id)
                    health = health_result.get(component_id)

                    if health and health.status == HealthStatus.HEALTHY:
                        incident.status = IncidentStatus.RESOLVED
                        incident.resolved_at = datetime.now(timezone.utc)
                        incident.auto_healed = True
                        incident.resolution = f"Auto-healed using {playbook.name}"

                        self._metrics["auto_healed"] += 1

                        # Move to resolved
                        self._resolved_incidents.append(incident)
                        if incident.id in self._active_incidents:
                            del self._active_incidents[incident.id]

                        logger.info(f"Incident {incident.id} auto-healed")
                        return

            incident.healing_attempts += 1

            if incident.healing_attempts >= playbook.max_retries:
                break

            # Wait before next attempt
            await asyncio.sleep(playbook.retry_delay_seconds)

        # Healing failed, escalate
        if playbook.escalate_on_failure:
            incident.status = IncidentStatus.ESCALATED
            await self._escalate_incident(incident, "Auto-healing failed")
            self._metrics["escalated"] += 1
        else:
            incident.status = IncidentStatus.MONITORING

    def _find_playbook(self, incident: Incident) -> Optional[HealingPlaybook]:
        """Find applicable playbook for an incident."""
        for playbook in self._playbooks.values():
            # Check error type match
            if playbook.trigger_error_types:
                if not any(
                    et.lower() in incident.error_type.lower()
                    for et in playbook.trigger_error_types
                ):
                    continue

            # Check component type match
            if playbook.trigger_component_types:
                component = self._components.get(incident.affected_components[0], {})
                component_type = component.get("type")
                if component_type not in playbook.trigger_component_types:
                    continue

            return playbook

        return None

    async def _execute_healing_action(self, action: HealingAction) -> bool:
        """Execute a healing action."""
        action.status = "executing"
        action.started_at = datetime.now(timezone.utc)

        handler = self._healing_handlers.get(action.action_type)
        if not handler:
            action.status = "failed"
            action.error = f"No handler for action type: {action.action_type}"
            return False

        try:
            result = await handler(action.target_component, action.parameters)
            action.status = "completed"
            action.completed_at = datetime.now(timezone.utc)
            action.result = str(result)
            return result.get("success", False) if isinstance(result, dict) else bool(result)

        except Exception as e:
            action.status = "failed"
            action.error = str(e)
            action.completed_at = datetime.now(timezone.utc)
            logger.error(f"Healing action failed: {action.id} - {e}")
            return False

    async def _escalate_incident(self, incident: Incident, reason: str):
        """Escalate an incident for human intervention."""
        incident.escalated_at = datetime.now(timezone.utc)
        incident.escalated_to = "on_call"

        # Would send notification here
        logger.warning(f"Incident {incident.id} escalated: {reason}")

    # =========================================================================
    # Healing Handlers
    # =========================================================================

    def register_healing_handler(
        self,
        action_type: HealingActionType,
        handler: Callable
    ):
        """Register a healing action handler."""
        self._healing_handlers[action_type] = handler

    async def _handler_retry(
        self,
        component_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Retry handler - wait and retry."""
        delay = params.get("delay", 5)
        await asyncio.sleep(delay)
        return {"success": True, "action": "retry", "delay": delay}

    async def _handler_restart(
        self,
        component_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Restart handler - would restart component."""
        # In production, would actually restart the component
        logger.info(f"Simulating restart of {component_id}")
        return {"success": True, "action": "restart", "component": component_id}

    async def _handler_clear_cache(
        self,
        component_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Clear cache handler."""
        pattern = params.get("pattern", "*")
        logger.info(f"Clearing cache for {component_id}, pattern: {pattern}")
        return {"success": True, "action": "clear_cache", "pattern": pattern}

    async def _handler_reconnect(
        self,
        component_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reconnect handler - attempt to reconnect."""
        logger.info(f"Attempting reconnection for {component_id}")
        return {"success": True, "action": "reconnect", "component": component_id}

    async def _handler_circuit_break(
        self,
        component_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Circuit break handler."""
        duration = params.get("duration", 60)
        cb = self._circuit_breakers.get(component_id)
        if cb:
            cb.state = "open"
            cb.opened_at = datetime.now(timezone.utc)
            cb.recovery_timeout_seconds = duration

        return {"success": True, "action": "circuit_break", "duration": duration}

    async def _handler_rate_limit(
        self,
        component_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Rate limit handler - reduce rate."""
        reduce_by = params.get("reduce_by", 50)
        logger.info(f"Reducing rate for {component_id} by {reduce_by}%")
        return {"success": True, "action": "rate_limit", "reduced_by": reduce_by}

    async def _handler_notify(
        self,
        component_id: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Notification handler."""
        channel = params.get("channel", "default")
        logger.info(f"Sending notification for {component_id} to {channel}")
        return {"success": True, "action": "notify", "channel": channel}

    # =========================================================================
    # Playbook Management
    # =========================================================================

    def add_playbook(self, playbook: HealingPlaybook):
        """Add a healing playbook."""
        self._playbooks[playbook.id] = playbook
        logger.info(f"Added playbook: {playbook.id}")

    def remove_playbook(self, playbook_id: str) -> bool:
        """Remove a playbook."""
        if playbook_id in self._playbooks:
            del self._playbooks[playbook_id]
            return True
        return False

    def get_playbook(self, playbook_id: str) -> Optional[HealingPlaybook]:
        """Get a playbook by ID."""
        return self._playbooks.get(playbook_id)

    def list_playbooks(self) -> List[Dict[str, Any]]:
        """List all playbooks."""
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "trigger_errors": p.trigger_error_types,
                "actions": len(p.actions)
            }
            for p in self._playbooks.values()
        ]

    # =========================================================================
    # Incident Management
    # =========================================================================

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Get incident by ID."""
        return (
            self._active_incidents.get(incident_id) or
            next((i for i in self._resolved_incidents if i.id == incident_id), None)
        )

    def get_active_incidents(self) -> List[Incident]:
        """Get all active incidents."""
        return list(self._active_incidents.values())

    def acknowledge_incident(self, incident_id: str) -> bool:
        """Acknowledge an incident."""
        incident = self._active_incidents.get(incident_id)
        if incident:
            incident.acknowledged_at = datetime.now(timezone.utc)
            incident.status = IncidentStatus.INVESTIGATING
            return True
        return False

    def resolve_incident(
        self,
        incident_id: str,
        resolution: str,
        root_cause: str = ""
    ) -> bool:
        """Manually resolve an incident."""
        incident = self._active_incidents.get(incident_id)
        if incident:
            incident.status = IncidentStatus.RESOLVED
            incident.resolved_at = datetime.now(timezone.utc)
            incident.resolution = resolution
            incident.root_cause = root_cause

            self._resolved_incidents.append(incident)
            del self._active_incidents[incident_id]

            logger.info(f"Incident {incident_id} manually resolved")
            return True
        return False

    # =========================================================================
    # Circuit Breaker Management
    # =========================================================================

    def get_circuit_breaker_status(self, component_id: str) -> Optional[Dict[str, Any]]:
        """Get circuit breaker status for a component."""
        cb = self._circuit_breakers.get(component_id)
        if not cb:
            return None

        return {
            "component_id": component_id,
            "state": cb.state,
            "failure_count": cb.failure_count,
            "failure_threshold": cb.failure_threshold,
            "last_failure": cb.last_failure_at.isoformat() if cb.last_failure_at else None,
            "opened_at": cb.opened_at.isoformat() if cb.opened_at else None,
            "recovery_timeout": cb.recovery_timeout_seconds
        }

    def reset_circuit_breaker(self, component_id: str) -> bool:
        """Manually reset a circuit breaker."""
        cb = self._circuit_breakers.get(component_id)
        if cb:
            cb.state = "closed"
            cb.failure_count = 0
            cb.success_count = 0
            cb.opened_at = None
            cb.half_open_at = None
            logger.info(f"Circuit breaker reset: {component_id}")
            return True
        return False

    # =========================================================================
    # Analytics & Reporting
    # =========================================================================

    def get_healing_metrics(self) -> Dict[str, Any]:
        """Get self-healing metrics."""
        resolved = self._resolved_incidents

        # Calculate MTTD (Mean Time To Detect) - assuming detection is instant here
        mttd = 0

        # Calculate MTTH (Mean Time To Heal)
        heal_times = []
        for incident in resolved:
            if incident.detected_at and incident.resolved_at:
                heal_time = (incident.resolved_at - incident.detected_at).total_seconds()
                heal_times.append(heal_time)

        mtth = sum(heal_times) / len(heal_times) if heal_times else 0

        return {
            "total_incidents": self._metrics["total_incidents"],
            "active_incidents": len(self._active_incidents),
            "resolved_incidents": len(resolved),
            "auto_healed": self._metrics["auto_healed"],
            "auto_heal_rate": (
                self._metrics["auto_healed"] / len(resolved) * 100
                if resolved else 0
            ),
            "escalated": self._metrics["escalated"],
            "mean_time_to_heal_seconds": round(mtth, 2),
            "circuit_breakers_open": len([
                cb for cb in self._circuit_breakers.values()
                if cb.state == "open"
            ])
        }

    def get_incident_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get incident summary for the past N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        recent = [
            i for i in self._resolved_incidents
            if i.detected_at >= cutoff
        ] + [
            i for i in self._active_incidents.values()
            if i.detected_at >= cutoff
        ]

        by_severity = {}
        by_component = {}
        by_type = {}

        for incident in recent:
            # By severity
            sev = incident.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            # By component
            for comp in incident.affected_components:
                by_component[comp] = by_component.get(comp, 0) + 1

            # By error type
            by_type[incident.error_type] = by_type.get(incident.error_type, 0) + 1

        return {
            "period_days": days,
            "total_incidents": len(recent),
            "by_severity": by_severity,
            "by_component": by_component,
            "by_error_type": by_type,
            "most_affected_component": max(by_component.items(), key=lambda x: x[1])[0] if by_component else None,
            "most_common_error": max(by_type.items(), key=lambda x: x[1])[0] if by_type else None
        }

    async def run_health_check_loop(self):
        """Run continuous health checking loop."""
        while True:
            try:
                await self.check_health()
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
            await asyncio.sleep(self._health_check_interval_seconds)
