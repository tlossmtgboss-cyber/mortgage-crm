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
from auth.dependencies import get_current_user
from database.models import User
from sqlalchemy.exc import SQLAlchemyError
import logging
import os

logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

router = APIRouter(
    prefix="/api/v1/recruiting",
    tags=["recruiting"],
    dependencies=[Depends(get_current_user)],
)


# =============================================================================
# QUIZ TEMPLATES ENDPOINTS
# =============================================================================

def get_options_for_question_type(question_type: str):
    """Generate options based on question type."""
    if question_type == "likert":
        return [
            {"value": "1", "label": "Poor", "score": 1},
            {"value": "2", "label": "Below Average", "score": 2},
            {"value": "3", "label": "Average", "score": 3},
            {"value": "4", "label": "Good", "score": 4},
            {"value": "5", "label": "Excellent", "score": 5}
        ]
    elif question_type == "yes_no":
        return [
            {"value": "yes", "label": "Yes", "score": 5},
            {"value": "no", "label": "No", "score": 1}
        ]
    else:
        return []


@router.get("/quiz/{disposition}")
async def get_quiz_by_disposition(
    disposition: str,
    db: Session = Depends(get_db)
):
    """
    Get quiz questions for a specific disposition (stage).

    Dispositions: screening, phone_screen, interview, assessment, offer
    """
    result = db.execute(text("""
        SELECT id, disposition, question_text, question_type, category, weight, display_order
        FROM recruit_quiz_templates
        WHERE disposition = :disposition AND is_active = true
        ORDER BY display_order ASC
    """), {"disposition": disposition})

    questions = []
    for row in result.fetchall():
        question_type = row[3]
        questions.append({
            "id": row[0],
            "disposition": row[1],
            "question_text": row[2],
            "question_type": question_type,
            "category": row[4],
            "weight": float(row[5]) if row[5] else 1.0,
            "display_order": row[6],
            "options": get_options_for_question_type(question_type)
        })

    if not questions:
        raise HTTPException(status_code=404, detail=f"No quiz found for disposition: {disposition}")

    disposition_labels = {
        "screening": "Screening",
        "phone_screen": "Phone Screen",
        "interview": "Interview",
        "assessment": "Assessment",
        "offer": "Offer"
    }

    return {
        "disposition": disposition,
        "disposition_label": disposition_labels.get(disposition, disposition.title()),
        "questions": questions,
        "total": len(questions)
    }


@router.get("/quiz-templates")
async def list_all_quiz_templates(
    db: Session = Depends(get_db)
):
    """Get all quiz templates grouped by disposition."""
    result = db.execute(text("""
        SELECT id, disposition, question_text, question_type, category, weight, display_order
        FROM recruit_quiz_templates
        WHERE is_active = true
        ORDER BY disposition, display_order ASC
    """))

    templates = {}
    for row in result.fetchall():
        disposition = row[1]
        if disposition not in templates:
            templates[disposition] = []
        templates[disposition].append({
            "id": row[0],
            "question_text": row[2],
            "question_type": row[3],
            "category": row[4],
            "weight": float(row[5]) if row[5] else 1.0,
            "display_order": row[6]
        })

    return {
        "templates": templates,
        "dispositions": list(templates.keys())
    }


class QuizResponseItem(BaseModel):
    template_id: int
    response_value: str
    numeric_score: float


class QuizSubmission(BaseModel):
    disposition: str
    responses: List[QuizResponseItem]


