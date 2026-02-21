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
import os
import uuid

from database import get_db
from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    success_response
)
from email_service import send_subscription_invite_email
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin/account-management", tags=["Account Management"])


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
        sql = f"DELETE FROM {validated_table} WHERE {where_clause}"
    else:
        sql = f"DELETE FROM {validated_table}"

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
        sql = f"DELETE FROM {validated_table} WHERE {validated_column} {operator}"
    else:
        sql = f"DELETE FROM {validated_table} WHERE {validated_column} {operator} :{param_name}"

    result = db.execute(text(sql), params)
    return result.rowcount

# Will be set by main.py
User = None
get_current_user = None


def set_dependencies(user_model, current_user_func):
    """Set dependencies from main.py"""
    global User, get_current_user
    User = user_model
    get_current_user = current_user_func


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
    except Exception:
        try:
            # Fall back to SQLite syntax
            result = db.execute(text("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name = :table_name
            """), {"table_name": table_name}).scalar()
            return result > 0
        except Exception:
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


# =============================================================================
# Helper Functions
# =============================================================================

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
    return await get_current_user(token, request, db)


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
        count_result = db.execute(text(f"""
            SELECT COUNT(*) FROM organizations o WHERE {where_sql}
        """), params).scalar() or 0

        # Get organizations with user metrics
        query = f"""
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
            WHERE {where_sql}
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


# =============================================================================
# Migration Endpoint
# =============================================================================

@router.post("/run-migration")
async def run_account_management_migration(
    admin_key: str = None,
    action: str = Query(default="migrate", description="Action: migrate or cleanup"),
    keep_admin_email: str = Query(default="admin@perenniaai.com", description="Admin email to preserve (for cleanup action)"),
    db: Session = Depends(get_db)
):
    """Run the account management tables migration, or perform cleanup.

    Actions:
    - migrate: Create account management tables (default)
    - cleanup: Delete all sample data, keeping only specified admin user
    """
    import os

    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Handle cleanup action
    if action == "cleanup":
        # Use fresh connection to avoid pooled connection issues
        from sqlalchemy import create_engine
        database_url = os.getenv("DATABASE_URL", "")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        try:
            engine = create_engine(database_url)
            results = {'deleted': {}, 'errors': [], 'preserved_admin': keep_admin_email}

            # Use autocommit to avoid transaction issues
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                # Delete all tasks (whitelist-validated)
                for table in ['tasks', 'task_instances', 'purl_tasks']:
                    try:
                        validated_table = validate_table_name(table)
                        result = conn.execute(text(f"DELETE FROM {validated_table}"))
                        results['deleted'][table] = result.rowcount
                    except SQLAlchemyError as e:
                        results['errors'].append(f"{table}: cleanup failed")

                # Delete team members/profiles (whitelist-validated)
                for table in ['team_members', 'team_member_profiles', 'extracted_data', 'referral_partners']:
                    try:
                        validated_table = validate_table_name(table)
                        result = conn.execute(text(f"DELETE FROM {validated_table}"))
                        results['deleted'][table] = result.rowcount
                    except Exception:
                        pass

                # Get admin user ID
                admin_row = conn.execute(text("SELECT id FROM users WHERE email = :email"), {'email': keep_admin_email}).fetchone()
                if not admin_row:
                    raise HTTPException(status_code=404, detail=f"Admin {keep_admin_email} not found")
                admin_id = admin_row[0]

                # Delete non-admin users
                users_result = conn.execute(text("SELECT email, full_name, role FROM users WHERE id != :admin_id"), {'admin_id': admin_id})
                results['users_to_delete'] = [{'email': u[0], 'name': u[1], 'role': u[2]} for u in users_result.fetchall()]

                result = conn.execute(text("DELETE FROM users WHERE id != :admin_id"), {'admin_id': admin_id})
                results['deleted']['users'] = result.rowcount

                # Delete suspended/cancelled accounts
                try:
                    result = conn.execute(text("DELETE FROM tenant_accounts WHERE status IN ('suspended', 'canceled')"))
                    results['deleted']['suspended_cancelled_accounts'] = result.rowcount
                except Exception:
                    pass

            total = sum(v for v in results['deleted'].values() if isinstance(v, int))
            return {"status": "success", "message": f"Cleanup done. Deleted {total} rows.", "data": results}
        except HTTPException:
            raise
        except SQLAlchemyError as e:
            raise HTTPException(status_code=500, detail="Cleanup failed")

    # Default: migration action
    try:
        # Check if tables already exist
        if table_exists(db, 'tenant_accounts'):
            return {"status": "success", "message": "Tables already exist"}

        # Create all tables
        migration_sql = """
        -- 1. Tenant Accounts
        CREATE TABLE IF NOT EXISTS tenant_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            domain VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'canceled')),
            plan_id VARCHAR(100),
            plan_name VARCHAR(100),
            billing_interval VARCHAR(20) DEFAULT 'monthly' CHECK (billing_interval IN ('monthly', 'annually')),
            seats_purchased INTEGER DEFAULT 1,
            stripe_customer_id VARCHAR(255),
            stripe_subscription_id VARCHAR(255),
            owner_user_id INTEGER REFERENCES users(id),
            internal_notes TEXT,
            add_ons JSONB DEFAULT '[]',
            settings JSONB DEFAULT '{}',
            suspended_at TIMESTAMP,
            suspended_reason TEXT,
            canceled_at TIMESTAMP,
            canceled_reason TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            is_deleted BOOLEAN DEFAULT false
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_accounts_status ON tenant_accounts(status);
        CREATE INDEX IF NOT EXISTS idx_tenant_accounts_domain ON tenant_accounts(domain);

        -- 2. Account Subscriptions
        CREATE TABLE IF NOT EXISTS account_subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID REFERENCES tenant_accounts(id) ON DELETE CASCADE,
            provider VARCHAR(50) NOT NULL DEFAULT 'stripe',
            provider_subscription_id VARCHAR(255),
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            plan_id VARCHAR(100),
            plan_name VARCHAR(100),
            price_amount NUMERIC(10, 2),
            price_currency VARCHAR(3) DEFAULT 'USD',
            quantity INTEGER DEFAULT 1,
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            cancel_at_period_end BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        -- 3. Subscription Events
        CREATE TABLE IF NOT EXISTS subscription_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID REFERENCES tenant_accounts(id) ON DELETE CASCADE,
            event_type VARCHAR(50) NOT NULL,
            from_plan VARCHAR(100),
            to_plan VARCHAR(100),
            amount NUMERIC(10, 2),
            actor_id INTEGER REFERENCES users(id),
            actor_name VARCHAR(255),
            reason TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- 4. Account Invoices
        CREATE TABLE IF NOT EXISTS account_invoices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID REFERENCES tenant_accounts(id) ON DELETE CASCADE,
            stripe_invoice_id VARCHAR(255),
            invoice_number VARCHAR(100),
            amount NUMERIC(12, 2) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            period_start TIMESTAMP,
            period_end TIMESTAMP,
            due_date TIMESTAMP,
            paid_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- 5. Cost Ledger
        CREATE TABLE IF NOT EXISTS cost_ledger_monthly (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID REFERENCES tenant_accounts(id) ON DELETE CASCADE,
            month VARCHAR(7) NOT NULL,
            cost_category VARCHAR(50) NOT NULL,
            vendor VARCHAR(100),
            amount NUMERIC(12, 4) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- 6. Login Events
        CREATE TABLE IF NOT EXISTS login_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            account_id UUID REFERENCES tenant_accounts(id),
            result VARCHAR(20) NOT NULL DEFAULT 'success',
            ip_address VARCHAR(45),
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- 7. Admin Audit Log
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_admin_id INTEGER NOT NULL REFERENCES users(id),
            actor_name VARCHAR(255),
            action_type VARCHAR(100) NOT NULL,
            target_type VARCHAR(50) NOT NULL,
            target_id VARCHAR(255),
            target_name VARCHAR(255),
            ip_address VARCHAR(45),
            old_values JSONB,
            new_values JSONB,
            reason TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );

        -- 8. Impersonation Sessions
        CREATE TABLE IF NOT EXISTS impersonation_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            admin_user_id INTEGER NOT NULL REFERENCES users(id),
            target_user_id INTEGER NOT NULL REFERENCES users(id),
            account_id UUID REFERENCES tenant_accounts(id),
            reason TEXT NOT NULL,
            started_at TIMESTAMP DEFAULT NOW(),
            ended_at TIMESTAMP,
            is_active BOOLEAN DEFAULT true
        );

        -- Add tenant_account_id to users if not exists
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'tenant_account_id') THEN
                ALTER TABLE users ADD COLUMN tenant_account_id UUID REFERENCES tenant_accounts(id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_activity_at') THEN
                ALTER TABLE users ADD COLUMN last_activity_at TIMESTAMP;
            END IF;
        END $$;
        """

        db.execute(text(migration_sql))
        db.commit()

        return {"status": "success", "message": "Account management tables created successfully"}

    except SQLAlchemyError as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Migration failed")


@router.post("/run-cleanup-migration")
async def run_cleanup_migration(
    admin_key: str = None,
    keep_admin_email: str = Query(default="admin@perenniaai.com"),
    db: Session = Depends(get_db)
):
    """Comprehensive cleanup: Delete ALL sample data including tasks, users, accounts.

    This migration-style endpoint removes:
    - All tasks (tasks, task_instances, purl_tasks)
    - All users except the specified admin email
    - All team members and profiles
    - All suspended and cancelled accounts
    - All account management sample data
    """
    import os

    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        results = {
            'deleted': {},
            'errors': [],
            'preserved_admin': keep_admin_email
        }

        # 1. Delete all tasks (whitelist-validated)
        task_tables = ['tasks', 'task_instances', 'purl_tasks']
        for table in task_tables:
            try:
                rowcount = safe_delete_from_table(db, table)
                results['deleted'][table] = rowcount
                logger.info(f"Cleanup: Deleted {rowcount} rows from {table}")
            except SQLAlchemyError as e:
                logger.error(f"Cleanup error for {table}: {e}")
                results['errors'].append(f"{table}: cleanup failed")

        # 2. Delete team members and profiles (whitelist-validated)
        team_tables = ['team_members', 'team_member_profiles']
        for table in team_tables:
            try:
                rowcount = safe_delete_from_table(db, table)
                results['deleted'][table] = rowcount
            except SQLAlchemyError as e:
                logger.error(f"Cleanup error for {table}: {e}")
                results['errors'].append(f"{table}: cleanup failed")

        # 3. Delete extracted_data (reconciliation)
        try:
            result = db.execute(text("DELETE FROM extracted_data"))
            results['deleted']['extracted_data'] = result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Cleanup error for extracted_data: {e}")
            results['errors'].append("extracted_data: cleanup failed")

        # 4. Delete referral partners
        try:
            result = db.execute(text("DELETE FROM referral_partners"))
            results['deleted']['referral_partners'] = result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Cleanup error for referral_partners: {e}")
            results['errors'].append("referral_partners: cleanup failed")

        # 5. Get admin user ID to preserve
        admin_result = db.execute(text("""
            SELECT id, email, full_name FROM users WHERE email = :admin_email
        """), {'admin_email': keep_admin_email})
        admin_row = admin_result.fetchone()

        if not admin_row:
            raise HTTPException(status_code=404, detail=f"Admin user {keep_admin_email} not found")

        admin_id = admin_row[0]

        # 6. Delete related user data for non-admin users
        user_related_tables = [
            ('user_settings', 'user_id'),
            ('user_notifications', 'user_id'),
            ('loan_officer_profiles', 'user_id'),
            ('conversations', 'user_id'),
            ('ai_conversation_messages', 'user_id'),
            ('onboarding_user_profiles', 'user_id'),
            ('onboarding_user_categories', 'user_id'),
            ('onboarding_user_responsibilities', 'user_id'),
            ('onboarding_user_permissions', 'user_id'),
        ]

        for table, column in user_related_tables:
            try:
                # Whitelist-validated table and column names
                rowcount = safe_delete_with_column_condition(
                    db, table, column, '!=', 'admin_id', {'admin_id': admin_id}
                )
                results['deleted'][table] = rowcount
            except Exception:
                pass  # Skip missing tables

        # 7. List and delete all users except admin
        users_result = db.execute(text("""
            SELECT id, email, full_name, role FROM users WHERE id != :admin_id
        """), {'admin_id': admin_id})
        users_to_delete = users_result.fetchall()
        results['users_deleted_list'] = [
            {'email': u[1], 'name': u[2], 'role': u[3]} for u in users_to_delete
        ]

        result = db.execute(text("""
            DELETE FROM users WHERE id != :admin_id
        """), {'admin_id': admin_id})
        results['deleted']['users'] = result.rowcount

        # 8. Delete suspended and cancelled accounts
        try:
            result = db.execute(text("""
                DELETE FROM tenant_accounts WHERE status IN ('suspended', 'canceled')
            """))
            results['deleted']['suspended_cancelled_accounts'] = result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Cleanup error for tenant_accounts: {e}")
            results['errors'].append("tenant_accounts: cleanup failed")

        # 9. Clean up account management tables (whitelist-validated)
        account_tables = [
            'subscription_events',
            'account_subscriptions',
            'account_invoices',
            'cost_ledger_monthly',
            'usage_events',
            'login_events',
            'admin_audit_log',
            'impersonation_sessions',
            'user_activity_stats',
            'account_kpi_snapshots',
            'account_user_roles',
        ]

        for table in account_tables:
            try:
                rowcount = safe_delete_from_table(db, table)
                if rowcount > 0:
                    results['deleted'][table] = rowcount
            except Exception:
                pass

        db.commit()

        total_deleted = sum(v for v in results['deleted'].values() if isinstance(v, int))
        results['total_rows_deleted'] = total_deleted

        return {
            "status": "success",
            "message": f"Cleanup completed. Deleted {total_deleted} total rows. Admin {keep_admin_email} preserved.",
            "data": results
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Cleanup migration failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Cleanup failed")


@router.post("/run-invitations-migration")
async def run_invitations_migration(
    admin_key: str = None,
    db: Session = Depends(get_db)
):
    """Run the subscriber_invitations table migration."""
    import os

    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        # Check if table already exists
        if table_exists(db, 'subscriber_invitations'):
            return {"status": "success", "message": "subscriber_invitations table already exists"}

        # Create subscriber_invitations table
        migration_sql = """
        CREATE TABLE subscriber_invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            token VARCHAR(255) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL,
            company_name VARCHAR(255) NOT NULL,
            contact_name VARCHAR(255),
            plan VARCHAR(100) NOT NULL DEFAULT 'professional',
            seats INTEGER NOT NULL DEFAULT 5,
            promo_code VARCHAR(50),
            personal_message TEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'expired', 'revoked')),
            invited_by INTEGER REFERENCES users(id),
            invited_by_name VARCHAR(255),
            expires_at TIMESTAMP NOT NULL,
            accepted_at TIMESTAMP,
            accepted_by_user_id INTEGER REFERENCES users(id),
            revoked_at TIMESTAMP,
            revoked_by INTEGER REFERENCES users(id),
            ip_address VARCHAR(45),
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_sub_invites_token ON subscriber_invitations(token);
        CREATE INDEX idx_sub_invites_email ON subscriber_invitations(email);
        CREATE INDEX idx_sub_invites_status ON subscriber_invitations(status);
        CREATE INDEX idx_sub_invites_expires ON subscriber_invitations(expires_at);
        CREATE INDEX idx_sub_invites_created ON subscriber_invitations(created_at);
        """

        db.execute(text(migration_sql))
        db.commit()

        return {"status": "success", "message": "subscriber_invitations table created successfully"}

    except SQLAlchemyError as e:
        logger.error(f"Invitations migration failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Migration failed")


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
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Check if tenant_accounts table exists
        if not table_exists(db, 'tenant_accounts'):
            # Calculate KPIs from organizations table instead
            return await _get_kpis_from_organizations(db)

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
            AND is_active = true
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
        raise DatabaseException("Failed to retrieve KPIs")


# =============================================================================
# Invitation Endpoints
# =============================================================================

class InviteSubscriberRequest(BaseModel):
    """Request to invite a new subscriber"""
    email: str = Field(..., description="Email address to invite")
    company_name: str = Field(..., description="Company/organization name")
    contact_name: Optional[str] = Field(None, description="Contact person name")
    plan: str = Field('professional', description="Subscription plan")
    seats: int = Field(5, ge=1, le=1000, description="Initial seat count")
    message: Optional[str] = Field(None, max_length=2000, description="Personal message")
    promo_code: Optional[str] = Field(None, max_length=50, description="Promo code for special pricing")


@router.post("/invite")
async def invite_subscriber(
    request: Request,
    invite: InviteSubscriberRequest,
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
        count_result = db.execute(text(f"""
            SELECT COUNT(*) as total
            FROM subscriber_invitations
            WHERE status = 'pending' {search_filter}
        """), params).fetchone()
        total = count_result.total if count_result else 0

        # Get invitations
        invitations = db.execute(text(f"""
            SELECT id, token, email, company_name, contact_name, plan, seats,
                   promo_code, status, invited_by_name, expires_at, created_at
            FROM subscriber_invitations
            WHERE status = 'pending' {search_filter}
            ORDER BY created_at DESC
            OFFSET :offset LIMIT :limit
        """), params).fetchall()

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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
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
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Use organizations table if tenant_accounts doesn't exist
        if not table_exists(db, 'tenant_accounts'):
            # Fall back to organizations table
            return await _list_accounts_from_organizations(db, status, search, page, limit, sort, order)

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
        raise DatabaseException("Failed to list accounts")


@router.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get detailed account information"""
    try:
        current_user = await get_user_from_request(request, db)
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
        raise DatabaseException("Failed to get account")


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
        current_user = await get_user_from_request(request, db)
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
    except SQLAlchemyError as e:
        logger.error(f"Error suspending account: {e}")
        db.rollback()
        raise DatabaseException("Failed to suspend account")


@router.post("/accounts/{account_id}/reinstate")
async def reinstate_account(
    account_id: str,
    action: AccountActionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Reinstate a suspended account"""
    try:
        current_user = await get_user_from_request(request, db)
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
    except SQLAlchemyError as e:
        logger.error(f"Error reinstating account: {e}")
        db.rollback()
        raise DatabaseException("Failed to reinstate account")


@router.post("/accounts/{account_id}/cancel")
async def cancel_account(
    account_id: str,
    action: AccountActionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Cancel an account (soft cancel)"""
    try:
        current_user = await get_user_from_request(request, db)
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
    except SQLAlchemyError as e:
        logger.error(f"Error canceling account: {e}")
        db.rollback()
        raise DatabaseException("Failed to cancel account")


@router.put("/accounts/{account_id}/notes")
async def update_notes(
    account_id: str,
    notes: InternalNotesRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update internal notes for an account"""
    try:
        current_user = await get_user_from_request(request, db)
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
    except SQLAlchemyError as e:
        logger.error(f"Error updating notes: {e}")
        db.rollback()
        raise DatabaseException("Failed to update notes")


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Permanently delete an account and all associated data"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Get account info for logging
        account = db.execute(text("""
            SELECT name, status FROM tenant_accounts
            WHERE id = :account_id AND is_deleted = false
        """), {'account_id': account_id}).fetchone()

        if not account:
            raise NotFoundException(f"Account {account_id} not found")

        account_name = account[0]

        # Get user IDs for this account
        user_rows = db.execute(text("""
            SELECT id FROM users WHERE tenant_account_id = :account_id
        """), {'account_id': account_id}).fetchall()
        user_ids = [row[0] for row in user_rows]

        if user_ids:
            # Delete all FK-dependent records for these users.
            # Use a comprehensive list of tables that reference users.id.
            # Tables with ondelete=CASCADE are handled automatically by the DB.
            dependent_tables = [
                # Permission / role tables
                ("user_assigned_roles", "user_id"),
                ("user_active_role", "user_id"),
                ("user_permissions", "user_id"),
                ("user_page_permissions", "user_id"),
                ("permission_requests", "employee_id"),
                ("permissions", "user_id"),
                # Auth / security
                ("api_keys", "user_id"),
                ("refresh_tokens", "user_id"),
                ("revoked_tokens", "user_id"),
                ("revoked_tokens", "revoked_by_id"),
                ("security_certifications", "employee_id"),
                ("microsoft_oauth_tokens", "user_id"),
                ("microsoft_credentials", "user_id"),
                ("audit_logs", "user_id"),
                ("audit_logs", "changed_by_id"),
                # Subscription / billing
                ("subscription_plans", "user_id"),
                ("account_subscriptions", "user_id"),
                # Communication
                ("email_tracking", "user_id"),
                ("sms_messages", "user_id"),
                ("call_logs", "user_id"),
                ("voicemail_drops", "user_id"),
                ("user_email_connections", "user_id"),
                # Tasks / workflow
                ("tasks", "assigned_to_id"),
                ("tasks", "owner_id"),
                ("workflow_tasks", "user_id"),
                # AI / chat
                ("ai_chat_sessions", "user_id"),
                ("ai_audit_logs", "user_id"),
                # Dialer
                ("dialer_sessions", "user_id"),
                ("dialer_agents", "agent_id"),
                # Core / settings
                ("user_settings", "user_id"),
                ("notification_preferences", "user_id"),
                ("impersonation_sessions", "manager_id"),
                ("impersonation_sessions", "impersonated_user_id"),
                # Invitations
                ("employee_invites", "invited_by_user_id"),
                ("employee_invites", "user_id"),
                ("subscriber_invitations", "accepted_by_user_id"),
            ]

            for table_name, column_name in dependent_tables:
                try:
                    db.execute(text(f"""
                        DELETE FROM {table_name} WHERE {column_name} IN :user_ids
                    """), {'user_ids': tuple(user_ids)})
                except Exception:
                    pass  # Table may not exist yet or column may differ

            # Also clean up tenant-level records
            try:
                db.execute(text("""
                    DELETE FROM user_invitations WHERE organization_id = :account_id
                """), {'account_id': account_id})
            except Exception:
                pass

        # Delete associated users
        db.execute(text("""
            DELETE FROM users WHERE tenant_account_id = :account_id
        """), {'account_id': account_id})

        # Soft delete the account
        db.execute(text("""
            UPDATE tenant_accounts
            SET is_deleted = true,
                status = 'deleted',
                updated_at = NOW()
            WHERE id = :account_id
        """), {'account_id': account_id})

        db.commit()

        log_admin_action(db, current_user, 'account.deleted', 'account',
                        account_id, account_name, request=request)

        return success_response(
            data={'account_id': account_id, 'name': account_name},
            message=f"Account '{account_name}' deleted successfully"
        )
    except (PermissionException, NotFoundException):
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error deleting account {account_id}: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to delete account: {str(e)[:200]}")


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
        current_user = await get_user_from_request(request, db)
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
            WHERE u.tenant_account_id = :account_id
            ORDER BY u.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {'account_id': account_id, 'limit': limit, 'offset': (page - 1) * limit}).fetchall()

        total = db.execute(text("""
            SELECT COUNT(*) FROM users
            WHERE tenant_account_id = :account_id
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
        raise DatabaseException("Failed to list users")


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
        current_user = await get_user_from_request(request, db)
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
            WHERE u.id = :user_id
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
        raise DatabaseException("Failed to get user")


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
        current_user = await get_user_from_request(request, db)
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
        raise DatabaseException("Failed to get login history")


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: str,
    action: UserActionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Disable a user"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        user = db.execute(text("""
            SELECT id, full_name, email, is_active FROM users
            WHERE id = :user_id
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
    except SQLAlchemyError as e:
        logger.error(f"Error disabling user: {e}")
        db.rollback()
        raise DatabaseException("Failed to disable user")


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Enable a disabled user"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        user = db.execute(text("""
            SELECT id, full_name, email, is_active FROM users
            WHERE id = :user_id
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
    except SQLAlchemyError as e:
        logger.error(f"Error enabling user: {e}")
        db.rollback()
        raise DatabaseException("Failed to enable user")


@router.put("/users/{user_id}/roles")
async def update_user_roles(
    user_id: str,
    roles: RoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update user roles"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        user = db.execute(text("""
            SELECT id, full_name, email, role FROM users
            WHERE id = :user_id
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
    except SQLAlchemyError as e:
        logger.error(f"Error updating roles: {e}")
        db.rollback()
        raise DatabaseException("Failed to update roles")


# =============================================================================
# User Permissions
# =============================================================================

class UserPermissionsRequest(BaseModel):
    """Request to update user permissions"""
    permissions: Dict[str, Dict[str, bool]] = Field(..., description="Page permissions map")


@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get page-level permissions for a user"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Verify user exists
        user = db.execute(text("""
            SELECT id, full_name, email, role FROM users
            WHERE id = :user_id
        """), {'user_id': user_id}).fetchone()

        if not user:
            raise NotFoundException(f"User {user_id} not found")

        # Ensure user_permissions table exists
        if not table_exists(db, 'user_permissions'):
            # Create the table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS user_permissions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    page_id VARCHAR(100) NOT NULL,
                    can_view BOOLEAN DEFAULT false,
                    can_create BOOLEAN DEFAULT false,
                    can_edit BOOLEAN DEFAULT false,
                    can_delete BOOLEAN DEFAULT false,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, page_id)
                );
                CREATE INDEX IF NOT EXISTS idx_user_permissions_user_id ON user_permissions(user_id);
            """))
            db.commit()

        # Get permissions
        permissions_result = db.execute(text("""
            SELECT page_id, can_view, can_create, can_edit, can_delete
            FROM user_permissions
            WHERE user_id = :user_id
        """), {'user_id': user_id}).fetchall()

        # Format as dict
        permissions = {}
        for row in permissions_result:
            permissions[row[0]] = {
                'view': row[1] or False,
                'create': row[2] or False,
                'edit': row[3] or False,
                'delete': row[4] or False
            }

        # If no custom permissions, return default based on role
        if not permissions:
            is_admin = user[3] in ('admin', 'master_admin', 'Admin')
            default_pages = [
                'dashboard', 'leads', 'active_loans', 'portfolio', 'tasks', 'calendar',
                'marketing', 'smart_docs', 'partners', 'scorecard', 'profitability',
                'market', 'ai_underwriter', 'ai_daily_blog', 'conversation_intelligence',
                'settings', 'team_management', 'recruiting', 'capacity'
            ]
            for page in default_pages:
                permissions[page] = {
                    'view': True,
                    'create': is_admin,
                    'edit': is_admin,
                    'delete': is_admin
                }

        return success_response(
            data={
                'userId': user_id,
                'userName': user[1] or user[2],
                'role': user[3],
                'permissions': permissions
            },
            message="Permissions retrieved successfully"
        )
    except (PermissionException, NotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error getting user permissions: {e}")
        raise DatabaseException("Failed to get user permissions")


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: str,
    permissions_request: UserPermissionsRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update page-level permissions for a user"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Verify user exists
        user = db.execute(text("""
            SELECT id, full_name, email FROM users
            WHERE id = :user_id
        """), {'user_id': user_id}).fetchone()

        if not user:
            raise NotFoundException(f"User {user_id} not found")

        # Ensure table exists
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                page_id VARCHAR(100) NOT NULL,
                can_view BOOLEAN DEFAULT false,
                can_create BOOLEAN DEFAULT false,
                can_edit BOOLEAN DEFAULT false,
                can_delete BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, page_id)
            )
        """))

        # Get old permissions for audit log
        old_permissions = {}
        old_result = db.execute(text("""
            SELECT page_id, can_view, can_create, can_edit, can_delete
            FROM user_permissions WHERE user_id = :user_id
        """), {'user_id': user_id}).fetchall()
        for row in old_result:
            old_permissions[row[0]] = {
                'view': row[1], 'create': row[2], 'edit': row[3], 'delete': row[4]
            }

        # Delete existing permissions
        db.execute(text("""
            DELETE FROM user_permissions WHERE user_id = :user_id
        """), {'user_id': user_id})

        # Insert new permissions
        for page_id, perms in permissions_request.permissions.items():
            db.execute(text("""
                INSERT INTO user_permissions (user_id, page_id, can_view, can_create, can_edit, can_delete)
                VALUES (:user_id, :page_id, :can_view, :can_create, :can_edit, :can_delete)
            """), {
                'user_id': user_id,
                'page_id': page_id,
                'can_view': perms.get('view', False),
                'can_create': perms.get('create', False),
                'can_edit': perms.get('edit', False),
                'can_delete': perms.get('delete', False)
            })

        db.commit()

        # Log the action
        log_admin_action(
            db, current_user, 'user.permissions_updated', 'user',
            user_id, user[1] or user[2],
            old_values={'permissions': old_permissions},
            new_values={'permissions': permissions_request.permissions},
            request=request
        )

        return success_response(
            data={
                'userId': user_id,
                'permissions': permissions_request.permissions,
                'pagesUpdated': len(permissions_request.permissions)
            },
            message=f"Permissions updated for '{user[1] or user[2]}'"
        )
    except (PermissionException, NotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error updating user permissions: {e}")
        db.rollback()
        raise DatabaseException("Failed to update user permissions")


# =============================================================================
# Permissions Table Migration
# =============================================================================

@router.post("/migrate-permissions-table")
async def migrate_permissions_table(
    request: Request,
    db: Session = Depends(get_db)
):
    """Migrate/recreate user_permissions table with correct schema"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Check if table exists and its structure
        table_info = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'user_permissions'
        """)).fetchall()

        columns = [row[0] for row in table_info] if table_info else []

        if 'page_id' not in columns:
            # Table exists but with wrong structure - drop and recreate
            db.execute(text("DROP TABLE IF EXISTS user_permissions CASCADE"))

            # Create with correct schema
            db.execute(text("""
                CREATE TABLE user_permissions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    page_id VARCHAR(100) NOT NULL,
                    can_view BOOLEAN DEFAULT false,
                    can_create BOOLEAN DEFAULT false,
                    can_edit BOOLEAN DEFAULT false,
                    can_delete BOOLEAN DEFAULT false,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, page_id)
                )
            """))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_permissions_user_id ON user_permissions(user_id)"))
            db.commit()

            return success_response(
                data={'action': 'recreated', 'old_columns': columns},
                message="User permissions table recreated with correct schema"
            )
        else:
            return success_response(
                data={'action': 'no_change', 'columns': columns},
                message="User permissions table already has correct schema"
            )
    except (PermissionException, NotFoundException):
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error migrating permissions table: {e}")
        db.rollback()
        raise DatabaseException("Failed to migrate permissions table")


# =============================================================================
# Impersonation
# =============================================================================

@router.post("/impersonate/start")
async def start_impersonation(
    imp_request: ImpersonationRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Start impersonating a user - generates a real JWT for the target user"""
    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Convert user_id to integer for database query
        try:
            user_id_int = int(imp_request.user_id)
        except (ValueError, TypeError):
            raise ValidationException(f"Invalid user_id: {imp_request.user_id}")

        target_user = db.execute(text("""
            SELECT id, full_name, email, tenant_account_id, role, permission_role
            FROM users
            WHERE id = :user_id
        """), {'user_id': user_id_int}).fetchone()

        if not target_user:
            raise NotFoundException(f"User {imp_request.user_id} not found")

        # Generate a real JWT token for the target user
        import secrets
        import jwt
        from datetime import datetime, timedelta, timezone
        import os

        SECRET_KEY = os.getenv("SECRET_KEY", "")
        ALGORITHM = "HS256"

        # Create token data for the target user
        token_data = {
            "sub": target_user[2],  # email
            "user_id": target_user[0],  # id
            "impersonated_by": current_user.id,  # track who is impersonating
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)  # 1 hour expiry for preview
        }

        # Generate the JWT
        access_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

        target_name = target_user[1] or target_user[2] or f"User {target_user[0]}"
        target_role = target_user[4] or target_user[5] or "user"

        return success_response(
            data={
                'sessionId': f"preview_{user_id_int}_{secrets.token_hex(4)}",
                'sessionToken': access_token,  # This is now a real JWT
                'token': access_token,  # Also provide as 'token' for compatibility
                'targetUserId': str(target_user[0]),
                'targetUserName': target_name,
                'targetUserRole': target_role,
            },
            message=f"Impersonation started for '{target_name}'"
        )
    except (PermissionException, NotFoundException, ValidationException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error starting impersonation: {e}")
        db.rollback()
        raise DatabaseException("Failed to start impersonation")


@router.post("/impersonate/stop")
async def stop_impersonation(
    request: Request,
    db: Session = Depends(get_db)
):
    """Stop impersonation session"""
    try:
        current_user = await get_user_from_request(request, db)
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
    except SQLAlchemyError as e:
        logger.error(f"Error stopping impersonation: {e}")
        db.rollback()
        raise DatabaseException("Failed to stop impersonation")


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
        current_user = await get_user_from_request(request, db)
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
        raise DatabaseException("Failed to get invoices")


@router.get("/accounts/{account_id}/cost-breakdown")
async def get_cost_breakdown(
    account_id: str,
    request: Request,
    month: Optional[str] = Query(None, description="Month in YYYY-MM format"),
    db: Session = Depends(get_db)
):
    """Get cost breakdown for an account"""
    try:
        current_user = await get_user_from_request(request, db)
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
        raise DatabaseException("Failed to get cost breakdown")


@router.get("/accounts/{account_id}/cost-trend")
async def get_cost_trend(
    account_id: str,
    request: Request,
    months: int = Query(6, ge=1, le=24, description="Number of months"),
    db: Session = Depends(get_db)
):
    """Get cost trend for an account"""
    try:
        current_user = await get_user_from_request(request, db)
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
        raise DatabaseException("Failed to get cost trend")


@router.get("/accounts/{account_id}/subscription-timeline")
async def get_subscription_timeline(
    account_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get subscription event timeline for an account"""
    try:
        current_user = await get_user_from_request(request, db)
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
        raise DatabaseException("Failed to get timeline")


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
        current_user = await get_user_from_request(request, db)
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
        raise DatabaseException("Failed to get audit log")


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
        current_user = await get_user_from_request(request, db)
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
        raise DatabaseException("Failed to get audit log")


@router.get("/security-audit-log")
async def get_security_audit_log(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    action_type: str = Query(None, description="Filter by action type"),
    db: Session = Depends(get_db)
):
    """Get general security audit log for the security dashboard"""
    try:
        current_user = await get_user_from_request(request, db)

        # Build query with optional filter
        query = """
            SELECT id, actor_admin_id, actor_name, action_type, target_type, target_id,
                   target_name, ip_address, old_values, new_values, reason, created_at
            FROM admin_audit_log
            WHERE 1=1
        """
        params = {'limit': limit, 'offset': (page - 1) * limit}

        if action_type:
            query += " AND action_type = :action_type"
            params['action_type'] = action_type

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        logs = db.execute(text(query), params).fetchall()

        # Get total count for pagination
        count_query = "SELECT COUNT(*) FROM admin_audit_log"
        if action_type:
            count_query += " WHERE action_type = :action_type"
        total = db.execute(text(count_query), {'action_type': action_type} if action_type else {}).scalar()

        audit_list = []
        for log in logs:
            # Map action types to user-friendly event names
            action_map = {
                'user_login': 'User Login',
                'user_logout': 'User Logout',
                'user_created': 'User Created',
                'user_updated': 'User Updated',
                'user_deleted': 'User Deleted',
                'user_disabled': 'User Disabled',
                'user_enabled': 'User Enabled',
                'permission_changed': 'Permission Changed',
                'role_changed': 'Role Changed',
                'password_reset': 'Password Reset',
                'password_changed': 'Password Changed',
                '2fa_enabled': '2FA Enabled',
                '2fa_disabled': '2FA Disabled',
                'api_key_created': 'API Key Generated',
                'api_key_revoked': 'API Key Revoked',
                'data_export': 'Data Export',
                'data_import': 'Data Import',
                'account_suspended': 'Account Suspended',
                'account_reinstated': 'Account Reinstated',
                'impersonation_started': 'Impersonation Started',
                'impersonation_ended': 'Impersonation Ended',
                'settings_changed': 'Settings Changed',
                'invite_sent': 'Invite Sent',
            }

            # Map to status badges
            status_map = {
                'user_login': 'Success',
                'user_logout': 'Success',
                'user_created': 'Created',
                'user_updated': 'Modified',
                'user_deleted': 'Deleted',
                'user_disabled': 'Disabled',
                'user_enabled': 'Enabled',
                'permission_changed': 'Modified',
                'role_changed': 'Modified',
                'password_reset': 'Reset',
                'password_changed': 'Changed',
                '2fa_enabled': 'Enabled',
                '2fa_disabled': 'Disabled',
                'api_key_created': 'Created',
                'api_key_revoked': 'Revoked',
                'data_export': 'Completed',
                'data_import': 'Completed',
                'account_suspended': 'Suspended',
                'account_reinstated': 'Reinstated',
                'impersonation_started': 'Started',
                'impersonation_ended': 'Ended',
                'settings_changed': 'Modified',
                'invite_sent': 'Sent',
            }

            action_type_raw = log[3] or 'unknown'

            audit_list.append({
                'id': str(log[0]),
                'actorId': log[1],
                'actorName': log[2] or 'System',
                'actionType': action_type_raw,
                'event': action_map.get(action_type_raw, action_type_raw.replace('_', ' ').title()),
                'targetType': log[4],
                'targetId': log[5],
                'targetName': log[6],
                'ipAddress': log[7] or 'N/A',
                'oldValues': log[8],
                'newValues': log[9],
                'reason': log[10],
                'status': status_map.get(action_type_raw, 'Info'),
                'timestamp': log[11].isoformat() if log[11] else None,
                'timeAgo': _format_time_ago(log[11]) if log[11] else 'Unknown'
            })

        return success_response(
            data={
                'logs': audit_list,
                'page': page,
                'limit': limit,
                'total': total,
                'totalPages': (total + limit - 1) // limit if total else 0
            },
            message=f"Retrieved {len(audit_list)} security audit entries"
        )
    except PermissionException:
        raise
    except Exception as e:
        logger.error(f"Error getting security audit log: {e}")
        raise DatabaseException("Failed to get security audit log")


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


# =============================================================================
# Data Cleanup Endpoints
# =============================================================================

@router.delete("/cleanup/sample-data")
async def cleanup_sample_data(
    request: Request,
    admin_key: str = Query(default=None, description="Admin API key for auth bypass"),
    db: Session = Depends(get_db)
):
    """Delete all sample/demo data from account management tables.
    Can be called with admin_key query param to bypass JWT authentication.
    """
    import os

    # Check for admin key bypass
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key and admin_key == expected_key:
        logger.info("Cleanup authorized via admin API key")
    else:
        try:
            current_user = await get_user_from_request(request, db)
            require_master_admin(current_user)
        except Exception:
            if not admin_key:
                raise HTTPException(status_code=401, detail="Auth required. Provide admin_key or JWT token.")
            raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        deleted_counts = {}

        # Delete in order to respect foreign key constraints
        # Use TRUNCATE CASCADE for faster deletion with FK handling
        tables_to_clean = [
            'subscription_events',
            'account_subscriptions',
            'account_invoices',
            'cost_ledger_monthly',
            'usage_events',
            'login_events',
            'admin_audit_log',
            'impersonation_sessions',
            'user_activity_stats',
            'account_kpi_snapshots',
            'account_user_roles',
            'subscriber_invitations',
            'tenant_accounts'
        ]

        # First, try to truncate tenant_accounts with CASCADE to handle all FKs
        try:
            db.execute(text("TRUNCATE TABLE tenant_accounts CASCADE"))
            db.commit()
            deleted_counts['tenant_accounts_cascade'] = 'truncated with cascade'
            logger.info("Truncated tenant_accounts with CASCADE")
        except SQLAlchemyError as e:
            db.rollback()
            logger.warning(f"CASCADE truncate failed, trying individual deletes: {e}")

            # Fall back to individual table deletes (whitelist-validated)
            for table in tables_to_clean:
                try:
                    # Start fresh for each table - use safe delete
                    rowcount = safe_delete_from_table(db, table)
                    db.commit()
                    deleted_counts[table] = rowcount
                    logger.info(f"Deleted {rowcount} rows from {table}")
                except Exception as table_e:
                    db.rollback()
                    logger.warning(f"Could not delete from {table}: {table_e}")
                    deleted_counts[table] = f"skipped"

        return success_response(
            data={
                'deleted_counts': deleted_counts,
                'tables_cleaned': len([k for k, v in deleted_counts.items() if isinstance(v, int) or v == 'truncated with cascade'])
            },
            message="Sample data cleanup completed"
        )
    except PermissionException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error cleaning up sample data: {e}")
        db.rollback()
        raise DatabaseException("Failed to cleanup sample data")


@router.delete("/cleanup/users")
async def cleanup_users(
    request: Request,
    admin_key: str = Query(default=None, description="Admin API key for auth bypass"),
    keep_admin_email: str = Query(default="admin@perenniaai.com", description="Admin email to preserve"),
    db: Session = Depends(get_db)
):
    """Delete all users except the specified admin user.
    Can be called with admin_key query param to bypass JWT authentication.
    """
    import os

    admin_id = None

    # Check for admin key bypass
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key and admin_key == expected_key:
        logger.info("User cleanup authorized via admin API key")
        # Find admin user by email
        admin_result = db.execute(text("""
            SELECT id, email FROM users WHERE email = :email
        """), {'email': keep_admin_email})
        admin_row = admin_result.fetchone()
        if admin_row:
            admin_id = admin_row[0]
        else:
            raise HTTPException(status_code=404, detail=f"Admin user {keep_admin_email} not found")
    else:
        try:
            current_user = await get_user_from_request(request, db)
            require_master_admin(current_user)
            admin_id = current_user.id
        except Exception:
            if not admin_key:
                raise HTTPException(status_code=401, detail="Auth required. Provide admin_key or JWT token.")
            raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        deleted_counts = {}

        # First, delete from tables that reference users
        related_tables = [
            ('user_settings', 'user_id'),
            ('user_notifications', 'user_id'),
            ('user_invitations', 'invited_by'),
            ('loan_officer_profiles', 'user_id'),
            ('conversations', 'user_id'),
            ('ai_conversation_messages', 'user_id'),
            ('subscriber_invitations', 'invited_by'),
            ('subscriber_invitations', 'accepted_by_user_id'),
            ('subscriber_invitations', 'revoked_by'),
            ('admin_audit_log', 'actor_admin_id'),
            ('login_events', 'user_id'),
            ('user_activity_stats', 'user_id'),
        ]

        for table, column in related_tables:
            try:
                # Whitelist-validated table and column names
                validated_table = validate_table_name(table)
                validated_column = validate_column_name(column)
                result = db.execute(text(f"""
                    DELETE FROM {validated_table}
                    WHERE {validated_column} IS NOT NULL AND {validated_column} != :admin_id
                """), {'admin_id': admin_id})
                deleted_counts[f"{table}.{column}"] = result.rowcount
            except SQLAlchemyError as e:
                logger.warning(f"Could not clean {table}.{column}: {e}")
                deleted_counts[f"{table}.{column}"] = "skipped: cleanup failed"

        # Also delete team_members and team_member_profiles (whitelist-validated)
        for table in ['team_members', 'team_member_profiles']:
            try:
                rowcount = safe_delete_from_table(db, table)
                deleted_counts[table] = rowcount
            except SQLAlchemyError as e:
                logger.warning(f"Could not delete from {table}: {e}")

        # Delete all tasks (whitelist-validated)
        for table in ['tasks', 'task_instances', 'purl_tasks']:
            try:
                rowcount = safe_delete_from_table(db, table)
                deleted_counts[table] = rowcount
            except SQLAlchemyError as e:
                logger.warning(f"Could not delete from {table}: {e}")

        # Now delete all users except the preserved admin
        result = db.execute(text("""
            DELETE FROM users WHERE id != :admin_id
        """), {'admin_id': admin_id})
        deleted_counts['users'] = result.rowcount

        db.commit()

        return success_response(
            data={
                'deleted_counts': deleted_counts,
                'preserved_admin': {
                    'id': admin_id,
                    'email': keep_admin_email
                }
            },
            message=f"Deleted {deleted_counts.get('users', 0)} users. Admin account preserved."
        )
    except PermissionException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning up users: {e}")
        db.rollback()
        raise DatabaseException("Failed to cleanup users")


@router.delete("/cleanup/all-sample-data")
async def cleanup_all_sample_data(
    request: Request,
    keep_admin_email: str = Query(default="admin@perenniaai.com", description="Admin email to preserve"),
    admin_key: str = Query(default=None, description="Admin API key for authentication bypass"),
    db: Session = Depends(get_db)
):
    """Comprehensive cleanup: Delete ALL sample data including tasks, users, accounts.

    This endpoint removes:
    - All tasks (tasks, task_instances, purl_tasks)
    - All users except the specified admin email
    - All team members and profiles
    - All suspended and cancelled accounts
    - All account management sample data

    Can be called with admin_key query param to bypass JWT authentication.
    """
    import os

    # Check for admin key bypass
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key and admin_key == expected_key:
        logger.info("Cleanup authorized via admin API key")
    else:
        # Fall back to JWT authentication
        try:
            current_user = await get_user_from_request(request, db)
            require_master_admin(current_user)
        except Exception as auth_error:
            if not admin_key:
                raise HTTPException(status_code=401, detail="Authentication required. Provide admin_key or valid JWT token.")
            raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        results = {
            'deleted': {},
            'errors': [],
            'preserved_admin': keep_admin_email
        }

        # 1. Delete all tasks (whitelist-validated)
        task_tables = ['tasks', 'task_instances', 'purl_tasks']
        for table in task_tables:
            try:
                rowcount = safe_delete_from_table(db, table)
                results['deleted'][table] = rowcount
                logger.info(f"Deleted {rowcount} rows from {table}")
            except SQLAlchemyError as e:
                logger.warning(f"Could not delete from {table}: {e}")
                results['errors'].append(f"{table}: cleanup failed")

        # 2. Delete team members and profiles (whitelist-validated)
        team_tables = ['team_members', 'team_member_profiles']
        for table in team_tables:
            try:
                rowcount = safe_delete_from_table(db, table)
                results['deleted'][table] = rowcount
            except SQLAlchemyError as e:
                logger.error(f"Cleanup error for {table}: {e}")
                results['errors'].append(f"{table}: cleanup failed")

        # 3. Delete extracted_data (reconciliation)
        try:
            result = db.execute(text("DELETE FROM extracted_data"))
            results['deleted']['extracted_data'] = result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Cleanup error for extracted_data: {e}")
            results['errors'].append("extracted_data: cleanup failed")

        # 4. Delete referral partners
        try:
            result = db.execute(text("DELETE FROM referral_partners"))
            results['deleted']['referral_partners'] = result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Cleanup error for referral_partners: {e}")
            results['errors'].append("referral_partners: cleanup failed")

        # 5. Delete workflow instances
        try:
            result = db.execute(text("DELETE FROM workflow_instances"))
            results['deleted']['workflow_instances'] = result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Cleanup error for workflow_instances: {e}")
            results['errors'].append("workflow_instances: cleanup failed")

        # 6. Get admin user ID to preserve
        admin_result = db.execute(text("""
            SELECT id, email, full_name FROM users WHERE email = :admin_email
        """), {'admin_email': keep_admin_email})
        admin_row = admin_result.fetchone()

        if not admin_row:
            # If admin doesn't exist, use current user
            admin_id = current_user.id
            results['preserved_admin'] = current_user.email
        else:
            admin_id = admin_row[0]
            results['preserved_admin'] = admin_row[1]

        # 7. Delete related user data for non-admin users
        user_related_tables = [
            ('user_settings', 'user_id'),
            ('user_notifications', 'user_id'),
            ('loan_officer_profiles', 'user_id'),
            ('conversations', 'user_id'),
            ('ai_conversation_messages', 'user_id'),
            ('onboarding_user_profiles', 'user_id'),
            ('onboarding_user_categories', 'user_id'),
            ('onboarding_user_responsibilities', 'user_id'),
            ('onboarding_user_permissions', 'user_id'),
        ]

        for table, column in user_related_tables:
            try:
                # Whitelist-validated table and column names
                rowcount = safe_delete_with_column_condition(
                    db, table, column, '!=', 'admin_id', {'admin_id': admin_id}
                )
                results['deleted'][f'{table}'] = rowcount
            except SQLAlchemyError as e:
                pass  # Silently skip missing tables

        # 8. Delete all users except admin
        try:
            # First list users to be deleted
            users_result = db.execute(text("""
                SELECT id, email, full_name, role FROM users WHERE id != :admin_id
            """), {'admin_id': admin_id})
            users_to_delete = users_result.fetchall()
            results['users_deleted_list'] = [
                {'email': u[1], 'name': u[2], 'role': u[3]} for u in users_to_delete
            ]

            result = db.execute(text("""
                DELETE FROM users WHERE id != :admin_id
            """), {'admin_id': admin_id})
            results['deleted']['users'] = result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Cleanup error for users: {e}")
            results['errors'].append("users: cleanup failed")

        # 9. Delete suspended and cancelled accounts
        try:
            result = db.execute(text("""
                DELETE FROM tenant_accounts WHERE status IN ('suspended', 'canceled')
            """))
            results['deleted']['suspended_cancelled_accounts'] = result.rowcount
        except SQLAlchemyError as e:
            logger.error(f"Cleanup error for tenant_accounts: {e}")
            results['errors'].append("tenant_accounts: cleanup failed")

        # 10. Clean up account management tables (whitelist-validated)
        account_tables = [
            'subscription_events',
            'account_subscriptions',
            'account_invoices',
            'cost_ledger_monthly',
            'usage_events',
            'login_events',
            'admin_audit_log',
            'impersonation_sessions',
            'user_activity_stats',
            'account_kpi_snapshots',
            'account_user_roles',
        ]

        for table in account_tables:
            try:
                rowcount = safe_delete_from_table(db, table)
                if rowcount > 0:
                    results['deleted'][table] = rowcount
            except Exception:
                pass

        db.commit()

        # Calculate totals
        total_deleted = sum(v for v in results['deleted'].values() if isinstance(v, int))
        results['total_rows_deleted'] = total_deleted

        return success_response(
            data=results,
            message=f"Comprehensive cleanup completed. Deleted {total_deleted} total rows. Admin {results['preserved_admin']} preserved."
        )

    except PermissionException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error in comprehensive cleanup: {e}")
        db.rollback()
        raise DatabaseException("Failed to cleanup")


@router.post("/emergency-admin-reset")
async def emergency_admin_reset(
    request: Request,
    email: str = Query(..., description="Admin email address"),
    password: str = Query(..., description="New password"),
    secret_key: str = Query(..., description="Emergency reset key"),
    db: Session = Depends(get_db)
):
    """Emergency endpoint to create or reset admin user password.
    Requires secret key for security.
    """
    import os
    import bcrypt

    # Verify secret key
    expected_key = os.getenv("EMERGENCY_ADMIN_KEY", "")
    if secret_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid secret key")

    try:
        # Hash the new password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

        # Check if user exists
        existing_user = db.execute(text("""
            SELECT id, email FROM users WHERE email = :email
        """), {'email': email}).fetchone()

        if existing_user:
            # Update existing user's password and ensure admin role
            db.execute(text("""
                UPDATE users
                SET hashed_password = :password,
                    role = 'admin',
                    permission_role = 'admin',
                    is_active = true,
                    updated_at = NOW()
                WHERE email = :email
            """), {'email': email, 'password': hashed_password})

            db.commit()

            return success_response(
                data={
                    'action': 'password_reset',
                    'user_id': existing_user.id,
                    'email': email
                },
                message=f"Password reset for {email}"
            )
        else:
            # Create new admin user
            result = db.execute(text("""
                INSERT INTO users (
                    email, hashed_password, full_name, role, permission_role,
                    is_active, created_at, updated_at
                ) VALUES (
                    :email, :password, 'Administrator', 'admin', 'admin',
                    true, NOW(), NOW()
                )
                RETURNING id
            """), {'email': email, 'password': hashed_password})

            new_user_id = result.fetchone()[0]
            db.commit()

            return success_response(
                data={
                    'action': 'user_created',
                    'user_id': new_user_id,
                    'email': email
                },
                message=f"Admin user created: {email}"
            )

    except SQLAlchemyError as e:
        logger.error(f"Emergency admin reset failed: {e}")
        db.rollback()
        raise DatabaseException("Failed to reset admin")


@router.get("/find-accounts")
async def find_accounts_by_api_key(
    request: Request,
    search: str = Query('', description="Search term"),
    db: Session = Depends(get_db)
):
    """Find accounts by name using ADMIN_API_KEY auth."""
    api_key = request.headers.get('X-API-Key', '')
    expected_key = os.getenv('ADMIN_API_KEY', '')
    if not api_key or not expected_key or api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    accounts = db.execute(text("""
        SELECT id, name, status, owner_user_id, created_at
        FROM tenant_accounts
        WHERE (name ILIKE :search OR :search = '')
          AND is_deleted = false
        ORDER BY created_at DESC
        LIMIT 20
    """), {'search': f'%{search}%'}).fetchall()

    return success_response(
        data={'accounts': [
            {'id': str(a[0]), 'name': a[1], 'status': a[2], 'owner_user_id': a[3],
             'created_at': str(a[4])} for a in accounts
        ]},
        message=f"Found {len(accounts)} accounts"
    )


@router.delete("/cleanup-account/{account_id}")
async def cleanup_account_by_api_key(
    account_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Emergency account cleanup using ADMIN_API_KEY auth.
    Deletes all dependent records, users, and soft-deletes the tenant account.
    Also resets the subscriber invitation so onboarding can be retried.
    """
    api_key = request.headers.get('X-API-Key', '')
    expected_key = os.getenv('ADMIN_API_KEY', '')
    if not api_key or not expected_key or api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    try:
        # Get account
        account = db.execute(text("""
            SELECT id, name, status FROM tenant_accounts WHERE id = :id
        """), {'id': account_id}).fetchone()

        if not account:
            raise NotFoundException(f"Account {account_id} not found")

        account_name = account[1]

        # Get user IDs
        user_rows = db.execute(text("""
            SELECT id FROM users WHERE tenant_account_id = :account_id
        """), {'account_id': account_id}).fetchall()
        user_ids = [row[0] for row in user_rows]

        deleted_from = []

        if user_ids:
            # Comprehensive FK cleanup - every table that references users.id
            dependent_tables = [
                ("user_assigned_roles", "user_id"),
                ("user_active_role", "user_id"),
                ("user_permissions", "user_id"),
                ("user_page_permissions", "user_id"),
                ("permission_requests", "employee_id"),
                ("permissions", "user_id"),
                ("api_keys", "user_id"),
                ("refresh_tokens", "user_id"),
                ("revoked_tokens", "user_id"),
                ("security_certifications", "employee_id"),
                ("microsoft_oauth_tokens", "user_id"),
                ("microsoft_credentials", "user_id"),
                ("audit_logs", "user_id"),
                ("subscription_plans", "user_id"),
                ("account_subscriptions", "user_id"),
                ("email_tracking", "user_id"),
                ("sms_messages", "user_id"),
                ("call_logs", "user_id"),
                ("voicemail_drops", "user_id"),
                ("user_email_connections", "user_id"),
                ("tasks", "assigned_to_id"),
                ("tasks", "owner_id"),
                ("workflow_tasks", "user_id"),
                ("ai_chat_sessions", "user_id"),
                ("ai_audit_logs", "user_id"),
                ("dialer_sessions", "user_id"),
                ("dialer_agents", "agent_id"),
                ("user_settings", "user_id"),
                ("notification_preferences", "user_id"),
                ("impersonation_sessions", "manager_id"),
                ("impersonation_sessions", "impersonated_user_id"),
                ("employee_invites", "invited_by_user_id"),
                ("employee_invites", "user_id"),
                ("subscriber_invitations", "accepted_by_user_id"),
                ("user_invitations", "invited_by"),
            ]

            for table_name, column_name in dependent_tables:
                try:
                    result = db.execute(text(f"""
                        DELETE FROM {table_name} WHERE {column_name} IN :user_ids
                    """), {'user_ids': tuple(user_ids)})
                    if result.rowcount > 0:
                        deleted_from.append(f"{table_name}.{column_name}: {result.rowcount}")
                except Exception:
                    pass

            # Tenant-level records
            try:
                db.execute(text("DELETE FROM user_invitations WHERE organization_id = :id"), {'id': account_id})
            except Exception:
                pass

        # Delete users
        user_del = db.execute(text("DELETE FROM users WHERE tenant_account_id = :id"), {'id': account_id})

        # Soft delete account
        db.execute(text("""
            UPDATE tenant_accounts SET is_deleted = true, status = 'deleted', updated_at = NOW()
            WHERE id = :id
        """), {'id': account_id})

        # Reset associated subscriber invitation so it can be reused
        db.execute(text("""
            UPDATE subscriber_invitations
            SET status = 'pending', accepted_at = NULL, accepted_by_user_id = NULL, updated_at = NOW()
            WHERE accepted_by_user_id IN :user_ids OR company_name = :name
        """), {'user_ids': tuple(user_ids) if user_ids else (0,), 'name': account_name})

        db.commit()

        return success_response(
            data={
                'account_id': account_id,
                'name': account_name,
                'users_deleted': user_del.rowcount,
                'dependent_records_cleaned': deleted_from,
            },
            message=f"Account '{account_name}' cleaned up and invitation reset"
        )
