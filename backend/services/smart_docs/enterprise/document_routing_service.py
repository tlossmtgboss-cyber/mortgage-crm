"""
Smart Docs Enterprise Document Routing Service

Production-quality async routing engine for document assignment. Evaluates
configurable rules against document and loan attributes to determine optimal
assignment (specific user, role, team, or named processing queue).

Routing strategies:
    AUTO_ASSIGN   - Direct assignment based on condition match
    ROUND_ROBIN   - Even distribution across team members
    LOAD_BALANCED - Assign to processor with lightest current workload
    SKILL_BASED   - Route complex documents to experienced processors
    ESCALATION    - Route based on urgency/priority level

Key features:
    - Multi-condition rule evaluation with priority ordering
    - Processing queue management with capacity limits
    - Dry-run routing (test rules without executing)
    - Rule conflict detection (overlapping conditions)
    - Assignment notifications with SLA-derived due dates
    - Reassignment with reason tracking
    - Workload rebalancing
    - Full routing audit trail
    - Routing analytics (distribution, wait times, throughput)

Usage:
    from services.smart_docs.enterprise.document_routing_service import (
        DocumentRoutingService,
    )

    service = DocumentRoutingService(db=db, org_id=1)
    decision = await service.route_document(document_id=42, event_data={...})
    analytics = await service.get_routing_analytics(days=30)
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, text, and_, or_
from sqlalchemy.orm import Session

from database.models.routing_rule import (
    RoutingRule,
    ProcessingQueue,
    RoutingAuditLog,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

RULE_TYPES = {"AUTO_ASSIGN", "ROUND_ROBIN", "LOAD_BALANCED", "SKILL_BASED", "ESCALATION"}
TARGET_TYPES = {"USER", "ROLE", "TEAM", "QUEUE"}
CONDITION_OPS = {"eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "contains"}

# SLA hours by document urgency for notification due dates
SLA_HOURS_BY_PRIORITY = {
    "critical": 4,
    "high": 8,
    "medium": 24,
    "low": 48,
    "normal": 24,
}

# Default routing rules seeded per-org on first access
DEFAULT_ROUTING_RULES: List[Dict[str, Any]] = [
    {
        "rule_name": "Simple Income Docs - Any Processor",
        "rule_type": "ROUND_ROBIN",
        "priority": 200,
        "conditions": [
            {"field": "doc_type", "op": "in", "value": ["W2", "PAYSTUB", "1099"]},
        ],
        "target_type": "ROLE",
        "target_config": {"role": "processor"},
    },
    {
        "rule_name": "Complex Income - Senior Processor",
        "rule_type": "SKILL_BASED",
        "priority": 100,
        "conditions": [
            {
                "field": "doc_type",
                "op": "in",
                "value": [
                    "TAX_RETURN",
                    "SCHEDULE_C",
                    "SCHEDULE_E",
                    "PROFIT_LOSS",
                    "K1",
                    "CORP_TAX_RETURN",
                ],
            },
        ],
        "target_type": "ROLE",
        "target_config": {"role": "senior_processor"},
    },
    {
        "rule_name": "Jumbo Loan Docs - Senior Processor",
        "rule_type": "SKILL_BASED",
        "priority": 90,
        "conditions": [
            {"field": "loan_amount", "op": "gt", "value": 726200},
        ],
        "target_type": "ROLE",
        "target_config": {"role": "senior_processor"},
    },
    {
        "rule_name": "FHA/VA Specialist Routing",
        "rule_type": "SKILL_BASED",
        "priority": 95,
        "conditions": [
            {"field": "loan_type", "op": "in", "value": ["FHA", "VA"]},
        ],
        "target_type": "ROLE",
        "target_config": {"role": "government_specialist"},
    },
    {
        "rule_name": "Fraud Alerts - Compliance Team",
        "rule_type": "ESCALATION",
        "priority": 10,
        "conditions": [
            {"field": "doc_type", "op": "eq", "value": "FRAUD_ALERT"},
        ],
        "target_type": "QUEUE",
        "target_config": {"queue_name": "fraud_check"},
    },
    {
        "rule_name": "E-Signature Docs - Closer",
        "rule_type": "AUTO_ASSIGN",
        "priority": 80,
        "conditions": [
            {"field": "doc_type", "op": "in", "value": ["CLOSING_DISCLOSURE", "NOTE", "DEED_OF_TRUST"]},
            {"field": "loan_stage", "op": "in", "value": ["CLEAR_TO_CLOSE", "DOCS", "DOCS_OUT", "CLOSING"]},
        ],
        "target_type": "ROLE",
        "target_config": {"role": "closer"},
    },
    {
        "rule_name": "Spanish Language - Bilingual Processor",
        "rule_type": "SKILL_BASED",
        "priority": 85,
        "conditions": [
            {"field": "borrower_language", "op": "eq", "value": "es"},
        ],
        "target_type": "ROLE",
        "target_config": {"role": "bilingual_processor"},
    },
    {
        "rule_name": "High Complexity Docs - Senior Processor",
        "rule_type": "SKILL_BASED",
        "priority": 50,
        "conditions": [
            {"field": "complexity_score", "op": "gte", "value": 7},
        ],
        "target_type": "ROLE",
        "target_config": {"role": "senior_processor"},
    },
]

# Default processing queues seeded per-org
DEFAULT_PROCESSING_QUEUES: List[Dict[str, Any]] = [
    {
        "queue_name": "income_review",
        "description": "Income document review and calculation verification",
        "max_items": 50,
        "avg_processing_time_hours": 4,
        "priority_weight": 100,
    },
    {
        "queue_name": "bank_analysis",
        "description": "Bank statement analysis and large deposit review",
        "max_items": 40,
        "avg_processing_time_hours": 3,
        "priority_weight": 100,
    },
    {
        "queue_name": "fraud_check",
        "description": "Fraud alert review and compliance verification",
        "max_items": 20,
        "avg_processing_time_hours": 2,
        "priority_weight": 10,
    },
    {
        "queue_name": "esign_closing",
        "description": "E-signature and closing document preparation",
        "max_items": 30,
        "avg_processing_time_hours": 6,
        "priority_weight": 50,
    },
    {
        "queue_name": "general_processing",
        "description": "General document processing and verification",
        "max_items": 100,
        "avg_processing_time_hours": 4,
        "priority_weight": 200,
    },
]

# Role-to-user lookup queries (org-scoped)
ROLE_LOOKUP_QUERIES: Dict[str, str] = {
    "processor": """
        SELECT u.id AS user_id, u.first_name, u.last_name
        FROM users u
        WHERE u.organization_id = :org_id
            AND u.role IN ('processor', 'loan_processor')
            AND u.is_active = true
    """,
    "senior_processor": """
        SELECT u.id AS user_id, u.first_name, u.last_name
        FROM users u
        WHERE u.organization_id = :org_id
            AND u.role IN ('senior_processor', 'lead_processor')
            AND u.is_active = true
    """,
    "closer": """
        SELECT u.id AS user_id, u.first_name, u.last_name
        FROM users u
        WHERE u.organization_id = :org_id
            AND u.role IN ('closer', 'closing_coordinator')
            AND u.is_active = true
    """,
    "government_specialist": """
        SELECT u.id AS user_id, u.first_name, u.last_name
        FROM users u
        WHERE u.organization_id = :org_id
            AND u.role IN ('government_specialist', 'fha_specialist', 'va_specialist')
            AND u.is_active = true
    """,
    "bilingual_processor": """
        SELECT u.id AS user_id, u.first_name, u.last_name
        FROM users u
        WHERE u.organization_id = :org_id
            AND u.role IN ('processor', 'loan_processor', 'senior_processor')
            AND u.is_active = true
    """,
    "loan_officer": """
        SELECT l.loan_officer_id AS user_id, u.first_name, u.last_name
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        WHERE l.id = :loan_id AND l.organization_id = :org_id
    """,
}


# =============================================================================
# DATA CLASSES
# =============================================================================

class RoutingDecision:
    """Result of a routing evaluation."""

    __slots__ = (
        "matched",
        "rule_id",
        "rule_name",
        "rule_type",
        "target_type",
        "target_user_id",
        "target_user_name",
        "target_queue_name",
        "priority",
        "due_at",
        "reason",
        "is_dry_run",
        "conflicts",
        "all_matches",
    )

    def __init__(
        self,
        matched: bool = False,
        rule_id: Optional[int] = None,
        rule_name: Optional[str] = None,
        rule_type: Optional[str] = None,
        target_type: Optional[str] = None,
        target_user_id: Optional[int] = None,
        target_user_name: Optional[str] = None,
        target_queue_name: Optional[str] = None,
        priority: Optional[str] = None,
        due_at: Optional[datetime] = None,
        reason: str = "",
        is_dry_run: bool = False,
        conflicts: Optional[List[Dict[str, Any]]] = None,
        all_matches: Optional[List[Dict[str, Any]]] = None,
    ):
        self.matched = matched
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.rule_type = rule_type
        self.target_type = target_type
        self.target_user_id = target_user_id
        self.target_user_name = target_user_name
        self.target_queue_name = target_queue_name
        self.priority = priority
        self.due_at = due_at
        self.reason = reason
        self.is_dry_run = is_dry_run
        self.conflicts = conflicts or []
        self.all_matches = all_matches or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_type": self.rule_type,
            "target_type": self.target_type,
            "target_user_id": self.target_user_id,
            "target_user_name": self.target_user_name,
            "target_queue_name": self.target_queue_name,
            "priority": self.priority,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "reason": self.reason,
            "is_dry_run": self.is_dry_run,
            "conflicts": self.conflicts,
            "all_matches": self.all_matches,
        }


class QueueStatus:
    """Snapshot of processing queue state."""

    __slots__ = (
        "queue_name",
        "description",
        "current_count",
        "max_items",
        "utilization_pct",
        "assigned_user_count",
        "avg_processing_time_hours",
        "estimated_wait_hours",
        "is_active",
    )

    def __init__(self, **kwargs: Any):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> Dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}


# =============================================================================
# SERVICE
# =============================================================================

class DocumentRoutingService:
    """Async document routing engine with org-level isolation.

    All queries are scoped to ``self.org_id`` to enforce multi-tenant
    boundaries at the service layer.
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    # ------------------------------------------------------------------
    # SYSTEM RULE & QUEUE SEEDING
    # ------------------------------------------------------------------

    async def ensure_system_rules(self) -> int:
        """Seed default routing rules if none exist for this org.

        Returns the number of rules created.
        """
        existing = (
            self.db.query(func.count(RoutingRule.id))
            .filter(
                RoutingRule.organization_id == self.org_id,
                RoutingRule.is_system == True,
            )
            .scalar()
        )
        if existing > 0:
            return 0

        created = 0
        for rule_def in DEFAULT_ROUTING_RULES:
            rule = RoutingRule(
                organization_id=self.org_id,
                rule_name=rule_def["rule_name"],
                rule_type=rule_def["rule_type"],
                priority=rule_def["priority"],
                conditions=rule_def["conditions"],
                target_type=rule_def["target_type"],
                target_config=rule_def["target_config"],
                is_active=True,
                is_system=True,
            )
            self.db.add(rule)
            created += 1

        self.db.flush()
        logger.info(
            "Seeded %d default routing rules for org_id=%d", created, self.org_id
        )
        return created

    async def ensure_processing_queues(self) -> int:
        """Seed default processing queues if none exist for this org."""
        existing = (
            self.db.query(func.count(ProcessingQueue.id))
            .filter(ProcessingQueue.organization_id == self.org_id)
            .scalar()
        )
        if existing > 0:
            return 0

        created = 0
        for q_def in DEFAULT_PROCESSING_QUEUES:
            queue = ProcessingQueue(
                organization_id=self.org_id,
                queue_name=q_def["queue_name"],
                description=q_def["description"],
                max_items=q_def["max_items"],
                avg_processing_time_hours=q_def["avg_processing_time_hours"],
                priority_weight=q_def.get("priority_weight", 100),
                assigned_users=[],
                is_active=True,
            )
            self.db.add(queue)
            created += 1

        self.db.flush()
        logger.info(
            "Seeded %d default processing queues for org_id=%d", created, self.org_id
        )
        return created

    # ------------------------------------------------------------------
    # CORE ROUTING
    # ------------------------------------------------------------------

    async def route_document(
        self,
        document_id: int,
        event_data: Dict[str, Any],
        dry_run: bool = False,
    ) -> RoutingDecision:
        """Route a document through the rule engine.

        Args:
            document_id: ID of the document to route.
            event_data: Dict containing document and loan attributes for
                        condition matching. Expected keys include:
                        doc_type, loan_amount, loan_type, loan_stage,
                        borrower_language, complexity_score, branch_id,
                        loan_id, priority.
            dry_run: If True, evaluate rules but do not execute assignment.

        Returns:
            RoutingDecision with the matched rule and target details.
        """
        await self.ensure_system_rules()
        await self.ensure_processing_queues()

        rules = (
            self.db.query(RoutingRule)
            .filter(
                RoutingRule.organization_id == self.org_id,
                RoutingRule.is_active == True,
            )
            .order_by(RoutingRule.priority.asc())
            .all()
        )

        if not rules:
            return RoutingDecision(
                matched=False,
                reason="No active routing rules configured",
                is_dry_run=dry_run,
            )

        # Evaluate all rules to detect conflicts
        matched_rules: List[Tuple[RoutingRule, float]] = []
        for rule in rules:
            score = self._evaluate_conditions(rule.conditions or [], event_data)
            if score > 0:
                matched_rules.append((rule, score))

        if not matched_rules:
            decision = RoutingDecision(
                matched=False,
                reason="No rules matched the document attributes",
                is_dry_run=dry_run,
            )
            if not dry_run:
                self._record_audit(
                    document_id=document_id,
                    loan_id=event_data.get("loan_id"),
                    action="ROUTED",
                    decision_reason="No matching rules",
                    event_data=event_data,
                    is_dry_run=False,
                )
            return decision

        # Sort by priority (lower = higher), then by condition match score
        matched_rules.sort(key=lambda x: (x[0].priority, -x[1]))

        # Detect conflicts: multiple rules at same priority level
        conflicts = self._detect_conflicts(matched_rules)

        # Build all_matches for transparency
        all_matches = [
            {
                "rule_id": r.id,
                "rule_name": r.rule_name,
                "rule_type": r.rule_type,
                "priority": r.priority,
                "match_score": score,
            }
            for r, score in matched_rules
        ]

        # Winner is highest priority (lowest number)
        winning_rule, winning_score = matched_rules[0]

        # Resolve the target user/queue
        target_user_id, target_user_name, target_queue_name = await self._resolve_target(
            winning_rule, event_data
        )

        # Calculate due date from SLA
        priority_str = event_data.get("priority", "normal")
        sla_hours = SLA_HOURS_BY_PRIORITY.get(priority_str, 24)
        due_at = datetime.now(timezone.utc) + timedelta(hours=sla_hours)

        decision = RoutingDecision(
            matched=True,
            rule_id=winning_rule.id,
            rule_name=winning_rule.rule_name,
            rule_type=winning_rule.rule_type,
            target_type=winning_rule.target_type,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            target_queue_name=target_queue_name,
            priority=priority_str,
            due_at=due_at,
            reason=f"Matched rule '{winning_rule.rule_name}' (priority {winning_rule.priority})",
            is_dry_run=dry_run,
            conflicts=conflicts,
            all_matches=all_matches,
        )

        if not dry_run:
            # Execute assignment
            if target_queue_name:
                await self._assign_to_queue(document_id, target_queue_name)
            self._record_audit(
                document_id=document_id,
                loan_id=event_data.get("loan_id"),
                action="ROUTED",
                rule_id=winning_rule.id,
                rule_name=winning_rule.rule_name,
                rule_type=winning_rule.rule_type,
                to_user_id=target_user_id,
                queue_name=target_queue_name,
                decision_reason=decision.reason,
                event_data=event_data,
                is_dry_run=False,
            )

            # Send assignment notification
            if target_user_id:
                await self._send_assignment_notification(
                    user_id=target_user_id,
                    document_id=document_id,
                    loan_id=event_data.get("loan_id"),
                    priority=priority_str,
                    due_at=due_at,
                    rule_name=winning_rule.rule_name,
                )

        else:
            self._record_audit(
                document_id=document_id,
                loan_id=event_data.get("loan_id"),
                action="DRY_RUN",
                rule_id=winning_rule.id,
                rule_name=winning_rule.rule_name,
                rule_type=winning_rule.rule_type,
                to_user_id=target_user_id,
                queue_name=target_queue_name,
                decision_reason=decision.reason,
                event_data=event_data,
                is_dry_run=True,
            )

        return decision

    async def route_to_queue(
        self,
        document_id: int,
        queue_name: str,
        loan_id: Optional[int] = None,
    ) -> None:
        """Manually route a document into a named processing queue.

        Args:
            document_id: ID of the document.
            queue_name: Target queue name.
            loan_id: Optional loan ID for audit trail.

        Raises:
            ValueError: If the queue does not exist or is at capacity.
        """
        queue = (
            self.db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.organization_id == self.org_id,
                ProcessingQueue.queue_name == queue_name,
                ProcessingQueue.is_active == True,
            )
            .first()
        )
        if not queue:
            raise ValueError(f"Queue '{queue_name}' not found or inactive")

        if queue.current_count >= queue.max_items:
            raise ValueError(
                f"Queue '{queue_name}' is at capacity "
                f"({queue.current_count}/{queue.max_items})"
            )

        queue.current_count = (queue.current_count or 0) + 1
        self.db.flush()

        self._record_audit(
            document_id=document_id,
            loan_id=loan_id,
            action="QUEUED",
            queue_name=queue_name,
            decision_reason=f"Manually routed to queue '{queue_name}'",
            event_data={"queue_name": queue_name},
            is_dry_run=False,
        )

        logger.info(
            "Document %d routed to queue '%s' (org_id=%d)",
            document_id,
            queue_name,
            self.org_id,
        )

    # ------------------------------------------------------------------
    # QUEUE MANAGEMENT
    # ------------------------------------------------------------------

    async def get_queue_status(
        self,
        queue_name: Optional[str] = None,
    ) -> List[QueueStatus]:
        """Get status of processing queues.

        Args:
            queue_name: If provided, return status for that queue only.
                        Otherwise return all queues.

        Returns:
            List of QueueStatus objects.
        """
        query = self.db.query(ProcessingQueue).filter(
            ProcessingQueue.organization_id == self.org_id,
        )
        if queue_name:
            query = query.filter(ProcessingQueue.queue_name == queue_name)

        queues = query.order_by(ProcessingQueue.priority_weight.asc()).all()

        results: List[QueueStatus] = []
        for q in queues:
            assigned_count = len(q.assigned_users or [])
            current = q.current_count or 0
            max_items = q.max_items or 50
            utilization = round((current / max_items) * 100, 1) if max_items > 0 else 0

            # Estimate wait: items / (assigned_users * throughput_per_user_per_hour)
            if assigned_count > 0 and q.avg_processing_time_hours:
                items_per_user_per_hour = 1 / q.avg_processing_time_hours
                total_throughput = assigned_count * items_per_user_per_hour
                estimated_wait = round(current / total_throughput, 1) if total_throughput > 0 else 0
            else:
                estimated_wait = None

            results.append(QueueStatus(
                queue_name=q.queue_name,
                description=q.description,
                current_count=current,
                max_items=max_items,
                utilization_pct=utilization,
                assigned_user_count=assigned_count,
                avg_processing_time_hours=q.avg_processing_time_hours,
                estimated_wait_hours=estimated_wait,
                is_active=q.is_active,
            ))

        return results

    async def dequeue_document(
        self,
        document_id: int,
        queue_name: str,
        loan_id: Optional[int] = None,
    ) -> None:
        """Remove a document from a processing queue (mark as picked up).

        Args:
            document_id: Document that was processed.
            queue_name: Queue to decrement.
            loan_id: Optional loan ID for audit.
        """
        queue = (
            self.db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.organization_id == self.org_id,
                ProcessingQueue.queue_name == queue_name,
            )
            .first()
        )
        if queue and (queue.current_count or 0) > 0:
            queue.current_count = queue.current_count - 1
            self.db.flush()

        self._record_audit(
            document_id=document_id,
            loan_id=loan_id,
            action="DEQUEUED",
            queue_name=queue_name,
            decision_reason=f"Document picked up from queue '{queue_name}'",
            event_data={"queue_name": queue_name},
            is_dry_run=False,
        )

    # ------------------------------------------------------------------
    # REASSIGNMENT
    # ------------------------------------------------------------------

    async def reassign(
        self,
        document_id: int,
        from_user_id: int,
        to_user_id: int,
        reason: str,
        loan_id: Optional[int] = None,
    ) -> None:
        """Manually reassign a document from one user to another.

        Args:
            document_id: Document to reassign.
            from_user_id: Current assignee.
            to_user_id: New assignee.
            reason: Reason for reassignment (PTO, workload, expertise, etc.).
            loan_id: Optional loan ID for context.
        """
        self._record_audit(
            document_id=document_id,
            loan_id=loan_id,
            action="REASSIGNED",
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            decision_reason=reason,
            event_data={
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
                "reason": reason,
            },
            is_dry_run=False,
        )

        # Notify new assignee
        await self._send_assignment_notification(
            user_id=to_user_id,
            document_id=document_id,
            loan_id=loan_id,
            priority="normal",
            due_at=datetime.now(timezone.utc) + timedelta(hours=24),
            rule_name=f"Reassigned from user {from_user_id}: {reason}",
        )

        logger.info(
            "Document %d reassigned from user %d to user %d (org_id=%d): %s",
            document_id,
            from_user_id,
            to_user_id,
            self.org_id,
            reason,
        )

    async def auto_reassign_absent_user(
        self,
        absent_user_id: int,
        backup_user_id: Optional[int] = None,
    ) -> int:
        """Reassign all pending documents from an absent user.

        If no backup_user_id is specified, uses load-balanced assignment
        among other team members in the same role.

        Args:
            absent_user_id: User going on PTO/leave.
            backup_user_id: Explicit backup, or None for auto-selection.

        Returns:
            Number of documents reassigned.
        """
        # Find documents currently assigned to the absent user via audit log
        recent_assignments = (
            self.db.query(RoutingAuditLog)
            .filter(
                RoutingAuditLog.organization_id == self.org_id,
                RoutingAuditLog.to_user_id == absent_user_id,
                RoutingAuditLog.action == "ROUTED",
            )
            .order_by(RoutingAuditLog.created_at.desc())
            .limit(200)
            .all()
        )

        # Deduplicate by document_id, keeping most recent
        seen_docs: Dict[int, RoutingAuditLog] = {}
        for entry in recent_assignments:
            if entry.document_id and entry.document_id not in seen_docs:
                seen_docs[entry.document_id] = entry

        if not seen_docs:
            return 0

        # If no explicit backup, find colleagues in same role
        if not backup_user_id:
            candidates = await self._get_load_balanced_user(self.org_id)
            if not candidates:
                logger.warning(
                    "No backup candidates found for absent user %d (org_id=%d)",
                    absent_user_id,
                    self.org_id,
                )
                return 0
            backup_user_id = candidates

        reassigned = 0
        for doc_id, audit_entry in seen_docs.items():
            await self.reassign(
                document_id=doc_id,
                from_user_id=absent_user_id,
                to_user_id=backup_user_id,
                reason=f"Auto-reassigned: user {absent_user_id} marked absent/PTO",
                loan_id=audit_entry.loan_id,
            )
            reassigned += 1

        logger.info(
            "Auto-reassigned %d documents from absent user %d to user %d (org_id=%d)",
            reassigned,
            absent_user_id,
            backup_user_id,
            self.org_id,
        )
        return reassigned

    async def rebalance_workload(self) -> Dict[str, Any]:
        """Rebalance document assignments across team members.

        Examines current workload distribution and moves items from
        overloaded users to underloaded ones. Only rebalances items
        assigned within the last 48 hours that have not yet been
        processed.

        Returns:
            Summary dict with rebalance statistics.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        # Get current assignment counts per user
        workload_rows = (
            self.db.query(
                RoutingAuditLog.to_user_id,
                func.count(RoutingAuditLog.id).label("doc_count"),
            )
            .filter(
                RoutingAuditLog.organization_id == self.org_id,
                RoutingAuditLog.action == "ROUTED",
                RoutingAuditLog.to_user_id.isnot(None),
                RoutingAuditLog.created_at >= cutoff,
                RoutingAuditLog.is_dry_run == False,
            )
            .group_by(RoutingAuditLog.to_user_id)
            .all()
        )

        if len(workload_rows) < 2:
            return {
                "rebalanced": 0,
                "reason": "Not enough users to rebalance",
            }

        workloads = {row.to_user_id: row.doc_count for row in workload_rows}
        avg_load = sum(workloads.values()) / len(workloads)
        threshold = avg_load * 1.5  # Flag users at >150% average

        overloaded = {uid: cnt for uid, cnt in workloads.items() if cnt > threshold}
        underloaded = {uid: cnt for uid, cnt in workloads.items() if cnt < avg_load * 0.7}

        if not overloaded or not underloaded:
            return {
                "rebalanced": 0,
                "reason": "Workload is within acceptable range",
                "avg_load": round(avg_load, 1),
                "workloads": workloads,
            }

        moved = 0
        for over_uid, over_count in sorted(overloaded.items(), key=lambda x: -x[1]):
            excess = int(over_count - avg_load)
            if excess <= 0:
                continue

            # Get recent assignments to this user
            recent = (
                self.db.query(RoutingAuditLog)
                .filter(
                    RoutingAuditLog.organization_id == self.org_id,
                    RoutingAuditLog.to_user_id == over_uid,
                    RoutingAuditLog.action == "ROUTED",
                    RoutingAuditLog.created_at >= cutoff,
                    RoutingAuditLog.is_dry_run == False,
                )
                .order_by(RoutingAuditLog.created_at.desc())
                .limit(excess)
                .all()
            )

            for entry in recent:
                if not underloaded:
                    break
                # Pick the least-loaded user
                target_uid = min(underloaded, key=underloaded.get)

                if entry.document_id:
                    await self.reassign(
                        document_id=entry.document_id,
                        from_user_id=over_uid,
                        to_user_id=target_uid,
                        reason="Workload rebalancing",
                        loan_id=entry.loan_id,
                    )
                    moved += 1

                    # Update tracking
                    underloaded[target_uid] = underloaded.get(target_uid, 0) + 1
                    if underloaded[target_uid] >= avg_load:
                        del underloaded[target_uid]

        self._record_audit(
            document_id=None,
            loan_id=None,
            action="REBALANCED",
            decision_reason=f"Rebalanced {moved} documents across team",
            event_data={
                "moved": moved,
                "avg_load": round(avg_load, 1),
                "overloaded_users": list(overloaded.keys()),
            },
            is_dry_run=False,
        )

        return {
            "rebalanced": moved,
            "avg_load": round(avg_load, 1),
            "overloaded_users": list(overloaded.keys()),
            "underloaded_users": list(underloaded.keys()) if underloaded else [],
        }

    # ------------------------------------------------------------------
    # DRY-RUN / TEST
    # ------------------------------------------------------------------

    async def test_routing(
        self,
        test_data: Dict[str, Any],
    ) -> RoutingDecision:
        """Test routing rules without executing assignment.

        Args:
            test_data: Simulated event_data dict with doc_type, loan_amount,
                       loan_type, etc.

        Returns:
            RoutingDecision with is_dry_run=True.
        """
        return await self.route_document(
            document_id=0,
            event_data=test_data,
            dry_run=True,
        )

    # ------------------------------------------------------------------
    # CONFLICT DETECTION
    # ------------------------------------------------------------------

    async def detect_rule_conflicts(self) -> List[Dict[str, Any]]:
        """Detect routing rules with overlapping conditions.

        Two rules conflict when they share the same priority level AND
        their conditions overlap (could both match the same document).

        Returns:
            List of conflict dicts with rule_a, rule_b, and overlap details.
        """
        rules = (
            self.db.query(RoutingRule)
            .filter(
                RoutingRule.organization_id == self.org_id,
                RoutingRule.is_active == True,
            )
            .order_by(RoutingRule.priority.asc())
            .all()
        )

        conflicts: List[Dict[str, Any]] = []
        for i, rule_a in enumerate(rules):
            for rule_b in rules[i + 1:]:
                if rule_a.priority != rule_b.priority:
                    continue

                overlap = self._find_condition_overlap(
                    rule_a.conditions or [], rule_b.conditions or []
                )
                if overlap:
                    conflict = {
                        "rule_a": {
                            "id": rule_a.id,
                            "name": rule_a.rule_name,
                            "priority": rule_a.priority,
                        },
                        "rule_b": {
                            "id": rule_b.id,
                            "name": rule_b.rule_name,
                            "priority": rule_b.priority,
                        },
                        "overlapping_fields": overlap,
                        "recommendation": (
                            f"Rules '{rule_a.rule_name}' and '{rule_b.rule_name}' "
                            f"share priority {rule_a.priority} with overlapping conditions "
                            f"on fields: {', '.join(overlap)}. Adjust priorities to "
                            f"establish deterministic ordering."
                        ),
                    }
                    conflicts.append(conflict)

                    # Record in audit log
                    self._record_audit(
                        document_id=None,
                        loan_id=None,
                        action="RULE_CONFLICT",
                        rule_id=rule_a.id,
                        rule_name=f"{rule_a.rule_name} vs {rule_b.rule_name}",
                        decision_reason=conflict["recommendation"],
                        event_data=conflict,
                        is_dry_run=False,
                    )

        return conflicts

    # ------------------------------------------------------------------
    # ANALYTICS
    # ------------------------------------------------------------------

    async def get_routing_analytics(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get routing analytics for the organization.

        Args:
            days: Lookback period in days.

        Returns:
            Dict with distribution, throughput, wait time, and rule
            effectiveness metrics.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # --- Assignment distribution across team ---
        distribution_rows = (
            self.db.query(
                RoutingAuditLog.to_user_id,
                func.count(RoutingAuditLog.id).label("count"),
            )
            .filter(
                RoutingAuditLog.organization_id == self.org_id,
                RoutingAuditLog.action == "ROUTED",
                RoutingAuditLog.to_user_id.isnot(None),
                RoutingAuditLog.created_at >= cutoff,
                RoutingAuditLog.is_dry_run == False,
            )
            .group_by(RoutingAuditLog.to_user_id)
            .all()
        )

        assignment_distribution = [
            {"user_id": row.to_user_id, "assignments": row.count}
            for row in distribution_rows
        ]
        total_assignments = sum(r["assignments"] for r in assignment_distribution)

        # --- Queue throughput ---
        queue_rows = (
            self.db.query(
                RoutingAuditLog.queue_name,
                RoutingAuditLog.action,
                func.count(RoutingAuditLog.id).label("count"),
            )
            .filter(
                RoutingAuditLog.organization_id == self.org_id,
                RoutingAuditLog.queue_name.isnot(None),
                RoutingAuditLog.action.in_(["QUEUED", "DEQUEUED"]),
                RoutingAuditLog.created_at >= cutoff,
                RoutingAuditLog.is_dry_run == False,
            )
            .group_by(RoutingAuditLog.queue_name, RoutingAuditLog.action)
            .all()
        )

        queue_throughput: Dict[str, Dict[str, int]] = defaultdict(lambda: {"queued": 0, "dequeued": 0})
        for row in queue_rows:
            action_key = "queued" if row.action == "QUEUED" else "dequeued"
            queue_throughput[row.queue_name][action_key] = row.count

        queue_stats = [
            {
                "queue_name": qname,
                "items_queued": stats["queued"],
                "items_processed": stats["dequeued"],
                "completion_rate": round(
                    (stats["dequeued"] / stats["queued"]) * 100, 1
                )
                if stats["queued"] > 0
                else 0,
            }
            for qname, stats in queue_throughput.items()
        ]

        # --- Rule effectiveness ---
        rule_rows = (
            self.db.query(
                RoutingAuditLog.rule_id,
                RoutingAuditLog.rule_name,
                func.count(RoutingAuditLog.id).label("match_count"),
            )
            .filter(
                RoutingAuditLog.organization_id == self.org_id,
                RoutingAuditLog.action == "ROUTED",
                RoutingAuditLog.rule_id.isnot(None),
                RoutingAuditLog.created_at >= cutoff,
                RoutingAuditLog.is_dry_run == False,
            )
            .group_by(RoutingAuditLog.rule_id, RoutingAuditLog.rule_name)
            .order_by(func.count(RoutingAuditLog.id).desc())
            .all()
        )

        rule_effectiveness = [
            {
                "rule_id": row.rule_id,
                "rule_name": row.rule_name,
                "match_count": row.match_count,
                "pct_of_total": round(
                    (row.match_count / total_assignments) * 100, 1
                )
                if total_assignments > 0
                else 0,
            }
            for row in rule_rows
        ]

        # --- Reassignment rate ---
        reassignment_count = (
            self.db.query(func.count(RoutingAuditLog.id))
            .filter(
                RoutingAuditLog.organization_id == self.org_id,
                RoutingAuditLog.action == "REASSIGNED",
                RoutingAuditLog.created_at >= cutoff,
                RoutingAuditLog.is_dry_run == False,
            )
            .scalar()
        ) or 0

        reassignment_rate = (
            round((reassignment_count / total_assignments) * 100, 1)
            if total_assignments > 0
            else 0
        )

        # --- Processing time by assignee (queue wait approximation) ---
        # Use time between QUEUED and DEQUEUED events for the same document
        wait_time_rows = self.db.execute(
            text("""
                SELECT
                    q.queue_name,
                    AVG(EXTRACT(EPOCH FROM (dq.created_at - q.created_at)) / 3600)
                        AS avg_wait_hours,
                    MAX(EXTRACT(EPOCH FROM (dq.created_at - q.created_at)) / 3600)
                        AS max_wait_hours,
                    COUNT(*) AS sample_count
                FROM smart_docs_routing_audit_log q
                JOIN smart_docs_routing_audit_log dq
                    ON dq.document_id = q.document_id
                    AND dq.organization_id = q.organization_id
                    AND dq.action = 'DEQUEUED'
                    AND dq.queue_name = q.queue_name
                WHERE q.organization_id = :org_id
                    AND q.action = 'QUEUED'
                    AND q.created_at >= :cutoff
                    AND q.is_dry_run = false
                GROUP BY q.queue_name
            """),
            {"org_id": self.org_id, "cutoff": cutoff},
        ).fetchall()

        queue_wait_times = [
            {
                "queue_name": row[0],
                "avg_wait_hours": round(float(row[1] or 0), 1),
                "max_wait_hours": round(float(row[2] or 0), 1),
                "sample_count": row[3],
            }
            for row in wait_time_rows
        ]

        return {
            "period_days": days,
            "total_routed": total_assignments,
            "total_reassigned": reassignment_count,
            "reassignment_rate_pct": reassignment_rate,
            "assignment_distribution": assignment_distribution,
            "queue_throughput": queue_stats,
            "queue_wait_times": queue_wait_times,
            "rule_effectiveness": rule_effectiveness,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_routing_audit_trail(
        self,
        document_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get routing audit trail entries.

        Args:
            document_id: Filter by document.
            loan_id: Filter by loan.
            limit: Max entries to return.

        Returns:
            List of audit log dicts ordered by most recent first.
        """
        query = self.db.query(RoutingAuditLog).filter(
            RoutingAuditLog.organization_id == self.org_id,
        )

        if document_id is not None:
            query = query.filter(RoutingAuditLog.document_id == document_id)
        if loan_id is not None:
            query = query.filter(RoutingAuditLog.loan_id == loan_id)

        entries = (
            query.order_by(RoutingAuditLog.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": e.id,
                "action": e.action,
                "document_id": e.document_id,
                "loan_id": e.loan_id,
                "rule_id": e.rule_id,
                "rule_name": e.rule_name,
                "rule_type": e.rule_type,
                "from_user_id": e.from_user_id,
                "to_user_id": e.to_user_id,
                "queue_name": e.queue_name,
                "decision_reason": e.decision_reason,
                "is_dry_run": e.is_dry_run,
                "created_by_user_id": e.created_by_user_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]

    # ------------------------------------------------------------------
    # RULE CRUD
    # ------------------------------------------------------------------

    async def create_rule(
        self,
        rule_name: str,
        rule_type: str,
        priority: int,
        conditions: List[Dict[str, Any]],
        target_type: str,
        target_config: Dict[str, Any],
    ) -> RoutingRule:
        """Create a new routing rule.

        Args:
            rule_name: Human-readable name.
            rule_type: One of RULE_TYPES.
            priority: Lower = evaluated first.
            conditions: List of condition dicts.
            target_type: One of TARGET_TYPES.
            target_config: Target-specific configuration.

        Returns:
            The created RoutingRule.

        Raises:
            ValueError: On invalid rule_type or target_type.
        """
        if rule_type not in RULE_TYPES:
            raise ValueError(f"Invalid rule_type '{rule_type}'. Must be one of {RULE_TYPES}")
        if target_type not in TARGET_TYPES:
            raise ValueError(f"Invalid target_type '{target_type}'. Must be one of {TARGET_TYPES}")

        # Validate condition operators
        for cond in conditions:
            op = cond.get("op")
            if op and op not in CONDITION_OPS:
                raise ValueError(f"Invalid condition operator '{op}'. Must be one of {CONDITION_OPS}")

        rule = RoutingRule(
            organization_id=self.org_id,
            rule_name=rule_name,
            rule_type=rule_type,
            priority=priority,
            conditions=conditions,
            target_type=target_type,
            target_config=target_config,
            is_active=True,
            is_system=False,
            created_by_user_id=self.user_id,
        )
        self.db.add(rule)
        self.db.flush()

        logger.info(
            "Created routing rule '%s' (id=%d, org_id=%d)",
            rule_name,
            rule.id,
            self.org_id,
        )
        return rule

    async def update_rule(
        self,
        rule_id: int,
        updates: Dict[str, Any],
    ) -> Optional[RoutingRule]:
        """Update an existing routing rule.

        Args:
            rule_id: Rule to update.
            updates: Dict of fields to update.

        Returns:
            Updated rule, or None if not found.
        """
        rule = (
            self.db.query(RoutingRule)
            .filter(
                RoutingRule.id == rule_id,
                RoutingRule.organization_id == self.org_id,
            )
            .first()
        )
        if not rule:
            return None

        allowed_fields = {
            "rule_name",
            "rule_type",
            "priority",
            "conditions",
            "target_type",
            "target_config",
            "is_active",
        }
        for field, value in updates.items():
            if field in allowed_fields:
                setattr(rule, field, value)

        rule.updated_at = datetime.now(timezone.utc)
        self.db.flush()

        logger.info(
            "Updated routing rule %d '%s' (org_id=%d)",
            rule_id,
            rule.rule_name,
            self.org_id,
        )
        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        """Soft-delete a routing rule by deactivating it.

        Args:
            rule_id: Rule to deactivate.

        Returns:
            True if rule was found and deactivated.
        """
        rule = (
            self.db.query(RoutingRule)
            .filter(
                RoutingRule.id == rule_id,
                RoutingRule.organization_id == self.org_id,
            )
            .first()
        )
        if not rule:
            return False

        rule.is_active = False
        rule.updated_at = datetime.now(timezone.utc)
        self.db.flush()

        logger.info(
            "Deactivated routing rule %d '%s' (org_id=%d)",
            rule_id,
            rule.rule_name,
            self.org_id,
        )
        return True

    async def list_rules(
        self,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        """List all routing rules for the org.

        Args:
            include_inactive: Whether to include deactivated rules.

        Returns:
            List of rule dicts.
        """
        query = self.db.query(RoutingRule).filter(
            RoutingRule.organization_id == self.org_id,
        )
        if not include_inactive:
            query = query.filter(RoutingRule.is_active == True)

        rules = query.order_by(RoutingRule.priority.asc()).all()

        return [
            {
                "id": r.id,
                "rule_name": r.rule_name,
                "rule_type": r.rule_type,
                "priority": r.priority,
                "conditions": r.conditions,
                "target_type": r.target_type,
                "target_config": r.target_config,
                "is_active": r.is_active,
                "is_system": r.is_system,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rules
        ]

    # ------------------------------------------------------------------
    # QUEUE CRUD
    # ------------------------------------------------------------------

    async def create_queue(
        self,
        queue_name: str,
        description: str = "",
        max_items: int = 50,
        avg_processing_time_hours: int = 4,
        assigned_users: Optional[List[int]] = None,
    ) -> ProcessingQueue:
        """Create a new processing queue.

        Args:
            queue_name: Unique queue name within org.
            description: Queue description.
            max_items: Capacity limit.
            avg_processing_time_hours: Expected hours per item.
            assigned_users: List of user IDs assigned to this queue.

        Returns:
            Created ProcessingQueue.

        Raises:
            ValueError: If queue name already exists.
        """
        existing = (
            self.db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.organization_id == self.org_id,
                ProcessingQueue.queue_name == queue_name,
            )
            .first()
        )
        if existing:
            raise ValueError(f"Queue '{queue_name}' already exists for this organization")

        queue = ProcessingQueue(
            organization_id=self.org_id,
            queue_name=queue_name,
            description=description,
            max_items=max_items,
            avg_processing_time_hours=avg_processing_time_hours,
            assigned_users=assigned_users or [],
            current_count=0,
            is_active=True,
        )
        self.db.add(queue)
        self.db.flush()

        logger.info(
            "Created processing queue '%s' (id=%d, org_id=%d)",
            queue_name,
            queue.id,
            self.org_id,
        )
        return queue

    async def update_queue_users(
        self,
        queue_name: str,
        user_ids: List[int],
    ) -> Optional[ProcessingQueue]:
        """Update the assigned users for a processing queue.

        Args:
            queue_name: Queue to update.
            user_ids: New list of assigned user IDs.

        Returns:
            Updated queue, or None if not found.
        """
        queue = (
            self.db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.organization_id == self.org_id,
                ProcessingQueue.queue_name == queue_name,
            )
            .first()
        )
        if not queue:
            return None

        queue.assigned_users = user_ids
        queue.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return queue

    # ------------------------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------------------------

    def _evaluate_conditions(
        self,
        conditions: List[Dict[str, Any]],
        event_data: Dict[str, Any],
    ) -> float:
        """Evaluate a list of conditions against event data.

        All conditions must match (AND logic). Returns a match score
        (number of conditions matched) or 0 if any condition fails.

        Args:
            conditions: List of condition dicts with field, op, value.
            event_data: Document/loan attributes.

        Returns:
            Score (float) representing match quality. 0 means no match.
        """
        if not conditions:
            # No conditions = matches everything (wildcard rule)
            return 0.1

        matched_count = 0
        for cond in conditions:
            field = cond.get("field", "")
            op = cond.get("op", "eq")
            expected = cond.get("value")
            actual = event_data.get(field)

            if actual is None:
                # Field not present in event data; condition cannot match
                return 0

            if not self._check_op(op, actual, expected):
                return 0

            matched_count += 1

        return float(matched_count)

    @staticmethod
    def _check_op(op: str, actual: Any, expected: Any) -> bool:
        """Check a single condition operator.

        Args:
            op: Operator string (eq, neq, in, not_in, gt, gte, lt, lte, contains).
            actual: Value from the event data.
            expected: Value from the rule condition.

        Returns:
            True if the condition passes.
        """
        try:
            if op == "eq":
                return actual == expected
            elif op == "neq":
                return actual != expected
            elif op == "in":
                return actual in (expected if isinstance(expected, (list, set, tuple)) else [expected])
            elif op == "not_in":
                return actual not in (expected if isinstance(expected, (list, set, tuple)) else [expected])
            elif op == "gt":
                return float(actual) > float(expected)
            elif op == "gte":
                return float(actual) >= float(expected)
            elif op == "lt":
                return float(actual) < float(expected)
            elif op == "lte":
                return float(actual) <= float(expected)
            elif op == "contains":
                return str(expected).lower() in str(actual).lower()
            else:
                logger.warning("Unknown condition operator: %s", op)
                return False
        except (TypeError, ValueError) as exc:
            logger.debug("Condition check failed for op=%s: %s", op, exc)
            return False

    def _detect_conflicts(
        self,
        matched_rules: List[Tuple[RoutingRule, float]],
    ) -> List[Dict[str, Any]]:
        """Detect conflicts among matched rules.

        Two rules conflict if they share the same priority level.

        Args:
            matched_rules: List of (rule, score) tuples.

        Returns:
            List of conflict detail dicts.
        """
        conflicts: List[Dict[str, Any]] = []
        by_priority: Dict[int, List[RoutingRule]] = defaultdict(list)
        for rule, _ in matched_rules:
            by_priority[rule.priority].append(rule)

        for priority, rules in by_priority.items():
            if len(rules) > 1:
                conflicts.append({
                    "priority": priority,
                    "conflicting_rules": [
                        {"id": r.id, "name": r.rule_name, "type": r.rule_type}
                        for r in rules
                    ],
                    "message": (
                        f"{len(rules)} rules matched at priority {priority}: "
                        f"{', '.join(r.rule_name for r in rules)}. "
                        f"First rule wins."
                    ),
                })

        return conflicts

    def _find_condition_overlap(
        self,
        conditions_a: List[Dict[str, Any]],
        conditions_b: List[Dict[str, Any]],
    ) -> List[str]:
        """Find overlapping condition fields between two rule condition sets.

        Args:
            conditions_a: Conditions from rule A.
            conditions_b: Conditions from rule B.

        Returns:
            List of field names that appear in both condition sets.
        """
        fields_a = {c.get("field") for c in conditions_a if c.get("field")}
        fields_b = {c.get("field") for c in conditions_b if c.get("field")}
        overlap = fields_a & fields_b

        # Only report as conflict if there is actual value overlap
        real_overlap: List[str] = []
        for field in overlap:
            vals_a = set()
            vals_b = set()
            for c in conditions_a:
                if c.get("field") == field:
                    v = c.get("value")
                    if isinstance(v, list):
                        vals_a.update(str(x) for x in v)
                    else:
                        vals_a.add(str(v))
            for c in conditions_b:
                if c.get("field") == field:
                    v = c.get("value")
                    if isinstance(v, list):
                        vals_b.update(str(x) for x in v)
                    else:
                        vals_b.add(str(v))

            if vals_a & vals_b:
                real_overlap.append(field)
            elif any(
                c.get("op") in ("gt", "gte", "lt", "lte")
                for c in conditions_a + conditions_b
                if c.get("field") == field
            ):
                # Range comparisons could overlap; flag for review
                real_overlap.append(field)

        return real_overlap

    async def _resolve_target(
        self,
        rule: RoutingRule,
        event_data: Dict[str, Any],
    ) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Resolve the final target user or queue for a rule match.

        Applies the rule's strategy (round-robin, load-balanced, etc.)
        to select a specific user when the target is a role or team.

        Args:
            rule: The matched routing rule.
            event_data: Document/loan attributes.

        Returns:
            Tuple of (user_id, user_name, queue_name).
        """
        config = rule.target_config or {}

        if rule.target_type == "QUEUE":
            queue_name = config.get("queue_name", "general_processing")
            return None, None, queue_name

        if rule.target_type == "USER":
            user_id = config.get("user_id")
            user_name = await self._get_user_name(user_id)
            return user_id, user_name, None

        # ROLE or TEAM: look up candidate users, then apply strategy
        candidates = await self._get_candidates(rule, event_data)

        if not candidates:
            # Fallback to general processing queue
            logger.warning(
                "No candidates found for rule '%s' (target=%s %s), "
                "falling back to general_processing queue",
                rule.rule_name,
                rule.target_type,
                config,
            )
            return None, None, "general_processing"

        # Apply routing strategy
        selected = await self._apply_strategy(rule.rule_type, candidates)
        return selected["user_id"], selected.get("user_name"), None

    async def _get_candidates(
        self,
        rule: RoutingRule,
        event_data: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Get candidate users for a role or team target.

        Args:
            rule: Rule with target_type ROLE or TEAM.
            event_data: Contains loan_id and other context.

        Returns:
            List of candidate dicts with user_id, first_name, last_name.
        """
        config = rule.target_config or {}

        if rule.target_type == "ROLE":
            role = config.get("role", "processor")
            query_template = ROLE_LOOKUP_QUERIES.get(role)
            if not query_template:
                # Fallback: generic role lookup
                query_template = """
                    SELECT u.id AS user_id, u.first_name, u.last_name
                    FROM users u
                    WHERE u.organization_id = :org_id
                        AND u.role = :target_role
                        AND u.is_active = true
                """
                params = {"org_id": self.org_id, "target_role": role}
            else:
                params = {
                    "org_id": self.org_id,
                    "loan_id": event_data.get("loan_id"),
                }

            try:
                rows = self.db.execute(text(query_template), params).fetchall()
                return [
                    {
                        "user_id": row[0],
                        "user_name": f"{row[1] or ''} {row[2] or ''}".strip()
                        if len(row) > 2
                        else str(row[0]),
                    }
                    for row in rows
                    if row[0] is not None
                ]
            except Exception as exc:
                logger.error(
                    "Failed to look up candidates for role '%s': %s", role, exc
                )
                return []

        elif rule.target_type == "TEAM":
            team_id = config.get("team_id")
            if not team_id:
                return []
            try:
                rows = self.db.execute(
                    text("""
                        SELECT u.id AS user_id, u.first_name, u.last_name
                        FROM users u
                        JOIN team_members tm ON tm.user_id = u.id
                        WHERE tm.team_id = :team_id
                            AND u.organization_id = :org_id
                            AND u.is_active = true
                    """),
                    {"team_id": team_id, "org_id": self.org_id},
                ).fetchall()
                return [
                    {
                        "user_id": row[0],
                        "user_name": f"{row[1] or ''} {row[2] or ''}".strip(),
                    }
                    for row in rows
                    if row[0] is not None
                ]
            except Exception as exc:
                logger.error(
                    "Failed to look up team %d members: %s", team_id, exc
                )
                return []

        return []

    async def _apply_strategy(
        self,
        rule_type: str,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply a routing strategy to select one user from candidates.

        Args:
            rule_type: AUTO_ASSIGN, ROUND_ROBIN, LOAD_BALANCED,
                       SKILL_BASED, ESCALATION.
            candidates: Non-empty list of candidate dicts.

        Returns:
            Selected candidate dict.
        """
        if not candidates:
            raise ValueError("No candidates to select from")

        if len(candidates) == 1 or rule_type == "AUTO_ASSIGN":
            return candidates[0]

        if rule_type == "ROUND_ROBIN":
            return await self._round_robin_select(candidates)

        if rule_type == "LOAD_BALANCED":
            return await self._load_balanced_select(candidates)

        if rule_type in ("SKILL_BASED", "ESCALATION"):
            # For skill-based and escalation, prefer users with fewer
            # recent assignments (proxy for availability / experience)
            return await self._load_balanced_select(candidates)

        # Default: first candidate
        return candidates[0]

    async def _round_robin_select(
        self,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Select next user in round-robin order.

        Uses the routing audit log to determine who was last assigned,
        then picks the next candidate in the list.
        """
        candidate_ids = [c["user_id"] for c in candidates]

        # Find the most recently assigned user among candidates
        last_assigned = (
            self.db.query(RoutingAuditLog.to_user_id)
            .filter(
                RoutingAuditLog.organization_id == self.org_id,
                RoutingAuditLog.action == "ROUTED",
                RoutingAuditLog.to_user_id.in_(candidate_ids),
                RoutingAuditLog.is_dry_run == False,
            )
            .order_by(RoutingAuditLog.created_at.desc())
            .first()
        )

        if last_assigned and last_assigned[0] in candidate_ids:
            last_idx = candidate_ids.index(last_assigned[0])
            next_idx = (last_idx + 1) % len(candidates)
            return candidates[next_idx]

        return candidates[0]

    async def _load_balanced_select(
        self,
        candidates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Select user with the lightest current workload."""
        candidate_ids = [c["user_id"] for c in candidates]
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        # Count recent assignments per candidate
        workload_rows = (
            self.db.query(
                RoutingAuditLog.to_user_id,
                func.count(RoutingAuditLog.id).label("count"),
            )
            .filter(
                RoutingAuditLog.organization_id == self.org_id,
                RoutingAuditLog.action == "ROUTED",
                RoutingAuditLog.to_user_id.in_(candidate_ids),
                RoutingAuditLog.created_at >= cutoff,
                RoutingAuditLog.is_dry_run == False,
            )
            .group_by(RoutingAuditLog.to_user_id)
            .all()
        )

        workloads = {row.to_user_id: row.count for row in workload_rows}

        # Select candidate with fewest assignments (default 0 for untracked)
        return min(candidates, key=lambda c: workloads.get(c["user_id"], 0))

    async def _get_load_balanced_user(self, org_id: int) -> Optional[int]:
        """Get the user with lightest workload across the org.

        Used as fallback when no specific candidates are identified.

        Returns:
            user_id of lightest-loaded active user, or None.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        row = self.db.execute(
            text("""
                SELECT u.id
                FROM users u
                LEFT JOIN (
                    SELECT to_user_id, COUNT(*) AS cnt
                    FROM smart_docs_routing_audit_log
                    WHERE organization_id = :org_id
                        AND action = 'ROUTED'
                        AND created_at >= :cutoff
                        AND is_dry_run = false
                    GROUP BY to_user_id
                ) w ON w.to_user_id = u.id
                WHERE u.organization_id = :org_id
                    AND u.is_active = true
                    AND u.role IN ('processor', 'loan_processor', 'senior_processor')
                ORDER BY COALESCE(w.cnt, 0) ASC
                LIMIT 1
            """),
            {"org_id": org_id, "cutoff": cutoff},
        ).fetchone()

        return row[0] if row else None

    async def _get_user_name(self, user_id: Optional[int]) -> Optional[str]:
        """Look up user display name by ID."""
        if not user_id:
            return None
        try:
            row = self.db.execute(
                text("""
                    SELECT first_name, last_name FROM users WHERE id = :uid
                """),
                {"uid": user_id},
            ).fetchone()
            if row:
                return f"{row[0] or ''} {row[1] or ''}".strip()
        except Exception as exc:
            logger.debug("Could not look up user %d: %s", user_id, exc)
        return None

    async def _assign_to_queue(
        self,
        document_id: int,
        queue_name: str,
    ) -> None:
        """Increment queue counter when assigning a document to a queue.

        Args:
            document_id: Document being queued.
            queue_name: Target queue.
        """
        queue = (
            self.db.query(ProcessingQueue)
            .filter(
                ProcessingQueue.organization_id == self.org_id,
                ProcessingQueue.queue_name == queue_name,
                ProcessingQueue.is_active == True,
            )
            .first()
        )
        if not queue:
            logger.warning(
                "Queue '%s' not found for org %d; skipping queue increment",
                queue_name,
                self.org_id,
            )
            return

        if (queue.current_count or 0) >= queue.max_items:
            logger.warning(
                "Queue '%s' at capacity (%d/%d); document %d queued anyway",
                queue_name,
                queue.current_count,
                queue.max_items,
                document_id,
            )

        queue.current_count = (queue.current_count or 0) + 1
        self.db.flush()

    async def _send_assignment_notification(
        self,
        user_id: int,
        document_id: int,
        loan_id: Optional[int],
        priority: str,
        due_at: datetime,
        rule_name: str,
    ) -> None:
        """Send in-app notification to the assigned user.

        Uses the Smart Docs notification model (DocNotification) if
        available. Gracefully degrades if the notification table is
        not yet created.

        Args:
            user_id: Assignee.
            document_id: Document assigned.
            loan_id: Associated loan.
            priority: Priority level string.
            due_at: SLA due date.
            rule_name: Name of the rule that triggered assignment.
        """
        try:
            from database.models.doc_notification import DocNotification

            severity_map = {
                "critical": "critical",
                "high": "urgent",
                "medium": "warning",
                "low": "info",
                "normal": "info",
            }

            notification = DocNotification(
                organization_id=self.org_id,
                user_id=user_id,
                loan_id=loan_id,
                notification_type="DOC_ASSIGNED",
                severity=severity_map.get(priority, "info"),
                title=f"Document assigned to you",
                body=(
                    f"A document (ID: {document_id}) has been routed to you "
                    f"via rule '{rule_name}'. Priority: {priority}. "
                    f"Due by: {due_at.strftime('%m/%d/%Y %H:%M UTC')}."
                ),
                action_url=f"/smart-docs/documents/{document_id}",
                action_label="Review Document",
                metadata={
                    "document_id": document_id,
                    "rule_name": rule_name,
                    "priority": priority,
                    "due_at": due_at.isoformat(),
                },
                delivery_channels=["in_app", "email"],
            )
            self.db.add(notification)
            self.db.flush()
        except Exception as exc:
            # Notification is non-critical; log and continue
            logger.warning(
                "Could not create assignment notification for user %d: %s",
                user_id,
                exc,
            )

    def _record_audit(
        self,
        document_id: Optional[int],
        loan_id: Optional[int],
        action: str,
        decision_reason: str = "",
        event_data: Optional[Dict[str, Any]] = None,
        is_dry_run: bool = False,
        rule_id: Optional[int] = None,
        rule_name: Optional[str] = None,
        rule_type: Optional[str] = None,
        from_user_id: Optional[int] = None,
        to_user_id: Optional[int] = None,
        queue_name: Optional[str] = None,
    ) -> None:
        """Write an entry to the routing audit log.

        Args:
            document_id: Document involved.
            loan_id: Loan involved.
            action: Action type (ROUTED, REASSIGNED, QUEUED, etc.).
            decision_reason: Human-readable reason.
            event_data: Full event snapshot.
            is_dry_run: Whether this was a test run.
            rule_id: Matched rule ID.
            rule_name: Matched rule name.
            rule_type: Matched rule type.
            from_user_id: Previous assignee (for reassignments).
            to_user_id: New assignee.
            queue_name: Queue involved.
        """
        try:
            entry = RoutingAuditLog(
                organization_id=self.org_id,
                document_id=document_id,
                loan_id=loan_id,
                action=action,
                rule_id=rule_id,
                rule_name=rule_name,
                rule_type=rule_type,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                queue_name=queue_name,
                event_data=event_data,
                decision_reason=decision_reason,
                is_dry_run=is_dry_run,
                created_by_user_id=self.user_id,
            )
            self.db.add(entry)
            self.db.flush()
        except Exception as exc:
            logger.error("Failed to write routing audit log: %s", exc)
