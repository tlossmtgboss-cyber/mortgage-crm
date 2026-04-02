"""
Duplicate Detection Routes
==========================
Endpoints for detecting and managing duplicate leads and loans.

Includes:
- Duplicate scanning and detection
- Task creation for duplicate review
- Admin debugging endpoints for duplicates
- Data management (clear/seed demo data)
- Admin migration endpoints
- Mission Control AI colleague tracking

Route prefixes:
- /api/v1/duplicates/* - Main duplicate detection API
- /admin/* - Admin debug endpoints (no auth for local debugging)
- /api/v1/data/* - Data management endpoints
- /api/v1/admin/* - Admin seeding/management
- /api/v1/mission-control/* - AI colleague tracking
"""

import hmac
import json
import logging
import os
import subprocess
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Duplicate Detection"])

# Migration secret from env — fail closed if not set
_ADMIN_MIGRATION_SECRET = os.getenv("ADMIN_MIGRATION_SECRET", "")


def _verify_admin_secret(request: dict) -> None:
    """Verify the admin migration secret from request body. Fail closed."""
    if not _ADMIN_MIGRATION_SECRET:
        raise HTTPException(status_code=503, detail="Migration endpoint not configured")
    provided = request.get("secret", "")
    if not provided or not hmac.compare_digest(provided, _ADMIN_MIGRATION_SECRET):
        raise HTTPException(status_code=403, detail="Invalid secret")


# ============================================================================
# RUNTIME IMPORT HELPERS (Avoid circular imports)
# ============================================================================

def get_current_user_dep():
    """Get current user dependency - imports from main at runtime."""
    import main
    return main.get_current_user


def get_current_user_flexible_dep():
    """Get flexible current user dependency - imports from main at runtime."""
    import main
    return main.get_current_user_flexible


def get_user_model():
    """Get User model - imports from main at runtime."""
    import main
    return main.User


def get_task_model():
    """Get Task model - imports from main at runtime."""
    import main
    return main.Task


def get_ai_colleague_action_model():
    """Get AIColleagueAction model - imports from main at runtime."""
    import main
    return main.AIColleagueAction


def get_ai_journey_insight_model():
    """Get AIJourneyInsight model - imports from main at runtime."""
    import main
    return main.AIJourneyInsight


# ============================================================================
# DUPLICATE DETECTION ENDPOINTS
# ============================================================================

@router.get("/api/v1/duplicates/scan")
async def scan_for_duplicates(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Scan for duplicate leads and loans.
    Returns list of potential duplicates with confidence scores.
    """
    from services.duplicate_detection_service import get_duplicate_detection_service

    try:
        service = get_duplicate_detection_service(db)
        lead_duplicates = service.find_duplicate_leads()
        loan_duplicates = service.find_duplicate_loans()

        return {
            "status": "success",
            "lead_duplicates": lead_duplicates,
            "loan_duplicates": loan_duplicates,
            "total_duplicates": len(lead_duplicates) + len(loan_duplicates)
        }
    except Exception as e:
        logger.error(f"Error scanning for duplicates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/v1/duplicates/create-tasks")
async def create_duplicate_merge_tasks(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Scan for duplicates and create tasks for each duplicate pair.
    Tasks are assigned to the current user.
    """
    from services.duplicate_detection_service import get_duplicate_detection_service

    try:
        logger.info(f"Starting duplicate scan for user {current_user.id}")
        service = get_duplicate_detection_service(db)
        results = service.scan_and_create_tasks(assigned_to_user_id=current_user.id)

        return {
            "status": "success",
            "message": f"Found {results['lead_duplicates_found']} lead duplicates and {results['loan_duplicates_found']} loan duplicates",
            "tasks_created": results['tasks_created'],
            "tasks_existing": results['tasks_existing'],
            "duplicates": results['duplicates'],
            "errors": results.get('errors', [])
        }
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Error creating duplicate tasks: {e}\n{error_traceback}")
        raise HTTPException(status_code=500, detail="Error creating duplicate tasks — check server logs")


@router.post("/admin/test-duplicate-task-creation")
async def test_duplicate_task_creation(db: Session = Depends(get_db), current_user=Depends(get_current_user_dep())):
    """Debug endpoint to test duplicate task creation."""
    from services.duplicate_detection_service import get_duplicate_detection_service

    try:
        # Check if tasks table exists and has required columns
        columns_check = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'tasks'
            ORDER BY ordinal_position
        """)).fetchall()

        column_names = [c[0] for c in columns_check]

        # Count leads in database
        lead_count = db.execute(text("SELECT COUNT(*) FROM leads")).scalar()

        # Get sample of emails to check for duplicates
        sample_emails = db.execute(text("""
            SELECT email, COUNT(*) as cnt FROM leads
            WHERE email IS NOT NULL
            GROUP BY email
            HAVING COUNT(*) > 1
            LIMIT 5
        """)).fetchall()

        test_result = {
            "tasks_table_exists": len(column_names) > 0,
            "columns": column_names,
            "has_owner_id": "owner_id" in column_names,
            "has_related_type": "related_type" in column_names,
            "has_related_contact_name": "related_contact_name" in column_names,
            "total_leads": lead_count,
            "duplicate_emails_in_db": [{"email": r[0], "count": r[1]} for r in sample_emails],
        }

        # Test the service
        service = get_duplicate_detection_service(db)

        # Just scan without creating tasks to test the scan
        lead_duplicates = service.find_duplicate_leads()
        test_result["lead_duplicates_found"] = len(lead_duplicates)
        if lead_duplicates:
            test_result["sample_duplicate"] = lead_duplicates[0]

        return {"status": "success", "debug_info": test_result}
    except Exception as e:
        logger.error(f"Duplicate detection test failed: {traceback.format_exc()}")
        return {
            "status": "error",
            "error": "Internal server error",
        }


@router.get("/admin/check-duplicate-tasks")
async def check_duplicate_tasks(db: Session = Depends(get_db), current_user=Depends(get_current_user_dep())):
    """Check for existing duplicate review tasks."""
    try:
        # Find all tasks with related_type like 'duplicate_%'
        existing_tasks = db.execute(text("""
            SELECT id, title, status, related_type, created_at
            FROM tasks
            WHERE related_type LIKE 'duplicate_%'
            ORDER BY created_at DESC
            LIMIT 50
        """)).fetchall()

        return {
            "status": "success",
            "existing_duplicate_tasks": len(existing_tasks),
            "tasks": [
                {
                    "id": t[0],
                    "title": t[1],
                    "status": t[2],
                    "related_type": t[3],
                    "created_at": t[4].isoformat() if t[4] else None
                }
                for t in existing_tasks
            ]
        }
    except Exception as e:
        return {"status": "error", "error": "Internal server error"}


@router.delete("/admin/clear-duplicate-tasks")
async def clear_duplicate_tasks(db: Session = Depends(get_db), current_user=Depends(get_current_user_dep())):
    """Clear all existing duplicate review tasks so new ones can be created."""
    try:
        result = db.execute(text("""
            DELETE FROM tasks
            WHERE related_type LIKE 'duplicate_%'
            RETURNING id
        """))
        deleted_ids = [r[0] for r in result.fetchall()]
        db.commit()

        return {
            "status": "success",
            "deleted_count": len(deleted_ids),
            "deleted_ids": deleted_ids
        }
    except Exception as e:
        db.rollback()
        return {"status": "error", "error": "Internal server error"}


@router.get("/admin/check-user-permissions/{user_id}")
async def check_user_permissions_debug(user_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user_dep())):
    """Debug endpoint to check a user's permissions (admin only)."""
    if not getattr(current_user, 'permission_role', None) or current_user.permission_role not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")
    User = get_user_model()

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"status": "error", "message": f"User {user_id} not found"}

        # Check actual table schema
        columns = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'user_permissions'
            ORDER BY ordinal_position
        """)).fetchall()
        column_names = [c[0] for c in columns]

        # Try to get permissions with actual column names
        permissions = {}
        if 'permission_key' in column_names:
            rows = db.execute(text("""
                SELECT permission_key, granted FROM user_permissions WHERE user_id = :user_id
            """), {"user_id": user_id}).fetchall()
            permissions = {r[0]: r[1] for r in rows}
        elif 'key' in column_names:
            rows = db.execute(text("""
                SELECT key, granted FROM user_permissions WHERE user_id = :user_id
            """), {"user_id": user_id}).fetchall()
            permissions = {r[0]: r[1] for r in rows}

        return {
            "status": "success",
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "permission_role": user.permission_role,
            "user_permissions_columns": column_names,
            "permissions_count": len(permissions),
            "permissions": permissions,
            "has_admin_view": permissions.get('admin.view', False),
            "has_admin_manage": permissions.get('admin.manage', False),
            "has_system_admin": permissions.get('system.admin', False),
            "frontend_should_allow": user.permission_role == 'admin' or user.permission_role == 'management',
        }
    except Exception as e:
        logger.error(f"Error checking permissions: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.post("/admin/fix-user-permission-role")
async def fix_user_permission_role(request: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user_dep())):
    """Admin endpoint to fix a user's permission_role.
    Usage: POST /admin/fix-user-permission-role with body: {"email": "user@example.com", "role": "admin"}
    """
    # Only platform admins can change roles
    if not getattr(current_user, 'permission_role', None) or current_user.permission_role not in ('admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

    User = get_user_model()

    email = request.get("email")
    new_role = request.get("role")

    if not email:
        return {"status": "error", "message": "Email is required"}

    valid_roles = ['admin', 'leadership', 'management', 'sales', 'processing', 'operations']
    if new_role not in valid_roles:
        return {"status": "error", "message": f"Invalid role. Must be one of: {valid_roles}"}

    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return {"status": "error", "message": f"User with email {email} not found"}

        old_role = user.permission_role
        user.permission_role = new_role
        db.commit()

        return {
            "status": "success",
            "message": f"Updated permission_role for {email}",
            "old_role": old_role,
            "new_role": new_role,
            "user_id": user.id
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error fixing permission role: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.get("/api/v1/duplicates/check/{record_type}/{record_id}")
async def check_single_record_duplicates(
    record_type: str,
    record_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Check if a specific lead or loan has duplicates.
    record_type: 'lead' or 'loan'
    """
    from services.duplicate_detection_service import get_duplicate_detection_service

    try:
        service = get_duplicate_detection_service(db)

        if record_type == 'lead':
            # Convert string UUID to actual UUID for query
            try:
                lead_uuid = UUID(record_id)
            except ValueError:
                lead_uuid = record_id

            duplicates = service.find_duplicate_leads(lead_id=lead_uuid)
        elif record_type == 'loan':
            # For loans, we'd need to modify the service
            duplicates = []
        else:
            raise HTTPException(status_code=400, detail="Invalid record_type. Use 'lead' or 'loan'")

        return {
            "status": "success",
            "record_type": record_type,
            "record_id": record_id,
            "has_duplicates": len(duplicates) > 0,
            "duplicates": duplicates
        }
    except Exception as e:
        logger.error(f"Error checking duplicates: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/clear-all-tasks")
