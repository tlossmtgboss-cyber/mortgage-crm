"""
Microsoft Teams Integration Routes
===================================
Endpoints for creating Teams meetings from the CRM.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from services.microsoft_graph import (
    MicrosoftGraphUserService,
    CalendarEventParams,
    CalendarResult,
)
from integrations.microsoft_graph import graph_client
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


_security = HTTPBearer(auto_error=False)

async def _get_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
):
    """Get current authenticated user for Teams endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    return await get_current_user_flexible(token=credentials.credentials, request=None, db=db)

router = APIRouter(
    prefix="/api/v1/teams", tags=["Teams Integration"],
)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class CreateMeetingRequest(BaseModel):
    """Request to create a Teams meeting."""
    subject: str = Field(..., description="Meeting subject/title")
    start_time: datetime = Field(..., description="Meeting start time (ISO format)")
    duration_minutes: int = Field(default=30, ge=15, le=480, description="Meeting duration in minutes")
    attendees: Optional[List[str]] = Field(default=None, description="List of attendee email addresses")
    notes: Optional[str] = Field(default=None, description="Meeting agenda/notes")
    meeting_type: Optional[str] = Field(default="consultation", description="Meeting type for reference")
    lead_id: Optional[int] = Field(default=None, description="Associated lead ID")
    loan_id: Optional[int] = Field(default=None, description="Associated loan ID")


class MeetingResponse(BaseModel):
    """Response after creating a Teams meeting."""
    success: bool
    event_id: Optional[str] = None
    web_link: Optional[str] = None
    teams_link: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error: Optional[str] = None


class AvailabilitySlot(BaseModel):
    """A time slot with availability status."""
    start: datetime
    end: datetime
    available: bool


class AvailabilityResponse(BaseModel):
    """Response with user's availability."""
    user_id: int
    date_range: dict
    busy_slots: List[dict]
    available_slots: List[dict]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/meetings", response_model=MeetingResponse)
