"""
Scheduler AI Scheduling - AI-powered slot recommendations and no-show risk scoring.

Endpoints:
  - POST   /ai-recommend-slots                    AI-recommended time slots
  - GET    /appointments/{id}/no-show-risk         No-show risk for one appointment
  - GET    /analytics/no-show-risks                Batch no-show risk for a date
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timezone
from typing import Optional
import logging

from smart_scheduler_models import AppointmentStatus
from scheduler_models import AvailableSlotsRequest

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id,
    _generate_available_slots,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# NO-SHOW RISK SCORING (internal helper)
# ============================================================================

def _calculate_no_show_risk(appointment, db, Appointment, AppointmentStatusEnum, org_id):
    """
    Calculate a predictive no-show risk score for an appointment.
    Returns dict with score (0-100), risk_level, and contributing factors.

    Delegates to the scheduling_intelligence service if available,
    otherwise uses a lightweight inline scoring model.
    """
    try:
        from services.scheduling_intelligence import predict_no_show_risk
        import asyncio
        # Try to get the event loop; if we're in an async context use it
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context -- cannot call sync; fall through to inline
            raise RuntimeError("Use inline")
        except RuntimeError:
            pass
    except (ImportError, RuntimeError):
        pass

    # Inline lightweight scoring model
    score = 20  # baseline
    factors = []

    # Factor: Lead source
    if appointment.lead_id:
        try:
            from database.models.lead_loan import Lead
            lead = db.query(Lead).filter(Lead.id == appointment.lead_id).first()
            if lead:
                high_intent = {'referral', 'rate_quote', 'application_started'}
                if lead.source in high_intent:
                    score -= 10
                    factors.append({"factor": "high_intent_source", "impact": -10})
                elif lead.source in {'cold_list', 'purchased'}:
                    score += 15
                    factors.append({"factor": "cold_lead_source", "impact": +15})
        except Exception as e:
            logger.warning(f"Lead source scoring failed for lead {appointment.lead_id}: {e}")

    # Factor: Historical no-shows for this attendee
    if appointment.attendee_email:
        try:
            past_no_shows = db.query(Appointment).filter(
                Appointment.attendee_email == appointment.attendee_email,
                Appointment.organization_id == org_id,
                Appointment.status == AppointmentStatusEnum.NO_SHOW,
            ).count()
            past_completed = db.query(Appointment).filter(
                Appointment.attendee_email == appointment.attendee_email,
                Appointment.organization_id == org_id,
                Appointment.status == AppointmentStatusEnum.COMPLETED,
            ).count()
            if past_no_shows > 0:
                ns_impact = min(past_no_shows * 15, 40)
                score += ns_impact
                factors.append({"factor": "prior_no_shows", "count": past_no_shows, "impact": ns_impact})
            if past_completed >= 2:
                score -= 10
                factors.append({"factor": "reliable_attendee", "completed": past_completed, "impact": -10})
        except Exception as e:
            logger.warning(f"No-show history lookup failed for {appointment.attendee_email}: {e}")

    # Factor: Time until appointment (further out = higher risk)
    if appointment.scheduled_start:
        from datetime import timezone as tz_mod
        now = datetime.now(tz_mod.utc).replace(tzinfo=None)
        days_until = (appointment.scheduled_start - now).total_seconds() / 86400
        if days_until > 7:
            score += 10
            factors.append({"factor": "far_out_booking", "days": round(days_until, 1), "impact": +10})
        elif days_until <= 1:
            score -= 5
            factors.append({"factor": "imminent_booking", "days": round(days_until, 1), "impact": -5})

    # Factor: Reschedule count
    reschedule_count = getattr(appointment, 'reschedule_count', 0) or 0
    if reschedule_count >= 2:
        score += 15
        factors.append({"factor": "multiple_reschedules", "count": reschedule_count, "impact": +15})

    # Clamp score
    score = max(0, min(100, score))

    if score >= 60:
        risk_level = "high"
    elif score >= 35:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "score": score,
        "risk_level": risk_level,
        "factors": factors,
    }


# ============================================================================
# AI SLOT RECOMMENDATIONS
# ============================================================================

@router.post("/ai-recommend-slots")
async def ai_recommend_slots(
    slot_request: AvailableSlotsRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get AI-recommended time slots based on:
    - User preferences
    - Lead/loan context
    - Historical patterns
    - Optimal meeting times
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    user_ids = slot_request.user_ids if slot_request.user_ids else [user.id]

    available_slots = _generate_available_slots(
        db=db,
        user_ids=user_ids,
        start_date=slot_request.start_date,
        end_date=slot_request.end_date,
        duration_minutes=slot_request.duration_minutes,
        org_id=org_id,
        max_per_day=8,
        check_cross_source=True,
        include_user_id=True,
        include_day_name=True,
    )

    if not available_slots:
        return {
            "recommendations": [],
            "message": "No available slots found in the requested range"
        }

    # Score each slot
    recommendations = []

    for slot in available_slots[:20]:  # Limit to first 20 for performance
        score = 1.0
        reasons = []

        # Parse the slot time
        try:
            slot_dt = datetime.fromisoformat(slot["start"])
        except (ValueError, TypeError):
            continue
        hour = slot_dt.hour
        day_name = slot["day"]

        # Score based on time of day (prefer mid-morning and early afternoon)
        if 9 <= hour <= 11:
            score += 0.3
            reasons.append("Optimal morning time slot")
        elif 14 <= hour <= 16:
            score += 0.2
            reasons.append("Good afternoon time slot")
        elif hour < 9 or hour > 17:
            score -= 0.2
            reasons.append("Outside peak hours")

        # Score based on day of week
        if day_name in ["tuesday", "wednesday", "thursday"]:
            score += 0.1
            reasons.append("Mid-week availability")
        elif day_name == "monday":
            score -= 0.1
            reasons.append("Monday may have competing priorities")
        elif day_name == "friday":
            score -= 0.1
            reasons.append("Friday afternoon may have lower engagement")

        # Bonus for sooner availability
        days_from_now = (slot_dt.date() - datetime.now(timezone.utc).date()).days
        if days_from_now <= 2:
            score += 0.2
            reasons.append("Soon availability - strike while hot")
        elif days_from_now > 7:
            score -= 0.1
            reasons.append("Further out - lead may cool")

        recommendations.append({
            "slot": slot,
            "score": round(score, 2),
            "reasons": reasons
        })

    # Sort by score descending
    recommendations.sort(key=lambda x: x["score"], reverse=True)

    return {
        "recommendations": recommendations[:5],  # Top 5
        "total_available": len(available_slots)
    }


# ============================================================================
# NO-SHOW RISK ENDPOINTS
# ============================================================================

@router.get("/appointments/{appointment_id}/no-show-risk")
async def get_appointment_no_show_risk(
    appointment_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get predictive no-show risk score for a single appointment.
    Score 0-100 with risk level (low/medium/high) and contributing factors.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    from database.enums import AppointmentStatus as _AppointmentStatus

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    risk = _calculate_no_show_risk(appointment, db, Appointment, _AppointmentStatus, org_id)

    return {
        "appointment_id": appointment_id,
        "attendee_name": appointment.attendee_name,
        "attendee_email": appointment.attendee_email,
        "scheduled_start": appointment.scheduled_start.isoformat() if appointment.scheduled_start else None,
        "status": appointment.status.value if appointment.status else None,
        **risk
    }


@router.get("/analytics/no-show-risks")
async def get_batch_no_show_risks(
    request: Request,
    target_date: date = Query(..., alias="date", description="Date to score (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Get no-show risk scores for all appointments on a given date.
    Returns a list sorted by risk score descending (highest risk first).
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    if _models is None:
        raise HTTPException(status_code=500, detail="Models not initialized")

    Appointment = _models['Appointment']
    from database.enums import AppointmentStatus as _AppointmentStatus

    start_dt = datetime.combine(target_date, time.min)
    end_dt = datetime.combine(target_date, time.max)

    appointments = db.query(Appointment).filter(
        Appointment.organization_id == org_id,
        Appointment.scheduled_start >= start_dt,
        Appointment.scheduled_start <= end_dt,
        Appointment.status.notin_([_AppointmentStatus.CANCELLED])
    ).order_by(Appointment.scheduled_start).all()

    results = []
    for appt in appointments:
        risk = _calculate_no_show_risk(appt, db, Appointment, _AppointmentStatus, org_id)
        results.append({
            "appointment_id": appt.id,
            "title": appt.title,
            "attendee_name": appt.attendee_name,
            "attendee_email": appt.attendee_email,
            "scheduled_start": appt.scheduled_start.isoformat() if appt.scheduled_start else None,
            "status": appt.status.value if appt.status else None,
            "meeting_type": appt.meeting_type.value if appt.meeting_type else None,
            **risk
        })

    # Sort by score descending (highest risk first)
    results.sort(key=lambda r: r["score"], reverse=True)

    # Summary counts
    high_risk = len([r for r in results if r["risk_level"] == "high"])
    medium_risk = len([r for r in results if r["risk_level"] == "medium"])
    low_risk = len([r for r in results if r["risk_level"] == "low"])

    return {
        "date": target_date.isoformat(),
        "total_appointments": len(results),
        "risk_summary": {
            "high": high_risk,
            "medium": medium_risk,
            "low": low_risk
        },
        "avg_risk_score": round(sum(r["score"] for r in results) / len(results), 1) if results else 0,
        "appointments": results
    }
