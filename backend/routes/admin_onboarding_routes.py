"""
Admin Onboarding Routes
Handles the onboarding flow for new administrators signing up via subscription invitation.
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging
import uuid
import json
import os

from database import get_db
from utils.error_handling import (
    ValidationException,
    NotFoundException,
    success_response
)
from email_service import email_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin-onboarding", tags=["Admin Onboarding"])

from sqlalchemy.exc import SQLAlchemyError

# Stripe integration
try:
    import stripe
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')
    STRIPE_AVAILABLE = bool(stripe.api_key)
except ImportError:
    STRIPE_AVAILABLE = False
    logger.warning("Stripe not installed. Install with: pip install stripe")


# =============================================================================
# Pydantic Models
# =============================================================================

class StartOnboardingRequest(BaseModel):
    """Request to start onboarding after validating invite"""
    invite_token: str = Field(..., description="Invitation token from email")
    email: EmailStr = Field(..., description="Admin email address")
    password: str = Field(..., min_length=8, description="Account password")
    accept_terms: bool = Field(..., description="Accept terms of service")

    @validator('password')
    def validate_password(cls, v):
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one number')
        return v

    @validator('accept_terms')
    def validate_terms(cls, v):
        if not v:
            raise ValueError('You must accept the terms of service')
        return v


class CompanyProfileRequest(BaseModel):
    """Company profile setup"""
    company_name: str = Field(..., min_length=2, max_length=255)
    company_phone: Optional[str] = Field(None, max_length=20)
    company_address: Optional[str] = Field(None, max_length=500)
    industry: str = Field('mortgage_broker', description="Industry type")
    logo_url: Optional[str] = Field(None, description="Company logo URL")


class UserProfileRequest(BaseModel):
    """Admin user profile setup"""
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    job_title: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    nmls_number: Optional[str] = Field(None, max_length=20)
    timezone: str = Field('America/New_York')
    headshot_url: Optional[str] = Field(None)


class TeamInvite(BaseModel):
    """Single team member invite"""
    email: EmailStr
    role: str = Field('loan_officer', description="Role for the invitee")
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class InviteTeamRequest(BaseModel):
    """Request to queue team invites"""
    invites: List[TeamInvite] = Field(default=[], max_items=50)
    skip: bool = Field(False, description="Skip inviting team members")


class PaymentRequest(BaseModel):
    """Payment/subscription request"""
    payment_method_id: str = Field(..., description="Stripe payment method ID or 'free_access_promo'")
    billing_name: Optional[str] = Field(None, description="Billing name (optional for promo codes)")
    billing_address: Optional[dict] = Field(None, description="Billing address object")
    billing_address_line1: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: str = Field('US')
    promo_code: Optional[str] = None
    selected_modules: Optional[list] = Field(None, description="Selected premium modules")


# =============================================================================
# Plan Configuration
# =============================================================================

PLAN_PRICES = {
    'starter': {
        'name': 'Starter',
        'monthly_price': 99,
        'stripe_price_id': os.getenv('STRIPE_STARTER_PRICE_ID', 'price_starter'),
    },
    'professional': {
        'name': 'Professional',
        'monthly_price': 299,
        'stripe_price_id': os.getenv('STRIPE_PROFESSIONAL_PRICE_ID', 'price_professional'),
    },
    'enterprise': {
        'name': 'Enterprise',
        'monthly_price': 499,
        'stripe_price_id': os.getenv('STRIPE_ENTERPRISE_PRICE_ID', 'price_enterprise'),
    },
    'custom': {
        'name': 'Custom',
        'monthly_price': 0,  # Custom pricing
        'stripe_price_id': None,
    }
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_invite_data(db: Session, token: str) -> Optional[dict]:
    """Look up invitation data from subscriber_invitations table"""
    # First try the new subscriber_invitations table
    result = db.execute(text("""
        SELECT id, token, email, company_name, contact_name, plan, seats,
               promo_code, personal_message, status, invited_by, invited_by_name,
               expires_at, created_at
        FROM subscriber_invitations
        WHERE token = :token
        LIMIT 1
    """), {'token': token}).fetchone()

    if result:
        # Check if already used/revoked
        if result.status == 'accepted':
            return {'already_used': True, 'email': result.email}
        if result.status == 'revoked':
            return {'revoked': True, 'email': result.email}

        # Check expiration
        if result.expires_at and datetime.now(timezone.utc) > result.expires_at.replace(tzinfo=timezone.utc):
            return {'expired': True, 'email': result.email}

        return {
            'invitation_id': str(result.id),
            'email': result.email,
            'company_name': result.company_name,
            'contact_name': result.contact_name,
            'plan': result.plan,
            'seats': result.seats,
            'promo_code': result.promo_code,
            'personal_message': result.personal_message,
            'expires_at': result.expires_at.isoformat() if result.expires_at else None,
            'created_at': result.created_at
        }

    # Fall back to audit log for older invitations
    audit_result = db.execute(text("""
        SELECT id, new_values, created_at, target_id
        FROM admin_audit_log
        WHERE action_type = 'invitation_sent'
          AND target_id = :token
        ORDER BY created_at DESC
        LIMIT 1
    """), {'token': token}).fetchone()

    if not audit_result:
        return None

    # Parse the stored data
    try:
        if isinstance(audit_result.new_values, str):
            try:
                data = json.loads(audit_result.new_values)
            except (json.JSONDecodeError, ValueError):
                logger.warning("Invalid JSON in audit_result.new_values")
                return None
        else:
            data = audit_result.new_values
    except Exception:
        return None

    # Check expiration
    expires_at_str = data.get('expires_at')
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                return {'expired': True, **data}
        except Exception:
            pass

    return {
        'audit_id': audit_result.id,
        'created_at': audit_result.created_at,
        **data
    }


def check_invite_used(db: Session, email: str) -> bool:
    """Check if email already has an account"""
    result = db.execute(text("""
        SELECT id FROM users WHERE email = :email LIMIT 1
    """), {'email': email}).fetchone()
    return result is not None


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    try:
        import bcrypt
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    except ImportError:
        # Fallback to simple hash if bcrypt not available
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/validate-invite/{token}")
async def validate_invite(token: str, db: Session = Depends(get_db)):
    """Validate a subscription invitation token"""
    try:
        invite_data = get_invite_data(db, token)

        if not invite_data:
            return success_response(
                data={'valid': False, 'reason': 'invalid'},
                message="Invalid invitation token"
            )

        if invite_data.get('expired'):
            return success_response(
                data={'valid': False, 'reason': 'expired'},
                message="This invitation has expired"
            )

        if invite_data.get('already_used'):
            return success_response(
                data={'valid': False, 'reason': 'already_used'},
                message="This invitation has already been accepted"
            )

        if invite_data.get('revoked'):
            return success_response(
                data={'valid': False, 'reason': 'revoked'},
                message="This invitation has been revoked"
            )

        # Check if email already has an account (for audit log fallback)
        if check_invite_used(db, invite_data.get('email', '')):
            return success_response(
                data={'valid': False, 'reason': 'already_used'},
                message="This invitation has already been accepted"
            )

        # Get plan details
        plan_key = invite_data.get('plan', 'professional')
        plan_info = PLAN_PRICES.get(plan_key, PLAN_PRICES['professional'])

        return success_response(
            data={
                'valid': True,
                'email': invite_data.get('email'),
                'company_name': invite_data.get('company_name'),
                'contact_name': invite_data.get('contact_name'),
                'plan': plan_key,
                'plan_name': plan_info['name'],
                'seats': invite_data.get('seats', 5),
                'monthly_price': plan_info['monthly_price'],
                'promo_code': invite_data.get('promo_code')
            },
            message="Invitation is valid"
        )

    except Exception as e:
        logger.error(f"Error validating invite: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/start")
async def start_onboarding(
    request: StartOnboardingRequest,
    db: Session = Depends(get_db)
):
    """Start the onboarding process - create account and tenant"""
    try:
        # Validate invite token
        invite_data = get_invite_data(db, request.invite_token)
        if not invite_data or invite_data.get('expired'):
            raise ValidationException("Invalid or expired invitation")

        # Check if email matches invite
        if invite_data.get('email', '').lower() != request.email.lower():
            raise ValidationException("Email does not match invitation")

        # Check if account already exists
        if check_invite_used(db, request.email):
            raise ValidationException("An account with this email already exists")

        # Create tenant account
        tenant_id = str(uuid.uuid4())
        plan_key = invite_data.get('plan', 'professional')

        db.execute(text("""
            INSERT INTO tenant_accounts (
                id, name, status, plan_id, plan_name, seats_purchased,
                created_at, updated_at
            ) VALUES (
                :id, :name, 'active', :plan_id, :plan_name, :seats,
                NOW(), NOW()
            )
        """), {
            'id': tenant_id,
            'name': invite_data.get('company_name', 'New Company'),
            'plan_id': plan_key,
            'plan_name': PLAN_PRICES.get(plan_key, {}).get('name', 'Professional'),
            'seats': invite_data.get('seats', 5)
        })

        # Create site admin user (NOT platform admin)
        # site_admin = organization-level admin, can manage their own users
        # admin = platform admin with full access (reserved for developers)
        hashed_password = hash_password(request.password)
        contact_name = invite_data.get('contact_name', '')
        name_parts = contact_name.split(' ', 1) if contact_name else ['', '']

        user_result = db.execute(text("""
            INSERT INTO users (
                email, hashed_password, full_name, first_name, last_name,
                role, permission_role, is_active, tenant_account_id,
                created_at, updated_at
            ) VALUES (
                :email, :hashed_password, :full_name, :first_name, :last_name,
                'site_admin', 'site_admin', true, :tenant_id,
                NOW(), NOW()
            )
            RETURNING id
        """), {
            'email': request.email,
            'hashed_password': hashed_password,
            'full_name': contact_name or request.email.split('@')[0],
            'first_name': name_parts[0] if len(name_parts) > 0 else '',
            'last_name': name_parts[1] if len(name_parts) > 1 else '',
            'tenant_id': tenant_id
        })

        user_id = user_result.fetchone()[0]

        # Assign Site Administrator role (multi-role support)
        try:
            # Look up Site Administrator role from onboarding_roles
            site_admin_role = db.execute(text("""
                SELECT id FROM onboarding_roles WHERE name = 'Site Administrator' LIMIT 1
            """)).fetchone()

            if site_admin_role:
                role_id = site_admin_role[0]

                # Assign Site Administrator role as primary
                db.execute(text("""
                    INSERT INTO user_assigned_roles (user_id, role_id, is_primary, assigned_at, assigned_by)
                    VALUES (:user_id, :role_id, TRUE, NOW(), :user_id)
                """), {'user_id': user_id, 'role_id': role_id})

                # Set Site Administrator as active role
                db.execute(text("""
                    INSERT INTO user_active_role (user_id, active_role_id, switched_at)
                    VALUES (:user_id, :role_id, NOW())
                """), {'user_id': user_id, 'role_id': role_id})

                logger.info(f"Assigned Site Administrator role (id={role_id}) to user {user_id}")
        except SQLAlchemyError as e:
            logger.warning(f"Could not assign Site Administrator role: {e}")
            # Continue signup even if role assignment fails

        # Update tenant with owner
        db.execute(text("""
            UPDATE tenant_accounts SET owner_user_id = :user_id WHERE id = :tenant_id
        """), {'user_id': user_id, 'tenant_id': tenant_id})

        # Mark invitation as accepted
        try:
            db.execute(text("""
                UPDATE subscriber_invitations
                SET status = 'accepted',
                    accepted_at = NOW(),
                    accepted_by_user_id = :user_id,
                    updated_at = NOW()
                WHERE token = :token
            """), {'token': request.invite_token, 'user_id': user_id})
        except Exception as update_err:
            logger.warning(f"Could not update invitation status: {update_err}")
            # Continue anyway - this is not critical

        # Create onboarding session
        session_id = str(uuid.uuid4())

        db.commit()

        # Generate auth token
        try:
            import jwt
            jwt_secret = (os.getenv('JWT_SECRET') or os.getenv('SECRET_KEY') or '').strip()
            if not jwt_secret:
                logger.error("JWT_SECRET/SECRET_KEY not configured for onboarding token")
                token = session_id  # Fallback to session_id if no secret
            else:
                token = jwt.encode(
                    {'sub': request.email, 'exp': datetime.utcnow() + timedelta(hours=24)},
                    jwt_secret,
                    algorithm='HS256'
                )
        except Exception:
            token = session_id  # Fallback

        return success_response(
            data={
                'user_id': user_id,
                'tenant_id': tenant_id,
                'session_id': session_id,
                'access_token': token,
                'plan': plan_key,
                'seats': invite_data.get('seats', 5),
                'company_name': invite_data.get('company_name')
            },
            message="Account created successfully"
        )

    except ValidationException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error starting onboarding: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/company-profile")
async def save_company_profile(
    request: Request,
    profile: CompanyProfileRequest,
    db: Session = Depends(get_db)
):
    """Save company profile during onboarding"""
    try:
        # Get user from auth header
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Unauthorized")

        token = auth.split(' ')[1]

        # Decode token to get user
        try:
            import jwt
            jwt_secret = (os.getenv('JWT_SECRET') or os.getenv('SECRET_KEY') or '').strip()
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'], options={"verify_aud": False})
            email = payload.get('sub')
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user and tenant
        user = db.execute(text("""
            SELECT id, tenant_account_id FROM users WHERE email = :email
        """), {'email': email}).fetchone()

        if not user or not user.tenant_account_id:
            raise HTTPException(status_code=404, detail="User not found")

        # Update tenant account
        company_settings = json.dumps({
            'phone': profile.company_phone,
            'address': profile.company_address,
            'industry': profile.industry,
            'logo_url': profile.logo_url
        })

        db.execute(text("""
            UPDATE tenant_accounts SET
                name = :name,
                settings = COALESCE(settings, '{}'::jsonb) || jsonb_build_object('company', CAST(:company_settings AS jsonb)),
                updated_at = NOW()
            WHERE id = CAST(:tenant_id AS uuid)
        """), {
            'name': profile.company_name,
            'company_settings': company_settings,
            'tenant_id': str(user.tenant_account_id)
        })

        db.commit()

        return success_response(
            data={'saved': True},
            message="Company profile saved"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving company profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/user-profile")
async def save_user_profile(
    request: Request,
    profile: UserProfileRequest,
    db: Session = Depends(get_db)
):
    """Save admin user profile during onboarding"""
    try:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Unauthorized")

        token = auth.split(' ')[1]

        try:
            import jwt
            jwt_secret = (os.getenv('JWT_SECRET') or os.getenv('SECRET_KEY') or '').strip()
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'], options={"verify_aud": False})
            email = payload.get('sub')
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Update user profile
        db.execute(text("""
            UPDATE users SET
                first_name = :first_name,
                last_name = :last_name,
                full_name = :full_name,
                phone = :phone,
                title = :job_title,
                nmls_id = :nmls,
                timezone = :timezone,
                headshot_url = :headshot
            WHERE email = :email
        """), {
            'first_name': profile.first_name,
            'last_name': profile.last_name,
            'full_name': f"{profile.first_name} {profile.last_name}".strip(),
            'phone': profile.phone,
            'job_title': profile.job_title,
            'nmls': profile.nmls_number,
            'timezone': profile.timezone,
            'headshot': profile.headshot_url,
            'email': email
        })

        db.commit()

        return success_response(
            data={'saved': True},
            message="Profile saved"
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error saving user profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/invite-team")
async def queue_team_invites(
    request: Request,
    invites: InviteTeamRequest,
    db: Session = Depends(get_db)
):
    """Queue team member invites (sent after payment)"""
    try:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Unauthorized")

        token = auth.split(' ')[1]

        try:
            import jwt
            jwt_secret = (os.getenv('JWT_SECRET') or os.getenv('SECRET_KEY') or '').strip()
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'], options={"verify_aud": False})
            email = payload.get('sub')
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

        if invites.skip:
            return success_response(
                data={'queued': 0, 'skipped': True},
                message="Team invites skipped"
            )

        # Get user and tenant
        user = db.execute(text("""
            SELECT u.id, u.tenant_account_id, t.seats_purchased
            FROM users u
            JOIN tenant_accounts t ON t.id = u.tenant_account_id
            WHERE u.email = :email
        """), {'email': email}).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check seat limit
        max_invites = (user.seats_purchased or 5) - 1  # Minus admin
        if len(invites.invites) > max_invites:
            raise ValidationException(f"You can only invite up to {max_invites} team members")

        # Store pending invites in tenant settings
        pending_invites = [
            {
                'email': inv.email,
                'role': inv.role,
                'first_name': inv.first_name,
                'last_name': inv.last_name
            }
            for inv in invites.invites
        ]

        db.execute(text("""
            UPDATE tenant_accounts SET
                settings = jsonb_set(
                    COALESCE(settings, '{}'::jsonb),
                    '{pending_invites}',
                    :invites::jsonb
                ),
                updated_at = NOW()
            WHERE id = :tenant_id
        """), {
            'invites': json.dumps(pending_invites),
            'tenant_id': str(user.tenant_account_id)
        })

        db.commit()

        return success_response(
            data={'queued': len(pending_invites)},
            message=f"{len(pending_invites)} team invites queued"
        )

    except ValidationException:
        raise
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error queueing team invites: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/create-subscription")
async def create_subscription(
    request: Request,
    payment: PaymentRequest,
    db: Session = Depends(get_db)
):
    """Process payment and create Stripe subscription"""
    try:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Unauthorized")

        token = auth.split(' ')[1]

        try:
            import jwt
            jwt_secret = (os.getenv('JWT_SECRET') or os.getenv('SECRET_KEY') or '').strip()
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'], options={"verify_aud": False})
            email = payload.get('sub')
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user and tenant
        user = db.execute(text("""
            SELECT u.id, u.tenant_account_id, u.full_name, t.plan_id, t.seats_purchased
            FROM users u
            JOIN tenant_accounts t ON t.id = u.tenant_account_id
            WHERE u.email = :email
        """), {'email': email}).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        plan_key = user.plan_id or 'professional'
        plan_info = PLAN_PRICES.get(plan_key, PLAN_PRICES['professional'])

        # Free access promo code - bypass payment entirely
        FREE_ACCESS_PROMO_CODE = os.getenv('FREE_ACCESS_PROMO_CODE', 'CHARLIE2016')
        if payment.payment_method_id == 'free_access_promo' and payment.promo_code and payment.promo_code.upper() == FREE_ACCESS_PROMO_CODE:
            logger.info(f"Free access promo code applied for user {email}")

            # Upgrade to business plan
            db.execute(text("""
                UPDATE tenant_accounts SET
                    status = 'active',
                    plan_id = 'business',
                    stripe_customer_id = :customer_id,
                    stripe_subscription_id = :sub_id,
                    updated_at = NOW()
                WHERE id = :tenant_id
            """), {
                'customer_id': f'promo_cus_{uuid.uuid4().hex[:8]}',
                'sub_id': f'promo_free_access_{uuid.uuid4().hex[:8]}',
                'tenant_id': str(user.tenant_account_id)
            })

            # Log the promo code usage
            db.execute(text("""
                INSERT INTO admin_audit_log (action_type, actor_admin_id, actor_name, target_type, target_id, new_values, reason)
                VALUES ('promo_code_applied', :user_id, :user_name, 'tenant', :tenant_id, :details, 'Free Business Plan Access')
            """), {
                'user_id': user.id,
                'user_name': user.full_name or email,
                'tenant_id': str(user.tenant_account_id),
                'details': json.dumps({'promo_code': FREE_ACCESS_PROMO_CODE, 'plan': 'business', 'price': 0})
            })

            db.commit()

            return success_response(
                data={
                    'success': True,
                    'free_access': True,
                    'promo_code': FREE_ACCESS_PROMO_CODE,
                    'plan': 'business',
                    'subscription_id': f'promo_free_access_{uuid.uuid4().hex[:8]}'
                },
                message="Free Business Plan activated with promo code"
            )

        if not STRIPE_AVAILABLE:
            # Demo mode - skip actual Stripe
            logger.warning("Stripe not configured - running in demo mode")

            db.execute(text("""
                UPDATE tenant_accounts SET
                    status = 'active',
                    stripe_customer_id = :customer_id,
                    stripe_subscription_id = :sub_id,
                    updated_at = NOW()
                WHERE id = :tenant_id
            """), {
                'customer_id': f'demo_cus_{uuid.uuid4().hex[:8]}',
                'sub_id': f'demo_sub_{uuid.uuid4().hex[:8]}',
                'tenant_id': str(user.tenant_account_id)
            })

            db.commit()

            return success_response(
                data={
                    'success': True,
                    'demo_mode': True,
                    'subscription_id': f'demo_sub_{uuid.uuid4().hex[:8]}'
                },
                message="Subscription created (demo mode)"
            )

        # Create Stripe customer
        customer = stripe.Customer.create(
            email=email,
            name=payment.billing_name,
            payment_method=payment.payment_method_id,
            invoice_settings={'default_payment_method': payment.payment_method_id},
            address={
                'line1': payment.billing_address_line1,
                'city': payment.billing_city,
                'state': payment.billing_state,
                'postal_code': payment.billing_postal_code,
                'country': payment.billing_country
            },
            metadata={
                'tenant_id': str(user.tenant_account_id),
                'user_id': str(user.id)
            }
        )

        # Apply promo code if provided
        coupon_id = None
        if payment.promo_code:
            try:
                promo = stripe.PromotionCode.list(code=payment.promo_code, active=True, limit=1)
                if promo.data:
                    coupon_id = promo.data[0].coupon.id
            except Exception:
                pass  # Ignore invalid promo codes

        # Create subscription
        subscription_params = {
            'customer': customer.id,
            'items': [{'price': plan_info['stripe_price_id'], 'quantity': user.seats_purchased or 1}],
            'payment_behavior': 'error_if_incomplete',
            'expand': ['latest_invoice.payment_intent']
        }

        if coupon_id:
            subscription_params['coupon'] = coupon_id

        subscription = stripe.Subscription.create(**subscription_params)

        # Update tenant with Stripe IDs
        db.execute(text("""
            UPDATE tenant_accounts SET
                status = 'active',
                stripe_customer_id = :customer_id,
                stripe_subscription_id = :sub_id,
                updated_at = NOW()
            WHERE id = :tenant_id
        """), {
            'customer_id': customer.id,
            'sub_id': subscription.id,
            'tenant_id': str(user.tenant_account_id)
        })

        # Create subscription record
        db.execute(text("""
            INSERT INTO account_subscriptions (
                id, account_id, provider, provider_subscription_id,
                status, plan_id, plan_name, price_amount, quantity,
                current_period_start, current_period_end,
                created_at, updated_at
            ) VALUES (
                :id, :account_id, 'stripe', :sub_id,
                :status, :plan_id, :plan_name, :price, :quantity,
                to_timestamp(:period_start), to_timestamp(:period_end),
                NOW(), NOW()
            )
        """), {
            'id': str(uuid.uuid4()),
            'account_id': str(user.tenant_account_id),
            'sub_id': subscription.id,
            'status': subscription.status,
            'plan_id': plan_key,
            'plan_name': plan_info['name'],
            'price': plan_info['monthly_price'],
            'quantity': user.seats_purchased or 1,
            'period_start': subscription.current_period_start,
            'period_end': subscription.current_period_end
        })

        db.commit()

        return success_response(
            data={
                'success': True,
                'subscription_id': subscription.id,
                'status': subscription.status
            },
            message="Subscription created successfully"
        )

    except stripe.error.CardError as e:
        raise ValidationException(f"Card error: {e.user_message}")
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating subscription: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/complete")
async def complete_onboarding(
    request: Request,
    db: Session = Depends(get_db)
):
    """Complete onboarding and send queued team invites"""
    try:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            raise HTTPException(status_code=401, detail="Unauthorized")

        token = auth.split(' ')[1]

        try:
            import jwt
            jwt_secret = (os.getenv('JWT_SECRET') or os.getenv('SECRET_KEY') or '').strip()
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'], options={"verify_aud": False})
            email = payload.get('sub')
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user and tenant with pending invites
        user = db.execute(text("""
            SELECT u.id, u.full_name, u.tenant_account_id, t.name as company_name, t.settings
            FROM users u
            JOIN tenant_accounts t ON t.id = u.tenant_account_id
            WHERE u.email = :email
        """), {'email': email}).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Mark onboarding complete
        db.execute(text("""
            UPDATE users SET onboarding_completed = true
            WHERE id = :user_id
        """), {'user_id': user.id})

        # Send pending team invites
        invites_sent = 0
        settings = user.settings or {}
        pending_invites = settings.get('pending_invites', [])

        # Ensure user_invitations table exists (may not have been migrated)
        if pending_invites:
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS user_invitations (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        email VARCHAR(255) NOT NULL,
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        permission_role VARCHAR(50) DEFAULT 'loan_officer',
                        invited_by UUID REFERENCES users(id),
                        organization_id UUID REFERENCES tenant_accounts(id),
                        token VARCHAR(255) UNIQUE NOT NULL,
                        expires_at TIMESTAMP,
                        status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_invites_email ON user_invitations(email)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_invites_token ON user_invitations(token)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_invites_org ON user_invitations(organization_id)"))
            except Exception as e:
                logger.warning(f"user_invitations table check: {e}")

        for invite in pending_invites:
            try:
                # Create invitation token
                invite_token = str(uuid.uuid4())

                # Store in user_invitations table
                db.execute(text("""
                    INSERT INTO user_invitations (
                        id, email, first_name, last_name, permission_role,
                        invited_by, organization_id, token, expires_at,
                        created_at
                    ) VALUES (
                        :id, :email, :first_name, :last_name, :role,
                        :invited_by, :org_id, :token,
                        NOW() + INTERVAL '7 days', NOW()
                    )
                """), {
                    'id': str(uuid.uuid4()),
                    'email': invite['email'],
                    'first_name': invite.get('first_name', ''),
                    'last_name': invite.get('last_name', ''),
                    'role': invite.get('role', 'loan_officer'),
                    'invited_by': user.id,
                    'org_id': str(user.tenant_account_id),
                    'token': invite_token
                })

                # Send invite email
                email_service.send_activation_email(
                    to_email=invite['email'],
                    user_name=invite.get('first_name', invite['email'].split('@')[0]),
                    activation_token=invite_token
                )

                invites_sent += 1

            except Exception as e:
                logger.warning(f"Failed to send invite to {invite.get('email')}: {e}")

        # Clear pending invites from settings
        db.execute(text("""
            UPDATE tenant_accounts SET
                settings = settings - 'pending_invites',
                updated_at = NOW()
            WHERE id = :tenant_id
        """), {'tenant_id': str(user.tenant_account_id)})

        db.commit()

        return success_response(
            data={
                'completed': True,
                'invites_sent': invites_sent,
                'company_name': user.company_name
            },
            message=f"Onboarding complete! {invites_sent} team invites sent."
        )

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error completing onboarding: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/validate-promo")
async def validate_promo_code(
    request: Request,
    db: Session = Depends(get_db)
):
    """Validate a promo code without revealing valid codes to the client"""
    try:
        body = await request.json()
        code = (body.get('promo_code') or '').strip().upper()

        # Server-side promo code validation
        FREE_ACCESS_PROMO_CODE = os.getenv('FREE_ACCESS_PROMO_CODE', 'CHARLIE2016')

        if code == FREE_ACCESS_PROMO_CODE:
            return success_response(
                data={'valid': True, 'type': 'free_access', 'message': 'Free Business Plan access granted!'},
                message="Promo code is valid"
            )

        # Check Stripe promo codes if available
        if STRIPE_AVAILABLE and code:
            try:
                promo = stripe.PromotionCode.list(code=code, active=True, limit=1)
                if promo.data:
                    return success_response(
                        data={'valid': True, 'type': 'discount', 'message': 'Promo code applied!'},
                        message="Promo code is valid"
                    )
            except Exception:
                pass

        return success_response(
            data={'valid': False, 'message': 'Invalid or expired promo code'},
            message="Invalid promo code"
        )
    except Exception as e:
        logger.error(f"Error validating promo code: {e}")
        return success_response(
            data={'valid': False, 'message': 'Could not validate promo code'},
            message="Validation error"
        )


@router.get("/plan-pricing")
async def get_plan_pricing():
    """Get available plan pricing for display"""
    return success_response(
        data={
            'plans': [
                {
                    'id': key,
                    'name': plan['name'],
                    'monthly_price': plan['monthly_price'],
                    'features': get_plan_features(key)
                }
                for key, plan in PLAN_PRICES.items()
                if key != 'custom'
            ]
        },
        message="Plan pricing retrieved"
    )


def get_plan_features(plan_key: str) -> List[str]:
    """Get features for a plan"""
    features = {
        'starter': [
            'Up to 3 users',
            'Basic CRM features',
            'Lead management',
            'Email support'
        ],
        'professional': [
            'Up to 25 users',
            'Full CRM suite',
            'AI-powered automation',
            'Document management',
            'Priority support'
        ],
        'enterprise': [
            'Unlimited users',
            'Custom integrations',
            'Dedicated success manager',
            'SLA guarantee',
            'Advanced analytics'
        ]
    }
    return features.get(plan_key, features['professional'])


@router.get("/available-roles")
async def get_available_roles(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get available roles for team member invites"""
    try:
        # Get roles from onboarding_roles table
        roles = db.execute(text("""
            SELECT id, name, description
            FROM onboarding_roles
            WHERE is_active = true
            ORDER BY
                CASE name
                    WHEN 'Site Administrator' THEN 1
                    WHEN 'Loan Officer' THEN 2
                    WHEN 'Processor' THEN 3
                    WHEN 'Underwriter' THEN 4
                    WHEN 'Closer' THEN 5
                    WHEN 'Manager' THEN 6
                    ELSE 100
                END,
                name ASC
        """)).fetchall()

        # Format roles for dropdown
        role_list = []
        # Roles to exclude from team invites (admin-level roles)
        excluded_roles = [
            'Site Administrator',
            'Site Admin',
            'Company Admin',
            'Admin',  # General admin role
        ]
        for role in roles:
            # Skip admin-level roles - those are for account owners only
            if role.name in excluded_roles:
                continue
            role_list.append({
                'id': role.id,
                'name': role.name,
                'value': role.name.lower().replace(' ', '_'),
                'description': role.description
            })

        return success_response(
            data={'roles': role_list},
            message=f"{len(role_list)} roles available"
        )

    except Exception as e:
        logger.error(f"Error fetching roles: {e}")
        # Return default roles as fallback (no admin roles)
        default_roles = [
            {'id': 0, 'name': 'Loan Officer', 'value': 'loan_officer', 'description': 'Originates and manages loans'},
            {'id': 0, 'name': 'Processor', 'value': 'processor', 'description': 'Processes loan applications'},
            {'id': 0, 'name': 'Underwriter', 'value': 'underwriter', 'description': 'Reviews and approves loans'},
            {'id': 0, 'name': 'Closer', 'value': 'closer', 'description': 'Handles loan closings'},
            {'id': 0, 'name': 'Manager', 'value': 'manager', 'description': 'Team management'},
            {'id': 0, 'name': 'Loan Officer Assistant', 'value': 'loan_officer_assistant', 'description': 'Supports loan officers'},
        ]
        return success_response(
            data={'roles': default_roles, 'fallback': True},
            message="Default roles returned"
        )


