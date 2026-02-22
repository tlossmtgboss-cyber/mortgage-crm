"""
Public Routes for Registration, Email Verification, and Onboarding

These endpoints don't require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from jose import jwt
import logging
import os

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

# Lazy import for get_db to avoid circular dependency with main.py
# Other model imports (User, Subscription, etc.) are done inside each function that needs them
def get_db():
    """Wrapper for get_db to avoid circular import with main.py."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# from integrations.stripe_service import StripeService  # Disabled for now
from integrations.email_service import EmailService, VerificationTokenService

logger = logging.getLogger(__name__)

router = APIRouter()

# JWT Configuration (duplicated to avoid circular import)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict):
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Initialize services
# Stripe service disabled for now - using mock
class MockStripeService:
    """Mock Stripe service when Stripe is not configured"""

    PLANS = {
        "starter": {
            "name": "Starter",
            "price_monthly": 99,
            "stripe_price_id": "price_starter",
            "features": [
                "Up to 5 team members",
                "1,000 leads per month",
                "Basic AI assistant",
                "Email support",
                "Calendar integration",
                "Task automation"
            ],
            "user_limit": 5
        },
        "professional": {
            "name": "Professional",
            "price_monthly": 199,
            "stripe_price_id": "price_professional",
            "features": [
                "Up to 15 team members",
                "Unlimited leads",
                "Advanced AI assistant with workflow automation",
                "Priority support",
                "Calendar + Email + Teams integration",
                "Custom workflows",
                "SMS notifications",
                "Analytics & reporting"
            ],
            "user_limit": 15
        },
        "enterprise": {
            "name": "Enterprise",
            "price_monthly": 399,
            "stripe_price_id": "price_enterprise",
            "features": [
                "Unlimited team members",
                "Unlimited leads",
                "Full AI agent capabilities",
                "24/7 dedicated support",
                "All integrations",
                "Custom AI training",
                "White-label options",
                "API access",
                "Custom reporting"
            ],
            "user_limit": 999
        }
    }

    def get_plan_info(self, plan):
        return self.PLANS.get(plan)

    def create_customer(self, *args, **kwargs):
        return None

    def create_subscription(self, *args, **kwargs):
        return None

    def get_all_plans(self):
        return [
            {
                "key": key,
                **plan_info
            }
            for key, plan_info in self.PLANS.items()
        ]

    def verify_webhook_signature(self, *args, **kwargs):
        return None

stripe_service = MockStripeService()
email_service = EmailService()


# ============================================================================
# QUICK TEST/DEMO USER SETUP
# ============================================================================

@router.post("/api/v1/create-demo-user")
async def create_demo_user(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db),
):
    """
    Create or reset a demo user for testing. Requires ADMIN_API_KEY.
    Password is read from DEMO_USER_PASSWORD env var (defaults to random).
    """
    import os as _os
    import secrets as _secrets
    _admin_api_key = _os.getenv("ADMIN_API_KEY")
    if not _admin_api_key or admin_key != _admin_api_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Lazy imports to avoid circular dependency
    from database.models import User, Subscription, OnboardingProgress
    from main import get_password_hash

    demo_email = "demo@test.com"
    demo_password = _os.getenv("DEMO_USER_PASSWORD") or _secrets.token_urlsafe(16)

    # Delete existing demo user if exists
    existing = db.query(User).filter(User.email == demo_email).first()
    if existing:
        db.delete(existing)
        db.commit()

    # Create demo user
    demo_user = User(
        email=demo_email,
        hashed_password=get_password_hash(demo_password),
        first_name="Demo",
        last_name="User",
        email_verified=True,
        is_active=True,
        role="loan_officer",
        user_metadata={
            "company_name": "Demo Company",
            "phone": "555-0000",
            "plan": "professional",
            "demo_mode": True
        }
    )
    db.add(demo_user)
    db.commit()
    db.refresh(demo_user)

    # Create demo subscription
    demo_subscription = Subscription(
        user_id=demo_user.id,
        stripe_customer_id="demo_customer",
        stripe_subscription_id="demo_subscription",
        status="active",
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=365),
        trial_end=None
    )
    db.add(demo_subscription)

    # Create onboarding progress (completed)
    onboarding = OnboardingProgress(
        user_id=demo_user.id,
        current_step=5,
        steps_completed=[1, 2, 3, 4, 5],
        is_complete=True,
        completed_at=datetime.utcnow()
    )
    db.add(onboarding)

    db.commit()

    return {
        "message": "Demo user created successfully",
        "email": demo_email,
        "password": demo_password,
        "note": "Use these credentials to login"
    }


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: Optional[str] = None
    phone: Optional[str] = None
    plan: str = "professional"  # starter, professional, enterprise


class EmailVerification(BaseModel):
    token: str


class OnboardingStepUpdate(BaseModel):
    step: int
    data: Dict


