"""
Onboarding Extended Routes

This module contains extended onboarding endpoints including:
1. Main onboarding flow endpoints (start, progress, step completion)
2. Email and SMS verification endpoints
3. Workflow stages endpoints
4. Permission system seed data function
5. Employee invite and onboarding API endpoints
6. AI quick actions endpoints

These routes are separated from main.py to improve code organization.
"""

import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from utils.pii_mask import mask_email, mask_phone

logger = logging.getLogger(__name__)

try:
    from middleware.rate_limiter import rate_limit, ip_key
except ImportError:
    logger.warning("Rate limiter unavailable for onboarding routes")

    def rate_limit(**kwargs):
        """No-op fallback when rate limiter is unavailable."""
        def decorator(func):
            return func
        return decorator

    def ip_key(request):
        return "unknown"


def _extract_token(request) -> str:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Not authenticated")


# Main onboarding router with /api/v1/onboarding prefix
router = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding Extended"])

# Workflow stages router
workflow_router = APIRouter(prefix="/api/v1/workflow-stages", tags=["Workflow Stages"])

# Admin/user onboarding router for employee invites
admin_router = APIRouter(tags=["Admin Onboarding"])

# AI quick actions router
ai_router = APIRouter(prefix="/api/v1/ai", tags=["AI Quick Actions"])


# =============================================================================
# PYDANTIC SCHEMAS (specific to these endpoints)
# =============================================================================

class EmployeeInviteCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    job_title: Optional[str] = Field(None, max_length=100)
    permission_role: str = Field(default="sales", max_length=50)
    branch_id: Optional[int] = None
    page_permissions: Optional[List[dict]] = None
    responsibilities: Optional[List[str]] = None


class InviteAcceptRequest(BaseModel):
    token: str
    password: str


# =============================================================================
# RUNTIME IMPORTS (to avoid circular imports)
# =============================================================================

def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'OnboardingProgress': main.OnboardingProgress,
        'OnboardingError': main.OnboardingError,
        'EmployeeInvite': main.EmployeeInvite,
        'InviteStatus': main.InviteStatus,
        'CRMPage': main.CRMPage,
        'RolePagePermission': main.RolePagePermission,
        'UserPagePermission': main.UserPagePermission,
        'AIQuickAction': main.AIQuickAction,
        'AIQuickActionRole': main.AIQuickActionRole,
        'Responsibility': main.Responsibility,
        'RoleResponsibility': main.RoleResponsibility,
        'UserResponsibility': main.UserResponsibility,
        'PermissionLevel': main.PermissionLevel,
        'Branch': main.Branch,
        'Lead': main.Lead,
        'Loan': main.Loan,
        'LoanStage': main.LoanStage,
    }


def get_schemas():
    """Get Pydantic schemas at runtime to avoid circular imports"""
    from schemas.onboarding import (
        Step1Data,
        OnboardingProgressResponse,
        SendVerificationRequest,
        VerifyCodeRequest,
    )
    return {
        'Step1Data': Step1Data,
        'OnboardingProgressResponse': OnboardingProgressResponse,
        'SendVerificationRequest': SendVerificationRequest,
        'VerifyCodeRequest': VerifyCodeRequest,
    }


def get_auth_deps():
    """Get authentication dependencies at runtime"""
    import main
    return {
        'get_current_user': main.get_current_user,
        'get_current_user_flexible': main.get_current_user_flexible,
        'create_access_token': main.create_access_token,
        'pwd_context': main.pwd_context,
    }


def get_onboarding_crud():
    """Get onboarding CRUD functions at runtime"""
    import main
    return main.onboarding_crud


# =============================================================================
# ONBOARDING ENDPOINTS
# =============================================================================

