"""
AI Prospect Re-Engagement Routes

Admin API for managing AI-driven prospect re-engagement:
config, monitoring, manual controls.
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prospect-reengagement", tags=["Prospect Re-Engagement"])


def _get_current_user():
    """Lazy import auth dependency to avoid circular imports."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible


# ============================================================================
# Request/Response Models
# ============================================================================

class ReengagementConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    stale_days: Optional[int] = None
    daily_limit: Optional[int] = None
    max_turns: Optional[int] = None
    expiry_days: Optional[int] = None
    initial_message_template: Optional[str] = None
    eligible_stages: Optional[List[str]] = None


class ManualInitiateResponse(BaseModel):
    success: bool
    lead_id: Optional[int] = None
    message_id: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


# ============================================================================
# Config Endpoints
# ============================================================================

@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Get re-engagement config for the current user's organization."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    from services.prospect_reengagement_service import ProspectReEngagementService
    svc = ProspectReEngagementService(db)
    config = svc.get_config(org_id)
    return {"status": "success", "data": config}


@router.put("/config")
def update_config(
    updates: ReengagementConfigUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Update re-engagement config for the current user's organization."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    # Validate ranges
    if updates.stale_days is not None and updates.stale_days < 7:
        raise HTTPException(status_code=400, detail="stale_days must be at least 7")
    if updates.daily_limit is not None and (updates.daily_limit < 1 or updates.daily_limit > 100):
        raise HTTPException(status_code=400, detail="daily_limit must be between 1 and 100")
    if updates.max_turns is not None and (updates.max_turns < 2 or updates.max_turns > 20):
        raise HTTPException(status_code=400, detail="max_turns must be between 2 and 20")

    # Upsert config
    existing = db.execute(text("""
        SELECT id FROM ai_reengagement_config WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    update_fields = {k: v for k, v in updates.dict().items() if v is not None}

    if existing:
        if update_fields:
            set_clauses = []
            params = {"org_id": org_id}
            for key, value in update_fields.items():
                if key == "eligible_stages":
                    import json
                    set_clauses.append(f"{key} = :val_{key}::jsonb")
                    params[f"val_{key}"] = json.dumps(value)
                else:
                    set_clauses.append(f"{key} = :val_{key}")
                    params[f"val_{key}"] = value
            set_clauses.append("updated_at = NOW()")

            db.execute(text(f"""
                UPDATE ai_reengagement_config
                SET {', '.join(set_clauses)}
                WHERE organization_id = :org_id
            """), params)
    else:
        import json
        db.execute(text("""
            INSERT INTO ai_reengagement_config (
                organization_id, enabled, stale_days, daily_limit,
                max_turns, expiry_days, initial_message_template,
                eligible_stages, created_at, updated_at
            ) VALUES (
                :org_id, :enabled, :stale_days, :daily_limit,
                :max_turns, :expiry_days, :template,
                :stages::jsonb, NOW(), NOW()
            )
        """), {
            "org_id": org_id,
            "enabled": updates.enabled or False,
            "stale_days": updates.stale_days or 30,
            "daily_limit": updates.daily_limit or 20,
            "max_turns": updates.max_turns or 8,
            "expiry_days": updates.expiry_days or 7,
            "template": updates.initial_message_template,
            "stages": json.dumps(updates.eligible_stages or [
                "Prospect", "Long-Term Nurture", "Attempted Contact", "New", "Credit Repair"
            ]),
        })

    db.commit()

    from services.prospect_reengagement_service import ProspectReEngagementService
    svc = ProspectReEngagementService(db)
    config = svc.get_config(org_id)
    return {"status": "success", "data": config}


# ============================================================================
# Conversation Endpoints
# ============================================================================

@router.get("/conversations")
def list_conversations(
    state: Optional[str] = Query(None),
    lo_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """List AI re-engagement conversations with optional filters."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    filters = ["c.organization_id = :org_id"]
    params = {"org_id": org_id, "limit": limit, "offset": offset}

    if state:
        filters.append("c.state = :state")
        params["state"] = state
    if lo_id:
        filters.append("c.lo_user_id = :lo_id")
        params["lo_id"] = lo_id

    where_sql = " AND ".join(filters)

    conversations = db.execute(text(f"""
        SELECT
            c.id, c.lead_id, c.lo_user_id, c.lead_phone,
            c.state, c.state_changed_at,
            c.turn_count, c.max_turns,
            c.outcome, c.booked_appointment_id,
            c.first_outreach_at, c.last_message_at, c.completed_at,
            c.created_at, c.expires_at,
            l.first_name as lead_first_name, l.last_name as lead_last_name,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name
        FROM ai_prospect_conversations c
        LEFT JOIN leads l ON l.id = c.lead_id
        LEFT JOIN users u ON u.id = c.lo_user_id
        WHERE {where_sql}
        ORDER BY c.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM ai_prospect_conversations c WHERE {where_sql}
    """), params).scalar() or 0

    data = []
    for row in conversations:
        r = dict(row._mapping)
        # Convert datetimes to ISO strings
        for key in ("state_changed_at", "first_outreach_at", "last_message_at",
                     "completed_at", "created_at", "expires_at"):
            if r.get(key) and hasattr(r[key], "isoformat"):
                r[key] = r[key].isoformat()
        data.append(r)

    return {"status": "success", "data": data, "total": total, "limit": limit, "offset": offset}


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Get a single conversation with full message history."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    conv = db.execute(text("""
        SELECT
            c.*,
            l.first_name as lead_first_name, l.last_name as lead_last_name,
            l.email as lead_email, l.stage as lead_stage,
            CONCAT(u.first_name, ' ', u.last_name) as lo_name
        FROM ai_prospect_conversations c
        LEFT JOIN leads l ON l.id = c.lead_id
        LEFT JOIN users u ON u.id = c.lo_user_id
        WHERE c.id = :id AND c.organization_id = :org_id
    """), {"id": conversation_id, "org_id": org_id}).fetchone()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    r = dict(conv._mapping)
    for key in ("state_changed_at", "first_outreach_at", "last_message_at",
                 "completed_at", "created_at", "expires_at"):
        if r.get(key) and hasattr(r[key], "isoformat"):
            r[key] = r[key].isoformat()

    return {"status": "success", "data": r}


# ============================================================================
# Stats
# ============================================================================

@router.get("/stats")
def get_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Get re-engagement stats dashboard."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    stats = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN state = 'initial_outreach_sent' THEN 1 END) as outreach_sent,
            COUNT(CASE WHEN state = 'awaiting_reply' THEN 1 END) as awaiting_reply,
            COUNT(CASE WHEN state = 'scheduling' THEN 1 END) as scheduling,
            COUNT(CASE WHEN state = 'appointment_booked' THEN 1 END) as booked,
            COUNT(CASE WHEN state = 'declined' THEN 1 END) as declined,
            COUNT(CASE WHEN state = 'opt_out' THEN 1 END) as opted_out,
            COUNT(CASE WHEN state = 'expired' THEN 1 END) as expired,
            COUNT(CASE WHEN state = 'cancelled' THEN 1 END) as cancelled,
            AVG(turn_count) as avg_turns,
            COUNT(CASE WHEN state IN ('initial_outreach_sent', 'awaiting_reply', 'scheduling') THEN 1 END) as active
        FROM ai_prospect_conversations
        WHERE organization_id = :org_id
          AND created_at >= NOW() - INTERVAL '1 day' * :days
    """), {"org_id": org_id, "days": days}).fetchone()

    if not stats:
        return {"status": "success", "data": {}}

    s = dict(stats._mapping)
    total = s.get("total", 0) or 0
    booked = s.get("booked", 0) or 0
    replied = total - (s.get("outreach_sent", 0) or 0) - (s.get("expired", 0) or 0)

    s["booking_rate"] = round((booked / total) * 100, 1) if total > 0 else 0
    s["response_rate"] = round((replied / total) * 100, 1) if total > 0 else 0
    s["period_days"] = days

    return {"status": "success", "data": s}


# ============================================================================
# Manual Controls
# ============================================================================

@router.post("/trigger-scan")
def trigger_scan(
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Manually trigger a prospect re-engagement scan for the current org."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    from services.prospect_reengagement_service import ProspectReEngagementService
    svc = ProspectReEngagementService(db)

    config = svc.get_config(org_id)
    if not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Re-engagement is not enabled for this organization")

    stale_days = config.get("stale_days", 30)
    daily_limit = config.get("daily_limit", 20)
    eligible_stages = config.get("eligible_stages")

    # Check daily limit
    sent_today = db.execute(text("""
        SELECT COUNT(*) FROM ai_prospect_conversations
        WHERE organization_id = :org_id AND first_outreach_at >= CURRENT_DATE
    """), {"org_id": org_id}).scalar() or 0

    remaining = max(0, daily_limit - sent_today)
    if remaining <= 0:
        return {
            "status": "success",
            "data": {"initiated": 0, "message": f"Daily limit reached ({sent_today}/{daily_limit})"},
        }

    prospects = svc.scan_stale_prospects(
        organization_id=org_id,
        stale_days=stale_days,
        limit=remaining,
        eligible_stages=eligible_stages,
    )

    initiated = 0
    errors = []
    for prospect in prospects:
        try:
            result = svc.initiate_outreach(prospect["id"])
            if result.get("success"):
                initiated += 1
            else:
                errors.append({"lead_id": prospect["id"], "error": result.get("error")})
        except Exception as e:
            logger.error(f"Manual scan — failed for lead {prospect['id']}: {e}")
            errors.append({"lead_id": prospect["id"], "error": str(e)})
            db.rollback()

    return {
        "status": "success",
        "data": {
            "scanned": len(prospects),
            "initiated": initiated,
            "errors": errors[:10],
            "sent_today_total": sent_today + initiated,
            "daily_limit": daily_limit,
        },
    }


@router.post("/initiate/{lead_id}")
def initiate_for_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Manually initiate AI re-engagement for a specific lead."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    # Verify lead belongs to org
    lead = db.execute(text("""
        SELECT id, organization_id FROM leads WHERE id = :lead_id
    """), {"lead_id": lead_id}).fetchone()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if dict(lead._mapping)["organization_id"] != org_id:
        raise HTTPException(status_code=403, detail="Lead does not belong to your organization")

    from services.prospect_reengagement_service import ProspectReEngagementService
    svc = ProspectReEngagementService(db)
    result = svc.initiate_outreach(lead_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to initiate outreach"))

    return {"status": "success", "data": result}


@router.post("/conversations/{conversation_id}/cancel")
def cancel_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(_get_current_user()),
):
    """Cancel an active AI re-engagement conversation."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")

    conv = db.execute(text("""
        SELECT id, state FROM ai_prospect_conversations
        WHERE id = :id AND organization_id = :org_id
    """), {"id": conversation_id, "org_id": org_id}).fetchone()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv_data = dict(conv._mapping)
    if conv_data["state"] in ("appointment_booked", "declined", "opt_out", "expired", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Conversation already in terminal state: {conv_data['state']}")

    db.execute(text("""
        UPDATE ai_prospect_conversations
        SET state = 'cancelled', state_changed_at = NOW(), completed_at = NOW(),
            outcome = 'cancelled', outcome_notes = 'Manually cancelled by admin'
        WHERE id = :id
    """), {"id": conversation_id})
    db.commit()

    return {"status": "success", "message": "Conversation cancelled"}