class TeamMemberCreate(BaseModel):
    name: str
    role: str
    responsibilities: str
    email: Optional[str] = None


class WorkflowCreate(BaseModel):
    name: str
    description: str
    steps: List[Dict]
    assigned_roles: List[str]


# ============================================================================
# REGISTRATION & EMAIL VERIFICATION
# ============================================================================

@router.get("/api/v1/migrate-database")
async def migrate_database(db: Session = Depends(get_db)):
    """Add missing onboarding_completed column to users table"""
    try:
        from sqlalchemy import text

        # Check if column exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users'
            AND column_name='onboarding_completed'
        """))

        if result.fetchone() is None:
            # Add the column
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE
            """))
            db.commit()
            return {
                "status": "success",
                "message": "Added onboarding_completed column to users table"
            }
        else:
            return {
                "status": "already_exists",
                "message": "Column already exists, no migration needed"
            }

    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "error": "Internal server error"
        }

@router.get("/api/v1/register-test")
async def register_test():
    """Test endpoint - DISABLED"""
    raise HTTPException(
        status_code=403,
        detail="Registration testing is disabled."
    )

@router.post("/api/v1/register")
async def register_user(registration: UserRegistration, db: Session = Depends(get_db)):
    """
    Register a new user - DISABLED

    Registration is disabled. Only @cmgfi.com users can access this system.
    Contact your system administrator for account access.
    """

    raise HTTPException(
        status_code=403,
        detail="Registration is disabled. This system is restricted to authorized @cmgfi.com users only. Please contact your administrator for access."
    )

    # Original registration code disabled below:
    """
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == registration.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Validate plan (just to ensure valid plan key)
        plan_info = stripe_service.get_plan_info(registration.plan)
        if not plan_info:
            # Default to professional if invalid plan
            registration.plan = "professional"
            plan_info = stripe_service.get_plan_info("professional")

        logger.info("Starting registration for new user")

        # Create user in database (auto-verified and activated)
        _name_parts = (registration.full_name or '').strip().split(' ', 1)
        db_user = User(
            email=registration.email,
            hashed_password=get_password_hash(registration.password),
            first_name=_name_parts[0] if _name_parts else '',
            last_name=_name_parts[1] if len(_name_parts) > 1 else '',
            email_verified=True,  # Auto-verify all accounts
            is_active=True,  # Auto-activate all accounts
            user_metadata={
                "company_name": registration.company_name or "",
                "phone": registration.phone or "",
                "plan": registration.plan,
                "dev_mode": True
            }
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        logger.info(f"User created with ID: {db_user.id}")

        # Create mock subscription record
        try:
            db_subscription = Subscription(
                user_id=db_user.id,
                stripe_customer_id=f"dev_customer_{db_user.id}",
                stripe_subscription_id=f"dev_sub_{db_user.id}",
                status="active",
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=365),
                trial_end=None
            )
            db.add(db_subscription)
            db.commit()
            logger.info(f"Subscription created for user {db_user.id}")
        except Exception as sub_error:
            logger.warning(f"Subscription creation failed (non-critical): {str(sub_error)}")
            # Continue even if subscription fails

        # Create onboarding progress
        try:
            onboarding = OnboardingProgress(
                user_id=db_user.id,
                current_step=1,
                steps_completed=[]
            )
            db.add(onboarding)
            db.commit()
            logger.info(f"Onboarding progress created for user {db_user.id}")
        except Exception as onboard_error:
            logger.warning(f"Onboarding creation failed (non-critical): {str(onboard_error)}")
            # Continue even if onboarding progress creation fails

        # Generate access token for immediate login
        try:
            access_token = create_access_token(data={"sub": db_user.email})
        except Exception as token_error:
            logger.error(f"Token generation failed: {str(token_error)}")
            raise HTTPException(status_code=500, detail="Failed to generate authentication token")

        logger.info("Registration successful for new user")

        return {
            "message": "Registration successful! Redirecting to dashboard...",
            "user_id": db_user.id,
            "email": db_user.email,
            "full_name": db_user.full_name,
            "access_token": access_token,
            "token_type": "bearer",
            "dev_mode": True,
            "redirect_to": "/dashboard"
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Registration failed with error: {str(e)}")
        logger.error(f"Full traceback: {error_details}")

        # Try to cleanup user if created
        try:
            if 'db_user' in locals() and db_user and hasattr(db_user, 'id'):
                db.query(User).filter(User.id == db_user.id).delete()
                db.commit()
                logger.info(f"Cleaned up user after failed registration")
        except Exception as cleanup_error:
            logger.error(f"Cleanup failed: {str(cleanup_error)}")

        # Return user-friendly error message
        raise HTTPException(
            status_code=500,
            detail="We encountered an error creating your account. Please try again or contact support if the issue persists."
        )
    """