@router.post("/start")
async def start_onboarding(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Initialize onboarding for a new user
    Creates OnboardingProgress record if it doesn't exist
    """
    models = get_models()
    auth = get_auth_deps()
    User = models['User']
    OnboardingProgress = models['OnboardingProgress']

    # Get current user
    import main
    current_user = await main.get_current_user_flexible(request, db)

    try:
        # Check if onboarding already exists
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if progress:
            return {
                "message": "Onboarding already started",
                "current_step": progress.current_step,
                "progress_id": progress.id
            }

        # Create new onboarding progress
        new_progress = OnboardingProgress(
            user_id=current_user.id,
            current_step=1
        )
        db.add(new_progress)
        db.commit()
        db.refresh(new_progress)

        logger.info(f"Started onboarding for user {current_user.id}")
        return {
            "message": "Onboarding started successfully",
            "current_step": 1,
            "progress_id": new_progress.id
        }

    except Exception as e:
        logger.error(f"Start onboarding error for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/progress")
async def get_onboarding_progress(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get current onboarding progress for the authenticated user
    """
    models = get_models()
    schemas = get_schemas()
    OnboardingProgress = models['OnboardingProgress']
    OnboardingProgressResponse = schemas['OnboardingProgressResponse']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    try:
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if not progress:
            raise HTTPException(
                status_code=404,
                detail="Onboarding not started. Call /api/v1/onboarding/start first."
            )

        return progress

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get onboarding progress error for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/resume")
async def should_resume_onboarding(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Check if user should resume onboarding (incomplete onboarding exists)
    """
    models = get_models()
    OnboardingProgress = models['OnboardingProgress']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    try:
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if not progress:
            return {"should_resume": False, "current_step": None}

        if progress.completed_at:
            return {"should_resume": False, "current_step": None, "completed": True}

        return {
            "should_resume": True,
            "current_step": progress.current_step,
            "last_updated": progress.last_updated
        }

    except Exception as e:
        logger.error(f"Check resume onboarding error for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/step-1/save")
async def save_step_1(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Save Step 1 data (registration information)
    """
    models = get_models()
    schemas = get_schemas()
    OnboardingProgress = models['OnboardingProgress']
    Step1Data = schemas['Step1Data']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    # Parse request body manually to use Step1Data schema
    from fastapi import Request
    # Note: This endpoint needs data parameter - handled via request body

    try:
        # This needs to be called with data in request body
        # For now, return instruction
        raise HTTPException(
            status_code=400,
            detail="This endpoint requires Step1Data in request body"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save Step 1 error for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/auto-save")
async def auto_save_step(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Auto-save any step's data (called every 30 seconds)
    """
    models = get_models()
    OnboardingProgress = models['OnboardingProgress']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    try:
        data = await request.json()
        step_number = data.get("step_number")
        step_data = data.get("data")

        if not step_number or not step_data:
            raise HTTPException(status_code=400, detail="step_number and data are required")

        # Get onboarding progress
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if not progress:
            raise HTTPException(status_code=404, detail="Onboarding not started")

        # Save to appropriate step data column
        step_column = f"step_{step_number}_data"
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
        if hasattr(progress, step_column) and step_column not in _protected:
            setattr(progress, step_column, step_data)
            progress.last_updated = datetime.now(timezone.utc)
            db.commit()

            return {"message": f"Step {step_number} auto-saved successfully"}
        else:
            raise HTTPException(status_code=400, detail=f"Invalid step number: {step_number}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auto-save error for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/step/{step_number}/complete")
async def complete_step(
    step_number: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Mark a step as complete and advance to next step
    """
    models = get_models()
    OnboardingProgress = models['OnboardingProgress']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    try:
        if step_number < 1 or step_number > 10:
            raise HTTPException(status_code=400, detail="Step number must be between 1 and 10")

        # Get onboarding progress
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()

        if not progress:
            raise HTTPException(status_code=404, detail="Onboarding not started")

        # Verify step data exists
        step_column = f"step_{step_number}_data"
        if not getattr(progress, step_column, None):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot complete step {step_number}: no data saved"
            )

        # Advance to next step
        if step_number == progress.current_step:
            if step_number < 10:
                progress.current_step = step_number + 1
            else:
                # Mark onboarding as complete
                progress.completed_at = datetime.now(timezone.utc)
                current_user.onboarding_completed = True

        progress.last_updated = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"User {current_user.id} completed step {step_number}")

        return {
            "message": f"Step {step_number} completed successfully",
            "current_step": progress.current_step,
            "is_complete": progress.completed_at is not None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Complete step error for user {current_user.id}, step {step_number}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/step-1/send-email-verification")
async def send_email_verification(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Send email verification code
    """
    models = get_models()
    schemas = get_schemas()
    SendVerificationRequest = schemas['SendVerificationRequest']
    onboarding_crud = get_onboarding_crud()

    import main
    current_user = await main.get_current_user_flexible(request, db)

    # Note: This needs request body with SendVerificationRequest schema
    # For the full implementation, the request parameter should be added

    try:
        email = current_user.email

        if not email:
            raise HTTPException(status_code=400, detail="Email is required")

        # Check rate limiting
        recent_count = onboarding_crud.count_recent_verifications(
            db, current_user.id, "email", hours=1
        )
        if recent_count >= 5:
            raise HTTPException(
                status_code=429,
                detail="Too many verification attempts. Please try again in 1 hour."
            )

        # Create verification token
        token = onboarding_crud.create_verification_token(
            db, current_user.id, "email"
        )

        # Send actual verification email
        try:
            from email_service import email_service

            user_name = current_user.full_name or email.split('@')[0]

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

                        <h2 style="color: #111827; margin: 0 0 16px; font-size: 22px;">Verify Your Email</h2>

                        <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                            Hi {user_name},
                        </p>

                        <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                            Use the verification code below to verify your email address:
                        </p>

                        <div style="background: #f3f4f6; border-radius: 12px; padding: 24px; margin: 24px 0; text-align: center;">
                            <p style="margin: 0 0 8px; color: #6b7280; font-size: 14px;">Your Verification Code</p>
                            <p style="margin: 0; color: #111827; font-size: 32px; font-weight: 700; letter-spacing: 8px; font-family: monospace;">
                                {token.token}
                            </p>
                        </div>

                        <p style="color: #6b7280; font-size: 14px; text-align: center;">
                            This code expires in 10 minutes.
                        </p>

                        <p style="color: #9ca3af; font-size: 13px; margin-top: 32px; text-align: center;">
                            If you didn't request this code, you can safely ignore this email.
                        </p>

                    </div>
                </div>
            </body>
            </html>
            """

            plain_text = f"""Hi {user_name},

Use this verification code to verify your email address:

{token.token}

This code expires in 10 minutes.

If you didn't request this code, you can safely ignore this email.

- The Perennia AI Team
"""

            email_sent = email_service.send_html_email(
                to_email=email,
                subject="Your Perennia AI Verification Code",
                html_body=html_content,
                plain_text_body=plain_text
            )

            if email_sent:
                logger.info(f"Email verification code sent to {mask_email(email)} for user {current_user.id}")
            else:
                logger.warning(f"Failed to send email verification to {mask_email(email)}, but code was created")

        except Exception as email_err:
            logger.error(f"Error sending verification email: {email_err}")
            # Continue anyway - code was created

        return {
            "message": "Verification code sent to email",
            "expires_at": token.expires_at
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Send email verification error for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/step-1/verify-email")
async def verify_email(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Verify email with 6-digit code
    """
    models = get_models()
    schemas = get_schemas()
    OnboardingProgress = models['OnboardingProgress']
    OnboardingError = models['OnboardingError']
    VerifyCodeRequest = schemas['VerifyCodeRequest']
    onboarding_crud = get_onboarding_crud()

    import main
    current_user = await main.get_current_user_flexible(request, db)

    try:
        body = await request.json()
        code = body.get("code", "")

        # Verify token
        token = onboarding_crud.verify_token(
            db, current_user.id, code, "email"
        )

        if not token:
            # Log error
            error = OnboardingError(
                user_id=current_user.id,
                error_code="OB-01-001",
                step_number=1,
                error_message="Invalid or expired email verification code",
                error_context={"code": code},
                user_action="retry"
            )
            db.add(error)
            db.commit()

            raise HTTPException(
                status_code=400,
                detail="Invalid or expired verification code"
            )

        # Mark email as verified
        current_user.email_verified_at = datetime.now(timezone.utc)
        current_user.email_verified = True

        # Update step 1 data if exists
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()
        if progress and progress.step_1_data:
            step_1_data = progress.step_1_data
            step_1_data["email_verified"] = True
            progress.step_1_data = step_1_data
            progress.last_updated = datetime.now(timezone.utc)

        db.commit()

        logger.info(f"Email verified for user {current_user.id}")
        return {"message": "Email verified successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify email error for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/step-1/send-sms-verification")
async def send_sms_verification(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Send SMS verification code
    """
    models = get_models()
    onboarding_crud = get_onboarding_crud()

    import main
    current_user = await main.get_current_user_flexible(request, db)

    try:
        phone = current_user.phone

        if not phone:
            raise HTTPException(status_code=400, detail="Phone number is required")

        # Check rate limiting (stricter for SMS)
        recent_count = onboarding_crud.count_recent_verifications(
            db, current_user.id, "sms", hours=1
        )
        if recent_count >= 5:
            raise HTTPException(
                status_code=429,
                detail="Too many SMS attempts. Please try again in 1 hour."
            )

        # Create verification token
        token = onboarding_crud.create_verification_token(
            db, current_user.id, "sms"
        )

        # Send actual SMS with verification code
        try:
            from services.notification_service import notification_service

            user_name = current_user.full_name.split()[0] if current_user.full_name else "there"

            sms_message = (
                f"Hi {user_name}, your Perennia AI verification code is: {token.token}. "
                f"This code expires in 10 minutes."
            )

            sms_result = notification_service.send_sms(
                to_phone=phone,
                message=sms_message
            )

            if sms_result.get("success"):
                logger.info(f"SMS verification code sent to {mask_phone(phone)} for user {current_user.id}")
            else:
                logger.warning(f"Failed to send SMS verification to {mask_phone(phone)}: {sms_result.get('error')}")

        except Exception as sms_err:
            logger.error(f"Error sending verification SMS: {sms_err}")
            # Continue anyway - code was created

        return {
            "message": "Verification code sent via SMS",
            "expires_at": token.expires_at
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Send SMS verification error for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/step-1/verify-sms")
async def verify_sms(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Verify phone with 6-digit code
    """
    models = get_models()
    OnboardingProgress = models['OnboardingProgress']
    OnboardingError = models['OnboardingError']
    onboarding_crud = get_onboarding_crud()

    import main
    current_user = await main.get_current_user_flexible(request, db)

    try:
        body = await request.json()
        code = body.get("code", "")

        # Verify token
        token = onboarding_crud.verify_token(
            db, current_user.id, code, "sms"
        )

        if not token:
            # Log error
            error = OnboardingError(
                user_id=current_user.id,
                error_code="OB-01-002",
                step_number=1,
                error_message="Invalid or expired SMS verification code",
                error_context={"code": code},
                user_action="retry"
            )
            db.add(error)
            db.commit()

            raise HTTPException(
                status_code=400,
                detail="Invalid or expired verification code"
            )

        # Mark phone as verified
        current_user.phone_verified_at = datetime.now(timezone.utc)

        # Update step 1 data if exists
        progress = db.query(OnboardingProgress).filter(
            OnboardingProgress.user_id == current_user.id
        ).first()
        if progress and progress.step_1_data:
            step_1_data = progress.step_1_data
            step_1_data["phone_verified"] = True
            progress.step_1_data = step_1_data
            progress.last_updated = datetime.now(timezone.utc)

        db.commit()

        logger.info(f"Phone verified for user {current_user.id}")
        return {"message": "Phone verified successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify SMS error for user {current_user.id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# WORKFLOW STAGES ENDPOINTS
# =============================================================================

@workflow_router.get("")
async def get_workflow_stages(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all workflow stages with their tasks"""
    import main
    current_user = await main.get_current_user_flexible(request, db)

    # Default workflow stages configuration
    stages = {
        "lead": {
            "name": "Lead",
            "description": "Initial contact and qualification workflow",
            "color": "#3b82f6",
            "tasks": [
                {"id": 1, "title": "Initial Contact", "description": "Make first contact with lead", "order": 1, "auto_trigger": "on_lead_create", "days_offset": 0},
                {"id": 2, "title": "Send Introduction Email", "description": "Send welcome email with information", "order": 2, "auto_trigger": "after_previous", "days_offset": 0},
                {"id": 3, "title": "Schedule Discovery Call", "description": "Set up initial consultation", "order": 3, "auto_trigger": "after_previous", "days_offset": 1},
                {"id": 4, "title": "Pre-Qualification Check", "description": "Verify basic qualification criteria", "order": 4, "auto_trigger": "after_previous", "days_offset": 0},
                {"id": 5, "title": "Collect Documents", "description": "Request income, assets, and ID documents", "order": 5, "auto_trigger": "after_previous", "days_offset": 1},
                {"id": 6, "title": "Credit Pull Authorization", "description": "Get authorization for credit check", "order": 6, "auto_trigger": "after_previous", "days_offset": 0},
                {"id": 7, "title": "Generate Pre-Approval Letter", "description": "Create pre-approval documentation", "order": 7, "auto_trigger": "after_previous", "days_offset": 1},
                {"id": 8, "title": "Convert to Active Loan", "description": "Move to active loan processing", "order": 8, "auto_trigger": "manual", "days_offset": 0}
            ]
        },
        "active_loan": {
            "name": "Active Loan",
            "description": "Loan processing and underwriting workflow",
            "color": "#10b981",
            "tasks": [
                {"id": 9, "title": "Application Submitted", "description": "Formal loan application received", "order": 1, "auto_trigger": "on_conversion", "days_offset": 0},
                {"id": 10, "title": "Order Appraisal", "description": "Request property appraisal", "order": 2, "auto_trigger": "after_previous", "days_offset": 1},
                {"id": 11, "title": "Title Search", "description": "Order title search and insurance", "order": 3, "auto_trigger": "after_previous", "days_offset": 0},
                {"id": 12, "title": "Submit to Underwriting", "description": "Package file for underwriter review", "order": 4, "auto_trigger": "after_previous", "days_offset": 2},
                {"id": 13, "title": "Address Conditions", "description": "Clear underwriting conditions", "order": 5, "auto_trigger": "on_conditions", "days_offset": 0},
                {"id": 14, "title": "Final Approval", "description": "Obtain clear to close", "order": 6, "auto_trigger": "after_previous", "days_offset": 3},
                {"id": 15, "title": "Schedule Closing", "description": "Coordinate closing date and location", "order": 7, "auto_trigger": "after_previous", "days_offset": 1},
                {"id": 16, "title": "Closing Day", "description": "Execute closing documents", "order": 8, "auto_trigger": "on_closing_date", "days_offset": 0},
                {"id": 17, "title": "Fund Loan", "description": "Wire funds and record documents", "order": 9, "auto_trigger": "after_previous", "days_offset": 1},
                {"id": 18, "title": "Move to Portfolio", "description": "Transfer to servicing/portfolio", "order": 10, "auto_trigger": "after_previous", "days_offset": 3}
            ]
        },
        "portfolio": {
            "name": "Portfolio",
            "description": "Post-closing servicing and retention workflow",
            "color": "#8b5cf6",
            "tasks": [
                {"id": 19, "title": "Welcome to Portfolio", "description": "Send post-closing welcome package", "order": 1, "auto_trigger": "on_portfolio_add", "days_offset": 0},
                {"id": 20, "title": "30-Day Check-In", "description": "First payment follow-up call", "order": 2, "auto_trigger": "scheduled", "days_offset": 30},
                {"id": 21, "title": "90-Day Review", "description": "Ensure smooth servicing transition", "order": 3, "auto_trigger": "scheduled", "days_offset": 90},
                {"id": 22, "title": "Annual Review", "description": "Yearly financial checkup", "order": 4, "auto_trigger": "annual", "days_offset": 365},
                {"id": 23, "title": "Refinance Opportunity Check", "description": "Review for refinance potential", "order": 5, "auto_trigger": "rate_trigger", "days_offset": 0},
                {"id": 24, "title": "Birthday Outreach", "description": "Send birthday greeting", "order": 6, "auto_trigger": "birthday", "days_offset": 0},
                {"id": 25, "title": "Loan Anniversary", "description": "Celebrate loan anniversary", "order": 7, "auto_trigger": "anniversary", "days_offset": 0},
                {"id": 26, "title": "Referral Request", "description": "Ask for referrals at key moments", "order": 8, "auto_trigger": "milestone", "days_offset": 0}
            ]
        }
    }

    # Load user customizations if authenticated
    if current_user:
        try:
            for stage_key in stages.keys():
                settings_key = f"workflow_tasks_{stage_key}"
                result = db.execute(text("""
                    SELECT setting_value FROM user_settings
                    WHERE user_id = :user_id AND setting_key = :key
                """), {"user_id": current_user.id, "key": settings_key}).fetchone()

                if result and result[0]:
                    custom_tasks = json.loads(result[0])
                    if custom_tasks:
                        stages[stage_key]["tasks"] = custom_tasks
        except Exception as e:
            logger.warning(f"Could not load user workflow settings: {e}")

    return {"stages": stages}


@workflow_router.get("/{stage_key}/team-members")
async def get_workflow_stage_team_members(
    stage_key: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get team members with their workflow progress for a specific stage"""
    models = get_models()
    User = models['User']
    Lead = models['Lead']
    Loan = models['Loan']
    LoanStage = models['LoanStage']

    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    # Map stage to query criteria
    stage_map = {
        "lead": {"model": Lead, "status_field": "stage", "name": "lead"},
        "active_loan": {"model": Loan, "status_field": "stage", "name": "loan"},
        "portfolio": {"model": None, "status_field": None, "name": "client"}
    }

    if stage_key not in stage_map:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage_key}")

    # Get all users (loan officers, processors, etc.)
    users = db.query(User).filter(User.is_active == True).all()

    team_members = []

    # Define tasks for each stage
    stage_tasks = {
        "lead": [
            {"id": 1, "title": "Initial Contact"},
            {"id": 2, "title": "Send Introduction Email"},
            {"id": 3, "title": "Schedule Discovery Call"},
            {"id": 4, "title": "Pre-Qualification Check"},
            {"id": 5, "title": "Collect Documents"},
            {"id": 6, "title": "Credit Pull Authorization"},
            {"id": 7, "title": "Generate Pre-Approval Letter"},
            {"id": 8, "title": "Convert to Active Loan"}
        ],
        "active_loan": [
            {"id": 9, "title": "Application Submitted"},
            {"id": 10, "title": "Order Appraisal"},
            {"id": 11, "title": "Title Search"},
            {"id": 12, "title": "Submit to Underwriting"},
            {"id": 13, "title": "Address Conditions"},
            {"id": 14, "title": "Final Approval"},
            {"id": 15, "title": "Schedule Closing"},
            {"id": 16, "title": "Closing Day"},
            {"id": 17, "title": "Fund Loan"},
            {"id": 18, "title": "Move to Portfolio"}
        ],
        "portfolio": [
            {"id": 19, "title": "Welcome to Portfolio"},
            {"id": 20, "title": "30-Day Check-In"},
            {"id": 21, "title": "90-Day Review"},
            {"id": 22, "title": "Annual Review"},
            {"id": 23, "title": "Refinance Opportunity Check"},
            {"id": 24, "title": "Birthday Outreach"},
            {"id": 25, "title": "Loan Anniversary"},
            {"id": 26, "title": "Referral Request"}
        ]
    }

    for user in users:
        # Count items for this user based on stage
        if stage_key == "lead":
            count = db.query(Lead).filter(Lead.owner_id == user.id).count()
        elif stage_key == "active_loan":
            count = db.query(Loan).filter(Loan.loan_officer_id == user.id).count()
        else:  # portfolio
            # Count funded loans as portfolio clients
            count = db.query(Loan).filter(
                Loan.loan_officer_id == user.id,
                Loan.stage == LoanStage.FUNDED
            ).count()

        if count > 0:
            # Generate mock workflow progress for demo
            import random
            completed_count = random.randint(0, len(stage_tasks[stage_key]) - 1)
            in_progress_idx = completed_count

            tasks_with_status = []
            for idx, task in enumerate(stage_tasks[stage_key]):
                if idx < completed_count:
                    status = "completed"
                elif idx == in_progress_idx:
                    status = "in_progress"
                else:
                    status = "pending"
                tasks_with_status.append({**task, "status": status})

            team_members.append({
                "id": user.id,
                "name": user.full_name or user.email,
                "role": user.role or "Team Member",
                "avatar": None,
                "count": count,
                "tasks": tasks_with_status
            })

    return {"team_members": team_members}


@workflow_router.put("/{stage_key}")
async def update_workflow_stage(
    stage_key: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update workflow tasks for a specific stage"""
    import main
    current_user = await main.get_current_user(_extract_token(request), request, db)

    valid_stages = ["lead", "active_loan", "portfolio"]
    if stage_key not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {stage_key}")

    try:
        data = await request.json()
        tasks = data.get("tasks", [])

        # Store workflow configuration in settings
        settings_key = f"workflow_tasks_{stage_key}"

        # Check if setting exists
        existing = db.execute(text("""
            SELECT id FROM user_settings
            WHERE user_id = :user_id AND setting_key = :key
        """), {"user_id": current_user.id, "key": settings_key}).fetchone()

        if existing:
            # Update existing
            db.execute(text("""
                UPDATE user_settings
                SET setting_value = :value, updated_at = NOW()
                WHERE user_id = :user_id AND setting_key = :key
            """), {
                "user_id": current_user.id,
                "key": settings_key,
                "value": json.dumps(tasks)
            })
        else:
            # Insert new
            db.execute(text("""
                INSERT INTO user_settings (user_id, setting_key, setting_value, created_at, updated_at)
                VALUES (:user_id, :key, :value, NOW(), NOW())
            """), {
                "user_id": current_user.id,
                "key": settings_key,
                "value": json.dumps(tasks)
            })

        db.commit()

        return {
            "success": True,
            "message": f"{stage_key} workflow saved successfully",
            "task_count": len(tasks)
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving workflow: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# PERMISSION SYSTEM SEED DATA
# =============================================================================

def seed_permission_system(db: Session):
    """Seed CRM pages, role permissions, AI quick actions, and responsibilities."""
    models = get_models()
    CRMPage = models['CRMPage']
    RolePagePermission = models['RolePagePermission']
    AIQuickAction = models['AIQuickAction']
    AIQuickActionRole = models['AIQuickActionRole']
    Responsibility = models['Responsibility']
    RoleResponsibility = models['RoleResponsibility']
    PermissionLevel = models['PermissionLevel']

    # Check if already seeded
    if db.query(CRMPage).count() > 0:
        logger.info("Permission system already seeded, skipping...")
        return

    logger.info("Seeding permission system...")

    # Seed CRM Pages
    pages_data = [
        {"key": "dashboard", "label": "Dashboard", "category": "Pipeline", "icon": "Dashboard", "route": "/dashboard", "sort_order": 1},
        {"key": "loans", "label": "Loans", "category": "Pipeline", "icon": "AccountBalance", "route": "/loans", "sort_order": 2},
        {"key": "contacts", "label": "Contacts", "category": "Pipeline", "icon": "People", "route": "/contacts", "sort_order": 3},
        {"key": "leads", "label": "Leads", "category": "Pipeline", "icon": "PersonAdd", "route": "/leads", "sort_order": 4},
        {"key": "tasks", "label": "Tasks", "category": "Pipeline", "icon": "CheckCircle", "route": "/tasks", "sort_order": 5},
        {"key": "reports", "label": "Reports", "category": "Reports", "icon": "Assessment", "route": "/reports", "sort_order": 10},
        {"key": "analytics", "label": "Analytics", "category": "Reports", "icon": "TrendingUp", "route": "/analytics", "sort_order": 11},
        {"key": "profitability", "label": "Profitability", "category": "Reports", "icon": "AttachMoney", "route": "/profitability", "sort_order": 12},
        {"key": "ai_landing", "label": "AI Assistant", "category": "AI", "icon": "Psychology", "route": "/ai", "sort_order": 20},
        {"key": "ai_chat", "label": "AI Chat", "category": "AI", "icon": "Chat", "route": "/ai/chat", "sort_order": 21},
        {"key": "admin_users", "label": "User Management", "category": "Admin", "icon": "ManageAccounts", "route": "/admin/users", "sort_order": 30},
        {"key": "admin_settings", "label": "Settings", "category": "Admin", "icon": "Settings", "route": "/admin/settings", "sort_order": 31},
        {"key": "admin_branches", "label": "Branches", "category": "Admin", "icon": "Business", "route": "/admin/branches", "sort_order": 32},
    ]

    for page_data in pages_data:
        db.add(CRMPage(**page_data, is_active=True))
    db.commit()

    # Get pages for role permission mapping
    pages = {p.key: p for p in db.query(CRMPage).all()}

    # Seed Role Page Permissions
    role_defaults = {
        "admin": {"dashboard": "full", "loans": "full", "contacts": "full", "leads": "full", "tasks": "full", "reports": "full", "analytics": "full", "profitability": "full", "ai_landing": "full", "ai_chat": "full", "admin_users": "full", "admin_settings": "full", "admin_branches": "full"},
        "leadership": {"dashboard": "full", "loans": "full", "contacts": "full", "leads": "full", "tasks": "full", "reports": "full", "analytics": "full", "profitability": "full", "ai_landing": "full", "ai_chat": "full", "admin_users": "view", "admin_settings": "view", "admin_branches": "view"},
        "management": {"dashboard": "full", "loans": "edit", "contacts": "edit", "leads": "edit", "tasks": "full", "reports": "view", "analytics": "view", "profitability": "view", "ai_landing": "full", "ai_chat": "full", "admin_users": "none", "admin_settings": "none", "admin_branches": "none"},
        "sales": {"dashboard": "view", "loans": "edit", "contacts": "edit", "leads": "full", "tasks": "edit", "reports": "none", "analytics": "none", "profitability": "none", "ai_landing": "full", "ai_chat": "full", "admin_users": "none", "admin_settings": "none", "admin_branches": "none"},
        "processing": {"dashboard": "view", "loans": "edit", "contacts": "view", "leads": "none", "tasks": "edit", "reports": "none", "analytics": "none", "profitability": "none", "ai_landing": "full", "ai_chat": "full", "admin_users": "none", "admin_settings": "none", "admin_branches": "none"},
        "operations": {"dashboard": "view", "loans": "view", "contacts": "view", "leads": "none", "tasks": "edit", "reports": "view", "analytics": "none", "profitability": "none", "ai_landing": "full", "ai_chat": "full", "admin_users": "none", "admin_settings": "none", "admin_branches": "none"},
    }

    for role, permissions in role_defaults.items():
        for page_key, level in permissions.items():
            if page_key in pages:
                db.add(RolePagePermission(role=role, page_id=pages[page_key].id, permission_level=PermissionLevel(level)))
    db.commit()

    # Seed AI Quick Actions
    actions_data = [
        {"key": "quick_quote", "label": "Quick Quote", "subtitle": "Generate a loan estimate in seconds", "icon": "Calculate", "primary_prompt": "I need to generate a quick loan quote for a borrower.", "requires_chat": True, "roles": ["admin", "leadership", "management", "sales"]},
        {"key": "lead_summary", "label": "Lead Summary", "subtitle": "Get AI insights on your hottest leads", "icon": "Whatshot", "primary_prompt": "Analyze my current leads and show me which ones need attention.", "requires_chat": False, "roles": ["admin", "leadership", "management", "sales"]},
        {"key": "pipeline_status", "label": "Pipeline Status", "subtitle": "Overview of loans in progress", "icon": "Timeline", "primary_prompt": "Show me the current status of my pipeline and any bottlenecks.", "requires_chat": False, "roles": ["admin", "leadership", "management", "sales", "processing"]},
        {"key": "rate_check", "label": "Rate Intelligence", "subtitle": "Current rates and lock recommendations", "icon": "TrendingUp", "primary_prompt": "What are today's rates and do I have any loans that should be locked?", "requires_chat": False, "roles": ["admin", "leadership", "management", "sales"]},
        {"key": "document_checklist", "label": "Document Checklist", "subtitle": "Missing documents and conditions", "icon": "Checklist", "primary_prompt": "Show me outstanding documents and conditions across my loans.", "requires_chat": False, "roles": ["admin", "leadership", "management", "processing", "operations"]},
        {"key": "draft_email", "label": "Draft Email", "subtitle": "AI-assisted communication", "icon": "Email", "primary_prompt": "Help me draft an email to a borrower or referral partner.", "requires_chat": True, "roles": ["admin", "leadership", "management", "sales", "processing"]},
        {"key": "compliance_review", "label": "Compliance Review", "subtitle": "Check disclosure timing and requirements", "icon": "Gavel", "primary_prompt": "Review compliance requirements for my loans in process.", "requires_chat": False, "roles": ["admin", "leadership", "management", "processing", "operations"]},
        {"key": "daily_briefing", "label": "Daily Briefing", "subtitle": "Your personalized morning update", "icon": "WbSunny", "primary_prompt": "Give me my daily briefing with tasks, pipeline updates, and priorities.", "requires_chat": False, "roles": ["admin", "leadership", "management", "sales", "processing", "operations"]},
    ]

    for i, action_data in enumerate(actions_data):
        roles = action_data.pop("roles")
        action = AIQuickAction(**action_data, is_active=True, sort_order=i)
        db.add(action)
        db.flush()
        for role in roles:
            db.add(AIQuickActionRole(ai_action_id=action.id, role=role))
    db.commit()

    # Seed Responsibilities
    responsibilities_data = [
        {"key": "lead_follow_up", "label": "Lead Follow-up", "category": "Sales", "icon": "Phone"},
        {"key": "referral_management", "label": "Referral Partner Management", "category": "Sales", "icon": "Handshake"},
        {"key": "borrower_communication", "label": "Borrower Communication", "category": "Sales", "icon": "Chat"},
        {"key": "rate_monitoring", "label": "Rate Lock Monitoring", "category": "Sales", "icon": "TrendingUp"},
        {"key": "document_collection", "label": "Document Collection", "category": "Processing", "icon": "FolderOpen"},
        {"key": "condition_clearing", "label": "Condition Clearing", "category": "Processing", "icon": "CheckCircle"},
        {"key": "title_coordination", "label": "Title Coordination", "category": "Processing", "icon": "Description"},
        {"key": "appraisal_management", "label": "Appraisal Management", "category": "Processing", "icon": "Home"},
        {"key": "disclosure_timing", "label": "Disclosure Timing", "category": "Operations", "icon": "Schedule"},
        {"key": "compliance_review", "label": "Compliance Review", "category": "Operations", "icon": "Gavel"},
        {"key": "closing_coordination", "label": "Closing Coordination", "category": "Operations", "icon": "EventAvailable"},
        {"key": "post_closing", "label": "Post-Closing", "category": "Operations", "icon": "Archive"},
    ]

    for i, resp_data in enumerate(responsibilities_data):
        db.add(Responsibility(**resp_data, sort_order=i, is_active=True))
    db.commit()

    # Seed Role Responsibilities
    role_resp_defaults = {
        "sales": ["lead_follow_up", "referral_management", "borrower_communication", "rate_monitoring"],
        "processing": ["document_collection", "condition_clearing", "title_coordination", "appraisal_management"],
        "operations": ["disclosure_timing", "compliance_review", "closing_coordination", "post_closing"],
        "management": ["lead_follow_up", "borrower_communication", "rate_monitoring", "compliance_review"],
    }

    responsibilities = {r.key: r for r in db.query(Responsibility).all()}
    for role, resp_keys in role_resp_defaults.items():
        for resp_key in resp_keys:
            if resp_key in responsibilities:
                db.add(RoleResponsibility(role=role, responsibility_id=responsibilities[resp_key].id))
    db.commit()

    logger.info("Permission system seeded successfully")


# =============================================================================
# EMPLOYEE INVITE / ONBOARDING API ENDPOINTS
# =============================================================================

@admin_router.get("/api/admin/users/check-email")
async def check_email_availability(
    email: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Check if email is available for new invite."""
    models = get_models()
    User = models['User']
    EmployeeInvite = models['EmployeeInvite']
    InviteStatus = models['InviteStatus']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    _role = (getattr(current_user, 'permission_role', '') or '').lower().strip()
    if _role not in ('admin', 'site_admin', 'leadership', 'management') and current_user.id != 1:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    _org_id = getattr(current_user, 'organization_id', None)

    # For User check - scope to org
    user_query = db.query(User).filter(User.email == email)
    if _org_id:
        user_query = user_query.filter(User.organization_id == _org_id)
    existing_user = user_query.first()

    # For EmployeeInvite check - scope to org
    invite_query = db.query(EmployeeInvite).filter(
        EmployeeInvite.email == email,
        EmployeeInvite.status == InviteStatus.PENDING
    )
    if _org_id:
        invite_query = invite_query.filter(EmployeeInvite.organization_id == _org_id)
    existing_invite = invite_query.first()

    return {
        "available": existing_user is None and existing_invite is None,
        "reason": "Email already in use" if existing_user else ("Pending invite exists" if existing_invite else None)
    }


@admin_router.get("/api/user-onboarding/options")
async def get_onboarding_options(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get roles, branches, pages, and responsibilities for onboarding wizard."""
    models = get_models()
    Branch = models['Branch']
    CRMPage = models['CRMPage']
    Responsibility = models['Responsibility']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    _role = (getattr(current_user, 'permission_role', '') or '').lower().strip()
    if _role not in ('admin', 'site_admin', 'leadership', 'management') and current_user.id != 1:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    roles = [
        {"value": "admin", "label": "Administrator", "description": "Full system access"},
        {"value": "leadership", "label": "Leadership", "description": "Executive oversight access"},
        {"value": "management", "label": "Management", "description": "Team management access"},
        {"value": "sales", "label": "Sales / Loan Officer", "description": "Lead and loan origination"},
        {"value": "processing", "label": "Processing", "description": "Loan processing access"},
        {"value": "operations", "label": "Operations", "description": "Operational support access"},
    ]

    branches = [{"id": b.id, "name": b.name} for b in db.query(Branch).all()]
    pages = [{"id": p.id, "key": p.key, "label": p.label, "category": p.category} for p in db.query(CRMPage).filter(CRMPage.is_active == True).order_by(CRMPage.sort_order).all()]
    responsibilities = [{"id": r.id, "key": r.key, "label": r.label, "category": r.category} for r in db.query(Responsibility).filter(Responsibility.is_active == True).order_by(Responsibility.sort_order).all()]

    return {"roles": roles, "branches": branches, "pages": pages, "responsibilities": responsibilities}


@admin_router.get("/api/user-onboarding/permissions-preview/{role}")
async def get_role_permissions_preview(
    role: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get default permissions for a role."""
    models = get_models()
    RolePagePermission = models['RolePagePermission']
    RoleResponsibility = models['RoleResponsibility']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    _role = (getattr(current_user, 'permission_role', '') or '').lower().strip()
    if _role not in ('admin', 'site_admin', 'leadership', 'management') and current_user.id != 1:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    role_perms = db.query(RolePagePermission).filter(RolePagePermission.role == role).all()
    role_resps = db.query(RoleResponsibility).filter(RoleResponsibility.role == role).all()

    return {
        "permissions": [{"page_id": rp.page_id, "page_key": rp.page.key, "level": rp.permission_level.value} for rp in role_perms],
        "responsibilities": [{"id": rr.responsibility_id, "key": rr.responsibility.key} for rr in role_resps]
    }


@admin_router.post("/api/admin/users/onboarding")
async def create_employee_invite(
    invite_data: EmployeeInviteCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new employee invite."""
    models = get_models()
    auth = get_auth_deps()
    User = models['User']
    EmployeeInvite = models['EmployeeInvite']
    InviteStatus = models['InviteStatus']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    # Permission check - only admin, site_admin, leadership, management can manage invites
    _role = (getattr(current_user, 'permission_role', '') or '').lower().strip()
    if _role not in ('admin', 'site_admin', 'leadership', 'management') and current_user.id != 1:
        raise HTTPException(status_code=403, detail="Insufficient permissions to manage invites")

    from utils.roles import ALLOWED_ROLES
    _requested_role = (invite_data.permission_role or '').lower().strip()
    if _requested_role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {invite_data.permission_role}. Allowed: {', '.join(sorted(ALLOWED_ROLES))}")

    # Prevent role escalation -- assigner must be at or above the target role
    from auth.role_guards import enforce_no_escalation
    enforce_no_escalation(_role, _requested_role)

    # Check email availability (scoped to current org for tenant isolation)
    _org_id = getattr(current_user, 'organization_id', None)
    email_query = db.query(User).filter(User.email == invite_data.email)
    if _org_id:
        email_query = email_query.filter(User.organization_id == _org_id)
    if email_query.first():
        raise HTTPException(status_code=400, detail="Email already in use")

    invite_query = db.query(EmployeeInvite).filter(EmployeeInvite.email == invite_data.email, EmployeeInvite.status == InviteStatus.PENDING)
    if _org_id:
        invite_query = invite_query.filter(EmployeeInvite.organization_id == _org_id)
    if invite_query.first():
        raise HTTPException(status_code=400, detail="Pending invite already exists for this email")

    # Generate invite token
    from utils.token_security import generate_invite_token
    invite_token = generate_invite_token()

    # Create invite
    invite = EmployeeInvite(
        email=invite_data.email,
        first_name=invite_data.first_name,
        last_name=invite_data.last_name,
        job_title=invite_data.job_title,
        permission_role=invite_data.permission_role,
        branch_id=invite_data.branch_id,
        organization_id=getattr(current_user, 'organization_id', None),
        invite_token=invite_token,
        invited_by_user_id=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        initial_config={
            "page_permissions": invite_data.page_permissions or [],
            "responsibilities": invite_data.responsibilities or []
        }
    )
    db.add(invite)
    db.flush()  # Get invite.id before commit

    # Audit log in same transaction
    try:
        from utils.invitation_audit import log_invite_event
        log_invite_event(db, "invite_created", invite_id=invite.id, actor_id=current_user.id,
                         org_id=getattr(current_user, 'organization_id', None),
                         target_email=invite_data.email,
                         details={"role": invite_data.permission_role})
    except Exception:
        pass

    db.commit()
    db.refresh(invite)

    # Send invite email with token
    invite_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/accept-invite?token={invite_token}"

    try:
        from email_service import email_service

        user_name = f"{invite_data.first_name} {invite_data.last_name}"
        inviter_name = current_user.full_name or current_user.email.split('@')[0]

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

                    <h2 style="color: #111827; margin: 0 0 16px; font-size: 22px;">Welcome to the Team, {invite_data.first_name}!</h2>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        {inviter_name} has invited you to join Perennia AI as a <strong>{invite_data.permission_role.title()}</strong>.
                    </p>

                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        Click the button below to set up your password and activate your account:
                    </p>

                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{invite_url}" style="display: inline-block; background: #3b82f6; color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                            Accept Invite &amp; Set Password
                        </a>
                    </div>

                    <div style="background: #f0f9ff; border-left: 4px solid #3b82f6; padding: 16px; margin: 24px 0; border-radius: 0 8px 8px 0;">
                        <h4 style="margin: 0 0 8px 0; color: #1e40af;">What's Next?</h4>
                        <ul style="margin: 0; padding-left: 20px; color: #4b5563;">
                            <li>Set your secure password</li>
                            <li>Review your assigned responsibilities</li>
                            <li>Access your personalized dashboard</li>
                            <li>Start managing your pipeline</li>
                        </ul>
                    </div>

                    <p style="color: #f59e0b; font-size: 14px; text-align: center; background: #fef3c7; padding: 12px 16px; border-radius: 8px;">
                        This invite expires in <strong>7 days</strong>
                    </p>

                    <p style="color: #9ca3af; font-size: 13px; margin-top: 32px; text-align: center;">
                        If you didn't expect this invitation, please contact your administrator.
                    </p>

                </div>
            </div>
        </body>
        </html>
        """

        plain_text = f"""Welcome to the Team, {invite_data.first_name}!

{inviter_name} has invited you to join Perennia AI as a {invite_data.permission_role.title()}.

Click the link below to set up your password and activate your account:

{invite_url}

What's Next?
- Set your secure password
- Review your assigned responsibilities
- Access your personalized dashboard
- Start managing your pipeline

This invite expires in 7 days.

If you didn't expect this invitation, please contact your administrator.

- The Perennia AI Team
"""

        email_sent = email_service.send_html_email(
            to_email=invite_data.email,
            subject=f"You're Invited to Join Perennia AI - {invite_data.permission_role.title()}",
            html_body=html_content,
            plain_text_body=plain_text
        )

        if email_sent:
            logger.info(f"Employee invite email sent to {mask_email(invite_data.email)}")
        else:
            logger.warning(f"Failed to send invite email to {mask_email(invite_data.email)}, invite still created")

    except Exception as email_err:
        logger.error(f"Error sending invite email: {email_err}")
        # Continue anyway - invite was created

    logger.info(f"Employee invite created: {mask_email(invite_data.email)}, invite_id: {invite.id}")

    return {
        "success": True,
        "invite_id": invite.id,
        "invite_url": invite_url,
        "expires_at": invite.expires_at.isoformat()
    }


@admin_router.get("/api/invite/{token}")
@rate_limit(limit=10, window=300, key_func=ip_key)
async def get_invite_details(token: str, request: Request, db: Session = Depends(get_db)):
    """Get invite details (public endpoint for invite acceptance page).
    Rate limited: 10 requests per 5 minutes per IP.
    """
    models = get_models()
    EmployeeInvite = models['EmployeeInvite']
    InviteStatus = models['InviteStatus']

    from utils.token_security import safe_token_compare

    invite = db.query(EmployeeInvite).filter(EmployeeInvite.invite_token == token).first()

    # Defense-in-depth: constant-time comparison even though SQL found the row
    if not invite or not safe_token_compare(invite.invite_token, token):
        raise HTTPException(status_code=404, detail="Invite not found")

    if invite.status != InviteStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Invite has been {invite.status.value}")

    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = InviteStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=400, detail="Invite has expired")

    return {
        "email": invite.email,
        "first_name": invite.first_name,
        "last_name": invite.last_name,
        "job_title": invite.job_title,
        "permission_role": invite.permission_role,
        "expires_at": invite.expires_at.isoformat()
    }


@admin_router.post("/api/invite/accept")
@rate_limit(limit=5, window=300, key_func=ip_key)
async def accept_invite(request: Request, body: InviteAcceptRequest, db: Session = Depends(get_db)):
    """Accept an invite and create user account.
    Rate limited: 5 requests per 5 minutes per IP.
    """
    models = get_models()
    auth = get_auth_deps()
    User = models['User']
    EmployeeInvite = models['EmployeeInvite']
    InviteStatus = models['InviteStatus']
    CRMPage = models['CRMPage']
    UserPagePermission = models['UserPagePermission']
    PermissionLevel = models['PermissionLevel']
    Responsibility = models['Responsibility']
    UserResponsibility = models['UserResponsibility']
    pwd_context = auth['pwd_context']
    create_access_token = auth['create_access_token']

    from utils.token_security import safe_token_compare
    from utils.password_policy import validate_password

    _client_ip = request.client.host if request.client else None

    invite = db.query(EmployeeInvite).filter(EmployeeInvite.invite_token == body.token).first()

    # Defense-in-depth: constant-time comparison even though SQL found the row
    if not invite or not safe_token_compare(invite.invite_token, body.token):
        try:
            from utils.invitation_audit import log_invite_event
            log_invite_event(db, "invite_accept_failed", details={"reason": "invalid_token"}, ip_address=_client_ip)
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="Invite not found")

    if invite.status != InviteStatus.PENDING:
        try:
            from utils.invitation_audit import log_invite_event
            log_invite_event(db, "invite_accept_failed", invite_id=invite.id,
                             target_email=invite.email, details={"reason": f"status_{invite.status.value}"},
                             ip_address=_client_ip)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"Invite has been {invite.status.value}")

    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = InviteStatus.EXPIRED
        db.commit()
        try:
            from utils.invitation_audit import log_invite_event
            log_invite_event(db, "invite_accept_failed", invite_id=invite.id,
                             target_email=invite.email, details={"reason": "expired"},
                             ip_address=_client_ip)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Invite has expired")

    # Validate password strength (unified policy)
    validate_password(body.password)

    # --- Seat limit enforcement (LIC-003) ---
    _org_id = invite.organization_id
    if not _org_id and invite.invited_by_user_id:
        _inviter = db.query(User).filter(User.id == invite.invited_by_user_id).first()
        if _inviter:
            _org_id = getattr(_inviter, 'organization_id', None)

    if _org_id:
        from sqlalchemy import func as _fn
        # FOR UPDATE lock prevents race condition where two concurrent accepts
        # both read the same count and both succeed past the seat limit
        _sub_row = db.execute(
            text(
                "SELECT max_users FROM organization_subscriptions "
                "WHERE organization_id = :org_id AND status = 'active' LIMIT 1 "
                "FOR UPDATE"
            ),
            {"org_id": _org_id}
        ).fetchone()

        if _sub_row and _sub_row[0] is not None and _sub_row[0] > 0:
            _active_count = db.query(_fn.count(User.id)).filter(
                User.organization_id == _org_id,
                User.is_active == True
            ).scalar() or 0
            if _active_count >= _sub_row[0]:
                raise HTTPException(
                    status_code=403,
                    detail="Seat limit reached. Contact your administrator to upgrade."
                )

    # Create user
    hashed_password = pwd_context.hash(body.password)
    user = User(
        email=invite.email,
        hashed_password=hashed_password,
        first_name=invite.first_name,
        last_name=invite.last_name,
        permission_role=invite.permission_role,
        role=invite.permission_role,
        branch_id=invite.branch_id,
        organization_id=_org_id,
        is_active=True
    )
    db.add(user)
    db.flush()

    # Apply permission overrides if any
    if invite.initial_config.get("page_permissions"):
        for perm in invite.initial_config["page_permissions"]:
            page = db.query(CRMPage).filter(CRMPage.key == perm.get("page_key")).first()
            if page:
                db.add(UserPagePermission(user_id=user.id, page_id=page.id, permission_level=PermissionLevel(perm["level"])))

    # Apply responsibilities
    if invite.initial_config.get("responsibilities"):
        for resp_key in invite.initial_config["responsibilities"]:
            resp = db.query(Responsibility).filter(Responsibility.key == resp_key).first()
            if resp:
                db.add(UserResponsibility(user_id=user.id, responsibility_id=resp.id, is_enabled=True))

    # Update invite status
    invite.status = InviteStatus.ACCEPTED
    invite.accepted_at = datetime.now(timezone.utc)
    invite.user_id = user.id
    invite.invite_token = None  # Clear token after use

    db.commit()

    # Audit log
    try:
        from utils.invitation_audit import log_invite_event
        _client_ip = request.client.host if request.client else None
        log_invite_event(db, "invite_accepted", invite_id=invite.id,
                         org_id=_org_id, target_email=invite.email,
                         details={"user_id": user.id, "role": invite.permission_role},
                         ip_address=_client_ip)
    except Exception:
        pass

    # Generate JWT token for immediate login
    access_token = create_access_token(data={"sub": user.email})

    return {
        "success": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "permission_role": user.permission_role}
    }


@admin_router.get("/api/admin/invites")
async def list_invites(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all employee invites."""
    models = get_models()
    EmployeeInvite = models['EmployeeInvite']
    InviteStatus = models['InviteStatus']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    # Permission check - only admin, site_admin, leadership, management can manage invites
    _role = (getattr(current_user, 'permission_role', '') or '').lower().strip()
    if _role not in ('admin', 'site_admin', 'leadership', 'management') and current_user.id != 1:
        raise HTTPException(status_code=403, detail="Insufficient permissions to manage invites")

    query = db.query(EmployeeInvite).order_by(EmployeeInvite.created_at.desc())

    # Tenant isolation - mandatory org enforcement
    _org_id = getattr(current_user, 'organization_id', None)
    if not _org_id and current_user.id != 1:
        raise HTTPException(status_code=403, detail="User not assigned to an organization")
    if _org_id:
        query = query.filter(EmployeeInvite.organization_id == _org_id)

    if status:
        query = query.filter(EmployeeInvite.status == InviteStatus(status))

    invites = query.all()

    def _effective_status(inv):
        """Return 'expired' if a pending invite has passed its expires_at."""
        raw = inv.status.value if hasattr(inv.status, 'value') else str(inv.status)
        if raw == 'pending' and inv.expires_at and inv.expires_at < datetime.now(timezone.utc):
            return 'expired'
        return raw

    return {
        "invites": [{
            "id": inv.id,
            "email": inv.email,
            "first_name": inv.first_name,
            "last_name": inv.last_name,
            "job_title": inv.job_title,
            "permission_role": inv.permission_role,
            "status": _effective_status(inv),
            "invite_token": inv.invite_token if inv.status == InviteStatus.PENDING and not (inv.expires_at and inv.expires_at < datetime.now(timezone.utc)) else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
            "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None
        } for inv in invites]
    }


@admin_router.post("/api/admin/invites/{invite_id}/revoke")
async def revoke_invite(
    invite_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Revoke a pending invite."""
    models = get_models()
    EmployeeInvite = models['EmployeeInvite']
    InviteStatus = models['InviteStatus']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    # Permission check - only admin, site_admin, leadership, management can manage invites
    _role = (getattr(current_user, 'permission_role', '') or '').lower().strip()
    if _role not in ('admin', 'site_admin', 'leadership', 'management') and current_user.id != 1:
        raise HTTPException(status_code=403, detail="Insufficient permissions to manage invites")

    invite = db.query(EmployeeInvite).filter(EmployeeInvite.id == invite_id).first()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    # Tenant isolation - mandatory org enforcement
    _org_id = getattr(current_user, 'organization_id', None)
    if not _org_id and current_user.id != 1:
        raise HTTPException(status_code=403, detail="User not assigned to an organization")
    if _org_id and invite.organization_id != _org_id:
        raise HTTPException(status_code=404, detail="Invite not found")

    if invite.status not in (InviteStatus.PENDING, InviteStatus.EXPIRED):
        raise HTTPException(status_code=400, detail="Can only revoke pending or expired invites")

    invite.status = InviteStatus.REVOKED
    invite.invite_token = None  # Clear token on revoke
    db.commit()

    try:
        from utils.invitation_audit import log_invite_event
        log_invite_event(db, "invite_revoked", invite_id=invite.id, actor_id=current_user.id,
                         org_id=_org_id, target_email=invite.email)
    except Exception:
        pass

    return {"success": True, "message": "Invite revoked"}


@admin_router.post("/api/admin/invites/{invite_id}/resend")
@rate_limit(limit=5, window=300, key_func=ip_key)
async def resend_invite(
    invite_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Resend a pending invite with a fresh token and extended expiry."""
    models = get_models()
    EmployeeInvite = models['EmployeeInvite']
    InviteStatus = models['InviteStatus']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    # Permission check
    _role = (getattr(current_user, 'permission_role', '') or '').lower().strip()
    if _role not in ('admin', 'site_admin', 'leadership', 'management') and current_user.id != 1:
        raise HTTPException(status_code=403, detail="Insufficient permissions to manage invites")

    invite = db.query(EmployeeInvite).filter(EmployeeInvite.id == invite_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    # Tenant isolation
    _org_id = getattr(current_user, 'organization_id', None)
    if not _org_id and current_user.id != 1:
        raise HTTPException(status_code=403, detail="User not assigned to an organization")
    if _org_id and invite.organization_id != _org_id:
        raise HTTPException(status_code=404, detail="Invite not found")

    if invite.status not in (InviteStatus.PENDING, InviteStatus.EXPIRED):
        raise HTTPException(status_code=400, detail="Can only resend pending or expired invites")

    # Generate fresh token and extend expiry
    from utils.token_security import generate_invite_token
    invite.invite_token = generate_invite_token()
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invite.status = InviteStatus.PENDING  # Reset expired back to pending

    db.commit()

    # Send invite email
    invite_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/accept-invite?token={invite.invite_token}"

    email_sent = False
    try:
        from email_service import email_service

        inviter_name = current_user.full_name or current_user.email.split('@')[0]

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f6f9fc;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <div style="background: white; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); padding: 40px;">
                    <div style="text-align: center; margin-bottom: 32px;">
                        <h1 style="color: #3b82f6; font-size: 28px; margin: 0;">Perennia AI</h1>
                    </div>
                    <h2 style="color: #111827; margin: 0 0 16px; font-size: 22px;">Reminder: You're Invited, {invite.first_name}!</h2>
                    <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                        {inviter_name} has resent your invitation to join Perennia AI as a <strong>{invite.permission_role.title()}</strong>.
                    </p>
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{invite_url}" style="display: inline-block; background: #3b82f6; color: white; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                            Accept Invite &amp; Set Password
                        </a>
                    </div>
                    <p style="color: #f59e0b; font-size: 14px; text-align: center; background: #fef3c7; padding: 12px 16px; border-radius: 8px;">
                        This invite expires in <strong>7 days</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        email_sent = email_service.send_html_email(
            to_email=invite.email,
            subject=f"Reminder: You're Invited to Join Perennia AI",
            html_body=html_content,
            plain_text_body=f"Hi {invite.first_name}, your invitation to join Perennia AI has been resent. Visit {invite_url} to accept."
        )
    except Exception as email_err:
        logger.error(f"Error sending resend email: {email_err}")

    try:
        from utils.invitation_audit import log_invite_event
        log_invite_event(db, "invite_resent", invite_id=invite.id, actor_id=current_user.id,
                         org_id=_org_id, target_email=invite.email)
    except Exception:
        pass

    return {
        "success": True,
        "message": "Invite resent",
        "email_sent": email_sent,
        "expires_at": invite.expires_at.isoformat()
    }


# =============================================================================
# AI QUICK ACTIONS ENDPOINTS
# =============================================================================

@ai_router.get("/quick-actions")
async def get_ai_quick_actions(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get AI quick actions available to the current user based on their role."""
    models = get_models()
    AIQuickAction = models['AIQuickAction']
    AIQuickActionRole = models['AIQuickActionRole']

    import main
    current_user = await main.get_current_user_flexible(request, db)

    user_role = current_user.permission_role or "sales"

    # Get actions for this role
    actions = db.query(AIQuickAction).join(AIQuickActionRole).filter(
        AIQuickActionRole.role == user_role,
        AIQuickAction.is_active == True
    ).order_by(AIQuickAction.sort_order).all()

    return {
        "actions": [{
            "key": a.key,
            "label": a.label,
            "subtitle": a.subtitle,
            "icon": a.icon,
            "primary_prompt": a.primary_prompt,
            "requires_chat": a.requires_chat
        } for a in actions]
    }