# =============================================================================
# TEMPORARY: Admin endpoints (for testing onboarding)
# =============================================================================

@router.get("/list-invitations")
async def list_invitations(
    request: Request,
    db: Session = Depends(get_db)
):
    """List subscriber invitations. Requires ADMIN_API_KEY."""
    admin_key = request.headers.get('X-Admin-Key', '')
    expected_key = (os.getenv('ADMIN_API_KEY') or '').strip()
    if not admin_key or not expected_key or admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Unauthorized")

    invites = db.execute(text("""
        SELECT id, token, email, company_name, status, created_at
        FROM subscriber_invitations
        ORDER BY created_at DESC LIMIT 20
    """)).fetchall()

    return success_response(
        data={'invitations': [
            {'id': str(i[0]), 'token': i[1], 'email': i[2], 'company': i[3], 'status': i[4], 'created': str(i[5])}
            for i in invites
        ]},
        message=f"Found {len(invites)} invitations"
    )

@router.post("/reset-invitation")
async def reset_invitation(
    request: Request,
    db: Session = Depends(get_db)
):
    """Reset a subscriber invitation to pending with fresh expiry. Requires ADMIN_API_KEY."""
    admin_key = request.headers.get('X-Admin-Key', '')
    expected_key = (os.getenv('ADMIN_API_KEY') or '').strip()
    if not admin_key or not expected_key or admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        body = await request.json()
        invite_id = body.get('invitation_id', '')

        result = db.execute(text("""
            UPDATE subscriber_invitations
            SET status = 'pending',
                accepted_at = NULL,
                accepted_by_user_id = NULL,
                expires_at = NOW() + INTERVAL '7 days'
            WHERE id = CAST(:id AS uuid)
            RETURNING id, token, email, company_name, status
        """), {'id': invite_id}).fetchone()

        if not result:
            return success_response(data={'reset': False}, message="Invitation not found")

        db.commit()
        return success_response(
            data={'reset': True, 'token': result[1], 'email': result[2], 'company': result[3]},
            message=f"Invitation reset for {result[3]}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cleanup-test-account")
