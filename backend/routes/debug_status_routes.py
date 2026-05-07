"""
Debug Status & Diagnostic Routes

Extracted from inline_legacy_routes.py.
Provides debug endpoints for PURL testing, appointment diagnostics,
SMS testing, cache stats, DataDog monitoring, CDN status, and admin tools.
"""
from fastapi import Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
import logging
import re

from auth.dependencies import require_auth

logger = logging.getLogger(__name__)

_SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

def _safe_identifier(name: str) -> str:
    """Validate and quote a SQL identifier to prevent injection."""
    if not _SAFE_IDENTIFIER_RE.match(name) or len(name) > 128:
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


def register_debug_status_routes(app, get_db, get_current_user, route_errors=None, **kwargs):
    """Register debug/diagnostic routes.
    
    Args:
        route_errors: Dict of route loading error strings, keyed by route name.
                     Used by status-check endpoints to report loading failures.
    """
    if route_errors is None:
        route_errors = {}

    # Lazy import for User model (needed by datadog-test-metrics)
    from database.models import User

    @app.get("/api/v1/debug/purl-routes-status", dependencies=[Depends(require_auth)])
    async def debug_purl_routes_status(current_user: User = Depends(get_current_user)):
        """Debug endpoint to check PURL routes loading status"""
        return {
            "purl_routes_loaded": route_errors.get("purl") is None,
            "error": route_errors.get("purl")
        }

    @app.get("/api/v1/debug/purl-tables-status", dependencies=[Depends(require_auth)])
    async def debug_purl_tables_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Debug endpoint to check if PURL tables exist in database"""
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        all_tables = inspector.get_table_names()

        purl_tables_expected = [
            'purl_workspaces',
            'purl_contacts',
            'purl_workspace_members',
            'purl_access_tokens',
            'purl_applications',
            'purl_loans',
            'purl_documents',
            'purl_portal_modules',
            'purl_milestone_definitions',
            'purl_loan_milestones',
            'purl_tasks',
            'purl_messages',
            'purl_events_outbox',
            'purl_audit_log',
            'purl_document_requests'
        ]

        existing_purl_tables = [t for t in all_tables if t.startswith('purl_')]
        missing_purl_tables = [t for t in purl_tables_expected if t not in all_tables]

        return {
            "purl_tables_exist": len(missing_purl_tables) == 0,
            "existing_purl_tables": existing_purl_tables,
            "missing_purl_tables": missing_purl_tables,
            "all_table_count": len(all_tables)
        }

    @app.get("/api/v1/debug/user-delete-diagnosis", dependencies=[Depends(require_auth)])
    async def debug_user_delete_diagnosis(
        user_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Debug endpoint to diagnose user deletion blockers (no actual deletion)"""
        # Check if user exists
        user = db.execute(text("SELECT id, email, full_name FROM users WHERE id = :uid"), {"uid": user_id}).fetchone()
        if not user:
            return {"error": "User not found", "user_id": user_id}

        # Get all FK constraints referencing users table
        fk_query = """
            SELECT tc.table_name, kcu.column_name, tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'users' AND tc.table_schema = 'public'
            ORDER BY tc.table_name
        """
        fks = db.execute(text(fk_query)).fetchall()

        # Check which tables reference this user
        blocking_tables = []
        for table_name, column_name, constraint_name in fks:
            if table_name == 'users':
                continue
            try:
                count_sql = "SELECT COUNT(*) FROM " + _safe_identifier(table_name) + " WHERE " + _safe_identifier(column_name) + " = :uid"
                count = db.execute(
                    text(count_sql),
                    {"uid": user_id}
                ).scalar()
                if count > 0:
                    blocking_tables.append({
                        "table": table_name,
                        "column": column_name,
                        "references": count
                    })
            except Exception as e:
                if "does not exist" not in str(e).lower():
                    blocking_tables.append({
                        "table": table_name,
                        "column": column_name,
                        "error": "Internal server error"[:100]
                    })

        return {
            "user_id": user_id,
            "user_email": user[1],
            "user_name": user[2],
            "total_fk_constraints": len(fks),
            "blocking_references": blocking_tables,
            "can_delete": len(blocking_tables) == 0
        }

    @app.get("/api/v1/debug/list-test-users", dependencies=[Depends(require_auth)])
    async def debug_list_test_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """List users available for testing (non-admin only)"""
        users = db.execute(text("""
            SELECT id, email, full_name, is_active, role
            FROM users
            WHERE email NOT LIKE '%admin%'
            ORDER BY id DESC
            LIMIT 10
        """)).fetchall()
        return {
            "users": [{"id": u[0], "email": u[1], "name": u[2], "active": u[3], "role": u[4]} for u in users],
            "note": "Use these IDs with /api/v1/debug/user-delete-diagnosis?user_id=X"
        }

    @app.get("/api/v1/debug/purl-token-verify", dependencies=[Depends(require_auth)])
    async def debug_purl_token_verify(
        token: str,
        workspace_slug: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to test PURL token verification"""
        import hashlib

        # Token format validation
        token_prefix = "purl_live_"
        is_valid_format = token.startswith(token_prefix) and len(token) == len(token_prefix) + 64

        # Compute hash
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Check workspace
        workspace = db.execute(text("""
            SELECT id, slug, organization_id, status
            FROM purl_workspaces
            WHERE slug = :slug
        """), {"slug": workspace_slug}).fetchone()

        workspace_info = None
        if workspace:
            workspace_info = {
                "id": workspace[0],
                "slug": workspace[1],
                "organization_id": workspace[2],
                "status": workspace[3]
            }

        # Check tokens for workspace
        tokens_info = []
        if workspace:
            tokens = db.execute(text("""
                SELECT id, token_hash, token_prefix, scope, status, expires_at, created_at
                FROM purl_access_tokens
                WHERE workspace_id = :workspace_id
            """), {"workspace_id": workspace[0]}).fetchall()

            for t in tokens:
                tokens_info.append({
                    "id": t[0],
                    "stored_hash": t[1],
                    "hash_matches": t[1] == token_hash,
                    "prefix": t[2],
                    "scope": t[3],
                    "status": t[4],
                    "expires_at": str(t[5]) if t[5] else None,
                    "created_at": str(t[6]) if t[6] else None
                })

        # Direct hash lookup
        token_by_hash = db.execute(text("""
            SELECT id, workspace_id, scope, status
            FROM purl_access_tokens
            WHERE token_hash = :hash
        """), {"hash": token_hash}).fetchone()

        hash_lookup = None
        if token_by_hash:
            hash_lookup = {
                "id": token_by_hash[0],
                "workspace_id": token_by_hash[1],
                "scope": token_by_hash[2],
                "status": token_by_hash[3]
            }

        return {
            "token_length": len(token),
            "expected_length": 74,
            "is_valid_format": is_valid_format,
            "computed_hash": token_hash,
            "workspace": workspace_info,
            "tokens_for_workspace": tokens_info,
            "token_found_by_hash": hash_lookup is not None,
            "hash_lookup_result": hash_lookup
        }

    @app.post("/api/v1/debug/purl-create-test-workspace", dependencies=[Depends(require_auth)])
    async def debug_create_test_workspace(
        test_name: str = "debug-test",
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Debug endpoint to create a test PURL workspace with token"""
        import hashlib
        import secrets

        try:
            # Generate slug
            random_suffix = secrets.token_hex(4)
            slug = f"{test_name.lower().replace(' ', '-')}-{random_suffix}"

            # Create workspace
            workspace = db.execute(text("""
                INSERT INTO purl_workspaces (
                    organization_id, slug, display_name, status, created_at, updated_at
                ) VALUES (
                    1, :slug, :display_name, 'lead', NOW(), NOW()
                )
                RETURNING id, slug
            """), {"slug": slug, "display_name": test_name}).fetchone()
            db.commit()

            workspace_id = workspace[0]
            workspace_slug = workspace[1]

            # Generate token
            token_bytes = secrets.token_bytes(32)
            token_hex = token_bytes.hex()
            full_token = f"purl_live_{token_hex}"
            token_hash = hashlib.sha256(full_token.encode()).hexdigest()
            token_prefix = full_token[:16]

            # Create token
            from datetime import timezone, timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)

            token = db.execute(text("""
                INSERT INTO purl_access_tokens (
                    organization_id, workspace_id, token_hash, token_prefix,
                    scope, status, expires_at, created_at
                ) VALUES (
                    1, :workspace_id, :token_hash, :token_prefix,
                    'full', 'active', :expires_at, NOW()
                )
                RETURNING id
            """), {
                "workspace_id": workspace_id,
                "token_hash": token_hash,
                "token_prefix": token_prefix,
                "expires_at": expires_at
            }).fetchone()
            db.commit()

            return {
                "success": True,
                "workspace_id": workspace_id,
                "workspace_slug": workspace_slug,
                "token": full_token,
                "token_id": token[0],
                "expires_at": expires_at.isoformat(),
                "portal_url": f"https://perenniaai.com/portal/{workspace_slug}",
                "test_curl": f'curl -H "Authorization: Bearer {full_token}" "https://app.perenniaai.com/api/purl/workspace/{workspace_slug}"'
            }
        except Exception as e:
            db.rollback()
            import traceback
            return {
                "success": False,
                "error": "Internal server error"
            }

    @app.get("/api/v1/debug/purl-auth-flow", dependencies=[Depends(require_auth)])
    async def debug_purl_auth_flow(
        token: str,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Debug endpoint to test the full PURL auth flow"""
        import traceback

        result = {
            "token_received": token[:20] + "...",
            "token_length": len(token),
            "steps": {}
        }

        try:
            # Step 1: Format validation
            from models.purl import PURLTokenGenerator, TokenScope, TokenStatus
            is_valid = PURLTokenGenerator.is_valid_format(token)
            result["steps"]["1_format_valid"] = is_valid

            if not is_valid:
                result["error"] = "Token format invalid"
                return result

            # Step 2: Hash token
            token_hash = PURLTokenGenerator.hash_token(token)
            result["steps"]["2_token_hash"] = token_hash[:20] + "..."

            # Step 3: Query token
            from models.purl import PURLAccessToken
            token_record = db.query(PURLAccessToken).filter(
                PURLAccessToken.token_hash == token_hash
            ).first()

            result["steps"]["3_token_found"] = token_record is not None

            if not token_record:
                result["error"] = "Token not found in database"
                return result

            result["steps"]["3_token_id"] = token_record.id
            result["steps"]["3_token_status"] = token_record.status
            result["steps"]["3_token_scope"] = token_record.scope

            # Step 4: Check status
            result["steps"]["4_status_check"] = token_record.status == TokenStatus.ACTIVE.value

            if token_record.status != TokenStatus.ACTIVE.value:
                result["error"] = f"Token status is {token_record.status}, not active"
                return result

            # Step 5: Check expiration
            from datetime import datetime, timezone
            if token_record.expires_at:
                is_expired = token_record.expires_at < datetime.now(timezone.utc)
                result["steps"]["5_expiration_check"] = not is_expired
                result["steps"]["5_expires_at"] = str(token_record.expires_at)

                if is_expired:
                    result["error"] = "Token is expired"
                    return result
            else:
                result["steps"]["5_expiration_check"] = "No expiration"

            # Step 6: Get workspace
            from models.purl import PURLWorkspace
            workspace = db.query(PURLWorkspace).filter(
                PURLWorkspace.id == token_record.workspace_id
            ).first()

            result["steps"]["6_workspace_found"] = workspace is not None

            if not workspace:
                result["error"] = "Workspace not found"
                return result

            result["steps"]["6_workspace_id"] = workspace.id
            result["steps"]["6_workspace_slug"] = workspace.slug
            result["steps"]["6_workspace_status"] = workspace.status

            # Step 7: Try creating TokenScope enum
            try:
                scope = TokenScope(token_record.scope)
                result["steps"]["7_scope_enum_created"] = True
                result["steps"]["7_scope_value"] = scope.value
            except Exception as e:
                result["steps"]["7_scope_enum_created"] = False
                result["steps"]["7_scope_error"] = str(e)
                result["error"] = f"Failed to create TokenScope enum: {e}"
                return result

            # Step 8: Try full service verification
            try:
                from services.purl_token_service import PURLTokenService
                service = PURLTokenService(db)
                context_data = service.verify_token(token)
                result["steps"]["8_service_verify"] = context_data is not None
                if context_data:
                    result["steps"]["8_context_keys"] = list(context_data.keys())
                else:
                    result["error"] = "Service verification returned None"
            except Exception as e:
                result["steps"]["8_service_verify"] = False
                result["steps"]["8_service_error"] = type(e).__name__
                result["error"] = "Service verification failed"
                logger.error(f"PURL auth flow debug - service verify failed: {traceback.format_exc()}")
                return result

            result["success"] = True
            return result

        except Exception as e:
            result["error"] = type(e).__name__
            logger.error(f"PURL auth flow debug failed: {traceback.format_exc()}")
            return result


    @app.get("/api/v1/debug/appointments-status", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def debug_appointments_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Debug endpoint to check recent appointments and reminder status"""
        result = {
            "scheduler_appointments": [],
            "legacy_appointments": [],
            "reminders_sent": [],
            "summary": {}
        }

        try:
            # Check smart scheduler appointments
            try:
                smart_appts = db.execute(text("""
                    SELECT
                        sa.id, sa.title, sa.scheduled_start, sa.status,
                        sa.attendee_name, sa.attendee_email, sa.attendee_phone,
                        sa.video_link, sa.created_at,
                        u.full_name as lo_name
                    FROM scheduler_appointments sa
                    LEFT JOIN users u ON u.id = sa.assigned_user_id
                    ORDER BY sa.created_at DESC
                    LIMIT 5
                """)).fetchall()

                for row in smart_appts:
                    result["scheduler_appointments"].append({
                        "id": row[0],
                        "title": row[1],
                        "scheduled_start": row[2].isoformat() if row[2] else None,
                        "status": row[3],
                        "attendee_name": row[4],
                        "attendee_email": row[5],
                        "attendee_phone": row[6],
                        "video_link": row[7],
                        "created_at": row[8].isoformat() if row[8] else None,
                        "lo_name": row[9] or ''
                    })
            except Exception as e:
                result["scheduler_appointments_error"] = str(e)

            # Check legacy appointments (may not exist in all deployments)
            try:
                # First check if appointments table exists
                table_check = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'appointments'
                    )
                """)).scalar()

                if table_check:
                    legacy_appts = db.execute(text("""
                        SELECT
                            a.id, a.appointment_type, a.scheduled_at, a.status,
                            a.reminder_sent, a.meeting_link,
                            l.name as lead_name, l.email as lead_email, l.phone as lead_phone,
                            u.full_name as lo_name
                        FROM appointments a
                        LEFT JOIN leads l ON l.id = a.lead_id
                        LEFT JOIN users u ON u.id = a.assigned_to
                        ORDER BY a.created_at DESC
                        LIMIT 5
                    """)).fetchall()

                    for row in legacy_appts:
                        result["legacy_appointments"].append({
                            "id": row[0],
                            "type": row[1],
                            "scheduled_at": row[2].isoformat() if row[2] else None,
                            "status": row[3],
                            "reminder_sent": row[4],
                            "meeting_link": row[5],
                            "lead_name": row[6],
                            "lead_email": row[7],
                            "lead_phone": row[8],
                            "lo_name": row[9] or ''
                        })
                else:
                    result["legacy_appointments_note"] = "appointments table does not exist"
            except Exception as e:
                result["legacy_appointments_error"] = str(e)

            # Check chat widget appointments (scheduled_appointments table)
            result["chat_widget_appointments"] = []
            try:
                table_check = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'scheduled_appointments'
                    )
                """)).scalar()

                if table_check:
                    chat_appts = db.execute(text("""
                        SELECT
                            sa.id, sa.appointment_id, sa.appointment_type, sa.start_time, sa.status,
                            sa.contact_name, sa.contact_email, sa.contact_phone,
                            sa.lo_name, sa.created_at
                        FROM scheduled_appointments sa
                        WHERE sa.status = 'scheduled'
                        ORDER BY sa.created_at DESC
                        LIMIT 10
                    """)).fetchall()

                    for row in chat_appts:
                        result["chat_widget_appointments"].append({
                            "id": row[0],
                            "appointment_id": row[1],
                            "type": row[2],
                            "start_time": row[3].isoformat() if row[3] else None,
                            "status": row[4],
                            "contact_name": row[5],
                            "contact_email": row[6],
                            "contact_phone": row[7],
                            "lo_name": row[8] or '',
                            "created_at": row[9].isoformat() if row[9] else None
                        })
                else:
                    result["chat_widget_appointments_note"] = "scheduled_appointments table does not exist"
            except Exception as e:
                result["chat_widget_appointments_error"] = str(e)

            # Check sent reminders
            try:
                reminders = db.execute(text("""
                    SELECT appointment_id, channel, hours_before, status, sent_at
                    FROM scheduler_reminders
                    ORDER BY created_at DESC
                    LIMIT 10
                """)).fetchall()

                for row in reminders:
                    result["reminders_sent"].append({
                        "appointment_id": row[0],
                        "channel": row[1],
                        "hours_before": row[2],
                        "status": row[3],
                        "sent_at": row[4].isoformat() if row[4] else None
                    })
            except Exception as e:
                result["reminders_error"] = str(e)

            # Check chat widget reminders
            result["chat_widget_reminders"] = []
            try:
                table_check = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'chat_appointment_reminders'
                    )
                """)).scalar()

                if table_check:
                    chat_reminders = db.execute(text("""
                        SELECT appointment_id, channel, hours_before, status, sent_at
                        FROM chat_appointment_reminders
                        ORDER BY created_at DESC
                        LIMIT 10
                    """)).fetchall()

                    for row in chat_reminders:
                        result["chat_widget_reminders"].append({
                            "appointment_id": row[0],
                            "channel": row[1],
                            "hours_before": row[2],
                            "status": row[3],
                            "sent_at": row[4].isoformat() if row[4] else None
                        })
            except Exception as e:
                result["chat_widget_reminders_error"] = str(e)

            result["summary"] = {
                "scheduler_appointments_count": len(result["scheduler_appointments"]),
                "legacy_appointments_count": len(result["legacy_appointments"]),
                "chat_widget_appointments_count": len(result["chat_widget_appointments"]),
                "reminders_sent_count": len(result["reminders_sent"]),
                "chat_widget_reminders_count": len(result["chat_widget_reminders"])
            }

            return result

        except Exception as e:
            return {"error": "Internal server error"}


    @app.post("/api/v1/debug/create-test-appointment", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def create_test_appointment(
        attendee_email: str = "tloss@me.com",
        attendee_phone: str = "8438345251",
        current_user: User = Depends(get_current_user),
        attendee_name: str = "Test Reminder",
        hours_from_now: int = 24,
        db: Session = Depends(get_db)
    ):
        """Create a test appointment for notification testing"""
        from datetime import datetime, timedelta

        scheduled_start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
        scheduled_end = scheduled_start + timedelta(minutes=30)

        try:
            # Get first user to assign
            user = db.execute(text("SELECT id, full_name FROM users LIMIT 1")).fetchone()
            user_id = user[0] if user else None
            user_name = user[1] if user else "Test LO"

            # Insert appointment (use uppercase enum values)
            result = db.execute(text("""
                INSERT INTO scheduler_appointments
                (title, scheduled_start, scheduled_end, duration_minutes, status,
                 attendee_name, attendee_email, attendee_phone, assigned_user_id,
                 meeting_type, timezone, created_at, updated_at)
                VALUES
                (:title, :start, :end, 30, 'BOOKED',
                 :name, :email, :phone, :user_id,
                 'DISCOVERY_CALL', 'America/New_York', NOW(), NOW())
                RETURNING id
            """), {
                "title": f"Test Call with {attendee_name}",
                "start": scheduled_start,
                "end": scheduled_end,
                "name": attendee_name,
                "email": attendee_email,
                "phone": attendee_phone,
                "user_id": user_id
            })

            appointment_id = result.fetchone()[0]
            db.commit()

            return {
                "success": True,
                "appointment_id": appointment_id,
                "scheduled_start": scheduled_start.isoformat(),
                "scheduled_end": scheduled_end.isoformat(),
                "attendee_email": attendee_email,
                "attendee_phone": attendee_phone,
                "assigned_to": user_name,
                "reminder_schedule": {
                    "24h_reminder": (scheduled_start - timedelta(hours=24)).isoformat() if hours_from_now > 24 else "Already passed",
                    "1h_reminder": (scheduled_start - timedelta(hours=1)).isoformat()
                },
                "note": f"Appointment created {hours_from_now} hours from now. Reminders will be sent automatically."
            }

        except Exception as e:
            db.rollback()
            return {"error": "Internal server error"}


    @app.post("/api/v1/debug/send-test-sms", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def send_test_sms(
        phone: str = "8438345251",
        message: str = "Test reminder from Perennia AI - your appointment is coming up!",
        current_user: User = Depends(get_current_user)
    ):
        """Send a test SMS to verify telephony provider is working"""
        import os
        try:
            from telephony.sms import send_sms as telnyx_send_sms

            from_number = os.getenv("TELNYX_PHONE_NUMBER")

            if not from_number:
                return {
                    "success": False,
                    "error": "Telnyx phone number not configured",
                    "config": {
                        "telnyx_phone": bool(os.getenv("TELNYX_PHONE_NUMBER")),
                        "telnyx_api_key": bool(os.getenv("TELNYX_API_KEY")),
                        "from_number": from_number
                    }
                }

            # Format phone number
            if not phone.startswith("+"):
                phone = "+1" + phone.replace("-", "").replace(" ", "")

            result = telnyx_send_sms(
                to=phone,
                from_=from_number,
                text=message,
            )

            msg_id = result.get("id", "unknown")

            return {
                "success": True,
                "message_sid": msg_id,
                "to": phone,
                "from": from_number,
                "status": "sent"
            }

        except Exception as e:
            return {"success": False, "error": "Internal server error"}


    @app.post("/api/v1/debug/trigger-appointment-reminders", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def trigger_appointment_reminders(current_user: User = Depends(get_current_user)):
        """Manually trigger the appointment reminder job"""
        try:
            from services.scheduler_service import scheduler_service
            scheduler_service.send_appointment_reminders()
            return {"success": True, "message": "Reminder job executed"}
        except Exception as e:
            return {"success": False, "error": "Internal server error"}


    @app.get("/api/v1/debug/cache-stats", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def debug_cache_stats(current_user: User = Depends(get_current_user)):
        """
        Debug endpoint to monitor Redis LLM cache statistics.

        Returns cache hit/miss rates, estimated savings, and Redis connection status.
        Used to verify caching is working and measure cost savings.
        """
        try:
            from services.llm_cache_service import llm_cache

            if llm_cache and llm_cache._enabled:
                stats = llm_cache.get_stats()
                return {
                    "cache_enabled": True,
                    "redis_connected": True,
                    "stats": {
                        "hits": stats.get("hits", 0),
                        "misses": stats.get("misses", 0),
                        "errors": stats.get("errors", 0),
                        "hit_rate_percent": stats.get("hit_rate", 0),
                        "estimated_savings_usd": stats.get("estimated_savings", 0),
                    },
                    "message": "Cache is operational"
                }
            else:
                return {
                    "cache_enabled": False,
                    "redis_connected": False,
                    "stats": None,
                    "message": "LLM cache service not enabled or Redis not connected"
                }
        except ImportError:
            return {
                "cache_enabled": False,
                "redis_connected": False,
                "stats": None,
                "message": "LLM cache service not available"
            }
        except Exception as e:
            return {
                "cache_enabled": False,
                "redis_connected": False,
                "stats": None,
                "error": "Internal server error",
                "message": "Error checking cache"
            }


    # DataDog monitoring status endpoint
    @app.get("/api/v1/debug/datadog-status", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def debug_datadog_status(current_user: User = Depends(get_current_user)):
        """
        Debug endpoint to check DataDog monitoring status.

        Returns APM tracing status, metrics collection status, and configuration.
        """
        try:
            from datadog_monitoring import (
                DD_SERVICE, DD_ENV, DD_TRACE_ENABLED,
                _tracer, _statsd, _initialized
            )

            return {
                "datadog_enabled": _initialized,
                "apm_tracing": {
                    "enabled": DD_TRACE_ENABLED,
                    "initialized": _tracer is not None,
                    "service": DD_SERVICE,
                    "environment": DD_ENV
                },
                "metrics": {
                    "statsd_initialized": _statsd is not None,
                    "prefix": "mortgage_crm"
                },
                "config": {
                    "DD_SERVICE": DD_SERVICE,
                    "DD_ENV": DD_ENV,
                    "DD_TRACE_ENABLED": DD_TRACE_ENABLED
                },
                "message": "DataDog monitoring is operational" if _initialized else "DataDog not fully initialized"
            }
        except ImportError:
            return {
                "datadog_enabled": False,
                "message": "DataDog monitoring module not available"
            }
        except Exception as e:
            return {
                "datadog_enabled": False,
                "error": "Internal server error",
                "message": "Error checking DataDog status"
            }


    @app.get("/api/v1/debug/datadog-dashboard-config", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def get_datadog_dashboard_config(current_user: User = Depends(get_current_user)):
        """
        Get DataDog dashboard configuration JSON.

        Returns the dashboard configuration that can be imported into DataDog
        using their Dashboard API.
        """
        try:
            from datadog_monitoring import get_dashboard_config
            return get_dashboard_config()
        except ImportError:
            return {"error": "DataDog monitoring module not available"}
        except Exception as e:
            return {"error": "Internal server error"}


    @app.post("/api/v1/debug/datadog-test-metrics", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def test_datadog_metrics(current_user: User = Depends(get_current_user)):
        """
        Send test metrics to DataDog.

        Useful for verifying the DataDog agent connection and metrics pipeline.
        """
        try:
            from datadog_monitoring import metrics, business_metrics

            # Send test metrics
            metrics.increment("test.counter", tags=["source:api_test"])
            metrics.gauge("test.gauge", 42.0, tags=["source:api_test"])
            metrics.histogram("test.histogram", 100.5, tags=["source:api_test"])

            # Send test business metric
            business_metrics.metrics.event(
                title="DataDog Test Event",
                text=f"Test event triggered by user {current_user.email}",
                alert_type="info",
                tags=["source:api_test", f"user:{current_user.id}"]
            )

            return {
                "success": True,
                "message": "Test metrics sent to DataDog",
                "metrics_sent": ["test.counter", "test.gauge", "test.histogram"],
                "event_sent": True
            }
        except ImportError:
            return {"success": False, "error": "DataDog monitoring module not available"}
        except Exception as e:
            return {"success": False, "error": "Internal server error"}


    @app.get("/api/v1/debug/cdn-status", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def get_cdn_status(current_user: User = Depends(get_current_user)):
        """
        Get CloudFront CDN status and configuration.

        Returns information about CDN setup, distribution status,
        and whether CDN URLs are being used.
        """
        try:
            from services.cdn_service import get_cdn_service
            cdn = get_cdn_service()
            status = cdn.get_distribution_status()
            return {
                "cdn_enabled": cdn.enabled,
                "distribution_id": cdn.distribution_id,
                "domain_name": cdn.domain_name,
                "s3_bucket": cdn.s3_bucket,
                "signed_urls_available": bool(cdn._private_key and cdn.key_pair_id),
                "distribution_status": status
            }
        except ImportError:
            return {
                "cdn_enabled": False,
                "error": "CDN service module not available",
                "message": "Install cdn_service.py and configure CloudFront"
            }
        except Exception as e:
            return {
                "cdn_enabled": False,
                "error": "Internal server error",
                "message": "Error checking CDN status"
            }


    @app.post("/api/v1/debug/cdn-invalidate", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def invalidate_cdn_cache(
        paths: list[str] = Body(..., description="List of paths to invalidate"),
        current_user: User = Depends(get_current_user)
    ):
        """
        Invalidate CloudFront cache for specified paths.

        Requires admin or appropriate permissions.
        """
        try:
            from services.cdn_service import get_cdn_service
            cdn = get_cdn_service()

            if not cdn.enabled:
                return {"success": False, "error": "CDN not configured"}

            result = cdn.invalidate_cache(paths)
            return result
        except ImportError:
            return {"success": False, "error": "CDN service module not available"}
        except Exception as e:
            return {"success": False, "error": "Internal server error"}


    @app.post("/api/v1/debug/add-missing-roles", tags=["Debug"], dependencies=[Depends(require_auth)])
    async def add_missing_employee_roles(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Add missing employee roles to the onboarding_roles table.

        Adds: Admin, Site Admin, Executive Management, Management, Operations Manager,
              Branch Manager, Underwriter, Closer, Funder
        """
        if current_user.role != 'admin' and current_user.permission_role != 'admin':
            raise HTTPException(status_code=403, detail="Admin access required")

        try:
            from sqlalchemy import text as sql_text
            from datetime import datetime, timezone

            MISSING_ROLES = [
                {"name": "Admin", "description": "System administrator with full access"},
                {"name": "Site Admin", "description": "Site-level administrator"},
                {"name": "Executive Management", "description": "Executive management team"},
                {"name": "Management", "description": "Management role"},
                {"name": "Operations Manager", "description": "Operations manager overseeing daily operations"},
                {"name": "Branch Manager", "description": "Branch manager overseeing branch operations"},
                {"name": "Underwriter", "description": "Loan underwriter"},
                {"name": "Closer", "description": "Loan closer handling closing process"},
                {"name": "Funder", "description": "Loan funder handling funding process"},
            ]

            added = []
            skipped = []

            for role in MISSING_ROLES:
                # Check if role exists
                existing = db.execute(
                    sql_text("SELECT id FROM onboarding_roles WHERE name = :name"),
                    {"name": role["name"]}
                ).fetchone()

                if existing:
                    skipped.append(role["name"])
                else:
                    db.execute(
                        sql_text("""
                            INSERT INTO onboarding_roles (name, description, is_active, created_at, updated_at)
                            VALUES (:name, :description, true, :now, :now)
                        """),
                        {
                            "name": role["name"],
                            "description": role["description"],
                            "now": datetime.now(timezone.utc)
                        }
                    )
                    added.append(role["name"])

            db.commit()

            # Get all roles for display
            all_roles = db.execute(
                sql_text("SELECT id, name, is_active FROM onboarding_roles WHERE is_active = true ORDER BY name")
            ).fetchall()

            return {
                "success": True,
                "added": added,
                "skipped": skipped,
                "message": f"Added {len(added)} roles, skipped {len(skipped)} existing roles",
                "all_roles": [{"id": r[0], "name": r[1]} for r in all_roles]
            }

        except Exception as e:
            db.rollback()
            return {"success": False, "error": "Internal server error"}


    logger.info("Debug status routes loaded")
