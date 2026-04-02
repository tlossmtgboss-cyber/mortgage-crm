"""
Account Management - Invitation Routes
Subscriber invitation endpoints: invite, list, resend, revoke, reinstate
Extracted from account_management_routes.py
"""

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging
import uuid

from database import get_db as _get_db_func
from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    success_response
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from email_service import send_subscription_invite_email

from routes.account_models import (
    InviteSubscriberRequest,
    table_exists,
    require_master_admin,
    get_user_from_request,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Account Management - Invitations"])

# Module-level dependency references
_get_current_user = None


def set_dependencies(user_model, current_user_func):
    """Set dependencies from parent module"""
    global _get_current_user
    _get_current_user = current_user_func
    # Update the account_models module with the auth dependency
    from routes.account_models import set_auth_dependency
    set_auth_dependency(current_user_func)


def get_db():
    return Depends(_get_db_func)


# =============================================================================
# Invitation Endpoints
# =============================================================================

@router.post("/invite")
async def invite_subscriber(
    request: Request,
    invite: InviteSubscriberRequest,
    db: Session = Depends(_get_db_func)
):
    """Send subscription invitation to a new organization"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Check if email already exists in users
        existing = db.execute(text("""
            SELECT id FROM users WHERE email = :email
        """), {'email': invite.email}).fetchone()

        if existing:
            raise ValidationException(f"An account with email {invite.email} already exists")

        # Create invitation token
        invitation_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        # Store invitation in subscriber_invitations table for validation
        try:
            db.execute(text("""
                INSERT INTO subscriber_invitations (
                    token, email, company_name, contact_name, plan, seats,
                    promo_code, personal_message, status, invited_by, invited_by_name,
                    expires_at, ip_address, created_at, updated_at
                ) VALUES (
                    :token, :email, :company_name, :contact_name, :plan, :seats,
                    :promo_code, :message, 'pending', :invited_by, :invited_by_name,
                    :expires_at, :ip, NOW(), NOW()
                )
            """), {
                'token': invitation_token,
                'email': invite.email,
                'company_name': invite.company_name,
                'contact_name': invite.contact_name,
                'plan': invite.plan,
                'seats': invite.seats,
                'promo_code': invite.promo_code,
                'message': invite.message,
                'invited_by': current_user.id,
                'invited_by_name': getattr(current_user, 'full_name', current_user.email),
                'expires_at': expires_at,
                'ip': request.client.host if request.client else 'unknown'
            })
            db.commit()
            logger.info("Invitation stored successfully")
        except Exception as store_err:
            logger.error(f"Could not store invitation: {store_err}")
            db.rollback()
            raise DatabaseException("Failed to create invitation")

        # Also log to audit log for historical tracking
        try:
            db.execute(text("""
                INSERT INTO admin_audit_log (
                    action_type, actor_admin_id, actor_name, target_type, target_id,
                    old_values, new_values, reason, ip_address
                ) VALUES (
                    'invitation_sent', :actor_id, :actor_name, 'invitation', :token,
                    NULL,
                    :details,
                    :message,
                    :ip
                )
            """), {
                'actor_id': current_user.id,
                'actor_name': getattr(current_user, 'full_name', current_user.email),
                'token': invitation_token,
                'details': str({
                    'email': invite.email,
                    'company_name': invite.company_name,
                    'contact_name': invite.contact_name,
                    'plan': invite.plan,
                    'seats': invite.seats,
                    'promo_code': invite.promo_code,
                    'expires_at': expires_at.isoformat()
                }),
                'message': invite.message or 'Subscription invitation',
                'ip': request.client.host if request.client else 'unknown'
            })
            db.commit()
        except Exception as log_err:
            logger.warning(f"Could not log invitation to audit: {log_err}")
            # Continue anyway - audit logging failure shouldn't block invitation

        # Log the action
        logger.info(f"Subscription invitation sent by user {current_user.id}")

        # Send the invitation email
        email_sent = False
        try:
            email_sent = await send_subscription_invite_email(
                to_email=invite.email,
                company_name=invite.company_name,
                contact_name=invite.contact_name,
                plan=invite.plan,
                seats=invite.seats,
                invitation_token=invitation_token,
                personal_message=invite.message,
                expires_days=7,
                promo_code=invite.promo_code
            )
            if email_sent:
                logger.info("Invitation email sent successfully")
            else:
                logger.warning("Failed to send invitation email")
        except Exception as email_err:
            logger.error(f"Error sending invitation email: {email_err}")
            # Continue anyway - email failure shouldn't block the invitation creation

        # Build invitation link with promo code if present
        invitation_link = f"https://perenniaai.com/signup?invite={invitation_token}"
        if invite.promo_code:
            invitation_link += f"&promo={invite.promo_code}"

        return success_response(
            data={
                'email': invite.email,
                'company_name': invite.company_name,
                'plan': invite.plan,
                'seats': invite.seats,
                'promo_code': invite.promo_code,
                'invitation_token': invitation_token,
                'expires_at': expires_at.isoformat(),
                'invitation_link': invitation_link,
                'email_sent': email_sent
            },
            message=f"Invitation {'sent' if email_sent else 'created (email pending)'} to {invite.email}"
        )

    except PermissionException:
        raise
    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Error sending invitation: {e}")
        db.rollback()
        raise DatabaseException("Failed to send invitation")


@router.get("/pending-invites")
async def list_pending_invites(
    request: Request,
    search: Optional[str] = Query(None, description="Search by email or company"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(_get_db_func)
):
    """List pending subscription invitations"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Check if table exists
        if not table_exists(db, 'subscriber_invitations'):
            return success_response(
                data={
                    'invitations': [],
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': 0,
                        'total_pages': 0
                    }
                },
                message="No invitations table found"
            )

        # Build search filter
        search_filter = ""
        params = {'offset': (page - 1) * limit, 'limit': limit}
        if search:
            search_filter = "AND (email ILIKE :search OR company_name ILIKE :search)"
            params['search'] = f"%{search}%"

        # Get total count
        count_sql = """
            SELECT COUNT(*) as total
            FROM subscriber_invitations
            WHERE status = 'pending' """ + search_filter + """
        """
        count_result = db.execute(text(count_sql), params).fetchone()
        total = count_result.total if count_result else 0

        # Get invitations
        invitations_sql = """
            SELECT id, token, email, company_name, contact_name, plan, seats,
                   promo_code, status, invited_by_name, expires_at, created_at
            FROM subscriber_invitations
            WHERE status = 'pending' """ + search_filter + """
            ORDER BY created_at DESC
            OFFSET :offset LIMIT :limit
        """
        invitations = db.execute(text(invitations_sql), params).fetchall()

        invite_list = []
        now = datetime.now(timezone.utc)
        for inv in invitations:
            expires_at = inv.expires_at
            is_expired = False
            if expires_at:
                if hasattr(expires_at, 'replace'):
                    expires_at_tz = expires_at.replace(tzinfo=timezone.utc)
                    is_expired = now > expires_at_tz

            invite_list.append({
                'id': str(inv.id),
                'email': inv.email,
                'name': inv.contact_name or '',
                'organizationName': inv.company_name,
                'planName': inv.plan.title() if inv.plan else 'Professional',
                'seatsPurchased': inv.seats or 5,
                'invitedAt': inv.created_at.isoformat() if inv.created_at else None,
                'invitedBy': inv.invited_by_name or 'System',
                'expiresAt': inv.expires_at.isoformat() if inv.expires_at else None,
                'status': 'expired' if is_expired else 'pending',
                'promoCode': inv.promo_code
            })

        return success_response(
            data={
                'invitations': invite_list,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'total_pages': (total + limit - 1) // limit
                }
            },
            message=f"Found {len(invite_list)} pending invitations"
        )

    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error listing pending invites: {e}")
        raise DatabaseException("Failed to list pending invites")