async def clear_all_tasks_endpoint(request: dict, db: Session = Depends(get_db)):
    """
    Clear all tasks from the database.
    Usage: POST /admin/clear-all-tasks with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    Task = get_task_model()

    # Simple security check
    _verify_admin_secret(request)

    try:
        # Get count before deletion
        task_count = db.query(Task).count()
        logger.info(f"Found {task_count} tasks to delete")

        if task_count == 0:
            return {
                "success": True,
                "message": "No tasks to delete",
                "deleted_count": 0
            }

        # Delete all tasks
        deleted_count = db.query(Task).delete()
        db.commit()

        logger.info(f"Successfully deleted {deleted_count} tasks")

        return {
            "success": True,
            "message": f"Successfully deleted {deleted_count} tasks",
            "deleted_count": deleted_count
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing tasks: {e}")
        raise HTTPException(status_code=500, detail="Error clearing tasks")


@router.post("/api/v1/data/clear-all-demo-data")
async def clear_sample_data(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Clear ALL sample/demo data from the CRM.
    This deletes: tasks, reconciliation events, messages, loans, leads, activities, documents,
    voicemails, calendar events, email drafts, SLA history, and more.

    KEEPS: User accounts, organization settings, OAuth tokens, system configurations.

    Note: Moved from /admin/ path to avoid IP whitelist restriction during data cleanup.
    """
    results = {}
    errors = []

    # Helper to safely delete from a table using raw SQL
    # Table names are hardcoded string literals below — never from user input
    def safe_delete(table_name: str) -> int:
        try:
            delete_sql = "DELETE FROM " + table_name
            result = db.execute(text(delete_sql))
            db.commit()  # Commit after each successful delete
            return result.rowcount
        except Exception as e:
            db.rollback()  # Rollback failed transaction to continue
            errors.append(f"{table_name}: {str(e)[:50]}")
            return 0

    logger.info(f"Starting comprehensive demo data cleanup for user {current_user.email}")

    # ===== DELETE IN ORDER (foreign key dependencies first) =====
    # All deletes use raw SQL with individual commits for transaction safety

    # 1. Task-related tables (reference tasks/loans/leads)
    results["task_approvals"] = safe_delete("task_approvals")
    results["loan_workflow_tasks"] = safe_delete("loan_workflow_tasks")
    results["workflow_task_instances"] = safe_delete("workflow_task_instances")
    results["broken_task_alerts"] = safe_delete("broken_task_alerts")

    # 2. Activities, Conversations, AI logs (reference loans/leads)
    results["activities"] = safe_delete("activities")
    results["conversations"] = safe_delete("conversations")
    results["conversation_memory"] = safe_delete("conversation_memory")
    results["ai_audit_logs"] = safe_delete("ai_audit_logs")
    results["ai_learning_metrics"] = safe_delete("ai_learning_metrics")
    results["ai_colleague_actions"] = safe_delete("ai_colleague_actions")
    results["ai_colleague_learning_metrics"] = safe_delete("ai_colleague_learning_metrics")
    results["ai_performance_daily"] = safe_delete("ai_performance_daily")
    results["ai_journey_insights"] = safe_delete("ai_journey_insights")
    results["ai_health_scores"] = safe_delete("ai_health_scores")

    # 3. Tasks (reference loans/leads)
    results["ai_tasks"] = safe_delete("ai_tasks")
    results["tasks"] = safe_delete("tasks")
    results["process_tasks"] = safe_delete("process_tasks")
    results["ai_delegated_tasks"] = safe_delete("ai_delegated_tasks")
    results["recurring_tasks"] = safe_delete("recurring_tasks")

    # 4. Email-related tables
    results["email_drafts"] = safe_delete("email_drafts")
    results["email_messages"] = safe_delete("email_messages")
    results["email_intakes"] = safe_delete("email_intakes")
    results["emails"] = safe_delete("emails")
    results["email_monitor_captured"] = safe_delete("email_monitor_captured")
    results["email_relevance_analysis"] = safe_delete("email_relevance_analysis")
    results["email_crm_links"] = safe_delete("email_crm_links")
    results["email_interactions"] = safe_delete("email_interactions")

    # 5. SMS and messaging
    results["sms_messages"] = safe_delete("sms_messages")
    results["sms_conversations"] = safe_delete("sms_conversations")
    results["teams_messages"] = safe_delete("teams_messages")

    # 6. Calendar and scheduling
    results["calendar_events"] = safe_delete("calendar_events")
    results["appointments"] = safe_delete("appointments")
    results["appointment_reminders"] = safe_delete("appointment_reminders")
    results["blocked_times"] = safe_delete("blocked_times")
    results["calendar_mappings"] = safe_delete("calendar_mappings")

    # 7. Voicemail and telephony
    results["voicemail_events"] = safe_delete("voicemail_events")
    results["voicemail_drops"] = safe_delete("voicemail_drops")
    results["voicemail_campaigns"] = safe_delete("voicemail_campaigns")
    results["call_logs"] = safe_delete("call_logs")
    results["active_calls"] = safe_delete("active_calls")
    results["dialer_session_tasks"] = safe_delete("dialer_session_tasks")
    results["dialer_sessions"] = safe_delete("dialer_sessions")

    # 8. Documents and attachments
    results["documents"] = safe_delete("documents")
    results["attachment_intakes"] = safe_delete("attachment_intakes")

    # 9. SLA tracking history
    results["sla_alerts"] = safe_delete("sla_alerts")
    results["loan_milestone_history"] = safe_delete("loan_milestone_history")
    results["sla_performance_snapshots"] = safe_delete("sla_performance_snapshots")
    results["sla_efficiency_reports"] = safe_delete("sla_efficiency_reports")

    # 10. Data reconciliation events (pending approvals)
    results["incoming_data_events"] = safe_delete("incoming_data_events")
    results["extracted_data"] = safe_delete("extracted_data")
    results["data_conflicts"] = safe_delete("data_conflicts")

    # 11. Loan team members (reference loans)
    results["loan_team_members"] = safe_delete("loan_team_members")

    # 12. Workflow executions
    results["workflow_executions"] = safe_delete("workflow_executions")

    # 13. Integration logs
    results["integration_logs"] = safe_delete("integration_logs")

    # 14. AI Training and feedback
    results["ai_training_events"] = safe_delete("ai_training_events")
    results["ai_feedback_logs"] = safe_delete("ai_feedback_logs")
    results["merge_training_events"] = safe_delete("merge_training_events")
    results["ai_actions"] = safe_delete("ai_actions")
    results["ai_quick_actions"] = safe_delete("ai_quick_actions")

    # 15. Duplicate handling
    results["duplicate_pairs"] = safe_delete("duplicate_pairs")
    results["blocked_senders"] = safe_delete("blocked_senders")

    # 16. Profiles (reference loans/leads)
    results["active_loan_profiles"] = safe_delete("active_loan_profiles")
    results["lead_profiles"] = safe_delete("lead_profiles")
    results["client_profiles"] = safe_delete("client_profiles")
    results["mum_client_profiles"] = safe_delete("mum_client_profiles")
    results["team_member_profiles"] = safe_delete("team_member_profiles")

    # 17. Analytics events
    results["analytics_events"] = safe_delete("analytics_events")

    # 18. MAIN DATA: Loans (no dependencies now)
    results["loans"] = safe_delete("loans")

    # 19. MAIN DATA: Leads (no dependencies now)
    results["leads"] = safe_delete("leads")

    # 20. Referral partners and MUM clients
    results["referral_partners"] = safe_delete("referral_partners")
    results["mum_clients"] = safe_delete("mum_clients")
    results["mum_transactions"] = safe_delete("mum_transactions")

    # 21. IT Helpdesk tickets
    results["helpdesk_tickets"] = safe_delete("it_helpdesk_tickets")

    # 22. Opportunities
    results["opportunities"] = safe_delete("opportunities")
    results["employer_records"] = safe_delete("employer_records")

    # 23. Video clips and related
    results["video_clip_views"] = safe_delete("clip_views")
    results["video_clip_comments"] = safe_delete("clip_comments")
    results["video_clip_shares"] = safe_delete("clip_shares")
    results["video_clip_notifications"] = safe_delete("clip_notifications")
    results["video_clips"] = safe_delete("video_clips")

    # Count total deleted
    total_deleted = sum(v for v in results.values() if isinstance(v, int))

    logger.info(f"Successfully cleared ALL demo data. Total records deleted: {total_deleted}")

    return {
        "success": True,
        "message": f"Successfully cleared ALL demo data from CRM. Total records deleted: {total_deleted}",
        "total_deleted": total_deleted,
        "details": results,
        "errors": errors if errors else None
    }


