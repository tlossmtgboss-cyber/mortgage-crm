"""
Escalation Strategy Service

Implements Module 3 gap: auto-escalation rules, warm handoff protocol,
queue management, and de-escalation framework.

Usage:
    from services.escalation_strategy_service import EscalationStrategyService
    service = EscalationStrategyService(db)
    result = service.evaluate_escalation(task_id=123, context={...})
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


# ============================================================================
# ESCALATION RULES ENGINE
# ============================================================================

# Module 3.1 — Escalation Trigger Matrix
ESCALATION_RULES = {
    # Level 1: Agent-to-Agent
    "domain_mismatch": {
        "level": 1,
        "description": "Query requires different agent's tools",
        "action": "route_with_context",
        "sla_minutes": 0,  # Immediate
    },
    "multi_domain_query": {
        "level": 1,
        "description": "Query spans multiple agent domains",
        "action": "route_with_context",
        "sla_minutes": 0,
    },

    # Level 2: Agent-to-Human
    "compliance_uncertainty": {
        "level": 2,
        "description": "Agent not 100% confident on compliance",
        "action": "create_urgent_task",
        "sla_minutes": 60,
        "escalate_to_role": "compliance_officer",
    },
    "borrower_distress": {
        "level": 2,
        "description": "Borrower angry/distressed AND asked for human",
        "action": "create_urgent_task",
        "sla_minutes": 30,
        "escalate_to_role": "loan_officer",
    },
    "adverse_action": {
        "level": 2,
        "description": "Adverse action decision required",
        "action": "create_urgent_task",
        "sla_minutes": 120,
        "escalate_to_role": "compliance_officer",
    },
    "tool_failure_critical": {
        "level": 2,
        "description": "Tool failure on critical path",
        "action": "create_urgent_task",
        "sla_minutes": 30,
        "escalate_to_role": "operations",
    },
    "repeated_failure": {
        "level": 2,
        "description": "3+ failed attempts to resolve",
        "action": "create_urgent_task",
        "sla_minutes": 60,
        "escalate_to_role": "supervisor",
    },

    # Level 3: Emergency
    "data_breach": {
        "level": 3,
        "description": "Data breach or unauthorized access",
        "action": "immediate_notification",
        "sla_minutes": 5,
        "escalate_to_role": "security_officer",
    },
    "regulatory_inquiry": {
        "level": 3,
        "description": "Regulatory audit or examiner inquiry",
        "action": "immediate_notification",
        "sla_minutes": 15,
        "escalate_to_role": "compliance_officer",
    },
    "critical_sla_breach": {
        "level": 3,
        "description": "Critical SLA breach on high-value loan",
        "action": "immediate_notification",
        "sla_minutes": 15,
        "escalate_to_role": "branch_manager",
    },
}

# Module 3.4 — Cross-Agent Routing Rules
ROUTING_RULES = {
    "check_loan_compliance": ["compliance_checker"],
    "borrower_upset_delay": ["ai_receptionist", "sla_tracker"],
    "email_realtor_closing": ["email_intelligence"],  # + compliance guardrail
    "pipeline_stuck": ["pipeline_analyst", "sla_tracker", "task_automation"],
    "score_lead_outreach": ["lead_nurturer"],
    "missing_docs": ["document_tracker"],  # + SLA impact check
    "lock_or_float": ["rate_advisor"],  # + market data + borrower timeline
    "rate_inquiry": ["rate_advisor"],
    "schedule_meeting": ["smart_scheduler"],
    "team_performance": ["team_coach"],
    "refi_opportunity": ["customer_intelligence", "rate_advisor"],
}


class EscalationStrategyService:
    """Evaluates and executes escalation strategies per Module 3."""

    def __init__(self, db_session):
        self.db = db_session

    def evaluate_escalation(
        self,
        trigger_type: str,
        context: Dict[str, Any],
        current_agent: Optional[str] = None,
        attempt_count: int = 0,
    ) -> Dict[str, Any]:
        """Evaluate whether escalation is needed and determine target.

        Args:
            trigger_type: Key from ESCALATION_RULES
            context: Current conversation/task context
            current_agent: The AI agent currently handling
            attempt_count: Number of resolution attempts so far

        Returns:
            Escalation decision with target, level, and context package
        """
        # Check for repeated failure auto-escalation
        if attempt_count >= 3 and trigger_type not in ESCALATION_RULES:
            trigger_type = "repeated_failure"

        rule = ESCALATION_RULES.get(trigger_type)
        if not rule:
            return {"escalate": False, "reason": f"Unknown trigger: {trigger_type}"}

        sla_deadline = datetime.now(timezone.utc) + timedelta(minutes=rule["sla_minutes"])

        return {
            "escalate": True,
            "level": rule["level"],
            "trigger_type": trigger_type,
            "description": rule["description"],
            "action": rule["action"],
            "escalate_to_role": rule.get("escalate_to_role"),
            "sla_deadline": sla_deadline.isoformat(),
            "sla_minutes": rule["sla_minutes"],
            "context_package": self._build_context_package(context, current_agent),
        }

    def _build_context_package(
        self,
        context: Dict[str, Any],
        current_agent: Optional[str],
    ) -> Dict[str, Any]:
        """Build Module 3.2 warm handoff context package.

        NEVER transfer without context. NEVER.
        """
        return {
            "handoff_from": current_agent,
            "conversation_summary": context.get("summary", ""),
            "active_entities": context.get("entities", []),
            "user_emotional_state": context.get("sentiment", "neutral"),
            "pending_question": context.get("pending_question", ""),
            "tools_already_used": context.get("tools_used", []),
            "data_already_retrieved": context.get("data_retrieved", {}),
        }

    def route_to_agents(self, intent: str) -> List[str]:
        """Determine which agent(s) should handle an intent per Module 3.4."""
        return ROUTING_RULES.get(intent, [])

    def check_sla_compliance(self, escalation_id: int) -> Dict[str, Any]:
        """Check if an escalation's SLA is being met.

        Module 3.2 Step 4: No response within SLA -> Re-escalate.
        """
        from database.models.task import EscalationRecord

        esc = self.db.query(EscalationRecord).filter(
            EscalationRecord.id == escalation_id
        ).first()

        if not esc:
            return {"found": False}

        now = datetime.now(timezone.utc)
        is_overdue = esc.sla_deadline and now > esc.sla_deadline
        is_acknowledged = esc.acknowledged_at is not None

        result = {
            "escalation_id": esc.id,
            "status": esc.status,
            "is_overdue": is_overdue,
            "is_acknowledged": is_acknowledged,
            "level": esc.escalation_level,
        }

        if is_overdue and esc.status in ("open", "acknowledged"):
            result["action"] = "re_escalate"
            result["new_level"] = min(esc.escalation_level + 1, 3)

        return result

    def generate_bridge_message(
        self,
        target_type: str,  # "agent" or "human"
        target_name: str,
        specific_need: str,
        timeframe: Optional[str] = None,
    ) -> str:
        """Generate Module 3.2 Step 2 bridge message for user.

        "I'm connecting you with [person/agent] for [specific need]."
        "I've shared our conversation so you won't need to repeat yourself."
        """
        msg = f"I'm connecting you with {target_name} for {specific_need}. "
        msg += "I've shared our conversation so you won't need to repeat yourself."

        if target_type == "human" and timeframe:
            msg += f" They should reach out within {timeframe}."

        return msg

    def apply_deescalation(self, emotional_state: str, context: Dict) -> Dict[str, Any]:
        """Apply Module 3.3 de-escalation framework.

        Step 1: ACKNOWLEDGE — Validate emotion
        Step 2: INVESTIGATE — Pull relevant data immediately
        Step 3: ACT — Specific next step with timeline
        Step 4: CONFIRM — Ask if anything else needed
        """
        responses = {
            "frustrated": {
                "acknowledge": "I understand this is frustrating, and I want to help resolve this right away.",
                "action": "investigate_and_act",
                "offer_human": False,
            },
            "angry": {
                "acknowledge": "I hear you, and you're right to be upset. Let me look into this immediately.",
                "action": "investigate_and_act",
                "offer_human": True,
            },
            "urgent": {
                "acknowledge": "I can see this needs immediate attention. Let me prioritize this right now.",
                "action": "fast_track",
                "offer_human": False,
            },
            "confused": {
                "acknowledge": "I want to make sure we get this right. Let me walk through this step by step.",
                "action": "clarify_and_guide",
                "offer_human": False,
            },
        }

        framework = responses.get(emotional_state, responses["frustrated"])

        return {
            "emotional_state": emotional_state,
            "acknowledge_message": framework["acknowledge"],
            "recommended_action": framework["action"],
            "offer_human_transfer": framework["offer_human"],
            "never_say": [
                "I understand",  # Too generic
                "Someone will get back to you",  # No specific SLA
                "That's not my department",  # Never deflect
            ],
        }