@router.post("/invites/{invite_id}/resend")
async def resend_invite(
    invite_id: str,
    request: Request,
    db: Session = Depends(_get_db_func)
):
    """Resend an invitation email"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Get invitation
        invitation = db.execute(text("""
            SELECT id, token, email, company_name, contact_name, plan, seats,
                   promo_code, personal_message, expires_at, status
            FROM subscriber_invitations
            WHERE id = :id
        """), {'id': invite_id}).fetchone()

        if not invitation:
            raise NotFoundException(f"Invitation {invite_id} not found")

        if invitation.status != 'pending':
            raise ValidationException(f"Cannot resend invitation with status '{invitation.status}'")

        # Generate new token and extend expiration
        new_token = str(uuid.uuid4())
        new_expires = datetime.now(timezone.utc) + timedelta(days=7)

        db.execute(text("""
            UPDATE subscriber_invitations
            SET token = :new_token,
                expires_at = :new_expires,
                updated_at = NOW()
            WHERE id = :id
        """), {
            'id': invite_id,
            'new_token': new_token,
            'new_expires': new_expires
        })
        db.commit()

        # Send the invitation email
        email_sent = False
        try:
            email_sent = await send_subscription_invite_email(
                to_email=invitation.email,
                company_name=invitation.company_name,
                contact_name=invitation.contact_name,
                plan=invitation.plan,
                seats=invitation.seats,
                invitation_token=new_token,
                personal_message=invitation.personal_message,
                expires_days=7,
                promo_code=invitation.promo_code
            )
        except Exception as email_err:
            logger.error(f"Error sending resend email: {email_err}")

        return success_response(
            data={
                'id': invite_id,
                'email': invitation.email,
                'new_token': new_token,
                'expires_at': new_expires.isoformat(),
                'email_sent': email_sent
            },
            message=f"Invitation resent to {invitation.email}"
        )

    except (PermissionException, NotFoundException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error resending invitation: {e}")
        db.rollback()
        raise DatabaseException("Failed to resend invitation")


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: str,
    request: Request,
    db: Session = Depends(_get_db_func)
):
    """Revoke a pending invitation"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Get invitation
        invitation = db.execute(text("""
            SELECT id, email, status FROM subscriber_invitations WHERE id = :id
        """), {'id': invite_id}).fetchone()

        if not invitation:
            raise NotFoundException(f"Invitation {invite_id} not found")

        if invitation.status != 'pending':
            raise ValidationException(f"Cannot revoke invitation with status '{invitation.status}'")

        # Revoke the invitation
        db.execute(text("""
            UPDATE subscriber_invitations
            SET status = 'revoked',
                revoked_at = NOW(),
                revoked_by = :revoked_by,
                updated_at = NOW()
            WHERE id = :id
        """), {
            'id': invite_id,
            'revoked_by': current_user.id
        })
        db.commit()

        return success_response(
            data={'id': invite_id, 'email': invitation.email},
            message=f"Invitation to {invitation.email} has been revoked"
        )

    except (PermissionException, NotFoundException, ValidationException):
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error revoking invitation: {e}")
        db.rollback()
        raise DatabaseException("Failed to revoke invitation")


