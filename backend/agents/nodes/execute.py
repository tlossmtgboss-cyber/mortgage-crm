"""
Action Executor Node

This node handles action requests - creating tasks, sending emails,
updating records, etc. It manages action confirmation and execution.
"""

import asyncio
import logging
import re
from typing import Any, Callable, Dict, List, Set
from datetime import datetime

from ..state import (
    AgentState,
    ActionResult,
    add_node_trace,
    add_error,
    update_state
)

# Import approval lists from tool_integration so execute node
# respects the same approval gates as AgentToolExecutor.
try:
    from ..tool_integration import AGENT_CONFIGS
    _APPROVAL_REQUIRED_TOOLS: Set[str] = set()
    for cfg in AGENT_CONFIGS.values():
        _APPROVAL_REQUIRED_TOOLS.update(cfg.requires_approval_for)
except ImportError:
    _APPROVAL_REQUIRED_TOOLS = set()

logger = logging.getLogger(__name__)


# Risk classification for actions
ACTION_RISK_LEVELS = {
    # LOW RISK - Auto-execute without confirmation
    "create_task": "low",
    "schedule_followup": "low",
    "get_tasks": "low",
    "get_pipeline": "low",
    "search_leads": "low",

    # MEDIUM RISK - Auto-execute for internal actions
    "send_email": "medium",  # To self only
    "update_lead": "medium",

    # HIGH RISK - Requires confirmation (but will auto-execute for explicit requests)
    "send_email_to_contact": "high",  # External emails
    "send_sms": "medium",             # Changed to medium for explicit user requests
    "send_text": "medium",            # Alias for send_sms
    "make_phone_call": "medium",
    "make_call": "medium",            # Alias for click_to_dial
    "click_to_dial": "medium",        # User explicitly requested call
    "call_contact": "medium",         # Alias
    "create_lead": "high",
    "update_loan_status": "high",

    # CRITICAL - Always requires explicit confirmation
    "delete_loan": "critical",
    "delete_lead": "critical",
    "escalate_to_human": "critical"
}


def classify_action_risk(action_type: str) -> str:
    """
    Classify the risk level of an action.

    Args:
        action_type: Type of action to classify

    Returns:
        Risk level: 'low', 'medium', 'high', or 'critical'
    """
    return ACTION_RISK_LEVELS.get(action_type, "medium")


def should_auto_execute(action_type: str, autonomous_mode: bool = True) -> bool:
    """
    Determine if an action should be auto-executed.

    Checks both the local ACTION_RISK_LEVELS dict and the centralized
    requires_approval_for lists in AGENT_CONFIGS (tool_integration.py).

    Args:
        action_type: Type of action
        autonomous_mode: Whether autonomous mode is enabled

    Returns:
        True if action should be auto-executed
    """
    if not autonomous_mode:
        return False

    # Check centralized approval list from tool_integration.AGENT_CONFIGS
    if action_type in _APPROVAL_REQUIRED_TOOLS:
        logger.info(f"[EXECUTE] Action '{action_type}' requires approval (AGENT_CONFIGS)")
        return False

    risk = classify_action_risk(action_type)
    if risk in ("high", "critical"):
        return False  # High/critical risk actions always require human approval
    return risk in ["low", "medium"] and autonomous_mode


async def execute_single_action(
    action: dict,
    tool_functions: Dict[str, Callable]
) -> ActionResult:
    """
    Execute a single action.

    Args:
        action: Action specification with type and parameters
        tool_functions: Available tool functions

    Returns:
        ActionResult with outcome
    """
    action_type = action.get("type", action.get("action_type", "unknown"))
    params = action.get("params", action.get("parameters", {}))

    result = ActionResult(
        action_type=action_type,
        success=False,
        message=""
    )

    try:
        func = tool_functions.get(action_type)
        if func is None:
            result.message = f"Action '{action_type}' not supported"
            result.error = "Function not found"
            return result

        # Execute the action
        if asyncio.iscoroutinefunction(func):
            action_result = await func(params)
        else:
            action_result = func(params)

        result.success = True
        result.message = action_result.get("message", f"Action {action_type} completed")
        result.data = action_result

        logger.info(f"Action {action_type} executed successfully")

    except Exception as e:
        result.success = False
        result.message = f"Action failed: {str(e)}"
        result.error = str(e)
        logger.error(f"Action {action_type} failed: {e}")

    return result


