"""
Beta Application API Routes
Perennia AI - IBMA

Handles beta program applications, tracking, and user onboarding
for the Perennia AI UVIP beta program.
"""

import enum
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, Integer, String, Text, DateTime, func, text, select
from sqlalchemy.orm import Session

from database import get_db, Base, engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/beta", tags=["Beta Program"])


# ================================================================
# ADMIN AUTHENTICATION
# ================================================================

# Lazy-loaded get_current_user dependency
_get_current_user = None

def _get_auth_dependency():
    """Get the authentication dependency from main module."""
    global _get_current_user
    if _get_current_user is None:
        import main
        _get_current_user = main.get_current_user
    return _get_current_user


async def require_admin_user(request, db: AsyncSession = Depends(get_async_db)):
    """
    Dependency that requires admin authentication.
    Use this for admin-only endpoints.
    """
    from fastapi.security import OAuth2PasswordBearer
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

    # Get token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header.replace("Bearer ", "")

    # Get current user via main's authentication
    import main
    try:
        user = await main.get_current_user(token=token, db=db)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Check if user is admin
    is_admin = (
        getattr(user, 'permission_role', None) == 'admin' or
        getattr(user, 'role', None) == 'admin'
    )
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin access required for this endpoint"
        )

    return user


# ================================================================
# DATABASE INITIALIZATION
# ================================================================

def ensure_beta_tables_exist():
    """Create beta tables if they don't exist."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS beta_applications (
                    id SERIAL PRIMARY KEY,
                    company_name VARCHAR(255) NOT NULL,
                    contact_name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    phone VARCHAR(50),
                    team_size VARCHAR(50),
                    current_crm VARCHAR(255),
                    monthly_loans VARCHAR(50),
                    pain_points TEXT,
                    use_cases TEXT,
                    referral_source VARCHAR(100),
                    status VARCHAR(50) DEFAULT 'pending',
                    notes TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    contacted_at TIMESTAMP WITH TIME ZONE,
                    activated_at TIMESTAMP WITH TIME ZONE
                );

                CREATE INDEX IF NOT EXISTS idx_beta_email ON beta_applications(email);
                CREATE INDEX IF NOT EXISTS idx_beta_status ON beta_applications(status);
                CREATE INDEX IF NOT EXISTS idx_beta_created ON beta_applications(created_at DESC);
            """))
            conn.commit()
            logger.info("Beta tables initialized")
    except SQLAlchemyError as e:
        logger.warning(f"Beta tables initialization note: {e}")


# Auto-create tables on module load
try:
    ensure_beta_tables_exist()
except SQLAlchemyError as e:
    logger.warning(f"Could not auto-create beta tables: {e}")


# ================================================================
# ENUMS
# ================================================================

class BetaApplicationStatus(str, enum.Enum):
    """Status values for beta applications."""
    PENDING = "pending"
    CONTACTED = "contacted"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    REJECTED = "rejected"
    CHURNED = "churned"


# ================================================================
# SQLAlchemy MODEL
# ================================================================

class BetaApplication(Base):
    """Beta program application database model."""
    __tablename__ = "beta_applications"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(255), nullable=False)
    contact_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(50))
    team_size = Column(String(50))
    current_crm = Column(String(255))
    monthly_loans = Column(String(50))
    pain_points = Column(Text)
    use_cases = Column(Text)
    referral_source = Column(String(100))
    status = Column(String(50), default=BetaApplicationStatus.PENDING.value)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    contacted_at = Column(DateTime(timezone=True))
    activated_at = Column(DateTime(timezone=True))


# ================================================================
# PYDANTIC MODELS - Requests
# ================================================================

class BetaApplicationCreate(BaseModel):
    """Request model for creating a beta application."""
    company_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Company name"
    )
    contact_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Primary contact name"
    )
    email: EmailStr = Field(..., description="Contact email address")
    phone: Optional[str] = Field(
        None,
        max_length=50,
        description="Contact phone number"
    )
    team_size: str = Field(
        ...,
        description="Team size range (e.g., '1-5', '6-20', '21-50', '50+')"
    )
    current_crm: Optional[str] = Field(
        None,
        max_length=255,
        description="Current CRM system in use"
    )
    monthly_loans: Optional[str] = Field(
        None,
        description="Monthly loan volume range"
    )
    pain_points: Optional[str] = Field(
        None,
        max_length=2000,
        description="Current pain points with existing systems"
    )
    use_cases: Optional[str] = Field(
        None,
        max_length=2000,
        description="Intended use cases for Perennia AI"
    )
    referral_source: Optional[str] = Field(
        None,
        max_length=100,
        description="How they heard about us"
    )


