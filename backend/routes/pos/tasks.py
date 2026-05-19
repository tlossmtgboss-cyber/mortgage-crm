"""Borrower-facing task routes for the POS portal.

Tasks are pushed from the CRM (by the LO or automation) and appear in the
borrower's portal so they know what to complete next (upload docs, sign
disclosures, schedule appraisal, etc.).

Auth: PURL token — borrower must own the application.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from database.models.pos import POSApplication
from database.models.task import Task
from middleware.purl_auth import check_purl_rate_limit

from ._helpers import (
    resolve_application_for_borrower,
    resolve_application_for_borrower_write,
)
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger("pos.tasks.routes")

router = APIRouter(
    prefix="/api/v1/pos/applications",
    tags=["POS - Tasks"],
    dependencies=[Depends(check_purl_rate_limit)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BorrowerTaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    due_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    category: str

    class Config:
        from_attributes = True


class BorrowerTaskCounts(BaseModel):
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    total: int = 0


class BorrowerTaskListResponse(BaseModel):
    application_id: str
    tasks: list[BorrowerTaskResponse]
    counts: BorrowerTaskCounts


# Internal task types that should never surface to borrowers.
_INTERNAL_TASK_TYPES = frozenset({
    "sf_disposition",
    "email_classification",
    "sla_milestone",
    "internal",
    "system",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task_to_response(task: Task) -> BorrowerTaskResponse:
    return BorrowerTaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status or "pending",
        priority=task.priority or "medium",
        due_date=task.due_date,
        created_at=task.created_at,
        completed_at=task.completed_at,
        category=task.related_type or "general",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{application_id}/tasks",
    response_model=BorrowerTaskListResponse,
    summary="List borrower-facing tasks for this application",
)
def list_tasks(
    include_completed: bool = Query(False, description="Include completed tasks"),
    application: POSApplication = Depends(resolve_application_for_borrower),
    db: AsyncSession = Depends(get_async_db),
) -> BorrowerTaskListResponse:
    """Return tasks linked to the application's loan.

    By default only returns non-completed tasks. Pass
    ``?include_completed=true`` to include everything.
    """
    app_id = str(application.id)

    if application.loan_id is None:
        return BorrowerTaskListResponse(
            application_id=app_id,
            tasks=[],
            counts=BorrowerTaskCounts(),
        )

    all_tasks = (
        db.query(Task)
        .filter(
            Task.loan_id == application.loan_id,
            Task.organization_id == application.organization_id,
        )
        .order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
        .all()
    )

    all_tasks = [t for t in all_tasks if (t.related_type or "") not in _INTERNAL_TASK_TYPES]

    counts = BorrowerTaskCounts(total=len(all_tasks))
    for t in all_tasks:
        s = t.status or "pending"
        if s == "pending":
            counts.pending += 1
        elif s == "in_progress":
            counts.in_progress += 1
        elif s == "completed":
            counts.completed += 1

    visible = all_tasks if include_completed else [t for t in all_tasks if t.status != "completed"]

    return BorrowerTaskListResponse(
        application_id=app_id,
        tasks=[_task_to_response(t) for t in visible],
        counts=counts,
    )


@router.patch(
    "/{application_id}/tasks/{task_id}",
    response_model=BorrowerTaskResponse,
    summary="Mark a task as completed",
)
def complete_task(
    task_id: int,
    application: POSApplication = Depends(resolve_application_for_borrower_write),
    db: AsyncSession = Depends(get_async_db),
) -> BorrowerTaskResponse:
    """Allow the borrower to mark a task as completed.

    The task must belong to the same loan as the application. Borrowers
    cannot modify any field other than status (set to ``completed``).
    """
    if application.loan_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    task = (
        db.query(Task)
        .filter(
            Task.id == task_id,
            Task.loan_id == application.loan_id,
            Task.organization_id == application.organization_id,
        )
        .first()
    )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    if task.status == "completed":
        # Idempotent — just return the existing state.
        return _task_to_response(task)

    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)

    logger.info(
        "Borrower completed task",
        extra={
            "task_id": task.id,
            "loan_id": application.loan_id,
            "application_id": str(application.id),
        },
    )

    return _task_to_response(task)
