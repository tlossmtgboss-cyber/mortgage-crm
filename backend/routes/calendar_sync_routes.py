"""
Calendar Sync & Integration Routes
Consolidated from:
  - routes/calendar_sync_routes.py (Salesforce sync - /api/calendar/)
  - routes/calendar_routes.py (CalendarEvent CRUD + CalendarAssignment CRUD)
  - routes/google_calendar_routes.py (Google Calendar OAuth + events)
  - routes/unified_calendar_routes.py (merged calendar view)

URL prefixes:
  - /api/calendar/ (Salesforce sync - preserved for backward compat)
  - /api/v1/calendar/ (CalendarEvent CRUD, unified view)
  - /api/v1/calendar-assignments/ (CalendarAssignment CRUD)
  - /api/v1/users/with-calendars (users query)
  - /api/v1/google-calendar/ (Google Calendar OAuth)
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Callable
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, Field

from database import get_db
from db import get_db as db_get_db
from encryption_utils import encrypt_value, decrypt_value

logger = logging.getLogger(__name__)


def _safe_decrypt(value: str) -> str:
    """Decrypt a value, falling back to plaintext for pre-encryption data.

    During the migration period, existing rows may still contain unencrypted
    tokens.  Fernet ciphertexts are base64-encoded and always longer than ~120
    characters, so a short value is almost certainly a raw OAuth token and can
    be returned as-is.
    """
    if not value:
        return value
    try:
        return decrypt_value(value)
    except Exception:
        # Value is not a valid Fernet token — treat as plaintext (pre-migration)
        logger.debug("Token appears to be plaintext (pre-encryption migration); returning as-is")
        return value


# ============================================================================
# ROUTERS
# ============================================================================

# Salesforce sync router - keeps /api/calendar/ prefix for backward compat
sf_sync_router = APIRouter(prefix="/api/calendar", tags=["Calendar Sync"])

# Calendar events & unified view router
calendar_v1_router = APIRouter(tags=["Calendar"])

# Google Calendar router
google_calendar_router = APIRouter(prefix="/api/v1/google-calendar", tags=["google-calendar"])

# Combined router that includes all sub-routers
router = APIRouter()


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

# Google Calendar dependency injection placeholders
_google_get_db: Optional[Callable] = None
_google_get_current_user: Optional[Callable] = None


def set_dependencies(get_db_func: Callable = None, get_current_user_func: Callable = None):
    """Set dependencies for Google Calendar routes at runtime from main.py."""
    global _google_get_db, _google_get_current_user
    if get_db_func:
        _google_get_db = get_db_func
    if get_current_user_func:
        _google_get_current_user = get_current_user_func


def _google_get_db_dep():
    """Get database session for Google Calendar routes."""
    if _google_get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _google_get_db()


async def _google_get_current_user_dep(request: Request, db: Session = Depends(_google_get_db_dep)):
    """Get current user for Google Calendar routes.
    Supports token from Authorization header OR query parameter (for browser redirect flows like OAuth initiation).
    """
    if _google_get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    # Fallback: token from query param (for window.location.href OAuth initiation)
    if not token:
        token = request.query_params.get("token", "")
    return await _google_get_current_user(token=token, request=request, db=db)


# Runtime imports for calendar events/assignments
def _get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'CalendarEvent': main.CalendarEvent,
        'CalendarAssignment': main.CalendarAssignment,
    }


def _get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


def _get_org_id(user) -> int:
    """Extract and validate organization_id from authenticated user."""
    org_id = getattr(user, 'organization_id', None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    return org_id


# ============================================================================
# ============================================================================
# SECTION 1: SALESFORCE CALENDAR SYNC (from calendar_sync_routes.py)
# Prefix: /api/calendar/
# ============================================================================
# ============================================================================

# --- Pydantic Models for Salesforce Sync ---

class AttendeeModel(BaseModel):
    email: str
    name: Optional[str] = None
    status: Optional[str] = "pending"


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


class PullRequest(BaseModel):
    since: Optional[datetime] = None
    limit: int = Field(200, ge=1, le=500)


class CDCWebhookPayload(BaseModel):
    """Salesforce CDC webhook payload structure."""
    changeType: str
    entityName: str
    changedRecords: List[dict] = []
    replayId: Optional[int] = None


def _sf_get_current_user_dep():
    """Get centralized auth dependency at runtime for SF sync routes."""
    import main
    return main.get_current_user


def _sf_event_to_response(event) -> EventResponse:
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


# --- SF Sync Event CRUD ---

@sf_sync_router.get("/events", response_model=List[EventResponse])
async def sf_list_events(
    start_date: Optional[datetime] = Query(None, description="Filter by start date >="),
    end_date: Optional[datetime] = Query(None, description="Filter by start date <="),
    status: Optional[str] = Query(None, description="Filter by status"),
    sync_status: Optional[str] = Query(None, description="Filter by sync status"),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """List calendar events for the current user, scoped to their organization."""
    try:
        from models.calendar_sync_models import SyncStatus as SyncStatusEnum
        from services.calendar_sync_service import get_calendar_sync_service

        org_id = _get_org_id(current_user)
        service = get_calendar_sync_service(db)

        events = service.get_events(
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
            status=status,
            sync_status=sync_status,
            limit=limit,
            organization_id=org_id
        )

        return [_sf_event_to_response(e) for e in events]
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error fetching calendar events: {e}")
        return []


@sf_sync_router.post("/events", response_model=EventResponse, status_code=201)
async def sf_create_event(
    event_data: EventCreateRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Create a new calendar event. Auto-synced to Salesforce."""
    from services.calendar_sync_service import get_calendar_sync_service

    org_id = _get_org_id(current_user)
    service = get_calendar_sync_service(db)

    if event_data.end_at <= event_data.start_at:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    event = service.create_event(
        user_id=current_user.id,
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

    background_tasks.add_task(_sf_sync_event_background, event.id)
    logger.info(f"Created calendar event: {event.id}")
    return _sf_event_to_response(event)


@sf_sync_router.get("/events/{event_id}", response_model=EventResponse)
async def sf_get_event(
    event_id: str,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get a single calendar event by ID."""
    from services.calendar_sync_service import get_calendar_sync_service

    org_id = _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    event = service.get_event(event_id, current_user.id, organization_id=org_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return _sf_event_to_response(event)


@sf_sync_router.put("/events/{event_id}", response_model=EventResponse)
async def sf_update_event(
    event_id: str,
    updates: EventUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Update a calendar event. Changes synced to Salesforce."""
    from models.calendar_sync_models import SyncStatus as SyncStatusEnum
    from services.calendar_sync_service import get_calendar_sync_service

    org_id = _get_org_id(current_user)
    service = get_calendar_sync_service(db)

    update_dict = {}
    for field, value in updates.model_dump().items():
        if value is not None:
            if field == "attendees":
                update_dict[field] = [a if isinstance(a, dict) else a.model_dump() for a in value]
            else:
                update_dict[field] = value

    if "start_at" in update_dict and "end_at" in update_dict:
        if update_dict["end_at"] <= update_dict["start_at"]:
            raise HTTPException(status_code=400, detail="End time must be after start time")

    event = service.update_event(event_id, current_user.id, update_dict, auto_sync=True, organization_id=org_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.sync_status == SyncStatusEnum.PENDING.value:
        background_tasks.add_task(_sf_sync_event_background, event.id)

    return _sf_event_to_response(event)


@sf_sync_router.delete("/events/{event_id}")
async def sf_delete_event(
    event_id: str,
    background_tasks: BackgroundTasks,
    hard_delete: bool = Query(False, description="Hard delete instead of cancel"),
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Cancel or delete a calendar event."""
    from services.calendar_sync_service import get_calendar_sync_service

    org_id = _get_org_id(current_user)
    service = get_calendar_sync_service(db)

    if hard_delete:
        event = service.get_event(event_id, current_user.id, organization_id=org_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        db.delete(event)
        db.commit()
        return {"status": "deleted", "event_id": event_id}
    else:
        event = service.cancel_event(event_id, current_user.id, auto_sync=True, organization_id=org_id)
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        background_tasks.add_task(_sf_sync_event_background, event.id)
        return {"status": "canceled", "event_id": event_id}


@sf_sync_router.post("/events/{event_id}/resync")
async def sf_resync_event(
    event_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Force resync an event to Salesforce."""
    from models.calendar_sync_models import SyncStatus as SyncStatusEnum
    from services.calendar_sync_service import get_calendar_sync_service

    org_id = _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    event = service.get_event(event_id, current_user.id, organization_id=org_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.sync_status = SyncStatusEnum.PENDING.value
    event.sync_error = None
    db.commit()

    background_tasks.add_task(_sf_sync_event_background, event.id)
    return {"status": "queued", "event_id": event_id, "message": "Event queued for resync to Salesforce"}


# --- SF Sync Management ---

@sf_sync_router.get("/sync/status", response_model=SyncStatusResponse)
async def sf_get_sync_status(
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get calendar sync status for the current user."""
    from services.calendar_sync_service import get_calendar_sync_service

    _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    status_data = service.get_sync_status(current_user.id)
    return SyncStatusResponse(**status_data)


@sf_sync_router.post("/sync/trigger")
async def sf_trigger_sync(
    background_tasks: BackgroundTasks,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Trigger manual sync of all pending events."""
    from models.calendar_sync_models import SyncStatus as SyncStatusEnum
    from services.calendar_sync_service import get_calendar_sync_service

    org_id = _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    pending = service.get_events(user_id=current_user.id, sync_status=SyncStatusEnum.PENDING.value, organization_id=org_id)
    if not pending:
        return {"status": "no_pending", "message": "No pending events to sync"}
    for event in pending:
        background_tasks.add_task(_sf_sync_event_background, event.id)
    return {"status": "queued", "events_queued": len(pending), "message": f"Queued {len(pending)} events for sync"}


@sf_sync_router.get("/sync/history")
async def sf_get_sync_history(
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get sync history for the current user."""
    from services.calendar_sync_service import get_calendar_sync_service

    _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    history = service.get_sync_history(current_user.id, limit)
    return {"history": history}


@sf_sync_router.get("/sync/failures")
async def sf_get_sync_failures(
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get events that failed to sync."""
    from services.calendar_sync_service import get_calendar_sync_service

    _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    failed = service.get_failed_events(current_user.id)
    return {"count": len(failed), "events": [_sf_event_to_response(e) for e in failed]}


@sf_sync_router.get("/sync/health")
async def sf_get_sync_health(
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get overall calendar sync health metrics."""
    from tasks.calendar_sync_tasks import check_sync_health

    _get_org_id(current_user)
    health = await check_sync_health()
    return health


# --- SF Sync Pull Endpoints ---

@sf_sync_router.post("/sync/pull")
async def sf_pull_events(
    pull_request: Optional[PullRequest] = None,
    background_tasks: BackgroundTasks = None,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Pull events from Salesforce into CRM."""
    from services.calendar_sync_service import get_calendar_sync_service

    _get_org_id(current_user)
    service = get_calendar_sync_service(db)

    since = pull_request.since if pull_request else None
    limit = pull_request.limit if pull_request else 200

    if not since:
        settings = service.get_settings(current_user.id)
        since = settings.last_poll_watermark

    result = await service.pull_events_from_salesforce(
        user_id=current_user.id, since=since, limit=limit
    )

    return {
        "status": "completed",
        "pulled": result["pulled"],
        "created": result["created"],
        "updated": result["updated"],
        "skipped_echo": result["skipped_echo"],
        "skipped_conflict": result["skipped_conflict"],
        "errors": result["errors"][:10] if result["errors"] else []
    }


@sf_sync_router.post("/sync/pull/{salesforce_event_id}")
async def sf_pull_single_event(
    salesforce_event_id: str,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Pull a single event from Salesforce by ID."""
    from services.calendar_sync_service import get_calendar_sync_service

    _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    result = await service.pull_single_event(user_id=current_user.id, salesforce_event_id=salesforce_event_id)

    if result.success:
        return {
            "status": "success", "action": result.operation,
            "crm_event_id": result.crm_event_id, "salesforce_event_id": result.salesforce_event_id
        }
    else:
        raise HTTPException(status_code=400, detail=result.error)


@sf_sync_router.post("/webhook/cdc")
async def sf_cdc_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Salesforce CDC webhook endpoint for real-time event sync.

    Per-organization validation:
    - Extracts the Salesforce org ID from the CDC payload
    - Looks up the IntegrationProfile matching that sf_org_id
    - Verifies the webhook signature against the org-specific secret
      (falls back to global SALESFORCE_CDC_WEBHOOK_SECRET for backward compat)
    - Validates the user's CRM organization has an active Salesforce integration
    """
    body = await request.body()
    signature = request.headers.get("X-Salesforce-Signature")

    # Parse payload first so we can identify the Salesforce org for per-org secret lookup
    try:
        import json
        payload = json.loads(body)
    except Exception as e:
        logger.error(f"Failed to parse CDC webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    change_event_header = payload.get("ChangeEventHeader", {})
    change_type = payload.get("changeType") or change_event_header.get("changeType")
    entity_name = payload.get("entityName") or change_event_header.get("entityName", "").replace("ChangeEvent", "")

    # Extract the Salesforce org ID from the CDC payload for per-org validation
    sf_org_id = change_event_header.get("organizationId") or payload.get("organizationId")

    # Look up per-org webhook secret from the IntegrationProfile
    org_webhook_secret = None
    matched_profile = None
    if sf_org_id:
        from salesforce_integration_models import IntegrationProfile
        matched_profile = db.query(IntegrationProfile).filter(
            IntegrationProfile.sf_org_id == sf_org_id,
            IntegrationProfile.status == "active",
            IntegrationProfile.provider == "salesforce",
        ).first()
        if matched_profile and matched_profile.cdc_webhook_secret:
            org_webhook_secret = matched_profile.cdc_webhook_secret

    # Determine which secret to use: per-org takes priority, then global fallback
    global_webhook_secret = os.getenv("SALESFORCE_CDC_WEBHOOK_SECRET")
    effective_secret = org_webhook_secret or global_webhook_secret

    if not effective_secret:
        logger.error("No CDC webhook secret configured (neither per-org nor global)")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    # Verify the HMAC signature against the effective secret
    if not _verify_webhook_signature(body, signature, effective_secret):
        # If we used an org-specific secret, also try the global as fallback
        # (handles the transition period when org secrets are being rolled out)
        if org_webhook_secret and global_webhook_secret and org_webhook_secret != global_webhook_secret:
            if not _verify_webhook_signature(body, signature, global_webhook_secret):
                logger.warning(f"Invalid CDC webhook signature for sf_org_id={sf_org_id}")
                raise HTTPException(status_code=401, detail="Invalid signature")
        else:
            logger.warning(f"Invalid CDC webhook signature for sf_org_id={sf_org_id}")
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Validate that the Salesforce org is associated with a known CRM organization
    validated_org_id = None
    if sf_org_id:
        if not matched_profile:
            logger.warning(
                f"CDC webhook from unknown Salesforce org {sf_org_id} - "
                "no active IntegrationProfile found, rejecting"
            )
            raise HTTPException(status_code=403, detail="Unknown Salesforce organization")

        # Resolve the CRM organization_id via the user linked to this IntegrationProfile
        from database.models.core import User
        profile_user = db.query(User).filter(User.id == matched_profile.user_id).first()
        if not profile_user or not profile_user.organization_id:
            logger.warning(
                f"CDC webhook: IntegrationProfile user_id={matched_profile.user_id} "
                f"has no CRM organization, rejecting sf_org_id={sf_org_id}"
            )
            raise HTTPException(status_code=403, detail="Integration user has no organization")
        validated_org_id = profile_user.organization_id
    else:
        logger.warning("CDC webhook payload missing organizationId - cannot validate org")
        raise HTTPException(status_code=400, detail="Missing organizationId in CDC payload")

    logger.info(
        f"Received CDC webhook: {change_type} on {entity_name} "
        f"from sf_org_id={sf_org_id} (crm_org={validated_org_id})"
    )

    if entity_name != "Event":
        return {"status": "ignored", "reason": "not_event_object"}

    changed_records = payload.get("changedRecords", [])
    if not changed_records:
        record_ids = change_event_header.get("recordIds", [])
        changed_records = [{"Id": rid} for rid in record_ids]

    if not changed_records:
        return {"status": "ignored", "reason": "no_records"}

    background_tasks.add_task(
        _sf_process_cdc_background, change_type, changed_records, db, validated_org_id
    )

    return {"status": "accepted", "change_type": change_type, "record_count": len(changed_records)}


@sf_sync_router.post("/sync/full")
async def sf_trigger_full_sync(
    background_tasks: BackgroundTasks,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Trigger a full bidirectional sync."""
    _get_org_id(current_user)
    background_tasks.add_task(_sf_full_sync_background, current_user.id, db)
    return {"status": "queued", "message": "Full bidirectional sync queued"}


# --- SF Sync Settings ---

@sf_sync_router.get("/settings")
async def sf_get_settings(
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Get calendar sync settings."""
    from services.calendar_sync_service import get_calendar_sync_service

    _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    settings = service.get_settings(current_user.id)
    return settings.to_dict()


@sf_sync_router.put("/settings")
async def sf_update_settings(
    settings_update: SyncSettingsRequest,
    current_user=Depends(_sf_get_current_user_dep()),
    db: Session = Depends(get_db)
):
    """Update calendar sync settings."""
    from services.calendar_sync_service import get_calendar_sync_service

    _get_org_id(current_user)
    service = get_calendar_sync_service(db)
    update_dict = {k: v for k, v in settings_update.model_dump().items() if v is not None}
    settings = service.update_settings(current_user.id, update_dict)
    return settings.to_dict()


# --- SF Sync Helper Functions ---

async def _sf_sync_event_background(event_id: str):
    """Background task to sync event to Salesforce."""
    try:
        from tasks.calendar_sync_tasks import push_event_to_salesforce
        result = await push_event_to_salesforce(event_id)
        if result.get("success"):
            logger.info(f"Background sync successful for event {event_id}")
        else:
            logger.warning(f"Background sync failed for event {event_id}: {result.get('error')}")
    except Exception as e:
        logger.exception(f"Background sync error for event {event_id}: {e}")


async def _sf_process_cdc_background(
    change_type: str,
    changed_records: List[dict],
    db: Session,
    validated_org_id: Optional[int] = None,
):
    """Background task to process CDC webhook payload.

    Args:
        change_type: CDC change type (CREATE, UPDATE, DELETE, etc.)
        changed_records: List of changed record dicts from the CDC payload
        db: Database session (not used directly; a fresh session is created)
        validated_org_id: The CRM organization_id validated at webhook entry.
            When set, only records belonging to users in this org are processed.
    """
    from database import SessionLocal
    from services.calendar_sync_service import get_calendar_sync_service

    db_session = SessionLocal()
    try:
        service = get_calendar_sync_service(db_session)
        for record in changed_records:
            record_id = record.get("Id")
            owner_id = record.get("OwnerId")
            if not record_id:
                continue

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

            # Per-organization validation: verify the resolved user belongs
            # to the same CRM organization that was validated at webhook entry
            if validated_org_id is not None:
                from database.models.core import User
                record_user = db_session.query(User).filter(User.id == user_id).first()
                if not record_user or record_user.organization_id != validated_org_id:
                    logger.warning(
                        f"CDC record {record_id}: user {user_id} belongs to "
                        f"org {getattr(record_user, 'organization_id', None)}, "
                        f"expected org {validated_org_id} - skipping cross-org event"
                    )
                    continue

            try:
                if change_type == "DELETE":
                    settings = service.get_settings(user_id)
                    await service._handle_sf_delete(user_id, record_id, settings)
                else:
                    await service.pull_single_event(user_id, record_id)
                logger.info(f"Processed CDC {change_type} for SF event {record_id}")
            except Exception as e:
                logger.error(f"Error processing CDC record {record_id}: {e}")
    except Exception as e:
        logger.exception(f"Error in CDC webhook background processing: {e}")
    finally:
        db_session.close()


async def _sf_full_sync_background(user_id: int, db: Session):
    """Background task for full bidirectional sync."""
    from database import SessionLocal
    from models.calendar_sync_models import SyncStatus as SyncStatusEnum
    from services.calendar_sync_service import get_calendar_sync_service
    from tasks.calendar_sync_tasks import push_event_to_salesforce

    db_session = SessionLocal()
    try:
        service = get_calendar_sync_service(db_session)

        logger.info(f"Full sync: pushing pending events for user {user_id}")
        pending = service.get_events(user_id=user_id, sync_status=SyncStatusEnum.PENDING.value)
        for event in pending:
            try:
                await push_event_to_salesforce(event.id)
            except Exception as e:
                logger.error(f"Full sync push error for {event.id}: {e}")

        logger.info(f"Full sync: pulling events from Salesforce for user {user_id}")
        since = datetime.now(timezone.utc) - timedelta(days=30)
        await service.pull_events_from_salesforce(user_id=user_id, since=since, limit=500)
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
        expected = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).digest()
        expected_b64 = base64.b64encode(expected).decode('utf-8')
        return hmac.compare_digest(signature, expected_b64)
    except Exception as e:
        logger.error(f"Error verifying Salesforce webhook signature: {e}")
        return False


# ============================================================================
# ============================================================================
# SECTION 2: CALENDAR EVENTS CRUD (from calendar_routes.py)
# Prefix: /api/v1/calendar/events
# ============================================================================
# ============================================================================

# --- Pydantic Schemas ---

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


# --- Calendar Event CRUD ---

@calendar_v1_router.post("/api/v1/calendar/events", response_model=CalendarEventResponse, status_code=201)
async def create_calendar_event(
    event: CalendarEventCreate,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Create a new calendar event"""
    models = _get_models()
    CalendarEvent = models['CalendarEvent']

    org_id = _get_org_id(current_user)
    db_event = CalendarEvent(
        **event.model_dump(exclude={'attendees'}),
        user_id=current_user.id,
        organization_id=org_id,
        attendees=event.attendees if event.attendees else []
    )

    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    logger.info(f"Calendar event created: {db_event.title}")
    return db_event


@calendar_v1_router.get("/api/v1/calendar/events", response_model=List[CalendarEventResponse])
async def get_calendar_events(
    skip: int = 0,
    limit: int = 100,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Get calendar events with optional date filtering"""
    models = _get_models()
    CalendarEvent = models['CalendarEvent']

    query = db.query(CalendarEvent).filter(CalendarEvent.user_id == current_user.id)
    if start_date:
        query = query.filter(CalendarEvent.start_time >= start_date)
    if end_date:
        query = query.filter(CalendarEvent.start_time <= end_date)

    events = query.order_by(CalendarEvent.start_time).offset(skip).limit(limit).all()
    return events


@calendar_v1_router.get("/api/v1/calendar/events/{event_id}", response_model=CalendarEventResponse)
async def get_calendar_event(
    event_id: int,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Get a specific calendar event"""
    models = _get_models()
    CalendarEvent = models['CalendarEvent']
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id, CalendarEvent.user_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@calendar_v1_router.patch("/api/v1/calendar/events/{event_id}", response_model=CalendarEventResponse)
async def update_calendar_event(
    event_id: int,
    event_update: CalendarEventUpdate,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Update a calendar event"""
    models = _get_models()
    CalendarEvent = models['CalendarEvent']
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id, CalendarEvent.user_id == current_user.id
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


@calendar_v1_router.delete("/api/v1/calendar/events/{event_id}", status_code=204)
async def delete_calendar_event(
    event_id: int,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Delete a calendar event"""
    models = _get_models()
    CalendarEvent = models['CalendarEvent']
    event = db.query(CalendarEvent).filter(
        CalendarEvent.id == event_id, CalendarEvent.user_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()
    logger.info(f"Calendar event deleted: {event.title}")
    return None


# ============================================================================
# SECTION 3: CALENDAR ASSIGNMENTS (from calendar_routes.py)
# ============================================================================

CALENDAR_PURPOSES = [
    {"purpose": "purchase_application", "label": "Purchase Application Scheduling"},
    {"purpose": "refinance_application", "label": "Refinance Application Scheduling"},
    {"purpose": "lead_consultation", "label": "Lead Consultation"},
    {"purpose": "document_review", "label": "Document Review Call"},
    {"purpose": "closing_call", "label": "Closing Preparation Call"},
    {"purpose": "general_appointment", "label": "General Appointment"},
    {"purpose": "website_demo", "label": "Website Demo Scheduler"},
]


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


@calendar_v1_router.get("/api/v1/calendar-assignments/purposes")
async def get_calendar_purposes():
    """Get list of all calendar purposes that can be assigned"""
    return CALENDAR_PURPOSES


@calendar_v1_router.get("/api/v1/calendar-assignments", response_model=List[CalendarAssignmentResponse])
async def get_calendar_assignments(
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Get all calendar assignments for the organization"""
    models = _get_models()
    User = models['User']
    CalendarAssignment = models['CalendarAssignment']

    assignments = db.query(CalendarAssignment).filter(
        or_(
            CalendarAssignment.organization_id == current_user.organization_id,
            CalendarAssignment.organization_id == None
        )
    ).all()

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
                row = db.execute(
                    text("SELECT slug, link_name FROM scheduler_booking_links WHERE id = :id AND is_active = true"),
                    {"id": assignment.booking_link_id}
                ).fetchone()
                if row:
                    data["booking_link_slug"] = row[0]
                    data["booking_link_name"] = row[1]
            except Exception as e:
                logger.error(f"Error fetching booking link for assignment: {e}")
        result.append(data)

    return result


@calendar_v1_router.get("/api/v1/calendar-assignments/{purpose}")
async def get_calendar_assignment_by_purpose(
    purpose: str,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Get calendar assignment for a specific purpose."""
    models = _get_models()
    User = models['User']
    CalendarAssignment = models['CalendarAssignment']

    org_id = _get_org_id(current_user)

    assignment = db.query(CalendarAssignment).filter(
        CalendarAssignment.purpose == purpose,
        CalendarAssignment.is_active == True,
        or_(
            CalendarAssignment.organization_id == org_id,
            CalendarAssignment.organization_id == None
        )
    ).first()

    if not assignment:
        return {"purpose": purpose, "has_assignment": False, "booking_link_url": None, "calendly_url": None}

    result = {
        "purpose": purpose, "has_assignment": True,
        "booking_link_url": None, "calendly_url": assignment.calendly_url,
        "assigned_user_first_name": None,
    }

    if assignment.assigned_user_id:
        user = db.query(User).filter(User.id == assignment.assigned_user_id).first()
        if user:
            result["assigned_user_first_name"] = getattr(user, 'first_name', None)
            try:
                from routes.calendly_routes import get_calendly_integration_for_user
                calendly = get_calendly_integration_for_user(db, assignment.assigned_user_id)
                if calendly and calendly.get("scheduling_url"):
                    result["calendly_url"] = calendly["scheduling_url"]
            except Exception as e:
                logger.error(f"Error fetching Calendly integration for user: {e}")

    if assignment.booking_link_id:
        try:
            row = db.execute(
                text("SELECT slug FROM scheduler_booking_links WHERE id = :id AND is_active = true"),
                {"id": assignment.booking_link_id}
            ).fetchone()
            if row:
                result["booking_link_url"] = f"/book/{row[0]}"
        except Exception as e:
            logger.error(f"Error fetching booking link slug: {e}")

    return result


@calendar_v1_router.post("/api/v1/calendar-assignments", response_model=CalendarAssignmentResponse, status_code=201)
async def create_calendar_assignment(
    assignment_data: CalendarAssignmentCreate,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Create a new calendar assignment"""
    models = _get_models()
    User = models['User']
    CalendarAssignment = models['CalendarAssignment']

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

    assigned_user_name = None
    if assignment.assigned_user_id:
        user = db.query(User).filter(User.id == assignment.assigned_user_id).first()
        if user:
            assigned_user_name = user.full_name

    logger.info(f"Calendar assignment created: {assignment.purpose} -> user {assignment.assigned_user_id}")
    return {**assignment.__dict__, "assigned_user_name": assigned_user_name}


@calendar_v1_router.put("/api/v1/calendar-assignments/{assignment_id}", response_model=CalendarAssignmentResponse)
async def update_calendar_assignment(
    assignment_id: int,
    assignment_data: CalendarAssignmentUpdate,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Update a calendar assignment"""
    models = _get_models()
    User = models['User']
    CalendarAssignment = models['CalendarAssignment']

    assignment = db.query(CalendarAssignment).filter(
        CalendarAssignment.id == assignment_id,
        CalendarAssignment.organization_id == current_user.organization_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

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

    assigned_user_name = None
    if assignment.assigned_user_id:
        user = db.query(User).filter(User.id == assignment.assigned_user_id).first()
        if user:
            assigned_user_name = user.full_name

    logger.info(f"Calendar assignment updated: {assignment.purpose}")
    return {**assignment.__dict__, "assigned_user_name": assigned_user_name}


@calendar_v1_router.delete("/api/v1/calendar-assignments/{assignment_id}", status_code=204)
async def delete_calendar_assignment(
    assignment_id: int,
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Delete a calendar assignment"""
    models = _get_models()
    CalendarAssignment = models['CalendarAssignment']

    assignment = db.query(CalendarAssignment).filter(
        CalendarAssignment.id == assignment_id,
        CalendarAssignment.organization_id == current_user.organization_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()
    logger.info(f"Calendar assignment deleted: {assignment.purpose}")
    return None


@calendar_v1_router.get("/api/v1/users/with-calendars")
async def get_users_with_calendars(
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep())
):
    """Get list of users who can receive calendar appointments"""
    models = _get_models()
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
            "id": user.id, "name": user.full_name,
            "email": user.email, "role": user.role,
            "has_calendly": False, "calendly_url": None
        }
        try:
            from routes.calendly_routes import get_calendly_integration_for_user
            calendly = get_calendly_integration_for_user(db, user.id)
            if calendly:
                user_data["has_calendly"] = True
                user_data["calendly_url"] = calendly.get("scheduling_url")
        except Exception as e:
            logger.error(f"Error checking Calendly integration for user {user.id}: {e}")
        result.append(user_data)

    return result


# ============================================================================
# ============================================================================
# SECTION 4: UNIFIED CALENDAR (from unified_calendar_routes.py)
# Prefix: /api/v1/calendar/unified
# ============================================================================
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
    source: str
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


@calendar_v1_router.get("/api/v1/calendar/unified", response_model=UnifiedCalendarResponse)
async def get_unified_calendar(
    start_date: str = Query(..., description="Start date (ISO format)"),
    end_date: str = Query(..., description="End date (ISO format)"),
    include_cancelled: bool = Query(False, description="Include cancelled events"),
    db: Session = Depends(db_get_db),
    current_user=Depends(_get_current_user_dep()),
):
    """
    Get unified calendar events from all sources.
    Merges events from calendar events, scheduled appointments, and CRM events.
    """
    try:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid start_date format: {start_date}. Use ISO format.")

        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid end_date format: {end_date}. Use ISO format.")

        if end_dt < start_dt:
            raise HTTPException(status_code=400, detail="end_date must be after start_date")

        from services.unified_calendar_service import get_unified_calendar_service

        org_id = getattr(current_user, 'organization_id', None)
        if not org_id:
            raise HTTPException(status_code=403, detail="No organization context")
        service = get_unified_calendar_service(db, current_user.id, organization_id=org_id)
        result = service.get_unified_events(start_date=start_dt, end_date=end_dt, include_cancelled=include_cancelled)

        logger.info(f"Unified calendar: {result['total_count']} events from {result['sources_queried']} for user {current_user.id}")
        return UnifiedCalendarResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unified calendar error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch unified calendar")


# ============================================================================
# ============================================================================
# SECTION 5: GOOGLE CALENDAR (from google_calendar_routes.py)
# Prefix: /api/v1/google-calendar/
# ============================================================================
# ============================================================================

# Allowlisted redirect URL prefixes for OAuth callback security
_ALLOWED_REDIRECT_PREFIXES = None


def _get_allowed_redirect_prefixes():
    """Get allowed redirect prefixes from environment."""
    global _ALLOWED_REDIRECT_PREFIXES
    if _ALLOWED_REDIRECT_PREFIXES is None:
        frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
        app_url = os.getenv("APP_URL", "https://app.perenniaai.com")
        _ALLOWED_REDIRECT_PREFIXES = [frontend_url, app_url]
    return _ALLOWED_REDIRECT_PREFIXES


def _is_safe_redirect(url: str) -> bool:
    """Validate that a redirect URL is on an allowed domain."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return False
        for prefix in _get_allowed_redirect_prefixes():
            if url.startswith(prefix):
                return True
        return False
    except Exception:
        return False


@google_calendar_router.get("/auth")
async def google_calendar_auth(
    request: Request,
    current_user=Depends(_google_get_current_user_dep)
):
    """Initiate Google Calendar OAuth flow"""
    from integrations.google_calendar_service import google_calendar_client
    import hashlib
    import hmac

    if not google_calendar_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar integration not configured"
        )

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
    redirect_url = f"{frontend_url}/settings/integrations"

    secret_key = os.getenv("SECRET_KEY", "")
    state_data = f"{user_id}:{redirect_url}"
    state_sig = hmac.new(secret_key.encode(), state_data.encode(), hashlib.sha256).hexdigest()[:16]
    state = f"{user_id}:{state_sig}:{redirect_url}"

    auth_url = google_calendar_client.get_authorization_url(state=state)
    return RedirectResponse(url=auth_url)


@google_calendar_router.get("/auth-url")
async def google_calendar_auth_url(
    request: Request,
    current_user=Depends(_google_get_current_user_dep)
):
    """Return Google Calendar OAuth URL as JSON (avoids putting JWT in URL query params).

    The frontend calls this via fetch() with an Authorization header, then navigates
    the popup to the returned auth_url. This keeps the JWT out of browser history,
    server logs, and Referer headers.
    """
    from integrations.google_calendar_service import google_calendar_client
    import hashlib
    import hmac

    if not google_calendar_client.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Calendar integration not configured"
        )

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
    redirect_url = f"{frontend_url}/settings/integrations"

    secret_key = os.getenv("SECRET_KEY", "")
    state_data = f"{user_id}:{redirect_url}"
    state_sig = hmac.new(secret_key.encode(), state_data.encode(), hashlib.sha256).hexdigest()[:16]
    state = f"{user_id}:{state_sig}:{redirect_url}"

    auth_url = google_calendar_client.get_authorization_url(state=state)
    return {"auth_url": auth_url}


@google_calendar_router.get("/callback")
async def google_calendar_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from Google"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(_google_get_db_dep)
):
    """Handle OAuth callback from Google. Exchanges authorization code for access token."""
    frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")

    if error:
        logger.error(f"Google Calendar OAuth error: {error} - {error_description}")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=google_calendar_auth_failed&message={error_description or error}"
        )

    from integrations.google_calendar_service import google_calendar_client
    import hashlib
    import hmac as _hmac

    user_id = None
    redirect_url = None
    if state:
        parts = state.split(":", 2)
        try:
            user_id = int(parts[0])
        except (ValueError, IndexError):
            pass

        if user_id and len(parts) == 3:
            provided_sig = parts[1]
            claimed_redirect = parts[2]
            secret_key = os.getenv("SECRET_KEY", "")
            expected_data = f"{user_id}:{claimed_redirect}"
            expected_sig = _hmac.new(secret_key.encode(), expected_data.encode(), hashlib.sha256).hexdigest()[:16]
            if not _hmac.compare_digest(provided_sig, expected_sig):
                logger.error("Invalid CSRF signature in Google Calendar OAuth state")
                return RedirectResponse(url=f"{frontend_url}/settings/integrations?error=invalid_state")
            redirect_url = claimed_redirect
        elif user_id and len(parts) == 2:
            redirect_url = None
        else:
            user_id = None

    if redirect_url and not _is_safe_redirect(redirect_url):
        logger.warning(f"Blocked unsafe OAuth redirect URL: {redirect_url}")
        redirect_url = None

    if not user_id:
        logger.error("Invalid state parameter in Google Calendar callback")
        return RedirectResponse(url=f"{frontend_url}/settings/integrations?error=invalid_state")

    token_data = await google_calendar_client.exchange_code_for_token(code)
    if not token_data:
        logger.error("Failed to exchange Google Calendar authorization code")
        return RedirectResponse(url=f"{frontend_url}/settings/integrations?error=google_calendar_token_exchange_failed")

    user_info = await google_calendar_client.get_user_info(token_data["access_token"])
    user_email = user_info.get("email") if user_info else None

    try:
        result = db.execute(text("""
            SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_integrations')
        """))
        table_exists = result.scalar()

        if not table_exists:
            db.execute(text("""
                CREATE TABLE user_integrations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    access_token TEXT,
                    refresh_token TEXT,
                    expires_at TIMESTAMP,
                    scopes TEXT,
                    email VARCHAR(255),
                    provider_user_id VARCHAR(255),
                    instance_url TEXT,
                    extra_data JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, provider)
                )
            """))
            db.commit()

        db.execute(text("""
            INSERT INTO user_integrations
                (user_id, provider, access_token, refresh_token, expires_at, email, scopes, extra_data, updated_at)
            VALUES
                (:user_id, 'google_calendar', :access_token, :refresh_token, :expires_at, :email, :scopes,
                 jsonb_build_object('token_type', :token_type), CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                email = EXCLUDED.email,
                scopes = EXCLUDED.scopes,
                extra_data = EXCLUDED.extra_data,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "user_id": user_id,
            "access_token": encrypt_value(token_data.get("access_token")),
            "refresh_token": encrypt_value(token_data.get("refresh_token")),
            "expires_at": token_data.get("expires_at"),
            "email": user_email,
            "scopes": token_data.get("scope"),
            "token_type": token_data.get("token_type", "Bearer")
        })
        db.commit()
        logger.info(f"Successfully stored encrypted Google Calendar tokens for user {user_id}")

    except SQLAlchemyError as e:
        logger.error(f"Error storing Google Calendar tokens: {e}")
        db.rollback()
        return RedirectResponse(url=f"{frontend_url}/settings/integrations?error=google_calendar_storage_failed")

    return RedirectResponse(
        url=f"{redirect_url or frontend_url + '/settings/integrations'}?success=google_calendar_connected"
    )


@google_calendar_router.get("/status")
async def google_calendar_status(
    current_user=Depends(_google_get_current_user_dep),
    db: Session = Depends(_google_get_db_dep)
):
    """Check Google Calendar connection status"""
    from integrations.google_calendar_service import google_calendar_client
    try:
        from utils.responses import success_response
    except ImportError:
        success_response = lambda data, msg="": data

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = db.execute(text("""
            SELECT access_token, refresh_token, expires_at, email, scopes
            FROM user_integrations WHERE user_id = :user_id AND provider = 'google_calendar'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row:
            return success_response({"connected": False, "enabled": google_calendar_client.enabled})

        is_expired = False
        if row.expires_at:
            is_expired = datetime.now(timezone.utc) > row.expires_at

        return success_response({
            "connected": True, "enabled": google_calendar_client.enabled,
            "email": row.email, "scopes": row.scopes,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "is_expired": is_expired
        })
    except Exception as e:
        logger.error(f"Error checking Google Calendar status: {e}")
        return success_response({"connected": False, "enabled": google_calendar_client.enabled, "error": "Internal server error"})


@google_calendar_router.post("/refresh")
async def refresh_google_calendar_token(
    current_user=Depends(_google_get_current_user_dep),
    db: Session = Depends(_google_get_db_dep)
):
    """Refresh Google Calendar access token"""
    from integrations.google_calendar_service import google_calendar_client
    try:
        from utils.responses import success_response
    except ImportError:
        success_response = lambda data, msg="": data

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        result = db.execute(text("""
            SELECT refresh_token FROM user_integrations
            WHERE user_id = :user_id AND provider = 'google_calendar'
        """), {"user_id": user_id})
        row = result.fetchone()

        if not row or not row.refresh_token:
            raise HTTPException(status_code=404, detail="No Google Calendar connection found")

        decrypted_refresh_token = _safe_decrypt(row.refresh_token)
        token_data = await google_calendar_client.refresh_access_token(decrypted_refresh_token)
        if not token_data:
            raise HTTPException(status_code=500, detail="Failed to refresh token")

        db.execute(text("""
            UPDATE user_integrations
            SET access_token = :access_token, refresh_token = :refresh_token,
                expires_at = :expires_at, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id AND provider = 'google_calendar'
        """), {
            "user_id": user_id,
            "access_token": encrypt_value(token_data.get("access_token")),
            "refresh_token": encrypt_value(token_data.get("refresh_token")),
            "expires_at": token_data.get("expires_at")
        })
        db.commit()

        return success_response({"refreshed": True, "expires_at": token_data.get("expires_at")})

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error refreshing Google Calendar token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@google_calendar_router.post("/disconnect")
async def disconnect_google_calendar(
    current_user=Depends(_google_get_current_user_dep),
    db: Session = Depends(_google_get_db_dep)
):
    """Disconnect Google Calendar integration"""
    try:
        from utils.responses import success_response
    except ImportError:
        success_response = lambda data, msg="": data

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    try:
        db.execute(text("""
            DELETE FROM user_integrations WHERE user_id = :user_id AND provider = 'google_calendar'
        """), {"user_id": user_id})
        db.commit()
        return success_response({"disconnected": True}, "Google Calendar integration disconnected")
    except SQLAlchemyError as e:
        logger.error(f"Error disconnecting Google Calendar: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@google_calendar_router.get("/calendars")
async def list_google_calendars(
    current_user=Depends(_google_get_current_user_dep),
    db: Session = Depends(_google_get_db_dep)
):
    """List all calendars for the connected user"""
    from integrations.google_calendar_service import google_calendar_client
    try:
        from utils.responses import success_response
    except ImportError:
        success_response = lambda data, msg="": data

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    result = db.execute(text("""
        SELECT access_token, refresh_token, expires_at
        FROM user_integrations WHERE user_id = :user_id AND provider = 'google_calendar'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Google Calendar not connected")

    access_token = _safe_decrypt(row.access_token)

    if row.expires_at and datetime.now(timezone.utc) > row.expires_at:
        decrypted_refresh = _safe_decrypt(row.refresh_token)
        token_data = await google_calendar_client.refresh_access_token(decrypted_refresh)
        if token_data:
            access_token = token_data["access_token"]
            db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token, refresh_token = :refresh_token,
                    expires_at = :expires_at, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'google_calendar'
            """), {
                "user_id": user_id,
                "access_token": encrypt_value(token_data.get("access_token")),
                "refresh_token": encrypt_value(token_data.get("refresh_token")),
                "expires_at": token_data.get("expires_at")
            })
            db.commit()
        else:
            raise HTTPException(status_code=401, detail="Token expired and refresh failed")

    calendars = await google_calendar_client.list_calendars(access_token)
    if calendars is None:
        raise HTTPException(status_code=500, detail="Failed to fetch calendars from Google")
    return success_response(calendars)


@google_calendar_router.get("/events")
async def list_google_events(
    calendar_id: str = Query("primary", description="Calendar ID"),
    days: int = Query(30, description="Number of days to fetch events for"),
    current_user=Depends(_google_get_current_user_dep),
    db: Session = Depends(_google_get_db_dep)
):
    """List events from a Google calendar"""
    from integrations.google_calendar_service import google_calendar_client
    try:
        from utils.responses import success_response
    except ImportError:
        success_response = lambda data, msg="": data

    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

    result = db.execute(text("""
        SELECT access_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'google_calendar'
    """), {"user_id": user_id})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Google Calendar not connected")

    time_min = datetime.now(timezone.utc)
    time_max = datetime.now(timezone.utc) + timedelta(days=days)

    decrypted_access_token = _safe_decrypt(row.access_token)
    events = await google_calendar_client.list_events(
        decrypted_access_token, calendar_id=calendar_id,
        time_min=time_min, time_max=time_max
    )

    if events is None:
        raise HTTPException(status_code=500, detail="Failed to fetch events from Google Calendar")
    return success_response(events)


# ============================================================================
# INCLUDE SUB-ROUTERS INTO MAIN ROUTER
# ============================================================================

router.include_router(sf_sync_router)
router.include_router(calendar_v1_router)
router.include_router(google_calendar_router)