class BetaStatusUpdate(BaseModel):
    """Request model for updating application status."""
    status: BetaApplicationStatus = Field(..., description="New status")
    notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Notes about the status change"
    )


# ================================================================
# PYDANTIC MODELS - Responses
# ================================================================

class BetaApplicationResponse(BaseModel):
    """Response model for a beta application."""
    id: int = Field(..., description="Application ID")
    company_name: str = Field(..., description="Company name")
    contact_name: str = Field(..., description="Primary contact name")
    email: str = Field(..., description="Contact email")
    phone: Optional[str] = Field(None, description="Contact phone")
    team_size: str = Field(..., description="Team size range")
    current_crm: Optional[str] = Field(None, description="Current CRM")
    monthly_loans: Optional[str] = Field(None, description="Monthly loan volume")
    pain_points: Optional[str] = Field(None, description="Pain points")
    use_cases: Optional[str] = Field(None, description="Use cases")
    referral_source: Optional[str] = Field(None, description="Referral source")
    status: str = Field(..., description="Application status")
    created_at: datetime = Field(..., description="Submission timestamp")

    class Config:
        from_attributes = True


class SubmitApplicationResponse(BaseModel):
    """Response model for submitting an application."""
    success: bool = Field(..., description="Whether submission succeeded")
    message: str = Field(..., description="Response message")
    application_id: Optional[int] = Field(None, description="ID of created application")


class BetaStatsResponse(BaseModel):
    """Response model for beta program statistics."""
    total_applications: int = Field(..., description="Total applications received")
    pending: int = Field(..., description="Applications pending review")
    active: int = Field(..., description="Active beta users")
    by_referral_source: Dict[str, int] = Field(default={}, description="Applications by referral source")
    by_team_size: Dict[str, int] = Field(default={}, description="Applications by team size")


# ================================================================
# EMAIL NOTIFICATIONS
# ================================================================

async def send_application_confirmation(email: str, contact_name: str, company_name: str):
    """Send confirmation email to applicant."""
    try:
        from email_service import send_email

        html_body = f"""
        <h2>Hi {contact_name},</h2>

        <p>Thank you for applying to the Perennia AI UVIP beta program!</p>

        <p>We've received your application for <strong>{company_name}</strong> and will review it within 2 business days.</p>

        <h3>What happens next?</h3>
        <ol>
            <li>Our team reviews your application</li>
            <li>We'll schedule a 15-minute demo call</li>
            <li>You get instant access to UVIP</li>
            <li>Weekly check-ins to gather feedback</li>
        </ol>

        <p>Questions? Reply to this email or contact beta@pipeline360.com</p>

        <p>Best regards,<br>The Perennia AI Team</p>
        """

        await send_email(
            to_email=email,
            subject="Thank you for applying to Perennia AI UVIP Beta",
            html_body=html_body
        )
        logger.info(f"Sent beta confirmation email to {email}")

    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}")


async def send_internal_notification(application: BetaApplication):
    """Notify internal team of new application."""
    try:
        from email_service import send_email

        created_str = application.created_at.strftime('%Y-%m-%d %H:%M UTC') if application.created_at else 'Unknown'

        html_body = f"""
        <h2>New Beta Application</h2>

        <p><strong>Company:</strong> {application.company_name}</p>
        <p><strong>Contact:</strong> {application.contact_name}</p>
        <p><strong>Email:</strong> {application.email}</p>
        <p><strong>Phone:</strong> {application.phone or 'Not provided'}</p>
        <p><strong>Team Size:</strong> {application.team_size}</p>
        <p><strong>Monthly Loans:</strong> {application.monthly_loans or 'Not provided'}</p>
        <p><strong>Current CRM:</strong> {application.current_crm or 'Not provided'}</p>

        <h3>Pain Points:</h3>
        <p>{application.pain_points or 'Not provided'}</p>

        <h3>Use Cases:</h3>
        <p>{application.use_cases or 'Not provided'}</p>

        <p><strong>Referral Source:</strong> {application.referral_source or 'Not provided'}</p>

        <hr>
        <p><em>Submitted: {created_str}</em></p>
        """

        await send_email(
            to_email="beta@pipeline360.com",
            subject=f"New Beta Application: {application.company_name}",
            html_body=html_body
        )
        logger.info(f"Sent internal notification for {application.company_name}")

    except Exception as e:
        logger.error(f"Failed to send internal notification: {e}")


# ================================================================
# API ENDPOINTS
# ================================================================

