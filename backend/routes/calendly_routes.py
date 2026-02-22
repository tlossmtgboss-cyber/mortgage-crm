"""
Calendly Integration API Routes

Provides endpoints for:
- OAuth flow (connect/disconnect Calendly)
- Integration settings management
- Availability queries
- Event type management
- Webhook handling
"""

import os
import json
import hmac
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from pydantic import BaseModel
from database import get_db, Base, engine

from sqlalchemy.exc import SQLAlchemyError
from services.calendly_service import (
    get_calendly_service,
    CalendlyService,
    encrypt_token,
    decrypt_token,
    availability_cache,
)

router = APIRouter()
logger = logging.getLogger(__name__)

CALENDLY_WEBHOOK_SECRET = os.getenv("CALENDLY_WEBHOOK_SECRET", "")


# =============================================================================
# AUTH DEPENDENCY
# =============================================================================

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_security = HTTPBearer(auto_error=False)


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
):
    """Get authenticated user. Rejects unauthenticated requests."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        from auth.dependencies import get_current_user_flexible
        user = await get_current_user_flexible(
            token=credentials.credentials, request=None, db=db
        )
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_current_user_from_token: {e}")
        raise HTTPException(status_code=401, detail="Could not validate credentials")


# =============================================================================
# DATABASE MODELS
# =============================================================================

class CalendlyIntegration(Base):
    """Stores Calendly integration settings for users"""
    __tablename__ = "calendly_integrations"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, unique=True)  # References users table

    # OAuth tokens (encrypted)
    access_token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    # Calendly user info
    calendly_user_uri = Column(String(255), nullable=True)
    calendly_user_name = Column(String(255), nullable=True)
    calendly_user_email = Column(String(255), nullable=True)
    calendly_organization_uri = Column(String(255), nullable=True)

    # Integration settings
    is_connected = Column(Boolean, default=False)
    selected_event_type_uri = Column(String(255), nullable=True)
    selected_event_type_name = Column(String(255), nullable=True)

    # Webhook
    webhook_subscription_uri = Column(String(255), nullable=True)

    # Calendar sync settings
    sync_to_smart_scheduler = Column(Boolean, default=True)
    auto_create_contacts = Column(Boolean, default=True)

    # Timestamps
    connected_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CalendlyBooking(Base):
    """Tracks bookings made through Calendly"""
    __tablename__ = "calendly_bookings"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)

    # Calendly event info
    calendly_event_uri = Column(String(255), unique=True, index=True)
    calendly_event_type_uri = Column(String(255), nullable=True)

    # Event details
    event_name = Column(String(255))
    start_time = Column(DateTime, index=True)
    end_time = Column(DateTime)
    status = Column(String(50), default="active")  # active, canceled

    # Invitee info
    invitee_name = Column(String(255))
    invitee_email = Column(String(255))
    invitee_timezone = Column(String(100), nullable=True)

    # Location
    location_type = Column(String(50), nullable=True)  # zoom, phone, in_person
    location_details = Column(Text, nullable=True)

    # Link to Smart Scheduler
    smart_scheduler_appointment_id = Column(String(50), nullable=True, index=True)

    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    canceled_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(Text, nullable=True)


# Create tables
try:
    CalendlyIntegration.__table__.create(engine, checkfirst=True)
    CalendlyBooking.__table__.create(engine, checkfirst=True)
    logger.info("Calendly tables created/verified")
except Exception as e:
    logger.warning(f"Could not create Calendly tables: {e}")


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class CalendlyConnectResponse(BaseModel):
    authorization_url: str
    state: str


class CalendlyIntegrationResponse(BaseModel):
    id: int
    user_id: int
    is_connected: bool
    calendly_user_name: Optional[str] = None
    calendly_user_email: Optional[str] = None
    selected_event_type_name: Optional[str] = None
    sync_to_smart_scheduler: bool
    auto_create_contacts: bool
    connected_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EventTypeResponse(BaseModel):
    uri: str
    name: str
    slug: str
    duration: int
    scheduling_url: str
    description: Optional[str] = None
    active: bool


class CalendlySettingsUpdate(BaseModel):
    selected_event_type_uri: Optional[str] = None
    sync_to_smart_scheduler: Optional[bool] = None
    auto_create_contacts: Optional[bool] = None


class AvailabilityRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    event_type_uri: Optional[str] = None


class BookingResponse(BaseModel):
    id: int
    calendly_event_uri: str
    event_name: str
    start_time: datetime
    end_time: datetime
    status: str
    invitee_name: str
    invitee_email: str
    location_type: Optional[str] = None
    smart_scheduler_appointment_id: Optional[str] = None

    class Config:
        from_attributes = True


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_integration(db: Session, user_id: int) -> Optional[CalendlyIntegration]:
    """Get Calendly integration for a user"""
    return db.query(CalendlyIntegration).filter(
        CalendlyIntegration.user_id == user_id
    ).first()


def get_or_create_integration(db: Session, user_id: int) -> CalendlyIntegration:
    """Get or create Calendly integration for a user"""
    integration = get_integration(db, user_id)
    if not integration:
        integration = CalendlyIntegration(user_id=user_id)
        db.add(integration)
        db.commit()
        db.refresh(integration)
    return integration


async def get_valid_access_token(
    db: Session,
    integration: CalendlyIntegration,
    service: CalendlyService
) -> Optional[str]:
    """Get a valid access token, refreshing if necessary"""
    if not integration.access_token_encrypted:
        return None

    # Check if token is expired
    if integration.token_expires_at and integration.token_expires_at < datetime.utcnow():
        # Refresh the token
        if not integration.refresh_token_encrypted:
            return None

        refresh_token = decrypt_token(integration.refresh_token_encrypted)
        result = await service.refresh_access_token(refresh_token)

        if not result.get("success"):
            logger.error("Failed to refresh Calendly token")
            return None

        # Update stored tokens
        integration.access_token_encrypted = encrypt_token(result["access_token"])
        if result.get("refresh_token"):
            integration.refresh_token_encrypted = encrypt_token(result["refresh_token"])
        integration.token_expires_at = datetime.utcnow() + timedelta(seconds=result["expires_in"])
        db.commit()

        return result["access_token"]

    return decrypt_token(integration.access_token_encrypted)


# =============================================================================
# OAUTH ROUTES
# =============================================================================

@router.get("/connect")
async def initiate_calendly_connect(
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
) -> CalendlyConnectResponse:
    """
    Initiate Calendly OAuth flow.
    Returns authorization URL to redirect user to.
    """
    import uuid
    user_id = current_user.id

    # Generate state for CSRF protection
    state = f"{user_id}:{uuid.uuid4().hex[:16]}"

    service = get_calendly_service()
    auth_url = service.get_authorization_url(state=state)

    logger.info(f"Initiating Calendly connect for user {user_id}")

    return CalendlyConnectResponse(
        authorization_url=auth_url,
        state=state
    )


@router.get("/callback")
async def calendly_oauth_callback(
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State parameter"),
    error: Optional[str] = Query(None, description="OAuth error"),
    error_description: Optional[str] = Query(None, description="Error description"),
    db: Session = Depends(get_db)
):
    """
    Handle Calendly OAuth callback.
    Exchange code for tokens and store integration.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")

    # Handle OAuth errors from Calendly
    if error:
        error_msg = error_description or error
        logger.error(f"Calendly OAuth error: {error_msg}")
        return RedirectResponse(
            url=f"{frontend_url}/settings?section=calendly&error={error_msg}",
            status_code=302
        )

    # Parse user_id from state
    try:
        user_id = int(state.split(":")[0])
    except (ValueError, IndexError):
        return RedirectResponse(
            url=f"{frontend_url}/settings?section=calendly&error=Invalid+state+parameter",
            status_code=302
        )

    service = get_calendly_service()

    # Exchange code for token
    token_result = await service.exchange_code_for_token(code)
    if not token_result.get("success"):
        error_msg = token_result.get('error', 'Failed to exchange code')
        logger.error(f"Calendly token exchange failed: {error_msg}")
        return RedirectResponse(
            url=f"{frontend_url}/settings?section=calendly&error=Token+exchange+failed",
            status_code=302
        )

    access_token = token_result["access_token"]

    # Get user info
    user_result = await service.get_current_user(access_token)
    if not user_result.get("success"):
        logger.error(f"Failed to get Calendly user info")
        return RedirectResponse(
            url=f"{frontend_url}/settings?section=calendly&error=Failed+to+get+user+info",
            status_code=302
        )

    # Store integration
    integration = get_or_create_integration(db, user_id)

    integration.access_token_encrypted = encrypt_token(access_token)
    integration.refresh_token_encrypted = encrypt_token(token_result["refresh_token"])
    integration.token_expires_at = datetime.utcnow() + timedelta(seconds=token_result["expires_in"])
    integration.calendly_user_uri = user_result["uri"]
    integration.calendly_user_name = user_result["name"]
    integration.calendly_user_email = user_result["email"]
    integration.calendly_organization_uri = user_result["current_organization"]
    integration.is_connected = True
    integration.connected_at = datetime.utcnow()

    db.commit()

    logger.info(f"Calendly connected for user {user_id}")

    # Redirect to frontend settings page
    return RedirectResponse(
        url=f"{frontend_url}/settings?section=calendly&connected=true",
        status_code=302
    )


