"""
Calendar Sync API Routes
CRUD operations for CRM calendar events with Salesforce sync

Phase 1 - Push (CRM → Salesforce):
- GET    /api/calendar/events          - List events
- POST   /api/calendar/events          - Create event
- GET    /api/calendar/events/{id}     - Get single event
- PUT    /api/calendar/events/{id}     - Update event
- DELETE /api/calendar/events/{id}     - Cancel/delete event
- POST   /api/calendar/events/{id}/resync - Force resync to Salesforce

Phase 2 - Pull (Salesforce → CRM):
- POST   /api/calendar/sync/pull       - Pull events from Salesforce
- POST   /api/calendar/sync/pull/{sf_event_id} - Pull single SF event
- POST   /api/calendar/webhook/cdc     - Salesforce CDC webhook

Sync Management:
- GET    /api/calendar/sync/status     - Get sync status
- POST   /api/calendar/sync/trigger    - Trigger manual sync (push)
- GET    /api/calendar/sync/history    - Get sync history
- GET    /api/calendar/sync/failures   - Get failed events
- GET    /api/calendar/sync/health     - Get sync health metrics

Settings:
- GET    /api/calendar/settings        - Get sync settings
- PUT    /api/calendar/settings        - Update sync settings
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field

from database import get_db
from models.calendar_sync_models import (
    CRMCalendarEvent,
    CalendarEventSyncMap,
    CalendarSyncLog,
    CalendarSyncSettings,
    SyncStatus,
    EventStatus
)
from services.calendar_sync_service import CalendarSyncService, get_calendar_sync_service
from sqlalchemy.exc import SQLAlchemyError
from tasks.calendar_sync_tasks import (
    push_event_to_salesforce,
    process_pending_sync_events,
    check_sync_health
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calendar", tags=["Calendar Sync"])


# ============================================================================
# Pydantic Models
# ============================================================================

class AttendeeModel(BaseModel):
    email: str
    name: Optional[str] = None
    status: Optional[str] = "pending"  # pending, accepted, declined, tentative


class EventCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    timezone: str = "America/New_York"
    all_day: bool = False
    location: Optional[str] = None
    notes: Optional[str] = None
    attendees: Optional[List[AttendeeModel]] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Client Consultation",
                "start_at": "2024-01-15T14:00:00Z",
                "end_at": "2024-01-15T15:00:00Z",
                "timezone": "America/New_York",
                "all_day": False,
                "location": "Zoom Meeting",
                "notes": "Discuss loan options with client",
                "attendees": [{"email": "client@example.com", "name": "John Doe"}],
                "related_entity_type": "lead",
                "related_entity_id": 123
            }
        }


class EventUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    timezone: Optional[str] = None
    all_day: Optional[bool] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    attendees: Optional[List[AttendeeModel]] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    status: Optional[str] = None


class EventResponse(BaseModel):
    id: str
    title: str
    start_at: datetime
    end_at: datetime
    timezone: str
    all_day: bool
    location: Optional[str]
    notes: Optional[str]
    owner_user_id: int
    attendees: List[dict]
    related_entity_type: Optional[str]
    related_entity_id: Optional[int]
    status: str
    source_system: str
    sync_status: str
    sync_error: Optional[str]
    salesforce_event_id: Optional[str]
    last_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SyncStatusResponse(BaseModel):
    pending_count: int
    failed_count: int
    last_sync_at: Optional[str]
    last_error: Optional[str]
    healthy: bool


class SyncSettingsRequest(BaseModel):
    sync_enabled: Optional[bool] = None
    sync_direction: Optional[str] = None
    conflict_policy: Optional[str] = None
    delete_policy: Optional[str] = None
    echo_ignore_window_seconds: Optional[int] = None


# ============================================================================
# Helper Functions
# ============================================================================

def get_current_user_id(request: Request, db: Session) -> Optional[int]:
    """Extract user ID from JWT token in request."""
    try:
        import jwt
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            secret_key = os.getenv("SECRET_KEY", "")
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=["HS256"],
                options={"verify_aud": False, "verify_iss": False}
            )
            email = payload.get("sub")
            if email:
                result = db.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email}
                ).fetchone()
                if result:
                    return result[0]
            return payload.get("user_id")
    except SQLAlchemyError as e:
        logger.warning(f"Failed to extract user ID: {e}")
    return None


def require_user(request: Request, db: Session = Depends(get_db)) -> int:
    """Dependency that requires authenticated user."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# ============================================================================