@router.post("/apply", response_model=SubmitApplicationResponse)
async def submit_beta_application(
    application: BetaApplicationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Submit a beta program application.

    Creates the application record and sends confirmation email
    to the applicant and notification to the internal team.
    """
    try:
        # Check for duplicate application
        existing = db.query(BetaApplication).filter(
            BetaApplication.email == application.email
        ).first()

        if existing:
            logger.info(f"Duplicate beta application from {application.email}")
            # Return success to not reveal if email exists (privacy)
            return SubmitApplicationResponse(
                success=True,
                message="Application submitted successfully"
            )

        # Create application record
        db_application = BetaApplication(
            company_name=application.company_name,
            contact_name=application.contact_name,
            email=application.email,
            phone=application.phone,
            team_size=application.team_size,
            current_crm=application.current_crm,
            monthly_loans=application.monthly_loans,
            pain_points=application.pain_points,
            use_cases=application.use_cases,
            referral_source=application.referral_source,
            status=BetaApplicationStatus.PENDING.value
        )

        db.add(db_application)
        db.commit()
        db.refresh(db_application)

        logger.info(f"Beta application created: {db_application.id} - {application.company_name}")

        # Queue email notifications (non-blocking)
        background_tasks.add_task(
            send_application_confirmation,
            application.email,
            application.contact_name,
            application.company_name
        )
        background_tasks.add_task(
            send_internal_notification,
            db_application
        )

        return SubmitApplicationResponse(
            success=True,
            message="Application submitted successfully",
            application_id=db_application.id
        )

    except Exception as e:
        logger.error(f"Error creating beta application: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to submit application. Please try again."
        )


@router.get("/applications", response_model=List[BetaApplicationResponse])
async def list_beta_applications(
    request: Request,
    status: Optional[BetaApplicationStatus] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum records to return"),
    db: Session = Depends(get_db)
):
    """
    List all beta applications.

    Requires admin authentication.
    """
    # Verify admin access
    await require_admin_user(request, db)

    query = db.query(BetaApplication)

    if status:
        query = query.filter(BetaApplication.status == status.value)

    applications = query.order_by(
        BetaApplication.created_at.desc()
    ).offset(skip).limit(limit).all()

    return applications


@router.get("/applications/{application_id}", response_model=BetaApplicationResponse)
async def get_beta_application(
    request: Request,
    application_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific beta application by ID.

    Requires admin authentication.
    """
    # Verify admin access
    await require_admin_user(request, db)

    application = db.query(BetaApplication).filter(
        BetaApplication.id == application_id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    return application


@router.patch("/applications/{application_id}/status")
async def update_application_status(
    request: Request,
    application_id: int,
    status_update: BetaStatusUpdate,
    db: Session = Depends(get_db)
):
    """
    Update beta application status.

    Requires admin authentication.
    Automatically tracks when applications are contacted or activated.
    """
    # Verify admin access
    await require_admin_user(request, db)

    application = db.query(BetaApplication).filter(
        BetaApplication.id == application_id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    application.status = status_update.status.value
    application.updated_at = datetime.now(timezone.utc)

    if status_update.notes:
        application.notes = status_update.notes

    # Track status change timestamps
    if status_update.status == BetaApplicationStatus.CONTACTED:
        application.contacted_at = datetime.now(timezone.utc)
    elif status_update.status == BetaApplicationStatus.ACTIVE:
        application.activated_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Beta application {application_id} status updated to {status_update.status.value}")

    return {
        "success": True,
        "status": status_update.status.value,
        "updated_at": application.updated_at.isoformat()
    }


@router.get("/stats", response_model=BetaStatsResponse)
async def get_beta_stats(request: Request, db: Session = Depends(get_db)):
    """
    Get beta program statistics.

    Requires admin authentication.
    Returns counts by status, referral source, and team size.
    """
    # Verify admin access
    await require_admin_user(request, db)

    total = db.query(func.count(BetaApplication.id)).scalar() or 0
    pending = db.query(func.count(BetaApplication.id)).filter(
        BetaApplication.status == BetaApplicationStatus.PENDING.value
    ).scalar() or 0
    active = db.query(func.count(BetaApplication.id)).filter(
        BetaApplication.status == BetaApplicationStatus.ACTIVE.value
    ).scalar() or 0

    # Get applications by referral source
    by_source = db.query(
        BetaApplication.referral_source,
        func.count(BetaApplication.id)
    ).group_by(BetaApplication.referral_source).all()

    # Get applications by team size
    by_team_size = db.query(
        BetaApplication.team_size,
        func.count(BetaApplication.id)
    ).group_by(BetaApplication.team_size).all()

    return BetaStatsResponse(
        total_applications=total,
        pending=pending,
        active=active,
        by_referral_source={source or 'unknown': count for source, count in by_source},
        by_team_size={size: count for size, count in by_team_size if size}
    )


@router.get("/health")
async def health_check():
    """Health check endpoint for beta program service."""
    return {
        "status": "healthy",
        "service": "beta-program",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
