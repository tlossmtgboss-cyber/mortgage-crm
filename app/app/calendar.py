from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, date
import sys
sys.path.append('..')
from app.db import get_db
from app.models import Activity

router = APIRouter(
    prefix="/api/calendar",
    tags=["calendar"]
)

# Pydantic schemas for Calendar Events (using Activity model)
class CalendarEventBase(BaseModel):
    lead_id: int
    activity_type: str  # e.g., 'call', 'email', 'meeting', 'appointment'
    subject: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = "scheduled"
    due_date: datetime

class CalendarEventCreate(CalendarEventBase):
    pass

class CalendarEventUpdate(BaseModel):
    lead_id: Optional[int] = None
    activity_type: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class CalendarEventResponse(CalendarEventBase):
    id: int
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class DayEventsResponse(BaseModel):
    date: date
    events: List[CalendarEventResponse]
    total_count: int

# Calendar-specific endpoints
@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
def create_calendar_event(event: CalendarEventCreate, db: Session = Depends(get_db)):
    """Create a new calendar event"""
    db_event = Activity(**event.dict())
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

@router.get("/events", response_model=List[CalendarEventResponse])
def get_calendar_events(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    activity_type: Optional[str] = None,
    status_filter: Optional[str] = None,
    lead_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get calendar events within a date range"""
    query = db.query(Activity)
    
    if start_date:
        query = query.filter(Activity.due_date >= start_date)
    if end_date:
        query = query.filter(Activity.due_date <= end_date)
    if activity_type:
        query = query.filter(Activity.activity_type == activity_type)
    if status_filter:
        query = query.filter(Activity.status == status_filter)
    if lead_id:
        query = query.filter(Activity.lead_id == lead_id)
    
    events = query.order_by(Activity.due_date).all()
    return events

@router.get("/events/today", response_model=DayEventsResponse)
def get_today_events(db: Session = Depends(get_db)):
    """Get all events scheduled for today"""
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())
    
    events = db.query(Activity).filter(
        Activity.due_date >= start_of_day,
        Activity.due_date <= end_of_day
    ).order_by(Activity.due_date).all()
    
    return DayEventsResponse(
        date=today,
        events=events,
        total_count=len(events)
    )

@router.get("/events/week")
def get_week_events(
    week_offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get all events for a specific week (offset from current week)"""
    today = datetime.utcnow().date()
    # Calculate start of week (Monday)
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=6)
    
    start_datetime = datetime.combine(start_of_week, datetime.min.time())
    end_datetime = datetime.combine(end_of_week, datetime.max.time())
    
    events = db.query(Activity).filter(
        Activity.due_date >= start_datetime,
        Activity.due_date <= end_datetime
    ).order_by(Activity.due_date).all()
    
    # Group events by day
    events_by_day = {}
    for event in events:
        event_date = event.due_date.date()
        if event_date not in events_by_day:
            events_by_day[event_date] = []
        events_by_day[event_date].append(event)
    
    return {
        "start_date": start_of_week,
        "end_date": end_of_week,
        "events_by_day": [
            {
                "date": day,
                "events": events,
                "count": len(events)
            }
            for day, events in sorted(events_by_day.items())
        ],
        "total_events": len(events)
    }

@router.get("/events/month")
def get_month_events(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all events for a specific month"""
    from calendar import monthrange
    
    today = datetime.utcnow()
    target_year = year if year else today.year
    target_month = month if month else today.month
    
    # Get first and last day of month
    first_day = date(target_year, target_month, 1)
    last_day = date(target_year, target_month, monthrange(target_year, target_month)[1])
    
    start_datetime = datetime.combine(first_day, datetime.min.time())
    end_datetime = datetime.combine(last_day, datetime.max.time())
    
    events = db.query(Activity).filter(
        Activity.due_date >= start_datetime,
        Activity.due_date <= end_datetime
    ).order_by(Activity.due_date).all()
    
    # Group events by day
    events_by_day = {}
    for event in events:
        event_date = event.due_date.date()
        if event_date not in events_by_day:
            events_by_day[event_date] = []
        events_by_day[event_date].append(event)
    
    return {
        "year": target_year,
        "month": target_month,
        "first_day": first_day,
        "last_day": last_day,
        "events_by_day": [
            {
                "date": day,
                "events": events,
                "count": len(events)
            }
            for day, events in sorted(events_by_day.items())
        ],
        "total_events": len(events)
    }

@router.get("/events/{event_id}", response_model=CalendarEventResponse)
def get_calendar_event(event_id: int, db: Session = Depends(get_db)):
    """Get a specific calendar event by ID"""
    event = db.query(Activity).filter(Activity.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    return event

@router.put("/events/{event_id}", response_model=CalendarEventResponse)
def update_calendar_event(event_id: int, event_update: CalendarEventUpdate, db: Session = Depends(get_db)):
    """Update a calendar event"""
    db_event = db.query(Activity).filter(Activity.id == event_id).first()
    if not db_event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    
    update_data = event_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_event, field, value)
    
    db.commit()
    db.refresh(db_event)
    return db_event

@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_calendar_event(event_id: int, db: Session = Depends(get_db)):
    """Delete a calendar event"""
    db_event = db.query(Activity).filter(Activity.id == event_id).first()
    if not db_event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    
    db.delete(db_event)
    db.commit()
    return None
