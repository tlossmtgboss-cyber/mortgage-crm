"""
SSE Notification Routes — ISO-017
Server-Sent Events endpoint with tenant-scoped notifications.

Each SSE connection is authenticated via JWT and scoped to the user's organization.
Notifications are filtered by organization_id to prevent cross-tenant leakage.
"""
from fastapi import Depends, Request, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def register_sse_notification_routes(app, get_db, get_current_user, **kwargs):
    """Register SSE notification endpoints (ISO-017)."""

    @app.get("/api/v1/notifications/stream", tags=["Notifications"])
    async def sse_notification_stream(
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Server-Sent Events stream for real-time tenant-scoped notifications.

        ISO-017: All notifications are filtered by the authenticated user's
        organization_id. Cross-tenant notification leakage is impossible because:
        1. JWT auth extracts user → organization_id
        2. Query filters by organization_id
        3. RLS on notifications table enforces tenant isolation at DB level
        """
        org_id = getattr(current_user, 'organization_id', None)
        user_id = current_user.id

        async def event_generator():
            """Generate SSE events scoped to tenant."""
            last_check = datetime.now(timezone.utc)
            yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id, 'org_id': org_id})}\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    # Query notifications scoped to org_id + user_id
                    rows = db.execute(text("""
                        SELECT id, title, message, notification_type, priority,
                               entity_type, entity_id, created_at
                        FROM notifications
                        WHERE organization_id = :org_id
                          AND (user_id = :user_id OR user_id IS NULL)
                          AND created_at > :since
                          AND is_read = FALSE
                        ORDER BY created_at ASC
                        LIMIT 50
                    """), {
                        "org_id": org_id,
                        "user_id": user_id,
                        "since": last_check,
                    }).fetchall()

                    for row in rows:
                        event_data = {
                            "type": "notification",
                            "id": row.id if hasattr(row, 'id') else row[0],
                            "title": row.title if hasattr(row, 'title') else row[1],
                            "message": row.message if hasattr(row, 'message') else row[2],
                            "notification_type": row[3] if not hasattr(row, 'notification_type') else row.notification_type,
                            "priority": row[4] if not hasattr(row, 'priority') else row.priority,
                            "timestamp": str(row[7] if not hasattr(row, 'created_at') else row.created_at),
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"

                    last_check = datetime.now(timezone.utc)
                except Exception as e:
                    logger.warning(f"SSE notification poll error: {e}")
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                await asyncio.sleep(3)  # Poll every 3 seconds

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    @app.post("/api/v1/notifications/broadcast", tags=["Notifications"])
    async def broadcast_tenant_notification(
        request: Request,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Broadcast a notification to all users in the current tenant.
        Admin-only. Notification is scoped to organization_id.
        """
        from utils.auth import require_admin
        require_admin(current_user)

        body = await request.json()
        org_id = getattr(current_user, 'organization_id', None)

        try:
            db.execute(text("""
                INSERT INTO notifications
                    (title, message, notification_type, priority, organization_id, created_at)
                VALUES
                    (:title, :message, :type, :priority, :org_id, NOW())
            """), {
                "title": body.get("title", "Notification"),
                "message": body.get("message", ""),
                "type": body.get("notification_type", "info"),
                "priority": body.get("priority", "normal"),
                "org_id": org_id,
            })
            db.commit()
            return {"status": "broadcast_sent", "organization_id": org_id}
        except Exception as e:
            db.rollback()
            logger.error(f"Broadcast failed: {e}")
            raise HTTPException(status_code=500, detail="Broadcast failed")

    logger.info("SSE notification routes loaded (ISO-017)")