@router.post("/candidates/{candidate_id}/quiz")
async def submit_quiz(
    candidate_id: int,
    submission: QuizSubmission,
    responded_by: int = Query(..., description="User ID who submitted the quiz"),
    db: Session = Depends(get_db)
):
    """
    Submit quiz responses for a candidate and compute assessment scores.
    """
    try:
        # Delete existing responses for this disposition
        db.execute(text("""
            DELETE FROM recruit_quiz_responses
            WHERE candidate_id = :candidate_id AND disposition = :disposition
        """), {"candidate_id": candidate_id, "disposition": submission.disposition})

        # Insert new responses
        for resp in submission.responses:
            db.execute(text("""
                INSERT INTO recruit_quiz_responses
                (candidate_id, template_id, disposition, response_value, numeric_score, responded_by)
                VALUES (:candidate_id, :template_id, :disposition, :response_value, :numeric_score, :responded_by)
            """), {
                "candidate_id": candidate_id,
                "template_id": resp.template_id,
                "disposition": submission.disposition,
                "response_value": resp.response_value,
                "numeric_score": resp.numeric_score,
                "responded_by": responded_by
            })

        # Compute scores by category
        scores_result = db.execute(text("""
            SELECT
                qt.category,
                AVG(qr.numeric_score) as avg_score,
                SUM(qr.numeric_score * qt.weight) / NULLIF(SUM(qt.weight), 0) as weighted_score
            FROM recruit_quiz_responses qr
            JOIN recruit_quiz_templates qt ON qt.id = qr.template_id
            WHERE qr.candidate_id = :candidate_id
            GROUP BY qt.category
        """), {"candidate_id": candidate_id})

        category_scores = {}
        for row in scores_result.fetchall():
            category_scores[row[0]] = round(float(row[2] or row[1] or 0), 1)

        # Calculate overall score
        overall_score = round(sum(category_scores.values()) / len(category_scores), 1) if category_scores else 0

        # Upsert assessment scores
        db.execute(text("""
            INSERT INTO recruit_assessment_scores
            (candidate_id, production_score, disc_score, character_score, skills_score, culture_fit_score, overall_score, last_quiz_disposition, quiz_count, last_updated)
            VALUES (:candidate_id, :production, :disc, :character, :skills, :culture_fit, :overall, :disposition, 1, NOW())
            ON CONFLICT (candidate_id) DO UPDATE SET
                production_score = COALESCE(:production, recruit_assessment_scores.production_score),
                disc_score = COALESCE(:disc, recruit_assessment_scores.disc_score),
                character_score = COALESCE(:character, recruit_assessment_scores.character_score),
                skills_score = COALESCE(:skills, recruit_assessment_scores.skills_score),
                culture_fit_score = COALESCE(:culture_fit, recruit_assessment_scores.culture_fit_score),
                overall_score = :overall,
                last_quiz_disposition = :disposition,
                quiz_count = recruit_assessment_scores.quiz_count + 1,
                last_updated = NOW()
        """), {
            "candidate_id": candidate_id,
            "production": category_scores.get("production"),
            "disc": category_scores.get("disc"),
            "character": category_scores.get("character"),
            "skills": category_scores.get("skills"),
            "culture_fit": category_scores.get("culture_fit"),
            "overall": overall_score,
            "disposition": submission.disposition
        })

        db.commit()

        return {
            "status": "success",
            "candidate_id": candidate_id,
            "disposition": submission.disposition,
            "responses_saved": len(submission.responses),
            "scores": {
                "production": category_scores.get("production"),
                "disc": category_scores.get("disc"),
                "character": category_scores.get("character"),
                "skills": category_scores.get("skills"),
                "culture_fit": category_scores.get("culture_fit"),
                "overall": overall_score
            }
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to submit quiz")


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

    # Use a simpler query that only selects columns that definitely exist
    results = db.execute(text(f"""
        SELECT
            id, name, contact_name, business_name, company,
            email, phone, license_number, notes,
            category, type, status, created_at
        FROM referral_partners
        WHERE {where_sql}
        ORDER BY created_at DESC NULLS LAST
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
        WHERE id = :id
    """), {"id": partner_id}).fetchone()

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
        WHERE category = 'realtor' OR type = 'Realtor'
    """)).fetchone()

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
    db: Session = Depends(get_db)
):
    """Update candidate details."""
    # Build SET clause dynamically from provided fields
    updates = []
    params = {"id": candidate_id}

    for field, value in data.model_dump(exclude_none=True).items():
        if value is not None:
            updates.append(f"{field} = :{field}")
            params[field] = value

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")
    query = f"UPDATE mm_candidates SET {', '.join(updates)} WHERE id = :id RETURNING id"

    result = db.execute(text(query), params).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    db.commit()
    return {"id": candidate_id, "updated": True}


@router.post("/admin/fix-candidate-portals")
async def fix_candidate_portals(
    admin_key: str = Query(..., description="Admin API key"),
    default_recruiter_id: int = Query(57, description="Default recruiter user ID"),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to fix existing candidates without portal workspaces.
    Creates workspaces and assigns default recruiter if missing.
    """
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    import secrets
    import re

    # Find candidates without portal workspaces
    candidates = db.execute(text("""
        SELECT c.id, c.first_name, c.last_name, c.referrer_user_id
        FROM mm_candidates c
        LEFT JOIN recruit_portal_workspaces w ON w.candidate_id = c.id
        WHERE w.id IS NULL
    """)).fetchall()

    fixed = []
    for c in candidates:
        # Generate slug
        first = c.first_name or "candidate"
        last = c.last_name or str(c.id)
        base_slug = f"{first.lower()}-{last.lower()}"
        base_slug = re.sub(r'[^a-z0-9-]', '', base_slug)
        slug = base_slug

        # Ensure unique slug
        count = 1
        while True:
            existing = db.execute(
                text("SELECT id FROM recruit_portal_workspaces WHERE slug = :slug"),
                {"slug": slug}
            ).fetchone()
            if not existing:
                break
            slug = f"{base_slug}-{count}"
            count += 1

        # Create workspace
        result = db.execute(text("""
            INSERT INTO recruit_portal_workspaces (candidate_id, slug, is_active, created_at)
            VALUES (:candidate_id, :slug, true, NOW())
            RETURNING id
        """), {"candidate_id": c.id, "slug": slug})
        workspace_id = result.fetchone().id

        # Create token
        token = f"recruit_{secrets.token_hex(32)}"
        db.execute(text("""
            INSERT INTO recruit_portal_tokens (workspace_id, token, scope, created_at)
            VALUES (:workspace_id, :token, 'full', NOW())
        """), {"workspace_id": workspace_id, "token": token})

        # Update referrer if missing
        if not c.referrer_user_id:
            db.execute(text("""
                UPDATE mm_candidates SET referrer_user_id = :recruiter WHERE id = :id
            """), {"recruiter": default_recruiter_id, "id": c.id})

        fixed.append({"candidate_id": c.id, "slug": slug, "portal_url": f"/join/{slug}"})

    # Also update any candidates with missing referrer but existing workspace
    db.execute(text("""
        UPDATE mm_candidates
        SET referrer_user_id = :recruiter
        WHERE referrer_user_id IS NULL
    """), {"recruiter": default_recruiter_id})

    db.commit()

    return {
        "message": f"Fixed {len(fixed)} candidates without portals",
        "default_recruiter_assigned": default_recruiter_id,
        "fixed_candidates": fixed
    }


@router.patch("/candidates/{candidate_id}/status")
async def update_candidate_status(
    candidate_id: int,
    data: CandidateStatusUpdate,
    organization_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update candidate status."""
    service = RecruitingService(db)
    try:
        result = await service.update_candidate_status(
            candidate_id=candidate_id,
            new_status=data.status,
            updated_by=current_user.id,
            reason=data.reason,
            organization_id=organization_id
        )
        return result
    except ValueError as e:
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
    # Update the candidate's assigned_to
    result = db.execute(
        text("""
            UPDATE mm_candidates
            SET assigned_to = :assigned_to,
                updated_at = NOW()
            WHERE id = :candidate_id
            RETURNING id, first_name, last_name, assigned_to
        """),
        {"candidate_id": candidate_id, "assigned_to": data.assigned_to}
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Add an activity log entry
    db.execute(
        text("""
            INSERT INTO mm_candidate_activities
            (candidate_id, type, description, performed_by, created_at)
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
        logger.error(f"Recruiting error: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
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


# DEBUG ENDPOINTS REMOVED - Security risk: unauthenticated access to interview creation and email sending
# If testing is needed, use the authenticated endpoints or write proper unit tests


@router.post("/candidates/{candidate_id}/interviews")
async def schedule_interview(
    candidate_id: int,
    data: InterviewSchedule,
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
            organization_id=organization_id or current_user.organization_id
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
    organization_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit feedback for an interview."""
    service = RecruitingService(db)
    try:
        result = await service.submit_interview_feedback(
            interview_id=interview_id,
            interviewer_id=current_user.id,
            feedback=data.model_dump(),
            organization_id=organization_id or current_user.organization_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Not found")


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

    # Get interview details
    interview = db.execute(text("""
        SELECT
            i.id, i.interview_type, i.scheduled_at, i.duration_minutes,
            i.location, i.meeting_link, i.timezone, i.title,
            i.interviewer_user_ids, i.primary_interviewer_id,
            c.id as candidate_id, c.first_name, c.last_name, c.email as candidate_email,
            c.phone as candidate_phone
        FROM mm_interviews i
        JOIN mm_candidates c ON c.id = i.candidate_id
        WHERE i.id = :interview_id
    """), {"interview_id": interview_id}).fetchone()

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
            subject = f"Interview Scheduled: {interview_title}"
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #3b82f6;">Your Interview is Scheduled!</h2>
                <p>Hello {interview.first_name},</p>
                <p>Your interview has been scheduled. Here are the details:</p>

                <div style="background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;">
                    <p><strong>Interview Type:</strong> {interview_title}</p>
                    <p><strong>Date:</strong> {formatted_date}</p>
                    <p><strong>Time:</strong> {formatted_time} ({interview.timezone})</p>
                    <p><strong>Duration:</strong> {interview.duration_minutes} minutes</p>
                    {f'<p><strong>Location:</strong> {interview.location}</p>' if interview.location else ''}
                    {f'<p><strong>Meeting Link:</strong> <a href="{interview.meeting_link}">{interview.meeting_link}</a></p>' if interview.meeting_link else ''}
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
                    to_number=interview.candidate_phone,
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
                SELECT id, email, full_name FROM users WHERE id = ANY(:ids)
            """), {"ids": interviewer_ids}).fetchall()

            for interviewer in interviewers:
                if data.send_email and interviewer.email:
                    subject = f"Interview Scheduled: {interview.first_name} {interview.last_name}"
                    html_content = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #3b82f6;">Interview Scheduled</h2>
                        <p>Hello {interviewer.full_name or 'Team Member'},</p>
                        <p>You have an upcoming interview scheduled:</p>

                        <div style="background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;">
                            <p><strong>Candidate:</strong> {interview.first_name} {interview.last_name}</p>
                            <p><strong>Interview Type:</strong> {interview_title}</p>
                            <p><strong>Date:</strong> {formatted_date}</p>
                            <p><strong>Time:</strong> {formatted_time} ({interview.timezone})</p>
                            <p><strong>Duration:</strong> {interview.duration_minutes} minutes</p>
                            {f'<p><strong>Location:</strong> {interview.location}</p>' if interview.location else ''}
                            {f'<p><strong>Meeting Link:</strong> <a href="{interview.meeting_link}">{interview.meeting_link}</a></p>' if interview.meeting_link else ''}
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
        raise HTTPException(status_code=404, detail="Not found")


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
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
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
                logger.error(f"Candidate {c[0]} {c[1]} creation failed: {e}")
                results["errors"].append(f"Candidate {c[0]} {c[1]}: creation failed")

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
            except SQLAlchemyError as e:
                logger.error(f"Job {jp[0]} creation failed: {e}")
                results["errors"].append(f"Job {jp[0]}: creation failed")

        db.commit()
        return results

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Seed failed")


@router.post("/admin/run-migration")
async def run_recruiting_migration(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Run the recruiting tables migration."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from migrations.add_recruiting_tables import run_migration
        result = run_migration()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Migration failed")


@router.post("/admin/add-quiz-templates")
async def add_quiz_templates(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Create quiz tables (templates, responses, scores) and seed with initial data."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        from sqlalchemy import text
        messages = []

        # Create quiz templates table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_quiz_templates (
                id SERIAL PRIMARY KEY,
                disposition VARCHAR(50) NOT NULL,
                question_text TEXT NOT NULL,
                question_type VARCHAR(20) DEFAULT 'likert',
                category VARCHAR(50) NOT NULL,
                weight DECIMAL(3,2) DEFAULT 1.0,
                display_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))
        messages.append("recruit_quiz_templates table ready")

        # Create quiz responses table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_quiz_responses (
                id SERIAL PRIMARY KEY,
                candidate_id INTEGER NOT NULL,
                template_id INTEGER REFERENCES recruit_quiz_templates(id),
                disposition VARCHAR(50) NOT NULL,
                response_value TEXT,
                numeric_score DECIMAL(3,1),
                responded_by INTEGER,
                responded_at TIMESTAMP DEFAULT NOW()
            );
        """))
        messages.append("recruit_quiz_responses table ready")

        # Create assessment scores table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_assessment_scores (
                id SERIAL PRIMARY KEY,
                candidate_id INTEGER NOT NULL UNIQUE,
                production_score DECIMAL(3,1),
                disc_score DECIMAL(3,1),
                character_score DECIMAL(3,1),
                skills_score DECIMAL(3,1),
                culture_fit_score DECIMAL(3,1),
                overall_score DECIMAL(3,1),
                last_quiz_disposition VARCHAR(50),
                quiz_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT NOW()
            );
        """))
        messages.append("recruit_assessment_scores table ready")

        # Check if template data exists
        result = db.execute(text("SELECT COUNT(*) FROM recruit_quiz_templates"))
        count = result.scalar()

        if count == 0:
            # Insert seed data
            db.execute(text("""
                INSERT INTO recruit_quiz_templates (disposition, question_text, question_type, category, weight, display_order) VALUES
                ('screening', 'Rate production volume', 'likert', 'production', 1.0, 1),
                ('screening', 'Has required licenses?', 'yes_no', 'skills', 1.0, 2),
                ('phone_screen', 'Communication skills?', 'likert', 'skills', 1.0, 1),
                ('phone_screen', 'Enthusiasm level?', 'likert', 'culture_fit', 0.9, 2),
                ('interview', 'Dominance trait', 'likert', 'disc', 1.0, 1),
                ('interview', 'Influence trait', 'likert', 'disc', 1.0, 2),
                ('interview', 'Integrity rating', 'likert', 'character', 1.0, 3),
                ('assessment', 'Technical performance?', 'likert', 'skills', 1.0, 1),
                ('assessment', 'Product knowledge?', 'likert', 'skills', 1.0, 2),
                ('assessment', 'Problem-solving?', 'likert', 'character', 0.9, 3),
                ('offer', 'Values alignment', 'likert', 'culture_fit', 1.0, 1),
                ('offer', 'Team compatibility', 'likert', 'culture_fit', 1.0, 2);
            """))
            messages.append("12 quiz templates seeded")
        else:
            messages.append(f"Templates exist ({count} records)")

        db.commit()
        return {"status": "success", "messages": messages}

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Migration failed")