@router.post("/api/v1/verify-email")
async def verify_email(verification: EmailVerification, db: Session = Depends(get_db)):
    """
    Verify user's email address with token
    """
    # Lazy import to avoid circular dependency
    from database.models import User

    user_id = VerificationTokenService.verify_token(db, verification.token)

    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    # Update user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.email_verified = True
    user.is_active = True
    db.commit()

    # Send welcome email
    email_service.send_welcome_email(user.email, user.full_name)

    logger.info(f"Email verified for user ID: {user.id}")

    return {
        "message": "Email verified successfully!",
        "email": user.email,
        "redirect_to": "/onboarding"
    }


@router.post("/api/v1/resend-verification")
async def resend_verification(email: EmailStr, db: Session = Depends(get_db)):
    """
    Resend verification email
    """
    # Lazy import to avoid circular dependency
    from database.models import User

    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.email_verified:
        raise HTTPException(status_code=400, detail="Email already verified")

    # Generate new token
    verification_token = VerificationTokenService.create_verification_token(
        db, user.id, user.email
    )

    # Send email
    email_service.send_verification_email(
        user.email,
        verification_token,
        user.full_name
    )

    return {"message": "Verification email sent"}


# ============================================================================
# SUBSCRIPTION PLANS
# ============================================================================

@router.get("/api/v1/plans")
async def get_subscription_plans():
    """
    Get all available subscription plans
    """
    return {
        "plans": stripe_service.get_all_plans()
    }


# ============================================================================
# STRIPE WEBHOOKS
# ============================================================================

