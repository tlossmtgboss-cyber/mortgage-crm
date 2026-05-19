"""
Mobile Notification Routes

GET   /api/v1/mobile/notifications            — List notifications for the current user
PATCH /api/v1/mobile/notifications/{id}/read  — Mark a single notification as read
POST  /api/v1/mobile/notifications/read-all   — Mark all notifications as read

Queries the `notifications` table (Notification model in database/models/security.py).
Used by VisionProSupport.swift (fetchNotifications) and the iOS notification center.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import require_auth, current_user_dep
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/mobile",
    tags=["Mobile Notifications"],
    dependencies=[Depends(require_auth)],
)


# =============================================================================
# GET /api/v1/mobile/notifications
# =============================================================================

@router.get("/notifications")
async def get_mobile_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Return notifications for the authenticated user.

    Response shape matches what VisionProSupport.swift expects:
    { notifications: [NotificationItem], unread_count: N, total: N }
    """
    from database.models.security import Notification

    base_filter = [Notification.user_id == current_user.id]

    org_id = getattr(current_user, "organization_id", None)
    if org_id:
        base_filter.append(Notification.organization_id == org_id)

    if unread_only:
        base_filter.append(Notification.is_read == False)  # noqa: E712

    # Total count (respecting unread_only filter)
    total = db.query(func.count(Notification.id)).filter(*base_filter).scalar() or 0

    # Unread count (always across all notifications, not filtered by unread_only)
    unread_filter = [
        Notification.user_id == current_user.id,
        Notification.is_read == False,  # noqa: E712
    ]
    if org_id:
        unread_filter.append(Notification.organization_id == org_id)
    unread_count = db.query(func.count(Notification.id)).filter(*unread_filter).scalar() or 0

    # Fetch page
    rows = (
        db.query(Notification)
        .filter(*base_filter)
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    notifications = []
    for n in rows:
        notifications.append({
            "id": str(n.id),
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "read": n.is_read,
            "is_read": n.is_read,  # iOS client expects snake_case is_read
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "data": {
                "link": n.link,
            } if n.link else None,
        })

    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "total": total,
    }


# =============================================================================
# PATCH /api/v1/mobile/notifications/{id}/read
# =============================================================================

@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Mark a single notification as read."""
    from database.models.security import Notification

    notif = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    if notif.is_read:
        return {"success": True, "id": notification_id, "already_read": True}

    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to mark notification %s as read: %s", notification_id, exc)
        raise HTTPException(status_code=500, detail="Failed to update notification")

    return {"success": True, "id": notification_id, "already_read": False}


# =============================================================================
# POST /api/v1/mobile/notifications/read-all
# =============================================================================

@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    current_user=Depends(current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Mark all unread notifications as read for the current user."""
    from database.models.security import Notification

    now = datetime.now(timezone.utc)

    filters = [
        Notification.user_id == current_user.id,
        Notification.is_read == False,  # noqa: E712
    ]
    org_id = getattr(current_user, "organization_id", None)
    if org_id:
        filters.append(Notification.organization_id == org_id)

    try:
        updated = (
            db.query(Notification)
            .filter(*filters)
            .update(
                {Notification.is_read: True, Notification.read_at: now},
                synchronize_session="fetch",
            )
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to mark all notifications as read: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update notifications")

    logger.info(
        "Marked %d notifications as read for user %s",
        updated, current_user.id,
    )

    return {"success": True, "updated_count": updated}
