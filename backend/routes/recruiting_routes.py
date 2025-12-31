"""
Recruiting Routes
API endpoints for Master Manager Platform Phase 2 - Recruiting Engine.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date
from database import get_db
from services.recruiting_service import RecruitingService

router = APIRouter(prefix="/api/v1/recruiting", tags=["recruiting"])


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
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    List partner recruits (realtors) from referral_partners table.
    These are potential realtor partners imported from RETR.
    """
    params = {"limit": limit, "offset": offset}
    filters = ["1=1"]  # Base filter

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

    results = db.execute(text(f"""
        SELECT
            id, name, contact_name, business_name, company,
            email, phone, license_number, notes,
            category, type, status, source,
            total_referrals, referrals_this_year, last_referral_date,
            loyalty_tier, reciprocity_score, engagement_status,
            created_at
        FROM referral_partners
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    # Get total count
    count_result = db.execute(text(f"""
        SELECT COUNT(*) FROM referral_partners WHERE {where_sql}
    """), {k: v for k, v in params.items() if k not in ['limit', 'offset']}).fetchone()

    partners = []
    for r in results:
        partners.append({
            "id": r.id,
            "name": r.name or r.contact_name,
            "company": r.company or r.business_name,
            "email": r.email,
            "phone": r.phone,
            "license_number": r.license_number,
            "notes": r.notes,
            "status": r.status or "active",
            "source": r.source or "unknown",
            "total_referrals": r.total_referrals or 0,
            "referrals_this_year": r.referrals_this_year or 0,
            "last_referral": r.last_referral_date.isoformat() if r.last_referral_date else None,
            "loyalty_tier": r.loyalty_tier,
            "reciprocity_score": r.reciprocity_score,
            "engagement_status": r.engagement_status,
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
    db: Session = Depends(get_db)
):
    """Get detailed partner recruit information."""
    result = db.execute(text("""
        SELECT
            id, name, contact_name, business_name, company,
            email, phone, license_number, notes,
            category, type, status, source,
            total_referrals, referrals_this_year, last_referral_date,
            loyalty_tier, reciprocity_score, engagement_status,
            address, city, state, zip_code,
            created_at, updated_at
        FROM referral_partners
        WHERE id = :id
    """), {"id": partner_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Partner not found")

    return {
        "id": result.id,
        "name": result.name or result.contact_name,
        "company": result.company or result.business_name,
        "email": result.email,
        "phone": result.phone,
        "license_number": result.license_number,
        "notes": result.notes,
        "status": result.status or "active",
        "source": result.source or "unknown",
        "total_referrals": result.total_referrals or 0,
        "referrals_this_year": result.referrals_this_year or 0,
        "last_referral": result.last_referral_date.isoformat() if result.last_referral_date else None,
        "loyalty_tier": result.loyalty_tier,
        "reciprocity_score": result.reciprocity_score,
        "engagement_status": result.engagement_status,
        "location": {
            "address": result.address,
            "city": result.city,
            "state": result.state,
            "zip_code": result.zip_code
        },
        "created_at": result.created_at.isoformat() if result.created_at else None
    }


@router.patch("/partners/{partner_id}/status")
async def update_partner_recruit_status(
    partner_id: int,
    status: str = Query(..., description="New status: active, prospect, inactive, converted"),
    db: Session = Depends(get_db)
):
    """Update partner recruit status."""
    valid_statuses = ["active", "prospect", "inactive", "converted", "nurturing"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    result = db.execute(text("""
        UPDATE referral_partners
        SET status = :status, updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        RETURNING id
    """), {"id": partner_id, "status": status}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Partner not found")

    db.commit()
    return {"id": partner_id, "status": status}


@router.get("/partners/stats/overview")
async def get_partner_recruit_stats(
    db: Session = Depends(get_db)
):
    """Get partner recruiting statistics overview."""
    stats = db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
            COUNT(CASE WHEN status = 'prospect' THEN 1 END) as prospects,
            COUNT(CASE WHEN status = 'converted' THEN 1 END) as converted,
            COUNT(CASE WHEN source = 'retr' THEN 1 END) as from_retr,
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 7 THEN 1 END) as new_this_week,
            COUNT(CASE WHEN created_at >= CURRENT_DATE - 30 THEN 1 END) as new_this_month,
            SUM(COALESCE(total_referrals, 0)) as total_referrals
        FROM referral_partners
        WHERE category = 'realtor' OR type = 'Realtor'
    """)).fetchone()

    return {
        "total_partners": stats.total or 0,
        "active": stats.active or 0,
        "prospects": stats.prospects or 0,
        "converted": stats.converted or 0,
        "from_retr": stats.from_retr or 0,
        "new_this_week": stats.new_this_week or 0,
        "new_this_month": stats.new_this_month or 0,
        "total_referrals_received": stats.total_referrals or 0
    }


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class CandidateCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
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
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get recruiting pipeline metrics."""
    service = RecruitingService(db)
    metrics = await service.get_pipeline_metrics(
        organization_id=organization_id,
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
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List candidates with filters."""
    service = RecruitingService(db)
    candidates = await service.get_candidates(
        organization_id=organization_id,
        status=status,
        role_id=role_id,
        source=source,
        search=search,
        limit=limit,
        offset=offset
    )
    return {"candidates": candidates, "count": len(candidates)}


