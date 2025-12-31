"""
Recruit Portal Routes
Public-facing API endpoints for candidates to view their application status.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from database import get_db
import secrets
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recruit-portal", tags=["recruit-portal"])


# =============================================================================
# GENERATE ACCESS TOKEN
# =============================================================================

@router.post("/generate-token/{candidate_id}")
async def generate_portal_token(
    candidate_id: int,
    db: Session = Depends(get_db)
):
    """Generate a portal access token for a candidate (internal use)."""
    # Generate a secure token
    token = secrets.token_urlsafe(32)

    # Store the token
    result = db.execute(text("""
        UPDATE mm_candidates
        SET portal_token = :token,
            portal_token_created_at = CURRENT_TIMESTAMP
        WHERE id = :id
        RETURNING id, first_name, last_name, email
    """), {"id": candidate_id, "token": token}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Candidate not found")

    db.commit()

    return {
        "token": token,
        "portal_url": f"/recruit-portal/{token}",
        "candidate": {
            "id": result.id,
            "name": f"{result.first_name} {result.last_name}",
            "email": result.email
        }
    }


# =============================================================================
# PUBLIC PORTAL ACCESS
# =============================================================================

@router.get("/{token}")
async def get_candidate_portal(
    token: str,
    db: Session = Depends(get_db)
):
    """Get candidate portal data using access token."""
    # Look up candidate by token
    result = db.execute(text("""
        SELECT
            c.id, c.first_name, c.last_name, c.email, c.phone,
            c.source, c.target_role_name, c.status, c.applied_at,
            c.years_experience, c.years_mortgage_experience, c.has_mortgage_experience,
            c.linkedin_url, c.resume_url,
            c.overall_score, c.vetting_score, c.behavioral_score, c.technical_score,
            c.culture_fit_score, c.placement_recommendation, c.talent_profile,
            -- Production fields
            c.annual_volume, c.annual_units, c.avg_loan_size, c.nmls_id,
            c.license_states, c.production_history, c.current_company, c.current_title,
            -- Social media fields
            c.facebook_url, c.instagram_url, c.twitter_url,
            c.linkedin_url as linkedin,
            -- Profile fields
            c.headshot_url, c.bio,
            c.created_at, c.updated_at
        FROM mm_candidates c
        WHERE c.portal_token = :token AND c.is_active = true
    """), {"token": token}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Invalid or expired portal token")

    # Get interviews (handle missing columns gracefully)
    try:
        interviews = db.execute(text("""
            SELECT id, interview_type as type, interview_round, scheduled_at,
                   status, notes as interviewer_names
            FROM mm_interviews
            WHERE candidate_id = :id
            ORDER BY scheduled_at DESC
        """), {"id": result.id}).fetchall()
    except Exception as e:
        logger.warning(f"Error fetching interviews: {e}")
        interviews = []

    # Get activities (public-safe ones only)
    activities = db.execute(text("""
        SELECT id, activity_type as type, description, created_at as timestamp
        FROM mm_candidate_activities
        WHERE candidate_id = :id
          AND activity_type NOT IN ('internal_note', 'private_comment')
        ORDER BY created_at DESC
        LIMIT 20
    """), {"id": result.id}).fetchall()

    # Determine next steps based on status
    next_steps = get_next_steps(result.status)

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

        "production": {
            "annual_volume": float(result.annual_volume) if result.annual_volume else None,
            "annual_units": result.annual_units,
            "nmls_id": result.nmls_id,
            "current_company": result.current_company,
            "current_title": result.current_title,
        },

        "social_media": {
            "linkedin": result.linkedin,
            "facebook": result.facebook_url,
            "instagram": result.instagram_url,
            "twitter": result.twitter_url,
        },

        "headshot_url": result.headshot_url,

        "interviews": [
            {
                "id": i.id,
                "type": i.type,
                "round": i.interview_round,
                "scheduled_at": i.scheduled_at.isoformat() if i.scheduled_at else None,
                "status": i.status,
                "meeting_url": None,  # Will be added when video integration is complete
            }
            for i in interviews
        ],

        "activities": [
            {
                "id": a.id,
                "type": a.type,
                "description": a.description,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
            }
            for a in activities
        ],

        "next_steps": next_steps,
        "documents": [],  # Future: document requests
    }


def get_next_steps(status: str) -> list:
    """Get next steps based on candidate status."""
    steps_by_status = {
        "new": [
            {"title": "Application Under Review", "description": "Our team is reviewing your application. We'll be in touch soon."}
        ],
        "screening": [
            {"title": "Initial Screening", "description": "A recruiter will reach out to schedule an initial call."}
        ],
        "phone_screen": [
            {"title": "Phone Screen Scheduled", "description": "Prepare for your phone screen discussion."},
            {"title": "Research the Company", "description": "Learn about our mission and values."}
        ],
        "interview": [
            {"title": "Interview Preparation", "description": "Review the position requirements and prepare questions."},
            {"title": "Technical Preparation", "description": "Be ready to discuss your experience in detail."}
        ],
        "assessment": [
            {"title": "Complete Assessment", "description": "Finish any pending assessments or tasks."}
        ],
        "offer": [
            {"title": "Review Offer", "description": "Take time to review the offer details."},
            {"title": "Ask Questions", "description": "Reach out if you have any questions about the offer."}
        ],
        "hired": [
            {"title": "Welcome Aboard!", "description": "We're excited to have you join the team."},
            {"title": "Onboarding", "description": "HR will send you onboarding materials soon."}
        ],
    }
    return steps_by_status.get(status, [])


# =============================================================================
# PORTAL ACTIONS
# =============================================================================

class InterestRequest(BaseModel):
    job_id: int


@router.post("/{token}/express-interest")
async def express_interest(
    token: str,
    request: InterestRequest,
    db: Session = Depends(get_db)
):
    """Allow candidate to express interest in another position."""
    # Verify token
    result = db.execute(text("""
        SELECT id FROM mm_candidates WHERE portal_token = :token
    """), {"token": token}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Invalid token")

    # Log the interest
    db.execute(text("""
        INSERT INTO mm_candidate_activities (candidate_id, activity_type, description, created_at)
        VALUES (:cid, 'expressed_interest', :desc, CURRENT_TIMESTAMP)
    """), {
        "cid": result.id,
        "desc": f"Expressed interest in job posting #{request.job_id} via portal"
    })

    db.commit()

    return {"success": True, "message": "Interest recorded"}


@router.post("/{token}/update-contact")
async def update_contact_info(
    token: str,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Allow candidate to update their contact information."""
    # Verify token
    result = db.execute(text("""
        SELECT id FROM mm_candidates WHERE portal_token = :token
    """), {"token": token}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Invalid token")

    updates = []
    params = {"id": result.id}

    if phone:
        updates.append("phone = :phone")
        params["phone"] = phone
    if email:
        updates.append("email = :email")
        params["email"] = email

    if updates:
        db.execute(text(f"""
            UPDATE mm_candidates
            SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), params)

        # Log the update
        db.execute(text("""
            INSERT INTO mm_candidate_activities (candidate_id, activity_type, description, created_at)
            VALUES (:cid, 'contact_updated', 'Updated contact information via portal', CURRENT_TIMESTAMP)
        """), {"cid": result.id})

        db.commit()

    return {"success": True, "message": "Contact information updated"}


# =============================================================================
# ADMIN: ADD PORTAL TOKEN COLUMN
# =============================================================================

@router.post("/admin/add-portal-columns")
async def add_portal_columns(
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Add portal token columns to mm_candidates table."""
    if admin_key != "perennia-admin-2024":
        raise HTTPException(status_code=403, detail="Invalid admin key")

    columns = [
        ("portal_token", "VARCHAR(100)", "Unique access token for candidate portal"),
        ("portal_token_created_at", "TIMESTAMP", "When the portal token was created"),
    ]

    added = []
    skipped = []

    for col_name, col_type, description in columns:
        try:
            db.execute(text(f"""
                ALTER TABLE mm_candidates
                ADD COLUMN IF NOT EXISTS {col_name} {col_type}
            """))
            added.append(col_name)
            logger.info(f"Added column: {col_name} ({description})")
        except Exception as e:
            if "already exists" in str(e).lower():
                skipped.append(col_name)
            else:
                logger.warning(f"Error adding {col_name}: {e}")

    # Add index on portal_token
    try:
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_mm_candidates_portal_token
            ON mm_candidates(portal_token)
        """))
    except Exception as e:
        logger.warning(f"Error creating index: {e}")

    db.commit()

    return {
        "success": True,
        "added": added,
        "skipped": skipped
    }
