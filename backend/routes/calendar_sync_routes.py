"""
Calendar Sync Routes - CRM Calendar ↔ Salesforce Events API

API endpoints for managing CRM calendar events with bi-directional
Salesforce/Outlook synchronization.

Endpoints:
- POST /api/calendar/events - Create event
- GET /api/calendar/events - List events
- GET /api/calendar/events/{id} - Get event
- PUT /api/calendar/events/{id} - Update event
- DELETE /api/calendar/events/{id} - Delete/Cancel event
- POST /api/calendar/events/{id}/resync - Force resync
- GET /api/calendar/sync/status - Get sync status
- GET /api/calendar/sync/settings - Get sync settings
- PUT /api/calendar/sync/settings - Update sync settings
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from calendar_sync_models import (
    CalendarEvent,
    CalendarEventSyncMap,
    CalendarSyncSettings,
    CalendarSyncEventLog,
    SalesforceUserMapping,
    CalendarEventStatus,
    CalendarEventVisibility,
    CalendarEventSourceSystem,
    CalendarSyncStatus,
    ConflictResolutionPolicy,
)
from services.calendar_sync_service import (
    calendar_sync_service,
    compute_fingerprint,
    get_sync_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calendar", tags=["Calendar Sync"])

# ============================================================================
# DEPENDENCY INJECTION (set from main.py)
# ============================================================================

_get_db = None
_get_current_user = None


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependency injection functions from main.py"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """Get database session"""
    if _get_db is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database dependency not configured"
        )
    return next(_get_db())


async def get_current_user(db: Session = Depends(get_db)):
    """Get current authenticated user"""
    if _get_current_user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth dependency not configured"
        )
    # This will be wired up from main.py
    return None


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class CalendarEventCreate(BaseModel):
    """Request schema for creating a calendar event"""
    title: str = Field(..., min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    timezone: str = Field(default="America/New_York")
    all_day: bool = Field(default=False)
    location: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    attendees: Optional[List[str]] = Field(default_factory=list)
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    visibility: CalendarEventVisibility = CalendarEventVisibility.INTERNAL


class CalendarEventUpdate(BaseModel):
    """Request schema for updating a calendar event"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    timezone: Optional[str] = None
    all_day: Optional[bool] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    attendees: Optional[List[str]] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    visibility: Optional[CalendarEventVisibility] = None


class CalendarEventResponse(BaseModel):
    """Response schema for a calendar event"""
    id: str
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    all_day: bool
    location: Optional[str]
    notes: Optional[str]
    owner_user_id: int
    attendees: List[str]
    related_entity_type: Optional[str]
    related_entity_id: Optional[str]
    status: CalendarEventStatus
    visibility: CalendarEventVisibility
    sync_status: CalendarSyncStatus
    last_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CalendarEventListResponse(BaseModel):
    """Response schema for listing calendar events"""
    events: List[CalendarEventResponse]
    total: int
    page: int
    page_size: int


class SyncStatusResponse(BaseModel):
    """Response schema for sync status"""
    last_push_cycle: Optional[str]
    last_pull_cycle: Optional[str]
    pending_pushes: int
    failed_syncs: int
    avg_sync_time_ms: float
    echo_prevented_last_hour: int


class SyncSettingsResponse(BaseModel):
    """Response schema for sync settings"""
    sync_mode: str
    conflict_policy: str
    echo_ignore_window_seconds: int
    push_interval_seconds: int
    pull_interval_seconds: int
    batch_size: int
    max_retries: int
    delete_policy: str
    enable_immediate_push: bool
    salesforce_api_version: str
    sync_enabled: bool


class SyncSettingsUpdate(BaseModel):
    """Request schema for updating sync settings"""
    sync_mode: Optional[str] = None
    conflict_policy: Optional[ConflictResolutionPolicy] = None
    echo_ignore_window_seconds: Optional[int] = None
    push_interval_seconds: Optional[int] = None
    pull_interval_seconds: Optional[int] = None
    batch_size: Optional[int] = None
    max_retries: Optional[int] = None
    delete_policy: Optional[str] = None
    enable_immediate_push: Optional[bool] = None
    sync_enabled: Optional[bool] = None


class ResyncResponse(BaseModel):
    """Response schema for resync request"""
    status: str
    message: str
    event_id: str


# ============================================================================
# CALENDAR EVENT CRUD ENDPOINTS
# ============================================================================