def extract_actions_from_analysis(state: AgentState) -> List[dict]:
    """
    Extract actionable requests from the user's query and analysis.

    This identifies when the user wants to DO something vs just GET information.

    Args:
        state: Current agent state

    Returns:
        List of action specifications
    """
    actions = []
    user_message = state.get("user_message", "").lower()
    recommendations = state.get("recommendations", [])

    # Detect email sending requests
    _email_patterns = [
        r"send me\b", r"email me\b", r"send email", r"send an email",
        r"email that", r"send a summary", r"send my",
        r"\bcompose\b", r"write\s+\w*\s*email", r"reply to\b",
        r"respond to\s+\w*\s*email",
    ]
    if any(re.search(pat, user_message) for pat in _email_patterns):
        # Determine email type from context
        content_type = "custom"
        if "task" in user_message or "priorities" in user_message:
            content_type = "task_summary"
        elif "pipeline" in user_message:
            content_type = "pipeline_update"
        elif "lead" in user_message:
            content_type = "lead_summary"

        actions.append({
            "type": "send_email",
            "params": {
                "content_type": content_type,
                "subject": "Your Requested Summary"
            },
            "auto_execute": True
        })

    # Detect task creation requests
    _task_patterns = [
        r"create\s+a?\s*task", r"add\s+a?\s*task", r"remind me\b",
        r"\bschedule\b", r"new task", r"make\s+a?\s*task",
        r"set\s+a?\s*reminder",
    ]
    if any(re.search(pat, user_message) for pat in _task_patterns):
        # Extract task details from context
        actions.append({
            "type": "create_task",
            "params": {
                "title": "Follow-up task (review details)",
                "priority": "medium"
            },
            "auto_execute": False,  # Need to extract proper details
            "needs_details": True
        })

    # Detect follow-up scheduling
    _followup_patterns = [
        r"follow\s*up", r"schedule\s+a?\s*call", r"reach out to\b",
        r"\bcontact\b", r"call back", r"book\s+a?\s*appointment",
        r"set\s+a?\s*meeting", r"arrange\s+a?\s*call",
        r"reach out\b",
    ]
    if any(re.search(pat, user_message) for pat in _followup_patterns):
        actions.append({
            "type": "schedule_followup",
            "params": {
                "followup_type": "call"
            },
            "auto_execute": False,
            "needs_details": True
        })

    # Detect lead/loan update requests
    _update_patterns = [
        r"\bupdate\b", r"change\s+\w*\s*status", r"move\s+\w*\s*to\b",
        r"mark\s+\w*\s*as\b", r"change\s+\w*\s*stage",
        r"set\s+\w*\s*status",
    ]
    if any(re.search(pat, user_message) for pat in _update_patterns):
        actions.append({
            "type": "update_lead",
            "params": {},
            "auto_execute": False,
            "needs_details": True
        })

    return actions


async def execute_actions(
    state: AgentState,
    tool_functions: Dict[str, Callable] = None,
    autonomous_mode: bool = True
) -> AgentState:
    """
    Execute requested actions based on user intent.

    Args:
        state: Current agent state
        tool_functions: Dictionary of available tool functions
        autonomous_mode: Whether to auto-execute low-risk actions

    Returns:
        Updated state with action results
    """
    state = add_node_trace(state, "execute")

    if tool_functions is None:
        tool_functions = {}

    # Check if this is an action request
    requires_action = state.get("requires_action", False)
    if not requires_action:
        logger.info("No actions required for this query")
        return update_state(state, {
            "actions_requested": [],
            "actions_executed": [],
            "actions_pending": []
        })

    try:
        # Extract actions from the user's request
        actions = extract_actions_from_analysis(state)

        if not actions:
            return update_state(state, {
                "actions_requested": actions,
                "actions_executed": [],
                "actions_pending": []
            })

        executed = []
        pending = []

        for action in actions:
            action_type = action.get("type")
            needs_details = action.get("needs_details", False)

            # If action needs more details, mark as pending
            if needs_details:
                pending.append(action)
                continue

            # Check if we should auto-execute
            if action.get("auto_execute") and should_auto_execute(action_type, autonomous_mode):
                result = await execute_single_action(action, tool_functions)
                executed.append(result)
            else:
                # Requires confirmation
                pending.append(action)

        # Update state with results
        state = update_state(state, {
            "actions_requested": actions,
            "actions_executed": executed,
            "actions_pending": pending
        })

        logger.info(f"Actions: {len(executed)} executed, {len(pending)} pending confirmation")

        # Fire cross-agent events for successful actions (fire-and-forget)
        if executed:
            asyncio.ensure_future(
                _emit_cross_agent_events(executed, state)
            )

        return state

    except Exception as e:
        logger.error(f"Action execution failed: {e}")
        state = add_error(state, f"Action execution error: {str(e)}")
        return update_state(state, {
            "actions_requested": [],
            "actions_executed": [],
            "actions_pending": []
        })


