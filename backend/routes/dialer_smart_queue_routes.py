"""
Power Dialer Smart Queue Routes

Intelligent call queue builder with filtering by last_contacted, stage, score,
and priority scoring. Supports both lead-based and loan-pipeline-based queues.

Endpoints:
    POST /api/v1/dialer/smart-queue           — Build smart queue from leads
    GET  /api/v1/dialer/smart-queue/presets    — Pre-built queue templates
    POST /api/v1/dialer/smart-queue/from-pipeline — Build queue from loan pipeline
    GET  /api/v1/dialer/smart-queue/{queue_id} — Get queue with position
    POST /api/v1/dialer/smart-queue/{queue_id}/next     — Next number to dial
    POST /api/v1/dialer/smart-queue/{queue_id}/skip     — Skip current item
    POST /api/v1/dialer/smart-queue/{queue_id}/complete — Mark called, advance
    GET  /api/v1/dialer/smart-queue/metrics    — Queue performance metrics
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import current_user_flexible_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dialer", tags=["Smart Queue"])


# =============================================================================
# Ensure tables exist at import time (production-safe pattern)
# =============================================================================

_tables_ensured = False


def _ensure_tables():
    """Create smart queue tables if they don't exist (idempotent)."""
    global _tables_ensured
    if _tables_ensured:
        return
    try:
        from db import engine
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dialer_smart_queues (
                    id VARCHAR(36) PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    name VARCHAR(255) NOT NULL,
                    queue_type VARCHAR(50) NOT NULL DEFAULT 'lead',
                    filters JSONB,
                    total_items INTEGER NOT NULL DEFAULT 0,
                    completed_items INTEGER NOT NULL DEFAULT 0,
                    skipped_items INTEGER NOT NULL DEFAULT 0,
                    current_position INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dialer_smart_queue_items (
                    id SERIAL PRIMARY KEY,
                    queue_id VARCHAR(36) NOT NULL REFERENCES dialer_smart_queues(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    contact_phone VARCHAR(50) NOT NULL,
                    contact_name VARCHAR(255),
                    lead_id INTEGER,
                    loan_id INTEGER,
                    priority_score INTEGER NOT NULL DEFAULT 0,
                    context JSONB,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    called_at TIMESTAMPTZ,
                    disposition VARCHAR(100),
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_dsq_user_status
                    ON dialer_smart_queues (user_id, status)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_dsqi_queue_position
                    ON dialer_smart_queue_items (queue_id, position)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_dsqi_queue_status
                    ON dialer_smart_queue_items (queue_id, status)
            """))
            conn.commit()
        _tables_ensured = True
        logger.info("Smart queue tables verified")
    except Exception as e:
        logger.warning(f"Smart queue table creation check (non-fatal): {e}")


_ensure_tables()


# =============================================================================
# Pydantic Models
# =============================================================================

class SmartQueueBuildRequest(BaseModel):
    """Request to build a smart call queue from leads."""
    name: Optional[str] = Field(None, description="Queue name (auto-generated if omitted)")
    stages: Optional[List[str]] = Field(None, description="Lead stages to include")
    min_score: Optional[int] = Field(None, ge=0, le=100, description="Minimum AI score")
    max_score: Optional[int] = Field(None, ge=0, le=100, description="Maximum AI score")
    sources: Optional[List[str]] = Field(None, description="Lead sources to include")
    states: Optional[List[str]] = Field(None, description="US states to include")
    not_contacted_days: Optional[int] = Field(None, ge=0, description="Days since last contact")
    owner_id: Optional[int] = Field(None, description="Specific LO's leads (default: current user)")
    loan_types: Optional[List[str]] = Field(None, description="Loan types to include")
    exclude_dnc: bool = Field(True, description="Exclude DNC numbers")
    limit: int = Field(200, ge=1, le=500, description="Max items in queue")


class PipelineQueueBuildRequest(BaseModel):
    """Request to build a call queue from the loan pipeline."""
    name: Optional[str] = Field(None, description="Queue name")
    stages: Optional[List[str]] = Field(None, description="Loan stages to include")
    lock_expiring_days: Optional[int] = Field(None, ge=0, description="Lock expires within N days")
    closing_within_days: Optional[int] = Field(None, ge=0, description="Closing date within N days")
    stale_days: Optional[int] = Field(None, ge=0, description="Days in stage threshold")
    exclude_dnc: bool = Field(True, description="Exclude DNC numbers")
    limit: int = Field(200, ge=1, le=500)


class QueueItemCompleteRequest(BaseModel):
    """Mark current queue item as complete."""
    disposition: Optional[str] = Field(None, description="Call disposition")
    notes: Optional[str] = Field(None, description="Call notes")


# =============================================================================
# Priority Scoring
# =============================================================================

def _calculate_lead_priority(row: dict, now: datetime) -> int:
    """Calculate priority score for a lead (higher = call sooner)."""
    score = 0

    # AI score contribution (0-30 points)
    ai_score = row.get("ai_score")
    if ai_score is not None:
        score += min(int(ai_score * 0.3), 30)

    # Recency penalty (0-25 points) -- longer since contact = more urgent
    last_contact = row.get("last_contact")
    if last_contact:
        if hasattr(last_contact, "tzinfo") and last_contact.tzinfo is None:
            last_contact = last_contact.replace(tzinfo=timezone.utc)
        days = (now - last_contact).days
        score += min(days * 2, 25)
    else:
        score += 25  # Never contacted = high priority

    # Stage priority (0-25 points)
    stage_scores = {
        "New": 25,
        "Attempted Contact": 20,
        "Prospect": 18,
        "Pre-Qualified": 15,
        "Application": 10,
        "Pre-Approved": 8,
    }
    score += stage_scores.get(row.get("stage"), 5)

    # Source priority (0-20 points)
    hot_sources = {
        "referral": 20,
        "rate_quote": 18,
        "application_started": 15,
        "website": 10,
        "landing_page": 10,
    }
    score += hot_sources.get(row.get("source") or "", 5)

    return round(score)


def _calculate_pipeline_priority(row: dict, now: datetime) -> int:
    """Calculate priority score for a loan pipeline item."""
    score = 0

    # Lock expiration urgency (0-40 points)
    lock_exp = row.get("lock_expiration_date")
    if lock_exp:
        if hasattr(lock_exp, "tzinfo") and lock_exp.tzinfo is None:
            lock_exp = lock_exp.replace(tzinfo=timezone.utc)
        days_left = (lock_exp - now).days
        if days_left <= 0:
            score += 40  # Already expired
        elif days_left <= 3:
            score += 35
        elif days_left <= 7:
            score += 25
        elif days_left <= 14:
            score += 15

    # Closing date urgency (0-30 points)
    closing = row.get("closing_date")
    if closing:
        if hasattr(closing, "tzinfo") and closing.tzinfo is None:
            closing = closing.replace(tzinfo=timezone.utc)
        days_to_close = (closing - now).days
        if days_to_close <= 3:
            score += 30
        elif days_to_close <= 7:
            score += 25
        elif days_to_close <= 14:
            score += 15
        elif days_to_close <= 30:
            score += 10

    # Stale stage penalty (0-20 points)
    stage_changed = row.get("stage_changed_at")
    if stage_changed:
        if hasattr(stage_changed, "tzinfo") and stage_changed.tzinfo is None:
            stage_changed = stage_changed.replace(tzinfo=timezone.utc)
        days_in_stage = (now - stage_changed).days
        score += min(days_in_stage * 2, 20)

    # Stage weight (0-10 points) -- closing stages get priority
    closing_stages = {"CTC", "CLEAR_TO_CLOSE", "DOCS", "DOCS_OUT", "CLOSING"}
    if row.get("stage") in closing_stages:
        score += 10

    return round(score)


# =============================================================================
# Helper: DNC subquery fragment
# =============================================================================

def _dnc_subquery(org_id: int) -> str:
    """Return a SQL fragment for DNC exclusion."""
    return (
        f"AND phone NOT IN ("
        f"  SELECT phone_number FROM contact_dnc_status "
        f"  WHERE organization_id = {int(org_id)}"
        f")"
    )


def _dnc_subquery_borrower(org_id: int) -> str:
    """Return a SQL fragment for DNC exclusion on borrower_phone."""
    return (
        f"AND borrower_phone NOT IN ("
        f"  SELECT phone_number FROM contact_dnc_status "
        f"  WHERE organization_id = {int(org_id)}"
        f")"
    )


# =============================================================================
# Helper: persist queue to DB
# =============================================================================

def _save_queue(db: Session, queue_id: str, user_id: int, org_id: int,
                name: str, queue_type: str, filters: dict, items: list):
    """Insert queue header and items into DB."""
    now_ts = datetime.now(timezone.utc).isoformat()
    db.execute(text("""
        INSERT INTO dialer_smart_queues
            (id, organization_id, user_id, name, queue_type, filters,
             total_items, current_position, status, created_at, updated_at)
        VALUES
            (:id, :org_id, :user_id, :name, :queue_type, :filters::jsonb,
             :total, 0, 'active', :now, :now)
    """), {
        "id": queue_id,
        "org_id": org_id,
        "user_id": user_id,
        "name": name,
        "queue_type": queue_type,
        "filters": __import__("json").dumps(filters),
        "total": len(items),
        "now": now_ts,
    })

    for idx, item in enumerate(items):
        db.execute(text("""
            INSERT INTO dialer_smart_queue_items
                (queue_id, position, contact_phone, contact_name,
                 lead_id, loan_id, priority_score, context, status)
            VALUES
                (:queue_id, :pos, :phone, :name, :lead_id, :loan_id,
                 :priority, :context::jsonb, 'pending')
        """), {
            "queue_id": queue_id,
            "pos": idx,
            "phone": item["phone"],
            "name": item.get("contact_name"),
            "lead_id": item.get("lead_id"),
            "loan_id": item.get("loan_id"),
            "priority": item.get("priority_score", 0),
            "context": __import__("json").dumps(item.get("context", {})),
        })

    db.commit()


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/smart-queue")
async def build_smart_queue(
    body: SmartQueueBuildRequest,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Build an intelligent call queue from leads based on filters and priority scoring."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    owner_id = body.owner_id or current_user.id
    now = datetime.now(timezone.utc)

    # Build dynamic WHERE clause
    conditions = [
        "l.organization_id = :org_id",
        "l.phone IS NOT NULL",
        "l.phone != ''",
        "l.stage NOT IN ('Closed', 'Funded', 'Withdrawn', 'Does Not Qualify', 'Do Not Call')",
    ]
    params: dict = {"org_id": org_id, "owner_id": owner_id, "limit": body.limit}

    conditions.append("l.owner_id = :owner_id")

    if body.stages:
        conditions.append("l.stage = ANY(:stages)")
        params["stages"] = body.stages

    if body.min_score is not None:
        conditions.append("COALESCE(l.ai_score, 0) >= :min_score")
        params["min_score"] = body.min_score

    if body.max_score is not None:
        conditions.append("COALESCE(l.ai_score, 0) <= :max_score")
        params["max_score"] = body.max_score

    if body.sources:
        conditions.append("l.source = ANY(:sources)")
        params["sources"] = body.sources

    if body.states:
        conditions.append("l.state = ANY(:states)")
        params["states"] = body.states

    if body.not_contacted_days is not None:
        cutoff = now - timedelta(days=body.not_contacted_days)
        conditions.append("(l.last_contact IS NULL OR l.last_contact <= :contact_cutoff)")
        params["contact_cutoff"] = cutoff

    if body.loan_types:
        conditions.append("l.loan_type = ANY(:loan_types)")
        params["loan_types"] = body.loan_types

    if body.exclude_dnc:
        conditions.append(
            "l.phone NOT IN (SELECT phone_number FROM contact_dnc_status WHERE organization_id = :org_id)"
        )

    where_sql = " AND ".join(conditions)

    query = (
        "SELECT l.id, l.first_name, l.last_name, l.phone, l.email,"
        " l.stage, l.source, l.ai_score, l.last_contact,"
        " l.loan_type, l.loan_amount, l.credit_score, l.state"
        " FROM leads l"
        " WHERE " + where_sql +
        " ORDER BY l.ai_score DESC NULLS LAST, l.last_contact ASC NULLS FIRST"
        " LIMIT :limit"
    )
    rows = db.execute(text(query), params).fetchall()

    if not rows:
        return {
            "queue_id": None,
            "total_items": 0,
            "message": "No leads match the given filters",
            "items": [],
        }

    columns = [
        "id", "first_name", "last_name", "phone", "email",
        "stage", "source", "ai_score", "last_contact",
        "loan_type", "loan_amount", "credit_score", "state",
    ]

    # Build items with priority scoring
    items = []
    for row in rows:
        rd = dict(zip(columns, row))
        priority = _calculate_lead_priority(rd, now)
        contact_name = f"{rd.get('first_name') or ''} {rd.get('last_name') or ''}".strip()
        items.append({
            "phone": rd["phone"],
            "contact_name": contact_name or "Unknown",
            "lead_id": rd["id"],
            "loan_id": None,
            "priority_score": priority,
            "context": {
                "stage": rd.get("stage"),
                "source": rd.get("source"),
                "ai_score": rd.get("ai_score"),
                "loan_type": rd.get("loan_type"),
                "state": rd.get("state"),
                "last_contact": rd["last_contact"].isoformat() if rd.get("last_contact") else None,
            },
        })

    # Sort by priority descending
    items.sort(key=lambda x: x["priority_score"], reverse=True)

    queue_id = str(uuid.uuid4())
    queue_name = body.name or f"Smart Queue - {now.strftime('%m/%d %H:%M')}"

    _save_queue(
        db, queue_id, current_user.id, org_id,
        queue_name, "lead", body.dict(exclude_none=True), items,
    )

    return {
        "queue_id": queue_id,
        "name": queue_name,
        "total_items": len(items),
        "items": [
            {
                "position": idx,
                "contact_name": it["contact_name"],
                "phone": it["phone"],
                "lead_id": it["lead_id"],
                "priority_score": it["priority_score"],
                "context": it["context"],
            }
            for idx, it in enumerate(items)
        ],
    }


@router.get("/smart-queue/presets")
async def get_smart_queue_presets(
    current_user=Depends(current_user_flexible_dep),
):
    """Return pre-built smart queue preset definitions."""
    presets = [
        {
            "id": "hot_leads",
            "name": "Hot Leads",
            "description": "High-score leads not contacted in 2+ days",
            "filters": {
                "min_score": 70,
                "not_contacted_days": 2,
                "exclude_dnc": True,
            },
            "icon": "flame",
        },
        {
            "id": "new_leads",
            "name": "New Leads",
            "description": "Leads in New stage created in the last 7 days",
            "filters": {
                "stages": ["New"],
                "not_contacted_days": 0,
                "exclude_dnc": True,
            },
            "icon": "sparkle",
        },
        {
            "id": "followup_due",
            "name": "Follow-up Due",
            "description": "Leads not contacted in 5+ days, not in terminal stage",
            "filters": {
                "not_contacted_days": 5,
                "exclude_dnc": True,
            },
            "icon": "clock",
        },
        {
            "id": "reengage",
            "name": "Re-engage",
            "description": "Leads not contacted in 14+ days with previous activity",
            "filters": {
                "not_contacted_days": 14,
                "min_score": 20,
                "exclude_dnc": True,
            },
            "icon": "refresh",
        },
        {
            "id": "closing_pipeline",
            "name": "Closing Pipeline",
            "description": "Borrowers on loans in closing stages (CTC, Clear to Close, Docs, Closing)",
            "filters": {
                "stages": ["CTC", "CLEAR_TO_CLOSE", "DOCS", "DOCS_OUT", "CLOSING"],
                "exclude_dnc": True,
            },
            "type": "pipeline",
            "icon": "check-circle",
        },
    ]
    return {"presets": presets}


@router.post("/smart-queue/from-pipeline")
async def build_pipeline_queue(
    body: PipelineQueueBuildRequest,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Build a call queue from the loan pipeline (borrowers, not leads)."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    now = datetime.now(timezone.utc)

    conditions = [
        "lo.organization_id = :org_id",
        "lo.loan_officer_id = :user_id",
        "lo.borrower_phone IS NOT NULL",
        "lo.borrower_phone != ''",
        "lo.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')",
    ]
    params: dict = {"org_id": org_id, "user_id": current_user.id, "limit": body.limit}

    if body.stages:
        conditions.append("lo.stage = ANY(:stages)")
        params["stages"] = body.stages

    if body.lock_expiring_days is not None:
        exp_cutoff = now + timedelta(days=body.lock_expiring_days)
        conditions.append("lo.lock_expiration_date IS NOT NULL AND lo.lock_expiration_date <= :lock_cutoff")
        params["lock_cutoff"] = exp_cutoff

    if body.closing_within_days is not None:
        close_cutoff = now + timedelta(days=body.closing_within_days)
        conditions.append("lo.closing_date IS NOT NULL AND lo.closing_date <= :close_cutoff")
        params["close_cutoff"] = close_cutoff

    if body.stale_days is not None:
        stale_cutoff = now - timedelta(days=body.stale_days)
        conditions.append("(lo.stage_changed_at IS NULL OR lo.stage_changed_at <= :stale_cutoff)")
        params["stale_cutoff"] = stale_cutoff

    if body.exclude_dnc:
        conditions.append(
            "lo.borrower_phone NOT IN ("
            "  SELECT phone_number FROM contact_dnc_status WHERE organization_id = :org_id"
            ")"
        )

    where_sql = " AND ".join(conditions)

    query = (
        "SELECT lo.id, lo.loan_number, lo.borrower_name, lo.borrower_phone,"
        " lo.stage, lo.amount, lo.loan_type, lo.closing_date,"
        " lo.lock_expiration_date, lo.stage_changed_at, lo.property_address"
        " FROM loans lo"
        " WHERE " + where_sql +
        " ORDER BY lo.lock_expiration_date ASC NULLS LAST, lo.closing_date ASC NULLS LAST"
        " LIMIT :limit"
    )
    rows = db.execute(text(query), params).fetchall()

    if not rows:
        return {
            "queue_id": None,
            "total_items": 0,
            "message": "No pipeline loans match the given filters",
            "items": [],
        }

    columns = [
        "id", "loan_number", "borrower_name", "borrower_phone",
        "stage", "amount", "loan_type", "closing_date",
        "lock_expiration_date", "stage_changed_at", "property_address",
    ]

    items = []
    for row in rows:
        rd = dict(zip(columns, row))
        priority = _calculate_pipeline_priority(rd, now)
        items.append({
            "phone": rd["borrower_phone"],
            "contact_name": rd.get("borrower_name") or "Unknown",
            "lead_id": None,
            "loan_id": rd["id"],
            "priority_score": priority,
            "context": {
                "loan_number": rd.get("loan_number"),
                "stage": rd.get("stage"),
                "loan_type": rd.get("loan_type"),
                "amount": float(rd["amount"]) if rd.get("amount") else None,
                "closing_date": rd["closing_date"].isoformat() if rd.get("closing_date") else None,
                "lock_expiration": rd["lock_expiration_date"].isoformat() if rd.get("lock_expiration_date") else None,
                "property_address": rd.get("property_address"),
            },
        })

    items.sort(key=lambda x: x["priority_score"], reverse=True)

    queue_id = str(uuid.uuid4())
    queue_name = body.name or f"Pipeline Queue - {now.strftime('%m/%d %H:%M')}"

    _save_queue(
        db, queue_id, current_user.id, org_id,
        queue_name, "pipeline", body.dict(exclude_none=True), items,
    )

    return {
        "queue_id": queue_id,
        "name": queue_name,
        "total_items": len(items),
        "items": [
            {
                "position": idx,
                "contact_name": it["contact_name"],
                "phone": it["phone"],
                "loan_id": it["loan_id"],
                "priority_score": it["priority_score"],
                "context": it["context"],
            }
            for idx, it in enumerate(items)
        ],
    }


@router.get("/smart-queue/metrics")
async def get_queue_metrics(
    days: int = Query(7, ge=1, le=90, description="Lookback period in days"),
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Get smart queue performance metrics for the current user."""
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stats = db.execute(text("""
        SELECT
            COUNT(DISTINCT q.id) AS total_queues,
            COALESCE(SUM(q.total_items), 0) AS total_items,
            COALESCE(SUM(q.completed_items), 0) AS total_completed,
            COALESCE(SUM(q.skipped_items), 0) AS total_skipped
        FROM dialer_smart_queues q
        WHERE q.user_id = :user_id
          AND q.organization_id = :org_id
          AND q.created_at >= :cutoff
    """), {"user_id": current_user.id, "org_id": org_id, "cutoff": cutoff}).fetchone()

    # Calculate connect rate from items that were completed
    connect_stats = db.execute(text("""
        SELECT
            COUNT(*) AS total_called,
            COUNT(CASE WHEN i.disposition IN ('connected', 'answered', 'spoke_with', 'appointment_set')
                       THEN 1 END) AS connected
        FROM dialer_smart_queue_items i
        JOIN dialer_smart_queues q ON q.id = i.queue_id
        WHERE q.user_id = :user_id
          AND q.organization_id = :org_id
          AND i.status = 'completed'
          AND q.created_at >= :cutoff
    """), {"user_id": current_user.id, "org_id": org_id, "cutoff": cutoff}).fetchone()

    total_called = connect_stats[0] if connect_stats else 0
    connected = connect_stats[1] if connect_stats else 0
    connect_rate = round((connected / total_called * 100), 1) if total_called > 0 else 0.0

    # Active queues
    active = db.execute(text("""
        SELECT id, name, total_items, completed_items, skipped_items, current_position, created_at
        FROM dialer_smart_queues
        WHERE user_id = :user_id AND organization_id = :org_id AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 5
    """), {"user_id": current_user.id, "org_id": org_id}).fetchall()

    active_cols = ["id", "name", "total_items", "completed_items", "skipped_items", "current_position", "created_at"]

    return {
        "period_days": days,
        "summary": {
            "total_queues": stats[0] if stats else 0,
            "total_items": stats[1] if stats else 0,
            "total_completed": stats[2] if stats else 0,
            "total_skipped": stats[3] if stats else 0,
            "connect_rate": connect_rate,
            "total_connected": connected,
        },
        "active_queues": [
            dict(zip(active_cols, r)) for r in active
        ],
    }


@router.get("/smart-queue/{queue_id}")
async def get_smart_queue(
    queue_id: str,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Get a smart queue with its current position and items."""
    org_id = getattr(current_user, "organization_id", None)

    queue = db.execute(text("""
        SELECT id, name, queue_type, filters, total_items, completed_items,
               skipped_items, current_position, status, created_at
        FROM dialer_smart_queues
        WHERE id = :queue_id AND user_id = :user_id AND organization_id = :org_id
    """), {"queue_id": queue_id, "user_id": current_user.id, "org_id": org_id}).fetchone()

    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")

    q_cols = [
        "id", "name", "queue_type", "filters", "total_items", "completed_items",
        "skipped_items", "current_position", "status", "created_at",
    ]
    q = dict(zip(q_cols, queue))

    items = db.execute(text("""
        SELECT id, position, contact_phone, contact_name, lead_id, loan_id,
               priority_score, context, status, called_at, disposition
        FROM dialer_smart_queue_items
        WHERE queue_id = :queue_id
        ORDER BY position ASC
    """), {"queue_id": queue_id}).fetchall()

    item_cols = [
        "id", "position", "contact_phone", "contact_name", "lead_id", "loan_id",
        "priority_score", "context", "status", "called_at", "disposition",
    ]

    return {
        "queue": q,
        "items": [dict(zip(item_cols, r)) for r in items],
        "current_item": next(
            (dict(zip(item_cols, r)) for r in items if r[1] == q["current_position"] and r[8] == "pending"),
            None,
        ),
        "remaining": len([r for r in items if r[8] == "pending"]),
    }


@router.post("/smart-queue/{queue_id}/next")
async def get_next_in_queue(
    queue_id: str,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Get the next number to dial from the queue."""
    org_id = getattr(current_user, "organization_id", None)

    queue = db.execute(text("""
        SELECT id, current_position, total_items, status
        FROM dialer_smart_queues
        WHERE id = :queue_id AND user_id = :user_id AND organization_id = :org_id
    """), {"queue_id": queue_id, "user_id": current_user.id, "org_id": org_id}).fetchone()

    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    if queue[3] != "active":
        raise HTTPException(status_code=400, detail="Queue is not active")

    # Find next pending item from current position forward
    next_item = db.execute(text("""
        SELECT id, position, contact_phone, contact_name, lead_id, loan_id,
               priority_score, context
        FROM dialer_smart_queue_items
        WHERE queue_id = :queue_id AND status = 'pending' AND position >= :pos
        ORDER BY position ASC
        LIMIT 1
    """), {"queue_id": queue_id, "pos": queue[1]}).fetchone()

    if not next_item:
        # Queue exhausted
        db.execute(text("""
            UPDATE dialer_smart_queues
            SET status = 'completed', completed_at = NOW(), updated_at = NOW()
            WHERE id = :queue_id
        """), {"queue_id": queue_id})
        db.commit()
        return {"status": "queue_complete", "next_item": None, "remaining": 0}

    # Update current position
    db.execute(text("""
        UPDATE dialer_smart_queues
        SET current_position = :pos, updated_at = NOW()
        WHERE id = :queue_id
    """), {"queue_id": queue_id, "pos": next_item[1]})
    db.commit()

    item_cols = ["id", "position", "contact_phone", "contact_name", "lead_id", "loan_id", "priority_score", "context"]
    item_dict = dict(zip(item_cols, next_item))

    remaining = db.execute(text("""
        SELECT COUNT(*) FROM dialer_smart_queue_items
        WHERE queue_id = :queue_id AND status = 'pending'
    """), {"queue_id": queue_id}).scalar()

    return {
        "status": "ready",
        "next_item": item_dict,
        "remaining": remaining,
    }


@router.post("/smart-queue/{queue_id}/skip")
async def skip_current_item(
    queue_id: str,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Skip the current queue item and advance to the next."""
    org_id = getattr(current_user, "organization_id", None)

    queue = db.execute(text("""
        SELECT id, current_position, status
        FROM dialer_smart_queues
        WHERE id = :queue_id AND user_id = :user_id AND organization_id = :org_id
    """), {"queue_id": queue_id, "user_id": current_user.id, "org_id": org_id}).fetchone()

    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    if queue[2] != "active":
        raise HTTPException(status_code=400, detail="Queue is not active")

    # Mark current item as skipped
    db.execute(text("""
        UPDATE dialer_smart_queue_items
        SET status = 'skipped'
        WHERE queue_id = :queue_id AND position = :pos AND status = 'pending'
    """), {"queue_id": queue_id, "pos": queue[1]})

    db.execute(text("""
        UPDATE dialer_smart_queues
        SET skipped_items = skipped_items + 1, updated_at = NOW()
        WHERE id = :queue_id
    """), {"queue_id": queue_id})
    db.commit()

    # Return the next pending item
    next_item = db.execute(text("""
        SELECT id, position, contact_phone, contact_name, lead_id, loan_id,
               priority_score, context
        FROM dialer_smart_queue_items
        WHERE queue_id = :queue_id AND status = 'pending' AND position > :pos
        ORDER BY position ASC
        LIMIT 1
    """), {"queue_id": queue_id, "pos": queue[1]}).fetchone()

    if not next_item:
        db.execute(text("""
            UPDATE dialer_smart_queues
            SET status = 'completed', completed_at = NOW(), updated_at = NOW()
            WHERE id = :queue_id
        """), {"queue_id": queue_id})
        db.commit()
        return {"status": "queue_complete", "next_item": None, "remaining": 0}

    db.execute(text("""
        UPDATE dialer_smart_queues SET current_position = :pos, updated_at = NOW()
        WHERE id = :queue_id
    """), {"queue_id": queue_id, "pos": next_item[1]})
    db.commit()

    item_cols = ["id", "position", "contact_phone", "contact_name", "lead_id", "loan_id", "priority_score", "context"]
    remaining = db.execute(text("""
        SELECT COUNT(*) FROM dialer_smart_queue_items
        WHERE queue_id = :queue_id AND status = 'pending'
    """), {"queue_id": queue_id}).scalar()

    return {
        "status": "skipped",
        "next_item": dict(zip(item_cols, next_item)),
        "remaining": remaining,
    }


@router.post("/smart-queue/{queue_id}/complete")
async def complete_current_item(
    queue_id: str,
    body: QueueItemCompleteRequest,
    current_user=Depends(current_user_flexible_dep),
    db: Session = Depends(get_db),
):
    """Mark the current queue item as called/completed and advance."""
    org_id = getattr(current_user, "organization_id", None)

    queue = db.execute(text("""
        SELECT id, current_position, status
        FROM dialer_smart_queues
        WHERE id = :queue_id AND user_id = :user_id AND organization_id = :org_id
    """), {"queue_id": queue_id, "user_id": current_user.id, "org_id": org_id}).fetchone()

    if not queue:
        raise HTTPException(status_code=404, detail="Queue not found")
    if queue[2] != "active":
        raise HTTPException(status_code=400, detail="Queue is not active")

    now_ts = datetime.now(timezone.utc)

    # Mark current item as completed
    db.execute(text("""
        UPDATE dialer_smart_queue_items
        SET status = 'completed', called_at = :now, disposition = :disp, notes = :notes
        WHERE queue_id = :queue_id AND position = :pos AND status = 'pending'
    """), {
        "queue_id": queue_id,
        "pos": queue[1],
        "now": now_ts,
        "disp": body.disposition,
        "notes": body.notes,
    })

    db.execute(text("""
        UPDATE dialer_smart_queues
        SET completed_items = completed_items + 1, updated_at = NOW()
        WHERE id = :queue_id
    """), {"queue_id": queue_id})

    # Also update lead.last_contact if this was a lead-based item
    lead_row = db.execute(text("""
        SELECT lead_id FROM dialer_smart_queue_items
        WHERE queue_id = :queue_id AND position = :pos
    """), {"queue_id": queue_id, "pos": queue[1]}).fetchone()

    if lead_row and lead_row[0]:
        db.execute(text("""
            UPDATE leads SET last_contact = :now, updated_at = :now
            WHERE id = :lead_id
        """), {"now": now_ts, "lead_id": lead_row[0]})

    db.commit()

    # Advance to next
    next_item = db.execute(text("""
        SELECT id, position, contact_phone, contact_name, lead_id, loan_id,
               priority_score, context
        FROM dialer_smart_queue_items
        WHERE queue_id = :queue_id AND status = 'pending' AND position > :pos
        ORDER BY position ASC
        LIMIT 1
    """), {"queue_id": queue_id, "pos": queue[1]}).fetchone()

    if not next_item:
        db.execute(text("""
            UPDATE dialer_smart_queues
            SET status = 'completed', completed_at = NOW(), updated_at = NOW()
            WHERE id = :queue_id
        """), {"queue_id": queue_id})
        db.commit()
        return {"status": "queue_complete", "next_item": None, "remaining": 0}

    db.execute(text("""
        UPDATE dialer_smart_queues SET current_position = :pos, updated_at = NOW()
        WHERE id = :queue_id
    """), {"queue_id": queue_id, "pos": next_item[1]})
    db.commit()

    item_cols = ["id", "position", "contact_phone", "contact_name", "lead_id", "loan_id", "priority_score", "context"]
    remaining = db.execute(text("""
        SELECT COUNT(*) FROM dialer_smart_queue_items
        WHERE queue_id = :queue_id AND status = 'pending'
    """), {"queue_id": queue_id}).scalar()

    return {
        "status": "completed",
        "next_item": dict(zip(item_cols, next_item)),
        "remaining": remaining,
    }
