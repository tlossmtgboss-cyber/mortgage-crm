"""
Account Management - Admin Routes
KPIs, account CRUD, account actions, user management, impersonation, billing, audit logs
Extracted from account_management_routes.py
"""

from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
import logging
import os

from database import get_db as _get_db_func
from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    success_response
)
from sqlalchemy.exc import SQLAlchemyError

from routes.account_models import (
    AccountActionRequest,
    UserActionRequest,
    ImpersonationRequest,
    RoleUpdateRequest,
    InternalNotesRequest,
    UserPermissionsRequest,
    table_exists,
    check_master_admin,
    require_master_admin,
    get_user_from_request,
    log_admin_action,
    calculate_account_metrics,
    format_account_response,
    _get_kpis_from_organizations,
    _list_accounts_from_organizations,
    _format_time_ago,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Account Management - Admin"])

# Module-level dependency references
_get_current_user = None


def set_dependencies(user_model, current_user_func):
    """Set dependencies from parent module"""
    global _get_current_user
    _get_current_user = current_user_func
    from routes.account_models import set_auth_dependency
    set_auth_dependency(current_user_func)


# =============================================================================
# KPI Endpoints
# =============================================================================

@router.get("/kpis")
async def get_kpis(
    request: Request,
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
        count_query = """
            SELECT COUNT(DISTINCT ta.id)
            FROM tenant_accounts ta
            LEFT JOIN users u ON u.id = ta.owner_user_id
            WHERE """ + where_sql + """
        """
        total = db.execute(text(count_query), params).scalar() or 0

        # Get accounts with owner info
        query = """
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
            WHERE """ + where_sql + """
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
                    savepoint = db.begin_nested()
                    delete_sql = "DELETE FROM " + table_name + " WHERE " + column_name + " IN :user_ids"
                    db.execute(text(delete_sql), {'user_ids': tuple(user_ids)})
                    savepoint.commit()
                except Exception as e:
                    logger.error(f"Error in delete_account (delete {table_name}.{column_name}): {e}")
                    savepoint.rollback()

            # Also clean up tenant-level records
            try:
                savepoint = db.begin_nested()
                db.execute(text("""
                    DELETE FROM user_invitations WHERE organization_id = :account_id
                """), {'account_id': account_id})
                savepoint.commit()
            except Exception as e:
                logger.error(f"Error in delete_account (delete user_invitations): {e}")
                savepoint.rollback()

        # Clear owner FK before deleting users
        db.execute(text("""
            UPDATE tenant_accounts SET owner_user_id = NULL WHERE id = :account_id
        """), {'account_id': account_id})

        # Delete associated users
        db.execute(text("""
            DELETE FROM users WHERE tenant_account_id = :account_id
        """), {'account_id': account_id})

        # Soft delete the account
        db.execute(text("""
            UPDATE tenant_accounts
            SET is_deleted = true,
                status = 'canceled',
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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

        events_sql = """
            SELECT id, result, failure_reason, ip_address, device, browser,
                   location, session_duration_seconds, created_at
            FROM login_events
            WHERE """ + where_clause + """
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        events = db.execute(text(events_sql), params).fetchall()

        count_sql = "SELECT COUNT(*) FROM login_events WHERE " + where_clause
        total = db.execute(text(count_sql), params).scalar() or 0

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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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

        # Revoke existing tokens so stale role claims cannot be reused
        from auth.tokens import token_blacklist
        token_blacklist.revoke_on_privilege_change(int(user_id), reason="role_changed")

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

@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: str,
    request: Request,
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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

        # Revoke existing tokens so stale permission claims cannot be reused
        from auth.tokens import token_blacklist
        token_blacklist.revoke_on_privilege_change(int(user_id), reason="permissions_changed")

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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
):
    """Start impersonating a user.

    Security (2026-04-19 audit, finding C1):
    - Uses canonical create_access_token (RS256, jti, iss, aud, type)
    - 15-min TTL (was 1hr), type=impersonation, impersonator claims
    - Cannot impersonate yourself or cross-org (unless superadmin)
    - Every issuance logged to admin_audit_log
    """
    import secrets
    from auth.tokens import create_access_token

    try:
        current_user = await get_user_from_request(request, db)
        require_master_admin(current_user)

        # Convert user_id to integer for database query
        try:
            user_id_int = int(imp_request.user_id)
        except (ValueError, TypeError):
            raise ValidationException(f"Invalid user_id: {imp_request.user_id}")

        # C1 guardrail: cannot impersonate yourself
        if user_id_int == current_user.id:
            raise ValidationException("Cannot impersonate yourself")

        target_user = db.execute(text("""
            SELECT id, full_name, email, tenant_account_id, role, permission_role
            FROM users
            WHERE id = :user_id
        """), {'user_id': user_id_int}).fetchone()

        if not target_user:
            raise NotFoundException(f"User {imp_request.user_id} not found")

        # C1 guardrail: cross-org impersonation blocked unless superadmin
        admin_tenant = getattr(current_user, 'tenant_account_id', None)
        target_tenant = target_user[3]  # tenant_account_id
        is_superadmin = getattr(current_user, 'is_superadmin', False)
        if target_tenant != admin_tenant and not is_superadmin:
            raise PermissionException("Cannot impersonate users in other organizations")

        # Use canonical token creator — sets jti, iat, exp, iss, aud,
        # type, and uses settings.algorithm (RS256 in prod). Per C1 fix.
        access_token = create_access_token(
            data={
                "sub": target_user[2],  # email
                "user_id": target_user[0],  # id
                "type": "impersonation",
                "impersonator_id": current_user.id,
                "impersonator_email": getattr(current_user, 'email', None),
                "organization_id": target_tenant,
            },
            expires_delta=timedelta(minutes=15),
        )

        target_name = target_user[1] or target_user[2] or f"User {target_user[0]}"
        target_role = target_user[4] or target_user[5] or "user"

        # SOC 2: audit every impersonation issuance
        log_admin_action(
            db, current_user, 'impersonation.started', 'user',
            str(target_user[0]), target_name=target_name, request=request,
        )

        return success_response(
            data={
                'sessionId': f"preview_{user_id_int}_{secrets.token_hex(4)}",
                'sessionToken': access_token,
                'token': access_token,
                'token_type': 'bearer',
                'expires_in': 900,
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
    db: Session = Depends(_get_db_func)
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
