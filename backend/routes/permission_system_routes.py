"""
Permission System API Routes

API endpoints for the permission management system including:
- Permission Request Workflow (create, list, approve, deny requests)
- Notifications (get, mark read, mark all read)
- Access Certification (due certifications, certification details, certify, skip, history)
- Compliance Dashboard (overview, by-department, export)
- Certification Background Jobs (manual triggers)
- Access & Audit (audit log, impersonation history, active sessions, revoke sessions)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from typing import Optional, List, Callable, Any
from pydantic import BaseModel
from datetime import datetime, date, timezone, timedelta
import logging
import csv
import io

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Permission System"])

# ============================================================================
# DEPENDENCY INJECTION STORAGE
# ============================================================================

_get_db: Callable = None
_get_current_user: Callable = None
_User: Any = None
_AuditLog: Any = None
_ImpersonationSession: Any = None
_UserSession: Any = None
_has_permission: Callable = None


def set_dependencies(
    get_db_func: Callable,
    get_current_user_func: Callable,
    user_model: Any,
    audit_log_model: Any = None,
    impersonation_session_model: Any = None,
    user_session_model: Any = None,
    has_permission_func: Callable = None
):
    """Set dependencies from main.py to avoid circular imports."""
    global _get_db, _get_current_user, _User, _AuditLog, _ImpersonationSession, _UserSession, _has_permission
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _User = user_model
    _AuditLog = audit_log_model
    _ImpersonationSession = impersonation_session_model
    _UserSession = user_session_model
    _has_permission = has_permission_func
    logger.info("Permission system routes dependencies set")


def get_db():
    """Get database session dependency - wrapper for injected dependency."""
    if _get_db is None:
        raise RuntimeError("Permission system routes not initialized. Call set_dependencies first.")
    yield from _get_db()


async def get_current_user(db: Session = Depends(get_db)):
    """Get current user dependency - wrapper for injected dependency."""
    if _get_current_user is None:
        raise RuntimeError("Permission system routes not initialized. Call set_dependencies first.")
    # Import Request here to avoid circular import
    from fastapi import Request
    # This will be called with the actual request in the route handler
    raise RuntimeError("Use Depends(get_current_user_dep) instead")


def get_current_user_dep():
    """Get current user - imports from main at runtime to avoid circular imports."""
    import main
    return main.get_current_user


def get_db_dep():
    """Get database session - imports from db module."""
    from db import get_db as db_get_db
    return db_get_db


def has_permission(user_id: int, permission_key: str, db: Session) -> bool:
    """Check if user has permission - uses injected function or imports from main."""
    if _has_permission is not None:
        return _has_permission(user_id, permission_key, db)
    # Fallback to importing from main
    import main
    return main.has_permission(user_id, permission_key, db)


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class RevokeSessionRequest(BaseModel):
    reason: Optional[str] = None


# ============================================================================
# PERMISSION REQUEST WORKFLOW - API ENDPOINTS
# ============================================================================

@router.post("/permission-requests")
async def create_permission_request(
    request: dict,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Employee creates a permission request
    Body: {
        "permission_key": "view_production_tracker",
        "justification": "I need this to track my sales performance...",
        "urgency": "medium",
        "is_temporary": false,
        "duration_days": null
    }
    """
    try:
        # Validate justification length
        justification = request.get('justification', '')
        if len(justification) < 50:
            raise HTTPException(status_code=400, detail="Justification must be at least 50 characters")

        permission_key = request.get('permission_key')
        if not permission_key:
            raise HTTPException(status_code=400, detail="permission_key is required")

        # Check if user already has this permission
        existing_perm = db.execute(text("""
            SELECT granted FROM user_permissions
            WHERE user_id = :user_id AND permission_key = :permission_key
        """), {
            'user_id': current_user.id,
            'permission_key': permission_key
        }).fetchone()

        if existing_perm and existing_perm[0]:
            raise HTTPException(status_code=400, detail="You already have this permission")

        # Check if there's already a pending request
        pending_request = db.execute(text("""
            SELECT id FROM permission_requests
            WHERE employee_id = :user_id AND permission_key = :permission_key AND status = 'pending'
        """), {
            'user_id': current_user.id,
            'permission_key': permission_key
        }).fetchone()

        if pending_request:
            raise HTTPException(status_code=400, detail="You already have a pending request for this permission")

        # Create request
        urgency = request.get('urgency', 'medium')
        is_temporary = request.get('is_temporary', False)
        duration_days = request.get('duration_days')

        if is_temporary and not duration_days:
            raise HTTPException(status_code=400, detail="duration_days required for temporary permissions")

        result = db.execute(text("""
            INSERT INTO permission_requests
            (employee_id, permission_key, justification, urgency, is_temporary, duration_days, status, created_at, updated_at)
            VALUES (:employee_id, :permission_key, :justification, :urgency, :is_temporary, :duration_days, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
        """), {
            'employee_id': current_user.id,
            'permission_key': permission_key,
            'justification': justification,
            'urgency': urgency,
            'is_temporary': is_temporary,
            'duration_days': duration_days
        })

        db.commit()
        request_id = result.fetchone()[0]

        logger.info(f"Permission request created: {request_id} by user {current_user.email} for {permission_key}")

        return {
            "success": True,
            "request_id": request_id,
            "status": "pending",
            "message": "Permission request submitted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create permission request error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/permission-requests")
