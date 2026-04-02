"""
DRE Calendly Integration — Scheduling intent detection and time slot fetching.

Functions:
    detect_scheduling_intent      — Keyword detection for scheduling tasks
    get_calendly_time_slots_for_user — Fetch available Calendly slots via API
    generate_scheduling_email_draft  — Draft email with embedded time slots
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.orm import Session

from services.dre._base import _ensure_models

logger = logging.getLogger(__name__)


def detect_scheduling_intent(title: str, description: str = "") -> bool:
    """Detect if a task is about scheduling a meeting/call with someone."""
    scheduling_keywords = [
        "schedule", "scheduling", "appointment", "meeting", "call",
        "pick a time", "pick time", "choose a time", "choose time",
        "set up a call", "set up call", "book", "booking",
        "calendar", "availability", "when to speak", "time to speak",
        "time to meet", "time to talk", "consultation", "consult"
    ]

    text_combined = f"{title} {description}".lower()
    return any(keyword in text_combined for keyword in scheduling_keywords)


async def get_calendly_time_slots_for_user(user_id: int, db: Session, num_slots: int = 5) -> dict:
    """Fetch available Calendly time slots for a user."""
    _ensure_models()
    from services.dre._base import IntegrationCredential

    try:
        cred = db.query(IntegrationCredential).filter(
            IntegrationCredential.user_id == user_id,
            IntegrationCredential.integration_type == "calendly",
            IntegrationCredential.is_active == True
        ).first()

        calendly_token = None
        if cred and cred.api_key:
            calendly_token = cred.api_key
        else:
            calendly_token = os.getenv("CALENDLY_API_TOKEN")

        if not calendly_token:
            logger.warning(f"No Calendly token found for user {user_id}")
            return {"success": False, "error": "Calendly not configured", "slots": []}

        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        user_response = await asyncio.to_thread(
            requests.get,
            "https://api.calendly.com/users/me",
            headers=headers,
            timeout=10
        )

        if user_response.status_code != 200:
            logger.error(f"Calendly user API error: {user_response.status_code}")
            return {"success": False, "error": "Could not fetch Calendly user", "slots": []}

        user_uri = user_response.json().get("resource", {}).get("uri")

        event_types_response = await asyncio.to_thread(
            requests.get,
            "https://api.calendly.com/event_types",
            headers=headers,
            params={"user": user_uri, "active": "true"},
            timeout=10
        )

        if event_types_response.status_code != 200:
            logger.error(f"Calendly event types API error: {event_types_response.status_code}")
            return {"success": False, "error": "Could not fetch event types", "slots": []}

        event_types = event_types_response.json().get("collection", [])

        if not event_types:
            return {"success": False, "error": "No active Calendly event types", "slots": []}

        event_type = event_types[0]
        event_type_uuid = event_type.get("uri", "").split("/")[-1]
        event_type_name = event_type.get("name", "Meeting")
        scheduling_url = event_type.get("scheduling_url", "")
        duration_minutes = event_type.get("duration", 30)

        start_time = datetime.now(timezone.utc).isoformat()
        end_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        availability_response = await asyncio.to_thread(
            requests.get,
            "https://api.calendly.com/event_type_available_times",
            headers=headers,
            params={
                "event_type": f"https://api.calendly.com/event_types/{event_type_uuid}",
                "start_time": start_time,
                "end_time": end_time
            },
            timeout=10
        )

        if availability_response.status_code != 200:
            logger.error(f"Calendly availability API error: {availability_response.status_code}")
            return {"success": False, "error": "Could not fetch availability", "slots": []}

        available_times = availability_response.json().get("collection", [])

        formatted_slots = []
        for slot in available_times[:num_slots]:
            start_str = slot.get("start_time", "")
            if start_str:
                slot_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                display_date = slot_dt.strftime("%A, %b %d at %-I:%M %p")
                booking_link = f"{scheduling_url}?month={slot_dt.strftime('%Y-%m')}&date={slot_dt.strftime('%Y-%m-%d')}"

                formatted_slots.append({
                    "display": display_date,
                    "iso": start_str,
                    "booking_link": booking_link,
                    "duration_minutes": duration_minutes
                })

        return {
            "success": True,
            "event_type_name": event_type_name,
            "scheduling_url": scheduling_url,
            "duration_minutes": duration_minutes,
            "slots": formatted_slots
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly API request error: {e}")
        return {"success": False, "error": "Internal server error", "slots": []}
    except Exception as e:
        logger.error(f"Error fetching Calendly slots: {e}")
        return {"success": False, "error": "Internal server error", "slots": []}


def generate_scheduling_email_draft(
    client_name: str,
    calendly_slots: dict,
    user_name: str = "Your Loan Officer"
) -> str:
    """Generate an AI-drafted email with embedded Calendly time slots."""
    first_name = client_name.split()[0] if client_name else "there"

    if not calendly_slots.get("success") or not calendly_slots.get("slots"):
        return f"""Hi {first_name},

    I'd like to schedule a call with you to discuss your loan. Please let me know what times work best for you this week.

    Looking forward to connecting!

    Best regards,
    {user_name}"""

    slots = calendly_slots.get("slots", [])
    duration = calendly_slots.get("duration_minutes", 30)

    time_slots_html = ""
    for slot in slots:
        display = slot.get("display", "")
        link = slot.get("booking_link", "")
        time_slots_html += f"""
    <div style="margin: 8px 0;">
      <a href="{link}" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #218D8D 0%, #10b981 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px;">
        {display}
      </a>
    </div>"""

    email_body = f"""Hi {first_name},

    I'd like to schedule a {duration}-minute call to discuss your mortgage. Please click one of the available times below to book directly on my calendar:

    <div style="margin: 20px 0; padding: 16px; background: #f7fafc; border-radius: 12px; border: 1px solid #e2e8f0;">
    <strong style="color: #1a202c; font-size: 14px;">Available Time Slots:</strong>
    {time_slots_html}
    </div>

    If none of these times work, you can also <a href="{calendly_slots.get('scheduling_url', '#')}" style="color: #218D8D; font-weight: 600;">view all available times</a> on my calendar.

    Looking forward to speaking with you!

    Best regards,
    {user_name}"""

    return email_body