async def create_teams_meeting(
    request: CreateMeetingRequest,
    current_user=Depends(_get_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Create a Microsoft Teams meeting.

    This endpoint creates a calendar event with a Teams meeting link.
    The user must have their Microsoft account connected via OAuth.
    """
    try:
        # Calculate end time
        end_time = request.start_time + timedelta(minutes=request.duration_minutes)

        # Build event body with meeting details
        body_html = f"""
        <p><strong>Meeting Type:</strong> {request.meeting_type or 'Consultation'}</p>
        """
        if request.notes:
            body_html += f"<p><strong>Agenda:</strong></p><p>{request.notes}</p>"
        if request.lead_id:
            body_html += f"<p><em>Lead ID: {request.lead_id}</em></p>"
        if request.loan_id:
            body_html += f"<p><em>Loan ID: {request.loan_id}</em></p>"

        # Create the meeting using user-delegated service
        user_id = current_user.id
        service = MicrosoftGraphUserService(user_id, db)

        result = await service.create_calendar_event(CalendarEventParams(
            subject=request.subject,
            start=request.start_time,
            end=end_time,
            body=body_html,
            attendees=request.attendees,
            is_online_meeting=True,  # This creates the Teams link
            reminder_minutes=15,
        ))

        if result.success:
            # Log activity if lead_id provided
            if request.lead_id:
                try:
                    from sqlalchemy import text
                    db.execute(text("""
                        INSERT INTO lead_activities (lead_id, activity_type, description, created_at)
                        VALUES (:lead_id, 'meeting_scheduled', :description, NOW())
                    """), {
                        "lead_id": request.lead_id,
                        "description": f"Teams meeting scheduled: {request.subject}"
                    })
                    db.commit()
                except SQLAlchemyError as e:
                    logger.warning(f"Failed to log meeting activity: {e}")

            return MeetingResponse(
                success=True,
                event_id=result.event_id,
                web_link=result.web_link,
                teams_link=result.teams_link,
                start_time=request.start_time.isoformat(),
                end_time=end_time.isoformat(),
            )
        else:
            return MeetingResponse(
                success=False,
                error=result.error or "Failed to create meeting"
            )

    except Exception as e:
        logger.error(f"Error creating Teams meeting: {e}")
        return MeetingResponse(
            success=False,
            error=str(e)
        )


@router.get("/availability", response_model=AvailabilityResponse)
async def get_user_availability(
    start_date: datetime = Query(..., description="Start of date range"),
    end_date: datetime = Query(..., description="End of date range"),
    slot_duration_minutes: int = Query(default=30, ge=15, le=120),
    current_user=Depends(_get_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Get a user's availability for scheduling meetings.

    Returns busy time slots and suggests available slots.
    """
    try:
        user_id = current_user.id
        service = MicrosoftGraphUserService(user_id, db)
        busy_slots = await service.get_availability(start_date, end_date)

        # Convert to response format
        busy_list = [
            {
                "start": slot["start"].isoformat(),
                "end": slot["end"].isoformat(),
                "status": slot.get("status", "busy")
            }
            for slot in busy_slots
        ]

        # Generate available slots (simple algorithm - gaps between busy periods)
        available_slots = []
        current_time = start_date

        # Sort busy slots by start time
        sorted_busy = sorted(busy_slots, key=lambda x: x["start"])

        for busy in sorted_busy:
            # If there's a gap before this busy slot
            if current_time < busy["start"]:
                gap_duration = (busy["start"] - current_time).total_seconds() / 60
                if gap_duration >= slot_duration_minutes:
                    available_slots.append({
                        "start": current_time.isoformat(),
                        "end": busy["start"].isoformat(),
                        "duration_minutes": int(gap_duration)
                    })
            current_time = max(current_time, busy["end"])

        # Check for availability after last busy slot
        if current_time < end_date:
            gap_duration = (end_date - current_time).total_seconds() / 60
            if gap_duration >= slot_duration_minutes:
                available_slots.append({
                    "start": current_time.isoformat(),
                    "end": end_date.isoformat(),
                    "duration_minutes": int(gap_duration)
                })

        return AvailabilityResponse(
            user_id=user_id,
            date_range={
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            busy_slots=busy_list,
            available_slots=available_slots
        )

    except Exception as e:
        logger.error(f"Error getting availability: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status")
async def get_teams_integration_status(
    current_user=Depends(_get_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Check if a user has Microsoft/Teams integration configured.
    """
    try:
        from sqlalchemy import text
        user_id = current_user.id

        result = db.execute(text("""
            SELECT id, expires_at, connected_email
            FROM user_integrations
            WHERE user_id = :user_id AND provider = 'microsoft'
            LIMIT 1
        """), {"user_id": user_id}).fetchone()

        if not result:
            return {
                "connected": False,
                "message": "Microsoft account not connected. Please connect via Settings.",
                "setup_url": "/settings/integrations"
            }

        # Check if token is expired
        now = datetime.utcnow()
        is_expired = result.expires_at and result.expires_at < now

        return {
            "connected": True,
            "email": result.connected_email,
            "expired": is_expired,
            "message": "Microsoft account connected" if not is_expired else "Token expired, please reconnect"
        }

    except Exception as e:
        logger.error(f"Error checking Teams status: {e}")
        return {
            "connected": False,
            "error": "Internal server error"
        }


@router.post("/meetings/{event_id}/cancel")
async def cancel_teams_meeting(
    event_id: str,
    send_cancellation: bool = Query(default=True, description="Send cancellation to attendees"),
    current_user=Depends(_get_authenticated_user),
    db: Session = Depends(get_db)
):
    """
    Cancel a Teams meeting.
    """
    try:
        import httpx
        user_id = current_user.id

        service = MicrosoftGraphUserService(user_id, db)
        if not await service.initialize():
            raise HTTPException(
                status_code=401,
                detail="Microsoft account not connected or token expired"
            )

        async with httpx.AsyncClient() as client:
            # Delete the event
            response = await client.delete(
                f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                headers={
                    "Authorization": f"Bearer {service.access_token}",
                    "Content-Type": "application/json"
                },
                timeout=30.0
            )

            if response.status_code in [200, 204]:
                return {"success": True, "message": "Meeting cancelled"}
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return {"success": False, "error": error_msg}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling meeting: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# MEETING TEMPLATES
# =============================================================================

MEETING_TEMPLATES = {
    "consultation": {
        "duration": 30,
        "subject_prefix": "Mortgage Consultation - ",
        "notes_template": """
Agenda:
- Review your financial goals
- Discuss loan options
- Answer questions
- Outline next steps
        """
    },
    "follow_up": {
        "duration": 15,
        "subject_prefix": "Follow-up Call - ",
        "notes_template": """
Agenda:
- Status update
- Address any questions
- Discuss timeline
        """
    },
    "document_review": {
        "duration": 45,
        "subject_prefix": "Document Review - ",
        "notes_template": """
Agenda:
- Review submitted documents
- Identify any missing items
- Clarify requirements
        """
    },
    "pre_approval": {
        "duration": 60,
        "subject_prefix": "Pre-Approval Meeting - ",
        "notes_template": """
Agenda:
- Review pre-approval application
- Verify income and assets
- Discuss property search
- Explain next steps
        """
    },
    "closing_prep": {
        "duration": 30,
        "subject_prefix": "Closing Preparation - ",
        "notes_template": """
Agenda:
- Review closing documents
- Explain closing costs
- Confirm wire transfer details
- Answer final questions
        """
    }
}


@router.get("/templates")
async def get_meeting_templates():
    """
    Get available meeting templates for quick setup.
    """
    return {
        "templates": [
            {
                "id": key,
                "name": key.replace("_", " ").title(),
                "duration_minutes": template["duration"],
                "subject_prefix": template["subject_prefix"],
                "default_notes": template["notes_template"].strip()
            }
            for key, template in MEETING_TEMPLATES.items()
        ]
    }
