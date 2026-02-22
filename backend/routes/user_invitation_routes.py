"""
User Invitation Routes
Handles inviting new users to the system and managing invitation lifecycle.
"""

import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/invitations", tags=["User Invitations"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class InviteUserRequest(BaseModel):
    """Request to invite a new user"""
    email: EmailStr = Field(..., description="Email address to invite")
    full_name: str = Field(..., min_length=1, max_length=200, description="Full name of the user")
    role: str = Field(default="sales", description="Permission role: admin, leadership, management, sales, processing, operations")
    send_email: bool = Field(default=True, description="Whether to send the invitation email")


class InvitationResponse(BaseModel):
    """Response after creating an invitation"""
    id: int
    email: str
    full_name: str
    role: str
    status: str
    invitation_token: Optional[str] = None
    invitation_url: Optional[str] = None
    expires_at: str
    created_at: str


class SetPasswordRequest(BaseModel):
    """Request to set password during activation"""
    token: str = Field(..., description="Invitation token from email")
    password: str = Field(..., min_length=8, description="New password")
    confirm_password: str = Field(..., description="Password confirmation")


class ResendInvitationRequest(BaseModel):
    """Request to resend an invitation"""
    user_id: int = Field(..., description="User ID to resend invitation to")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_invitation_token() -> str:
    """Generate a secure invitation token"""
    return secrets.token_urlsafe(32)


