"""
Client file routes — aggregate root CRUD and sub-resource projections.
Wired under /api/v1 via inline_legacy_routes.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import get_db


def get_current_user_dep():
    from auth.dependencies import get_current_user
    return get_current_user


router = APIRouter(tags=["Client File"])


# ─── Response schemas ────────────────────────────────────────────────────

class AddressSchema(BaseModel):
    street: Optional[str] = None
    unit: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None

    class Config:
        from_attributes = True


class ClientFileResponse(BaseModel):
    id: str
    org_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    preferred_name: Optional[str] = None
    primary_email: Optional[str] = None
    secondary_email: Optional[str] = None
    primary_phone: Optional[str] = None
    secondary_phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    ssn_last_4: Optional[str] = None
    mailing_address: Optional[AddressSchema] = None
    property_address: Optional[AddressSchema] = None
    language_pref: str = "en"
    preferred_channel: Optional[str] = None
    preferred_contact_window: Optional[str] = None
    sticky_note: Optional[str] = None
    lifecycle_stage: str
    source: Optional[str] = None
    assigned_loan_officer_id: Optional[str] = None
    assigned_loan_officer_name: Optional[str] = None
    assigned_loan_assistant_id: Optional[str] = None
    assigned_processor_id: Optional[str] = None
    last_contact_at: Optional[str] = None
    last_inbound_at: Optional[str] = None
    last_outbound_at: Optional[str] = None
    unread_thread_count: int = 0
    open_doc_request_count: int = 0
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict = Field(default_factory=dict)
    active_loan_id: Optional[str] = None
    active_loan_program: Optional[str] = None
    active_loan_purpose: Optional[str] = None
    active_loan_amount: Optional[float] = None
    active_loan_fico: Optional[int] = None
    active_loan_lock_expires_at: Optional[str] = None
    active_loan_projected_close_date: Optional[str] = None
    active_loan_current_milestone: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ─── Helpers ─────────────────────────────────────────────────────────────

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _to_response(cf: Any, lo_name: Optional[str] = None) -> dict:
    return ClientFileResponse(
        id=str(cf.id),
        org_id=str(cf.organization_id),
        first_name=cf.first_name,
        last_name=cf.last_name,
        primary_email=cf.primary_email,
        primary_phone=cf.primary_phone,
        property_address=cf.property_address,
        sticky_note=cf.sticky_note,
        lifecycle_stage=cf.lifecycle_stage,
        source=cf.source,
        preferred_channel=cf.preferred_channel,
        assigned_loan_officer_id=str(cf.assigned_loan_officer_id) if cf.assigned_loan_officer_id else None,
        assigned_loan_officer_name=lo_name,
        assigned_loan_assistant_id=str(cf.assigned_loan_assistant_id) if cf.assigned_loan_assistant_id else None,
        assigned_processor_id=str(cf.assigned_processor_id) if cf.assigned_processor_id else None,
        last_contact_at=_iso(cf.last_contact_at),
        tags=cf.tags or [],
        active_loan_program=cf.active_loan_program,
        active_loan_purpose=cf.active_loan_purpose,
        active_loan_amount=float(cf.active_loan_amount) if cf.active_loan_amount else None,
        active_loan_fico=cf.active_loan_fico,
        active_loan_lock_expires_at=_iso(cf.active_loan_lock_expires_at),
        active_loan_projected_close_date=_iso(cf.active_loan_projected_close_date),
        created_at=cf.created_at.isoformat(),
        updated_at=cf.updated_at.isoformat(),
    ).model_dump()


def _get_cf(db: Session, cf_id: uuid.UUID, org_id: int):
    from database.models.client_file import ClientFile
    cf = db.execute(
        select(ClientFile).where(
            ClientFile.id == cf_id,
            ClientFile.organization_id == org_id,
        )
    ).scalar_one_or_none()
    if cf is None:
        raise HTTPException(404, "client file not found")
    return cf


def _lo_name(db: Session, user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None
    from database.models.core import User
    u = db.get(User, user_id)
    return f"{u.first_name} {u.last_name}".strip() if u else None


# ─── Core CRUD ───────────────────────────────────────────────────────────

@router.get("/clients/{client_file_id}")
def get_client_file(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    return _to_response(cf, _lo_name(db, cf.assigned_loan_officer_id))


class ClientFilePatch(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    primary_email: Optional[str] = None
    primary_phone: Optional[str] = None
    preferred_channel: Optional[str] = None
    source: Optional[str] = None
    property_address: Optional[dict] = None
    assigned_loan_officer_id: Optional[int] = None
    assigned_loan_assistant_id: Optional[int] = None
    assigned_processor_id: Optional[int] = None


@router.patch("/clients/{client_file_id}")
def patch_client_file(
    client_file_id: uuid.UUID,
    body: ClientFilePatch,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(cf, field, value)
    db.commit()
    db.refresh(cf)
    return _to_response(cf, _lo_name(db, cf.assigned_loan_officer_id))


class LifecycleBody(BaseModel):
    lifecycle_stage: str


@router.post("/clients/{client_file_id}/lifecycle")
def set_lifecycle_stage(
    client_file_id: uuid.UUID,
    body: LifecycleBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    cf.lifecycle_stage = body.lifecycle_stage
    db.commit()
    db.refresh(cf)
    return _to_response(cf, _lo_name(db, cf.assigned_loan_officer_id))


class StickyNoteBody(BaseModel):
    sticky_note: Optional[str] = None


@router.put("/clients/{client_file_id}/sticky-note")
def set_sticky_note(
    client_file_id: uuid.UUID,
    body: StickyNoteBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    cf.sticky_note = body.sticky_note
    db.commit()
    db.refresh(cf)
    return _to_response(cf, _lo_name(db, cf.assigned_loan_officer_id))


class TagBody(BaseModel):
    tag: str


@router.post("/clients/{client_file_id}/tags")
def add_tag(
    client_file_id: uuid.UUID,
    body: TagBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    tags = list(cf.tags or [])
    if body.tag not in tags:
        tags.append(body.tag)
        cf.tags = tags
        db.commit()
        db.refresh(cf)
    return _to_response(cf, _lo_name(db, cf.assigned_loan_officer_id))


@router.delete("/clients/{client_file_id}/tags/{tag}")
def remove_tag(
    client_file_id: uuid.UUID,
    tag: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    tags = list(cf.tags or [])
    if tag in tags:
        tags.remove(tag)
        cf.tags = tags
        db.commit()
        db.refresh(cf)
    return _to_response(cf, _lo_name(db, cf.assigned_loan_officer_id))


# ─── Tasks (projected from existing `tasks` table via lead_id) ───────────

class TaskResponse(BaseModel):
    id: str
    client_file_id: str
    title: str
    body: Optional[str] = None
    status: str
    priority: str
    due_at: Optional[str] = None
    completed_at: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    assigned_to_user_name: Optional[str] = None
    created_by_user_id: Optional[str] = None


def _task_to_response(task: Any, cf_id: uuid.UUID) -> dict:
    return TaskResponse(
        id=str(task.id),
        client_file_id=str(cf_id),
        title=task.title,
        body=task.description,
        status="done" if task.status == "completed" else task.status or "open",
        priority=task.priority or "normal",
        due_at=_iso(task.due_date),
        completed_at=_iso(task.completed_at),
        assigned_to_user_id=str(task.owner_id) if task.owner_id else None,
        created_by_user_id=None,
    ).model_dump()


@router.get("/clients/{client_file_id}/tasks")
def list_tasks(
    client_file_id: uuid.UUID,
    include_done: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    if not cf.lead_id:
        return []
    from database.models.task import Task
    q = select(Task).where(
        Task.lead_id == cf.lead_id,
        Task.organization_id == current_user.organization_id,
    )
    if not include_done:
        q = q.where(Task.status != "completed")
    q = q.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc())
    tasks = db.execute(q).scalars().all()
    return [_task_to_response(t, client_file_id) for t in tasks]


class CreateTaskBody(BaseModel):
    title: str
    body: Optional[str] = None
    priority: str = "normal"
    due_at: Optional[str] = None
    assigned_to_user_id: Optional[int] = None


@router.post("/clients/{client_file_id}/tasks")
def create_task(
    client_file_id: uuid.UUID,
    body: CreateTaskBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    from database.models.task import Task
    due_date = None
    if body.due_at:
        due_date = datetime.fromisoformat(body.due_at)
    task = Task(
        organization_id=current_user.organization_id,
        title=body.title,
        description=body.body,
        priority=body.priority,
        due_date=due_date,
        owner_id=body.assigned_to_user_id or current_user.id,
        lead_id=cf.lead_id,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_to_response(task, client_file_id)


@router.post("/clients/{client_file_id}/tasks/{task_id}/complete")
def complete_task(
    client_file_id: uuid.UUID,
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    from database.models.task import Task
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == current_user.organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, "task not found")
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return _task_to_response(task, client_file_id)


@router.post("/clients/{client_file_id}/tasks/{task_id}/reopen")
def reopen_task(
    client_file_id: uuid.UUID,
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    from database.models.task import Task
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == current_user.organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, "task not found")
    task.status = "pending"
    task.completed_at = None
    db.commit()
    db.refresh(task)
    return _task_to_response(task, client_file_id)


# ─── Cadence sequences (projected from followup executions via lead_id) ──

class CadenceSequenceResponse(BaseModel):
    id: str
    client_file_id: str
    loan_officer_id: str
    goal: str
    cohort: str
    status: str
    selected_arm: str
    attempts_made: int
    max_attempts: int
    next_check_at: Optional[str] = None
    expires_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    last_skill_used: Optional[str] = None
    stop_reason: Optional[str] = None


@router.get("/clients/{client_file_id}/cadence-sequences")
def list_cadence_sequences(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    if not cf.lead_id:
        return []
    from database.models.lead_loan import Loan
    loan_ids = [
        lid for (lid,) in db.execute(
            select(Loan.id).where(
                Loan.lead_id == cf.lead_id,
                Loan.organization_id == current_user.organization_id,
            )
        ).all()
    ]
    if not loan_ids:
        return []
    from database.models.followup_cadence import FollowupExecution
    execs = db.execute(
        select(FollowupExecution).where(
            FollowupExecution.loan_id.in_(loan_ids),
            FollowupExecution.organization_id == current_user.organization_id,
        ).order_by(FollowupExecution.created_at.desc())
    ).scalars().all()
    results = []
    for ex in execs:
        results.append(CadenceSequenceResponse(
            id=str(ex.id),
            client_file_id=str(client_file_id),
            loan_officer_id="",
            goal=ex.pause_reason or "document_followup",
            cohort=ex.ab_variant or "default",
            status=ex.status.lower() if ex.status else "active",
            selected_arm="standard",
            attempts_made=ex.attempts_made or 0,
            max_attempts=5,
            next_check_at=_iso(ex.next_send_at),
            expires_at=None,
            started_at=_iso(ex.created_at),
            ended_at=_iso(ex.completed_at or ex.cancelled_at),
            last_skill_used=None,
            stop_reason=ex.cancel_reason,
        ).model_dump())
    return results


# ─── Stubs — typed empty responses for unbuilt features ──────────────────


@router.get("/clients/{client_file_id}/timeline")
def list_timeline(
    client_file_id: uuid.UUID,
    category: str = Query("all"),
    limit: int = Query(100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    return []


@router.get("/clients/{client_file_id}/insight")
def get_insight(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    return None


@router.post("/clients/{client_file_id}/insight/recompute", status_code=501)
def recompute_insight(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    return {"detail": "insight recompute not yet implemented"}


@router.get("/clients/{client_file_id}/document-sets")
def list_document_sets(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    return []


@router.get("/clients/{client_file_id}/relationships")
def list_relationships(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    return []


@router.get("/clients/{client_file_id}/action-plan-runs")
def list_action_plan_runs(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    return []


@router.post("/clients/{client_file_id}/notes", status_code=501)
def add_note(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    return {"detail": "notes not yet implemented"}


@router.post("/clients/{client_file_id}/messages", status_code=501)
def send_message(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    return {"detail": "messages not yet implemented"}


@router.post("/clients/{client_file_id}/timeline/{event_id}/star", status_code=501)
def star_event(
    client_file_id: uuid.UUID,
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    return {"detail": "star not yet implemented"}


@router.delete("/clients/{client_file_id}/timeline/{event_id}/star", status_code=501)
def unstar_event(
    client_file_id: uuid.UUID,
    event_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    return {"detail": "unstar not yet implemented"}
