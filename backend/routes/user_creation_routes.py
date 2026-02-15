"""
User Creation & Onboarding API Routes
Perennia AI - IBMA

Handles single user creation and bulk upload workflows for
the Perennia AI platform. Includes user activation, role assignment,
permission configuration, and KPI scorecard generation.
"""

import csv
import io
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, Query
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/users", tags=["User Management"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class BasicInfoRequest(BaseModel):
    """Request schema for creating a single user - basic info."""
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User's first name"
    )
    last_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User's last name"
    )
    email: EmailStr = Field(..., description="User's email address")
    phone: Optional[str] = Field(None, max_length=50, description="Phone number")
    internal_title: Optional[str] = Field(None, max_length=100, description="Job title")
    profile_image_url: Optional[str] = Field(None, description="Profile image URL")

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_names(cls, v: str) -> str:
        return v.strip()


class RoleBuilderRequest(BaseModel):
    """Request schema for role builder step."""
    user_id: int = Field(..., description="User ID being configured")
    onboarding_session_id: int = Field(..., description="Onboarding session ID")
    role_id: int = Field(..., description="Role ID to assign")
    category_ids: List[int] = Field(default=[], description="Category IDs to assign")
    responsibility_ids: List[int] = Field(default=[], description="Responsibility IDs to assign")


class PermissionsBuilderRequest(BaseModel):
    """Request schema for permissions builder step."""
    user_id: int = Field(..., description="User ID being configured")
    onboarding_session_id: int = Field(..., description="Onboarding session ID")
    permission_source: str = Field(
        ...,
        description="Source of permissions: 'template' or 'custom'"
    )
    permission_template_id: Optional[int] = Field(None, description="Permission template ID")
    custom_permissions: Optional[Dict[str, Any]] = Field(None, description="Custom permissions JSON")


class FinalizeUserRequest(BaseModel):
    """Request schema for finalizing user creation."""
    user_id: int = Field(..., description="User ID to finalize")
    onboarding_session_id: int = Field(..., description="Onboarding session ID")


class ColumnMappingRequest(BaseModel):
    """Request schema for column mapping in bulk upload."""
    session_id: int = Field(..., description="Bulk upload session ID")
    column_mapping: Dict[str, str] = Field(..., description="Column name to field mapping")


class BulkRoleBuilderRequest(BaseModel):
    """Request schema for bulk role builder."""
    session_id: int = Field(..., description="Bulk upload session ID")
    apply_to_all: bool = Field(True, description="Apply same config to all users")
    default_config: Optional[Dict[str, Any]] = Field(None, description="Default role config")
    per_user_overrides: Optional[List[Dict[str, Any]]] = Field(None, description="Per-user overrides")


class ResponsibilityFilterRequest(BaseModel):
    """Request schema for filtering responsibilities."""
    category_ids: List[int] = Field(..., description="Category IDs to filter by")
    role_id: Optional[int] = Field(None, description="Optional role ID filter")


class ActivatePasswordRequest(BaseModel):
    """Request schema for setting password during activation."""
    activation_token: str = Field(..., description="Activation token from email")
    password: str = Field(
        ...,
        min_length=8,
        description="New password (min 8 chars, requires uppercase, lowercase, number, special char)"
    )
    password_confirmation: str = Field(..., description="Password confirmation")

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in v):
            raise ValueError('Password must contain at least one special character')
        return v

    @field_validator('password_confirmation')
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class RoleResponse(BaseModel):
    """Response schema for a role."""
    id: int = Field(..., description="Role ID")
    name: str = Field(..., description="Role name")
    description: Optional[str] = Field(None, description="Role description")

    class Config:
        from_attributes = True


class CategoryResponse(BaseModel):
    """Response schema for a category."""
    id: int = Field(..., description="Category ID")
    name: str = Field(..., description="Category name")
    description: Optional[str] = Field(None, description="Category description")

    class Config:
        from_attributes = True


class ResponsibilityResponse(BaseModel):
    """Response schema for a responsibility."""
    id: int = Field(..., description="Responsibility ID")
    name: str = Field(..., description="Responsibility name")
    description: Optional[str] = Field(None, description="Responsibility description")
    category_id: int = Field(..., description="Parent category ID")
    category_name: Optional[str] = Field(None, description="Parent category name")

    class Config:
        from_attributes = True


class PermissionTemplateResponse(BaseModel):
    """Response schema for a permission template."""
    id: int = Field(..., description="Template ID")
    name: str = Field(..., description="Template name")
    description: Optional[str] = Field(None, description="Template description")
    is_system_template: bool = Field(..., description="Whether this is a system-defined template")

    class Config:
        from_attributes = True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_activation_token() -> str:
    """Generate a secure activation token"""
    return secrets.token_urlsafe(32)


