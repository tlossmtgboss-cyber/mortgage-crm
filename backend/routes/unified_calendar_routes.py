"""
Unified Calendar API Routes

Provides a single endpoint that merges events from 3 calendar sources:
1. CalendarEvent - User calendar events
2. ScheduledAppointment - Scheduled appointments
3. CRMCalendarEvent - CRM events (Salesforce sync)

This replaces 3 parallel frontend API calls with a single call.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calendar", tags=["Unified Calendar"])


# ============================================================================
# RUNTIME IMPORTS TO AVOID CIRCULAR DEPENDENCIES
# ============================================================================

def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class UnifiedEventResponse(BaseModel):
    """Single unified event from any source."""
    id: str
    title: str
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    event_type: Optional[str] = None
    location: Optional[str] = None
    source: str  # calendar | scheduler | crm
    related_lead_id: Optional[int] = None
    related_loan_id: Optional[int] = None
    related_contact_id: Optional[int] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    attendee_phone: Optional[str] = None
    meeting_mode: Optional[str] = None
    assigned_user_id: Optional[int] = None
    status: Optional[str] = None
    is_appointment: bool = False
    is_crm_event: bool = False

    class Config:
        from_attributes = True


class UnifiedCalendarResponse(BaseModel):
    """Response containing merged events from all sources."""
    events: List[dict]
    total_count: int
    warnings: List[str]
    sources_queried: List[str]


# ============================================================================
# UNIFIED CALENDAR ENDPOINT
# ============================================================================

@router.get("/unified", response_model=UnifiedCalendarResponse)
async def get_unified_calendar(
    start_date: str = Query(..., description="Start date (ISO format)"),
    end_date: str = Query(..., description="End date (ISO format)"),
    include_cancelled: bool = Query(False, description="Include cancelled events"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep()),
):
    """
    Get unified calendar events from all sources.

    Merges events from:
    - Calendar events (user's calendar)
    - Scheduled appointments (smart scheduler)
    - CRM calendar events (Salesforce sync)

    Returns sorted events with partial failure support - if one source
    fails, others are still returned with warnings.

    Args:
        start_date: Start of date range (ISO format, required)
        end_date: End of date range (ISO format, required)
        include_cancelled: Whether to include cancelled events (default: False)

    Returns:
        UnifiedCalendarResponse with events, total_count, warnings, and sources_queried
    """
    try:
        # Parse dates
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid start_date format: {start_date}. Use ISO format."
            )

        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid end_date format: {end_date}. Use ISO format."
            )

        # Validate date range
        if end_dt < start_dt:
            raise HTTPException(
                status_code=400,
                detail="end_date must be after start_date"
            )

        # Get unified events
        from services.unified_calendar_service import get_unified_calendar_service

        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="No organization context")
        service = get_unified_calendar_service(
            db, current_user.id,
            organization_id=org_id,
        )
        result = service.get_unified_events(
            start_date=start_dt,
            end_date=end_dt,
            include_cancelled=include_cancelled,
        )

        logger.info(
            f"Unified calendar: {result['total_count']} events from "
            f"{result['sources_queried']} for user {current_user.id}"
        )

        return UnifiedCalendarResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unified calendar error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch unified calendar"
        )
