"""
Meeting Routes - Meeting link generation and meeting room endpoints.

Endpoints:
  - POST /api/v1/scheduler/appointments/{id}/meeting-link
        Generate or regenerate a meeting link for an existing appointment.
  - GET  /api/v1/meet/{room_id}
        Get meeting room info for the Perennia Meet lobby page (public, no auth).
  - GET  /api/v1/meet/{room_id}/status
        Check meeting status (started/waiting/ended) for countdown/redirect logic.
"""

import logging
from typing import Optional, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from services.meeting_link_service import MeetingLinkService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["meetings"])

# Dependency injection placeholders (set from smart_scheduler_routes or main.py)
_get_current_user: Optional[Callable] = None
_models: dict = {}


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable, models_dict: dict):
    """Set dependencies at runtime."""
    global _get_current_user, _models
    _get_current_user = get_current_user_func
    _models = models_dict


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# =============================================================================
# Request / Response schemas
# =============================================================================

class GenerateMeetingLinkRequest(BaseModel):
    """Request body for generating a meeting link."""
    provider: str = "auto"  # "auto", "zoom", "teams", "perennia"


class MeetingLinkResponse(BaseModel):
    """Response for meeting link generation."""
    success: bool
    provider: str
    join_url: str = ""
    host_url: str = ""
    meeting_id: str = ""
    dial_in: str = ""
    error: str = ""


class MeetingRoomInfoResponse(BaseModel):
    """Response for meeting room info (public endpoint)."""
    room_id: str
    title: str = ""
    host_name: str = ""
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    duration_minutes: Optional[int] = None
    status: str = "unknown"
    provider: str = "perennia"
    join_url: str = ""
    redirect_url: Optional[str] = None


# =============================================================================
# GENERATE MEETING LINK (authenticated)
# =============================================================================

