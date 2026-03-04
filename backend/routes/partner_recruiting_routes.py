"""
Partner Recruiting Routes
API endpoints for Loan Officers to recruit and manage referral partners.
Each LO only sees their own partner recruits (owner_id + organization_id filtering).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from database import get_db
from auth.dependencies import get_current_user
from database.models import User
import json
import os
from sqlalchemy.exc import SQLAlchemyError



router = APIRouter(prefix="/api/v1/partner-recruiting", tags=["partner-recruiting"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class PartnerCandidateCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    partner_type: str = "realtor"
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    company_name: Optional[str] = None
    business_name: Optional[str] = None
    title: Optional[str] = None
    years_in_business: Optional[int] = None
    website: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    source: Optional[str] = None
    source_detail: Optional[str] = None
    notes: Optional[str] = None
    linkedin_url: Optional[str] = None
    preferred_contact_method: Optional[str] = None
    best_contact_time: Optional[str] = None


class PartnerCandidateUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    partner_type: Optional[str] = None
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    company_name: Optional[str] = None
    business_name: Optional[str] = None
    title: Optional[str] = None
    years_in_business: Optional[int] = None
    website: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    notes: Optional[str] = None
    linkedin_url: Optional[str] = None
    preferred_contact_method: Optional[str] = None
    best_contact_time: Optional[str] = None
    production_volume: Optional[float] = None


class PartnerStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class PartnerMeetingCreate(BaseModel):
    meeting_type: str = "coffee"
    title: Optional[str] = None
    scheduled_at: datetime
    duration_minutes: int = 30
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    timezone: str = "America/New_York"


class PartnerMeetingComplete(BaseModel):
    outcome: str  # very_positive, positive, neutral, negative, needs_followup
    next_steps: Optional[str] = None
    key_takeaways: Optional[str] = None
    objections: Optional[str] = None
    interest_level: Optional[int] = None  # 1-5


class PartnerProposalCreate(BaseModel):
    proposal_type: str = "standard"
    referral_commission_structure: Optional[dict] = None
    co_marketing_benefits: Optional[List[str]] = None
    technology_access: Optional[List[str]] = None
    exclusive_territory: Optional[str] = None
    additional_benefits: Optional[str] = None
    expires_in_days: int = 14


class PartnerProposalSend(BaseModel):
    expires_in_days: int = 14


class PartnerProposalRespond(BaseModel):
    accepted: bool
    notes: Optional[str] = None


class PartnerNoteCreate(BaseModel):
    note_type: str = "general"
    content: str
    is_private: bool = False


class LogCallRequest(BaseModel):
    outcome: str  # connected, voicemail, no_answer, busy, wrong_number
    duration_seconds: Optional[int] = None
    notes: Optional[str] = None
    callback_scheduled: Optional[datetime] = None


class PartnerAssessmentUpdate(BaseModel):
    production_score: Optional[float] = None
    referral_potential_score: Optional[float] = None
    relationship_score: Optional[float] = None
    professionalism_score: Optional[float] = None
    market_presence_score: Optional[float] = None
    communication_score: Optional[float] = None
    technical_skills_score: Optional[float] = None
    experience_score: Optional[float] = None
    strengths: Optional[List[str]] = None
    concerns: Optional[List[str]] = None
    talking_points: Optional[List[str]] = None
    recommended_approach: Optional[str] = None


class EmployeeCandidateCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    employee_role: str  # loan_officer, processor, closer, underwriter, assistant
    nmls_id: Optional[str] = None
    license_states: Optional[List[str]] = None
    current_employer: Optional[str] = None
    years_experience: Optional[int] = None
    desired_compensation: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None
    linkedin_url: Optional[str] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def verify_partner_ownership(partner_id: int, user_id: int, db: Session, organization_id: int = None):
    """Verify user owns this partner recruit within their organization."""
    if organization_id:
        result = db.execute(text("""
            SELECT id, first_name, last_name, status, candidate_category
            FROM partner_candidates
            WHERE id = :id AND owner_id = :user_id
              AND organization_id = :org_id AND is_active = true
        """), {"id": partner_id, "user_id": user_id, "org_id": organization_id}).fetchone()
    else:
        result = db.execute(text("""
            SELECT id, first_name, last_name, status, candidate_category
            FROM partner_candidates
            WHERE id = :id AND owner_id = :user_id AND is_active = true
        """), {"id": partner_id, "user_id": user_id}).fetchone()

    if not result:
        raise HTTPException(
            status_code=404,
            detail="Partner not found or you don't have access"
        )
    return result


# Status lists by candidate category
PARTNER_VALID_STATUSES = [
    'new', 'contacted', 'qualified', 'meeting_scheduled', 'met',
    'proposal_sent', 'negotiating', 'onboarded', 'declined', 'inactive'
]

EMPLOYEE_VALID_STATUSES = [
    'new', 'contacted', 'qualified', 'meeting_scheduled', 'met',
    'screening', 'interview', 'offer', 'hired',
    'declined', 'inactive', 'withdrawn'
]

VALID_EMPLOYEE_ROLES = ['loan_officer', 'processor', 'closer', 'underwriter', 'assistant']


def log_partner_activity(
    db: Session,
    partner_id: int,
    activity_type: str,
    description: str,
    user_id: int,
    metadata: dict = None,
    meeting_id: int = None,
    proposal_id: int = None,
    organization_id: int = None
):
    """Log an activity for a partner candidate."""
    db.execute(text("""
        INSERT INTO partner_activities
        (partner_candidate_id, activity_type, description, metadata, meeting_id, proposal_id, performed_by, organization_id, created_at)
        VALUES (:partner_id, :activity_type, :description, :metadata, :meeting_id, :proposal_id, :user_id, :org_id, CURRENT_TIMESTAMP)
    """), {
        "partner_id": partner_id,
        "activity_type": activity_type,
        "description": description,
        "metadata": json.dumps(metadata) if metadata else "{}",
        "meeting_id": meeting_id,
        "proposal_id": proposal_id,
        "user_id": user_id,
        "org_id": organization_id
    })


def calculate_overall_grade(score: float) -> str:
    """Calculate letter grade from score."""
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 85: return "A-"
    if score >= 80: return "B+"
    if score >= 75: return "B"
    if score >= 70: return "B-"
    if score >= 65: return "C+"
    if score >= 60: return "C"
    if score >= 55: return "C-"
    if score >= 50: return "D"
    return "F"


# =============================================================================
# DASHBOARD & STATS
# =============================================================================

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    candidate_category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recruiting dashboard stats for current LO."""
    user_id = current_user.id
    org_id = current_user.organization_id

    category_filter = ""
    params = {"user_id": user_id, "org_id": org_id}
    if candidate_category:
        category_filter = "AND candidate_category = :candidate_category"
        params["candidate_category"] = candidate_category

    # Get counts by status
    status_counts = db.execute(text(f"""
        SELECT status, COUNT(*) as count
        FROM partner_candidates
        WHERE owner_id = :user_id AND organization_id = :org_id AND is_active = true {category_filter}
        GROUP BY status
    """), params).fetchall()

    counts = {row.status: row.count for row in status_counts}

    # Get recent activity count (last 7 days)
    recent_count = db.execute(text(f"""
        SELECT COUNT(*) as count
        FROM partner_candidates
        WHERE owner_id = :user_id AND organization_id = :org_id
          AND is_active = true
          AND created_at >= CURRENT_DATE - INTERVAL '7 days'
          {category_filter}
    """), params).fetchone()

    # Get upcoming meetings
    upcoming_meetings = db.execute(text(f"""
        SELECT COUNT(*) as count
        FROM partner_meetings pm
        JOIN partner_candidates pc ON pc.id = pm.partner_candidate_id
        WHERE pc.owner_id = :user_id
          AND pm.status IN ('scheduled', 'confirmed')
          AND pm.scheduled_at >= CURRENT_TIMESTAMP
          AND pm.scheduled_at < CURRENT_TIMESTAMP + INTERVAL '7 days'
          {category_filter.replace('candidate_category', 'pc.candidate_category') if category_filter else ''}
    """), params).fetchone()

    # Get pending proposals (partner-only concept)
    pending_proposals = db.execute(text(f"""
        SELECT COUNT(*) as count
        FROM partner_proposals pp
        JOIN partner_candidates pc ON pc.id = pp.partner_candidate_id
        WHERE pc.owner_id = :user_id
          AND pp.status IN ('sent', 'viewed')
          {category_filter.replace('candidate_category', 'pc.candidate_category') if category_filter else ''}
    """), params).fetchone()

    # Calculate total active pipeline based on category
    if candidate_category == 'employee':
        active_statuses = ['new', 'contacted', 'qualified', 'meeting_scheduled', 'met', 'screening', 'interview', 'offer']
        pipeline_stages = [
            {"status": "new", "label": "New", "count": counts.get('new', 0)},
            {"status": "contacted", "label": "Contacted", "count": counts.get('contacted', 0)},
            {"status": "qualified", "label": "Qualified", "count": counts.get('qualified', 0)},
            {"status": "meeting_scheduled", "label": "Meeting Scheduled", "count": counts.get('meeting_scheduled', 0)},
            {"status": "met", "label": "Met", "count": counts.get('met', 0)},
            {"status": "screening", "label": "Screening", "count": counts.get('screening', 0)},
            {"status": "interview", "label": "Interview", "count": counts.get('interview', 0)},
            {"status": "offer", "label": "Offer Extended", "count": counts.get('offer', 0)},
            {"status": "hired", "label": "Hired", "count": counts.get('hired', 0)},
        ]
        terminal_label = "hired"
        terminal_count = counts.get('hired', 0)
    else:
        active_statuses = ['new', 'contacted', 'qualified', 'meeting_scheduled', 'met', 'proposal_sent', 'negotiating']
        pipeline_stages = [
            {"status": "new", "label": "New", "count": counts.get('new', 0)},
            {"status": "contacted", "label": "Contacted", "count": counts.get('contacted', 0)},
            {"status": "qualified", "label": "Qualified", "count": counts.get('qualified', 0)},
            {"status": "meeting_scheduled", "label": "Meeting Scheduled", "count": counts.get('meeting_scheduled', 0)},
            {"status": "met", "label": "Met", "count": counts.get('met', 0)},
            {"status": "proposal_sent", "label": "Proposal Sent", "count": counts.get('proposal_sent', 0)},
            {"status": "negotiating", "label": "Negotiating", "count": counts.get('negotiating', 0)},
            {"status": "onboarded", "label": "Onboarded", "count": counts.get('onboarded', 0)},
        ]
        terminal_label = "onboarded"
        terminal_count = counts.get('onboarded', 0)

    total_active = sum(counts.get(s, 0) for s in active_statuses)

    return {
        "candidate_category": candidate_category or "all",
        "total_active": total_active,
        "new_this_week": recent_count.count if recent_count else 0,
        "upcoming_meetings": upcoming_meetings.count if upcoming_meetings else 0,
        "pending_proposals": pending_proposals.count if pending_proposals else 0,
        "onboarded_total": terminal_count,
        "by_status": counts,
        "pipeline_stages": pipeline_stages
    }