@router.post("/api/v1/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Stripe webhook events
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe_service.verify_webhook_signature(payload, sig_header)
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {str(e)}")
        raise HTTPException(status_code=400, detail="Bad request")

    # Handle different event types
    event_type = event['type']

    if event_type == 'checkout.session.completed':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_checkout_completed(event['data']['object'], db)

    elif event_type == 'customer.subscription.created':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_subscription_created(event['data']['object'], db)

    elif event_type == 'customer.subscription.updated':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_subscription_updated(event['data']['object'], db)

    elif event_type == 'customer.subscription.deleted':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_subscription_deleted(event['data']['object'], db)

    elif event_type == 'invoice.payment_succeeded':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_payment_succeeded(event['data']['object'], db)

    elif event_type == 'invoice.payment_failed':
        from integrations.stripe_service import StripeWebhookHandlers
        StripeWebhookHandlers.handle_payment_failed(event['data']['object'], db)

    return {"status": "success"}


# ============================================================================
# ONBOARDING
# ============================================================================

@router.get("/api/v1/onboarding/progress")
async def get_onboarding_progress(user_id: int, db: Session = Depends(get_db)):
    """
    Get onboarding progress for a user
    """
    # Lazy import to avoid circular dependency
    from database.models import OnboardingProgress

    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding progress not found")

    return {
        "current_step": progress.current_step,
        "steps_completed": progress.steps_completed,
        "is_complete": progress.is_complete,
        "team_members_added": progress.team_members_added,
        "workflows_generated": progress.workflows_generated
    }


@router.post("/api/v1/onboarding/step")
async def update_onboarding_step(
    user_id: int,
    step_update: OnboardingStepUpdate,
    db: Session = Depends(get_db)
):
    """
    Update onboarding step progress
    """
    # Lazy import to avoid circular dependency
    from database.models import OnboardingProgress

    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding progress not found")

    # Update step
    if step_update.step not in progress.steps_completed:
        progress.steps_completed.append(step_update.step)

    # Move to next step
    if step_update.step >= progress.current_step:
        progress.current_step = min(step_update.step + 1, 5)

    # Check if all steps completed
    if len(progress.steps_completed) >= 5:
        progress.is_complete = True
        progress.completed_at = datetime.utcnow()

    progress.updated_at = datetime.utcnow()
    db.commit()

    return {
        "message": "Onboarding step updated",
        "current_step": progress.current_step,
        "is_complete": progress.is_complete
    }


@router.post("/api/v1/onboarding/upload-documents")
async def upload_onboarding_documents(
    user_id: int,
    files: List[str],  # File paths or base64 encoded content
    db: Session = Depends(get_db)
):
    """
    Handle document uploads during onboarding

    In production, this would use file upload and storage (S3, etc.)
    """
    # Lazy import to avoid circular dependency
    from database.models import OnboardingProgress

    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress:
        raise HTTPException(status_code=404, detail="Onboarding progress not found")

    # Store document references
    if not progress.uploaded_documents:
        progress.uploaded_documents = []

    progress.uploaded_documents.extend(files)
    progress.updated_at = datetime.utcnow()
    db.commit()

    return {
        "message": f"{len(files)} documents uploaded successfully",
        "total_documents": len(progress.uploaded_documents)
    }


@router.post("/api/v1/onboarding/team-member")
async def add_team_member(
    user_id: int,
    team_member: TeamMemberCreate,
    db: Session = Depends(get_db)
):
    """
    Add a team member during onboarding
    """
    # Lazy import to avoid circular dependency
    from database.models import TeamMember, OnboardingProgress

    db_member = TeamMember(
        user_id=user_id,
        name=team_member.name,
        role=team_member.role,
        responsibilities=team_member.responsibilities,
        email=team_member.email,
        status="pending"
    )
    db.add(db_member)

    # Update onboarding progress
    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()
    if progress:
        progress.team_members_added += 1

    db.commit()

    return {
        "message": "Team member added",
        "member_id": db_member.id
    }


def _get_default_workflows():
    """Return default workflows when AI generation fails"""
    return [
        {
            "name": "Lead to Application Workflow",
            "description": "Automated workflow for moving leads through the application process",
            "steps": [
                {"order": 1, "name": "Initial Contact", "assigned_role": "Loan Officer"},
                {"order": 2, "name": "Pre-qualification", "assigned_role": "Loan Officer"},
                {"order": 3, "name": "Application Submission", "assigned_role": "Processor"},
                {"order": 4, "name": "Document Collection", "assigned_role": "Processor"},
                {"order": 5, "name": "Underwriting", "assigned_role": "Underwriter"}
            ]
        },
        {
            "name": "Client Onboarding Workflow",
            "description": "Workflow for onboarding new clients",
            "steps": [
                {"order": 1, "name": "Welcome Email", "assigned_role": "System"},
                {"order": 2, "name": "Initial Consultation", "assigned_role": "Loan Officer"},
                {"order": 3, "name": "Document Request", "assigned_role": "Processor"},
                {"order": 4, "name": "Credit Pull", "assigned_role": "Loan Officer"}
            ]
        }
    ]


@router.post("/api/v1/onboarding/generate-workflows")
async def generate_workflows(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Use AI to generate workflows from uploaded documents and team structure

    This is a placeholder - actual implementation would use OpenAI to parse
    documents and generate custom workflows
    """
    # Lazy import to avoid circular dependency
    from database.models import TeamMember, OnboardingProgress, Workflow

    # Get team members
    team_members = db.query(TeamMember).filter(TeamMember.user_id == user_id).all()

    # Get uploaded documents from onboarding progress
    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress or not progress.uploaded_documents:
        raise HTTPException(status_code=400, detail="No documents uploaded for workflow generation")

    # Generate workflows using Claude AI
    import httpx
    import json

    team_roles = list(set([m.role for m in team_members])) if team_members else ["Loan Officer", "Processor"]
    documents_info = json.dumps(progress.uploaded_documents) if isinstance(progress.uploaded_documents, list) else str(progress.uploaded_documents)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [{
                        "role": "user",
                        "content": f"""Based on the following mortgage company information, generate 2-3 custom workflows.

Team Roles Available: {', '.join(team_roles)}
Uploaded Documents: {documents_info[:2000]}

Generate workflows as a JSON array. Each workflow should have:
- name: descriptive workflow name
- description: brief description
- steps: array of {{ "order": number, "name": step name, "assigned_role": role from team }}

Focus on mortgage industry workflows like:
- Lead qualification and conversion
- Loan processing pipeline
- Document collection
- Closing coordination

Return ONLY valid JSON, no markdown or explanation."""
                    }],
                },
            )

            if response.status_code == 200:
                result = response.json()
                ai_response = result["content"][0]["text"]

                # Try to parse AI-generated workflows
                try:
                    # Clean up response if needed
                    ai_response = ai_response.strip()
                    if ai_response.startswith("```"):
                        ai_response = ai_response.split("```")[1]
                        if ai_response.startswith("json"):
                            ai_response = ai_response[4:]
                    sample_workflows = json.loads(ai_response)
                except json.JSONDecodeError:
                    logger.warning("AI returned invalid JSON, using default workflows")
                    sample_workflows = _get_default_workflows()
            else:
                logger.warning(f"AI API returned {response.status_code}, using default workflows")
                sample_workflows = _get_default_workflows()

    except Exception as e:
        logger.error(f"AI workflow generation failed: {e}, using defaults")
        sample_workflows = _get_default_workflows()

    created_workflows = []
    for workflow_data in sample_workflows:
        db_workflow = Workflow(
            user_id=user_id,
            name=workflow_data["name"],
            description=workflow_data["description"],
            steps=workflow_data["steps"],
            assigned_roles=[step["assigned_role"] for step in workflow_data["steps"]],
            automation_rules={},
            created_by_ai=True
        )
        db.add(db_workflow)
        created_workflows.append(db_workflow)

    # Update progress
    if progress:
        progress.workflows_generated = len(created_workflows)
        progress.updated_at = datetime.utcnow()

    db.commit()

    return {
        "message": f"{len(created_workflows)} workflows generated",
        "workflows": [
            {
                "id": w.id,
                "name": w.name,
                "description": w.description,
                "steps_count": len(w.steps)
            }
            for w in created_workflows
        ]
    }


# ============================================================================
# PUBLIC QUESTIONNAIRES (Landing Pages)
# ============================================================================

class MortgagePlannerSubmission(BaseModel):
    """Schema for Mortgage Planner Questionnaire submission"""
    name: str
    email: EmailStr
    phone: str
    isVeteran: str
    hasOwnedHomeBefore: str
    currentHousingStatus: str
    previousMortgageType: Optional[str] = None
    currentMonthlyPayment: Optional[str] = None
    mortgageImportance: List[str]
    personalGoals: List[str]
    financialPhilosophy: str
    hasTaxDeferredRetirement: str
    hasFinancialPlanner: str
    financialPlannerRating: Optional[str] = None
    hasAccountant: str
    accountantRating: Optional[str] = None
    hasLifeInsuranceAgent: str
    lifeInsuranceAgentRating: Optional[str] = None
    hasEstatePlanner: str
    estatePlannerRating: Optional[str] = None
    loan_officer_id: Optional[str] = None
    source: Optional[str] = None
    submitted_at: Optional[str] = None


@router.post("/api/v1/questionnaire/mortgage-planner")
async def submit_mortgage_planner_questionnaire(
    submission: MortgagePlannerSubmission,
    db: Session = Depends(get_db)
):
    """
    Handle Mortgage Planning Questionnaire submissions.

    This endpoint:
    1. Creates or updates a lead with the questionnaire data
    2. Creates circle_contacts for trusted professionals the borrower has
    3. Creates tasks to get introductions to excellent-rated professionals
    4. Creates tasks to make referrals when borrower needs professionals
    """
    from database.models import Lead, Task
    from sqlalchemy import text

    try:
        # Determine the loan officer ID (default to demo user ID 1 if not specified)
        loan_officer_id = int(submission.loan_officer_id) if submission.loan_officer_id else 1

        # Check if lead already exists by email
        existing_lead = db.query(Lead).filter(Lead.email == submission.email).first()

        if existing_lead:
            # Update existing lead
            lead = existing_lead
            lead.name = submission.name
            lead.phone = submission.phone
        else:
            # Create new lead
            from database.enums import LeadStage
            lead = Lead(
                name=submission.name,
                email=submission.email,
                phone=submission.phone,
                owner_id=loan_officer_id,
                source="Mortgage Planner Questionnaire",
                stage=LeadStage.NEW
            )
            db.add(lead)
            db.flush()  # Get the lead ID

        # Store questionnaire responses in lead metadata
        lead.notes = f"""
MORTGAGE PLANNER QUESTIONNAIRE RESPONSES
========================================
Submitted: {submission.submitted_at or datetime.utcnow().isoformat()}

PERSONAL INFORMATION
- Name: {submission.name}
- Email: {submission.email}
- Phone: {submission.phone}
- Veteran: {submission.isVeteran}

HOME OWNERSHIP HISTORY
- Previously owned home: {submission.hasOwnedHomeBefore}
- Current status: {submission.currentHousingStatus}
- Previous mortgage type: {submission.previousMortgageType or 'N/A'}
- Current monthly payment: ${submission.currentMonthlyPayment or 'N/A'}

MORTGAGE PRIORITIES
{chr(10).join(['- ' + p for p in submission.mortgageImportance])}

PERSONAL GOALS
{chr(10).join(['- ' + g for g in submission.personalGoals])}

FINANCIAL PHILOSOPHY
- {submission.financialPhilosophy}

PROFESSIONAL NETWORK (Circle of Cashflow)
- Tax-deferred retirement plan: {submission.hasTaxDeferredRetirement}
- Financial Planner: {submission.hasFinancialPlanner} (Rating: {submission.financialPlannerRating or 'N/A'})
- Accountant: {submission.hasAccountant} (Rating: {submission.accountantRating or 'N/A'})
- Life Insurance Agent: {submission.hasLifeInsuranceAgent} (Rating: {submission.lifeInsuranceAgentRating or 'N/A'})
- Estate Planner: {submission.hasEstatePlanner} (Rating: {submission.estatePlannerRating or 'N/A'})
"""

        # Track professionals for circle contacts and tasks
        missing_professionals = []
        excellent_professionals = []
        circle_contacts_created = []

        # Professional mapping: (has_field, rating_field, type_name, icon)
        professionals = [
            ('hasFinancialPlanner', 'financialPlannerRating', 'Financial Advisor', '💼'),
            ('hasAccountant', 'accountantRating', 'Accountant', '📊'),
            ('hasLifeInsuranceAgent', 'lifeInsuranceAgentRating', 'Life Insurance Agent', '🛡️'),
            ('hasEstatePlanner', 'estatePlannerRating', 'Estate Planner', '📜'),
        ]

        for has_field, rating_field, type_name, icon in professionals:
            has_professional = getattr(submission, has_field)
            rating = getattr(submission, rating_field)

            if has_professional == 'No':
                # Borrower needs this professional - create referral task
                missing_professionals.append(type_name)
            elif has_professional == 'Yes':
                # Skip circle_contacts creation for now - table may not exist
                # If rated Excellent, create task to get introduction
                if rating == 'Excellent':
                    excellent_professionals.append(type_name)

        # Create tasks using raw SQL to avoid column mismatch issues
        # (The ORM model may have columns that don't exist in production DB)

        # Create tasks for excellent-rated professionals (get introductions)
        for prof_type in excellent_professionals:
            intro_description = f"""{submission.name} has rated their {prof_type} as "Excellent" in their Mortgage Planner Questionnaire.

ACTION REQUIRED:
Ask {submission.name} for an introduction to their {prof_type}. This is a great opportunity to:
- Build your professional network
- Potentially receive referrals
- Create reciprocal referral relationships

CONTACT INFO:
- Client: {submission.name}
- Email: {submission.email}
- Phone: {submission.phone}

Suggested approach: Mention that you work with many clients who need a {prof_type}, and you'd love to connect with professionals your clients trust.
"""
            db.execute(text("""
                INSERT INTO tasks (title, description, priority, status, owner_id, lead_id, due_date, related_type, related_contact_name, created_at, updated_at)
                VALUES (:title, :description, :priority, :status, :owner_id, :lead_id, :due_date, :related_type, :related_contact_name, NOW(), NOW())
            """), {
                "title": f"Get Introduction to {submission.name}'s {prof_type}",
                "description": intro_description,
                "priority": "high",
                "status": "pending",
                "owner_id": loan_officer_id,
                "lead_id": lead.id,
                "due_date": datetime.utcnow() + timedelta(days=7),
                "related_type": "introduction_request",
                "related_contact_name": submission.name
            })

        # Create tasks for missing professionals (make referrals)
        if missing_professionals:
            referral_description = f"""{submission.name} needs the following professionals based on their Mortgage Planner Questionnaire:

PROFESSIONALS NEEDED:
{chr(10).join(['- ' + p for p in missing_professionals])}

ACTION REQUIRED:
Connect {submission.name} with trusted partners from your network. This builds:
- Client loyalty and trust
- Reciprocal referral relationships with partners
- Complete client service experience

CONTACT INFO:
- Client: {submission.name}
- Email: {submission.email}
- Phone: {submission.phone}

Track which partners you introduce and follow up on the outcomes for your Circle of Cashflow records.
"""
            db.execute(text("""
                INSERT INTO tasks (title, description, priority, status, owner_id, lead_id, due_date, related_type, related_contact_name, created_at, updated_at)
                VALUES (:title, :description, :priority, :status, :owner_id, :lead_id, :due_date, :related_type, :related_contact_name, NOW(), NOW())
            """), {
                "title": f"Make Referrals for {submission.name}",
                "description": referral_description,
                "priority": "medium",
                "status": "pending",
                "owner_id": loan_officer_id,
                "lead_id": lead.id,
                "due_date": datetime.utcnow() + timedelta(days=3),
                "related_type": "referral_opportunity",
                "related_contact_name": submission.name
            })

        # Create review task for questionnaire
        review_description = f"""Review {submission.name}'s Mortgage Planner Questionnaire responses.

CONTACT INFO:
- Email: {submission.email}
- Phone: {submission.phone}

KEY PRIORITIES:
{chr(10).join(['- ' + p for p in submission.mortgageImportance[:3]])}

FINANCIAL PHILOSOPHY: {submission.financialPhilosophy}

CIRCLE OF CASHFLOW STATUS:
- Excellent-rated professionals to get introductions: {len(excellent_professionals)}
- Missing professionals to refer: {len(missing_professionals)}
- Circle contacts created: {len(circle_contacts_created)}
"""
        db.execute(text("""
            INSERT INTO tasks (title, description, priority, status, owner_id, lead_id, due_date, related_type, related_contact_name, created_at, updated_at)
            VALUES (:title, :description, :priority, :status, :owner_id, :lead_id, :due_date, :related_type, :related_contact_name, NOW(), NOW())
        """), {
            "title": f"Review Questionnaire - {submission.name}",
            "description": review_description,
            "priority": "high",
            "status": "pending",
            "owner_id": loan_officer_id,
            "lead_id": lead.id,
            "due_date": datetime.utcnow() + timedelta(days=1),
            "related_type": "questionnaire",
            "related_contact_name": submission.name
        })

        db.commit()

        logger.info(f"Mortgage Planner Questionnaire submitted for {submission.name} (Lead ID: {lead.id})")
        logger.info(f"  - Circle contacts created: {circle_contacts_created}")
        logger.info(f"  - Introduction tasks for: {excellent_professionals}")
        logger.info(f"  - Referral opportunities: {missing_professionals}")

        return {
            "success": True,
            "message": "Questionnaire submitted successfully",
            "lead_id": lead.id,
            "circle_contacts_created": circle_contacts_created,
            "introduction_opportunities": excellent_professionals,
            "referral_opportunities": missing_professionals
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error processing Mortgage Planner Questionnaire: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to process questionnaire. Please try again."
        )


# ============================================================================
# PUBLIC PARTNER SEARCH (for borrower intake forms)
# ============================================================================

class PartnerSearchResult(BaseModel):
    """Public partner info for autocomplete"""
    id: int
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    partner_type: Optional[str] = None


@router.get("/api/v1/public/partners/search", response_model=List[PartnerSearchResult])
async def search_partners_public(
    q: str = "",
    partner_type: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Public endpoint to search referral partners by name/company for borrower intake forms.
    This allows applicants to find and select their real estate agent from the CRM database.

    Parameters:
    - q: Search query (matches name, company, or email)
    - partner_type: Optional filter by type (e.g., "Realtor", "Builder", "Insurance Agent")
    - limit: Maximum results to return (default 10)
    """
    try:
        from database.models import ReferralPartner
        from sqlalchemy import or_, func

        # Include active partners and those with null/unknown status
        query = db.query(ReferralPartner).filter(
            or_(
                ReferralPartner.status == "active",
                ReferralPartner.status.is_(None),
                ReferralPartner.status == ""
            )
        )

        # Filter by partner type if specified
        if partner_type:
            query = query.filter(
                func.lower(ReferralPartner.type).contains(partner_type.lower())
            )

        # Search by name, company, or email if query provided
        if q and len(q) >= 2:
            search_term = q.lower()
            query = query.filter(
                or_(
                    func.lower(ReferralPartner.name).contains(search_term),
                    func.lower(ReferralPartner.company).contains(search_term),
                    func.lower(ReferralPartner.email).contains(search_term),
                    func.lower(ReferralPartner.contact_name).contains(search_term)
                )
            )

        # Order by name and limit results
        partners = query.order_by(ReferralPartner.name).limit(limit).all()

        # Return sanitized results (only public info)
        return [
            PartnerSearchResult(
                id=p.id,
                name=p.name or p.contact_name or "Unknown",
                company=p.company,
                email=p.email,
                phone=p.phone,
                partner_type=p.type
            )
            for p in partners
        ]

    except Exception as e:
        logger.error(f"Error searching partners: {str(e)}")
        # Return empty list on error (don't fail the form)
        return []


@router.get("/api/v1/public/partners/realtors", response_model=List[PartnerSearchResult])
async def get_realtors_public(
    q: str = "",
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Public endpoint to search specifically for realtors/real estate agents.
    Now also includes all active partners with empty/unknown types to be more inclusive.
    """
    try:
        from database.models import ReferralPartner
        from sqlalchemy import or_, func

        # Include realtor-type partners AND partners with empty/unknown types
        query = db.query(ReferralPartner).filter(
            or_(
                ReferralPartner.status == "active",
                ReferralPartner.status.is_(None)
            ),
            or_(
                func.lower(ReferralPartner.type).contains("realtor"),
                func.lower(ReferralPartner.type).contains("real estate"),
                func.lower(ReferralPartner.type).contains("agent"),
                ReferralPartner.type.is_(None),
                ReferralPartner.type == "",
                func.lower(ReferralPartner.type) == "other"
            )
        )

        # Search by name, company, or email if query provided
        if q and len(q) >= 2:
            search_term = q.lower()
            query = query.filter(
                or_(
                    func.lower(ReferralPartner.name).contains(search_term),
                    func.lower(ReferralPartner.company).contains(search_term),
                    func.lower(ReferralPartner.contact_name).contains(search_term)
                )
            )

        partners = query.order_by(ReferralPartner.name).limit(limit).all()

        return [
            PartnerSearchResult(
                id=p.id,
                name=p.name or p.contact_name or "Unknown",
                company=p.company,
                email=p.email,
                phone=p.phone,
                partner_type=p.type
            )
            for p in partners
        ]

    except Exception as e:
        logger.error(f"Error searching realtors: {str(e)}")
        return []


# ============================================================================
# ACCOUNT VERIFICATION ENDPOINTS
# ============================================================================

class ResendEmailRequest(BaseModel):
    email: EmailStr
    user_id: Optional[int] = None


class SendPhoneCodeRequest(BaseModel):
    phone: str
    method: str = "text"  # "text" or "email"
    user_id: Optional[int] = None


class VerifyPhoneRequest(BaseModel):
    phone: str
    code: str
    user_id: Optional[int] = None


# Store verification codes in memory (in production, use Redis or database)
verification_codes: Dict[str, Dict] = {}


@router.post("/api/v1/verification/resend-email")
async def resend_email_verification(
    request: ResendEmailRequest,
    db: Session = Depends(get_db)
):
    """
    Resend email verification link
    """
    try:
        import random
        import string

        # Generate verification token
        token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))

        # Store token (expires in 24 hours)
        verification_codes[f"email_{request.email}"] = {
            "token": token,
            "expires": datetime.utcnow() + timedelta(hours=24),
            "type": "email"
        }

        # Send actual verification email
        from services.notification_service import NotificationService
        notification_service = NotificationService()

        verification_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/verify-email?token={token}"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: #f8f9fa; border-radius: 8px; padding: 30px; text-align: center;">
                <h2 style="color: #333;">Verify Your Email</h2>
                <p style="color: #666;">Please click the button below to verify your email address.</p>
                <a href="{verification_url}"
                   style="display: inline-block; background: #218D8D; color: white; padding: 12px 30px;
                          border-radius: 6px; text-decoration: none; margin: 20px 0;">
                    Verify Email
                </a>
                <p style="color: #999; font-size: 12px; margin-top: 20px;">
                    This link will expire in 24 hours.
                </p>
            </div>
        </body>
        </html>
        """

        result = notification_service.send_email(
            to_email=request.email,
            subject="Verify Your Email Address",
            html_content=html_content
        )

        logger.info(f"Email verification sent: {result}")

        return {
            "success": result.get("success", False),
            "message": "Verification email sent" if result.get("success") else "Failed to send verification email"
        }

    except Exception as e:
        logger.error(f"Error resending email verification: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send verification email")


@router.post("/api/v1/verification/send-phone-code")
async def send_phone_verification_code(
    request: SendPhoneCodeRequest,
    db: Session = Depends(get_db)
):
    """
    Send phone verification code via SMS or email
    """
    try:
        import random

        # Generate 6-digit code
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])

        # Store code (expires in 10 minutes)
        verification_codes[f"phone_{request.phone}"] = {
            "code": code,
            "expires": datetime.utcnow() + timedelta(minutes=10),
            "method": request.method
        }

        # Send actual SMS or email with code
        from services.notification_service import NotificationService
        notification_service = NotificationService()

        if request.method == "text":
            # Send SMS
            message = f"Your verification code is: {code}. This code expires in 10 minutes."
            result = notification_service.send_sms(
                to_phone=request.phone,
                message=message
            )
        else:
            # Send via email (method == "email")
            # Would need email address - for now just log
            logger.info(f"Phone verification code sent to {mask_phone(request.phone)}")
            result = {"success": True, "dry_run": True}

        logger.info(f"Phone verification sent to {mask_phone(request.phone)}: {result}")

        return {
            "success": result.get("success", False),
            "message": f"Verification code sent via {request.method}" if result.get("success") else "Failed to send verification code"
        }

    except Exception as e:
        logger.error(f"Error sending phone verification: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send verification code")


@router.post("/api/v1/verification/verify-phone")
async def verify_phone_code(
    request: VerifyPhoneRequest,
    db: Session = Depends(get_db)
):
    """
    Verify phone with the submitted code
    """
    try:
        stored = verification_codes.get(f"phone_{request.phone}")

        if not stored:
            raise HTTPException(status_code=400, detail="No verification code found. Please request a new code.")

        if datetime.utcnow() > stored["expires"]:
            # Clean up expired code
            del verification_codes[f"phone_{request.phone}"]
            raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new code.")

        if stored["code"] != request.code:
            raise HTTPException(status_code=400, detail="Invalid verification code")

        # Code verified - clean up
        del verification_codes[f"phone_{request.phone}"]

        # Update user's phone verification status if user_id provided
        if request.user_id:
            from models import User
            user = db.query(User).filter(User.id == request.user_id).first()
            if user:
                user.phone_verified = True
                user.phone_verified_at = datetime.utcnow()
                db.commit()

        return {
            "success": True,
            "message": "Phone verified successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying phone: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to verify phone")


@router.get("/api/v1/verification/check-email/{token}")
async def check_email_verification(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Check if email verification token is valid (called when user clicks email link)
    """
    try:
        # Find token in verification_codes
        for key, data in verification_codes.items():
            import hmac as _hmac
            if key.startswith("email_") and _hmac.compare_digest(data.get("token") or "", token):
                if datetime.utcnow() > data["expires"]:
                    del verification_codes[key]
                    return {"valid": False, "message": "Token expired"}

                # Mark email as verified
                email = key.replace("email_", "")
                del verification_codes[key]

                # Update user if found
                from models import User
                user = db.query(User).filter(User.email == email).first()
                if user:
                    user.email_verified = True
                    user.email_verified_at = datetime.utcnow()
                    db.commit()

                return {"valid": True, "email": email, "message": "Email verified"}

        return {"valid": False, "message": "Invalid token"}

    except Exception as e:
        logger.error(f"Error checking email verification: {str(e)}")
        return {"valid": False, "message": "Verification failed"}


# debug/token-info endpoint REMOVED — was unauthenticated and exposed
# token metadata (workspace, scope, expiry) to anyone with a token value.
