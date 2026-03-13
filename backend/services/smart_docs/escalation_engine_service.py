"""
Smart Docs Escalation Engine Service

Rule-based escalation system for document collection and compliance events.
Supports multi-level escalation chains, acknowledgment tracking,
auto-resolution, cooldown suppression, and analytics.

Trigger types:
    DOC_OVERDUE            - Document request overdue by N days
    CONDITION_OVERDUE      - Underwriting condition past deadline
    SLA_BREACH             - SLA timer breached or imminent
    FRAUD_DETECTED         - Fraud detection flagged a document
    INCOME_DISCREPANCY     - Income variance exceeds threshold
    APPROVAL_TIMEOUT       - Document approval pending too long
    BORROWER_UNRESPONSIVE  - Borrower unresponsive after N follow-up attempts

Escalation chain example:
    [
        {"level": 1, "notify": "loan_officer",       "after_hours": 0},
        {"level": 2, "notify": "processor_manager",  "after_hours": 24},
        {"level": 3, "notify": "branch_manager",     "after_hours": 48},
        {"level": 4, "notify": "vp_operations",      "after_hours": 72},
    ]

Usage:
    from services.smart_docs.escalation_engine_service import EscalationEngineService

    engine = EscalationEngineService(db=db, org_id=1)
    await engine.evaluate_triggers(loan_id=42)
    dashboard = await engine.get_dashboard_data()
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, text, and_, or_, case
from sqlalchemy.orm import Session

from database.models.escalation_rule import EscalationRule, EscalationEvent

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Default cooldown: do not re-fire the same trigger_type + loan_id within this window
DEFAULT_COOLDOWN_HOURS = 24

# Supported trigger types
TRIGGER_TYPES = {
    "DOC_OVERDUE",
    "CONDITION_OVERDUE",
    "SLA_BREACH",
    "FRAUD_DETECTED",
    "INCOME_DISCREPANCY",
    "APPROVAL_TIMEOUT",
    "BORROWER_UNRESPONSIVE",
}

# Role-to-relationship map used when resolving "who to notify" from a chain step.
# Each key is a logical role; the value describes how to look up the user.
ROLE_LOOKUP_QUERIES: Dict[str, str] = {
    "loan_officer": """
        SELECT l.loan_officer_id AS user_id
        FROM loans l
        WHERE l.id = :loan_id AND l.organization_id = :org_id
    """,
    "processor": """
        SELECT ltm.user_id
        FROM loan_team_members ltm
        WHERE ltm.loan_id = :loan_id AND ltm.role = 'processor'
        LIMIT 1
    """,
    "processor_manager": """
        SELECT u.reports_to_id AS user_id
        FROM loan_team_members ltm
        JOIN users u ON u.id = ltm.user_id
        WHERE ltm.loan_id = :loan_id AND ltm.role = 'processor'
        LIMIT 1
    """,
    "branch_manager": """
        SELECT b.manager_id AS user_id
        FROM loans l
        JOIN users lo ON lo.id = l.loan_officer_id
        JOIN branches b ON b.id = lo.branch_id
        WHERE l.id = :loan_id AND l.organization_id = :org_id
        LIMIT 1
    """,
    "vp_operations": """
        SELECT u.id AS user_id
        FROM users u
        WHERE u.organization_id = :org_id AND u.role = 'vp_operations'
        LIMIT 1
    """,
    "underwriter": """
        SELECT ltm.user_id
        FROM loan_team_members ltm
        WHERE ltm.loan_id = :loan_id AND ltm.role = 'underwriter'
        LIMIT 1
    """,
}

# Default system rules seeded per-org on first access
DEFAULT_SYSTEM_RULES: List[Dict[str, Any]] = [
    {
        "rule_name": "Document Overdue - Standard",
        "trigger_type": "DOC_OVERDUE",
        "trigger_config": {"threshold_days": 5, "severity": "medium"},
        "escalation_chain": [
            {"level": 1, "notify": "loan_officer", "after_hours": 0},
            {"level": 2, "notify": "processor_manager", "after_hours": 24},
            {"level": 3, "notify": "branch_manager", "after_hours": 72},
        ],
    },
    {
        "rule_name": "Fraud Alert - Immediate",
        "trigger_type": "FRAUD_DETECTED",
        "trigger_config": {"min_risk_score": 70, "severity": "critical"},
        "escalation_chain": [
            {"level": 1, "notify": "loan_officer", "after_hours": 0},
            {"level": 2, "notify": "branch_manager", "after_hours": 0},
            {"level": 3, "notify": "vp_operations", "after_hours": 4},
        ],
    },
    {
        "rule_name": "SLA Breach Warning",
        "trigger_type": "SLA_BREACH",
        "trigger_config": {"warn_hours_before": 8, "severity": "high"},
        "escalation_chain": [
            {"level": 1, "notify": "processor", "after_hours": 0},
            {"level": 2, "notify": "loan_officer", "after_hours": 4},
            {"level": 3, "notify": "processor_manager", "after_hours": 12},
        ],
    },
    {
        "rule_name": "Borrower Unresponsive",
        "trigger_type": "BORROWER_UNRESPONSIVE",
        "trigger_config": {"min_attempts": 3, "lookback_days": 14, "severity": "medium"},
        "escalation_chain": [
            {"level": 1, "notify": "loan_officer", "after_hours": 0},
            {"level": 2, "notify": "processor_manager", "after_hours": 48},
        ],
    },
    {
        "rule_name": "Income Discrepancy",
        "trigger_type": "INCOME_DISCREPANCY",
        "trigger_config": {"variance_pct": 25, "severity": "high"},
        "escalation_chain": [
            {"level": 1, "notify": "underwriter", "after_hours": 0},
            {"level": 2, "notify": "loan_officer", "after_hours": 4},
            {"level": 3, "notify": "branch_manager", "after_hours": 24},
        ],
    },
    {
        "rule_name": "Approval Timeout",
        "trigger_type": "APPROVAL_TIMEOUT",
        "trigger_config": {"timeout_hours": 48, "severity": "medium"},
        "escalation_chain": [
            {"level": 1, "notify": "processor", "after_hours": 0},
            {"level": 2, "notify": "processor_manager", "after_hours": 12},
        ],
    },
    {
        "rule_name": "Condition Overdue",
        "trigger_type": "CONDITION_OVERDUE",
        "trigger_config": {"threshold_days": 3, "severity": "high"},
        "escalation_chain": [
            {"level": 1, "notify": "loan_officer", "after_hours": 0},
            {"level": 2, "notify": "processor_manager", "after_hours": 24},
            {"level": 3, "notify": "branch_manager", "after_hours": 48},
        ],
    },
]


# =============================================================================
# SERVICE
# =============================================================================

class EscalationEngineService:
    """Async escalation engine with org-level isolation.

    All queries are scoped to ``self.org_id`` to enforce multi-tenant
    boundaries at the service layer.
    """

    def __init__(self, db: Session, org_id: int, user_id: Optional[int] = None):
        self.db = db
        self.org_id = org_id
        self.user_id = user_id

    # ------------------------------------------------------------------
    # SYSTEM RULE SEEDING
    # ------------------------------------------------------------------

    async def ensure_system_rules(self) -> int:
        """Seed default system rules for this org if none exist.

        Returns the number of rules created (0 if already seeded).
        """
        existing_count = (
            self.db.query(func.count(EscalationRule.id))
            .filter(
                EscalationRule.organization_id == self.org_id,
                EscalationRule.is_system == True,
            )
            .scalar()
        )
        if existing_count > 0:
            return 0

        created = 0
        for rule_def in DEFAULT_SYSTEM_RULES:
            rule = EscalationRule(
                organization_id=self.org_id,
                rule_name=rule_def["rule_name"],
                trigger_type=rule_def["trigger_type"],
                trigger_config=rule_def["trigger_config"],
                escalation_chain=rule_def["escalation_chain"],
                is_active=True,
                is_system=True,
            )
            self.db.add(rule)
            created += 1

        self.db.flush()
        logger.info("Seeded %d system escalation rules for org %d", created, self.org_id)
        return created

    # ------------------------------------------------------------------
    # RULE CRUD
    # ------------------------------------------------------------------

    async def create_rule(
        self,
        rule_name: str,
        trigger_type: str,
        trigger_config: Dict[str, Any],
        escalation_chain: List[Dict[str, Any]],
    ) -> EscalationRule:
        """Create a custom (non-system) escalation rule."""
        if trigger_type not in TRIGGER_TYPES:
            raise ValueError(f"Unknown trigger_type: {trigger_type}")
        self._validate_chain(escalation_chain)

        rule = EscalationRule(
            organization_id=self.org_id,
            rule_name=rule_name,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            escalation_chain=escalation_chain,
            is_active=True,
            is_system=False,
        )
        self.db.add(rule)
        self.db.flush()
        logger.info("Created escalation rule %d (%s) for org %d", rule.id, rule_name, self.org_id)
        return rule

    async def update_rule(
        self,
        rule_id: int,
        *,
        rule_name: Optional[str] = None,
        trigger_config: Optional[Dict[str, Any]] = None,
        escalation_chain: Optional[List[Dict[str, Any]]] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[EscalationRule]:
        """Update an existing rule. System rules can be deactivated but not deleted."""
        rule = self._get_rule(rule_id)
        if rule is None:
            return None

        if rule_name is not None:
            rule.rule_name = rule_name
        if trigger_config is not None:
            rule.trigger_config = trigger_config
        if escalation_chain is not None:
            self._validate_chain(escalation_chain)
            rule.escalation_chain = escalation_chain
        if is_active is not None:
            rule.is_active = is_active

        self.db.flush()
        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        """Delete a custom rule. System rules cannot be deleted (deactivate instead)."""
        rule = self._get_rule(rule_id)
        if rule is None:
            return False
        if rule.is_system:
            raise ValueError("System rules cannot be deleted; deactivate them instead")

        self.db.delete(rule)
        self.db.flush()
        logger.info("Deleted escalation rule %d for org %d", rule_id, self.org_id)
        return True

    async def list_rules(
        self,
        trigger_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[EscalationRule]:
        """List escalation rules for this org."""
        query = self.db.query(EscalationRule).filter(
            EscalationRule.organization_id == self.org_id
        )
        if trigger_type:
            query = query.filter(EscalationRule.trigger_type == trigger_type)
        if active_only:
            query = query.filter(EscalationRule.is_active == True)
        return query.order_by(EscalationRule.trigger_type, EscalationRule.rule_name).all()

    # ------------------------------------------------------------------
    # TRIGGER EVALUATION
    # ------------------------------------------------------------------

    async def fire_trigger(
        self,
        trigger_type: str,
        loan_id: int,
        trigger_details: Optional[Dict[str, Any]] = None,
        *,
        force: bool = False,
    ) -> Optional[EscalationEvent]:
        """Fire an escalation trigger for a loan.

        Evaluates matching active rules and creates an EscalationEvent
        if the trigger_config criteria are met and the cooldown has elapsed.

        Args:
            trigger_type: One of TRIGGER_TYPES.
            loan_id: The loan to escalate.
            trigger_details: Contextual data (e.g. document_id, variance_pct).
            force: If True, bypass cooldown suppression.

        Returns:
            The created EscalationEvent, or None if suppressed / no matching rule.
        """
        if trigger_type not in TRIGGER_TYPES:
            logger.warning("Unknown trigger type: %s", trigger_type)
            return None

        # Find matching active rules
        rules = (
            self.db.query(EscalationRule)
            .filter(
                EscalationRule.organization_id == self.org_id,
                EscalationRule.trigger_type == trigger_type,
                EscalationRule.is_active == True,
            )
            .all()
        )

        if not rules:
            logger.debug("No active rules for trigger %s in org %d", trigger_type, self.org_id)
            return None

        # Use the first matching rule (rules are org-specific; system + custom)
        rule = rules[0]

        # Cooldown suppression check
        if not force and await self._is_suppressed(trigger_type, loan_id, rule.id):
            logger.debug(
                "Escalation suppressed (cooldown) for %s on loan %d", trigger_type, loan_id
            )
            return None

        # Resolve first-level notification target
        chain = rule.escalation_chain or []
        first_step = chain[0] if chain else None
        escalated_to_user_id = None
        if first_step:
            escalated_to_user_id = await self._resolve_notify_target(
                first_step.get("notify", "loan_officer"), loan_id
            )

        # Calculate next escalation time
        next_at = None
        if len(chain) > 1:
            second_step = chain[1]
            after_hours = second_step.get("after_hours", 24)
            next_at = datetime.now(timezone.utc) + timedelta(hours=after_hours)

        event = EscalationEvent(
            organization_id=self.org_id,
            rule_id=rule.id,
            loan_id=loan_id,
            trigger_type=trigger_type,
            trigger_details=trigger_details or {},
            current_level=1,
            status="ACTIVE",
            escalated_to_user_id=escalated_to_user_id,
            next_escalation_at=next_at,
        )
        self.db.add(event)
        self.db.flush()

        # Send notification for level 1
        await self._send_escalation_notification(event, rule, level=1)

        logger.info(
            "Escalation event %d created: %s for loan %d (rule %d, level 1)",
            event.id, trigger_type, loan_id, rule.id,
        )
        return event

    async def evaluate_triggers(self, loan_id: int) -> List[EscalationEvent]:
        """Evaluate all applicable triggers for a loan.

        Checks DOC_OVERDUE, SLA_BREACH, BORROWER_UNRESPONSIVE, and
        APPROVAL_TIMEOUT against live data and fires triggers as needed.

        This is the primary method called by scheduled tasks.
        """
        created_events: List[EscalationEvent] = []

        # --- DOC_OVERDUE ---
        doc_overdue_events = await self._evaluate_doc_overdue(loan_id)
        created_events.extend(doc_overdue_events)

        # --- SLA_BREACH ---
        sla_events = await self._evaluate_sla_breach(loan_id)
        created_events.extend(sla_events)

        # --- BORROWER_UNRESPONSIVE ---
        unresponsive_events = await self._evaluate_borrower_unresponsive(loan_id)
        created_events.extend(unresponsive_events)

        # --- APPROVAL_TIMEOUT ---
        approval_events = await self._evaluate_approval_timeout(loan_id)
        created_events.extend(approval_events)

        # --- CONDITION_OVERDUE ---
        condition_events = await self._evaluate_condition_overdue(loan_id)
        created_events.extend(condition_events)

        return created_events

    # ------------------------------------------------------------------
    # ESCALATION PROGRESSION
    # ------------------------------------------------------------------

    async def process_pending_escalations(self) -> int:
        """Advance escalations whose next_escalation_at has passed.

        Called by a periodic task (e.g. every 15 minutes).  For each
        event that is due, moves to the next chain level, notifies the
        new target, and sets the next timer.

        Returns the number of events advanced.
        """
        now = datetime.now(timezone.utc)

        due_events = (
            self.db.query(EscalationEvent)
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.status == "ACTIVE",
                EscalationEvent.next_escalation_at != None,
                EscalationEvent.next_escalation_at <= now,
            )
            .all()
        )

        advanced_count = 0
        for event in due_events:
            rule = self._get_rule(event.rule_id)
            if rule is None:
                continue

            chain = rule.escalation_chain or []
            next_level = event.current_level + 1

            if next_level > len(chain):
                # No more levels — mark as the final level (stays active until resolved)
                event.next_escalation_at = None
                self.db.flush()
                continue

            step = chain[next_level - 1]  # 0-indexed

            # Resolve new target
            new_target = await self._resolve_notify_target(
                step.get("notify", "loan_officer"), event.loan_id
            )

            event.current_level = next_level
            event.escalated_to_user_id = new_target

            # Set next timer
            if next_level < len(chain):
                following_step = chain[next_level]  # next after current
                after_hours = following_step.get("after_hours", 24)
                event.next_escalation_at = now + timedelta(hours=after_hours)
            else:
                event.next_escalation_at = None  # final level

            self.db.flush()

            await self._send_escalation_notification(event, rule, level=next_level)
            advanced_count += 1

            logger.info(
                "Escalation event %d advanced to level %d (loan %d)",
                event.id, next_level, event.loan_id,
            )

        return advanced_count

    # ------------------------------------------------------------------
    # ACKNOWLEDGMENT & RESOLUTION
    # ------------------------------------------------------------------

    async def acknowledge_event(
        self,
        event_id: int,
        user_id: int,
    ) -> Optional[EscalationEvent]:
        """Acknowledge an escalation event to pause further escalation."""
        event = self._get_event(event_id)
        if event is None:
            return None
        if event.status != "ACTIVE":
            return event  # already resolved/expired

        event.acknowledged_at = datetime.now(timezone.utc)
        event.acknowledged_by_user_id = user_id
        # Pause automatic escalation once acknowledged
        event.next_escalation_at = None
        self.db.flush()

        logger.info("Escalation event %d acknowledged by user %d", event_id, user_id)
        return event

    async def resolve_event(
        self,
        event_id: int,
        user_id: int,
        resolution_notes: Optional[str] = None,
    ) -> Optional[EscalationEvent]:
        """Resolve an escalation event."""
        event = self._get_event(event_id)
        if event is None:
            return None
        if event.status == "RESOLVED":
            return event

        event.status = "RESOLVED"
        event.resolved_at = datetime.now(timezone.utc)
        event.resolved_by_user_id = user_id
        event.resolution_notes = resolution_notes
        event.next_escalation_at = None
        self.db.flush()

        logger.info("Escalation event %d resolved by user %d", event_id, user_id)
        return event

    async def suppress_event(
        self,
        event_id: int,
        user_id: int,
        reason: Optional[str] = None,
    ) -> Optional[EscalationEvent]:
        """Suppress an escalation (mark it as intentionally ignored)."""
        event = self._get_event(event_id)
        if event is None:
            return None

        event.status = "SUPPRESSED"
        event.resolved_at = datetime.now(timezone.utc)
        event.resolved_by_user_id = user_id
        event.resolution_notes = reason or "Manually suppressed"
        event.next_escalation_at = None
        self.db.flush()

        logger.info("Escalation event %d suppressed by user %d", event_id, user_id)
        return event

    # ------------------------------------------------------------------
    # AUTO-RESOLUTION
    # ------------------------------------------------------------------

    async def auto_resolve_for_loan(
        self,
        loan_id: int,
        trigger_type: Optional[str] = None,
        resolution_notes: str = "Auto-resolved: underlying issue fixed",
    ) -> int:
        """Auto-resolve active escalations when the underlying issue is fixed.

        For example, when a missing document is uploaded, call this with
        trigger_type='DOC_OVERDUE' to close related escalations.

        Returns the number of events resolved.
        """
        query = self.db.query(EscalationEvent).filter(
            EscalationEvent.organization_id == self.org_id,
            EscalationEvent.loan_id == loan_id,
            EscalationEvent.status == "ACTIVE",
        )
        if trigger_type:
            query = query.filter(EscalationEvent.trigger_type == trigger_type)

        events = query.all()
        now = datetime.now(timezone.utc)
        count = 0
        for event in events:
            event.status = "RESOLVED"
            event.resolved_at = now
            event.resolution_notes = resolution_notes
            event.next_escalation_at = None
            count += 1

        if count > 0:
            self.db.flush()
            logger.info(
                "Auto-resolved %d escalation(s) for loan %d (trigger=%s)",
                count, loan_id, trigger_type or "ALL",
            )
        return count

    # ------------------------------------------------------------------
    # BULK OPERATIONS
    # ------------------------------------------------------------------

    async def bulk_resolve_for_loan(
        self,
        loan_id: int,
        user_id: int,
        resolution_notes: Optional[str] = None,
    ) -> int:
        """Resolve ALL active escalations for a loan."""
        events = (
            self.db.query(EscalationEvent)
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.loan_id == loan_id,
                EscalationEvent.status == "ACTIVE",
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        count = 0
        for event in events:
            event.status = "RESOLVED"
            event.resolved_at = now
            event.resolved_by_user_id = user_id
            event.resolution_notes = resolution_notes or "Bulk resolved"
            event.next_escalation_at = None
            count += 1

        if count > 0:
            self.db.flush()
        logger.info("Bulk-resolved %d escalations for loan %d", count, loan_id)
        return count

    async def expire_stale_events(self, max_age_days: int = 30) -> int:
        """Expire active escalations older than max_age_days.

        Prevents zombie escalations from accumulating indefinitely.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        events = (
            self.db.query(EscalationEvent)
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.status == "ACTIVE",
                EscalationEvent.created_at < cutoff,
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        count = 0
        for event in events:
            event.status = "EXPIRED"
            event.resolved_at = now
            event.resolution_notes = f"Auto-expired after {max_age_days} days"
            event.next_escalation_at = None
            count += 1

        if count > 0:
            self.db.flush()
        logger.info("Expired %d stale escalation events for org %d", count, self.org_id)
        return count

    # ------------------------------------------------------------------
    # QUERY / DASHBOARD
    # ------------------------------------------------------------------

    async def get_active_events(
        self,
        loan_id: Optional[int] = None,
        trigger_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[EscalationEvent]:
        """Get active escalation events, optionally filtered."""
        query = self.db.query(EscalationEvent).filter(
            EscalationEvent.organization_id == self.org_id,
            EscalationEvent.status == "ACTIVE",
        )
        if loan_id is not None:
            query = query.filter(EscalationEvent.loan_id == loan_id)
        if trigger_type is not None:
            query = query.filter(EscalationEvent.trigger_type == trigger_type)

        return (
            query
            .order_by(EscalationEvent.created_at.desc())
            .limit(limit)
            .all()
        )

    async def get_event_detail(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed info for a single escalation event including rule data."""
        event = self._get_event(event_id)
        if event is None:
            return None

        rule = self._get_rule(event.rule_id)
        chain = rule.escalation_chain if rule else []

        return {
            "id": event.id,
            "loan_id": event.loan_id,
            "trigger_type": event.trigger_type,
            "trigger_details": event.trigger_details,
            "current_level": event.current_level,
            "max_level": len(chain),
            "status": event.status,
            "escalated_to_user_id": event.escalated_to_user_id,
            "acknowledged_at": _iso(event.acknowledged_at),
            "acknowledged_by_user_id": event.acknowledged_by_user_id,
            "resolved_at": _iso(event.resolved_at),
            "resolved_by_user_id": event.resolved_by_user_id,
            "resolution_notes": event.resolution_notes,
            "next_escalation_at": _iso(event.next_escalation_at),
            "created_at": _iso(event.created_at),
            "rule": {
                "id": rule.id,
                "rule_name": rule.rule_name,
                "escalation_chain": chain,
            } if rule else None,
            "sla": self._calculate_event_sla(event),
        }

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Aggregate data for the escalation dashboard.

        Returns counts, breakdowns by trigger type, recent events, and
        SLA metrics for the org.
        """
        now = datetime.now(timezone.utc)

        # Active counts by trigger type
        type_counts = (
            self.db.query(
                EscalationEvent.trigger_type,
                func.count(EscalationEvent.id).label("count"),
            )
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.status == "ACTIVE",
            )
            .group_by(EscalationEvent.trigger_type)
            .all()
        )

        # Total active
        total_active = sum(row.count for row in type_counts)

        # Unacknowledged count
        unacknowledged = (
            self.db.query(func.count(EscalationEvent.id))
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.status == "ACTIVE",
                EscalationEvent.acknowledged_at == None,
            )
            .scalar()
        ) or 0

        # Overdue escalations (next_escalation_at in the past)
        overdue = (
            self.db.query(func.count(EscalationEvent.id))
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.status == "ACTIVE",
                EscalationEvent.next_escalation_at != None,
                EscalationEvent.next_escalation_at < now,
            )
            .scalar()
        ) or 0

        # Resolution stats (last 30 days)
        thirty_days_ago = now - timedelta(days=30)
        resolution_stats = self.db.query(
            func.count(EscalationEvent.id).label("resolved_count"),
            func.avg(
                func.extract("epoch", EscalationEvent.resolved_at - EscalationEvent.created_at) / 3600
            ).label("avg_resolution_hours"),
        ).filter(
            EscalationEvent.organization_id == self.org_id,
            EscalationEvent.status == "RESOLVED",
            EscalationEvent.resolved_at >= thirty_days_ago,
        ).first()

        # Recent events (last 10)
        recent = (
            self.db.query(EscalationEvent)
            .filter(EscalationEvent.organization_id == self.org_id)
            .order_by(EscalationEvent.created_at.desc())
            .limit(10)
            .all()
        )

        return {
            "total_active": total_active,
            "unacknowledged": unacknowledged,
            "overdue_escalations": overdue,
            "by_trigger_type": {
                row.trigger_type: row.count for row in type_counts
            },
            "resolution_stats_30d": {
                "resolved_count": resolution_stats.resolved_count if resolution_stats else 0,
                "avg_resolution_hours": (
                    round(float(resolution_stats.avg_resolution_hours), 1)
                    if resolution_stats and resolution_stats.avg_resolution_hours
                    else None
                ),
            },
            "recent_events": [
                {
                    "id": e.id,
                    "loan_id": e.loan_id,
                    "trigger_type": e.trigger_type,
                    "current_level": e.current_level,
                    "status": e.status,
                    "created_at": _iso(e.created_at),
                }
                for e in recent
            ],
        }

    # ------------------------------------------------------------------
    # ANALYTICS
    # ------------------------------------------------------------------

    async def get_analytics(
        self,
        days: int = 90,
    ) -> Dict[str, Any]:
        """Escalation analytics: frequency, resolution times, repeat offenders.

        Args:
            days: Lookback period in days.

        Returns:
            Dict with frequency_by_type, avg_resolution_by_type,
            repeat_loans (loans with >2 escalations), and level_distribution.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Frequency by type
        frequency = (
            self.db.query(
                EscalationEvent.trigger_type,
                func.count(EscalationEvent.id).label("count"),
            )
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.created_at >= cutoff,
            )
            .group_by(EscalationEvent.trigger_type)
            .order_by(func.count(EscalationEvent.id).desc())
            .all()
        )

        # Average resolution time by type (hours)
        resolution_by_type = (
            self.db.query(
                EscalationEvent.trigger_type,
                func.avg(
                    func.extract("epoch", EscalationEvent.resolved_at - EscalationEvent.created_at) / 3600
                ).label("avg_hours"),
                func.count(EscalationEvent.id).label("count"),
            )
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.status == "RESOLVED",
                EscalationEvent.created_at >= cutoff,
                EscalationEvent.resolved_at != None,
            )
            .group_by(EscalationEvent.trigger_type)
            .all()
        )

        # Repeat offenders: loans with more than 2 escalations in the period
        repeat_loans = (
            self.db.query(
                EscalationEvent.loan_id,
                func.count(EscalationEvent.id).label("escalation_count"),
            )
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.created_at >= cutoff,
            )
            .group_by(EscalationEvent.loan_id)
            .having(func.count(EscalationEvent.id) > 2)
            .order_by(func.count(EscalationEvent.id).desc())
            .limit(20)
            .all()
        )

        # Level distribution (how many escalations reach each level)
        level_dist = (
            self.db.query(
                EscalationEvent.current_level,
                func.count(EscalationEvent.id).label("count"),
            )
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.created_at >= cutoff,
            )
            .group_by(EscalationEvent.current_level)
            .order_by(EscalationEvent.current_level)
            .all()
        )

        # Acknowledgment rate
        total_in_period = (
            self.db.query(func.count(EscalationEvent.id))
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.created_at >= cutoff,
            )
            .scalar()
        ) or 0

        acked_in_period = (
            self.db.query(func.count(EscalationEvent.id))
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.created_at >= cutoff,
                EscalationEvent.acknowledged_at != None,
            )
            .scalar()
        ) or 0

        return {
            "period_days": days,
            "total_escalations": total_in_period,
            "frequency_by_type": {
                row.trigger_type: row.count for row in frequency
            },
            "avg_resolution_hours_by_type": {
                row.trigger_type: round(float(row.avg_hours), 1)
                for row in resolution_by_type
                if row.avg_hours is not None
            },
            "repeat_offender_loans": [
                {"loan_id": row.loan_id, "escalation_count": row.escalation_count}
                for row in repeat_loans
            ],
            "level_distribution": {
                row.current_level: row.count for row in level_dist
            },
            "acknowledgment_rate_pct": (
                round((acked_in_period / total_in_period) * 100, 1)
                if total_in_period > 0 else 0.0
            ),
        }

    async def get_user_escalation_summary(self, target_user_id: int) -> Dict[str, Any]:
        """Get escalation summary for a specific user (their active assignments)."""
        active_for_user = (
            self.db.query(EscalationEvent)
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.escalated_to_user_id == target_user_id,
                EscalationEvent.status == "ACTIVE",
            )
            .order_by(EscalationEvent.created_at.desc())
            .all()
        )

        unacked = [e for e in active_for_user if e.acknowledged_at is None]
        now = datetime.now(timezone.utc)
        overdue = [
            e for e in active_for_user
            if e.next_escalation_at and e.next_escalation_at < now
        ]

        return {
            "user_id": target_user_id,
            "total_active": len(active_for_user),
            "unacknowledged": len(unacked),
            "overdue": len(overdue),
            "events": [
                {
                    "id": e.id,
                    "loan_id": e.loan_id,
                    "trigger_type": e.trigger_type,
                    "current_level": e.current_level,
                    "acknowledged": e.acknowledged_at is not None,
                    "created_at": _iso(e.created_at),
                }
                for e in active_for_user
            ],
        }

    # ------------------------------------------------------------------
    # SLA TRACKING FOR ESCALATION RESPONSE
    # ------------------------------------------------------------------

    def _calculate_event_sla(self, event: EscalationEvent) -> Dict[str, Any]:
        """Calculate SLA metrics for an individual escalation event.

        Measures time-to-acknowledge, time-to-resolve, and whether the
        event was acknowledged before the next escalation level fired.
        """
        now = datetime.now(timezone.utc)
        created = event.created_at or now

        # Time to acknowledge
        if event.acknowledged_at:
            ack_hours = (event.acknowledged_at - created).total_seconds() / 3600
        else:
            ack_hours = (now - created).total_seconds() / 3600

        # Time to resolve
        if event.resolved_at:
            resolution_hours = (event.resolved_at - created).total_seconds() / 3600
        else:
            resolution_hours = None

        # Was it acknowledged before it escalated?
        acked_before_escalation = (
            event.acknowledged_at is not None
            and event.current_level == 1
        )

        return {
            "time_to_acknowledge_hours": round(ack_hours, 1),
            "time_to_resolve_hours": round(resolution_hours, 1) if resolution_hours is not None else None,
            "is_acknowledged": event.acknowledged_at is not None,
            "acked_before_escalation": acked_before_escalation,
            "current_level": event.current_level,
        }

    # ------------------------------------------------------------------
    # INTERNAL: TRIGGER EVALUATORS
    # ------------------------------------------------------------------

    async def _evaluate_doc_overdue(self, loan_id: int) -> List[EscalationEvent]:
        """Check for overdue document requests on the loan."""
        rules = await self._get_active_rules("DOC_OVERDUE")
        events = []
        for rule in rules:
            threshold_days = rule.trigger_config.get("threshold_days", 5)
            cutoff = datetime.now(timezone.utc) - timedelta(days=threshold_days)

            overdue_docs = self.db.execute(
                text("""
                    SELECT dr.id AS request_id, dr.title, dr.sla_due_at
                    FROM smart_docs_requests dr
                    WHERE dr.loan_id = :loan_id
                      AND dr.organization_id = :org_id
                      AND dr.status IN ('OPEN', 'PENDING_REVIEW')
                      AND dr.is_active = true
                      AND dr.sla_due_at IS NOT NULL
                      AND dr.sla_due_at < :cutoff
                    LIMIT 10
                """),
                {"loan_id": loan_id, "org_id": self.org_id, "cutoff": cutoff},
            ).fetchall()

            for row in overdue_docs:
                evt = await self.fire_trigger(
                    trigger_type="DOC_OVERDUE",
                    loan_id=loan_id,
                    trigger_details={
                        "request_id": row.request_id,
                        "title": row.title,
                        "sla_due_at": _iso(row.sla_due_at),
                    },
                )
                if evt:
                    events.append(evt)
        return events

    async def _evaluate_sla_breach(self, loan_id: int) -> List[EscalationEvent]:
        """Check for SLA breaches or imminent breaches."""
        rules = await self._get_active_rules("SLA_BREACH")
        events = []
        for rule in rules:
            warn_hours = rule.trigger_config.get("warn_hours_before", 8)
            warn_cutoff = datetime.now(timezone.utc) + timedelta(hours=warn_hours)

            at_risk = self.db.execute(
                text("""
                    SELECT dr.id AS request_id, dr.title, dr.sla_due_at
                    FROM smart_docs_requests dr
                    WHERE dr.loan_id = :loan_id
                      AND dr.organization_id = :org_id
                      AND dr.status IN ('OPEN', 'PENDING_REVIEW')
                      AND dr.is_active = true
                      AND dr.sla_due_at IS NOT NULL
                      AND dr.sla_due_at <= :warn_cutoff
                      AND dr.sla_due_at > :now
                    LIMIT 10
                """),
                {
                    "loan_id": loan_id,
                    "org_id": self.org_id,
                    "warn_cutoff": warn_cutoff,
                    "now": datetime.now(timezone.utc),
                },
            ).fetchall()

            for row in at_risk:
                evt = await self.fire_trigger(
                    trigger_type="SLA_BREACH",
                    loan_id=loan_id,
                    trigger_details={
                        "request_id": row.request_id,
                        "title": row.title,
                        "sla_due_at": _iso(row.sla_due_at),
                        "imminent": True,
                    },
                )
                if evt:
                    events.append(evt)
        return events

    async def _evaluate_borrower_unresponsive(self, loan_id: int) -> List[EscalationEvent]:
        """Check if borrower has been unresponsive after N follow-up attempts."""
        rules = await self._get_active_rules("BORROWER_UNRESPONSIVE")
        events = []
        for rule in rules:
            min_attempts = rule.trigger_config.get("min_attempts", 3)
            lookback_days = rule.trigger_config.get("lookback_days", 14)
            cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

            result = self.db.execute(
                text("""
                    SELECT COUNT(*) AS attempt_count
                    FROM smart_docs_followup_events fe
                    JOIN smart_docs_followup_campaigns fc ON fc.id = fe.campaign_id
                    WHERE fc.loan_id = :loan_id
                      AND fc.organization_id = :org_id
                      AND fe.status = 'DELIVERED'
                      AND fe.created_at >= :cutoff
                """),
                {"loan_id": loan_id, "org_id": self.org_id, "cutoff": cutoff},
            ).fetchone()

            attempt_count = result.attempt_count if result else 0

            # Check that there is no borrower response (upload) in the same window
            has_response = self.db.execute(
                text("""
                    SELECT EXISTS(
                        SELECT 1 FROM documents d
                        WHERE d.loan_id = :loan_id
                          AND d.organization_id = :org_id
                          AND d.uploaded_at >= :cutoff
                          AND d.source = 'borrower_portal'
                    ) AS responded
                """),
                {"loan_id": loan_id, "org_id": self.org_id, "cutoff": cutoff},
            ).fetchone()

            responded = has_response.responded if has_response else False

            if attempt_count >= min_attempts and not responded:
                evt = await self.fire_trigger(
                    trigger_type="BORROWER_UNRESPONSIVE",
                    loan_id=loan_id,
                    trigger_details={
                        "attempts_in_window": attempt_count,
                        "lookback_days": lookback_days,
                    },
                )
                if evt:
                    events.append(evt)
        return events

    async def _evaluate_approval_timeout(self, loan_id: int) -> List[EscalationEvent]:
        """Check for document approvals pending longer than the threshold."""
        rules = await self._get_active_rules("APPROVAL_TIMEOUT")
        events = []
        for rule in rules:
            timeout_hours = rule.trigger_config.get("timeout_hours", 48)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)

            stale = self.db.execute(
                text("""
                    SELECT dr.id AS request_id, dr.title, dr.updated_at
                    FROM smart_docs_requests dr
                    WHERE dr.loan_id = :loan_id
                      AND dr.organization_id = :org_id
                      AND dr.status = 'PENDING_REVIEW'
                      AND dr.is_active = true
                      AND dr.updated_at < :cutoff
                    LIMIT 10
                """),
                {"loan_id": loan_id, "org_id": self.org_id, "cutoff": cutoff},
            ).fetchall()

            for row in stale:
                evt = await self.fire_trigger(
                    trigger_type="APPROVAL_TIMEOUT",
                    loan_id=loan_id,
                    trigger_details={
                        "request_id": row.request_id,
                        "title": row.title,
                        "pending_since": _iso(row.updated_at),
                    },
                )
                if evt:
                    events.append(evt)
        return events

    async def _evaluate_condition_overdue(self, loan_id: int) -> List[EscalationEvent]:
        """Check for underwriting conditions past their deadline."""
        rules = await self._get_active_rules("CONDITION_OVERDUE")
        events = []
        for rule in rules:
            threshold_days = rule.trigger_config.get("threshold_days", 3)
            cutoff = datetime.now(timezone.utc) - timedelta(days=threshold_days)

            overdue = self.db.execute(
                text("""
                    SELECT ca.id AS alert_id, ca.title, ca.deadline_date
                    FROM compliance_alerts ca
                    WHERE ca.loan_id = :loan_id
                      AND ca.status = 'open'
                      AND ca.deadline_date IS NOT NULL
                      AND ca.deadline_date < :cutoff
                    LIMIT 10
                """),
                {"loan_id": loan_id, "cutoff": cutoff.date()},
            ).fetchall()

            for row in overdue:
                evt = await self.fire_trigger(
                    trigger_type="CONDITION_OVERDUE",
                    loan_id=loan_id,
                    trigger_details={
                        "alert_id": row.alert_id,
                        "title": row.title,
                        "deadline_date": str(row.deadline_date),
                    },
                )
                if evt:
                    events.append(evt)
        return events

    # ------------------------------------------------------------------
    # INTERNAL: COOLDOWN / SUPPRESSION
    # ------------------------------------------------------------------

    async def _is_suppressed(
        self,
        trigger_type: str,
        loan_id: int,
        rule_id: int,
    ) -> bool:
        """Check if a recent active/resolved event for the same trigger+loan
        exists within the cooldown window, indicating suppression."""
        cooldown_hours = DEFAULT_COOLDOWN_HOURS
        cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)

        exists = (
            self.db.query(func.count(EscalationEvent.id))
            .filter(
                EscalationEvent.organization_id == self.org_id,
                EscalationEvent.rule_id == rule_id,
                EscalationEvent.loan_id == loan_id,
                EscalationEvent.trigger_type == trigger_type,
                EscalationEvent.status.in_(["ACTIVE", "RESOLVED"]),
                EscalationEvent.created_at >= cutoff,
            )
            .scalar()
        )
        return (exists or 0) > 0

    # ------------------------------------------------------------------
    # INTERNAL: NOTIFICATION
    # ------------------------------------------------------------------

    async def _send_escalation_notification(
        self,
        event: EscalationEvent,
        rule: EscalationRule,
        level: int,
    ) -> None:
        """Send notification via the notification center.

        Creates a Notification record for the target user.  This integrates
        with the existing notification center (database.models.security.Notification).
        """
        if not event.escalated_to_user_id:
            logger.debug("No target user for escalation event %d level %d", event.id, level)
            return

        try:
            from database.models.security import Notification
        except ImportError:
            logger.warning("Notification model not available; skipping notification")
            return

        severity_label = (rule.trigger_config or {}).get("severity", "medium")
        title = f"Escalation (L{level}): {rule.rule_name}"
        message = self._build_notification_message(event, rule, level, severity_label)

        notification = Notification(
            organization_id=self.org_id,
            user_id=event.escalated_to_user_id,
            type="escalation",
            title=title,
            message=message,
            link=f"/loans/{event.loan_id}/escalations/{event.id}",
            is_read=False,
        )
        self.db.add(notification)
        self.db.flush()

        logger.info(
            "Sent escalation notification to user %d for event %d (level %d)",
            event.escalated_to_user_id, event.id, level,
        )

    def _build_notification_message(
        self,
        event: EscalationEvent,
        rule: EscalationRule,
        level: int,
        severity: str,
    ) -> str:
        """Build a human-readable notification message."""
        details = event.trigger_details or {}
        parts = [
            f"[{severity.upper()}] {rule.rule_name}",
            f"Loan ID: {event.loan_id}",
            f"Escalation Level: {level}",
        ]

        if "title" in details:
            parts.append(f"Document: {details['title']}")
        if "request_id" in details:
            parts.append(f"Request ID: {details['request_id']}")
        if "variance_pct" in details:
            parts.append(f"Income Variance: {details['variance_pct']}%")
        if "attempts_in_window" in details:
            parts.append(f"Follow-up Attempts: {details['attempts_in_window']}")

        return " | ".join(parts)

    # ------------------------------------------------------------------
    # INTERNAL: ROLE RESOLUTION
    # ------------------------------------------------------------------

    async def _resolve_notify_target(
        self,
        role: str,
        loan_id: int,
    ) -> Optional[int]:
        """Resolve a logical role (e.g. 'loan_officer') to a user_id."""
        query_template = ROLE_LOOKUP_QUERIES.get(role)
        if not query_template:
            logger.warning("Unknown notification role: %s", role)
            return None

        try:
            result = self.db.execute(
                text(query_template),
                {"loan_id": loan_id, "org_id": self.org_id},
            ).fetchone()
            if result and result.user_id:
                return result.user_id
        except Exception as e:
            logger.error("Failed to resolve role %s for loan %d: %s", role, loan_id, e)

        # Fallback: try loan_officer if the requested role could not be found
        if role != "loan_officer":
            return await self._resolve_notify_target("loan_officer", loan_id)

        return None

    # ------------------------------------------------------------------
    # INTERNAL: HELPERS
    # ------------------------------------------------------------------

    def _get_rule(self, rule_id: int) -> Optional[EscalationRule]:
        """Get an escalation rule scoped to this org."""
        return (
            self.db.query(EscalationRule)
            .filter(
                EscalationRule.id == rule_id,
                EscalationRule.organization_id == self.org_id,
            )
            .first()
        )

    def _get_event(self, event_id: int) -> Optional[EscalationEvent]:
        """Get an escalation event scoped to this org."""
        return (
            self.db.query(EscalationEvent)
            .filter(
                EscalationEvent.id == event_id,
                EscalationEvent.organization_id == self.org_id,
            )
            .first()
        )

    async def _get_active_rules(self, trigger_type: str) -> List[EscalationRule]:
        """Get active rules for a trigger type in this org."""
        return (
            self.db.query(EscalationRule)
            .filter(
                EscalationRule.organization_id == self.org_id,
                EscalationRule.trigger_type == trigger_type,
                EscalationRule.is_active == True,
            )
            .all()
        )

    @staticmethod
    def _validate_chain(chain: List[Dict[str, Any]]) -> None:
        """Validate an escalation chain structure."""
        if not chain:
            raise ValueError("Escalation chain must have at least one step")
        for i, step in enumerate(chain):
            if "level" not in step:
                raise ValueError(f"Chain step {i} missing 'level'")
            if "notify" not in step:
                raise ValueError(f"Chain step {i} missing 'notify'")
            if "after_hours" not in step:
                raise ValueError(f"Chain step {i} missing 'after_hours'")
            if not isinstance(step["after_hours"], (int, float)) or step["after_hours"] < 0:
                raise ValueError(f"Chain step {i}: 'after_hours' must be a non-negative number")


# =============================================================================
# HELPERS
# =============================================================================

def _iso(dt: Optional[datetime]) -> Optional[str]:
    """Format datetime as ISO string or None."""
    return dt.isoformat() if dt else None
