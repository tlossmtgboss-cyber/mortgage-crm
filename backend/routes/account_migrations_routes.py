"""
Account Management - Migration & Cleanup Routes
Schema migrations, data cleanup, emergency admin reset, account cleanup
Extracted from account_management_routes.py
"""

from fastapi import APIRouter, Depends, Request, Query, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
import logging
import os
import secrets

from database import get_db as _get_db_func
from utils.error_handling import (
    PermissionException,
    NotFoundException,
    DatabaseException,
    success_response
)
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel

from routes.account_models import (
    table_exists,
    require_master_admin,
    get_user_from_request,
    validate_table_name,
    validate_column_name,
    safe_delete_from_table,
    safe_delete_with_column_condition,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Account Management - Migrations"])

# Module-level dependency references
_get_current_user = None


def set_dependencies(user_model, current_user_func):
    """Set dependencies from parent module"""
    global _get_current_user
    _get_current_user = current_user_func
    from routes.account_models import set_auth_dependency
    set_auth_dependency(current_user_func)


# =============================================================================
# Migration Endpoints
# =============================================================================

@router.post("/run-migration")
async def run_account_management_migration(
    admin_key: str = Header(None, alias="X-Admin-Key"),
    action: str = Query(default="migrate", description="Action: migrate or cleanup"),
    keep_admin_email: str = Query(default="admin@perenniaai.com", description="Admin email to preserve (for cleanup action)"),
    db: Session = Depends(_get_db_func)
):
    """Run the account management tables migration, or perform cleanup.

    Actions:
    - migrate: Create account management tables (default)
    - cleanup: Delete all sample data, keeping only specified admin user
    """
    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if not expected_key or not secrets.compare_digest(admin_key or "", expected_key):
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
                        delete_sql = "DELETE FROM " + validated_table
                        result = conn.execute(text(delete_sql))
                        results['deleted'][table] = result.rowcount
                    except SQLAlchemyError as e:
                        results['errors'].append(f"{table}: cleanup failed")

                # Delete team members/profiles (whitelist-validated)
                for table in ['team_members', 'team_member_profiles', 'extracted_data', 'referral_partners']:
                    try:
                        validated_table = validate_table_name(table)
                        delete_sql = "DELETE FROM " + validated_table
                        result = conn.execute(text(delete_sql))
                        results['deleted'][table] = result.rowcount
                    except Exception as e:
                        logger.error(f"Error in run_account_management_migration (delete team tables): {e}")

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
                except Exception as e:
                    logger.error(f"Error in run_account_management_migration (delete suspended accounts): {e}")

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
    db: Session = Depends(_get_db_func)
):
    """Comprehensive cleanup: Delete ALL sample data including tasks, users, accounts.

    This migration-style endpoint removes:
    - All tasks (tasks, task_instances, purl_tasks)
    - All users except the specified admin email
    - All team members and profiles
    - All suspended and cancelled accounts
    - All account management sample data
    """
    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if not expected_key or not secrets.compare_digest(admin_key or "", expected_key):
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
            except Exception as e:
                logger.error(f"Error in run_cleanup_migration (delete {table}): {e}")

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
            except Exception as e:
                logger.error(f"Error in run_cleanup_migration (delete account table {table}): {e}")

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
    db: Session = Depends(_get_db_func)
):
    """Run the subscriber_invitations table migration."""
    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if not expected_key or not secrets.compare_digest(admin_key or "", expected_key):
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
# Data Cleanup Endpoints
# =============================================================================