@router.post("/admin/add-social-production-fields")
async def add_social_production_fields(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db)
):
    """Add social media and production fields to mm_candidates table."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        # Production fields from RETR
        production_columns = [
            ("annual_volume", "NUMERIC(15,2)"),
            ("annual_units", "INTEGER"),
            ("avg_loan_size", "NUMERIC(12,2)"),
            ("nmls_id", "VARCHAR(20)"),
            ("license_states", "JSONB"),
            ("production_history", "JSONB"),
            ("current_company", "VARCHAR(255)"),
            ("current_title", "VARCHAR(100)"),
        ]

        # Social media fields
        social_columns = [
            ("facebook_url", "VARCHAR(500)"),
            ("instagram_url", "VARCHAR(500)"),
            ("twitter_url", "VARCHAR(500)"),
            ("social_profiles", "JSONB"),
            ("social_posts", "JSONB"),
            ("social_last_synced", "TIMESTAMP"),
        ]

        # Profile enhancement fields
        profile_columns = [
            ("headshot_url", "VARCHAR(500)"),
            ("bio", "TEXT"),
            ("specialties", "JSONB"),
            ("market_areas", "JSONB"),
            ("education", "JSONB"),
            ("certifications", "JSONB"),
            ("awards", "JSONB"),
            ("testimonials", "JSONB"),
        ]

        all_columns = production_columns + social_columns + profile_columns
        added = []
        skipped = []

        for col_name, col_type in all_columns:
            try:
                db.execute(text(f"""
                    ALTER TABLE mm_candidates
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                """))
                added.append(col_name)
            except SQLAlchemyError as e:
                if "already exists" in str(e).lower():
                    skipped.append(col_name)
                else:
                    skipped.append(f"{col_name}: {str(e)}")

        db.commit()
        return {"success": True, "added": added, "skipped": skipped}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Migration failed")


@router.get("/candidates/{candidate_id}/full-profile")
async def get_candidate_full_profile(
    candidate_id: int,
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
            c.license_states, c.production_history, c.current_company, c.current_title,
            -- Social media fields
            c.facebook_url, c.instagram_url, c.twitter_url, c.social_profiles,
            c.social_posts, c.social_last_synced,
            -- Profile fields
            c.headshot_url, c.bio, c.specialties, c.market_areas,
            c.education, c.certifications, c.awards, c.testimonials,
            c.created_at, c.updated_at
        FROM mm_candidates c
        WHERE c.id = :id AND c.is_active = true
    """), {"id": candidate_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Get interview history
    interviews = db.execute(text("""
        SELECT id, interview_type, interview_round, scheduled_at, status, overall_score
        FROM mm_interviews WHERE candidate_id = :id ORDER BY scheduled_at DESC
    """), {"id": candidate_id}).fetchall()

    # Get notes
    notes = db.execute(text("""
        SELECT id, content, note_type, created_at
        FROM mm_candidate_notes WHERE candidate_id = :id ORDER BY created_at DESC LIMIT 10
    """), {"id": candidate_id}).fetchall()

    # Get activity timeline
    activities = db.execute(text("""
        SELECT id, activity_type, description, created_at
        FROM mm_candidate_activities WHERE candidate_id = :id ORDER BY created_at DESC LIMIT 20
    """), {"id": candidate_id}).fetchall()

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
        } if True else None,
    }


