"""
Client file routes — aggregate root CRUD and sub-resource projections.
Wired under /api/v1 via inline_legacy_routes.py.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)


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
    active_loan_stage: Optional[str] = None
    active_loan_type: Optional[str] = None
    active_loan_term: Optional[int] = None
    active_loan_purchase_price: Optional[float] = None
    active_loan_interest_rate: Optional[float] = None
    lead_id: Optional[int] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


# ─── Helpers ─────────────────────────────────────────────────────────────

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _to_response(cf: Any, lo_name: Optional[str] = None, loan: Any = None) -> dict:
    def _loan_attr(attr: str, convert=None):
        if not loan:
            return None
        val = getattr(loan, attr, None)
        if val is None:
            return None
        return convert(val) if convert else val

    return ClientFileResponse(
        id=str(cf.id),
        org_id=str(cf.organization_id),
        first_name=cf.first_name,
        last_name=cf.last_name,
        primary_email=cf.primary_email,
        primary_phone=cf.primary_phone,
        property_address=cf.property_address if isinstance(cf.property_address, dict) else None,
        sticky_note=cf.sticky_note,
        lifecycle_stage=cf.lifecycle_stage or "new_lead",
        source=cf.source,
        preferred_channel=cf.preferred_channel,
        assigned_loan_officer_id=str(cf.assigned_loan_officer_id) if cf.assigned_loan_officer_id else None,
        assigned_loan_officer_name=lo_name,
        assigned_loan_assistant_id=str(cf.assigned_loan_assistant_id) if cf.assigned_loan_assistant_id else None,
        assigned_processor_id=str(cf.assigned_processor_id) if cf.assigned_processor_id else None,
        last_contact_at=_iso(cf.last_contact_at),
        tags=cf.tags or [],
        active_loan_id=str(loan.id) if loan else None,
        active_loan_program=getattr(cf, 'active_loan_program', None) or _loan_attr('program'),
        active_loan_purpose=getattr(cf, 'active_loan_purpose', None) or _loan_attr('loan_type'),
        active_loan_amount=_loan_attr('amount', float) or (float(cf.active_loan_amount) if getattr(cf, 'active_loan_amount', None) else None),
        active_loan_fico=getattr(cf, 'active_loan_fico', None),
        active_loan_lock_expires_at=_iso(getattr(cf, 'active_loan_lock_expires_at', None)),
        active_loan_projected_close_date=_iso(_loan_attr('closing_date')) or _iso(getattr(cf, 'active_loan_projected_close_date', None)),
        active_loan_stage=_loan_attr('stage'),
        active_loan_type=_loan_attr('loan_type'),
        active_loan_term=_loan_attr('term'),
        active_loan_purchase_price=_loan_attr('purchase_price', float),
        active_loan_interest_rate=_loan_attr('rate', float),
        lead_id=cf.lead_id,
        created_at=cf.created_at.isoformat() if cf.created_at else datetime.now(timezone.utc).isoformat(),
        updated_at=cf.updated_at.isoformat() if cf.updated_at else datetime.now(timezone.utc).isoformat(),
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
        # Orphan repair: backfill may have set wrong org_id
        from sqlalchemy import text as _text
        orphan = db.execute(
            select(ClientFile).where(ClientFile.id == cf_id)
        ).scalar_one_or_none()
        if orphan is not None:
            db.execute(
                _text("UPDATE client_files SET organization_id = :org WHERE id = :id"),
                {"org": org_id, "id": cf_id},
            )
            db.commit()
            db.refresh(orphan)
            return orphan
        raise HTTPException(404, "client file not found")
    return cf


def _active_loan(db: Session, cf: Any, org_id: int):
    loan_ids = _get_loan_ids_for_cf(db, cf, org_id)
    if not loan_ids:
        return None
    from database.models.lead_loan import Loan
    return db.execute(
        select(Loan).where(Loan.id == loan_ids[0])
    ).scalar_one_or_none()


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
    # Backfill name from linked lead if missing
    if not cf.first_name and not cf.last_name and cf.lead_id:
        try:
            from database.models.lead_loan import Lead
            lead = db.get(Lead, cf.lead_id)
            if lead:
                first = lead.first_name
                last = lead.last_name
                if not first and not last and getattr(lead, "name", None):
                    parts = lead.name.strip().split(" ", 1)
                    first = parts[0]
                    last = parts[1] if len(parts) > 1 else ""
                if first or last:
                    cf.first_name = first or ""
                    cf.last_name = last or ""
                    db.flush()
        except Exception as e:
            logger.warning("Could not backfill name from lead %s: %s", cf.lead_id, e)
    try:
        loan = _active_loan(db, cf, current_user.organization_id)
    except Exception as e:
        logger.exception("Failed to resolve active loan for client file %s", client_file_id)
        loan = None
    try:
        lo_name = _lo_name(db, cf.assigned_loan_officer_id)
    except Exception as e:
        logger.exception("Failed to resolve LO name for client file %s", client_file_id)
        lo_name = None
    try:
        return _to_response(cf, lo_name, loan=loan)
    except Exception as e:
        logger.exception("Failed to serialize client file %s: %s", client_file_id, e)
        return {
            "id": str(cf.id),
            "org_id": str(cf.organization_id),
            "first_name": cf.first_name,
            "last_name": cf.last_name,
            "primary_email": cf.primary_email,
            "primary_phone": cf.primary_phone,
            "lifecycle_stage": cf.lifecycle_stage or "new_lead",
            "lead_id": cf.lead_id,
            "tags": cf.tags or [],
            "custom_fields": {},
            "unread_thread_count": 0,
            "open_doc_request_count": 0,
            "created_at": cf.created_at.isoformat() if cf.created_at else datetime.now(timezone.utc).isoformat(),
            "updated_at": cf.updated_at.isoformat() if cf.updated_at else datetime.now(timezone.utc).isoformat(),
        }


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


def _task_to_response(task: Any, cf_id: uuid.UUID, owner_name: Optional[str] = None) -> dict:
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
        assigned_to_user_name=owner_name,
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

    owner_ids = {t.owner_id for t in tasks if t.owner_id}
    owner_names: dict[int, str] = {}
    if owner_ids:
        from database.models.core import User
        users = db.execute(
            select(User.id, User.first_name, User.last_name).where(User.id.in_(owner_ids))
        ).all()
        for u in users:
            owner_names[u.id] = f"{u.first_name or ''} {u.last_name or ''}".strip()

    return [_task_to_response(t, client_file_id, owner_names.get(t.owner_id)) for t in tasks]


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


class PatchTaskBody(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    priority: Optional[str] = None
    due_at: Optional[str] = None
    assigned_to_user_id: Optional[int] = None


@router.patch("/clients/{client_file_id}/tasks/{task_id}")
def patch_task(
    client_file_id: uuid.UUID,
    task_id: int,
    body: PatchTaskBody,
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
    if body.title is not None:
        task.title = body.title
    if body.body is not None:
        task.description = body.body
    if body.priority is not None:
        task.priority = body.priority
    if body.due_at is not None:
        task.due_date = datetime.fromisoformat(body.due_at) if body.due_at else None
    if body.assigned_to_user_id is not None:
        task.owner_id = body.assigned_to_user_id
    db.commit()
    db.refresh(task)
    owner_name = _lo_name(db, task.owner_id)
    return _task_to_response(task, client_file_id, owner_name)


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
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
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
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    org_id = current_user.organization_id
    lead_id = cf.lead_id
    client_phone = cf.primary_phone

    from database.models.communication import Activity, Email, EmailMessage, SMSMessage, SMSConversation
    from database.enums import ActivityType

    events: list[dict] = []

    # ── Activities (notes, calls, meetings, docs) ───────────────────────
    if lead_id:
        try:
            activity_q = select(Activity).where(
                Activity.lead_id == lead_id,
                Activity.organization_id == org_id,
            )
            if category == "notes":
                activity_q = activity_q.where(Activity.type == ActivityType.NOTE)
            elif category == "calls":
                activity_q = activity_q.where(Activity.type == ActivityType.CALL)
            elif category == "texts":
                activity_q = activity_q.where(Activity.type == ActivityType.SMS)
            elif category == "emails":
                activity_q = activity_q.where(Activity.type == ActivityType.EMAIL)

            kind_map = {
                ActivityType.NOTE: "note_added",
                ActivityType.CALL: "call_outbound",
                ActivityType.EMAIL: "message_sent_email",
                ActivityType.SMS: "message_sent_sms",
                ActivityType.MEETING: "appointment_booked",
                ActivityType.DOCUMENT: "document_uploaded",
            }
            cat_map = {
                ActivityType.NOTE: "notes",
                ActivityType.CALL: "calls",
                ActivityType.EMAIL: "emails",
                ActivityType.SMS: "texts",
                ActivityType.MEETING: "activity",
                ActivityType.DOCUMENT: "documents",
            }
            for a in db.execute(activity_q.order_by(Activity.created_at.desc()).limit(limit)).scalars():
                events.append(_make_timeline_event(
                    id=f"act-{a.id}",
                    client_file_id=str(client_file_id),
                    org_id=str(org_id),
                    kind=kind_map.get(a.type, "note_added"),
                    event_category=cat_map.get(a.type, "activity"),
                    occurred_at=a.created_at,
                    headline=a.type.value if a.type else "Activity",
                    body=a.content,
                    actor_user_id=str(a.user_id) if a.user_id else None,
                ))
        except Exception as e:
            logger.exception("Timeline: failed to load activities for lead %s: %s", lead_id, e)
            db.rollback()

    # ── SMS messages (by lead_id + phone-based via conversation) ────────
    if category in ("all", "texts"):
        seen_sms_ids: set[int] = set()

        if lead_id:
            try:
                sms_q = (
                    select(SMSMessage)
                    .where(SMSMessage.lead_id == lead_id, SMSMessage.organization_id == org_id)
                    .order_by(SMSMessage.created_at.desc())
                    .limit(limit)
                )
                for s in db.execute(sms_q).scalars():
                    seen_sms_ids.add(s.id)
                    inbound = s.direction == "inbound"
                    events.append(_make_timeline_event(
                        id=f"sms-{s.id}",
                        client_file_id=str(client_file_id),
                        org_id=str(org_id),
                        kind="message_received_sms" if inbound else "message_sent_sms",
                        event_category="texts",
                        occurred_at=s.created_at,
                        headline="Text received" if inbound else "Text sent",
                        body=s.message,
                        actor_user_id=str(s.user_id) if s.user_id and not inbound else None,
                        related_message_id=s.provider_message_id,
                    ))
            except Exception as e:
                logger.exception("Timeline: failed to load SMS for lead %s: %s", lead_id, e)
                db.rollback()

        if client_phone:
            try:
                normalized = client_phone.strip().replace("-", "").replace("(", "").replace(")", "").replace(" ", "")
                if not normalized.startswith("+"):
                    normalized = "+1" + normalized if len(normalized) == 10 else "+" + normalized
                conv_ids = [
                    c.id for c in db.execute(
                        select(SMSConversation.id).where(
                            SMSConversation.organization_id == org_id,
                            SMSConversation.phone_number == normalized,
                        )
                    ).scalars()
                ]
                if conv_ids:
                    phone_sms_q = (
                        select(SMSMessage)
                        .where(
                            SMSMessage.conversation_id.in_(conv_ids),
                            SMSMessage.organization_id == org_id,
                        )
                        .order_by(SMSMessage.created_at.desc())
                        .limit(limit)
                    )
                    for s in db.execute(phone_sms_q).scalars():
                        if s.id in seen_sms_ids:
                            continue
                        seen_sms_ids.add(s.id)
                        inbound = s.direction == "inbound"
                        events.append(_make_timeline_event(
                            id=f"sms-{s.id}",
                            client_file_id=str(client_file_id),
                            org_id=str(org_id),
                            kind="message_received_sms" if inbound else "message_sent_sms",
                            event_category="texts",
                            occurred_at=s.created_at,
                            headline="Text received" if inbound else "Text sent",
                            body=s.message,
                            actor_user_id=str(s.user_id) if s.user_id and not inbound else None,
                            related_message_id=s.provider_message_id,
                        ))
            except Exception as e:
                logger.exception("Timeline: failed to load phone-based SMS for client %s: %s", client_file_id, e)
                db.rollback()

        # ── SMS from sms_delivery_log (outbound Telnyx tracking) ──────
        phone_suffix = ""
        if client_phone:
            phone_suffix = client_phone.strip().replace("-", "").replace("(", "").replace(")", "").replace(" ", "").replace("+", "")
            if len(phone_suffix) > 10:
                phone_suffix = phone_suffix[-10:]

        if lead_id or phone_suffix:
            try:
                conditions = []
                dl_params: dict = {"org_id": org_id, "lim": limit}
                if lead_id:
                    conditions.append("lead_id = :lead_id")
                    dl_params["lead_id"] = lead_id
                if phone_suffix:
                    conditions.append("REPLACE(REPLACE(REPLACE(to_phone, '+', ''), '-', ''), ' ', '') LIKE :phone_pat")
                    dl_params["phone_pat"] = f"%{phone_suffix}"
                where_clause = " OR ".join(conditions)
                for r in db.execute(text(f"""
                    SELECT id, message_body, sent_at, created_at, user_id, telnyx_message_id
                    FROM sms_delivery_log
                    WHERE organization_id = :org_id AND ({where_clause})
                    ORDER BY COALESCE(sent_at, created_at) DESC
                    LIMIT :lim
                """), dl_params).fetchall():
                    events.append(_make_timeline_event(
                        id=f"dl-{r[0]}",
                        client_file_id=str(client_file_id),
                        org_id=str(org_id),
                        kind="message_sent_sms",
                        event_category="texts",
                        occurred_at=r[2] or r[3],
                        headline="Text sent",
                        body=r[1],
                        actor_user_id=str(r[4]) if r[4] else None,
                        related_message_id=r[5],
                    ))
            except Exception as exc:
                logger.warning("Timeline: sms_delivery_log query failed: %s", exc)
                try:
                    db.rollback()
                except Exception:
                    pass

        # ── SMS from sms_panel_messages (two-way SMS archive) ─────────
        if phone_suffix:
            try:
                for r in db.execute(text("""
                    SELECT id, direction, body, sender_name, sender_user_id, status,
                           created_at, telnyx_message_id
                    FROM sms_panel_messages
                    WHERE organization_id = :org_id
                      AND REPLACE(REPLACE(REPLACE(phone, '+', ''), '-', ''), ' ', '') LIKE :phone_pat
                    ORDER BY created_at DESC
                    LIMIT :lim
                """), {"org_id": org_id, "phone_pat": f"%{phone_suffix}", "lim": limit}).fetchall():
                    inbound = r[1] == "inbound"
                    events.append(_make_timeline_event(
                        id=f"pm-{r[0]}",
                        client_file_id=str(client_file_id),
                        org_id=str(org_id),
                        kind="message_received_sms" if inbound else "message_sent_sms",
                        event_category="texts",
                        occurred_at=r[6],
                        headline="Text received" if inbound else "Text sent",
                        body=r[2],
                        actor_user_id=str(r[4]) if r[4] and not inbound else None,
                        related_message_id=r[7],
                    ))
            except Exception as exc:
                logger.warning("Timeline: sms_panel_messages query failed: %s", exc)
                try:
                    db.rollback()
                except Exception:
                    pass

    # ── Emails (outbound via email_messages + inbound via emails) ──────
    if category in ("all", "emails") and lead_id:
        try:
            for em in db.execute(
                select(EmailMessage)
                .where(EmailMessage.lead_id == lead_id, EmailMessage.organization_id == org_id)
                .order_by(EmailMessage.created_at.desc())
                .limit(limit)
            ).scalars():
                inbound = em.direction == "inbound"
                events.append(_make_timeline_event(
                    id=f"em-{em.id}",
                    client_file_id=str(client_file_id),
                    org_id=str(org_id),
                    kind="message_received_email" if inbound else "message_sent_email",
                    event_category="emails",
                    occurred_at=em.created_at,
                    headline=em.subject or ("Email received" if inbound else "Email sent"),
                    body=(em.body or em.html_body or "")[:500],
                    actor_user_id=str(em.user_id) if em.user_id and not inbound else None,
                    related_message_id=em.microsoft_message_id,
                ))
        except Exception as e:
            logger.exception("Timeline: failed to load email_messages for lead %s: %s", lead_id, e)
            db.rollback()

        try:
            for e in db.execute(
                select(Email)
                .where(Email.lead_id == lead_id, Email.organization_id == org_id)
                .order_by(Email.received_date.desc())
                .limit(limit)
            ).scalars():
                is_sent = (e.folder_name or "").lower() in ("sent", "sent items", "sentitems")
                events.append(_make_timeline_event(
                    id=f"graph-{e.id}",
                    client_file_id=str(client_file_id),
                    org_id=str(org_id),
                    kind="message_sent_email" if is_sent else "message_received_email",
                    event_category="emails",
                    occurred_at=e.received_date or e.created_at,
                    headline=e.subject or ("Email sent" if is_sent else "Email received"),
                    body=(e.body_text or "")[:500],
                    actor_user_id=str(e.user_id) if e.user_id and is_sent else None,
                    metadata={"sender_email": e.sender_email, "sender_name": e.sender_name},
                ))
        except Exception as e:
            logger.exception("Timeline: failed to load Graph emails for lead %s: %s", lead_id, e)
            db.rollback()

    # Deduplicate: prefer dedicated records (sms-*, em-*, graph-*) over Activity records (act-*)
    # when they describe the same event (same body text within the same second).
    detailed_keys: set[str] = set()
    for ev in events:
        eid = ev.get("id", "")
        if eid.startswith(("sms-", "em-", "graph-", "dl-", "pm-")):
            body_key = (ev.get("body") or "")[:100]
            if not body_key:
                continue
            ts = (ev.get("occurred_at") or "")[:16]
            detailed_keys.add(f"{body_key}|{ts}")

    seen_msg_ids: set[str] = set()
    deduped: list[dict] = []
    for ev in events:
        eid = ev.get("id", "")
        mid = ev.get("related_message_id")
        if mid and mid in seen_msg_ids:
            continue
        if mid:
            seen_msg_ids.add(mid)
        if eid.startswith("act-"):
            body_key = (ev.get("body") or "")[:100]
            ts = (ev.get("occurred_at") or "")[:16]
            if f"{body_key}|{ts}" in detailed_keys:
                continue
        deduped.append(ev)

    deduped.sort(key=lambda e: e.get("occurred_at", ""), reverse=True)
    return deduped[:limit]


def _make_timeline_event(
    *,
    id: str,
    client_file_id: str,
    org_id: str,
    kind: str,
    event_category: str,
    occurred_at: Optional[datetime],
    headline: str,
    body: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    actor_agent_slug: Optional[str] = None,
    related_message_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    return {
        "id": id,
        "org_id": org_id,
        "client_file_id": client_file_id,
        "kind": kind,
        "category": event_category,
        "occurred_at": occurred_at.isoformat() if occurred_at else datetime.now(timezone.utc).isoformat(),
        "headline": headline,
        "body": body,
        "actor_user_id": actor_user_id,
        "actor_user_name": None,
        "actor_agent_slug": actor_agent_slug,
        "actor_agent_skill": None,
        "actor_agent_skill_version": None,
        "actor_is_system": actor_agent_slug is not None,
        "related_message_id": related_message_id,
        "related_thread_id": None,
        "related_document_request_id": None,
        "related_task_id": None,
        "related_cadence_sequence_id": None,
        "compliance_review_passed": None,
        "metadata": metadata or {},
        "is_starred": False,
        "ai_generated": False,
    }


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


def _get_loan_ids_for_cf(db: Session, cf, org_id: int) -> list[int]:
    """Resolve client_file → lead → loan IDs.

    Three resolution strategies, tried in order:
    1. Lead.loan_number → Loan.loan_number (SF sync, manual entry)
    2. APP-{lead_id} convention → Loan.loan_number (POS application flow)
    3. Lead.email → Loan.borrower_email (fallback for unlinked records)
    """
    if not cf.lead_id:
        return []
    from database.models.lead_loan import Lead, Loan
    lead = db.execute(
        select(Lead.id, Lead.loan_number, Lead.email).where(
            Lead.id == cf.lead_id, Lead.organization_id == org_id,
        )
    ).first()
    if not lead:
        return []
    loan_ids = []

    if lead.loan_number:
        loan_ids = [
            lid for (lid,) in db.execute(
                select(Loan.id).where(
                    Loan.loan_number == lead.loan_number,
                    Loan.organization_id == org_id,
                )
            ).all()
        ]

    if not loan_ids:
        app_loan_number = f"APP-{str(lead.id).zfill(6)}"
        loan_ids = [
            lid for (lid,) in db.execute(
                select(Loan.id).where(
                    Loan.loan_number == app_loan_number,
                    Loan.organization_id == org_id,
                )
            ).all()
        ]

    if not loan_ids and lead.email:
        loan_ids = [
            lid for (lid,) in db.execute(
                select(Loan.id).where(
                    Loan.borrower_email == lead.email,
                    Loan.organization_id == org_id,
                )
            ).all()
        ]
    return loan_ids


@router.get("/clients/{client_file_id}/document-sets")
def list_document_sets(
    client_file_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
    if not loan_ids:
        return []

    from models.smart_docs_models import DocumentRequest, SmartDocument

    requests = db.execute(
        select(DocumentRequest).where(
            DocumentRequest.loan_id.in_(loan_ids),
            DocumentRequest.is_active == True,
        ).order_by(DocumentRequest.created_at.desc())
    ).scalars().all()

    docs_by_request: dict[int, list] = {}
    if requests:
        req_ids = [r.id for r in requests]
        docs = db.execute(
            select(SmartDocument).where(
                SmartDocument.request_id.in_(req_ids),
                SmartDocument.status != "DELETED",
            )
        ).scalars().all()
        for d in docs:
            docs_by_request.setdefault(d.request_id, []).append(d)

    DOC_TYPE_CATEGORY = {
        "PAYSTUB": "income", "W2": "income", "TAX_RETURN": "income",
        "BUSINESS_TAX_RETURN": "income", "PROFIT_LOSS": "income",
        "BALANCE_SHEET": "income",
        "BANK_STATEMENT": "assets", "INVESTMENT_STATEMENT": "assets",
        "GIFT_LETTER": "assets",
        "DRIVERS_LICENSE": "identity", "VA_COE": "identity", "DD214": "identity",
        "PURCHASE_CONTRACT": "property", "APPRAISAL": "property",
        "TITLE_REPORT": "property",
        "HOMEOWNERS_INSURANCE": "insurance",
        "BANKRUPTCY_DISCHARGE": "credit",
        "LOE": "other", "LEASE_AGREEMENT": "other",
        "FHA_CERT": "other", "OTHER": "other",
    }

    STATUS_MAP = {
        "OPEN": "pending", "PENDING_REVIEW": "under_review",
        "ACCEPTED": "fulfilled", "REJECTED": "rejected", "WAIVED": "waived",
    }

    sets_map: dict[str, dict] = {}
    for req in requests:
        dt = req.doc_type.value if hasattr(req.doc_type, "value") else str(req.doc_type)
        cat = DOC_TYPE_CATEGORY.get(dt, "other")
        if cat not in sets_map:
            sets_map[cat] = {
                "id": cat,
                "set_type": cat,
                "title": cat.replace("_", " ").title(),
                "open_count": 0,
                "fulfilled_count": 0,
                "rejected_count": 0,
                "requests": [],
            }
        s = sets_map[cat]
        status_str = req.status.value if hasattr(req.status, "value") else str(req.status)
        mapped_status = STATUS_MAP.get(status_str, "pending")
        is_stale = False
        req_docs = docs_by_request.get(req.id, [])
        for d in req_docs:
            if d.is_expired:
                is_stale = True
                break

        if mapped_status == "fulfilled":
            s["fulfilled_count"] += 1
        elif mapped_status == "rejected":
            s["rejected_count"] += 1
        else:
            s["open_count"] += 1

        s["requests"].append({
            "id": str(req.id),
            "client_file_id": str(client_file_id),
            "document_set_id": cat,
            "doc_type": dt,
            "title": req.title,
            "description": req.description,
            "status": mapped_status,
            "priority": (req.priority.value if hasattr(req.priority, "value") else str(req.priority or "NORMAL")).lower(),
            "due_at": _iso(req.due_date),
            "expires_after_days": req.freshness_days,
            "fulfilled_at": _iso(req.fulfilled_at),
            "rejection_reason": None,
            "is_stale": is_stale,
        })

    return list(sets_map.values())


@router.get("/clients/{client_file_id}/documents")
def list_documents(
    client_file_id: uuid.UUID,
    tab: str = Query("all"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """List documents for a client file. tab: requested, received, archived, all."""
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
    if not loan_ids:
        return {"requests": [], "documents": []}

    from models.smart_docs_models import DocumentRequest, SmartDocument

    requests = db.execute(
        select(DocumentRequest).where(
            DocumentRequest.loan_id.in_(loan_ids),
            DocumentRequest.is_active == True,
        ).order_by(DocumentRequest.created_at.desc())
    ).scalars().all()

    docs = db.execute(
        select(SmartDocument).where(
            SmartDocument.loan_id.in_(loan_ids),
            SmartDocument.status != "DELETED",
        ).order_by(SmartDocument.created_at.desc())
    ).scalars().all()

    def _req_to_dict(r):
        st = r.status.value if hasattr(r.status, "value") else str(r.status)
        dt = r.doc_type.value if hasattr(r.doc_type, "value") else str(r.doc_type)
        pr = r.priority.value if hasattr(r.priority, "value") else str(r.priority or "NORMAL")
        return {
            "id": r.id,
            "loan_id": r.loan_id,
            "doc_type": dt,
            "title": r.title,
            "description": r.description,
            "instructions": r.instructions,
            "status": st,
            "priority": pr,
            "due_date": _iso(r.due_date),
            "sla_due_at": _iso(r.sla_due_at),
            "freshness_days": r.freshness_days,
            "fulfilled_at": _iso(r.fulfilled_at),
            "created_at": _iso(r.created_at),
        }

    def _doc_to_dict(d):
        dt = d.doc_type.value if hasattr(d.doc_type, "value") else str(d.doc_type) if d.doc_type else None
        return {
            "id": d.id,
            "request_id": d.request_id,
            "loan_id": d.loan_id,
            "file_name": d.file_name,
            "original_filename": d.original_filename,
            "mime_type": d.mime_type,
            "file_size": d.file_size,
            "page_count": d.page_count,
            "doc_type": dt,
            "detected_doc_type": d.detected_doc_type,
            "display_name": d.display_name,
            "status": d.status,
            "decision": d.decision.value if d.decision and hasattr(d.decision, "value") else d.decision,
            "decision_reasons": d.decision_reasons,
            "rejection_reason": d.rejection_reason,
            "rejection_category": d.rejection_category.value if d.rejection_category and hasattr(d.rejection_category, "value") else d.rejection_category,
            "fix_instructions": d.fix_instructions,
            "detected_is_screenshot": d.detected_is_screenshot,
            "screenshot_confidence": d.screenshot_confidence,
            "is_expired": d.is_expired,
            "doc_date": _iso(d.doc_date),
            "doc_expires_at": _iso(d.doc_expires_at),
            "extracted_names": d.extracted_names,
            "extracted_employer": d.extracted_employer,
            "extracted_amount": float(d.extracted_amount) if d.extracted_amount else None,
            "extraction_confidence": d.extraction_confidence,
            "reviewed_at": _iso(d.reviewed_at),
            "reviewed_by": d.reviewed_by,
            "uploaded_at": _iso(d.uploaded_at),
            "created_at": _iso(d.created_at),
        }

    REQUESTED_STATUSES = {"OPEN", "PENDING_REVIEW"}
    RECEIVED_DOC_STATUSES = {"UPLOADED", "SCANNING", "PROCESSING", "PENDING_REVIEW", "NEEDS_REVIEW", "APPROVED"}
    ARCHIVED_DOC_STATUSES = {"REJECTED", "EXPIRED", "SUPERSEDED"}
    ARCHIVED_REQ_STATUSES = {"ACCEPTED", "WAIVED", "REJECTED"}

    req_list = [_req_to_dict(r) for r in requests]
    doc_list = [_doc_to_dict(d) for d in docs]

    if tab == "requested":
        req_list = [r for r in req_list if r["status"] in REQUESTED_STATUSES]
        doc_list = []
    elif tab == "received":
        req_list = [r for r in req_list if r["status"] == "PENDING_REVIEW"]
        doc_list = [d for d in doc_list if d["status"] in RECEIVED_DOC_STATUSES]
    elif tab == "archived":
        req_list = [r for r in req_list if r["status"] in ARCHIVED_REQ_STATUSES]
        doc_list = [d for d in doc_list if d["status"] in ARCHIVED_DOC_STATUSES]

    return {"requests": req_list, "documents": doc_list}


@router.get("/clients/{client_file_id}/documents/{document_id}")
def get_document_detail(
    client_file_id: uuid.UUID,
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get full document detail including AI review results."""
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
    if not loan_ids:
        raise HTTPException(404, "no loans linked to this client file")

    from models.smart_docs_models import SmartDocument
    doc = db.execute(
        select(SmartDocument).where(
            SmartDocument.id == document_id,
            SmartDocument.loan_id.in_(loan_ids),
        )
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(404, "document not found")

    dt = doc.doc_type.value if hasattr(doc.doc_type, "value") else str(doc.doc_type) if doc.doc_type else None
    return {
        "id": doc.id,
        "request_id": doc.request_id,
        "loan_id": doc.loan_id,
        "file_name": doc.file_name,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "file_size": doc.file_size,
        "page_count": doc.page_count,
        "storage_key": doc.storage_key,
        "doc_type": dt,
        "detected_doc_type": doc.detected_doc_type,
        "display_name": doc.display_name,
        "status": doc.status,
        "decision": doc.decision.value if doc.decision and hasattr(doc.decision, "value") else doc.decision,
        "decision_reasons": doc.decision_reasons,
        "rejection_reason": doc.rejection_reason,
        "rejection_category": doc.rejection_category.value if doc.rejection_category and hasattr(doc.rejection_category, "value") else doc.rejection_category,
        "fix_instructions": doc.fix_instructions,
        "detected_is_screenshot": doc.detected_is_screenshot,
        "screenshot_confidence": doc.screenshot_confidence,
        "screenshot_reasons": doc.screenshot_reasons,
        "is_expired": doc.is_expired,
        "doc_date": _iso(doc.doc_date),
        "doc_expires_at": _iso(doc.doc_expires_at),
        "days_until_expiration": doc.days_until_expiration,
        "extracted_dates": doc.extracted_dates,
        "extracted_names": doc.extracted_names,
        "extracted_employer": doc.extracted_employer,
        "extracted_account_number": doc.extracted_account_number,
        "extracted_amount": float(doc.extracted_amount) if doc.extracted_amount else None,
        "extraction_confidence": doc.extraction_confidence,
        "ocr_text": doc.ocr_text[:500] if doc.ocr_text else None,
        "reviewed_at": _iso(doc.reviewed_at),
        "reviewed_by": doc.reviewed_by,
        "upload_source": doc.upload_source,
        "uploaded_at": _iso(doc.uploaded_at),
        "created_at": _iso(doc.created_at),
    }


class CreateDocRequestBody(BaseModel):
    doc_type: str
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    priority: str = "NORMAL"
    due_date: Optional[str] = None


@router.post("/clients/{client_file_id}/documents/request")
def create_document_request(
    client_file_id: uuid.UUID,
    body: CreateDocRequestBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Create a new document request for this client's loan."""
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
    if not loan_ids:
        raise HTTPException(400, "no loan linked to this client file — cannot request documents")

    from models.smart_docs_models import DocumentRequest, DocType, RequestPriority
    try:
        doc_type = DocType(body.doc_type)
    except ValueError:
        doc_type = DocType.OTHER

    try:
        priority = RequestPriority(body.priority)
    except ValueError:
        priority = RequestPriority.NORMAL

    due = None
    if body.due_date:
        due = datetime.fromisoformat(body.due_date)

    req = DocumentRequest(
        organization_id=current_user.organization_id,
        loan_id=loan_ids[0],
        doc_type=doc_type,
        title=body.title,
        description=body.description,
        instructions=body.instructions,
        priority=priority,
        due_date=due,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    return {
        "id": req.id,
        "loan_id": req.loan_id,
        "doc_type": req.doc_type.value if hasattr(req.doc_type, "value") else str(req.doc_type),
        "title": req.title,
        "status": req.status.value if hasattr(req.status, "value") else str(req.status),
        "priority": req.priority.value if hasattr(req.priority, "value") else str(req.priority),
        "created_at": _iso(req.created_at),
    }


@router.post("/clients/{client_file_id}/documents/{document_id}/approve")
def approve_document(
    client_file_id: uuid.UUID,
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
    if not loan_ids:
        raise HTTPException(404, "no loans linked")

    from models.smart_docs_models import SmartDocument, DocumentRequest
    doc = db.execute(
        select(SmartDocument).where(
            SmartDocument.id == document_id,
            SmartDocument.loan_id.in_(loan_ids),
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "document not found")

    doc.status = "APPROVED"
    doc.decision = "ACCEPT"
    doc.reviewed_at = datetime.now(timezone.utc)
    doc.reviewed_by = str(current_user.id)

    if doc.request_id:
        req = db.get(DocumentRequest, doc.request_id)
        if req:
            req.status = "ACCEPTED"
            req.fulfilled_at = datetime.now(timezone.utc)

    db.commit()
    return {"status": "approved", "document_id": document_id}


class RejectDocBody(BaseModel):
    reason: str
    category: str = "OTHER"
    fix_instructions: Optional[str] = None


@router.post("/clients/{client_file_id}/documents/{document_id}/reject")
def reject_document(
    client_file_id: uuid.UUID,
    document_id: int,
    body: RejectDocBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
    if not loan_ids:
        raise HTTPException(404, "no loans linked")

    from models.smart_docs_models import SmartDocument, DocumentRequest
    doc = db.execute(
        select(SmartDocument).where(
            SmartDocument.id == document_id,
            SmartDocument.loan_id.in_(loan_ids),
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "document not found")

    doc.status = "REJECTED"
    doc.decision = "REJECT"
    doc.rejection_reason = body.reason
    doc.rejection_category = body.category
    doc.fix_instructions = body.fix_instructions
    doc.reviewed_at = datetime.now(timezone.utc)
    doc.reviewed_by = str(current_user.id)

    if doc.request_id:
        req = db.get(DocumentRequest, doc.request_id)
        if req:
            req.status = "REJECTED"

    db.commit()
    return {"status": "rejected", "document_id": document_id}


@router.post("/clients/{client_file_id}/documents/{document_id}/ai-review")
def trigger_ai_review(
    client_file_id: uuid.UUID,
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Trigger AI review for a document."""
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
    if not loan_ids:
        raise HTTPException(404, "no loans linked")

    from models.smart_docs_models import SmartDocument
    doc = db.execute(
        select(SmartDocument).where(
            SmartDocument.id == document_id,
            SmartDocument.loan_id.in_(loan_ids),
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "document not found")

    try:
        from services.smart_docs.ai_review_service import review_document
        result = review_document(db, doc)
        return {
            "document_id": document_id,
            "decision": result.get("decision"),
            "reasons": result.get("reasons", []),
            "fix_instructions": result.get("fix_instructions"),
        }
    except ImportError:
        return {
            "document_id": document_id,
            "decision": doc.decision.value if doc.decision and hasattr(doc.decision, "value") else doc.decision,
            "reasons": doc.decision_reasons or [],
            "fix_instructions": doc.fix_instructions,
        }


@router.get("/clients/{client_file_id}/documents/{document_id}/download-url")
def get_document_download_url(
    client_file_id: uuid.UUID,
    document_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Get a presigned download URL for a document."""
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    loan_ids = _get_loan_ids_for_cf(db, cf, current_user.organization_id)
    if not loan_ids:
        raise HTTPException(404, "no loans linked")

    from models.smart_docs_models import SmartDocument
    doc = db.execute(
        select(SmartDocument).where(
            SmartDocument.id == document_id,
            SmartDocument.loan_id.in_(loan_ids),
        )
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "document not found")

    try:
        from services.smart_docs.s3_storage_service import generate_presigned_url
        url = generate_presigned_url(doc.storage_key)
        return {"url": url, "filename": doc.original_filename or doc.file_name}
    except Exception:
        raise HTTPException(501, "document download not available")


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


class NoteBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=10000)


@router.post("/clients/{client_file_id}/notes", status_code=201)
def add_note(
    client_file_id: uuid.UUID,
    payload: NoteBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    if not cf.lead_id:
        raise HTTPException(400, "client file has no linked lead")

    from database.models.communication import Activity
    from database.enums import ActivityType

    activity = Activity(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        lead_id=cf.lead_id,
        type=ActivityType.NOTE,
        content=payload.body,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    return _make_timeline_event(
        id=f"act-{activity.id}",
        client_file_id=str(client_file_id),
        org_id=str(current_user.organization_id),
        kind="note_added",
        event_category="notes",
        occurred_at=activity.created_at,
        headline="Note",
        body=payload.body,
        actor_user_id=str(current_user.id),
    )


class SendMessageBody(BaseModel):
    channel: str = Field(..., pattern="^(sms|email|voice_brief)$")
    body: str = Field(..., min_length=1, max_length=10000)
    subject: Optional[str] = None
    also_start_followup: bool = False
    followup_goal: Optional[str] = None


@router.post("/clients/{client_file_id}/messages", status_code=201)
async def send_message(
    client_file_id: uuid.UUID,
    payload: SendMessageBody,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    cf = _get_cf(db, client_file_id, current_user.organization_id)
    if not cf.lead_id:
        raise HTTPException(400, "client file has no linked lead")

    org_id = current_user.organization_id
    user_id = current_user.id

    if payload.channel == "sms":
        return await _send_sms_from_client_file(
            db, cf, client_file_id, org_id, user_id, payload.body, current_user,
        )
    elif payload.channel == "email":
        return await _send_email_from_client_file(
            db, cf, client_file_id, org_id, user_id, payload.body,
            payload.subject, current_user,
        )
    else:
        raise HTTPException(400, f"channel '{payload.channel}' not yet supported")


async def _send_sms_from_client_file(
    db: Session,
    cf: Any,
    client_file_id: uuid.UUID,
    org_id: int,
    user_id: int,
    body: str,
    current_user: Any,
) -> dict:
    # Read ALL attributes from cf BEFORE SMSClient touches the session.
    # SMSClient.__init__ and .send_sms() do multiple db.rollback()/flush()
    # calls that expire ORM objects and corrupt the session state.
    phone = cf.primary_phone
    lead_id = cf.lead_id
    if not phone:
        raise HTTPException(400, "client has no phone number on file")

    from integrations.sms_service import SMSClient

    sms_client = SMSClient(db, user_id=user_id)
    if not sms_client.enabled:
        raise HTTPException(503, "SMS service not configured")

    from_number = sms_client.from_number or ""

    try:
        result = sms_client.send_sms(
            phone,
            body,
            lead_id=lead_id,
            user_id=user_id,
            organization_id=org_id,
        )
    except Exception as e:
        logger.error("SMS send_sms exception: %s", e, exc_info=True)
        raise HTTPException(502, f"SMS send failed: {e}")

    if not result.get("success"):
        error = result.get("error") or result.get("reason") or "SMS send failed"
        raise HTTPException(502, error)

    # SMS was delivered — record-keeping uses a fresh DB session + raw SQL
    # because the request-scoped session is corrupted by SMSClient internals.
    provider_msg_id = result.get("message_id")

    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)

    from db import SessionLocal
    from sqlalchemy import text as sa_text

    sms_row_id = None
    activity_row_id = None
    try:
        record_db = SessionLocal()
        # TENANT-017: Set RLS context for record-keeping session
        if org_id:
            try:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(record_db, org_id)
            except Exception:
                pass
        try:
            row = record_db.execute(sa_text("""
                INSERT INTO sms_messages
                    (organization_id, user_id, lead_id, to_number, from_number,
                     message, direction, status, provider_message_id, created_at)
                VALUES (:org_id, :user_id, :lead_id, :to_number, :from_number,
                        :message, 'outbound', 'sent', :provider_msg_id, NOW())
                RETURNING id
            """), {
                "org_id": org_id, "user_id": user_id, "lead_id": lead_id,
                "to_number": phone, "from_number": from_number,
                "message": body, "provider_msg_id": provider_msg_id,
            }).fetchone()
            if row:
                sms_row_id = row[0]
        except Exception as e:
            record_db.rollback()
            logger.warning("sms_messages insert failed (SMS was sent): %s", e)

        try:
            row = record_db.execute(sa_text("""
                INSERT INTO activities
                    (organization_id, user_id, lead_id, type, content, created_at)
                VALUES (:org_id, :user_id, :lead_id, 'SMS', :content, NOW())
                RETURNING id
            """), {
                "org_id": org_id, "user_id": user_id, "lead_id": lead_id,
                "content": body,
            }).fetchone()
            if row:
                activity_row_id = row[0]
        except Exception as e:
            record_db.rollback()
            logger.warning("Activity insert failed (SMS was sent): %s", e)

        record_db.commit()
    except Exception as e:
        logger.error("SMS record-keeping failed: %s", e)
    finally:
        try:
            record_db.close()
        except Exception:
            pass

    event_id = f"sms-{sms_row_id}" if sms_row_id else (
        f"act-{activity_row_id}" if activity_row_id else f"tmp-{provider_msg_id or 'sms'}"
    )

    return _make_timeline_event(
        id=event_id,
        client_file_id=str(client_file_id),
        org_id=str(org_id),
        kind="message_sent_sms",
        event_category="texts",
        occurred_at=now,
        headline="Text sent",
        body=body,
        actor_user_id=str(user_id),
        related_message_id=provider_msg_id,
    )


async def _send_email_from_client_file(
    db: Session,
    cf: Any,
    client_file_id: uuid.UUID,
    org_id: int,
    user_id: int,
    body: str,
    subject: Optional[str],
    current_user: Any,
) -> dict:
    to_email = cf.primary_email
    if not to_email:
        raise HTTPException(400, "client has no email address on file")

    subject = subject or "Message from your loan officer"

    from routes.ai_email_routes import _get_microsoft_token, _send_via_graph

    try:
        access_token = await _get_microsoft_token(user_id, db)
    except Exception as e:
        logger.warning("Microsoft token unavailable for user %s: %s", user_id, e)
        raise HTTPException(
            400,
            "Microsoft 365 not connected. Please connect your Outlook account in Settings.",
        )

    import html as _html
    safe_body_html = f"<p>{_html.escape(body)}</p>"

    result = await _send_via_graph(
        access_token=access_token,
        to_email=to_email,
        subject=subject,
        body_html=safe_body_html,
    )

    if not result.get("success"):
        error_msg = result.get("error", "Email send failed")
        if "401" in str(error_msg) or "token" in str(error_msg).lower():
            raise HTTPException(
                400,
                "Microsoft 365 session expired. Please reconnect your Outlook account.",
            )
        raise HTTPException(502, error_msg)

    from database.models.communication import Activity, EmailMessage
    from database.enums import ActivityType

    from_email = getattr(current_user, "email", "") or ""
    em = EmailMessage(
        organization_id=org_id,
        user_id=user_id,
        lead_id=cf.lead_id,
        to_email=to_email,
        from_email=from_email,
        subject=subject,
        body=body,
        html_body=safe_body_html,
        direction="outbound",
        status="sent",
        microsoft_message_id=result.get("message_id"),
    )
    db.add(em)

    activity = Activity(
        organization_id=org_id,
        user_id=user_id,
        lead_id=cf.lead_id,
        type=ActivityType.EMAIL,
        content=f"Email sent: {subject}",
    )
    db.add(activity)
    db.commit()
    db.refresh(em)

    return _make_timeline_event(
        id=f"em-{em.id}",
        client_file_id=str(client_file_id),
        org_id=str(org_id),
        kind="message_sent_email",
        event_category="emails",
        occurred_at=em.created_at,
        headline=subject,
        body=body,
        actor_user_id=str(user_id),
        related_message_id=em.microsoft_message_id,
    )


@router.post("/clients/{client_file_id}/timeline/{event_id}/star")
def star_event(
    client_file_id: uuid.UUID,
    event_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    return _make_timeline_event(
        id=str(event_id),
        client_file_id=str(client_file_id),
        org_id=str(current_user.organization_id),
        kind="note_added",
        event_category="activity",
        occurred_at=datetime.now(timezone.utc),
        headline="Starred",
    )


# ─── Cross-entity client file resolution (auto-create) ────────────────

def _get_or_create_client_file(db: Session, lead_id: int, org_id: int) -> str:
    """Look up the client file for a lead. If none exists, create one from the lead data."""
    from database.models.client_file import ClientFile
    from database.models.lead_loan import Lead

    cf_id = db.execute(
        select(ClientFile.id).where(
            ClientFile.lead_id == lead_id,
            ClientFile.organization_id == org_id,
        )
    ).scalar_one_or_none()
    if cf_id is not None:
        return str(cf_id)

    # Fix orphaned records from backfill with wrong org_id
    orphan_id = db.execute(
        select(ClientFile.id).where(ClientFile.lead_id == lead_id)
    ).scalar_one_or_none()
    if orphan_id is not None:
        db.execute(
            text("UPDATE client_files SET organization_id = :org WHERE id = :id"),
            {"org": org_id, "id": orphan_id},
        )
        db.commit()
        return str(orphan_id)

    lead = db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id)
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(404, "lead not found")

    stage_map = {
        "New": "new_lead", "Attempted Contact": "new_lead",
        "Prospect": "prospect", "Pre-Qualified": "prospect",
        "Application": "active_borrower", "Pre-Approved": "active_borrower",
        "Funded": "post_close",
    }
    lifecycle = stage_map.get(lead.stage, "new_lead")

    cf = ClientFile(
        organization_id=org_id,
        lead_id=lead_id,
        first_name=lead.first_name or (lead.name.split()[0] if lead.name else None),
        last_name=lead.last_name or (lead.name.split()[-1] if lead.name and " " in lead.name else None),
        primary_email=lead.email,
        primary_phone=lead.phone,
        lifecycle_stage=lifecycle,
        source=lead.source,
        preferred_channel=lead.preferred_communication,
        assigned_loan_officer_id=lead.owner_id,
        property_address={
            "street": lead.address, "city": lead.city,
            "state": lead.state, "zip": lead.zip_code,
        } if lead.address else None,
        active_loan_amount=float(lead.loan_amount) if lead.loan_amount else None,
        active_loan_fico=lead.credit_score,
        created_by_user_id=lead.owner_id,
    )
    db.add(cf)
    db.commit()
    db.refresh(cf)
    return str(cf.id)


def _find_lead_for_loan(db: Session, loan_id: int, org_id: int) -> int:
    """Resolve a loan to its originating lead via loan_number or borrower_email."""
    from database.models.lead_loan import Lead, Loan

    loan = db.execute(
        select(Loan.loan_number, Loan.borrower_email).where(
            Loan.id == loan_id, Loan.organization_id == org_id,
        )
    ).first()
    if loan is None:
        raise HTTPException(404, "loan not found")

    lead_id = None
    if loan.loan_number:
        lead_id = db.execute(
            select(Lead.id).where(
                Lead.loan_number == loan.loan_number,
                Lead.organization_id == org_id,
            )
        ).scalar_one_or_none()
    if lead_id is None and loan.borrower_email:
        lead_id = db.execute(
            select(Lead.id).where(
                Lead.email == loan.borrower_email,
                Lead.organization_id == org_id,
            )
        ).scalar_one_or_none()
    if lead_id is None:
        raise HTTPException(404, "no matching lead found for this loan")
    return lead_id


def _find_lead_for_mum(db: Session, mum_id: int, org_id: int) -> int:
    """Resolve a MUM client to its originating lead via loan_number or email."""
    from database.models.lead_loan import Lead
    from database.models.referral import MUMClient

    mum = db.execute(
        select(MUMClient.loan_number, MUMClient.email).where(
            MUMClient.id == mum_id, MUMClient.organization_id == org_id,
        )
    ).first()
    if mum is None:
        raise HTTPException(404, "MUM client not found")

    lead_id = None
    if mum.loan_number:
        lead_id = db.execute(
            select(Lead.id).where(
                Lead.loan_number == mum.loan_number,
                Lead.organization_id == org_id,
            )
        ).scalar_one_or_none()
    if lead_id is None and mum.email:
        lead_id = db.execute(
            select(Lead.id).where(
                Lead.email == mum.email,
                Lead.organization_id == org_id,
            )
        ).scalar_one_or_none()
    if lead_id is None:
        raise HTTPException(404, "no matching lead found for this MUM client")
    return lead_id


@router.get("/loans/{loan_id}/client-file-id")
def get_client_file_id_for_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Return (or auto-create) the client_file for a loan."""
    lead_id = _find_lead_for_loan(db, loan_id, current_user.organization_id)
    cf_id = _get_or_create_client_file(db, lead_id, current_user.organization_id)
    return {"client_file_id": cf_id}


@router.get("/mum-clients/{mum_id}/client-file-id")
def get_client_file_id_for_mum(
    mum_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """Return (or auto-create) the client_file for a MUM client."""
    lead_id = _find_lead_for_mum(db, mum_id, current_user.organization_id)
    cf_id = _get_or_create_client_file(db, lead_id, current_user.organization_id)
    return {"client_file_id": cf_id}


@router.delete("/clients/{client_file_id}/timeline/{event_id}/star")
def unstar_event(
    client_file_id: uuid.UUID,
    event_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    _get_cf(db, client_file_id, current_user.organization_id)
    return _make_timeline_event(
        id=str(event_id),
        client_file_id=str(client_file_id),
        org_id=str(current_user.organization_id),
        kind="note_added",
        event_category="activity",
        occurred_at=datetime.now(timezone.utc),
        headline="Unstarred",
    )
