"""
Service-level governance helper.

Extracted from `backend/agents/service.py` (Wave 2 mechanical decomposition).
Wraps the Wave 1 post-response governance call so the agent service body
stays a single line at the call-site. Logic is unchanged.

The actual hook implementations live in `agents/orchestration/governance_hooks.py`.
This module only sequences the wiring + swallows non-fatal failures, identical
to the original inline block in `AIAgentService.process_message`.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from .orchestration.governance_hooks import run_post_response_governance
    _GOVERNANCE_HOOKS_AVAILABLE = True
except Exception:  # pragma: no cover - never break agent path
    _GOVERNANCE_HOOKS_AVAILABLE = False


def apply_post_response_governance(result: Any, current_user: Any) -> None:
    """Run Wave 1 post-response governance (compliance + token + hallucination).

    Identical semantics to the prior inline block in AIAgentService.process_message:
    - No-op if hooks module is unavailable.
    - Swallows all exceptions at debug level (must not break agent path).
    """
    if not _GOVERNANCE_HOOKS_AVAILABLE:
        return
    try:
        _response_text = result.get("response", "") if isinstance(result, dict) else ""
        _usage = result.get("usage", {}) if isinstance(result, dict) else {}
        run_post_response_governance(
            agent_id=str(getattr(current_user, "id", "unknown")),
            agent_role=getattr(current_user, "role", "loan_officer"),
            response_text=_response_text,
            input_tokens=int(_usage.get("input_tokens", 0) or 0),
            output_tokens=int(_usage.get("output_tokens", 0) or 0),
            context_data=result if isinstance(result, dict) else None,
        )
    except Exception as _gov_exc:  # pragma: no cover
        logger.debug(f"Governance hook non-fatal failure: {_gov_exc}")
