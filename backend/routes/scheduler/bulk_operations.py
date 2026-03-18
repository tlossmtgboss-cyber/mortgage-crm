"""
Scheduler Bulk Operations - Enterprise bulk appointment management.

Endpoints:
  - POST /appointments/bulk-create       Create multiple appointments in one request
  - POST /appointments/bulk-cancel       Cancel multiple appointments
  - POST /appointments/bulk-reschedule   Reschedule multiple appointments
  - POST /appointments/bulk-assign       Reassign appointments to different LOs

All endpoints use savepoints so partial failures still commit the successful items.
Max 50 items per request. Requires authentication and tenant isolation (organization_id).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, EmailStr
import logging

from smart_scheduler_models import (
    AppointmentStatus, MeetingType, MeetingMode,
)
from scheduler_email_service import (
    send_appointment_confirmation_email,
    send_appointment_cancellation_email,
    send_appointment_update_email,
    send_team_member_notification_email,
    send_team_member_cancellation_email,
    generate_reschedule_url,
)
from services.notification_service import notification_service

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin,
    _convert_utc_to_user_tz,
    _check_appointment_conflict, _check_duplicate_booking,
    _ensure_lead_for_booking, _log_appointment_activity, _create_followup_task,
    _audit_log,
)
from routes.scheduler.constants import (
    DEFAULT_APPOINTMENT_DURATION_MINUTES,
    MIN_APPOINTMENT_DURATION_MINUTES,
    MAX_APPOINTMENT_DURATION_MINUTES,
    MAX_BULK_OPERATION_SIZE,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_BULK_SIZE = MAX_BULK_OPERATION_SIZE


# ============================================================================
# PYDANTIC REQUEST / RESPONSE MODELS
# ============================================================================

class BulkAppointmentItem(BaseModel):
    """A single appointment to create in a bulk request."""
    appointment_type_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    meeting_type: Optional[str] = "custom"
    meeting_mode: str = "video"
    scheduled_start: datetime
    duration_minutes: int = Field(DEFAULT_APPOINTMENT_DURATION_MINUTES, ge=MIN_APPOINTMENT_DURATION_MINUTES, le=MAX_APPOINTMENT_DURATION_MINUTES)
    timezone: str = "America/Chicago"

    attendee_name: Optional[str] = Field(None, min_length=1, max_length=200)
    attendee_email: Optional[EmailStr] = None
    attendee_phone: Optional[str] = Field(None, max_length=20)
    attendee_notes: Optional[str] = Field(None, max_length=2000)

    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    contact_id: Optional[int] = None
    assigned_user_id: Optional[int] = None

    intake_responses: Dict = {}
    booked_by_ai: bool = False
    ai_booking_context: Optional[Dict] = None


class BulkCreateRequest(BaseModel):
    """Request body for bulk appointment creation."""
    appointments: List[BulkAppointmentItem] = Field(
        ..., min_length=1, max_length=MAX_BULK_SIZE,
        description=f"Array of appointments to create (max {MAX_BULK_SIZE})"
    )
    send_notifications: bool = Field(True, description="Send confirmation emails for created appointments")


class BulkCancelItem(BaseModel):
    """A single appointment to cancel."""
    appointment_id: int


class BulkCancelRequest(BaseModel):
    """Request body for bulk cancellation."""
    appointment_ids: List[int] = Field(
        ..., min_length=1, max_length=MAX_BULK_SIZE,
        description=f"Array of appointment IDs to cancel (max {MAX_BULK_SIZE})"
    )
    reason: Optional[str] = Field(None, max_length=2000, description="Cancellation reason applied to all")
    send_notifications: bool = Field(True, description="Send cancellation emails")


class BulkRescheduleItem(BaseModel):
    """A single appointment to reschedule."""
    appointment_id: int
    new_scheduled_start: datetime
    new_duration_minutes: Optional[int] = Field(None, ge=MIN_APPOINTMENT_DURATION_MINUTES, le=MAX_APPOINTMENT_DURATION_MINUTES, description="New duration; if omitted, keeps original")


class BulkRescheduleRequest(BaseModel):
    """Request body for bulk rescheduling."""
    items: List[BulkRescheduleItem] = Field(
        ..., min_length=1, max_length=MAX_BULK_SIZE,
        description=f"Array of reschedule items (max {MAX_BULK_SIZE})"
    )
    send_notifications: bool = Field(True, description="Send update emails for rescheduled appointments")


class BulkAssignItem(BaseModel):
    """A single appointment to reassign."""
    appointment_id: int
    new_lo_id: int = Field(..., description="User ID of the new assigned loan officer")


class BulkAssignRequest(BaseModel):
    """Request body for bulk reassignment."""
    items: List[BulkAssignItem] = Field(
        ..., min_length=1, max_length=MAX_BULK_SIZE,
        description=f"Array of assignment items (max {MAX_BULK_SIZE})"
    )
    send_notifications: bool = Field(True, description="Send update emails to attendees and new LOs")


class BulkResultItem(BaseModel):
    """Result for a single item in a bulk operation."""
    index: int = Field(..., description="Zero-based index in the input array")
    success: bool
    appointment_id: Optional[int] = None
    error: Optional[str] = None


class BulkOperationResponse(BaseModel):
    """Standardized response for all bulk operations."""
    total: int = Field(..., description="Total items submitted")
    succeeded: int = Field(..., description="Number of items that succeeded")
    failed: int = Field(..., description="Number of items that failed")
    results: List[BulkResultItem] = Field(default_factory=list)


# ============================================================================
# BULK CREATE
# ============================================================================

@router.post("/appointments/bulk-create", response_model=BulkOperationResponse)
async def bulk_create_appointments(
    payload: BulkCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Create multiple appointments in a single transaction.

    Each appointment is created inside its own savepoint. If one fails (e.g.
    conflict, validation error), the others still commit. Returns per-item
    success/failure details.

    Requires admin role or will only allow creation assigned to self.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    is_admin = _is_scheduler_admin(user)

    _models = get_models()
    Appointment = _models['Appointment']

    results: List[BulkResultItem] = []
    succeeded = 0
    created_appointments = []  # For post-commit notifications

    for idx, item in enumerate(payload.appointments):
        savepoint = db.begin_nested()
        try:
            # Non-admins can only create appointments assigned to themselves
            assigned_user = item.assigned_user_id or user.id
            if not is_admin and assigned_user != user.id:
                raise ValueError(
                    f"Non-admin users can only create appointments assigned to themselves"
                )

            # Calculate end time
            scheduled_end = item.scheduled_start + timedelta(minutes=item.duration_minutes)

            # Conflict and duplicate checks
            _check_appointment_conflict(
                db, assigned_user, item.scheduled_start, scheduled_end, org_id=org_id
            )
            _check_duplicate_booking(
                db, item.attendee_email, assigned_user, item.scheduled_start, org_id=org_id
            )

            # Parse enums
            meeting_type = MeetingType.CUSTOM
            if item.meeting_type:
                try:
                    meeting_type = MeetingType(item.meeting_type)
                except ValueError:
                    pass

            meeting_mode = MeetingMode.VIDEO
            if item.meeting_mode:
                try:
                    meeting_mode = MeetingMode(item.meeting_mode)
                except ValueError:
                    pass

            appointment = Appointment(
                organization_id=org_id,
                appointment_type_id=item.appointment_type_id,
                assigned_user_id=assigned_user,
                created_by_user_id=user.id,
                lead_id=item.lead_id,
                loan_id=item.loan_id,
                contact_id=item.contact_id,
                title=item.title,
                description=item.description,
                meeting_type=meeting_type,
                meeting_mode=meeting_mode,
                scheduled_start=item.scheduled_start,
                scheduled_end=scheduled_end,
                duration_minutes=item.duration_minutes,
                timezone=item.timezone,
                attendee_name=item.attendee_name,
                attendee_email=item.attendee_email,
                attendee_phone=item.attendee_phone,
                attendee_notes=item.attendee_notes,
                intake_responses=item.intake_responses,
                status=AppointmentStatus.BOOKED,
                status_changed_at=datetime.now(timezone.utc),
                booked_by_ai=item.booked_by_ai,
                ai_booking_context=item.ai_booking_context,
            )

            db.add(appointment)
            db.flush()  # Get appointment.id

            # CRM: Link or create lead
            if not appointment.lead_id and item.attendee_email:
                lead_id = _ensure_lead_for_booking(
                    db, item.attendee_email, item.attendee_name,
                    item.attendee_phone, assigned_user, org_id
                )
                if lead_id:
                    appointment.lead_id = lead_id

            # CRM: Log activity
            _log_appointment_activity(
                db, org_id, user.id, appointment.lead_id, appointment.loan_id,
                f"Appointment scheduled (bulk): {appointment.title} on "
                f"{appointment.scheduled_start.strftime('%m/%d/%Y %I:%M %p') if appointment.scheduled_start else 'TBD'}"
            )

            # CRM: Create follow-up task
            if appointment.scheduled_end:
                _create_followup_task(
                    db, org_id, assigned_user,
                    appointment.lead_id, appointment.loan_id,
                    title=f"Follow up after: {appointment.title}"[:255],
                    description=(
                        f"Follow up with {item.attendee_name or 'attendee'} after "
                        f"meeting on {appointment.scheduled_start.strftime('%m/%d/%Y') if appointment.scheduled_start else 'TBD'}"
                    ),
                    due_date=appointment.scheduled_end + timedelta(days=1),
                )

            # Audit
            _audit_log(db, org_id, user.id, 'bulk_created', 'appointment',
                       entity_id=appointment.id, changes={
                           'title': item.title,
                           'attendee_email': item.attendee_email,
                           'scheduled_start': item.scheduled_start.isoformat(),
                       }, request=request)

            savepoint.commit()
            succeeded += 1
            results.append(BulkResultItem(
                index=idx, success=True, appointment_id=appointment.id
            ))
            created_appointments.append({
                'appointment': appointment,
                'item': item,
            })

        except HTTPException as exc:
            savepoint.rollback()
            results.append(BulkResultItem(
                index=idx, success=False, error=exc.detail
            ))
        except Exception as exc:
            savepoint.rollback()
            logger.warning(f"Bulk create item {idx} failed: {exc}")
            results.append(BulkResultItem(
                index=idx, success=False, error=str(exc)
            ))

    # Commit all successful savepoints
    db.commit()

    logger.info(
        f"Bulk create: {succeeded}/{len(payload.appointments)} succeeded "
        f"by user {user.id} in org {org_id}"
    )

    # Post-commit: send confirmation emails (best-effort, non-blocking)
    if payload.send_notifications:
        for entry in created_appointments:
            try:
                appt = entry['appointment']
                item = entry['item']
                db.refresh(appt)  # Ensure we have committed state
                if item.attendee_email:
                    _send_create_notification(db, _models, appt, item, org_id)
            except Exception as e:
                logger.warning(f"Bulk create notification failed for appointment {entry.get('appointment', {})}: {e}")

    return BulkOperationResponse(
        total=len(payload.appointments),
        succeeded=succeeded,
        failed=len(payload.appointments) - succeeded,
        results=results,
    )


# ============================================================================
# BULK CANCEL
# ============================================================================

@router.post("/appointments/bulk-cancel", response_model=BulkOperationResponse)
async def bulk_cancel_appointments(
    payload: BulkCancelRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Cancel multiple appointments in a single transaction.

    Each cancellation uses its own savepoint. Partial failures still commit
    the successful cancellations. Sends cancellation notifications by default.

    Non-admins can only cancel appointments they own or are assigned to.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    is_admin = _is_scheduler_admin(user)

    _models = get_models()
    Appointment = _models['Appointment']
    User = _models['User']

    results: List[BulkResultItem] = []
    succeeded = 0
    cancelled_details = []  # For post-commit notifications

    # Deduplicate IDs while preserving order
    seen_ids = set()
    unique_ids = []
    for aid in payload.appointment_ids:
        if aid not in seen_ids:
            seen_ids.add(aid)
            unique_ids.append(aid)

    for idx, appointment_id in enumerate(unique_ids):
        savepoint = db.begin_nested()
        try:
            # Fetch with tenant isolation
            filters = [
                Appointment.id == appointment_id,
                Appointment.organization_id == org_id,
            ]
            if not is_admin:
                filters.append(or_(
                    Appointment.assigned_user_id == user.id,
                    Appointment.created_by_user_id == user.id,
                ))

            appointment = db.query(Appointment).filter(and_(*filters)).first()

            if not appointment:
                raise ValueError(f"Appointment {appointment_id} not found or access denied")

            if appointment.status == AppointmentStatus.CANCELLED:
                raise ValueError(f"Appointment {appointment_id} is already cancelled")

            # Store details before cancellation for notifications
            cancel_info = {
                'appointment_id': appointment.id,
                'attendee_email': appointment.attendee_email,
                'attendee_name': appointment.attendee_name or 'Valued Client',
                'title': appointment.title or 'Appointment',
                'assigned_user_id': appointment.assigned_user_id,
                'lead_id': appointment.lead_id,
                'loan_id': appointment.loan_id,
                'scheduled_start': appointment.scheduled_start,
            }

            # Cancel the appointment
            appointment.status = AppointmentStatus.CANCELLED
            appointment.cancelled_at = datetime.now(timezone.utc)
            appointment.cancellation_reason = payload.reason
            appointment.status_changed_by = user.id
            appointment.status_changed_at = datetime.now(timezone.utc)

            # Audit
            _audit_log(db, org_id, user.id, 'bulk_cancelled', 'appointment',
                       entity_id=appointment_id,
                       changes={'reason': payload.reason},
                       request=request)

            # CRM: Log cancellation activity
            _log_appointment_activity(
                db, org_id, user.id, appointment.lead_id, appointment.loan_id,
                f"Appointment cancelled (bulk): {appointment.title} - Reason: {payload.reason or 'None given'}",
                activity_type="Note"
            )

            # CRM: Create re-engagement task
            _create_followup_task(
                db, org_id, appointment.assigned_user_id or user.id,
                appointment.lead_id, appointment.loan_id,
                title=f"Re-engage: {appointment.attendee_name or 'cancelled booking'}"[:255],
                description=(
                    f"Appointment '{appointment.title}' was cancelled (bulk). "
                    f"Reason: {payload.reason or 'None given'}. Attempt to re-engage."
                ),
                due_date=datetime.now(timezone.utc) + timedelta(days=1),
                priority="high",
            )

            savepoint.commit()
            succeeded += 1
            results.append(BulkResultItem(
                index=idx, success=True, appointment_id=appointment_id
            ))
            cancelled_details.append(cancel_info)

        except HTTPException as exc:
            savepoint.rollback()
            results.append(BulkResultItem(
                index=idx, success=False, appointment_id=appointment_id, error=exc.detail
            ))
        except Exception as exc:
            savepoint.rollback()
            logger.warning(f"Bulk cancel item {idx} (appt {appointment_id}) failed: {exc}")
            results.append(BulkResultItem(
                index=idx, success=False, appointment_id=appointment_id, error=str(exc)
            ))

    # Commit all successful savepoints
    db.commit()

    logger.info(
        f"Bulk cancel: {succeeded}/{len(unique_ids)} succeeded "
        f"by user {user.id} in org {org_id}"
    )

    # Post-commit: send cancellation notifications (best-effort)
    if payload.send_notifications:
        User = _models['User']
        for info in cancelled_details:
            try:
                _send_cancel_notification(db, User, info, payload.reason, org_id, user)
            except Exception as e:
                logger.warning(
                    f"Bulk cancel notification failed for appointment {info['appointment_id']}: {e}"
                )

    return BulkOperationResponse(
        total=len(unique_ids),
        succeeded=succeeded,
        failed=len(unique_ids) - succeeded,
        results=results,
    )


# ============================================================================
# BULK RESCHEDULE
# ============================================================================

@router.post("/appointments/bulk-reschedule", response_model=BulkOperationResponse)
async def bulk_reschedule_appointments(
    payload: BulkRescheduleRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Reschedule multiple appointments in a single transaction.

    Validates conflict-free scheduling for each item. Each reschedule uses its
    own savepoint, so a conflict on one does not block the others.

    Non-admins can only reschedule appointments they own or are assigned to.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    is_admin = _is_scheduler_admin(user)

    _models = get_models()
    Appointment = _models['Appointment']

    results: List[BulkResultItem] = []
    succeeded = 0
    rescheduled_details = []  # For post-commit notifications

    for idx, item in enumerate(payload.items):
        savepoint = db.begin_nested()
        try:
            # Fetch with tenant isolation
            filters = [
                Appointment.id == item.appointment_id,
                Appointment.organization_id == org_id,
            ]
            if not is_admin:
                filters.append(or_(
                    Appointment.assigned_user_id == user.id,
                    Appointment.created_by_user_id == user.id,
                ))

            appointment = db.query(Appointment).filter(and_(*filters)).first()

            if not appointment:
                raise ValueError(f"Appointment {item.appointment_id} not found or access denied")

            if appointment.status == AppointmentStatus.CANCELLED:
                raise ValueError(f"Appointment {item.appointment_id} is cancelled and cannot be rescheduled")

            # Calculate new end time
            duration = item.new_duration_minutes or appointment.duration_minutes or DEFAULT_APPOINTMENT_DURATION_MINUTES
            new_end = item.new_scheduled_start + timedelta(minutes=duration)

            # Conflict check (exclude self)
            _check_appointment_conflict(
                db,
                appointment.assigned_user_id,
                item.new_scheduled_start,
                new_end,
                org_id=org_id,
                exclude_appointment_id=appointment.id,
            )

            # Store old values for notification
            old_start = appointment.scheduled_start
            old_end = appointment.scheduled_end

            # Apply reschedule
            appointment.scheduled_start = item.new_scheduled_start
            appointment.scheduled_end = new_end
            if item.new_duration_minutes is not None:
                appointment.duration_minutes = item.new_duration_minutes
            appointment.reschedule_count = (appointment.reschedule_count or 0) + 1
            appointment.status_changed_at = datetime.now(timezone.utc)
            appointment.status_changed_by = user.id

            # Audit
            _audit_log(db, org_id, user.id, 'bulk_rescheduled', 'appointment',
                       entity_id=appointment.id, changes={
                           'old_start': old_start.isoformat() if old_start else None,
                           'new_start': item.new_scheduled_start.isoformat(),
                           'old_end': old_end.isoformat() if old_end else None,
                           'new_end': new_end.isoformat(),
                       }, request=request)

            # CRM: Log activity
            _log_appointment_activity(
                db, org_id, user.id, appointment.lead_id, appointment.loan_id,
                f"Appointment rescheduled (bulk): {appointment.title} from "
                f"{old_start.strftime('%m/%d/%Y %I:%M %p') if old_start else 'TBD'} to "
                f"{item.new_scheduled_start.strftime('%m/%d/%Y %I:%M %p')}"
            )

            savepoint.commit()
            succeeded += 1
            results.append(BulkResultItem(
                index=idx, success=True, appointment_id=appointment.id
            ))
            rescheduled_details.append({
                'appointment_id': appointment.id,
                'attendee_email': appointment.attendee_email,
                'attendee_name': appointment.attendee_name or 'Valued Client',
                'attendee_phone': getattr(appointment, 'attendee_phone', None),
                'title': appointment.title or 'Appointment',
                'assigned_user_id': appointment.assigned_user_id,
                'new_start': item.new_scheduled_start,
                'new_end': new_end,
                'duration_minutes': duration,
                'old_start': old_start,
                'meeting_mode': appointment.meeting_mode,
                'video_link': getattr(appointment, 'video_link', None),
            })

        except HTTPException as exc:
            savepoint.rollback()
            results.append(BulkResultItem(
                index=idx, success=False, appointment_id=item.appointment_id, error=exc.detail
            ))
        except Exception as exc:
            savepoint.rollback()
            logger.warning(f"Bulk reschedule item {idx} (appt {item.appointment_id}) failed: {exc}")
            results.append(BulkResultItem(
                index=idx, success=False, appointment_id=item.appointment_id, error=str(exc)
            ))

    # Commit all successful savepoints
    db.commit()

    logger.info(
        f"Bulk reschedule: {succeeded}/{len(payload.items)} succeeded "
        f"by user {user.id} in org {org_id}"
    )

    # Post-commit: send update notifications (best-effort)
    if payload.send_notifications:
        User = _models['User']
        for info in rescheduled_details:
            try:
                _send_reschedule_notification(db, User, info, org_id)
            except Exception as e:
                logger.warning(
                    f"Bulk reschedule notification failed for appointment {info['appointment_id']}: {e}"
                )

    return BulkOperationResponse(
        total=len(payload.items),
        succeeded=succeeded,
        failed=len(payload.items) - succeeded,
        results=results,
    )


# ============================================================================
# BULK ASSIGN
# ============================================================================

@router.post("/appointments/bulk-assign", response_model=BulkOperationResponse)
async def bulk_assign_appointments(
    payload: BulkAssignRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Reassign multiple appointments to different loan officers.

    Useful for LO departure, vacation coverage, or team rebalancing.
    Validates that the new LO exists in the same organization and has no
    scheduling conflict for each appointment's time slot.

    Requires admin role.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    if not _is_scheduler_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Bulk assignment requires admin privileges"
        )

    _models = get_models()
    Appointment = _models['Appointment']
    User = _models['User']

    # Pre-validate all target LOs exist in this org (single query)
    target_lo_ids = list({item.new_lo_id for item in payload.items})
    valid_los = db.query(User).filter(
        User.id.in_(target_lo_ids),
        User.organization_id == org_id,
    ).all()
    valid_lo_map = {lo.id: lo for lo in valid_los}

    results: List[BulkResultItem] = []
    succeeded = 0
    assigned_details = []  # For post-commit notifications

    for idx, item in enumerate(payload.items):
        savepoint = db.begin_nested()
        try:
            # Validate target LO
            new_lo = valid_lo_map.get(item.new_lo_id)
            if not new_lo:
                raise ValueError(
                    f"User {item.new_lo_id} not found in this organization"
                )

            # Fetch appointment with tenant isolation
            appointment = db.query(Appointment).filter(
                Appointment.id == item.appointment_id,
                Appointment.organization_id == org_id,
            ).first()

            if not appointment:
                raise ValueError(f"Appointment {item.appointment_id} not found")

            if appointment.status == AppointmentStatus.CANCELLED:
                raise ValueError(f"Appointment {item.appointment_id} is cancelled")

            # Skip if already assigned to the target
            if appointment.assigned_user_id == item.new_lo_id:
                # Treat as success (idempotent)
                savepoint.commit()
                succeeded += 1
                results.append(BulkResultItem(
                    index=idx, success=True, appointment_id=appointment.id
                ))
                continue

            # Check new LO has no conflict at this time
            if appointment.scheduled_start and appointment.scheduled_end:
                _check_appointment_conflict(
                    db,
                    item.new_lo_id,
                    appointment.scheduled_start,
                    appointment.scheduled_end,
                    org_id=org_id,
                    exclude_appointment_id=appointment.id,
                )

            old_lo_id = appointment.assigned_user_id
            appointment.assigned_user_id = item.new_lo_id

            # Audit
            _audit_log(db, org_id, user.id, 'bulk_reassigned', 'appointment',
                       entity_id=appointment.id, changes={
                           'old_assigned_user_id': old_lo_id,
                           'new_assigned_user_id': item.new_lo_id,
                       }, request=request)

            # CRM: Log activity
            new_lo_name = f"{new_lo.first_name or ''} {new_lo.last_name or ''}".strip() or str(new_lo.id)
            _log_appointment_activity(
                db, org_id, user.id, appointment.lead_id, appointment.loan_id,
                f"Appointment reassigned (bulk): {appointment.title} to {new_lo_name}"
            )

            savepoint.commit()
            succeeded += 1
            results.append(BulkResultItem(
                index=idx, success=True, appointment_id=appointment.id
            ))
            assigned_details.append({
                'appointment_id': appointment.id,
                'attendee_email': appointment.attendee_email,
                'attendee_name': appointment.attendee_name or 'Valued Client',
                'title': appointment.title or 'Appointment',
                'old_lo_id': old_lo_id,
                'new_lo_id': item.new_lo_id,
                'new_lo_name': new_lo_name,
                'new_lo_email': new_lo.email,
                'scheduled_start': appointment.scheduled_start,
                'scheduled_end': appointment.scheduled_end,
                'duration_minutes': appointment.duration_minutes,
                'meeting_mode': appointment.meeting_mode,
                'video_link': getattr(appointment, 'video_link', None),
            })

        except HTTPException as exc:
            savepoint.rollback()
            results.append(BulkResultItem(
                index=idx, success=False, appointment_id=item.appointment_id, error=exc.detail
            ))
        except Exception as exc:
            savepoint.rollback()
            logger.warning(f"Bulk assign item {idx} (appt {item.appointment_id}) failed: {exc}")
            results.append(BulkResultItem(
                index=idx, success=False, appointment_id=item.appointment_id, error=str(exc)
            ))

    # Commit all successful savepoints
    db.commit()

    logger.info(
        f"Bulk assign: {succeeded}/{len(payload.items)} succeeded "
        f"by user {user.id} in org {org_id}"
    )

    # Post-commit: send reassignment notifications (best-effort)
    if payload.send_notifications:
        for info in assigned_details:
            try:
                _send_assign_notification(db, User, info, org_id)
            except Exception as e:
                logger.warning(
                    f"Bulk assign notification failed for appointment {info['appointment_id']}: {e}"
                )

    return BulkOperationResponse(
        total=len(payload.items),
        succeeded=succeeded,
        failed=len(payload.items) - succeeded,
        results=results,
    )


# ============================================================================
# NOTIFICATION HELPERS (best-effort, post-commit)
# ============================================================================

def _send_create_notification(db, _models, appointment, item, org_id):
    """Send confirmation email for a newly created appointment (best-effort)."""
    local_start = _convert_utc_to_user_tz(
        appointment.scheduled_start, appointment.assigned_user_id, db, org_id=org_id
    )
    appointment_date = local_start.strftime("%A, %B %d, %Y")
    appointment_time = local_start.strftime("%I:%M %p %Z")
    duration_str = f"{appointment.duration_minutes} minutes"

    meeting_mode_str = "Phone Call"
    if appointment.meeting_mode:
        mode_display = {
            "video": "Video Call", "phone": "Phone Call",
            "in_person": "In Person", "screen_share": "Screen Share",
        }
        raw_mode = appointment.meeting_mode.value if hasattr(appointment.meeting_mode, 'value') else str(appointment.meeting_mode)
        meeting_mode_str = mode_display.get(raw_mode.lower(), "Phone Call")

    # Get team member info
    team_member_name = None
    team_member_email = None
    User = _models.get('User')
    if appointment.assigned_user_id and User:
        assigned_user_obj = db.query(User).filter(User.id == appointment.assigned_user_id).first()
        if assigned_user_obj:
            team_member_name = assigned_user_obj.first_name
            if assigned_user_obj.last_name:
                team_member_name += f" {assigned_user_obj.last_name}"
            team_member_email = assigned_user_obj.email

    video_link = appointment.video_link if appointment.video_link else None
    reschedule_url = generate_reschedule_url(appointment.id, item.attendee_email)

    send_appointment_confirmation_email(
        attendee_email=item.attendee_email,
        attendee_name=item.attendee_name or "there",
        appointment_title=appointment.title,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        duration=duration_str,
        meeting_mode=meeting_mode_str,
        team_member_name=team_member_name,
        team_member_email=team_member_email,
        video_link=video_link,
        scheduled_start=appointment.scheduled_start,
        duration_minutes=appointment.duration_minutes,
        reschedule_url=reschedule_url,
    )


def _send_cancel_notification(db, UserModel, info, reason, org_id, user):
    """Send cancellation emails for a cancelled appointment (best-effort)."""
    if info['scheduled_start']:
        local_start = _convert_utc_to_user_tz(
            info['scheduled_start'], info['assigned_user_id'], db, org_id=org_id
        )
        appointment_date = local_start.strftime('%B %d, %Y')
        appointment_time = local_start.strftime('%I:%M %p %Z')
    else:
        appointment_date = 'TBD'
        appointment_time = 'TBD'

    # Get team member info
    team_member_name = None
    team_member_email = None
    if info['assigned_user_id']:
        team_member = db.query(UserModel).filter(UserModel.id == info['assigned_user_id']).first()
        if team_member:
            team_member_name = getattr(team_member, 'full_name', None) or team_member.email
            team_member_email = team_member.email

    # Notify attendee
    if info['attendee_email']:
        send_appointment_cancellation_email(
            attendee_email=info['attendee_email'],
            attendee_name=info['attendee_name'],
            appointment_title=info['title'],
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            team_member_name=team_member_name,
            cancellation_reason=reason,
        )

    # Notify team member (if different from canceller)
    if team_member_email and info['assigned_user_id'] != user.id:
        send_team_member_cancellation_email(
            team_member_email=team_member_email,
            team_member_name=team_member_name,
            attendee_name=info['attendee_name'],
            appointment_title=info['title'],
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            cancellation_reason=reason,
            cancelled_by=getattr(user, 'full_name', None) or user.email,
        )


def _send_reschedule_notification(db, UserModel, info, org_id):
    """Send update emails for a rescheduled appointment (best-effort)."""
    # Format new date/time
    new_local = _convert_utc_to_user_tz(
        info['new_start'], info['assigned_user_id'], db, org_id=org_id
    )
    new_date = new_local.strftime('%B %d, %Y')
    new_time = new_local.strftime('%I:%M %p %Z')

    # Format old date/time
    old_date = None
    old_time = None
    if info['old_start']:
        old_local = _convert_utc_to_user_tz(
            info['old_start'], info['assigned_user_id'], db, org_id=org_id
        )
        old_date = old_local.strftime('%B %d, %Y')
        old_time = old_local.strftime('%I:%M %p %Z')

    duration_minutes = info['duration_minutes'] or DEFAULT_APPOINTMENT_DURATION_MINUTES
    duration_str = f"{duration_minutes} minutes"

    meeting_mode = "Phone Call"
    if info['meeting_mode']:
        mode_display = {
            "video": "Video Call", "phone": "Phone Call",
            "in_person": "In Person", "screen_share": "Screen Share",
        }
        raw_mode = info['meeting_mode'].value if hasattr(info['meeting_mode'], 'value') else str(info['meeting_mode'])
        meeting_mode = mode_display.get(raw_mode.lower(), "Phone Call")

    # Get team member info
    team_member_name = None
    team_member_email = None
    if info['assigned_user_id']:
        team_member = db.query(UserModel).filter(UserModel.id == info['assigned_user_id']).first()
        if team_member:
            team_member_name = getattr(team_member, 'full_name', None) or team_member.email
            team_member_email = team_member.email

    # Notify attendee
    if info['attendee_email']:
        send_appointment_update_email(
            attendee_email=info['attendee_email'],
            attendee_name=info['attendee_name'],
            appointment_title=info['title'],
            appointment_date=new_date,
            appointment_time=new_time,
            duration=duration_str,
            meeting_mode=meeting_mode,
            team_member_name=team_member_name,
            team_member_email=team_member_email,
            video_link=info.get('video_link'),
            scheduled_start=info['new_start'],
            duration_minutes=duration_minutes,
            old_date=old_date,
            old_time=old_time,
        )


def _send_assign_notification(db, UserModel, info, org_id):
    """Send notification emails when an appointment is reassigned (best-effort)."""
    # Format date/time
    appointment_date = 'TBD'
    appointment_time = 'TBD'
    if info['scheduled_start']:
        local_start = _convert_utc_to_user_tz(
            info['scheduled_start'], info['new_lo_id'], db, org_id=org_id
        )
        appointment_date = local_start.strftime('%B %d, %Y')
        appointment_time = local_start.strftime('%I:%M %p %Z')

    duration_minutes = info['duration_minutes'] or DEFAULT_APPOINTMENT_DURATION_MINUTES
    duration_str = f"{duration_minutes} minutes"

    meeting_mode_str = "Phone Call"
    if info['meeting_mode']:
        mode_display = {
            "video": "Video Call", "phone": "Phone Call",
            "in_person": "In Person", "screen_share": "Screen Share",
        }
        raw_mode = info['meeting_mode'].value if hasattr(info['meeting_mode'], 'value') else str(info['meeting_mode'])
        meeting_mode_str = mode_display.get(raw_mode.lower(), "Phone Call")

    # Notify the new LO that they have been assigned
    if info.get('new_lo_email'):
        try:
            send_team_member_notification_email(
                team_member_email=info['new_lo_email'],
                team_member_name=info['new_lo_name'],
                attendee_name=info['attendee_name'],
                attendee_email=info.get('attendee_email') or '',
                attendee_phone='',
                appointment_title=info['title'],
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration=duration_str,
                meeting_mode=meeting_mode_str,
                video_link=info.get('video_link'),
                scheduled_start=info['scheduled_start'],
                duration_minutes=duration_minutes,
            )
        except Exception as e:
            logger.warning(f"Failed to notify new LO for appointment {info['appointment_id']}: {e}")

    # Notify attendee about the LO change
    if info.get('attendee_email'):
        try:
            send_appointment_update_email(
                attendee_email=info['attendee_email'],
                attendee_name=info['attendee_name'],
                appointment_title=info['title'],
                appointment_date=appointment_date,
                appointment_time=appointment_time,
                duration=duration_str,
                meeting_mode=meeting_mode_str,
                team_member_name=info['new_lo_name'],
                team_member_email=info.get('new_lo_email'),
                video_link=info.get('video_link'),
                scheduled_start=info['scheduled_start'],
                duration_minutes=duration_minutes,
            )
        except Exception as e:
            logger.warning(f"Failed to notify attendee for reassigned appointment {info['appointment_id']}: {e}")
