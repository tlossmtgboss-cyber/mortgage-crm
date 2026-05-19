"""
Governance Hooks — Convenience Wrapper

Single entry point that bundles the three D3 governance guardrails:

    * TokenBudgetManager      (cost governance)
    * ComplianceGuard         (TRID/RESPA/ECOA/TCPA/FDCPA red flags)
    * HallucinationGuard      (numeric/date grounding check)

Callers in `agents/service.py` (and any other LLM dispatch site) should
call `run_post_response_governance(...)` AFTER receiving an LLM response
and BEFORE returning it to the user.

The hook is best-effort: any exception inside a guard is logged and
swallowed so a guardrail failure can never break the response path.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .compliance_guard import compliance_guard
from .hallucination_guard import hallucination_guard
from .token_budget import token_budget_manager

logger = logging.getLogger(__name__)


def run_post_response_governance(
    *,
    agent_id: str,
    agent_role: str,
    response_text: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    context_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run all three governance checks against an LLM response.

    Returns:
        {
            "compliance":     {...},   # ComplianceGuard.validate_response result
            "hallucination":  {...},   # HallucinationGuard.verify_claims result
            "usage":          {...},   # TokenBudgetManager.get_usage snapshot
        }

    On internal failure, returns best-effort partial results without raising.
    """
    out: Dict[str, Any] = {"compliance": None, "hallucination": None, "usage": None}

    try:
        out["compliance"] = compliance_guard.validate_response(response_text, agent_role)
        if not out["compliance"]["passed"]:
            logger.warning(
                "Compliance violation by agent=%s role=%s violations=%s",
                agent_id, agent_role, out["compliance"]["violations"],
            )
    except Exception as exc:
        logger.error("ComplianceGuard failed for agent=%s: %s", agent_id, exc, exc_info=True)

    try:
        out["hallucination"] = hallucination_guard.verify_claims(response_text, context_data)
        if not out["hallucination"]["verified"]:
            logger.info(
                "Hallucination guard flagged unverified claims for agent=%s: %s (confidence=%.2f)",
                agent_id,
                out["hallucination"]["unverified_claims"],
                out["hallucination"]["confidence"],
            )
    except Exception as exc:
        logger.error("HallucinationGuard failed for agent=%s: %s", agent_id, exc, exc_info=True)

    try:
        token_budget_manager.record_usage(agent_id, input_tokens, output_tokens)
        out["usage"] = token_budget_manager.get_usage(agent_id)
    except Exception as exc:
        logger.error("TokenBudgetManager failed for agent=%s: %s", agent_id, exc, exc_info=True)

    return out
