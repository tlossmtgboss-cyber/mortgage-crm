"""
DEPRECATED — NOT REGISTERED IN APP.
Active Calendly integration: routes/calendly_routes.py
This file retained for reference only. Do NOT import or register.

Original description:
Calendly Integration Routes — endpoints for Calendly calendar integration including:
- Connecting Calendly accounts via API key
- Fetching event types from Calendly
- Creating scheduling links for leads
- Webhook handling for booking events
- Calendar stage mappings
- AI-powered scheduling conversations

All endpoints require authentication except for the webhook endpoint.
"""

import os
import logging
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

import asyncio
import requests

CALENDLY_WEBHOOK_SECRET = os.getenv("CALENDLY_WEBHOOK_SECRET", "")


async def _async_get(*args, **kwargs):
    """Run blocking requests.get() in thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(requests.get, *args, **kwargs)


async def _async_post(*args, **kwargs):
    """Run blocking requests.post() in thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(requests.post, *args, **kwargs)
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/calendly", tags=["calendly"])

# Dependency injection placeholders
_get_db: Optional[Callable] = None
_get_current_user: Optional[Callable] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """Get database session - wrapper that works at request time."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


def get_models():
    """Runtime import for models to avoid circular imports."""
    from database.models import User, Lead, Task, IntegrationCredential, CalendarMapping
    return User, Lead, Task, IntegrationCredential, CalendarMapping


def _resolve_org_from_webhook(db, payload: dict) -> Optional[int]:
    """Resolve organization_id from Calendly webhook payload.

    Uses event_memberships[0].user URI to look up CalendlyIntegration,
    which stores the org relationship. Returns None if unresolvable.
    """
    try:
        from routes.calendly_routes import CalendlyIntegration
    except ImportError:
        logger.error("Cannot import CalendlyIntegration model for org resolution")
        return None

    event = payload.get("payload", {}).get("scheduled_event", {})
    event_memberships = event.get("event_memberships", [])
    if not event_memberships:
        # Try alternate payload structure
        event_memberships = payload.get("payload", {}).get("event_memberships", [])

    if not event_memberships:
        logger.warning("No event_memberships in Calendly webhook — cannot resolve org")
        return None

    calendly_user_uri = event_memberships[0].get("user")
    if not calendly_user_uri:
        return None

    integration = db.query(CalendlyIntegration).filter(
        CalendlyIntegration.calendly_user_uri == calendly_user_uri
    ).first()

    if integration:
        return integration.organization_id

    logger.warning(f"No CalendlyIntegration found for user URI: {calendly_user_uri}")
    return None


@router.post("/connect")
async def connect_calendly(
    request: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save user's Calendly API key for integration.
    """
    User, Lead, Task, IntegrationCredential, CalendarMapping = get_models()

    api_key = request.get("api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    try:
        # Verify the API key works by making a test call to Calendly
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        test_response = await _async_get(
            "https://api.calendly.com/users/me",
            headers=headers
        )

        if test_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid Calendly API key")

        # Check if user already has a Calendly credential
        existing_cred = db.query(IntegrationCredential).filter(
            IntegrationCredential.user_id == current_user.id,
            IntegrationCredential.integration_type == "calendly"
        ).first()

        if existing_cred:
            # Update existing credential
            existing_cred.api_key = api_key
            existing_cred.is_active = True
            existing_cred.updated_at = datetime.now(timezone.utc)
        else:
            # Create new credential
            new_cred = IntegrationCredential(
                user_id=current_user.id,
                integration_type="calendly",
                api_key=api_key,
                is_active=True
            )
            db.add(new_cred)

        db.commit()

        return {
            "message": "Calendly connected successfully",
            "status": "connected"
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly API test failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to verify Calendly API key")
    except Exception as e:
        db.rollback()
        logger.error(f"Error connecting Calendly: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/event-types")
async def get_calendly_event_types(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's Calendly event types (available meeting types).
    Uses user's stored Calendly API key.
    """
    User, Lead, Task, IntegrationCredential, CalendarMapping = get_models()

    # Get user's Calendly credential from database
    cred = db.query(IntegrationCredential).filter(
        IntegrationCredential.user_id == current_user.id,
        IntegrationCredential.integration_type == "calendly",
        IntegrationCredential.is_active == True
    ).first()

    if not cred:
        # Return empty list if not connected
        return {
            "event_types": [],
            "count": 0
        }

    try:
        # First, get the current user's URI
        headers = {
            "Authorization": f"Bearer {cred.api_key}",
            "Content-Type": "application/json"
        }

        # Get current user info
        user_response = await _async_get(
            "https://api.calendly.com/users/me",
            headers=headers
        )
        user_response.raise_for_status()
        user_data = user_response.json()
        user_uri = user_data["resource"]["uri"]

        # Get event types for this user
        event_types_response = await _async_get(
            f"https://api.calendly.com/event_types",
            headers=headers,
            params={"user": user_uri}
        )
        event_types_response.raise_for_status()
        event_types_data = event_types_response.json()

        return {
            "event_types": event_types_data.get("collection", []),
            "count": event_types_data.get("pagination", {}).get("count", 0)
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch event types")


@router.post("/scheduling-link")
async def create_scheduling_link(
    request: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a single-use Calendly scheduling link for a lead.
    This link can be sent via email/SMS to allow the lead to book a meeting.
    """
    User, Lead, Task, IntegrationCredential, CalendarMapping = get_models()

    calendly_token = os.getenv("CALENDLY_API_TOKEN")
    if not calendly_token:
        raise HTTPException(status_code=500, detail="Calendly API not configured")

    lead_id = request.get("lead_id")
    event_type_uuid = request.get("event_type_uuid")

    if not lead_id or not event_type_uuid:
        raise HTTPException(status_code=400, detail="lead_id and event_type_uuid required")

    # Get lead details
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        # Create single-use scheduling link
        payload = {
            "max_event_count": 1,  # Single-use link
            "owner": f"https://api.calendly.com/event_types/{event_type_uuid}",
            "owner_type": "EventType"
        }

        response = await _async_post(
            "https://api.calendly.com/scheduling_links",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()

        booking_url = data["resource"]["booking_url"]

        # Store the scheduling link in lead metadata
        if not lead.meta_data:
            lead.meta_data = {}
        lead.meta_data["calendly_link"] = booking_url
        lead.meta_data["calendly_created_at"] = datetime.now(timezone.utc).isoformat()
        db.commit()

        return {
            "booking_url": booking_url,
            "lead_id": lead_id,
            "lead_name": lead.name,
            "message": "Single-use scheduling link created successfully"
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create scheduling link")


@router.post("/webhook")
async def calendly_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook endpoint to receive Calendly events.
    Handles invitee.created, invitee.canceled, etc.

    To set this up:
    1. Go to Calendly Integrations > Webhooks
    2. Add webhook URL: https://your-domain.com/api/v1/calendly/webhook
    3. Subscribe to events: invitee.created, invitee.canceled
    """
    User, Lead, Task, IntegrationCredential, CalendarMapping = get_models()

    # Read body once for both signature validation and JSON parsing
    body = await request.body()

    # Validate Calendly webhook signature (fail-closed: reject if secret not configured)
    if not CALENDLY_WEBHOOK_SECRET:
        logger.error("CALENDLY_WEBHOOK_SECRET not configured — rejecting webhook (fail-closed)")
        return {"status": "error", "detail": "Webhook signature verification not configured"}

    signature = request.headers.get("Calendly-Webhook-Signature", "")
    # Calendly signature format: "t=timestamp,v1=signature"
    sig_parts = {}
    for part in signature.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            sig_parts[k] = v
    timestamp = sig_parts.get("t", "")
    provided_sig = sig_parts.get("v1", "")
    expected = hmac.new(
        CALENDLY_WEBHOOK_SECRET.encode(),
        f"{timestamp}.{body.decode()}".encode(),
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(provided_sig, expected):
        logger.warning(f"Invalid Calendly webhook signature from {request.client.host}")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        import json as _json
        payload = _json.loads(body)
        event_type = payload.get("event")

        logger.info(f"Calendly webhook received: {event_type}")

        # Resolve organization from webhook payload (tenant isolation)
        organization_id = _resolve_org_from_webhook(db, payload)
        if not organization_id:
            logger.error("Cannot resolve organization_id from Calendly webhook — skipping processing")
            return {"status": "error", "detail": "Unable to resolve organization context"}

        if event_type == "invitee.created":
            # Extract invitee and event details
            invitee_data = payload.get("payload", {})
            invitee_email = invitee_data.get("email")
            invitee_name = invitee_data.get("name")
            event_uri = invitee_data.get("event")
            scheduled_at = invitee_data.get("scheduled_event", {}).get("start_time")

            # Try to find matching lead by email within the same org
            lead = db.query(Lead).filter(
                Lead.email == invitee_email,
                Lead.organization_id == organization_id
            ).first()

            if lead:
                # Update lead with appointment info
                if not lead.meta_data:
                    lead.meta_data = {}

                lead.meta_data["calendly_booked"] = True
                lead.meta_data["calendly_booked_at"] = scheduled_at
                lead.meta_data["calendly_event_uri"] = event_uri

                # Move lead to "Meeting Scheduled" stage if applicable
                lead.stage = "meeting_scheduled"

                # Create a task for the user (with org isolation)
                task = Task(
                    title=f"Meeting scheduled with {invitee_name}",
                    description=f"Calendly meeting booked for {scheduled_at}",
                    due_date=datetime.fromisoformat(scheduled_at.replace('Z', '+00:00')) if scheduled_at else None,
                    priority="high",
                    status="pending",
                    lead_id=lead.id,
                    organization_id=organization_id
                )
                db.add(task)
                db.commit()

                logger.info(f"Lead {lead.id} updated with Calendly appointment (org={organization_id})")
            else:
                # Create new lead from Calendly booking (with org isolation)
                new_lead = Lead(
                    name=invitee_name,
                    email=invitee_email,
                    stage="meeting_scheduled",
                    source="Calendly",
                    organization_id=organization_id,
                    meta_data={
                        "calendly_booked": True,
                        "calendly_booked_at": scheduled_at,
                        "calendly_event_uri": event_uri
                    },
                    lead_received_date=datetime.now(timezone.utc),  # Auto-set for SLA tracking
                )
                db.add(new_lead)
                db.commit()

                logger.info(f"New lead created from Calendly: {invitee_name} (org={organization_id})")

        elif event_type == "invitee.canceled":
            # Handle cancellation
            invitee_data = payload.get("payload", {})
            invitee_email = invitee_data.get("email")

            # Filter by org to prevent cross-tenant data access
            lead = db.query(Lead).filter(
                Lead.email == invitee_email,
                Lead.organization_id == organization_id
            ).first()
            if lead:
                if lead.meta_data:
                    lead.meta_data["calendly_booked"] = False
                    lead.meta_data["calendly_canceled_at"] = datetime.now(timezone.utc).isoformat()
                    db.commit()

                    logger.info(f"Lead {lead.id} Calendly appointment canceled (org={organization_id})")

        return {"status": "success", "event": event_type}

    except Exception as e:
        logger.error(f"Calendly webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/calendar-mappings")
async def create_calendar_mapping(
    request: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Map a lead stage to a Calendly event type.
    Example: map "new" stage to "Discovery Call" event type
    """
    User, Lead, Task, IntegrationCredential, CalendarMapping = get_models()

    stage = request.get("stage")
    event_type_uuid = request.get("event_type_uuid")
    event_type_name = request.get("event_type_name")
    event_type_url = request.get("event_type_url")

    if not all([stage, event_type_uuid, event_type_name]):
        raise HTTPException(status_code=400, detail="stage, event_type_uuid, and event_type_name required")

    # Check if mapping already exists
    existing = db.query(CalendarMapping).filter(
        CalendarMapping.user_id == current_user.id,
        CalendarMapping.stage == stage
    ).first()

    if existing:
        # Update existing mapping
        existing.event_type_uuid = event_type_uuid
        existing.event_type_name = event_type_name
        existing.event_type_url = event_type_url
        existing.is_active = True
        db.commit()
        return {"message": "Calendar mapping updated", "mapping_id": existing.id}
    else:
        # Create new mapping
        mapping = CalendarMapping(
            user_id=current_user.id,
            stage=stage,
            event_type_uuid=event_type_uuid,
            event_type_name=event_type_name,
            event_type_url=event_type_url
        )
        db.add(mapping)
        db.commit()
        return {"message": "Calendar mapping created", "mapping_id": mapping.id}


@router.get("/calendar-mappings")
async def get_calendar_mappings(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all calendar mappings for current user"""
    User, Lead, Task, IntegrationCredential, CalendarMapping = get_models()

    mappings = db.query(CalendarMapping).filter(
        CalendarMapping.user_id == current_user.id,
        CalendarMapping.is_active == True
    ).all()

    return {
        "mappings": [
            {
                "id": m.id,
                "stage": m.stage,
                "event_type_uuid": m.event_type_uuid,
                "event_type_name": m.event_type_name,
                "event_type_url": m.event_type_url
            }
            for m in mappings
        ]
    }


@router.get("/availability")
async def get_availability(
    event_type_uuid: str,
    start_time: str,
    end_time: str,
    current_user=Depends(get_current_user)
):
    """
    Get available time slots for a Calendly event type.

    Args:
        event_type_uuid: The UUID of the event type
        start_time: ISO 8601 format (e.g., "2024-01-15T00:00:00Z")
        end_time: ISO 8601 format (e.g., "2024-01-22T00:00:00Z")
    """
    calendly_token = os.getenv("CALENDLY_API_TOKEN")
    if not calendly_token:
        raise HTTPException(status_code=500, detail="Calendly API not configured")

    try:
        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        # Get availability from Calendly
        response = await _async_get(
            f"https://api.calendly.com/event_type_available_times",
            headers=headers,
            params={
                "event_type": f"https://api.calendly.com/event_types/{event_type_uuid}",
                "start_time": start_time,
                "end_time": end_time
            }
        )
        response.raise_for_status()
        data = response.json()

        return {
            "available_times": data.get("collection", []),
            "count": len(data.get("collection", []))
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly availability API error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch availability")


@router.post("/ai-schedule")
async def ai_schedule_conversation(
    request: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    AI-powered scheduling conversation endpoint.
    The AI can view availability and book appointments automatically.

    Example conversation:
    User: "I'd like to schedule a meeting"
    AI: "I have these times available: Jan 15 at 2pm, Jan 16 at 10am..."
    User: "Jan 15 at 2pm works"
    AI: *books appointment* "Great! You're confirmed for Jan 15 at 2pm"
    """
    import anthropic

    User, Lead, Task, IntegrationCredential, CalendarMapping = get_models()

    lead_id = request.get("lead_id")
    message = request.get("message")
    conversation_history = request.get("conversation_history", [])

    if not lead_id or not message:
        raise HTTPException(status_code=400, detail="lead_id and message required")

    # Get lead details
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Get the appropriate calendar mapping for this lead's stage
    mapping = db.query(CalendarMapping).filter(
        CalendarMapping.user_id == current_user.id,
        CalendarMapping.stage == lead.stage,
        CalendarMapping.is_active == True
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"No calendar mapping found for stage '{lead.stage}'. Please configure calendar mappings first."
        )

    calendly_token = os.getenv("CALENDLY_API_TOKEN")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    if not calendly_token or not anthropic_api_key:
        raise HTTPException(status_code=500, detail="Calendly or Anthropic API not configured")

    try:
        # Get availability for next 14 days
        start_time = datetime.now(timezone.utc).isoformat()
        end_time = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()

        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        # Fetch available times
        availability_response = await _async_get(
            f"https://api.calendly.com/event_type_available_times",
            headers=headers,
            params={
                "event_type": f"https://api.calendly.com/event_types/{mapping.event_type_uuid}",
                "start_time": start_time,
                "end_time": end_time
            }
        )

        available_slots = []
        if availability_response.status_code == 200:
            avail_data = availability_response.json()
            available_slots = avail_data.get("collection", [])

        # Format available slots for AI
        formatted_slots = []
        for slot in available_slots[:10]:  # Show first 10 slots
            start_dt = datetime.fromisoformat(slot["start_time"].replace('Z', '+00:00'))
            formatted_slots.append({
                "datetime": start_dt.strftime("%A, %B %d at %I:%M %p"),
                "iso_time": slot["start_time"]
            })

        # Build context for Claude
        system_prompt = f"""You are a scheduling assistant for a mortgage loan officer. You help schedule {mapping.event_type_name} appointments.

Lead Information:
- Name: {lead.name}
- Email: {lead.email}
- Stage: {lead.stage}

Available Time Slots:
{chr(10).join([f"- {slot['datetime']}" for slot in formatted_slots]) if formatted_slots else "No availability in the next 14 days"}

Your capabilities:
1. View and present available time slots in a natural way
2. When the lead confirms a specific time, extract the ISO timestamp and respond with BOOK:[iso_timestamp]
3. Be friendly, professional, and helpful

Rules:
- Only book times from the available slots list
- When booking, respond with EXACTLY: BOOK:[iso_timestamp] (e.g., "BOOK:2024-01-15T14:00:00Z")
- After booking, confirm the appointment in natural language
- If no slots available, suggest alternative dates or contact methods"""

        # Call Claude
        client = anthropic.Anthropic(api_key=anthropic_api_key)

        messages = conversation_history + [{"role": "user", "content": message}]

        ai_response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )

        ai_message = ai_response.content[0].text

        # Check if AI wants to book an appointment
        if "BOOK:" in ai_message:
            # Extract timestamp
            booking_line = [line for line in ai_message.split('\n') if 'BOOK:' in line][0]
            iso_timestamp = booking_line.split('BOOK:')[1].strip()

            # Create single-use scheduling link
            scheduling_payload = {
                "max_event_count": 1,
                "owner": f"https://api.calendly.com/event_types/{mapping.event_type_uuid}",
                "owner_type": "EventType"
            }

            scheduling_response = await _async_post(
                "https://api.calendly.com/scheduling_links",
                headers=headers,
                json=scheduling_payload
            )

            if scheduling_response.status_code == 201:
                scheduling_data = scheduling_response.json()
                booking_url = scheduling_data["resource"]["booking_url"]

                # Store in lead metadata
                if not lead.meta_data:
                    lead.meta_data = {}
                lead.meta_data["calendly_link"] = booking_url
                lead.meta_data["ai_suggested_time"] = iso_timestamp
                lead.meta_data["calendly_created_at"] = datetime.now(timezone.utc).isoformat()
                db.commit()

                # Remove BOOK: directive from message shown to user
                clean_message = ai_message.replace(booking_line, "").strip()

                return {
                    "ai_message": clean_message,
                    "booking_created": True,
                    "booking_url": booking_url,
                    "suggested_time": iso_timestamp,
                    "lead_name": lead.name
                }

        # Regular conversation response
        return {
            "ai_message": ai_message,
            "booking_created": False,
            "available_slots": formatted_slots[:5]  # Show top 5 in response
        }

    except Exception as e:
        logger.error(f"AI scheduling error: {e}")
        raise HTTPException(status_code=500, detail="AI scheduling failed")