def get_user_invitation_routes(
    get_db,
    get_current_user,
    User,
    get_password_hash,
    create_access_token,
    email_service
):
    """
    Factory function to create invitation routes with injected dependencies.
    """
    import os
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://perenniaai.com")

    @router.post("", response_model=InvitationResponse)
    async def invite_user(
        request: InviteUserRequest,
        req: Request,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Invite a new user to the system.

        Admins, leadership, and management can invite new users.
        Creates a pending user account and sends an activation email.
        """
        # Check permission - allow admin, leadership, and management roles
        # Also allow the first user (master admin) regardless of role
        allowed_roles = ['admin', 'leadership', 'management']
        user_role = (current_user.permission_role or '').lower().strip()
        user_functional_role = (getattr(current_user, 'role', '') or '').lower().strip()
        is_master_user = current_user.id == 1

        # Also check if user has admin in their functional role field (some users have role vs permission_role)
        has_admin_role = (
            user_role in allowed_roles or
            user_functional_role in allowed_roles or
            'admin' in user_role or
            'admin' in user_functional_role
        )

        logger.info(f"Invite permission check: user_id={current_user.id}, permission_role='{current_user.permission_role}', role='{getattr(current_user, 'role', None)}', is_master={is_master_user}, has_admin={has_admin_role}")

        if not is_master_user and not has_admin_role:
            logger.warning(f"User {current_user.id} with role '{current_user.permission_role}' attempted to invite user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins, leadership, and management can invite users"
            )

        # Check if email already exists
        existing_user = db.query(User).filter(User.email == request.email).first()
        if existing_user:
            if existing_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A user with this email already exists and is active"
                )
            else:
                # User exists but is inactive - resend invitation
                return await _resend_invitation_for_user(existing_user, db, request.send_email, FRONTEND_URL, email_service)

        # Validate role
        valid_roles = ['admin', 'leadership', 'management', 'sales', 'processing', 'operations']
        if request.role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            )

        try:
            # Generate invitation token
            invitation_token = generate_invitation_token()
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)

            # Create the user with pending status
            # Split full_name into first/last for User columns
            _name_parts = (request.full_name or '').strip().split(' ', 1)
            new_user = User(
                email=request.email,
                hashed_password="",  # Will be set during activation
                first_name=_name_parts[0] if _name_parts else '',
                last_name=_name_parts[1] if len(_name_parts) > 1 else '',
                role="pending",
                permission_role=request.role,
                is_active=False,
                # Store invitation data in user_metadata JSON field
                user_metadata={
                    "invitation_token": invitation_token,
                    "invitation_expires_at": expires_at.isoformat(),
                    "invited_by": current_user.id,
                    "invited_at": datetime.now(timezone.utc).isoformat(),
                    "status": "pending"
                }
            )

            # Set organization_id if current user has one
            if hasattr(current_user, 'organization_id') and current_user.organization_id:
                new_user.organization_id = current_user.organization_id

            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            invitation_url = f"{FRONTEND_URL}/activate?token={invitation_token}"

            # Send invitation email if requested
            if request.send_email:
                try:
                    email_sent = email_service.send_activation_email(
                        to_email=request.email,
                        user_name=request.full_name.split()[0],  # First name
                        activation_token=invitation_token,
                        base_url=FRONTEND_URL
                    )
                    if email_sent:
                        logger.info(f"Invitation email sent to {request.email}")
                    else:
                        logger.warning(f"Failed to send invitation email to {request.email}")
                except Exception as e:
                    logger.error(f"Error sending invitation email: {e}")
                    # Don't fail the invitation creation if email fails

            logger.info(f"User invited: {request.email} by {current_user.email}")

            return InvitationResponse(
                id=new_user.id,
                email=new_user.email,
                full_name=new_user.full_name,
                role=request.role,
                status="pending",
                invitation_token=invitation_token if not request.send_email else None,  # Only return token if email not sent
                invitation_url=invitation_url if not request.send_email else None,
                expires_at=expires_at.isoformat(),
                created_at=datetime.now(timezone.utc).isoformat()
            )

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error inviting user: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create invitation"
            )


    async def _resend_invitation_for_user(user, db: Session, send_email: bool, frontend_url: str, email_svc) -> InvitationResponse:
        """Helper to resend invitation for existing inactive user"""
        # Generate new token
        invitation_token = generate_invitation_token()
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        # Update user metadata
        user_meta = user.user_metadata or {}
        user_meta["invitation_token"] = invitation_token
        user_meta["invitation_expires_at"] = expires_at.isoformat()
        user_meta["resent_at"] = datetime.now(timezone.utc).isoformat()
        user.user_metadata = user_meta

        db.commit()
        db.refresh(user)

        invitation_url = f"{frontend_url}/activate?token={invitation_token}"

        # Send email
        if send_email:
            try:
                email_svc.send_activation_email(
                    to_email=user.email,
                    user_name=user.full_name.split()[0] if user.full_name else "User",
                    activation_token=invitation_token,
                    base_url=frontend_url
                )
            except SQLAlchemyError as e:
                logger.error(f"Error sending invitation email: {e}")

        return InvitationResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name or "",
            role=user.permission_role or "sales",
            status="pending (resent)",
            invitation_token=invitation_token if not send_email else None,
            invitation_url=invitation_url if not send_email else None,
            expires_at=expires_at.isoformat(),
            created_at=datetime.now(timezone.utc).isoformat()
        )


    @router.get("")
    async def list_invitations(
        status_filter: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        List all pending invitations.

        Only admins and leadership can view invitations.
        """
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins and leadership can view invitations"
            )

        # Query inactive users (pending invitations)
        query = db.query(User).filter(User.is_active == False)

        if status_filter == "pending":
            query = query.filter(User.hashed_password == "")
        elif status_filter == "expired":
            # This would require checking user_metadata, which is more complex
            pass

        pending_users = query.all()

        invitations = []
        for user in pending_users:
            user_meta = user.user_metadata or {}
            expires_at = user_meta.get("invitation_expires_at")
            is_expired = False

            if expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    is_expired = exp_dt < datetime.now(timezone.utc)
                except Exception as e:
                    logger.error(f"Error parsing invitation expiry date: {e}")

            invitations.append({
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.permission_role,
                "status": "expired" if is_expired else "pending",
                "invited_at": user_meta.get("invited_at"),
                "expires_at": expires_at,
                "resent_at": user_meta.get("resent_at")
            })

        return {
            "invitations": invitations,
            "total": len(invitations)
        }


    @router.post("/resend")
    async def resend_invitation(
        request: ResendInvitationRequest,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Resend an invitation email to a pending user.
        """
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins and leadership can resend invitations"
            )

        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already active"
            )

        return await _resend_invitation_for_user(user, db, True, FRONTEND_URL, email_service)


    @router.delete("/{user_id}")
    async def revoke_invitation(
        user_id: int,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """
        Revoke a pending invitation by deleting the user.
        """
        if current_user.permission_role not in ['admin', 'site_admin', 'leadership']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins and leadership can revoke invitations"
            )

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot revoke invitation for active user"
            )

        email = user.email
        db.delete(user)
        db.commit()

        logger.info(f"Invitation revoked for {email} by {current_user.email}")

        return {"message": f"Invitation for {email} has been revoked"}


    @router.get("/validate/{token}")
    async def validate_invitation_token(
        token: str,
        db: Session = Depends(get_db)
    ):
        """
        Validate an invitation token (public endpoint for activation page).
        """
        # Find user with this token
        users = db.query(User).filter(User.is_active == False).all()

        for user in users:
            user_meta = user.user_metadata or {}
            import hmac
            if hmac.compare_digest(user_meta.get("invitation_token") or "", token):
                # Check expiration
                expires_at = user_meta.get("invitation_expires_at")
                if expires_at:
                    try:
                        exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                        if exp_dt < datetime.now(timezone.utc):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Invitation has expired. Please request a new invitation."
                            )
                    except ValueError:
                        pass

                return {
                    "valid": True,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.permission_role
                }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token"
        )


    @router.post("/activate")
    async def activate_account(
        request: SetPasswordRequest,
        db: Session = Depends(get_db)
    ):
        """
        Activate account by setting password (public endpoint).
        """
        if request.password != request.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )

        # Validate password strength
        if len(request.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters"
            )

        # Find user with this token
        users = db.query(User).filter(User.is_active == False).all()
        target_user = None

        for user in users:
            user_meta = user.user_metadata or {}
            import hmac
            if hmac.compare_digest(user_meta.get("invitation_token") or "", request.token):
                # Check expiration
                expires_at = user_meta.get("invitation_expires_at")
                if expires_at:
                    try:
                        exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                        if exp_dt < datetime.now(timezone.utc):
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Invitation has expired. Please request a new invitation."
                            )
                    except ValueError:
                        pass
                target_user = user
                break

        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invitation token"
            )

        try:
            # Set password and activate
            target_user.hashed_password = get_password_hash(request.password)
            target_user.is_active = True
            target_user.role = target_user.permission_role  # Sync role field

            # Update metadata
            user_meta = target_user.user_metadata or {}
            user_meta["status"] = "active"
            user_meta["activated_at"] = datetime.now(timezone.utc).isoformat()
            user_meta.pop("invitation_token", None)  # Remove token
            target_user.user_metadata = user_meta

            db.commit()
            db.refresh(target_user)

            # Generate access token for immediate login
            access_token = create_access_token(data={"sub": target_user.email})

            logger.info(f"User activated: {target_user.email}")

            return {
                "success": True,
                "message": "Account activated successfully",
                "user": {
                    "id": target_user.id,
                    "email": target_user.email,
                    "full_name": target_user.full_name,
                    "role": target_user.permission_role
                },
                "access_token": access_token,
                "token_type": "bearer"
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error activating user: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to activate account"
            )

    return router
