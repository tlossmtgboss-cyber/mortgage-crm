"""
AI Agent Coordination Service

Coordinates multiple AI agents working together:
- Agent registry and capability management
- Task delegation and load balancing
- Inter-agent communication
- Conflict resolution
- Collaborative decision making
- Performance monitoring across agents
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import asyncio
from queue import PriorityQueue
import uuid

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Types of AI agents."""
    RECEPTIONIST = "receptionist"
    LEAD_QUALIFIER = "lead_qualifier"
    DOCUMENT_PROCESSOR = "document_processor"
    COMPLIANCE_CHECKER = "compliance_checker"
    UNDERWRITING_ASSISTANT = "underwriting_assistant"
    CUSTOMER_SERVICE = "customer_service"
    SALES_COACH = "sales_coach"
    ANALYTICS = "analytics"
    WORKFLOW = "workflow"
    SCHEDULER = "scheduler"
    KNOWLEDGE = "knowledge"


class AgentStatus(str, Enum):
    """Agent status."""
    AVAILABLE = "available"
    BUSY = "busy"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"


class TaskPriority(int, Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    BACKGROUND = 5


class TaskStatus(str, Enum):
    """Task status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELEGATED = "delegated"


class CommunicationType(str, Enum):
    """Types of inter-agent communication."""
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    HANDOFF = "handoff"
    NOTIFICATION = "notification"
    QUERY = "query"


@dataclass
class AgentCapability:
    """Represents an agent's capability."""
    name: str
    description: str
    input_types: List[str] = field(default_factory=list)
    output_types: List[str] = field(default_factory=list)
    avg_processing_time_ms: int = 1000
    max_concurrent: int = 10
    requires_context: List[str] = field(default_factory=list)


@dataclass
class AIAgent:
    """Represents an AI agent in the system."""
    id: str
    name: str
    agent_type: AgentType
    status: AgentStatus = AgentStatus.AVAILABLE

    # Capabilities
    capabilities: List[AgentCapability] = field(default_factory=list)

    # Performance metrics
    current_load: int = 0
    max_load: int = 10
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    avg_response_time_ms: float = 0.0
    success_rate: float = 1.0

    # Configuration
    priority_weight: float = 1.0
    specializations: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    # State
    context: Dict[str, Any] = field(default_factory=dict)
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentTask:
    """A task to be executed by an agent."""
    id: str
    task_type: str
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING

    # Task details
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    # Assignment
    assigned_agent_id: Optional[str] = None
    required_capabilities: List[str] = field(default_factory=list)
    preferred_agent_type: Optional[AgentType] = None

    # Timing
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None

    # Error handling
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None

    # Callbacks
    on_complete_callback: Optional[str] = None
    parent_task_id: Optional[str] = None

    def __lt__(self, other):
        return self.priority.value < other.priority.value


@dataclass
class AgentMessage:
    """Message for inter-agent communication."""
    id: str
    message_type: CommunicationType
    from_agent_id: str
    to_agent_id: Optional[str] = None  # None for broadcast

    # Content
    subject: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    correlation_id: Optional[str] = None  # For request/response pairing
    requires_response: bool = False
    response_deadline: Optional[datetime] = None

    # Status
    is_read: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    read_at: Optional[datetime] = None


@dataclass
class CollaborationSession:
    """A collaborative session between multiple agents."""
    id: str
    name: str
    participating_agents: List[str] = field(default_factory=list)
    lead_agent_id: Optional[str] = None

    # Session state
    goal: str = ""
    current_phase: str = "initialization"
    shared_context: Dict[str, Any] = field(default_factory=dict)
    decisions: List[Dict[str, Any]] = field(default_factory=list)

    # Status
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class AIAgentCoordinationService:
    """
    Coordinates multiple AI agents working together.

    Features:
    - Agent registry and discovery
    - Smart task delegation
    - Load balancing across agents
    - Inter-agent messaging
    - Collaborative decision making
    - Conflict resolution
    - Performance monitoring
    """

    def __init__(self, db_session=None):
        self.db = db_session

        # Agent registry
        self._agents: Dict[str, AIAgent] = {}

        # Task management
        self._task_queue: PriorityQueue = PriorityQueue()
        self._active_tasks: Dict[str, AgentTask] = {}
        self._completed_tasks: Dict[str, AgentTask] = {}

        # Messaging
        self._message_queue: Dict[str, List[AgentMessage]] = {}  # agent_id -> messages
        self._broadcast_log: List[AgentMessage] = []

        # Collaboration
        self._collaborations: Dict[str, CollaborationSession] = {}

        # Callbacks
        self._task_handlers: Dict[str, Callable] = {}

        # Initialize default agents
        self._initialize_default_agents()

        logger.info("AIAgentCoordinationService initialized")

    def _initialize_default_agents(self):
        """Initialize default AI agents."""
        default_agents = [
            {
                "id": "agent_receptionist",
                "name": "AI Receptionist",
                "agent_type": AgentType.RECEPTIONIST,
                "capabilities": [
                    AgentCapability(
                        name="answer_call",
                        description="Answer and handle incoming calls",
                        input_types=["call_data", "caller_info"],
                        output_types=["call_result", "transcript"]
                    ),
                    AgentCapability(
                        name="schedule_appointment",
                        description="Schedule appointments and meetings",
                        input_types=["appointment_request"],
                        output_types=["appointment_confirmation"]
                    )
                ],
                "specializations": ["voice", "scheduling", "routing"]
            },
            {
                "id": "agent_lead_qualifier",
                "name": "Lead Qualification Agent",
                "agent_type": AgentType.LEAD_QUALIFIER,
                "capabilities": [
                    AgentCapability(
                        name="qualify_lead",
                        description="Qualify and score incoming leads",
                        input_types=["lead_data"],
                        output_types=["qualification_result", "lead_score"]
                    ),
                    AgentCapability(
                        name="extract_requirements",
                        description="Extract loan requirements from conversation",
                        input_types=["conversation"],
                        output_types=["requirements"]
                    )
                ],
                "specializations": ["scoring", "mortgage", "analysis"]
            },
            {
                "id": "agent_doc_processor",
                "name": "Document Processing Agent",
                "agent_type": AgentType.DOCUMENT_PROCESSOR,
                "capabilities": [
                    AgentCapability(
                        name="extract_data",
                        description="Extract data from documents",
                        input_types=["document"],
                        output_types=["extracted_data"]
                    ),
                    AgentCapability(
                        name="validate_document",
                        description="Validate document completeness and accuracy",
                        input_types=["document", "requirements"],
                        output_types=["validation_result"]
                    )
                ],
                "specializations": ["ocr", "extraction", "validation"]
            },
            {
                "id": "agent_compliance",
                "name": "Compliance Agent",
                "agent_type": AgentType.COMPLIANCE_CHECKER,
                "capabilities": [
                    AgentCapability(
                        name="check_compliance",
                        description="Check regulatory compliance",
                        input_types=["loan_data", "documents"],
                        output_types=["compliance_report"]
                    ),
                    AgentCapability(
                        name="audit_trail",
                        description="Generate audit trail",
                        input_types=["actions"],
                        output_types=["audit_report"]
                    )
                ],
                "specializations": ["trid", "respa", "fair_lending"]
            },
            {
                "id": "agent_analytics",
                "name": "Analytics Agent",
                "agent_type": AgentType.ANALYTICS,
                "capabilities": [
                    AgentCapability(
                        name="generate_insights",
                        description="Generate insights from data",
                        input_types=["data"],
                        output_types=["insights"]
                    ),
                    AgentCapability(
                        name="predict",
                        description="Make predictions based on data",
                        input_types=["historical_data", "features"],
                        output_types=["prediction"]
                    )
                ],
                "specializations": ["reporting", "forecasting", "trends"]
            }
        ]

        for agent_config in default_agents:
            self.register_agent(
                agent_id=agent_config["id"],
                name=agent_config["name"],
                agent_type=agent_config["agent_type"],
                capabilities=agent_config["capabilities"],
                specializations=agent_config.get("specializations", [])
            )

    # =========================================================================
    # Agent Registry
    # =========================================================================

    def register_agent(
        self,
        agent_id: str,
        name: str,
        agent_type: AgentType,
        capabilities: List[AgentCapability] = None,
        specializations: List[str] = None,
        max_load: int = 10
    ) -> AIAgent:
        """Register a new AI agent."""
        agent = AIAgent(
            id=agent_id,
            name=name,
            agent_type=agent_type,
            capabilities=capabilities or [],
            specializations=specializations or [],
            max_load=max_load
        )

        self._agents[agent_id] = agent
        self._message_queue[agent_id] = []

        logger.info(f"Registered agent: {agent_id} ({name})")
        return agent

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            if agent_id in self._message_queue:
                del self._message_queue[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")
            return True
        return False

    def get_agent(self, agent_id: str) -> Optional[AIAgent]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def get_agents_by_type(self, agent_type: AgentType) -> List[AIAgent]:
        """Get all agents of a specific type."""
        return [a for a in self._agents.values() if a.agent_type == agent_type]

    def get_agents_with_capability(self, capability_name: str) -> List[AIAgent]:
        """Get all agents with a specific capability."""
        return [
            a for a in self._agents.values()
            if any(c.name == capability_name for c in a.capabilities)
        ]

    def update_agent_status(self, agent_id: str, status: AgentStatus) -> bool:
        """Update an agent's status."""
        agent = self._agents.get(agent_id)
        if agent:
            agent.status = status
            agent.last_active = datetime.now(timezone.utc)
            return True
        return False

    # =========================================================================
    # Task Management
    # =========================================================================

    async def submit_task(
        self,
        task_type: str,
        input_data: Dict[str, Any],
        priority: TaskPriority = TaskPriority.MEDIUM,
        required_capabilities: List[str] = None,
        preferred_agent_type: AgentType = None,
        deadline: datetime = None,
        context: Dict[str, Any] = None
    ) -> AgentTask:
        """Submit a task for execution."""
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        task = AgentTask(
            id=task_id,
            task_type=task_type,
            priority=priority,
            input_data=input_data,
            context=context or {},
            required_capabilities=required_capabilities or [],
            preferred_agent_type=preferred_agent_type,
            deadline=deadline
        )

        # Find best agent
        agent = self._select_best_agent(task)

        if agent:
            task.assigned_agent_id = agent.id
            task.status = TaskStatus.ASSIGNED
            task.assigned_at = datetime.now(timezone.utc)
            agent.current_load += 1

            # Execute task
            asyncio.create_task(self._execute_task(task, agent))
        else:
            # Queue for later
            self._task_queue.put(task)

        self._active_tasks[task_id] = task
        logger.info(f"Submitted task: {task_id} ({task_type}) -> {agent.id if agent else 'queued'}")

        return task

    def _select_best_agent(self, task: AgentTask) -> Optional[AIAgent]:
        """Select the best agent for a task."""
        candidates = []

        for agent in self._agents.values():
            # Skip unavailable agents
            if agent.status not in [AgentStatus.AVAILABLE, AgentStatus.BUSY]:
                continue

            # Skip overloaded agents
            if agent.current_load >= agent.max_load:
                continue

            # Check preferred type
            if task.preferred_agent_type and agent.agent_type != task.preferred_agent_type:
                continue

            # Check required capabilities
            if task.required_capabilities:
                agent_caps = {c.name for c in agent.capabilities}
                if not all(rc in agent_caps for rc in task.required_capabilities):
                    continue

            # Calculate score
            score = self._calculate_agent_score(agent, task)
            candidates.append((score, agent))

        if not candidates:
            return None

        # Sort by score (higher is better) and return best
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _calculate_agent_score(self, agent: AIAgent, task: AgentTask) -> float:
        """Calculate agent suitability score for a task."""
        score = 100.0

        # Load factor (less load = higher score)
        load_ratio = agent.current_load / agent.max_load
        score -= load_ratio * 30

        # Success rate factor
        score += agent.success_rate * 20

        # Response time factor (faster = higher score)
        if agent.avg_response_time_ms > 0:
            time_factor = min(5000 / agent.avg_response_time_ms, 1.0)
            score += time_factor * 15

        # Specialization bonus
        task_keywords = task.task_type.lower().split("_")
        matching_specs = sum(1 for s in agent.specializations if s.lower() in task_keywords)
        score += matching_specs * 10

        # Priority weight
        score *= agent.priority_weight

        return score

    async def _execute_task(self, task: AgentTask, agent: AIAgent):
        """Execute a task using an agent."""
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now(timezone.utc)

        try:
            # Get handler for task type
            handler = self._task_handlers.get(task.task_type)

            if handler:
                # Execute custom handler
                result = await handler(task, agent)
            else:
                # Default execution (simulated)
                await asyncio.sleep(0.1)  # Simulate processing
                result = {
                    "status": "completed",
                    "agent_id": agent.id,
                    "task_type": task.task_type
                }

            task.output_data = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)

            # Update agent metrics
            agent.total_tasks_completed += 1
            duration_ms = (task.completed_at - task.started_at).total_seconds() * 1000
            agent.avg_response_time_ms = (
                (agent.avg_response_time_ms * (agent.total_tasks_completed - 1) + duration_ms)
                / agent.total_tasks_completed
            )

            logger.info(f"Task completed: {task.id} by {agent.id}")

        except Exception as e:
            task.error = str(e)
            task.retry_count += 1

            if task.retry_count < task.max_retries:
                # Retry
                task.status = TaskStatus.PENDING
                await asyncio.sleep(task.retry_count * 2)  # Exponential backoff
                await self._execute_task(task, agent)
            else:
                task.status = TaskStatus.FAILED
                agent.total_tasks_failed += 1
                logger.error(f"Task failed: {task.id} - {e}")

        finally:
            agent.current_load = max(0, agent.current_load - 1)
            agent.last_active = datetime.now(timezone.utc)

            # Move to completed
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                self._completed_tasks[task.id] = task
                if task.id in self._active_tasks:
                    del self._active_tasks[task.id]

            # Update success rate
            total = agent.total_tasks_completed + agent.total_tasks_failed
            agent.success_rate = agent.total_tasks_completed / total if total > 0 else 1.0

            # Process queue if agent has capacity
            if agent.current_load < agent.max_load and not self._task_queue.empty():
                queued_task = self._task_queue.get_nowait()
                await self.submit_task(
                    queued_task.task_type,
                    queued_task.input_data,
                    queued_task.priority,
                    queued_task.required_capabilities,
                    queued_task.preferred_agent_type
                )

    def register_task_handler(
        self,
        task_type: str,
        handler: Callable[[AgentTask, AIAgent], Dict]
    ):
        """Register a handler for a task type."""
        self._task_handlers[task_type] = handler
        logger.debug(f"Registered handler for task type: {task_type}")

    def get_task(self, task_id: str) -> Optional[AgentTask]:
        """Get a task by ID."""
        return self._active_tasks.get(task_id) or self._completed_tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or active task."""
        task = self._active_tasks.get(task_id)
        if task and task.status in [TaskStatus.PENDING, TaskStatus.ASSIGNED]:
            task.status = TaskStatus.CANCELLED
            if task.assigned_agent_id:
                agent = self._agents.get(task.assigned_agent_id)
                if agent:
                    agent.current_load = max(0, agent.current_load - 1)
            return True
        return False

    # =========================================================================
    # Inter-Agent Communication
    # =========================================================================

    def send_message(
        self,
        from_agent_id: str,
        to_agent_id: str,
        message_type: CommunicationType,
        subject: str,
        payload: Dict[str, Any],
        requires_response: bool = False,
        response_deadline: datetime = None,
        correlation_id: str = None
    ) -> AgentMessage:
        """Send a message between agents."""
        message_id = f"msg_{uuid.uuid4().hex[:12]}"

        message = AgentMessage(
            id=message_id,
            message_type=message_type,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            subject=subject,
            payload=payload,
            requires_response=requires_response,
            response_deadline=response_deadline,
            correlation_id=correlation_id or message_id
        )

        # Add to recipient's queue
        if to_agent_id in self._message_queue:
            self._message_queue[to_agent_id].append(message)

        logger.debug(f"Message sent: {message_id} from {from_agent_id} to {to_agent_id}")
        return message

    def broadcast_message(
        self,
        from_agent_id: str,
        subject: str,
        payload: Dict[str, Any],
        target_types: List[AgentType] = None
    ) -> AgentMessage:
        """Broadcast a message to multiple agents."""
        message_id = f"msg_{uuid.uuid4().hex[:12]}"

        message = AgentMessage(
            id=message_id,
            message_type=CommunicationType.BROADCAST,
            from_agent_id=from_agent_id,
            to_agent_id=None,
            subject=subject,
            payload=payload
        )

        # Add to all matching agents' queues
        for agent_id, agent in self._agents.items():
            if agent_id == from_agent_id:
                continue
            if target_types and agent.agent_type not in target_types:
                continue
            if agent_id in self._message_queue:
                self._message_queue[agent_id].append(message)

        self._broadcast_log.append(message)
        logger.debug(f"Broadcast sent: {message_id} from {from_agent_id}")
        return message

    def get_messages(
        self,
        agent_id: str,
        unread_only: bool = False
    ) -> List[AgentMessage]:
        """Get messages for an agent."""
        messages = self._message_queue.get(agent_id, [])
        if unread_only:
            messages = [m for m in messages if not m.is_read]
        return messages

    def mark_message_read(self, agent_id: str, message_id: str) -> bool:
        """Mark a message as read."""
        messages = self._message_queue.get(agent_id, [])
        for message in messages:
            if message.id == message_id:
                message.is_read = True
                message.read_at = datetime.now(timezone.utc)
                return True
        return False

    async def request_and_wait(
        self,
        from_agent_id: str,
        to_agent_id: str,
        request_payload: Dict[str, Any],
        timeout_seconds: int = 30
    ) -> Optional[Dict[str, Any]]:
        """Send a request and wait for response."""
        correlation_id = f"req_{uuid.uuid4().hex[:8]}"

        # Send request
        self.send_message(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message_type=CommunicationType.REQUEST,
            subject="Request",
            payload=request_payload,
            requires_response=True,
            response_deadline=datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds),
            correlation_id=correlation_id
        )

        # Wait for response
        start_time = datetime.now(timezone.utc)
        while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout_seconds:
            messages = self.get_messages(from_agent_id)
            for msg in messages:
                if (msg.message_type == CommunicationType.RESPONSE and
                    msg.correlation_id == correlation_id):
                    self.mark_message_read(from_agent_id, msg.id)
                    return msg.payload
            await asyncio.sleep(0.1)

        return None

    # =========================================================================
    # Collaboration
    # =========================================================================

    def start_collaboration(
        self,
        name: str,
        goal: str,
        agent_ids: List[str],
        lead_agent_id: str = None
    ) -> CollaborationSession:
        """Start a collaboration session between agents."""
        session_id = f"collab_{uuid.uuid4().hex[:12]}"

        # Validate agents exist
        valid_agents = [aid for aid in agent_ids if aid in self._agents]

        session = CollaborationSession(
            id=session_id,
            name=name,
            goal=goal,
            participating_agents=valid_agents,
            lead_agent_id=lead_agent_id or (valid_agents[0] if valid_agents else None)
        )

        self._collaborations[session_id] = session

        # Notify participating agents
        for agent_id in valid_agents:
            self.send_message(
                from_agent_id="system",
                to_agent_id=agent_id,
                message_type=CommunicationType.NOTIFICATION,
                subject="Collaboration Started",
                payload={
                    "session_id": session_id,
                    "goal": goal,
                    "participants": valid_agents,
                    "lead": lead_agent_id
                }
            )

        logger.info(f"Started collaboration: {session_id} with {len(valid_agents)} agents")
        return session

    def update_collaboration_context(
        self,
        session_id: str,
        agent_id: str,
        context_update: Dict[str, Any]
    ) -> bool:
        """Update shared context in a collaboration session."""
        session = self._collaborations.get(session_id)
        if not session or agent_id not in session.participating_agents:
            return False

        # Update context
        session.shared_context.update(context_update)

        # Notify other participants
        for participant_id in session.participating_agents:
            if participant_id != agent_id:
                self.send_message(
                    from_agent_id=agent_id,
                    to_agent_id=participant_id,
                    message_type=CommunicationType.NOTIFICATION,
                    subject="Context Update",
                    payload={
                        "session_id": session_id,
                        "update": context_update
                    }
                )

        return True

    def record_collaboration_decision(
        self,
        session_id: str,
        decision: str,
        decided_by: str,
        reasoning: str = "",
        votes: Dict[str, str] = None
    ) -> bool:
        """Record a decision made in a collaboration session."""
        session = self._collaborations.get(session_id)
        if not session:
            return False

        session.decisions.append({
            "decision": decision,
            "decided_by": decided_by,
            "reasoning": reasoning,
            "votes": votes or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        return True

    async def collaborative_vote(
        self,
        session_id: str,
        question: str,
        options: List[str],
        initiator_id: str,
        timeout_seconds: int = 30
    ) -> Dict[str, Any]:
        """Conduct a vote among collaborating agents."""
        session = self._collaborations.get(session_id)
        if not session:
            return {"error": "Session not found"}

        # Send vote requests
        correlation_id = f"vote_{uuid.uuid4().hex[:8]}"

        for agent_id in session.participating_agents:
            self.send_message(
                from_agent_id=initiator_id,
                to_agent_id=agent_id,
                message_type=CommunicationType.REQUEST,
                subject="Vote Request",
                payload={
                    "question": question,
                    "options": options,
                    "session_id": session_id
                },
                requires_response=True,
                correlation_id=correlation_id
            )

        # Collect votes
        votes = {}
        start_time = datetime.now(timezone.utc)

        while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout_seconds:
            for agent_id in session.participating_agents:
                if agent_id in votes:
                    continue

                messages = self.get_messages(agent_id)
                for msg in messages:
                    if (msg.correlation_id == correlation_id and
                        msg.message_type == CommunicationType.RESPONSE):
                        votes[agent_id] = msg.payload.get("vote")

            if len(votes) == len(session.participating_agents):
                break

            await asyncio.sleep(0.1)

        # Tally results
        vote_counts = {}
        for vote in votes.values():
            vote_counts[vote] = vote_counts.get(vote, 0) + 1

        winner = max(vote_counts.items(), key=lambda x: x[1])[0] if vote_counts else None

        # Record decision
        self.record_collaboration_decision(
            session_id,
            decision=winner,
            decided_by="collaborative_vote",
            reasoning=f"Vote result: {vote_counts}",
            votes=votes
        )

        return {
            "question": question,
            "votes": votes,
            "vote_counts": vote_counts,
            "winner": winner,
            "unanimous": len(set(votes.values())) == 1 if votes else False
        }

    def end_collaboration(self, session_id: str, outcome: str = "") -> bool:
        """End a collaboration session."""
        session = self._collaborations.get(session_id)
        if not session:
            return False

        session.status = "completed"
        session.completed_at = datetime.now(timezone.utc)
        session.shared_context["outcome"] = outcome

        # Notify participants
        for agent_id in session.participating_agents:
            self.send_message(
                from_agent_id="system",
                to_agent_id=agent_id,
                message_type=CommunicationType.NOTIFICATION,
                subject="Collaboration Ended",
                payload={
                    "session_id": session_id,
                    "outcome": outcome,
                    "decisions_made": len(session.decisions)
                }
            )

        logger.info(f"Ended collaboration: {session_id}")
        return True

    # =========================================================================
    # Handoff
    # =========================================================================

    async def handoff_task(
        self,
        task_id: str,
        from_agent_id: str,
        to_agent_id: str,
        reason: str = ""
    ) -> bool:
        """Handoff a task from one agent to another."""
        task = self._active_tasks.get(task_id)
        if not task or task.assigned_agent_id != from_agent_id:
            return False

        to_agent = self._agents.get(to_agent_id)
        if not to_agent or to_agent.status not in [AgentStatus.AVAILABLE, AgentStatus.BUSY]:
            return False

        # Update task assignment
        from_agent = self._agents.get(from_agent_id)
        if from_agent:
            from_agent.current_load = max(0, from_agent.current_load - 1)

        task.assigned_agent_id = to_agent_id
        task.status = TaskStatus.DELEGATED
        to_agent.current_load += 1

        # Send handoff message
        self.send_message(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message_type=CommunicationType.HANDOFF,
            subject=f"Task Handoff: {task.task_type}",
            payload={
                "task_id": task_id,
                "task_type": task.task_type,
                "input_data": task.input_data,
                "context": task.context,
                "reason": reason
            }
        )

        # Re-execute task with new agent
        task.status = TaskStatus.ASSIGNED
        asyncio.create_task(self._execute_task(task, to_agent))

        logger.info(f"Handoff task {task_id}: {from_agent_id} -> {to_agent_id}")
        return True

    # =========================================================================
    # Monitoring & Analytics
    # =========================================================================

    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status."""
        total_agents = len(self._agents)
        available_agents = len([a for a in self._agents.values() if a.status == AgentStatus.AVAILABLE])
        busy_agents = len([a for a in self._agents.values() if a.status == AgentStatus.BUSY])

        total_load = sum(a.current_load for a in self._agents.values())
        total_capacity = sum(a.max_load for a in self._agents.values())

        return {
            "agents": {
                "total": total_agents,
                "available": available_agents,
                "busy": busy_agents,
                "offline": total_agents - available_agents - busy_agents
            },
            "capacity": {
                "current_load": total_load,
                "total_capacity": total_capacity,
                "utilization_percent": round(total_load / total_capacity * 100, 1) if total_capacity > 0 else 0
            },
            "tasks": {
                "active": len(self._active_tasks),
                "queued": self._task_queue.qsize(),
                "completed": len(self._completed_tasks)
            },
            "collaborations": {
                "active": len([c for c in self._collaborations.values() if c.status == "active"]),
                "completed": len([c for c in self._collaborations.values() if c.status == "completed"])
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def get_agent_performance(self, agent_id: str) -> Dict[str, Any]:
        """Get performance metrics for an agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            return {}

        return {
            "agent_id": agent_id,
            "name": agent.name,
            "type": agent.agent_type.value,
            "status": agent.status.value,
            "metrics": {
                "tasks_completed": agent.total_tasks_completed,
                "tasks_failed": agent.total_tasks_failed,
                "success_rate": round(agent.success_rate * 100, 1),
                "avg_response_time_ms": round(agent.avg_response_time_ms, 2),
                "current_load": agent.current_load,
                "max_load": agent.max_load,
                "utilization": round(agent.current_load / agent.max_load * 100, 1) if agent.max_load > 0 else 0
            },
            "last_active": agent.last_active.isoformat()
        }

    def get_all_agents_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all agents."""
        return [self.get_agent_performance(aid) for aid in self._agents.keys()]
