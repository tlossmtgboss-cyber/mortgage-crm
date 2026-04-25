"""
Smart Docs Business Rules Configuration Routes

Admin endpoints for viewing and managing business rule configurations.
Rules control thresholds, limits, and settings that previously required
code deploys to change.

Endpoints:
- GET  /config/rules              — list all rules for the org
- GET  /config/rules/{category}   — list rules by category
- PUT  /config/rules/{rule_key}   — update a rule value (admin only)
- GET  /config/rules/{rule_key}/history — rule change history
- POST /config/rules/seed-defaults — seed default rules for org

All endpoints require authentication. Write operations require
Platform Admin or Site Admin role.
"""

import logging
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/config",
    tags=["business-rules"],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class RuleUpdateRequest(BaseModel):
    """Request body for updating a business rule."""
    value: Any = Field(..., description="The new rule value")
    effective_date: Optional[str] = Field(
        None,
        description="Effective date (YYYY-MM-DD). Defaults to today.",
    )
    expiration_date: Optional[str] = Field(
        None,
        description="Expiration date (YYYY-MM-DD). Null = no expiration.",
    )
    source: Optional[str] = Field(
        None,
        description="Regulatory source reference (e.g., 'irs_2026', 'fannie_mae').",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of the rule.",
    )


class RuleResponse(BaseModel):
    """Response for a single business rule."""
    rule_key: str
    rule_value: Any
    value_type: str
    rule_category: str
    description: Optional[str] = None
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    source: Optional[str] = None
    is_active: bool = True
    organization_id: Optional[int] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


# =============================================================================
# AUTH HELPERS
# =============================================================================

def _require_admin(user) -> None:
    """Verify the user is a Platform Admin or Site Admin.

    Raises HTTPException 403 if not authorized.
    """
    role = getattr(user, "role", None)
    if role not in ("Platform Admin", "Site Admin", "Admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin access required to modify business rules",
        )


