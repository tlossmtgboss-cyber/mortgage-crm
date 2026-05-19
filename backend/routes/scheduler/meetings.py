"""
Scheduler Meetings - Virtual meeting integration endpoints.

Endpoints:
  - POST   /appointments/{id}/meeting       Create meeting for existing appointment
  - DELETE /appointments/{id}/meeting       Remove meeting from appointment
  - GET    /appointments/{id}/meeting       Get meeting details for appointment
  - POST   /meetings/test-connection        Test provider connectivity
  - GET    /meetings/settings               Get provider preferences
  - POST   /meetings/settings               Save provider preferences
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Dict, List, Optional
import logging

from db import get_db
from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _is_scheduler_admin, _audit_log,
)
from services.virtual_meeting_service import (
    MeetingProviderFactory,
    MeetingDetails,
    MeetingResult,
    create_meeting_for_appointment,
    get_meeting_provider_settings,
    save_meeting_provider_settings,
)
from exceptions import EntityNotFoundError, PerenniaError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# REQUEST / RESPONSE SCHEMAS
# =============================================================================

class CreateMeetingRequest(BaseModel):
    """Request body for creating a meeting on an appointment."""
    provider: str = Field("auto", description="Provider: auto, zoom, google_meet, teams, perennia")


class MeetingDetailsResponse(BaseModel):
    """Meeting details response."""
    has_meeting: bool = False
    provider: str = ""
    join_url: str = ""
    host_url: str = ""
    meeting_id: str = ""
    passcode: str = ""
    dial_in_numbers: List[Dict[str, str]] = []
    appointment_id: int = 0
    appointment_title: str = ""
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None


class TestConnectionRequest(BaseModel):
    """Request body for testing a meeting provider connection."""
    provider: str = Field(..., description="Provider to test: zoom, google_meet, teams, perennia")


class TestConnectionResponse(BaseModel):
    """Response for connection test."""
    success: bool
    provider: str
    message: str = ""
    metadata: Dict = {}


class SaveProviderSettingsRequest(BaseModel):
    """Request body for saving meeting provider preferences."""
    default_provider: Optional[str] = Field(
        None,
        description="Default provider: auto, zoom, google_meet, teams, perennia, manual",
    )
    auto_create_for_video: Optional[bool] = Field(
        None,
        description="Automatically create meeting link for video appointments",
    )
    default_meeting_duration: Optional[int] = Field(
        None,
        description="Default meeting duration in minutes (5-480)",
        ge=5,
        le=480,
    )


class ProviderSettingsResponse(BaseModel):
    """Response for provider settings."""
    default_provider: str = "auto"
    auto_create_for_video: bool = True
    default_meeting_duration: int = 30
    available_providers: List[str] = []
    connected_providers: List[str] = []


# =============================================================================
# CREATE MEETING
# =============================================================================

@router.post("/appointments/{appointment_id}/meeting")
async def create_meeting(
    appointment_id: int,
    body: CreateMeetingRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Create a virtual meeting for an existing appointment.

    Generates a meeting link via the requested provider and attaches it
    to the appointment. If the appointment already has a meeting link,
    it will be replaced.

    Requires authentication. User must be the assigned user or creator.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models["Appointment"]

    appointment = (await db.execute(select(Appointment).where(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id,
        ),
    ))).scalars().first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Validate provider
    valid_providers = MeetingProviderFactory.get_available_providers() + ["auto"]
    if body.provider not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{body.provider}'. Valid: {', '.join(valid_providers)}",
        )

    result = await create_meeting_for_appointment(
        db=db,
        appointment=appointment,
        provider=body.provider,
        user_id=user.id,
        org_id=org_id,
    )

    if result.success:
        _audit_log(db, org_id, user.id, "meeting_created", "appointment",
                   entity_id=appointment_id,
                   changes={"provider": result.provider, "join_url": result.join_url},
                   request=request)
        await db.commit()
        await db.refresh(appointment)

        logger.info(
            f"Meeting created for appointment {appointment_id}: "
            f"provider={result.provider}, user={user.id}"
        )

        return {
            "success": True,
            "provider": result.provider,
            "join_url": result.join_url,
            "host_url": result.host_url,
            "meeting_id": result.meeting_id,
            "passcode": result.passcode,
            "dial_in_numbers": result.dial_in_numbers,
        }

    raise HTTPException(
        status_code=502,
        detail=f"Failed to create meeting: {result.error}",
    )


# =============================================================================
# DELETE MEETING
# =============================================================================

@router.delete("/appointments/{appointment_id}/meeting")
async def delete_meeting(
    appointment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Remove meeting from an appointment.

    Attempts to cancel/delete the meeting on the provider side,
    then clears the meeting details from the appointment.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models["Appointment"]

    appointment = (await db.execute(select(Appointment).where(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id,
        ),
    ))).scalars().first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if not appointment.video_link:
        raise HTTPException(status_code=404, detail="No meeting attached to this appointment")

    # Detect provider from video_link
    video_link = appointment.video_link or ""
    provider_name = _detect_provider_from_url(video_link)

    # Try to delete on provider side (best-effort)
    deletion_result = None
    meeting_id = _extract_meeting_id(appointment)

    if meeting_id and provider_name != "perennia":
        try:
            provider = MeetingProviderFactory.get_provider(
                provider_name, db, user.id, org_id
            )
            deletion_result = await provider.delete_meeting(meeting_id)
        except Exception as e:
            logger.warning(
                f"Could not delete meeting on provider side for appointment {appointment_id}: {e}"
            )

    # Clear meeting details from appointment
    old_link = appointment.video_link
    appointment.video_link = None
    appointment.dial_in_info = None

    _audit_log(db, org_id, user.id, "meeting_removed", "appointment",
               entity_id=appointment_id,
               changes={"old_video_link": old_link, "provider": provider_name},
               request=request)
    await db.commit()

    logger.info(f"Meeting removed from appointment {appointment_id} by user {user.id}")

    return {
        "success": True,
        "message": "Meeting removed from appointment",
        "provider_deletion": deletion_result.to_dict() if deletion_result else None,
    }


# =============================================================================
# GET MEETING DETAILS
# =============================================================================

@router.get("/appointments/{appointment_id}/meeting", response_model=MeetingDetailsResponse)
async def get_meeting_details(
    appointment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Get meeting details for an appointment.

    Returns meeting join URL, provider info, passcode, and dial-in numbers.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    Appointment = _models["Appointment"]

    appointment = (await db.execute(select(Appointment).where(
        Appointment.id == appointment_id,
        Appointment.organization_id == org_id,
        or_(
            Appointment.assigned_user_id == user.id,
            Appointment.created_by_user_id == user.id,
        ),
    ))).scalars().first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if not appointment.video_link:
        return MeetingDetailsResponse(
            has_meeting=False,
            appointment_id=appointment.id,
            appointment_title=appointment.title or "",
        )

    # Parse dial-in info
    dial_in_numbers = []
    passcode = ""
    if appointment.dial_in_info:
        for line in (appointment.dial_in_info or "").split("\n"):
            line = line.strip()
            if line.startswith("Dial-in:"):
                dial_in_numbers.append({"number": line.replace("Dial-in:", "").strip()})
            elif line.startswith("Passcode:") or line.startswith("Password:") or line.startswith("Meeting Password:"):
                passcode = line.split(":", 1)[1].strip()

    provider = _detect_provider_from_url(appointment.video_link)
    meeting_id = _extract_meeting_id(appointment)

    return MeetingDetailsResponse(
        has_meeting=True,
        provider=provider,
        join_url=appointment.video_link,
        meeting_id=meeting_id or "",
        passcode=passcode,
        dial_in_numbers=dial_in_numbers,
        appointment_id=appointment.id,
        appointment_title=appointment.title or "",
        scheduled_start=appointment.scheduled_start.isoformat() if appointment.scheduled_start else None,
        scheduled_end=appointment.scheduled_end.isoformat() if appointment.scheduled_end else None,
    )


# =============================================================================
# TEST CONNECTION
# =============================================================================

@router.post("/meetings/test-connection", response_model=TestConnectionResponse)
async def test_meeting_connection(
    body: TestConnectionRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Test connectivity to a meeting provider.

    Verifies that the user has valid OAuth credentials for the requested
    provider and that the provider's API is reachable.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    valid_providers = MeetingProviderFactory.get_available_providers()
    if body.provider not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{body.provider}'. Valid: {', '.join(valid_providers)}",
        )

    try:
        provider = MeetingProviderFactory.get_provider(
            body.provider, db, user.id, org_id
        )
        result = await provider.test_connection()

        return TestConnectionResponse(
            success=result.success,
            provider=result.provider,
            message="Connection successful" if result.success else result.error,
            metadata=result.metadata,
        )

    except Exception as e:
        logger.exception(f"Error testing {body.provider} connection for user {user.id}: {e}")
        return TestConnectionResponse(
            success=False,
            provider=body.provider,
            message=str(e),
        )


# =============================================================================
# PROVIDER SETTINGS
# =============================================================================

@router.get("/meetings/settings", response_model=ProviderSettingsResponse)
async def get_provider_settings(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Get meeting provider settings for the current user.

    Returns the user's default provider preference, available providers,
    and which providers the user has connected OAuth for.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    settings = get_meeting_provider_settings(db, user.id, org_id)
    connected = _get_connected_providers(db, user.id)

    return ProviderSettingsResponse(
        default_provider=settings.default_provider,
        auto_create_for_video=settings.auto_create_for_video,
        default_meeting_duration=settings.default_meeting_duration,
        available_providers=MeetingProviderFactory.get_available_providers(),
        connected_providers=connected,
    )


@router.post("/meetings/settings", response_model=ProviderSettingsResponse)
async def save_provider_settings(
    body: SaveProviderSettingsRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Save meeting provider preferences for the current user.

    Configures which provider to use by default when creating meetings,
    whether to auto-create meeting links for video appointments, and
    the default meeting duration.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    try:
        settings = save_meeting_provider_settings(
            db=db,
            user_id=user.id,
            org_id=org_id,
            default_provider=body.default_provider,
            auto_create_for_video=body.auto_create_for_video,
            default_meeting_duration=body.default_meeting_duration,
        )

        _audit_log(db, org_id, user.id, "settings_updated", "meeting_provider",
                   changes=body.model_dump(exclude_none=True), request=request)
        await db.commit()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error saving meeting provider settings for user {user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings")

    connected = _get_connected_providers(db, user.id)

    return ProviderSettingsResponse(
        default_provider=settings.default_provider,
        auto_create_for_video=settings.auto_create_for_video,
        default_meeting_duration=settings.default_meeting_duration,
        available_providers=MeetingProviderFactory.get_available_providers(),
        connected_providers=connected,
    )


# =============================================================================
# HELPERS
# =============================================================================

def _get_connected_providers(db: Session, user_id: int) -> List[str]:
    """Get list of meeting providers the user has connected via OAuth."""
    connected = []
    try:
        from sqlalchemy import text
        result = db.execute(
            text("""
                SELECT provider FROM user_integrations
                WHERE user_id = :user_id
                AND provider IN ('zoom', 'google', 'microsoft')
            """),
            {"user_id": user_id},
        )
        provider_map = {"zoom": "zoom", "google": "google_meet", "microsoft": "teams"}
        for row in result.fetchall():
            mapped = provider_map.get(row[0])
            if mapped:
                connected.append(mapped)
    except Exception as e:
        logger.warning(f"Error fetching connected providers for user {user_id}: {e}")
    # Perennia and Manual are always available
    connected.extend(["perennia", "manual"])
    return connected


def _detect_provider_from_url(video_link: str) -> str:
    """Detect meeting provider from the video link URL."""
    if not video_link:
        return "unknown"
    link_lower = video_link.lower()
    if "zoom.us" in link_lower:
        return "zoom"
    if "meet.google.com" in link_lower:
        return "google_meet"
    if "teams.microsoft.com" in link_lower:
        return "teams"
    if "/meet/" in link_lower:
        return "perennia"
    return "unknown"


def _extract_meeting_id(appointment) -> Optional[str]:
    """Extract meeting ID from appointment metadata or video link."""
    # Check for stored meeting ID in google_calendar_event_id or outlook_event_id
    google_event_id = getattr(appointment, "google_calendar_event_id", None)
    outlook_event_id = getattr(appointment, "outlook_event_id", None)

    if google_event_id:
        return google_event_id
    if outlook_event_id:
        return outlook_event_id

    # Try to extract from video_link for Zoom
    video_link = getattr(appointment, "video_link", "") or ""
    if "zoom.us" in video_link:
        # Zoom URL format: https://zoom.us/j/12345678 or https://us02web.zoom.us/j/12345678
        import re
        match = re.search(r"/j/(\d+)", video_link)
        if match:
            return match.group(1)

    # For Perennia Meet, extract room ID
    if "/meet/" in video_link:
        parts = video_link.split("/meet/")
        if len(parts) > 1:
            return parts[1].split("?")[0].split("#")[0]

    return None
