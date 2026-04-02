"""
Account Management Models, Helpers, and SQL Safety Infrastructure
Extracted from account_management_routes.py
"""

from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging

from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    success_response
)
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# =============================================================================
# SQL Safety: Whitelist-validated table/column operations
# =============================================================================

# Whitelist of tables allowed for DELETE operations in admin cleanup
ALLOWED_CLEANUP_TABLES = frozenset({
    'tasks', 'task_instances', 'purl_tasks',
    'team_members', 'team_member_profiles',
    'extracted_data', 'referral_partners',
    'user_settings', 'user_notifications', 'user_invitations',
    'loan_officer_profiles', 'conversations', 'ai_conversation_messages',
    'onboarding_user_profiles', 'onboarding_user_categories',
    'onboarding_user_responsibilities', 'onboarding_user_permissions',
    'subscription_events', 'account_subscriptions', 'account_invoices',
    'cost_ledger_monthly', 'usage_events', 'login_events',
    'admin_audit_log', 'impersonation_sessions', 'user_activity_stats',
    'account_kpi_snapshots', 'account_user_roles', 'subscriber_invitations',
    'tenant_accounts', 'users'
})

# Whitelist of columns allowed for WHERE clauses
ALLOWED_CLEANUP_COLUMNS = frozenset({
    'user_id', 'invited_by', 'accepted_by_user_id', 'revoked_by',
    'actor_admin_id', 'id', 'email', 'status'
})


def validate_table_name(table: str) -> str:
    """Validate table name against whitelist. Raises ValueError if invalid."""
    if table not in ALLOWED_CLEANUP_TABLES:
        raise ValueError(f"Table '{table}' is not in the allowed cleanup tables whitelist")
    return table


def validate_column_name(column: str) -> str:
    """Validate column name against whitelist. Raises ValueError if invalid."""
    if column not in ALLOWED_CLEANUP_COLUMNS:
        raise ValueError(f"Column '{column}' is not in the allowed columns whitelist")
    return column


def safe_delete_from_table(db: Session, table: str, where_clause: str = None, params: dict = None) -> int:
    """
    Safely execute DELETE on a whitelisted table.

    Args:
        db: Database session
        table: Table name (must be in whitelist)
        where_clause: Optional WHERE clause (e.g., "user_id != :admin_id")
        params: Parameters for the WHERE clause

    Returns:
        Number of rows deleted

    Raises:
        ValueError: If table is not in whitelist
    """
    validated_table = validate_table_name(table)

    if where_clause:
        sql = "DELETE FROM " + validated_table + " WHERE " + where_clause
    else:
        sql = "DELETE FROM " + validated_table

    result = db.execute(text(sql), params or {})
    return result.rowcount


def safe_delete_with_column_condition(
    db: Session,
    table: str,
    column: str,
    operator: str,
    param_name: str,
    params: dict
) -> int:
    """
    Safely execute DELETE with a column-based WHERE condition.

    Args:
        db: Database session
        table: Table name (must be in whitelist)
        column: Column name (must be in whitelist)
        operator: SQL operator (=, !=, IS NOT NULL, etc.)
        param_name: Parameter name for the value (e.g., "admin_id")
        params: Parameters dict containing the param_name

    Returns:
        Number of rows deleted
    """
    validated_table = validate_table_name(table)
    validated_column = validate_column_name(column)

    # Validate operator to prevent injection through operator
    allowed_operators = {'=', '!=', '<>', 'IS NULL', 'IS NOT NULL', '<', '>', '<=', '>='}
    if operator.upper() not in allowed_operators:
        raise ValueError(f"Operator '{operator}' is not allowed")

    if 'IS' in operator.upper():
        sql = "DELETE FROM " + validated_table + " WHERE " + validated_column + " " + operator
    else:
        sql = "DELETE FROM " + validated_table + " WHERE " + validated_column + " " + operator + " :" + param_name

    result = db.execute(text(sql), params)
    return result.rowcount


def table_exists(db: Session, table_name: str) -> bool:
    """Check if a table exists in the database (works with both PostgreSQL and SQLite)"""
    try:
        # Try PostgreSQL syntax first
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table_name
            )
        """), {"table_name": table_name}).scalar()
        return bool(result)
    except Exception as e:
        logger.error(f"Error in table_exists (PostgreSQL check): {e}")
        try:
            # Fall back to SQLite syntax
            result = db.execute(text("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name = :table_name
            """), {"table_name": table_name}).scalar()
            return result > 0
        except Exception as e2:
            logger.error(f"Error in table_exists (SQLite fallback): {e2}")
            return False


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
    acknowledgment: bool = Field(True, description="Acknowledgment checkbox (defaults to true for admin preview)")


class RoleUpdateRequest(BaseModel):
    """Request to update user roles"""
    roles: List[str] = Field(..., min_items=1, description="New roles for user")


class InternalNotesRequest(BaseModel):
    """Request to update internal notes"""
    notes: str = Field(..., max_length=5000, description="Internal notes content")


