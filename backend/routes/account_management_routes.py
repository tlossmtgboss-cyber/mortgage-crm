"""
Account Management Routes
Master Administrator account, user, subscription, and cost management
"""

from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func, and_, or_, desc
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging
import uuid

from database import get_db
from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    success_response
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin/account-management", tags=["Account Management"])

# Will be set by main.py
User = None
get_current_user = None


def set_dependencies(user_model, current_user_func):
    """Set dependencies from main.py"""
    global User, get_current_user
    User = user_model
    get_current_user = current_user_func


# =============================================================================
# Pydantic Models
# =============================================================================

class AccountFilters(BaseModel):
    """Account list filters"""
    status: Optional[str] = Field(None, description="Filter by status")
    search: Optional[str] = Field(None, description="Search by name, email, or ID")
    plan_ids: Optional[List[str]] = Field(None, description="Filter by plan IDs")
    churn_risk: Optional[bool] = Field(None, description="Show only at-risk accounts")
    min_mrr: Optional[float] = Field(None, description="Minimum MRR filter")
    max_mrr: Optional[float] = Field(None, description="Maximum MRR filter")


class AccountActionRequest(BaseModel):
    """Request for account actions (suspend, reinstate, cancel)"""
    reason: str = Field(..., min_length=1, max_length=1000, description="Reason for action")


class UserActionRequest(BaseModel):
    """Request for user actions"""
    reason: Optional[str] = Field(None, max_length=1000, description="Reason for action")


class ImpersonationRequest(BaseModel):
    """Request to start impersonation"""
    user_id: str = Field(..., description="User ID to impersonate")
    reason: str = Field(..., min_length=10, max_length=1000, description="Reason for impersonation")
    acknowledgment: bool = Field(..., description="Acknowledgment checkbox")

    @validator('acknowledgment')
    def validate_acknowledgment(cls, v):
        if not v:
            raise ValueError('You must acknowledge that this action is logged')
        return v


class RoleUpdateRequest(BaseModel):
    """Request to update user roles"""
    roles: List[str] = Field(..., min_items=1, description="New roles for user")


class InternalNotesRequest(BaseModel):
    """Request to update internal notes"""
    notes: str = Field(..., max_length=5000, description="Internal notes content")


# =============================================================================
# Helper Functions
# =============================================================================

def check_master_admin(user) -> bool:
    """Check if user is a master administrator"""
    if not user:
        return False
    role = getattr(user, 'role', None)
    is_master = getattr(user, 'is_master_admin', False)
    return role == 'master_admin' or is_master or role == 'admin'


def require_master_admin(user):
    """Require master admin permission"""
    if not check_master_admin(user):
        raise PermissionException("Master Administrator access required")


def log_admin_action(db: Session, admin_user, action_type: str, target_type: str,
                     target_id: str, target_name: str = None, reason: str = None,
                     old_values: dict = None, new_values: dict = None,
                     request: Request = None):
    """Log an admin action to audit log"""
    try:
        ip_address = request.client.host if request else None
        user_agent = request.headers.get('user-agent') if request else None

        db.execute(text("""
            INSERT INTO admin_audit_log
            (actor_admin_id, actor_name, action_type, target_type, target_id,
             target_name, ip_address, user_agent, old_values, new_values, reason)
            VALUES (:admin_id, :admin_name, :action_type, :target_type, :target_id,
                    :target_name, :ip_address, :user_agent, :old_values::jsonb, :new_values::jsonb, :reason)
        """), {
            'admin_id': admin_user.id,
            'admin_name': getattr(admin_user, 'full_name', admin_user.email),
            'action_type': action_type,
            'target_type': target_type,
            'target_id': str(target_id),
            'target_name': target_name,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'old_values': str(old_values) if old_values else None,
            'new_values': str(new_values) if new_values else None,
            'reason': reason
        })
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")


def calculate_account_metrics(db: Session, account_id: str) -> dict:
    """Calculate metrics for an account"""
    # Get seat usage
    users_result = db.execute(text("""
        SELECT
            COUNT(*) as total_users,
            COUNT(CASE WHEN is_active = true THEN 1 END) as active_users,
            COUNT(CASE WHEN last_activity_at > NOW() - INTERVAL '30 days' THEN 1 END) as active_30d
        FROM users
        WHERE tenant_account_id = :account_id AND is_deleted = false
    """), {'account_id': account_id}).fetchone()

    # Get cost data for current month
    current_month = datetime.now().strftime('%Y-%m')
    cost_result = db.execute(text("""
        SELECT COALESCE(SUM(amount), 0) as total_cost
        FROM cost_ledger_monthly
        WHERE account_id = :account_id AND month = :month
    """), {'account_id': account_id, 'month': current_month}).fetchone()

    total_users = users_result[0] if users_result else 0
    active_users = users_result[1] if users_result else 0
    active_30d = users_result[2] if users_result else 0
    total_cost = float(cost_result[0]) if cost_result else 0

    return {
        'total_users': total_users,
        'active_users': active_users,
        'active_users_30d': active_30d,
        'total_cost': total_cost,
        'cost_per_user': total_cost / active_users if active_users > 0 else 0
    }