async def cleanup_test_account(
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a test company account and reset its invitation.
    Requires ADMIN_API_KEY header for auth."""
    admin_key = request.headers.get('X-Admin-Key', '')
    expected_key = (os.getenv('ADMIN_API_KEY') or '').strip()
    if not admin_key or not expected_key or admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        body = await request.json()
        search_name = body.get('company_name', 'test')

        # Find the account
        account = db.execute(text("""
            SELECT id, name, owner_user_id FROM tenant_accounts
            WHERE name ILIKE :search AND is_deleted = false
            ORDER BY created_at DESC LIMIT 1
        """), {'search': f'%{search_name}%'}).fetchone()

        if not account:
            return success_response(data={'deleted': False}, message=f"No account found matching '{search_name}'")

        account_id = str(account[0])
        account_name = account[1]

        # Get user IDs for this tenant
        user_rows = db.execute(text(
            "SELECT id FROM users WHERE tenant_account_id = :tid"
        ), {'tid': account_id}).fetchall()
        user_ids = [str(r[0]) for r in user_rows]

        # Clear owner FK
        db.execute(text("UPDATE tenant_accounts SET owner_user_id = NULL WHERE id = :id"), {'id': account_id})

        # Delete dependent records with savepoints
        if user_ids:
            dependent_tables = [
                ('audit_logs', 'user_id'), ('audit_logs', 'changed_by_id'),
                ('user_invitations', 'invited_by'),
                ('user_sessions', 'user_id'), ('user_preferences', 'user_id'),
                ('notification_preferences', 'user_id'), ('api_keys', 'user_id'),
            ]
            for table_name, col in dependent_tables:
                try:
                    sp = db.begin_nested()
                    db.execute(text(f"DELETE FROM {table_name} WHERE {col} = ANY(:ids)"), {'ids': user_ids})
                    sp.commit()
                except Exception:
                    sp.rollback()

            # Delete users
            try:
                sp = db.begin_nested()
                db.execute(text("DELETE FROM users WHERE tenant_account_id = :tid"), {'tid': account_id})
                sp.commit()
            except Exception:
                sp.rollback()

        # Mark account as canceled
        try:
            sp = db.begin_nested()
            db.execute(text(
                "UPDATE tenant_accounts SET status = 'canceled', is_deleted = true WHERE id = :id"
            ), {'id': account_id})
            sp.commit()
        except Exception:
            sp.rollback()

        # Reset subscriber invitation for reuse
        db.execute(text("""
            UPDATE subscriber_invitations SET status = 'pending', accepted_at = NULL, accepted_by_user_id = NULL
            WHERE company_name ILIKE :search AND status = 'accepted'
        """), {'search': f'%{search_name}%'})

        db.commit()

        return success_response(
            data={'deleted': True, 'account_name': account_name, 'users_cleaned': len(user_ids)},
            message=f"Account '{account_name}' cleaned up, invitation reset"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