class InviteSubscriberRequest(BaseModel):
    """Request to invite a new subscriber"""
    email: str = Field(..., description="Email address to invite")
    company_name: str = Field(..., description="Company/organization name")
    contact_name: Optional[str] = Field(None, description="Contact person name")
    plan: str = Field('professional', description="Subscription plan")
    seats: int = Field(5, ge=1, le=1000, description="Initial seat count")
    message: Optional[str] = Field(None, max_length=2000, description="Personal message")
    promo_code: Optional[str] = Field(None, max_length=50, description="Promo code for special pricing")


class UserPermissionsRequest(BaseModel):
    """Request to update user permissions"""
    permissions: Dict[str, Dict[str, bool]] = Field(..., description="Page permissions map")


# =============================================================================
# Helper Functions
# =============================================================================

# Module-level globals set by set_dependencies()
_get_current_user = None


def set_auth_dependency(current_user_func):
    """Set auth dependency from parent module"""
    global _get_current_user
    _get_current_user = current_user_func


def check_master_admin(user) -> bool:
    """Check if user is a master administrator or site administrator"""
    if not user:
        return False
    role = getattr(user, 'role', None)
    permission_role = getattr(user, 'permission_role', None)
    is_master = getattr(user, 'is_master_admin', False)
    # Allow master_admin, admin, and site_admin roles
    admin_roles = ['master_admin', 'admin', 'site_admin']
    return (
        role in admin_roles or
        permission_role in admin_roles or
        is_master
    )


def require_master_admin(user):
    """Require master admin permission"""
    if not check_master_admin(user):
        raise PermissionException("Master Administrator access required")


async def get_user_from_request(request: Request, db: Session):
    """Helper to extract token and get current user."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = auth_header.replace('Bearer ', '')
    return await _get_current_user(token, request, db)


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
    except SQLAlchemyError as e:
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
        WHERE tenant_account_id = :account_id
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


async def _get_kpis_from_organizations(db: Session):
    """Calculate KPIs from organizations table when tenant_accounts doesn't exist"""
    try:
        # Get organization counts (exclude default org with id=1)
        active_count = db.execute(text("""
            SELECT COUNT(*) FROM organizations
            WHERE id > 1 AND (is_active = 1 OR is_active IS NULL)
        """)).scalar() or 0

        suspended_count = db.execute(text("""
            SELECT COUNT(*) FROM organizations
            WHERE id > 1 AND is_active = 0
        """)).scalar() or 0

        # Get total users
        total_users = db.execute(text("""
            SELECT COUNT(*) FROM users WHERE organization_id > 1
        """)).scalar() or 0

        # Calculate MRR based on subscription tiers
        tier_data = db.execute(text("""
            SELECT
                o.subscription_tier,
                COUNT(*) as org_count,
                (SELECT COUNT(*) FROM users WHERE organization_id = o.id) as user_count
            FROM organizations o
            WHERE o.id > 1 AND (o.is_active = 1 OR o.is_active IS NULL)
            GROUP BY o.id, o.subscription_tier
        """)).fetchall()

        tier_prices = {
            'starter': 99,
            'professional': 199,
            'business': 399,
            'enterprise': 799,
            'lead_management': 49,
            'full_pipeline': 149
        }

        total_mrr = 0
        total_seats = 0
        for tier, count, users in tier_data:
            mrr = tier_prices.get(tier, 199)
            total_mrr += mrr
            total_seats += max(5, (users or 0) + 2)

        # Get users with no recent activity
        no_activity_30d = db.execute(text("""
            SELECT COUNT(DISTINCT organization_id) FROM users
            WHERE organization_id > 1
            AND (last_activity_at IS NULL OR last_activity_at < datetime('now', '-30 days'))
        """)).scalar() or 0

        avg_cost_per_user = 35
        avg_margin = 65.0 if total_mrr > 0 else 0

        return success_response(
            data={
                'totalActiveAccounts': active_count,
                'totalSuspendedAccounts': suspended_count,
                'totalCanceledAccounts': 0,
                'totalMRR': total_mrr,
                'totalARR': total_mrr * 12,
                'totalSeatsPurchased': total_seats,
                'totalSeatsUsed': total_users,
                'avgCostPerUser': avg_cost_per_user,
                'avgMarginPercent': avg_margin,
                'accountsAtRisk': no_activity_30d,
                'accountsNoActivity30d': no_activity_30d,
                'accountsPaymentFailure': 0,
                'mrrGrowth': 5.2,
                'churnRate': 2.5,
            },
            message="KPIs retrieved from organizations"
        )
    except Exception as e:
        logger.error(f"Error getting KPIs from organizations: {e}")
        raise DatabaseException("Failed to get KPIs")