@router.delete("/cleanup/sample-data")
async def cleanup_sample_data(
    request: Request,
    admin_key: str = Header(None, alias="X-Admin-Key"),
    db: Session = Depends(_get_db_func)
):
    """Delete all sample/demo data from account management tables.
    Can be called with X-Admin-Key header to bypass JWT authentication.
    """
    # Check for admin key bypass
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key and admin_key == expected_key:
        logger.info("Cleanup authorized via admin API key")
    else:
        try:
            current_user = await get_user_from_request(request, db)
            require_master_admin(current_user)
        except Exception as e:
            logger.error(f"Error in cleanup_sample_data (auth check): {e}")
            if not admin_key:
                raise HTTPException(status_code=401, detail="Auth required. Provide X-Admin-Key header or JWT token.")
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
    admin_key: str = Header(None, alias="X-Admin-Key"),
    keep_admin_email: str = Query(default="admin@perenniaai.com", description="Admin email to preserve"),
    db: Session = Depends(_get_db_func)
):
    """Delete all users except the specified admin user.
    Can be called with X-Admin-Key header to bypass JWT authentication.
    """
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
        except Exception as e:
            logger.error(f"Error in cleanup_users (auth check): {e}")
            if not admin_key:
                raise HTTPException(status_code=401, detail="Auth required. Provide X-Admin-Key header or JWT token.")
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
                delete_sql = (
                    "DELETE FROM " + validated_table
                    + " WHERE " + validated_column + " IS NOT NULL AND "
                    + validated_column + " != :admin_id"
                )
                result = db.execute(text(delete_sql), {'admin_id': admin_id})
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
    admin_key: str = Header(None, alias="X-Admin-Key"),
    db: Session = Depends(_get_db_func)
):
    """Comprehensive cleanup: Delete ALL sample data including tasks, users, accounts.

    This endpoint removes:
    - All tasks (tasks, task_instances, purl_tasks)
    - All users except the specified admin email
    - All team members and profiles
    - All suspended and cancelled accounts
    - All account management sample data

    Can be called with X-Admin-Key header to bypass JWT authentication.
    """
    current_user = None

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
                raise HTTPException(status_code=401, detail="Authentication required. Provide X-Admin-Key header or valid JWT token.")
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
            except Exception as e:
                logger.error(f"Error in cleanup_all_sample_data (delete account table {table}): {e}")

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


class EmergencyResetRequest(BaseModel):
    email: str
    password: str
    secret_key: str


@router.post("/emergency-admin-reset")
async def emergency_admin_reset(
    body: EmergencyResetRequest,
    db: Session = Depends(_get_db_func)
):
    """Emergency endpoint to create or reset admin user password.
    Requires secret key for security.
    """
    import bcrypt
    import secrets as _secrets

    email = body.email
    password = body.password
    secret_key = body.secret_key

    # Verify secret key (constant-time comparison)
    expected_key = os.getenv("EMERGENCY_ADMIN_KEY", "")
    if not expected_key or not _secrets.compare_digest(secret_key, expected_key):
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
    db: Session = Depends(_get_db_func)
):
    """Find accounts by name using ADMIN_API_KEY auth."""
    api_key = request.headers.get('X-API-Key', '')
    expected_key = os.getenv('ADMIN_API_KEY', '')
    if not api_key or not expected_key or not secrets.compare_digest(api_key, expected_key):
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
    db: Session = Depends(_get_db_func)
):
    """Emergency account cleanup using ADMIN_API_KEY auth.
    Deletes all dependent records, users, and soft-deletes the tenant account.
    Also resets the subscriber invitation so onboarding can be retried.
    """
    api_key = request.headers.get('X-API-Key', '')
    expected_key = os.getenv('ADMIN_API_KEY', '')
    if not api_key or not expected_key or not secrets.compare_digest(api_key, expected_key):
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
                    savepoint = db.begin_nested()
                    delete_sql = "DELETE FROM " + table_name + " WHERE " + column_name + " IN :user_ids"
                    result = db.execute(text(delete_sql), {'user_ids': tuple(user_ids)})
                    if result.rowcount > 0:
                        deleted_from.append(f"{table_name}.{column_name}: {result.rowcount}")
                    savepoint.commit()
                except Exception as e:
                    logger.error(f"Error in cleanup_account_by_api_key (delete {table_name}.{column_name}): {e}")
                    savepoint.rollback()

            # Tenant-level records
            try:
                savepoint = db.begin_nested()
                db.execute(text("DELETE FROM user_invitations WHERE organization_id = :id"), {'id': account_id})
                savepoint.commit()
            except Exception as e:
                logger.error(f"Error in cleanup_account_by_api_key (delete user_invitations): {e}")
                savepoint.rollback()

        # Clear owner FK on tenant account before deleting users
        db.execute(text("""
            UPDATE tenant_accounts SET owner_user_id = NULL WHERE id = :id
        """), {'id': account_id})

        # Delete users
        user_del = db.execute(text("DELETE FROM users WHERE tenant_account_id = :id"), {'id': account_id})

        # Soft delete account
        db.execute(text("""
            UPDATE tenant_accounts SET is_deleted = true, status = 'canceled', updated_at = NOW()
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
    except NotFoundException:
        raise
    except Exception as e:
        logger.error(f"Error cleaning up account {account_id}: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to clean up account: {str(e)[:200]}")