async def _emit_cross_agent_events(
    executed: List[ActionResult],
    state: AgentState,
) -> None:
    """Inspect executed action results and emit inter-agent events.

    This is fire-and-forget: any failure is logged and swallowed so it
    never blocks the user-facing response.

    Also sends push notifications via AgentNotificationService for
    document, SLA, and compliance findings so loan officers get
    real-time mobile alerts.
    """
    try:
        from services.agent_event_bridge import agent_event_bridge
    except ImportError:
        return  # Bridge not available -- skip silently

    org_id = str(state.get("organization_id")) if state.get("organization_id") else None

    # Lazily acquire push notification service and DB session.
    # Both are optional: if unavailable, events still fire normally.
    push_svc = None
    push_db = None
    try:
        from services.agent_notification_service import get_agent_notification_service
        from db import SessionLocal
        push_svc = get_agent_notification_service()
        push_db = SessionLocal()
    except Exception:
        pass  # Push notifications unavailable -- degrade gracefully

    try:
        for result in executed:
            if not result.success or not result.data:
                continue

            data = result.data
            action_type = result.action_type

            try:
                # Lead scoring -> hot lead detection
                if action_type == "score_lead" and data.get("new_score", 0) >= 60:
                    await agent_event_bridge.on_hot_lead_detected(
                        lead_id=data.get("lead_id"),
                        score=data.get("new_score", 0),
                        lo_id=data.get("lo_id"),
                        org_id=org_id,
                    )

                # Document expiration check -> expired documents
                if action_type == "check_document_expiration" and data.get("expired"):
                    expired_types = [
                        doc.get("document_type", "unknown")
                        for doc in data.get("expired", [])
                    ]
                    loan_ids_seen = set()
                    for doc in data.get("expired", []):
                        lid = doc.get("loan_id")
                        if lid and lid not in loan_ids_seen:
                            loan_ids_seen.add(lid)
                            await agent_event_bridge.on_documents_expired(
                                loan_id=lid,
                                doc_types=expired_types,
                                org_id=org_id,
                            )
                            # Push notification: doc expiring/expired
                            if push_svc and push_db:
                                try:
                                    for exp_doc in data.get("expired", []):
                                        if exp_doc.get("loan_id") == lid:
                                            push_svc.notify_doc_expiring(
                                                db=push_db,
                                                loan_id=lid,
                                                doc_type=exp_doc.get("document_type", "Document"),
                                                expire_date=exp_doc.get("expires_at", ""),
                                                borrower_name=exp_doc.get("borrower", ""),
                                                loan_number=exp_doc.get("loan_number", ""),
                                            )
                                            break  # One push per loan, not per doc type
                                except Exception as push_err:
                                    logger.debug(
                                        "[EXECUTE] Push notify_doc_expiring failed for loan %s: %s",
                                        lid, push_err,
                                    )

                    # Also push for expiring-soon docs
                    if push_svc and push_db and data.get("expiring_soon"):
                        expiring_loan_ids = set()
                        for exp_doc in data.get("expiring_soon", []):
                            lid = exp_doc.get("loan_id")
                            if lid and lid not in expiring_loan_ids:
                                expiring_loan_ids.add(lid)
                                try:
                                    push_svc.notify_doc_expiring(
                                        db=push_db,
                                        loan_id=lid,
                                        doc_type=exp_doc.get("document_type", "Document"),
                                        expire_date=exp_doc.get("expires_at", ""),
                                        borrower_name=exp_doc.get("borrower", ""),
                                        loan_number=exp_doc.get("loan_number", ""),
                                    )
                                except Exception as push_err:
                                    logger.debug(
                                        "[EXECUTE] Push notify_doc_expiring (soon) failed for loan %s: %s",
                                        lid, push_err,
                                    )

                # Missing documents check -> notify LO about needed docs
                if action_type == "get_missing_documents" and data.get("missing"):
                    missing_required = [
                        m.get("type", "unknown")
                        for m in data.get("missing", [])
                        if m.get("required")
                    ]
                    loan_id = data.get("loan_id")
                    if push_svc and push_db and loan_id and missing_required:
                        try:
                            push_svc.notify_document_needed(
                                db=push_db,
                                loan_id=loan_id,
                                doc_types=missing_required,
                                borrower_name="",
                                loan_number=data.get("loan_number", ""),
                            )
                        except Exception as push_err:
                            logger.debug(
                                "[EXECUTE] Push notify_document_needed failed for loan %s: %s",
                                loan_id, push_err,
                            )

                # Compliance audit -> violations
                if action_type in ("check_trid_compliance", "check_tolerance_violations", "audit_loan_file"):
                    issues = data.get("issues", [])
                    violations = data.get("violations", [])
                    failed_checks = data.get("results", {}).get("failed", [])
                    all_issues = issues + violations + failed_checks
                    compliance_push_sent = False
                    for issue in all_issues:
                        severity = issue.get("severity", "medium")
                        if severity in ("high", "critical"):
                            await agent_event_bridge.on_compliance_violation(
                                loan_id=data.get("loan_id"),
                                violation_type=issue.get("type", action_type),
                                severity=severity,
                                description=issue.get("message", ""),
                                org_id=org_id,
                            )
                            # Push notification: compliance alert (one per loan per tool invocation)
                            if push_svc and push_db and data.get("loan_id") and not compliance_push_sent:
                                try:
                                    push_svc.notify_compliance_alert(
                                        db=push_db,
                                        loan_id=data.get("loan_id"),
                                        alert_title=issue.get("message", issue.get("type", action_type)),
                                        severity=severity,
                                        borrower_name="",
                                        loan_number=data.get("loan_number", ""),
                                    )
                                    compliance_push_sent = True
                                except Exception as push_err:
                                    logger.debug(
                                        "[EXECUTE] Push notify_compliance_alert failed for loan %s: %s",
                                        data.get("loan_id"), push_err,
                                    )

                # Pipeline bottleneck -> stalled loans (one event per stage)
                if action_type == "get_bottleneck_analysis":
                    for bottleneck in data.get("bottlenecks", []):
                        if bottleneck.get("severity") == "critical":
                            stage_name = bottleneck.get("stage", "UNKNOWN")
                            # Use stage-specific identifier so each bottleneck
                            # stage gets its own dedup key instead of all
                            # collapsing into loan_stalled:0:<org_id>.
                            await agent_event_bridge.on_loan_stalled(
                                loan_id=f"bottleneck:{stage_name}",
                                days_stale=int(bottleneck.get("avg_days", 0)),
                                stage=stage_name,
                                org_id=org_id,
                            )

                # Loan aging report -> SLA breach notifications for over-threshold loans
                if action_type == "get_loan_aging_report" and data.get("total_over_threshold", 0) > 0:
                    for stage_info in data.get("by_stage", []):
                        if stage_info.get("over_threshold", 0) > 0 and stage_info.get("avg_days", 0) > stage_info.get("target_days", 999):
                            stage_name = stage_info.get("stage", "UNKNOWN")
                            # Use stage-specific identifier so each aging
                            # stage gets its own dedup key instead of all
                            # collapsing into loan_stalled:0:<org_id>.
                            await agent_event_bridge.on_loan_stalled(
                                loan_id=f"aging:{stage_name}",
                                days_stale=int(stage_info.get("avg_days", 0)),
                                stage=stage_name,
                                org_id=org_id,
                            )

                # SLA breach from loan conditions (past-due conditions)
                if action_type == "get_loan_conditions" and data.get("past_due", 0) > 0:
                    loan_id = data.get("loan_id")
                    if push_svc and push_db and loan_id:
                        past_due_conditions = [
                            c for c in data.get("conditions", [])
                            if c.get("is_past_due")
                        ]
                        for condition in past_due_conditions[:1]:  # One push per invocation
                            try:
                                push_svc.notify_sla_breach(
                                    db=push_db,
                                    loan_id=loan_id,
                                    sla_name=condition.get("title", condition.get("type", "Condition")),
                                    days_over=0,  # Exact days not available from conditions
                                    loan_number="",
                                )
                            except Exception as push_err:
                                logger.debug(
                                    "[EXECUTE] Push notify_sla_breach failed for loan %s: %s",
                                    loan_id, push_err,
                                )

            except Exception as e:
                logger.warning(
                    "[EXECUTE] Cross-agent event emission failed for %s: %s",
                    action_type, e,
                )
    finally:
        # Always close the push DB session if we opened one
        if push_db is not None:
            try:
                push_db.close()
            except Exception:
                pass


def format_action_confirmation_request(pending_actions: List[dict]) -> str:
    """
    Format pending actions into a confirmation request for the user.

    Args:
        pending_actions: List of actions needing confirmation

    Returns:
        Formatted string requesting user confirmation
    """
    if not pending_actions:
        return ""

    lines = ["The following actions require your confirmation:"]

    for i, action in enumerate(pending_actions, 1):
        action_type = action.get("type", "unknown")
        params = action.get("params", {})

        if action_type == "send_email_to_contact":
            lines.append(f"{i}. Send email to {params.get('recipient', 'contact')}")
        elif action_type == "send_sms":
            lines.append(f"{i}. Send SMS to {params.get('phone', 'contact')}")
        elif action_type == "create_task":
            lines.append(f"{i}. Create task: {params.get('title', 'New task')}")
        elif action_type == "update_lead":
            lines.append(f"{i}. Update lead status")
        else:
            lines.append(f"{i}. {action_type.replace('_', ' ').title()}")

    lines.append("\nReply 'confirm' to proceed or 'cancel' to abort.")

    return "\n".join(lines)
