"""
Borrower Application API Routes

Provides endpoints for the borrower application flow, including:
- LO-facing endpoints (authenticated) for creating and managing applications
- Public borrower-facing endpoints (token-based auth) for completing applications
- Document upload and AI analysis
- AI Concierge for conversational mortgage application
- Review call scheduling
- MISMO XML export
- LO Dashboard and application management
- Co-borrower invitation and completion flow
- Public pre-qualification calculator

Endpoints:
  LO-facing (authenticated):
    POST   /api/v1/applications/                    - Create new application
    GET    /api/v1/applications/                    - List applications
    GET    /api/v1/applications/{id}                - Get application by ID
    GET    /api/v1/applications/analytics           - Get application analytics

  Public borrower-facing (token-based):
    GET    /api/v1/apply/{token}                    - Get application by token
    PATCH  /api/v1/apply/{token}                    - Update application
    POST   /api/v1/apply/{token}/step               - Save step data
    POST   /api/v1/apply/{token}/prequalify         - Calculate pre-qualification
    POST   /api/v1/apply/{token}/credit-auth        - Capture credit authorization
    POST   /api/v1/apply/{token}/submit             - Submit application
    POST   /api/v1/apply/{token}/documents          - Upload document
    POST   /api/v1/apply/{token}/documents/{id}/analyze - Analyze document with AI
    GET    /api/v1/apply/{token}/documents          - List documents
    DELETE /api/v1/apply/{token}/documents/{id}     - Delete document
    POST   /api/v1/apply/{token}/concierge          - AI Concierge conversation
    GET    /api/v1/apply/{token}/concierge/status   - Get concierge status
    GET    /api/v1/apply/{token}/available-slots    - Get available time slots
    POST   /api/v1/apply/{token}/schedule-review-call - Schedule review call
    GET    /api/v1/apply/{token}/review-call        - Get scheduled review call
    GET    /api/v1/apply/{token}/export/mismo       - Export as MISMO XML
    POST   /api/v1/apply/{token}/coborrower         - Create co-borrower invitation

  LO Dashboard:
    GET    /api/v1/lo/dashboard/stats               - Get LO dashboard stats
    GET    /api/v1/lo/applications                  - Get LO's applications
    GET    /api/v1/lo/activity                      - Get recent activity
    POST   /api/v1/lo/social/generate               - Generate social content
    GET    /api/v1/lo/social/schedule-suggestions   - Get posting suggestions
    GET    /api/v1/lo/applications/{id}             - Get application detail
    PUT    /api/v1/lo/applications/{id}/status      - Update status
    POST   /api/v1/lo/applications/{id}/notes       - Add note
    GET    /api/v1/lo/applications/{id}/documents   - Get documents
    GET    /api/v1/lo/applications/{id}/export/mismo - Export MISMO

  Admin:
    GET    /api/v1/admin/applications/{id}/export/mismo - Admin MISMO export

  Co-borrower:
    GET    /api/v1/coborrower/{token}               - Get invitation
    POST   /api/v1/coborrower/{token}/save          - Save co-borrower data
    POST   /api/v1/coborrower/{token}/submit        - Submit co-borrower section
    POST   /api/v1/coborrower/{token}/credit-auth   - Capture credit auth

  Public:
    POST   /api/v1/prequalify                       - Public pre-qualification
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import enum

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from utils.pii_mask import mask_email, mask_phone
from schemas.pii_masking import sanitize_step_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Borrower Applications"])


# ============================================================================
# Runtime imports to avoid circular dependencies
# ============================================================================

def get_db_session():
    """Get database session - runtime import to avoid circular dependency"""
    from database import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency - runtime import"""
    import main
    return main.get_current_user


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'BorrowerApplication': main.BorrowerApplication,
        'ApplicationEvent': main.ApplicationEvent,
        'ApplicationDocument': main.ApplicationDocument,
        'CoborrowerInvitation': main.CoborrowerInvitation,
        'Lead': main.Lead,
        'LeadStage': main.LeadStage,
        'Organization': main.Organization,
    }


def get_enums():
    """Get enums at runtime to avoid circular imports"""
    import main
    return {
        'ApplicationStatus': main.ApplicationStatus,
        'ApplicationStep': main.ApplicationStep,
        'DocumentCategory': main.DocumentCategory,
    }


# ============================================================================
# Enums (local copies for type hints and schema definitions)
# ============================================================================

class ApplicationStatus(str, enum.Enum):
    """Status of the borrower application"""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    PENDING_DOCUMENTS = "pending_documents"
    PENDING_COBORROWER = "pending_coborrower"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class ApplicationStep(str, enum.Enum):
    """Steps in the borrower application process"""
    PERSONAL_INFO = "personal_info"
    COBORROWER = "coborrower"
    PROPERTY = "property"
    INCOME = "income"
    ASSETS = "assets"
    LIABILITIES = "liabilities"
    DECLARATIONS = "declarations"
    DOCUMENTS = "documents"
    CREDIT_AUTH = "credit_auth"
    REVIEW = "review"


class DocumentCategory(str, enum.Enum):
    """Document categories for organization"""
    INCOME = "Income"
    ASSETS = "Assets"
    CREDIT = "Credit"
    PROPERTY = "Property"
    IDENTITY = "Identity"
    DISCLOSURES = "Disclosures"
    APPLICATION = "Application"
    MISC = "Miscellaneous"


# ============================================================================
# Pydantic Schemas
# ============================================================================

class BorrowerApplicationCreate(BaseModel):
    """Schema for creating a new borrower application"""
    lead_id: Optional[int] = None
    borrower_first_name: Optional[str] = None
    borrower_last_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    has_coborrower: bool = False
    coborrower_email: Optional[str] = None
    expires_in_days: int = 30


class BorrowerApplicationUpdate(BaseModel):
    """Schema for updating application data"""
    current_step: Optional[str] = None
    step_data: Optional[Dict[str, Any]] = None
    completed_steps: Optional[List[str]] = None
    progress_percentage: Optional[int] = None
    borrower_first_name: Optional[str] = None
    borrower_last_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    has_coborrower: Optional[bool] = None
    coborrower_email: Optional[str] = None
    notes: Optional[str] = None
    time_spent_seconds: Optional[int] = None


VALID_STEPS = {
    "personal_info", "coborrower", "property", "income", "assets",
    "liabilities", "declarations", "documents", "credit_auth", "review",
    "about_you", "new_home", "current_mortgage", "second_mortgage",
    "credit", "background", "government_monitoring", "schedule",
    "authorizations", "real_estate_owned",
}


class StepDataUpdate(BaseModel):
    """Schema for updating a specific step's data"""
    step: str = Field(..., max_length=50)
    data: Dict[str, Any]
    mark_completed: bool = False


class CreditAuthCapture(BaseModel):
    """Schema for capturing credit authorization"""
    ssn_last4: str = Field(..., min_length=4, max_length=4, pattern=r'^\d{4}$')
    consent_text: str
    consent_agreed: bool
    signature_data: Optional[str] = None


class PrequalificationRequest(BaseModel):
    """Schema for pre-qualification calculation"""
    annual_income: float = Field(..., ge=0)
    monthly_debts: float = Field(..., ge=0)
    credit_score_range: str = Field(..., max_length=50)
    down_payment: float = Field(..., ge=0)
    down_payment_type: str = Field(default="percentage", max_length=20)
    property_value: Optional[float] = Field(default=None, ge=0)
    loan_type: str = Field(default="conventional", max_length=30)
    property_type: str = Field(default="single_family", max_length=30)
    occupancy: str = Field(default="primary", max_length=20)


class PrequalificationResponse(BaseModel):
    """Schema for pre-qualification results"""
    max_loan_amount: float
    estimated_rate: float
    estimated_monthly_payment: float
    front_end_dti: float
    back_end_dti: float
    max_home_price: float
    loan_type: str
    rate_assumptions: Dict[str, Any]
    warnings: List[str] = []


class DocumentUploadResponse(BaseModel):
    """Schema for document upload response"""
    id: int
    filename: str
    original_filename: str
    category: str
    file_size: int
    mime_type: str
    upload_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CoborrowerInvitationCreate(BaseModel):
    """Schema for creating co-borrower invitation"""
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    relationship_type: Optional[str] = None
    send_email: bool = True
    send_sms: bool = False