@router.post("/events", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
async def create_calendar_event(
    event_data: CalendarEventCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new calendar event.

    The event will be queued for synchronization with Salesforce.
    If immediate_push is enabled, sync happens within seconds.
    Otherwise, sync occurs in the next 60-second cycle.
    """
    try:
        # Generate event ID
        event_id = calendar_sync_service._generate_ulid()

        # Compute fingerprint
        fingerprint = compute_fingerprint({
            'title': event_data.title,
            'start_at': event_data.start_at.isoformat(),
            'end_at': event_data.end_at.isoformat(),
            'all_day': event_data.all_day,
            'location': event_data.location,
            'notes': event_data.notes,
        })

        # Create event
        event = CalendarEvent(
            id=event_id,
            title=event_data.title,
            start_at=event_data.start_at,
            end_at=event_data.end_at,
            timezone=event_data.timezone,
            all_day=event_data.all_day,
            location=event_data.location,
            notes=event_data.notes,
            owner_user_id=current_user.id if current_user else 1,
            attendees=event_data.attendees or [],
            related_entity_type=event_data.related_entity_type,
            related_entity_id=event_data.related_entity_id,
            visibility=event_data.visibility,
            status=CalendarEventStatus.SCHEDULED,
            source_system=CalendarEventSourceSystem.CRM,
            last_modified_by_system=CalendarEventSourceSystem.CRM,
            sync_status=CalendarSyncStatus.PENDING,
            fingerprint_hash=fingerprint,
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        # Queue immediate push if enabled
        settings = db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id == event.owner_user_id
        ).first()

        if settings and settings.enable_immediate_push and settings.sync_enabled:
            background_tasks.add_task(
                calendar_sync_service.immediate_push,
                db,
                event_id
            )

        logger.info(f"Created calendar event {event_id}")

        return CalendarEventResponse(
            id=event.id,
            title=event.title,
            start_at=event.start_at,
            end_at=event.end_at,
            timezone=event.timezone,
            all_day=event.all_day,
            location=event.location,
            notes=event.notes,
            owner_user_id=event.owner_user_id,
            attendees=event.attendees or [],
            related_entity_type=event.related_entity_type,
            related_entity_id=event.related_entity_id,
            status=event.status,
            visibility=event.visibility,
            sync_status=event.sync_status,
            last_synced_at=event.last_synced_at,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    except Exception as e:
        logger.exception(f"Failed to create calendar event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/events", response_model=CalendarEventListResponse)
async def list_calendar_events(
    start_date: Optional[datetime] = Query(None, description="Filter events starting after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events ending before this date"),
    status: Optional[CalendarEventStatus] = Query(None, description="Filter by status"),
    sync_status: Optional[CalendarSyncStatus] = Query(None, description="Filter by sync status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List calendar events for the current user.

    Supports filtering by date range, status, and sync status.
    """
    try:
        user_id = current_user.id if current_user else 1

        query = db.query(CalendarEvent).filter(
            CalendarEvent.owner_user_id == user_id
        )

        if start_date:
            query = query.filter(CalendarEvent.start_at >= start_date)
        if end_date:
            query = query.filter(CalendarEvent.end_at <= end_date)
        if status:
            query = query.filter(CalendarEvent.status == status)
        if sync_status:
            query = query.filter(CalendarEvent.sync_status == sync_status)

        total = query.count()

        events = query.order_by(CalendarEvent.start_at.asc()) \
            .offset((page - 1) * page_size) \
            .limit(page_size) \
            .all()

        return CalendarEventListResponse(
            events=[
                CalendarEventResponse(
                    id=e.id,
                    title=e.title,
                    start_at=e.start_at,
                    end_at=e.end_at,
                    timezone=e.timezone,
                    all_day=e.all_day,
                    location=e.location,
                    notes=e.notes,
                    owner_user_id=e.owner_user_id,
                    attendees=e.attendees or [],
                    related_entity_type=e.related_entity_type,
                    related_entity_id=e.related_entity_id,
                    status=e.status,
                    visibility=e.visibility,
                    sync_status=e.sync_status,
                    last_synced_at=e.last_synced_at,
                    created_at=e.created_at,
                    updated_at=e.updated_at,
                )
                for e in events
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.exception(f"Failed to list calendar events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/events/{event_id}", response_model=CalendarEventResponse)
async def get_calendar_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get a specific calendar event by ID"""
    try:
        user_id = current_user.id if current_user else 1

        event = db.query(CalendarEvent).filter(
            CalendarEvent.id == event_id,
            CalendarEvent.owner_user_id == user_id
        ).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        return CalendarEventResponse(
            id=event.id,
            title=event.title,
            start_at=event.start_at,
            end_at=event.end_at,
            timezone=event.timezone,
            all_day=event.all_day,
            location=event.location,
            notes=event.notes,
            owner_user_id=event.owner_user_id,
            attendees=event.attendees or [],
            related_entity_type=event.related_entity_type,
            related_entity_id=event.related_entity_id,
            status=event.status,
            visibility=event.visibility,
            sync_status=event.sync_status,
            last_synced_at=event.last_synced_at,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get calendar event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/events/{event_id}", response_model=CalendarEventResponse)
async def update_calendar_event(
    event_id: str,
    event_data: CalendarEventUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a calendar event.

    Changes will be synced to Salesforce/Outlook.
    """
    try:
        user_id = current_user.id if current_user else 1

        event = db.query(CalendarEvent).filter(
            CalendarEvent.id == event_id,
            CalendarEvent.owner_user_id == user_id
        ).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        # Update fields
        update_data = event_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(event, key, value)

        # Recompute fingerprint
        event.fingerprint_hash = compute_fingerprint({
            'title': event.title,
            'start_at': event.start_at.isoformat() if event.start_at else None,
            'end_at': event.end_at.isoformat() if event.end_at else None,
            'all_day': event.all_day,
            'location': event.location,
            'notes': event.notes,
        })

        # Mark for re-sync
        event.last_modified_by_system = CalendarEventSourceSystem.CRM
        event.last_modified_at = datetime.now(timezone.utc)
        event.sync_status = CalendarSyncStatus.PENDING

        db.commit()
        db.refresh(event)

        # Queue immediate push if enabled
        settings = db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id == event.owner_user_id
        ).first()

        if settings and settings.enable_immediate_push and settings.sync_enabled:
            background_tasks.add_task(
                calendar_sync_service.immediate_push,
                db,
                event_id
            )

        logger.info(f"Updated calendar event {event_id}")

        return CalendarEventResponse(
            id=event.id,
            title=event.title,
            start_at=event.start_at,
            end_at=event.end_at,
            timezone=event.timezone,
            all_day=event.all_day,
            location=event.location,
            notes=event.notes,
            owner_user_id=event.owner_user_id,
            attendees=event.attendees or [],
            related_entity_type=event.related_entity_type,
            related_entity_id=event.related_entity_id,
            status=event.status,
            visibility=event.visibility,
            sync_status=event.sync_status,
            last_synced_at=event.last_synced_at,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update calendar event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_event(
    event_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Cancel/delete a calendar event.

    By default, events are soft-canceled (marked as canceled) rather than
    hard-deleted. This preserves the audit trail and syncs the cancellation
    to Salesforce/Outlook.
    """
    try:
        user_id = current_user.id if current_user else 1

        event = db.query(CalendarEvent).filter(
            CalendarEvent.id == event_id,
            CalendarEvent.owner_user_id == user_id
        ).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        # Get settings to determine delete policy
        settings = db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id == user_id
        ).first()

        delete_policy = settings.delete_policy if settings else 'soft_cancel'

        if delete_policy == 'hard_delete':
            db.delete(event)
        else:
            # Soft cancel
            event.status = CalendarEventStatus.CANCELED
            event.last_modified_by_system = CalendarEventSourceSystem.CRM
            event.last_modified_at = datetime.now(timezone.utc)
            event.sync_status = CalendarSyncStatus.PENDING

        db.commit()

        # Queue immediate push if enabled
        if settings and settings.enable_immediate_push and settings.sync_enabled:
            if delete_policy != 'hard_delete':
                background_tasks.add_task(
                    calendar_sync_service.immediate_push,
                    db,
                    event_id
                )

        logger.info(f"Deleted/canceled calendar event {event_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete calendar event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# SYNC CONTROL ENDPOINTS
# ============================================================================

@router.post("/events/{event_id}/resync", response_model=ResyncResponse)
async def resync_event(
    event_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Force resync a specific event.

    Queues the event for immediate synchronization with Salesforce.
    """
    try:
        user_id = current_user.id if current_user else 1

        event = db.query(CalendarEvent).filter(
            CalendarEvent.id == event_id,
            CalendarEvent.owner_user_id == user_id
        ).first()

        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event {event_id} not found"
            )

        # Reset sync status
        event.sync_status = CalendarSyncStatus.PENDING
        event.sync_error = None
        db.commit()

        # Queue immediate push
        background_tasks.add_task(
            calendar_sync_service.immediate_push,
            db,
            event_id
        )

        logger.info(f"Queued resync for event {event_id}")

        return ResyncResponse(
            status="queued",
            message="Resync initiated",
            event_id=event_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to resync event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_calendar_sync_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get current calendar sync status.

    Returns information about the last sync cycles, pending events,
    and sync performance metrics.
    """
    try:
        status_data = await get_sync_status(db)

        return SyncStatusResponse(
            last_push_cycle=status_data.get('last_push_cycle'),
            last_pull_cycle=status_data.get('last_pull_cycle'),
            pending_pushes=status_data.get('pending_pushes', 0),
            failed_syncs=status_data.get('failed_syncs', 0),
            avg_sync_time_ms=status_data.get('avg_sync_time_ms', 0),
            echo_prevented_last_hour=status_data.get('echo_prevented_last_hour', 0),
        )

    except Exception as e:
        logger.exception(f"Failed to get sync status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/sync/settings", response_model=SyncSettingsResponse)
async def get_calendar_sync_settings(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get calendar sync settings for the current user"""
    try:
        user_id = current_user.id if current_user else 1

        settings = db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id == user_id
        ).first()

        if not settings:
            # Return defaults
            return SyncSettingsResponse(
                sync_mode="crm_only",
                conflict_policy="last_write_wins",
                echo_ignore_window_seconds=90,
                push_interval_seconds=60,
                pull_interval_seconds=60,
                batch_size=100,
                max_retries=5,
                delete_policy="soft_cancel",
                enable_immediate_push=True,
                salesforce_api_version="v60.0",
                sync_enabled=False,
            )

        return SyncSettingsResponse(
            sync_mode=settings.sync_mode,
            conflict_policy=settings.conflict_policy.value if settings.conflict_policy else "last_write_wins",
            echo_ignore_window_seconds=settings.echo_ignore_window_seconds,
            push_interval_seconds=settings.push_interval_seconds,
            pull_interval_seconds=settings.pull_interval_seconds,
            batch_size=settings.batch_size,
            max_retries=settings.max_retries,
            delete_policy=settings.delete_policy,
            enable_immediate_push=settings.enable_immediate_push,
            salesforce_api_version=settings.salesforce_api_version,
            sync_enabled=settings.sync_enabled,
        )

    except Exception as e:
        logger.exception(f"Failed to get sync settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/sync/settings", response_model=SyncSettingsResponse)
async def update_calendar_sync_settings(
    settings_data: SyncSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update calendar sync settings for the current user"""
    try:
        user_id = current_user.id if current_user else 1

        settings = db.query(CalendarSyncSettings).filter(
            CalendarSyncSettings.user_id == user_id
        ).first()

        if not settings:
            settings = CalendarSyncSettings(user_id=user_id)
            db.add(settings)

        # Update fields
        update_data = settings_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(settings, key, value)

        db.commit()
        db.refresh(settings)

        logger.info(f"Updated sync settings for user {user_id}")

        return SyncSettingsResponse(
            sync_mode=settings.sync_mode,
            conflict_policy=settings.conflict_policy.value if settings.conflict_policy else "last_write_wins",
            echo_ignore_window_seconds=settings.echo_ignore_window_seconds,
            push_interval_seconds=settings.push_interval_seconds,
            pull_interval_seconds=settings.pull_interval_seconds,
            batch_size=settings.batch_size,
            max_retries=settings.max_retries,
            delete_policy=settings.delete_policy,
            enable_immediate_push=settings.enable_immediate_push,
            salesforce_api_version=settings.salesforce_api_version,
            sync_enabled=settings.sync_enabled,
        )

    except Exception as e:
        logger.exception(f"Failed to update sync settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@router.post("/sync/trigger-push", status_code=status.HTTP_202_ACCEPTED)
async def trigger_push_cycle(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Manually trigger a push sync cycle.

    Admin endpoint to force a push of all pending events to Salesforce.
    """
    try:
        background_tasks.add_task(
            calendar_sync_service.push_pending_events,
            db
        )

        return {"status": "queued", "message": "Push cycle initiated"}

    except Exception as e:
        logger.exception(f"Failed to trigger push cycle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/sync/trigger-pull", status_code=status.HTTP_202_ACCEPTED)
async def trigger_pull_cycle(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Manually trigger a pull sync cycle.

    Admin endpoint to force a pull of Salesforce events to CRM.
    """
    try:
        background_tasks.add_task(
            calendar_sync_service.pull_salesforce_changes,
            db
        )

        return {"status": "queued", "message": "Pull cycle initiated"}

    except Exception as e:
        logger.exception(f"Failed to trigger pull cycle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/sync/logs")
async def get_sync_logs(
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
    direction: Optional[str] = Query(None, description="Filter by direction (push/pull)"),
    result: Optional[str] = Query(None, description="Filter by result (success/failed/echo)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get recent sync logs for debugging/monitoring"""
    try:
        query = db.query(CalendarSyncEventLog).order_by(
            CalendarSyncEventLog.created_at.desc()
        )

        if direction:
            query = query.filter(CalendarSyncEventLog.direction == direction)
        if result:
            query = query.filter(CalendarSyncEventLog.result == result)

        logs = query.limit(limit).all()

        return {
            "logs": [
                {
                    "id": log.id,
                    "crm_event_id": log.crm_event_id,
                    "salesforce_event_id": log.salesforce_event_id,
                    "direction": log.direction,
                    "operation": log.operation,
                    "result": log.result,
                    "error_message": log.error_message,
                    "duration_ms": log.duration_ms,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
            "total": len(logs),
        }

    except Exception as e:
        logger.exception(f"Failed to get sync logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
