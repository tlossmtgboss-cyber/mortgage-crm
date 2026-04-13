"""
Task Snooze Routes

PATCH /api/v1/tasks/{task_id}/snooze — Snooze a task (push due_date forward)

This endpoint is called by push notification quick actions
(see frontend/src/services/notificationActions.js, TASK_DUE category).
Delegates to the shared _snooze_task() helper in mobile_tasks_routes.
"""

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import require_auth, current_user_dep
from routes.mobile_tasks_routes import SnoozeRequest, _snooze_task

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["Tasks"],
    dependencies=[Depends(require_auth)],
)


@router.patch("/{task_id}/snooze")
async def snooze_task(
    task_id: int,
    body: SnoozeRequest = Body(default=SnoozeRequest()),
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Snooze a task — PATCH /api/v1/tasks/{task_id}/snooze

    Called by push notification quick actions when the user taps "Snooze 1h".
    Accepts ``snooze_until`` (ISO datetime) or ``duration_minutes``.
    Defaults to +60 minutes when neither is provided.

    Returns ``{success: true, task_id, new_due_date}``.
    """
    return await _snooze_task(task_id, body, current_user, db)