@router.post(
    "/api/v1/scheduler/appointments/{appointment_id}/meeting-link",
    response_model=MeetingLinkResponse,
)
async def generate_meeting_link(
    appointment_id: int,
    body: GenerateMeetingLinkRequest = GenerateMeetingLinkRequest(),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Generate or regenerate a meeting link for an appointment.

    If the appointment already has a video_link, this will replace it with a
    new one from the requested provider. The old link will no longer work for
    Perennia Meet rooms.

    Requires authentication. The user must be the assigned user or the creator
    of the appointment.
    """
    user = await get_current_user(request, db)
    user_id = user.id if hasattr(user, "id") else user.get("user_id")

    Appointment = _models.get("Appointment")
    if not Appointment:
        raise HTTPException(status_code=500, detail="Scheduler models not loaded")

    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Authorization: must be assigned user or creator
    if (
        appointment.assigned_user_id != user_id
        and appointment.created_by_user_id != user_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only generate meeting links for your own appointments",
        )

    # Generate the meeting link
    result = await MeetingLinkService.create_meeting_link(
        db=db,
        appointment=appointment,
        provider=body.provider,
        user_id=user_id,
    )

    if result.success:
        # Update the appointment
        appointment.video_link = result.join_url
        if result.dial_in:
            dial_parts = []
            if result.dial_in:
                dial_parts.append(f"Dial-in: {result.dial_in}")
            if result.password:
                dial_parts.append(f"Password: {result.password}")
            appointment.dial_in_info = "\n".join(dial_parts)

        db.commit()
        logger.info(
            f"Meeting link generated for appointment {appointment_id}: "
            f"provider={result.provider}"
        )

    return MeetingLinkResponse(
        success=result.success,
        provider=result.provider,
        join_url=result.join_url,
        host_url=result.host_url,
        meeting_id=result.meeting_id,
        dial_in=result.dial_in,
        error=result.error,
    )


# =============================================================================
# MEETING ROOM INFO (public, no auth required)
# =============================================================================

@router.get(
    "/api/v1/meet/{room_id}",
    response_model=MeetingRoomInfoResponse,
)
async def get_meeting_room_info(
    room_id: str,
    db: Session = Depends(get_db),
):
    """Get meeting room information for the lobby page.

    This is a public endpoint (no authentication required) so that meeting
    attendees can view the meeting lobby without logging in.

    The room_id is the short code from the Perennia Meet link
    (e.g., "a1b2-c3d4-e5f6").
    """
    # Validate room_id format (alphanumeric + dashes, max 20 chars)
    clean_room_id = room_id.strip()
    if not clean_room_id or len(clean_room_id) > 20:
        raise HTTPException(status_code=400, detail="Invalid room ID")

    for char in clean_room_id:
        if char not in "abcdefghijklmnopqrstuvwxyz0123456789-":
            raise HTTPException(status_code=400, detail="Invalid room ID format")

    meeting_info = MeetingLinkService.get_meeting_info_for_room(clean_room_id, db)

    if not meeting_info:
        raise HTTPException(
            status_code=404,
            detail="Meeting room not found or has expired",
        )

    # Determine if this is a redirect to an external provider
    video_link = meeting_info.get("video_link", "")
    redirect_url = None
    provider = "perennia"

    if video_link:
        if "zoom.us" in video_link:
            redirect_url = video_link
            provider = "zoom"
        elif "meet.google.com" in video_link:
            redirect_url = video_link
            provider = "google_meet"
        elif "teams.microsoft.com" in video_link:
            redirect_url = video_link
            provider = "teams"

    return MeetingRoomInfoResponse(
        room_id=clean_room_id,
        title=meeting_info.get("title", ""),
        host_name=meeting_info.get("host_name", ""),
        scheduled_start=meeting_info.get("scheduled_start"),
        scheduled_end=meeting_info.get("scheduled_end"),
        duration_minutes=meeting_info.get("duration_minutes"),
        status=meeting_info.get("status", "unknown"),
        provider=provider,
        join_url=video_link or "",
        redirect_url=redirect_url,
    )


@router.get("/api/v1/meet/{room_id}/status")
async def get_meeting_status(
    room_id: str,
    db: Session = Depends(get_db),
):
    """Check meeting status for countdown/redirect logic.

    Returns a lightweight status object that the frontend polls to determine
    when the meeting has started or ended.

    This is a public endpoint (no authentication required).
    """
    clean_room_id = room_id.strip()
    if not clean_room_id or len(clean_room_id) > 20:
        raise HTTPException(status_code=400, detail="Invalid room ID")

    meeting_info = MeetingLinkService.get_meeting_info_for_room(clean_room_id, db)

    if not meeting_info:
        return {
            "room_id": clean_room_id,
            "status": "not_found",
            "message": "Meeting not found",
        }

    from datetime import datetime, timezone as tz

    status = meeting_info.get("status", "unknown")
    scheduled_start = meeting_info.get("scheduled_start")

    # Determine meeting phase
    now = datetime.now(tz.utc)
    phase = "waiting"

    if status in ("completed", "cancelled", "no_show"):
        phase = "ended"
    elif status in ("checked_in",):
        phase = "active"
    elif scheduled_start:
        from datetime import datetime as dt
        try:
            start_dt = dt.fromisoformat(scheduled_start.replace("Z", "+00:00"))
            if hasattr(start_dt, "tzinfo") and start_dt.tzinfo is None:
                import pytz
                start_dt = pytz.utc.localize(start_dt)

            minutes_until = (start_dt - now).total_seconds() / 60

            if minutes_until <= -60:  # More than 1 hour past start
                phase = "ended"
            elif minutes_until <= 0:  # Meeting should have started
                phase = "active"
            elif minutes_until <= 5:  # Within 5 minutes of start
                phase = "starting_soon"
            else:
                phase = "waiting"
        except (ValueError, TypeError):
            phase = "waiting"

    return {
        "room_id": clean_room_id,
        "status": status,
        "phase": phase,
        "scheduled_start": meeting_info.get("scheduled_start"),
        "scheduled_end": meeting_info.get("scheduled_end"),
        "title": meeting_info.get("title", ""),
    }
