"""
Recruiting Routes
API endpoints for Master Manager Platform Phase 2 - Recruiting Engine.
"""

import html as html_mod
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime, date
from database import get_db
from services.recruiting_service import RecruitingService
from auth.dependencies import get_current_user
from database.models import User
from sqlalchemy.exc import SQLAlchemyError
import json
import logging
import os

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================



router = APIRouter(
    prefix="/api/v1/recruiting",
    tags=["recruiting"],
    dependencies=[Depends(get_current_user)],
)


from routes.recruiting._utils import verify_candidate_org as _verify_candidate_org


# =============================================================================
# QUIZ ENDPOINTS — canonical implementation in recruit_assessment_routes.py
# Removed from here to eliminate duplicate route registration.
# =============================================================================


# =============================================================================
# PARTNER RECRUIT ENDPOINTS (Realtors from RETR)
# =============================================================================

@router.get("/partners")
async def list_partner_recruits(
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List partner recruits (realtors) from referral_partners table.
    These are potential realtor partners imported from RETR.
    """
    organization_id = current_user.organization_id
    params = {"limit": limit, "offset": offset, "org_id": organization_id}
    filters = ["organization_id = :org_id"]

    # Filter for realtor category (partners from RETR)
    filters.append("(category = 'realtor' OR type = 'Realtor')")

    if status:
        filters.append("status = :status")
        params["status"] = status

    if source:
        filters.append("source = :source")
        params["source"] = source

    if search:
        filters.append("(name ILIKE :search OR email ILIKE :search OR company ILIKE :search)")
        params["search"] = f"%{search}%"

    where_sql = " AND ".join(filters)

    # Use a simpler query that only selects columns that definitely exist
    select_sql = """
        SELECT
            id, name, contact_name, business_name, company,
            email, phone, license_number, notes,
            category, type, status, created_at
        FROM referral_partners
        WHERE """ + where_sql + """
        ORDER BY created_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    results = db.execute(text(select_sql), params).fetchall()

    # Get total count
    count_sql = "SELECT COUNT(*) FROM referral_partners WHERE " + where_sql
    count_result = db.execute(text(count_sql), {k: v for k, v in params.items() if k not in ['limit', 'offset']}).fetchone()

    partners = []
    for r in results:
        partners.append({
            "id": r.id,
            "name": r.name or r.contact_name,
            "contact_name": r.contact_name,
            "company": r.company or r.business_name,
            "business_name": r.business_name,
            "email": r.email,
            "phone": r.phone,
            "license_number": r.license_number,
            "notes": r.notes,
            "status": r.status or "active",
            "source": "retr" if r.category == "realtor" else "direct",  # Infer source from category
            "created_at": r.created_at.isoformat() if r.created_at else None
        })

    return {
        "partners": partners,
        "count": len(partners),
        "total": count_result[0] if count_result else 0
    }


@router.get("/partners/{partner_id}")
async def get_partner_recruit(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed partner recruit information."""
    result = db.execute(text("""
        SELECT
            id, name, contact_name, business_name, company,
            email, phone, license_number, notes,
            category, type, status,
            created_at
        FROM referral_partners
        WHERE id = :id AND organization_id = :org_id
    """), {"id": partner_id, "org_id": current_user.organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Partner not found")

    return {
        "id": result.id,
        "name": result.name or result.contact_name,
        "contact_name": result.contact_name,
        "company": result.company or result.business_name,
        "business_name": result.business_name,
        "email": result.email,
        "phone": result.phone,
        "license_number": result.license_number,
        "notes": result.notes,
        "status": result.status or "active",
        "source": "retr" if result.category == "realtor" else "direct",
        "created_at": result.created_at.isoformat() if result.created_at else None
    }


@router.patch("/partners/{partner_id}/status")
async def update_partner_recruit_status(
    partner_id: int,
    status: str = Query(..., description="New status: active, prospect, inactive, converted"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update partner recruit status."""
    valid_statuses = ["active", "prospect", "inactive", "converted", "nurturing"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    result = db.execute(text("""
        UPDATE referral_partners
        SET status = :status, updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND organization_id = :org_id
        RETURNING id
    """), {"id": partner_id, "status": status, "org_id": current_user.organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Partner not found")

    db.commit()
    return {"id": partner_id, "status": status}


@router.get("/partners/stats/overview")
async def get_partner_recruit_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get partner recruiting statistics overview."""
    stats = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
            COUNT(CASE WHEN status = 'new' OR status IS NULL THEN 1 END) as new,
            COUNT(CASE WHEN status = 'contacted' THEN 1 END) as contacted,
            COUNT(CASE WHEN status = 'meeting_scheduled' THEN 1 END) as meeting_scheduled,
            COUNT(CASE WHEN status = 'in_negotiation' THEN 1 END) as in_negotiation,
            COUNT(CASE WHEN status = 'onboarded' THEN 1 END) as onboarded,
            COUNT(CASE WHEN status = 'inactive' THEN 1 END) as inactive,
            COUNT(CASE WHEN status = 'declined' THEN 1 END) as declined,
            COUNT(CASE WHEN category = 'realtor' THEN 1 END) as from_retr,
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 7 THEN 1 END) as new_this_week,
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 30 THEN 1 END) as new_this_month
        FROM referral_partners
        WHERE (category = 'realtor' OR type = 'Realtor')
        AND organization_id = :org_id
    """), {"org_id": current_user.organization_id}).fetchone()

    # Calculate conversion rates
    total = stats.total or 0
    contacted = stats.contacted or 0
    onboarded = stats.onboarded or 0

    contact_rate = round((contacted / total) * 100, 1) if total > 0 else 0
    onboard_rate = round((onboarded / contacted) * 100, 1) if contacted > 0 else 0
    overall_rate = round((onboarded / total) * 100, 1) if total > 0 else 0

    return {
        "total": total,
        "active": stats.active or 0,
        "new": stats.new or 0,
        "contacted": contacted,
        "meeting_scheduled": stats.meeting_scheduled or 0,
        "in_negotiation": stats.in_negotiation or 0,
        "onboarded": onboarded,
        "inactive": stats.inactive or 0,
        "declined": stats.declined or 0,
        "from_retr": stats.from_retr or 0,
        "new_this_week": stats.new_this_week or 0,
        "new_this_month": stats.new_this_month or 0,
        "conversion_rates": {
            "new_to_contacted": contact_rate,
            "contacted_to_onboarded": onboard_rate,
            "overall": overall_rate
        },
        "by_status": {
            "new": stats.new or 0,
            "active": stats.active or 0,
            "contacted": contacted,
            "meeting_scheduled": stats.meeting_scheduled or 0,
            "in_negotiation": stats.in_negotiation or 0,
            "onboarded": onboarded,
            "inactive": stats.inactive or 0,
            "declined": stats.declined or 0
        }
    }


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class CandidateCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    source: Optional[str] = "direct"
    referrer_user_id: Optional[int] = None
    target_role_id: Optional[int] = None
    target_role_name: Optional[str] = None
    years_experience: Optional[int] = None
    years_mortgage_experience: Optional[int] = None
    has_mortgage_experience: bool = False
    resume_url: Optional[str] = None
    linkedin_url: Optional[str] = None


class CandidateStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None
    disposition_code: Optional[str] = None
    skip_score_gate: bool = False  # Admin override for score/NMLS gates
    bypass_reason: Optional[str] = None  # Required justification when skip_score_gate=True


class JobPostingCreate(BaseModel):
    title: str
    role_definition_id: Optional[int] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    benefits: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_type: str = "salary"
    is_published: bool = False
    is_remote: bool = False
    location: Optional[str] = None
    employment_type: str = "full_time"


class JobPostingUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    benefits: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    is_published: Optional[bool] = None
    is_remote: Optional[bool] = None
    location: Optional[str] = None


class InterviewSchedule(BaseModel):
    interview_type: str = "video"
    interview_round: int = 1
    title: Optional[str] = None
    scheduled_at: datetime
    duration_minutes: int = 30
    timezone: str = "America/New_York"
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    interviewer_user_ids: List[int] = Field(default_factory=list)
    primary_interviewer_id: Optional[int] = None


class InterviewFeedback(BaseModel):
    overall_score: float = Field(..., ge=1, le=5)
    recommendation: str  # strong_hire, hire, undecided, no_hire, strong_no_hire
    strengths: Optional[List[str]] = None
    areas_for_improvement: Optional[List[str]] = None
    notes: Optional[str] = None
    culture_fit_score: Optional[float] = None
    technical_score: Optional[float] = None
    communication_score: Optional[float] = None


class OfferCreate(BaseModel):
    job_posting_id: Optional[int] = None
    role_title: str
    role_definition_id: Optional[int] = None
    department: Optional[str] = None
    reports_to_user_id: Optional[int] = None
    salary_amount: int
    salary_type: str = "salary"
    bonus_amount: Optional[int] = None
    bonus_type: Optional[str] = None
    benefits_summary: Optional[str] = None
    pto_days: Optional[int] = None
    employment_type: str = "full_time"
    start_date: Optional[date] = None
    is_remote: bool = False
    work_location: Optional[str] = None


class OfferSend(BaseModel):
    expires_in_days: int = 7


class OfferResponse(BaseModel):
    accepted: bool
    notes: Optional[str] = None


class CandidateNoteCreate(BaseModel):
    note_type: str = "general"
    content: str
    is_private: bool = False


# =============================================================================
# PIPELINE METRICS
# =============================================================================

@router.get("/pipeline/metrics")
async def get_pipeline_metrics(
    days: int = Query(90, ge=7, le=365),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recruiting pipeline metrics."""
    service = RecruitingService(db)
    metrics = await service.get_pipeline_metrics(
        organization_id=current_user.organization_id,
        days=days
    )
    return {
        "total_candidates": metrics.total_candidates,
        "by_status": metrics.by_status,
        "avg_time_to_hire_days": metrics.avg_time_to_hire_days,
        "conversion_rates": metrics.conversion_rates,
        "open_positions": metrics.open_positions,
        "pending_offers": metrics.pending_offers
    }


# =============================================================================
# CANDIDATES
# =============================================================================

@router.get("/candidates")
async def list_candidates(
    status: Optional[str] = None,
    role_id: Optional[int] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List candidates with filters."""
    service = RecruitingService(db)
    candidates = await service.get_candidates(
        organization_id=current_user.organization_id,
        status=status,
        role_id=role_id,
        source=source,
        search=search,
        limit=limit,
        offset=offset
    )
    total = await service.count_candidates(
        organization_id=current_user.organization_id,
        status=status,
        role_id=role_id,
        source=source,
        search=search,
    )
    return {"candidates": candidates, "count": len(candidates), "total": total, "offset": offset}


@router.get("/candidates/{candidate_id}")
async def get_candidate(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed candidate information."""
    service = RecruitingService(db)
    candidate = await service.get_candidate_detail(
        candidate_id=candidate_id,
        organization_id=current_user.organization_id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@router.post("/candidates")
async def create_candidate(
    data: CandidateCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new candidate."""
    try:
        service = RecruitingService(db)
        result = await service.create_candidate(
            data=data.model_dump(),
            created_by=current_user.id,
            organization_id=current_user.organization_id
        )
        return result
    except Exception as e:
        import traceback
        logger.error(f"Recruiting error: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


class CandidateUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    referrer_user_id: Optional[int] = None
    target_role_name: Optional[str] = None
    years_experience: Optional[int] = None
    has_mortgage_experience: Optional[bool] = None


@router.put("/candidates/{candidate_id}")
async def update_candidate(
    candidate_id: int,
    data: CandidateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update candidate details."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    # Explicit whitelist of updatable columns — prevents field name injection
    ALLOWED_FIELDS = {
        "first_name", "last_name", "email", "phone",
        "referrer_user_id", "target_role_name",
        "years_experience", "has_mortgage_experience",
    }

    # Build SET clause dynamically from provided fields
    updates = []
    params = {"id": candidate_id, "org_id": current_user.organization_id}

    for field, value in data.model_dump(exclude_none=True).items():
        if field not in ALLOWED_FIELDS:
            continue
        if value is not None:
            updates.append(f"{field} = :{field}")
            params[field] = value

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")
    query = f"UPDATE mm_candidates SET {', '.join(updates)} WHERE id = :id AND organization_id = :org_id RETURNING id"

    result = db.execute(text(query), params).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    db.commit()
    return {"id": candidate_id, "updated": True}


@router.patch("/candidates/{candidate_id}/status")
async def update_candidate_status(
    candidate_id: int,
    data: CandidateStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update candidate status."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    # Require disposition_code for terminal statuses
    if data.status in ("rejected", "withdrawn", "not_selected") and not data.disposition_code:
        raise HTTPException(
            status_code=400,
            detail="disposition_code is required when rejecting or withdrawing a candidate"
        )

    if data.skip_score_gate and current_user.role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Only admins can override score gates")

    # Capture old status before the update (needed for bypass audit trail)
    old_status_row = db.execute(
        text("SELECT status FROM mm_candidates WHERE id = :id AND organization_id = :org_id"),
        {"id": candidate_id, "org_id": current_user.organization_id}
    ).fetchone()
    old_status = old_status_row.status if old_status_row else None

    service = RecruitingService(db)
    try:
        result = await service.update_candidate_status(
            candidate_id=candidate_id,
            new_status=data.status,
            updated_by=current_user.id,
            reason=data.reason,
            organization_id=current_user.organization_id,
            disposition_code=data.disposition_code,
            skip_score_gate=data.skip_score_gate,
        )

        # Audit trail for score gate bypass
        if data.skip_score_gate:
            try:
                db.execute(text("""
                    INSERT INTO mm_score_gate_bypass_log
                        (organization_id, candidate_id, bypassed_by_user_id,
                         old_status, new_status, bypass_reason, bypassed_at)
                    VALUES
                        (:org_id, :candidate_id, :user_id,
                         :old_status, :new_status, :bypass_reason, NOW())
                """), {
                    "org_id": current_user.organization_id,
                    "candidate_id": candidate_id,
                    "user_id": current_user.id,
                    "old_status": old_status,
                    "new_status": data.status,
                    "bypass_reason": data.bypass_reason,
                })
                db.commit()
            except Exception as e:
                logger.warning("Failed to write score gate bypass audit log: %s", e)

        return result
    except ValueError as e:
        error_msg = str(e)
        if "Cannot advance" in error_msg or "NMLS validation" in error_msg:
            raise HTTPException(status_code=400, detail=error_msg)
        raise HTTPException(status_code=404, detail="Not found")


class EscalateRequest(BaseModel):
    assigned_to: int
    note: Optional[str] = None


@router.post("/candidates/{candidate_id}/escalate")
async def escalate_candidate(
    candidate_id: int,
    data: EscalateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Escalate/reassign a candidate to another team member."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    # Verify assigned_to user belongs to the same organization
    target_user = db.execute(
        text("SELECT id FROM users WHERE id = :user_id AND organization_id = :org_id"),
        {"user_id": data.assigned_to, "org_id": current_user.organization_id}
    ).fetchone()
    if not target_user:
        raise HTTPException(status_code=400, detail="Target user not found in your organization")

    # Update the candidate's assigned_to
    result = db.execute(
        text("""
            UPDATE mm_candidates
            SET assigned_to = :assigned_to,
                updated_at = NOW()
            WHERE id = :candidate_id AND organization_id = :org_id
            RETURNING id, first_name, last_name, assigned_to
        """),
        {"candidate_id": candidate_id, "assigned_to": data.assigned_to, "org_id": current_user.organization_id}
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Add an activity log entry
    db.execute(
        text("""
            INSERT INTO mm_candidate_activities
            (candidate_id, activity_type, description, performed_by, created_at)
            VALUES (:candidate_id, 'escalated', :description, :performed_by, NOW())
        """),
        {
            "candidate_id": candidate_id,
            "description": f"Candidate escalated to user {data.assigned_to}" + (f": {data.note}" if data.note else ""),
            "performed_by": current_user.id
        }
    )

    db.commit()

    return {
        "success": True,
        "candidate_id": candidate_id,
        "assigned_to": data.assigned_to,
        "message": f"Candidate {row.first_name} {row.last_name} has been escalated"
    }


# =============================================================================
# JOB POSTINGS
# =============================================================================

@router.get("/job-postings")
async def list_job_postings(
    is_published: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List job postings."""
    service = RecruitingService(db)
    postings = await service.get_job_postings(
        organization_id=current_user.organization_id,
        is_published=is_published,
        limit=limit
    )
    return {"job_postings": postings, "count": len(postings)}


@router.post("/job-postings")
async def create_job_posting(
    data: JobPostingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new job posting."""
    try:
        service = RecruitingService(db)
        result = await service.create_job_posting(
            data=data.model_dump(),
            created_by=current_user.id,
            organization_id=current_user.organization_id
        )
        return result
    except Exception as e:
        import traceback
        logger.error(f"Recruiting error: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.patch("/job-postings/{posting_id}")
async def update_job_posting(
    posting_id: int,
    data: JobPostingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a job posting."""
    ALLOWED_FIELDS = {
        "title", "summary", "description", "requirements", "responsibilities",
        "benefits", "salary_min", "salary_max", "is_published", "is_remote",
        "location", "employment_type", "expires_at"
    }
    update_fields = []
    params = {"id": posting_id, "org_id": current_user.organization_id}

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None and field in ALLOWED_FIELDS:
            update_fields.append(f"{field} = :{field}")
            params[field] = value

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields.append("updated_at = CURRENT_TIMESTAMP")

    update_sql = """
        UPDATE mm_job_postings
        SET """ + ', '.join(update_fields) + """
        WHERE id = :id
        AND organization_id = :org_id
        RETURNING id
    """
    query = text(update_sql)

    result = db.execute(query, params).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Job posting not found")

    db.commit()
    return {"id": posting_id, "updated": True}


@router.post("/job-postings/{posting_id}/publish")
async def publish_job_posting(
    posting_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Publish a job posting."""
    result = db.execute(text("""
        UPDATE mm_job_postings
        SET is_published = true,
            published_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        AND organization_id = :org_id
        RETURNING id, slug
    """), {"id": posting_id, "org_id": current_user.organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Job posting not found")

    db.commit()
    return {"id": posting_id, "slug": result.slug, "is_published": True}


@router.post("/job-postings/{posting_id}/unpublish")
async def unpublish_job_posting(
    posting_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unpublish a job posting."""
    result = db.execute(text("""
        UPDATE mm_job_postings
        SET is_published = false,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        AND organization_id = :org_id
        RETURNING id
    """), {"id": posting_id, "org_id": current_user.organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Job posting not found")

    db.commit()
    return {"id": posting_id, "is_published": False}


# =============================================================================
# INTERVIEWS
# =============================================================================

@router.get("/candidates/{candidate_id}/interviews")
async def list_candidate_interviews(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all interviews for a candidate."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    results = db.execute(text("""
        SELECT
            i.id, i.interview_type, i.interview_round, i.title,
            i.scheduled_at, i.duration_minutes, i.location, i.meeting_link,
            i.status, i.overall_score, i.recommendation,
            u.full_name as primary_interviewer_name
        FROM mm_interviews i
        LEFT JOIN users u ON u.id = i.primary_interviewer_id
        WHERE i.candidate_id = :candidate_id
        ORDER BY i.scheduled_at DESC
    """), {"candidate_id": candidate_id}).fetchall()

    return {
        "interviews": [
            {
                "id": r.id,
                "interview_type": r.interview_type,
                "round": r.interview_round,
                "title": r.title,
                "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
                "duration_minutes": r.duration_minutes,
                "location": r.location,
                "meeting_link": r.meeting_link,
                "status": r.status,
                "overall_score": r.overall_score,
                "recommendation": r.recommendation,
                "primary_interviewer": r.primary_interviewer_name
            }
            for r in results
        ]
    }


# DEBUG ENDPOINTS REMOVED - Security risk: unauthenticated access to interview creation and email sending
# If testing is needed, use the authenticated endpoints or write proper unit tests


@router.post("/candidates/{candidate_id}/interviews")
async def schedule_interview(
    candidate_id: int,
    data: InterviewSchedule,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Schedule an interview for a candidate."""
    import logging
    import traceback
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Scheduling interview for candidate {candidate_id} by user {current_user.id} (org: {current_user.organization_id})")
        logger.info(f"Interview data: {data.model_dump()}")

        service = RecruitingService(db)
        result = await service.schedule_interview(
            candidate_id=candidate_id,
            data=data.model_dump(),
            created_by=current_user.id,
            organization_id=current_user.organization_id
        )
        return result
    except Exception as e:
        tb = traceback.format_exc()
        error_msg = f"Failed to schedule interview: {str(e)}"
        logger.error(f"{error_msg}\n{tb}")
        # Return error as JSON instead of raising HTTPException so frontend can see details
        return {
            "success": False,
            "error": "Internal server error",
            "candidate_id": candidate_id
        }


@router.post("/interviews/{interview_id}/feedback")
async def submit_feedback(
    interview_id: int,
    data: InterviewFeedback,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit feedback for an interview."""
    interview_row = db.execute(text("""
        SELECT interviewer_user_ids, primary_interviewer_id
        FROM mm_interviews
        WHERE id = :id AND organization_id = :org_id
    """), {"id": interview_id, "org_id": current_user.organization_id}).fetchone()

    if not interview_row:
        raise HTTPException(status_code=404, detail="Interview not found")

    interviewer_ids = interview_row.interviewer_user_ids
    if isinstance(interviewer_ids, str):
        interviewer_ids = json.loads(interviewer_ids)
    interviewer_ids = interviewer_ids or []

    is_admin = current_user.role in ("admin", "platform_admin", "site_admin")
    is_interviewer = (
        current_user.id in interviewer_ids
        or current_user.id == interview_row.primary_interviewer_id
    )
    if not (is_admin or is_interviewer):
        raise HTTPException(status_code=403, detail="Only assigned interviewers can submit feedback")

    service = RecruitingService(db)
    try:
        result = await service.submit_interview_feedback(
            interview_id=interview_id,
            interviewer_id=current_user.id,
            feedback=data.model_dump(),
            organization_id=current_user.organization_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


@router.patch("/interviews/{interview_id}/status")
async def update_interview_status(
    interview_id: int,
    status: str = Query(..., description="New status: scheduled, confirmed, completed, cancelled, no_show"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update interview status."""
    valid_statuses = ["scheduled", "confirmed", "completed", "cancelled", "no_show"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    result = db.execute(text("""
        UPDATE mm_interviews
        SET status = :status,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND organization_id = :org_id
        RETURNING id
    """), {"id": interview_id, "status": status, "org_id": current_user.organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Interview not found")

    db.commit()
    return {"id": interview_id, "status": status}


class InterviewNotificationRequest(BaseModel):
    send_calendar: bool = True
    send_email: bool = True
    send_sms: bool = False
    recipients: List[str] = Field(default_factory=lambda: ["candidate", "interviewers"])


@router.post("/interviews/{interview_id}/notify")
async def send_interview_notifications(
    interview_id: int,
    data: InterviewNotificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send notifications for a scheduled interview."""
    import logging
    from services.notification_service import NotificationService

    logger = logging.getLogger(__name__)

    # Get interview details (scoped to caller's org)
    interview = db.execute(text("""
        SELECT
            i.id, i.interview_type, i.scheduled_at, i.duration_minutes,
            i.location, i.meeting_link, i.timezone, i.title,
            i.interviewer_user_ids, i.primary_interviewer_id,
            c.id as candidate_id, c.first_name, c.last_name, c.email as candidate_email,
            c.phone as candidate_phone
        FROM mm_interviews i
        JOIN mm_candidates c ON c.id = i.candidate_id
        WHERE i.id = :interview_id AND c.organization_id = :org_id
    """), {"interview_id": interview_id, "org_id": current_user.organization_id}).fetchone()

    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    notifications_sent = []
    notification_service = NotificationService()

    # Format interview time
    scheduled_time = interview.scheduled_at
    if isinstance(scheduled_time, str):
        scheduled_time = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))

    formatted_date = scheduled_time.strftime("%A, %B %d, %Y")
    formatted_time = scheduled_time.strftime("%I:%M %p")

    interview_title = interview.title or f"{interview.interview_type.replace('_', ' ').title()} Interview"

    # Send to candidate
    if "candidate" in data.recipients and interview.candidate_email:
        if data.send_email:
            safe_first = html_mod.escape(str(interview.first_name or ''))
            safe_title = html_mod.escape(str(interview_title))
            safe_date = html_mod.escape(formatted_date)
            safe_time = html_mod.escape(formatted_time)
            safe_tz = html_mod.escape(str(interview.timezone or ''))
            safe_location = html_mod.escape(str(interview.location or ''))
            safe_link = html_mod.escape(str(interview.meeting_link or ''))

            subject = f"Interview Scheduled: {interview_title}"
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #3b82f6;">Your Interview is Scheduled!</h2>
                <p>Hello {safe_first},</p>
                <p>Your interview has been scheduled. Here are the details:</p>

                <div style="background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <p><strong>Interview Type:</strong> {safe_title}</p>
                    <p><strong>Date:</strong> {safe_date}</p>
                    <p><strong>Time:</strong> {safe_time} ({safe_tz})</p>
                    <p><strong>Duration:</strong> {interview.duration_minutes} minutes</p>
                    {f'<p><strong>Location:</strong> {safe_location}</p>' if interview.location else ''}
                    {f'<p><strong>Meeting Link:</strong> <a href="{safe_link}">{safe_link}</a></p>' if interview.meeting_link else ''}
                </div>

                <p>Please make sure to:</p>
                <ul>
                    <li>Test your camera and microphone if this is a video interview</li>
                    <li>Join 5 minutes early</li>
                    <li>Have a quiet, professional environment</li>
                </ul>

                <p>We look forward to speaking with you!</p>

                <p style="color: #64748b; font-size: 12px; margin-top: 30px;">
                    If you need to reschedule, please reply to this email.
                </p>
            </div>
            """

            try:
                result = notification_service.send_email(
                    to_email=interview.candidate_email,
                    subject=subject,
                    html_content=html_content
                )
                if result.get("success"):
                    notifications_sent.append({"type": "email", "recipient": "candidate", "email": interview.candidate_email})
                    logger.info(f"Sent interview notification to candidate: {interview.candidate_email}")
                else:
                    logger.error(f"Failed to send email to candidate: {result.get('error')}")
            except Exception as e:
                logger.error(f"Error sending candidate email: {e}")

        if data.send_sms and interview.candidate_phone:
            try:
                sms_message = f"Your interview is scheduled for {formatted_date} at {formatted_time}. Check your email for details."
                result = notification_service.send_sms(
                    to_phone=interview.candidate_phone,
                    message=sms_message
                )
                if result.get("success"):
                    notifications_sent.append({"type": "sms", "recipient": "candidate", "phone": interview.candidate_phone})
            except Exception as e:
                logger.error(f"Error sending candidate SMS: {e}")

    # Send to interviewers
    if "interviewers" in data.recipients:
        import json
        interviewer_ids = interview.interviewer_user_ids
        if isinstance(interviewer_ids, str):
            interviewer_ids = json.loads(interviewer_ids)

        if interviewer_ids:
            interviewers = db.execute(text("""
                SELECT id, email, full_name FROM users WHERE id = ANY(:ids) AND organization_id = :org_id
            """), {"ids": interviewer_ids, "org_id": current_user.organization_id}).fetchall()

            for interviewer in interviewers:
                if data.send_email and interviewer.email:
                    safe_cand = html_mod.escape(f"{interview.first_name} {interview.last_name}")
                    safe_interviewer = html_mod.escape(interviewer.full_name or 'Team Member')
                    safe_title = html_mod.escape(interview_title)
                    safe_location = html_mod.escape(interview.location) if interview.location else ""
                    safe_link = html_mod.escape(interview.meeting_link) if interview.meeting_link else ""
                    subject = f"Interview Scheduled: {interview.first_name} {interview.last_name}"
                    html_content = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #3b82f6;">Interview Scheduled</h2>
                        <p>Hello {safe_interviewer},</p>
                        <p>You have an upcoming interview scheduled:</p>

                        <div style="background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;">
                            <p><strong>Candidate:</strong> {safe_cand}</p>
                            <p><strong>Interview Type:</strong> {safe_title}</p>
                            <p><strong>Date:</strong> {formatted_date}</p>
                            <p><strong>Time:</strong> {formatted_time} ({html_mod.escape(interview.timezone or '')})</p>
                            <p><strong>Duration:</strong> {interview.duration_minutes} minutes</p>
                            {f'<p><strong>Location:</strong> {safe_location}</p>' if interview.location else ''}
                            {f'<p><strong>Meeting Link:</strong> <a href="{safe_link}">{safe_link}</a></p>' if interview.meeting_link else ''}
                        </div>

                        <p style="color: #64748b; font-size: 12px; margin-top: 30px;">
                            Please review the candidate's profile before the interview.
                        </p>
                    </div>
                    """

                    try:
                        result = notification_service.send_email(
                            to_email=interviewer.email,
                            subject=subject,
                            html_content=html_content
                        )
                        if result.get("success"):
                            notifications_sent.append({"type": "email", "recipient": "interviewer", "email": interviewer.email})
                            logger.info(f"Sent interview notification to interviewer: {interviewer.email}")
                    except Exception as e:
                        logger.error(f"Error sending interviewer email: {e}")

    return {
        "success": True,
        "interview_id": interview_id,
        "notifications_sent": notifications_sent,
        "total_sent": len(notifications_sent)
    }


# =============================================================================
# OFFERS
# =============================================================================

@router.get("/offers")
async def list_offers(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all offers."""
    query = text("""
        SELECT
            o.id, o.offer_number, o.role_title, o.salary_amount,
            o.status, o.sent_at, o.expires_at, o.responded_at,
            c.first_name || ' ' || c.last_name as candidate_name,
            c.id as candidate_id
        FROM mm_offers o
        JOIN mm_candidates c ON c.id = o.candidate_id
        WHERE o.organization_id = :org_id
        AND (:status IS NULL OR o.status = :status)
        ORDER BY o.created_at DESC
        LIMIT :limit
    """)

    results = db.execute(query, {
        "org_id": current_user.organization_id,
        "status": status,
        "limit": limit
    }).fetchall()

    return {
        "offers": [
            {
                "id": r.id,
                "offer_number": r.offer_number,
                "role_title": r.role_title,
                "salary_amount": r.salary_amount,
                "status": r.status,
                "candidate_name": r.candidate_name,
                "candidate_id": r.candidate_id,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "responded_at": r.responded_at.isoformat() if r.responded_at else None
            }
            for r in results
        ]
    }


@router.post("/candidates/{candidate_id}/offers")
async def create_offer(
    candidate_id: int,
    data: OfferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create an offer for a candidate."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)
    service = RecruitingService(db)
    result = await service.create_offer(
        candidate_id=candidate_id,
        data=data.model_dump(),
        created_by=current_user.id,
        organization_id=current_user.organization_id
    )
    return result


@router.get("/offers/{offer_id}")
async def get_offer(
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get offer details."""
    result = db.execute(text("""
        SELECT
            o.*,
            c.first_name || ' ' || c.last_name as candidate_name,
            c.email as candidate_email,
            u.full_name as reports_to_name
        FROM mm_offers o
        JOIN mm_candidates c ON c.id = o.candidate_id
        LEFT JOIN users u ON u.id = o.reports_to_user_id
        WHERE o.id = :id
        AND o.organization_id = :org_id
    """), {"id": offer_id, "org_id": current_user.organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Offer not found")

    return {
        "id": result.id,
        "offer_number": result.offer_number,
        "candidate_name": result.candidate_name,
        "candidate_email": result.candidate_email,
        "candidate_id": result.candidate_id,
        "role_title": result.role_title,
        "department": result.department,
        "reports_to": result.reports_to_name,
        "compensation": {
            "salary_amount": result.salary_amount,
            "salary_type": result.salary_type,
            "bonus_amount": result.bonus_amount,
            "bonus_type": result.bonus_type
        },
        "benefits": {
            "summary": result.benefits_summary,
            "pto_days": result.pto_days,
            "health_insurance": getattr(result, 'health_insurance', None),
            "retirement_match_pct": getattr(result, 'retirement_match_pct', None)
        },
        "terms": {
            "employment_type": result.employment_type,
            "start_date": result.start_date.isoformat() if result.start_date else None,
            "is_remote": result.is_remote,
            "work_location": result.work_location
        },
        "status": result.status,
        "sent_at": result.sent_at.isoformat() if result.sent_at else None,
        "expires_at": result.expires_at.isoformat() if result.expires_at else None,
        "responded_at": result.responded_at.isoformat() if result.responded_at else None,
        "negotiation_count": getattr(result, 'counter_offer_count', 0)
    }


@router.post("/offers/{offer_id}/send")
async def send_offer(
    offer_id: int,
    data: OfferSend,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send an offer to the candidate."""
    service = RecruitingService(db)
    try:
        result = await service.send_offer(
            offer_id=offer_id,
            sent_by=current_user.id,
            expires_in_days=data.expires_in_days,
            organization_id=current_user.organization_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/offers/{offer_id}/respond")
async def respond_to_offer(
    offer_id: int,
    data: OfferResponse,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record candidate's response to an offer."""
    service = RecruitingService(db)
    result = await service.respond_to_offer(
        offer_id=offer_id,
        accepted=data.accepted,
        notes=data.notes,
        organization_id=current_user.organization_id
    )
    return result


@router.post("/offers/{offer_id}/withdraw")
async def withdraw_offer(
    offer_id: int,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Withdraw an offer."""
    result = db.execute(text("""
        UPDATE mm_offers
        SET status = 'withdrawn',
            withdrawn_at = CURRENT_TIMESTAMP,
            withdrawn_reason = :reason,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        AND organization_id = :org_id
        RETURNING id, candidate_id
    """), {"id": offer_id, "reason": reason, "org_id": current_user.organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Offer not found")

    db.commit()
    return {"id": offer_id, "status": "withdrawn"}


# =============================================================================
# CANDIDATE NOTES
# =============================================================================

@router.get("/candidates/{candidate_id}/notes")
async def list_candidate_notes(
    candidate_id: int,
    include_private: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List notes for a candidate."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    is_admin = current_user.role in ("admin", "platform_admin", "site_admin")
    if include_private and is_admin:
        privacy_clause = "1=1"
    else:
        privacy_clause = "n.is_private IS NOT TRUE OR n.created_by = :user_id"

    query = text(f"""
        SELECT
            n.id, n.note_type, n.content, n.is_private, n.created_at,
            u.full_name as author_name
        FROM mm_candidate_notes n
        JOIN users u ON u.id = n.created_by
        WHERE n.candidate_id = :candidate_id
        AND n.organization_id = :org_id
        AND ({privacy_clause})
        ORDER BY n.created_at DESC
    """)

    results = db.execute(query, {
        "candidate_id": candidate_id,
        "org_id": current_user.organization_id,
        "user_id": current_user.id
    }).fetchall()

    return {
        "notes": [
            {
                "id": r.id,
                "note_type": r.note_type,
                "content": r.content,
                "is_private": r.is_private,
                "author": r.author_name,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in results
        ]
    }


@router.post("/candidates/{candidate_id}/notes")
async def create_candidate_note(
    candidate_id: int,
    data: CandidateNoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a note for a candidate."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    result = db.execute(text("""
        INSERT INTO mm_candidate_notes (
            organization_id, candidate_id, note_type, content, is_private, created_by
        ) VALUES (
            :org_id, :candidate_id, :note_type, :content, :is_private, :created_by
        )
        RETURNING id
    """), {
        "org_id": current_user.organization_id,
        "candidate_id": candidate_id,
        "note_type": data.note_type,
        "content": data.content,
        "is_private": data.is_private,
        "created_by": current_user.id
    }).fetchone()

    db.commit()
    return {"id": result.id}


# =============================================================================
# ACTIVITY FEED
# =============================================================================

@router.get("/candidates/{candidate_id}/activities")
async def list_candidate_activities(
    candidate_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List activity feed for a candidate."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    results = db.execute(text("""
        SELECT
            a.id, a.activity_type, a.description, a.created_at,
            a.interview_id, a.offer_id, a.is_automated,
            u.full_name as performed_by_name
        FROM mm_candidate_activities a
        LEFT JOIN users u ON u.id = a.performed_by
        WHERE a.candidate_id = :candidate_id
        ORDER BY a.created_at DESC
        LIMIT :limit
    """), {"candidate_id": candidate_id, "limit": limit}).fetchall()

    return {
        "activities": [
            {
                "id": r.id,
                "type": r.activity_type,
                "description": r.description,
                "performed_by": r.performed_by_name,
                "is_automated": r.is_automated,
                "interview_id": r.interview_id,
                "offer_id": r.offer_id,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in results
        ]
    }


# =============================================================================
# DASHBOARD STATS
# =============================================================================

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recruiting dashboard statistics."""
    organization_id = current_user.organization_id

    # Get various stats in parallel
    candidates_stats = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'new' THEN 1 END) as new,
            COUNT(CASE WHEN status = 'interview' THEN 1 END) as interviewing,
            COUNT(CASE WHEN status = 'offer' THEN 1 END) as offer_stage,
            COUNT(CASE WHEN applied_at >= CURRENT_DATE - 7 THEN 1 END) as this_week
        FROM mm_candidates
        WHERE is_active = true
        AND organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    interviews_stats = db.execute(text("""
        SELECT
            COUNT(CASE WHEN status = 'scheduled' AND scheduled_at >= CURRENT_DATE THEN 1 END) as upcoming,
            COUNT(CASE WHEN status = 'scheduled' AND scheduled_at::date = CURRENT_DATE THEN 1 END) as today,
            COUNT(CASE WHEN status = 'completed' AND completed_at >= CURRENT_DATE - 7 THEN 1 END) as completed_this_week
        FROM mm_interviews
        WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    offers_stats = db.execute(text("""
        SELECT
            COUNT(CASE WHEN status = 'draft' THEN 1 END) as draft,
            COUNT(CASE WHEN status = 'sent' THEN 1 END) as pending_response,
            COUNT(CASE WHEN status = 'accepted' AND accepted_at >= CURRENT_DATE - 30 THEN 1 END) as accepted_this_month
        FROM mm_offers
        WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    positions_stats = db.execute(text("""
        SELECT
            COUNT(CASE WHEN is_published = true THEN 1 END) as open,
            COALESCE(SUM(CASE WHEN is_published = true THEN views ELSE 0 END), 0) as total_views,
            COALESCE(SUM(CASE WHEN is_published = true THEN applications ELSE 0 END), 0) as total_applications
        FROM mm_job_postings
        WHERE organization_id = :org_id
    """), {"org_id": organization_id}).fetchone()

    return {
        "candidates": {
            "total_active": candidates_stats.total if candidates_stats else 0,
            "new": candidates_stats.new if candidates_stats else 0,
            "interviewing": candidates_stats.interviewing if candidates_stats else 0,
            "offer_stage": candidates_stats.offer_stage if candidates_stats else 0,
            "applied_this_week": candidates_stats.this_week if candidates_stats else 0
        },
        "interviews": {
            "upcoming": interviews_stats.upcoming if interviews_stats else 0,
            "today": interviews_stats.today if interviews_stats else 0,
            "completed_this_week": interviews_stats.completed_this_week if interviews_stats else 0
        },
        "offers": {
            "draft": offers_stats.draft if offers_stats else 0,
            "pending_response": offers_stats.pending_response if offers_stats else 0,
            "accepted_this_month": offers_stats.accepted_this_month if offers_stats else 0
        },
        "positions": {
            "open": positions_stats.open if positions_stats else 0,
            "total_views": positions_stats.total_views or 0,
            "total_applications": positions_stats.total_applications or 0
        }
    }


@router.get("/dashboard/upcoming-interviews")
async def get_upcoming_interviews(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get upcoming interviews for the dashboard."""
    results = db.execute(text("""
        SELECT
            i.id, i.interview_type, i.title, i.scheduled_at, i.duration_minutes,
            i.meeting_link, i.location,
            c.first_name || ' ' || c.last_name as candidate_name,
            c.id as candidate_id,
            u.full_name as interviewer_name
        FROM mm_interviews i
        JOIN mm_candidates c ON c.id = i.candidate_id
        LEFT JOIN users u ON u.id = i.primary_interviewer_id
        WHERE i.status = 'scheduled'
        AND i.scheduled_at >= CURRENT_TIMESTAMP
        AND i.organization_id = :org_id
        ORDER BY i.scheduled_at ASC
        LIMIT :limit
    """), {"org_id": current_user.organization_id, "limit": limit}).fetchall()

    return {
        "interviews": [
            {
                "id": r.id,
                "type": r.interview_type,
                "title": r.title,
                "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
                "duration_minutes": r.duration_minutes,
                "meeting_link": r.meeting_link,
                "location": r.location,
                "candidate_name": r.candidate_name,
                "candidate_id": r.candidate_id,
                "interviewer": r.interviewer_name
            }
            for r in results
        ]
    }


# =============================================================================
# Migration/admin endpoints removed — use backend/migrations/ scripts instead.
# =============================================================================


@router.get("/candidates/{candidate_id}/full-profile")
async def get_candidate_full_profile(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get complete candidate profile including production data and social media."""
    result = db.execute(text("""
        SELECT
            c.id, c.first_name, c.last_name, c.email, c.phone,
            c.source, c.target_role_name, c.status, c.applied_at,
            c.years_experience, c.years_mortgage_experience, c.has_mortgage_experience,
            c.linkedin_url, c.resume_url, c.cover_letter,
            c.overall_score, c.vetting_score, c.behavioral_score, c.technical_score,
            c.culture_fit_score, c.placement_recommendation, c.talent_profile,
            c.previous_companies, c.licenses,
            -- Production fields
            c.annual_volume, c.annual_units, c.avg_loan_size, c.nmls_id,
            c.license_states, c.license_expiration_dates, c.ce_credits_completed,
            c.sponsorship_transfer_status,
            c.production_history, c.current_company, c.current_title,
            -- Social media fields
            c.facebook_url, c.instagram_url, c.twitter_url, c.social_profiles,
            c.social_posts, c.social_last_synced,
            -- Profile fields
            c.headshot_url, c.bio, c.specialties, c.market_areas,
            c.education, c.certifications, c.awards, c.testimonials,
            c.created_at, c.updated_at
        FROM mm_candidates c
        WHERE c.id = :id AND c.is_active = true AND c.organization_id = :org_id
    """), {"id": candidate_id, "org_id": current_user.organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get interview history (org-scoped)
    interviews = db.execute(text("""
        SELECT id, interview_type, interview_round, scheduled_at, status, overall_score
        FROM mm_interviews WHERE candidate_id = :id AND organization_id = :org_id ORDER BY scheduled_at DESC
    """), {"id": candidate_id, "org_id": current_user.organization_id}).fetchall()

    # Get notes (org-scoped, exclude private notes)
    notes = db.execute(text("""
        SELECT id, content, note_type, created_at
        FROM mm_candidate_notes WHERE candidate_id = :id AND organization_id = :org_id
        AND (is_private = false OR is_private IS NULL)
        ORDER BY created_at DESC LIMIT 10
    """), {"id": candidate_id, "org_id": current_user.organization_id}).fetchall()

    # Get activity timeline (org-scoped)
    activities = db.execute(text("""
        SELECT id, activity_type, description, created_at
        FROM mm_candidate_activities WHERE candidate_id = :id AND organization_id = :org_id ORDER BY created_at DESC LIMIT 20
    """), {"id": candidate_id, "org_id": current_user.organization_id}).fetchall()

    # Get portal workspace info
    portal_workspace = db.execute(text("""
        SELECT id, slug, is_active, created_at
        FROM recruit_portal_workspaces
        WHERE candidate_id = :id AND is_active = true
    """), {"id": candidate_id}).fetchone()

    return {
        "id": result.id,
        "name": f"{result.first_name} {result.last_name}",
        "first_name": result.first_name,
        "last_name": result.last_name,
        "email": result.email,
        "phone": result.phone,
        "status": result.status,
        "source": result.source,
        "target_role": result.target_role_name,
        "applied_at": result.applied_at.isoformat() if result.applied_at else None,

        # Experience
        "experience": {
            "years_total": result.years_experience,
            "years_mortgage": result.years_mortgage_experience,
            "has_mortgage_experience": result.has_mortgage_experience,
            "previous_companies": result.previous_companies or [],
            "licenses": result.licenses or [],
        },

        # Production Data (RETR)
        "production": {
            "annual_volume": float(result.annual_volume) if result.annual_volume else None,
            "annual_units": result.annual_units,
            "avg_loan_size": float(result.avg_loan_size) if result.avg_loan_size else None,
            "nmls_id": result.nmls_id,
            "license_states": result.license_states or [],
            "license_expiration_dates": result.license_expiration_dates or {},
            "ce_credits_completed": result.ce_credits_completed,
            "sponsorship_transfer_status": result.sponsorship_transfer_status,
            "production_history": result.production_history or [],
            "current_company": result.current_company,
            "current_title": result.current_title,
        },

        # Social Media
        "social_media": {
            "linkedin": result.linkedin_url,
            "facebook": result.facebook_url,
            "instagram": result.instagram_url,
            "twitter": result.twitter_url,
            "all_profiles": result.social_profiles or {},
            "recent_posts": result.social_posts or [],
            "last_synced": result.social_last_synced.isoformat() if result.social_last_synced else None,
        },

        # Profile
        "profile": {
            "headshot_url": result.headshot_url,
            "bio": result.bio,
            "specialties": result.specialties or [],
            "market_areas": result.market_areas or [],
            "education": result.education or [],
            "certifications": result.certifications or [],
            "awards": result.awards or [],
            "testimonials": result.testimonials or [],
        },

        # Scores
        "scores": {
            "overall": result.overall_score,
            "vetting": result.vetting_score,
            "behavioral": result.behavioral_score,
            "technical": result.technical_score,
            "culture_fit": result.culture_fit_score,
            "placement_recommendation": result.placement_recommendation,
        },

        # Resume & Application
        "documents": {
            "resume_url": result.resume_url,
            "cover_letter": result.cover_letter,
        },

        # Talent Profile (intelligence)
        "talent_profile": result.talent_profile or {},

        # Interview History
        "interviews": [
            {
                "id": i.id,
                "type": i.interview_type,
                "round": i.interview_round,
                "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
                "status": i.status,
                "score": i.overall_score,
            }
            for i in interviews
        ],

        # Notes
        "notes": [
            {
                "id": n.id,
                "content": n.content,
                "type": n.note_type,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notes
        ],

        # Activity Timeline
        "activities": [
            {
                "id": a.id,
                "type": a.activity_type,
                "description": a.description,
                "timestamp": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities
        ],

        "created_at": result.created_at.isoformat() if result.created_at else None,
        "updated_at": result.updated_at.isoformat() if result.updated_at else None,

        # Portal workspace info
        "portal": {
            "workspace_id": portal_workspace.id if portal_workspace else None,
            "slug": portal_workspace.slug if portal_workspace else None,
            "is_active": portal_workspace.is_active if portal_workspace else False,
            "has_portal": portal_workspace is not None,
        },
    }


@router.put("/candidates/{candidate_id}/social-media")
async def update_candidate_social_media(
    candidate_id: int,
    facebook_url: Optional[str] = None,
    instagram_url: Optional[str] = None,
    twitter_url: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update candidate social media URLs."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    result = db.execute(text("""
        UPDATE mm_candidates
        SET facebook_url = COALESCE(:facebook, facebook_url),
            instagram_url = COALESCE(:instagram, instagram_url),
            twitter_url = COALESCE(:twitter, twitter_url),
            linkedin_url = COALESCE(:linkedin, linkedin_url),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND organization_id = :org_id
        RETURNING id
    """), {
        "id": candidate_id,
        "org_id": current_user.organization_id,
        "facebook": facebook_url,
        "instagram": instagram_url,
        "twitter": twitter_url,
        "linkedin": linkedin_url,
    }).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    db.commit()
    return {"id": candidate_id, "status": "updated"}


@router.put("/candidates/{candidate_id}/production")
async def update_candidate_production(
    candidate_id: int,
    annual_volume: Optional[float] = None,
    annual_units: Optional[int] = None,
    nmls_id: Optional[str] = None,
    current_company: Optional[str] = None,
    current_title: Optional[str] = None,
    license_states: Optional[List[str]] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update candidate production data."""
    import json
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    result = db.execute(text("""
        UPDATE mm_candidates
        SET annual_volume = COALESCE(:volume, annual_volume),
            annual_units = COALESCE(:units, annual_units),
            nmls_id = COALESCE(:nmls, nmls_id),
            current_company = COALESCE(:company, current_company),
            current_title = COALESCE(:title, current_title),
            license_states = COALESCE(CAST(:states AS JSONB), license_states),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND organization_id = :org_id
        RETURNING id
    """), {
        "id": candidate_id,
        "org_id": current_user.organization_id,
        "volume": annual_volume,
        "units": annual_units,
        "nmls": nmls_id,
        "company": current_company,
        "title": current_title,
        "states": json.dumps(license_states) if license_states else None,
    }).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    db.commit()
    return {"id": candidate_id, "status": "updated"}


@router.put("/candidates/{candidate_id}/basic-info")
async def update_candidate_basic_info(
    candidate_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update candidate basic information (name, email, phone)."""
    _verify_candidate_org(db, candidate_id, current_user.organization_id)

    result = db.execute(text("""
        UPDATE mm_candidates
        SET first_name = COALESCE(:first_name, first_name),
            last_name = COALESCE(:last_name, last_name),
            email = COALESCE(:email, email),
            phone = COALESCE(:phone, phone),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND organization_id = :org_id
        RETURNING id
    """), {
        "id": candidate_id,
        "org_id": current_user.organization_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
    }).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    db.commit()
    return {"id": candidate_id, "status": "updated"}


# =============================================================================
# EEOC / OFCCP ADVERSE IMPACT REPORTING
# =============================================================================

@router.get("/eeoc/adverse-impact")
async def get_adverse_impact_report(
    days: int = Query(365, description="Lookback period in days"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    OFCCP adverse impact report using the 4/5ths (80%) rule.

    Compares selection rates across demographic groups. A group's rate
    below 80% of the highest group's rate indicates potential adverse impact.
    Restricted to admin/compliance roles.
    """
    if current_user.role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required for EEOC reports")
    org_id = current_user.organization_id

    try:
        gender_stats = db.execute(text("""
            SELECT
                COALESCE(eeoc_gender, 'undisclosed') as group_name,
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'hired' THEN 1 END) as selected,
                COUNT(CASE WHEN disposition_code IS NOT NULL THEN 1 END) as dispositioned
            FROM mm_candidates
            WHERE organization_id = :org_id
              AND applied_at >= CURRENT_DATE - :days
              AND is_active = true
            GROUP BY COALESCE(eeoc_gender, 'undisclosed')
            HAVING COUNT(*) >= 3
        """), {"org_id": org_id, "days": days}).fetchall()

        ethnicity_stats = db.execute(text("""
            SELECT
                COALESCE(eeoc_race_ethnicity, 'undisclosed') as group_name,
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'hired' THEN 1 END) as selected,
                COUNT(CASE WHEN disposition_code IS NOT NULL THEN 1 END) as dispositioned
            FROM mm_candidates
            WHERE organization_id = :org_id
              AND applied_at >= CURRENT_DATE - :days
              AND is_active = true
            GROUP BY COALESCE(eeoc_race_ethnicity, 'undisclosed')
            HAVING COUNT(*) >= 3
        """), {"org_id": org_id, "days": days}).fetchall()

    except SQLAlchemyError as e:
        logger.warning(f"EEOC columns may not exist yet: {e}")
        return {
            "period_days": days,
            "message": "EEOC demographic columns not available. Run EEOC/NMLS migration first.",
            "gender_analysis": [],
            "ethnicity_analysis": [],
        }

    def analyze_groups(stats):
        groups = []
        for row in stats:
            rate = row.selected / row.total if row.total > 0 else 0
            groups.append({
                "group": row.group_name,
                "total_applicants": row.total,
                "selected": row.selected,
                "selection_rate": round(rate, 4),
                "dispositioned": row.dispositioned,
            })
        if not groups:
            return groups
        max_rate = max(g["selection_rate"] for g in groups)
        for g in groups:
            if max_rate > 0:
                ratio = g["selection_rate"] / max_rate
                g["impact_ratio"] = round(ratio, 4)
                g["adverse_impact"] = ratio < 0.80
            else:
                g["impact_ratio"] = None
                g["adverse_impact"] = False
        return groups

    return {
        "period_days": days,
        "organization_id": org_id,
        "gender_analysis": analyze_groups(gender_stats),
        "ethnicity_analysis": analyze_groups(ethnicity_stats),
        "methodology": "4/5ths (80%) rule per EEOC Uniform Guidelines",
    }


# =============================================================================
# DATA RETENTION / CCPA ENDPOINTS
# =============================================================================


@router.post("/candidates/{candidate_id}/anonymize")
async def anonymize_candidate(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Anonymize a candidate's PII (CCPA right-to-delete). Admin only."""
    if current_user.role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from services.recruit_retention_service import RecruitRetentionService
    service = RecruitRetentionService(db)
    try:
        result = service.process_deletion_request(
            candidate_id=candidate_id,
            organization_id=current_user.organization_id,
            requested_by=current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/retention/report")
async def get_retention_report(
    retention_days: int = Query(365, ge=30, le=3650),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Preview candidates eligible for anonymization under retention policy."""
    if current_user.role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from services.recruit_retention_service import RecruitRetentionService
    service = RecruitRetentionService(db)
    return service.enforce_candidate_retention(
        organization_id=current_user.organization_id,
        retention_days=retention_days,
        dry_run=True,
    )


@router.post("/retention/enforce")
async def enforce_retention(
    retention_days: int = Query(365, ge=30, le=3650),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Execute retention enforcement — anonymize eligible candidates. Admin only."""
    if current_user.role not in ("admin", "platform_admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from services.recruit_retention_service import RecruitRetentionService
    service = RecruitRetentionService(db)
    return service.enforce_candidate_retention(
        organization_id=current_user.organization_id,
        retention_days=retention_days,
        dry_run=False,
    )
