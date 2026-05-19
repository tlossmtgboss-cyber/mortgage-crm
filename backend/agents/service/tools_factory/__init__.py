"""
Tools factory package — per-domain builders for the inline tool closures
previously defined in ``backend/agents/service/__init__.py``.

The original ``create_tool_functions_from_main`` function was a 1,861-line
monolith that defined every async tool closure inline. This package splits
those closures into per-domain modules without changing any behavior:

    ``_pipeline``   — pipeline & priorities tools
    ``_tasks``      — task read/create tools
    ``_leads``      — lead search & intelligence tools
    ``_loans``      — loan search & rate lock advisory
    ``_telephony``  — click-to-dial, SMS, bulk outreach
    ``_comms``      — email send/read, push notifications
    ``_partners``   — referral partner tools
    ``_analytics``  — historical performance/compare tools

Each sub-module exposes ``build_<domain>_tools(db, current_user, ctx) -> dict``.
The top-level :func:`build_tool_functions` composes them into a single dict
identical to what the original function returned.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _build_context(current_user: Any) -> Dict[str, Any]:
    """Compute shared authorization context once, mirroring the original code."""
    org_id = getattr(current_user, "organization_id", None)
    if org_id is None:
        logger.warning(
            f"[TOOLS] No organization_id on current_user (id={getattr(current_user, 'id', '?')}) "
            "— tenant isolation degraded for AI tool queries"
        )

    user_role = (getattr(current_user, "permission_role", "") or "").lower()
    has_org_wide_access = user_role in ("admin", "site_admin", "leadership", "management")
    if has_org_wide_access:
        logger.info(
            f"[TOOLS] User {getattr(current_user, 'id', '?')} has org-wide AI tool access (role={user_role})"
        )

    return {
        "org_id": org_id,
        "_user_role": user_role,
        "_has_org_wide_access": has_org_wide_access,
    }


def build_tool_functions(db: Session, current_user: Any) -> Dict[str, Callable]:
    """Compose all per-domain tool builders into the single dict the
    orchestrator/dispatcher expects.

    Identical in signature and semantics to the historical
    ``create_tool_functions_from_main`` — callers do not need to change.
    """
    ctx = _build_context(current_user)

    # Imported lazily so each sub-module is only loaded when needed and to
    # avoid any circular-import surprises at package import time.
    from ._pipeline import build_pipeline_tools
    from ._tasks import build_task_tools
    from ._leads import build_lead_tools
    from ._loans import build_loan_tools
    from ._telephony import build_telephony_tools
    from ._comms import build_comms_tools
    from ._partners import build_partner_tools
    from ._analytics import build_analytics_tools

    tools: Dict[str, Callable] = {}
    tools.update(build_pipeline_tools(db, current_user, ctx))
    tools.update(build_task_tools(db, current_user, ctx))
    tools.update(build_lead_tools(db, current_user, ctx))
    tools.update(build_loan_tools(db, current_user, ctx))
    tools.update(build_telephony_tools(db, current_user, ctx))
    tools.update(build_comms_tools(db, current_user, ctx))
    tools.update(build_partner_tools(db, current_user, ctx))
    tools.update(build_analytics_tools(db, current_user, ctx))
    return tools