def get_user_creation_routes(
    get_db,
    get_current_user,
    User,
    UserProfile,
    Role,
    Category,
    Responsibility,
    PermissionTemplate,
    UserPermissions,
    UserCategory,
    UserResponsibility,
    RoleDefaultCategory,
    RoleDefaultResponsibility,
    KPIScorecard,
    BulkUploadSession,
    BulkUserDraft,
    UserAuditLog,
    OnboardingSession,
    pwd_context,
    create_access_token,
    email_service=None
):
    """
    Factory function that creates routes with injected dependencies
    This allows the routes to work with the existing main.py models
    """
    import os
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://perenniaai.com")

    # ========================================================================
    # UNIFIED USER CREATION ENDPOINT (All-in-one)
    # ========================================================================

    @router.post("/create")
    async def create_user_unified(
        request: Request,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Unified endpoint that creates a user with all configuration in one call.
        Used by the UserCreationWizard frontend component.
        """
        # Check permission
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create users"
            )

        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        email = data.get('email')
        full_name = data.get('full_name', '')
        phone = data.get('phone')
        role_id = data.get('role_id')
        category_ids = data.get('category_ids', [])
        responsibility_ids = data.get('responsibility_ids', [])
        permission_template_id = data.get('permission_template_id')
        custom_permissions = data.get('custom_permissions')

        if not email:
            raise HTTPException(status_code=400, detail="Email is required")

        # Check email uniqueness
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists in the system"
            )

        try:
            # Parse full_name into first_name and last_name
            name_parts = full_name.strip().split(' ', 1) if full_name else ['', '']
            first_name = name_parts[0] if name_parts else ''
            last_name = name_parts[1] if len(name_parts) > 1 else ''

            # Create the base User record
            new_user = User(
                email=email,
                hashed_password="",  # Will be set during activation
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role="pending",
                permission_role="pending",
                is_active=False
            )
            db.add(new_user)
            db.flush()

            # Create UserProfile record
            user_profile = UserProfile(
                user_id=new_user.id,
                first_name=first_name,
                last_name=last_name,
                role_id=role_id,
                status="pending_setup",
                created_by=current_user.id
            )
            db.add(user_profile)
            db.flush()

            # Add categories
            for cat_id in category_ids:
                user_cat = UserCategory(
                    user_profile_id=user_profile.id,
                    category_id=cat_id
                )
                db.add(user_cat)

            # Add responsibilities
            for resp_id in responsibility_ids:
                user_resp = UserResponsibility(
                    user_profile_id=user_profile.id,
                    responsibility_id=resp_id
                )
                db.add(user_resp)

            # Handle permissions
            permissions_data = {}
            if permission_template_id:
                template = db.query(PermissionTemplate).filter(
                    PermissionTemplate.id == permission_template_id
                ).first()
                if template:
                    user_profile.permission_template_id = permission_template_id
                    permissions_data = template.permissions or {}
            elif custom_permissions:
                permissions_data = custom_permissions

            if permissions_data:
                user_perms = UserPermissions(
                    user_profile_id=user_profile.id,
                    permissions=permissions_data,
                    source="template" if permission_template_id else "custom"
                )
                db.add(user_perms)

            # Generate KPI Scorecard
            scorecard_config = generate_kpi_scorecard_config(responsibility_ids, db, Responsibility)
            scorecard = KPIScorecard(
                user_profile_id=user_profile.id,
                scorecard_config=scorecard_config
            )
            db.add(scorecard)

            # Generate activation token
            activation_token = generate_activation_token()
            user_profile.activation_token = activation_token
            user_profile.activation_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            user_profile.status = "active_awaiting_setup"

            # Audit log
            audit_log = UserAuditLog(
                user_id=new_user.id,
                action="user_created",
                performed_by=current_user.id,
                details={"email": email, "role_id": role_id},
                ip_address=request.client.host if request.client else None
            )
            db.add(audit_log)

            db.commit()

            # Get role name for response
            role = db.query(Role).filter(Role.id == role_id).first()

            return {
                "success": True,
                "user_id": new_user.id,
                "email": email,
                "full_name": full_name,
                "role": role.name if role else "Unknown",
                "scorecard": {
                    "id": scorecard.id,
                    "kpi_count": len(scorecard_config.get('daily_kpis', [])) +
                                 len(scorecard_config.get('weekly_kpis', [])) +
                                 len(scorecard_config.get('monthly_kpis', []))
                },
                "activation_token": activation_token,
                "activation_expires_at": user_profile.activation_token_expires_at.isoformat()
            }

        except IntegrityError:
            db.rollback()
            logger.warning(f"Duplicate email conflict during user creation: {email}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists in the system"
            )
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating user: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )

    # ========================================================================
    # SINGLE USER CREATION ENDPOINTS (Step-by-step)
    # ========================================================================

    @router.post("/create/single")
    async def create_single_user(
        data: BasicInfoRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Step 1: Create a new user with basic information
        Returns user_id and onboarding_session_id for subsequent steps
        """
        # Check permission (manage_users)
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create users"
            )

        # Check email uniqueness
        existing_user = db.query(User).filter(User.email == data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists in the system"
            )

        try:
            # Create the base User record
            new_user = User(
                email=data.email,
                hashed_password="",  # Will be set during activation
                first_name=data.first_name,
                last_name=data.last_name,
                phone=data.phone,
                role="pending",
                permission_role="pending",
                is_active=False
            )
            db.add(new_user)
            db.flush()  # Get the ID

            # Create UserProfile record
            user_profile = UserProfile(
                user_id=new_user.id,
                first_name=data.first_name,
                last_name=data.last_name,
                internal_title=data.internal_title,
                profile_image_url=data.profile_image_url,
                status="pending_setup",
                created_by=current_user.id
            )
            db.add(user_profile)
            db.flush()

            # Create onboarding session
            session_token = secrets.token_urlsafe(32)
            onboarding_session = OnboardingSession(
                session_token=session_token,
                user_id=new_user.id,
                user_profile_id=user_profile.id,
                created_by=current_user.id,
                current_step="basic_info",
                status="in_progress",
                basic_info_data=data.dict(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            db.add(onboarding_session)
            db.flush()

            # Audit log
            audit_log = UserAuditLog(
                user_id=new_user.id,
                action="user_created",
                performed_by=current_user.id,
                details={"step": "basic_info", "email": data.email},
                ip_address=request.client.host if request.client else None
            )
            db.add(audit_log)

            db.commit()

            return {
                "success": True,
                "data": {
                    "user_id": new_user.id,
                    "user_profile_id": user_profile.id,
                    "onboarding_session_id": onboarding_session.id,
                    "status": "pending_setup",
                    "next_step": "role_builder"
                }
            }

        except IntegrityError:
            db.rollback()
            logger.warning(f"Duplicate email conflict during single user creation: {data.email}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists in the system"
            )
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error creating user: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )

    @router.post("/create/single/role-builder")
    async def save_role_builder_single(
        data: RoleBuilderRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Step 2: Save role, categories, and responsibilities for a single user
        """
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        # Validate session
        session = db.query(OnboardingSession).filter(
            OnboardingSession.id == data.onboarding_session_id,
            OnboardingSession.user_id == data.user_id,
            OnboardingSession.status == "in_progress"
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Onboarding session not found")

        # Get user profile
        user_profile = db.query(UserProfile).filter(
            UserProfile.user_id == data.user_id
        ).first()

        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile not found")

        # Validate role exists
        role = db.query(Role).filter(Role.id == data.role_id).first()
        if not role:
            raise HTTPException(status_code=400, detail="Invalid role ID")

        try:
            # Update user profile with role
            user_profile.role_id = data.role_id

            # Clear existing categories and responsibilities
            db.query(UserCategory).filter(
                UserCategory.user_profile_id == user_profile.id
            ).delete()
            db.query(UserResponsibility).filter(
                UserResponsibility.user_profile_id == user_profile.id
            ).delete()

            # Add new categories
            for cat_id in data.category_ids:
                user_cat = UserCategory(
                    user_profile_id=user_profile.id,
                    category_id=cat_id
                )
                db.add(user_cat)

            # Add new responsibilities
            for resp_id in data.responsibility_ids:
                user_resp = UserResponsibility(
                    user_profile_id=user_profile.id,
                    responsibility_id=resp_id
                )
                db.add(user_resp)

            # Update session
            session.role_builder_data = {
                "role_id": data.role_id,
                "category_ids": data.category_ids,
                "responsibility_ids": data.responsibility_ids
            }
            session.current_step = "role_builder"

            # Generate role summary
            responsibilities = db.query(Responsibility).filter(
                Responsibility.id.in_(data.responsibility_ids)
            ).all()
            resp_names = [r.name for r in responsibilities]
            role_summary = f"This user will be a {role.name} with responsibilities including: {', '.join(resp_names[:3])}{'...' if len(resp_names) > 3 else ''}. KPI Scorecard will be automatically generated based on selected responsibilities."

            db.commit()

            return {
                "success": True,
                "data": {
                    "user_id": data.user_id,
                    "role_summary": role_summary,
                    "next_step": "permissions_builder"
                }
            }

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error saving role builder: {e}")
            raise HTTPException(status_code=500, detail="Failed to save role configuration")

    @router.post("/create/single/permissions-builder")
    async def save_permissions_builder_single(
        data: PermissionsBuilderRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Step 3: Save permission configuration for a single user
        """
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        # Validate session
        session = db.query(OnboardingSession).filter(
            OnboardingSession.id == data.onboarding_session_id,
            OnboardingSession.user_id == data.user_id,
            OnboardingSession.status == "in_progress"
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Onboarding session not found")

        user_profile = db.query(UserProfile).filter(
            UserProfile.user_id == data.user_id
        ).first()

        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile not found")

        try:
            permissions_data = {}
            template_name = None

            if data.permission_source == "template" and data.permission_template_id:
                # Get template permissions
                template = db.query(PermissionTemplate).filter(
                    PermissionTemplate.id == data.permission_template_id
                ).first()
                if not template:
                    raise HTTPException(status_code=400, detail="Invalid permission template")

                user_profile.permission_template_id = data.permission_template_id
                permissions_data = template.permissions
                template_name = template.name
            elif data.permission_source == "custom" and data.custom_permissions:
                permissions_data = data.custom_permissions
                template_name = "Custom Permissions"
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Must provide either permission_template_id or custom_permissions"
                )

            # Create or update user permissions
            existing_perms = db.query(UserPermissions).filter(
                UserPermissions.user_profile_id == user_profile.id
            ).first()

            if existing_perms:
                existing_perms.permissions = permissions_data
                existing_perms.source = data.permission_source
            else:
                user_perms = UserPermissions(
                    user_profile_id=user_profile.id,
                    permissions=permissions_data,
                    source=data.permission_source
                )
                db.add(user_perms)

            # Update session
            session.permissions_data = {
                "permission_source": data.permission_source,
                "permission_template_id": data.permission_template_id,
                "custom_permissions": data.custom_permissions
            }
            session.current_step = "permissions_builder"

            # Generate permission summary
            perm_summary = generate_permission_summary(permissions_data)

            db.commit()

            return {
                "success": True,
                "data": {
                    "user_id": data.user_id,
                    "permission_summary": perm_summary,
                    "next_step": "review_confirm"
                }
            }

        except HTTPException:
            raise
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error saving permissions: {e}")
            raise HTTPException(status_code=500, detail="Failed to save permissions")

    @router.get("/create/single/review/{user_id}")
    async def get_review_summary_single(
        user_id: int,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Step 4: Get the complete review summary before finalization
        """
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user_profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()

        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile not found")

        # Get role
        role = db.query(Role).filter(Role.id == user_profile.role_id).first()

        # Get categories
        user_categories = db.query(UserCategory).filter(
            UserCategory.user_profile_id == user_profile.id
        ).all()
        categories = []
        for uc in user_categories:
            cat = db.query(Category).filter(Category.id == uc.category_id).first()
            if cat:
                categories.append({"id": cat.id, "name": cat.name})

        # Get responsibilities
        user_responsibilities = db.query(UserResponsibility).filter(
            UserResponsibility.user_profile_id == user_profile.id
        ).all()
        responsibilities = []
        for ur in user_responsibilities:
            resp = db.query(Responsibility).filter(Responsibility.id == ur.responsibility_id).first()
            if resp:
                cat = db.query(Category).filter(Category.id == resp.category_id).first()
                responsibilities.append({
                    "id": resp.id,
                    "name": resp.name,
                    "category_name": cat.name if cat else "Unknown"
                })

        # Get permissions
        user_perms = db.query(UserPermissions).filter(
            UserPermissions.user_profile_id == user_profile.id
        ).first()

        template_name = "Custom Permissions"
        if user_profile.permission_template_id:
            template = db.query(PermissionTemplate).filter(
                PermissionTemplate.id == user_profile.permission_template_id
            ).first()
            if template:
                template_name = template.name

        perm_summary = generate_permission_summary(user_perms.permissions if user_perms else {})

        # Generate scorecard preview
        scorecard_preview = generate_scorecard_preview(responsibilities, db, Responsibility)

        return {
            "success": True,
            "data": {
                "user": {
                    "id": user.id,
                    "first_name": user_profile.first_name,
                    "last_name": user_profile.last_name,
                    "email": user.email,
                    "phone": user.phone,
                    "internal_title": user_profile.internal_title,
                    "profile_image_url": user_profile.profile_image_url
                },
                "role": {
                    "id": role.id if role else None,
                    "name": role.name if role else "Not assigned"
                },
                "categories": categories,
                "responsibilities": responsibilities,
                "permissions": {
                    "template_name": template_name,
                    "source": user_perms.source if user_perms else "none",
                    "summary": perm_summary
                },
                "scorecard_preview": scorecard_preview
            }
        }

    @router.post("/create/single/finalize")
    async def finalize_single_user(
        data: FinalizeUserRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Final step: Generate scorecard, create activation token, send email
        """
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        # Validate session
        session = db.query(OnboardingSession).filter(
            OnboardingSession.id == data.onboarding_session_id,
            OnboardingSession.user_id == data.user_id,
            OnboardingSession.status == "in_progress"
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Onboarding session not found")

        user = db.query(User).filter(User.id == data.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user_profile = db.query(UserProfile).filter(
            UserProfile.user_id == data.user_id
        ).first()

        if not user_profile:
            raise HTTPException(status_code=404, detail="User profile not found")

        try:
            # Get responsibilities for scorecard generation
            user_responsibilities = db.query(UserResponsibility).filter(
                UserResponsibility.user_profile_id == user_profile.id
            ).all()
            responsibility_ids = [ur.responsibility_id for ur in user_responsibilities]

            # Generate KPI Scorecard
            scorecard_config = generate_kpi_scorecard_config(responsibility_ids, db, Responsibility)

            scorecard = KPIScorecard(
                user_profile_id=user_profile.id,
                scorecard_config=scorecard_config
            )
            db.add(scorecard)

            # Generate activation token
            activation_token = generate_activation_token()
            user_profile.activation_token = activation_token
            user_profile.activation_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            user_profile.status = "active_awaiting_setup"

            # Update session
            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)

            # Audit log
            audit_log = UserAuditLog(
                user_id=user.id,
                action="user_finalized",
                performed_by=current_user.id,
                details={
                    "scorecard_generated": True,
                    "activation_token_expires": user_profile.activation_token_expires_at.isoformat()
                },
                ip_address=request.client.host if request.client else None
            )
            db.add(audit_log)

            db.commit()

            # Send activation email
            email_sent = False
            if email_service:
                try:
                    email_sent = email_service.send_activation_email(
                        to_email=user.email,
                        user_name=user_profile.first_name,
                        activation_token=activation_token,
                        base_url=FRONTEND_URL
                    )
                    if email_sent:
                        logger.info(f"Activation email sent to {user.email}")
                    else:
                        logger.warning(f"Failed to send activation email to {user.email}")
                except Exception as e:
                    logger.error(f"Error sending activation email: {e}")
            else:
                logger.warning("Email service not configured - activation email not sent")

            return {
                "success": True,
                "data": {
                    "user_id": user.id,
                    "email": user.email,
                    "status": "active_awaiting_setup",
                    "scorecard_id": scorecard.id,
                    "activation_email_sent": email_sent,
                    "activation_token_expires_at": user_profile.activation_token_expires_at.isoformat(),
                    "activation_url": f"{FRONTEND_URL}/activate?token={activation_token}" if not email_sent else None
                }
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error finalizing user: {e}")
            raise HTTPException(status_code=500, detail="Failed to finalize user")

    # ========================================================================
    # REFERENCE DATA ENDPOINTS
    # ========================================================================

    @router.get("/roles")
    async def list_roles(
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """List all available roles"""
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        roles = db.query(Role).filter(Role.is_active == True).order_by(Role.name).all()

        return {
            "success": True,
            "data": {
                "roles": [
                    {
                        "id": r.id,
                        "name": r.name,
                        "description": r.description
                    }
                    for r in roles
                ]
            }
        }

    @router.get("/roles/{role_id}/defaults")
    async def get_role_defaults(
        role_id: int,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Get default categories, responsibilities, and permission template for a role"""
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        # Get default categories
        default_cats = db.query(RoleDefaultCategory).filter(
            RoleDefaultCategory.role_id == role_id
        ).all()
        categories = []
        for dc in default_cats:
            cat = db.query(Category).filter(Category.id == dc.category_id).first()
            if cat:
                categories.append({"id": cat.id, "name": cat.name})

        # Get default responsibilities
        default_resps = db.query(RoleDefaultResponsibility).filter(
            RoleDefaultResponsibility.role_id == role_id
        ).all()
        responsibilities = []
        for dr in default_resps:
            resp = db.query(Responsibility).filter(Responsibility.id == dr.responsibility_id).first()
            if resp:
                cat = db.query(Category).filter(Category.id == resp.category_id).first()
                responsibilities.append({
                    "id": resp.id,
                    "name": resp.name,
                    "category_id": resp.category_id,
                    "category_name": cat.name if cat else "Unknown"
                })

        # Get default permission template
        default_template = None
        if role.default_permission_template_id:
            template = db.query(PermissionTemplate).filter(
                PermissionTemplate.id == role.default_permission_template_id
            ).first()
            if template:
                default_template = {"id": template.id, "name": template.name}

        return {
            "success": True,
            "data": {
                "role_id": role.id,
                "role_name": role.name,
                "default_categories": categories,
                "default_responsibilities": responsibilities,
                "default_permission_template": default_template
            }
        }

    @router.get("/categories")
    async def list_categories(
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """List all available categories"""
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        categories = db.query(Category).filter(
            Category.is_active == True
        ).order_by(Category.sort_order, Category.name).all()

        return {
            "success": True,
            "data": {
                "categories": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "description": c.description
                    }
                    for c in categories
                ]
            }
        }

    @router.post("/responsibilities/filter")
    async def filter_responsibilities(
        data: ResponsibilityFilterRequest,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Get responsibilities filtered by categories and optionally role"""
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        query = db.query(Responsibility).filter(
            Responsibility.is_active == True,
            Responsibility.category_id.in_(data.category_ids)
        )

        responsibilities = query.order_by(Responsibility.name).all()

        result = []
        for r in responsibilities:
            cat = db.query(Category).filter(Category.id == r.category_id).first()
            result.append({
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "category_id": r.category_id,
                "category_name": cat.name if cat else "Unknown"
            })

        return {
            "success": True,
            "data": {
                "responsibilities": result
            }
        }

    @router.get("/permission-templates")
    async def list_permission_templates(
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """List all permission templates"""
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        templates = db.query(PermissionTemplate).order_by(
            PermissionTemplate.is_system_template.desc(),
            PermissionTemplate.name
        ).all()

        return {
            "success": True,
            "data": {
                "templates": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "description": t.description,
                        "is_system_template": t.is_system_template
                    }
                    for t in templates
                ]
            }
        }

    @router.get("/permission-templates/{template_id}")
    async def get_permission_template_details(
        template_id: int,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Get full details of a permission template including permissions JSON"""
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(status_code=403, detail="Permission denied")

        template = db.query(PermissionTemplate).filter(
            PermissionTemplate.id == template_id
        ).first()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        return {
            "success": True,
            "data": {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "is_system_template": template.is_system_template,
                "permissions": template.permissions
            }
        }

    # ========================================================================
    # USER ACTIVATION ENDPOINTS
    # ========================================================================

    @router.get("/activate/validate/{activation_token}")
    async def validate_activation_token(
        activation_token: str,
        db: Session = Depends(get_db)
    ):
        """Validate an activation token"""
        user_profile = db.query(UserProfile).filter(
            UserProfile.activation_token == activation_token
        ).first()

        if not user_profile:
            raise HTTPException(status_code=400, detail="Invalid activation token")

        if user_profile.activation_token_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Activation token has expired")

        if user_profile.status == "active":
            raise HTTPException(status_code=400, detail="User is already activated")

        user = db.query(User).filter(User.id == user_profile.user_id).first()
        role = db.query(Role).filter(Role.id == user_profile.role_id).first()

        return {
            "success": True,
            "data": {
                "token_valid": True,
                "user": {
                    "id": user.id,
                    "first_name": user_profile.first_name,
                    "last_name": user_profile.last_name,
                    "email": user.email,
                    "role_name": role.name if role else "Unknown"
                },
                "expires_at": user_profile.activation_token_expires_at.isoformat()
            }
        }

    @router.post("/activate/set-password")
    async def activate_set_password(
        data: ActivatePasswordRequest,
        request: Request,
        db: Session = Depends(get_db)
    ):
        """Set password and activate user account"""
        user_profile = db.query(UserProfile).filter(
            UserProfile.activation_token == data.activation_token
        ).first()

        if not user_profile:
            raise HTTPException(status_code=400, detail="Invalid activation token")

        if user_profile.activation_token_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Activation token has expired")

        user = db.query(User).filter(User.id == user_profile.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            # Hash and store password
            user.hashed_password = pwd_context.hash(data.password)
            user.is_active = True

            # Update profile status
            user_profile.status = "active"
            user_profile.activated_at = datetime.now(timezone.utc)
            user_profile.activation_token = None  # Clear the token

            # Audit log
            audit_log = UserAuditLog(
                user_id=user.id,
                action="user_activated",
                performed_by=user.id,
                details={"activation_method": "email_token"},
                ip_address=request.client.host if request.client else None
            )
            db.add(audit_log)

            db.commit()

            # Generate auth token
            access_token = create_access_token(data={"sub": user.email})

            return {
                "success": True,
                "data": {
                    "user_id": user.id,
                    "status": "active",
                    "redirect_url": "/dashboard",
                    "auth_token": access_token
                }
            }

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error activating user: {e}")
            raise HTTPException(status_code=500, detail="Failed to activate user")

    return router


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_permission_summary(permissions: Dict[str, Any]) -> str:
    """Generate a human-readable summary of permissions"""
    if not permissions:
        return "No permissions configured"

    summary_parts = []

    # Check leads permissions
    leads = permissions.get('leads', {})
    if leads.get('view') and leads.get('edit'):
        summary_parts.append("Can view and edit leads")
    elif leads.get('view'):
        summary_parts.append("Can view leads only")

    # Check loans permissions
    loans = permissions.get('active_loans', {})
    if loans.get('view_all_branch'):
        summary_parts.append("can view all branch loans")
    elif loans.get('view_assigned'):
        summary_parts.append("can view assigned loans only")

    # Check MUM permissions
    mum = permissions.get('mum', {})
    if mum.get('execute_annual_reviews'):
        summary_parts.append("can execute MUM annual reviews")

    # Check admin permissions
    admin = permissions.get('admin', {})
    if admin.get('manage_users'):
        summary_parts.append("can manage users")
    else:
        summary_parts.append("no admin access")

    return "; ".join(summary_parts) if summary_parts else "Standard permissions"


def generate_scorecard_preview(responsibilities: List[dict], db: Session, Responsibility) -> dict:
    """Generate a preview of the KPI scorecard based on responsibilities"""
    preview = {
        "daily_kpis": [],
        "weekly_kpis": [],
        "monthly_kpis": [],
        "efficiency_scores": [],
        "communication_scores": [],
        "referral_scores": [],
        "mum_engagement_scores": []
    }

    # Get full responsibility objects with KPI mappings
    resp_ids = [r['id'] for r in responsibilities]
    full_resps = db.query(Responsibility).filter(
        Responsibility.id.in_(resp_ids)
    ).all()

    for resp in full_resps:
        if resp.kpi_mapping:
            kpi_map = resp.kpi_mapping
            for kpi_type in preview.keys():
                if kpi_type in kpi_map:
                    for kpi_id in kpi_map[kpi_type]:
                        kpi_def = get_kpi_definition(kpi_id)
                        if kpi_def and kpi_def not in preview[kpi_type]:
                            preview[kpi_type].append(kpi_def)

    return preview


def generate_kpi_scorecard_config(responsibility_ids: List[int], db: Session, Responsibility) -> dict:
    """Generate full KPI scorecard configuration from responsibilities"""
    config = {
        "daily_kpis": [],
        "weekly_kpis": [],
        "monthly_kpis": [],
        "efficiency_scores": [],
        "communication_scores": [],
        "referral_scores": [],
        "mum_engagement_scores": []
    }

    responsibilities = db.query(Responsibility).filter(
        Responsibility.id.in_(responsibility_ids)
    ).all()

    seen_kpis = set()

    for resp in responsibilities:
        if resp.kpi_mapping:
            kpi_map = resp.kpi_mapping
            for kpi_type in config.keys():
                if kpi_type in kpi_map:
                    for kpi_id in kpi_map[kpi_type]:
                        if kpi_id not in seen_kpis:
                            kpi_def = get_full_kpi_definition(kpi_id)
                            if kpi_def:
                                config[kpi_type].append(kpi_def)
                                seen_kpis.add(kpi_id)

    return config


# KPI Library - Full definitions
KPI_LIBRARY = {
    "leads_contacted": {
        "id": "leads_contacted_daily",
        "name": "Leads Contacted",
        "description": "Number of leads contacted via phone or email each day"
    },
    "leads_qualified": {
        "id": "leads_qualified_daily",
        "name": "Leads Qualified",
        "description": "Number of leads successfully qualified"
    },
    "outbound_calls_made": {
        "id": "outbound_calls_daily",
        "name": "Outbound Calls",
        "description": "Number of outbound prospecting calls made"
    },
    "leads_generated": {
        "id": "leads_generated_daily",
        "name": "Leads Generated",
        "description": "Number of new leads generated"
    },
    "follow_up_calls": {
        "id": "follow_up_calls_daily",
        "name": "Follow-up Calls",
        "description": "Number of follow-up calls completed"
    },
    "emails_sent": {
        "id": "emails_sent_daily",
        "name": "Emails Sent",
        "description": "Number of emails sent to leads"
    },
    "milestone_updates_sent": {
        "id": "milestone_updates_daily",
        "name": "Milestone Updates",
        "description": "Number of milestone updates sent to borrowers"
    },
    "documents_requested": {
        "id": "documents_requested_daily",
        "name": "Documents Requested",
        "description": "Number of document requests sent"
    },
    "documents_received": {
        "id": "documents_received_daily",
        "name": "Documents Received",
        "description": "Number of documents received and processed"
    },
    "issues_resolved": {
        "id": "issues_resolved_daily",
        "name": "Issues Resolved",
        "description": "Number of borrower issues resolved"
    },
    "applications_reviewed": {
        "id": "applications_reviewed_daily",
        "name": "Applications Reviewed",
        "description": "Number of applications reviewed for completeness"
    },
    "credit_analyses_completed": {
        "id": "credit_analyses_daily",
        "name": "Credit Analyses",
        "description": "Number of credit analyses completed"
    },
    "income_verifications_completed": {
        "id": "income_verifications_daily",
        "name": "Income Verifications",
        "description": "Number of income verifications completed"
    },
    "prequalifications_issued": {
        "id": "prequalifications_daily",
        "name": "Pre-qualifications Issued",
        "description": "Number of pre-qualification letters issued"
    },
    "milestones_updated": {
        "id": "milestones_updated_daily",
        "name": "Milestones Updated",
        "description": "Number of loan milestones updated"
    },
    "conditions_cleared": {
        "id": "conditions_cleared_daily",
        "name": "Conditions Cleared",
        "description": "Number of underwriting conditions cleared"
    },
    "uw_submissions": {
        "id": "uw_submissions_daily",
        "name": "UW Submissions",
        "description": "Number of files submitted to underwriting"
    },
    "rate_alerts_sent": {
        "id": "rate_alerts_daily",
        "name": "Rate Alerts",
        "description": "Number of rate alert notifications sent"
    },
    "lead_conversion_rate": {
        "id": "lead_conversion_weekly",
        "name": "Lead Conversion Rate",
        "description": "Percentage of leads converted to applications"
    },
    "consultations_completed": {
        "id": "consultations_weekly",
        "name": "Consultations Completed",
        "description": "Number of borrower consultations completed"
    },
    "preapprovals_issued": {
        "id": "preapprovals_weekly",
        "name": "Pre-approvals Issued",
        "description": "Number of pre-approval letters issued"
    },
    "preapproval_followups": {
        "id": "preapproval_followups_weekly",
        "name": "Pre-approval Follow-ups",
        "description": "Number of pre-approval follow-ups completed"
    },
    "partner_updates_sent": {
        "id": "partner_updates_weekly",
        "name": "Partner Updates",
        "description": "Number of updates sent to referral partners"
    },
    "orders_placed": {
        "id": "orders_placed_weekly",
        "name": "Orders Placed",
        "description": "Number of title/appraisal orders placed"
    },
    "closing_docs_prepared": {
        "id": "closing_docs_weekly",
        "name": "Closing Docs Prepared",
        "description": "Number of closing document packages prepared"
    },
    "closings_scheduled": {
        "id": "closings_scheduled_weekly",
        "name": "Closings Scheduled",
        "description": "Number of closings scheduled"
    },
    "walkthroughs_completed": {
        "id": "walkthroughs_weekly",
        "name": "Walkthroughs Completed",
        "description": "Number of final walkthroughs completed"
    },
    "rate_locks_executed": {
        "id": "rate_locks_weekly",
        "name": "Rate Locks Executed",
        "description": "Number of rate locks executed"
    },
    "referral_acknowledgments_sent": {
        "id": "referral_acks_weekly",
        "name": "Referral Acknowledgments",
        "description": "Number of referral acknowledgments sent"
    },
    "prospecting_volume": {
        "id": "prospecting_monthly",
        "name": "Prospecting Volume",
        "description": "Total prospecting activity volume for the month"
    },
    "partner_meetings": {
        "id": "partner_meetings_monthly",
        "name": "Partner Meetings",
        "description": "Number of partner relationship meetings"
    },
    "partners_onboarded": {
        "id": "partners_onboarded_monthly",
        "name": "Partners Onboarded",
        "description": "Number of new partners onboarded"
    },
    "post_close_contacts": {
        "id": "post_close_monthly",
        "name": "Post-Close Contacts",
        "description": "Number of post-closing follow-up contacts"
    },
    "annual_reviews_completed": {
        "id": "annual_reviews_monthly",
        "name": "Annual Reviews",
        "description": "Number of MUM annual reviews completed"
    },
    "refi_opportunities_identified": {
        "id": "refi_opportunities_monthly",
        "name": "Refi Opportunities",
        "description": "Number of refinance opportunities identified"
    },
    "referrals_tracked": {
        "id": "referrals_tracked_monthly",
        "name": "Referrals Tracked",
        "description": "Number of referrals tracked and attributed"
    },
    "incentives_distributed": {
        "id": "incentives_monthly",
        "name": "Incentives Distributed",
        "description": "Number of referral incentives distributed"
    },
    "response_time": {
        "id": "response_time_efficiency",
        "name": "Response Time",
        "description": "Average time to respond to lead inquiries"
    },
    "review_time": {
        "id": "review_time_efficiency",
        "name": "Review Time",
        "description": "Average time to review applications"
    },
    "prequal_turnaround_time": {
        "id": "prequal_turnaround_efficiency",
        "name": "Pre-qual Turnaround",
        "description": "Average pre-qualification turnaround time"
    },
    "consultation_to_app_rate": {
        "id": "consultation_conversion_efficiency",
        "name": "Consultation to App Rate",
        "description": "Percentage of consultations converting to applications"
    },
    "document_collection_rate": {
        "id": "doc_collection_efficiency",
        "name": "Document Collection Rate",
        "description": "Rate of successful document collection"
    },
    "preapproval_to_app_conversion": {
        "id": "preapproval_conversion_efficiency",
        "name": "Pre-approval Conversion",
        "description": "Percentage of pre-approvals converting to full applications"
    },
    "condition_clearance_rate": {
        "id": "condition_clearance_efficiency",
        "name": "Condition Clearance Rate",
        "description": "Rate of successful condition clearance"
    },
    "borrower_satisfaction": {
        "id": "borrower_satisfaction_communication",
        "name": "Borrower Satisfaction",
        "description": "Borrower satisfaction score based on feedback"
    },
    "update_timeliness": {
        "id": "update_timeliness_communication",
        "name": "Update Timeliness",
        "description": "Timeliness of milestone updates"
    },
    "resolution_time": {
        "id": "resolution_time_communication",
        "name": "Resolution Time",
        "description": "Average time to resolve borrower issues"
    },
    "partner_satisfaction": {
        "id": "partner_satisfaction_referral",
        "name": "Partner Satisfaction",
        "description": "Referral partner satisfaction score"
    },
    "referral_volume_from_partners": {
        "id": "referral_volume_referral",
        "name": "Referral Volume",
        "description": "Volume of referrals from partners"
    },
    "referral_source_diversity": {
        "id": "source_diversity_referral",
        "name": "Source Diversity",
        "description": "Diversity of referral sources"
    },
    "acknowledgment_timeliness": {
        "id": "ack_timeliness_referral",
        "name": "Acknowledgment Timeliness",
        "description": "Timeliness of referral acknowledgments"
    },
    "borrower_retention": {
        "id": "borrower_retention_mum",
        "name": "Borrower Retention",
        "description": "MUM borrower retention rate"
    },
    "review_completion_rate": {
        "id": "review_completion_mum",
        "name": "Review Completion Rate",
        "description": "Percentage of annual reviews completed"
    },
    "refi_conversion_rate": {
        "id": "refi_conversion_mum",
        "name": "Refi Conversion Rate",
        "description": "Percentage of refi opportunities converted"
    }
}


def get_kpi_definition(kpi_id: str) -> Optional[dict]:
    """Get a simple KPI definition for preview"""
    kpi = KPI_LIBRARY.get(kpi_id)
    if kpi:
        return {
            "name": kpi["name"],
            "description": kpi["description"]
        }
    return None


def get_full_kpi_definition(kpi_id: str) -> Optional[dict]:
    """Get the full KPI definition for scorecard"""
    return KPI_LIBRARY.get(kpi_id)
