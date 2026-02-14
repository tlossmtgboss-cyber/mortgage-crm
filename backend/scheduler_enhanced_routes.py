"""
Enhanced Scheduler API Routes - Advanced Features

Provides endpoints for:
- Resource Management (CRUD, status, capacity)
- Soft Hold Management (create, release, convert)
- SLA & Load Balancing
- Reminder System
- No-Show Detection & Recovery
- Analytics & Reporting
- Group Sessions
- Series Scheduling
- Campaign Tracking
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
import logging

from scheduler_enhancements import (
    ResourceType, ResourceStatus, SchedulingMode, SoftHoldStatus,
    ReminderType, BookingChannel, DEFAULT_REMINDER_PROFILES,
    ResourceCreate, ResourceUpdate, SoftHoldCreate, GroupSessionCreate,
    CampaignBookingCreate, AnalyticsQuery,
    calculate_show_rate, calculate_no_show_rate, get_optimal_slot_score,
    parse_natural_language_time, generate_ics_content
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler", tags=["Smart Scheduler Enhanced"])

# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

_get_db = None
_get_current_user = None
_models = None
_enhanced_models = None


def set_enhanced_dependencies(get_db_func, get_current_user_func, models_dict, enhanced_models_dict):
    """Set dependencies from main.py"""
    global _get_db, _get_current_user, _models, _enhanced_models
    _get_db = get_db_func
    _get_current_user = get_current_user_func
    _models = models_dict
    _enhanced_models = enhanced_models_dict


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user is None:
        raise RuntimeError("Dependencies not set")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# ============================================================================
# RESOURCE MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/resources")
async def list_resources(
    request: Request,
    resource_type: Optional[str] = None,
    status: Optional[str] = None,
    skill: Optional[str] = None,
    language: Optional[str] = None,
    licensed_state: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all scheduling resources with filters"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SchedulerResource = _enhanced_models['SchedulerResource']

    query = db.query(SchedulerResource)

    # Apply filters
    if resource_type:
        try:
            rt = ResourceType(resource_type)
            query = query.filter(SchedulerResource.resource_type == rt)
        except ValueError:
            pass

    if status:
        try:
            st = ResourceStatus(status)
            query = query.filter(SchedulerResource.status == st)
        except ValueError:
            pass

    if skill:
        query = query.filter(SchedulerResource.skills.contains([skill]))

    if language:
        query = query.filter(SchedulerResource.languages.contains([language]))

    if licensed_state:
        query = query.filter(SchedulerResource.licensed_states.contains([licensed_state]))

    resources = query.all()

    return {
        "resources": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "resource_type": r.resource_type.value if r.resource_type else None,
                "display_name": r.display_name,
                "title": r.title,
                "status": r.status.value if r.status else None,
                "skills": r.skills,
                "languages": r.languages,
                "licensed_states": r.licensed_states,
                "max_daily_appointments": r.max_daily_appointments,
                "current_daily_load": r.current_daily_load,
                "total_appointments": r.total_appointments,
                "show_rate": calculate_show_rate(r.completed_appointments, r.total_appointments),
                "conversion_rate": r.conversion_rate,
                "routing_weight": r.routing_weight
            }
            for r in resources
        ],
        "total": len(resources)
    }


@router.post("/resources")
async def create_resource(
    resource_data: ResourceCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a new scheduling resource"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SchedulerResource = _enhanced_models['SchedulerResource']

    # Check if resource already exists for this user
    existing = db.query(SchedulerResource).filter(
        SchedulerResource.user_id == resource_data.user_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Resource already exists for this user")

    # Parse resource type
    resource_type = ResourceType.LOAN_OFFICER
    try:
        resource_type = ResourceType(resource_data.resource_type)
    except ValueError:
        pass

    resource = SchedulerResource(
        user_id=resource_data.user_id,
        resource_type=resource_type,
        display_name=resource_data.display_name,
        title=resource_data.title,
        direct_phone=resource_data.direct_phone,
        skills=resource_data.skills,
        product_expertise=resource_data.product_expertise,
        languages=resource_data.languages,
        licensed_states=resource_data.licensed_states,
        nmls_id=resource_data.nmls_id,
        max_daily_appointments=resource_data.max_daily_appointments,
        max_weekly_appointments=resource_data.max_weekly_appointments
    )

    db.add(resource)
    db.commit()
    db.refresh(resource)

    logger.info(f"Created scheduler resource {resource.id} for user {resource_data.user_id}")

    return {"message": "Resource created", "resource_id": resource.id}


@router.get("/resources/{resource_id}")
async def get_resource(
    resource_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get resource details"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SchedulerResource = _enhanced_models['SchedulerResource']

    resource = db.query(SchedulerResource).filter(
        SchedulerResource.id == resource_id
    ).first()

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    return {
        "resource": {
            "id": resource.id,
            "user_id": resource.user_id,
            "resource_type": resource.resource_type.value if resource.resource_type else None,
            "display_name": resource.display_name,
            "title": resource.title,
            "bio": resource.bio,
            "photo_url": resource.photo_url,
            "direct_phone": resource.direct_phone,
            "backup_phone": resource.backup_phone,
            "calendar_email": resource.calendar_email,
            "skills": resource.skills,
            "product_expertise": resource.product_expertise,
            "certifications": resource.certifications,
            "languages": resource.languages,
            "primary_language": resource.primary_language,
            "licensed_states": resource.licensed_states,
            "nmls_id": resource.nmls_id,
            "max_daily_appointments": resource.max_daily_appointments,
            "max_weekly_appointments": resource.max_weekly_appointments,
            "current_daily_load": resource.current_daily_load,
            "current_weekly_load": resource.current_weekly_load,
            "sla_target_hours": resource.sla_target_hours,
            "status": resource.status.value if resource.status else None,
            "status_reason": resource.status_reason,
            "status_until": resource.status_until.isoformat() if resource.status_until else None,
            "total_appointments": resource.total_appointments,
            "completed_appointments": resource.completed_appointments,
            "no_show_count": resource.no_show_count,
            "cancellation_count": resource.cancellation_count,
            "show_rate": calculate_show_rate(resource.completed_appointments, resource.total_appointments),
            "no_show_rate": calculate_no_show_rate(resource.no_show_count, resource.total_appointments),
            "avg_rating": resource.avg_rating,
            "conversion_rate": resource.conversion_rate,
            "routing_weight": resource.routing_weight,
            "accept_new_leads": resource.accept_new_leads,
            "accept_existing_clients": resource.accept_existing_clients,
            "accept_partner_referrals": resource.accept_partner_referrals
        }
    }


@router.put("/resources/{resource_id}")
async def update_resource(
    resource_id: int,
    resource_data: ResourceUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Update a resource"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SchedulerResource = _enhanced_models['SchedulerResource']

    resource = db.query(SchedulerResource).filter(
        SchedulerResource.id == resource_id
    ).first()

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    update_fields = resource_data.dict(exclude_unset=True)

    # Handle status enum
    if "status" in update_fields:
        try:
            update_fields["status"] = ResourceStatus(update_fields["status"])
        except ValueError:
            del update_fields["status"]

    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for field, value in update_fields.items():
        if field not in _protected:
            setattr(resource, field, value)

    db.commit()

    return {"message": "Resource updated"}


@router.put("/resources/{resource_id}/status")
async def update_resource_status(
    resource_id: int,
    status: str,
    reason: Optional[str] = None,
    until: Optional[datetime] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Update resource status (active, vacation, etc.)"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SchedulerResource = _enhanced_models['SchedulerResource']

    resource = db.query(SchedulerResource).filter(
        SchedulerResource.id == resource_id
    ).first()

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    try:
        resource.status = ResourceStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status")

    resource.status_reason = reason
    resource.status_until = until

    db.commit()

    return {"message": f"Resource status updated to {status}"}


# ============================================================================
# SOFT HOLD MANAGEMENT
# ============================================================================

@router.post("/soft-holds")
async def create_soft_hold(
    hold_data: SoftHoldCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Create a soft hold on a time slot during AI conversation.
    Prevents double-booking while AI works with a client.
    """
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SoftHold = _enhanced_models['SoftHold']

    # Check if slot is already held
    existing = db.query(SoftHold).filter(
        SoftHold.slot_start == hold_data.slot_start,
        SoftHold.status == SoftHoldStatus.ACTIVE,
        SoftHold.expires_at > datetime.utcnow()
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="Slot already has an active hold")

    # Calculate expiration
    expires_at = datetime.utcnow() + timedelta(minutes=hold_data.hold_duration_minutes)

    # Parse channel
    channel = BookingChannel.AI_VOICE
    try:
        channel = BookingChannel(hold_data.channel)
    except ValueError:
        pass

    hold = SoftHold(
        slot_start=hold_data.slot_start,
        slot_end=hold_data.slot_end,
        resource_id=hold_data.resource_id,
        hold_duration_minutes=hold_data.hold_duration_minutes,
        expires_at=expires_at,
        channel=channel,
        session_id=hold_data.session_id,
        contact_phone=hold_data.contact_phone,
        contact_email=hold_data.contact_email
    )

    db.add(hold)
    db.commit()
    db.refresh(hold)

    logger.info(f"Soft hold {hold.id} created for slot {hold_data.slot_start}")

    return {
        "message": "Soft hold created",
        "hold_id": hold.id,
        "expires_at": hold.expires_at.isoformat(),
        "slot_start": hold.slot_start.isoformat(),
        "slot_end": hold.slot_end.isoformat()
    }


