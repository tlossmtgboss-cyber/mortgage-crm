"""
UPL (Unauthorized Practice of Law) Routes

Endpoints for inspecting and querying the multi-state UPL rules engine.

NOTE: Engine results are a software check, not legal advice.

Endpoints:
    GET  /api/v1/compliance/upl/rules/{state_abbr} - Return rule set for state
    POST /api/v1/compliance/upl/check              - Run an action check
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UPLCheckRequest(BaseModel):
    action: str = Field(..., description="One of SUPPORTED_ACTIONS")
    state: str = Field(..., description="State abbreviation (e.g., CA, NY)")
    context: Optional[Dict[str, Any]] = None


class UPLCheckResponse(BaseModel):
    allowed: bool
    action: str
    state: str
    restrictions: list[str]
    warnings: list[str]
    required_disclosures: list[str]
    regulatory_citations: list[str]
    state_rules_version: str
    blocking_restrictions: Optional[list[str]] = None


class UPLRuleSetResponse(BaseModel):
    state: str
    state_rules_version: str
    restrictions: list[str]
    warnings: list[str]
    required_disclosures: list[str]
    regulatory_citations: list[str]
    last_updated: str
    modeled: bool = False


# ---------------------------------------------------------------------------
# Lazy auth dep — uses main.get_current_user (matches existing route pattern)
# ---------------------------------------------------------------------------

def _get_current_user_dep():
    """Resolve get_current_user lazily to avoid import cycles at module load."""
    try:
        from main import get_current_user  # type: ignore
        return get_current_user
    except Exception:  # pragma: no cover — fall back to auth dependencies
        from auth.dependencies import get_current_user  # type: ignore
        return get_current_user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/api/v1/compliance/upl/rules/{state_abbr}",
    response_model=UPLRuleSetResponse,
)
def get_upl_rules(
    state_abbr: str,
    _user=Depends(_get_current_user_dep()),
) -> UPLRuleSetResponse:
    """Return the full UPL rule set for a state."""
    from services.compliance.upl_rules_engine import upl_rules_engine

    if not state_abbr or len(state_abbr.strip()) > 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="state_abbr must be a valid state/territory code",
        )

    rule = upl_rules_engine.get_rule_set(state_abbr)
    return UPLRuleSetResponse(
        state=rule["state"],
        state_rules_version=rule["state_rules_version"],
        restrictions=rule["restrictions"],
        warnings=rule["warnings"],
        required_disclosures=rule["required_disclosures"],
        regulatory_citations=rule["regulatory_citations"],
        last_updated=rule.get("last_updated", ""),
        modeled=bool(rule.get("modeled", False)),
    )


@router.post(
    "/api/v1/compliance/upl/check",
    response_model=UPLCheckResponse,
)
def check_upl_action(
    body: UPLCheckRequest,
    _user=Depends(_get_current_user_dep()),
) -> UPLCheckResponse:
    """Check whether an action is permitted for the given state."""
    from services.compliance.upl_rules_engine import (
        SUPPORTED_ACTIONS,
        upl_rules_engine,
    )

    if body.action not in SUPPORTED_ACTIONS:
        # Engine handles this by returning allowed=False, but reject upfront
        # so callers get a clear 400.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown action '{body.action}'. "
                   f"Supported: {sorted(SUPPORTED_ACTIONS)}",
        )

    result = upl_rules_engine.check(body.action, body.state, body.context or {})
    return UPLCheckResponse(
        allowed=bool(result["allowed"]),
        action=result["action"],
        state=result["state"],
        restrictions=result["restrictions"],
        warnings=result["warnings"],
        required_disclosures=result["required_disclosures"],
        regulatory_citations=result["regulatory_citations"],
        state_rules_version=result["state_rules_version"],
        blocking_restrictions=result.get("blocking_restrictions"),
    )


__all__ = ["router"]
