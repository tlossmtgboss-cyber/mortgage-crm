"""
Calendar Events and Calendar Assignment API Routes

This module contains the calendar event CRUD operations and calendar assignment
management endpoints extracted from main.py.

Calendar Events CRUD:
- POST   /api/v1/calendar/events           - Create a new calendar event
- GET    /api/v1/calendar/events           - List calendar events with optional date filtering
- GET    /api/v1/calendar/events/{id}      - Get a specific calendar event
- PATCH  /api/v1/calendar/events/{id}      - Update a calendar event
- DELETE /api/v1/calendar/events/{id}      - Delete a calendar event

Calendar Assignments API:
- GET    /api/v1/calendar-assignments/purposes        - Get available calendar purposes
- GET    /api/v1/calendar-assignments                 - List all calendar assignments
- GET    /api/v1/calendar-assignments/{purpose}       - Get assignment for specific purpose (public)
- POST   /api/v1/calendar-assignments                 - Create a new calendar assignment
- PUT    /api/v1/calendar-assignments/{id}            - Update a calendar assignment
- DELETE /api/v1/calendar-assignments/{id}            - Delete a calendar assignment
- GET    /api/v1/users/with-calendars                 - Get users who can receive appointments
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel

from db import get_db

logger = logging.getLogger(__name__)


# ============================================================================
# RUNTIME IMPORTS TO AVOID CIRCULAR DEPENDENCIES
# ============================================================================

def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'CalendarEvent': main.CalendarEvent,
        'CalendarAssignment': main.CalendarAssignment,
    }


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


# ============================================================================
# PYDANTIC SCHEMAS - CALENDAR EVENTS
# ============================================================================

class CalendarEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    all_day: bool = False
    location: Optional[str] = None
    event_type: Optional[str] = None
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    attendees: Optional[List[str]] = None
    reminder_minutes: Optional[int] = None


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[str] = None
    attendees: Optional[List[str]] = None


class CalendarEventResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    all_day: bool
    location: Optional[str]
    event_type: Optional[str]
    status: str
    lead_id: Optional[int]
    loan_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# PYDANTIC SCHEMAS - CALENDAR ASSIGNMENTS
# ============================================================================

class CalendarAssignmentCreate(BaseModel):
    purpose: str
    purpose_label: Optional[str] = None
    assigned_user_id: Optional[int] = None
    calendly_url: Optional[str] = None
    booking_link_id: Optional[int] = None
    is_active: bool = True


class CalendarAssignmentUpdate(BaseModel):
    purpose_label: Optional[str] = None
    assigned_user_id: Optional[int] = None
    calendly_url: Optional[str] = None
    booking_link_id: Optional[int] = None
    is_active: Optional[bool] = None


class CalendarAssignmentResponse(BaseModel):
    id: int
    purpose: str
    purpose_label: Optional[str]
    assigned_user_id: Optional[int]
    assigned_user_name: Optional[str] = None
    calendly_url: Optional[str]
    booking_link_id: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# CONSTANTS
# ============================================================================

# Default calendar purposes that can be assigned
CALENDAR_PURPOSES = [
    {"purpose": "purchase_application", "label": "Purchase Application Scheduling"},
    {"purpose": "refinance_application", "label": "Refinance Application Scheduling"},
    {"purpose": "lead_consultation", "label": "Lead Consultation"},
    {"purpose": "document_review", "label": "Document Review Call"},
    {"purpose": "closing_call", "label": "Closing Preparation Call"},
    {"purpose": "general_appointment", "label": "General Appointment"},
    {"purpose": "website_demo", "label": "Website Demo Scheduler"},
]


# ============================================================================
# ROUTER SETUP
# ============================================================================

router = APIRouter(tags=["Calendar"])


# ============================================================================
# CALENDAR EVENTS CRUD
# ============================================================================

@router.post("/api/v1/calendar/events", response_model=CalendarEventResponse, status_code=201)
async def create_event(
    event: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Create a new calendar event"""
    models = get_models()
    CalendarEvent = models['CalendarEvent']

    db_event = CalendarEvent(
        **event.model_dump(exclude={'attendees'}),
        user_id=current_user.id,
        attendees=event.attendees if event.attendees else []
    )

    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    logger.info(f"Calendar event created: {db_event.title}")
    return db_event