class CoborrowerInvitationResponse(BaseModel):
    """Schema for co-borrower invitation response"""
    id: int
    invitation_token: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    status: str
    sent_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BorrowerApplicationResponse(BaseModel):
    """Full application response schema.

    Enterprise Readiness 3.19: ssn_encrypted and co_ssn_encrypted are
    intentionally excluded.  Only masked last-4 is exposed via ssn_display.
    """
    id: int
    public_token: str
    status: str
    current_step: str
    progress_percentage: int
    completed_steps: List[str]
    borrower_first_name: Optional[str] = None
    borrower_last_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    has_coborrower: bool
    coborrower_email: Optional[str] = None
    coborrower_completed: bool
    prequalification_amount: Optional[float] = None
    prequalification_rate: Optional[float] = None
    prequalification_monthly_payment: Optional[float] = None
    credit_auth_captured: bool
    # Masked SSN display: ***-**-1234 (derived from credit_auth_ssn_last4)
    ssn_display: Optional[str] = None
    expires_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ApplicationPublicResponse(BaseModel):
    """Limited public response for borrowers (no internal IDs)"""
    status: str
    current_step: str
    progress_percentage: int
    completed_steps: List[str]
    step_data: Dict[str, Any]
    borrower_first_name: Optional[str] = None
    borrower_last_name: Optional[str] = None
    borrower_email: Optional[str] = None
    borrower_phone: Optional[str] = None
    has_coborrower: bool
    coborrower_completed: bool
    prequalification_data: Optional[Dict[str, Any]] = None
    credit_auth_captured: bool
    expires_at: Optional[datetime] = None
    lo_name: Optional[str] = None
    lo_email: Optional[str] = None
    lo_phone: Optional[str] = None
    company_name: Optional[str] = None

    @field_validator('step_data', mode='before')
    @classmethod
    def sanitize_pii_from_step_data(cls, v):
        """Enterprise Readiness 3.19: Strip SSN/PII from step_data before serialization"""
        return sanitize_step_data(v)

    class Config:
        from_attributes = True


class ApplicationAnalytics(BaseModel):
    """Schema for application analytics data"""
    total_applications: int
    by_status: Dict[str, int]
    avg_completion_time_minutes: float
    avg_progress_percentage: float
    conversion_rate: float
    drop_off_by_step: Dict[str, int]
    documents_uploaded: int
    coborrower_completion_rate: float


class ConciergeMessage(BaseModel):
    message: str
    current_stage: str = "greeting"
    extracted_data: Dict[str, Any] = {}
    conversation_history: List[Dict[str, str]] = []


class ReviewCallScheduleRequest(BaseModel):
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    timezone: str = "America/New_York"
    contact_method: str = "phone"
    notes: Optional[str] = None


class ApplicationStatusUpdate(BaseModel):
    status: str


class ApplicationNoteCreate(BaseModel):
    note: str


class SocialContentRequest(BaseModel):
    type: str
    platform: str = "all"


# ============================================================================
# Helper Functions
# ============================================================================

_tables_ensured = False

def _ensure_application_tables(db: Session):
    """Ensure borrower_applications and application_events tables exist."""
    global _tables_ensured
    if _tables_ensured:
        return
    try:
        from database import Base, engine
        models = get_models()
        BorrowerApplication = models['BorrowerApplication']
        ApplicationEvent = models['ApplicationEvent']
        BorrowerApplication.__table__.create(engine, checkfirst=True)
        ApplicationEvent.__table__.create(engine, checkfirst=True)
        _tables_ensured = True
        logger.info("Borrower application tables verified/created")
    except Exception as e:
        logger.warning(f"Table creation check: {e}")
        _tables_ensured = True  # Don't retry on every request


def generate_token(length: int = 32) -> str:
    """Generate a secure random token"""
    import secrets
    return secrets.token_urlsafe(length)


def calculate_progress(completed_steps: List[str]) -> int:
    """Calculate progress percentage based on completed steps"""
    all_steps = [s.value for s in ApplicationStep]
    if not completed_steps:
        return 0
    return int((len(completed_steps) / len(all_steps)) * 100)


def calculate_prequalification(data: PrequalificationRequest) -> PrequalificationResponse:
    """Calculate pre-qualification based on financial data"""
    # Credit score to rate mapping (simplified)
    rate_adjustments = {
        "760+": 0,
        "740-759": 0.125,
        "720-739": 0.25,
        "700-719": 0.375,
        "680-699": 0.5,
        "660-679": 0.75,
        "640-659": 1.0,
        "620-639": 1.5,
        "<620": 2.0,
    }

    # Base rates by loan type (simplified)
    base_rates = {
        "conventional": 6.5,
        "fha": 6.25,
        "va": 6.0,
        "usda": 6.25,
        "jumbo": 7.0,
    }

    # Calculate DTI limits by loan type
    dti_limits = {
        "conventional": {"front": 28, "back": 45},
        "fha": {"front": 31, "back": 43},
        "va": {"front": 41, "back": 41},
        "usda": {"front": 29, "back": 41},
        "jumbo": {"front": 36, "back": 43},
    }

    monthly_income = data.annual_income / 12
    base_rate = base_rates.get(data.loan_type, 6.5)
    rate_adj = rate_adjustments.get(data.credit_score_range, 0.5)
    estimated_rate = base_rate + rate_adj

    limits = dti_limits.get(data.loan_type, {"front": 28, "back": 45})

    # Calculate max payment based on DTI
    max_front_payment = monthly_income * (limits["front"] / 100)
    max_total_debt = monthly_income * (limits["back"] / 100)
    max_housing_from_back = max_total_debt - data.monthly_debts

    # Use the more conservative limit
    max_monthly_payment = min(max_front_payment, max_housing_from_back)

    # Calculate max loan amount (simplified - assumes 30yr fixed, no PMI calc)
    monthly_rate = estimated_rate / 100 / 12
    n_payments = 360  # 30 years

    # Reverse mortgage formula: P = PMT * ((1 - (1 + r)^-n) / r)
    if monthly_rate > 0:
        max_loan = max_monthly_payment * ((1 - (1 + monthly_rate) ** -n_payments) / monthly_rate)
    else:
        max_loan = max_monthly_payment * n_payments

    # Account for taxes/insurance (estimate 1.5% of home value annually)
    max_loan = max_loan * 0.8  # Conservative adjustment for PITI

    # Calculate down payment
    if data.down_payment_type == "percentage":
        down_pct = data.down_payment / 100
    else:
        down_pct = data.down_payment / (max_loan / (1 - (data.down_payment / 100))) if data.property_value else 0.2

    max_home_price = max_loan / (1 - down_pct) if down_pct < 1 else max_loan

    # Calculate actual payment for display
    actual_loan = max_loan
    if data.property_value:
        if data.down_payment_type == "percentage":
            actual_loan = data.property_value * (1 - data.down_payment / 100)
        else:
            actual_loan = data.property_value - data.down_payment

    if monthly_rate > 0:
        monthly_payment = actual_loan * (monthly_rate * (1 + monthly_rate) ** n_payments) / ((1 + monthly_rate) ** n_payments - 1)
    else:
        monthly_payment = actual_loan / n_payments

    # Calculate actual DTI ratios
    front_dti = (monthly_payment / monthly_income) * 100
    back_dti = ((monthly_payment + data.monthly_debts) / monthly_income) * 100

    warnings = []
    if back_dti > limits["back"]:
        warnings.append(f"Back-end DTI ({back_dti:.1f}%) exceeds typical {data.loan_type} limit ({limits['back']}%)")
    if front_dti > limits["front"]:
        warnings.append(f"Front-end DTI ({front_dti:.1f}%) exceeds typical {data.loan_type} limit ({limits['front']}%)")

    return PrequalificationResponse(
        max_loan_amount=round(max_loan, 0),
        estimated_rate=round(estimated_rate, 3),
        estimated_monthly_payment=round(monthly_payment, 2),
        front_end_dti=round(front_dti, 1),
        back_end_dti=round(back_dti, 1),
        max_home_price=round(max_home_price, 0),
        loan_type=data.loan_type,
        rate_assumptions={
            "base_rate": base_rate,
            "credit_adjustment": rate_adj,
            "term_years": 30,
            "calculation_date": datetime.now(timezone.utc).isoformat(),
        },
        warnings=warnings,
    )


# ============================================================================
# LO-facing endpoints (authenticated)
# ============================================================================