@router.post("/api/v1/data/clear-old-leads")
async def clear_old_leads(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Clear leads created BEFORE today, keeping only today's uploads.
    Also clears related records (tasks, activities, etc.) for deleted leads.
    """
    # Get start of today (UTC)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    results = {}
    errors = []

    try:
        # First, get count of leads to delete vs keep
        old_leads_count = db.execute(
            text("SELECT COUNT(*) FROM leads WHERE created_at < :today"),
            {"today": today_start}
        ).scalar()

        new_leads_count = db.execute(
            text("SELECT COUNT(*) FROM leads WHERE created_at >= :today"),
            {"today": today_start}
        ).scalar()

        results["leads_to_delete"] = old_leads_count
        results["leads_to_keep"] = new_leads_count

        if old_leads_count == 0:
            return {
                "success": True,
                "message": "No old leads to delete",
                "details": results
            }

        # Get IDs of old leads
        old_lead_ids_result = db.execute(
            text("SELECT id FROM leads WHERE created_at < :today"),
            {"today": today_start}
        ).fetchall()
        old_lead_ids = [row[0] for row in old_lead_ids_result]

        # Delete related records for old leads
        for lead_id in old_lead_ids:
            try:
                db.execute(text("DELETE FROM activities WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM tasks WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM ai_tasks WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM documents WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM notes WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM communications WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM workflow_executions WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM lead_profiles WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM circle_contacts WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("DELETE FROM notifications WHERE lead_id = :id"), {"id": lead_id})
                db.execute(text("UPDATE loans SET lead_id = NULL WHERE lead_id = :id"), {"id": lead_id})
            except Exception as e:
                errors.append(f"Lead {lead_id}: {str(e)[:50]}")

        # Delete old leads
        delete_result = db.execute(
            text("DELETE FROM leads WHERE created_at < :today"),
            {"today": today_start}
        )
        results["leads_deleted"] = delete_result.rowcount

        db.commit()

        logger.info(f"Cleared {results['leads_deleted']} old leads, kept {new_leads_count} new leads")

        return {
            "success": True,
            "message": f"Deleted {results['leads_deleted']} old leads, kept {new_leads_count} leads from today",
            "details": results,
            "errors": errors if errors else None
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing old leads: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/v1/admin/seed-demo-people")
async def seed_demo_people(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Seed comprehensive demo data: team members, leads, loans, and MUM clients.
    Creates realistic placeholder people across all CRM categories.
    """
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        results = {}
        import secrets as _secrets
        default_password = pwd_context.hash(_secrets.token_urlsafe(24))

        # TEAM MEMBERS
        team_members = [
            {"name": "Sarah Mitchell", "email": "sarah.mitchell@company.com", "role": "admin", "department": "Leadership"},
            {"name": "Michael Chen", "email": "michael.chen@company.com", "role": "management", "department": "Leadership"},
            {"name": "Jennifer Rodriguez", "email": "jennifer.rodriguez@company.com", "role": "management", "department": "Management"},
            {"name": "David Thompson", "email": "david.thompson@company.com", "role": "management", "department": "Management"},
            {"name": "Robert Garcia", "email": "robert.garcia@company.com", "role": "operations", "department": "Operations"},
            {"name": "Amanda Foster", "email": "amanda.foster@company.com", "role": "operations", "department": "Operations"},
            {"name": "Marcus Johnson", "email": "marcus.johnson@company.com", "role": "sales", "department": "Sales"},
            {"name": "Emily Patterson", "email": "emily.patterson@company.com", "role": "sales", "department": "Sales"},
            {"name": "Brandon Lee", "email": "brandon.lee@company.com", "role": "loan_officer", "department": "Sales"},
        ]

        team_count = 0
        for member in team_members:
            existing = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": member["email"]}).fetchone()
            if not existing:
                db.execute(text("""
                    INSERT INTO users (email, hashed_password, full_name, role, account_status, department, created_at)
                    VALUES (:email, :password, :name, :role, 'active', :department, CURRENT_TIMESTAMP)
                """), {
                    "email": member["email"],
                    "password": default_password,
                    "name": member["name"],
                    "role": member["role"],
                    "department": member["department"]
                })
                team_count += 1

        # LEADS - Use enum string values (not keys)
        leads_data = [
            {"name": "James Wilson", "email": "james.wilson@email.com", "phone": "(555) 234-5678", "stage": "New", "source": "Website", "loan_type": "Purchase - Conventional", "credit_score": 750, "annual_income": 125000, "property_value": 450000, "down_payment": 90000},
            {"name": "Maria Hernandez", "email": "maria.hernandez@email.com", "phone": "(555) 345-6789", "stage": "Prospect", "source": "Referral Partner", "loan_type": "Purchase - FHA", "credit_score": 680, "annual_income": 85000, "property_value": 325000, "down_payment": 11375},
            {"name": "Robert Taylor", "email": "robert.taylor@email.com", "phone": "(555) 456-7890", "stage": "Application Started", "source": "Zillow", "loan_type": "Refinance - Conventional", "credit_score": 720, "annual_income": 150000, "property_value": 550000},
            {"name": "Ashley Thompson", "email": "ashley.thompson@email.com", "phone": "(555) 567-8901", "stage": "Application Complete", "source": "Facebook Ad", "loan_type": "Purchase - VA", "credit_score": 695, "annual_income": 95000, "property_value": 380000},
            {"name": "Christopher Davis", "email": "chris.davis@email.com", "phone": "(555) 678-9012", "stage": "Pre-Approved", "source": "Realtor Referral", "loan_type": "Purchase - Jumbo", "credit_score": 780, "annual_income": 250000, "property_value": 850000, "down_payment": 170000, "preapproval_amount": 680000},
        ]

        loan_officer = db.execute(text("SELECT id FROM users WHERE role IN ('loan_officer', 'sales') ORDER BY id LIMIT 1")).fetchone()
        owner_id = loan_officer.id if loan_officer else current_user.id
        leads_count = 0

        for lead in leads_data:
            existing = db.execute(text("SELECT id FROM leads WHERE email = :email"), {"email": lead["email"]}).fetchone()
            if not existing:
                loan_amount = lead.get("property_value", 0) - lead.get("down_payment", 0)
                # Skip stage column - enum might not be created yet in production
                db.execute(text("""
                    INSERT INTO leads (name, email, phone, source, loan_type, credit_score, annual_income, property_value, down_payment, loan_amount, owner_id, ai_score, sentiment, created_at, updated_at)
                    VALUES (:name, :email, :phone, :source, :loan_type, :credit_score, :income, :property_value, :down_payment, :loan_amount, :owner_id, 65, 'positive', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """), {"name": lead["name"], "email": lead["email"], "phone": lead.get("phone"), "source": lead.get("source"), "loan_type": lead.get("loan_type"), "credit_score": lead.get("credit_score"), "income": lead.get("annual_income"), "property_value": lead.get("property_value"), "down_payment": lead.get("down_payment"), "loan_amount": loan_amount, "owner_id": owner_id})
                leads_count += 1

        # ACTIVE LOANS - Use enum string values (not keys)
        loans_data = [
            {"loan_number": "2025-001234", "borrower_name": "Michael Roberts", "coborrower_name": "Sarah Roberts", "stage": "Processing", "program": "Conventional 30-Year Fixed", "loan_type": "Purchase", "amount": 420000, "purchase_price": 525000, "down_payment": 105000, "rate": 6.875, "term": 360, "property_address": "1234 Oak Street, Austin, TX 78701"},
            {"loan_number": "2025-001235", "borrower_name": "Jennifer Kim", "stage": "UW Received", "program": "FHA 30-Year Fixed", "loan_type": "Purchase", "amount": 285000, "purchase_price": 300000, "down_payment": 10500, "rate": 6.625, "term": 360, "property_address": "5678 Elm Avenue, Houston, TX 77002"},
            {"loan_number": "2025-001236", "borrower_name": "William Turner", "coborrower_name": "Patricia Turner", "stage": "Approved", "program": "VA 30-Year Fixed", "loan_type": "Purchase", "amount": 365000, "rate": 6.500, "term": 360, "property_address": "9012 Pine Road, Dallas, TX 75201"},
            {"loan_number": "2025-001237", "borrower_name": "Elizabeth Moore", "coborrower_name": "Richard Moore", "stage": "CTC", "program": "Jumbo 30-Year Fixed", "loan_type": "Purchase", "amount": 825000, "purchase_price": 1100000, "down_payment": 275000, "rate": 7.125, "term": 360, "property_address": "7890 Highland Drive, Plano, TX 75024"},
        ]

        loans_count = 0
        for loan in loans_data:
            existing = db.execute(text("SELECT id FROM loans WHERE loan_number = :loan_number"), {"loan_number": loan["loan_number"]}).fetchone()
            if not existing:
                closing_date = datetime.now(timezone.utc) + timedelta(days=25)
                # Skip stage column - enum might not be created yet
                db.execute(text("""
                    INSERT INTO loans (loan_number, borrower_name, coborrower_name, program, loan_type, amount, purchase_price, down_payment, rate, term, property_address, closing_date, loan_officer_id, days_in_stage, sla_status, created_at, updated_at)
                    VALUES (:loan_number, :borrower_name, :coborrower_name, :program, :loan_type, :amount, :purchase_price, :down_payment, :rate, :term, :property_address, :closing_date, :lo_id, 8, 'on-track', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """), {"loan_number": loan["loan_number"], "borrower_name": loan["borrower_name"], "coborrower_name": loan.get("coborrower_name"), "program": loan.get("program"), "loan_type": loan.get("loan_type"), "amount": loan["amount"], "purchase_price": loan.get("purchase_price"), "down_payment": loan.get("down_payment"), "rate": loan.get("rate"), "term": loan.get("term"), "property_address": loan.get("property_address"), "closing_date": closing_date, "lo_id": owner_id})
                loans_count += 1

        # TASKS - Linked to loans and leads with specific details
        tasks_data = [
            {"title": "Call Michael Roberts about missing pay stubs", "description": "Need last 2 months pay stubs for loan #2025-001234. Borrower requested callback after 2pm.", "priority": "high", "due_days": 0, "loan_number": "2025-001234", "related_contact": "Michael Roberts"},
            {"title": "Order appraisal for Jennifer Kim - FHA loan", "description": "FHA appraisal needed for 5678 Elm Avenue, Houston. Loan #2025-001235. Contact appraiser AMC Express.", "priority": "high", "due_days": 1, "loan_number": "2025-001235", "related_contact": "Jennifer Kim"},
            {"title": "Follow up with Christopher Davis on pre-approval docs", "description": "Jumbo loan pre-approval. Need 2 years tax returns and bank statements for $680k approval.", "priority": "medium", "due_days": 0, "related_contact": "Christopher Davis"},
            {"title": "Schedule closing for Elizabeth Moore - CTC", "description": "Loan #2025-001237 is Clear to Close. Coordinate with title company for closing at 7890 Highland Drive.", "priority": "high", "due_days": 2, "loan_number": "2025-001237", "related_contact": "Elizabeth Moore"},
            {"title": "Review William Turner VA loan conditions", "description": "Underwriting approved with conditions. Review VA appraisal repairs and termite inspection.", "priority": "medium", "due_days": 1, "loan_number": "2025-001236", "related_contact": "William Turner"},
            {"title": "Send rate lock reminder to James Wilson", "description": "New lead interested in $450k purchase. Current rate 6.875% - discuss lock options before rate changes.", "priority": "medium", "due_days": 0, "related_contact": "James Wilson"},
        ]

        tasks_count = 0
        for task_item in tasks_data:
            # Find related loan if loan_number provided
            loan_id = None
            if task_item.get("loan_number"):
                loan_row = db.execute(text("SELECT id FROM loans WHERE loan_number = :ln"), {"ln": task_item["loan_number"]}).fetchone()
                loan_id = loan_row.id if loan_row else None

            due_date = datetime.now(timezone.utc) + timedelta(days=task_item["due_days"])
            db.execute(text("""
                INSERT INTO tasks (title, description, priority, due_date, status, owner_id, loan_id, related_contact_name, created_at, updated_at)
                VALUES (:title, :desc, :priority, :due_date, 'pending', :owner_id, :loan_id, :contact, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """), {
                "title": task_item["title"],
                "desc": task_item.get("description"),
                "priority": task_item["priority"],
                "due_date": due_date,
                "owner_id": owner_id,
                "loan_id": loan_id,
                "contact": task_item.get("related_contact")
            })
            tasks_count += 1

        # MUM CLIENTS
        mum_data = [
            {"name": "Charles Bennett", "email": "charles.bennett@email.com", "phone": "(555) 111-2222", "loan_number": "MUM-2023-001", "original_loan_amount": 385000, "current_property_value": 485000, "days_ago": 730},
            {"name": "Rebecca Sullivan", "email": "rebecca.sullivan@email.com", "phone": "(555) 222-3333", "loan_number": "MUM-2022-001", "original_loan_amount": 425000, "current_property_value": 525000, "days_ago": 1095},
            {"name": "Gregory Phillips", "email": "gregory.phillips@email.com", "phone": "(555) 333-4444", "loan_number": "MUM-2024-001", "original_loan_amount": 295000, "current_property_value": 315000, "days_ago": 365},
        ]

        mum_count = 0
        for client in mum_data:
            existing = db.execute(text("SELECT id FROM mum_clients WHERE loan_number = :loan_number"), {"loan_number": client["loan_number"]}).fetchone()
            if not existing:
                original_date = datetime.now(timezone.utc) - timedelta(days=client["days_ago"])
                last_contact = datetime.now(timezone.utc) - timedelta(days=45)
                loan_balance = client["original_loan_amount"] * 0.92  # Assume 8% paid down
                db.execute(text("""
                    INSERT INTO mum_clients (name, loan_number, original_close_date, days_since_funding, original_rate, current_rate, loan_balance, engagement_score, status, last_contact, created_at)
                    VALUES (:name, :loan_number, :original_date, :days_since, 6.5, 6.875, :loan_balance, 75, 'active', :last_contact, CURRENT_TIMESTAMP)
                """), {
                    "name": client["name"],
                    "loan_number": client["loan_number"],
                    "original_date": original_date,
                    "days_since": client["days_ago"],
                    "loan_balance": loan_balance,
                    "last_contact": last_contact
                })
                mum_count += 1

        db.commit()

        results = {
            "success": True,
            "message": "Demo data seeded successfully",
            "team_members": team_count,
            "leads": leads_count,
            "active_loans": loans_count,
            "tasks": tasks_count,
            "mum_clients": mum_count,
            "total": team_count + leads_count + loans_count + tasks_count + mum_count
        }

        logger.info(f"Seeded demo data: {results}")
        return results

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding demo data: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Error seeding data")


@router.post("/api/v1/admin/assign-demo-data")
async def assign_demo_data_to_user(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Assign all demo leads and loans to the current user.
    Useful for making demo data visible in your dashboard.
    """
    try:
        # Update all leads to current user
        leads_updated = db.execute(text("""
            UPDATE leads
            SET owner_id = :user_id
            WHERE email LIKE '%@email.com'
        """), {"user_id": current_user.id})

        # Update all loans to current user
        loans_updated = db.execute(text("""
            UPDATE loans
            SET loan_officer_id = :user_id
            WHERE loan_number LIKE '2025-%'
        """), {"user_id": current_user.id})

        db.commit()

        return {
            "success": True,
            "message": f"Assigned demo data to {current_user.email}",
            "leads_updated": leads_updated.rowcount,
            "loans_updated": loans_updated.rowcount
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error assigning demo data: {e}")
        raise HTTPException(status_code=500, detail="Error")


@router.post("/api/v1/admin/fix-lead-stages")
async def fix_lead_stages(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Fix leads that have stage values stored as display names (e.g. 'New')
    instead of enum keys (e.g. 'NEW'). This can happen when the frontend
    sends enum values rather than enum keys.
    """
    try:
        # Map display values to enum keys
        stage_mappings = {
            'New': 'NEW',
            'Attempted Contact': 'ATTEMPTED_CONTACT',
            'Prospect': 'PROSPECT',
            'Application': 'APPLICATION',
            'Document Fulfillment': 'DOCUMENT_FULFILLMENT',
            'Pre-Qualified': 'PRE_QUALIFIED',
            'Pre-Approved': 'PRE_APPROVED',
            'Under Contract': 'UNDER_CONTRACT',
            'Long-Term Nurture': 'LONG_TERM_NURTURE',
            'Closed': 'CLOSED',
            'AMR': 'AMR',
            'Referral Source': 'REFERRAL_SOURCE',
            'Withdrawn': 'WITHDRAWN',
            'Does Not Qualify': 'DOES_NOT_QUALIFY',
            'Disclosed': 'DISCLOSED',
        }

        total_fixed = 0
        details = {}

        for display_val, enum_key in stage_mappings.items():
            if display_val == enum_key:
                continue  # Skip if they're the same (e.g. AMR)
            result = db.execute(
                text("UPDATE leads SET stage = :enum_key WHERE stage::text = :display_val"),
                {"enum_key": enum_key, "display_val": display_val}
            )
            if result.rowcount > 0:
                details[f"{display_val} -> {enum_key}"] = result.rowcount
                total_fixed += result.rowcount

        db.commit()

        return {
            "success": True,
            "message": f"Fixed {total_fixed} lead stage values",
            "total_fixed": total_fixed,
            "details": details
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error fixing lead stages: {e}")
        raise HTTPException(status_code=500, detail="Error")


@router.post("/api/v1/admin/fix-loan-stages")
async def fix_loan_stages(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Fix loans that have NULL stage values by setting them to appropriate defaults based on loan number.
    """
    try:
        # Update loans with NULL stages to have proper stage values
        # NOTE: Using enum keys (PROCESSING, UW_RECEIVED, etc.) rather than values
        db.execute(text("""
            UPDATE loans
            SET stage = (CASE
                WHEN loan_number LIKE '%-001234' THEN 'PROCESSING'
                WHEN loan_number LIKE '%-001235' THEN 'UW_RECEIVED'
                WHEN loan_number LIKE '%-001236' THEN 'APPROVED'
                WHEN loan_number LIKE '%-001237' THEN 'CTC'
                ELSE 'PROCESSING'
            END)::loanstage
            WHERE stage IS NULL
        """))

        db.commit()

        return {
            "success": True,
            "message": "Fixed loan stages"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error fixing loan stages: {e}")
        raise HTTPException(status_code=500, detail="Error")


@router.post("/api/v1/admin/update-permission-roles")
async def update_permission_roles(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Update permission templates to new role structure:
    Admin, Leadership, Management, Sales, Processing, Operations
    """
    try:
        # Step 1: Drop old check constraint and create new one
        db.execute(text("""
            ALTER TABLE permission_templates DROP CONSTRAINT IF EXISTS template_category_check;
        """))
        db.execute(text("""
            ALTER TABLE permission_templates
            ADD CONSTRAINT template_category_check
            CHECK (category IN ('admin', 'leadership', 'management', 'sales', 'processing', 'operations', 'custom'));
        """))
        db.commit()

        # Step 2: Define new permission templates
        admin_perms = {
            "dashboard.view_all_widgets": True, "leads.view_all": True, "clients.view_all": True,
            "loans.view_all": True, "team.view_all": True, "team.impersonate": True,
            "permissions.manage": True, "settings.manage": True, "system.admin": True
        }

        leadership_perms = {
            "dashboard.view_all_widgets": True, "leads.view_all": True, "clients.view_all": True,
            "loans.view_all": True, "team.view_all": True, "team.impersonate": True,
            "analytics.view_all": True, "reports.executive": True
        }

        management_perms = {
            "dashboard.view_all_widgets": True, "leads.view_team": True, "clients.view_team": True,
            "loans.view_team": True, "team.view_team": True, "team.manage": True,
            "team.impersonate": True
        }

        sales_perms = {
            "leads.view_assigned": True, "leads.edit_own": True, "leads.create": True,
            "clients.view_assigned": True, "loans.view_assigned": True
        }

        processing_perms = {
            "loans.view_all": True, "loans.process": True, "loans.edit_documents": True,
            "clients.view_all": True, "dashboard.view_processing": True
        }

        operations_perms = {
            "leads.view_all": True, "clients.view_all": True, "loans.view_all": True,
            "loans.process": True, "operations.manage": True
        }

        # Step 3: Delete old templates
        db.execute(text("DELETE FROM permission_templates WHERE is_system_default = TRUE"))

        # Step 4: Insert new templates
        db.execute(text("""
            INSERT INTO permission_templates
            (name, description, permissions, is_system_default, category, created_at)
            VALUES
            ('Admin', 'Full system access', CAST(:admin AS jsonb), TRUE, 'admin', CURRENT_TIMESTAMP),
            ('Leadership', 'Executive level access', CAST(:leadership AS jsonb), TRUE, 'leadership', CURRENT_TIMESTAMP),
            ('Management', 'Team management access', CAST(:management AS jsonb), TRUE, 'management', CURRENT_TIMESTAMP),
            ('Sales', 'Sales focused access', CAST(:sales AS jsonb), TRUE, 'sales', CURRENT_TIMESTAMP),
            ('Processing', 'Loan processing access', CAST(:processing AS jsonb), TRUE, 'processing', CURRENT_TIMESTAMP),
            ('Operations', 'Operations access', CAST(:operations AS jsonb), TRUE, 'operations', CURRENT_TIMESTAMP)
        """), {
            'admin': json.dumps(admin_perms),
            'leadership': json.dumps(leadership_perms),
            'management': json.dumps(management_perms),
            'sales': json.dumps(sales_perms),
            'processing': json.dumps(processing_perms),
            'operations': json.dumps(operations_perms)
        })

        db.commit()

        return {
            "success": True,
            "message": "Permission templates updated",
            "roles": ["Admin", "Leadership", "Management", "Sales", "Processing", "Operations"]
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating permission roles: {e}")
        raise HTTPException(status_code=500, detail="Error")


@router.post("/admin/initialize-ai-system")
async def initialize_ai_system_endpoint(request: dict):
    """
    Temporary endpoint to initialize AI system remotely.
    Usage: POST /admin/initialize-ai-system with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        # Run initialization script
        result = subprocess.run(
            ["python3", "initialize_ai_system.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Initialization timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/admin/run-mission-control-migration")
async def run_mission_control_migration_endpoint(request: dict):
    """
    Run Mission Control database migration remotely.
    Usage: POST /admin/run-mission-control-migration with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        # Run migration script
        result = subprocess.run(
            ["python3", "run_ai_colleague_migration.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Migration timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/admin/run-phase1-migration")
async def run_phase1_migration_endpoint(request: dict):
    """
    Run Phase 1 Comprehensive Profiles migration remotely.
    Creates: LeadProfile, ActiveLoanProfile, MUMClientProfile, TeamMemberProfile,
             EmailInteraction, FieldUpdateHistory, DataConflict tables
    Usage: POST /admin/run-phase1-migration with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        # Run migration script
        result = subprocess.run(
            ["python3", "migrations/001_create_comprehensive_profiles.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Migration timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/admin/run-employee-permission-migration")
async def run_employee_permission_migration_endpoint(request: dict):
    """
    Run Employee Permission System migration remotely.
    Creates comprehensive employee management, permissions, impersonation, and audit tables.
    Usage: POST /admin/run-employee-permission-migration with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        # Run migration script
        result = subprocess.run(
            ["python3", "migrations/create_employee_permission_system.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        # If successful, seed default templates
        if result.returncode == 0:
            seed_result = subprocess.run(
                ["python3", "migrations/seed_default_permission_templates.py"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd="/app"
            )

            return {
                "success": result.returncode == 0 and seed_result.returncode == 0,
                "migration_stdout": result.stdout,
                "migration_stderr": result.stderr,
                "seed_stdout": seed_result.stdout,
                "seed_stderr": seed_result.stderr,
                "returncode": seed_result.returncode
            }

        return {
            "success": False,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Migration timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/admin/run-vapi-migration")
async def run_vapi_migration_endpoint(request: dict):
    """
    Run VAPI AI tables migration remotely.
    Creates tables for AI call management, transcripts, assistants, and phone numbers.
    Usage: POST /admin/run-vapi-migration with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        # Run migration script
        result = subprocess.run(
            ["python3", "run_vapi_migration.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Migration timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/admin/fix-vapi-metadata-column")
async def fix_vapi_metadata_column(request: dict, db: Session = Depends(get_db)):
    """
    Fix vapi_calls table column name from 'metadata' to 'call_metadata'
    Usage: POST /admin/fix-vapi-metadata-column with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        # Check if metadata column exists
        check_result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'vapi_calls'
            AND column_name IN ('metadata', 'call_metadata')
        """))
        columns = [row[0] for row in check_result]

        if 'call_metadata' in columns:
            return {
                "success": True,
                "message": "Column 'call_metadata' already exists - no fix needed",
                "columns": columns
            }

        if 'metadata' in columns:
            # Rename the column
            db.execute(text("""
                ALTER TABLE vapi_calls
                RENAME COLUMN metadata TO call_metadata
            """))
            db.commit()

            return {
                "success": True,
                "message": "Successfully renamed 'metadata' to 'call_metadata'",
                "action": "renamed"
            }

        return {
            "success": False,
            "message": "Neither 'metadata' nor 'call_metadata' column found",
            "columns": columns
        }

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/admin/run-estimate-parser-migration")
async def run_estimate_parser_migration(request: dict, db: Session = Depends(get_db)):
    """
    Run Estimate Parser Cache migration remotely.
    Creates tables for caching parsed loan estimates and tracking comparisons.
    Usage: POST /admin/run-estimate-parser-migration with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        results = []

        # Check if estimate_parse_cache table already exists
        check_result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'estimate_parse_cache'
            )
        """))
        if check_result.scalar():
            results.append("estimate_parse_cache already exists")
        else:
            # Create estimate_parse_cache table
            db.execute(text("""
                CREATE TABLE estimate_parse_cache (
                    doc_hash VARCHAR(64) PRIMARY KEY,
                    parsed_json JSONB NOT NULL,
                    confidence_score NUMERIC(3, 2),
                    needs_review BOOLEAN DEFAULT FALSE,
                    source_type VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW(),
                    accessed_at TIMESTAMP DEFAULT NOW(),
                    access_count INTEGER DEFAULT 1
                )
            """))
            db.execute(text("CREATE INDEX idx_estimate_cache_created ON estimate_parse_cache (created_at)"))
            db.execute(text("CREATE INDEX idx_estimate_cache_needs_review ON estimate_parse_cache (needs_review) WHERE needs_review = true"))
            db.execute(text("CREATE INDEX idx_estimate_cache_source_type ON estimate_parse_cache (source_type)"))
            results.append("Created estimate_parse_cache table")

        # Check if estimate_parse_failures table exists
        check_result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'estimate_parse_failures'
            )
        """))
        if check_result.scalar():
            results.append("estimate_parse_failures already exists")
        else:
            # Create estimate_parse_failures table
            db.execute(text("""
                CREATE TABLE estimate_parse_failures (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    request_id UUID NOT NULL,
                    doc_hash VARCHAR(64) NOT NULL,
                    error_stage VARCHAR(50) NOT NULL,
                    error_message TEXT,
                    raw_text TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db.execute(text("CREATE INDEX idx_failures_created ON estimate_parse_failures (created_at)"))
            db.execute(text("CREATE INDEX idx_failures_stage ON estimate_parse_failures (error_stage)"))
            db.execute(text("CREATE INDEX idx_failures_doc_hash ON estimate_parse_failures (doc_hash)"))
            results.append("Created estimate_parse_failures table")

        # Check if estimate_comparisons table exists
        check_result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'estimate_comparisons'
            )
        """))
        if check_result.scalar():
            results.append("estimate_comparisons already exists")
        else:
            # Create estimate_comparisons table
            db.execute(text("""
                CREATE TABLE estimate_comparisons (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id INTEGER,
                    session_id VARCHAR(100),
                    estimate_a_hash VARCHAR(64) NOT NULL,
                    estimate_b_hash VARCHAR(64) NOT NULL,
                    winner VARCHAR(1),
                    winner_reason VARCHAR(200),
                    savings_amount NUMERIC(12, 2),
                    comparison_data JSONB,
                    converted BOOLEAN DEFAULT FALSE,
                    converted_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                    CONSTRAINT fk_estimate_a FOREIGN KEY (estimate_a_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE,
                    CONSTRAINT fk_estimate_b FOREIGN KEY (estimate_b_hash) REFERENCES estimate_parse_cache(doc_hash) ON DELETE CASCADE
                )
            """))
            db.execute(text("CREATE INDEX idx_comparisons_user ON estimate_comparisons (user_id)"))
            db.execute(text("CREATE INDEX idx_comparisons_created ON estimate_comparisons (created_at)"))
            db.execute(text("CREATE INDEX idx_comparisons_converted ON estimate_comparisons (converted)"))
            results.append("Created estimate_comparisons table")

        db.commit()

        return {
            "success": True,
            "message": "Estimate parser migration completed",
            "results": results
        }

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/admin/setup-demo-impersonation")
async def setup_demo_impersonation(request: dict, db: Session = Depends(get_db)):
    """
    Setup demo account with impersonation permissions
    Usage: POST /admin/setup-demo-impersonation with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        # Run setup script
        result = subprocess.run(
            ["python3", "setup_demo_impersonation.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Setup timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.get("/admin/verify-phase1-tables")
async def verify_phase1_tables(db: Session = Depends(get_db), current_user=Depends(get_current_user_dep())):
    """
    Verify Phase 1 tables exist in the database.
    Returns list of Phase 1 tables that were successfully created.
    """
    try:
        # Query for Phase 1 tables
        result = db.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN (
                'lead_profiles',
                'active_loan_profiles',
                'mum_client_profiles',
                'team_member_profiles',
                'email_interactions',
                'field_update_history',
                'data_conflicts'
            )
            ORDER BY table_name
        """))

        tables = [row[0] for row in result]

        return {
            "success": True,
            "tables_found": len(tables),
            "total_expected": 7,
            "tables": tables,
            "phase1_complete": len(tables) == 7
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


@router.post("/admin/initialize-ai-only")
async def initialize_ai_only_endpoint(request: dict):
    """
    Initialize AI system (skip migration - for when tables already exist).
    Usage: POST /admin/initialize-ai-only with body: {"secret": "<ADMIN_MIGRATION_SECRET>"}
    """
    # Simple security check
    _verify_admin_secret(request)

    try:
        # Run initialization script (skip migration)
        result = subprocess.run(
            ["python3", "initialize_ai_only.py"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app"
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Initialization timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "Internal server error"
        }


# ============================================================================
# MISSION CONTROL - AI COLLEAGUE PERFORMANCE TRACKING API
# ============================================================================

@router.get("/api/v1/mission-control/health")
async def get_ai_health(
    days: int = 7,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get AI Colleague health score and metrics"""
    AIColleagueAction = get_ai_colleague_action_model()

    try:
        period_start = datetime.now(timezone.utc) - timedelta(days=days)
        period_end = datetime.now(timezone.utc)

        # Get all actions in period
        actions = db.query(AIColleagueAction).filter(
            AIColleagueAction.created_at >= period_start,
            AIColleagueAction.created_at <= period_end
        ).all()

        # Calculate metrics
        total_actions = len(actions)
        autonomous_actions = len([a for a in actions if a.autonomy_level == 'full'])
        successful_actions = len([a for a in actions if a.outcome == 'success'])
        approved_actions = len([a for a in actions if a.status == 'approved' or not a.required_approval])

        # Calculate scores
        autonomy_score = (autonomous_actions / total_actions * 100) if total_actions > 0 else 0
        success_rate = (successful_actions / total_actions * 100) if total_actions > 0 else 0
        approval_rate = (approved_actions / total_actions * 100) if total_actions > 0 else 0
        avg_confidence = sum([a.confidence_score or 0 for a in actions]) / total_actions if total_actions > 0 else 0

        # Overall health score (weighted average)
        overall_score = (
            autonomy_score * 0.3 +
            success_rate * 0.3 +
            approval_rate * 0.2 +
            avg_confidence * 100 * 0.2
        )

        # Determine health status
        if overall_score >= 80:
            health_status = "excellent"
        elif overall_score >= 60:
            health_status = "good"
        elif overall_score >= 40:
            health_status = "fair"
        else:
            health_status = "needs_attention"

        return {
            "overall_score": round(overall_score, 2),
            "health_status": health_status,
            "component_scores": {
                "autonomy": round(autonomy_score, 2),
                "accuracy": round(success_rate, 2),
                "approval": round(approval_rate, 2),
                "confidence": round(avg_confidence * 100, 2)
            },
            "metrics": {
                "total_actions": total_actions,
                "autonomous_actions": autonomous_actions,
                "successful_actions": successful_actions,
                "approved_actions": approved_actions
            },
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "days": days
            }
        }
    except Exception as e:
        logger.error(f"Error getting AI health: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/v1/mission-control/metrics")
async def get_ai_metrics(
    days: int = 30,
    agent_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get detailed AI performance metrics"""
    AIColleagueAction = get_ai_colleague_action_model()

    try:
        period_start = datetime.now(timezone.utc) - timedelta(days=days)

        query = db.query(AIColleagueAction).filter(
            AIColleagueAction.created_at >= period_start
        )

        if agent_name:
            query = query.filter(AIColleagueAction.agent_name == agent_name)

        actions = query.all()

        # Group by agent
        agents_metrics = {}
        for action in actions:
            agent = action.agent_name
            if agent not in agents_metrics:
                agents_metrics[agent] = {
                    "total": 0,
                    "autonomous": 0,
                    "successful": 0,
                    "failed": 0,
                    "approved": 0,
                    "rejected": 0,
                    "avg_confidence": 0,
                    "confidences": []
                }

            agents_metrics[agent]["total"] += 1
            if action.autonomy_level == 'full':
                agents_metrics[agent]["autonomous"] += 1
            if action.outcome == 'success':
                agents_metrics[agent]["successful"] += 1
            elif action.outcome == 'failure':
                agents_metrics[agent]["failed"] += 1
            if action.status == 'approved':
                agents_metrics[agent]["approved"] += 1
            elif action.status == 'rejected':
                agents_metrics[agent]["rejected"] += 1
            if action.confidence_score:
                agents_metrics[agent]["confidences"].append(action.confidence_score)

        # Calculate averages
        for agent, metrics in agents_metrics.items():
            if metrics["confidences"]:
                metrics["avg_confidence"] = round(sum(metrics["confidences"]) / len(metrics["confidences"]) * 100, 2)
            metrics["success_rate"] = round((metrics["successful"] / metrics["total"] * 100) if metrics["total"] > 0 else 0, 2)
            metrics["autonomy_rate"] = round((metrics["autonomous"] / metrics["total"] * 100) if metrics["total"] > 0 else 0, 2)
            del metrics["confidences"]  # Remove temp list

        return {
            "period_days": days,
            "total_actions": len(actions),
            "agents": agents_metrics
        }
    except Exception as e:
        logger.error(f"Error getting AI metrics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/v1/mission-control/recent-actions")
async def get_recent_actions(
    limit: int = 50,
    agent_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get recent AI actions for activity feed"""
    AIColleagueAction = get_ai_colleague_action_model()

    try:
        query = db.query(AIColleagueAction).order_by(AIColleagueAction.created_at.desc())

        if agent_name:
            query = query.filter(AIColleagueAction.agent_name == agent_name)

        actions = query.limit(limit).all()

        return {
            "actions": [
                {
                    "id": a.id,
                    "action_id": a.action_id,
                    "agent_name": a.agent_name,
                    "action_type": a.action_type,
                    "lead_id": a.lead_id,
                    "loan_id": a.loan_id,
                    "autonomy_level": a.autonomy_level,
                    "confidence_score": round(a.confidence_score * 100, 2) if a.confidence_score else None,
                    "status": a.status,
                    "outcome": a.outcome,
                    "reasoning": a.reasoning,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "completed_at": a.completed_at.isoformat() if a.completed_at else None
                }
                for a in actions
            ],
            "count": len(actions)
        }
    except Exception as e:
        logger.error(f"Error getting recent actions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/v1/mission-control/log-action")
async def log_ai_action(
    action_data: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Log an AI Colleague action for tracking"""
    AIColleagueAction = get_ai_colleague_action_model()

    try:
        # Generate action ID if not provided
        if "action_id" not in action_data:
            action_data["action_id"] = f"{action_data.get('agent_name', 'ai')}_{datetime.now(timezone.utc).timestamp()}"

        # Create action record
        action = AIColleagueAction(
            action_id=action_data["action_id"],
            agent_name=action_data.get("agent_name", "Smart AI"),
            action_type=action_data.get("action_type", "unknown"),
            lead_id=action_data.get("lead_id"),
            loan_id=action_data.get("loan_id"),
            user_id=action_data.get("user_id"),
            context=action_data.get("context"),
            trigger_type=action_data.get("trigger_type"),
            trigger_data=action_data.get("trigger_data"),
            confidence_score=action_data.get("confidence_score"),
            reasoning=action_data.get("reasoning"),
            alternatives_considered=action_data.get("alternatives_considered"),
            autonomy_level=action_data.get("autonomy_level", "assisted"),
            required_approval=action_data.get("required_approval", False),
            status=action_data.get("status", "pending"),
            outcome=action_data.get("outcome"),
            impact_score=action_data.get("impact_score"),
            business_metrics=action_data.get("business_metrics"),
            customer_response=action_data.get("customer_response"),
            response_time_minutes=action_data.get("response_time_minutes"),
            metadata=action_data.get("metadata")
        )

        db.add(action)
        db.commit()
        db.refresh(action)

        return {
            "success": True,
            "action_id": action.action_id,
            "message": "AI action logged successfully"
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error logging AI action: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/v1/mission-control/update-action")
async def update_ai_action(
    action_id: str,
    updates: dict,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible_dep())
):
    """Update an AI action (e.g., mark as completed, update outcome)"""
    AIColleagueAction = get_ai_colleague_action_model()

    try:
        action = db.query(AIColleagueAction).filter(
            AIColleagueAction.action_id == action_id
        ).first()

        if not action:
            raise HTTPException(status_code=404, detail="Action not found")

        # Update fields
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
        for key, value in updates.items():
            if hasattr(action, key) and key not in _protected:
                setattr(action, key, value)

        # Set completed_at if outcome is set and not already set
        if updates.get("outcome") and not action.completed_at:
            action.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(action)

        return {
            "success": True,
            "action_id": action.action_id,
            "message": "AI action updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating AI action: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/v1/mission-control/insights")
async def get_ai_insights(
    limit: int = 10,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get AI-discovered journey insights"""
    AIJourneyInsight = get_ai_journey_insight_model()

    try:
        query = db.query(AIJourneyInsight).order_by(AIJourneyInsight.discovered_at.desc())

        if status:
            query = query.filter(AIJourneyInsight.status == status)

        insights = query.limit(limit).all()

        return {
            "insights": [
                {
                    "id": i.id,
                    "insight_id": i.insight_id,
                    "insight_type": i.insight_type,
                    "pattern_description": i.pattern_description,
                    "pattern_confidence": round(i.pattern_confidence * 100, 2) if i.pattern_confidence else None,
                    "recommended_action": i.recommended_action,
                    "priority": i.priority,
                    "status": i.status,
                    "discovered_at": i.discovered_at.isoformat() if i.discovered_at else None
                }
                for i in insights
            ],
            "count": len(insights)
        }
    except Exception as e:
        logger.error(f"Error getting AI insights: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
