"""
Beta Application API Routes
Handles beta program applications and tracking
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import logging
import enum

from database import get_db, Base

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/beta", tags=["beta"])


# ============================================================================
# Models
# ============================================================================

class BetaApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    CONTACTED = "contacted"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    REJECTED = "rejected"
    CHURNED = "churned"


class BetaApplication(Base):
    """Beta program application model"""
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    contacted_at = Column(DateTime)
    activated_at = Column(DateTime)


# ============================================================================
# Schemas
# ============================================================================

class BetaApplicationCreate(BaseModel):
    """Schema for creating a beta application"""
    company_name: str
    contact_name: str
    email: EmailStr
    phone: Optional[str] = None
    team_size: str
    current_crm: Optional[str] = None
    monthly_loans: Optional[str] = None
    pain_points: Optional[str] = None
    use_cases: Optional[str] = None
    referral_source: Optional[str] = None


class BetaApplicationResponse(BaseModel):
    """Schema for beta application response"""
    id: int
    company_name: str
    contact_name: str
    email: str
    phone: Optional[str]
    team_size: str
    current_crm: Optional[str]
    monthly_loans: Optional[str]
    pain_points: Optional[str]
    use_cases: Optional[str]
    referral_source: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Email Notifications
# ============================================================================

async def send_application_confirmation(email: str, contact_name: str, company_name: str):
    """Send confirmation email to applicant"""
    try:
        # Import email service
        from email_service import send_email

        html_body = f"""
        <h2>Hi {contact_name},</h2>

        <p>Thank you for applying to the Pipeline 360 UVIP beta program!</p>

        <p>We've received your application for <strong>{company_name}</strong> and will review it within 2 business days.</p>

        <h3>What happens next?</h3>
        <ol>
            <li>Our team reviews your application</li>
            <li>We'll schedule a 15-minute demo call</li>
            <li>You get instant access to UVIP</li>
            <li>Weekly check-ins to gather feedback</li>
        </ol>

        <p>Questions? Reply to this email or contact beta@pipeline360.com</p>

        <p>Best regards,<br>The Pipeline 360 Team</p>
        """

        await send_email(
            to_email=email,
            subject="Thank you for applying to Pipeline 360 UVIP Beta",
            html_body=html_body
        )
        logger.info(f"Sent beta confirmation email to {email}")

    except Exception as e:
        logger.error(f"Failed to send confirmation email: {str(e)}")


async def send_internal_notification(application: BetaApplication):
    """Notify internal team of new application"""
    try:
        from email_service import send_email

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
        <p><em>Submitted: {application.created_at.strftime('%Y-%m-%d %H:%M UTC')}</em></p>
        """

        # Send to internal team email
        await send_email(
            to_email="beta@pipeline360.com",  # Configure this
            subject=f"New Beta Application: {application.company_name}",
            html_body=html_body
        )
        logger.info(f"Sent internal notification for {application.company_name}")

    except Exception as e:
        logger.error(f"Failed to send internal notification: {str(e)}")


# ============================================================================
# Routes
# ============================================================================

@router.post("/apply", response_model=dict)
async def submit_beta_application(
    application: BetaApplicationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Submit a beta program application.
    Sends confirmation email and notifies internal team.
    """
    try:
        # Check for duplicate application
        existing = db.query(BetaApplication).filter(
            BetaApplication.email == application.email
        ).first()

        if existing:
            logger.info(f"Duplicate beta application from {application.email}")
            # Still return success to not reveal if email exists
            return {
                "success": True,
                "message": "Application submitted successfully"
            }

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

        return {
            "success": True,
            "message": "Application submitted successfully",
            "application_id": db_application.id
        }

    except Exception as e:
        logger.error(f"Error creating beta application: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to submit application. Please try again."
        )


@router.get("/applications", response_model=list[BetaApplicationResponse])
async def list_beta_applications(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    List all beta applications (admin only).
    Filter by status optionally.
    """
    # TODO: Add admin authentication check
    query = db.query(BetaApplication)

    if status:
        query = query.filter(BetaApplication.status == status)

    applications = query.order_by(
        BetaApplication.created_at.desc()
    ).offset(skip).limit(limit).all()

    return applications


@router.get("/applications/{application_id}", response_model=BetaApplicationResponse)
async def get_beta_application(
    application_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific beta application by ID"""
    application = db.query(BetaApplication).filter(
        BetaApplication.id == application_id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    return application


@router.patch("/applications/{application_id}/status")
async def update_application_status(
    application_id: int,
    status: str,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Update beta application status"""
    application = db.query(BetaApplication).filter(
        BetaApplication.id == application_id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Validate status
    try:
        BetaApplicationStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    application.status = status
    if notes:
        application.notes = notes

    # Track status changes
    if status == BetaApplicationStatus.CONTACTED.value:
        application.contacted_at = datetime.utcnow()
    elif status == BetaApplicationStatus.ACTIVE.value:
        application.activated_at = datetime.utcnow()

    db.commit()

    logger.info(f"Beta application {application_id} status updated to {status}")

    return {"success": True, "status": status}


@router.get("/stats")
async def get_beta_stats(db: Session = Depends(get_db)):
    """Get beta program statistics"""
    from sqlalchemy import func

    total = db.query(func.count(BetaApplication.id)).scalar()
    pending = db.query(func.count(BetaApplication.id)).filter(
        BetaApplication.status == BetaApplicationStatus.PENDING.value
    ).scalar()
    active = db.query(func.count(BetaApplication.id)).filter(
        BetaApplication.status == BetaApplicationStatus.ACTIVE.value
    ).scalar()

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

    return {
        "total_applications": total,
        "pending": pending,
        "active": active,
        "by_referral_source": {source or 'unknown': count for source, count in by_source},
        "by_team_size": {size: count for size, count in by_team_size if size}
    }