@router.post("/api/v1/applications/", response_model=BorrowerApplicationResponse, status_code=201)
async def create_borrower_application(
    data: BorrowerApplicationCreate,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Create a new borrower application and generate a public token"""
    try:
        models = get_models()
        BorrowerApplication = models['BorrowerApplication']
        ApplicationEvent = models['ApplicationEvent']

        # Ensure tables exist
        _ensure_application_tables(db)

        # Generate public token
        public_token = generate_token(32)

        # Calculate expiration date
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

        # Create application
        application = BorrowerApplication(
            public_token=public_token,
            lead_id=data.lead_id,
            owner_id=current_user.id,
            organization_id=current_user.organization_id,
            borrower_first_name=data.borrower_first_name,
            borrower_last_name=data.borrower_last_name,
            borrower_email=data.borrower_email,
            borrower_phone=data.borrower_phone,
            has_coborrower=data.has_coborrower,
            coborrower_email=data.coborrower_email,
            expires_at=expires_at,
            completed_steps=[],
            step_data={},
        )

        db.add(application)
        db.commit()
        db.refresh(application)

        # Log event (non-blocking — don't fail if event logging fails)
        try:
            event = ApplicationEvent(
                application_id=application.id,
                event_type="created",
                actor_type="lo",
                actor_email=current_user.email,
            )
            db.add(event)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to log application creation event: {e}")
            db.rollback()

        return application

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create borrower application: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create application")


@router.get("/api/v1/applications/", response_model=List[BorrowerApplicationResponse])
async def list_applications(
    status: Optional[str] = None,
    lead_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """List all borrower applications for the current user"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    query = db.query(BorrowerApplication).filter(BorrowerApplication.owner_id == current_user.id)

    if status:
        query = query.filter(BorrowerApplication.status == status)
    if lead_id:
        query = query.filter(BorrowerApplication.lead_id == lead_id)

    query = query.order_by(BorrowerApplication.created_at.desc())
    applications = query.offset(offset).limit(limit).all()

    return applications


@router.get("/api/v1/applications/analytics", response_model=ApplicationAnalytics)
async def get_application_analytics(
    days: int = 30,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get analytics for borrower applications"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationStatus = enums['ApplicationStatus']

    since = datetime.now(timezone.utc) - timedelta(days=days)

    apps = db.query(BorrowerApplication).filter(
        BorrowerApplication.owner_id == current_user.id,
        BorrowerApplication.created_at >= since
    ).all()

    # Calculate metrics
    total = len(apps)
    by_status = {}
    total_time = 0
    total_progress = 0
    submitted_count = 0
    drop_off = {}
    docs_count = 0
    coborrower_apps = 0
    coborrower_completed = 0

    for app in apps:
        # Count by status
        status = app.status.value if hasattr(app.status, 'value') else str(app.status)
        by_status[status] = by_status.get(status, 0) + 1

        # Track time and progress
        total_time += app.time_spent_seconds or 0
        total_progress += app.progress_percentage or 0

        if app.submitted_at:
            submitted_count += 1

        # Track drop-off by step
        if app.current_step and app.status in [ApplicationStatus.DRAFT, ApplicationStatus.EXPIRED]:
            step = app.current_step.value if hasattr(app.current_step, 'value') else str(app.current_step)
            drop_off[step] = drop_off.get(step, 0) + 1

        # Count documents
        docs_count += len(app.documents) if app.documents else 0

        # Track co-borrower completion
        if app.has_coborrower:
            coborrower_apps += 1
            if app.coborrower_completed:
                coborrower_completed += 1

    return ApplicationAnalytics(
        total_applications=total,
        by_status=by_status,
        avg_completion_time_minutes=round((total_time / total / 60) if total > 0 else 0, 1),
        avg_progress_percentage=round((total_progress / total) if total > 0 else 0, 1),
        conversion_rate=round((submitted_count / total * 100) if total > 0 else 0, 1),
        drop_off_by_step=drop_off,
        documents_uploaded=docs_count,
        coborrower_completion_rate=round((coborrower_completed / coborrower_apps * 100) if coborrower_apps > 0 else 0, 1),
    )


@router.get("/api/v1/applications/{application_id}", response_model=BorrowerApplicationResponse)
async def get_application(
    application_id: int,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get a specific application by ID"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id,
        BorrowerApplication.owner_id == current_user.id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    return application


# ============================================================================
# Public borrower-facing endpoints (token-based auth)
# ============================================================================

@router.get("/api/v1/apply/{token}", response_model=ApplicationPublicResponse)
async def get_application_by_token(
    token: str,
    db: Session = Depends(get_db_session()),
    request: Request = None
):
    """Get application data using public token (borrower-facing)"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    User = models['User']
    Organization = models['Organization']
    ApplicationStatus = enums['ApplicationStatus']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Check expiration
    if application.expires_at and application.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        application.status = ApplicationStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=410, detail="Application link has expired")

    # Update last activity
    application.last_activity_at = datetime.now(timezone.utc)
    db.commit()

    # Get LO info
    owner = db.query(User).filter(User.id == application.owner_id).first()
    org = db.query(Organization).filter(Organization.id == application.organization_id).first() if application.organization_id else None

    # Enterprise Readiness Check 3.19: Sanitize step_data to strip raw SSN values
    safe_step_data = sanitize_step_data(application.step_data)

    return ApplicationPublicResponse(
        status=application.status.value if hasattr(application.status, 'value') else str(application.status),
        current_step=application.current_step.value if hasattr(application.current_step, 'value') else str(application.current_step),
        progress_percentage=application.progress_percentage or 0,
        completed_steps=application.completed_steps or [],
        step_data=safe_step_data,
        borrower_first_name=application.borrower_first_name,
        borrower_last_name=application.borrower_last_name,
        borrower_email=application.borrower_email,
        borrower_phone=application.borrower_phone,
        has_coborrower=application.has_coborrower,
        coborrower_completed=application.coborrower_completed,
        prequalification_data=application.prequalification_data,
        credit_auth_captured=application.credit_auth_captured,
        expires_at=application.expires_at,
        lo_name=owner.full_name if owner else None,
        lo_email=owner.email if owner else None,
        lo_phone=owner.phone if owner else None,
        company_name=org.name if org else None,
    )


@router.patch("/api/v1/apply/{token}")
async def update_application_by_token(
    token: str,
    data: BorrowerApplicationUpdate,
    db: Session = Depends(get_db_session()),
    request: Request = None
):
    """Update application data (borrower-facing)"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationStatus = enums['ApplicationStatus']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.expires_at and application.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=410, detail="Application link has expired")

    # Update fields — whitelist to prevent mass assignment of sensitive attrs
    _ALLOWED_UPDATE_FIELDS = {
        'current_step', 'step_data', 'completed_steps',
        'borrower_first_name', 'borrower_last_name',
        'borrower_email', 'borrower_phone',
        'has_coborrower', 'coborrower_email',
        'notes', 'time_spent_seconds',
    }
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id', 'borrower_id'}
    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field in _ALLOWED_UPDATE_FIELDS and hasattr(application, field) and field not in _protected:
            setattr(application, field, value)

    # Update status to in_progress if still draft
    if application.status == ApplicationStatus.DRAFT:
        application.status = ApplicationStatus.IN_PROGRESS

    application.last_activity_at = datetime.now(timezone.utc)
    application.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(application)

    return {"status": "success", "progress": application.progress_percentage}


@router.post("/api/v1/apply/{token}/step")
async def save_step_data(
    token: str,
    data: StepDataUpdate,
    db: Session = Depends(get_db_session()),
    request: Request = None
):
    """Save data for a specific step"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationEvent = models['ApplicationEvent']
    ApplicationStatus = enums['ApplicationStatus']
    ApplicationStep = enums['ApplicationStep']

    # Validate step name
    if data.step not in VALID_STEPS:
        raise HTTPException(status_code=400, detail=f"Invalid step name: {data.step}")

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.expires_at and application.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=410, detail="Application link has expired")

    # Update step data
    step_data = application.step_data or {}
    step_data[data.step] = data.data
    application.step_data = step_data

    # Update completed steps if marked
    if data.mark_completed:
        completed = application.completed_steps or []
        if data.step not in completed:
            completed.append(data.step)
            application.completed_steps = completed
            application.progress_percentage = calculate_progress(completed)

    # Update current step to next step
    step_order = [s.value for s in ApplicationStep]
    if data.mark_completed and data.step in step_order:
        current_idx = step_order.index(data.step)
        if current_idx < len(step_order) - 1:
            application.current_step = ApplicationStep(step_order[current_idx + 1])

    application.last_activity_at = datetime.now(timezone.utc)
    application.status = ApplicationStatus.IN_PROGRESS

    # Log event
    event = ApplicationEvent(
        application_id=application.id,
        event_type="step_saved" if not data.mark_completed else "step_completed",
        event_data={"step": data.step},
        actor_type="borrower",
        actor_email=application.borrower_email,
        step=data.step,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(event)

    db.commit()

    return {
        "status": "success",
        "step": data.step,
        "completed": data.mark_completed,
        "progress": application.progress_percentage,
        "next_step": application.current_step.value if hasattr(application.current_step, 'value') else str(application.current_step)
    }


@router.post("/api/v1/apply/{token}/prequalify", response_model=PrequalificationResponse)
async def calculate_prequalification_for_application(
    token: str,
    data: PrequalificationRequest,
    db: Session = Depends(get_db_session())
):
    """Calculate pre-qualification and save to application"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    result = calculate_prequalification(data)

    # Save to application
    application.prequalification_amount = result.max_loan_amount
    application.prequalification_rate = result.estimated_rate
    application.prequalification_monthly_payment = result.estimated_monthly_payment
    application.prequalification_data = result.dict()
    application.last_activity_at = datetime.now(timezone.utc)

    db.commit()

    return result


@router.post("/api/v1/apply/{token}/credit-auth")
async def capture_credit_authorization(
    token: str,
    data: CreditAuthCapture,
    db: Session = Depends(get_db_session()),
    request: Request = None
):
    """Capture credit authorization from borrower"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationEvent = models['ApplicationEvent']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if not data.consent_agreed:
        raise HTTPException(status_code=400, detail="Consent must be agreed to")

    # Capture authorization
    application.credit_auth_captured = True
    application.credit_auth_timestamp = datetime.now(timezone.utc)
    application.credit_auth_ip_address = request.client.host if request else None
    application.credit_auth_user_agent = request.headers.get("user-agent") if request else None
    application.credit_auth_ssn_last4 = data.ssn_last4

    # Store consent text in metadata
    meta = application.metadata or {}
    meta["credit_auth"] = {
        "consent_text": data.consent_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "has_signature": bool(data.signature_data),
    }
    application.metadata = meta

    # Log event
    event = ApplicationEvent(
        application_id=application.id,
        event_type="credit_auth_captured",
        actor_type="borrower",
        actor_email=application.borrower_email,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(event)

    db.commit()

    return {"status": "success", "captured_at": application.credit_auth_timestamp}


@router.post("/api/v1/apply/{token}/submit")
async def submit_application(
    token: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session()),
    request: Request = None
):
    """Submit the completed application"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationEvent = models['ApplicationEvent']
    Lead = models['Lead']
    LeadStage = models['LeadStage']
    User = models['User']
    ApplicationStatus = enums['ApplicationStatus']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Validate required steps are completed
    required_steps = ["personal_info", "property", "income", "credit_auth"]
    completed = application.completed_steps or []
    missing = [s for s in required_steps if s not in completed]

    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required steps: {', '.join(missing)}")

    # Check co-borrower completion if applicable
    if application.has_coborrower and not application.coborrower_completed:
        application.status = ApplicationStatus.PENDING_COBORROWER
    else:
        application.status = ApplicationStatus.SUBMITTED

    application.submitted_at = datetime.now(timezone.utc)
    application.progress_percentage = 100

    # Log event
    event = ApplicationEvent(
        application_id=application.id,
        event_type="submitted",
        actor_type="borrower",
        actor_email=application.borrower_email,
        ip_address=request.client.host if request else None,
    )
    db.add(event)

    # Update lead if linked
    _lead_stage_changed = False
    _lead_id_for_wf = None
    if application.lead_id:
        lead = db.query(Lead).filter(Lead.id == application.lead_id).first()
        if lead:
            lead.application_completed_date = datetime.now(timezone.utc)
            if lead.stage == LeadStage.NEW:
                lead.stage = LeadStage.APPLICATION
                _lead_stage_changed = True
                _lead_id_for_wf = lead.id

    db.commit()

    # Event-driven workflow enrollment if lead stage changed (eliminates 60s polling delay)
    if _lead_stage_changed and _lead_id_for_wf:
        try:
            from services.workflow_scheduler import trigger_workflow_evaluation_for_lead
            trigger_workflow_evaluation_for_lead(db, _lead_id_for_wf, 'Application')
        except Exception as wf_err:
            logger.warning(f"Workflow evaluation trigger failed for borrower app lead {_lead_id_for_wf}: {wf_err}")

    # Send notifications in background
    try:
        from services.notification_service import notification_service

        # Get LO info for notifications
        lo_name = "Your Loan Officer"
        lo_email = ""
        lo_phone = None
        if application.owner_id:
            lo = db.query(User).filter(User.id == application.owner_id).first()
            if lo:
                lo_name = f"{lo.first_name or ''} {lo.last_name or ''}".strip() or lo.email
                lo_email = lo.email
                lo_phone = getattr(lo, 'phone', None)

        borrower_name = f"{application.borrower_first_name or ''} {application.borrower_last_name or ''}".strip() or "there"

        # Send borrower confirmation email
        if application.borrower_email:
            background_tasks.add_task(
                notification_service.send_application_confirmation,
                borrower_email=application.borrower_email,
                borrower_name=borrower_name,
                application_id=str(application.id),
                lo_name=lo_name,
                lo_email=lo_email,
                lo_phone=lo_phone,
            )

        # Send borrower confirmation SMS
        if application.borrower_phone:
            background_tasks.add_task(
                notification_service.send_application_confirmation_sms,
                borrower_phone=application.borrower_phone,
                borrower_name=borrower_name,
                lo_name=lo_name,
            )

        # Alert LO about new application
        if lo_email:
            step_data = application.step_data or {}
            property_data = step_data.get("property", {})
            loan_purpose = property_data.get("loan_purpose", "purchase")
            loan_amount = property_data.get("loan_amount", 0) or application.prequalification_amount or 0

            background_tasks.add_task(
                notification_service.send_lo_new_application_alert,
                lo_email=lo_email,
                lo_name=lo_name,
                borrower_name=borrower_name,
                borrower_email=application.borrower_email,
                borrower_phone=application.borrower_phone,
                loan_purpose=loan_purpose,
                loan_amount=float(loan_amount),
                application_id=str(application.id),
            )

        logger.info(f"Notification tasks queued for application {application.id}")
    except Exception as notify_err:
        logger.warning(f"Failed to queue notifications for application {application.id}: {notify_err}")

    return {"status": "success", "application_status": application.status.value}


# ============================================================================
# Document upload endpoints
# ============================================================================

@router.post("/api/v1/apply/{token}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    token: str,
    file: UploadFile = File(...),
    category: str = Form("other"),
    description: str = Form(None),
    db: Session = Depends(get_db_session())
):
    """Upload a document to the application"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationDocument = models['ApplicationDocument']
    ApplicationEvent = models['ApplicationEvent']
    DocumentCategory = enums['DocumentCategory']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Validate file size and type
    MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
    ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: PDF and images only.")
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 20MB.")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")
    await file.seek(0)

    # Generate unique filename with validated extension
    import uuid, re
    raw_ext = file.filename.rsplit('.', 1)[-1] if '.' in (file.filename or '') else 'pdf'
    ext = raw_ext if re.match(r'^[a-zA-Z0-9]{1,10}$', raw_ext) else 'pdf'
    unique_filename = f"{uuid.uuid4()}.{ext}"

    # For now, store locally (in production, use S3)
    storage_dir = Path("uploads/applications")
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / unique_filename
    with open(storage_path, "wb") as f:
        f.write(contents)

    # Create document record
    doc = ApplicationDocument(
        application_id=application.id,
        filename=unique_filename,
        original_filename=file.filename,
        file_size=len(contents),
        mime_type=file.content_type,
        category=DocumentCategory(category) if category in [e.value for e in DocumentCategory] else DocumentCategory.MISC,
        description=description,
        storage_key=str(storage_path),
        uploaded_by="borrower",
    )

    db.add(doc)

    # Log event
    event = ApplicationEvent(
        application_id=application.id,
        event_type="document_uploaded",
        event_data={"filename": file.filename, "category": category},
        actor_type="borrower",
        actor_email=application.borrower_email,
    )
    db.add(event)

    db.commit()
    db.refresh(doc)

    return doc


@router.post("/api/v1/apply/{token}/documents/{doc_id}/analyze")
async def analyze_document(
    token: str,
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session())
):
    """Analyze a document using AI (Claude Vision)"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationDocument = models['ApplicationDocument']
    ApplicationEvent = models['ApplicationEvent']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    doc = db.query(ApplicationDocument).filter(
        ApplicationDocument.id == doc_id,
        ApplicationDocument.application_id == application.id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get borrower name for verification
    borrower_name = f"{application.borrower_first_name or ''} {application.borrower_last_name or ''}".strip()

    try:
        from services.document_analysis_service import document_analysis_service

        # Run analysis
        result = await document_analysis_service.analyze_document(
            file_path=doc.storage_key,
            claimed_type=doc.category.value if doc.category else None,
            borrower_name=borrower_name if borrower_name else None,
        )

        # Update document with analysis results
        doc.ai_analysis = result.to_dict()
        doc.ai_verified = result.verified
        doc.ai_confidence = result.confidence
        doc.ai_document_type = result.document_type
        doc.ai_extracted_data = result.extracted_data
        doc.ai_analyzed_at = datetime.now(timezone.utc)

        # Log event
        event = ApplicationEvent(
            application_id=application.id,
            event_type="document_analyzed",
            event_data={
                "doc_id": doc_id,
                "verified": result.verified,
                "confidence": result.confidence,
                "document_type": result.document_type,
                "issues_count": len(result.issues),
            },
            actor_type="system",
        )
        db.add(event)

        db.commit()

        return {
            "status": "success",
            "analysis": result.to_dict(),
        }

    except Exception as e:
        logger.error(f"Document analysis failed for doc {doc_id}: {e}")
        return {
            "status": "error",
            "message": "Document analysis failed",
        }


@router.get("/api/v1/apply/{token}/documents")
async def list_documents(
    token: str,
    db: Session = Depends(get_db_session())
):
    """List documents uploaded to an application"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationDocument = models['ApplicationDocument']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    docs = db.query(ApplicationDocument).filter(
        ApplicationDocument.application_id == application.id
    ).order_by(ApplicationDocument.created_at.desc()).all()

    return [
        {
            "id": d.id,
            "filename": d.original_filename,
            "category": d.category.value if hasattr(d.category, 'value') else str(d.category),
            "file_size": d.file_size,
            "uploaded_at": d.created_at,
            "is_verified": d.is_verified,
        }
        for d in docs
    ]


@router.delete("/api/v1/apply/{token}/documents/{doc_id}")
async def delete_document(
    token: str,
    doc_id: int,
    db: Session = Depends(get_db_session())
):
    """Delete a document from the application"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationDocument = models['ApplicationDocument']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    doc = db.query(ApplicationDocument).filter(
        ApplicationDocument.id == doc_id,
        ApplicationDocument.application_id == application.id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from storage
    if doc.storage_key:
        try:
            Path(doc.storage_key).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Failed to delete storage file in delete_document: {e}")

    db.delete(doc)
    db.commit()

    return {"status": "success"}


# ============================================================================
# AI Concierge endpoints
# ============================================================================

@router.post("/api/v1/apply/{token}/concierge")
async def concierge_conversation(
    token: str,
    data: ConciergeMessage,
    db: Session = Depends(get_db_session())
):
    """AI Concierge for conversational mortgage application"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        from services.concierge_service import concierge_service

        # Process the message
        result = await concierge_service.process_message(
            user_message=data.message,
            current_stage=data.current_stage,
            extracted_data=data.extracted_data,
            conversation_history=data.conversation_history,
        )

        # Validate and clean extracted data
        if result.get("extracted_data"):
            cleaned_data = concierge_service.validate_extracted_data(result["extracted_data"])
            result["extracted_data"] = cleaned_data

            # Merge with existing application step_data
            step_data = application.step_data or {}
            step_data.update(cleaned_data)
            application.step_data = step_data
            db.commit()

        return result

    except Exception as e:
        logger.error(f"Concierge error for application {token}: {e}")
        return {
            "response": "I apologize, but I'm experiencing technical difficulties. Please try again or switch to the traditional form.",
            "extracted_data": {},
            "next_stage": data.current_stage,
            "is_complete": False,
            "error": "Internal server error"
        }


@router.get("/api/v1/apply/{token}/concierge/status")
async def get_concierge_status(
    token: str,
    db: Session = Depends(get_db_session())
):
    """Get AI Concierge completion status"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        from services.concierge_service import concierge_service

        step_data = application.step_data or {}
        status = concierge_service.get_completion_status(step_data)

        return {
            "status": "success",
            "completion": status,
            "extracted_data": sanitize_step_data(step_data),
        }

    except Exception as e:
        logger.error(f"Concierge status error: {e}")
        return {
            "status": "error",
            "message": "Failed to retrieve concierge status"
        }


# ============================================================================
# Review Call Scheduling endpoints
# ============================================================================

@router.get("/api/v1/apply/{token}/available-slots")
async def get_available_slots(
    token: str,
    date: str,
    timezone: str = "America/New_York",
    db: Session = Depends(get_db_session())
):
    """Get available time slots for a given date"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Generate default slots (9 AM - 5 PM, excluding lunch)
    # In production, this would check the LO's calendar
    slots = []
    for hour in range(9, 18):
        if hour != 12:  # Skip lunch
            slots.append({"time": f"{hour:02d}:00", "available": True})
            if hour != 17:
                slots.append({"time": f"{hour:02d}:30", "available": True})

    return {"date": date, "timezone": timezone, "slots": slots}


@router.post("/api/v1/apply/{token}/schedule-review-call")
async def schedule_review_call(
    token: str,
    data: ReviewCallScheduleRequest,
    db: Session = Depends(get_db_session())
):
    """Schedule a mandatory review call before submission"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        from datetime import datetime as dt
        import pytz

        # Parse the scheduled time
        tz = pytz.timezone(data.timezone)
        scheduled_datetime = dt.strptime(f"{data.date} {data.time}", "%Y-%m-%d %H:%M")
        scheduled_datetime = tz.localize(scheduled_datetime)
        scheduled_utc = scheduled_datetime.astimezone(pytz.UTC)

        # Create appointment record
        appointment = {
            "application_id": application.id,
            "scheduled_at": scheduled_utc.isoformat(),
            "timezone": data.timezone,
            "contact_method": data.contact_method,
            "notes": data.notes,
            "status": "scheduled",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Update application with review call info
        application.review_call_scheduled = True
        application.review_call_scheduled_at = scheduled_utc

        # Store appointment in step_data for now
        step_data = application.step_data or {}
        step_data["review_appointment"] = appointment
        application.step_data = step_data

        db.commit()

        # Send confirmation email and SMS
        try:
            from services.notification_service import notification_service

            borrower_name = f"{application.borrower_first_name or ''} {application.borrower_last_name or ''}".strip() or "there"
            borrower_email = application.borrower_email
            borrower_phone = application.borrower_phone

            # Get LO info if available
            lo_name = "Your Loan Officer"
            lo_email = None
            if application.owner:
                lo_name = application.owner.name or lo_name
                lo_email = application.owner.email

            # Send confirmation email
            if borrower_email:
                notification_service.send_appointment_confirmation(
                    borrower_email=borrower_email,
                    borrower_name=borrower_name,
                    appointment_type="Loan Review Call",
                    appointment_time=scheduled_utc,
                    lo_name=lo_name,
                    phone_number=borrower_phone if data.contact_method == "phone" else None,
                    appointment_id=str(application.id),
                    duration_minutes=30,
                    lo_email=lo_email,
                )
                logger.info(f"Review call confirmation email sent to {mask_email(borrower_email)}")

            # Send confirmation SMS
            if borrower_phone:
                local_time = scheduled_datetime.strftime("%I:%M %p on %B %d")
                sms_message = (
                    f"Hi {borrower_name.split()[0] if borrower_name != 'there' else 'there'}, "
                    f"your loan review call with {lo_name} is confirmed for {local_time} ({data.timezone}). "
                    f"We'll {'call you' if data.contact_method == 'phone' else 'send you a meeting link'}. "
                    f"Reply STOP to opt out."
                )
                notification_service.send_sms(to_phone=borrower_phone, message=sms_message)
                logger.info(f"Review call confirmation SMS sent to {mask_phone(borrower_phone)}")

        except Exception as notif_err:
            logger.error(f"Error sending review call confirmation: {notif_err}")
            # Continue - appointment was still created

        return {
            "status": "success",
            "appointment": appointment,
            "message": f"Review call scheduled for {data.date} at {data.time} {data.timezone}"
        }

    except Exception as e:
        logger.error(f"Failed to schedule review call: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/v1/apply/{token}/review-call")
async def get_review_call(
    token: str,
    db: Session = Depends(get_db_session())
):
    """Get scheduled review call for an application"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    step_data = application.step_data or {}
    appointment = step_data.get("review_appointment")

    return {
        "has_appointment": appointment is not None,
        "appointment": appointment,
    }


# ============================================================================
# MISMO XML Export endpoints
# ============================================================================

@router.get("/api/v1/apply/{token}/export/mismo")
async def export_mismo_xml(
    token: str,
    db: Session = Depends(get_db_session())
):
    """Export application data as MISMO 3.4 XML"""
    from fastapi.responses import Response
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Only allow export for submitted or later applications
    if application.expires_at and application.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=410, detail="Application link has expired")

    submitted_statuses = {"submitted", "under_review", "approved"}
    app_status = application.status.value if hasattr(application.status, 'value') else str(application.status)
    if app_status not in submitted_statuses:
        raise HTTPException(status_code=403, detail="MISMO export is only available for submitted applications")

    try:
        from services.mismo_generator import MISMOGenerator

        generator = MISMOGenerator()

        # Merge application step_data with model fields
        data = application.step_data or {}

        # Add borrower info from model
        data["first_name"] = application.borrower_first_name
        data["last_name"] = application.borrower_last_name
        data["email"] = application.borrower_email
        data["phone"] = application.borrower_phone

        # Generate XML
        xml_content = generator.generate(data)
        filename = generator.generate_filename(str(application.id))

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-MISMO-Version": "3.4.0",
            }
        )

    except Exception as e:
        logger.error(f"MISMO export failed: {e}")
        raise HTTPException(status_code=500, detail="Export failed")


@router.get("/api/v1/admin/applications/{application_id}/export/mismo")
async def admin_export_mismo_xml(
    application_id: int,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Admin endpoint to export application as MISMO 3.4 XML"""
    from fastapi.responses import Response
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Check access (must be assigned LO or admin)
    if current_user.role != "admin" and application.assigned_to_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        from services.mismo_generator import MISMOGenerator

        generator = MISMOGenerator()

        # Merge application step_data with model fields
        data = application.step_data or {}
        data["first_name"] = application.borrower_first_name
        data["last_name"] = application.borrower_last_name
        data["email"] = application.borrower_email
        data["phone"] = application.borrower_phone

        xml_content = generator.generate(data)
        filename = generator.generate_filename(str(application.id))

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-MISMO-Version": "3.4.0",
            }
        )

    except Exception as e:
        logger.error(f"MISMO export failed: {e}")
        raise HTTPException(status_code=500, detail="Export failed")


# ============================================================================
# LO Dashboard endpoints
# ============================================================================

@router.get("/api/v1/lo/dashboard/stats")
async def get_lo_dashboard_stats(
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get LO dashboard statistics"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationStatus = enums['ApplicationStatus']

    # Get pipeline count and volume for this LO (use owner_id which is the correct field)
    pipeline_stats = db.query(
        func.count(BorrowerApplication.id).label("count"),
        func.sum(BorrowerApplication.prequalification_amount).label("volume")
    ).filter(
        BorrowerApplication.owner_id == current_user.id,
        BorrowerApplication.status.notin_([ApplicationStatus.APPROVED, ApplicationStatus.DENIED, ApplicationStatus.EXPIRED])
    ).first()

    # Get pending review count
    pending_count = db.query(func.count(BorrowerApplication.id)).filter(
        BorrowerApplication.owner_id == current_user.id,
        BorrowerApplication.status == ApplicationStatus.SUBMITTED
    ).scalar()

    # Get calls scheduled today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Count appointments (stored in step_data for now)
    calls_today = 0  # Would query appointments table in production

    return {
        "pipeline_count": pipeline_stats[0] or 0,
        "pipeline_volume": float(pipeline_stats[1] or 0),
        "pending_review": pending_count or 0,
        "calls_today": calls_today,
    }


@router.get("/api/v1/lo/applications")
async def get_lo_applications(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get applications assigned to the current LO"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationStatus = enums['ApplicationStatus']

    query = db.query(BorrowerApplication).filter(
        BorrowerApplication.owner_id == current_user.id
    )

    if status and status != "all":
        # Convert string status to enum
        try:
            status_enum = ApplicationStatus(status)
            query = query.filter(BorrowerApplication.status == status_enum)
        except ValueError:
            pass  # Invalid status, ignore filter

    total = query.count()
    applications = query.order_by(
        BorrowerApplication.updated_at.desc()
    ).offset(offset).limit(limit).all()

    # Get loan purpose from step_data if available
    def get_loan_purpose(app):
        if app.step_data and isinstance(app.step_data, dict):
            property_data = app.step_data.get('property', {})
            return property_data.get('loan_purpose', 'Purchase')
        return 'Purchase'

    return {
        "total": total,
        "applications": [
            {
                "id": app.id,
                "borrower_first_name": app.borrower_first_name,
                "borrower_last_name": app.borrower_last_name,
                "borrower_email": app.borrower_email,
                "loan_amount": float(app.prequalification_amount or 0),
                "loan_purpose": get_loan_purpose(app),
                "status": app.status.value if hasattr(app.status, 'value') else str(app.status),
                "created_at": app.created_at.isoformat() if app.created_at else None,
                "updated_at": app.updated_at.isoformat() if app.updated_at else None,
                "progress_percentage": app.progress_percentage,
            }
            for app in applications
        ],
    }


@router.get("/api/v1/lo/activity")
async def get_lo_activity(
    limit: int = 20,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get recent activity for the current LO"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    # In production, this would query an activity log table
    # For now, return recent application updates
    recent_apps = db.query(BorrowerApplication).filter(
        BorrowerApplication.owner_id == current_user.id
    ).order_by(BorrowerApplication.updated_at.desc()).limit(limit).all()

    activities = []
    for app in recent_apps:
        status_str = app.status.value if hasattr(app.status, 'value') else str(app.status)
        activities.append({
            "type": "application",
            "description": f"{app.borrower_first_name or 'Unknown'} {app.borrower_last_name or 'Borrower'} - {status_str.replace('_', ' ')}",
            "created_at": app.updated_at.isoformat() if app.updated_at else None,
            "application_id": app.id,
        })

    return {"activities": activities}


@router.post("/api/v1/lo/social/generate")
async def generate_social_content(
    data: SocialContentRequest,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Generate AI-powered social media content"""
    try:
        from services.social_content_service import social_content_service

        content = await social_content_service.generate_content(
            content_type=data.type,
            platform=data.platform,
            lo_name=current_user.full_name or current_user.email.split("@")[0],
            company_name=None,  # Could get from user profile
        )

        return {
            "status": "success",
            "content": content,
        }

    except Exception as e:
        logger.error(f"Social content generation failed: {e}")
        return {
            "status": "error",
            "message": "Content generation failed",
            "content": [],
        }


@router.get("/api/v1/lo/social/schedule-suggestions")
async def get_social_schedule_suggestions(
    platform: str = "all",
    current_user = Depends(get_current_user_dep())
):
    """Get optimal posting time suggestions"""
    from services.social_content_service import social_content_service

    if platform == "all":
        platforms = ["linkedin", "facebook", "instagram", "twitter"]
        suggestions = {
            p: social_content_service.get_posting_schedule_suggestions(p)
            for p in platforms
        }
    else:
        suggestions = {
            platform: social_content_service.get_posting_schedule_suggestions(platform)
        }

    return {"suggestions": suggestions}


# ============================================================================
# LO Application Detail Endpoints
# ============================================================================

@router.get("/api/v1/lo/applications/{application_id}")
async def get_lo_application_detail(
    application_id: int,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get detailed application information for LO view"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id,
        BorrowerApplication.owner_id == current_user.id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Extract data from step_data
    step_data = application.step_data or {}
    property_data = step_data.get('property', {})
    employment_data = step_data.get('employment', {})
    assets_data = step_data.get('assets', {})

    # Get documents count
    doc_count = db.execute(text("""
        SELECT COUNT(*) FROM application_documents WHERE application_id = :app_id
    """), {"app_id": application_id}).scalar() or 0

    # Get notes
    notes = []
    try:
        notes_result = db.execute(text("""
            SELECT id, note, created_at, created_by FROM application_notes
            WHERE application_id = :app_id ORDER BY created_at DESC
        """), {"app_id": application_id}).fetchall()
        notes = [{"id": n[0], "note": n[1], "created_at": n[2].isoformat() if n[2] else None, "created_by": n[3]} for n in notes_result]
    except Exception as e:
        logger.warning(f"Failed to fetch application notes in get_lo_application_detail: {e}")

    return {
        "id": application.id,
        "borrower_first_name": application.borrower_first_name,
        "borrower_last_name": application.borrower_last_name,
        "borrower_email": application.borrower_email,
        "borrower_phone": application.borrower_phone,
        "coborrower_first_name": application.coborrower_first_name,
        "coborrower_last_name": application.coborrower_last_name,
        "coborrower_email": application.coborrower_email,
        "has_coborrower": application.has_coborrower,
        "loan_amount": float(application.prequalification_amount or 0),
        "loan_purpose": property_data.get('loan_purpose', 'Purchase'),
        "property_type": property_data.get('property_type'),
        "property_address": property_data.get('address'),
        "property_city": property_data.get('city'),
        "property_state": property_data.get('state'),
        "property_zip": property_data.get('zip_code'),
        "occupancy_type": property_data.get('occupancy_type'),
        "status": application.status.value if hasattr(application.status, 'value') else str(application.status),
        "current_step": application.current_step,
        "progress_percentage": application.progress_percentage,
        "employment": employment_data,
        "assets_summary": {
            "total_assets": assets_data.get('total_assets', 0),
            "checking": assets_data.get('checking', 0),
            "savings": assets_data.get('savings', 0),
            "retirement": assets_data.get('retirement', 0),
        },
        "document_count": doc_count,
        "notes": notes,
        "created_at": application.created_at.isoformat() if application.created_at else None,
        "updated_at": application.updated_at.isoformat() if application.updated_at else None,
        "submitted_at": application.submitted_at.isoformat() if application.submitted_at else None,
        "timeline": [
            {"event": "Application Created", "date": application.created_at.isoformat() if application.created_at else None},
            {"event": "Last Updated", "date": application.updated_at.isoformat() if application.updated_at else None},
            {"event": "Submitted", "date": application.submitted_at.isoformat() if application.submitted_at else None},
        ],
    }


@router.put("/api/v1/lo/applications/{application_id}/status")
async def update_lo_application_status(
    application_id: int,
    data: ApplicationStatusUpdate,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Update application status"""
    models = get_models()
    enums = get_enums()
    BorrowerApplication = models['BorrowerApplication']
    ApplicationStatus = enums['ApplicationStatus']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id,
        BorrowerApplication.owner_id == current_user.id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        new_status = ApplicationStatus(data.status)
        application.status = new_status
        application.updated_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "status": "success",
            "message": f"Application status updated to {new_status.value}",
            "application_id": application_id,
            "new_status": new_status.value,
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {data.status}")


@router.post("/api/v1/lo/applications/{application_id}/notes")
async def add_lo_application_note(
    application_id: int,
    data: ApplicationNoteCreate,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Add a note to an application"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id,
        BorrowerApplication.owner_id == current_user.id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Ensure notes table exists
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS application_notes (
                id SERIAL PRIMARY KEY,
                application_id INTEGER REFERENCES borrower_applications(id),
                note TEXT NOT NULL,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to create application_notes table in add_lo_application_note: {e}")

    # Insert note
    try:
        result = db.execute(text("""
            INSERT INTO application_notes (application_id, note, created_by, created_at)
            VALUES (:app_id, :note, :user_id, :now)
            RETURNING id
        """), {
            "app_id": application_id,
            "note": data.note,
            "user_id": current_user.id,
            "now": datetime.now(timezone.utc)
        })
        db.commit()
        note_id = result.scalar()

        return {
            "status": "success",
            "note_id": note_id,
            "message": "Note added successfully",
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add note: {e}")
        raise HTTPException(status_code=500, detail="Failed to add note")


@router.get("/api/v1/lo/applications/{application_id}/documents")
async def get_lo_application_documents(
    application_id: int,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Get documents for an application"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id,
        BorrowerApplication.owner_id == current_user.id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    try:
        docs = db.execute(text("""
            SELECT id, document_type, file_name, file_url, status, uploaded_at, verified_at
            FROM application_documents
            WHERE application_id = :app_id
            ORDER BY uploaded_at DESC
        """), {"app_id": application_id}).fetchall()

        return {
            "documents": [
                {
                    "id": d[0],
                    "document_type": d[1],
                    "file_name": d[2],
                    "file_url": d[3],
                    "status": d[4],
                    "uploaded_at": d[5].isoformat() if d[5] else None,
                    "verified_at": d[6].isoformat() if d[6] else None,
                }
                for d in docs
            ],
            "total": len(docs),
        }
    except Exception as e:
        logger.error(f"Error fetching documents: {e}")
        return {"documents": [], "total": 0}


@router.get("/api/v1/lo/applications/{application_id}/export/mismo")
async def export_application_mismo(
    application_id: int,
    db: Session = Depends(get_db_session()),
    current_user = Depends(get_current_user_dep())
):
    """Export application in MISMO 3.4 XML format"""
    from fastapi.responses import Response
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == application_id,
        BorrowerApplication.owner_id == current_user.id
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    step_data = application.step_data or {}
    property_data = step_data.get('property', {})
    employment_data = step_data.get('employment', {})

    # Generate MISMO 3.4 XML
    mismo_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<MESSAGE xmlns="http://www.mismo.org/residential/2009/schemas" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <ABOUT_VERSIONS>
        <ABOUT_VERSION>
            <DataVersionIdentifier>3.4</DataVersionIdentifier>
        </ABOUT_VERSION>
    </ABOUT_VERSIONS>
    <DEAL_SETS>
        <DEAL_SET>
            <DEALS>
                <DEAL>
                    <PARTIES>
                        <PARTY>
                            <INDIVIDUAL>
                                <NAME>
                                    <FirstName>{application.borrower_first_name or ''}</FirstName>
                                    <LastName>{application.borrower_last_name or ''}</LastName>
                                </NAME>
                            </INDIVIDUAL>
                            <ROLES>
                                <ROLE>
                                    <BORROWER>
                                        <BORROWER_DETAIL>
                                            <BorrowerClassificationType>Primary</BorrowerClassificationType>
                                        </BORROWER_DETAIL>
                                    </BORROWER>
                                </ROLE>
                            </ROLES>
                            <CONTACT_POINTS>
                                <CONTACT_POINT>
                                    <CONTACT_POINT_EMAIL>
                                        <ContactPointEmailValue>{application.borrower_email or ''}</ContactPointEmailValue>
                                    </CONTACT_POINT_EMAIL>
                                </CONTACT_POINT>
                                <CONTACT_POINT>
                                    <CONTACT_POINT_TELEPHONE>
                                        <ContactPointTelephoneValue>{application.borrower_phone or ''}</ContactPointTelephoneValue>
                                    </CONTACT_POINT_TELEPHONE>
                                </CONTACT_POINT>
                            </CONTACT_POINTS>
                        </PARTY>
                    </PARTIES>
                    <LOANS>
                        <LOAN>
                            <LOAN_DETAIL>
                                <LoanPurposeType>{property_data.get('loan_purpose', 'Purchase')}</LoanPurposeType>
                            </LOAN_DETAIL>
                            <TERMS_OF_LOAN>
                                <BaseLoanAmount>{application.prequalification_amount or 0}</BaseLoanAmount>
                            </TERMS_OF_LOAN>
                        </LOAN>
                    </LOANS>
                    <COLLATERALS>
                        <COLLATERAL>
                            <SUBJECT_PROPERTY>
                                <ADDRESS>
                                    <AddressLineText>{property_data.get('address', '')}</AddressLineText>
                                    <CityName>{property_data.get('city', '')}</CityName>
                                    <StateCode>{property_data.get('state', '')}</StateCode>
                                    <PostalCode>{property_data.get('zip_code', '')}</PostalCode>
                                </ADDRESS>
                                <PROPERTY_DETAIL>
                                    <PropertyUsageType>{property_data.get('occupancy_type', 'PrimaryResidence')}</PropertyUsageType>
                                </PROPERTY_DETAIL>
                            </SUBJECT_PROPERTY>
                        </COLLATERAL>
                    </COLLATERALS>
                </DEAL>
            </DEALS>
        </DEAL_SET>
    </DEAL_SETS>
</MESSAGE>'''

    return Response(
        content=mismo_xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=application_{application_id}_mismo.xml"
        }
    )


# ============================================================================
# Co-borrower invitation endpoints
# ============================================================================

@router.post("/api/v1/apply/{token}/coborrower", response_model=CoborrowerInvitationResponse)
async def create_coborrower_invitation(
    token: str,
    data: CoborrowerInvitationCreate,
    db: Session = Depends(get_db_session())
):
    """Create a co-borrower invitation"""
    models = get_models()
    BorrowerApplication = models['BorrowerApplication']
    CoborrowerInvitation = models['CoborrowerInvitation']

    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.public_token == token
    ).first()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # Generate invitation token
    invitation_token = generate_token(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=14)

    invitation = CoborrowerInvitation(
        application_id=application.id,
        invitation_token=invitation_token,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        relationship_type=data.relationship_type,
        expires_at=expires_at,
        status="pending",
    )

    db.add(invitation)

    # Update application
    application.has_coborrower = True
    application.coborrower_email = data.email

    # Send email/SMS notification
    if data.send_email:
        try:
            from email_service import email_service
            from services.notification_service import notification_service

            borrower_name = f"{application.borrower_first_name or ''} {application.borrower_last_name or ''}".strip() or "the primary borrower"
            coborrower_name = f"{data.first_name or ''} {data.last_name or ''}".strip() or "there"
            invite_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/coborrower/{invitation_token}"

            # Send invitation email
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
                <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                    <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">

                        <div style="text-align: center; margin-bottom: 32px;">
                            <h1 style="color: #3b82f6; font-size: 28px; margin: 0;">Perennia AI</h1>
                        </div>

                        <h2 style="color: #111827; margin: 0 0 16px; font-size: 22px;">You've Been Invited as a Co-Borrower</h2>

                        <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                            Hi {coborrower_name.split()[0] if coborrower_name != 'there' else 'there'},
                        </p>

                        <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                            <strong>{borrower_name}</strong> has invited you to complete your portion of a mortgage application as a co-borrower.
                        </p>

                        <div style="text-align: center; margin: 32px 0;">
                            <a href="{invite_url}" style="display: inline-block; background: #3b82f6; color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                                Complete Your Application
                            </a>
                        </div>

                        <div style="background: #f0f9ff; border-left: 4px solid #3b82f6; padding: 16px; margin: 24px 0; border-radius: 0 8px 8px 0;">
                            <h4 style="margin: 0 0 8px 0; color: #1e40af;">What You'll Need</h4>
                            <ul style="margin: 0; padding-left: 20px; color: #4b5563;">
                                <li>Personal information (SSN, DOB, address history)</li>
                                <li>Employment and income details</li>
                                <li>Asset information (bank accounts, investments)</li>
                                <li>About 15-20 minutes to complete</li>
                            </ul>
                        </div>

                        <p style="color: #f59e0b; font-size: 14px; text-align: center; background: #fef3c7; padding: 12px 16px; border-radius: 8px;">
                            This invitation expires in <strong>14 days</strong>
                        </p>

                        <p style="color: #9ca3af; font-size: 13px; margin-top: 32px; text-align: center;">
                            If you weren't expecting this invitation, please contact {borrower_name}.
                        </p>

                    </div>
                </div>
            </body>
            </html>
            """

            plain_text = f"""Hi {coborrower_name.split()[0] if coborrower_name != 'there' else 'there'},

{borrower_name} has invited you to complete your portion of a mortgage application as a co-borrower.

Click the link below to get started:
{invite_url}

What You'll Need:
- Personal information (SSN, DOB, address history)
- Employment and income details
- Asset information (bank accounts, investments)
- About 15-20 minutes to complete

This invitation expires in 14 days.

If you weren't expecting this invitation, please contact {borrower_name}.

- The Perennia AI Team
"""

            email_sent = email_service.send_html_email(
                to_email=data.email,
                subject=f"{borrower_name} has invited you to complete a mortgage application",
                html_body=html_content,
                plain_text_body=plain_text
            )

            if email_sent:
                logger.info(f"Co-borrower invitation email sent to {mask_email(data.email)}")

            # Send SMS if phone provided
            if data.phone:
                sms_message = (
                    f"Hi {coborrower_name.split()[0] if coborrower_name != 'there' else 'there'}, "
                    f"{borrower_name} invited you as a co-borrower on their mortgage application. "
                    f"Complete your info here: {invite_url} (expires in 14 days). Reply STOP to opt out."
                )
                notification_service.send_sms(to_phone=data.phone, message=sms_message)
                logger.info(f"Co-borrower invitation SMS sent to {mask_phone(data.phone)}")

            invitation.sent_at = datetime.now(timezone.utc)
            invitation.status = "sent"

        except Exception as notif_err:
            logger.error(f"Error sending co-borrower invitation: {notif_err}")
            # Still mark as sent since we tried
            invitation.sent_at = datetime.now(timezone.utc)
            invitation.status = "sent"

    db.commit()
    db.refresh(invitation)

    return invitation


@router.get("/api/v1/coborrower/{invitation_token}")
async def get_coborrower_invitation(
    invitation_token: str,
    db: Session = Depends(get_db_session())
):
    """Get co-borrower invitation by token"""
    models = get_models()
    CoborrowerInvitation = models['CoborrowerInvitation']
    BorrowerApplication = models['BorrowerApplication']

    invitation = db.query(CoborrowerInvitation).filter(
        CoborrowerInvitation.invitation_token == invitation_token
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.expires_at and invitation.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        invitation.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Invitation has expired")

    # Mark as opened
    if not invitation.opened_at:
        invitation.opened_at = datetime.now(timezone.utc)
        invitation.status = "opened"
        db.commit()

    # Get application data
    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == invitation.application_id
    ).first()

    return {
        "invitation_id": invitation.id,
        "email": invitation.email,
        "first_name": invitation.first_name,
        "last_name": invitation.last_name,
        "relationship_type": invitation.relationship_type,
        "borrower_first_name": application.borrower_first_name if application else None,
        "borrower_last_name": application.borrower_last_name if application else None,
        "coborrower_data": invitation.coborrower_data or {},
        "status": invitation.status,
    }


@router.post("/api/v1/coborrower/{invitation_token}/save")
async def save_coborrower_data(
    invitation_token: str,
    data: Dict[str, Any],
    db: Session = Depends(get_db_session())
):
    """Save co-borrower section data"""
    models = get_models()
    CoborrowerInvitation = models['CoborrowerInvitation']

    invitation = db.query(CoborrowerInvitation).filter(
        CoborrowerInvitation.invitation_token == invitation_token
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.expires_at and invitation.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=410, detail="Invitation has expired")

    # Update invitation data
    invitation.coborrower_data = data
    invitation.status = "in_progress"
    if not invitation.started_at:
        invitation.started_at = datetime.now(timezone.utc)

    db.commit()

    return {"status": "success"}


@router.post("/api/v1/coborrower/{invitation_token}/submit")
async def submit_coborrower_section(
    invitation_token: str,
    db: Session = Depends(get_db_session()),
    request: Request = None
):
    """Submit the co-borrower section"""
    models = get_models()
    enums = get_enums()
    CoborrowerInvitation = models['CoborrowerInvitation']
    BorrowerApplication = models['BorrowerApplication']
    ApplicationStatus = enums['ApplicationStatus']

    invitation = db.query(CoborrowerInvitation).filter(
        CoborrowerInvitation.invitation_token == invitation_token
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # Mark as completed
    invitation.completed_at = datetime.now(timezone.utc)
    invitation.status = "completed"

    # Update application
    application = db.query(BorrowerApplication).filter(
        BorrowerApplication.id == invitation.application_id
    ).first()

    if application:
        application.coborrower_completed = True

        # If application was waiting for co-borrower, update status
        if application.status == ApplicationStatus.PENDING_COBORROWER:
            application.status = ApplicationStatus.SUBMITTED

    db.commit()

    return {"status": "success"}


@router.post("/api/v1/coborrower/{invitation_token}/credit-auth")
async def capture_coborrower_credit_auth(
    invitation_token: str,
    data: CreditAuthCapture,
    db: Session = Depends(get_db_session()),
    request: Request = None
):
    """Capture credit authorization from co-borrower"""
    models = get_models()
    CoborrowerInvitation = models['CoborrowerInvitation']

    invitation = db.query(CoborrowerInvitation).filter(
        CoborrowerInvitation.invitation_token == invitation_token
    ).first()

    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if not data.consent_agreed:
        raise HTTPException(status_code=400, detail="Consent must be agreed to")

    invitation.credit_auth_captured = True
    invitation.credit_auth_timestamp = datetime.now(timezone.utc)
    invitation.credit_auth_ip_address = request.client.host if request else None

    db.commit()

    return {"status": "success", "captured_at": invitation.credit_auth_timestamp}


# ============================================================================
# Public pre-qualification calculator (no token needed)
# ============================================================================

@router.post("/api/v1/prequalify", response_model=PrequalificationResponse)
async def calculate_public_prequalification(data: PrequalificationRequest):
    """Public pre-qualification calculator (no auth required)"""
    return calculate_prequalification(data)