def _get_org_id(user) -> Optional[int]:
    """Extract organization_id from user object."""
    return getattr(user, "organization_id", None)


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/rules")
async def list_rules(
    category: Optional[str] = Query(None, description="Filter by rule category"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all business rules for the current organization.

    Returns system defaults merged with any org-specific overrides.
    """
    org_id = _get_org_id(current_user)

    from services.smart_docs.business_rules_service import (
        BusinessRulesService,
        RULE_DEFAULTS,
    )

    service = BusinessRulesService(db)

    if category:
        values = service.get_rules_by_category(category, org_id=org_id)
        rules_output = []
        for key, val in values.items():
            default = RULE_DEFAULTS.get(key, {})
            rules_output.append({
                "rule_key": key,
                "rule_value": val,
                "value_type": default.get("value_type", "json"),
                "rule_category": category,
                "description": default.get("description"),
                "source": default.get("source"),
            })
    else:
        rules_output = []
        for key, default in RULE_DEFAULTS.items():
            val = service.get_rule(key, org_id=org_id)
            rules_output.append({
                "rule_key": key,
                "rule_value": val,
                "value_type": default.get("value_type", "json"),
                "rule_category": default.get("category"),
                "description": default.get("description"),
                "source": default.get("source"),
            })

    return {
        "status": "success",
        "organization_id": org_id,
        "count": len(rules_output),
        "rules": rules_output,
    }


@router.get("/rules/{category}")
async def list_rules_by_category(
    category: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all business rules in a specific category.

    Categories: income, fraud, document, followup, esign, compliance, ai
    """
    org_id = _get_org_id(current_user)

    from services.smart_docs.business_rules_service import (
        BusinessRulesService,
        RULE_DEFAULTS,
    )

    service = BusinessRulesService(db)
    values = service.get_rules_by_category(category, org_id=org_id)

    if not values:
        return {
            "status": "success",
            "category": category,
            "count": 0,
            "rules": [],
        }

    rules_output = []
    for key, val in values.items():
        default = RULE_DEFAULTS.get(key, {})
        rules_output.append({
            "rule_key": key,
            "rule_value": val,
            "value_type": default.get("value_type", "json"),
            "rule_category": category,
            "description": default.get("description"),
            "source": default.get("source"),
        })

    return {
        "status": "success",
        "category": category,
        "organization_id": org_id,
        "count": len(rules_output),
        "rules": rules_output,
    }


@router.put("/rules/{rule_key}")
async def update_rule(
    rule_key: str,
    body: RuleUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a business rule value. Admin only.

    Creates a new time-versioned entry if effective_date differs from
    any existing entry, or updates the existing entry if dates match.
    """
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    user_id = getattr(current_user, "id", None)

    from services.smart_docs.business_rules_service import BusinessRulesService, RULE_DEFAULTS

    # Validate rule_key is known
    if rule_key not in RULE_DEFAULTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown rule key: '{rule_key}'. "
                   f"Valid keys: {', '.join(sorted(RULE_DEFAULTS.keys()))}",
        )

    # Parse dates
    effective = None
    if body.effective_date:
        try:
            effective = date.fromisoformat(body.effective_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid effective_date format. Use YYYY-MM-DD.")

    expiration = None
    if body.expiration_date:
        try:
            expiration = date.fromisoformat(body.expiration_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expiration_date format. Use YYYY-MM-DD.")

    service = BusinessRulesService(db)

    try:
        rule = service.set_rule(
            rule_key=rule_key,
            value=body.value,
            org_id=org_id,
            effective_date=effective,
            expiration_date=expiration,
            source=body.source,
            description=body.description,
            updated_by=user_id,
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Failed to update rule '{rule_key}': {e}")
        raise HTTPException(status_code=500, detail="Failed to update rule")

    logger.info(
        f"Business rule updated: key={rule_key}, org={org_id}, "
        f"value={body.value}, by_user={user_id}"
    )

    return {
        "status": "success",
        "message": f"Rule '{rule_key}' updated",
        "rule": {
            "rule_key": rule.rule_key,
            "rule_value": rule.rule_value,
            "value_type": rule.value_type,
            "rule_category": rule.rule_category,
            "effective_date": rule.effective_date.isoformat() if rule.effective_date else None,
            "expiration_date": rule.expiration_date.isoformat() if rule.expiration_date else None,
            "source": rule.source,
            "organization_id": rule.organization_id,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        },
    }


@router.get("/rules/{rule_key}/history")
async def get_rule_history(
    rule_key: str,
    scope: str = Query("org", description="'org' for org-specific, 'system' for system defaults"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the full version history of a business rule.

    Returns all versions (active and inactive), ordered by effective_date desc.
    Useful for auditing when and why a rule changed.
    """
    org_id = _get_org_id(current_user) if scope == "org" else None

    from services.smart_docs.business_rules_service import BusinessRulesService

    service = BusinessRulesService(db)
    history = service.get_rule_history(rule_key, org_id=org_id)

    return {
        "status": "success",
        "rule_key": rule_key,
        "scope": scope,
        "organization_id": org_id,
        "count": len(history),
        "history": history,
    }


@router.post("/rules/seed-defaults")
async def seed_defaults(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Seed default business rules for the current organization.

    Creates DB rows for all known rules from RULE_DEFAULTS, skipping
    any that already exist. Admin only.
    """
    _require_admin(current_user)
    org_id = _get_org_id(current_user)
    user_id = getattr(current_user, "id", None)

    from services.smart_docs.business_rules_service import BusinessRulesService

    service = BusinessRulesService(db)

    try:
        created = service.seed_defaults(org_id=org_id, updated_by=user_id)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception(f"Failed to seed default rules: {e}")
        raise HTTPException(status_code=500, detail="Failed to seed defaults")

    return {
        "status": "success",
        "message": f"Seeded {created} default rules",
        "organization_id": org_id,
        "created": created,
    }