async def _list_accounts_from_organizations(db: Session, status: str, search: str, page: int, limit: int, sort: str, order: str):
    """Fallback: List accounts from organizations table when tenant_accounts doesn't exist"""
    try:
        # Map status to is_active
        is_active = status == 'active'

        # Build where clause
        where_clauses = ["1=1"]
        params = {'limit': limit, 'offset': (page - 1) * limit}

        if status == 'active':
            where_clauses.append("(o.is_active = 1 OR o.is_active IS NULL)")
        elif status == 'suspended':
            where_clauses.append("o.is_active = 0")
        elif status == 'canceled':
            where_clauses.append("o.is_active = 0")

        if search:
            where_clauses.append("(o.name LIKE :search OR o.slug LIKE :search)")
            params['search'] = f"%{search}%"

        # Exclude default organization
        where_clauses.append("o.id > 1")

        where_sql = " AND ".join(where_clauses)

        # Count total
        count_sql = "SELECT COUNT(*) FROM organizations o WHERE " + where_sql
        count_result = db.execute(text(count_sql), params).scalar() or 0

        # Get organizations with user metrics
        query = """
            SELECT
                o.id,
                o.name,
                o.slug,
                o.subscription_tier,
                o.is_active,
                o.created_at,
                (SELECT COUNT(*) FROM users WHERE organization_id = o.id) as user_count,
                (SELECT MAX(last_activity_at) FROM users WHERE organization_id = o.id) as last_activity,
                (SELECT email FROM users WHERE organization_id = o.id AND role IN ('admin', 'master_admin', 'loan_officer') ORDER BY created_at LIMIT 1) as owner_email,
                (SELECT full_name FROM users WHERE organization_id = o.id AND role IN ('admin', 'master_admin', 'loan_officer') ORDER BY created_at LIMIT 1) as owner_name,
                (SELECT id FROM users WHERE organization_id = o.id ORDER BY created_at LIMIT 1) as owner_id
            FROM organizations o
            WHERE """ + where_sql + """
            ORDER BY o.created_at DESC
            LIMIT :limit OFFSET :offset
        """

        orgs = db.execute(text(query), params).fetchall()

        # Format response
        account_list = []
        for org in orgs:
            org_id, name, slug, tier, is_active_val, created_at, user_count, last_activity, owner_email, owner_name, owner_id = org

            # Calculate MRR based on subscription tier
            tier_prices = {
                'starter': 99,
                'professional': 199,
                'business': 399,
                'enterprise': 799,
                'lead_management': 49,
                'full_pipeline': 149
            }
            mrr = tier_prices.get(tier, 199) if user_count else 0

            # Calculate metrics
            seats_purchased = max(5, user_count + 2)  # Estimate seats
            cost_per_user = 35  # Estimated cost
            gross_margin = mrr - (cost_per_user * user_count) if user_count else 0
            margin_pct = (gross_margin / mrr * 100) if mrr > 0 else 0

            # Determine status
            acc_status = 'active' if is_active_val or is_active_val is None else 'suspended'

            account_list.append({
                'id': str(org_id),
                'name': name or f'Organization {org_id}',
                'domain': slug,
                'status': acc_status,
                'planName': (tier or 'Professional').replace('_', ' ').title(),
                'billingInterval': 'monthly',
                'seatsPurchased': seats_purchased,
                'seatsUsed': user_count or 0,
                'seatUtilizationPercent': round((user_count / seats_purchased * 100) if seats_purchased > 0 else 0),
                'mrr': mrr,
                'arr': mrr * 12,
                'trueCostPerUser': cost_per_user,
                'grossMargin': round(gross_margin, 2),
                'grossMarginPercent': round(margin_pct, 1),
                'lastActivityAt': last_activity.isoformat() if last_activity else None,
                'renewalDate': None,
                'canceledAt': None,
                'suspendedAt': None,
                'createdAt': created_at.isoformat() if created_at else None,
                'ownerUserId': owner_id,
                'ownerName': owner_name or owner_email,
                'ownerEmail': owner_email,
                'internalNotes': None,
                'addOns': [],
                'churnRiskScore': 15 if last_activity else 50,
                'activeUsersLast30Days': user_count or 0,
            })

        return success_response(
            data={
                'accounts': account_list,
                'total': count_result,
                'page': page,
                'limit': limit,
                'totalPages': (count_result + limit - 1) // limit if count_result > 0 else 0
            },
            message=f"Retrieved {len(account_list)} accounts from organizations"
        )
    except Exception as e:
        logger.error(f"Error listing accounts from organizations: {e}")
        raise DatabaseException("Failed to list accounts")


def _format_time_ago(dt):
    """Format datetime as relative time string"""
    from datetime import datetime, timezone
    if not dt:
        return 'Unknown'

    now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
    diff = now - dt

    seconds = diff.total_seconds()
    if seconds < 60:
        return 'Just now'
    elif seconds < 3600:
        mins = int(seconds // 60)
        return f'{mins} min ago' if mins == 1 else f'{mins} mins ago'
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f'{hours} hour ago' if hours == 1 else f'{hours} hours ago'
    elif seconds < 604800:
        days = int(seconds // 86400)
        return f'{days} day ago' if days == 1 else f'{days} days ago'
    else:
        return dt.strftime('%b %d, %Y')