async def get_permission_requests(
    status: Optional[str] = None,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Employees see their own requests
    Managers see their team's pending requests
    """
    try:
        # Check if user is a manager
        is_manager = current_user.role in ['manager', 'management'] or current_user.permission_role in ['management']

        if is_manager:
            # Managers see all requests (or filtered by status)
            if status:
                requests = db.execute(text("""
                    SELECT pr.*, u.full_name as employee_name, u.email as employee_email
                    FROM permission_requests pr
                    JOIN users u ON pr.employee_id = u.id
                    WHERE pr.status = :status
                    ORDER BY pr.created_at DESC
                """), {'status': status}).fetchall()
            else:
                # Default to pending for managers
                requests = db.execute(text("""
                    SELECT pr.*, u.full_name as employee_name, u.email as employee_email
                    FROM permission_requests pr
                    JOIN users u ON pr.employee_id = u.id
                    WHERE pr.status = 'pending'
                    ORDER BY pr.created_at DESC
                """)).fetchall()
        else:
            # Employees see only their own requests
            if status:
                requests = db.execute(text("""
                    SELECT pr.*, u.full_name as employee_name, u.email as employee_email
                    FROM permission_requests pr
                    JOIN users u ON pr.employee_id = u.id
                    WHERE pr.employee_id = :user_id AND pr.status = :status
                    ORDER BY pr.created_at DESC
                """), {'user_id': current_user.id, 'status': status}).fetchall()
            else:
                requests = db.execute(text("""
                    SELECT pr.*, u.full_name as employee_name, u.email as employee_email
                    FROM permission_requests pr
                    JOIN users u ON pr.employee_id = u.id
                    WHERE pr.employee_id = :user_id
                    ORDER BY pr.created_at DESC
                """), {'user_id': current_user.id}).fetchall()

        return {
            "requests": [
                {
                    "id": req.id,
                    "employee_id": req.employee_id,
                    "employee_name": req.employee_name,
                    "employee_email": req.employee_email,
                    "permission_key": req.permission_key,
                    "justification": req.justification,
                    "urgency": req.urgency,
                    "is_temporary": req.is_temporary,
                    "duration_days": req.duration_days,
                    "status": req.status,
                    "manager_notes": req.manager_notes,
                    "created_at": req.created_at.isoformat() if req.created_at else None,
                    "decided_at": req.decided_at.isoformat() if req.decided_at else None
                }
                for req in requests
            ]
        }

    except Exception as e:
        logger.error(f"Get permission requests error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/permission-requests/{request_id}/approve")
async def approve_permission_request(
    request_id: int,
    data: dict,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Manager approves permission request and grants the permission"""

    try:
        # Check if user is a manager
        is_manager = current_user.role in ['manager', 'management'] or current_user.permission_role in ['management']
        if not is_manager:
            raise HTTPException(status_code=403, detail="Only managers can approve requests")

        # Get the request
        perm_request = db.execute(text("""
            SELECT * FROM permission_requests WHERE id = :request_id
        """), {'request_id': request_id}).fetchone()

        if not perm_request:
            raise HTTPException(status_code=404, detail="Request not found")

        if perm_request.status != 'pending':
            raise HTTPException(status_code=400, detail="Request already processed")

        # Update request status
        notes = data.get('notes', '')
        db.execute(text("""
            UPDATE permission_requests
            SET status = 'approved',
                manager_notes = :notes,
                decided_by_id = :decided_by,
                decided_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :request_id
        """), {
            'request_id': request_id,
            'notes': notes,
            'decided_by': current_user.id
        })

        # Grant the permission
        expires_at = None
        if perm_request.is_temporary and perm_request.duration_days:
            # Calculate expiration date
            expires_at = datetime.now(timezone.utc) + timedelta(days=perm_request.duration_days)

        db.execute(text("""
            INSERT INTO user_permissions (user_id, permission_key, granted, granted_by, granted_at, expires_at, created_at, updated_at)
            VALUES (:user_id, :permission_key, TRUE, :granted_by, CURRENT_TIMESTAMP, :expires_at, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, permission_key) DO UPDATE
            SET granted = TRUE, granted_by = :granted_by, granted_at = CURRENT_TIMESTAMP, expires_at = :expires_at, updated_at = CURRENT_TIMESTAMP
        """), {
            'user_id': perm_request.employee_id,
            'permission_key': perm_request.permission_key,
            'granted_by': current_user.id,
            'expires_at': expires_at
        })

        # Create notification for employee
        temp_text = f" (temporary - {perm_request.duration_days} days)" if perm_request.is_temporary else ""
        db.execute(text("""
            INSERT INTO notifications (user_id, type, title, message, link, created_at)
            VALUES (:user_id, :type, :title, :message, :link, CURRENT_TIMESTAMP)
        """), {
            'user_id': perm_request.employee_id,
            'type': 'permission_approved',
            'title': 'Permission Request Approved',
            'message': f'Your request for "{perm_request.permission_key}" has been approved{temp_text}. {notes if notes else ""}',
            'link': '/my-permissions'
        })

        db.commit()

        logger.info(f"Permission request {request_id} approved by {current_user.email}, granted {perm_request.permission_key} to user {perm_request.employee_id}")

        return {
            "success": True,
            "message": "Permission request approved and granted"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approve permission request error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/permission-requests/{request_id}/deny")
async def deny_permission_request(
    request_id: int,
    data: dict,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Manager denies permission request"""

    try:
        # Check if user is a manager
        is_manager = current_user.role in ['manager', 'management'] or current_user.permission_role in ['management']
        if not is_manager:
            raise HTTPException(status_code=403, detail="Only managers can deny requests")

        # Get the request
        perm_request = db.execute(text("""
            SELECT * FROM permission_requests WHERE id = :request_id
        """), {'request_id': request_id}).fetchone()

        if not perm_request:
            raise HTTPException(status_code=404, detail="Request not found")

        if perm_request.status != 'pending':
            raise HTTPException(status_code=400, detail="Request already processed")

        # Validate reason
        reason = data.get('reason', '')
        if not reason:
            raise HTTPException(status_code=400, detail="Reason is required when denying")

        # Update request status
        db.execute(text("""
            UPDATE permission_requests
            SET status = 'denied',
                manager_notes = :reason,
                decided_by_id = :decided_by,
                decided_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :request_id
        """), {
            'request_id': request_id,
            'reason': reason,
            'decided_by': current_user.id
        })

        # Create notification for employee
        db.execute(text("""
            INSERT INTO notifications (user_id, type, title, message, link, created_at)
            VALUES (:user_id, :type, :title, :message, :link, CURRENT_TIMESTAMP)
        """), {
            'user_id': perm_request.employee_id,
            'type': 'permission_denied',
            'title': 'Permission Request Denied',
            'message': f'Your request for "{perm_request.permission_key}" was denied. Reason: {reason}',
            'link': '/my-permissions'
        })

        db.commit()

        logger.info(f"Permission request {request_id} denied by {current_user.email}")

        return {
            "success": True,
            "message": "Permission request denied"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deny permission request error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# NOTIFICATIONS - API ENDPOINTS
# ============================================================================

@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Get notifications for current user"""

    try:
        query = db.execute(text("""
            SELECT * FROM notifications
            WHERE user_id = :user_id
            {}
            ORDER BY created_at DESC
            LIMIT :limit
        """.format("AND is_read = FALSE" if unread_only else "")), {
            'user_id': current_user.id,
            'limit': limit
        })

        notifications = query.fetchall()

        # Get unread count
        unread_count_query = db.execute(text("""
            SELECT COUNT(*) as count FROM notifications
            WHERE user_id = :user_id AND is_read = FALSE
        """), {'user_id': current_user.id})

        unread_count = unread_count_query.fetchone()[0]

        return {
            "notifications": [
                {
                    "id": n.id,
                    "type": n.type,
                    "title": n.title,
                    "message": n.message,
                    "link": n.link,
                    "is_read": n.is_read,
                    "read_at": n.read_at.isoformat() if n.read_at else None,
                    "created_at": n.created_at.isoformat()
                }
                for n in notifications
            ],
            "unread_count": unread_count
        }

    except Exception as e:
        logger.error(f"Get notifications error: {e}")
        # Return empty notifications on error (e.g., table doesn't exist) instead of 500
        try:
            db.rollback()
        except Exception as e:
            logger.error(f"Error during rollback in get_notifications: {e}")
        return {
            "notifications": [],
            "unread_count": 0,
            "error": "Notifications unavailable"
        }


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Mark a notification as read"""

    try:
        # Verify notification belongs to current user
        notification = db.execute(text("""
            SELECT * FROM notifications
            WHERE id = :id AND user_id = :user_id
        """), {
            'id': notification_id,
            'user_id': current_user.id
        }).fetchone()

        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        if notification.is_read:
            return {"success": True, "message": "Already marked as read"}

        # Mark as read
        db.execute(text("""
            UPDATE notifications
            SET is_read = TRUE, read_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {'id': notification_id})

        db.commit()

        return {"success": True, "message": "Notification marked as read"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Mark notification read error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/notifications/read-all")
async def mark_all_notifications_read(
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Mark all notifications as read for current user"""

    try:
        result = db.execute(text("""
            UPDATE notifications
            SET is_read = TRUE, read_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND is_read = FALSE
        """), {'user_id': current_user.id})

        db.commit()

        return {
            "success": True,
            "message": "All notifications marked as read"
        }

    except Exception as e:
        logger.error(f"Mark all notifications read error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# ACCESS CERTIFICATION - API ENDPOINTS
# ============================================================================

@router.get("/certifications/due")
async def get_due_certifications(
    status: Optional[str] = None,  # pending, overdue, all
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Get certifications due for manager's team
    Managers see their direct reports
    Admins see all
    """
    try:
        # Build base query
        if current_user.role == 'manager':
            # Get team member IDs
            team_query = text("""
                SELECT id FROM users WHERE manager_id = :manager_id
            """)
            team_members = db.execute(team_query, {"manager_id": current_user.id}).fetchall()
            team_ids = [m.id for m in team_members]

            if not team_ids:
                return {"certifications": []}

            # Get certifications for team
            query = text("""
                SELECT ac.id, ac.employee_id, ac.certification_period, ac.due_date,
                       ac.status, ac.permissions_snapshot,
                       u.full_name as employee_name
                FROM access_certifications ac
                JOIN users u ON ac.employee_id = u.id
                WHERE ac.employee_id = ANY(:team_ids)
            """)

            if status:
                query = text(str(query) + " AND ac.status = :status")
                certs = db.execute(query, {"team_ids": team_ids, "status": status}).fetchall()
            else:
                query = text(str(query) + " AND ac.status IN ('pending', 'overdue')")
                certs = db.execute(query, {"team_ids": team_ids}).fetchall()

        elif current_user.role in ['management', 'admin']:
            # Get all certifications
            query = text("""
                SELECT ac.id, ac.employee_id, ac.certification_period, ac.due_date,
                       ac.status, ac.permissions_snapshot,
                       u.full_name as employee_name
                FROM access_certifications ac
                JOIN users u ON ac.employee_id = u.id
            """)

            if status:
                query = text(str(query) + " WHERE ac.status = :status")
                certs = db.execute(query, {"status": status}).fetchall()
            else:
                query = text(str(query) + " WHERE ac.status IN ('pending', 'overdue')")
                certs = db.execute(query).fetchall()
        else:
            raise HTTPException(403, "Only managers can view certifications")

        return {
            "certifications": [
                {
                    "id": cert.id,
                    "employee_id": cert.employee_id,
                    "employee_name": cert.employee_name,
                    "certification_period": cert.certification_period,
                    "due_date": cert.due_date.isoformat() if isinstance(cert.due_date, date) else cert.due_date,
                    "status": cert.status,
                    "days_until_due": (cert.due_date - date.today()).days if isinstance(cert.due_date, date) else 0,
                    "permissions_count": len(cert.permissions_snapshot) if cert.permissions_snapshot else 0
                }
                for cert in certs
            ]
        }

    except Exception as e:
        logger.error(f"Get due certifications error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/certifications/{cert_id}")
async def get_certification_details(
    cert_id: int,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Get full certification details including permission snapshot"""
    try:
        query = text("""
            SELECT ac.*, u.full_name, u.role as user_role, u.department, u.manager_id,
                   cb.full_name as certified_by_name
            FROM access_certifications ac
            JOIN users u ON ac.employee_id = u.id
            LEFT JOIN users cb ON ac.certified_by_id = cb.id
            WHERE ac.id = :cert_id
        """)

        cert = db.execute(query, {"cert_id": cert_id}).fetchone()

        if not cert:
            raise HTTPException(404, "Certification not found")

        # Verify access
        if current_user.role not in ['management', 'admin']:
            if cert.manager_id != current_user.id:
                raise HTTPException(403, "Can only view certifications for your team")

        # Get current permissions to compare
        from jobs.certification_jobs import get_user_permissions_dict
        current_permissions = get_user_permissions_dict(cert.employee_id, db)

        # Compare permissions
        snapshot_perms = set(cert.permissions_snapshot.keys()) if cert.permissions_snapshot else set()
        current_perms = set(current_permissions.keys())

        changes = {
            "added": list(current_perms - snapshot_perms),
            "removed": list(snapshot_perms - current_perms)
        }

        return {
            "id": cert.id,
            "employee": {
                "id": cert.employee_id,
                "name": cert.full_name,
                "role": cert.user_role,
                "department": cert.department
            },
            "certification_period": cert.certification_period,
            "due_date": cert.due_date.isoformat(),
            "status": cert.status,
            "permissions_at_snapshot": cert.permissions_snapshot,
            "current_permissions": current_permissions,
            "permissions_changed_since_snapshot": changes,
            "certified_by": cert.certified_by_name if cert.certified_by_name else None,
            "certified_at": cert.certified_at.isoformat() if cert.certified_at else None,
            "certification_notes": cert.certification_notes
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get certification details error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/certifications/{cert_id}/certify")
async def certify_employee_access(
    cert_id: int,
    data: dict,  # { "notes": "...", "permissions_to_revoke": [...] }
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Manager certifies employee's access
    Optionally revoke permissions during certification
    """
    try:
        # Get certification
        query = text("""
            SELECT ac.*, u.manager_id, u.full_name
            FROM access_certifications ac
            JOIN users u ON ac.employee_id = u.id
            WHERE ac.id = :cert_id
        """)

        cert = db.execute(query, {"cert_id": cert_id}).fetchone()

        if not cert:
            raise HTTPException(404, "Certification not found")

        # Verify manager
        if current_user.role not in ['management', 'admin']:
            if cert.manager_id != current_user.id:
                raise HTTPException(403, "Can only certify your team members")

        if cert.status not in ['pending', 'overdue']:
            raise HTTPException(400, "Certification already completed")

        # Revoke any permissions specified
        permissions_revoked = data.get('permissions_to_revoke', [])
        for perm_key in permissions_revoked:
            # Revoke permission
            db.execute(text("""
                UPDATE user_permissions
                SET granted = FALSE, revoked_by_id = :revoked_by_id, revoked_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND permission_key = :perm_key
            """), {
                "user_id": cert.employee_id,
                "perm_key": perm_key,
                "revoked_by_id": current_user.id
            })

        # Update certification
        db.execute(text("""
            UPDATE access_certifications
            SET status = 'certified',
                certified_by_id = :certified_by_id,
                certified_at = CURRENT_TIMESTAMP,
                certification_notes = :notes,
                permissions_changed = :permissions_changed
            WHERE id = :cert_id
        """), {
            "cert_id": cert_id,
            "certified_by_id": current_user.id,
            "notes": data.get('notes', ''),
            "permissions_changed": str({
                "revoked": permissions_revoked,
                "revoked_by": current_user.id,
                "revoked_at": datetime.now(timezone.utc).isoformat()
            })
        })

        # Notify employee if permissions were revoked
        if permissions_revoked:
            db.execute(text("""
                INSERT INTO notifications (user_id, type, title, message, link, created_at)
                VALUES (:user_id, :type, :title, :message, :link, CURRENT_TIMESTAMP)
            """), {
                "user_id": cert.employee_id,
                "type": "permissions_revoked",
                "title": "Permissions Revoked During Certification",
                "message": f"The following permissions were revoked: {', '.join(permissions_revoked)}",
                "link": "/my-permissions"
            })

        db.commit()

        return {
            "success": True,
            "message": "Access certification completed",
            "permissions_revoked": len(permissions_revoked)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Certify access error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/certifications/{cert_id}/skip")
async def skip_certification(
    cert_id: int,
    data: dict,  # { "reason": "..." }
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Manager skips certification with reason (requires escalation approval)"""
    try:
        if not data.get('reason'):
            raise HTTPException(400, "Reason required to skip certification")

        # Get certification
        cert = db.execute(text("""
            SELECT * FROM access_certifications WHERE id = :cert_id
        """), {"cert_id": cert_id}).fetchone()

        if not cert:
            raise HTTPException(404, "Certification not found")

        # Update status
        db.execute(text("""
            UPDATE access_certifications
            SET status = 'skipped',
                certification_notes = :notes
            WHERE id = :cert_id
        """), {
            "cert_id": cert_id,
            "notes": f"SKIPPED: {data['reason']}"
        })

        # Create escalation notification to admin/compliance
        db.execute(text("""
            INSERT INTO notifications (user_id, type, title, message, created_at)
            SELECT u.id, 'certification_skipped',
                   'Certification Skipped - Requires Review',
                   :message,
                   CURRENT_TIMESTAMP
            FROM users u
            WHERE u.role IN ('management', 'admin')
        """), {
            "message": f"Manager {current_user.full_name} skipped certification {cert_id}. Reason: {data['reason']}"
        })

        db.commit()

        return {"success": True, "message": "Certification skipped, escalated to compliance"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Skip certification error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}/certifications/history")
async def get_certification_history(
    user_id: int,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Get all past certifications for an employee"""
    try:
        query = text("""
            SELECT ac.*, cb.full_name as certified_by_name
            FROM access_certifications ac
            LEFT JOIN users cb ON ac.certified_by_id = cb.id
            WHERE ac.employee_id = :user_id
            ORDER BY ac.due_date DESC
        """)

        certifications = db.execute(query, {"user_id": user_id}).fetchall()

        return {
            "certifications": [
                {
                    "period": cert.certification_period,
                    "due_date": cert.due_date.isoformat(),
                    "status": cert.status,
                    "certified_by": cert.certified_by_name if cert.certified_by_name else None,
                    "certified_at": cert.certified_at.isoformat() if cert.certified_at else None,
                    "permissions_changed": cert.permissions_changed
                }
                for cert in certifications
            ]
        }

    except Exception as e:
        logger.error(f"Get certification history error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# COMPLIANCE DASHBOARD - API ENDPOINTS
# ============================================================================

@router.get("/compliance/overview")
async def get_compliance_overview(
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Get high-level compliance metrics
    Admin/Management only
    """
    try:
        if current_user.role not in ['management', 'admin']:
            raise HTTPException(403, "Admin access required")

        # Total users
        total_users = db.execute(text("""
            SELECT COUNT(*) as count FROM users WHERE account_status = 'active'
        """)).fetchone().count

        # Certification metrics
        total_certs = db.execute(text("""
            SELECT COUNT(*) as count FROM access_certifications
        """)).fetchone().count

        certified = db.execute(text("""
            SELECT COUNT(*) as count FROM access_certifications
            WHERE status = 'certified'
        """)).fetchone().count

        overdue = db.execute(text("""
            SELECT COUNT(*) as count FROM access_certifications
            WHERE status = 'overdue'
        """)).fetchone().count

        # Permission metrics
        total_permissions_granted = db.execute(text("""
            SELECT COUNT(*) as count FROM user_permissions
            WHERE granted = TRUE
        """)).fetchone().count

        # High-risk permissions (define your own criteria)
        high_risk_perms = ['delete_clients', 'delete_loans', 'manage_users',
                          'access_audit_logs', 'emergency_revoke']
        high_risk_count = db.execute(text("""
            SELECT COUNT(*) as count FROM user_permissions
            WHERE granted = TRUE
            AND permission_key = ANY(:high_risk_perms)
        """), {"high_risk_perms": high_risk_perms}).fetchone().count

        # Recent access changes (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_changes = db.execute(text("""
            SELECT COUNT(*) as count FROM user_permissions
            WHERE granted_at >= :since
            OR revoked_at >= :since
        """), {"since": thirty_days_ago}).fetchone().count

        return {
            "users": {
                "total": total_users,
                "active": total_users
            },
            "certifications": {
                "total": total_certs,
                "certified": certified,
                "certified_percent": round((certified / total_certs * 100) if total_certs > 0 else 0, 1),
                "overdue": overdue,
                "pending": total_certs - certified - overdue
            },
            "permissions": {
                "total_granted": total_permissions_granted,
                "high_risk_granted": high_risk_count,
                "recent_changes_30d": recent_changes
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get compliance overview error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/compliance/certifications/by-department")
async def get_certifications_by_department(
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Get certification completion rates by department"""
    try:
        if current_user.role not in ['management', 'admin']:
            raise HTTPException(403, "Admin access required")

        # Get all departments
        departments_query = text("""
            SELECT DISTINCT department FROM users
            WHERE department IS NOT NULL
            AND account_status = 'active'
        """)

        departments = db.execute(departments_query).fetchall()

        results = []
        for dept_row in departments:
            dept = dept_row.department

            # Get employees in department
            dept_employees_query = text("""
                SELECT COUNT(*) as count FROM users
                WHERE department = :dept
                AND account_status = 'active'
            """)

            total_employees = db.execute(dept_employees_query, {"dept": dept}).fetchone().count

            # Get certifications for these employees
            total_certs_query = text("""
                SELECT COUNT(*) as count FROM access_certifications ac
                JOIN users u ON ac.employee_id = u.id
                WHERE u.department = :dept
                AND u.account_status = 'active'
            """)

            total = db.execute(total_certs_query, {"dept": dept}).fetchone().count

            certified_query = text("""
                SELECT COUNT(*) as count FROM access_certifications ac
                JOIN users u ON ac.employee_id = u.id
                WHERE u.department = :dept
                AND u.account_status = 'active'
                AND ac.status = 'certified'
            """)

            certified = db.execute(certified_query, {"dept": dept}).fetchone().count

            overdue_query = text("""
                SELECT COUNT(*) as count FROM access_certifications ac
                JOIN users u ON ac.employee_id = u.id
                WHERE u.department = :dept
                AND u.account_status = 'active'
                AND ac.status = 'overdue'
            """)

            overdue = db.execute(overdue_query, {"dept": dept}).fetchone().count

            results.append({
                "department": dept,
                "total_employees": total_employees,
                "total_certifications": total,
                "certified": certified,
                "certified_percent": round((certified / total * 100) if total > 0 else 0, 1),
                "overdue": overdue
            })

        return {"departments": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get certifications by department error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/compliance/export")
async def export_compliance_report(
    format: str = 'csv',
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """Generate downloadable compliance report"""
    try:
        if current_user.role not in ['management', 'admin']:
            raise HTTPException(403, "Admin access required")

        # Gather compliance data
        overview = await get_compliance_overview(current_user, db)
        dept_data = await get_certifications_by_department(current_user, db)

        if format == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)

            # Header
            writer.writerow(['Compliance Report', f'Generated: {datetime.now(timezone.utc).isoformat()}'])
            writer.writerow([])

            # Overview
            writer.writerow(['OVERVIEW'])
            writer.writerow(['Total Users', overview['users']['total']])
            writer.writerow(['Certifications Completed', f"{overview['certifications']['certified_percent']}%"])
            writer.writerow(['Overdue Certifications', overview['certifications']['overdue']])
            writer.writerow([])

            def _sanitize_csv(val):
                """Prevent CSV formula injection by prefixing dangerous characters."""
                s = str(val) if val is not None else ""
                if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
                    return "'" + s
                return s

            # Department breakdown
            writer.writerow(['DEPARTMENT BREAKDOWN'])
            writer.writerow(['Department', 'Employees', 'Certifications', 'Certified %', 'Overdue'])
            for dept in dept_data['departments']:
                writer.writerow([
                    _sanitize_csv(dept['department']),
                    dept['total_employees'],
                    dept['total_certifications'],
                    f"{dept['certified_percent']}%",
                    dept['overdue']
                ])

            # Return CSV
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=compliance_report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"}
            )

        raise HTTPException(400, "Only CSV format supported")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export compliance report error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# CERTIFICATION BACKGROUND JOBS - MANUAL TRIGGERS
# ============================================================================

@router.post("/admin/certification-jobs/create")
async def run_create_certifications(
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Manually trigger quarterly certification creation (admin only)
    Creates certifications for all active employees for the current quarter
    """
    try:
        if current_user.role not in ['management', 'admin']:
            raise HTTPException(403, "Admin access required")

        # Import and run the job
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))

        from jobs.certification_jobs import create_quarterly_certifications
        result = create_quarterly_certifications()

        if result.get('success'):
            return {
                "success": True,
                "message": f"Created {result.get('created', 0)} certifications for {result.get('quarter')}",
                "created": result.get('created', 0),
                "skipped": result.get('skipped', 0),
                "quarter": result.get('quarter')
            }
        else:
            raise HTTPException(500, f"Job failed: {result.get('error')}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Run create certifications error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/certification-jobs/reminders")
async def run_certification_reminders(
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Manually trigger certification reminder sending (admin only)
    Sends 30-day, 7-day, and overdue reminders
    """
    try:
        if current_user.role not in ['management', 'admin']:
            raise HTTPException(403, "Admin access required")

        # Import and run the job
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))

        from jobs.certification_jobs import send_certification_reminders
        result = send_certification_reminders()

        if result.get('success'):
            return {
                "success": True,
                "message": "Certification reminders sent successfully",
                "reminders_30d": result.get('reminders_30d', 0),
                "reminders_7d": result.get('reminders_7d', 0),
                "overdue": result.get('overdue', 0)
            }
        else:
            raise HTTPException(500, f"Job failed: {result.get('error')}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Run certification reminders error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Endpoint to verify admin user exists
@router.post("/admin/verify-admin-user")
async def verify_admin_user(db: Session = Depends(get_db_dep())):
    """
    Verify admin@perenniaai.com user exists and has admin role
    """
    try:
        # Import User model at runtime to avoid circular import
        import main
        User = main.User

        user = db.query(User).filter(User.email == "admin@perenniaai.com").first()
        if not user:
            raise HTTPException(status_code=404, detail="Admin user not found")

        return {
            "success": True,
            "message": f"Admin user verified with role '{user.role}'",
            "user": {
                "email": user.email,
                "name": user.full_name,
                "role": user.role
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify admin user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/run-compliance-migrations")
async def run_compliance_migrations(db: Session = Depends(get_db_dep())):
    """
    Run database migrations to add compliance system columns
    Adds: account_status, department, full_name to users table
    """
    try:
        results = []

        # Migration 1: Add account_status column
        try:
            db.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status VARCHAR(20) DEFAULT 'active'
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_account_status ON users(account_status)
            """))
            db.execute(text("""
                UPDATE users SET account_status = 'active' WHERE account_status IS NULL
            """))
            results.append("Added account_status column")
        except Exception as e:
            results.append(f"account_status: {str(e)}")

        # Migration 2: Add department column
        try:
            db.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR(100)
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_department ON users(department)
            """))
            db.execute(text("""
                UPDATE users
                SET department = CASE
                    WHEN role IN ('sales', 'loan_officer') THEN 'Sales'
                    WHEN role = 'operations' THEN 'Operations'
                    WHEN role IN ('manager', 'management') THEN 'Management'
                    WHEN role = 'admin' THEN 'Administration'
                    ELSE 'General'
                END
                WHERE department IS NULL
            """))
            results.append("Added department column")
        except Exception as e:
            results.append(f"department: {str(e)}")

        # Migration 3: Add full_name column
        try:
            db.execute(text("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)
            """))
            # Try to populate from email if no other name field exists
            db.execute(text("""
                UPDATE users SET full_name = COALESCE(full_name, email) WHERE full_name IS NULL
            """))
            results.append("Added full_name column")
        except Exception as e:
            db.rollback()  # Rollback this specific failure
            results.append(f"full_name: {str(e)}")

        # Migration 4: Create access_certifications table
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS access_certifications (
                    id SERIAL PRIMARY KEY,
                    employee_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    certification_period VARCHAR(20) NOT NULL,
                    due_date DATE NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',

                    certified_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    certified_at TIMESTAMP,
                    certification_notes TEXT,

                    permissions_snapshot JSONB,
                    permissions_changed JSONB,

                    reminder_sent_30d BOOLEAN DEFAULT FALSE,
                    reminder_sent_7d BOOLEAN DEFAULT FALSE,
                    reminder_sent_overdue BOOLEAN DEFAULT FALSE,

                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_certifications_employee ON access_certifications(employee_id)
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_certifications_due_date ON access_certifications(due_date)
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_certifications_status ON access_certifications(status)
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_certifications_period ON access_certifications(certification_period)
            """))
            results.append("Created access_certifications table")
        except Exception as e:
            db.rollback()  # Rollback this specific failure
            results.append(f"access_certifications: {str(e)}")

        db.commit()

        return {
            "success": True,
            "message": "Compliance migrations completed",
            "results": results
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Migration failed")


# ============================================================================
# TAB 6: ACCESS & AUDIT - API ENDPOINTS
# ============================================================================

@router.get("/users/{user_id}/audit-log")
async def get_user_audit_log(
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    change_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Get audit log for a user - all changes to their profile and permissions
    """
    try:
        # Import models at runtime to avoid circular import
        import main
        AuditLog = main.AuditLog
        User = main.User

        # Check permission
        if not has_permission(current_user.id, 'team.view_all', db) and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Build query
        query = db.query(AuditLog).filter(AuditLog.user_id == user_id)

        # Apply filters
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            query = query.filter(AuditLog.timestamp >= start_dt)

        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            query = query.filter(AuditLog.timestamp <= end_dt)

        if change_type:
            query = query.filter(AuditLog.change_type == change_type)

        if search:
            query = query.filter(
                or_(
                    AuditLog.entity_type.contains(search),
                    AuditLog.reason.contains(search)
                )
            )

        # Get total count
        total = query.count()

        # Get paginated results
        changes = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()

        # Format response
        change_list = []
        for change in changes:
            changed_by = db.query(User).filter(User.id == change.changed_by_id).first()
            change_list.append({
                "id": change.id,
                "timestamp": change.timestamp.isoformat(),
                "changed_by": {
                    "id": changed_by.id,
                    "name": changed_by.full_name,
                    "role": changed_by.role
                } if changed_by else None,
                "change_type": change.change_type,
                "entity_type": change.entity_type,
                "entity_id": change.entity_id,
                "before_state": change.before_state,
                "after_state": change.after_state,
                "ip_address": change.ip_address,
                "session_id": change.session_id,
                "reason": change.reason
            })

        return {
            "total": total,
            "changes": change_list
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get audit log error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}/impersonation-history")
async def get_impersonation_history(
    user_id: int,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Get impersonation history for a user
    """
    try:
        # Import models at runtime to avoid circular import
        import main
        ImpersonationSession = main.ImpersonationSession
        AuditLog = main.AuditLog
        User = main.User

        # Check permission
        if not has_permission(current_user.id, 'team.view_all', db) and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get impersonation sessions
        sessions = db.query(ImpersonationSession).filter(
            ImpersonationSession.impersonated_user_id == user_id
        ).order_by(ImpersonationSession.started_at.desc()).all()

        # Format response
        session_list = []
        reason_counts = {}
        manager_counts = {}
        total_duration = 0

        for session in sessions:
            manager = db.query(User).filter(User.id == session.manager_id).first()

            # Calculate duration
            if session.ended_at:
                duration = int((session.ended_at - session.started_at).total_seconds() / 60)
            elif session.is_active:
                duration = int((datetime.now(timezone.utc) - session.started_at).total_seconds() / 60)
            else:
                duration = session.duration_minutes

            total_duration += duration

            # Count reasons and managers
            reason_counts[session.reason] = reason_counts.get(session.reason, 0) + 1
            if manager:
                manager_counts[manager.full_name] = manager_counts.get(manager.full_name, 0) + 1

            # Get actions taken during this impersonation session
            session_end = session.ended_at if session.ended_at else datetime.now(timezone.utc)
            actions_query = db.query(AuditLog).filter(
                AuditLog.changed_by_id == session.manager_id,
                AuditLog.user_id == session.impersonated_user_id,
                AuditLog.timestamp >= session.started_at,
                AuditLog.timestamp <= session_end
            ).order_by(AuditLog.timestamp.asc()).all()

            actions = [
                {
                    "id": action.id,
                    "action_type": action.change_type,
                    "entity_type": action.entity_type,
                    "entity_id": action.entity_id,
                    "timestamp": action.timestamp.isoformat(),
                    "reason": action.reason
                }
                for action in actions_query
            ]

            session_list.append({
                "id": session.id,
                "started_at": session.started_at.isoformat(),
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "duration_minutes": duration,
                "manager": {
                    "id": manager.id,
                    "name": manager.full_name
                } if manager else None,
                "mode": session.mode,
                "reason": session.reason,
                "reason_notes": session.reason if session.reason else None,
                "employee_notified": session.notify_employee,
                "actions": actions
            })

        # Calculate summary
        most_common_reason = max(reason_counts.items(), key=lambda x: x[1])[0] if reason_counts else None
        most_frequent_manager = max(manager_counts.items(), key=lambda x: x[1])[0] if manager_counts else None
        avg_duration = int(total_duration / len(sessions)) if sessions else 0

        return {
            "total_sessions": len(sessions),
            "sessions": session_list,
            "summary": {
                "total_sessions": len(sessions),
                "avg_duration_minutes": avg_duration,
                "most_common_reason": most_common_reason,
                "most_frequent_manager": most_frequent_manager
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get impersonation history error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}/active-sessions")
async def get_active_sessions(
    user_id: int,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Get active sessions for a user
    """
    try:
        # Import models at runtime to avoid circular import
        import main
        UserSession = main.UserSession

        # Check permission
        if not has_permission(current_user.id, 'team.view_all', db) and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get active sessions
        sessions = db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.is_active == True
        ).order_by(UserSession.logged_in_at.desc()).all()

        # Format response
        session_list = []
        for session in sessions:
            session_list.append({
                "session_id": session.session_id,
                "logged_in_at": session.logged_in_at.isoformat(),
                "ip_address": session.ip_address,
                "location": session.location,
                "device": session.device,
                "user_agent": session.user_agent,
                "last_activity": session.last_activity.isoformat()
            })

        return {
            "sessions": session_list
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get active sessions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{user_id}/sessions/{session_id}")
async def revoke_user_session(
    user_id: int,
    session_id: str,
    body: RevokeSessionRequest,
    current_user = Depends(get_current_user_dep()),
    db: Session = Depends(get_db_dep())
):
    """
    Revoke a specific user session
    """
    try:
        # Import models at runtime to avoid circular import
        import main
        UserSession = main.UserSession

        # Check permission
        if not has_permission(current_user.id, 'team.manage_permissions', db):
            raise HTTPException(status_code=403, detail="Access denied")

        # Get session
        session = db.query(UserSession).filter(
            UserSession.session_id == session_id,
            UserSession.user_id == user_id
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Revoke session
        session.is_active = False
        session.revoked_at = datetime.now(timezone.utc)
        session.revoked_by_id = current_user.id
        session.revoke_reason = body.reason

        db.commit()

        return {
            "success": True,
            "message": "Session revoked successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Revoke session error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