@router.post("/invites/{invite_id}/reinstate")
async def reinstate_invite(
    invite_id: str,
    request: Request,
    db: Session = Depends(_get_db_func)
):
    """Reinstate a revoked invitation back to pending status"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Get invitation
        invitation = db.execute(text("""
            SELECT id, email, token, status FROM subscriber_invitations WHERE id = :id
        """), {'id': invite_id}).fetchone()

        if not invitation:
            raise NotFoundException(f"Invitation {invite_id} not found")

        if invitation.status not in ('revoked', 'expired'):
            raise ValidationException(f"Can only reinstate revoked or expired invitations, current status is '{invitation.status}'")

        # Generate new token and extend expiration
        new_token = str(uuid.uuid4())
        new_expires = datetime.now(timezone.utc) + timedelta(days=7)

        # Reinstate the invitation
        db.execute(text("""
            UPDATE subscriber_invitations
            SET status = 'pending',
                token = :new_token,
                expires_at = :expires_at,
                revoked_at = NULL,
                revoked_by = NULL,
                updated_at = NOW()
            WHERE id = :id
        """), {
            'id': invite_id,
            'new_token': new_token,
            'expires_at': new_expires
        })
        db.commit()

        # Build new invitation link
        invitation_link = f"https://perenniaai.com/signup?invite={new_token}"

        return success_response(
            data={
                'id': invite_id,
                'email': invitation.email,
                'new_token': new_token,
                'invitation_link': invitation_link,
                'expires_at': new_expires.isoformat()
            },
            message=f"Invitation to {invitation.email} has been reinstated"
        )

    except (PermissionException, NotFoundException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error reinstating invitation: {e}")
        db.rollback()
        raise DatabaseException("Failed to reinstate invitation")


@router.post("/invites/reinstate-by-token/{token}")
async def reinstate_invite_by_token(
    token: str,
    db: Session = Depends(_get_db_func)
):
    """Reinstate a revoked invitation by token (public endpoint for quick fixes)"""
    try:
        # Get invitation
        invitation = db.execute(text("""
            SELECT id, email, status FROM subscriber_invitations WHERE token = :token
        """), {'token': token}).fetchone()

        if not invitation:
            raise NotFoundException(f"Invitation with token not found")

        if invitation.status not in ('revoked', 'expired'):
            raise ValidationException(f"Can only reinstate revoked or expired invitations, current status is '{invitation.status}'")

        # Extend expiration
        new_expires = datetime.now(timezone.utc) + timedelta(days=7)

        # Reinstate the invitation (keep same token)
        db.execute(text("""
            UPDATE subscriber_invitations
            SET status = 'pending',
                expires_at = :expires_at,
                revoked_at = NULL,
                revoked_by = NULL,
                updated_at = NOW()
            WHERE token = :token
        """), {
            'token': token,
            'expires_at': new_expires
        })
        db.commit()

        return success_response(
            data={
                'id': str(invitation.id),
                'email': invitation.email,
                'expires_at': new_expires.isoformat()
            },
            message=f"Invitation to {invitation.email} has been reinstated"
        )

    except (NotFoundException, ValidationException):
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error reinstating invitation: {e}")
        db.rollback()
        raise DatabaseException("Failed to reinstate invitation")


@router.post("/invites/resend-by-token/{token}")
async def resend_invite_by_token(
    token: str,
    db: Session = Depends(_get_db_func)
):
    """Resend invitation email by token (public endpoint for quick fixes)"""
    try:
        # Get invitation
        invitation = db.execute(text("""
            SELECT id, token, email, company_name, contact_name, plan, seats,
                   promo_code, personal_message, expires_at, status
            FROM subscriber_invitations
            WHERE token = :token
        """), {'token': token}).fetchone()

        if not invitation:
            raise NotFoundException(f"Invitation with token not found")

        if invitation.status != 'pending':
            raise ValidationException(f"Cannot resend invitation with status '{invitation.status}'")

        # Extend expiration
        new_expires = datetime.now(timezone.utc) + timedelta(days=7)

        db.execute(text("""
            UPDATE subscriber_invitations
            SET expires_at = :new_expires,
                updated_at = NOW()
            WHERE token = :token
        """), {
            'token': token,
            'new_expires': new_expires
        })
        db.commit()

        # Build invitation link
        invitation_link = f"https://perenniaai.com/signup?invite={token}"
        if invitation.promo_code:
            invitation_link += f"&promo={invitation.promo_code}"

        # Send the invitation email
        email_sent = False
        try:
            email_sent = await send_subscription_invite_email(
                to_email=invitation.email,
                company_name=invitation.company_name,
                contact_name=invitation.contact_name,
                plan=invitation.plan,
                seats=invitation.seats,
                invitation_token=token,
                personal_message=invitation.personal_message,
                expires_days=7,
                promo_code=invitation.promo_code
            )
        except Exception as email_err:
            logger.error(f"Error sending invitation email: {email_err}")

        return success_response(
            data={
                'id': str(invitation.id),
                'email': invitation.email,
                'company_name': invitation.company_name,
                'invitation_link': invitation_link,
                'expires_at': new_expires.isoformat(),
                'email_sent': email_sent
            },
            message=f"Invitation email {'sent' if email_sent else 'failed to send'} to {invitation.email}"
        )

    except (NotFoundException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error resending invitation: {e}")
        db.rollback()
        raise DatabaseException("Failed to resend invitation")