@router.post("/disconnect")
async def disconnect_calendly(
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect Calendly integration"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration or not integration.is_connected:
        raise HTTPException(status_code=404, detail="No Calendly integration found")

    # Delete webhook subscription if exists
    if integration.webhook_subscription_uri and integration.access_token_encrypted:
        try:
            service = get_calendly_service()
            access_token = await get_valid_access_token(db, integration, service)
            if access_token:
                await service.delete_webhook_subscription(access_token, integration.webhook_subscription_uri)
        except Exception as e:
            logger.warning(f"Failed to delete webhook: {e}")

    # Clear integration data
    integration.access_token_encrypted = None
    integration.refresh_token_encrypted = None
    integration.token_expires_at = None
    integration.calendly_user_uri = None
    integration.calendly_user_name = None
    integration.calendly_user_email = None
    integration.calendly_organization_uri = None
    integration.webhook_subscription_uri = None
    integration.is_connected = False
    integration.connected_at = None

    db.commit()

    logger.info(f"Calendly disconnected for user {user_id}")

    return {"success": True, "message": "Calendly disconnected"}


# =============================================================================
# INTEGRATION SETTINGS ROUTES
# =============================================================================

@router.get("/status", response_model=CalendlyIntegrationResponse)
async def get_calendly_status(
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Get Calendly integration status for a user"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration:
        return CalendlyIntegrationResponse(
            id=0,
            user_id=user_id,
            is_connected=False,
            sync_to_smart_scheduler=True,
            auto_create_contacts=True
        )

    return CalendlyIntegrationResponse(
        id=integration.id,
        user_id=integration.user_id,
        is_connected=integration.is_connected,
        calendly_user_name=integration.calendly_user_name,
        calendly_user_email=integration.calendly_user_email,
        selected_event_type_name=integration.selected_event_type_name,
        sync_to_smart_scheduler=integration.sync_to_smart_scheduler,
        auto_create_contacts=integration.auto_create_contacts,
        connected_at=integration.connected_at,
        last_sync_at=integration.last_sync_at
    )


@router.put("/settings", response_model=CalendlyIntegrationResponse)
async def update_calendly_settings(
    settings: CalendlySettingsUpdate,
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Update Calendly integration settings"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration or not integration.is_connected:
        raise HTTPException(status_code=404, detail="No Calendly integration found")

    if settings.selected_event_type_uri is not None:
        integration.selected_event_type_uri = settings.selected_event_type_uri
        # Fetch event type name
        if settings.selected_event_type_uri:
            service = get_calendly_service()
            access_token = await get_valid_access_token(db, integration, service)
            if access_token:
                event_types = await service.get_event_types(
                    access_token,
                    user_uri=integration.calendly_user_uri
                )
                for et in event_types.get("event_types", []):
                    if et["uri"] == settings.selected_event_type_uri:
                        integration.selected_event_type_name = et["name"]
                        break

    if settings.sync_to_smart_scheduler is not None:
        integration.sync_to_smart_scheduler = settings.sync_to_smart_scheduler

    if settings.auto_create_contacts is not None:
        integration.auto_create_contacts = settings.auto_create_contacts

    db.commit()
    db.refresh(integration)

    return CalendlyIntegrationResponse(
        id=integration.id,
        user_id=integration.user_id,
        is_connected=integration.is_connected,
        calendly_user_name=integration.calendly_user_name,
        calendly_user_email=integration.calendly_user_email,
        selected_event_type_name=integration.selected_event_type_name,
        sync_to_smart_scheduler=integration.sync_to_smart_scheduler,
        auto_create_contacts=integration.auto_create_contacts,
        connected_at=integration.connected_at,
        last_sync_at=integration.last_sync_at
    )


# =============================================================================
# EVENT TYPES ROUTES
# =============================================================================

@router.get("/event-types", response_model=List[EventTypeResponse])
async def get_event_types(
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Get available Calendly event types for selection"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration or not integration.is_connected:
        raise HTTPException(status_code=404, detail="Calendly not connected")

    service = get_calendly_service()
    access_token = await get_valid_access_token(db, integration, service)

    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await service.get_event_types(
        access_token,
        user_uri=integration.calendly_user_uri
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    return [
        EventTypeResponse(
            uri=et["uri"],
            name=et["name"],
            slug=et["slug"],
            duration=et["duration"],
            scheduling_url=et["scheduling_url"],
            description=et.get("description"),
            active=et["active"]
        )
        for et in result["event_types"]
    ]


# =============================================================================
# AVAILABILITY ROUTES
# =============================================================================

@router.post("/availability")
async def get_availability(
    request: AvailabilityRequest,
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Get available time slots from Calendly"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration or not integration.is_connected:
        raise HTTPException(status_code=404, detail="Calendly not connected")

    service = get_calendly_service()
    access_token = await get_valid_access_token(db, integration, service)

    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Get busy times
    busy_result = await service.get_busy_times(
        access_token,
        integration.calendly_user_uri,
        request.start_time,
        request.end_time
    )

    if not busy_result.get("success"):
        raise HTTPException(status_code=500, detail=busy_result.get("error"))

    return {
        "success": True,
        "user_uri": integration.calendly_user_uri,
        "busy_times": busy_result["busy_times"],
        "query": {
            "start_time": request.start_time.isoformat(),
            "end_time": request.end_time.isoformat(),
        }
    }


# =============================================================================
# BOOKINGS ROUTES
# =============================================================================

@router.get("/bookings", response_model=List[BookingResponse])
async def get_bookings(
    status: Optional[str] = Query("active", description="Filter by status"),
    days_ahead: int = Query(30, description="Days to look ahead"),
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Get bookings from Calendly"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration or not integration.is_connected:
        raise HTTPException(status_code=404, detail="Calendly not connected")

    service = get_calendly_service()
    access_token = await get_valid_access_token(db, integration, service)

    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Get events from Calendly
    result = await service.get_scheduled_events(
        access_token,
        user_uri=integration.calendly_user_uri,
        min_start_time=datetime.utcnow(),
        max_start_time=datetime.utcnow() + timedelta(days=days_ahead),
        status=status
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    # Get local bookings to include smart scheduler links
    local_bookings = {
        b.calendly_event_uri: b
        for b in db.query(CalendlyBooking).filter(
            CalendlyBooking.user_id == user_id
        ).all()
    }

    bookings = []
    for event in result["events"]:
        local = local_bookings.get(event["uri"])

        # Get invitee info
        invitees = await service.get_event_invitees(access_token, event["uri"])
        invitee = invitees.get("invitees", [{}])[0] if invitees.get("success") else {}

        bookings.append(BookingResponse(
            id=local.id if local else 0,
            calendly_event_uri=event["uri"],
            event_name=event["name"],
            start_time=datetime.fromisoformat(event["start_time"].replace("Z", "+00:00")),
            end_time=datetime.fromisoformat(event["end_time"].replace("Z", "+00:00")),
            status=event["status"],
            invitee_name=invitee.get("name", "Unknown"),
            invitee_email=invitee.get("email", ""),
            location_type=event.get("location", {}).get("type") if event.get("location") else None,
            smart_scheduler_appointment_id=local.smart_scheduler_appointment_id if local else None
        ))

    return bookings


@router.post("/bookings/{event_uri}/cancel")
async def cancel_booking(
    event_uri: str,
    reason: Optional[str] = None,
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a Calendly booking"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration or not integration.is_connected:
        raise HTTPException(status_code=404, detail="Calendly not connected")

    service = get_calendly_service()
    access_token = await get_valid_access_token(db, integration, service)

    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Cancel in Calendly
    result = await service.cancel_event(access_token, event_uri, reason)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    # Update local booking
    local_booking = db.query(CalendlyBooking).filter(
        CalendlyBooking.calendly_event_uri == event_uri
    ).first()

    if local_booking:
        local_booking.status = "canceled"
        local_booking.canceled_at = datetime.utcnow()
        local_booking.cancellation_reason = reason
        db.commit()

    return {"success": True, "message": "Booking cancelled"}


# =============================================================================
# WEBHOOK ROUTES
# =============================================================================

@router.post("/webhook")
async def handle_calendly_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Handle incoming Calendly webhook events.

    Events:
    - invitee.created: New booking made
    - invitee.canceled: Booking cancelled
    """
    # Verify webhook signature — fail-closed when secret not configured
    body = await request.body()
    if not CALENDLY_WEBHOOK_SECRET:
        logger.error("CALENDLY_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=401, detail="Webhook verification not configured")
    signature = request.headers.get("Calendly-Webhook-Signature")
    if not signature:
        logger.warning("Missing Calendly-Webhook-Signature header")
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    expected_signature = hmac.new(
        CALENDLY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        logger.warning("Invalid Calendly webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("event")
    event_payload = payload.get("payload", {})

    logger.info(f"Received Calendly webhook: {event_type}")

    if event_type == "invitee.created":
        background_tasks.add_task(process_booking_created, db, event_payload)
    elif event_type == "invitee.canceled":
        background_tasks.add_task(process_booking_canceled, db, event_payload)

    return {"success": True, "received": event_type}


async def process_booking_created(db: Session, payload: Dict[str, Any]):
    """Process new booking from Calendly"""
    try:
        event = payload.get("scheduled_event", {})
        invitee = payload.get("invitee", {})

        # Find user by calendly user URI
        event_memberships = event.get("event_memberships", [])
        if not event_memberships:
            logger.warning("No event memberships in webhook payload")
            return

        calendly_user_uri = event_memberships[0].get("user")

        integration = db.query(CalendlyIntegration).filter(
            CalendlyIntegration.calendly_user_uri == calendly_user_uri
        ).first()

        if not integration:
            logger.warning(f"No integration found for user URI: {calendly_user_uri}")
            return

        # Create local booking record
        booking = CalendlyBooking(
            user_id=integration.user_id,
            calendly_event_uri=event.get("uri"),
            calendly_event_type_uri=event.get("event_type"),
            event_name=event.get("name"),
            start_time=datetime.fromisoformat(event.get("start_time", "").replace("Z", "+00:00")),
            end_time=datetime.fromisoformat(event.get("end_time", "").replace("Z", "+00:00")),
            invitee_name=invitee.get("name"),
            invitee_email=invitee.get("email"),
            invitee_timezone=invitee.get("timezone"),
            location_type=event.get("location", {}).get("type") if event.get("location") else None,
            location_details=json.dumps(event.get("location")) if event.get("location") else None,
        )

        db.add(booking)
        db.commit()

        logger.info(f"Created booking for user {integration.user_id}: {invitee.get('name')}")

        # Optionally sync to Smart Scheduler
        if integration.sync_to_smart_scheduler:
            # Import here to avoid circular imports
            from services.smart_scheduler_service import get_scheduler_service

            scheduler = get_scheduler_service(db)
            result = scheduler.book_appointment(
                contact_name=invitee.get("name"),
                contact_email=invitee.get("email"),
                appointment_time=datetime.fromisoformat(event.get("start_time", "").replace("Z", "+00:00")),
                appointment_type="calendly_sync",
                notes=f"Booked via Calendly: {event.get('name')}",
            )

            if result.get("success"):
                booking.smart_scheduler_appointment_id = result["appointment_id"]
                db.commit()
                logger.info(f"Synced to Smart Scheduler: {result['appointment_id']}")

        # Invalidate availability cache
        availability_cache.invalidate(calendly_user_uri)

    except SQLAlchemyError as e:
        logger.error(f"Error processing booking created webhook: {e}")


async def process_booking_canceled(db: Session, payload: Dict[str, Any]):
    """Process booking cancellation from Calendly"""
    try:
        invitee = payload.get("invitee", {})
        event_uri = invitee.get("event")
        cancellation = invitee.get("cancellation", {})

        # Update local booking
        booking = db.query(CalendlyBooking).filter(
            CalendlyBooking.calendly_event_uri == event_uri
        ).first()

        if booking:
            booking.status = "canceled"
            booking.canceled_at = datetime.utcnow()
            booking.cancellation_reason = cancellation.get("reason")
            db.commit()

            # Cancel in Smart Scheduler if linked
            if booking.smart_scheduler_appointment_id:
                from services.smart_scheduler_service import get_scheduler_service
                scheduler = get_scheduler_service(db)
                scheduler.cancel_appointment(
                    booking.smart_scheduler_appointment_id,
                    reason=f"Cancelled via Calendly: {cancellation.get('reason')}"
                )

            logger.info(f"Booking cancelled: {event_uri}")

            # Invalidate availability cache
            integration = db.query(CalendlyIntegration).filter(
                CalendlyIntegration.user_id == booking.user_id
            ).first()
            if integration:
                availability_cache.invalidate(integration.calendly_user_uri)

    except SQLAlchemyError as e:
        logger.error(f"Error processing booking canceled webhook: {e}")


# =============================================================================
# WEBHOOK MANAGEMENT ROUTES
# =============================================================================

@router.post("/webhook/subscribe")
async def subscribe_to_webhooks(
    webhook_url: str = Query(..., description="URL to receive webhooks"),
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Subscribe to Calendly webhook events"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration or not integration.is_connected:
        raise HTTPException(status_code=404, detail="Calendly not connected")

    service = get_calendly_service()
    access_token = await get_valid_access_token(db, integration, service)

    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await service.create_webhook_subscription(
        access_token,
        url=webhook_url,
        events=["invitee.created", "invitee.canceled"],
        organization_uri=integration.calendly_organization_uri,
        user_uri=integration.calendly_user_uri,
        scope="user"
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    # Store webhook URI
    integration.webhook_subscription_uri = result["webhook"]["uri"]
    db.commit()

    return {
        "success": True,
        "webhook": result["webhook"]
    }


@router.delete("/webhook/unsubscribe")
async def unsubscribe_from_webhooks(
    current_user=Depends(_get_current_user),
    db: Session = Depends(get_db)
):
    """Unsubscribe from Calendly webhook events"""
    user_id = current_user.id
    integration = get_integration(db, user_id)

    if not integration or not integration.webhook_subscription_uri:
        raise HTTPException(status_code=404, detail="No webhook subscription found")

    service = get_calendly_service()
    access_token = await get_valid_access_token(db, integration, service)

    if not access_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await service.delete_webhook_subscription(
        access_token,
        integration.webhook_subscription_uri
    )

    if result.get("success"):
        integration.webhook_subscription_uri = None
        db.commit()

    return result