@router.get("/pipeline/metrics")
async def get_pipeline_metrics(
    days: int = Query(90, ge=7, le=365),
    candidate_category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get pipeline conversion metrics for current LO."""
    user_id = current_user.id
    org_id = current_user.organization_id

    category_filter = ""
    params = {"user_id": user_id, "org_id": org_id, "days": days}
    if candidate_category:
        category_filter = "AND candidate_category = :candidate_category"
        params["candidate_category"] = candidate_category

    def calc_rate(num, denom):
        return round((num / denom) * 100, 1) if denom > 0 else 0

    if candidate_category == 'employee':
        # Employee funnel
        funnel = db.execute(text(f"""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status NOT IN ('new', 'declined', 'inactive', 'withdrawn')) as contacted,
                COUNT(*) FILTER (WHERE status IN ('qualified', 'meeting_scheduled', 'met', 'screening', 'interview', 'offer', 'hired')) as qualified,
                COUNT(*) FILTER (WHERE status IN ('met', 'screening', 'interview', 'offer', 'hired')) as met,
                COUNT(*) FILTER (WHERE status IN ('screening', 'interview', 'offer', 'hired')) as screening,
                COUNT(*) FILTER (WHERE status IN ('interview', 'offer', 'hired')) as interview,
                COUNT(*) FILTER (WHERE status IN ('offer', 'hired')) as offer,
                COUNT(*) FILTER (WHERE status = 'hired') as hired,
                COUNT(*) FILTER (WHERE status IN ('declined', 'withdrawn')) as declined
            FROM partner_candidates
            WHERE owner_id = :user_id AND organization_id = :org_id
              AND is_active = true
              AND created_at >= CURRENT_DATE - :days * INTERVAL '1 day'
              {category_filter}
        """), params).fetchone()

        return {
            "period_days": days,
            "candidate_category": "employee",
            "funnel": {
                "total": funnel.total,
                "contacted": funnel.contacted,
                "qualified": funnel.qualified,
                "met": funnel.met,
                "screening": funnel.screening,
                "interview": funnel.interview,
                "offer": funnel.offer,
                "hired": funnel.hired,
                "declined": funnel.declined
            },
            "conversion_rates": {
                "contact_rate": calc_rate(funnel.contacted, funnel.total),
                "qualify_rate": calc_rate(funnel.qualified, funnel.contacted),
                "meeting_rate": calc_rate(funnel.met, funnel.qualified),
                "screening_rate": calc_rate(funnel.screening, funnel.met),
                "interview_rate": calc_rate(funnel.interview, funnel.screening),
                "offer_rate": calc_rate(funnel.offer, funnel.interview),
                "hire_rate": calc_rate(funnel.hired, funnel.offer),
                "overall_conversion": calc_rate(funnel.hired, funnel.total)
            }
        }

    # Partner funnel (default)
    funnel = db.execute(text(f"""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status IN ('contacted', 'qualified', 'meeting_scheduled', 'met', 'proposal_sent', 'negotiating', 'onboarded')) as contacted,
            COUNT(*) FILTER (WHERE status IN ('qualified', 'meeting_scheduled', 'met', 'proposal_sent', 'negotiating', 'onboarded')) as qualified,
            COUNT(*) FILTER (WHERE status IN ('met', 'proposal_sent', 'negotiating', 'onboarded')) as met,
            COUNT(*) FILTER (WHERE status IN ('proposal_sent', 'negotiating', 'onboarded')) as proposal_sent,
            COUNT(*) FILTER (WHERE status = 'onboarded') as onboarded,
            COUNT(*) FILTER (WHERE status = 'declined') as declined
        FROM partner_candidates
        WHERE owner_id = :user_id AND organization_id = :org_id
          AND is_active = true
          AND created_at >= CURRENT_DATE - :days * INTERVAL '1 day'
          {category_filter}
    """), params).fetchone()

    return {
        "period_days": days,
        "candidate_category": candidate_category or "all",
        "funnel": {
            "total": funnel.total,
            "contacted": funnel.contacted,
            "qualified": funnel.qualified,
            "met": funnel.met,
            "proposal_sent": funnel.proposal_sent,
            "onboarded": funnel.onboarded,
            "declined": funnel.declined
        },
        "conversion_rates": {
            "contact_rate": calc_rate(funnel.contacted, funnel.total),
            "qualify_rate": calc_rate(funnel.qualified, funnel.contacted),
            "meeting_rate": calc_rate(funnel.met, funnel.qualified),
            "proposal_rate": calc_rate(funnel.proposal_sent, funnel.met),
            "close_rate": calc_rate(funnel.onboarded, funnel.proposal_sent),
            "overall_conversion": calc_rate(funnel.onboarded, funnel.total)
        }
    }


# =============================================================================
# PARTNER CANDIDATES
# =============================================================================

@router.get("/candidates")
async def list_partner_candidates(
    status: Optional[str] = None,
    partner_type: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    candidate_category: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List partner/employee candidates for current LO (owner_id + org filtered)."""
    user_id = current_user.id
    org_id = current_user.organization_id
    params = {"user_id": user_id, "org_id": org_id, "limit": limit, "offset": offset}
    filters = ["owner_id = :user_id", "organization_id = :org_id", "is_active = true"]

    if candidate_category:
        filters.append("candidate_category = :candidate_category")
        params["candidate_category"] = candidate_category

    if status:
        filters.append("status = :status")
        params["status"] = status

    if partner_type:
        filters.append("partner_type = :partner_type")
        params["partner_type"] = partner_type

    if source:
        filters.append("source = :source")
        params["source"] = source

    if search:
        filters.append("""(
            first_name ILIKE :search
            OR last_name ILIKE :search
            OR email ILIKE :search
            OR company_name ILIKE :search
            OR business_name ILIKE :search
            OR current_employer ILIKE :search
        )""")
        params["search"] = f"%{search}%"

    where_sql = " AND ".join(filters)

    results = db.execute(text(f"""
        SELECT
            id, first_name, last_name, email, phone,
            partner_type, company_name, business_name, title,
            status, status_changed_at, source,
            overall_score, production_volume,
            city, state, created_at, last_activity_at,
            candidate_category, employee_role, current_employer, years_experience
        FROM partner_candidates
        WHERE {where_sql}
        ORDER BY
            CASE status
                WHEN 'new' THEN 1
                WHEN 'contacted' THEN 2
                WHEN 'qualified' THEN 3
                WHEN 'meeting_scheduled' THEN 4
                WHEN 'met' THEN 5
                WHEN 'screening' THEN 5
                WHEN 'proposal_sent' THEN 6
                WHEN 'interview' THEN 6
                WHEN 'negotiating' THEN 7
                WHEN 'offer' THEN 7
                WHEN 'onboarded' THEN 8
                WHEN 'hired' THEN 8
                ELSE 9
            END,
            created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    # Get total count
    count_result = db.execute(text(f"""
        SELECT COUNT(*) as count FROM partner_candidates WHERE {where_sql}
    """), {k: v for k, v in params.items() if k not in ['limit', 'offset']}).fetchone()

    candidates = []
    for r in results:
        candidate = {
            "id": r.id,
            "first_name": r.first_name,
            "last_name": r.last_name,
            "name": f"{r.first_name} {r.last_name}",
            "email": r.email,
            "phone": r.phone,
            "partner_type": r.partner_type,
            "company": r.company_name or r.business_name,
            "title": r.title,
            "status": r.status,
            "status_changed_at": r.status_changed_at.isoformat() if r.status_changed_at else None,
            "source": r.source,
            "overall_score": float(r.overall_score) if r.overall_score else None,
            "production_volume": float(r.production_volume) if r.production_volume else None,
            "location": f"{r.city}, {r.state}" if r.city and r.state else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_activity_at": r.last_activity_at.isoformat() if r.last_activity_at else None,
            "candidate_category": r.candidate_category or "partner",
        }
        # Add employee-specific fields
        if r.candidate_category == 'employee':
            candidate["employee_role"] = r.employee_role
            candidate["current_employer"] = r.current_employer
            candidate["years_experience"] = r.years_experience
        candidates.append(candidate)

    return {
        "candidates": candidates,
        "count": len(candidates),
        "total": count_result.count if count_result else len(candidates)
    }


@router.get("/candidates/{partner_id}")
async def get_partner_candidate(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed partner candidate information."""
    user_id = current_user.id
    org_id = current_user.organization_id

    result = db.execute(text("""
        SELECT
            pc.*,
            rp.id as referral_partner_id_linked
        FROM partner_candidates pc
        LEFT JOIN referral_partners rp ON rp.id = pc.referral_partner_id
        WHERE pc.id = :partner_id AND pc.owner_id = :user_id
          AND pc.organization_id = :org_id AND pc.is_active = true
    """), {"partner_id": partner_id, "user_id": user_id, "org_id": org_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Partner not found")

    # Get assessment
    assessment = db.execute(text("""
        SELECT * FROM partner_assessments WHERE partner_candidate_id = :partner_id
    """), {"partner_id": partner_id}).fetchone()

    # Get upcoming meetings
    upcoming_meetings = db.execute(text("""
        SELECT id, meeting_type, title, scheduled_at, duration_minutes, location, meeting_link, status
        FROM partner_meetings
        WHERE partner_candidate_id = :partner_id
          AND status IN ('scheduled', 'confirmed')
          AND scheduled_at >= CURRENT_TIMESTAMP
        ORDER BY scheduled_at ASC
        LIMIT 3
    """), {"partner_id": partner_id}).fetchall()

    # Get latest proposal
    latest_proposal = db.execute(text("""
        SELECT id, proposal_number, proposal_type, status, sent_at, expires_at
        FROM partner_proposals
        WHERE partner_candidate_id = :partner_id
        ORDER BY created_at DESC
        LIMIT 1
    """), {"partner_id": partner_id}).fetchone()

    return {
        "id": result.id,
        "first_name": result.first_name,
        "last_name": result.last_name,
        "name": f"{result.first_name} {result.last_name}",
        "email": result.email,
        "phone": result.phone,
        "partner_type": result.partner_type,
        "license_number": result.license_number,
        "license_state": result.license_state,
        "company_name": result.company_name,
        "business_name": result.business_name,
        "title": result.title,
        "years_in_business": result.years_in_business,
        "website": result.website,
        "address": {
            "street": result.street_address,
            "city": result.city,
            "state": result.state,
            "zip_code": result.zip_code
        },
        "source": result.source,
        "source_detail": result.source_detail,
        "status": result.status,
        "status_changed_at": result.status_changed_at.isoformat() if result.status_changed_at else None,
        "linkedin_url": result.linkedin_url,
        "preferred_contact_method": result.preferred_contact_method,
        "best_contact_time": result.best_contact_time,
        "notes": result.notes,
        "production_volume": float(result.production_volume) if result.production_volume else None,
        "overall_score": float(result.overall_score) if result.overall_score else None,
        "onboarded_at": result.onboarded_at.isoformat() if result.onboarded_at else None,
        "referral_partner_id": result.referral_partner_id,
        "created_at": result.created_at.isoformat() if result.created_at else None,
        # Category & employee fields
        "candidate_category": getattr(result, 'candidate_category', 'partner') or 'partner',
        "employee_role": getattr(result, 'employee_role', None),
        "nmls_id": getattr(result, 'nmls_id', None),
        "license_states": json.loads(result.license_states) if getattr(result, 'license_states', None) else [],
        "current_employer": getattr(result, 'current_employer', None),
        "years_experience": getattr(result, 'years_experience', None),
        "desired_compensation": getattr(result, 'desired_compensation', None),
        "hired_at": result.hired_at.isoformat() if getattr(result, 'hired_at', None) else None,
        "assessment": {
            "production_score": float(assessment.production_score) if assessment and assessment.production_score else None,
            "referral_potential_score": float(assessment.referral_potential_score) if assessment and assessment.referral_potential_score else None,
            "relationship_score": float(assessment.relationship_score) if assessment and assessment.relationship_score else None,
            "professionalism_score": float(assessment.professionalism_score) if assessment and assessment.professionalism_score else None,
            "market_presence_score": float(assessment.market_presence_score) if assessment and assessment.market_presence_score else None,
            "communication_score": float(assessment.communication_score) if assessment and assessment.communication_score else None,
            "technical_skills_score": float(assessment.technical_skills_score) if assessment and getattr(assessment, 'technical_skills_score', None) else None,
            "experience_score": float(assessment.experience_score) if assessment and getattr(assessment, 'experience_score', None) else None,
            "overall_score": float(assessment.overall_score) if assessment and assessment.overall_score else None,
            "overall_grade": assessment.overall_grade if assessment else None,
            "strengths": json.loads(assessment.strengths) if assessment and assessment.strengths else [],
            "concerns": json.loads(assessment.concerns) if assessment and assessment.concerns else [],
        } if assessment else None,
        "upcoming_meetings": [
            {
                "id": m.id,
                "type": m.meeting_type,
                "title": m.title,
                "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
                "duration_minutes": m.duration_minutes,
                "location": m.location,
                "meeting_link": m.meeting_link,
                "status": m.status
            }
            for m in upcoming_meetings
        ],
        "latest_proposal": {
            "id": latest_proposal.id,
            "proposal_number": latest_proposal.proposal_number,
            "type": latest_proposal.proposal_type,
            "status": latest_proposal.status,
            "sent_at": latest_proposal.sent_at.isoformat() if latest_proposal.sent_at else None,
            "expires_at": latest_proposal.expires_at.isoformat() if latest_proposal.expires_at else None
        } if latest_proposal else None
    }


@router.post("/candidates")
async def create_partner_candidate(
    data: PartnerCandidateCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new partner candidate."""
    user_id = current_user.id
    org_id = current_user.organization_id

    # Check for duplicate email within this owner's org
    existing = db.execute(text("""
        SELECT id FROM partner_candidates
        WHERE owner_id = :user_id AND organization_id = :org_id
          AND email = :email AND is_active = true
    """), {"user_id": user_id, "org_id": org_id, "email": data.email}).fetchone()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have a partner with this email address"
        )

    try:
        result = db.execute(text("""
            INSERT INTO partner_candidates (
                owner_id, organization_id, first_name, last_name, email, phone,
                partner_type, license_number, license_state,
                company_name, business_name, title, years_in_business, website,
                street_address, city, state, zip_code,
                source, source_detail, notes, linkedin_url,
                preferred_contact_method, best_contact_time,
                status, status_changed_at, created_at, updated_at
            ) VALUES (
                :owner_id, :organization_id, :first_name, :last_name, :email, :phone,
                :partner_type, :license_number, :license_state,
                :company_name, :business_name, :title, :years_in_business, :website,
                :street_address, :city, :state, :zip_code,
                :source, :source_detail, :notes, :linkedin_url,
                :preferred_contact_method, :best_contact_time,
                'new', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id
        """), {
            "owner_id": user_id,
            "organization_id": current_user.organization_id,
            **data.model_dump()
        })

        partner_id = result.fetchone().id

        # Log activity
        log_partner_activity(
            db, partner_id, "created",
            f"Partner candidate created: {data.first_name} {data.last_name}",
            user_id,
            organization_id=current_user.organization_id
        )

        db.commit()

        return {
            "id": partner_id,
            "status": "created",
            "message": f"Partner candidate {data.first_name} {data.last_name} created successfully"
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create partner candidate")


@router.post("/employee-candidates")
async def create_employee_candidate(
    data: EmployeeCandidateCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new employee recruit candidate."""
    user_id = current_user.id
    org_id = current_user.organization_id

    if data.employee_role not in VALID_EMPLOYEE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid employee_role. Must be one of: {VALID_EMPLOYEE_ROLES}"
        )

    # Check for duplicate email within this owner's org
    existing = db.execute(text("""
        SELECT id FROM partner_candidates
        WHERE owner_id = :user_id AND organization_id = :org_id
          AND email = :email AND is_active = true
    """), {"user_id": user_id, "org_id": org_id, "email": data.email}).fetchone()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have a candidate with this email address"
        )

    try:
        result = db.execute(text("""
            INSERT INTO partner_candidates (
                owner_id, organization_id,
                candidate_category, partner_type,
                employee_role, nmls_id, license_states,
                current_employer, years_experience, desired_compensation,
                first_name, last_name, email, phone,
                city, state, source, notes, linkedin_url,
                status, status_changed_at, created_at, updated_at
            ) VALUES (
                :owner_id, :organization_id,
                'employee', :employee_role,
                :employee_role, :nmls_id, :license_states,
                :current_employer, :years_experience, :desired_compensation,
                :first_name, :last_name, :email, :phone,
                :city, :state, :source, :notes, :linkedin_url,
                'new', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING id
        """), {
            "owner_id": user_id,
            "organization_id": current_user.organization_id,
            "employee_role": data.employee_role,
            "nmls_id": data.nmls_id,
            "license_states": json.dumps(data.license_states or []),
            "current_employer": data.current_employer,
            "years_experience": data.years_experience,
            "desired_compensation": data.desired_compensation,
            "first_name": data.first_name,
            "last_name": data.last_name,
            "email": data.email,
            "phone": data.phone,
            "city": data.city,
            "state": data.state,
            "source": data.source,
            "notes": data.notes,
            "linkedin_url": data.linkedin_url,
        })

        candidate_id = result.fetchone().id

        log_partner_activity(
            db, candidate_id, "created",
            f"Employee candidate created: {data.first_name} {data.last_name} ({data.employee_role})",
            user_id,
            organization_id=current_user.organization_id
        )

        db.commit()

        return {
            "id": candidate_id,
            "status": "created",
            "candidate_category": "employee",
            "message": f"Employee candidate {data.first_name} {data.last_name} created successfully"
        }
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create employee candidate")


@router.post("/candidates/{partner_id}/hire")
async def hire_employee_candidate(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark an employee candidate as hired."""
    user_id = current_user.id
    candidate = verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    category = getattr(candidate, 'candidate_category', 'partner') or 'partner'
    if category != 'employee':
        raise HTTPException(status_code=400, detail="This action is only valid for employee candidates")

    if candidate.status == 'hired':
        raise HTTPException(status_code=400, detail="Candidate is already hired")

    db.execute(text("""
        UPDATE partner_candidates
        SET status = 'hired',
            hired_at = CURRENT_TIMESTAMP,
            status_changed_at = CURRENT_TIMESTAMP,
            status_changed_by = :user_id,
            last_activity_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :partner_id AND organization_id = :org_id
    """), {"partner_id": partner_id, "user_id": user_id, "org_id": current_user.organization_id})

    log_partner_activity(
        db, partner_id, "hired",
        "Employee candidate marked as hired",
        user_id
    )

    db.commit()

    return {
        "partner_id": partner_id,
        "status": "hired",
        "message": "Employee candidate has been marked as hired"
    }


@router.put("/candidates/{partner_id}")
async def update_partner_candidate(
    partner_id: int,
    data: PartnerCandidateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a partner candidate."""
    user_id = current_user.id
    org_id = current_user.organization_id
    verify_partner_ownership(partner_id, user_id, db, org_id)

    # Allowlist of updatable fields to prevent SQL injection via dynamic field names
    allowed_fields = {
        "first_name", "last_name", "email", "phone", "partner_type",
        "license_number", "license_state", "company_name", "business_name",
        "title", "years_in_business", "website", "street_address", "city",
        "state", "zip_code", "source", "source_detail", "notes", "linkedin_url",
        "preferred_contact_method", "best_contact_time",
        # Employee-specific fields
        "employee_role", "nmls_id", "current_employer",
        "years_experience", "desired_compensation",
    }

    update_fields = []
    params = {"partner_id": partner_id, "user_id": user_id, "org_id": org_id}

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None and field in allowed_fields:
            update_fields.append(f"{field} = :{field}")
            params[field] = value

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields.append("updated_at = CURRENT_TIMESTAMP")

    try:
        result = db.execute(text(f"""
            UPDATE partner_candidates
            SET {', '.join(update_fields)}
            WHERE id = :partner_id AND owner_id = :user_id AND organization_id = :org_id
            RETURNING id
        """), params)

        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Partner not found")

        db.commit()
        return {"id": partner_id, "updated": True}
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update partner candidate")


@router.delete("/candidates/{partner_id}")
async def delete_partner_candidate(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft delete a partner candidate."""
    user_id = current_user.id
    verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    try:
        db.execute(text("""
            UPDATE partner_candidates
            SET is_active = false, updated_at = CURRENT_TIMESTAMP
            WHERE id = :partner_id AND owner_id = :user_id
              AND organization_id = :org_id
        """), {"partner_id": partner_id, "user_id": user_id, "org_id": current_user.organization_id})

        log_partner_activity(db, partner_id, "deleted", "Partner candidate deleted", user_id)
        db.commit()

        return {"id": partner_id, "deleted": True}
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete partner candidate")


@router.patch("/candidates/{partner_id}/status")
async def update_partner_status(
    partner_id: int,
    data: PartnerStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update partner/employee candidate status."""
    user_id = current_user.id
    partner = verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)
    old_status = partner.status

    # Category-aware status validation
    category = getattr(partner, 'candidate_category', 'partner') or 'partner'
    valid_statuses = EMPLOYEE_VALID_STATUSES if category == 'employee' else PARTNER_VALID_STATUSES

    if data.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status for {category}. Must be one of: {valid_statuses}")

    # Build extra SET clauses for terminal statuses
    extra_sets = ""
    if data.status == 'hired' and category == 'employee':
        extra_sets = ", hired_at = CURRENT_TIMESTAMP"
    elif data.status == 'withdrawn' and category == 'employee':
        extra_sets = ", withdrawn_at = CURRENT_TIMESTAMP"

    db.execute(text(f"""
        UPDATE partner_candidates
        SET status = :status,
            status_changed_at = CURRENT_TIMESTAMP,
            status_changed_by = :user_id,
            last_activity_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
            {extra_sets}
        WHERE id = :partner_id AND organization_id = :org_id
    """), {"partner_id": partner_id, "status": data.status, "user_id": user_id, "org_id": current_user.organization_id})

    log_partner_activity(
        db, partner_id, "status_change",
        f"Status changed from {old_status} to {data.status}" + (f": {data.reason}" if data.reason else ""),
        user_id,
        metadata={"old_status": old_status, "new_status": data.status, "reason": data.reason}
    )

    db.commit()

    return {
        "id": partner_id,
        "old_status": old_status,
        "new_status": data.status,
        "message": f"Status updated to {data.status}"
    }


# =============================================================================
# MEETINGS
# =============================================================================

@router.get("/candidates/{partner_id}/meetings")
async def list_partner_meetings(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all meetings for a partner candidate."""
    user_id = current_user.id
    verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    results = db.execute(text("""
        SELECT
            id, meeting_type, meeting_round, title,
            scheduled_at, duration_minutes, timezone, location, meeting_link,
            status, outcome, next_steps, key_takeaways, interest_level,
            completed_at, created_at
        FROM partner_meetings
        WHERE partner_candidate_id = :partner_id
        ORDER BY scheduled_at DESC
    """), {"partner_id": partner_id}).fetchall()

    return {
        "meetings": [
            {
                "id": r.id,
                "meeting_type": r.meeting_type,
                "round": r.meeting_round,
                "title": r.title,
                "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
                "duration_minutes": r.duration_minutes,
                "timezone": r.timezone,
                "location": r.location,
                "meeting_link": r.meeting_link,
                "status": r.status,
                "outcome": r.outcome,
                "next_steps": r.next_steps,
                "key_takeaways": r.key_takeaways,
                "interest_level": r.interest_level,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in results
        ]
    }


@router.post("/candidates/{partner_id}/meetings")
async def schedule_partner_meeting(
    partner_id: int,
    data: PartnerMeetingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Schedule a meeting with a partner candidate."""
    user_id = current_user.id
    partner = verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    # Get the next round number
    round_result = db.execute(text("""
        SELECT COALESCE(MAX(meeting_round), 0) + 1 as next_round
        FROM partner_meetings
        WHERE partner_candidate_id = :partner_id
    """), {"partner_id": partner_id}).fetchone()

    result = db.execute(text("""
        INSERT INTO partner_meetings (
            partner_candidate_id, meeting_type, meeting_round, title,
            scheduled_at, duration_minutes, timezone, location, meeting_link,
            status, created_by, created_at
        ) VALUES (
            :partner_id, :meeting_type, :round, :title,
            :scheduled_at, :duration_minutes, :timezone, :location, :meeting_link,
            'scheduled', :user_id, CURRENT_TIMESTAMP
        )
        RETURNING id
    """), {
        "partner_id": partner_id,
        "meeting_type": data.meeting_type,
        "round": round_result.next_round,
        "title": data.title or f"{data.meeting_type.replace('_', ' ').title()} with {partner.first_name}",
        "scheduled_at": data.scheduled_at,
        "duration_minutes": data.duration_minutes,
        "timezone": data.timezone,
        "location": data.location,
        "meeting_link": data.meeting_link,
        "user_id": user_id
    })

    meeting_id = result.fetchone().id

    # Update partner status to meeting_scheduled if appropriate
    if partner.status in ['new', 'contacted', 'qualified']:
        db.execute(text("""
            UPDATE partner_candidates
            SET status = 'meeting_scheduled',
                status_changed_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :partner_id
        """), {"partner_id": partner_id})

    log_partner_activity(
        db, partner_id, "meeting_scheduled",
        f"Meeting scheduled for {data.scheduled_at.strftime('%m/%d/%Y %I:%M %p')}",
        user_id,
        meeting_id=meeting_id
    )

    db.commit()

    return {
        "id": meeting_id,
        "status": "scheduled",
        "message": f"Meeting scheduled for {data.scheduled_at.strftime('%m/%d/%Y %I:%M %p')}"
    }


@router.patch("/meetings/{meeting_id}/complete")
async def complete_partner_meeting(
    meeting_id: int,
    data: PartnerMeetingComplete,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a meeting as completed with outcome."""
    user_id = current_user.id
    org_id = current_user.organization_id

    # Get meeting and verify ownership + tenant isolation
    meeting = db.execute(text("""
        SELECT pm.*, pc.owner_id, pc.status as partner_status
        FROM partner_meetings pm
        JOIN partner_candidates pc ON pc.id = pm.partner_candidate_id
        WHERE pm.id = :meeting_id AND pc.organization_id = :org_id
    """), {"meeting_id": meeting_id, "org_id": org_id}).fetchone()

    if not meeting or meeting.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    db.execute(text("""
        UPDATE partner_meetings
        SET status = 'completed',
            completed_at = CURRENT_TIMESTAMP,
            outcome = :outcome,
            next_steps = :next_steps,
            key_takeaways = :key_takeaways,
            objections = :objections,
            interest_level = :interest_level,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :meeting_id
    """), {
        "meeting_id": meeting_id,
        "outcome": data.outcome,
        "next_steps": data.next_steps,
        "key_takeaways": data.key_takeaways,
        "objections": data.objections,
        "interest_level": data.interest_level
    })

    # Update partner status to 'met' if appropriate
    if meeting.partner_status == 'meeting_scheduled':
        db.execute(text("""
            UPDATE partner_candidates
            SET status = 'met',
                status_changed_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :partner_id
        """), {"partner_id": meeting.partner_candidate_id})

    log_partner_activity(
        db, meeting.partner_candidate_id, "meeting_completed",
        f"Meeting completed with outcome: {data.outcome}",
        user_id,
        meeting_id=meeting_id,
        metadata={"outcome": data.outcome, "interest_level": data.interest_level}
    )

    db.commit()

    return {
        "id": meeting_id,
        "status": "completed",
        "outcome": data.outcome
    }


@router.delete("/meetings/{meeting_id}")
async def cancel_partner_meeting(
    meeting_id: int,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a meeting."""
    user_id = current_user.id
    org_id = current_user.organization_id

    meeting = db.execute(text("""
        SELECT pm.*, pc.owner_id
        FROM partner_meetings pm
        JOIN partner_candidates pc ON pc.id = pm.partner_candidate_id
        WHERE pm.id = :meeting_id AND pc.organization_id = :org_id
    """), {"meeting_id": meeting_id, "org_id": org_id}).fetchone()

    if not meeting or meeting.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    db.execute(text("""
        UPDATE partner_meetings
        SET status = 'cancelled',
            cancellation_reason = :reason,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :meeting_id
    """), {"meeting_id": meeting_id, "reason": reason})

    log_partner_activity(
        db, meeting.partner_candidate_id, "meeting_cancelled",
        f"Meeting cancelled" + (f": {reason}" if reason else ""),
        user_id,
        meeting_id=meeting_id
    )

    db.commit()

    return {"id": meeting_id, "status": "cancelled"}


# =============================================================================
# PROPOSALS
# =============================================================================

@router.get("/candidates/{partner_id}/proposals")
async def list_partner_proposals(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all proposals for a partner candidate."""
    user_id = current_user.id
    verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    results = db.execute(text("""
        SELECT
            id, proposal_number, proposal_type, status,
            referral_commission_structure, co_marketing_benefits, technology_access,
            sent_at, viewed_at, expires_at, responded_at,
            accepted_at, declined_at, declined_reason,
            created_at
        FROM partner_proposals
        WHERE partner_candidate_id = :partner_id
        ORDER BY created_at DESC
    """), {"partner_id": partner_id}).fetchall()

    return {
        "proposals": [
            {
                "id": r.id,
                "proposal_number": r.proposal_number,
                "proposal_type": r.proposal_type,
                "status": r.status,
                "commission_structure": json.loads(r.referral_commission_structure) if r.referral_commission_structure else None,
                "co_marketing_benefits": json.loads(r.co_marketing_benefits) if r.co_marketing_benefits else [],
                "technology_access": json.loads(r.technology_access) if r.technology_access else [],
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "viewed_at": r.viewed_at.isoformat() if r.viewed_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "responded_at": r.responded_at.isoformat() if r.responded_at else None,
                "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
                "declined_at": r.declined_at.isoformat() if r.declined_at else None,
                "declined_reason": r.declined_reason,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in results
        ]
    }


@router.post("/candidates/{partner_id}/proposals")
async def create_partner_proposal(
    partner_id: int,
    data: PartnerProposalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new proposal for a partner candidate."""
    user_id = current_user.id
    verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    result = db.execute(text("""
        INSERT INTO partner_proposals (
            partner_candidate_id, proposal_type,
            referral_commission_structure, co_marketing_benefits, technology_access,
            exclusive_territory, additional_benefits,
            status, created_by, created_at
        ) VALUES (
            :partner_id, :proposal_type,
            :commission_structure, :co_marketing, :tech_access,
            :exclusive_territory, :additional_benefits,
            'draft', :user_id, CURRENT_TIMESTAMP
        )
        RETURNING id, proposal_number
    """), {
        "partner_id": partner_id,
        "proposal_type": data.proposal_type,
        "commission_structure": json.dumps(data.referral_commission_structure) if data.referral_commission_structure else "{}",
        "co_marketing": json.dumps(data.co_marketing_benefits) if data.co_marketing_benefits else "[]",
        "tech_access": json.dumps(data.technology_access) if data.technology_access else "[]",
        "exclusive_territory": data.exclusive_territory,
        "additional_benefits": data.additional_benefits,
        "user_id": user_id
    })

    row = result.fetchone()

    log_partner_activity(
        db, partner_id, "proposal_created",
        f"Proposal {row.proposal_number} created",
        user_id,
        proposal_id=row.id
    )

    db.commit()

    return {
        "id": row.id,
        "proposal_number": row.proposal_number,
        "status": "draft"
    }


@router.patch("/proposals/{proposal_id}/send")
async def send_partner_proposal(
    proposal_id: int,
    data: PartnerProposalSend,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a proposal to a partner candidate."""
    user_id = current_user.id
    org_id = current_user.organization_id

    proposal = db.execute(text("""
        SELECT pp.*, pc.owner_id, pc.first_name, pc.last_name, pc.email, pc.status as partner_status
        FROM partner_proposals pp
        JOIN partner_candidates pc ON pc.id = pp.partner_candidate_id
        WHERE pp.id = :proposal_id AND pc.organization_id = :org_id
    """), {"proposal_id": proposal_id, "org_id": org_id}).fetchone()

    if not proposal or proposal.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    expires_at = datetime.now() + timedelta(days=data.expires_in_days)

    db.execute(text("""
        UPDATE partner_proposals
        SET status = 'sent',
            sent_at = CURRENT_TIMESTAMP,
            sent_by = :user_id,
            expires_at = :expires_at,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :proposal_id
    """), {"proposal_id": proposal_id, "user_id": user_id, "expires_at": expires_at})

    # Update partner status
    if proposal.partner_status in ['met', 'qualified']:
        db.execute(text("""
            UPDATE partner_candidates
            SET status = 'proposal_sent',
                status_changed_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :partner_id
        """), {"partner_id": proposal.partner_candidate_id})

    log_partner_activity(
        db, proposal.partner_candidate_id, "proposal_sent",
        f"Proposal {proposal.proposal_number} sent to {proposal.first_name} {proposal.last_name}",
        user_id,
        proposal_id=proposal_id
    )

    db.commit()

    return {
        "id": proposal_id,
        "status": "sent",
        "expires_at": expires_at.isoformat()
    }


@router.patch("/proposals/{proposal_id}/respond")
async def record_proposal_response(
    proposal_id: int,
    data: PartnerProposalRespond,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record partner's response to a proposal."""
    user_id = current_user.id
    org_id = current_user.organization_id

    proposal = db.execute(text("""
        SELECT pp.*, pc.owner_id, pc.first_name, pc.last_name
        FROM partner_proposals pp
        JOIN partner_candidates pc ON pc.id = pp.partner_candidate_id
        WHERE pp.id = :proposal_id AND pc.organization_id = :org_id
    """), {"proposal_id": proposal_id, "org_id": org_id}).fetchone()

    if not proposal or proposal.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if data.accepted:
        db.execute(text("""
            UPDATE partner_proposals
            SET status = 'accepted',
                accepted_at = CURRENT_TIMESTAMP,
                responded_at = CURRENT_TIMESTAMP,
                response_notes = :notes,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :proposal_id
        """), {"proposal_id": proposal_id, "notes": data.notes})

        # Update partner status to negotiating (will be onboarded manually)
        db.execute(text("""
            UPDATE partner_candidates
            SET status = 'negotiating',
                status_changed_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :partner_id
        """), {"partner_id": proposal.partner_candidate_id})

        activity_type = "proposal_accepted"
        activity_msg = f"Proposal {proposal.proposal_number} accepted"
    else:
        db.execute(text("""
            UPDATE partner_proposals
            SET status = 'declined',
                declined_at = CURRENT_TIMESTAMP,
                responded_at = CURRENT_TIMESTAMP,
                declined_reason = :notes,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :proposal_id
        """), {"proposal_id": proposal_id, "notes": data.notes})

        activity_type = "proposal_declined"
        activity_msg = f"Proposal {proposal.proposal_number} declined" + (f": {data.notes}" if data.notes else "")

    log_partner_activity(
        db, proposal.partner_candidate_id, activity_type,
        activity_msg,
        user_id,
        proposal_id=proposal_id
    )

    db.commit()

    return {
        "id": proposal_id,
        "status": "accepted" if data.accepted else "declined"
    }


# =============================================================================
# ONBOARDING (Convert to ReferralPartner)
# =============================================================================

@router.post("/candidates/{partner_id}/onboard")
async def onboard_partner(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Onboard a partner candidate - creates a ReferralPartner record and links it.
    This converts a recruited partner into an active referral partner.
    """
    user_id = current_user.id
    org_id = current_user.organization_id
    partner = verify_partner_ownership(partner_id, user_id, db, org_id)

    # Get full partner data
    partner_data = db.execute(text("""
        SELECT * FROM partner_candidates
        WHERE id = :partner_id AND organization_id = :org_id
    """), {"partner_id": partner_id, "org_id": org_id}).fetchone()

    if partner_data.status == 'onboarded':
        raise HTTPException(status_code=400, detail="Partner is already onboarded")

    # Create ReferralPartner record
    rp_result = db.execute(text("""
        INSERT INTO referral_partners (
            name, business_name, contact_name, company, category, type,
            phone, email, license_number,
            street_address, city, state, zip_code,
            title, notes, status, owner_id, created_at
        ) VALUES (
            :name, :business_name, :contact_name, :company, :category, :type,
            :phone, :email, :license_number,
            :street_address, :city, :state, :zip_code,
            :title, :notes, 'active', :owner_id, CURRENT_TIMESTAMP
        )
        RETURNING id
    """), {
        "name": f"{partner_data.first_name} {partner_data.last_name}",
        "business_name": partner_data.business_name or "",
        "contact_name": f"{partner_data.first_name} {partner_data.last_name}",
        "company": partner_data.company_name or partner_data.business_name,
        "category": partner_data.partner_type,
        "type": partner_data.partner_type.replace('_', ' ').title(),
        "phone": partner_data.phone,
        "email": partner_data.email,
        "license_number": partner_data.license_number,
        "street_address": partner_data.street_address,
        "city": partner_data.city,
        "state": partner_data.state,
        "zip_code": partner_data.zip_code,
        "title": partner_data.title,
        "notes": partner_data.notes,
        "owner_id": user_id
    })

    referral_partner_id = rp_result.fetchone().id

    # Update partner_candidate with link and status
    db.execute(text("""
        UPDATE partner_candidates
        SET status = 'onboarded',
            onboarded_at = CURRENT_TIMESTAMP,
            referral_partner_id = :rp_id,
            status_changed_at = CURRENT_TIMESTAMP,
            status_changed_by = :user_id,
            last_activity_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :partner_id
    """), {"partner_id": partner_id, "rp_id": referral_partner_id, "user_id": user_id})

    log_partner_activity(
        db, partner_id, "onboarded",
        f"Partner onboarded and linked to ReferralPartner #{referral_partner_id}",
        user_id,
        metadata={"referral_partner_id": referral_partner_id}
    )

    db.commit()

    return {
        "partner_candidate_id": partner_id,
        "referral_partner_id": referral_partner_id,
        "status": "onboarded",
        "message": f"{partner_data.first_name} {partner_data.last_name} has been onboarded as a referral partner"
    }


# =============================================================================
# NOTES & ACTIVITIES
# =============================================================================

@router.get("/candidates/{partner_id}/notes")
async def list_partner_notes(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List notes for a partner candidate."""
    user_id = current_user.id
    verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    results = db.execute(text("""
        SELECT
            pn.id, pn.note_type, pn.content, pn.is_private, pn.is_pinned,
            pn.created_at, pn.updated_at,
            u.full_name as author_name
        FROM partner_notes pn
        LEFT JOIN users u ON u.id = pn.created_by
        WHERE pn.partner_candidate_id = :partner_id
        ORDER BY pn.is_pinned DESC, pn.created_at DESC
    """), {"partner_id": partner_id}).fetchall()

    return {
        "notes": [
            {
                "id": r.id,
                "note_type": r.note_type,
                "content": r.content,
                "is_private": r.is_private,
                "is_pinned": r.is_pinned,
                "author": r.author_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None
            }
            for r in results
        ]
    }


@router.post("/candidates/{partner_id}/notes")
async def add_partner_note(
    partner_id: int,
    data: PartnerNoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a note to a partner candidate."""
    user_id = current_user.id
    verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    result = db.execute(text("""
        INSERT INTO partner_notes (
            partner_candidate_id, note_type, content, is_private,
            created_by, created_at
        ) VALUES (
            :partner_id, :note_type, :content, :is_private,
            :user_id, CURRENT_TIMESTAMP
        )
        RETURNING id
    """), {
        "partner_id": partner_id,
        "note_type": data.note_type,
        "content": data.content,
        "is_private": data.is_private,
        "user_id": user_id
    })

    note_id = result.fetchone().id

    # Update last activity
    db.execute(text("""
        UPDATE partner_candidates
        SET last_activity_at = CURRENT_TIMESTAMP
        WHERE id = :partner_id
    """), {"partner_id": partner_id})

    log_partner_activity(
        db, partner_id, "note_added",
        f"Note added: {data.content[:50]}..." if len(data.content) > 50 else f"Note added: {data.content}",
        user_id
    )

    db.commit()

    return {"id": note_id, "status": "created"}


@router.get("/candidates/{partner_id}/activities")
async def list_partner_activities(
    partner_id: int,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List activity timeline for a partner candidate."""
    user_id = current_user.id
    verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    results = db.execute(text("""
        SELECT
            pa.id, pa.activity_type, pa.description, pa.metadata,
            pa.meeting_id, pa.proposal_id, pa.is_automated,
            pa.created_at,
            u.full_name as performed_by_name
        FROM partner_activities pa
        LEFT JOIN users u ON u.id = pa.performed_by
        WHERE pa.partner_candidate_id = :partner_id
        ORDER BY pa.created_at DESC
        LIMIT :limit
    """), {"partner_id": partner_id, "limit": limit}).fetchall()

    return {
        "activities": [
            {
                "id": r.id,
                "activity_type": r.activity_type,
                "description": r.description,
                "metadata": json.loads(r.metadata) if r.metadata else {},
                "meeting_id": r.meeting_id,
                "proposal_id": r.proposal_id,
                "is_automated": r.is_automated,
                "performed_by": r.performed_by_name,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in results
        ]
    }


# =============================================================================
# QUICK ACTIONS
# =============================================================================

@router.post("/candidates/{partner_id}/log-call")
async def log_partner_call(
    partner_id: int,
    data: LogCallRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Log a phone call with a partner candidate."""
    user_id = current_user.id
    partner = verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    # Update last activity and status if needed
    update_status = ""
    if partner.status == 'new':
        update_status = ", status = 'contacted', status_changed_at = CURRENT_TIMESTAMP"

    db.execute(text(f"""
        UPDATE partner_candidates
        SET last_activity_at = CURRENT_TIMESTAMP{update_status}
        WHERE id = :partner_id
    """), {"partner_id": partner_id})

    log_partner_activity(
        db, partner_id, "call_made",
        f"Call: {data.outcome}" + (f" - {data.notes}" if data.notes else ""),
        user_id,
        metadata={
            "outcome": data.outcome,
            "duration_seconds": data.duration_seconds,
            "callback_scheduled": data.callback_scheduled.isoformat() if data.callback_scheduled else None
        }
    )

    db.commit()

    return {
        "logged": True,
        "partner_id": partner_id,
        "outcome": data.outcome
    }


@router.post("/candidates/{partner_id}/log-email")
async def log_partner_email(
    partner_id: int,
    subject: str,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Log an email sent to a partner candidate."""
    user_id = current_user.id
    partner = verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    # Update status if new
    if partner.status == 'new':
        db.execute(text("""
            UPDATE partner_candidates
            SET status = 'contacted',
                status_changed_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :partner_id
        """), {"partner_id": partner_id})
    else:
        db.execute(text("""
            UPDATE partner_candidates
            SET last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :partner_id
        """), {"partner_id": partner_id})

    log_partner_activity(
        db, partner_id, "email_sent",
        f"Email sent: {subject}",
        user_id,
        metadata={"subject": subject, "notes": notes}
    )

    db.commit()

    return {"logged": True, "partner_id": partner_id}


# =============================================================================
# ASSESSMENTS
# =============================================================================

@router.get("/candidates/{partner_id}/assessment")
async def get_partner_assessment(
    partner_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get assessment for a partner candidate."""
    user_id = current_user.id
    verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    result = db.execute(text("""
        SELECT * FROM partner_assessments WHERE partner_candidate_id = :partner_id
    """), {"partner_id": partner_id}).fetchone()

    if not result:
        return {"assessment": None}

    return {
        "assessment": {
            "id": result.id,
            "production_score": float(result.production_score) if result.production_score else None,
            "referral_potential_score": float(result.referral_potential_score) if result.referral_potential_score else None,
            "relationship_score": float(result.relationship_score) if result.relationship_score else None,
            "professionalism_score": float(result.professionalism_score) if result.professionalism_score else None,
            "market_presence_score": float(result.market_presence_score) if result.market_presence_score else None,
            "communication_score": float(result.communication_score) if result.communication_score else None,
            "technical_skills_score": float(result.technical_skills_score) if getattr(result, 'technical_skills_score', None) else None,
            "experience_score": float(result.experience_score) if getattr(result, 'experience_score', None) else None,
            "overall_score": float(result.overall_score) if result.overall_score else None,
            "overall_grade": result.overall_grade,
            "strengths": json.loads(result.strengths) if result.strengths else [],
            "concerns": json.loads(result.concerns) if result.concerns else [],
            "talking_points": json.loads(result.talking_points) if result.talking_points else [],
            "recommended_approach": result.recommended_approach,
            "assessed_at": result.assessed_at.isoformat() if result.assessed_at else None
        }
    }


@router.post("/candidates/{partner_id}/assessment")
async def update_partner_assessment(
    partner_id: int,
    data: PartnerAssessmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update assessment for a partner/employee candidate."""
    user_id = current_user.id
    candidate = verify_partner_ownership(partner_id, user_id, db, current_user.organization_id)

    # Determine scoring weights based on candidate category
    category = getattr(candidate, 'candidate_category', 'partner') or 'partner'

    if category == 'employee':
        weights = {
            "technical_skills_score": 0.25,
            "experience_score": 0.25,
            "production_score": 0.20,
            "professionalism_score": 0.15,
            "communication_score": 0.10,
            "relationship_score": 0.05,
        }
    else:
        weights = {
            "production_score": 0.20,
            "referral_potential_score": 0.25,
            "relationship_score": 0.20,
            "professionalism_score": 0.15,
            "market_presence_score": 0.10,
            "communication_score": 0.10,
        }

    # Calculate overall score from provided scores
    scores = []
    for field, weight in weights.items():
        value = getattr(data, field, None)
        if value is not None:
            scores.append((value, weight))

    overall_score = None
    overall_grade = None
    if scores:
        total_weight = sum(w for _, w in scores)
        overall_score = sum(s * w for s, w in scores) / total_weight if total_weight > 0 else None
        if overall_score:
            overall_grade = calculate_overall_grade(overall_score)

    # Upsert assessment (includes both partner and employee dimension columns)
    db.execute(text("""
        INSERT INTO partner_assessments (
            partner_candidate_id,
            production_score, referral_potential_score, relationship_score,
            professionalism_score, market_presence_score, communication_score,
            technical_skills_score, experience_score,
            overall_score, overall_grade,
            strengths, concerns, talking_points, recommended_approach,
            assessed_by, assessed_at, created_at, updated_at
        ) VALUES (
            :partner_id,
            :production_score, :referral_potential_score, :relationship_score,
            :professionalism_score, :market_presence_score, :communication_score,
            :technical_skills_score, :experience_score,
            :overall_score, :overall_grade,
            :strengths, :concerns, :talking_points, :recommended_approach,
            :user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (partner_candidate_id) DO UPDATE SET
            production_score = COALESCE(:production_score, partner_assessments.production_score),
            referral_potential_score = COALESCE(:referral_potential_score, partner_assessments.referral_potential_score),
            relationship_score = COALESCE(:relationship_score, partner_assessments.relationship_score),
            professionalism_score = COALESCE(:professionalism_score, partner_assessments.professionalism_score),
            market_presence_score = COALESCE(:market_presence_score, partner_assessments.market_presence_score),
            communication_score = COALESCE(:communication_score, partner_assessments.communication_score),
            technical_skills_score = COALESCE(:technical_skills_score, partner_assessments.technical_skills_score),
            experience_score = COALESCE(:experience_score, partner_assessments.experience_score),
            overall_score = :overall_score,
            overall_grade = :overall_grade,
            strengths = COALESCE(:strengths, partner_assessments.strengths),
            concerns = COALESCE(:concerns, partner_assessments.concerns),
            talking_points = COALESCE(:talking_points, partner_assessments.talking_points),
            recommended_approach = COALESCE(:recommended_approach, partner_assessments.recommended_approach),
            assessed_by = :user_id,
            assessed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "partner_id": partner_id,
        "production_score": data.production_score,
        "referral_potential_score": data.referral_potential_score,
        "relationship_score": data.relationship_score,
        "professionalism_score": data.professionalism_score,
        "market_presence_score": data.market_presence_score,
        "communication_score": data.communication_score,
        "technical_skills_score": data.technical_skills_score,
        "experience_score": data.experience_score,
        "overall_score": overall_score,
        "overall_grade": overall_grade,
        "strengths": json.dumps(data.strengths) if data.strengths else None,
        "concerns": json.dumps(data.concerns) if data.concerns else None,
        "talking_points": json.dumps(data.talking_points) if data.talking_points else None,
        "recommended_approach": data.recommended_approach,
        "user_id": user_id
    })

    # Update overall score on partner record too
    if overall_score:
        db.execute(text("""
            UPDATE partner_candidates
            SET overall_score = :overall_score,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE id = :partner_id
        """), {"partner_id": partner_id, "overall_score": overall_score})

    log_partner_activity(
        db, partner_id, "assessment_updated",
        f"Assessment updated - Overall: {overall_grade} ({round(overall_score, 1) if overall_score else 'N/A'})",
        user_id
    )

    db.commit()

    return {
        "partner_id": partner_id,
        "overall_score": round(overall_score, 1) if overall_score else None,
        "overall_grade": overall_grade
    }


# =============================================================================
# Migration/admin endpoints removed — use backend/migrations/ scripts instead.
# =============================================================================