def format_account_response(account: dict, metrics: dict = None) -> dict:
    """Format account data for API response"""
    seats_purchased = account.get('seats_purchased', 1)
    seats_used = metrics.get('total_users', 0) if metrics else 0
    mrr = float(account.get('mrr', 0) or 0)
    total_cost = metrics.get('total_cost', 0) if metrics else 0

    gross_margin = mrr - total_cost
    gross_margin_pct = (gross_margin / mrr * 100) if mrr > 0 else 0
    cost_per_user = metrics.get('cost_per_user', 0) if metrics else 0

    # Calculate churn risk score based on activity and margin
    churn_risk = 0
    if metrics:
        if metrics.get('active_users_30d', 0) == 0:
            churn_risk += 40
        elif metrics.get('active_users_30d', 0) < metrics.get('total_users', 1) * 0.5:
            churn_risk += 20
        if gross_margin_pct < 40:
            churn_risk += 30
        if seats_used < seats_purchased * 0.5:
            churn_risk += 10

    return {
        'id': str(account.get('id', '')),
        'name': account.get('name', ''),
        'domain': account.get('domain'),
        'status': account.get('status', 'active'),
        'planId': account.get('plan_id'),
        'planName': account.get('plan_name', 'Unknown'),
        'billingInterval': account.get('billing_interval', 'monthly'),
        'seatsPurchased': seats_purchased,
        'seatsUsed': seats_used,
        'seatUtilizationPercent': round((seats_used / seats_purchased * 100) if seats_purchased > 0 else 0),
        'mrr': mrr,
        'arr': mrr * 12,
        'trueCostPerUser': round(cost_per_user, 2),
        'grossMargin': round(gross_margin, 2),
        'grossMarginPercent': round(gross_margin_pct, 1),
        'lastActivityAt': account.get('last_activity_at'),
        'renewalDate': account.get('renewal_date'),
        'canceledAt': account.get('canceled_at'),
        'suspendedAt': account.get('suspended_at'),
        'createdAt': account.get('created_at'),
        'ownerUserId': account.get('owner_user_id'),
        'ownerName': account.get('owner_name'),
        'ownerEmail': account.get('owner_email'),
        'internalNotes': account.get('internal_notes'),
        'addOns': account.get('add_ons') or [],
        'churnRiskScore': churn_risk,
        'activeUsersLast30Days': metrics.get('active_users_30d', 0) if metrics else 0,
    }


# =============================================================================
# KPI Endpoints
# =============================================================================

