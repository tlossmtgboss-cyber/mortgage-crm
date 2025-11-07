"""
Public Routes for Registration, Email Verification, and Onboarding

These endpoints don't require authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, List
from datetime import datetime
import logging

from main import (
    get_db, User, Subscription, OnboardingProgress, EmailVerificationToken,
    TeamMember, Workflow, get_password_hash
)
from integrations.stripe_service import StripeService
from integrations.email_service import EmailService, VerificationTokenService

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
stripe_service = StripeService()
email_service = EmailService()


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
    Register a new user with Stripe subscription

    Flow:
    1. Validate email not already registered
    2. Create Stripe customer
    3. Create user in database (unverified)
    4. Create Stripe subscription with trial
    5. Send verification email
    6. Return user info and client secret for payment setup
    """

    # Check if user already exists
    existing_user = db.query(User).filter(User.email == registration.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate plan
    plan_info = stripe_service.get_plan_info(registration.plan)
    if not plan_info:
        raise HTTPException(status_code=400, detail="Invalid subscription plan")

    try:
        # Create Stripe customer
        stripe_customer = stripe_service.create_customer(
            email=registration.email,
            name=registration.full_name,
            metadata={
                "company": registration.company_name,
                "phone": registration.phone
            }
        )

        # Create user in database (unverified)
        db_user = User(
            email=registration.email,
            hashed_password=get_password_hash(registration.password),
            full_name=registration.full_name,
            email_verified=False,
            is_active=False,  # Activate after email verification
            user_metadata={
                "company_name": registration.company_name,
                "phone": registration.phone,
                "plan": registration.plan
            }
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        # Create Stripe subscription with trial
        stripe_subscription = stripe_service.create_subscription(
            customer_id=stripe_customer.id,
            price_id=plan_info["stripe_price_id"],
            trial_days=14
        )

        # Save subscription to database
        db_subscription = Subscription(
            user_id=db_user.id,
            plan_name=registration.plan,
            stripe_customer_id=stripe_customer.id,
            stripe_subscription_id=stripe_subscription.id,
            status="trialing",
            current_period_start=datetime.fromtimestamp(stripe_subscription.current_period_start),
            current_period_end=datetime.fromtimestamp(stripe_subscription.current_period_end),
            trial_end=datetime.fromtimestamp(stripe_subscription.trial_end) if stripe_subscription.trial_end else None
        )
        db.add(db_subscription)

        # Create onboarding progress
        onboarding = OnboardingProgress(
            user_id=db_user.id,
            current_step=1,
            steps_completed=[]
        )
        db.add(onboarding)

        db.commit()

        # Generate and send verification email
        verification_token = VerificationTokenService.create_verification_token(
            db, db_user.id, registration.email
        )
        email_service.send_verification_email(
            registration.email,
            verification_token,
            registration.full_name
        )

        logger.info(f"User registered: {registration.email}, subscription: {stripe_subscription.id}")

        # Get client secret for payment setup
        client_secret = None
        if stripe_subscription.latest_invoice:
            if hasattr(stripe_subscription.latest_invoice, 'payment_intent'):
                client_secret = stripe_subscription.latest_invoice.payment_intent.client_secret

        return {
            "message": "Registration successful. Please check your email to verify your account.",
            "user_id": db_user.id,
            "email": db_user.email,
            "subscription_id": stripe_subscription.id,
            "client_secret": client_secret,
            "trial_end": stripe_subscription.trial_end
        }

    except Exception as e:
        logger.error(f"Registration failed: {str(e)}")
        # Cleanup if something failed
        if db_user and db_user.id:
            db.delete(db_user)
            db.commit()
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


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