@router.put("/candidates/{candidate_id}/social-media")
async def update_candidate_social_media(
    candidate_id: int,
    facebook_url: Optional[str] = None,
    instagram_url: Optional[str] = None,
    twitter_url: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Update candidate social media URLs."""
    result = db.execute(text("""
        UPDATE mm_candidates
        SET facebook_url = COALESCE(:facebook, facebook_url),
            instagram_url = COALESCE(:instagram, instagram_url),
            twitter_url = COALESCE(:twitter, twitter_url),
            linkedin_url = COALESCE(:linkedin, linkedin_url),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        RETURNING id
    """), {
        "id": candidate_id,
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
    db: Session = Depends(get_db)
):
    """Update candidate production data."""
    import json

    result = db.execute(text("""
        UPDATE mm_candidates
        SET annual_volume = COALESCE(:volume, annual_volume),
            annual_units = COALESCE(:units, annual_units),
            nmls_id = COALESCE(:nmls, nmls_id),
            current_company = COALESCE(:company, current_company),
            current_title = COALESCE(:title, current_title),
            license_states = COALESCE(CAST(:states AS JSONB), license_states),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        RETURNING id
    """), {
        "id": candidate_id,
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
    db: Session = Depends(get_db)
):
    """Update candidate basic information (name, email, phone)."""
    result = db.execute(text("""
        UPDATE mm_candidates
        SET first_name = COALESCE(:first_name, first_name),
            last_name = COALESCE(:last_name, last_name),
            email = COALESCE(:email, email),
            phone = COALESCE(:phone, phone),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        RETURNING id
    """), {
        "id": candidate_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
    }).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    db.commit()
    return {"id": candidate_id, "status": "updated"}
