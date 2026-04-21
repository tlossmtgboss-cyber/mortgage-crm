"""
Perennia AI — Smart Calendar Adapter
====================================
Books loan officer kickoff calls via the Perennia CRM's Smart Calendar API.
Used after URLA finalize to get the borrower on the LO's calendar before the
voice call ends.

The Smart Calendar owns:
  - Per-LO availability windows (business hours by timezone, holidays)
  - Round-robin / load-balancing across a team
  - Back-to-back buffer
  - Calendar invite + confirmation email/SMS dispatch

This adapter just asks "give me N open slots for NMLSR X" and then books
the chosen slot. Idempotent on booking via X-Idempotency-Key.

Expected Smart Calendar API contract
------------------------------------
GET  /v1/calendar/availability
    Query: loan_officer_nmlsr_id, duration_minutes, lookahead_days, max_slots,
           meeting_type, caller_timezone (optional)
    Returns: { "slots": [
        {
          "slot_id": "slot_abc123",
          "start": "2026-04-23T14:00:00-04:00",
          "end":   "2026-04-23T14:30:00-04:00",
          "loan_officer_nmlsr_id": "1234567",
          "loan_officer_name": "Sarah Nguyen",
          "timezone": "America/New_York"
        }, ...
    ] }

POST /v1/calendar/bookings
    Body:  { slot_id, meeting_type, meeting_title, duration_minutes,
             attendees: [{role, nmlsr_id | name/phone/email}],
             related_loan_id, notes, send_confirmations }
    Returns: { event_id, confirmation_number, scheduled_start, scheduled_end,
               loan_officer_name, status }
    409 -> slot taken since availability was fetched (no retry).
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import httpx


logger = logging.getLogger("urla.calendar")


@dataclass
class AvailableSlot:
    slot_id: str
    start: datetime              # tz-aware ISO from Smart Calendar
    end: datetime
    loan_officer_nmlsr_id: str
    loan_officer_name: str
    timezone: str                # IANA, e.g. "America/New_York"


@dataclass
class BookingResult:
    success: bool
    event_id: Optional[str] = None
    confirmation_number: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    scheduled_timezone: Optional[str] = None
    loan_officer_name: Optional[str] = None
    error: Optional[str] = None
    slot_no_longer_available: bool = False
    raw_response: Optional[dict] = None


class SmartCalendarConfig:
    """Env-driven config for the Perennia CRM Smart Calendar API."""

    def __init__(self):
        self.base_url = os.getenv("SMART_CALENDAR_API_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("SMART_CALENDAR_API_KEY", "")
        self.tenant_header = os.getenv("SMART_CALENDAR_TENANT_HEADER", "X-Tenant-ID")
        self.timeout_seconds = float(os.getenv("SMART_CALENDAR_TIMEOUT", "15"))
        self.max_retries = int(os.getenv("SMART_CALENDAR_MAX_RETRIES", "3"))
        self.default_meeting_minutes = int(
            os.getenv("SMART_CALENDAR_KICKOFF_MINUTES", "30")
        )
        self.default_lookahead_days = int(
            os.getenv("SMART_CALENDAR_LOOKAHEAD_DAYS", "5")
        )
        self.default_max_slots = int(
            os.getenv("SMART_CALENDAR_MAX_SLOTS", "4")
        )

    def assert_ready(self) -> None:
        if not self.base_url or not self.api_key:
            raise RuntimeError(
                "Smart Calendar config missing. Set SMART_CALENDAR_API_BASE_URL "
                "and SMART_CALENDAR_API_KEY."
            )


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

async def fetch_available_slots(
    tenant_id: str,
    loan_officer_nmlsr_id: str,
    duration_minutes: Optional[int] = None,
    lookahead_days: Optional[int] = None,
    max_slots: Optional[int] = None,
    caller_timezone: Optional[str] = None,
    meeting_type: str = "URLA_KICKOFF",
    config: Optional[SmartCalendarConfig] = None,
) -> List[AvailableSlot]:
    """
    Fetch open slots on the given LO's Smart Calendar.
    Returns [] on any failure — the agent falls back gracefully.
    """
    cfg = config or SmartCalendarConfig()
    cfg.assert_ready()

    params = {
        "loan_officer_nmlsr_id": loan_officer_nmlsr_id,
        "duration_minutes": duration_minutes or cfg.default_meeting_minutes,
        "lookahead_days": lookahead_days or cfg.default_lookahead_days,
        "max_slots": max_slots or cfg.default_max_slots,
        "meeting_type": meeting_type,
    }
    if caller_timezone:
        params["caller_timezone"] = caller_timezone

    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Accept": "application/json",
        cfg.tenant_header: tenant_id,
        "X-Source-System": "perennia-urla-voice-agent",
    }
    url = f"{cfg.base_url}/v1/calendar/availability"

    last_error: Optional[str] = None
    async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
        for attempt in range(1, cfg.max_retries + 1):
            try:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return [
                        AvailableSlot(
                            slot_id=s["slot_id"],
                            start=datetime.fromisoformat(s["start"]),
                            end=datetime.fromisoformat(s["end"]),
                            loan_officer_nmlsr_id=s.get(
                                "loan_officer_nmlsr_id", loan_officer_nmlsr_id
                            ),
                            loan_officer_name=s.get("loan_officer_name", ""),
                            timezone=s.get("timezone", "America/New_York"),
                        )
                        for s in data.get("slots", [])
                    ]
                if 400 <= resp.status_code < 500:
                    logger.error(
                        "Smart Calendar availability rejected",
                        extra={
                            "status": resp.status_code,
                            "body": resp.text[:500],
                        },
                    )
                    return []
                last_error = f"HTTP {resp.status_code}"
            except httpx.HTTPError as e:
                last_error = str(e)
                logger.warning(
                    "Smart Calendar availability transient failure",
                    extra={"attempt": attempt, "error": str(e)},
                )
            await asyncio.sleep(min(2 ** attempt, 4))

    logger.error(
        "Smart Calendar availability failed after retries",
        extra={"error": last_error},
    )
    return []


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

async def book_slot(
    tenant_id: str,
    slot_id: str,
    loan_id: str,
    borrower_name: str,
    borrower_phone: str,
    borrower_email: str,
    loan_officer_nmlsr_id: str,
    meeting_title: Optional[str] = None,
    meeting_type: str = "URLA_KICKOFF",
    notes: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    config: Optional[SmartCalendarConfig] = None,
) -> BookingResult:
    """
    Book the specified slot. Idempotent on loan_id + slot_id — safe to retry
    on transient failures without risk of double-booking.
    """
    cfg = config or SmartCalendarConfig()
    cfg.assert_ready()

    payload = {
        "slot_id": slot_id,
        "meeting_type": meeting_type,
        "meeting_title": meeting_title
            or f"Loan Application Kickoff — {borrower_name}",
        "duration_minutes": duration_minutes or cfg.default_meeting_minutes,
        "attendees": [
            {
                "role": "loan_officer",
                "nmlsr_id": loan_officer_nmlsr_id,
            },
            {
                "role": "borrower",
                "name": borrower_name,
                "phone": borrower_phone,
                "email": borrower_email,
            },
        ],
        "related_loan_id": loan_id,
        "notes": notes
            or "Post-application review call. Auto-booked via URLA voice agent.",
        "send_confirmations": True,
    }

    headers = {
        "Authorization": f"Bearer {cfg.api_key}",
        "Content-Type": "application/json",
        cfg.tenant_header: tenant_id,
        "X-Idempotency-Key": f"{loan_id}:{slot_id}",
        "X-Source-System": "perennia-urla-voice-agent",
    }
    url = f"{cfg.base_url}/v1/calendar/bookings"

    last_error: Optional[str] = None
    async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
        for attempt in range(1, cfg.max_retries + 1):
            try:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return BookingResult(
                        success=True,
                        event_id=data.get("event_id"),
                        confirmation_number=data.get("confirmation_number"),
                        scheduled_start=(
                            datetime.fromisoformat(data["scheduled_start"])
                            if data.get("scheduled_start") else None
                        ),
                        scheduled_end=(
                            datetime.fromisoformat(data["scheduled_end"])
                            if data.get("scheduled_end") else None
                        ),
                        scheduled_timezone=data.get("timezone"),
                        loan_officer_name=data.get("loan_officer_name"),
                        raw_response=data,
                    )
                if resp.status_code == 409:
                    # Slot was taken between availability fetch and booking.
                    # Agent should re-offer fresh slots.
                    return BookingResult(
                        success=False,
                        slot_no_longer_available=True,
                        error="SLOT_NO_LONGER_AVAILABLE",
                        raw_response=_try_json(resp),
                    )
                if 400 <= resp.status_code < 500:
                    return BookingResult(
                        success=False,
                        error=(
                            f"Calendar rejected booking ({resp.status_code}): "
                            f"{resp.text[:300]}"
                        ),
                        raw_response=_try_json(resp),
                    )
                last_error = f"HTTP {resp.status_code}"
            except httpx.HTTPError as e:
                last_error = str(e)
                logger.warning(
                    "Smart Calendar booking transient failure",
                    extra={"attempt": attempt, "error": str(e)},
                )
            await asyncio.sleep(min(2 ** attempt, 4))

    return BookingResult(
        success=False, error=last_error or "Unknown calendar error"
    )


def _try_json(resp: httpx.Response) -> Optional[dict]:
    try:
        return resp.json()
    except Exception:
        return None
