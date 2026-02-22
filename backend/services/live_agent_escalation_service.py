"""
Live Agent Escalation Network Service
Manages seamless AI → human handoff with intelligent routing
Supports integration with external agent networks (Smith.ai model)
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class EscalationReason(str, Enum):
    """Reasons for escalating to a live agent"""
    CALLER_REQUEST = "caller_request"
    SENTIMENT_THRESHOLD = "sentiment_threshold"
    COMPLEXITY_THRESHOLD = "complexity_threshold"
    REPEATED_FAILURES = "repeated_failures"
    VIP_CALLER = "vip_caller"
    SENSITIVE_TOPIC = "sensitive_topic"
    COMPLIANCE_REQUIRED = "compliance_required"
    TIME_EXCEEDED = "time_exceeded"
    LANGUAGE_BARRIER = "language_barrier"
    TECHNICAL_ISSUE = "technical_issue"


class AgentStatus(str, Enum):
    """Live agent availability status"""
    AVAILABLE = "available"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"
    IN_CALL = "in_call"


class EscalationStatus(str, Enum):
    """Status of an escalation request"""
    PENDING = "pending"
    ROUTING = "routing"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    CALLBACK_SCHEDULED = "callback_scheduled"


@dataclass
class LiveAgent:
    """Represents a live agent in the network"""
    id: str
    name: str
    email: str
    phone: str
    status: AgentStatus = AgentStatus.OFFLINE
    skills: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=lambda: ["en"])
    max_concurrent_calls: int = 1
    current_calls: int = 0
    priority: int = 1  # Higher = preferred
    avg_handle_time_seconds: int = 300
    satisfaction_rating: float = 4.5
    organization_id: Optional[int] = None
    external_agent_id: Optional[str] = None  # For external networks
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EscalationRequest:
    """Request to escalate a call to a live agent"""
    id: str
    call_id: str
    caller_phone: str
    caller_name: Optional[str] = None
    reason: EscalationReason = EscalationReason.CALLER_REQUEST
    priority: int = 1  # 1=normal, 2=high, 3=urgent
    status: EscalationStatus = EscalationStatus.PENDING
    context: Dict[str, Any] = field(default_factory=dict)
    required_skills: List[str] = field(default_factory=list)
    preferred_language: str = "en"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_agent_id: Optional[str] = None
    connected_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    resolution: Optional[str] = None
    caller_satisfaction: Optional[float] = None


@dataclass
class EscalationTrigger:
    """Configurable trigger for automatic escalation"""
    id: str
    name: str
    trigger_type: str  # sentiment, keyword, time, failure_count, etc.
    condition: Dict[str, Any]
    action: EscalationReason
    priority: int = 1
    enabled: bool = True
    organization_id: Optional[int] = None


@dataclass
class HandoffContext:
    """Context passed to live agent during handoff"""
    call_id: str
    caller_phone: str
    caller_name: Optional[str]
    conversation_summary: str
    key_points: List[str]
    caller_intent: str
    sentiment_history: List[Dict]
    previous_interactions: int
    escalation_reason: str
    ai_recommendations: List[str]
    relevant_data: Dict[str, Any]


class LiveAgentEscalationService:
    """
    Service for managing live agent escalation network

    Features:
    - Intelligent agent routing based on skills and availability
    - Seamless AI → human handoff with full context
    - Support for external agent networks (Smith.ai, etc.)
    - Configurable escalation triggers
    - Real-time agent status tracking
    - Callback scheduling when agents unavailable
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self._agents: Dict[str, LiveAgent] = {}
        self._escalations: Dict[str, EscalationRequest] = {}
        self._triggers: Dict[str, EscalationTrigger] = {}
        self._callback_queue: List[Dict] = []

        # Default escalation triggers
        self._initialize_default_triggers()

    def _initialize_default_triggers(self):
        """Set up default escalation triggers"""
        default_triggers = [
            EscalationTrigger(
                id="TRG-001",
                name="Low Sentiment",
                trigger_type="sentiment",
                condition={"threshold": 0.3, "consecutive_messages": 2},
                action=EscalationReason.SENTIMENT_THRESHOLD,
                priority=2
            ),
            EscalationTrigger(
                id="TRG-002",
                name="Explicit Request",
                trigger_type="keyword",
                condition={"keywords": ["speak to human", "real person", "talk to someone", "agent", "representative"]},
                action=EscalationReason.CALLER_REQUEST,
                priority=3
            ),
            EscalationTrigger(
                id="TRG-003",
                name="Long Call Duration",
                trigger_type="time",
                condition={"max_duration_seconds": 600},
                action=EscalationReason.TIME_EXCEEDED,
                priority=1
            ),
            EscalationTrigger(
                id="TRG-004",
                name="Repeated Misunderstanding",
                trigger_type="failure_count",
                condition={"max_failures": 3},
                action=EscalationReason.REPEATED_FAILURES,
                priority=2
            ),
            EscalationTrigger(
                id="TRG-005",
                name="Compliance Topics",
                trigger_type="keyword",
                condition={"keywords": ["lawyer", "lawsuit", "discrimination", "complaint", "regulatory"]},
                action=EscalationReason.COMPLIANCE_REQUIRED,
                priority=3
            )
        ]

        for trigger in default_triggers:
            self._triggers[trigger.id] = trigger

    def register_agent(
        self,
        agent_id: str,
        name: str,
        email: str,
        phone: str,
        skills: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        organization_id: Optional[int] = None,
        external_agent_id: Optional[str] = None
    ) -> LiveAgent:
        """
        Register a live agent in the network

        Args:
            agent_id: Unique agent identifier
            name: Agent's name
            email: Agent's email
            phone: Agent's phone number
            skills: List of skills (e.g., ["mortgage", "refinance", "spanish"])
            languages: Languages spoken
            organization_id: Organization the agent belongs to
            external_agent_id: ID in external system (Smith.ai, etc.)

        Returns:
            Registered LiveAgent
        """
        agent = LiveAgent(
            id=agent_id,
            name=name,
            email=email,
            phone=phone,
            skills=skills or ["general"],
            languages=languages or ["en"],
            organization_id=organization_id,
            external_agent_id=external_agent_id,
            status=AgentStatus.OFFLINE
        )

        self._agents[agent_id] = agent

        if self.db:
            self._persist_agent(agent)

        logger.info(f"Registered agent: {name} ({agent_id})")
        return agent

    def update_agent_status(
        self,
        agent_id: str,
        status: AgentStatus
    ) -> bool:
        """Update an agent's availability status"""
        if agent_id not in self._agents:
            return False

        agent = self._agents[agent_id]
        agent.status = status
        agent.last_activity = datetime.now(timezone.utc)

        logger.debug(f"Agent {agent_id} status: {status.value}")
        return True

    def check_escalation_triggers(
        self,
        call_id: str,
        message: str,
        sentiment_score: float,
        call_duration_seconds: int,
        failure_count: int,
        context: Optional[Dict] = None
    ) -> Optional[EscalationReason]:
        """
        Check if any escalation triggers are activated

        Args:
            call_id: Current call ID
            message: Latest message content
            sentiment_score: Current sentiment (0-1)
            call_duration_seconds: Total call duration
            failure_count: Number of AI failures in call
            context: Additional context

        Returns:
            EscalationReason if triggered, None otherwise
        """
        triggered_reasons = []

        for trigger in self._triggers.values():
            if not trigger.enabled:
                continue

            triggered = False

            if trigger.trigger_type == "sentiment":
                threshold = trigger.condition.get("threshold", 0.3)
                if sentiment_score < threshold:
                    triggered = True

            elif trigger.trigger_type == "keyword":
                keywords = trigger.condition.get("keywords", [])
                message_lower = message.lower()
                if any(kw in message_lower for kw in keywords):
                    triggered = True

            elif trigger.trigger_type == "time":
                max_duration = trigger.condition.get("max_duration_seconds", 600)
                if call_duration_seconds > max_duration:
                    triggered = True

            elif trigger.trigger_type == "failure_count":
                max_failures = trigger.condition.get("max_failures", 3)
                if failure_count >= max_failures:
                    triggered = True

            if triggered:
                triggered_reasons.append((trigger.priority, trigger.action))

        if triggered_reasons:
            # Return highest priority reason
            triggered_reasons.sort(key=lambda x: x[0], reverse=True)
            return triggered_reasons[0][1]

        return None

    async def request_escalation(
        self,
        call_id: str,
        caller_phone: str,
        reason: EscalationReason,
        caller_name: Optional[str] = None,
        context: Optional[Dict] = None,
        required_skills: Optional[List[str]] = None,
        preferred_language: str = "en",
        priority: int = 1
    ) -> EscalationRequest:
        """
        Request escalation to a live agent

        Args:
            call_id: Current call ID
            caller_phone: Caller's phone number
            reason: Reason for escalation
            caller_name: Caller's name if known
            context: Call context for handoff
            required_skills: Skills needed for this call
            preferred_language: Caller's preferred language
            priority: 1=normal, 2=high, 3=urgent

        Returns:
            EscalationRequest with status
        """
        import uuid
        escalation_id = f"ESC-{str(uuid.uuid4())[:8].upper()}"

        request = EscalationRequest(
            id=escalation_id,
            call_id=call_id,
            caller_phone=caller_phone,
            caller_name=caller_name,
            reason=reason,
            priority=priority,
            context=context or {},
            required_skills=required_skills or [],
            preferred_language=preferred_language
        )

        self._escalations[escalation_id] = request

        logger.info(f"Escalation requested: {escalation_id} - Reason: {reason.value}")

        # Try to find an available agent
        agent = await self._find_best_agent(request)

        if agent:
            request.status = EscalationStatus.ROUTING
            request.assigned_agent_id = agent.id
            await self._initiate_handoff(request, agent)
        else:
            # No agent available - offer callback
            request.status = EscalationStatus.CALLBACK_SCHEDULED
            self._schedule_callback(request)

        return request

    async def _find_best_agent(
        self,
        request: EscalationRequest
    ) -> Optional[LiveAgent]:
        """Find the best available agent for the escalation"""
        available_agents = [
            agent for agent in self._agents.values()
            if agent.status == AgentStatus.AVAILABLE
            and agent.current_calls < agent.max_concurrent_calls
        ]

        if not available_agents:
            return None

        # Score agents based on match criteria
        scored_agents = []
        for agent in available_agents:
            score = 0

            # Language match (highest priority)
            if request.preferred_language in agent.languages:
                score += 100

            # Skills match
            if request.required_skills:
                skill_match = len(set(request.required_skills) & set(agent.skills))
                score += skill_match * 20

            # Agent priority
            score += agent.priority * 10

            # Satisfaction rating
            score += agent.satisfaction_rating * 5

            # Prefer agents with fewer current calls
            score -= agent.current_calls * 15

            scored_agents.append((score, agent))

        if scored_agents:
            scored_agents.sort(key=lambda x: x[0], reverse=True)
            return scored_agents[0][1]

        return None

    async def _initiate_handoff(
        self,
        request: EscalationRequest,
        agent: LiveAgent
    ):
        """Initiate the handoff to a live agent"""
        request.status = EscalationStatus.CONNECTING
        agent.status = AgentStatus.IN_CALL
        agent.current_calls += 1

        # Prepare handoff context
        handoff_context = self._prepare_handoff_context(request)

        # In production, this would:
        # 1. Notify the agent via their preferred channel
        # 2. Transfer the call via Telnyx
        # 3. Send context to agent's interface

        logger.info(
            f"Initiating handoff: {request.id} -> Agent {agent.name}"
        )

        # Simulate connection (would be webhook-based in production)
        request.status = EscalationStatus.CONNECTED
        request.connected_at = datetime.now(timezone.utc)

    def _prepare_handoff_context(
        self,
        request: EscalationRequest
    ) -> HandoffContext:
        """Prepare context for the live agent"""
        context = request.context

        return HandoffContext(
            call_id=request.call_id,
            caller_phone=request.caller_phone,
            caller_name=request.caller_name,
            conversation_summary=context.get("summary", "No summary available"),
            key_points=context.get("key_points", []),
            caller_intent=context.get("intent", "Unknown"),
            sentiment_history=context.get("sentiment_history", []),
            previous_interactions=context.get("previous_interactions", 0),
            escalation_reason=request.reason.value,
            ai_recommendations=context.get("recommendations", []),
            relevant_data=context.get("relevant_data", {})
        )

    def _schedule_callback(self, request: EscalationRequest):
        """Schedule a callback when no agents are available"""
        callback = {
            "escalation_id": request.id,
            "caller_phone": request.caller_phone,
            "caller_name": request.caller_name,
            "scheduled_for": datetime.now(timezone.utc) + timedelta(minutes=30),
            "priority": request.priority,
            "context": request.context
        }

        self._callback_queue.append(callback)
        self._callback_queue.sort(key=lambda x: (x["priority"], x["scheduled_for"]), reverse=True)

        logger.info(f"Callback scheduled for escalation: {request.id}")

    def complete_escalation(
        self,
        escalation_id: str,
        resolution: str,
        caller_satisfaction: Optional[float] = None
    ) -> bool:
        """
        Mark an escalation as completed

        Args:
            escalation_id: Escalation ID
            resolution: Resolution description
            caller_satisfaction: Caller satisfaction score (1-5)

        Returns:
            Success status
        """
        if escalation_id not in self._escalations:
            return False

        request = self._escalations[escalation_id]
        request.status = EscalationStatus.COMPLETED
        request.completed_at = datetime.now(timezone.utc)
        request.resolution = resolution
        request.caller_satisfaction = caller_satisfaction

        # Free up the agent
        if request.assigned_agent_id and request.assigned_agent_id in self._agents:
            agent = self._agents[request.assigned_agent_id]
            agent.current_calls = max(0, agent.current_calls - 1)
            if agent.current_calls == 0:
                agent.status = AgentStatus.AVAILABLE

        logger.info(f"Escalation completed: {escalation_id}")
        return True

    def get_escalation_status(self, escalation_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of an escalation"""
        if escalation_id not in self._escalations:
            return None

        request = self._escalations[escalation_id]
        agent = self._agents.get(request.assigned_agent_id) if request.assigned_agent_id else None

        return {
            "escalation_id": request.id,
            "call_id": request.call_id,
            "status": request.status.value,
            "reason": request.reason.value,
            "priority": request.priority,
            "created_at": request.created_at.isoformat(),
            "assigned_agent": {
                "id": agent.id,
                "name": agent.name
            } if agent else None,
            "connected_at": request.connected_at.isoformat() if request.connected_at else None,
            "wait_time_seconds": (
                (request.connected_at - request.created_at).total_seconds()
                if request.connected_at else
                (datetime.now(timezone.utc) - request.created_at).total_seconds()
            )
        }

    def get_agent_dashboard(self) -> Dict[str, Any]:
        """Get real-time agent network dashboard"""
        agents = list(self._agents.values())

        by_status = {}
        for status in AgentStatus:
            by_status[status.value] = len([a for a in agents if a.status == status])

        active_escalations = [
            e for e in self._escalations.values()
            if e.status in [EscalationStatus.PENDING, EscalationStatus.ROUTING, EscalationStatus.CONNECTING, EscalationStatus.CONNECTED]
        ]

        pending_callbacks = [c for c in self._callback_queue]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_agents": len(agents),
            "agents_by_status": by_status,
            "available_capacity": sum(
                a.max_concurrent_calls - a.current_calls
                for a in agents if a.status == AgentStatus.AVAILABLE
            ),
            "active_escalations": len(active_escalations),
            "pending_escalations": len([e for e in active_escalations if e.status == EscalationStatus.PENDING]),
            "connected_calls": len([e for e in active_escalations if e.status == EscalationStatus.CONNECTED]),
            "pending_callbacks": len(pending_callbacks),
            "avg_wait_time_seconds": self._calculate_avg_wait_time(),
            "escalation_reasons": self._get_escalation_reason_breakdown()
        }

    def get_escalation_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get escalation metrics for reporting"""
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        escalations = [
            e for e in self._escalations.values()
            if start_date <= e.created_at <= end_date
        ]

        if not escalations:
            return {
                "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "total_escalations": 0
            }

        completed = [e for e in escalations if e.status == EscalationStatus.COMPLETED]
        failed = [e for e in escalations if e.status == EscalationStatus.FAILED]
        abandoned = [e for e in escalations if e.status == EscalationStatus.ABANDONED]

        # Calculate average wait time
        wait_times = []
        for e in completed:
            if e.connected_at:
                wait_times.append((e.connected_at - e.created_at).total_seconds())

        # Calculate average handle time
        handle_times = []
        for e in completed:
            if e.connected_at and e.completed_at:
                handle_times.append((e.completed_at - e.connected_at).total_seconds())

        # Satisfaction scores
        satisfaction_scores = [e.caller_satisfaction for e in completed if e.caller_satisfaction]

        # By reason
        by_reason = {}
        for e in escalations:
            reason = e.reason.value
            if reason not in by_reason:
                by_reason[reason] = 0
            by_reason[reason] += 1

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_escalations": len(escalations),
            "completed": len(completed),
            "failed": len(failed),
            "abandoned": len(abandoned),
            "completion_rate": len(completed) / len(escalations) * 100 if escalations else 0,
            "avg_wait_time_seconds": sum(wait_times) / len(wait_times) if wait_times else 0,
            "avg_handle_time_seconds": sum(handle_times) / len(handle_times) if handle_times else 0,
            "avg_satisfaction": sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else None,
            "by_reason": by_reason,
            "by_priority": {
                "normal": len([e for e in escalations if e.priority == 1]),
                "high": len([e for e in escalations if e.priority == 2]),
                "urgent": len([e for e in escalations if e.priority == 3])
            }
        }

    def configure_trigger(
        self,
        trigger_id: str,
        enabled: Optional[bool] = None,
        condition: Optional[Dict] = None,
        priority: Optional[int] = None
    ) -> bool:
        """Configure an escalation trigger"""
        if trigger_id not in self._triggers:
            return False

        trigger = self._triggers[trigger_id]

        if enabled is not None:
            trigger.enabled = enabled
        if condition is not None:
            trigger.condition.update(condition)
        if priority is not None:
            trigger.priority = priority

        logger.info(f"Updated trigger: {trigger_id}")
        return True

    def add_custom_trigger(
        self,
        name: str,
        trigger_type: str,
        condition: Dict[str, Any],
        action: EscalationReason,
        priority: int = 1,
        organization_id: Optional[int] = None
    ) -> EscalationTrigger:
        """Add a custom escalation trigger"""
        import uuid
        trigger_id = f"TRG-{str(uuid.uuid4())[:8].upper()}"

        trigger = EscalationTrigger(
            id=trigger_id,
            name=name,
            trigger_type=trigger_type,
            condition=condition,
            action=action,
            priority=priority,
            organization_id=organization_id
        )

        self._triggers[trigger_id] = trigger

        logger.info(f"Added custom trigger: {name} ({trigger_id})")
        return trigger

    def get_triggers(self) -> List[Dict[str, Any]]:
        """Get all configured escalation triggers"""
        return [
            {
                "id": t.id,
                "name": t.name,
                "type": t.trigger_type,
                "condition": t.condition,
                "action": t.action.value,
                "priority": t.priority,
                "enabled": t.enabled
            }
            for t in self._triggers.values()
        ]

    def _calculate_avg_wait_time(self) -> float:
        """Calculate average wait time for recent escalations"""
        recent = [
            e for e in self._escalations.values()
            if e.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
            and e.connected_at
        ]

        if not recent:
            return 0

        wait_times = [(e.connected_at - e.created_at).total_seconds() for e in recent]
        return sum(wait_times) / len(wait_times)

    def _get_escalation_reason_breakdown(self) -> Dict[str, int]:
        """Get breakdown of escalation reasons"""
        recent = [
            e for e in self._escalations.values()
            if e.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)
        ]

        breakdown = {}
        for e in recent:
            reason = e.reason.value
            breakdown[reason] = breakdown.get(reason, 0) + 1

        return breakdown

    def _persist_agent(self, agent: LiveAgent):
        """Persist agent to database"""
        # Implementation would save to database
        pass


# Create singleton instance
live_agent_escalation_service = LiveAgentEscalationService()
