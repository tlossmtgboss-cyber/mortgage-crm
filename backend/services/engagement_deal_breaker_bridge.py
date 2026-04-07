"""Engagement-Deal Breaker Bridge — connects SMS qualification flow to deal breaker evaluation.

Bridges the SMS conversation manager's accumulated context_data to the
DealBreakerService rules engine, then generates ECOA-compliant SMS responses
that never dead-end a borrower.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from services.deal_breaker_service import (
    DealBreakerResult,
    DealBreakerService,
    get_deal_breaker_service,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credit-range string -> midpoint mapping (matches SMS qualifying questions)
# ---------------------------------------------------------------------------
CREDIT_RANGE_MAP: Dict[str, int] = {
    "excellent": 760,
    "740+": 760,
    "good": 710,
    "680-739": 710,
    "fair": 650,
    "620-679": 650,
    "below 620": 580,
    "below620": 580,
    "poor": 560,
    "under 580": 550,
    "very poor": 520,
    "under 500": 480,
}

# Employment text normalizations
EMPLOYMENT_MAP: Dict[str, str] = {
    "employed": "w2",
    "w2": "w2",
    "salaried": "w2",
    "self-employed": "self_employed",
    "self employed": "self_employed",
    "1099": "self_employed",
    "business owner": "self_employed",
    "retired": "retired",
    "pension": "retired",
}


# ---------------------------------------------------------------------------
# Data mapping — SMS context_data -> DealBreakerService borrower_data
# ---------------------------------------------------------------------------

def _map_context_to_borrower_data(
    context_data: Dict[str, Any],
    lead_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Translate SMS conversation context_data into deal_breaker_service input format.

    SMS conversation manager stores qualification answers in context_data with
    keys like 'credit_range', 'loan_purpose', 'employment', 'price_range',
    'timeline'. The deal breaker service expects 'credit_score', 'employment_type',
    'property_type', etc.
    """
    borrower: Dict[str, Any] = {"lead_id": lead_id or "sms_unknown"}

    # --- Credit score ---
    credit_raw = (context_data.get("credit_range") or context_data.get("credit_score_range") or "").strip().lower()
    if credit_raw:
        borrower["credit_score"] = CREDIT_RANGE_MAP.get(credit_raw)
        # If user typed a raw number, try to parse it
        if borrower["credit_score"] is None:
            try:
                borrower["credit_score"] = int(credit_raw)
            except (ValueError, TypeError):
                pass

    # --- Employment ---
    emp_raw = (context_data.get("employment") or context_data.get("employment_status") or "").strip().lower()
    if emp_raw:
        borrower["employment_type"] = EMPLOYMENT_MAP.get(emp_raw, emp_raw)

    # --- Loan purpose ---
    purpose_raw = (context_data.get("loan_purpose") or "").strip().lower()
    if purpose_raw:
        borrower["loan_purpose"] = purpose_raw

    # --- Property type ---
    prop_raw = (context_data.get("property_type") or "").strip().lower()
    if prop_raw:
        borrower["property_type"] = prop_raw

    # --- Price / loan amount ---
    price_raw = context_data.get("price_range") or context_data.get("property_value")
    if price_raw is not None:
        try:
            borrower["loan_amount"] = float(str(price_raw).replace("$", "").replace(",", "").strip())
        except (ValueError, TypeError):
            pass

    # --- Down payment -> rough LTV ---
    down_raw = context_data.get("down_payment")
    if down_raw is not None and borrower.get("loan_amount"):
        try:
            dp = float(str(down_raw).replace("$", "").replace(",", "").replace("%", "").strip())
            if dp <= 100:
                # Treat as a percentage
                borrower["ltv"] = 100 - dp
            else:
                # Treat as a dollar amount
                borrower["ltv"] = round(((borrower["loan_amount"] - dp) / borrower["loan_amount"]) * 100, 1)
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # --- Employment tenure (for self-employed checks) ---
    years_emp = context_data.get("years_in_current_employment") or context_data.get("years_employed")
    if years_emp is not None:
        try:
            borrower["years_in_current_employment"] = float(years_emp)
        except (ValueError, TypeError):
            pass

    # --- Bankruptcy / foreclosure (may be captured in later interactions) ---
    if context_data.get("years_since_bankruptcy") is not None:
        borrower["years_since_bankruptcy"] = context_data["years_since_bankruptcy"]
        borrower["bankruptcy_type"] = context_data.get("bankruptcy_type", "chapter_7")

    if context_data.get("years_since_foreclosure") is not None:
        borrower["years_since_foreclosure"] = context_data["years_since_foreclosure"]

    # --- Veteran status ---
    if context_data.get("is_veteran") is True:
        borrower["is_veteran"] = True

    # --- Income verifiability (rarely captured in SMS, but support it) ---
    if context_data.get("income_verifiable") is not None:
        borrower["income_verifiable"] = context_data["income_verifiable"]

    return borrower


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

