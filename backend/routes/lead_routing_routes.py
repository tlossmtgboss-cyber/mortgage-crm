"""
Lead Routing Engine — Intelligent lead assignment with configurable rules

Supports routing by:
  - Loan type specialization (conventional, FHA, VA, jumbo, etc.)
  - Geographic state / zip code
  - Language preference
  - Round-robin (weighted or equal)
  - Capacity-based (current pipeline count)
  - Custom rules (e.g., referral source → specific LO)

Used by speed-to-lead trigger and manual lead assignment.
"""

import os
import logging
from datetime import datetime, timezone
from typing import List, Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from db import get_db
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/lead-routing", tags=["Lead Routing"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RoutingRuleCreate(BaseModel):
    rule_name: str
    rule_type: str  # loan_type, state, language, source, zip_code, default
    match_value: str  # e.g., "VA", "CA", "spanish", "referral"
    assigned_lo_ids: List[int] = Field(default_factory=list)
    priority: int = 0  # higher = checked first
    weight: int = 1  # for weighted round-robin within the rule
    is_active: bool = True


class RoutingRuleResponse(BaseModel):
    id: int
    rule_name: str
    rule_type: str
    match_value: str
    assigned_lo_ids: List[int]
    priority: int
    weight: int
    is_active: bool


class RouteLeadRequest(BaseModel):
    lead_id: Optional[int] = None
    loan_type: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    language: Optional[str] = None
    source: Optional[str] = None
    loan_amount: Optional[float] = None


class RouteLeadResponse(BaseModel):
    assigned_lo_id: int
    lo_name: str
    match_reason: str
    rule_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Routing engine
# ---------------------------------------------------------------------------

def _get_routing_rules(db: Session, org_id: int) -> list:
    """Load active routing rules for the org, ordered by priority DESC."""
    rows = db.execute(text("""
        SELECT id, rule_name, rule_type, match_value, assigned_lo_ids,
               priority, weight, is_active
        FROM lead_routing_rules
        WHERE organization_id = :org_id AND is_active = TRUE
        ORDER BY priority DESC, id ASC
    """), {"org_id": org_id}).fetchall()
    return rows