@router.post("/soft-holds/{hold_id}/release")
async def release_soft_hold(
    hold_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Release a soft hold (slot becomes available again)"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SoftHold = _enhanced_models['SoftHold']

    hold = db.query(SoftHold).filter(SoftHold.id == hold_id).first()

    if not hold:
        raise HTTPException(status_code=404, detail="Soft hold not found")

    hold.status = SoftHoldStatus.RELEASED
    hold.released_at = datetime.utcnow()

    db.commit()

    logger.info(f"Soft hold {hold_id} released")

    return {"message": "Soft hold released"}


@router.post("/soft-holds/{hold_id}/convert")
async def convert_soft_hold(
    hold_id: int,
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Convert a soft hold to a confirmed appointment"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SoftHold = _enhanced_models['SoftHold']

    hold = db.query(SoftHold).filter(SoftHold.id == hold_id).first()

    if not hold:
        raise HTTPException(status_code=404, detail="Soft hold not found")

    hold.status = SoftHoldStatus.CONVERTED
    hold.converted_at = datetime.utcnow()
    hold.converted_to_appointment_id = appointment_id

    db.commit()

    logger.info(f"Soft hold {hold_id} converted to appointment {appointment_id}")

    return {"message": "Soft hold converted to appointment"}


@router.get("/soft-holds/active")
async def list_active_soft_holds(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all active soft holds"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SoftHold = _enhanced_models['SoftHold']

    now = datetime.utcnow()
    holds = db.query(SoftHold).filter(
        SoftHold.status == SoftHoldStatus.ACTIVE,
        SoftHold.expires_at > now
    ).all()

    return {
        "active_holds": [
            {
                "id": h.id,
                "slot_start": h.slot_start.isoformat(),
                "slot_end": h.slot_end.isoformat(),
                "resource_id": h.resource_id,
                "expires_at": h.expires_at.isoformat(),
                "channel": h.channel.value if h.channel else None,
                "session_id": h.session_id,
                "created_at": h.created_at.isoformat() if h.created_at else None
            }
            for h in holds
        ],
        "total": len(holds)
    }


@router.post("/soft-holds/cleanup")
async def cleanup_expired_holds(
    request: Request,
    db: Session = Depends(get_db)
):
    """Clean up expired soft holds (background job endpoint)"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SoftHold = _enhanced_models['SoftHold']

    now = datetime.utcnow()
    expired = db.query(SoftHold).filter(
        SoftHold.status == SoftHoldStatus.ACTIVE,
        SoftHold.expires_at <= now
    ).all()

    count = 0
    for hold in expired:
        hold.status = SoftHoldStatus.EXPIRED
        count += 1

    db.commit()

    logger.info(f"Cleaned up {count} expired soft holds")

    return {"message": f"Cleaned up {count} expired soft holds"}


# ============================================================================
# SLA & LOAD BALANCING
# ============================================================================

@router.get("/sla/dashboard")
async def get_sla_dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get SLA and load balancing dashboard"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SchedulerResource = _enhanced_models['SchedulerResource']

    resources = db.query(SchedulerResource).filter(
        SchedulerResource.status == ResourceStatus.ACTIVE
    ).all()

    resource_stats = []
    for r in resources:
        daily_utilization = (r.current_daily_load / r.max_daily_appointments * 100) if r.max_daily_appointments > 0 else 0
        weekly_utilization = (r.current_weekly_load / r.max_weekly_appointments * 100) if r.max_weekly_appointments > 0 else 0

        resource_stats.append({
            "resource_id": r.id,
            "display_name": r.display_name,
            "resource_type": r.resource_type.value if r.resource_type else None,
            "current_daily_load": r.current_daily_load,
            "max_daily_appointments": r.max_daily_appointments,
            "daily_utilization_pct": round(daily_utilization, 1),
            "current_weekly_load": r.current_weekly_load,
            "max_weekly_appointments": r.max_weekly_appointments,
            "weekly_utilization_pct": round(weekly_utilization, 1),
            "sla_target_hours": r.sla_target_hours,
            "show_rate": calculate_show_rate(r.completed_appointments, r.total_appointments),
            "no_show_rate": calculate_no_show_rate(r.no_show_count, r.total_appointments),
            "is_at_capacity": r.current_daily_load >= r.max_daily_appointments,
            "needs_attention": daily_utilization > 80 or r.no_show_count > 5
        })

    # Sort by utilization descending
    resource_stats.sort(key=lambda x: x['daily_utilization_pct'], reverse=True)

    # Calculate team totals
    total_capacity = sum(r.max_daily_appointments for r in resources)
    total_load = sum(r.current_daily_load for r in resources)
    team_utilization = (total_load / total_capacity * 100) if total_capacity > 0 else 0

    return {
        "team_summary": {
            "total_resources": len(resources),
            "total_daily_capacity": total_capacity,
            "current_daily_load": total_load,
            "team_utilization_pct": round(team_utilization, 1),
            "resources_at_capacity": len([r for r in resource_stats if r['is_at_capacity']]),
            "resources_need_attention": len([r for r in resource_stats if r['needs_attention']])
        },
        "resources": resource_stats
    }


@router.post("/sla/rebalance")
async def rebalance_load(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Suggest load rebalancing across resources.
    Returns recommendations for redistributing appointments.
    """
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    SchedulerResource = _enhanced_models['SchedulerResource']

    resources = db.query(SchedulerResource).filter(
        SchedulerResource.status == ResourceStatus.ACTIVE
    ).all()

    # Find overloaded and underloaded resources
    overloaded = []
    underloaded = []
    avg_load = sum(r.current_daily_load for r in resources) / len(resources) if resources else 0

    for r in resources:
        utilization = r.current_daily_load / r.max_daily_appointments if r.max_daily_appointments > 0 else 0
        if utilization > 0.8:
            overloaded.append({
                "resource_id": r.id,
                "display_name": r.display_name,
                "current_load": r.current_daily_load,
                "max_load": r.max_daily_appointments,
                "excess": r.current_daily_load - int(r.max_daily_appointments * 0.7)
            })
        elif utilization < 0.5:
            underloaded.append({
                "resource_id": r.id,
                "display_name": r.display_name,
                "current_load": r.current_daily_load,
                "max_load": r.max_daily_appointments,
                "capacity": int(r.max_daily_appointments * 0.7) - r.current_daily_load
            })

    recommendations = []
    for over in overloaded:
        for under in underloaded:
            if under['capacity'] > 0 and over['excess'] > 0:
                transfer_count = min(over['excess'], under['capacity'])
                recommendations.append({
                    "from_resource": over['display_name'],
                    "to_resource": under['display_name'],
                    "suggested_transfers": transfer_count,
                    "reason": f"Rebalance load: {over['display_name']} is at {over['current_load']}/{over['max_load']}"
                })
                over['excess'] -= transfer_count
                under['capacity'] -= transfer_count

    return {
        "analysis": {
            "average_load": round(avg_load, 1),
            "overloaded_count": len(overloaded),
            "underloaded_count": len(underloaded)
        },
        "recommendations": recommendations
    }


# ============================================================================
# NO-SHOW DETECTION & RECOVERY
# ============================================================================

@router.post("/no-show/detect")
async def detect_no_shows(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Detect no-shows for appointments that have passed.
    Marks appointments as no-show 15 minutes after scheduled end.
    """
    user = await get_current_user(request, db)

    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    from smart_scheduler_models import AppointmentStatus

    # Find appointments that ended > 15 minutes ago and are still "booked"
    cutoff = datetime.utcnow() - timedelta(minutes=15)

    no_show_candidates = db.query(Appointment).filter(
        Appointment.status == AppointmentStatus.BOOKED,
        Appointment.scheduled_end < cutoff
    ).all()

    marked_count = 0
    for appt in no_show_candidates:
        appt.status = AppointmentStatus.NO_SHOW
        appt.no_show_at = datetime.utcnow()
        marked_count += 1

        # Update resource metrics
        if _enhanced_models and appt.assigned_user_id:
            SchedulerResource = _enhanced_models['SchedulerResource']
            resource = db.query(SchedulerResource).filter(
                SchedulerResource.user_id == appt.assigned_user_id
            ).first()
            if resource:
                resource.no_show_count += 1

        logger.info(f"Marked appointment {appt.id} as no-show")

    db.commit()

    return {
        "message": f"Detected {marked_count} no-shows",
        "no_show_ids": [a.id for a in no_show_candidates]
    }


@router.post("/no-show/{appointment_id}/recover")
async def recover_no_show(
    appointment_id: int,
    send_reschedule_offer: bool = True,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Initiate no-show recovery workflow.
    Sends reschedule offer to the attendee.
    """
    user = await get_current_user(request, db)

    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    from smart_scheduler_models import AppointmentStatus

    appt = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.status == AppointmentStatus.NO_SHOW
    ).first()

    if not appt:
        raise HTTPException(status_code=404, detail="No-show appointment not found")

    recovery_actions = []

    if send_reschedule_offer and appt.attendee_email:
        recovery_actions.append({
            "action": "reschedule_email",
            "recipient": appt.attendee_email,
            "status": "queued"
        })

    if send_reschedule_offer and appt.attendee_phone:
        recovery_actions.append({
            "action": "reschedule_sms",
            "recipient": appt.attendee_phone,
            "status": "queued"
        })

    return {
        "message": "No-show recovery initiated",
        "appointment_id": appointment_id,
        "attendee_name": appt.attendee_name,
        "recovery_actions": recovery_actions
    }


# ============================================================================
# ANALYTICS & REPORTING
# ============================================================================

@router.get("/analytics/overview")
async def get_analytics_overview(
    start_date: date = Query(...),
    end_date: date = Query(...),
    resource_id: Optional[int] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get comprehensive analytics overview"""
    user = await get_current_user(request, db)

    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    from smart_scheduler_models import AppointmentStatus

    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    query = db.query(Appointment).filter(
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt
    )

    if resource_id:
        query = query.filter(Appointment.assigned_user_id == resource_id)

    appointments = query.all()

    # Calculate metrics
    total = len(appointments)
    completed = len([a for a in appointments if a.status == AppointmentStatus.COMPLETED])
    no_shows = len([a for a in appointments if a.status == AppointmentStatus.NO_SHOW])
    cancelled = len([a for a in appointments if a.status == AppointmentStatus.CANCELLED])
    rescheduled = len([a for a in appointments if a.status == AppointmentStatus.RESCHEDULED])

    # Channel breakdown
    channel_breakdown = {}
    for appt in appointments:
        source = appt.external_source or "crm_manual"
        channel_breakdown[source] = channel_breakdown.get(source, 0) + 1

    # Time slot breakdown
    time_slots = {}
    for appt in appointments:
        hour = appt.scheduled_start.strftime("%H:00")
        time_slots[hour] = time_slots.get(hour, 0) + 1

    # Day breakdown
    day_breakdown = {}
    for appt in appointments:
        day = appt.scheduled_start.strftime("%A")
        day_breakdown[day] = day_breakdown.get(day, 0) + 1

    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "summary": {
            "total_appointments": total,
            "completed": completed,
            "no_shows": no_shows,
            "cancelled": cancelled,
            "rescheduled": rescheduled,
            "show_rate": calculate_show_rate(completed, total - cancelled),
            "no_show_rate": calculate_no_show_rate(no_shows, total - cancelled),
            "cancellation_rate": round((cancelled / total * 100) if total > 0 else 0, 2)
        },
        "breakdowns": {
            "by_channel": channel_breakdown,
            "by_time_slot": dict(sorted(time_slots.items())),
            "by_day": day_breakdown
        }
    }


@router.get("/analytics/resource/{resource_id}")
async def get_resource_analytics(
    resource_id: int,
    start_date: date = Query(...),
    end_date: date = Query(...),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get detailed analytics for a specific resource"""
    user = await get_current_user(request, db)

    # Use the overview endpoint with resource filter
    return await get_analytics_overview(
        start_date=start_date,
        end_date=end_date,
        resource_id=resource_id,
        request=request,
        db=db
    )


@router.get("/analytics/best-times")
async def get_best_booking_times(
    request: Request,
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """Analyze best times to offer appointments based on show rates"""
    user = await get_current_user(request, db)

    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    from smart_scheduler_models import AppointmentStatus

    start_dt = datetime.utcnow() - timedelta(days=days_back)

    appointments = db.query(Appointment).filter(
        Appointment.scheduled_start >= start_dt,
        Appointment.status.in_([AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW])
    ).all()

    # Analyze by hour
    hour_stats = {}
    for appt in appointments:
        hour = appt.scheduled_start.hour
        if hour not in hour_stats:
            hour_stats[hour] = {"total": 0, "completed": 0}
        hour_stats[hour]["total"] += 1
        if appt.status == AppointmentStatus.COMPLETED:
            hour_stats[hour]["completed"] += 1

    # Calculate show rates by hour
    best_times = []
    for hour, stats in hour_stats.items():
        show_rate = (stats["completed"] / stats["total"] * 100) if stats["total"] > 0 else 0
        best_times.append({
            "hour": f"{hour:02d}:00",
            "total_appointments": stats["total"],
            "completed": stats["completed"],
            "show_rate": round(show_rate, 1)
        })

    # Sort by show rate descending
    best_times.sort(key=lambda x: x["show_rate"], reverse=True)

    # Analyze by day
    day_stats = {}
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for appt in appointments:
        day = day_names[appt.scheduled_start.weekday()]
        if day not in day_stats:
            day_stats[day] = {"total": 0, "completed": 0}
        day_stats[day]["total"] += 1
        if appt.status == AppointmentStatus.COMPLETED:
            day_stats[day]["completed"] += 1

    best_days = []
    for day, stats in day_stats.items():
        show_rate = (stats["completed"] / stats["total"] * 100) if stats["total"] > 0 else 0
        best_days.append({
            "day": day,
            "total_appointments": stats["total"],
            "completed": stats["completed"],
            "show_rate": round(show_rate, 1)
        })

    best_days.sort(key=lambda x: x["show_rate"], reverse=True)

    return {
        "analysis_period_days": days_back,
        "total_appointments_analyzed": len(appointments),
        "best_times_by_hour": best_times[:5],
        "worst_times_by_hour": best_times[-3:] if len(best_times) > 3 else [],
        "best_days": best_days[:3],
        "worst_days": best_days[-2:] if len(best_days) > 2 else [],
        "recommendations": [
            f"Best hour: {best_times[0]['hour']} ({best_times[0]['show_rate']}% show rate)" if best_times else "Not enough data",
            f"Best day: {best_days[0]['day']} ({best_days[0]['show_rate']}% show rate)" if best_days else "Not enough data"
        ]
    }


# ============================================================================
# GROUP SESSIONS
# ============================================================================

@router.post("/group-sessions")
async def create_group_session(
    session_data: GroupSessionCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Create a group session/workshop"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    GroupSession = _enhanced_models['GroupSession']

    session = GroupSession(
        title=session_data.title,
        description=session_data.description,
        session_type=session_data.session_type,
        scheduled_start=session_data.scheduled_start,
        scheduled_end=session_data.scheduled_end,
        max_attendees=session_data.max_attendees,
        host_resource_id=session_data.host_resource_id,
        meeting_mode=session_data.meeting_mode,
        location=session_data.location
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "message": "Group session created",
        "session_id": session.id
    }


@router.get("/group-sessions")
async def list_group_sessions(
    request: Request,
    upcoming_only: bool = True,
    db: Session = Depends(get_db)
):
    """List group sessions"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    GroupSession = _enhanced_models['GroupSession']

    query = db.query(GroupSession)

    if upcoming_only:
        query = query.filter(GroupSession.scheduled_start > datetime.utcnow())

    sessions = query.order_by(GroupSession.scheduled_start).all()

    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "session_type": s.session_type,
                "scheduled_start": s.scheduled_start.isoformat(),
                "scheduled_end": s.scheduled_end.isoformat(),
                "current_attendees": s.current_attendees,
                "max_attendees": s.max_attendees,
                "spots_available": s.max_attendees - s.current_attendees,
                "waitlist_count": s.waitlist_count,
                "status": s.status,
                "registration_open": s.registration_open
            }
            for s in sessions
        ]
    }


@router.post("/group-sessions/{session_id}/register")
async def register_for_group_session(
    session_id: int,
    attendee_name: str,
    attendee_email: EmailStr,
    attendee_phone: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Register for a group session"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    GroupSession = _enhanced_models['GroupSession']

    session = db.query(GroupSession).filter(GroupSession.id == session_id).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.registration_open:
        raise HTTPException(status_code=400, detail="Registration is closed")

    attendee = {
        "name": attendee_name,
        "email": attendee_email,
        "phone": attendee_phone,
        "registered_at": datetime.utcnow().isoformat()
    }

    if session.current_attendees < session.max_attendees:
        # Add to attendees
        attendees = session.attendees or []
        attendees.append(attendee)
        session.attendees = attendees
        session.current_attendees += 1

        db.commit()

        return {
            "message": "Successfully registered",
            "status": "confirmed",
            "session_id": session_id
        }
    elif session.waitlist_enabled:
        # Add to waitlist
        waitlist = session.waitlist or []
        waitlist.append(attendee)
        session.waitlist = waitlist
        session.waitlist_count += 1

        db.commit()

        return {
            "message": "Added to waitlist",
            "status": "waitlisted",
            "waitlist_position": session.waitlist_count
        }
    else:
        raise HTTPException(status_code=400, detail="Session is full")


# ============================================================================
# CAMPAIGN TRACKING
# ============================================================================

@router.post("/campaigns/track")
async def track_campaign_booking(
    campaign_data: CampaignBookingCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Track a booking from a campaign"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    CampaignBooking = _enhanced_models['CampaignBooking']

    # Parse channel
    channel = BookingChannel.CRM_MANUAL
    try:
        channel = BookingChannel(campaign_data.channel)
    except ValueError:
        pass

    tracking = CampaignBooking(
        campaign_id=campaign_data.campaign_id,
        campaign_name=campaign_data.campaign_name,
        campaign_type=campaign_data.campaign_type,
        channel=channel,
        contact_phone=campaign_data.contact_phone,
        contact_email=campaign_data.contact_email,
        contact_name=campaign_data.contact_name,
        partner_id=campaign_data.partner_id,
        partner_type=campaign_data.partner_type,
        partner_name=campaign_data.partner_name,
        booking_started_at=datetime.utcnow()
    )

    db.add(tracking)
    db.commit()
    db.refresh(tracking)

    return {
        "message": "Campaign tracking created",
        "tracking_id": tracking.id
    }


@router.get("/campaigns/analytics")
async def get_campaign_analytics(
    campaign_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """Get campaign booking analytics"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    CampaignBooking = _enhanced_models['CampaignBooking']

    query = db.query(CampaignBooking)

    if campaign_id:
        query = query.filter(CampaignBooking.campaign_id == campaign_id)

    if start_date:
        query = query.filter(CampaignBooking.created_at >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(CampaignBooking.created_at <= datetime.combine(end_date, time.max))

    bookings = query.all()

    # Funnel analysis
    total = len(bookings)
    voicemail_sent = len([b for b in bookings if b.voicemail_sent_at])
    sms_replied = len([b for b in bookings if b.sms_reply_at])
    booking_completed = len([b for b in bookings if b.booking_completed_at])
    appointment_kept = len([b for b in bookings if b.appointment_kept_at])
    converted = len([b for b in bookings if b.converted_to_application_at])
    funded = len([b for b in bookings if b.funded_at])

    return {
        "summary": {
            "total_tracked": total,
            "voicemail_sent": voicemail_sent,
            "sms_replied": sms_replied,
            "bookings_completed": booking_completed,
            "appointments_kept": appointment_kept,
            "converted_to_application": converted,
            "funded": funded
        },
        "funnel_rates": {
            "voicemail_to_reply": round((sms_replied / voicemail_sent * 100) if voicemail_sent > 0 else 0, 2),
            "reply_to_booking": round((booking_completed / sms_replied * 100) if sms_replied > 0 else 0, 2),
            "booking_to_show": round((appointment_kept / booking_completed * 100) if booking_completed > 0 else 0, 2),
            "show_to_application": round((converted / appointment_kept * 100) if appointment_kept > 0 else 0, 2),
            "application_to_funding": round((funded / converted * 100) if converted > 0 else 0, 2)
        }
    }


# ============================================================================
# MIGRATION ENDPOINT FOR ENHANCED TABLES
# ============================================================================

@router.post("/migrate-enhanced")
async def run_enhanced_migration(
    request: Request,
    db: Session = Depends(get_db)
):
    """Create all enhanced scheduler tables"""
    user = await get_current_user(request, db)

    if _enhanced_models is None:
        raise HTTPException(status_code=500, detail="Enhanced models not initialized")

    try:
        # Get metadata from any model
        SchedulerResource = _enhanced_models['SchedulerResource']
        metadata = SchedulerResource.__table__.metadata

        # Create all tables
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        existing_tables = inspector.get_table_names()

        tables_to_create = [
            'scheduler_resources',
            'scheduler_soft_holds',
            'scheduler_reminder_profiles',
            'scheduler_analytics',
            'scheduler_campaign_bookings',
            'scheduler_group_sessions',
            'scheduler_series',
            'scheduler_calendar_sync',
            'scheduler_intake_questions'
        ]

        created = []
        for table_name in tables_to_create:
            if table_name not in existing_tables:
                created.append(table_name)

        metadata.create_all(bind=db.bind, checkfirst=True)

        logger.info(f"Enhanced scheduler migration complete. Created: {created}")

        return {
            "message": "Enhanced scheduler migration complete",
            "created_tables": created,
            "existing_tables": [t for t in tables_to_create if t in existing_tables]
        }

    except Exception as e:
        logger.error(f"Enhanced migration error: {e}")
        raise HTTPException(status_code=500, detail="Migration failed")