async def evaluate_qualification_data(
    context_data: Dict[str, Any],
    lead_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate accumulated SMS qualification data against deal breaker rules.

    Args:
        context_data: The SMS conversation's context_data dict.
        lead_id: Optional lead ID for traceability.

    Returns:
        Structured dict with keys: has_deal_breakers, deal_breaker_list,
        eligible_programs, recommended_action, ai_response_text.
    """
    borrower_data = _map_context_to_borrower_data(context_data, lead_id)
    service: DealBreakerService = get_deal_breaker_service()
    result: DealBreakerResult = service.evaluate(borrower_data)

    response_text = generate_deal_breaker_response(result)

    return {
        "has_deal_breakers": result.has_deal_breakers,
        "deal_breaker_list": [
            {
                "name": db.name,
                "reason": db.reason,
                "severity": db.severity,
                "category": db.category,
                "remediation": db.remediation,
            }
            for db in result.deal_breakers
        ],
        "eligible_programs": result.eligible_programs,
        "recommended_action": result.recommended_action,
        "ai_response_text": response_text,
        "evaluation_id": result.evaluation_id,
        "borrower_data_used": borrower_data,
    }


# ---------------------------------------------------------------------------
# SMS response generation — ECOA compliant, always a path forward
# ---------------------------------------------------------------------------

_PROGRAM_FRIENDLY_NAMES: Dict[str, str] = {
    "conventional": "Conventional",
    "fha": "FHA",
    "fha_10pct_down": "FHA (10% down)",
    "va": "VA",
    "usda": "USDA",
    "jumbo": "Jumbo",
    "non_qm": "Non-QM / Bank Statement",
}

# Remediation-oriented responses for hard blockers, keyed by deal breaker name
_HARD_BLOCKER_RESPONSES: Dict[str, str] = {
    "credit_below_minimum": (
        "Based on what you've shared, we may need to work on strengthening your credit profile first. "
        "I can connect you with a trusted credit repair partner who helps people in similar situations "
        "and we'll check back in 6 months to get you on track."
    ),
    "recent_bankruptcy_ch7": (
        "Bankruptcy doesn't close the door — it just means a waiting period before you're eligible. "
        "I'll note your timeline and personally follow up when you're in the window for financing."
    ),
    "recent_bankruptcy_ch13": (
        "Being in a Chapter 13 plan actually shows you're taking the right steps. "
        "Depending on timing and court approval, FHA or VA could be an option. "
        "Let me have a loan officer review the details."
    ),
    "recent_foreclosure": (
        "A past foreclosure has waiting periods, but they do end. "
        "I'll set a reminder so we can reconnect when you're eligible — "
        "in the meantime, keeping credit strong will give you the best options."
    ),
    "dti_exceeds_maximum": (
        "Your debt-to-income ratio is a bit high for current programs. "
        "A quick call with a loan officer could uncover strategies — "
        "sometimes paying down a small balance makes a big difference. Want to chat?"
    ),
    "unlicensed_state": (
        "It looks like the property you're interested in is in a state we aren't licensed in. "
        "I can refer you to a trusted partner there so you're still in good hands."
    ),
}

_SOFT_BLOCKER_RESPONSES: Dict[str, str] = {
    "credit_fha_10pct_only": (
        "Great news — you still have options! An FHA loan with 10% down could work. "
        "A loan officer can walk you through the details. Want me to set up a call?"
    ),
    "self_employed_under_2yr": (
        "Self-employment income is totally workable. Bank statement loan programs can use "
        "12-24 months of deposits instead of tax returns. Let me connect you with someone "
        "who specializes in these."
    ),
    "no_verifiable_income": (
        "There are programs designed exactly for your situation — bank statement loans, "
        "asset-based lending, and more. A short call would help us find the best fit."
    ),
    "manufactured_home_restrictions": (
        "Manufactured homes do have some extra requirements, but FHA and VA both offer "
        "options depending on the foundation type. Let's get a loan officer to take a look."
    ),
    "ltv_exceeds_maximum": (
        "There are programs with very low or zero down payment — VA, USDA, "
        "and down payment assistance could help. Let me have someone dig into "
        "the best option for you."
    ),
    "non_resident_alien": (
        "There are loan programs available for your situation, including ITIN loans. "
        "Let me connect you with a loan officer who has experience with these."
    ),
}


def generate_deal_breaker_response(result: DealBreakerResult) -> str:
    """Generate a compassionate, ECOA-compliant SMS response based on deal breaker evaluation.

    Rules:
    - Never reference protected classes (race, religion, sex, national origin, etc.)
    - Never dead-end — always provide a path forward or nurture enrollment
    - Keep under 300 chars when possible (2 SMS segments) for single-issue responses
    - Use empathetic, forward-looking language
    """
    if not result.has_deal_breakers:
        # Clean — proceed to booking
        programs = [_PROGRAM_FRIENDLY_NAMES.get(p, p) for p in result.eligible_programs[:3]]
        if programs:
            program_str = ", ".join(programs)
            return (
                f"Based on what you've shared, you could be a great fit for {program_str} financing. "
                "Let me set up a quick call with a loan officer to go over your options — what time works best?"
            )
        return (
            "Based on what you've shared, it looks like you have solid options. "
            "Let me set up a quick call with a loan officer to go over next steps — when works best for you?"
        )

    hard_breakers = [b for b in result.deal_breakers if b.severity == "hard"]
    soft_breakers = [b for b in result.deal_breakers if b.severity == "soft"]

    # --- Hard blockers: lead with the most impactful, provide remediation ---
    if hard_breakers:
        primary = hard_breakers[0]
        response = _HARD_BLOCKER_RESPONSES.get(primary.name)
        if response:
            return response
        # Fallback for unknown hard blockers
        return (
            "Based on what you've shared, there are a couple of things to work through first — "
            "but that's totally normal and there IS a path forward. "
            "Want me to have a loan officer reach out to discuss your options?"
        )

    # --- Soft blockers only: emphasize alternative programs ---
    if soft_breakers:
        primary = soft_breakers[0]
        response = _SOFT_BLOCKER_RESPONSES.get(primary.name)
        if response:
            # If there are eligible programs, mention them
            if result.eligible_programs:
                programs = [_PROGRAM_FRIENDLY_NAMES.get(p, p) for p in result.eligible_programs[:2]]
                response += f" Programs like {', '.join(programs)} could be a great fit."
            return response
        # Fallback for unknown soft blockers
        programs = [_PROGRAM_FRIENDLY_NAMES.get(p, p) for p in result.eligible_programs[:3]]
        if programs:
            return (
                f"You have options! Programs like {', '.join(programs)} could work for your situation. "
                "Let me connect you with a loan officer who can dive into the details."
            )
        return (
            "There are definitely some programs that could work for you. "
            "A quick call with a loan officer would help nail down the best path. Want me to set that up?"
        )

    # Should not reach here, but safety fallback
    return (
        "Thanks for sharing that info! Let me connect you with a loan officer "
        "who can review everything and find the best program for you."
    )


# ---------------------------------------------------------------------------
# Readiness check — should we evaluate yet?
# ---------------------------------------------------------------------------

def should_evaluate(context_data: Dict[str, Any]) -> bool:
    """Return True when enough qualification data has been collected to run deal breaker evaluation.

    Minimum required: credit_score_range + loan_purpose.
    Returns False if already evaluated for this conversation (tracked via _deal_breaker_evaluated flag).
    """
    if context_data.get("_deal_breaker_evaluated"):
        return False

    has_credit = bool(
        context_data.get("credit_range")
        or context_data.get("credit_score_range")
    )
    has_purpose = bool(context_data.get("loan_purpose"))

    return has_credit and has_purpose


# ---------------------------------------------------------------------------
# Stage-transition hook
# ---------------------------------------------------------------------------

async def on_qualification_stage_complete(
    db: Session,
    conversation_id: str,
    lead_id: Optional[str],
    context_data: Dict[str, Any],
    organization_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Hook called when SMS conversation transitions past qualifying stage.

    Actions:
    - Evaluates collected data via DealBreakerService
    - If deal breakers found: pauses drip, routes to turn-down/nurture sequence
    - If clean: proceeds to appointment booking flow
    - Logs evaluation to ai_activity_log table

    Returns dict with evaluation results and routing decision.
    """
    if not should_evaluate(context_data):
        return {"action": "skip", "reason": "insufficient_data_or_already_evaluated"}

    # Run evaluation
    eval_result = await evaluate_qualification_data(context_data, lead_id)
    recommended = eval_result["recommended_action"]

    # Mark as evaluated in context_data (caller should persist this)
    context_data["_deal_breaker_evaluated"] = True
    context_data["_deal_breaker_result"] = {
        "evaluation_id": eval_result["evaluation_id"],
        "action": recommended,
        "has_deal_breakers": eval_result["has_deal_breakers"],
    }

    # Determine routing
    routing: Dict[str, Any] = {
        "action": recommended,
        "evaluation": eval_result,
        "conversation_id": conversation_id,
    }

    if recommended == "proceed":
        routing["next_stage"] = "scheduling"
        routing["sms_response"] = eval_result["ai_response_text"]
    elif recommended == "alternative_path":
        routing["next_stage"] = "scheduling"
        routing["sms_response"] = eval_result["ai_response_text"]
    elif recommended in ("nurture", "disqualify"):
        routing["next_stage"] = "nurture"
        routing["pause_drip"] = True
        routing["sms_response"] = eval_result["ai_response_text"]
    else:
        routing["next_stage"] = "scheduling"
        routing["sms_response"] = eval_result["ai_response_text"]

    # Log to ai_activity_log
    _log_evaluation(db, eval_result, lead_id, organization_id, conversation_id)

    logger.info(
        "Deal breaker evaluation complete for conversation %s: action=%s, breakers=%d",
        conversation_id,
        recommended,
        len(eval_result["deal_breaker_list"]),
    )

    return routing


# ---------------------------------------------------------------------------
# Activity logging
# ---------------------------------------------------------------------------

def _log_evaluation(
    db: Session,
    eval_result: Dict[str, Any],
    lead_id: Optional[str],
    organization_id: Optional[str],
    conversation_id: str,
) -> None:
    """Write deal breaker evaluation to ai_activity_log table."""
    try:
        from routes.ai_activity_routes import AIActivityLog

        breaker_count = len(eval_result["deal_breaker_list"])
        action = eval_result["recommended_action"]

        if action == "proceed":
            outcome = "success"
            outcome_label = "Qualified"
            title = "SMS qualification passed — no deal breakers"
        elif action == "alternative_path":
            outcome = "info"
            outcome_label = "Alternative Path"
            title = f"SMS qualification: {breaker_count} soft issue(s), alternatives available"
        elif action == "nurture":
            outcome = "warning"
            outcome_label = "Nurture"
            title = f"SMS qualification: {breaker_count} issue(s) found, moved to nurture"
        else:
            outcome = "critical"
            outcome_label = "Disqualified"
            title = f"SMS qualification: {breaker_count} hard blocker(s) detected"

        summary_parts = []
        for db_item in eval_result["deal_breaker_list"]:
            severity_tag = "HARD" if db_item["severity"] == "hard" else "SOFT"
            summary_parts.append(f"[{severity_tag}] {db_item['reason']}")
        if eval_result["eligible_programs"]:
            programs = ", ".join(eval_result["eligible_programs"])
            summary_parts.append(f"Eligible programs: {programs}")
        summary = "\n".join(summary_parts) if summary_parts else "No issues found — clear to proceed."

        log_entry = AIActivityLog(
            organization_id=int(organization_id) if organization_id else 0,
            loan_id=int(lead_id) if lead_id else 0,
            agent_type="deal-breaker",
            agent_label="Deal Breaker Radar",
            action_title=title,
            summary=summary,
            outcome=outcome,
            outcome_label=outcome_label,
            metadata_={
                "source": "sms_qualification",
                "conversation_id": conversation_id,
                "evaluation_id": eval_result["evaluation_id"],
                "deal_breakers": eval_result["deal_breaker_list"],
                "eligible_programs": eval_result["eligible_programs"],
            },
            detail_sections=[
                {"label": "Response Sent", "content": eval_result["ai_response_text"]},
            ],
            stats=[
                {"value": str(breaker_count), "label": "Issues Found"},
                {"value": str(len(eval_result["eligible_programs"])), "label": "Eligible Programs"},
                {"value": action.replace("_", " ").title(), "label": "Routing"},
            ],
        )
        db.add(log_entry)
        db.flush()
    except Exception as e:
        logger.exception("Failed to log deal breaker evaluation to ai_activity_log: %s", e)