# Event CRUD Endpoints
# ============================================================================

@router.get("/events", response_model=List[EventResponse])
async def list_events(
    request: Request,
    start_date: Optional[datetime] = Query(None, description="Filter by start date >="),
    end_date: Optional[datetime] = Query(None, description="Filter by start date <="),
    status: Optional[str] = Query(None, description="Filter by status"),
    sync_status: Optional[str] = Query(None, description="Filter by sync status"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    List calendar events for the current user.

    Supports filtering by date range, status, and sync status.
    """
    try:
        user_id = require_user(request, db)
        service = get_calendar_sync_service(db)

        events = service.get_events(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            status=status,
            sync_status=sync_status,
            limit=limit
        )

        return [_event_to_response(e) for e in events]
    except HTTPException:
        raise  # Re-raise HTTP exceptions (like 401)
    except Exception as e:
        logger.warning(f"Error fetching calendar events: {e}")
        # Return empty list instead of 500 error
        return []


@router.post("/events", response_model=EventResponse, status_code=201)
async def create_event(
    request: Request,
    event_data: EventCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a new calendar event.

    The event will be automatically synced to Salesforce/Outlook.
    Returns immediately with sync_status = "pending".
    """
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    # Validate dates
    if event_data.end_at <= event_data.start_at:
        raise HTTPException(
            status_code=400,
            detail="End time must be after start time"
        )

    event = service.create_event(
        user_id=user_id,
        title=event_data.title,
        start_at=event_data.start_at,
        end_at=event_data.end_at,
        timezone=event_data.timezone,
        all_day=event_data.all_day,
        location=event_data.location,
        notes=event_data.notes,
        attendees=[a.model_dump() for a in event_data.attendees] if event_data.attendees else None,
        related_entity_type=event_data.related_entity_type,
        related_entity_id=event_data.related_entity_id,
        auto_sync=True
    )

    # Queue background sync to Salesforce
    background_tasks.add_task(_sync_event_background, event.id)

    logger.info(f"Created calendar event: {event.id}")

    return _event_to_response(event)


@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get a single calendar event by ID."""
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    event = service.get_event(event_id, user_id)

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return _event_to_response(event)


@router.put("/events/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    request: Request,
    updates: EventUpdateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Update a calendar event.

    Changes will be synced to Salesforce/Outlook.
    """
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    # Build update dict (exclude None values)
    update_dict = {}
    for field, value in updates.model_dump().items():
        if value is not None:
            if field == "attendees":
                update_dict[field] = [a if isinstance(a, dict) else a.model_dump() for a in value]
            else:
                update_dict[field] = value

    # Validate dates if both provided
    if "start_at" in update_dict and "end_at" in update_dict:
        if update_dict["end_at"] <= update_dict["start_at"]:
            raise HTTPException(
                status_code=400,
                detail="End time must be after start time"
            )

    event = service.update_event(event_id, user_id, update_dict, auto_sync=True)

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Queue background sync
    if event.sync_status == SyncStatus.PENDING.value:
        background_tasks.add_task(_sync_event_background, event.id)

    return _event_to_response(event)


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    hard_delete: bool = Query(False, description="Hard delete instead of cancel"),
    db: Session = Depends(get_db)
):
    """
    Cancel or delete a calendar event.

    By default, events are soft-cancelled (status = "canceled").
    Use hard_delete=true to permanently remove.
    """
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    if hard_delete:
        # Hard delete
        event = service.get_event(event_id, user_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        # Delete from database
        db.delete(event)
        db.commit()

        return {"status": "deleted", "event_id": event_id}
    else:
        # Soft cancel
        event = service.cancel_event(event_id, user_id, auto_sync=True)

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        # Queue background sync
        background_tasks.add_task(_sync_event_background, event.id)

        return {"status": "canceled", "event_id": event_id}


@router.post("/events/{event_id}/resync")
async def resync_event(
    event_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Force resync an event to Salesforce.

    Recreates the Salesforce event if the mapping is missing.
    """
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    event = service.get_event(event_id, user_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Reset sync status and queue
    event.sync_status = SyncStatus.PENDING.value
    event.sync_error = None
    db.commit()

    # Queue sync
    background_tasks.add_task(_sync_event_background, event.id)

    return {
        "status": "queued",
        "event_id": event_id,
        "message": "Event queued for resync to Salesforce"
    }


# ============================================================================
# Sync Management Endpoints
# ============================================================================

@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get calendar sync status for the current user."""
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    status = service.get_sync_status(user_id)
    return SyncStatusResponse(**status)


@router.post("/sync/trigger")
async def trigger_sync(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger manual sync of all pending events.

    Returns immediately; sync happens in background.
    """
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    # Get pending events for this user
    pending = service.get_events(user_id=user_id, sync_status=SyncStatus.PENDING.value)

    if not pending:
        return {
            "status": "no_pending",
            "message": "No pending events to sync"
        }

    # Queue all for sync
    for event in pending:
        background_tasks.add_task(_sync_event_background, event.id)

    return {
        "status": "queued",
        "events_queued": len(pending),
        "message": f"Queued {len(pending)} events for sync"
    }


@router.get("/sync/history")
async def get_sync_history(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get sync history for the current user."""
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    history = service.get_sync_history(user_id, limit)
    return {"history": history}


@router.get("/sync/failures")
async def get_sync_failures(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get events that failed to sync."""
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    failed = service.get_failed_events(user_id)
    return {
        "count": len(failed),
        "events": [_event_to_response(e) for e in failed]
    }


@router.get("/sync/health")
async def get_sync_health(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get overall calendar sync health metrics.

    Returns health status, metrics, and any alerts.
    """
    require_user(request, db)  # Auth check

    import asyncio
    health = asyncio.run(check_sync_health())
    return health


# ============================================================================
# Phase 2: Pull Endpoints (Salesforce → CRM)
# ============================================================================

class PullRequest(BaseModel):
    since: Optional[datetime] = None
    limit: int = Field(200, ge=1, le=500)


class CDCWebhookPayload(BaseModel):
    """Salesforce CDC webhook payload structure."""
    changeType: str  # CREATE, UPDATE, DELETE, UNDELETE
    entityName: str  # Event
    changedRecords: List[dict] = []
    replayId: Optional[int] = None


@router.post("/sync/pull")
async def pull_events_from_salesforce(
    request: Request,
    pull_request: Optional[PullRequest] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Pull events from Salesforce into CRM.

    Fetches events from Salesforce and creates/updates corresponding CRM events.
    Uses fingerprint matching to prevent sync loops.

    Args:
        since: Only pull events modified after this datetime
        limit: Maximum events to pull (default 200)

    Returns:
        Summary of pull operation with counts
    """
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    since = pull_request.since if pull_request else None
    limit = pull_request.limit if pull_request else 200

    # If no since provided, use last poll watermark
    if not since:
        settings = service.get_settings(user_id)
        since = settings.last_poll_watermark

    import asyncio
    result = await service.pull_events_from_salesforce(
        user_id=user_id,
        since=since,
        limit=limit
    )

    return {
        "status": "completed",
        "pulled": result["pulled"],
        "created": result["created"],
        "updated": result["updated"],
        "skipped_echo": result["skipped_echo"],
        "skipped_conflict": result["skipped_conflict"],
        "errors": result["errors"][:10] if result["errors"] else []  # Limit error details
    }


@router.post("/sync/pull/{salesforce_event_id}")
async def pull_single_event(
    salesforce_event_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Pull a single event from Salesforce by ID.

    Useful for manually syncing specific events or handling webhook notifications.

    Args:
        salesforce_event_id: The Salesforce Event ID (18-char)

    Returns:
        Pull result with action taken
    """
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    result = await service.pull_single_event(
        user_id=user_id,
        salesforce_event_id=salesforce_event_id
    )

    if result.success:
        return {
            "status": "success",
            "action": result.operation,
            "crm_event_id": result.crm_event_id,
            "salesforce_event_id": result.salesforce_event_id
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=result.error
        )


@router.post("/webhook/cdc")
async def salesforce_cdc_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Salesforce CDC (Change Data Capture) webhook endpoint.

    Receives real-time notifications when Salesforce Events are created,
    updated, or deleted. Processes changes to sync back to CRM.

    This endpoint should be registered as a webhook in Salesforce
    Platform Events or via the Streaming API.

    Security: Validates webhook signature if configured.
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify webhook signature (if configured)
    webhook_secret = os.getenv("SALESFORCE_CDC_WEBHOOK_SECRET")
    if webhook_secret:
        signature = request.headers.get("X-Salesforce-Signature")
        if not _verify_webhook_signature(body, signature, webhook_secret):
            logger.warning("Invalid CDC webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        import json
        payload = json.loads(body)
    except Exception as e:
        logger.error(f"Failed to parse CDC webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Extract CDC data
    change_type = payload.get("changeType") or payload.get("ChangeEventHeader", {}).get("changeType")
    entity_name = payload.get("entityName") or payload.get("ChangeEventHeader", {}).get("entityName", "").replace("ChangeEvent", "")

    logger.info(f"Received CDC webhook: {change_type} on {entity_name}")

    # Only process Event changes
    if entity_name != "Event":
        return {"status": "ignored", "reason": "not_event_object"}

    # Extract user ID from the event owner or use default processing
    # In production, you'd map the SF OwnerId to a CRM user
    changed_records = payload.get("changedRecords", [])
    if not changed_records:
        # Try alternate CDC format
        record_ids = payload.get("ChangeEventHeader", {}).get("recordIds", [])
        changed_records = [{"Id": rid} for rid in record_ids]

    if not changed_records:
        return {"status": "ignored", "reason": "no_records"}

    # Process in background to respond quickly
    background_tasks.add_task(
        _process_cdc_webhook_background,
        change_type,
        changed_records,
        db
    )

    return {
        "status": "accepted",
        "change_type": change_type,
        "record_count": len(changed_records)
    }


@router.post("/sync/full")
async def trigger_full_sync(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Trigger a full bidirectional sync.

    1. Pushes all pending CRM events to Salesforce
    2. Pulls all recent Salesforce events to CRM

    Use with caution - may be slow for large calendars.
    """
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    # Queue full sync in background
    background_tasks.add_task(
        _full_sync_background,
        user_id,
        db
    )

    return {
        "status": "queued",
        "message": "Full bidirectional sync queued"
    }


# ============================================================================
# Settings Endpoints
# ============================================================================

@router.get("/settings")
async def get_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get calendar sync settings for the current user."""
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    settings = service.get_settings(user_id)
    return settings.to_dict()


@router.put("/settings")
async def update_settings(
    request: Request,
    settings_update: SyncSettingsRequest,
    db: Session = Depends(get_db)
):
    """Update calendar sync settings for the current user."""
    user_id = require_user(request, db)
    service = get_calendar_sync_service(db)

    update_dict = {
        k: v for k, v in settings_update.model_dump().items()
        if v is not None
    }

    settings = service.update_settings(user_id, update_dict)
    return settings.to_dict()


# ============================================================================
# Helper Functions
# ============================================================================

def _event_to_response(event: CRMCalendarEvent) -> EventResponse:
    """Convert CRMCalendarEvent to response model."""
    return EventResponse(
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
        source_system=event.source_system,
        sync_status=event.sync_status,
        sync_error=event.sync_error,
        salesforce_event_id=event.sync_mapping.salesforce_event_id if event.sync_mapping else None,
        last_synced_at=event.last_synced_at,
        created_at=event.created_at,
        updated_at=event.updated_at
    )


async def _sync_event_background(event_id: str):
    """Background task to sync event to Salesforce."""
    try:
        result = await push_event_to_salesforce(event_id)
        if result.get("success"):
            logger.info(f"Background sync successful for event {event_id}")
        else:
            logger.warning(f"Background sync failed for event {event_id}: {result.get('error')}")
    except Exception as e:
        logger.exception(f"Background sync error for event {event_id}: {e}")


async def _process_cdc_webhook_background(
    change_type: str,
    changed_records: List[dict],
    db: Session
):
    """Background task to process CDC webhook payload."""
    from database import SessionLocal

    # Create new session for background task
    db_session = SessionLocal()

    try:
        service = get_calendar_sync_service(db_session)

        for record in changed_records:
            record_id = record.get("Id")
            owner_id = record.get("OwnerId")

            if not record_id:
                continue

            # Find CRM user by SF owner ID
            user_id = None
            if owner_id:
                from salesforce_integration_models import IntegrationProfile
                profile = db_session.query(IntegrationProfile).filter(
                    IntegrationProfile.sf_user_id == owner_id,
                    IntegrationProfile.status == "active"
                ).first()
                if profile:
                    user_id = profile.user_id

            if not user_id:
                logger.warning(f"Could not find CRM user for SF owner {owner_id}")
                continue

            try:
                if change_type == "DELETE":
                    # Handle deletion
                    settings = service.get_settings(user_id)
                    await service._handle_sf_delete(user_id, record_id, settings)
                else:
                    # CREATE or UPDATE - pull the event
                    await service.pull_single_event(user_id, record_id)

                logger.info(f"Processed CDC {change_type} for SF event {record_id}")

            except Exception as e:
                logger.error(f"Error processing CDC record {record_id}: {e}")

    except Exception as e:
        logger.exception(f"Error in CDC webhook background processing: {e}")
    finally:
        db_session.close()


async def _full_sync_background(user_id: int, db: Session):
    """Background task for full bidirectional sync."""
    from database import SessionLocal

    # Create new session for background task
    db_session = SessionLocal()

    try:
        service = get_calendar_sync_service(db_session)

        # Step 1: Push all pending CRM events
        logger.info(f"Full sync: pushing pending events for user {user_id}")
        pending = service.get_events(user_id=user_id, sync_status=SyncStatus.PENDING.value)
        for event in pending:
            try:
                await push_event_to_salesforce(event.id)
            except Exception as e:
                logger.error(f"Full sync push error for {event.id}: {e}")

        # Step 2: Pull all events from Salesforce (last 30 days)
        logger.info(f"Full sync: pulling events from Salesforce for user {user_id}")
        since = datetime.utcnow() - timedelta(days=30)
        await service.pull_events_from_salesforce(
            user_id=user_id,
            since=since,
            limit=500
        )

        logger.info(f"Full sync completed for user {user_id}")

    except Exception as e:
        logger.exception(f"Error in full sync background: {e}")
    finally:
        db_session.close()


def _verify_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify Salesforce webhook signature."""
    import hmac
    import hashlib
    import base64

    if not signature:
        return False

    try:
        expected = hmac.new(
            secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).digest()
        expected_b64 = base64.b64encode(expected).decode('utf-8')
        return hmac.compare_digest(signature, expected_b64)
    except Exception as e:
        logger.error(f"Error verifying Nylas webhook signature: {e}")
        return False