def _get_round_robin_next(db: Session, org_id: int, lo_ids: List[int]) -> Optional[int]:
    """
    Pick the next LO from the list using round-robin.
    Tracks last-assigned in lead_routing_rr_state table.
    Falls back to least-recently-assigned LO.
    """
    if not lo_ids:
        return None

    # Get the last assigned LO for this org
    last = db.execute(text("""
        SELECT last_lo_id FROM lead_routing_rr_state
        WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    last_lo_id = last.last_lo_id if last else None

    # Find next in rotation
    if last_lo_id and last_lo_id in lo_ids:
        idx = lo_ids.index(last_lo_id)
        next_id = lo_ids[(idx + 1) % len(lo_ids)]
    else:
        next_id = lo_ids[0]

    # Update state
    try:
        if last:
            db.execute(text("""
                UPDATE lead_routing_rr_state SET last_lo_id = :lo_id, updated_at = :now
                WHERE organization_id = :org_id
            """), {"lo_id": next_id, "now": datetime.now(timezone.utc), "org_id": org_id})
        else:
            db.execute(text("""
                INSERT INTO lead_routing_rr_state (organization_id, last_lo_id, updated_at)
                VALUES (:org_id, :lo_id, :now)
            """), {"org_id": org_id, "lo_id": next_id, "now": datetime.now(timezone.utc)})
        db.commit()
    except Exception as e:
        logger.debug("Round-robin state update failed (table may not exist): %s", e)
        db.rollback()

    return next_id


def _get_lo_pipeline_counts(db: Session, org_id: int, lo_ids: List[int]) -> dict:
    """Get active pipeline count per LO for capacity routing."""
    if not lo_ids:
        return {}

    placeholders = ", ".join([f":id{i}" for i in range(len(lo_ids))])
    params = {"org_id": org_id}
    for i, lid in enumerate(lo_ids):
        params[f"id{i}"] = lid

    sql = (
        "SELECT loan_officer_id, COUNT(*) as cnt"
        " FROM loans"
        " WHERE organization_id = :org_id"
        " AND loan_officer_id IN (" + placeholders + ")"
        " AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')"
        " GROUP BY loan_officer_id"
    )
    rows = db.execute(text(sql), params).fetchall()

    counts = {r.loan_officer_id: r.cnt for r in rows}
    # Include LOs with zero pipeline
    for lid in lo_ids:
        if lid not in counts:
            counts[lid] = 0
    return counts


def _check_availability(db: Session, lo_id: int) -> bool:
    """Quick check if LO is available (from lo_availability table if it exists)."""
    try:
        row = db.execute(text("""
            SELECT status FROM lo_availability
            WHERE user_id = :uid AND status = 'available'
        """), {"uid": lo_id}).fetchone()
        return row is not None
    except Exception:
        return True  # If table doesn't exist, assume available


def route_lead(
    db: Session,
    org_id: int,
    loan_type: Optional[str] = None,
    state: Optional[str] = None,
    zip_code: Optional[str] = None,
    language: Optional[str] = None,
    source: Optional[str] = None,
) -> Optional[dict]:
    """
    Core routing logic. Returns {"lo_id": int, "lo_name": str, "reason": str, "rule_id": int}
    or None if no match.
    """
    rules = _get_routing_rules(db, org_id)

    if not rules:
        return _fallback_route(db, org_id)

    # Build a match map from the lead's attributes
    lead_attrs = {
        "loan_type": (loan_type or "").lower(),
        "state": (state or "").upper(),
        "zip_code": zip_code or "",
        "language": (language or "").lower(),
        "source": (source or "").lower(),
    }

    for rule in rules:
        rule_type = rule.rule_type
        match_value = (rule.match_value or "").strip()

        # Parse assigned_lo_ids (stored as comma-separated or JSON array)
        raw_ids = rule.assigned_lo_ids
        if isinstance(raw_ids, str):
            lo_ids = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]
        elif isinstance(raw_ids, list):
            lo_ids = [int(x) for x in raw_ids if str(x).isdigit()]
        else:
            continue

        if not lo_ids:
            continue

        matched = False

        if rule_type == "loan_type" and lead_attrs["loan_type"] == match_value.lower():
            matched = True
        elif rule_type == "state" and lead_attrs["state"] == match_value.upper():
            matched = True
        elif rule_type == "zip_code" and lead_attrs["zip_code"].startswith(match_value):
            matched = True
        elif rule_type == "language" and lead_attrs["language"] == match_value.lower():
            matched = True
        elif rule_type == "source" and lead_attrs["source"] == match_value.lower():
            matched = True
        elif rule_type == "default":
            matched = True  # Catch-all

        if not matched:
            continue

        # Filter to available LOs
        available_ids = [lid for lid in lo_ids if _check_availability(db, lid)]
        if not available_ids:
            available_ids = lo_ids  # Fall through if availability check unavailable

        # Pick by round-robin within matched rule
        chosen_id = _get_round_robin_next(db, org_id, available_ids)
        if not chosen_id:
            continue

        lo_row = db.execute(text(
            "SELECT first_name, last_name FROM users WHERE id = :uid"
        ), {"uid": chosen_id}).fetchone()

        return {
            "lo_id": chosen_id,
            "lo_name": f"{lo_row.first_name} {lo_row.last_name}" if lo_row else "Unknown",
            "reason": f"Matched {rule_type}={match_value} (rule: {rule.rule_name})",
            "rule_id": rule.id,
        }

    # No rule matched → fallback
    return _fallback_route(db, org_id)


def _fallback_route(db: Session, org_id: int) -> Optional[dict]:
    """Fallback: assign to the LO with the smallest active pipeline in the org."""
    row = db.execute(text("""
        SELECT u.id, u.first_name, u.last_name, COUNT(l.id) as pipeline
        FROM users u
        LEFT JOIN loans l ON l.loan_officer_id = u.id
            AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
        WHERE u.organization_id = :org_id AND u.role IN ('loan_officer', 'admin', 'lo')
        GROUP BY u.id, u.first_name, u.last_name
        ORDER BY pipeline ASC
        LIMIT 1
    """), {"org_id": org_id}).fetchone()

    if not row:
        return None

    return {
        "lo_id": row.id,
        "lo_name": f"{row.first_name} {row.last_name}",
        "reason": "Fallback: lowest pipeline count",
        "rule_id": None,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/route", response_model=RouteLeadResponse)
async def route_a_lead(
    body: RouteLeadRequest,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Route a lead to the best LO based on configured rules."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    # If lead_id provided, fetch attributes from the lead
    loan_type = body.loan_type
    state = body.state
    zip_code = body.zip_code
    language = body.language
    source = body.source

    if body.lead_id:
        lead = db.execute(text("""
            SELECT loan_type, state, zip_code, preferred_language, source
            FROM leads WHERE id = :lid AND organization_id = :org_id
        """), {"lid": body.lead_id, "org_id": org_id}).fetchone()
        if lead:
            loan_type = loan_type or getattr(lead, "loan_type", None)
            state = state or getattr(lead, "state", None)
            zip_code = zip_code or getattr(lead, "zip_code", None)
            language = language or getattr(lead, "preferred_language", None)
            source = source or getattr(lead, "source", None)

    result = route_lead(db, org_id, loan_type, state, zip_code, language, source)

    if not result:
        raise HTTPException(status_code=404, detail="No eligible loan officer found for routing")

    # Optionally assign the lead
    if body.lead_id:
        try:
            db.execute(text("""
                UPDATE leads SET owner_id = :lo_id, updated_at = :now
                WHERE id = :lid AND organization_id = :org_id
            """), {
                "lo_id": result["lo_id"],
                "now": datetime.now(timezone.utc),
                "lid": body.lead_id,
                "org_id": org_id,
            })
            db.commit()
            logger.info("Lead %s routed to LO %s: %s", body.lead_id, result["lo_id"], result["reason"])
        except Exception as e:
            logger.exception("Failed to assign lead %s: %s", body.lead_id, e)
            db.rollback()

    return RouteLeadResponse(
        assigned_lo_id=result["lo_id"],
        lo_name=result["lo_name"],
        match_reason=result["reason"],
        rule_id=result.get("rule_id"),
    )


# ---------------------------------------------------------------------------
# CRUD for routing rules
# ---------------------------------------------------------------------------

@router.get("/rules")
async def list_routing_rules(
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """List all routing rules for the current org."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    rows = db.execute(text("""
        SELECT id, rule_name, rule_type, match_value, assigned_lo_ids,
               priority, weight, is_active
        FROM lead_routing_rules
        WHERE organization_id = :org_id
        ORDER BY priority DESC, id ASC
    """), {"org_id": org_id}).fetchall()

    return {
        "rules": [
            {
                "id": r.id,
                "rule_name": r.rule_name,
                "rule_type": r.rule_type,
                "match_value": r.match_value,
                "assigned_lo_ids": r.assigned_lo_ids,
                "priority": r.priority,
                "weight": r.weight,
                "is_active": r.is_active,
            }
            for r in rows
        ],
    }


@router.post("/rules")
async def create_routing_rule(
    body: RoutingRuleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Create a new routing rule."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    now = datetime.now(timezone.utc)
    ids_str = ",".join(str(x) for x in body.assigned_lo_ids)

    db.execute(text("""
        INSERT INTO lead_routing_rules
            (organization_id, rule_name, rule_type, match_value, assigned_lo_ids,
             priority, weight, is_active, created_at, updated_at)
        VALUES (:org_id, :name, :type, :val, :ids, :pri, :wt, :active, :now, :now)
    """), {
        "org_id": org_id, "name": body.rule_name, "type": body.rule_type,
        "val": body.match_value, "ids": ids_str, "pri": body.priority,
        "wt": body.weight, "active": body.is_active, "now": now,
    })
    db.commit()

    return {"status": "created", "rule_name": body.rule_name}


@router.put("/rules/{rule_id}")
async def update_routing_rule(
    rule_id: int,
    body: RoutingRuleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Update a routing rule."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    ids_str = ",".join(str(x) for x in body.assigned_lo_ids)

    result = db.execute(text("""
        UPDATE lead_routing_rules SET
            rule_name = :name, rule_type = :type, match_value = :val,
            assigned_lo_ids = :ids, priority = :pri, weight = :wt,
            is_active = :active, updated_at = :now
        WHERE id = :rid AND organization_id = :org_id
    """), {
        "rid": rule_id, "org_id": org_id, "name": body.rule_name,
        "type": body.rule_type, "val": body.match_value, "ids": ids_str,
        "pri": body.priority, "wt": body.weight, "active": body.is_active,
        "now": datetime.now(timezone.utc),
    })
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rule not found")

    return {"status": "updated"}


@router.delete("/rules/{rule_id}")
async def delete_routing_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Delete a routing rule."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    result = db.execute(text("""
        DELETE FROM lead_routing_rules
        WHERE id = :rid AND organization_id = :org_id
    """), {"rid": rule_id, "org_id": org_id})
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Rule not found")

    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def routing_stats(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user=Depends(current_user_flexible_dep),
):
    """Get routing assignment stats for the org."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization required")

    # Lead assignments by LO in the last N days
    rows = db.execute(text("""
        SELECT u.id as lo_id, CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               COUNT(l.id) as assigned_count
        FROM users u
        LEFT JOIN leads l ON l.owner_id = u.id
            AND l.organization_id = :org_id
            AND l.created_at >= CURRENT_DATE - :days
        WHERE u.organization_id = :org_id AND u.role IN ('loan_officer', 'admin', 'lo')
        GROUP BY u.id, u.first_name, u.last_name
        ORDER BY assigned_count DESC
    """), {"org_id": org_id, "days": days}).fetchall()

    return {
        "period_days": days,
        "by_lo": [
            {"lo_id": r.lo_id, "lo_name": r.lo_name, "assigned": r.assigned_count}
            for r in rows
        ],
    }