@router.get("/kpis")
async def get_kpis(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get account management KPIs"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        # Check if tenant_accounts table exists
        table_check = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'tenant_accounts'
            )
        """)).scalar()

        if not table_check:
            # Return mock data if tables don't exist yet
            return success_response(
                data={
                    'totalActiveAccounts': 0,
                    'totalSuspendedAccounts': 0,
                    'totalCanceledAccounts': 0,
                    'totalMRR': 0,
                    'totalARR': 0,
                    'totalSeatsPurchased': 0,
                    'totalSeatsUsed': 0,
                    'avgCostPerUser': 0,
                    'avgMarginPercent': 0,
                    'accountsAtRisk': 0,
                    'accountsNoActivity30d': 0,
                    'accountsPaymentFailure': 0,
                    'mrrGrowth': 0,
                    'churnRate': 0,
                },
                message="KPIs retrieved (tables pending migration)"
            )

        # Get account counts by status
        status_counts = db.execute(text("""
            SELECT
                status,
                COUNT(*) as count,
                COALESCE(SUM(
                    CASE WHEN billing_interval = 'monthly'
                    THEN (SELECT price_amount FROM account_subscriptions
                          WHERE account_id = tenant_accounts.id AND status = 'active' LIMIT 1)
                    ELSE (SELECT price_amount / 12 FROM account_subscriptions
                          WHERE account_id = tenant_accounts.id AND status = 'active' LIMIT 1)
                    END
                ), 0) as mrr,
                COALESCE(SUM(seats_purchased), 0) as seats
            FROM tenant_accounts
            WHERE is_deleted = false
            GROUP BY status
        """)).fetchall()

        totals = {
            'active': {'count': 0, 'mrr': 0, 'seats': 0},
            'suspended': {'count': 0, 'mrr': 0, 'seats': 0},
            'canceled': {'count': 0, 'mrr': 0, 'seats': 0}
        }

        for row in status_counts:
            if row[0] in totals:
                totals[row[0]] = {'count': row[1], 'mrr': float(row[2] or 0), 'seats': row[3] or 0}

        total_mrr = totals['active']['mrr']
        total_seats = sum(t['seats'] for t in totals.values())

        # Get active users count
        users_result = db.execute(text("""
            SELECT COUNT(*) FROM users
            WHERE tenant_account_id IS NOT NULL
            AND is_active = true AND is_deleted = false
        """)).scalar() or 0

        # Get at-risk accounts (no activity in 30 days)
        at_risk = db.execute(text("""
            SELECT COUNT(*) FROM tenant_accounts
            WHERE status = 'active' AND is_deleted = false
            AND (
                updated_at < NOW() - INTERVAL '30 days'
                OR NOT EXISTS (
                    SELECT 1 FROM users
                    WHERE tenant_account_id = tenant_accounts.id
                    AND last_activity_at > NOW() - INTERVAL '30 days'
                )
            )
        """)).scalar() or 0

        return success_response(
            data={
                'totalActiveAccounts': totals['active']['count'],
                'totalSuspendedAccounts': totals['suspended']['count'],
                'totalCanceledAccounts': totals['canceled']['count'],
                'totalMRR': total_mrr,
                'totalARR': total_mrr * 12,
                'totalSeatsPurchased': total_seats,
                'totalSeatsUsed': users_result,
                'avgCostPerUser': 35.0,  # Placeholder - calculate from cost_ledger
                'avgMarginPercent': 65.0,  # Placeholder
                'accountsAtRisk': at_risk,
                'accountsNoActivity30d': at_risk,
                'accountsPaymentFailure': 0,  # Placeholder
                'mrrGrowth': 5.2,  # Placeholder
                'churnRate': 2.5,  # Placeholder
            },
            message="KPIs retrieved successfully"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error fetching KPIs: {e}")
        raise DatabaseException(f"Failed to retrieve KPIs: {str(e)}")


# =============================================================================
# Account List Endpoints
# =============================================================================

@router.get("/accounts")
async def list_accounts(
    request: Request,
    status: str = Query('active', description="Account status filter"),
    search: Optional[str] = Query(None, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort: str = Query('mrr', description="Sort field"),
    order: str = Query('desc', description="Sort order"),
    db: Session = Depends(get_db)
):
    """List accounts with filtering and pagination"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        # Check if table exists
        table_check = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'tenant_accounts'
            )
        """)).scalar()

        if not table_check:
            return success_response(
                data={
                    'accounts': [],
                    'total': 0,
                    'page': page,
                    'limit': limit,
                    'totalPages': 0
                },
                message="No accounts (tables pending migration)"
            )

        # Build query
        where_clauses = ["ta.is_deleted = false"]
        params = {'limit': limit, 'offset': (page - 1) * limit}

        if status:
            where_clauses.append("ta.status = :status")
            params['status'] = status

        if search:
            where_clauses.append("""
                (ta.name ILIKE :search OR ta.domain ILIKE :search
                 OR ta.id::text ILIKE :search OR u.email ILIKE :search)
            """)
            params['search'] = f"%{search}%"

        where_sql = " AND ".join(where_clauses)

        # Get total count
        count_query = f"""
            SELECT COUNT(DISTINCT ta.id)
            FROM tenant_accounts ta
            LEFT JOIN users u ON u.id = ta.owner_user_id
            WHERE {where_sql}
        """
        total = db.execute(text(count_query), params).scalar() or 0

        # Get accounts with owner info
        query = f"""
            SELECT
                ta.id, ta.name, ta.domain, ta.status, ta.plan_id, ta.plan_name,
                ta.billing_interval, ta.seats_purchased, ta.internal_notes, ta.add_ons,
                ta.suspended_at, ta.canceled_at, ta.created_at, ta.updated_at,
                ta.owner_user_id,
                u.full_name as owner_name, u.email as owner_email,
                (SELECT MAX(last_activity_at) FROM users WHERE tenant_account_id = ta.id) as last_activity_at,
                (SELECT current_period_end FROM account_subscriptions
                 WHERE account_id = ta.id AND status = 'active' LIMIT 1) as renewal_date,
                COALESCE((SELECT price_amount FROM account_subscriptions
                 WHERE account_id = ta.id AND status = 'active' LIMIT 1), 0) as mrr
            FROM tenant_accounts ta
            LEFT JOIN users u ON u.id = ta.owner_user_id
            WHERE {where_sql}
            ORDER BY ta.created_at DESC
            LIMIT :limit OFFSET :offset
        """

        accounts = db.execute(text(query), params).fetchall()

        # Format response
        account_list = []
        for acc in accounts:
            acc_dict = {
                'id': acc[0], 'name': acc[1], 'domain': acc[2], 'status': acc[3],
                'plan_id': acc[4], 'plan_name': acc[5], 'billing_interval': acc[6],
                'seats_purchased': acc[7], 'internal_notes': acc[8], 'add_ons': acc[9],
                'suspended_at': acc[10].isoformat() if acc[10] else None,
                'canceled_at': acc[11].isoformat() if acc[11] else None,
                'created_at': acc[12].isoformat() if acc[12] else None,
                'owner_user_id': acc[14], 'owner_name': acc[15], 'owner_email': acc[16],
                'last_activity_at': acc[17].isoformat() if acc[17] else None,
                'renewal_date': acc[18].isoformat() if acc[18] else None,
                'mrr': float(acc[19] or 0)
            }
            metrics = calculate_account_metrics(db, str(acc[0]))
            account_list.append(format_account_response(acc_dict, metrics))

        return success_response(
            data={
                'accounts': account_list,
                'total': total,
                'page': page,
                'limit': limit,
                'totalPages': (total + limit - 1) // limit
            },
            message=f"Retrieved {len(account_list)} accounts"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
        raise DatabaseException(f"Failed to list accounts: {str(e)}")


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get detailed account information"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        # Get account
        account = db.execute(text("""
            SELECT
                ta.*, u.full_name as owner_name, u.email as owner_email,
                (SELECT current_period_end FROM account_subscriptions
                 WHERE account_id = ta.id AND status = 'active' LIMIT 1) as renewal_date,
                COALESCE((SELECT price_amount FROM account_subscriptions
                 WHERE account_id = ta.id AND status = 'active' LIMIT 1), 0) as mrr
            FROM tenant_accounts ta
            LEFT JOIN users u ON u.id = ta.owner_user_id
            WHERE ta.id = :account_id AND ta.is_deleted = false
        """), {'account_id': account_id}).fetchone()

        if not account:
            raise NotFoundException(f"Account {account_id} not found")

        # Convert to dict
        columns = ['id', 'name', 'domain', 'status', 'plan_id', 'plan_name', 'billing_interval',
                   'seats_purchased', 'stripe_customer_id', 'stripe_subscription_id',
                   'owner_user_id', 'internal_notes', 'add_ons', 'settings',
                   'suspended_at', 'suspended_reason', 'canceled_at', 'canceled_reason',
                   'created_at', 'updated_at', 'is_deleted', 'owner_name', 'owner_email',
                   'renewal_date', 'mrr']
        acc_dict = dict(zip(columns, account))

        metrics = calculate_account_metrics(db, account_id)
        formatted = format_account_response(acc_dict, metrics)

        # Log view action
        log_admin_action(db, current_user, 'account.viewed', 'account',
                        account_id, acc_dict.get('name'), request=request)

        return success_response(
            data=formatted,
            message="Account retrieved successfully"
        )
    except (PermissionException, NotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        raise DatabaseException(f"Failed to get account: {str(e)}")


# =============================================================================
# Account Actions
# =============================================================================

@router.post("/accounts/{account_id}/suspend")
async def suspend_account(
    account_id: str,
    action: AccountActionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Suspend an account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        # Get current account
        account = db.execute(text("""
            SELECT id, name, status FROM tenant_accounts
            WHERE id = :account_id AND is_deleted = false
        """), {'account_id': account_id}).fetchone()

        if not account:
            raise NotFoundException(f"Account {account_id} not found")

        if account[2] != 'active':
            raise ValidationException(f"Account is not active (current status: {account[2]})")

        # Suspend account
        db.execute(text("""
            UPDATE tenant_accounts
            SET status = 'suspended', suspended_at = NOW(), suspended_reason = :reason, updated_at = NOW()
            WHERE id = :account_id
        """), {'account_id': account_id, 'reason': action.reason})

        # Log subscription event
        db.execute(text("""
            INSERT INTO subscription_events
            (account_id, event_type, actor_id, actor_name, reason)
            VALUES (:account_id, 'suspended', :actor_id, :actor_name, :reason)
        """), {
            'account_id': account_id,
            'actor_id': current_user.id,
            'actor_name': getattr(current_user, 'full_name', current_user.email),
            'reason': action.reason
        })

        db.commit()

        # Log admin action
        log_admin_action(db, current_user, 'account.suspended', 'account',
                        account_id, account[1], reason=action.reason, request=request)

        return success_response(
            data={'status': 'suspended'},
            message=f"Account '{account[1]}' suspended successfully"
        )
    except (PermissionException, NotFoundException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error suspending account: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to suspend account: {str(e)}")


@router.post("/accounts/{account_id}/reinstate")
async def reinstate_account(
    account_id: str,
    action: AccountActionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Reinstate a suspended account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        account = db.execute(text("""
            SELECT id, name, status FROM tenant_accounts
            WHERE id = :account_id AND is_deleted = false
        """), {'account_id': account_id}).fetchone()

        if not account:
            raise NotFoundException(f"Account {account_id} not found")

        if account[2] != 'suspended':
            raise ValidationException(f"Account is not suspended (current status: {account[2]})")

        db.execute(text("""
            UPDATE tenant_accounts
            SET status = 'active', suspended_at = NULL, suspended_reason = NULL, updated_at = NOW()
            WHERE id = :account_id
        """), {'account_id': account_id})

        db.execute(text("""
            INSERT INTO subscription_events
            (account_id, event_type, actor_id, actor_name, reason)
            VALUES (:account_id, 'reinstated', :actor_id, :actor_name, :reason)
        """), {
            'account_id': account_id,
            'actor_id': current_user.id,
            'actor_name': getattr(current_user, 'full_name', current_user.email),
            'reason': action.reason
        })

        db.commit()

        log_admin_action(db, current_user, 'account.reinstated', 'account',
                        account_id, account[1], reason=action.reason, request=request)

        return success_response(
            data={'status': 'active'},
            message=f"Account '{account[1]}' reinstated successfully"
        )
    except (PermissionException, NotFoundException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error reinstating account: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to reinstate account: {str(e)}")


@router.post("/accounts/{account_id}/cancel")
async def cancel_account(
    account_id: str,
    action: AccountActionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Cancel an account (soft cancel)"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        account = db.execute(text("""
            SELECT id, name, status FROM tenant_accounts
            WHERE id = :account_id AND is_deleted = false
        """), {'account_id': account_id}).fetchone()

        if not account:
            raise NotFoundException(f"Account {account_id} not found")

        if account[2] == 'canceled':
            raise ValidationException("Account is already canceled")

        db.execute(text("""
            UPDATE tenant_accounts
            SET status = 'canceled', canceled_at = NOW(), canceled_reason = :reason, updated_at = NOW()
            WHERE id = :account_id
        """), {'account_id': account_id, 'reason': action.reason})

        db.execute(text("""
            INSERT INTO subscription_events
            (account_id, event_type, actor_id, actor_name, reason)
            VALUES (:account_id, 'canceled', :actor_id, :actor_name, :reason)
        """), {
            'account_id': account_id,
            'actor_id': current_user.id,
            'actor_name': getattr(current_user, 'full_name', current_user.email),
            'reason': action.reason
        })

        db.commit()

        log_admin_action(db, current_user, 'account.canceled', 'account',
                        account_id, account[1], reason=action.reason, request=request)

        return success_response(
            data={'status': 'canceled'},
            message=f"Account '{account[1]}' canceled successfully"
        )
    except (PermissionException, NotFoundException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error canceling account: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to cancel account: {str(e)}")


@router.put("/accounts/{account_id}/notes")
async def update_notes(
    account_id: str,
    notes: InternalNotesRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update internal notes for an account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        result = db.execute(text("""
            UPDATE tenant_accounts
            SET internal_notes = :notes, updated_at = NOW()
            WHERE id = :account_id AND is_deleted = false
            RETURNING name
        """), {'account_id': account_id, 'notes': notes.notes}).fetchone()

        if not result:
            raise NotFoundException(f"Account {account_id} not found")

        db.commit()

        log_admin_action(db, current_user, 'account.notes_updated', 'account',
                        account_id, result[0], request=request)

        return success_response(
            data={'notes': notes.notes},
            message="Notes updated successfully"
        )
    except (PermissionException, NotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error updating notes: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to update notes: {str(e)}")


# =============================================================================
# Account Users
# =============================================================================

@router.get("/accounts/{account_id}/users")
async def list_account_users(
    account_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List users for an account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        # Verify account exists
        account = db.execute(text("""
            SELECT name FROM tenant_accounts WHERE id = :account_id AND is_deleted = false
        """), {'account_id': account_id}).fetchone()

        if not account:
            raise NotFoundException(f"Account {account_id} not found")

        # Get users
        users = db.execute(text("""
            SELECT
                u.id, u.email, u.full_name, u.role, u.is_active, u.mfa_enabled,
                u.created_at, u.last_activity_at, u.device_count, u.active_sessions_count,
                COALESCE(s.tasks_completed, 0) as tasks_30d,
                COALESCE(s.calls_placed, 0) as calls_placed_30d,
                COALESCE(s.calls_received, 0) as calls_received_30d,
                COALESCE(s.texts_sent, 0) as texts_30d,
                COALESCE(s.emails_sent, 0) as emails_30d
            FROM users u
            LEFT JOIN user_activity_stats s ON s.user_id = u.id
                AND s.period = to_char(NOW(), 'YYYY-MM')
            WHERE u.tenant_account_id = :account_id AND u.is_deleted = false
            ORDER BY u.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {'account_id': account_id, 'limit': limit, 'offset': (page - 1) * limit}).fetchall()

        total = db.execute(text("""
            SELECT COUNT(*) FROM users
            WHERE tenant_account_id = :account_id AND is_deleted = false
        """), {'account_id': account_id}).scalar() or 0

        user_list = []
        for u in users:
            status = 'active' if u[4] else 'disabled'
            user_list.append({
                'id': str(u[0]),
                'email': u[1],
                'name': u[2] or '',
                'roles': [u[3]] if u[3] else [],
                'status': status,
                'mfaEnabled': u[5] or False,
                'createdAt': u[6].isoformat() if u[6] else None,
                'lastLoginAt': u[7].isoformat() if u[7] else None,
                'deviceCount': u[8] or 0,
                'activeSessions': u[9] or 0,
                'accountId': account_id,
                'accountName': account[0],
                'tasksCompleted30d': u[10],
                'callsPlaced30d': u[11],
                'callsReceived30d': u[12],
                'textsSent30d': u[13],
                'emailsSent30d': u[14],
            })

        return success_response(
            data={
                'users': user_list,
                'total': total,
                'page': page,
                'limit': limit
            },
            message=f"Retrieved {len(user_list)} users"
        )
    except (PermissionException, NotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise DatabaseException(f"Failed to list users: {str(e)}")


# =============================================================================
# User Detail & Actions
# =============================================================================

@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get detailed user information"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        user = db.execute(text("""
            SELECT
                u.*, ta.name as account_name,
                s.tasks_completed, s.calls_placed, s.calls_received, s.texts_sent,
                s.emails_sent, s.notes_created, s.leads_created, s.loans_created,
                s.documents_uploaded, s.ai_actions_triggered
            FROM users u
            LEFT JOIN tenant_accounts ta ON ta.id = u.tenant_account_id
            LEFT JOIN user_activity_stats s ON s.user_id = u.id
                AND s.period = to_char(NOW(), 'YYYY-MM')
            WHERE u.id = :user_id AND u.is_deleted = false
        """), {'user_id': user_id}).fetchone()

        if not user:
            raise NotFoundException(f"User {user_id} not found")

        status = 'active' if user.is_active else 'disabled'

        user_data = {
            'id': str(user.id),
            'email': user.email,
            'name': user.full_name or '',
            'accountId': str(user.tenant_account_id) if user.tenant_account_id else None,
            'accountName': user.account_name or '',
            'roles': [user.role] if user.role else [],
            'status': status,
            'mfaEnabled': user.mfa_enabled or False,
            'createdAt': user.created_at.isoformat() if user.created_at else None,
            'lastLoginAt': user.last_activity_at.isoformat() if user.last_activity_at else None,
            'deviceCount': user.device_count or 0,
            'activeSessions': user.active_sessions_count or 0,
            'tasksCompleted30d': user.tasks_completed or 0,
            'callsPlaced30d': user.calls_placed or 0,
            'callsReceived30d': user.calls_received or 0,
            'textsSent30d': user.texts_sent or 0,
            'emailsSent30d': user.emails_sent or 0,
            'notesCreated30d': user.notes_created or 0,
            'leadsCreated30d': user.leads_created or 0,
            'loansCreated30d': user.loans_created or 0,
            'documentsUploaded30d': user.documents_uploaded or 0,
            'aiActionsTriggered30d': user.ai_actions_triggered or 0,
        }

        log_admin_action(db, current_user, 'user.viewed', 'user',
                        user_id, user.full_name or user.email, request=request)

        return success_response(
            data=user_data,
            message="User retrieved successfully"
        )
    except (PermissionException, NotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        raise DatabaseException(f"Failed to get user: {str(e)}")


@router.get("/users/{user_id}/login-history")
async def get_login_history(
    user_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    result_filter: Optional[str] = Query(None, alias="filter"),
    db: Session = Depends(get_db)
):
    """Get user login history"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        where_clause = "user_id = :user_id"
        params = {'user_id': user_id, 'limit': limit, 'offset': (page - 1) * limit}

        if result_filter and result_filter in ['success', 'failed']:
            where_clause += " AND result = :result"
            params['result'] = result_filter

        events = db.execute(text(f"""
            SELECT id, result, failure_reason, ip_address, device, browser,
                   location, session_duration_seconds, created_at
            FROM login_events
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).fetchall()

        total = db.execute(text(f"""
            SELECT COUNT(*) FROM login_events WHERE {where_clause}
        """), params).scalar() or 0

        history = []
        for e in events:
            history.append({
                'id': str(e[0]),
                'result': e[1],
                'failureReason': e[2],
                'ipAddress': e[3],
                'device': e[4],
                'browser': e[5],
                'location': e[6],
                'sessionDuration': e[7],
                'timestamp': e[8].isoformat() if e[8] else None
            })

        return success_response(
            data={
                'events': history,
                'total': total,
                'page': page,
                'limit': limit
            },
            message=f"Retrieved {len(history)} login events"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error getting login history: {e}")
        raise DatabaseException(f"Failed to get login history: {str(e)}")


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: str,
    action: UserActionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Disable a user"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        user = db.execute(text("""
            SELECT id, full_name, email, is_active FROM users
            WHERE id = :user_id AND is_deleted = false
        """), {'user_id': user_id}).fetchone()

        if not user:
            raise NotFoundException(f"User {user_id} not found")

        if not user[3]:
            raise ValidationException("User is already disabled")

        db.execute(text("""
            UPDATE users SET is_active = false, updated_at = NOW()
            WHERE id = :user_id
        """), {'user_id': user_id})

        db.commit()

        log_admin_action(db, current_user, 'user.disabled', 'user',
                        user_id, user[1] or user[2], reason=action.reason, request=request)

        return success_response(
            data={'status': 'disabled'},
            message=f"User '{user[1] or user[2]}' disabled successfully"
        )
    except (PermissionException, NotFoundException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error disabling user: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to disable user: {str(e)}")


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Enable a disabled user"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        user = db.execute(text("""
            SELECT id, full_name, email, is_active FROM users
            WHERE id = :user_id AND is_deleted = false
        """), {'user_id': user_id}).fetchone()

        if not user:
            raise NotFoundException(f"User {user_id} not found")

        if user[3]:
            raise ValidationException("User is already active")

        db.execute(text("""
            UPDATE users SET is_active = true, updated_at = NOW()
            WHERE id = :user_id
        """), {'user_id': user_id})

        db.commit()

        log_admin_action(db, current_user, 'user.enabled', 'user',
                        user_id, user[1] or user[2], request=request)

        return success_response(
            data={'status': 'active'},
            message=f"User '{user[1] or user[2]}' enabled successfully"
        )
    except (PermissionException, NotFoundException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error enabling user: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to enable user: {str(e)}")


@router.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: str,
    roles: RoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update user roles"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        user = db.execute(text("""
            SELECT id, full_name, email, role FROM users
            WHERE id = :user_id AND is_deleted = false
        """), {'user_id': user_id}).fetchone()

        if not user:
            raise NotFoundException(f"User {user_id} not found")

        old_role = user[3]
        new_role = roles.roles[0] if roles.roles else None

        db.execute(text("""
            UPDATE users SET role = :role, updated_at = NOW()
            WHERE id = :user_id
        """), {'user_id': user_id, 'role': new_role})

        db.commit()

        log_admin_action(db, current_user, 'user.role_changed', 'user',
                        user_id, user[1] or user[2],
                        old_values={'role': old_role},
                        new_values={'role': new_role},
                        request=request)

        return success_response(
            data={'roles': roles.roles},
            message=f"Roles updated for '{user[1] or user[2]}'"
        )
    except (PermissionException, NotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error updating roles: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to update roles: {str(e)}")


# =============================================================================
# Impersonation
# =============================================================================

@router.post("/impersonate/start")
async def start_impersonation(
    imp_request: ImpersonationRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Start impersonating a user"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        target_user = db.execute(text("""
            SELECT id, full_name, email, tenant_account_id FROM users
            WHERE id = :user_id AND is_deleted = false
        """), {'user_id': imp_request.user_id}).fetchone()

        if not target_user:
            raise NotFoundException(f"User {imp_request.user_id} not found")

        # Create impersonation session
        session_id = db.execute(text("""
            INSERT INTO impersonation_sessions
            (admin_user_id, target_user_id, account_id, reason, acknowledgment_checked,
             ip_address, user_agent)
            VALUES (:admin_id, :target_id, :account_id, :reason, :ack, :ip, :ua)
            RETURNING id
        """), {
            'admin_id': current_user.id,
            'target_id': target_user[0],
            'account_id': target_user[3],
            'reason': imp_request.reason,
            'ack': imp_request.acknowledgment,
            'ip': request.client.host,
            'ua': request.headers.get('user-agent')
        }).scalar()

        db.commit()

        log_admin_action(db, current_user, 'impersonation.started', 'user',
                        imp_request.user_id, target_user[1] or target_user[2],
                        reason=imp_request.reason, request=request)

        return success_response(
            data={
                'sessionId': str(session_id),
                'targetUserId': str(target_user[0]),
                'targetUserName': target_user[1] or target_user[2],
            },
            message=f"Impersonation started for '{target_user[1] or target_user[2]}'"
        )
    except (PermissionException, NotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error starting impersonation: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to start impersonation: {str(e)}")


@router.post("/impersonate/stop")
async def stop_impersonation(
    request: Request,
    db: Session = Depends(get_db)
):
    """Stop impersonation session"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        # Find active session
        session = db.execute(text("""
            SELECT id, target_user_id FROM impersonation_sessions
            WHERE admin_user_id = :admin_id AND is_active = true
            ORDER BY started_at DESC LIMIT 1
        """), {'admin_id': current_user.id}).fetchone()

        if not session:
            raise ValidationException("No active impersonation session found")

        # End session
        db.execute(text("""
            UPDATE impersonation_sessions
            SET is_active = false, ended_at = NOW()
            WHERE id = :session_id
        """), {'session_id': session[0]})

        db.commit()

        log_admin_action(db, current_user, 'impersonation.stopped', 'user',
                        str(session[1]), request=request)

        return success_response(
            data={'sessionEnded': True},
            message="Impersonation session ended"
        )
    except (PermissionException, ValidationException):
        raise
    except Exception as e:
        logger.error(f"Error stopping impersonation: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to stop impersonation: {str(e)}")


# =============================================================================
# Billing & Costs
# =============================================================================

@router.get("/accounts/{account_id}/invoices")
async def get_account_invoices(
    account_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get invoices for an account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        invoices = db.execute(text("""
            SELECT id, invoice_number, amount, status, description,
                   invoice_url, created_at, paid_at, due_date
            FROM account_invoices
            WHERE account_id = :account_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), {'account_id': account_id, 'limit': limit, 'offset': (page - 1) * limit}).fetchall()

        total = db.execute(text("""
            SELECT COUNT(*) FROM account_invoices WHERE account_id = :account_id
        """), {'account_id': account_id}).scalar() or 0

        invoice_list = []
        for inv in invoices:
            invoice_list.append({
                'id': str(inv[0]),
                'invoiceNumber': inv[1],
                'amount': float(inv[2] or 0),
                'status': inv[3],
                'description': inv[4],
                'invoiceUrl': inv[5],
                'createdAt': inv[6].isoformat() if inv[6] else None,
                'paidAt': inv[7].isoformat() if inv[7] else None,
                'dueDate': inv[8].isoformat() if inv[8] else None
            })

        return success_response(
            data={
                'invoices': invoice_list,
                'total': total,
                'page': page,
                'limit': limit
            },
            message=f"Retrieved {len(invoice_list)} invoices"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error getting invoices: {e}")
        raise DatabaseException(f"Failed to get invoices: {str(e)}")


@router.get("/accounts/{account_id}/cost-breakdown")
async def get_cost_breakdown(
    account_id: str,
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """Get cost breakdown for an account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        if not month:
            month = datetime.now().strftime('%Y-%m')

        costs = db.execute(text("""
            SELECT cost_category, vendor, SUM(amount) as amount, SUM(units) as units
            FROM cost_ledger_monthly
            WHERE account_id = :account_id AND month = :month
            GROUP BY cost_category, vendor
            ORDER BY amount DESC
        """), {'account_id': account_id, 'month': month}).fetchall()

        breakdown = {}
        total_cost = 0
        for c in costs:
            category = c[0]
            amount = float(c[2] or 0)
            total_cost += amount
            if category not in breakdown:
                breakdown[category] = {'amount': 0, 'vendors': []}
            breakdown[category]['amount'] += amount
            if c[1]:
                breakdown[category]['vendors'].append({'name': c[1], 'amount': amount})

        return success_response(
            data={
                'accountId': account_id,
                'month': month,
                'totalCost': total_cost,
                'breakdown': breakdown,
                'categories': [
                    {
                        'category': cat,
                        'amount': data['amount'],
                        'percentage': round(data['amount'] / total_cost * 100, 1) if total_cost > 0 else 0
                    }
                    for cat, data in sorted(breakdown.items(), key=lambda x: x[1]['amount'], reverse=True)
                ]
            },
            message=f"Cost breakdown for {month}"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error getting cost breakdown: {e}")
        raise DatabaseException(f"Failed to get cost breakdown: {str(e)}")


@router.get("/accounts/{account_id}/cost-trend")
async def get_cost_trend(
    account_id: str,
    request: Request,
    months: int = Query(6, ge=1, le=24, description="Number of months"),
    db: Session = Depends(get_db)
):
    """Get cost trend for an account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        trend = db.execute(text("""
            SELECT month, SUM(amount) as total_cost
            FROM cost_ledger_monthly
            WHERE account_id = :account_id
            AND month >= to_char(NOW() - INTERVAL ':months months', 'YYYY-MM')
            GROUP BY month
            ORDER BY month ASC
        """.replace(':months', str(months))), {'account_id': account_id}).fetchall()

        trend_data = []
        for t in trend:
            trend_data.append({
                'month': t[0],
                'totalCost': float(t[1] or 0),
                'costPerUser': 0,  # Would need user count per month
                'margin': 0  # Would need revenue per month
            })

        return success_response(
            data={
                'accountId': account_id,
                'months': months,
                'trend': trend_data
            },
            message=f"Cost trend for last {months} months"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error getting cost trend: {e}")
        raise DatabaseException(f"Failed to get cost trend: {str(e)}")


@router.get("/accounts/{account_id}/subscription-timeline")
async def get_subscription_timeline(
    account_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get subscription event timeline for an account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        events = db.execute(text("""
            SELECT id, event_type, from_plan, to_plan, from_seats, to_seats,
                   amount, actor_name, reason, created_at
            FROM subscription_events
            WHERE account_id = :account_id
            ORDER BY created_at DESC
            LIMIT 50
        """), {'account_id': account_id}).fetchall()

        timeline = []
        for e in events:
            timeline.append({
                'id': str(e[0]),
                'eventType': e[1],
                'fromPlan': e[2],
                'toPlan': e[3],
                'fromSeats': e[4],
                'toSeats': e[5],
                'amount': float(e[6]) if e[6] else None,
                'actorName': e[7],
                'reason': e[8],
                'timestamp': e[9].isoformat() if e[9] else None
            })

        return success_response(
            data={'timeline': timeline},
            message=f"Retrieved {len(timeline)} events"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error getting timeline: {e}")
        raise DatabaseException(f"Failed to get timeline: {str(e)}")


# =============================================================================
# Audit Log
# =============================================================================

@router.get("/accounts/{account_id}/audit-log")
async def get_account_audit_log(
    account_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get audit log for an account"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        logs = db.execute(text("""
            SELECT id, actor_name, action_type, target_type, target_name,
                   ip_address, reason, created_at
            FROM admin_audit_log
            WHERE target_type = 'account' AND target_id = :account_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), {'account_id': account_id, 'limit': limit, 'offset': (page - 1) * limit}).fetchall()

        audit_list = []
        for log in logs:
            audit_list.append({
                'id': str(log[0]),
                'actorName': log[1],
                'actionType': log[2],
                'targetType': log[3],
                'targetName': log[4],
                'ipAddress': log[5],
                'reason': log[6],
                'timestamp': log[7].isoformat() if log[7] else None
            })

        return success_response(
            data={
                'logs': audit_list,
                'page': page,
                'limit': limit
            },
            message=f"Retrieved {len(audit_list)} audit entries"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        raise DatabaseException(f"Failed to get audit log: {str(e)}")


@router.get("/users/{user_id}/audit-log")
async def get_user_audit_log(
    user_id: str,
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get audit log for a user"""
    try:
        current_user = await get_current_user(request, db)
        require_master_admin(current_user)

        logs = db.execute(text("""
            SELECT id, actor_name, action_type, target_name, ip_address, reason, created_at
            FROM admin_audit_log
            WHERE target_type = 'user' AND target_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), {'user_id': user_id, 'limit': limit, 'offset': (page - 1) * limit}).fetchall()

        audit_list = []
        for log in logs:
            audit_list.append({
                'id': str(log[0]),
                'actorName': log[1],
                'actionType': log[2],
                'targetName': log[3],
                'ipAddress': log[4],
                'reason': log[5],
                'timestamp': log[6].isoformat() if log[6] else None
            })

        return success_response(
            data={
                'logs': audit_list,
                'page': page,
                'limit': limit
            },
            message=f"Retrieved {len(audit_list)} audit entries"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        raise DatabaseException(f"Failed to get audit log: {str(e)}")
