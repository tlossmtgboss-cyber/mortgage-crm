"""
Recruit Portal Routes
Public-facing API endpoints for candidates to view their application status.
Includes:
- Portal access and token management
- AI chat interaction
- Production impact calculator
- Company updates/propaganda
- Appointment scheduling
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from database import get_db
import secrets
import logging
import os
import time
import threading
from collections import defaultdict

from auth.dependencies import get_current_user
from database.models import User
from services.recruit_portal_service import RecruitPortalService
from sqlalchemy.exc import SQLAlchemyError
from models.recruit_portal_models import (
    ChatRequest, ChatResponse, AppointmentCreate, Appointment,
    CalculatorInput, CalculatorResult, PortalData, CompanyUpdate
)

logger = logging.getLogger(__name__)

_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

# Portal token TTL — tokens older than this are rejected
PORTAL_TOKEN_TTL_DAYS = int(os.getenv("PORTAL_TOKEN_TTL_DAYS", "90"))

# ── Rate limiter for public portal endpoints ────────────────────────────
# Keyed by client IP.  Separate limits for general vs AI chat endpoints.
_rate_store: dict = defaultdict(list)
_rate_lock = threading.Lock()
_RATE_WINDOW = 60          # seconds
_RATE_MAX_GENERAL = 30     # requests per window for general endpoints
_RATE_MAX_CHAT = 5         # requests per window for AI chat (expensive)
_RATE_MAX_KEYS = 10_000    # max tracked IPs before forced cleanup


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str, bucket: str, max_requests: int) -> bool:
    """Return True if the request is allowed, False if rate-limited."""
    now = time.time()
    key = f"portal:{bucket}:{ip}"
    with _rate_lock:
        _rate_store[key] = [t for t in _rate_store[key] if now - t < _RATE_WINDOW]
        # Periodic cleanup
        if len(_rate_store) > _RATE_MAX_KEYS:
            stale = [k for k, v in _rate_store.items() if not v or now - v[-1] > _RATE_WINDOW]
            for k in stale:
                del _rate_store[k]
        if len(_rate_store[key]) >= max_requests:
            return False
        _rate_store[key].append(now)
    return True


def _enforce_rate_limit(request: Request, bucket: str = "general", max_requests: int = _RATE_MAX_GENERAL):
    ip = _get_client_ip(request)
    if not _check_rate_limit(ip, bucket, max_requests):
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")


router = APIRouter(prefix="/api/v1/recruit-portal", tags=["recruit-portal"])
portal_service = RecruitPortalService()


# ── Helper: validate portal token with expiration ───────────────────────

def _validate_portal_token(db: Session, token: str, *, require_active: bool = True):
    """Look up candidate by portal token, enforcing TTL.

    Returns the candidate row or raises 404.
    """
    row = db.execute(text("""
        SELECT id, first_name, last_name, email, phone, status,
               portal_token_created_at
        FROM mm_candidates
        WHERE portal_token = :token
          AND is_active = true
    """), {"token": token}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Invalid or expired portal token")

    # Enforce token TTL
    if row.portal_token_created_at:
        created = row.portal_token_created_at
        # Handle naive datetimes from PostgreSQL TIMESTAMP WITHOUT TIME ZONE
        if created.tzinfo is None:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=PORTAL_TOKEN_TTL_DAYS)
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=PORTAL_TOKEN_TTL_DAYS)
        if created < cutoff:
            raise HTTPException(status_code=410, detail="Portal token has expired. Please contact your recruiter for a new link.")

    return row


# =============================================================================
# GENERATE ACCESS TOKEN
# =============================================================================

@router.post("/generate-token/{candidate_id}")
async def generate_portal_token(
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a portal access token for a candidate (requires auth)."""
    # Generate a secure token
    token = secrets.token_urlsafe(32)

    # Store the token — scoped to the caller's organization
    result = db.execute(text("""
        UPDATE mm_candidates
        SET portal_token = :token,
            portal_token_created_at = CURRENT_TIMESTAMP
        WHERE id = :id AND organization_id = :org_id
        RETURNING id, first_name, last_name, email
    """), {"id": candidate_id, "token": token, "org_id": current_user.organization_id}).fetchone()

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
    request: Request,
    db: Session = Depends(get_db)
):
    """Get candidate portal data using access token."""
    _enforce_rate_limit(request)

    # Validate token with TTL enforcement
    validated = _validate_portal_token(db, token)

    # Fetch full profile using validated candidate id
    result = db.execute(text("""
        SELECT
            c.id, c.first_name, c.last_name, c.email, c.phone,
            c.source, c.target_role_name, c.status, c.applied_at,
            c.years_experience, c.years_mortgage_experience, c.has_mortgage_experience,
            c.linkedin_url, c.resume_url,
            c.overall_score, c.vetting_score, c.behavioral_score, c.technical_score,
            c.culture_fit_score, c.placement_recommendation, c.talent_profile,
            c.created_at, c.updated_at
        FROM mm_candidates c
        WHERE c.id = :id AND c.is_active = true
    """), {"id": validated.id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Invalid or expired portal token")

    # Try to get extended profile data (columns may not exist in all deployments)
    extended_data = {"production": {}, "social": {}, "headshot_url": None}
    try:
        ext = db.execute(text("""
            SELECT annual_volume, annual_units, avg_loan_size, nmls_id,
                   current_company, current_title,
                   facebook_url, instagram_url, twitter_url,
                   headshot_url, bio
            FROM mm_candidates WHERE id = :id
        """), {"id": result.id}).fetchone()
        if ext:
            extended_data["production"] = {
                "annual_volume": float(ext.annual_volume) if ext.annual_volume else None,
                "annual_units": ext.annual_units,
                "nmls_id": ext.nmls_id,
                "current_company": ext.current_company,
                "current_title": ext.current_title,
            }
            extended_data["social"] = {
                "facebook": ext.facebook_url,
                "instagram": ext.instagram_url,
                "twitter": ext.twitter_url,
            }
            extended_data["headshot_url"] = ext.headshot_url
    except Exception as e:
        logger.warning(f"Extended profile columns not available: {e}")

    # Get interviews (handle missing columns gracefully)
    try:
        interviews = db.execute(text("""
            SELECT id, interview_type as type, interview_round, scheduled_at,
                   status, notes as interviewer_names
            FROM mm_interviews
            WHERE candidate_id = :id
            ORDER BY scheduled_at DESC
        """), {"id": result.id}).fetchall()
    except SQLAlchemyError as e:
        logger.warning(f"Error fetching interviews: {e}")
        interviews = []

    # Get activities (public-safe ones only)
    try:
        activities = db.execute(text("""
            SELECT id, activity_type as type, description, created_at as timestamp
            FROM mm_candidate_activities
            WHERE candidate_id = :id
              AND activity_type NOT IN ('internal_note', 'private_comment')
            ORDER BY created_at DESC
            LIMIT 20
        """), {"id": result.id}).fetchall()
    except SQLAlchemyError as e:
        logger.warning(f"Error fetching activities: {e}")
        activities = []

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

        "production": extended_data["production"],

        "social_media": {
            "linkedin": result.linkedin_url,
            **extended_data["social"],
        },

        "headshot_url": extended_data["headshot_url"],

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
    interest: InterestRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Allow candidate to express interest in another position."""
    _enforce_rate_limit(request)
    result = _validate_portal_token(db, token)

    # Log the interest
    db.execute(text("""
        INSERT INTO mm_candidate_activities (candidate_id, activity_type, description, created_at)
        VALUES (:cid, 'expressed_interest', :desc, CURRENT_TIMESTAMP)
    """), {
        "cid": result.id,
        "desc": f"Expressed interest in job posting #{interest.job_id} via portal"
    })

    db.commit()

    return {"success": True, "message": "Interest recorded"}


@router.post("/{token}/update-contact")
async def update_contact_info(
    token: str,
    request: Request,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Allow candidate to update their contact information."""
    _enforce_rate_limit(request)
    result = _validate_portal_token(db, token)

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
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
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
        except SQLAlchemyError as e:
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
    except SQLAlchemyError as e:
        logger.warning(f"Error creating index: {e}")

    db.commit()

    return {
        "success": True,
        "added": added,
        "skipped": skipped
    }


@router.post("/admin/create-portal-tables")
async def create_portal_tables(
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Create PURL portal tables."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS recruit_portal_workspaces (
                id SERIAL PRIMARY KEY,
                candidate_id INTEGER NOT NULL UNIQUE,
                slug VARCHAR(100) UNIQUE NOT NULL,
                is_active BOOLEAN DEFAULT true,
                theme_config JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_portal_workspaces_slug
                ON recruit_portal_workspaces(slug) WHERE is_active = true;

            CREATE TABLE IF NOT EXISTS recruit_portal_tokens (
                id SERIAL PRIMARY KEY,
                workspace_id INTEGER NOT NULL,
                token VARCHAR(100) UNIQUE NOT NULL,
                scope VARCHAR(20) DEFAULT 'full',
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_portal_tokens_token
                ON recruit_portal_tokens(token);

            CREATE TABLE IF NOT EXISTS recruit_company_updates (
                id SERIAL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                media_url TEXT,
                category VARCHAR(50) DEFAULT 'news',
                is_featured BOOLEAN DEFAULT false,
                is_active BOOLEAN DEFAULT true,
                published_at TIMESTAMP DEFAULT NOW(),
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_company_updates_category
                ON recruit_company_updates(category, is_active) WHERE is_active = true;

            CREATE TABLE IF NOT EXISTS recruit_portal_messages (
                id SERIAL PRIMARY KEY,
                workspace_id INTEGER NOT NULL,
                role VARCHAR(20) NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_portal_messages_workspace
                ON recruit_portal_messages(workspace_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS recruit_portal_appointments (
                id SERIAL PRIMARY KEY,
                workspace_id INTEGER NOT NULL,
                appointment_type VARCHAR(50) NOT NULL,
                scheduled_at TIMESTAMP NOT NULL,
                duration_minutes INTEGER DEFAULT 30,
                notes TEXT,
                status VARCHAR(20) DEFAULT 'scheduled',
                recruiter_id INTEGER,
                calendar_event_id VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_portal_appointments_workspace
                ON recruit_portal_appointments(workspace_id);

            -- Production calculator configuration
            CREATE TABLE IF NOT EXISTS recruit_calculator_config (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                lead_conversion_lift DECIMAL(4,2) DEFAULT 1.25,
                avg_deal_size_lift DECIMAL(4,2) DEFAULT 1.15,
                closing_speed_factor DECIMAL(4,2) DEFAULT 0.85,
                tech_efficiency_gain DECIMAL(4,2) DEFAULT 1.20,
                marketing_lead_boost DECIMAL(4,2) DEFAULT 1.30,
                comp_percentage DECIMAL(5,4) DEFAULT 0.0125,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );

            -- Insert default calculator config if not exists
            INSERT INTO recruit_calculator_config (organization_id)
            SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM recruit_calculator_config WHERE organization_id = 1);

            -- Seed sample company updates
            INSERT INTO recruit_company_updates (title, content, category, is_featured)
            SELECT 'Welcome to Perennia!',
                   'We are excited you are considering joining our team. At Perennia, we provide loan officers with cutting-edge technology, superior leads, and unmatched support to help you close more loans.',
                   'welcome', true
            WHERE NOT EXISTS (SELECT 1 FROM recruit_company_updates WHERE category = 'welcome' LIMIT 1);
        """))
        db.commit()

        return {"status": "success", "message": "Portal tables created successfully"}
    except SQLAlchemyError as e:
        logger.error(f"Error creating portal tables: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ENHANCED PORTAL FEATURES - PURL Portal v2
# =============================================================================

@router.get("/purl/{slug}")
async def get_purl_portal_data(
    slug: str,
    request: Request,
    token: Optional[str] = Query(None, description="Portal access token"),
    db: Session = Depends(get_db)
):
    """Get PURL portal data for candidate including calculator config and company info."""
    _enforce_rate_limit(request)
    try:
        portal_data = portal_service.get_portal_by_slug(slug, token)
        if not portal_data:
            raise HTTPException(status_code=404, detail="Portal not found")
        return portal_data
    except Exception as e:
        logger.error(f"Error getting portal data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/purl/{slug}/updates")
async def get_purl_company_updates(
    slug: str,
    request: Request,
    category: Optional[str] = None,
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db)
):
    """Get company updates/propaganda for the PURL portal."""
    _enforce_rate_limit(request)
    try:
        updates = portal_service.get_company_updates(category=category, limit=limit)
        return {"updates": updates}
    except Exception as e:
        logger.error(f"Error getting company updates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/purl/{slug}/chat", response_model=ChatResponse)
async def purl_chat_with_assistant(
    slug: str,
    chat_request: ChatRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """AI chat interaction for candidate questions on PURL portal."""
    _enforce_rate_limit(request, "chat", _RATE_MAX_CHAT)
    try:
        portal_data = portal_service.get_portal_by_slug(slug)
        if not portal_data:
            raise HTTPException(status_code=404, detail="Portal not found")

        result = portal_service.chat_with_assistant(
            workspace_id=portal_data.workspace_id,
            message=chat_request.message,
            context=chat_request.context
        )
        return ChatResponse(response=result.get("response", ""), metadata={"timestamp": datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/purl/{slug}/availability")
async def get_purl_availability(
    slug: str,
    request: Request,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    duration_minutes: int = Query(30, description="Meeting duration"),
    db: Session = Depends(get_db)
):
    """Get available time slots for scheduling on PURL portal."""
    _enforce_rate_limit(request)
    try:
        portal_data = portal_service.get_portal_by_slug(slug)
        if not portal_data:
            raise HTTPException(status_code=404, detail="Portal not found")

        slots = portal_service.get_availability(
            workspace_id=portal_data.workspace_id,
            date=date
        )
        return {"date": date, "duration_minutes": duration_minutes, "slots": slots}
    except Exception as e:
        logger.error(f"Error getting availability: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/purl/{slug}/schedule")
async def schedule_purl_appointment(
    slug: str,
    appointment: AppointmentCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Book an appointment through the PURL portal."""
    _enforce_rate_limit(request)
    try:
        portal_data = portal_service.get_portal_by_slug(slug)
        if not portal_data:
            raise HTTPException(status_code=404, detail="Portal not found")

        # Convert datetime to ISO string for the service
        scheduled_at_str = appointment.scheduled_at.isoformat() if hasattr(appointment.scheduled_at, 'isoformat') else str(appointment.scheduled_at)

        created = portal_service.schedule_appointment(
            workspace_id=portal_data.workspace_id,
            scheduled_at=scheduled_at_str,
            appointment_type=appointment.appointment_type,
            notes=appointment.notes
        )
        return created
    except Exception as e:
        logger.error(f"Error scheduling appointment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/purl/{slug}/calculator", response_model=CalculatorResult)
async def calculate_purl_production_impact(
    slug: str,
    input_data: CalculatorInput,
    request: Request,
    db: Session = Depends(get_db)
):
    """Calculate production impact if candidate joins the company."""
    _enforce_rate_limit(request)
    try:
        result = portal_service.calculate_production_impact(input_data)
        return result
    except Exception as e:
        logger.error(f"Error calculating production impact: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/purl/{slug}/chat-history")
async def get_purl_chat_history(
    slug: str,
    request: Request,
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db)
):
    """Get chat message history for the PURL portal."""
    _enforce_rate_limit(request)
    try:
        portal_data = portal_service.get_portal_by_slug(slug)
        if not portal_data:
            raise HTTPException(status_code=404, detail="Portal not found")

        messages = portal_service.get_chat_history(
            workspace_id=portal_data.workspace_id,
            limit=limit
        )
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ADMIN PORTAL MANAGEMENT
# =============================================================================

@router.post("/admin/workspaces")
async def create_purl_portal_workspace(
    candidate_id: int,
    slug: Optional[str] = None,
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Create a PURL portal workspace for a candidate (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        workspace = portal_service.create_portal_workspace(
            candidate_id=candidate_id,
            slug=slug
        )
        return workspace
    except Exception as e:
        logger.error(f"Error creating workspace: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/admin/workspaces/by-candidate/{candidate_id}/slug")
async def update_workspace_slug_by_candidate(
    candidate_id: int,
    new_slug: str = Query(..., description="New slug for the workspace"),
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Update workspace slug by candidate ID (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        result = db.execute(
            text("""
                UPDATE recruit_portal_workspaces
                SET slug = :new_slug
                WHERE candidate_id = :candidate_id
                RETURNING id, slug, candidate_id
            """),
            {"candidate_id": candidate_id, "new_slug": new_slug}
        )
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Workspace not found for this candidate")

        return {"id": row.id, "slug": row.slug, "candidate_id": row.candidate_id}
    except SQLAlchemyError as e:
        logger.error(f"Error updating workspace slug: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/workspaces/by-candidate/{candidate_id}")
async def get_workspace_by_candidate(
    candidate_id: int,
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Get workspace info by candidate ID (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        result = db.execute(
            text("""
                SELECT id, slug, candidate_id, is_active, created_at
                FROM recruit_portal_workspaces
                WHERE candidate_id = :candidate_id
            """),
            {"candidate_id": candidate_id}
        )
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Workspace not found for this candidate")

        return {
            "id": row.id,
            "slug": row.slug,
            "candidate_id": row.candidate_id,
            "is_active": row.is_active,
            "created_at": str(row.created_at)
        }
    except Exception as e:
        logger.error(f"Error getting workspace: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/workspaces")
async def list_purl_portal_workspaces(
    admin_key: str = Query(...),
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List all PURL portal workspaces (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        workspaces = portal_service.list_workspaces(limit=limit, offset=offset)
        return {"workspaces": workspaces, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Error listing workspaces: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/admin/candidates/{candidate_id}/email")
async def update_candidate_email(
    candidate_id: int,
    email: str = Query(..., description="New email address"),
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Update candidate email address (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        result = db.execute(
            text("""
                UPDATE mm_candidates
                SET email = :email
                WHERE id = :candidate_id
                RETURNING id, first_name, last_name, email
            """),
            {"candidate_id": candidate_id, "email": email}
        )
        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(status_code=404, detail="Candidate not found")

        return {"id": row.id, "name": f"{row.first_name} {row.last_name}", "email": row.email}
    except SQLAlchemyError as e:
        logger.error(f"Error updating candidate email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/workspaces/{workspace_id}/tokens")
async def create_purl_portal_token(
    workspace_id: int,
    scope: str = "full",
    expires_days: Optional[int] = None,
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Create an access token for a PURL portal workspace."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        token = portal_service.create_portal_token(
            workspace_id=workspace_id,
            scope=scope,
            expires_days=expires_days
        )
        return token
    except Exception as e:
        logger.error(f"Error creating token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class CompanyUpdateCreate(BaseModel):
    title: str
    content: str
    media_url: Optional[str] = None
    category: str = "news"
    is_featured: bool = False


@router.post("/admin/updates")
async def create_purl_company_update(
    update: CompanyUpdateCreate,
    admin_key: str = Query(...),
    created_by: int = 1,
    db: Session = Depends(get_db)
):
    """Create a company update/propaganda post (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        created = portal_service.create_company_update(
            title=update.title,
            content=update.content,
            media_url=update.media_url,
            category=update.category,
            is_featured=update.is_featured,
            created_by=created_by
        )
        return created
    except Exception as e:
        logger.error(f"Error creating update: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/updates")
async def list_purl_company_updates(
    admin_key: str = Query(...),
    category: Optional[str] = None,
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db)
):
    """List company updates (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        updates = portal_service.get_company_updates(category=category, limit=limit)
        return {"updates": updates}
    except Exception as e:
        logger.error(f"Error listing updates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/admin/updates/{update_id}")
async def delete_purl_company_update(
    update_id: int,
    admin_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """Delete a company update (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        portal_service.delete_company_update(update_id)
        return {"status": "deleted", "id": update_id}
    except SQLAlchemyError as e:
        logger.error(f"Error deleting update: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class CalculatorConfigUpdate(BaseModel):
    lead_conversion_lift: Optional[float] = None
    avg_deal_size_lift: Optional[float] = None
    closing_speed_factor: Optional[float] = None
    tech_efficiency_gain: Optional[float] = None
    marketing_lead_boost: Optional[float] = None
    comp_percentage: Optional[float] = None


@router.put("/admin/calculator-config")
async def update_purl_calculator_config(
    config: CalculatorConfigUpdate,
    admin_key: str = Query(...),
    organization_id: int = 1,
    db: Session = Depends(get_db)
):
    """Update production calculator configuration (admin)."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        updated = portal_service.update_calculator_config(
            organization_id=organization_id,
            **config.dict(exclude_unset=True)
        )
        return updated
    except Exception as e:
        logger.error(f"Error updating calculator config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/admin/calculator-config")
async def get_purl_calculator_config(
    admin_key: str = Query(...),
    organization_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get production calculator configuration."""
    if admin_key != _ADMIN_API_KEY or not _ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        config = portal_service.get_calculator_config(organization_id)
        return config
    except Exception as e:
        logger.error(f"Error getting calculator config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
