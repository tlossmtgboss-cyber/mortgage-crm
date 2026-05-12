"""
User Invitation Routes (Consolidated)

All invitation storage now uses the employee_invites table (Path B).
These endpoints maintain backward compatibility with the /api/v1/invitations prefix
while routing through the canonical EmployeeInvite model.

Previously stored tokens in User.user_metadata JSON — now deprecated.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from utils.roles import ALLOWED_ROLES, INVITE_GRANTING_ROLES, ADMIN_ROLES, validate_role
from utils.token_security import generate_invite_token, safe_token_compare
from utils.password_policy import validate_password
from utils.invitation_audit import log_invite_event, mask_email_for_audit

logger = logging.getLogger(__name__)

try:
    from middleware.rate_limiter import rate_limit, ip_key
except ImportError:
    logger.warning("Rate limiter unavailable for invitation routes")

    def rate_limit(**kwargs):
        def decorator(func):
            return func
        return decorator

    def ip_key(request):
        return "unknown"

router = APIRouter(prefix="/api/v1/invitations", tags=["User Invitations"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class InviteUserRequest(BaseModel):
    """Request to invite a new user"""
    email: EmailStr = Field(..., description="Email address to invite")
    full_name: str = Field(..., min_length=1, max_length=200, description="Full name of the user")
    role: str = Field(default="sales", description="Permission role")
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
    user_id: int = Field(..., description="Invite ID to resend")


# ============================================================================
# ROUTE FACTORY
# ============================================================================

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
    Now uses employee_invites table (Path B) as canonical storage.
    """
    import os
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://perenniaai.com")

    def _get_invite_models():
        """Lazy-load EmployeeInvite and InviteStatus."""
        from database.models.permission import EmployeeInvite
        from database.enums import InviteStatus
        return EmployeeInvite, InviteStatus

    def _check_invite_permission(current_user):
        """Check if user can manage invites. Returns normalized role."""
        user_role = (getattr(current_user, 'permission_role', '') or '').lower().strip()
        user_functional_role = (getattr(current_user, 'role', '') or '').lower().strip()
        is_master = current_user.id == 1

        can_invite = (
            user_role in INVITE_GRANTING_ROLES or
            user_functional_role in INVITE_GRANTING_ROLES or
            is_master
        )

        if not can_invite:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins, leadership, and management can manage invites"
            )
        return user_role

    def _enforce_org(current_user):
        """Enforce org assignment. Returns org_id (None for master admin)."""
        _org_id = getattr(current_user, 'organization_id', None)
        if not _org_id and current_user.id != 1:
            raise HTTPException(status_code=403, detail="User not assigned to an organization")
        return _org_id

    @router.post("", response_model=InvitationResponse)
    async def invite_user(
        request: InviteUserRequest,
        req: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
    ):
        """Invite a new user. Creates an EmployeeInvite record."""
        EmployeeInvite, InviteStatus = _get_invite_models()

        inviter_role = _check_invite_permission(current_user)
        _org_id = _enforce_org(current_user)

        # Validate requested role
        try:
            validated_role = validate_role(request.role)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Prevent role escalation -- assigner must be at or above the target role
        from auth.role_guards import enforce_no_escalation
        enforce_no_escalation(inviter_role, validated_role)

        # Check if email already in use (active user in same org)
        _email_query = db.query(User).filter(User.email == request.email, User.is_active == True)
        if _org_id:
            _email_query = _email_query.filter(User.organization_id == _org_id)
        if _email_query.first():
            raise HTTPException(status_code=400, detail="A user with this email already exists and is active")

        # Check for existing pending invite in same org
        _invite_query = db.query(EmployeeInvite).filter(
            EmployeeInvite.email == request.email,
            EmployeeInvite.status == InviteStatus.PENDING
        )
        if _org_id:
            _invite_query = _invite_query.filter(EmployeeInvite.organization_id == _org_id)
        existing_invite = _invite_query.first()

        if existing_invite:
            # Resend the existing invite with a fresh token
            existing_invite.invite_token = generate_invite_token()
            existing_invite.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            db.commit()
            db.refresh(existing_invite)

            _name = f"{existing_invite.first_name or ''} {existing_invite.last_name or ''}".strip()

            log_invite_event(db, "invite_resent", invite_id=existing_invite.id,
                             actor_id=current_user.id, org_id=_org_id, target_email=request.email)

            invite_url = f"{FRONTEND_URL}/accept-invite?token={existing_invite.invite_token}"

            if request.send_email:
                try:
                    email_service.send_activation_email(
                        to_email=request.email,
                        user_name=_name.split()[0] if _name else "User",
                        activation_token=existing_invite.invite_token,
                        base_url=FRONTEND_URL
                    )
                except Exception as e:
                    logger.error(f"Error sending invite email: {e}")

            return InvitationResponse(
                id=existing_invite.id,
                email=existing_invite.email,
                full_name=_name,
                role=existing_invite.permission_role or "sales",
                status="pending (resent)",
                invitation_token=existing_invite.invite_token if not request.send_email else None,
                invitation_url=invite_url if not request.send_email else None,
                expires_at=existing_invite.expires_at.isoformat(),
                created_at=datetime.now(timezone.utc).isoformat()
            )

        # Create new EmployeeInvite record
        try:
            invitation_token = generate_invite_token()
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)

            _name_parts = (request.full_name or '').strip().split(' ', 1)
            first_name = _name_parts[0] if _name_parts else ''
            last_name = _name_parts[1] if len(_name_parts) > 1 else ''

            invite = EmployeeInvite(
                email=request.email,
                first_name=first_name,
                last_name=last_name,
                permission_role=validated_role,
                invite_token=invitation_token,
                status=InviteStatus.PENDING,
                invited_by_user_id=current_user.id,
                organization_id=_org_id,
                expires_at=expires_at,
                initial_config={}
            )
            db.add(invite)
            db.flush()  # Get invite.id before commit

            # Audit log in same transaction so it commits together
            log_invite_event(db, "invite_created", invite_id=invite.id,
                             actor_id=current_user.id, org_id=_org_id, target_email=request.email,
                             details={"role": validated_role})

            db.commit()
            db.refresh(invite)

            invite_url = f"{FRONTEND_URL}/accept-invite?token={invitation_token}"

            if request.send_email:
                try:
                    email_service.send_activation_email(
                        to_email=request.email,
                        user_name=first_name or "User",
                        activation_token=invitation_token,
                        base_url=FRONTEND_URL
                    )
                    logger.info(f"Invitation email sent to {mask_email_for_audit(request.email)}")
                except Exception as e:
                    logger.error(f"Error sending invitation email: {e}")

            logger.info(f"Invite created for {mask_email_for_audit(request.email)} by user {current_user.id}")

            return InvitationResponse(
                id=invite.id,
                email=invite.email,
                full_name=f"{first_name} {last_name}".strip(),
                role=validated_role,
                status="pending",
                invitation_token=invitation_token if not request.send_email else None,
                invitation_url=invite_url if not request.send_email else None,
                expires_at=expires_at.isoformat(),
                created_at=datetime.now(timezone.utc).isoformat()
            )

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating invite: {e}")
            raise HTTPException(status_code=500, detail="Failed to create invitation")


    @router.get("")
    async def list_invitations(
        status_filter: Optional[str] = None,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
    ):
        """List invitations from employee_invites table."""
        EmployeeInvite, InviteStatus = _get_invite_models()

        _check_invite_permission(current_user)
        _org_id = _enforce_org(current_user)

        query = db.query(EmployeeInvite).order_by(EmployeeInvite.created_at.desc())

        if _org_id:
            query = query.filter(EmployeeInvite.organization_id == _org_id)

        if status_filter and status_filter != "all":
            try:
                query = query.filter(EmployeeInvite.status == InviteStatus(status_filter))
            except ValueError:
                pass

        invites = query.all()

        def _effective_status(inv):
            """Return 'expired' if a pending invite has passed its expires_at."""
            raw = inv.status.value if hasattr(inv.status, 'value') else str(inv.status)
            if raw == 'pending' and inv.expires_at and inv.expires_at < datetime.now(timezone.utc):
                return 'expired'
            return raw

        return {
            "invites": [
                {
                    "id": inv.id,
                    "email": inv.email,
                    "first_name": inv.first_name,
                    "last_name": inv.last_name,
                    "job_title": getattr(inv, 'job_title', None),
                    "permission_role": inv.permission_role,
                    "status": _effective_status(inv),
                    "invite_token": inv.invite_token if hasattr(inv.status, 'value') and inv.status.value == 'pending' and not (inv.expires_at and inv.expires_at < datetime.now(timezone.utc)) else None,
                    "created_at": inv.created_at.isoformat() if inv.created_at else None,
                    "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
                    "accepted_at": inv.accepted_at.isoformat() if getattr(inv, 'accepted_at', None) else None,
                }
                for inv in invites
            ]
        }


    @router.post("/resend")
    async def resend_invitation(
        request: ResendInvitationRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
    ):
        """Resend an invitation by invite ID."""
        EmployeeInvite, InviteStatus = _get_invite_models()

        _check_invite_permission(current_user)
        _org_id = _enforce_org(current_user)

        invite = db.query(EmployeeInvite).filter(EmployeeInvite.id == request.user_id).first()
        if not invite:
            raise HTTPException(status_code=404, detail="Invitation not found")

        if _org_id and invite.organization_id != _org_id:
            raise HTTPException(status_code=404, detail="Invitation not found")

        if invite.status not in (InviteStatus.PENDING, InviteStatus.EXPIRED):
            raise HTTPException(status_code=400, detail="Can only resend pending or expired invites")

        # Fresh token and extended expiry
        invite.invite_token = generate_invite_token()
        invite.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        invite.status = InviteStatus.PENDING
        db.commit()
        db.refresh(invite)

        invite_url = f"{FRONTEND_URL}/accept-invite?token={invite.invite_token}"

        try:
            email_service.send_activation_email(
                to_email=invite.email,
                user_name=invite.first_name or "User",
                activation_token=invite.invite_token,
                base_url=FRONTEND_URL
            )
        except Exception as e:
            logger.error(f"Error resending invitation email: {e}")

        log_invite_event(db, "invite_resent", invite_id=invite.id,
                         actor_id=current_user.id, org_id=_org_id, target_email=invite.email)

        _name = f"{invite.first_name or ''} {invite.last_name or ''}".strip()
        return InvitationResponse(
            id=invite.id,
            email=invite.email,
            full_name=_name,
            role=invite.permission_role or "sales",
            status="pending (resent)",
            invitation_token=invite.invite_token,
            invitation_url=invite_url,
            expires_at=invite.expires_at.isoformat(),
            created_at=datetime.now(timezone.utc).isoformat()
        )


    @router.delete("/{user_id}")
    async def revoke_invitation(
        user_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user)
    ):
        """Revoke a pending invitation (soft delete — sets status to revoked)."""
        EmployeeInvite, InviteStatus = _get_invite_models()

        _check_invite_permission(current_user)
        _org_id = _enforce_org(current_user)

        invite = db.query(EmployeeInvite).filter(EmployeeInvite.id == user_id).first()
        if not invite:
            raise HTTPException(status_code=404, detail="Invitation not found")

        if _org_id and invite.organization_id != _org_id:
            raise HTTPException(status_code=404, detail="Invitation not found")

        if invite.status not in (InviteStatus.PENDING, InviteStatus.EXPIRED):
            raise HTTPException(status_code=400, detail="Can only revoke pending or expired invites")

        invite.status = InviteStatus.REVOKED
        invite.invite_token = None  # Clear token
        db.commit()

        log_invite_event(db, "invite_revoked", invite_id=invite.id,
                         actor_id=current_user.id, org_id=_org_id, target_email=invite.email)

        logger.info(f"Invite {invite.id} revoked by user {current_user.id}")

        return {"message": f"Invitation for {mask_email_for_audit(invite.email)} has been revoked"}


    @router.get("/validate/{token}")
    @rate_limit(limit=10, window=300, key_func=ip_key)
    async def validate_invitation_token(
        token: str,
        request: Request,
        db: Session = Depends(get_db)
    ):
        """
        Validate an invitation token (public endpoint).
        Now uses indexed lookup on employee_invites table instead of full table scan.
        """
        EmployeeInvite, InviteStatus = _get_invite_models()

        invite = db.query(EmployeeInvite).filter(EmployeeInvite.invite_token == token).first()

        if not invite or not safe_token_compare(invite.invite_token, token):
            raise HTTPException(status_code=400, detail="Invalid or expired invitation token")

        if invite.status != InviteStatus.PENDING:
            raise HTTPException(status_code=400, detail=f"Invitation has been {invite.status.value}")

        if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
            invite.status = InviteStatus.EXPIRED
            db.commit()
            raise HTTPException(status_code=400, detail="Invitation has expired. Please request a new invitation.")

        return {
            "valid": True,
            "email": invite.email,
            "full_name": f"{invite.first_name or ''} {invite.last_name or ''}".strip(),
            "role": invite.permission_role
        }


    @router.post("/activate")
    @rate_limit(limit=5, window=300, key_func=ip_key)
    async def activate_account(
        request: Request,
        body: SetPasswordRequest,
        db: Session = Depends(get_db)
    ):
        """
        Activate account by setting password (public endpoint).
        Now uses employee_invites table for token lookup and creates user on accept.
        """
        if body.password != body.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        # Unified password policy
        validate_password(body.password)

        EmployeeInvite, InviteStatus = _get_invite_models()
        _client_ip = request.client.host if request.client else None

        # Indexed lookup instead of full table scan
        invite = db.query(EmployeeInvite).filter(EmployeeInvite.invite_token == body.token).first()

        if not invite or not safe_token_compare(invite.invite_token, body.token):
            log_invite_event(db, "invite_accept_failed", details={"reason": "invalid_token"}, ip_address=_client_ip)
            raise HTTPException(status_code=400, detail="Invalid or expired invitation token")

        if invite.status != InviteStatus.PENDING:
            log_invite_event(db, "invite_accept_failed", invite_id=invite.id,
                             target_email=invite.email, details={"reason": f"status_{invite.status.value}"},
                             ip_address=_client_ip)
            raise HTTPException(status_code=400, detail=f"Invitation has been {invite.status.value}")

        if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
            invite.status = InviteStatus.EXPIRED
            db.commit()
            log_invite_event(db, "invite_accept_failed", invite_id=invite.id,
                             target_email=invite.email, details={"reason": "expired"}, ip_address=_client_ip)
            raise HTTPException(status_code=400, detail="Invitation has expired. Please request a new invitation.")

        # --- Seat limit enforcement with FOR UPDATE lock ---
        _org_id = invite.organization_id
        if not _org_id and invite.invited_by_user_id:
            _inviter = db.query(User).filter(User.id == invite.invited_by_user_id).first()
            if _inviter:
                _org_id = getattr(_inviter, 'organization_id', None)

        if _org_id:
            from sqlalchemy import func as _fn
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
                    raise HTTPException(status_code=403, detail="Seat limit reached. Contact your administrator to upgrade.")

        try:
            # Create user from invite data
            new_user = User(
                email=invite.email,
                hashed_password=get_password_hash(body.password),
                first_name=invite.first_name or '',
                last_name=invite.last_name or '',
                role=invite.permission_role,
                permission_role=invite.permission_role,
                is_active=True,
                organization_id=_org_id,
                branch_id=invite.branch_id,
            )
            db.add(new_user)
            db.flush()

            # Update invite status
            invite.status = InviteStatus.ACCEPTED
            invite.accepted_at = datetime.now(timezone.utc)
            invite.user_id = new_user.id
            invite.invite_token = None  # Clear token after use

            db.commit()
            db.refresh(new_user)

            # Generate access token for immediate login
            access_token = create_access_token(data={"sub": new_user.email})

            log_invite_event(db, "invite_accepted", invite_id=invite.id,
                             org_id=_org_id, target_email=invite.email,
                             details={"user_id": new_user.id, "role": invite.permission_role},
                             ip_address=_client_ip)

            logger.info(f"User activated via invite {invite.id}: {mask_email_for_audit(invite.email)}")

            return {
                "success": True,
                "message": "Account activated successfully",
                "user": {
                    "id": new_user.id,
                    "email": new_user.email,
                    "full_name": f"{new_user.first_name} {new_user.last_name}".strip(),
                    "role": new_user.permission_role
                },
                "access_token": access_token,
                "token_type": "bearer"
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error activating user: {e}")
            raise HTTPException(status_code=500, detail="Failed to activate account")

    return router