@router.get("/candidates/{candidate_id}")
async def get_candidate(
    candidate_id: int,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get detailed candidate information."""
    service = RecruitingService(db)
    candidate = await service.get_candidate_detail(
        candidate_id=candidate_id,
        organization_id=organization_id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@router.post("/candidates")
async def create_candidate(
    data: CandidateCreate,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create a new candidate."""
    try:
        service = RecruitingService(db)
        result = await service.create_candidate(
            data=data.model_dump(),
            created_by=user_id or 1,
            organization_id=organization_id
        )
        return result
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail=f"Error: {str(e)}\n\nTraceback: {traceback.format_exc()}"
        )


@router.patch("/candidates/{candidate_id}/status")
async def update_candidate_status(
    candidate_id: int,
    data: CandidateStatusUpdate,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Update candidate status."""
    service = RecruitingService(db)
    try:
        result = await service.update_candidate_status(
            candidate_id=candidate_id,
            new_status=data.status,
            updated_by=user_id or 1,
            reason=data.reason,
            organization_id=organization_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# JOB POSTINGS
# =============================================================================

@router.get("/job-postings")
async def list_job_postings(
    is_published: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List job postings."""
    service = RecruitingService(db)
    postings = await service.get_job_postings(
        organization_id=organization_id,
        is_published=is_published,
        limit=limit
    )
    return {"job_postings": postings, "count": len(postings)}


@router.post("/job-postings")
async def create_job_posting(
    data: JobPostingCreate,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create a new job posting."""
    try:
        service = RecruitingService(db)
        result = await service.create_job_posting(
            data=data.model_dump(),
            created_by=user_id or 1,
            organization_id=organization_id
        )
        return result
    except Exception as e:
        import traceback
        raise HTTPException(
            status_code=500,
            detail=f"Error: {str(e)}\n\nTraceback: {traceback.format_exc()}"
        )


@router.patch("/job-postings/{posting_id}")
async def update_job_posting(
    posting_id: int,
    data: JobPostingUpdate,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Update a job posting."""
    update_fields = []
    params = {"id": posting_id}

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            update_fields.append(f"{field} = :{field}")
            params[field] = value

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields.append("updated_at = CURRENT_TIMESTAMP")

    query = text(f"""
        UPDATE mm_job_postings
        SET {', '.join(update_fields)}
        WHERE id = :id
        AND (:org_id IS NULL OR organization_id = :org_id)
        RETURNING id
    """)
    params["org_id"] = organization_id

    result = db.execute(query, params).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Job posting not found")

    db.commit()
    return {"id": posting_id, "updated": True}


@router.post("/job-postings/{posting_id}/publish")
async def publish_job_posting(
    posting_id: int,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Publish a job posting."""
    result = db.execute(text("""
        UPDATE mm_job_postings
        SET is_published = true,
            published_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        AND (:org_id IS NULL OR organization_id = :org_id)
        RETURNING id, slug
    """), {"id": posting_id, "org_id": organization_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Job posting not found")

    db.commit()
    return {"id": posting_id, "slug": result.slug, "is_published": True}


@router.post("/job-postings/{posting_id}/unpublish")
async def unpublish_job_posting(
    posting_id: int,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Unpublish a job posting."""
    result = db.execute(text("""
        UPDATE mm_job_postings
        SET is_published = false,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        AND (:org_id IS NULL OR organization_id = :org_id)
        RETURNING id
    """), {"id": posting_id, "org_id": organization_id}).fetchone()

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
    db: Session = Depends(get_db)
):
    """List all interviews for a candidate."""
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


@router.post("/candidates/{candidate_id}/interviews")
async def schedule_interview(
    candidate_id: int,
    data: InterviewSchedule,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Schedule an interview for a candidate."""
    service = RecruitingService(db)
    result = await service.schedule_interview(
        candidate_id=candidate_id,
        data=data.model_dump(),
        created_by=user_id or 1,
        organization_id=organization_id
    )
    return result


@router.post("/interviews/{interview_id}/feedback")
async def submit_feedback(
    interview_id: int,
    data: InterviewFeedback,
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Submit feedback for an interview."""
    service = RecruitingService(db)
    try:
        result = await service.submit_interview_feedback(
            interview_id=interview_id,
            interviewer_id=user_id or 1,
            feedback=data.model_dump(),
            organization_id=organization_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/interviews/{interview_id}/status")
async def update_interview_status(
    interview_id: int,
    status: str = Query(..., description="New status: scheduled, confirmed, completed, cancelled, no_show"),
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
        WHERE id = :id
        RETURNING id
    """), {"id": interview_id, "status": status}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Interview not found")

    db.commit()
    return {"id": interview_id, "status": status}


# =============================================================================
# OFFERS
# =============================================================================

@router.get("/offers")
async def list_offers(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    organization_id: Optional[int] = None,
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
        WHERE (:org_id IS NULL OR o.organization_id = :org_id)
        AND (:status IS NULL OR o.status = :status)
        ORDER BY o.created_at DESC
        LIMIT :limit
    """)

    results = db.execute(query, {
        "org_id": organization_id,
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
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create an offer for a candidate."""
    service = RecruitingService(db)
    result = await service.create_offer(
        candidate_id=candidate_id,
        data=data.model_dump(),
        created_by=user_id or 1,
        organization_id=organization_id
    )
    return result


@router.get("/offers/{offer_id}")
async def get_offer(
    offer_id: int,
    organization_id: Optional[int] = None,
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
        AND (:org_id IS NULL OR o.organization_id = :org_id)
    """), {"id": offer_id, "org_id": organization_id}).fetchone()

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
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Send an offer to the candidate."""
    service = RecruitingService(db)
    try:
        result = await service.send_offer(
            offer_id=offer_id,
            sent_by=user_id or 1,
            expires_in_days=data.expires_in_days,
            organization_id=organization_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/offers/{offer_id}/respond")
async def respond_to_offer(
    offer_id: int,
    data: OfferResponse,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Record candidate's response to an offer."""
    service = RecruitingService(db)
    result = await service.respond_to_offer(
        offer_id=offer_id,
        accepted=data.accepted,
        notes=data.notes,
        organization_id=organization_id
    )
    return result


@router.post("/offers/{offer_id}/withdraw")
async def withdraw_offer(
    offer_id: int,
    reason: Optional[str] = None,
    organization_id: Optional[int] = None,
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
        AND (:org_id IS NULL OR organization_id = :org_id)
        RETURNING id, candidate_id
    """), {"id": offer_id, "reason": reason, "org_id": organization_id}).fetchone()

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
    user_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List notes for a candidate."""
    query = text("""
        SELECT
            n.id, n.note_type, n.content, n.is_private, n.created_at,
            u.full_name as author_name
        FROM mm_candidate_notes n
        JOIN users u ON u.id = n.created_by
        WHERE n.candidate_id = :candidate_id
        AND (:include_private = true OR n.is_private = false OR n.created_by = :user_id)
        ORDER BY n.created_at DESC
    """)

    results = db.execute(query, {
        "candidate_id": candidate_id,
        "include_private": include_private,
        "user_id": user_id or 0
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
    user_id: Optional[int] = None,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Create a note for a candidate."""
    result = db.execute(text("""
        INSERT INTO mm_candidate_notes (
            organization_id, candidate_id, note_type, content, is_private, created_by
        ) VALUES (
            :org_id, :candidate_id, :note_type, :content, :is_private, :created_by
        )
        RETURNING id
    """), {
        "org_id": organization_id,
        "candidate_id": candidate_id,
        "note_type": data.note_type,
        "content": data.content,
        "is_private": data.is_private,
        "created_by": user_id or 1
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
    db: Session = Depends(get_db)
):
    """List activity feed for a candidate."""
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
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get recruiting dashboard statistics."""
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
        AND (:org_id IS NULL OR organization_id = :org_id)
    """), {"org_id": organization_id}).fetchone()

    interviews_stats = db.execute(text("""
        SELECT
            COUNT(CASE WHEN status = 'scheduled' AND scheduled_at >= CURRENT_DATE THEN 1 END) as upcoming,
            COUNT(CASE WHEN status = 'scheduled' AND scheduled_at::date = CURRENT_DATE THEN 1 END) as today,
            COUNT(CASE WHEN status = 'completed' AND completed_at >= CURRENT_DATE - 7 THEN 1 END) as completed_this_week
        FROM mm_interviews
        WHERE (:org_id IS NULL OR organization_id = :org_id)
    """), {"org_id": organization_id}).fetchone()

    offers_stats = db.execute(text("""
        SELECT
            COUNT(CASE WHEN status = 'draft' THEN 1 END) as draft,
            COUNT(CASE WHEN status = 'sent' THEN 1 END) as pending_response,
            COUNT(CASE WHEN status = 'accepted' AND accepted_at >= CURRENT_DATE - 30 THEN 1 END) as accepted_this_month
        FROM mm_offers
        WHERE (:org_id IS NULL OR organization_id = :org_id)
    """), {"org_id": organization_id}).fetchone()

    positions_stats = db.execute(text("""
        SELECT
            COUNT(CASE WHEN is_published = true THEN 1 END) as open,
            COALESCE(SUM(CASE WHEN is_published = true THEN views ELSE 0 END), 0) as total_views,
            COALESCE(SUM(CASE WHEN is_published = true THEN applications ELSE 0 END), 0) as total_applications
        FROM mm_job_postings
        WHERE (:org_id IS NULL OR organization_id = :org_id)
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
    organization_id: Optional[int] = None,
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
        AND (:org_id IS NULL OR i.organization_id = :org_id)
        ORDER BY i.scheduled_at ASC
        LIMIT :limit
    """), {"org_id": organization_id, "limit": limit}).fetchall()

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
# ADMIN ENDPOINTS
# =============================================================================

@router.post("/admin/seed-test-data")
async def seed_test_data(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Seed test candidates and job postings."""
    if admin_key != "perennia-admin-2024":
        raise HTTPException(status_code=403, detail="Invalid admin key")

    import json
    results = {"candidates": [], "job_postings": [], "errors": []}

    try:
        # Create test candidates
        candidates = [
            ("Sarah", "Johnson", "sarah.johnson@example.com", "555-123-4567", "linkedin", "Senior Loan Officer", 8, 6, True),
            ("Michael", "Chen", "michael.chen@example.com", "555-234-5678", "referral", "Loan Processor", 4, 3, True),
            ("Emily", "Rodriguez", "emily.rodriguez@example.com", "555-345-6789", "indeed", "Junior Loan Officer", 1, 0, False),
            ("David", "Williams", "david.williams@example.com", "555-456-7890", "website", "Senior Loan Officer", 10, 8, True),
            ("Jessica", "Martinez", "jessica.martinez@example.com", "555-567-8901", "referral", "Loan Processor", 3, 2, True),
        ]

        for c in candidates:
            try:
                result = db.execute(text("""
                    INSERT INTO mm_candidates (
                        first_name, last_name, email, phone, source,
                        target_role_name, years_experience, years_mortgage_experience,
                        has_mortgage_experience, status, applied_at, is_active
                    ) VALUES (
                        :first_name, :last_name, :email, :phone, :source,
                        :target_role, :years_exp, :years_mortgage,
                        :has_mortgage, 'new', CURRENT_TIMESTAMP, true
                    )
                    RETURNING id
                """), {
                    "first_name": c[0], "last_name": c[1], "email": c[2], "phone": c[3],
                    "source": c[4], "target_role": c[5], "years_exp": c[6],
                    "years_mortgage": c[7], "has_mortgage": c[8]
                }).fetchone()
                results["candidates"].append({"id": result.id, "name": f"{c[0]} {c[1]}"})
            except Exception as e:
                results["errors"].append(f"Candidate {c[0]} {c[1]}: {str(e)}")

        # Create test job postings
        job_postings = [
            ("Senior Loan Officer", "senior-loan-officer", "Experienced LO for growing team", 80000, 150000, "Charlotte, NC"),
            ("Loan Processor", "loan-processor", "Detail-oriented processor", 50000, 70000, "Remote"),
            ("Junior Loan Officer", "junior-loan-officer", "Entry-level opportunity", 45000, 60000, "Atlanta, GA"),
        ]

        for jp in job_postings:
            try:
                result = db.execute(text("""
                    INSERT INTO mm_job_postings (
                        title, slug, summary, salary_min, salary_max, location,
                        is_published, employment_type, requirements, responsibilities, benefits
                    ) VALUES (
                        :title, :slug, :summary, :salary_min, :salary_max, :location,
                        true, 'full_time', '[]'::jsonb, '[]'::jsonb, '[]'::jsonb
                    )
                    RETURNING id, slug
                """), {
                    "title": jp[0], "slug": jp[1], "summary": jp[2],
                    "salary_min": jp[3], "salary_max": jp[4], "location": jp[5]
                }).fetchone()
                results["job_postings"].append({"id": result.id, "slug": result.slug})
            except Exception as e:
                results["errors"].append(f"Job {jp[0]}: {str(e)}")

        db.commit()
        return results

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Seed failed: {str(e)}")


@router.post("/admin/run-migration")
async def run_recruiting_migration(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Run the recruiting tables migration."""
    if admin_key != "perennia-admin-2024":
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from migrations.add_recruiting_tables import run_migration
        result = run_migration()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
