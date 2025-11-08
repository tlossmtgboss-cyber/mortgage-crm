"""
Public Routes for Registration, Email Verification, and Onboarding

These endpoints don't require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from jose import jwt
import logging
import os

from main import (
    get_db, User, Subscription, OnboardingProgress, EmailVerificationToken,
    TeamMember, Workflow, get_password_hash
)
# from integrations.stripe_service import StripeService  # Disabled for now
from integrations.email_service import EmailService, VerificationTokenService

logger = logging.getLogger(__name__)

router = APIRouter()

# JWT Configuration (duplicated to avoid circular import)
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
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
async def create_demo_user(db: Session = Depends(get_db)):
    """
    Create or reset a demo user for testing
    Email: demo@test.com
    Password: demo123
    """
    demo_email = "demo@test.com"

    # Delete existing demo user if exists
    existing = db.query(User).filter(User.email == demo_email).first()
    if existing:
        db.delete(existing)
        db.commit()

    # Create demo user
    demo_user = User(
        email=demo_email,
        hashed_password=get_password_hash("demo123"),
        full_name="Demo User",
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
        "password": "demo123",
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

@router.post("/api/v1/register")
async def register_user(registration: UserRegistration, db: Session = Depends(get_db)):
    """
    Register a new user - PAYMENT BYPASSED FOR ALL USERS

    Flow:
    1. Validate email not already registered
    2. Create user in database (auto-verified and activated)
    3. Create mock subscription record
    4. Create onboarding progress
    5. Generate JWT token and return for immediate login
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

        logger.info(f"Starting registration for: {registration.email}")

        # Create user in database (auto-verified and activated)
        db_user = User(
            email=registration.email,
            hashed_password=get_password_hash(registration.password),
            full_name=registration.full_name,
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

        logger.info(f"Registration successful for: {registration.email}")

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
        logger.error(f"Registration failed with error: {str(e)}")
        # Try to cleanup user if created
        try:
            if 'db_user' in locals() and db_user and hasattr(db_user, 'id'):
                db.query(User).filter(User.id == db_user.id).delete()
                db.commit()
                logger.info(f"Cleaned up user after failed registration")
        except Exception as cleanup_error:
            logger.error(f"Cleanup failed: {str(cleanup_error)}")

        # Return user-friendly error
        raise HTTPException(
            status_code=500,
            detail="We encountered an error creating your account. Please try again or contact support if the issue persists."
        )


@router.post("/api/v1/verify-email")
async def verify_email(verification: EmailVerification, db: Session = Depends(get_db)):
    """
    Verify user's email address with token
    """
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

    logger.info(f"Email verified for user: {user.email}")

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
        raise HTTPException(status_code=400, detail=str(e))

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
    # Get team members
    team_members = db.query(TeamMember).filter(TeamMember.user_id == user_id).all()

    # Get uploaded documents from onboarding progress
    progress = db.query(OnboardingProgress).filter(
        OnboardingProgress.user_id == user_id
    ).first()

    if not progress or not progress.uploaded_documents:
        raise HTTPException(status_code=400, detail="No documents uploaded for workflow generation")

    # TODO: Implement AI workflow generation using OpenAI
    # This would parse the documents and create custom workflows

    # For now, create sample workflows
    sample_workflows = [
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