@router.get("/api/v1/calendar/events", response_model=List[CalendarEventResponse])
async def get_events(
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get calendar events with optional date filtering"""
    models = get_models()
    CalendarEvent = models['CalendarEvent']

    query = db.query(CalendarEvent).filter(CalendarEvent.user_id == current_user.id)

    if start_date:
        query = query.filter(CalendarEvent.start_time >= start_date)
    if end_date:
        query = query.filter(CalendarEvent.start_time <= end_date)

    events = query.order_by(CalendarEvent.start_time).offset(skip).limit(limit).all()
    return events


@router.get("/api/v1/calendar/events/{event_id}", response_model=CalendarEventResponse)
async def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get a specific calendar event"""
    models = get_models()
    CalendarEvent = models['CalendarEvent']

    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return event


@router.patch("/api/v1/calendar/events/{event_id}", response_model=CalendarEventResponse)
async def update_event(
    event_id: int,
    event_update: CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Update a calendar event"""
    models = get_models()
    CalendarEvent = models['CalendarEvent']

    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for key, value in event_update.model_dump(exclude_unset=True).items():
        if key not in _protected:
            setattr(event, key, value)

    event.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)

    logger.info(f"Calendar event updated: {event.title}")
    return event


@router.delete("/api/v1/calendar/events/{event_id}", status_code=204)
async def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Delete a calendar event"""
    models = get_models()
    CalendarEvent = models['CalendarEvent']

    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id,
        CalendarEvent.user_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    db.delete(event)
    db.commit()

    logger.info(f"Calendar event deleted: {event.title}")
    return None


# ============================================================================
# CALENDAR ASSIGNMENT API
# ============================================================================

@router.get("/api/v1/calendar-assignments/purposes")
async def get_calendar_purposes():
    """Get list of all calendar purposes that can be assigned"""
    return CALENDAR_PURPOSES


@router.get("/api/v1/calendar-assignments", response_model=List[CalendarAssignmentResponse])
async def get_calendar_assignments(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get all calendar assignments for the organization"""
    models = get_models()
    User = models['User']
    CalendarAssignment = models['CalendarAssignment']

    assignments = db.query(CalendarAssignment).filter(
        or_(
            CalendarAssignment.organization_id == current_user.organization_id,
            CalendarAssignment.organization_id == None
        )
    ).all()

    # Enrich with user names and booking link details
    result = []
    for assignment in assignments:
        data = {
            "id": assignment.id,
            "purpose": assignment.purpose,
            "purpose_label": assignment.purpose_label,
            "assigned_user_id": assignment.assigned_user_id,
            "assigned_user_name": None,
            "calendly_url": assignment.calendly_url,
            "booking_link_id": assignment.booking_link_id,
            "booking_link_slug": None,
            "booking_link_name": None,
            "is_active": assignment.is_active,
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
        }
        if assignment.assigned_user_id:
            user = db.query(User).filter(User.id == assignment.assigned_user_id).first()
            if user:
                data["assigned_user_name"] = user.full_name
        if assignment.booking_link_id:
            try:
                from sqlalchemy import text
                row = db.execute(
                    text("SELECT slug, link_name FROM scheduler_booking_links WHERE id = :id AND is_active = true"),
                    {"id": assignment.booking_link_id}
                ).fetchone()
                if row:
                    data["booking_link_slug"] = row[0]
                    data["booking_link_name"] = row[1]
            except Exception:
                pass
        result.append(data)

    return result


@router.get("/api/v1/calendar-assignments/{purpose}")
async def get_calendar_assignment_by_purpose(
    purpose: str,
    db: Session = Depends(get_db)
):
    """Get calendar assignment for a specific purpose (public endpoint for applications)"""
    models = get_models()
    User = models['User']
    CalendarAssignment = models['CalendarAssignment']

    assignment = db.query(CalendarAssignment).filter(
        CalendarAssignment.purpose == purpose,
        CalendarAssignment.is_active == True
    ).first()

    if not assignment:
        # Return default - no specific assignment
        return {
            "purpose": purpose,
            "assigned_user_id": None,
            "calendly_url": None,
            "booking_link_id": None,
            "booking_link_slug": None,
            "booking_link_url": None,
            "assigned_user_name": None,
            "assigned_user_calendly": None
        }

    result = {
        "purpose": purpose,
        "assigned_user_id": assignment.assigned_user_id,
        "calendly_url": assignment.calendly_url,
        "booking_link_id": assignment.booking_link_id,
        "booking_link_slug": None,
        "booking_link_url": None,
        "assigned_user_name": None,
        "assigned_user_calendly": None
    }

    # Get user's Calendly URL if assigned to a user
    if assignment.assigned_user_id:
        user = db.query(User).filter(User.id == assignment.assigned_user_id).first()
        if user:
            result["assigned_user_name"] = user.full_name
            # Try to get user's Calendly integration
            try:
                from routes.calendly_routes import get_calendly_integration_for_user
                calendly = get_calendly_integration_for_user(db, assignment.assigned_user_id)
                if calendly and calendly.get("scheduling_url"):
                    result["assigned_user_calendly"] = calendly["scheduling_url"]
            except Exception:
                pass  # Calendly integration may not be available

    # Get booking link slug if booking_link_id is set
    if assignment.booking_link_id:
        try:
            from sqlalchemy import text
            row = db.execute(
                text("SELECT slug FROM scheduler_booking_links WHERE id = :id AND is_active = true"),
                {"id": assignment.booking_link_id}
            ).fetchone()
            if row:
                result["booking_link_slug"] = row[0]
                result["booking_link_url"] = f"/book/{row[0]}"
        except Exception:
            pass  # Scheduler table may not exist

    return result


@router.post("/api/v1/calendar-assignments", response_model=CalendarAssignmentResponse, status_code=201)
async def create_calendar_assignment(
    assignment_data: CalendarAssignmentCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Create a new calendar assignment"""
    models = get_models()
    User = models['User']
    CalendarAssignment = models['CalendarAssignment']

    # Check if assignment already exists for this purpose
    existing = db.query(CalendarAssignment).filter(
        CalendarAssignment.organization_id == current_user.organization_id,
        CalendarAssignment.purpose == assignment_data.purpose
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Assignment already exists for this purpose. Use PUT to update.")

    assignment = CalendarAssignment(
        organization_id=current_user.organization_id,
        purpose=assignment_data.purpose,
        purpose_label=assignment_data.purpose_label,
        assigned_user_id=assignment_data.assigned_user_id,
        calendly_url=assignment_data.calendly_url,
        booking_link_id=assignment_data.booking_link_id,
        is_active=assignment_data.is_active
    )

    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    # Get user name
    assigned_user_name = None
    if assignment.assigned_user_id:
        user = db.query(User).filter(User.id == assignment.assigned_user_id).first()
        if user:
            assigned_user_name = user.full_name

    logger.info(f"Calendar assignment created: {assignment.purpose} -> user {assignment.assigned_user_id}")

    return {
        **assignment.__dict__,
        "assigned_user_name": assigned_user_name
    }


@router.put("/api/v1/calendar-assignments/{assignment_id}", response_model=CalendarAssignmentResponse)
async def update_calendar_assignment(
    assignment_id: int,
    assignment_data: CalendarAssignmentUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Update a calendar assignment"""
    models = get_models()
    User = models['User']
    CalendarAssignment = models['CalendarAssignment']

    assignment = db.query(CalendarAssignment).filter(
        CalendarAssignment.id == assignment_id
    ).first()

    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Update fields
    if assignment_data.purpose_label is not None:
        assignment.purpose_label = assignment_data.purpose_label
    if assignment_data.assigned_user_id is not None:
        assignment.assigned_user_id = assignment_data.assigned_user_id
    if assignment_data.calendly_url is not None:
        assignment.calendly_url = assignment_data.calendly_url
    if assignment_data.booking_link_id is not None:
        assignment.booking_link_id = assignment_data.booking_link_id
    if assignment_data.is_active is not None:
        assignment.is_active = assignment_data.is_active

    db.commit()
    db.refresh(assignment)

    # Get user name
    assigned_user_name = None
    if assignment.assigned_user_id:
        user = db.query(User).filter(User.id == assignment.assigned_user_id).first()
        if user:
            assigned_user_name = user.full_name

    logger.info(f"Calendar assignment updated: {assignment.purpose}")

    return {
        **assignment.__dict__,
        "assigned_user_name": assigned_user_name
    }


@router.delete("/api/v1/calendar-assignments/{assignment_id}", status_code=204)
async def delete_calendar_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Delete a calendar assignment"""
    models = get_models()
    CalendarAssignment = models['CalendarAssignment']

    assignment = db.query(CalendarAssignment).filter(
        CalendarAssignment.id == assignment_id
    ).first()

    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()

    logger.info(f"Calendar assignment deleted: {assignment.purpose}")
    return None


@router.get("/api/v1/users/with-calendars")
async def get_users_with_calendars(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get list of users who can receive calendar appointments"""
    models = get_models()
    User = models['User']

    users = db.query(User).filter(
        User.is_active == True,
        or_(
            User.organization_id == current_user.organization_id,
            User.organization_id == None
        )
    ).all()

    result = []
    for user in users:
        user_data = {
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "role": user.role,
            "has_calendly": False,
            "calendly_url": None
        }

        # Check if user has Calendly connected
        try:
            from routes.calendly_routes import get_calendly_integration_for_user
            calendly = get_calendly_integration_for_user(db, user.id)
            if calendly:
                user_data["has_calendly"] = True
                user_data["calendly_url"] = calendly.get("scheduling_url")
        except Exception:
            pass  # Calendly integration may not be available

        result.append(user_data)

    return result
