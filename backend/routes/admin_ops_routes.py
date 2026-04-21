"""
Admin Operations Routes
Admin, setup, debug, and data management endpoints.
Extracted from inline_legacy_routes.py.
"""
from fastapi import (
    Depends, HTTPException, Query, Request,
    UploadFile, File, Form,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging
import os
import secrets

from database.models import (
    User, ApiKey, Loan, ExtractedData,
)
from database import SessionLocal

logger = logging.getLogger(__name__)
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _verify_admin_key(provided_key: str) -> None:
    """Validate admin API key with timing-safe comparison. Fail-closed if not configured."""
    if not _ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin key not configured")
    if not provided_key or not secrets.compare_digest(provided_key, _ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin key")

import re
_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

def _safe_identifier(name: str) -> str:
    """Validate and quote a SQL identifier (table/column name) to prevent injection."""
    if not _SAFE_IDENTIFIER_RE.match(name) or len(name) > 128:
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


def register_admin_ops_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register admin operations routes.

    Endpoints extracted:
      - Pool & Salesforce admin (pool-status, salesforce-sync-status, etc.)
      - Admin setup / migration endpoints (run-essential-migrations, create-api-keys-table, etc.)
      - Admin stats & user management (admin/stats, admin/users, debug/delete-user, etc.)
      - Admin data endpoints (loan-check, debug-data, task-check, import-loans, etc.)
    """
    pwd_context = kwargs.get('pwd_context')
    get_password_hash = kwargs.get('get_password_hash')
    create_access_token = kwargs.get('create_access_token')
    DATABASE_URL = kwargs.get('DATABASE_URL', '')
    match_entity = kwargs.get('match_entity')  # closure from inline_legacy_routes

    # ========================================================================
    # POOL & SALESFORCE ADMIN (originally lines ~14799-15502)
    # ========================================================================

    @app.get("/api/v1/admin/pool-status")
    async def get_pool_status_endpoint(current_user = Depends(get_current_user)):
        """
        Get database connection pool status WITHOUT using a db connection.
        Use this to diagnose connection exhaustion issues.
        """
        try:
            from database import get_pool_status, engine
            pool_status = get_pool_status()
            return {
                "status": "ok",
                "pool": pool_status,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {"status": "error", "error": "Internal server error"}


    @app.get("/api/v1/admin/salesforce-sync-status")
    async def get_salesforce_sync_status(current_user = Depends(get_current_user)):
        """
        Get Salesforce sync status including connected profiles, recent sync activity,
        and health metrics.
        """
        db = SessionLocal()
        try:
            result = {
                "status": "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scheduler": {
                    "job_id": "salesforce_sync_all_users",
                    "interval_minutes": 5,
                    "enabled": True
                },
                "connected_profiles": {
                    "total": 0,
                    "active": 0,
                    "error": 0,
                    "sync_enabled": 0
                },
                "recent_syncs": [],
                "health": {
                    "healthy": False,
                    "last_successful_sync": None,
                    "inbound_syncs_24h": 0,
                    "outbound_syncs_24h": 0,
                    "errors_24h": 0
                },
                "profiles": []
            }

            # Check if integration_profiles table exists
            try:
                profiles_exist = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'integration_profiles'
                    )
                """)).scalar()
            except Exception as e:
                logger.error(f"Error checking integration_profiles table in get_salesforce_sync_status: {e}")
                profiles_exist = False

            if not profiles_exist:
                result["status"] = "no_tables"
                result["message"] = "Salesforce integration tables not created yet"
                return result

            # Get connected profiles count
            try:
                profile_counts = db.execute(text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN status IN ('connected', 'active') THEN 1 END) as active,
                        COUNT(CASE WHEN status = 'error' THEN 1 END) as error_count,
                        COUNT(CASE WHEN sync_enabled = TRUE THEN 1 END) as sync_enabled
                    FROM integration_profiles
                    WHERE provider = 'salesforce'
                """)).fetchone()

                if profile_counts:
                    result["connected_profiles"] = {
                        "total": profile_counts[0] or 0,
                        "active": profile_counts[1] or 0,
                        "error": profile_counts[2] or 0,
                        "sync_enabled": profile_counts[3] or 0
                    }
            except Exception as e:
                result["connected_profiles"]["error_message"] = str(e)

            # Get profile details
            try:
                profiles = db.execute(text("""
                    SELECT
                        ip.id,
                        ip.user_id,
                        u.email as user_email,
                        ip.status,
                        ip.sf_username,
                        ip.instance_url,
                        ip.sync_enabled,
                        ip.last_sync_at,
                        ip.last_error,
                        ip.connected_at
                    FROM integration_profiles ip
                    LEFT JOIN users u ON u.id = ip.user_id
                    WHERE ip.provider = 'salesforce'
                    ORDER BY ip.last_sync_at DESC NULLS LAST
                    LIMIT 20
                """)).fetchall()

                result["profiles"] = [
                    {
                        "id": p[0],
                        "user_id": p[1],
                        "user_email": p[2],
                        "status": p[3],
                        "sf_username": p[4],
                        "instance_url": p[5],
                        "sync_enabled": p[6],
                        "last_sync_at": p[7].isoformat() if p[7] else None,
                        "last_error": p[8],
                        "connected_at": p[9].isoformat() if p[9] else None
                    }
                    for p in profiles
                ]
            except Exception as e:
                result["profiles_error"] = str(e)

            # Check salesforce_sync_logs table
            try:
                logs_exist = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'salesforce_sync_logs'
                    )
                """)).scalar()

                if logs_exist:
                    # Check if sync_direction column exists, add it if not
                    has_sync_direction = db.execute(text("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns
                            WHERE table_name = 'salesforce_sync_logs' AND column_name = 'sync_direction'
                        )
                    """)).scalar()

                    if not has_sync_direction:
                        try:
                            db.execute(text("ALTER TABLE salesforce_sync_logs ADD COLUMN sync_direction VARCHAR(20) DEFAULT 'inbound'"))
                            db.commit()
                            result["migration_applied"] = "Added sync_direction column to salesforce_sync_logs"
                            has_sync_direction = True
                        except Exception as col_err:
                            result["column_migration_error"] = str(col_err)[:100]

                    # Get recent sync logs (with or without sync_direction)
                    if has_sync_direction:
                        recent_logs = db.execute(text("""
                            SELECT
                                id, sync_type, sync_direction, status,
                                records_processed, records_created, records_updated, records_failed,
                                started_at, completed_at, error_message
                            FROM salesforce_sync_logs
                            ORDER BY started_at DESC NULLS LAST
                            LIMIT 10
                        """)).fetchall()

                        result["recent_syncs"] = [
                            {
                                "id": log[0],
                                "sync_type": log[1],
                                "direction": log[2],
                                "status": log[3],
                                "records_processed": log[4],
                                "records_created": log[5],
                                "records_updated": log[6],
                                "records_failed": log[7],
                                "started_at": log[8].isoformat() if log[8] else None,
                                "completed_at": log[9].isoformat() if log[9] else None,
                                "error": log[10][:200] if log[10] else None
                            }
                            for log in recent_logs
                        ]

                        # Get health metrics
                        health_stats = db.execute(text("""
                            SELECT
                                MAX(CASE WHEN status = 'success' THEN completed_at END) as last_success,
                                COUNT(CASE WHEN sync_direction = 'inbound' AND started_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as inbound_24h,
                                COUNT(CASE WHEN sync_direction = 'outbound' AND started_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as outbound_24h,
                                COUNT(CASE WHEN status = 'error' AND started_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as errors_24h
                            FROM salesforce_sync_logs
                        """)).fetchone()
                    else:
                        # Fallback query without sync_direction
                        recent_logs = db.execute(text("""
                            SELECT
                                id, sync_type, status,
                                records_processed, records_created, records_updated, records_failed,
                                started_at, completed_at, error_message
                            FROM salesforce_sync_logs
                            ORDER BY started_at DESC NULLS LAST
                            LIMIT 10
                        """)).fetchall()

                        result["recent_syncs"] = [
                            {
                                "id": log[0],
                                "sync_type": log[1],
                                "direction": "unknown",
                                "status": log[2],
                                "records_processed": log[3],
                                "records_created": log[4],
                                "records_updated": log[5],
                                "records_failed": log[6],
                                "started_at": log[7].isoformat() if log[7] else None,
                                "completed_at": log[8].isoformat() if log[8] else None,
                                "error": log[9][:200] if log[9] else None
                            }
                            for log in recent_logs
                        ]

                        # Simplified health stats without sync_direction
                        health_stats = db.execute(text("""
                            SELECT
                                MAX(CASE WHEN status = 'success' THEN completed_at END) as last_success,
                                COUNT(CASE WHEN started_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as total_24h,
                                0 as outbound_24h,
                                COUNT(CASE WHEN status = 'error' AND started_at >= NOW() - INTERVAL '24 hours' THEN 1 END) as errors_24h
                            FROM salesforce_sync_logs
                        """)).fetchone()

                    if health_stats:
                        result["health"] = {
                            "healthy": result["connected_profiles"]["active"] > 0 and (health_stats[3] or 0) < 5,
                            "last_successful_sync": health_stats[0].isoformat() if health_stats[0] else None,
                            "inbound_syncs_24h": health_stats[1] or 0,
                            "outbound_syncs_24h": health_stats[2] or 0,
                            "errors_24h": health_stats[3] or 0
                        }
            except Exception as e:
                db.rollback()
                result["sync_logs_error"] = str(e)

            # Check integration_events table for additional metrics
            try:
                events_exist = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'integration_events'
                    )
                """)).scalar()

                if events_exist:
                    event_stats = db.execute(text("""
                        SELECT
                            COUNT(*) as total_events,
                            COUNT(CASE WHEN status = 'success' THEN 1 END) as success,
                            COUNT(CASE WHEN status = 'error' THEN 1 END) as errors,
                            MAX(created_at) as last_event
                        FROM integration_events
                        WHERE created_at >= NOW() - INTERVAL '24 hours'
                    """)).fetchone()

                    if event_stats:
                        result["integration_events_24h"] = {
                            "total": event_stats[0] or 0,
                            "success": event_stats[1] or 0,
                            "errors": event_stats[2] or 0,
                            "last_event": event_stats[3].isoformat() if event_stats[3] else None
                        }
            except Exception as e:
                result["integration_events_error"] = str(e)

            # Determine overall status
            if result["connected_profiles"]["active"] == 0:
                result["status"] = "no_connected_profiles"
                result["message"] = "No users have connected Salesforce. Users need to complete OAuth at /api/integrations/salesforce/oauth/start"
            elif result["connected_profiles"]["sync_enabled"] == 0:
                result["status"] = "sync_disabled"
                result["message"] = "Profiles exist but sync is disabled for all users"
            else:
                result["status"] = "ok"
                result["message"] = f"{result['connected_profiles']['active']} active profile(s) with sync enabled"

            return result

        except Exception as e:
            logger.error(f"Salesforce sync status check failed: {e}")
            return {
                "status": "error",
                "error": "Internal server error",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        finally:
            db.close()


    @app.post("/api/v1/admin/salesforce-trigger-sync")
    async def trigger_salesforce_sync_admin(current_user = Depends(get_current_user)):
        """
        Admin endpoint to manually trigger Salesforce sync for all connected profiles.
        """
        try:
            from tasks.salesforce_sync_tasks import sync_all_users_salesforce

            result = await sync_all_users_salesforce(
                sync_emails=True,
                sync_calendar=True,
                push_to_salesforce=True,
                email_days_back=7,
                calendar_days_back=7,
                calendar_days_forward=30,
                push_since_hours=24
            )

            return {
                "status": "success",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sync_result": result
            }
        except Exception as e:
            logger.error(f"Manual Salesforce sync trigger failed: {e}")
            return {
                "status": "error",
                "error": "Internal server error",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }


    @app.post("/api/v1/admin/salesforce-test-email-match")
    async def test_salesforce_email_match(email: str = None, lead_id: int = None, current_user = Depends(get_current_user)):
        """
        Test the Salesforce email matching functionality.

        Either provide an email to search for in Salesforce, or a lead_id to push.
        """
        db = SessionLocal()
        try:
            from services.salesforce.sync_service import salesforce_sync
            from services.salesforce.oauth_service import salesforce_oauth
            from salesforce_integration_models import IntegrationProfile

            # Get the first connected integration profile
            profile = db.query(IntegrationProfile).filter(
                IntegrationProfile.status.in_(['active', 'connected'])
            ).first()

            if not profile:
                return {"status": "error", "error": "No connected Salesforce integration profile found"}

            # Get access token
            access_token, instance_url = await salesforce_oauth.get_access_token(db, profile.id)

            if not access_token:
                return {"status": "error", "error": "Failed to get Salesforce access token"}

            result = {
                "status": "success",
                "profile_id": profile.id,
                "instance_url": instance_url,
                "tests": []
            }

            # Test 1: Email search in Salesforce
            if email:
                match_result = await salesforce_sync._find_salesforce_record_by_email(
                    access_token, instance_url, email
                )
                result["tests"].append({
                    "test": "email_search",
                    "email": email,
                    "found": match_result.get("found", False),
                    "salesforce_type": match_result.get("type"),
                    "salesforce_id": match_result.get("id"),
                    "record": match_result.get("record")
                })

            # Test 2: Push a specific lead
            if lead_id:
                # Get the lead
                lead = db.execute(text("SELECT * FROM leads WHERE id = :id"), {"id": lead_id}).fetchone()
                if lead:
                    push_result = await salesforce_sync.push_lead_to_salesforce(
                        db, profile.id, lead_id
                    )
                    result["tests"].append({
                        "test": "push_lead",
                        "lead_id": lead_id,
                        "lead_email": lead.email if hasattr(lead, 'email') else None,
                        "result": push_result
                    })
                else:
                    result["tests"].append({
                        "test": "push_lead",
                        "lead_id": lead_id,
                        "error": "Lead not found"
                    })

            # If no specific test, get a sample lead to show
            if not email and not lead_id:
                sample_lead = db.execute(text("""
                    SELECT id, first_name, last_name, email, salesforce_id
                    FROM leads
                    WHERE email IS NOT NULL
                    ORDER BY updated_at DESC
                    LIMIT 5
                """)).fetchall()

                result["sample_leads"] = [
                    {
                        "id": l.id,
                        "name": f"{l.first_name} {l.last_name}",
                        "email": l.email,
                        "salesforce_id": l.salesforce_id
                    }
                    for l in sample_lead
                ]
                result["usage"] = {
                    "test_email": "/api/v1/admin/salesforce-test-email-match?email=test@example.com",
                    "push_lead": "/api/v1/admin/salesforce-test-email-match?lead_id=123"
                }

            return result

        except Exception as e:
            logger.error(f"Salesforce email match test failed: {e}")
            import traceback
            return {
                "status": "error",
                "error": "Internal server error"
            }
        finally:
            db.close()


    @app.post("/api/v1/admin/salesforce-migrate-schema")
    async def migrate_salesforce_schema():
        """
        Run database migrations to add missing columns for Salesforce sync.
        Safe to run multiple times - uses IF NOT EXISTS.
        """
        db = SessionLocal()
        migrations_run = []
        errors = []

        try:
            # 1. Add salesforce_id to leads table
            try:
                db.execute(text("""
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS salesforce_id VARCHAR
                """))
                db.commit()
                migrations_run.append("leads.salesforce_id")
            except Exception as e:
                db.rollback()
                errors.append(f"leads.salesforce_id: {str(e)[:100]}")

            # 2. Add meta_data to leads table
            try:
                db.execute(text("""
                    ALTER TABLE leads ADD COLUMN IF NOT EXISTS meta_data JSONB
                """))
                db.commit()
                migrations_run.append("leads.meta_data")
            except Exception as e:
                db.rollback()
                errors.append(f"leads.meta_data: {str(e)[:100]}")

            # 3. Add meta_data to calendar_events table
            try:
                db.execute(text("""
                    ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS meta_data JSONB
                """))
                db.commit()
                migrations_run.append("calendar_events.meta_data")
            except Exception as e:
                db.rollback()
                errors.append(f"calendar_events.meta_data: {str(e)[:100]}")

            # 4. Set default for integration_events.status if column exists but has NULL values
            try:
                db.execute(text("""
                    ALTER TABLE integration_events
                    ALTER COLUMN status SET DEFAULT 'pending'
                """))
                db.execute(text("""
                    UPDATE integration_events SET status = 'pending' WHERE status IS NULL
                """))
                db.commit()
                migrations_run.append("integration_events.status default")
            except Exception as e:
                db.rollback()
                errors.append(f"integration_events.status: {str(e)[:100]}")

            # 5. Add updated_at to calendar_events if missing
            try:
                db.execute(text("""
                    ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                """))
                db.commit()
                migrations_run.append("calendar_events.updated_at")
            except Exception as e:
                db.rollback()
                errors.append(f"calendar_events.updated_at: {str(e)[:100]}")

            # 6. Add meta_data to tasks table
            try:
                db.execute(text("""
                    ALTER TABLE tasks ADD COLUMN IF NOT EXISTS meta_data JSONB
                """))
                db.commit()
                migrations_run.append("tasks.meta_data")
            except Exception as e:
                db.rollback()
                errors.append(f"tasks.meta_data: {str(e)[:100]}")

            # 7. Add salesforce_id to loans table
            try:
                db.execute(text("""
                    ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_id VARCHAR
                """))
                db.commit()
                migrations_run.append("loans.salesforce_id")
            except Exception as e:
                db.rollback()
                errors.append(f"loans.salesforce_id: {str(e)[:100]}")

            # 8. Add meta_data to loans table
            try:
                db.execute(text("""
                    ALTER TABLE loans ADD COLUMN IF NOT EXISTS meta_data JSONB
                """))
                db.commit()
                migrations_run.append("loans.meta_data")
            except Exception as e:
                db.rollback()
                errors.append(f"loans.meta_data: {str(e)[:100]}")

            # 9. Add meta_data to email_messages table
            try:
                db.execute(text("""
                    ALTER TABLE email_messages ADD COLUMN IF NOT EXISTS meta_data JSONB
                """))
                db.commit()
                migrations_run.append("email_messages.meta_data")
            except Exception as e:
                db.rollback()
                errors.append(f"email_messages.meta_data: {str(e)[:100]}")

            return {
                "status": "success" if not errors else "partial",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "migrations_run": migrations_run,
                "errors": errors
            }
        except Exception as e:
            return {
                "status": "error",
                "error": "Internal server error",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        finally:
            db.close()


    @app.post("/api/v1/admin/pool-reset")
    async def reset_pool_endpoint(admin_key: str = Query(...)):
        """
        Dispose and recreate the database connection pool.
        Use this when pool is exhausted and connections are stale.
        Requires admin key for safety.
        """
        _verify_admin_key(admin_key)

        try:
            from database import engine, get_pool_status

            # Get status before reset
            before_status = get_pool_status()

            # Dispose all connections in the pool
            engine.dispose()
            logger.warning("Database connection pool disposed - all connections closed")

            # Get status after reset
            after_status = get_pool_status()

            return {
                "status": "success",
                "message": "Connection pool reset successfully",
                "before": before_status,
                "after": after_status,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error(f"Pool reset failed: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "error": "Internal server error"}
            )


    @app.post("/api/v1/admin/update-telephony-config")
    async def update_user_telephony_config(
        admin_key: str = Query(...),
        email: str = Query(..., description="User email"),
        phone_number: str = Query(None, description="Telnyx phone number in E.164 format"),
        account_sid: str = Query(None, description="Telnyx Account SID"),
        auth_token: str = Query(None, description="Telnyx Auth Token"),
        db: Session = Depends(get_db)
    ):
        """
        Update telephony configuration for a user by email.
        Requires admin key for safety.
        """
        _verify_admin_key(admin_key)

        try:
            # Find the user
            user = db.execute(text("SELECT id, email, full_name FROM users WHERE email = :email"), {"email": email}).fetchone()
            if not user:
                raise HTTPException(status_code=404, detail=f"User with email {email} not found")

            user_id = user[0]
            user_email = user[1]
            user_name = user[2]

            # Check if telephony config exists for this user
            existing = db.execute(text("SELECT id FROM user_twilio_config WHERE user_id = :user_id"), {"user_id": user_id}).fetchone()  # Legacy table name

            updates = []
            params = {"user_id": user_id}

            if phone_number:
                updates.append("phone_number = :phone_number")
                params["phone_number"] = phone_number
            if account_sid:
                updates.append("account_sid = :account_sid")
                params["account_sid"] = account_sid
            if auth_token:
                updates.append("auth_token = :auth_token")
                params["auth_token"] = auth_token

            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update provided")

            updates.append("updated_at = NOW()")

            if existing:
                # Update existing config
                update_sql = f"UPDATE user_twilio_config SET {', '.join(updates)} WHERE user_id = :user_id"  # Legacy table name
                db.execute(text(update_sql), params)
                action = "updated"
            else:
                # Insert new config
                insert_fields = ["user_id"]
                insert_values = [":user_id"]
                if phone_number:
                    insert_fields.append("phone_number")
                    insert_values.append(":phone_number")
                if account_sid:
                    insert_fields.append("account_sid")
                    insert_values.append(":account_sid")
                if auth_token:
                    insert_fields.append("auth_token")
                    insert_values.append(":auth_token")
                insert_fields.extend(["created_at", "updated_at"])
                insert_values.extend(["NOW()", "NOW()"])

                insert_sql = f"INSERT INTO user_twilio_config ({', '.join(insert_fields)}) VALUES ({', '.join(insert_values)})"  # Legacy table name
                db.execute(text(insert_sql), params)
                action = "created"

            db.commit()

            # Verify the update
            config = db.execute(text("""
                SELECT phone_number, account_sid,
                       CASE WHEN auth_token IS NOT NULL THEN '***masked***' ELSE NULL END as auth_token
                FROM user_twilio_config WHERE user_id = :user_id  -- Legacy table name
            """), {"user_id": user_id}).fetchone()

            return {
                "status": "success",
                "action": action,
                "user": {"id": user_id, "email": user_email, "name": user_name},
                "config": {
                    "phone_number": config[0] if config else None,
                    "account_sid": config[1] if config else None,
                    "auth_token": config[2] if config else None
                }
            }
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update telephony config: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # ========================================================================
    # AUTHENTICATION TEST & ADMIN SETUP / MIGRATION ENDPOINTS
    # (originally lines ~17074-17873)
    # ========================================================================

    @app.post("/authentication/test")
    async def authentication_test_post(current_user: User = Depends(get_current_user_flexible)):
        """
        Zapier authentication test endpoint (POST method).
        This endpoint verifies that the API key authentication is working correctly.
        """
        return {
            "authenticated": True,
            "user_id": current_user.id,
            "email": current_user.email,
            "name": current_user.full_name,
            "message": "Authentication successful",
            "timestamp": datetime.now(timezone.utc)
        }

    @app.get("/authentication/test")
    async def authentication_test_get(current_user: User = Depends(get_current_user_flexible)):
        """
        Zapier authentication test endpoint (GET method).
        This endpoint verifies that the API key authentication is working correctly.
        """
        return {
            "authenticated": True,
            "user_id": current_user.id,
            "email": current_user.email,
            "name": current_user.full_name,
            "message": "Authentication successful",
            "timestamp": datetime.now(timezone.utc)
        }

    @app.post("/admin/run-essential-migrations")
    async def run_essential_migrations(
        admin_key: str = Query(...),
        db: Session = Depends(get_db)
    ):
        """
        Run essential table migrations using existing connection pool.
        Creates: notifications, user_permissions, permission_templates, ai_tasks tables.
        """
        _verify_admin_key(admin_key)

        results = {"created": [], "already_exists": [], "errors": []}

        try:
            # 1. Create notifications table
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        type VARCHAR(50) NOT NULL,
                        title VARCHAR(255) NOT NULL,
                        message TEXT NOT NULL,
                        link VARCHAR(500),
                        is_read BOOLEAN DEFAULT FALSE,
                        read_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC)"))
                db.commit()
                results["created"].append("notifications")
                logger.info("Created notifications table")
            except Exception as e:
                db.rollback()
                if "already exists" in str(e).lower():
                    results["already_exists"].append("notifications")
                else:
                    results["errors"].append(f"notifications: {str(e)[:100]}")

            # 2. Create permission_templates table
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS permission_templates (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL UNIQUE,
                        description TEXT,
                        category VARCHAR(50) NOT NULL,
                        permissions JSONB NOT NULL DEFAULT '{}',
                        is_system_default BOOLEAN DEFAULT FALSE,
                        created_by INTEGER REFERENCES users(id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_permission_templates_category ON permission_templates(category)"))
                db.commit()
                results["created"].append("permission_templates")
                logger.info("Created permission_templates table")
            except Exception as e:
                db.rollback()
                if "already exists" in str(e).lower():
                    results["already_exists"].append("permission_templates")
                else:
                    results["errors"].append(f"permission_templates: {str(e)[:100]}")

            # 3. Create user_permissions table
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS user_permissions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        permission_key VARCHAR(255) NOT NULL,
                        granted BOOLEAN DEFAULT TRUE,
                        granted_by INTEGER REFERENCES users(id),
                        granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP,
                        inherited_from VARCHAR(50) DEFAULT 'template',
                        CONSTRAINT unique_user_permission UNIQUE (user_id, permission_key)
                    )
                """))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_permissions_user ON user_permissions(user_id)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_user_permissions_composite ON user_permissions(user_id, permission_key, granted)"))
                db.commit()
                results["created"].append("user_permissions")
                logger.info("Created user_permissions table")
            except Exception as e:
                db.rollback()
                if "already exists" in str(e).lower():
                    results["already_exists"].append("user_permissions")
                else:
                    results["errors"].append(f"user_permissions: {str(e)[:100]}")

            # 4. Add permission_role column to users if missing
            try:
                db.execute(text("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='users' AND column_name='permission_role'
                        ) THEN
                            ALTER TABLE users ADD COLUMN permission_role VARCHAR(50) DEFAULT 'sales';
                        END IF;
                    END $$;
                """))
                db.commit()
                results["created"].append("users.permission_role column")
            except Exception as e:
                db.rollback()
                results["errors"].append(f"permission_role column: {str(e)[:100]}")

            # 5. Seed default permission templates if empty
            try:
                count = db.execute(text("SELECT COUNT(*) FROM permission_templates")).scalar()
                if count == 0:
                    # Management template
                    db.execute(text("""
                        INSERT INTO permission_templates (name, description, category, permissions, is_system_default)
                        VALUES ('Management', 'Full access for management roles', 'management',
                                '{"dashboard.view_all_widgets": true, "leads.view_all": true, "loans.view_all": true, "team.manage_permissions": true}'::jsonb,
                                true)
                        ON CONFLICT (name) DO NOTHING
                    """))
                    # Sales template
                    db.execute(text("""
                        INSERT INTO permission_templates (name, description, category, permissions, is_system_default)
                        VALUES ('Sales', 'Sales-focused template', 'sales',
                                '{"dashboard.view_all_widgets": false, "leads.view_assigned": true, "loans.view_assigned": true}'::jsonb,
                                true)
                        ON CONFLICT (name) DO NOTHING
                    """))
                    # Operations template
                    db.execute(text("""
                        INSERT INTO permission_templates (name, description, category, permissions, is_system_default)
                        VALUES ('Operations', 'Operations-focused template', 'operations',
                                '{"loans.view_all": true, "loans.process": true}'::jsonb,
                                true)
                        ON CONFLICT (name) DO NOTHING
                    """))
                    db.commit()
                    results["created"].append("default permission templates (3)")
            except Exception as e:
                db.rollback()
                results["errors"].append(f"permission templates seed: {str(e)[:100]}")

            # 6. Create ai_tasks table if not exists
            try:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS ai_tasks (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        type VARCHAR(50),
                        category VARCHAR(100),
                        priority INTEGER DEFAULT 0,
                        ai_confidence FLOAT,
                        ai_reasoning TEXT,
                        suggested_action TEXT,
                        completed_action TEXT,
                        borrower_name VARCHAR(255),
                        lead_id INTEGER,
                        loan_id INTEGER,
                        assigned_to_id INTEGER REFERENCES users(id),
                        due_date TIMESTAMP,
                        completed_at TIMESTAMP,
                        estimated_time INTEGER,
                        feedback TEXT,
                        user_metadata JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_tasks_assigned ON ai_tasks(assigned_to_id)"))
                db.execute(text("CREATE INDEX IF NOT EXISTS idx_ai_tasks_type ON ai_tasks(type)"))
                db.commit()
                results["created"].append("ai_tasks")
                logger.info("Created ai_tasks table")
            except Exception as e:
                db.rollback()
                if "already exists" in str(e).lower():
                    results["already_exists"].append("ai_tasks")
                else:
                    results["errors"].append(f"ai_tasks: {str(e)[:100]}")

            return {
                "success": True,
                "message": f"Created {len(results['created'])} items, {len(results['already_exists'])} already existed",
                "details": results
            }

        except Exception as e:
            logger.error(f"Essential migrations failed: {e}")
            return {
                "success": False,
                "message": "Migration failed — check server logs",
                "details": results
            }


    @app.post("/admin/create-api-keys-table")
    async def create_api_keys_table(db: Session = Depends(get_db)):
        """Admin endpoint to manually create the api_keys table"""
        try:
            # Create api_keys table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR UNIQUE NOT NULL,
                    name VARCHAR NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP
                );
            """))

            # Create index
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_api_keys_key ON api_keys(key);
            """))

            db.commit()

            logger.info("api_keys table created successfully")
            return {"status": "success", "message": "api_keys table created"}
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create api_keys table: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/admin/add-coborrower-columns")
    async def add_coborrower_columns(db: Session = Depends(get_db)):
        """Admin endpoint to add co-borrower email and phone columns"""
        try:
            # Add co_applicant_email column
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='leads' AND column_name='co_applicant_email'
                    ) THEN
                        ALTER TABLE leads ADD COLUMN co_applicant_email VARCHAR;
                    END IF;
                END $$;
            """))

            # Add co_applicant_phone column
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='leads' AND column_name='co_applicant_phone'
                    ) THEN
                        ALTER TABLE leads ADD COLUMN co_applicant_phone VARCHAR;
                    END IF;
                END $$;
            """))

            db.commit()

            logger.info("Co-borrower columns added successfully")
            return {"status": "success", "message": "Co-borrower columns added"}
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add co-borrower columns: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/admin/add-task-related-columns")
    async def add_task_related_columns(db: Session = Depends(get_db)):
        """Admin endpoint to add all required columns to tasks table.
        These columns are required for task creation including duplicate merge tasks."""
        try:
            # Add owner_id column (for task ownership)
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='tasks' AND column_name='owner_id'
                    ) THEN
                        ALTER TABLE tasks ADD COLUMN owner_id INTEGER REFERENCES users(id);
                    END IF;
                END $$;
            """))

            # Add related_type column
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='tasks' AND column_name='related_type'
                    ) THEN
                        ALTER TABLE tasks ADD COLUMN related_type VARCHAR(100);
                    END IF;
                END $$;
            """))

            # Add related_contact_name column
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='tasks' AND column_name='related_contact_name'
                    ) THEN
                        ALTER TABLE tasks ADD COLUMN related_contact_name VARCHAR(255);
                    END IF;
                END $$;
            """))

            # Add lead_id column if missing
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='tasks' AND column_name='lead_id'
                    ) THEN
                        ALTER TABLE tasks ADD COLUMN lead_id INTEGER REFERENCES leads(id);
                    END IF;
                END $$;
            """))

            # Add loan_id column if missing
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='tasks' AND column_name='loan_id'
                    ) THEN
                        ALTER TABLE tasks ADD COLUMN loan_id INTEGER REFERENCES loans(id);
                    END IF;
                END $$;
            """))

            # Create indexes
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_tasks_related_type ON tasks(related_type);
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_tasks_owner_id ON tasks(owner_id);
            """))

            db.commit()

            logger.info("Task columns added successfully")
            return {"status": "success", "message": "Task columns (owner_id, related_type, related_contact_name, lead_id, loan_id) added"}
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add task columns: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/admin/add-dre-columns")
    async def add_dre_columns(db: Session = Depends(get_db)):
        """Admin endpoint to add missing columns to extracted_data table"""
        try:
            # Add applied_at column
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='extracted_data' AND column_name='applied_at'
                    ) THEN
                        ALTER TABLE extracted_data ADD COLUMN applied_at TIMESTAMP;
                    END IF;
                END $$;
            """))

            # Add reviewed_by column
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='extracted_data' AND column_name='reviewed_by'
                    ) THEN
                        ALTER TABLE extracted_data ADD COLUMN reviewed_by INTEGER REFERENCES users(id);
                    END IF;
                END $$;
            """))

            # Add reviewed_at column
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='extracted_data' AND column_name='reviewed_at'
                    ) THEN
                        ALTER TABLE extracted_data ADD COLUMN reviewed_at TIMESTAMP;
                    END IF;
                END $$;
            """))

            db.commit()

            logger.info("DRE columns added successfully")
            return {"status": "success", "message": "DRE columns added successfully"}
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add DRE columns: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/admin/add-appraisal-columns")
    async def add_appraisal_columns(db: Session = Depends(get_db)):
        """Admin endpoint to add appraisal and loan columns"""
        try:
            columns_to_add = [
                ("loans", "appraisal_ordered_date", "TIMESTAMP"),
                ("loans", "appraisal_scheduled_date", "TIMESTAMP"),
                ("loans", "appraisal_completed_date", "TIMESTAMP"),
                ("loans", "appraisal_value", "DECIMAL(15, 2)"),
                ("loans", "lock_expiration_date", "TIMESTAMP"),
                ("loans", "property_city", "VARCHAR(100)"),
                ("loans", "property_state", "VARCHAR(50)"),
                ("loans", "property_zip", "VARCHAR(20)"),
                ("loans", "lender", "VARCHAR(255)"),
            ]

            for table, column, col_type in columns_to_add:
                # table, column, col_type are from hardcoded list above — not user input.
                # Validate identifiers and build DDL outside text().
                safe_table = _safe_identifier(table)
                safe_col = _safe_identifier(column)
                # col_type is from hardcoded list (TIMESTAMP, DECIMAL, VARCHAR) — safe to concatenate
                ddl_sql = (
                    "DO $$ BEGIN"
                    " IF NOT EXISTS ("
                    "   SELECT 1 FROM information_schema.columns"
                    "   WHERE table_name=" + "'" + table + "'"
                    "   AND column_name=" + "'" + column + "'"
                    " ) THEN"
                    "   ALTER TABLE " + safe_table + " ADD COLUMN " + safe_col + " " + col_type + ";"
                    " END IF;"
                    " END $$;"
                )
                db.execute(text(ddl_sql))

            db.commit()
            logger.info("Appraisal columns added successfully")
            return {"status": "success", "message": "Appraisal columns added successfully"}
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add appraisal columns: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/admin/rematch-extracted-data")
    async def rematch_extracted_data(db: Session = Depends(get_db)):
        """Admin endpoint to re-run entity matching on all pending extracted data

        This uses the improved matching logic (co-borrower, last name matching)
        on existing extracted data records that haven't been matched.
        """
        try:
            # Get all extracted data with needs_review status that have no match
            unmatched = db.query(ExtractedData).filter(
                ExtractedData.status.in_(["needs_review", "pending_review"]),
                or_(
                    ExtractedData.match_entity_id.is_(None),
                    ExtractedData.match_confidence < 0.5
                )
            ).all()

            logger.info(f"Found {len(unmatched)} unmatched extracted data records to rematch")

            matched_count = 0
            # Get the default user (loan officer) for matching context
            default_user = db.query(User).first()
            user_id = default_user.id if default_user else 1

            for extracted in unmatched:
                fields = extracted.fields or {}
                if not fields:
                    continue

                # Re-run matching with improved logic
                entity_match = match_entity(fields, db, user_id)

                if entity_match["entity_type"] and entity_match["confidence"] > 0.5:
                    extracted.match_entity_type = entity_match["entity_type"]
                    extracted.match_entity_id = entity_match["entity_id"]
                    extracted.match_confidence = entity_match["confidence"]
                    matched_count += 1
                    logger.info(f"Rematched extracted_data {extracted.id}: {entity_match['entity_type']} {entity_match['entity_id']} ({entity_match['confidence']:.2f})")

            db.commit()
            logger.info(f"Rematched {matched_count}/{len(unmatched)} extracted data records")

            return {
                "status": "success",
                "total_unmatched": len(unmatched),
                "newly_matched": matched_count,
                "message": f"Rematched {matched_count} of {len(unmatched)} records"
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to rematch extracted data: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/admin/create-dre-tables")
    async def create_dre_tables(db: Session = Depends(get_db)):
        """Admin endpoint to create Data Reconciliation Engine tables"""
        try:
            # Create incoming_data_events table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS incoming_data_events (
                    id SERIAL PRIMARY KEY,
                    source VARCHAR NOT NULL,
                    raw_text TEXT,
                    raw_html TEXT,
                    subject VARCHAR,
                    sender VARCHAR,
                    recipients JSON,
                    attachments JSON,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed BOOLEAN DEFAULT FALSE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # Create extracted_data table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS extracted_data (
                    id SERIAL PRIMARY KEY,
                    event_id INTEGER NOT NULL REFERENCES incoming_data_events(id),
                    category VARCHAR,
                    subcategory VARCHAR,
                    fields JSON NOT NULL,
                    match_entity_type VARCHAR,
                    match_entity_id INTEGER,
                    match_confidence FLOAT,
                    ai_confidence FLOAT,
                    status VARCHAR DEFAULT 'pending_review',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # Create ai_training_events table
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_training_events (
                    id SERIAL PRIMARY KEY,
                    extracted_data_id INTEGER NOT NULL REFERENCES extracted_data(id),
                    field_name VARCHAR NOT NULL,
                    original_value VARCHAR,
                    corrected_value VARCHAR,
                    label VARCHAR NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            db.commit()

            logger.info("DRE tables created successfully")
            return {
                "status": "success",
                "message": "Data Reconciliation Engine tables created",
                "tables": ["incoming_data_events", "extracted_data", "ai_training_events"]
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create DRE tables: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/admin/create-microsoft-oauth-table")
    async def create_microsoft_oauth_table(db: Session = Depends(get_db)):
        """Admin endpoint to create Microsoft OAuth tokens table"""
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS microsoft_oauth_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
                    access_token TEXT,
                    refresh_token TEXT,
                    token_expires_at TIMESTAMP,
                    email_address VARCHAR,
                    sync_enabled BOOLEAN DEFAULT TRUE,
                    last_sync_at TIMESTAMP,
                    sync_folder VARCHAR DEFAULT 'Inbox',
                    sync_frequency_minutes INTEGER DEFAULT 15,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            db.commit()

            logger.info("Microsoft OAuth tokens table created successfully")
            return {
                "status": "success",
                "message": "Microsoft OAuth tokens table created"
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create Microsoft OAuth tokens table: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/api/v1/loans/setup-team-members-table")
    async def create_loan_team_members_table(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
        """Create the loan_team_members table for custom team member assignments"""
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS loan_team_members (
                    id SERIAL PRIMARY KEY,
                    loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    role VARCHAR(100) NOT NULL,
                    email VARCHAR(255),
                    phone VARCHAR(50),
                    company VARCHAR(255),
                    license_number VARCHAR(100),
                    notes TEXT,
                    is_employee BOOLEAN DEFAULT FALSE,
                    user_id INTEGER REFERENCES users(id),
                    referral_partner_id INTEGER REFERENCES referral_partners(id),
                    is_new BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER REFERENCES users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_loan_team_members_loan_id ON loan_team_members(loan_id);
                CREATE INDEX IF NOT EXISTS idx_loan_team_members_referral_partner ON loan_team_members(referral_partner_id);
                CREATE INDEX IF NOT EXISTS idx_loan_team_members_user ON loan_team_members(user_id);
            """))
            db.commit()
            logger.info("loan_team_members table created successfully")
            return {"success": True, "message": "loan_team_members table created"}
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create loan_team_members table: {e}")
            return {"success": False, "error": "Internal server error"}


    @app.post("/admin/populate-loan-team-members")
    async def populate_loan_team_members(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """Admin endpoint to populate team members for loans in the user's organization."""
        try:
            # Team member data to assign
            team_members = {
                "processor": {"name": "Robert Garcia", "email": "robert.garcia@company.com"},
                "processor_assistant": {"name": "Amanda Foster", "email": "amanda.foster@company.com"},
                "underwriter": {"name": "Rachel Stevens", "email": "rachel.stevens@company.com"},
                "closer": {"name": "Lisa Wong", "email": "lisa.wong@company.com"},
                "loan_officer": {"name": "Timothy Loss", "email": "tloss@cmgfi.com"}
            }

            # Get loans scoped to user's organization
            loan_query = db.query(Loan)
            if current_user.organization_id:
                loan_query = loan_query.filter(Loan.organization_id == current_user.organization_id)
            loans = loan_query.all()

            updated_count = 0
            for loan in loans:
                # Update loan officer
                loan.loan_officer_name = team_members["loan_officer"]["name"]
                loan.loan_officer_email = team_members["loan_officer"]["email"]

                # Update processor
                loan.processor = team_members["processor"]["name"]
                loan.processor_email = team_members["processor"]["email"]

                # Update underwriter
                loan.underwriter = team_members["underwriter"]["name"]
                loan.underwriter_email = team_members["underwriter"]["email"]

                # Update closer
                loan.closer = team_members["closer"]["name"]
                loan.closer_email = team_members["closer"]["email"]

                updated_count += 1

            db.commit()

            logger.info(f"Updated {updated_count} loans with team members")
            return {
                "status": "success",
                "message": f"Updated {updated_count} loans with team members",
                "loans_updated": updated_count
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to populate loan team members: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    @app.post("/admin/create-zapier-api-key")
    async def create_zapier_api_key(db: Session = Depends(get_db)):
        """Admin endpoint to create the Zapier API key for integration"""
        try:
            # Get the first user (demo user) or create one
            user = db.query(User).first()
            if not user:
                logger.error("No users found in database")
                return JSONResponse(
                    status_code=500,
                    content={"status": "error", "message": "No users found. Please create a user first."}
                )

            # Check if the Zapier API key already exists - get from env or generate new
            import uuid
            import hashlib as _hashlib
            zapier_api_key = os.getenv("ZAPIER_API_KEY", str(uuid.uuid4()))
            existing_key = db.query(ApiKey).filter(ApiKey.name == "Zapier Integration").first()

            if existing_key:
                logger.info("Zapier API key already exists")
                return {
                    "status": "success",
                    "message": "Zapier API key already exists",
                    "key_prefix": existing_key.key_prefix or (existing_key.key[:8] if existing_key.key else "****"),
                    "user_email": user.email
                }

            # Create the API key — store only the hash, never plaintext
            zapier_key_hash = _hashlib.sha256(zapier_api_key.encode()).hexdigest()
            new_api_key = ApiKey(
                key=None,
                key_hash=zapier_key_hash,
                key_prefix=zapier_api_key[:8],
                name="Zapier Integration",
                user_id=user.id,
                organization_id=getattr(user, 'organization_id', None),
                is_active=True
            )

            db.add(new_api_key)
            db.commit()
            db.refresh(new_api_key)

            logger.info(f"Zapier API key created for user {user.id}")
            return {
                "status": "success",
                "message": "Zapier API key created successfully. Save this key — it will not be shown again.",
                "key": zapier_api_key,
                "user_email": user.email
            }
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create Zapier API key: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal server error"}
            )

    # ========================================================================
    # ADMIN STATS & USER MANAGEMENT (originally lines ~18902-19653)
    # ========================================================================

    @app.get("/api/v1/admin/stats")
    async def get_admin_stats(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Get admin dashboard statistics"""
        from utils.auth import require_admin
        require_admin(current_user)

        from datetime import datetime

        # Count users by role
        total_users = db.query(User).count()
        total_los = db.query(User).filter(User.role == 'loan_officer').count()
        total_realtors = db.query(User).filter(User.role == 'realtor').count()

        # Count leads and loans
        total_leads = 0
        total_loans = 0
        mtd_volume = 0

        try:
            # Try to get lead count
            lead_count = db.execute(text("SELECT COUNT(*) FROM leads")).scalar()
            total_leads = lead_count or 0
        except Exception as e:
            logger.error(f"Error fetching lead count in get_admin_stats: {e}")

        try:
            # Try to get loan count and MTD volume
            loan_count = db.execute(text("SELECT COUNT(*) FROM loans")).scalar()
            total_loans = loan_count or 0

            # MTD volume - sum of loan amounts funded this month
            mtd_result = db.execute(text("""
                SELECT COALESCE(SUM(loan_amount), 0)
                FROM loans
                WHERE status = 'funded'
                AND funded_at >= date_trunc('month', CURRENT_DATE)
            """)).scalar()
            mtd_volume = float(mtd_result or 0)
        except Exception as e:
            logger.error(f"Error fetching loan count/MTD volume in get_admin_stats: {e}")

        return {
            "total_users": total_users,
            "total_los": total_los,
            "total_realtors": total_realtors,
            "total_leads": total_leads,
            "total_loans": total_loans,
            "mtd_volume": mtd_volume
        }

    # Note: GET /api/v1/admin/users/roles is handled by user_creation_routes.py

    @app.get("/api/v1/admin/users")
    async def get_all_users(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Get all registered users (admin only)

        Multi-tenancy:
        - Platform admins (permission_role='admin') see all users
        - Site administrators see only users from their organization
        """
        from utils.auth import require_admin
        require_admin(current_user)

        # Check if platform admin (can see all users across all organizations)
        is_platform_admin = (
            current_user.permission_role == 'admin' or
            current_user.email == 'admin@perenniaai.com'
        )

        if is_platform_admin:
            # Platform admin sees all users
            users = db.query(User).order_by(User.created_at.desc()).all()
        else:
            # Site admin sees only users from their organization
            # Exclude platform admin from organization user lists
            query = db.query(User).filter(
                User.organization_id == current_user.organization_id,
                User.email != 'admin@perenniaai.com'  # Never show platform admin to org users
            )
            users = query.order_by(User.created_at.desc()).all()

        return [{
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "permission_role": user.permission_role,
            "is_active": user.is_active,
            "email_verified": user.email_verified,
            "onboarding_completed": user.onboarding_completed,
            "user_metadata": user.user_metadata,
            "created_at": user.created_at.isoformat() if user.created_at else None
        } for user in users]

    @app.patch("/api/v1/admin/users/{user_id}")
    @app.put("/api/v1/admin/users/{user_id}")
    async def update_user(
        user_id: int,
        updates: dict,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Update user (admin only) - supports both PUT and PATCH"""
        from utils.auth import require_admin
        require_admin(current_user)

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Update allowed fields
        allowed_fields = ['is_active', 'role', 'permission_role', 'email_verified', 'onboarding_completed']
        for field, value in updates.items():
            if field == 'full_name' and value:
                parts = str(value).strip().split(' ', 1)
                user.first_name = parts[0]
                user.last_name = parts[1] if len(parts) > 1 else ''
            elif field in allowed_fields:
                setattr(user, field, value)

        db.commit()
        db.refresh(user)

        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "permission_role": user.permission_role,
            "is_active": user.is_active,
            "email_verified": user.email_verified,
            "onboarding_completed": user.onboarding_completed,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }

    @app.post("/api/v1/admin/users")
    async def create_user(
        user_data: dict,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Create a new user (admin only)"""
        import secrets
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        email = user_data.get('email')
        password = user_data.get('password')

        # Handle both full_name and first_name/last_name formats
        full_name = user_data.get('full_name', '')
        if not full_name:
            first_name = user_data.get('first_name', '')
            last_name = user_data.get('last_name', '')
            full_name = f"{first_name} {last_name}".strip()

        role = user_data.get('role', 'loan_officer')
        is_active = user_data.get('is_active', True)
        phone = user_data.get('phone', '')
        nmls_id = user_data.get('nmls_id', '')

        if not email:
            raise HTTPException(status_code=400, detail="Email is required")

        # Check if email already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already in use")

        # Generate temporary password if not provided
        if not password:
            password = secrets.token_urlsafe(12)

        # Hash the password
        hashed_password = pwd_context.hash(password)

        # Create the user — split full_name into first/last columns
        _name_parts = (full_name or '').strip().split(' ', 1)
        new_user = User(
            email=email,
            hashed_password=hashed_password,
            first_name=_name_parts[0] if _name_parts else '',
            last_name=_name_parts[1] if len(_name_parts) > 1 else '',
            role=role,
            is_active=is_active,
            email_verified=False,
            onboarding_completed=False,
            organization_id=current_user.organization_id,
            phone=phone if hasattr(User, 'phone') else None,
            nmls_id=nmls_id if hasattr(User, 'nmls_id') else None
        )

        # Set phone and nmls_id if columns exist
        if phone and hasattr(new_user, 'phone'):
            new_user.phone = phone
        if nmls_id and hasattr(new_user, 'nmls_id'):
            new_user.nmls_id = nmls_id

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role,
            "is_active": new_user.is_active,
            "email_verified": new_user.email_verified,
            "onboarding_completed": new_user.onboarding_completed,
            "created_at": new_user.created_at.isoformat() if new_user.created_at else None,
            "temp_password": password if not user_data.get('password') else None  # Return temp password for admin to share
        }

    # Note: debug/user-deletion-blockers is defined below using _get_deletion_blockers helper

    @app.post("/api/v1/debug/create-test-user")
    async def debug_create_test_user(
        admin_key: str = None,
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to create a test user for deletion testing"""
        _verify_admin_key(admin_key)

        import random
        import string
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        # Generate unique email and secure random password
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        test_email = f"test-user-{random_suffix}@example.com"
        generated_password = secrets.token_urlsafe(16)

        # Create the user
        new_user = User(
            email=test_email,
            first_name="Test",
            last_name=f"User {random_suffix}",
            hashed_password=pwd_context.hash(generated_password),
            role="loan_officer",
            is_active=True
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "success": True,
            "message": f"Test user created with ID {new_user.id}",
            "user": {
                "id": new_user.id,
                "email": new_user.email,
                "full_name": new_user.full_name,
                "role": new_user.role
            },
            "temp_password": generated_password
        }


    @app.delete("/api/v1/debug/delete-user/{user_id}")
    async def debug_delete_user(
        user_id: int,
        admin_key: str = None,
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to delete user with admin_key protection"""
        _verify_admin_key(admin_key)

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user_email = user.email
        params = {"user_id": user_id}
        deleted_from = []
        errors = []

        # Direct cleanup - each query in its own try/except
        # Order matters - delete child tables first
        cleanup_queries = [
            # First delete wizard sessions that reference user profiles
            ("onboarding_wizard_sessions", "DELETE FROM onboarding_wizard_sessions WHERE user_profile_id IN (SELECT id FROM onboarding_user_profiles WHERE user_id = :user_id)"),
            # Then delete user profiles
            ("onboarding_user_profiles", "DELETE FROM onboarding_user_profiles WHERE user_id = :user_id"),
            # Delete scheduler child tables before scheduler resources
            ("scheduler_soft_holds", "DELETE FROM scheduler_soft_holds WHERE resource_id IN (SELECT id FROM scheduler_resources WHERE user_id = :user_id)"),
            ("scheduler_group_sessions", "DELETE FROM scheduler_group_sessions WHERE host_resource_id IN (SELECT id FROM scheduler_resources WHERE user_id = :user_id)"),
            ("scheduler_resources", "DELETE FROM scheduler_resources WHERE user_id = :user_id"),
            ("user_settings", "DELETE FROM user_settings WHERE user_id = :user_id"),
            ("notifications", "DELETE FROM notifications WHERE user_id = :user_id"),
            ("user_sessions", "DELETE FROM user_sessions WHERE user_id = :user_id"),
        ]

        for table_name, query in cleanup_queries:
            try:
                result = db.execute(text(query), params)
                deleted_from.append(f"{table_name}:{result.rowcount}")
                db.commit()
            except Exception as e:
                db.rollback()
                errors.append(f"{table_name}: {str(e)[:150]}")

        # Now try to delete the user
        try:
            db.execute(text("DELETE FROM users WHERE id = :user_id"), params)
            db.commit()
            logger.info(f"Debug delete: User {user_id} deleted. Cleaned: {deleted_from}")
            return {
                "success": True,
                "message": f"User {user_id} ({user_email}) deleted successfully",
                "cleaned_tables": deleted_from,
                "cleanup_errors": errors
            }
        except Exception as e:
            db.rollback()
            error_msg = str(e)
            logger.error(f"Debug delete failed for user {user_id}: {error_msg}. Cleaned: {deleted_from}. Errors: {errors}")

            # Return detailed error info
            return {
                "success": False,
                "error": error_msg[:500],
                "cleaned_tables": deleted_from,
                "cleanup_errors": errors,
                "user_id": user_id,
                "user_email": user_email
            }


    # Note: GET /api/v1/admin/users/{user_id}/deletion-blockers is defined below using _get_deletion_blockers helper

    @app.delete("/api/v1/admin/users/{user_id}")
    async def delete_user(
        user_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Delete user (admin only) - OPTIMIZED: only cleans tables with actual data"""
        # Prevent self-deletion
        if user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user_email = user.email
        params = {"user_id": user_id}

        try:
            # =========================================================================
            # STEP 1: Find all tables that actually reference this user
            # =========================================================================
            tables_with_data = []
            try:
                fk_query = """
                    SELECT tc.table_name, kcu.column_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND ccu.table_name = 'users'
                        AND tc.table_schema = 'public'
                        AND tc.table_name != 'users'
                """
                result = db.execute(text(fk_query))
                for table_name, column_name in result.fetchall():
                    try:
                        safe_table = _safe_identifier(table_name)
                        safe_col = _safe_identifier(column_name)
                        count_sql = "SELECT COUNT(*) FROM " + safe_table + " WHERE " + safe_col + " = :user_id"
                        count = db.execute(text(count_sql), params).scalar()
                        if count and count > 0:
                            tables_with_data.append((table_name, column_name, count))
                    except Exception as e:
                        logger.error(f"Error scanning FK table {table_name}.{column_name} for user {user_id}: {e}")
            except Exception as e:
                logger.warning(f"FK scan failed: {e}")

            logger.info(f"User {user_id} cleanup: {len(tables_with_data)} tables have data")

            # =========================================================================
            # STEP 2: Handle tables with special cascade requirements (order matters)
            # =========================================================================
            cascade_order = [
                # Child tables that must be deleted before their parents
                ("onboarding_wizard_sessions", "user_profile_id", "SELECT id FROM onboarding_user_profiles WHERE user_id = :user_id"),
                ("scheduler_soft_holds", "resource_id", "SELECT id FROM scheduler_resources WHERE user_id = :user_id"),
                ("scheduler_group_sessions", "host_resource_id", "SELECT id FROM scheduler_resources WHERE user_id = :user_id"),
                ("ci_realtime_suggestions", "session_id", "SELECT id FROM ci_realtime_sessions WHERE agent_user_id = :user_id"),
                ("ci_call_analyses", "recording_id", "SELECT id FROM ci_call_recordings WHERE agent_user_id = :user_id"),
                ("ci_transcription_segments", "transcription_id", "SELECT id FROM ci_call_transcriptions WHERE recording_id IN (SELECT id FROM ci_call_recordings WHERE agent_user_id = :user_id)"),
                ("ci_call_transcriptions", "recording_id", "SELECT id FROM ci_call_recordings WHERE agent_user_id = :user_id"),
                ("video_meeting_participants", "meeting_id", "SELECT id FROM video_meeting_recordings WHERE host_user_id = :user_id"),
                ("video_project_scenes", "project_id", "SELECT id FROM video_projects WHERE user_id = :user_id"),
                ("video_avatar_jobs", "avatar_id", "SELECT id FROM video_avatar_profiles WHERE user_id = :user_id"),
                ("dialer_session_tasks", "session_id", "SELECT id FROM dialer_sessions WHERE agent_id = :user_id"),
            ]

            for child_table, child_col, parent_subquery in cascade_order:
                try:
                    safe_ct = _safe_identifier(child_table)
                    safe_cc = _safe_identifier(child_col)
                    cascade_sql = "DELETE FROM " + safe_ct + " WHERE " + safe_cc + " IN (" + parent_subquery + ")"
                    db.execute(text(cascade_sql), params)
                except Exception as e:
                    logger.error(f"Error cascading delete from {child_table}.{child_col} for user {user_id}: {e}")

            # =========================================================================
            # STEP 3: Clean only tables that have data for this user
            # =========================================================================
            cleaned = 0
            for table_name, column_name, count in tables_with_data:
                try:
                    safe_tbl = _safe_identifier(table_name)
                    safe_col = _safe_identifier(column_name)
                    # Try UPDATE to NULL first (for nullable columns)
                    update_null_sql = "UPDATE " + safe_tbl + " SET " + safe_col + " = NULL WHERE " + safe_col + " = :user_id"
                    db.execute(text(update_null_sql), params)
                    cleaned += 1
                except Exception as update_e:
                    # If UPDATE fails (NOT NULL constraint), try DELETE
                    try:
                        delete_sql = "DELETE FROM " + safe_tbl + " WHERE " + safe_col + " = :user_id"
                        db.execute(text(delete_sql), params)
                        cleaned += 1
                    except Exception as del_e:
                        logger.warning(f"Could not clean {table_name}.{column_name}: {del_e}")

            # =========================================================================
            # STEP 4: Delete the user
            # =========================================================================
            db.execute(text("DELETE FROM users WHERE id = :user_id"), params)
            db.commit()

            logger.info(f"User {user_id} deleted by user {current_user.id} - cleaned {cleaned} tables")
            return {"message": "User deleted successfully", "tables_cleaned": cleaned}

        except Exception as e:
            db.rollback()
            error_msg = str(e)
            logger.error(f"Delete user {user_id} failed: {error_msg}")

            # Extract blocking table from FK error
            if "violates foreign key constraint" in error_msg:
                import re
                match = re.search(r'on table "(\w+)"', error_msg)
                if match:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Cannot delete: still referenced by '{match.group(1)}'"
                    )
            raise HTTPException(status_code=500, detail="Delete failed due to existing references. Check server logs.")


    @app.post("/api/v1/admin/cleanup-sample-users")
    async def cleanup_sample_users(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Delete sample/demo users (admin only)

        This endpoint identifies and deletes demo/sample users that match known patterns:
        - Users with @company.com email (from demo seed script)
        - Users with names matching known demo users (Sarah Johnson, Michael Chen, etc.)

        Protected users (will NOT be deleted):
        - admin@perenniaai.com (platform admin)
        - Current user
        - Users with real activity (loans, leads, etc.)
        """
        # Admin check
        if not current_user.is_admin and current_user.permission_role != 'admin':
            raise HTTPException(status_code=403, detail="Admin access required")

        # Known demo/sample user patterns
        demo_email_patterns = ['@company.com']  # From seed_demo_people.py
        demo_names = [
            'Sarah Johnson', 'Michael Chen', 'Emily Davis', 'James Wilson',
            'Sarah Mitchell', 'Jennifer Rodriguez', 'David Thompson', 'Lisa Wong',
            'Robert Garcia', 'Amanda Foster', 'Kevin Park', 'Rachel Stevens',
            'Marcus Johnson', 'Emily Patterson', 'Brandon Lee', 'Samantha Brooks',
            'Tyler Martinez', 'Olivia Anderson', 'Admin User'
        ]

        protected_emails = ['admin@perenniaai.com', current_user.email]

        try:
            # Find sample users
            sample_users = []

            # Find users with demo email patterns
            for pattern in demo_email_patterns:
                users = db.query(User).filter(
                    User.email.like(f'%{pattern}'),
                    ~User.email.in_(protected_emails)
                ).all()
                sample_users.extend(users)

            # Find users with demo names (but not protected emails)
            for name in demo_names:
                users = db.query(User).filter(
                    User.full_name == name,
                    ~User.email.in_(protected_emails)
                ).all()
                for user in users:
                    if user not in sample_users:
                        sample_users.append(user)

            if not sample_users:
                return {
                    "message": "No sample users found to clean up",
                    "deleted_count": 0,
                    "deleted_users": []
                }

            deleted_users = []
            errors = []

            for user in sample_users:
                try:
                    user_info = {"id": user.id, "email": user.email, "name": user.full_name}
                    params = {"user_id": user.id}

                    # Clean up related data first
                    cleanup_tables = [
                        ('process_tasks', 'user_id'),
                        ('process_milestones', 'user_id'),
                        ('process_roles', 'user_id'),
                        ('onboarding_progress', 'user_id'),
                        ('sessions', 'user_id'),
                        ('loan_activities', 'user_id'),
                    ]

                    for table_name, column_name in cleanup_tables:
                        try:
                            cleanup_sql = "DELETE FROM " + _safe_identifier(table_name) + " WHERE " + _safe_identifier(column_name) + " = :user_id"
                            db.execute(text(cleanup_sql), params)
                        except Exception as e:
                            logger.error(f"Error cleaning up {table_name}.{column_name} for sample user deletion: {e}")

                    # Delete the user
                    db.execute(text("DELETE FROM users WHERE id = :user_id"), params)
                    deleted_users.append(user_info)

                except Exception as e:
                    errors.append({"user": user.email, "error": "Internal server error"[:100]})

            db.commit()

            logger.info(f"Sample user cleanup by user {current_user.id}: {len(deleted_users)} deleted")

            return {
                "message": f"Cleaned up {len(deleted_users)} sample users",
                "deleted_count": len(deleted_users),
                "deleted_users": deleted_users,
                "errors": errors if errors else None
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Sample user cleanup failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    async def _get_deletion_blockers(user_id: int, db: Session):
        """Helper function to check deletion blockers."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        blockers = []

        # Query all tables that reference users
        try:
            fk_query = """
                SELECT
                    tc.table_name,
                    kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND ccu.table_name = 'users'
                    AND tc.table_schema = 'public'
            """
            result = db.execute(text(fk_query))
            fk_refs = result.fetchall()

            for table_name, column_name in fk_refs:
                if table_name == 'users':
                    continue
                try:
                    count_query = f"SELECT COUNT(*) FROM {_safe_identifier(table_name)} WHERE {_safe_identifier(column_name)} = :user_id"
                    count_result = db.execute(text(count_query), {"user_id": user_id}).scalar()
                    if count_result > 0:
                        blockers.append({
                            "table": table_name,
                            "column": column_name,
                            "count": count_result
                        })
                except Exception as e:
                    pass  # Table might not exist

        except Exception as e:
            return {"error": "Internal server error", "blockers": []}

        return {
            "user_id": user_id,
            "user_email": user.email,
            "blockers": blockers,
            "total_blocking_records": sum(b["count"] for b in blockers)
        }


    @app.get("/api/v1/admin/users/{user_id}/deletion-blockers")
    async def check_user_deletion_blockers(
        user_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Check what tables/records are blocking user deletion (requires auth)."""
        return await _get_deletion_blockers(user_id, db)


    @app.get("/api/v1/debug/user-deletion-blockers/{user_id}")
    async def debug_user_deletion_blockers(
        user_id: int,
        db: Session = Depends(get_db)
    ):
        """Check what tables/records are blocking user deletion (public debug endpoint)."""
        return await _get_deletion_blockers(user_id, db)

    # ========================================================================
    # ADMIN DATA ENDPOINTS (originally lines ~23040-23402)
    # ========================================================================

    @app.get("/api/v1/admin/loan-check")
    async def check_loan_status(
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Check loan and user status for debugging."""
        _verify_admin_key(migration_key)

        try:
            # Get all users using raw SQL
            users_result = db.execute(text("SELECT id, email, organization_id FROM users")).fetchall()
            user_info = [{"id": u[0], "email": u[1], "org_id": u[2]} for u in users_result]

            # Get loan stats using raw SQL
            total_result = db.execute(text("SELECT COUNT(*) FROM loans")).fetchone()
            total_loans = total_result[0] if total_result else 0

            orphan_result = db.execute(text("SELECT COUNT(*) FROM loans WHERE organization_id IS NULL")).fetchone()
            orphan_loans = orphan_result[0] if orphan_result else 0

            # Count loans without loan_officer_id
            no_lo_result = db.execute(text("SELECT COUNT(*) FROM loans WHERE loan_officer_id IS NULL")).fetchone()
            no_lo_loans = no_lo_result[0] if no_lo_result else 0

            # Get sample loans using raw SQL - include loan_officer_id
            sample_result = db.execute(
                text("SELECT id, loan_number, borrower_name, organization_id, loan_officer_id FROM loans LIMIT 5")
            ).fetchall()
            loan_info = [{"id": l[0], "loan_number": l[1], "borrower": l[2], "org_id": l[3], "lo_id": l[4]} for l in sample_result]

            # Get task assignments to understand multi-tenancy
            task_summary = db.execute(text("""
                SELECT u.email, COUNT(*) as count
                FROM ai_tasks t
                LEFT JOIN users u ON u.id = t.assigned_to_id
                GROUP BY u.email, t.assigned_to_id
            """)).fetchall()
            task_info = [{"email": t[0], "count": t[1]} for t in task_summary]

            # Get sample AI tasks
            sample_ai_tasks = db.execute(text("""
                SELECT t.id, t.assigned_to_id, u.email, t.title
                FROM ai_tasks t
                LEFT JOIN users u ON u.id = t.assigned_to_id
                LIMIT 10
            """)).fetchall()
            ai_task_samples = [{"id": t[0], "assigned_to_id": t[1], "email": t[2], "title": t[3][:50] if t[3] else None} for t in sample_ai_tasks]

            # Get regular tasks summary
            regular_task_summary = db.execute(text("""
                SELECT u.email, COUNT(*) as count
                FROM tasks t
                LEFT JOIN users u ON u.id = t.owner_id
                GROUP BY u.email, t.owner_id
            """)).fetchall()
            regular_task_info = [{"email": t[0], "count": t[1]} for t in regular_task_summary]

            # Get sample regular tasks
            sample_tasks = db.execute(text("""
                SELECT t.id, t.owner_id, u.email, t.title, t.status
                FROM tasks t
                LEFT JOIN users u ON u.id = t.owner_id
                LIMIT 20
            """)).fetchall()
            task_samples = [{"id": t[0], "owner_id": t[1], "email": t[2], "title": t[3][:50] if t[3] else None, "status": t[4]} for t in sample_tasks]

            # Count workflow task instances
            workflow_tasks = db.execute(text("""
                SELECT COUNT(*) FROM workflow_task_instances
            """)).fetchone()
            workflow_count = workflow_tasks[0] if workflow_tasks else 0

            return {
                "users": user_info,
                "total_loans": total_loans,
                "orphan_loans": orphan_loans,
                "no_loan_officer": no_lo_loans,
                "sample_loans": loan_info,
                "ai_tasks_by_user": task_info,
                "ai_task_samples": ai_task_samples,
                "regular_tasks_by_user": regular_task_info,
                "regular_task_samples": task_samples,
                "workflow_task_instances_count": workflow_count
            }
        except Exception as e:
            logger.error(f"Loan check failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.get("/api/v1/admin/debug-data")
    async def debug_data(
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to check data isolation."""
        _verify_admin_key(migration_key)

        try:
            # Check loans
            loans_result = db.execute(text("""
                SELECT loan_officer_id, organization_id, COUNT(*) as count
                FROM loans
                GROUP BY loan_officer_id, organization_id
            """)).fetchall()
            loans_by_owner = [{"lo_id": r[0], "org_id": r[1], "count": r[2]} for r in loans_result]

            # Check tasks
            tasks_result = db.execute(text("""
                SELECT assigned_to_id, COUNT(*) as count
                FROM ai_tasks
                GROUP BY assigned_to_id
            """)).fetchall()
            tasks_by_user = [{"user_id": r[0], "count": r[1]} for r in tasks_result]

            # Check users
            users_result = db.execute(text("SELECT id, email, organization_id FROM users")).fetchall()
            users = [{"id": r[0], "email": r[1], "org_id": r[2]} for r in users_result]

            return {
                "loans_by_owner": loans_by_owner,
                "tasks_by_user": tasks_by_user,
                "users": users
            }
        except Exception as e:
            return {"error": "Internal server error"}


    @app.get("/api/v1/admin/task-check")
    async def task_check(
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to check task assignments and multi-tenancy."""
        _verify_admin_key(migration_key)

        try:
            # Check all tasks with their assignments
            tasks_result = db.execute(text("""
                SELECT
                    t.id, t.title, t.assigned_to_id,
                    u.email as assigned_to_email,
                    l.loan_number,
                    t.created_at
                FROM ai_tasks t
                LEFT JOIN users u ON u.id = t.assigned_to_id
                LEFT JOIN loans l ON l.id = t.loan_id
                ORDER BY t.created_at DESC
                LIMIT 50
            """)).fetchall()

            tasks = [
                {
                    "id": r[0],
                    "title": r[1][:50] if r[1] else None,
                    "assigned_to_id": r[2],
                    "assigned_to_email": r[3],
                    "loan_number": r[4],
                    "created_at": r[5].isoformat() if r[5] else None
                }
                for r in tasks_result
            ]

            # Summary by user
            summary_result = db.execute(text("""
                SELECT u.email, COUNT(*) as count
                FROM ai_tasks t
                LEFT JOIN users u ON u.id = t.assigned_to_id
                GROUP BY u.email, t.assigned_to_id
            """)).fetchall()
            summary = [{"email": r[0], "count": r[1]} for r in summary_result]

            return {
                "total_tasks": len(tasks),
                "summary_by_user": summary,
                "recent_tasks": tasks[:20]
            }
        except Exception as e:
            return {"error": "Internal server error"}


    @app.delete("/api/v1/admin/clear-imported-loans")
    async def clear_imported_loans(
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Clear loans that were imported (have IMP- prefix or Unknown borrower)."""
        _verify_admin_key(migration_key)

        try:
            result = db.execute(text("""
                DELETE FROM loans
                WHERE loan_number LIKE 'IMP-%' OR borrower_name = 'Unknown'
            """))
            deleted = result.rowcount
            db.commit()
            return {"status": "success", "deleted": deleted}
        except Exception as e:
            logger.error(f"Clear imported loans failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/admin/import-loans")
    async def admin_import_loans(
        file: UploadFile = File(...),
        migration_key: str = Form(...),
        user_email: str = Form("tloss@cmgfi.com"),
        db: Session = Depends(get_db)
    ):
        """Import loans from Excel file (admin only, protected by migration key)."""
        _verify_admin_key(migration_key)

        import pandas as pd
        import io

        try:
            # Read the file
            contents = await file.read()
            if file.filename.endswith('.xlsx'):
                df = pd.read_excel(io.BytesIO(contents))
            else:
                df = pd.read_csv(io.BytesIO(contents))

            # Get user's organization
            user_result = db.execute(
                text("SELECT id, organization_id FROM users WHERE email = :email"),
                {"email": user_email}
            ).fetchone()

            if not user_result:
                raise HTTPException(status_code=404, detail=f"User {user_email} not found")

            user_id = user_result[0]
            org_id = user_result[1]

            # Import the field mapping service
            from field_mapping_service import auto_map_fields

            # Get column mappings
            source_columns = list(df.columns)
            mapping_results = auto_map_fields(source_columns, min_confidence=0.7)

            # Get actual columns in loans table
            columns_result = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'loans'
            """)).fetchall()
            existing_columns = {row[0] for row in columns_result}

            # Map column names for insertion - only include existing columns
            column_map = {}
            skipped_columns = []
            for result in mapping_results:
                if result.crm_field and result.crm_field != 'skip':
                    if result.crm_field in existing_columns:
                        column_map[result.excel_column] = result.crm_field
                    else:
                        skipped_columns.append(result.crm_field)

            successful = 0
            failed = 0
            errors = []

            # Create a mapping from target field to source column for name/number handling
            all_field_map = {}
            for result in mapping_results:
                if result.crm_field:
                    all_field_map[result.crm_field] = result.excel_column

            for idx, row in df.iterrows():
                try:
                    # Build INSERT statement dynamically
                    mapped_values = {}
                    for source_col, target_col in column_map.items():
                        value = row.get(source_col)
                        if pd.notna(value):
                            mapped_values[target_col] = value

                    if not mapped_values:
                        continue

                    # Add organization_id
                    mapped_values['organization_id'] = org_id

                    # Handle loan_number - get from original mapping or "File Name" column
                    if 'loan_number' not in mapped_values:
                        # Check for explicit loan_number mapping
                        if 'loan_number' in all_field_map:
                            ln_col = all_field_map['loan_number']
                            ln_val = row.get(ln_col)
                            if pd.notna(ln_val):
                                mapped_values['loan_number'] = str(ln_val)
                        # Fall back to file_name mapping (often contains loan number)
                        if 'loan_number' not in mapped_values and 'file_name' in all_field_map:
                            fn_col = all_field_map['file_name']
                            fn_val = row.get(fn_col)
                            if pd.notna(fn_val):
                                mapped_values['loan_number'] = str(fn_val)
                        # Also try "File Name" column directly
                        if 'loan_number' not in mapped_values and 'File Name' in row.index:
                            fn_val = row.get('File Name')
                            if pd.notna(fn_val):
                                mapped_values['loan_number'] = str(fn_val)
                        # Generate if still missing
                        if 'loan_number' not in mapped_values:
                            import uuid
                            mapped_values['loan_number'] = f"IMP-{uuid.uuid4().hex[:8].upper()}"

                    # Handle borrower_name - combine first/last from original data
                    if 'borrower_name' not in mapped_values:
                        first = ''
                        last = ''
                        if 'borrower_first_name' in all_field_map:
                            fn_col = all_field_map['borrower_first_name']
                            fn_val = row.get(fn_col)
                            if pd.notna(fn_val):
                                first = str(fn_val)
                        if 'borrower_last_name' in all_field_map:
                            ln_col = all_field_map['borrower_last_name']
                            ln_val = row.get(ln_col)
                            if pd.notna(ln_val):
                                last = str(ln_val)
                        if first or last:
                            mapped_values['borrower_name'] = f"{first} {last}".strip()
                        else:
                            mapped_values['borrower_name'] = 'Unknown'

                    # Ensure amount is set
                    if 'amount' not in mapped_values:
                        mapped_values['amount'] = 0

                    # Validate column names to prevent injection via field mappings
                    safe_cols = [_safe_identifier(k) for k in mapped_values.keys()]
                    columns = ', '.join(safe_cols)
                    placeholders = ', '.join([':' + k for k in mapped_values.keys()])

                    insert_sql = "INSERT INTO loans (" + columns + ") VALUES (" + placeholders + ")"
                    db.execute(text(insert_sql), mapped_values)
                    successful += 1
                except Exception as e:
                    failed += 1
                    if len(errors) < 5:
                        errors.append(f"Row {idx}: {str(e)[:100]}")

            db.commit()

            return {
                "status": "success",
                "total_rows": len(df),
                "successful": successful,
                "failed": failed,
                "errors": errors if errors else None,
                "fields_mapped": len(column_map),
                "skipped_columns": skipped_columns[:10] if skipped_columns else None,
                "organization_id": org_id
            }
        except Exception as e:
            logger.error(f"Admin import loans failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # ========================================================================
    # CLEAR SALESFORCE-IMPORTED DATA
    # ========================================================================

    @app.post("/api/v1/admin/clear-salesforce-data")
    async def clear_salesforce_imported_data(
        dry_run: bool = True,
        admin_key: str = Query(None),
        db: Session = Depends(get_db),
    ):
        """
        Delete all leads and loans that were imported from Salesforce
        (records with a non-null salesforce_id). Nullifies FK references
        in child tables before deleting to avoid constraint violations.

        Pass dry_run=false to actually delete. Default is dry_run=true (preview only).
        Requires ADMIN_API_KEY.
        """
        _verify_admin_key(admin_key)

        try:
            # --- Count what will be deleted ---
            sf_lead_ids = db.execute(text(
                "SELECT id FROM leads WHERE salesforce_id IS NOT NULL"
            )).fetchall()
            sf_loan_ids = db.execute(text(
                "SELECT id FROM loans WHERE salesforce_id IS NOT NULL"
            )).fetchall()

            lead_ids = [row[0] for row in sf_lead_ids]
            loan_ids = [row[0] for row in sf_loan_ids]

            result = {
                "dry_run": dry_run,
                "sf_leads_found": len(lead_ids),
                "sf_loans_found": len(loan_ids),
                "deleted_leads": 0,
                "deleted_loans": 0,
                "child_records_cleaned": {},
            }

            if not lead_ids and not loan_ids:
                result["message"] = "No Salesforce-imported records found"
                return result

            if dry_run:
                result["message"] = (
                    f"DRY RUN: Would delete {len(lead_ids)} leads and "
                    f"{len(loan_ids)} loans imported from Salesforce. "
                    f"Set dry_run=false to execute."
                )
                return result

            # --- Dynamically find ALL FK constraints referencing leads/loans ---
            fk_refs = db.execute(text("""
                SELECT
                    tc.table_name AS child_table,
                    kcu.column_name AS child_column,
                    ccu.table_name AS parent_table
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                    AND tc.table_schema = ccu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND ccu.table_name IN ('leads', 'loans')
                ORDER BY ccu.table_name, tc.table_name
            """)).fetchall()

            lead_refs = [(r[0], r[1]) for r in fk_refs if r[2] == 'leads']
            loan_refs = [(r[0], r[1]) for r in fk_refs if r[2] == 'loans']

            lead_subq = "SELECT id FROM leads WHERE salesforce_id IS NOT NULL"
            loan_subq = "SELECT id FROM loans WHERE salesforce_id IS NOT NULL"

            cleaned = {}

            # Clean all lead FK references
            if lead_ids:
                for child_tbl, child_col in lead_refs:
                    try:
                        r = db.execute(text(
                            f'UPDATE "{child_tbl}" SET "{child_col}" = NULL '
                            f'WHERE "{child_col}" IN ({lead_subq})'
                        ))
                        if r.rowcount > 0:
                            cleaned[f"{child_tbl}.{child_col}"] = r.rowcount
                    except Exception:
                        db.rollback()
                        # Column might be NOT NULL — delete child rows instead
                        try:
                            r = db.execute(text(
                                f'DELETE FROM "{child_tbl}" '
                                f'WHERE "{child_col}" IN ({lead_subq})'
                            ))
                            if r.rowcount > 0:
                                cleaned[f"{child_tbl}.{child_col} (deleted)"] = r.rowcount
                        except Exception as e2:
                            logger.debug(f"Skipping {child_tbl}.{child_col}: {e2}")
                            db.rollback()

            # Clean all loan FK references
            if loan_ids:
                for child_tbl, child_col in loan_refs:
                    try:
                        r = db.execute(text(
                            f'UPDATE "{child_tbl}" SET "{child_col}" = NULL '
                            f'WHERE "{child_col}" IN ({loan_subq})'
                        ))
                        if r.rowcount > 0:
                            cleaned[f"{child_tbl}.{child_col}"] = r.rowcount
                    except Exception:
                        db.rollback()
                        try:
                            r = db.execute(text(
                                f'DELETE FROM "{child_tbl}" '
                                f'WHERE "{child_col}" IN ({loan_subq})'
                            ))
                            if r.rowcount > 0:
                                cleaned[f"{child_tbl}.{child_col} (deleted)"] = r.rowcount
                        except Exception as e2:
                            logger.debug(f"Skipping {child_tbl}.{child_col}: {e2}")
                            db.rollback()

            # --- Delete MUM clients linked to SF ---
            try:
                r = db.execute(text(
                    "DELETE FROM mum_clients WHERE salesforce_id IS NOT NULL"
                ))
                if r.rowcount > 0:
                    cleaned["mum_clients"] = r.rowcount
            except Exception as e:
                logger.debug(f"Skipping mum_clients cleanup: {e}")
                db.rollback()

            # --- Delete the SF-imported records ---
            deleted_loans = db.execute(text(
                "DELETE FROM loans WHERE salesforce_id IS NOT NULL"
            )).rowcount

            deleted_leads = db.execute(text(
                "DELETE FROM leads WHERE salesforce_id IS NOT NULL"
            )).rowcount

            db.commit()

            result["deleted_leads"] = deleted_leads
            result["deleted_loans"] = deleted_loans
            result["child_records_cleaned"] = cleaned
            result["message"] = (
                f"Deleted {deleted_leads} SF-imported leads and "
                f"{deleted_loans} SF-imported loans. Ready for re-import."
            )

            logger.info(
                f"Admin cleared SF data: "
                f"{deleted_leads} leads, {deleted_loans} loans"
            )

            return result

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error clearing SF data: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/api/v1/admin/clear-all-crm-data")
    async def clear_all_crm_data(
        admin_key: str = Query(None),
        db: Session = Depends(get_db),
    ):
        """
        Delete ALL CRM data: leads, loans, MUM clients, tasks, documents,
        smart docs, activities, etc. Keeps user accounts and settings.
        """
        _verify_admin_key(admin_key)

        try:
            cleaned = {}

            # Order matters: delete child tables first, then parent tables.
            # Use information_schema to find all tables with FK refs to leads/loans,
            # then delete everything in the right order.

            # Phase 1: Delete from tables that reference leads or loans
            fk_refs = db.execute(text("""
                SELECT DISTINCT tc.table_name, kcu.column_name, ccu.table_name AS parent
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                    AND tc.table_schema = ccu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND ccu.table_name IN ('leads', 'loans')
            """)).fetchall()

            # Null out or delete child references
            # Values come from information_schema but validate with _safe_identifier
            # as defense-in-depth
            for child_tbl, child_col, parent_tbl in fk_refs:
                try:
                    safe_tbl = _safe_identifier(child_tbl)
                    safe_col = _safe_identifier(child_col)
                    r = db.execute(text(
                        f'UPDATE {safe_tbl} SET {safe_col} = NULL'
                    ))
                    if r.rowcount > 0:
                        cleaned[f"{child_tbl}.{child_col} nulled"] = r.rowcount
                except ValueError:
                    logger.warning(f"Blocked invalid identifier from information_schema: {child_tbl}.{child_col}")
                except Exception:
                    db.rollback()
                    try:
                        safe_tbl = _safe_identifier(child_tbl)
                        r = db.execute(text("DELETE FROM " + safe_tbl))
                        if r.rowcount > 0:
                            cleaned[f"{child_tbl} deleted"] = r.rowcount
                    except ValueError:
                        logger.warning(f"Blocked invalid identifier: {child_tbl}")
                    except Exception:
                        db.rollback()

            # Phase 2: Delete from specific CRM tables
            tables_to_clear = [
                "mum_clients",
                # Smart docs (current model table names)
                "smart_documents",
                "doc_policy_events",
                "smart_document_requests",
                "client_reminder_settings",
                # Smart docs (legacy table names, may still exist)
                "smart_doc_requests",
                "smart_doc_items",
                "needs_list_items",
                "needs_lists",
                "document_requests",
                "documents",
                "tasks",
                "ai_tasks",
                "activities",
                "sla_milestones",
                "workflow_task_instances",
                "workflow_executions",
                "stage_history",
                "compliance_alerts",
                "loan_fees",
                "disclosure_events",
                "data_reconciliation_pairs",
                "referral_commissions",
            ]

            for tbl in tables_to_clear:
                try:
                    r = db.execute(text("DELETE FROM " + _safe_identifier(tbl)))
                    if r.rowcount > 0:
                        cleaned[tbl] = r.rowcount
                except Exception:
                    db.rollback()

            # Phase 3: Delete loans then leads (parents)
            deleted_loans = db.execute(text("DELETE FROM loans")).rowcount
            cleaned["loans"] = deleted_loans

            deleted_leads = db.execute(text("DELETE FROM leads")).rowcount
            cleaned["leads"] = deleted_leads

            db.commit()

            logger.info(f"Admin cleared ALL CRM data: {cleaned}")

            return {
                "status": "success",
                "message": f"Cleared all CRM data: {deleted_leads} leads, {deleted_loans} loans, plus related records.",
                "details": cleaned,
            }

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error clearing all CRM data: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

    # ========================================================================
    # DEMO DATA SEEDING & CLEANUP
    # ========================================================================

    @app.post("/api/v1/admin/seed-demo-data")
    async def seed_demo_data_endpoint(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Seed realistic demo data into the current user's organization.
        Admin/site_admin/platform_admin only.
        """
        if not hasattr(current_user, 'role') or current_user.role not in ('admin', 'site_admin', 'platform_admin'):
            raise HTTPException(status_code=403, detail="Admin role required to seed demo data")

        try:
            from scripts.seed_demo_org import seed_demo_data
            result = seed_demo_data(
                db,
                organization_id=current_user.organization_id,
                user_id=current_user.id,
            )
            return {
                "status": "ok",
                "message": f"Seeded {result['total']} demo entities",
                **result,
            }
        except Exception as e:
            logger.exception("Demo data seeding failed")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.delete("/api/v1/admin/seed-demo-data")
    async def clear_demo_data_endpoint(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Remove all demo-seeded data from the current user's organization.
        Admin/site_admin/platform_admin only.
        """
        if not hasattr(current_user, 'role') or current_user.role not in ('admin', 'site_admin', 'platform_admin'):
            raise HTTPException(status_code=403, detail="Admin role required to clear demo data")

        try:
            from scripts.seed_demo_org import clear_demo_data
            result = clear_demo_data(
                db,
                organization_id=current_user.organization_id,
            )
            return {
                "status": "ok",
                "message": f"Removed {result['total']} demo entities",
                **result,
            }
        except Exception as e:
            logger.exception("Demo data cleanup failed")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/api/v1/admin/crm-data-counts")
    async def get_crm_data_counts(
        admin_key: str = Query(None),
        db: Session = Depends(get_db),
    ):
        """Quick count of all CRM data tables for verification."""
        _verify_admin_key(admin_key)

        tables = [
            "leads", "loans", "mum_clients", "tasks", "documents",
            "smart_documents", "smart_document_requests", "doc_policy_events",
            "client_reminder_settings",
            "smart_doc_requests", "smart_doc_items", "needs_list_items",
            "needs_lists", "document_requests", "activities",
            "stage_history", "workflow_task_instances", "sla_milestones",
            "compliance_alerts", "referral_commissions",
        ]
        counts = {}
        for tbl in tables:
            try:
                r = db.execute(text("SELECT COUNT(*) FROM " + _safe_identifier(tbl))).scalar()
                counts[tbl] = r
            except Exception:
                db.rollback()
                counts[tbl] = "(table not found)"

        total = sum(v for v in counts.values() if isinstance(v, int))
        return {"counts": counts, "total_rows": total}

    @app.post("/api/v1/admin/seed-demo-account")
    async def seed_demo_account_endpoint(
        admin_key: str = Query(None),
        db: Session = Depends(get_db),
    ):
        """Create the demo@perenniaai.com account for App Store review.
        Protected by ADMIN_API_KEY.
        """
        _verify_admin_key(admin_key)

        try:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

            demo_email = "demo@perenniaai.com"
            demo_password = os.getenv("DEMO_USER_PASSWORD", "")
            if not demo_password:
                raise HTTPException(status_code=500, detail="DEMO_USER_PASSWORD env var required")
            org_name = "Summit Peak Mortgage"
            org_slug = "summit-peak-demo-appstore"
            now = datetime.now(timezone.utc)

            # Check if demo org already exists
            existing = db.execute(text("SELECT id FROM organizations WHERE slug = :s"), {"s": org_slug}).fetchone()
            if existing:
                org_id = existing[0]
                # Check if user already exists
                user_exists = db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": demo_email}).fetchone()
                if user_exists:
                    # Update password and ensure correct role
                    hashed = pwd_context.hash(demo_password)
                    db.execute(text(
                        "UPDATE users SET hashed_password = :h, role = 'loan_officer', permission_role = 'sales' WHERE email = :e"
                    ), {"h": hashed, "e": demo_email})
                    db.commit()
                    return {"status": "updated", "message": "Demo user password and role updated", "email": demo_email, "org_id": org_id}
            else:
                # Create org
                db.execute(text("""
                    INSERT INTO organizations (name, slug, domain, subscription_tier, is_active, timezone, created_at)
                    VALUES (:name, :slug, :domain, :tier, TRUE, :tz, :now)
                """), {"name": org_name, "slug": org_slug, "domain": "summitpeakdemo.com",
                       "tier": "professional", "tz": "America/Chicago", "now": now})
                org_id = db.execute(text("SELECT id FROM organizations WHERE slug = :s"), {"s": org_slug}).scalar()

            # Create or update demo user
            hashed = pwd_context.hash(demo_password)
            user_exists = db.execute(text("SELECT id FROM users WHERE email = :e"), {"e": demo_email}).fetchone()
            if user_exists:
                db.execute(text(
                    "UPDATE users SET hashed_password = :h, organization_id = :oid, "
                    "role = 'loan_officer', permission_role = 'sales' WHERE email = :e"
                ), {"h": hashed, "e": demo_email, "oid": org_id})
            else:
                db.execute(text("""
                    INSERT INTO users (email, hashed_password, first_name, last_name, role, permission_role,
                                      organization_id, is_active, created_at)
                    VALUES (:email, :hash, :first, :last, 'loan_officer', 'sales', :oid, TRUE, :now)
                """), {"email": demo_email, "hash": hashed, "first": "Demo", "last": "User",
                       "oid": org_id, "now": now})

            db.commit()
            return {"status": "created", "message": "Demo account ready", "email": demo_email, "org_id": org_id}
        except Exception as e:
            db.rollback()
            logger.exception("Demo account seed failed")
            import traceback
            return JSONResponse(status_code=500, content={
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
