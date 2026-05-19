"""
Voicemail Drop Routes

This module contains all API endpoints for the voicemail drop system.
Extracted from main.py for better code organization.
"""

import asyncio
import os
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import Response, JSONResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from sqlalchemy import or_

from db import get_db
from utils.pii_mask import mask_phone

logger = logging.getLogger(__name__)


# OBS-002: Wrapper to surface background task failures in logs
async def _safe_background_task_vm(func, *args, task_name="unknown", **kwargs):
    """Wrapper that logs background task failures instead of silently dropping them."""
    try:
        if asyncio.iscoroutinefunction(func):
            await func(*args, **kwargs)
        else:
            func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Background task '{task_name}' failed: {e}", exc_info=True)


router = APIRouter(prefix="/api/v1/voicemail", tags=["Voicemail Drop"])

# =============================================================================
# TCPA Compliance Constants
# =============================================================================

# TCPA calling window: 8:00 AM - 9:00 PM in recipient's local timezone
TCPA_CALL_START = dt_time(8, 0)
TCPA_CALL_END = dt_time(21, 0)

# Allowed delivery methods for voicemail drops
ALLOWED_DELIVERY_METHODS = {"vapi_ai", "slybroadcast", "drop_cowboy", "direct", "ringless"}

# US area code to timezone mapping (covers major area codes)
# Falls back to America/New_York if unknown
AREA_CODE_TIMEZONE = {
    # Eastern Time
    "201": "America/New_York", "202": "America/New_York", "203": "America/New_York",
    "207": "America/New_York", "212": "America/New_York", "215": "America/New_York",
    "216": "America/New_York", "229": "America/New_York", "231": "America/New_York",
    "234": "America/New_York", "239": "America/New_York", "240": "America/New_York",
    "248": "America/New_York", "252": "America/New_York",
    "267": "America/New_York", "269": "America/New_York", "272": "America/New_York",
    "276": "America/New_York", "278": "America/New_York", "301": "America/New_York",
    "302": "America/New_York", "304": "America/New_York", "305": "America/New_York",
    "313": "America/New_York", "315": "America/New_York", "321": "America/New_York",
    "330": "America/New_York", "336": "America/New_York", "339": "America/New_York",
    "347": "America/New_York", "351": "America/New_York", "352": "America/New_York",
    "386": "America/New_York", "401": "America/New_York", "404": "America/New_York",
    "407": "America/New_York", "410": "America/New_York", "412": "America/New_York",
    "413": "America/New_York", "419": "America/New_York",
    "440": "America/New_York", "443": "America/New_York", "470": "America/New_York",
    "475": "America/New_York", "478": "America/New_York", "484": "America/New_York",
    "502": "America/New_York", "508": "America/New_York", "513": "America/New_York",
    "516": "America/New_York", "517": "America/New_York", "518": "America/New_York",
    "540": "America/New_York", "551": "America/New_York", "561": "America/New_York",
    "567": "America/New_York", "570": "America/New_York", "571": "America/New_York",
    "585": "America/New_York", "586": "America/New_York",
    "603": "America/New_York", "607": "America/New_York", "609": "America/New_York",
    "610": "America/New_York", "614": "America/New_York", "616": "America/New_York",
    "617": "America/New_York", "631": "America/New_York", "646": "America/New_York",
    "678": "America/New_York", "681": "America/New_York",
    "689": "America/New_York", "704": "America/New_York", "706": "America/New_York",
    "716": "America/New_York", "717": "America/New_York", "718": "America/New_York",
    "724": "America/New_York", "727": "America/New_York", "732": "America/New_York",
    "740": "America/New_York", "754": "America/New_York", "757": "America/New_York",
    "762": "America/New_York", "770": "America/New_York",
    "772": "America/New_York", "774": "America/New_York", "781": "America/New_York",
    "786": "America/New_York", "803": "America/New_York", "804": "America/New_York",
    "810": "America/New_York", "813": "America/New_York", "828": "America/New_York",
    "843": "America/New_York", "845": "America/New_York", "848": "America/New_York",
    "856": "America/New_York", "857": "America/New_York", "860": "America/New_York",
    "862": "America/New_York", "863": "America/New_York", "864": "America/New_York",
    "878": "America/New_York", "904": "America/New_York", "908": "America/New_York",
    "910": "America/New_York", "912": "America/New_York", "914": "America/New_York",
    "917": "America/New_York", "919": "America/New_York",
    "929": "America/New_York", "937": "America/New_York",
    "941": "America/New_York", "954": "America/New_York",
    "973": "America/New_York", "978": "America/New_York", "980": "America/New_York",
    # Central Time
    "205": "America/Chicago", "210": "America/Chicago", "214": "America/Chicago",
    "217": "America/Chicago", "218": "America/Chicago", "219": "America/Chicago",
    "224": "America/Chicago", "225": "America/Chicago", "228": "America/Chicago",
    "254": "America/Chicago", "256": "America/Chicago", "260": "America/Chicago",
    "262": "America/Chicago", "281": "America/Chicago", "309": "America/Chicago",
    "312": "America/Chicago", "314": "America/Chicago", "316": "America/Chicago",
    "317": "America/Chicago", "318": "America/Chicago", "319": "America/Chicago",
    "320": "America/Chicago", "325": "America/Chicago", "331": "America/Chicago",
    "334": "America/Chicago", "337": "America/Chicago", "346": "America/Chicago",
    "361": "America/Chicago", "380": "America/Chicago", "402": "America/Chicago",
    "405": "America/Chicago", "409": "America/Chicago", "417": "America/Chicago",
    "430": "America/Chicago", "432": "America/Chicago", "469": "America/Chicago",
    "479": "America/Chicago", "501": "America/Chicago", "504": "America/Chicago",
    "507": "America/Chicago", "512": "America/Chicago", "515": "America/Chicago",
    "531": "America/Chicago", "534": "America/Chicago",
    "539": "America/Chicago", "563": "America/Chicago", "573": "America/Chicago",
    "580": "America/Chicago", "608": "America/Chicago", "612": "America/Chicago",
    "615": "America/Chicago", "618": "America/Chicago", "620": "America/Chicago",
    "630": "America/Chicago", "636": "America/Chicago", "641": "America/Chicago",
    "660": "America/Chicago", "662": "America/Chicago", "682": "America/Chicago",
    "701": "America/Chicago", "708": "America/Chicago", "712": "America/Chicago",
    "713": "America/Chicago", "715": "America/Chicago",
    "726": "America/Chicago", "731": "America/Chicago", "737": "America/Chicago",
    "743": "America/Chicago", "769": "America/Chicago", "773": "America/Chicago",
    "779": "America/Chicago", "785": "America/Chicago", "806": "America/Chicago",
    "812": "America/Chicago", "815": "America/Chicago", "816": "America/Chicago",
    "817": "America/Chicago", "830": "America/Chicago", "832": "America/Chicago",
    "847": "America/Chicago", "850": "America/Chicago", "870": "America/Chicago",
    "872": "America/Chicago", "901": "America/Chicago", "903": "America/Chicago",
    "913": "America/Chicago", "918": "America/Chicago", "936": "America/Chicago",
    "938": "America/Chicago", "940": "America/Chicago", "945": "America/Chicago",
    "947": "America/Chicago", "956": "America/Chicago", "972": "America/Chicago",
    "979": "America/Chicago",
    # Corrected: these were previously in Eastern but are Central Time
    "251": "America/Chicago", "414": "America/Chicago", "601": "America/Chicago",
    "651": "America/Chicago", "763": "America/Chicago", "920": "America/Chicago",
    "931": "America/Chicago",
    # Mountain Time
    "303": "America/Denver", "307": "America/Denver", "385": "America/Denver",
    "406": "America/Denver", "435": "America/Denver", "505": "America/Denver",
    "575": "America/Denver", "602": "America/Phoenix", "623": "America/Phoenix",
    "720": "America/Denver", "801": "America/Denver", "928": "America/Phoenix",
    "970": "America/Denver", "480": "America/Phoenix",
    # Corrected: these were previously in Central but are Mountain Time
    "520": "America/Phoenix", "719": "America/Denver",
    # Pacific Time
    "206": "America/Los_Angeles", "208": "America/Los_Angeles",
    "209": "America/Los_Angeles", "213": "America/Los_Angeles",
    "253": "America/Los_Angeles", "310": "America/Los_Angeles",
    "323": "America/Los_Angeles", "341": "America/Los_Angeles",
    "360": "America/Los_Angeles", "369": "America/Los_Angeles",
    "408": "America/Los_Angeles", "415": "America/Los_Angeles",
    "424": "America/Los_Angeles", "425": "America/Los_Angeles",
    "442": "America/Los_Angeles", "458": "America/Los_Angeles",
    "503": "America/Los_Angeles", "509": "America/Los_Angeles",
    "510": "America/Los_Angeles", "530": "America/Los_Angeles",
    "541": "America/Los_Angeles", "559": "America/Los_Angeles",
    "562": "America/Los_Angeles", "564": "America/Los_Angeles",
    "619": "America/Los_Angeles", "626": "America/Los_Angeles",
    "628": "America/Los_Angeles", "650": "America/Los_Angeles",
    "657": "America/Los_Angeles", "661": "America/Los_Angeles",
    "669": "America/Los_Angeles", "702": "America/Los_Angeles",
    "707": "America/Los_Angeles", "714": "America/Los_Angeles",
    "725": "America/Los_Angeles", "747": "America/Los_Angeles",
    "760": "America/Los_Angeles", "775": "America/Los_Angeles",
    "805": "America/Los_Angeles", "818": "America/Los_Angeles",
    "831": "America/Los_Angeles", "858": "America/Los_Angeles",
    "909": "America/Los_Angeles", "916": "America/Los_Angeles",
    "925": "America/Los_Angeles", "935": "America/Los_Angeles",
    "949": "America/Los_Angeles", "951": "America/Los_Angeles",
    "971": "America/Los_Angeles",
    # Alaska / Hawaii
    "907": "America/Anchorage",
    "808": "Pacific/Honolulu",
}


# =============================================================================
# Runtime Import Helpers
# =============================================================================

# Use canonical auth (deduped from local wrapper)
from auth.dependencies import get_current_user


def get_voicemail_drop_model():
    """Get VoicemailDrop model - imports from main at runtime"""
    import main
    return main.VoicemailDrop


def get_voicemail_event_model():
    """Get VoicemailEvent model - imports from main at runtime"""
    import main
    return main.VoicemailEvent


def get_voicemail_template_model():
    """Get VoicemailTemplate model - imports from main at runtime"""
    import main
    return main.VoicemailTemplate


def get_voicemail_campaign_model():
    """Get VoicemailCampaign model - imports from main at runtime"""
    import main
    return main.VoicemailCampaign


# =============================================================================
# TCPA Compliance Helpers
# =============================================================================

def _normalize_phone(phone_number: str) -> str:
    """Normalize phone number to digits only, stripping +1 prefix."""
    digits = re.sub(r'\D', '', phone_number)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits


def _get_area_code(phone_number: str) -> Optional[str]:
    """Extract 3-digit area code from phone number."""
    digits = _normalize_phone(phone_number)
    if len(digits) >= 10:
        return digits[:3]
    return None


def _get_recipient_timezone(phone_number: str) -> str:
    """Infer timezone from phone area code. Falls back to America/New_York."""
    area_code = _get_area_code(phone_number)
    if area_code:
        return AREA_CODE_TIMEZONE.get(area_code, "America/New_York")
    return "America/New_York"


def check_calling_hours(phone_number: str) -> Tuple[bool, str]:
    """
    Check if current time is within TCPA calling hours (8am-9pm)
    in the recipient's local timezone.

    Returns (is_allowed, message).
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    tz_name = _get_recipient_timezone(phone_number)
    try:
        tz = ZoneInfo(tz_name)
    except Exception as e:
        logger.error(f"Error creating timezone '{tz_name}' in check_calling_hours: {e}")
        tz = ZoneInfo("America/New_York")

    recipient_now = datetime.now(tz)
    local_time = recipient_now.time()

    if local_time < TCPA_CALL_START or local_time >= TCPA_CALL_END:
        return False, (
            f"TCPA: Cannot call outside 8:00 AM - 9:00 PM recipient local time. "
            f"Current time in {tz_name}: {local_time.strftime('%I:%M %p')}"
        )
    return True, ""


def _check_national_dnc_scrub_freshness() -> Tuple[bool, str]:
    """
    Block outbound calls/voicemails if the National DNC Registry scrub data is stale.
    TCPA requires scrubbing against the National DNC Registry at least every 31 days.
    Set NATIONAL_DNC_LAST_SCRUB env var (ISO date) after each scrub.

    Returns (is_stale, message). If is_stale is True, the operation MUST be blocked.
    """
    last_scrub_date = os.getenv("NATIONAL_DNC_LAST_SCRUB")
    if not last_scrub_date:
        msg = (
            "National DNC scrub is stale: NATIONAL_DNC_LAST_SCRUB env var not set. "
            "TCPA requires National DNC Registry scrubbing every 31 days. "
            "All outbound calls are blocked until a valid scrub date is configured."
        )
        logger.error(msg)
        return True, msg

    try:
        scrub_dt = datetime.fromisoformat(last_scrub_date)
        if scrub_dt.tzinfo is None:
            scrub_dt = scrub_dt.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - scrub_dt).days
        if days_since > 31:
            msg = (
                f"National DNC Registry scrub is {days_since} days old (max 31). "
                "TCPA requires re-scrubbing. All outbound calls are blocked until "
                "NATIONAL_DNC_LAST_SCRUB is updated after a fresh scrub."
            )
            logger.error(msg)
            return True, msg
    except (ValueError, TypeError) as e:
        msg = (
            f"Invalid NATIONAL_DNC_LAST_SCRUB format: {e}. "
            "Cannot verify DNC scrub freshness. All outbound calls are blocked "
            "until a valid ISO date is set."
        )
        logger.error(msg)
        return True, msg

    return False, ""


def check_dnc_status(phone_number: str, db: Session, organization_id: Optional[int] = None) -> Tuple[bool, str]:
    """
    Check if phone number is on the Do Not Call list.
    Checks both internal DNC table and National DNC Registry scrub freshness.

    Returns (is_blocked, message).
    """
    from database.models.dialer import ContactDNCStatus

    digits = _normalize_phone(phone_number)

    # Normalize DNC entries to digits-only for reliable matching.
    # Uses SQL to strip non-digits so format variations (dashes, parens, +1) all match.
    suffix_param = f"%{digits[-10:]}" if len(digits) >= 10 else f"%{digits}"
    if organization_id is not None:
        dnc = db.execute(text("""
            SELECT id, reason FROM contact_dnc_status
            WHERE regexp_replace(phone_number, '[^0-9]', '', 'g') LIKE :suffix
              AND organization_id = :org_id
            LIMIT 1
        """), {"suffix": suffix_param, "org_id": organization_id}).fetchone()
    else:
        dnc = db.execute(text("""
            SELECT id, reason FROM contact_dnc_status
            WHERE regexp_replace(phone_number, '[^0-9]', '', 'g') LIKE :suffix
            LIMIT 1
        """), {"suffix": suffix_param}).fetchone()

    if dnc:
        return True, f"Phone number is on Do Not Call list (reason: {dnc[1] or 'N/A'})"

    # Check National DNC Registry scrub freshness (TCPA requires scrub every 31 days)
    # BLOCKING — TCPA mandates scrubbing against the National DNC Registry at least
    # every 31 days. A stale scrub means we cannot confirm the number is safe to call.
    is_stale, stale_msg = _check_national_dnc_scrub_freshness()
    if is_stale:
        logger.warning(f"DNC scrub stale — blocking call to {mask_phone(phone_number)}: {stale_msg}")
        return True, stale_msg  # Block the call

    return False, ""


def check_consent(lead_id: Optional[int], db: Session, organization_id: Optional[int] = None) -> Tuple[bool, str]:
    """
    Check if the lead/borrower has given communication consent.
    If no lead_id is provided, consent is assumed (manual dial).

    Returns (has_consent, message).
    """
    if not lead_id:
        # No lead associated — treated as manual outreach by LO
        return True, ""

    try:
        from database.models.borrower import BorrowerProfile
        import main

        # Check if the lead has an opt-out flag
        Lead = main.Lead
        lead_query = db.query(Lead).filter(Lead.id == lead_id)
        if organization_id is not None:
            lead_query = lead_query.filter(Lead.organization_id == organization_id)
        lead = lead_query.first()
        if not lead:
            return False, "Lead not found — denying voicemail drop (fail-closed)"

        # Check if lead has a matching BorrowerProfile with consent fields
        # BorrowerProfile doesn't have a phone column — match on email
        if lead.email:
            borrower = db.query(BorrowerProfile).filter(
                BorrowerProfile.email == lead.email
            ).first()

            if borrower:
                # Check if consent has been revoked
                if borrower.consent_revoked_at is not None:
                    return False, "Contact has revoked communication consent"

                if borrower.communication_consent is False:
                    return False, "Contact has opted out of communications"

                if borrower.marketing_consent is False:
                    # Allow transactional (loan status, doc requests) but warn about marketing
                    logger.info(
                        f"Lead {lead_id}: marketing_consent=False — "
                        "allowing transactional voicemail, blocking marketing"
                    )

                # FCC one-to-one consent: warn if consent_given_to is missing
                if not getattr(borrower, 'consent_given_to', None):
                    logger.info(
                        f"Lead {lead_id}: consent_given_to not recorded — "
                        "FCC one-to-one consent rule may not be satisfied"
                    )

    except ImportError:
        logger.warning("BorrowerProfile model not available for consent check")
    except Exception as e:
        logger.error("Consent check failed for lead %s: %s", lead_id, e)
        return False, "Consent verification unavailable — cannot proceed"

    return True, ""


def run_compliance_checks(
    phone_number: str,
    lead_id: Optional[int],
    db: Session,
    organization_id: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Run all TCPA compliance checks before sending a voicemail.

    Returns (is_allowed, rejection_reason).
    """
    # 1. DNC check (scoped to organization)
    is_blocked, dnc_msg = check_dnc_status(phone_number, db, organization_id=organization_id)
    if is_blocked:
        logger.warning(f"Voicemail blocked by DNC: {mask_phone(phone_number)}")
        return False, dnc_msg

    # 2. Consent check
    has_consent, consent_msg = check_consent(lead_id, db, organization_id=organization_id)
    if not has_consent:
        logger.warning(f"Voicemail blocked by consent: lead_id={lead_id}")
        return False, consent_msg

    # 3. Calling hours check
    is_allowed, hours_msg = check_calling_hours(phone_number)
    if not is_allowed:
        logger.warning(f"Voicemail blocked by calling hours: {mask_phone(phone_number)}")
        return False, hours_msg

    return True, None


# =============================================================================
# Rate Limiting
# =============================================================================

# Per-user rate limits
VOICEMAIL_DAILY_LIMIT = 100       # Max drops per user per day
VOICEMAIL_PER_MINUTE_LIMIT = 5    # Max drops per user per minute

# Thread-safe in-memory rate tracker with asyncio lock
_rate_tracker: dict = {}
_rate_lock = asyncio.Lock()
_RATE_TRACKER_MAX_KEYS = 5000


def _clean_stale_rate_entries():
    """Remove entries older than 24 hours to prevent memory growth. Must hold _rate_lock."""
    if len(_rate_tracker) < _RATE_TRACKER_MAX_KEYS:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    stale_keys = [
        uid for uid, timestamps in _rate_tracker.items()
        if not timestamps or timestamps[-1] < cutoff
    ]
    for key in stale_keys:
        del _rate_tracker[key]


async def check_rate_limit(user_id: int, db: Session, organization_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    """
    Check per-user voicemail drop rate limits.
    Uses async lock for thread-safety. Falls back to DB count for
    deploy-resilient daily limiting (in-memory only tracks burst/minute).

    Returns (is_allowed, rejection_reason).
    """
    async with _rate_lock:
        _clean_stale_rate_entries()

        now = datetime.now(timezone.utc)
        if user_id not in _rate_tracker:
            _rate_tracker[user_id] = []

        timestamps = _rate_tracker[user_id]

        # Clean old entries (older than 24h)
        day_ago = now - timedelta(hours=24)
        timestamps[:] = [ts for ts in timestamps if ts > day_ago]

        # Check per-minute limit (in-memory — instant burst protection)
        minute_ago = now - timedelta(minutes=1)
        recent_count = sum(1 for ts in timestamps if ts > minute_ago)
        if recent_count >= VOICEMAIL_PER_MINUTE_LIMIT:
            return False, f"Too many voicemails sent. Limit: {VOICEMAIL_PER_MINUTE_LIMIT}/minute."

        # Record this attempt
        timestamps.append(now)

    # Check daily limit via DB (survives deploys)
    try:
        VoicemailDrop = get_voicemail_drop_model()
        day_start = now - timedelta(hours=24)
        daily_query = db.query(func.count(VoicemailDrop.id)).filter(
            VoicemailDrop.user_id == user_id,
            VoicemailDrop.created_at >= day_start,
        )
        if organization_id is not None:
            daily_query = daily_query.filter(VoicemailDrop.organization_id == organization_id)
        daily_count = daily_query.scalar() or 0
        if daily_count >= VOICEMAIL_DAILY_LIMIT:
            return False, f"Daily voicemail limit reached ({VOICEMAIL_DAILY_LIMIT}/day). Try again tomorrow."
    except Exception as e:
        logger.warning(f"DB rate limit check failed, using in-memory only: {e}")
        # Fallback to in-memory daily count
        if len(timestamps) >= VOICEMAIL_DAILY_LIMIT:
            return False, f"Daily voicemail limit reached ({VOICEMAIL_DAILY_LIMIT}/day). Try again tomorrow."

    return True, None


# =============================================================================
# Helper Functions
# =============================================================================

async def send_voicemail_via_vapi(
    phone_number: str,
    message: str,
    recipient_name: str,
    user_name: str,
    voicemail_drop_id: int,
    db: Session,
    voice_provider: str = "deepgram",
    voice_id: str = "asteria",
    voice_speed: float = 1.0,
    audio_url: str = None,
) -> dict:
    """Helper function to send voicemail using Vapi AI"""
    import httpx

    vapi_api_key = os.getenv("VAPI_API_KEY")
    # VAPI_PHONE_NUMBER_ID is the Vapi phone number resource (not the assistant)
    # Falls back to VAPI_ASSISTANT_ID for backward compatibility
    vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID") or os.getenv("VAPI_ASSISTANT_ID")
    vapi_assistant_id = os.getenv("VAPI_VOICEMAIL_ASSISTANT_ID") or os.getenv("VAPI_ASSISTANT_ID")

    if not vapi_api_key:
        raise HTTPException(status_code=503, detail="Vapi API key not configured")

    # Format phone number to E.164 format
    clean_number = ''.join(filter(str.isdigit, phone_number))
    if len(clean_number) == 10:
        clean_number = f"+1{clean_number}"
    elif len(clean_number) == 11 and clean_number.startswith('1'):
        clean_number = f"+{clean_number}"

    # Create voicemail assistant configuration
    greeting = f"Hi {recipient_name}, " if recipient_name else "Hello, "
    full_message = (
        f"{greeting}this is calling from {user_name}'s office. "
        f"{message} "
        f"Feel free to call us back at your convenience. "
        f"If you no longer wish to receive these calls, please call us back and ask to be placed on our do-not-call list. "
        f"Have a great day!"
    )

    # Build voice config from template settings
    voice_config = {
        "provider": voice_provider or "deepgram",
        "voiceId": voice_id or "asteria",
    }
    if voice_speed and voice_speed != 1.0:
        voice_config["speed"] = float(voice_speed)

    # Vapi call configuration
    vapi_payload = {
        "phoneNumberId": vapi_phone_number_id,
        "assistantId": vapi_assistant_id,
        "customer": {
            "number": clean_number,
            "name": recipient_name
        },
        "assistantOverrides": {
            "firstMessage": full_message,
            "model": {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.7
            },
            "voice": voice_config,
            "endCallFunctionEnabled": True,
            "endCallMessage": "Thank you, goodbye!",
            "voicemailMessage": full_message,
            "voicemailDetection": {
                "provider": "vapi",
                "beepMaxAwaitSeconds": 25,
            }
        },
        "metadata": {
            "voicemail_drop_id": voicemail_drop_id,
            "type": "voicemail_drop"
        }
    }

    # If audio URL is provided, use it as the voicemail message
    if audio_url:
        vapi_payload["assistantOverrides"]["voicemailMessage"] = audio_url

    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.vapi.ai/call/phone",
                    headers={
                        "Authorization": f"Bearer {vapi_api_key}",
                        "Content-Type": "application/json"
                    },
                    json=vapi_payload
                )

                if response.status_code not in [200, 201]:
                    error_msg = response.text
                    # Don't retry client errors (4xx)
                    if 400 <= response.status_code < 500:
                        logger.error(f"Vapi API client error (no retry): {error_msg}")
                        raise HTTPException(status_code=500, detail="Voice call initiation failed")
                    # Retry server errors (5xx)
                    logger.warning(f"Vapi API server error (attempt {attempt + 1}/{max_retries}): {error_msg}")
                    last_error = error_msg
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                        continue
                    raise HTTPException(status_code=500, detail="Voice call initiation failed after retries")

                result = response.json()
                call_id = result.get("id")

                logger.info(f"Vapi call initiated: {call_id}")

                return {
                    "success": True,
                    "call_id": call_id,
                    "vapi_response": result
                }

        except httpx.HTTPError as e:
            last_error = str(e)
            logger.warning(f"HTTP error calling Vapi (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise HTTPException(status_code=500, detail=f"Failed to initiate call after {max_retries} attempts: {last_error}")


# =============================================================================
# SMS Follow-up After Voicemail Drop
# =============================================================================

async def _send_followup_sms(
    *,
    voicemail_drop_id: int,
    phone_number: str,
    contact_name: str,
    lo_name: str,
    lo_phone: str,
    user_id: int,
    lead_id: Optional[int],
    organization_id: Optional[int],
):
    """
    Send a follow-up SMS after a voicemail drop.

    Best-effort: failures are logged but never propagated to the caller.
    Uses its own DB session so the parent request is not affected.
    Compliance gate (DNC, quiet hours, opt-out) runs via send_sms_verified_async.
    """
    from db import SessionLocal
    from database.tenant_mixin import set_tenant_context

    db = SessionLocal()
    # TENANT-017: Set RLS context for background task
    if organization_id:
        try:
            set_tenant_context(db, organization_id)
        except Exception as _exc:  # noqa: BLE001
            pass
    try:
        from telephony.sms import send_sms_verified_async

        # Build a concise, professional follow-up message
        if contact_name and contact_name.strip():
            greeting = f"Hi {contact_name.strip().split()[0]}"
        else:
            greeting = "Hi"

        if lo_phone:
            cta = f"Feel free to call me back at {lo_phone} or reply to this text."
        else:
            cta = "Feel free to reply to this text or call me back."

        sms_text = (
            f"{greeting}, I just left you a voicemail regarding your mortgage. "
            f"{cta} — {lo_name}"
        )

        result = await send_sms_verified_async(
            to=phone_number,
            text=sms_text,
            user_id=user_id,
            lead_id=lead_id,
            organization_id=organization_id,
            db=db,
            bypass_compliance=False,
        )

        VoicemailDrop = get_voicemail_drop_model()
        drop = db.query(VoicemailDrop).filter(VoicemailDrop.id == voicemail_drop_id).first()
        if drop:
            if result.get("status") == "sent":
                drop.followup_sms_sent = True
                drop.followup_sms_id = result.get("id")
                logger.info(
                    "SMS follow-up sent for voicemail drop %s (msg_id=%s)",
                    voicemail_drop_id,
                    result.get("id"),
                )
            else:
                drop.followup_sms_sent = False
                drop.followup_sms_blocked_reason = result.get("reason", "unknown")[:500]
                logger.info(
                    "SMS follow-up blocked for voicemail drop %s: %s",
                    voicemail_drop_id,
                    result.get("reason"),
                )
            db.commit()

    except Exception as e:
        logger.error(
            "SMS follow-up failed for voicemail drop %s: %s",
            voicemail_drop_id,
            e,
            exc_info=True,
        )
        # Best-effort: update the drop record if possible
        try:
            VoicemailDrop = get_voicemail_drop_model()
            drop = db.query(VoicemailDrop).filter(VoicemailDrop.id == voicemail_drop_id).first()
            if drop:
                drop.followup_sms_sent = False
                drop.followup_sms_blocked_reason = f"Error: {str(e)[:480]}"
                db.commit()
        except Exception as _exc:  # noqa: BLE001
            pass
    finally:
        db.close()


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/drop")
async def create_voicemail_drop(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Create and send a single voicemail drop

    Request body:
    {
        "phone_number": "925-389-6782",
        "recipient_name": "John Doe",
        "message": "Your closing documents are ready",
        "lead_id": 123,  // optional
        "loan_id": 456,  // optional
        "template_id": 1,  // optional
        "send_followup_sms": true  // optional, default true — send SMS after VM drop
    }
    """
    VoicemailDrop = get_voicemail_drop_model()
    VoicemailEvent = get_voicemail_event_model()

    try:
        data = await request.json()

        phone_number = data.get("phone_number")
        recipient_name = data.get("recipient_name", "")
        recipient_email = data.get("recipient_email") or data.get("email")
        message = data.get("message")
        lead_id = data.get("lead_id")
        loan_id = data.get("loan_id")
        template_id = data.get("template_id")
        send_followup_sms = data.get("send_followup_sms", True)
        # TCPA-D4: audio duration (seconds) when caller pre-validates an upload
        duration_seconds = data.get("duration_seconds")

        if not phone_number:
            raise HTTPException(status_code=400, detail="Phone number is required")

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # --- TCPA-D4: explicit consent_revoked_at enforcement (BorrowerProfile) ---
        # Fail-closed on revocation; fail-open on lookup error.  Runs BEFORE the
        # broader run_compliance_checks because we want a deterministic 403 body
        # the frontend can act on (revoked_at timestamp).
        try:
            from database.models.borrower import BorrowerProfile
            lookup_email = recipient_email
            if not lookup_email and lead_id:
                try:
                    import main as _main_for_lead
                    _lead = db.query(_main_for_lead.Lead).filter(
                        _main_for_lead.Lead.id == lead_id
                    ).first()
                    if _lead and getattr(_lead, "email", None):
                        lookup_email = _lead.email
                except Exception as _lead_err:
                    logger.warning(
                        "TCPA-D4: lead email lookup failed (fail-open): %s", _lead_err
                    )
            if lookup_email:
                borrower_for_consent = db.query(BorrowerProfile).filter(
                    BorrowerProfile.email == lookup_email
                ).first()
                if borrower_for_consent and getattr(
                    borrower_for_consent, "consent_revoked_at", None
                ) is not None:
                    revoked_ts = borrower_for_consent.consent_revoked_at
                    try:
                        revoked_iso = revoked_ts.isoformat()
                    except Exception:
                        revoked_iso = str(revoked_ts)
                    logger.warning(
                        "TCPA-D4: voicemail blocked — consent revoked for %s at %s",
                        mask_phone(phone_number),
                        revoked_iso,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": "consent_revoked",
                            "message": "Recipient has revoked communication consent — voicemail blocked under TCPA.",
                            "revoked_at": revoked_iso,
                        },
                    )
        except HTTPException:
            raise
        except Exception as _consent_err:
            # Fail-open on lookup error per spec
            logger.warning(
                "TCPA-D4: BorrowerProfile consent lookup failed (fail-open): %s",
                _consent_err,
            )

        # --- TCPA Compliance Checks ---
        org_id = getattr(current_user, 'organization_id', None)
        is_allowed, rejection_reason = run_compliance_checks(
            phone_number=phone_number,
            lead_id=lead_id,
            db=db,
            organization_id=org_id,
        )
        if not is_allowed:
            logger.warning(
                f"Voicemail drop blocked for {phone_number}: {rejection_reason} "
                f"(user={current_user.id})"
            )
            raise HTTPException(status_code=403, detail=rejection_reason)

        # --- TCPA-D4: audio duration validation (>= 5 seconds) ---
        # Slybroadcast hard-rejects audio < 5s.  We pre-validate via either:
        #   1. mutagen on the local file referenced by template.audio_url, or
        #   2. caller-supplied duration_seconds in the request body.
        # If neither is available and we're about to submit to Slybroadcast,
        # fail-closed with HTTP 400.
        delivery_method_for_check = None
        _template_audio_url_for_check = None
        try:
            if template_id:
                # Best-effort: re-read template to know which delivery_method we'll use
                from sqlalchemy import text as _text
                _row = db.execute(
                    _text("SELECT delivery_method, audio_url FROM voicemail_templates WHERE id = :tid"),
                    {"tid": template_id},
                ).fetchone()
                if _row:
                    delivery_method_for_check = _row[0]
                    _template_audio_url_for_check = _row[1]
            if not delivery_method_for_check:
                delivery_method_for_check = os.getenv("VOICEMAIL_DELIVERY_METHOD", "vapi_ai")
        except Exception:
            delivery_method_for_check = os.getenv("VOICEMAIL_DELIVERY_METHOD", "vapi_ai")

        _needs_sb_check = delivery_method_for_check in ("slybroadcast", "ringless")
        if _needs_sb_check:
            MIN_DURATION = 5.0
            duration_ok = False
            # Path 1: mutagen on local file referenced by template
            try:
                if _template_audio_url_for_check:
                    local_filename = str(_template_audio_url_for_check).rstrip("/").split("/")[-1]
                    upload_dir = os.path.join(
                        os.path.dirname(__file__), "..", "uploads", "voicemail_audio"
                    )
                    local_path = os.path.join(upload_dir, local_filename)
                    if os.path.isfile(local_path):
                        try:
                            import mutagen  # noqa: F401
                            from mutagen.mp3 import MP3 as _MP3
                            audio_obj = _MP3(local_path)
                            if audio_obj.info.length >= MIN_DURATION:
                                duration_ok = True
                            else:
                                logger.warning(
                                    "TCPA-D4: audio file too short via mutagen: %.2fs",
                                    audio_obj.info.length,
                                )
                                return JSONResponse(
                                    status_code=400,
                                    content={
                                        "error": "audio_too_short",
                                        "message": f"Audio is {audio_obj.info.length:.1f}s; Slybroadcast requires >= {MIN_DURATION:.0f}s.",
                                    },
                                )
                        except ImportError:
                            # mutagen unavailable; fall through to duration_seconds path
                            pass
            except Exception as _dur_err:
                logger.debug("TCPA-D4: mutagen check skipped: %s", _dur_err)

            # Path 2: caller-supplied duration_seconds
            if not duration_ok:
                if duration_seconds is None:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "audio_too_short",
                            "message": "duration_seconds required when audio length cannot be measured server-side.",
                        },
                    )
                try:
                    if float(duration_seconds) < MIN_DURATION:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": "audio_too_short",
                                "message": f"Audio is {float(duration_seconds):.1f}s; Slybroadcast requires >= {MIN_DURATION:.0f}s.",
                            },
                        )
                except (TypeError, ValueError):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "audio_too_short",
                            "message": "duration_seconds must be numeric.",
                        },
                    )

        # --- Rate Limiting ---
        is_allowed, rate_msg = await check_rate_limit(current_user.id, db, organization_id=org_id)
        if not is_allowed:
            raise HTTPException(status_code=429, detail=rate_msg)

        # --- Idempotency: prevent duplicate drops within 60 seconds ---
        if org_id is not None:
            recent_dup = db.execute(text("""
                SELECT id FROM voicemail_drops
                WHERE user_id = :uid AND phone_number = :phone
                  AND organization_id = :org_id
                  AND created_at > NOW() - INTERVAL '60 seconds'
                LIMIT 1
            """), {"uid": current_user.id, "phone": phone_number, "org_id": org_id}).fetchone()
        else:
            recent_dup = db.execute(text("""
                SELECT id FROM voicemail_drops
                WHERE user_id = :uid AND phone_number = :phone
                  AND created_at > NOW() - INTERVAL '60 seconds'
                LIMIT 1
            """), {"uid": current_user.id, "phone": phone_number}).fetchone()
        if recent_dup:
            raise HTTPException(
                status_code=409,
                detail="A voicemail to this number was already sent in the last 60 seconds"
            )

        # Load template voice settings if template_id provided
        VoicemailTemplate = get_voicemail_template_model()
        voice_provider = "deepgram"
        voice_id = "asteria"
        voice_speed = 1.0
        audio_url = None
        delivery_method = os.getenv("VOICEMAIL_DELIVERY_METHOD", "vapi_ai")

        if template_id:
            template_query = db.query(VoicemailTemplate).filter(
                VoicemailTemplate.id == template_id
            )
            if org_id is not None:
                template_query = template_query.filter(
                    or_(
                        VoicemailTemplate.organization_id == None,
                        VoicemailTemplate.organization_id == org_id,
                    )
                )
            template = template_query.first()
            if template:
                voice_provider = template.voice_provider or voice_provider
                voice_id = template.voice_id or voice_id
                voice_speed = float(template.voice_speed) if template.voice_speed else voice_speed
                audio_url = template.audio_url
                delivery_method = template.delivery_method or delivery_method
                if delivery_method not in ALLOWED_DELIVERY_METHODS:
                    raise HTTPException(status_code=400, detail=f"Invalid delivery method: {delivery_method}")
                # Increment usage atomically
                db.execute(text("""
                    UPDATE voicemail_templates
                    SET times_used = COALESCE(times_used, 0) + 1,
                        last_used_at = NOW()
                    WHERE id = :tid
                """), {"tid": template_id})
                db.flush()

        # Create voicemail drop record
        voicemail_drop = VoicemailDrop(
            user_id=current_user.id,
            organization_id=getattr(current_user, 'organization_id', None),
            lead_id=lead_id,
            loan_id=loan_id,
            template_id=template_id,
            contact_name=recipient_name,
            phone_number=phone_number,
            message_text=message,
            delivery_method=delivery_method,
            status='pending'
        )
        db.add(voicemail_drop)
        db.commit()
        db.refresh(voicemail_drop)

        # Create event
        event = VoicemailEvent(
            voicemail_drop_id=voicemail_drop.id,
            event_type='queued',
            event_data={"message": "Voicemail queued for delivery"}
        )
        db.add(event)
        db.commit()

        # Send voicemail via configured delivery method
        # Ringless (Slybroadcast) is preferred; falls back to Vapi if it fails.
        async def _deliver_via_vapi():
            """Deliver voicemail via Vapi AI outbound call."""
            vapi_result = await send_voicemail_via_vapi(
                phone_number=phone_number,
                message=message,
                recipient_name=recipient_name,
                user_name=current_user.full_name or "your loan officer",
                voicemail_drop_id=voicemail_drop.id,
                db=db,
                voice_provider=voice_provider,
                voice_id=voice_id,
                voice_speed=voice_speed,
                audio_url=audio_url,
            )
            voicemail_drop.vapi_call_id = vapi_result.get("call_id")
            voicemail_drop.status = 'calling'
            voicemail_drop.delivery_attempts = (voicemail_drop.delivery_attempts or 0) + 1
            voicemail_drop.last_attempt_at = datetime.now(timezone.utc)
            db.commit()

            calling_event = VoicemailEvent(
                voicemail_drop_id=voicemail_drop.id,
                event_type='calling',
                event_data={"vapi_call_id": vapi_result.get("call_id")}
            )
            db.add(calling_event)
            db.commit()
            logger.info(f"Voicemail drop {voicemail_drop.id} initiated via Vapi")
            return {
                "success": True,
                "voicemail_drop_id": voicemail_drop.id,
                "vapi_call_id": vapi_result.get("call_id"),
                "status": "calling",
                "message": "Voicemail is being delivered"
            }

        # Helper to fire SMS follow-up as a background task (best-effort)
        async def _maybe_send_followup_sms(result_dict: dict) -> dict:
            """If SMS follow-up is enabled, fire it as a background task
            and annotate the response dict. Never fails the voicemail drop."""
            if not send_followup_sms:
                result_dict["followup_sms"] = "disabled"
                return result_dict

            try:
                lo_phone = getattr(current_user, 'phone', '') or ''
                lo_name = current_user.full_name or "Your Loan Officer"
                asyncio.ensure_future(_safe_background_task_vm(
                    _send_followup_sms,
                    task_name=f"sms_followup_drop_{voicemail_drop.id}",
                    voicemail_drop_id=voicemail_drop.id,
                    phone_number=phone_number,
                    contact_name=recipient_name,
                    lo_name=lo_name,
                    lo_phone=lo_phone,
                    user_id=current_user.id,
                    lead_id=lead_id,
                    organization_id=org_id,
                ))
                result_dict["followup_sms"] = "queued"
            except Exception as sms_err:
                logger.error(
                    "Failed to queue SMS follow-up for drop %s: %s",
                    voicemail_drop.id,
                    sms_err,
                )
                result_dict["followup_sms"] = "error"
            return result_dict

        try:
            if delivery_method == "ringless":
                try:
                    rvm_result = await send_voicemail_ringless(
                        phone_number=phone_number,
                        message=message,
                        audio_url=audio_url,
                        voicemail_drop_id=voicemail_drop.id,
                        voice=voice_id or "nova",
                        voice_speed=float(voice_speed or 1.0),
                    )

                    voicemail_drop.rvm_session_id = rvm_result.get("session_id")
                    voicemail_drop.rvm_provider = rvm_result.get("provider")
                    voicemail_drop.status = 'sending'
                    voicemail_drop.delivery_attempts = 1
                    voicemail_drop.last_attempt_at = datetime.now(timezone.utc)
                    db.commit()

                    sending_event = VoicemailEvent(
                        voicemail_drop_id=voicemail_drop.id,
                        event_type='sending',
                        event_data={
                            "rvm_session_id": rvm_result.get("session_id"),
                            "provider": rvm_result.get("provider"),
                        }
                    )
                    db.add(sending_event)
                    db.commit()
                    logger.info(f"RVM drop {voicemail_drop.id} submitted to {rvm_result.get('provider')}")

                    response = {
                        "success": True,
                        "voicemail_drop_id": voicemail_drop.id,
                        "rvm_session_id": rvm_result.get("session_id"),
                        "provider": rvm_result.get("provider"),
                        "status": "sending",
                        "message": "Ringless voicemail submitted for delivery"
                    }
                    return await _maybe_send_followup_sms(response)
                except Exception as rvm_err:
                    # Ringless failed — fall back to Vapi AI call
                    logger.warning(
                        f"Ringless delivery failed for drop {voicemail_drop.id}, "
                        f"falling back to Vapi: {rvm_err}"
                    )
                    fallback_event = VoicemailEvent(
                        voicemail_drop_id=voicemail_drop.id,
                        event_type='fallback',
                        event_data={
                            "original_method": "ringless",
                            "fallback_method": "vapi_ai",
                            "reason": str(rvm_err)[:300],
                        }
                    )
                    db.add(fallback_event)
                    db.commit()
                    voicemail_drop.delivery_method = "vapi_ai"
                    db.commit()
                    vapi_response = await _deliver_via_vapi()
                    return await _maybe_send_followup_sms(vapi_response)
            else:
                vapi_response = await _deliver_via_vapi()
                return await _maybe_send_followup_sms(vapi_response)

        except Exception as e:
            voicemail_drop.status = 'failed'
            voicemail_drop.error_message = str(e)[:500]
            db.commit()

            failed_event = VoicemailEvent(
                voicemail_drop_id=voicemail_drop.id,
                event_type='failed',
                event_data={"error": "Internal server error"}
            )
            db.add(failed_event)
            db.commit()

            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating voicemail drop: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/transcribe")
async def transcribe_voice_message(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Transcribe voice recording using OpenAI Whisper

    Request body should be multipart/form-data with:
    - audio_file: The audio file to transcribe
    """
    try:
        import httpx

        form_data = await request.form()
        audio_file = form_data.get("audio_file")

        if not audio_file:
            raise HTTPException(status_code=400, detail="Audio file is required")

        # Validate file type
        ALLOWED_AUDIO_TYPES = {
            "audio/webm", "audio/mp3", "audio/mpeg", "audio/wav",
            "audio/wave", "audio/x-wav", "audio/ogg", "audio/mp4",
            "audio/m4a", "audio/x-m4a", "audio/flac",
        }
        ALLOWED_EXTENSIONS = {".webm", ".mp3", ".wav", ".ogg", ".m4a", ".mp4", ".flac"}
        MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB (Whisper API limit)

        content_type = getattr(audio_file, 'content_type', '') or ''
        filename = getattr(audio_file, 'filename', '') or 'audio.webm'
        file_ext = os.path.splitext(filename)[1].lower()

        if content_type and content_type not in ALLOWED_AUDIO_TYPES:
            if file_ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid audio file type: {content_type}. Allowed: webm, mp3, wav, ogg, m4a, mp4, flac"
                )

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=503, detail="OpenAI API key not configured")

        # Read audio file with size limit
        audio_data = await audio_file.read()
        if len(audio_data) > MAX_AUDIO_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large ({len(audio_data) // (1024*1024)}MB). Maximum: 25MB"
            )
        if len(audio_data) == 0:
            raise HTTPException(status_code=400, detail="Audio file is empty")

        # Infer content type for Whisper from extension
        ext_to_mime = {
            ".webm": "audio/webm", ".mp3": "audio/mpeg", ".wav": "audio/wav",
            ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".mp4": "audio/mp4",
            ".flac": "audio/flac",
        }
        upload_mime = ext_to_mime.get(file_ext, content_type or "audio/webm")

        # Call OpenAI Whisper API
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {
                'file': (filename, audio_data, upload_mime),
                'model': (None, 'whisper-1')
            }

            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {openai_api_key}"
                },
                files=files
            )

            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Whisper API error: {error_msg}")
                raise HTTPException(status_code=500, detail="Transcription failed")

            result = response.json()
            transcription = result.get("text", "")

            logger.info(f"Transcribed voice message: {transcription[:100]}...")

            return {
                "success": True,
                "transcription": transcription
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transcribing voice: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/templates")
async def get_voicemail_templates(
    category: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get voicemail templates (default templates + user's custom templates)"""
    VoicemailTemplate = get_voicemail_template_model()

    try:
        org_id = getattr(current_user, 'organization_id', None)
        query = db.query(VoicemailTemplate).filter(
            VoicemailTemplate.is_active == True
        ).filter(
            or_(
                VoicemailTemplate.user_id == None,  # Default templates
                VoicemailTemplate.user_id == current_user.id  # User's templates
            )
        )
        if org_id is not None:
            query = query.filter(
                or_(
                    VoicemailTemplate.organization_id == None,  # Default/global templates
                    VoicemailTemplate.organization_id == org_id,
                )
            )

        if category:
            query = query.filter(VoicemailTemplate.category == category)

        templates = query.order_by(
            VoicemailTemplate.is_default.desc(),
            VoicemailTemplate.name
        ).all()

        return {
            "success": True,
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "category": t.category,
                    "message_text": t.message_text,
                    "variables": t.variables,
                    "is_default": t.is_default,
                    "times_used": t.times_used,
                    "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None,
                    "audio_url": t.audio_url,
                    "voice_provider": t.voice_provider,
                    "voice_id": t.voice_id,
                    "voice_speed": float(t.voice_speed) if t.voice_speed else 1.0,
                    "delivery_method": t.delivery_method,
                }
                for t in templates
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/templates")
async def create_voicemail_template(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new voicemail template"""
    VoicemailTemplate = get_voicemail_template_model()

    try:
        data = await request.json()

        name = data.get("name")
        category = data.get("category", "custom")
        message_text = data.get("message_text")
        variables = data.get("variables", [])

        if not name:
            raise HTTPException(status_code=400, detail="Template name is required")

        if not message_text:
            raise HTTPException(status_code=400, detail="Message text is required")

        template = VoicemailTemplate(
            user_id=current_user.id,
            organization_id=getattr(current_user, 'organization_id', None),
            name=name,
            category=category,
            message_text=message_text,
            variables=variables,
            voice_provider=data.get("voice_provider", "deepgram"),
            voice_id=data.get("voice_id", "asteria"),
            voice_speed=data.get("voice_speed", 1.0),
            delivery_method=data.get("delivery_method", "vapi_ai") if data.get("delivery_method", "vapi_ai") in ALLOWED_DELIVERY_METHODS else "vapi_ai",
            is_active=True,
            is_default=False
        )

        db.add(template)
        db.commit()
        db.refresh(template)

        logger.info(f"Created voicemail template {template.id} for user {current_user.id}")

        return {
            "success": True,
            "template": {
                "id": template.id,
                "name": template.name,
                "category": template.category,
                "message_text": template.message_text,
                "variables": template.variables,
                "audio_url": template.audio_url,
                "voice_provider": template.voice_provider,
                "voice_id": template.voice_id,
                "voice_speed": float(template.voice_speed) if template.voice_speed else 1.0,
                "delivery_method": template.delivery_method,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/history")
async def get_voicemail_history(
    limit: int = 50,
    offset: int = 0,
    status: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get voicemail drop history for current user"""
    VoicemailDrop = get_voicemail_drop_model()

    try:
        org_id = getattr(current_user, 'organization_id', None)
        query = db.query(VoicemailDrop).filter(
            VoicemailDrop.user_id == current_user.id
        )
        if org_id is not None:
            query = query.filter(VoicemailDrop.organization_id == org_id)

        if status:
            query = query.filter(VoicemailDrop.status == status)

        total = query.count()

        voicemails = query.order_by(
            VoicemailDrop.created_at.desc()
        ).offset(offset).limit(limit).all()

        return {
            "success": True,
            "total": total,
            "voicemails": [
                {
                    "id": vm.id,
                    "contact_name": vm.contact_name,
                    "phone_number": vm.phone_number,
                    "message_text": vm.message_text,
                    "status": vm.status,
                    "delivery_method": vm.delivery_method,
                    "rvm_provider": getattr(vm, "rvm_provider", None),
                    "created_at": vm.created_at.isoformat(),
                    "delivered_at": vm.delivered_at.isoformat() if vm.delivered_at else None,
                    "call_duration": vm.call_duration,
                    "call_cost": float(vm.call_cost) if vm.call_cost else None,
                    "callback_received": vm.callback_received,
                    "error_message": vm.error_message,
                    "followup_sms_sent": getattr(vm, "followup_sms_sent", None),
                    "followup_sms_blocked_reason": getattr(vm, "followup_sms_blocked_reason", None),
                }
                for vm in voicemails
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching voicemail history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analytics")
async def get_voicemail_analytics(
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get voicemail analytics for current user"""
    VoicemailDrop = get_voicemail_drop_model()

    try:
        # Default to last 30 days
        if not start_date:
            start_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        if not end_date:
            end_date = datetime.now(timezone.utc).isoformat()

        # Parse dates
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        # Base filters — reused for each independent query to avoid mutation bug
        org_id = getattr(current_user, 'organization_id', None)
        base_filters = [
            VoicemailDrop.user_id == current_user.id,
            VoicemailDrop.created_at >= start,
            VoicemailDrop.created_at <= end,
        ]
        if org_id is not None:
            base_filters.append(VoicemailDrop.organization_id == org_id)

        total_sent = db.query(func.count(VoicemailDrop.id)).filter(
            *base_filters
        ).scalar() or 0

        delivered = db.query(func.count(VoicemailDrop.id)).filter(
            *base_filters, VoicemailDrop.status == 'delivered'
        ).scalar() or 0

        failed = db.query(func.count(VoicemailDrop.id)).filter(
            *base_filters, VoicemailDrop.status == 'failed'
        ).scalar() or 0

        callbacks = db.query(func.count(VoicemailDrop.id)).filter(
            *base_filters, VoicemailDrop.callback_received == True
        ).scalar() or 0

        # Calculate total cost
        cost_result = db.query(func.sum(VoicemailDrop.call_cost)).filter(
            *base_filters
        ).scalar()
        total_cost = float(cost_result) if cost_result else 0.0

        # Calculate average duration
        duration_result = db.query(func.avg(VoicemailDrop.call_duration)).filter(
            *base_filters, VoicemailDrop.call_duration != None
        ).scalar()
        avg_duration = int(duration_result) if duration_result else 0

        # Delivery rate
        delivery_rate = (delivered / total_sent * 100) if total_sent > 0 else 0

        # Callback rate
        callback_rate = (callbacks / delivered * 100) if delivered > 0 else 0

        # SMS follow-up metrics
        sms_followup_sent = db.query(func.count(VoicemailDrop.id)).filter(
            *base_filters, VoicemailDrop.followup_sms_sent == True
        ).scalar() or 0

        sms_followup_blocked = db.query(func.count(VoicemailDrop.id)).filter(
            *base_filters,
            VoicemailDrop.followup_sms_sent == False,
            VoicemailDrop.followup_sms_blocked_reason != None,
        ).scalar() or 0

        return {
            "success": True,
            "analytics": {
                "total_sent": total_sent,
                "delivered": delivered,
                "failed": failed,
                "callbacks_received": callbacks,
                "delivery_rate": round(delivery_rate, 2),
                "callback_rate": round(callback_rate, 2),
                "total_cost": round(total_cost, 2),
                "average_duration_seconds": avg_duration,
                "sms_followup_sent": sms_followup_sent,
                "sms_followup_blocked": sms_followup_blocked,
                "period": {
                    "start": start_date,
                    "end": end_date
                }
            }
        }

    except Exception as e:
        logger.error(f"Error fetching analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Ringless Voicemail Delivery (Slybroadcast / Drop Cowboy)
# =============================================================================

async def send_voicemail_ringless(
    phone_number: str,
    message: str,
    audio_url: str = None,
    voicemail_drop_id: int = None,
    voice: str = "nova",
    voice_speed: float = 1.0,
) -> dict:
    """
    Send voicemail via ringless voicemail (RVM) provider.

    Supported providers:
      - slybroadcast: https://www.slybroadcast.com/gateway/vmb.json.php
        Auth: c_uid (email) + c_password
      - dropcowboy: https://api.dropcowboy.com/v1/rvm
        Auth: x-team-id + x-secret headers

    If no audio_url is provided, generates one from message text via OpenAI TTS.

    Env vars:
      RINGLESS_VM_PROVIDER   - "slybroadcast" or "dropcowboy"
      SLYBROADCAST_EMAIL     - Slybroadcast account email (c_uid)
      SLYBROADCAST_PASSWORD  - Slybroadcast password
      DROPCOWBOY_TEAM_ID     - Drop Cowboy team ID
      DROPCOWBOY_SECRET      - Drop Cowboy API secret
      RINGLESS_VM_CALLER_ID  - Caller ID for RVM (e.g., +18438838956)
      API_BASE_URL           - Public URL for audio file serving
    """
    import httpx

    provider = os.getenv("RINGLESS_VM_PROVIDER", "").lower().strip()
    caller_id = os.getenv("RINGLESS_VM_CALLER_ID", "") or os.getenv("SLYBROADCAST_CALLER_ID", "")

    if not provider:
        raise HTTPException(
            status_code=503,
            detail="Ringless voicemail provider not configured. Set RINGLESS_VM_PROVIDER env var."
        )

    # Auto-generate audio from text if no pre-recorded audio
    if not audio_url:
        if not message or not message.strip():
            raise HTTPException(
                status_code=400,
                detail="Either audio_url or message text is required for ringless voicemail."
            )
        filename = await _generate_audio_from_text(
            message=message,
            voice=voice,
            speed=voice_speed,
            voicemail_drop_id=voicemail_drop_id,
        )
        audio_url = _get_public_audio_url(filename)
        logger.info(f"Auto-generated TTS audio for RVM drop {voicemail_drop_id}: {audio_url}")
    else:
        # Validate pre-recorded audio duration if file is local
        # Slybroadcast API requires audio > 5 seconds
        _validate_audio_url_duration(audio_url)

    clean_number = ''.join(filter(str.isdigit, phone_number))
    if len(clean_number) == 10:
        clean_number = f"1{clean_number}"

    # ---- Slybroadcast ----
    # API docs: https://www.slybroadcast.com/docs/Slybroadcast_API.pdf
    # URL: https://www.mobile-sphere.com/gateway/vmb.php  (form POST)
    # Response: plain text — "OK\n<session_id>\nNumber of Phone #s = N"
    # Webhook: POST with $_POST['var'] = pipe-delimited with quotes
    if provider == "slybroadcast":
        sb_email = os.getenv("SLYBROADCAST_EMAIL", "")
        sb_password = os.getenv("SLYBROADCAST_PASSWORD", "")

        if not sb_email or not sb_password:
            raise HTTPException(
                status_code=503,
                detail="Slybroadcast credentials not configured. Set SLYBROADCAST_EMAIL and SLYBROADCAST_PASSWORD."
            )

        # Build webhook URL for delivery status callback
        base_url = os.getenv("API_BASE_URL", os.getenv("RAILWAY_PUBLIC_DOMAIN", ""))
        if base_url and not base_url.startswith("http"):
            base_url = f"https://{base_url}"
        dispo_url = f"{base_url}/api/v1/voicemail/webhook/rvm" if base_url else ""

        # NOTE: Do NOT pre-encode the audio_url — httpx form POST already
        # application/x-www-form-urlencoded-encodes all values.  Pre-encoding
        # causes double-encoding which makes the URL unreachable.

        clean_caller = caller_id.replace("+", "")
        # Slybroadcast expects 10-digit caller ID (no country code prefix)
        if len(clean_caller) == 11 and clean_caller.startswith("1"):
            clean_caller = clean_caller[1:]

        logger.info(
            f"Slybroadcast request: drop={voicemail_drop_id} phone={clean_number} "
            f"callerID={clean_caller} audio_url={audio_url[:120]}"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "c_uid": sb_email,
                "c_password": sb_password,
                "c_callerID": clean_caller,
                "c_phone": clean_number,
                "c_url": audio_url,
                "c_date": "now",
                "c_audio": "mp3",
                "mobile_only": "1",
            }
            if dispo_url:
                payload["c_dispo_url"] = dispo_url

            response = await client.post(
                "https://www.mobile-sphere.com/gateway/vmb.php",
                data=payload,
            )

            if response.status_code != 200:
                logger.error(f"Slybroadcast HTTP error {response.status_code}: {response.text[:500]}")
                raise HTTPException(status_code=502, detail="Slybroadcast API returned an error")

            # Response is plain text:
            #   Success: "OK\n912345678\nNumber of Phone #s = 1"
            #   Error:   any line not starting with "OK"
            body = response.text.strip()
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]

            logger.info(f"Slybroadcast response for drop {voicemail_drop_id}: {body[:300]}")

            if not lines or lines[0].upper() != "OK":
                error_msg = body[:300]
                logger.error(f"Slybroadcast error for drop {voicemail_drop_id}: {error_msg}")
                raise HTTPException(status_code=502, detail="Voicemail delivery service error")

            # Second line is session_id (may be "session_id=12345" or just "12345")
            raw_session = lines[1] if len(lines) > 1 else ""
            session_id = raw_session.split("=", 1)[-1].strip() if "=" in raw_session else raw_session

            logger.info(f"Slybroadcast RVM sent: session_id={session_id}, drop={voicemail_drop_id}")

            return {
                "success": True,
                "session_id": session_id,
                "provider": "slybroadcast",
            }

    # ---- Drop Cowboy ----
    elif provider == "dropcowboy":
        team_id = os.getenv("DROPCOWBOY_TEAM_ID", "")
        secret = os.getenv("DROPCOWBOY_SECRET", "")

        if not team_id or not secret:
            raise HTTPException(
                status_code=503,
                detail="Drop Cowboy credentials not configured. Set DROPCOWBOY_TEAM_ID and DROPCOWBOY_SECRET."
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "phone_number": clean_number,
                "caller_id": caller_id.replace("+", ""),
                "audio_url": audio_url,
                "brand_id": os.getenv("DROPCOWBOY_BRAND_ID", "default"),
                "forwarding_number": caller_id.replace("+", ""),
            }
            if voicemail_drop_id:
                payload["foreign_id"] = str(voicemail_drop_id)

            response = await client.post(
                "https://api.dropcowboy.com/v1/rvm",
                headers={
                    "x-team-id": team_id,
                    "x-secret": secret,
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if response.status_code not in (200, 201):
                logger.error(f"Drop Cowboy HTTP error {response.status_code}: {response.text[:500]}")
                raise HTTPException(status_code=502, detail="Drop Cowboy API returned an error")

            try:
                result = response.json()
            except Exception as e:
                logger.error(f"Drop Cowboy non-JSON response: {response.text[:500]}: {e}")
                raise HTTPException(status_code=502, detail="Drop Cowboy returned invalid response")

            msg_id = str(result.get("id", result.get("message_id", "")))
            logger.info(f"Drop Cowboy RVM sent: id={msg_id}, drop={voicemail_drop_id}")

            return {
                "success": True,
                "session_id": msg_id,
                "provider": "dropcowboy",
            }

    # Unsupported provider
    logger.warning(f"RVM provider '{provider}' not implemented")
    raise HTTPException(
        status_code=503,
        detail=f"RVM provider '{provider}' is not supported. Supported: slybroadcast, dropcowboy"
    )


# =============================================================================
# Audio Upload for Templates
# =============================================================================

ALLOWED_AUDIO_UPLOAD_TYPES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/wave", "audio/x-wav",
    "audio/ogg", "audio/m4a", "audio/x-m4a", "audio/mp4",
}
ALLOWED_AUDIO_UPLOAD_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".mp4"}
MAX_TEMPLATE_AUDIO_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/templates/{template_id}/upload-audio")
async def upload_template_audio(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Upload a pre-recorded audio file for a voicemail template.

    Accepts multipart/form-data with an 'audio_file' field.
    Max 10 MB, formats: mp3, wav, ogg, m4a.
    """
    VoicemailTemplate = get_voicemail_template_model()

    try:
        org_id = getattr(current_user, 'organization_id', None)
        template_query = db.query(VoicemailTemplate).filter(
            VoicemailTemplate.id == template_id,
            VoicemailTemplate.user_id == current_user.id,
        )
        if org_id is not None:
            template_query = template_query.filter(VoicemailTemplate.organization_id == org_id)
        template = template_query.first()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        form_data = await request.form()
        audio_file = form_data.get("audio_file")
        if not audio_file:
            raise HTTPException(status_code=400, detail="audio_file is required")

        filename = getattr(audio_file, 'filename', '') or 'audio.mp3'
        content_type = getattr(audio_file, 'content_type', '') or ''
        file_ext = os.path.splitext(filename)[1].lower()

        if file_ext not in ALLOWED_AUDIO_UPLOAD_EXTS:
            raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_AUDIO_UPLOAD_EXTS)}")

        # Stream to disk with size enforcement (prevents DOS from large uploads)
        # TENANT-007: Namespace file storage by organization to prevent cross-tenant access
        org_id = getattr(current_user, 'organization_id', None) or 'default'
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", f"org_{org_id}", "voicemail_audio")
        os.makedirs(upload_dir, exist_ok=True)

        safe_name = f"{template_id}_{uuid.uuid4().hex[:8]}{file_ext}"
        file_path = os.path.join(upload_dir, safe_name)

        total_size = 0
        _CHUNK_SIZE = 64 * 1024  # 64KB chunks
        try:
            with open(file_path, "wb") as f:
                while True:
                    chunk = await audio_file.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > MAX_TEMPLATE_AUDIO_SIZE:
                        break
                    f.write(chunk)
        except Exception as write_err:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=500, detail=f"Failed to save audio file: {write_err}")

        if total_size > MAX_TEMPLATE_AUDIO_SIZE:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=413, detail="File too large. Max: 10MB")
        if total_size == 0:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=400, detail="Audio file is empty")

        # Generate URL (relative — frontend/proxy will serve)
        audio_url = f"/api/v1/voicemail/audio/{safe_name}"

        template.audio_url = audio_url
        db.commit()

        logger.info(f"Uploaded audio for template {template_id}: {safe_name}")

        return {
            "success": True,
            "audio_url": audio_url,
            "file_size": total_size,
            "filename": safe_name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading template audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/audio/{filename}")
async def serve_voicemail_audio(
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Serve uploaded voicemail audio files (authenticated)."""
    # Sanitize filename to prevent directory traversal
    safe_name = os.path.basename(filename)
    # TENANT-007: Serve files from org-namespaced directory
    org_id = getattr(current_user, 'organization_id', None) or 'default'
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", f"org_{org_id}", "voicemail_audio")
    file_path = os.path.join(upload_dir, safe_name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    ext = os.path.splitext(safe_name)[1].lower()
    mime_types = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
    content_type = mime_types.get(ext, "audio/mpeg")

    with open(file_path, "rb") as f:
        data = f.read()

    return Response(content=data, media_type=content_type)


# =============================================================================
# Public Audio Serving (for RVM providers that fetch audio via URL)
# =============================================================================

def _get_public_audio_url(filename: str) -> str:
    """Generate a signed public URL for an audio file.

    RVM providers like Slybroadcast need to download the audio from a
    publicly-accessible URL (no Bearer auth).  We sign the filename with
    an HMAC so that only URLs we generate are valid.
    """
    import hashlib
    import hmac

    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        raise HTTPException(status_code=500, detail="Server configuration error")
    token = hmac.new(
        secret.encode(), filename.encode(), hashlib.sha256
    ).hexdigest()[:32]

    base_url = os.getenv(
        "API_BASE_URL",
        os.getenv("RAILWAY_PUBLIC_DOMAIN", ""),
    )
    # Normalise: ensure https:// prefix
    if base_url and not base_url.startswith("http"):
        base_url = f"https://{base_url}"

    if not base_url:
        base_url = "https://localhost:8000"

    return f"{base_url}/api/v1/voicemail/audio/public/{token}/{filename}"


@router.get("/audio/public/{token}/{filename}")
async def serve_public_voicemail_audio(
    token: str,
    filename: str,
):
    """Serve voicemail audio without auth, validated by HMAC token.

    Used by RVM providers (Slybroadcast, Drop Cowboy) to fetch audio files.
    """
    import hashlib
    import hmac

    # Validate HMAC token
    secret = os.getenv("SECRET_KEY", "")
    if not secret:
        raise HTTPException(status_code=500, detail="Server configuration error")
    expected = hmac.new(
        secret.encode(), filename.encode(), hashlib.sha256
    ).hexdigest()[:32]

    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Invalid token")

    safe_name = os.path.basename(filename)
    upload_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "uploads", "voicemail_audio"
    )
    file_path = os.path.join(upload_dir, safe_name)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    ext = os.path.splitext(safe_name)[1].lower()
    mime_types = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".ogg": "audio/ogg", ".m4a": "audio/mp4",
    }
    content_type = mime_types.get(ext, "audio/mpeg")

    with open(file_path, "rb") as f:
        data = f.read()

    return Response(content=data, media_type=content_type)


async def _generate_audio_from_text(
    message: str,
    voice: str = "nova",
    speed: float = 1.0,
    voicemail_drop_id: int = None,
) -> str:
    """Generate MP3 audio from text using OpenAI TTS.

    Saves to uploads/voicemail_audio/ and returns the filename.
    """
    import httpx

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured for TTS")

    speed = max(0.25, min(4.0, float(speed)))

    # OpenAI TTS only accepts these voices — map non-OpenAI voice names to a default
    OPENAI_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
    if voice not in OPENAI_VOICES:
        voice = "nova"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": message[:4096],  # OpenAI TTS limit
                "voice": voice,
                "speed": speed,
                "response_format": "mp3",
            },
        )

        if response.status_code != 200:
            logger.error(f"OpenAI TTS error {response.status_code}: {response.text[:500]}")
            raise HTTPException(status_code=500, detail="TTS audio generation failed")

        # Save to disk
        upload_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "uploads", "voicemail_audio"
        )
        os.makedirs(upload_dir, exist_ok=True)

        suffix = f"_drop{voicemail_drop_id}" if voicemail_drop_id else ""
        filename = f"rvm_tts_{uuid.uuid4().hex[:12]}{suffix}.mp3"
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as f:
            f.write(response.content)

        # Validate audio duration >= 5 seconds (Slybroadcast API requirement)
        audio_duration = _estimate_audio_duration_seconds(response.content)
        if audio_duration < 5.0:
            logger.warning(
                f"TTS audio too short ({audio_duration:.1f}s < 5s minimum): {filename}. "
                f"Slybroadcast requires audio > 5 seconds."
            )
            os.remove(file_path)
            raise HTTPException(
                status_code=422,
                detail=f"Generated audio is too short ({audio_duration:.1f}s). "
                       f"Slybroadcast requires audio > 5 seconds. Use a longer message."
            )

        logger.info(f"TTS audio generated: {filename} ({len(response.content)} bytes, ~{audio_duration:.1f}s)")
        return filename


def _estimate_audio_duration_seconds(mp3_data: bytes) -> float:
    """Estimate MP3 audio duration from file size.

    Uses average bitrate estimation for OpenAI TTS (tts-1 outputs ~48kbps MP3).
    For precise validation, use mutagen or ffprobe if available.
    """
    try:
        import mutagen.mp3
        import io
        audio = mutagen.mp3.MP3(io.BytesIO(mp3_data))
        return audio.info.length
    except (ImportError, Exception):
        # Fallback: estimate from file size assuming ~48kbps bitrate (OpenAI tts-1 default)
        bitrate_bytes_per_sec = 48000 / 8  # 6000 bytes/sec
        return len(mp3_data) / bitrate_bytes_per_sec


def _validate_audio_url_duration(audio_url: str) -> None:
    """Validate that a pre-recorded audio URL points to audio >= 5 seconds.

    Checks local files directly. For remote URLs, attempts a HEAD request
    to estimate duration from Content-Length. Logs a warning if unable to
    validate (does not block — TTS-generated audio is already validated).
    """
    MIN_DURATION = 5.0
    # Check if audio_url points to a local file served by the app
    upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads", "voicemail_audio")
    if not audio_url:
        return
    # Extract filename from URL path
    filename = audio_url.rstrip("/").split("/")[-1] if "/" in audio_url else audio_url
    local_path = os.path.join(upload_dir, filename)
    if os.path.isfile(local_path):
        with open(local_path, "rb") as f:
            data = f.read()
        duration = _estimate_audio_duration_seconds(data)
        if duration < MIN_DURATION:
            raise HTTPException(
                status_code=422,
                detail=f"Audio file too short ({duration:.1f}s). "
                       f"Slybroadcast requires audio > {MIN_DURATION} seconds."
            )
        logger.info(f"Pre-recorded audio validated: {filename} (~{duration:.1f}s)")
    else:
        # Remote URL — warn but don't block (can't easily download and check)
        logger.info(f"Audio URL is remote, skipping local duration check: {audio_url}")


@router.delete("/templates/{template_id}/audio")
async def delete_template_audio(
    template_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Remove audio file from a voicemail template."""
    VoicemailTemplate = get_voicemail_template_model()

    org_id = getattr(current_user, 'organization_id', None)
    template_query = db.query(VoicemailTemplate).filter(
        VoicemailTemplate.id == template_id,
        VoicemailTemplate.user_id == current_user.id,
    )
    if org_id is not None:
        template_query = template_query.filter(VoicemailTemplate.organization_id == org_id)
    template = template_query.first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if template.audio_url:
        # Delete physical file
        # TENANT-007: Use org-namespaced directory
        safe_name = os.path.basename(template.audio_url)
        org_id = getattr(current_user, 'organization_id', None) or 'default'
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", f"org_{org_id}", "voicemail_audio")
        file_path = os.path.join(upload_dir, safe_name)
        if os.path.exists(file_path):
            os.remove(file_path)

        template.audio_url = None
        db.commit()

    return {"success": True, "message": "Audio removed"}


# =============================================================================
# Voice Preview (TTS)
# =============================================================================

@router.post("/preview")
async def preview_voicemail_voice(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Generate a TTS audio preview of a voicemail message.

    Request body:
    {
        "message": "Hello, this is a test voicemail...",
        "voice": "alloy",          // OpenAI voice: alloy, echo, fable, onyx, nova, shimmer
        "speed": 1.0               // 0.25 - 4.0
    }

    Returns audio/mpeg binary.
    """
    import httpx

    try:
        data = await request.json()
        message = data.get("message", "").strip()
        voice = data.get("voice", "nova")
        speed = data.get("speed", 1.0)

        if not message:
            raise HTTPException(status_code=400, detail="Message text is required")

        # Limit preview length
        if len(message) > 1000:
            message = message[:1000]

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=503, detail="OpenAI API key not configured")

        # Clamp speed
        speed = max(0.25, min(4.0, float(speed)))

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1",
                    "input": message,
                    "voice": voice,
                    "speed": speed,
                    "response_format": "mp3",
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenAI TTS error: {response.text}")
                raise HTTPException(status_code=500, detail="Voice preview generation failed")

            return Response(
                content=response.content,
                media_type="audio/mpeg",
                headers={"Content-Disposition": "inline; filename=preview.mp3"},
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating voice preview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Template Updates (voice config, edit, delete)
# =============================================================================

@router.put("/templates/{template_id}")
async def update_voicemail_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a voicemail template (name, message, voice settings, delivery method)."""
    VoicemailTemplate = get_voicemail_template_model()

    try:
        org_id = getattr(current_user, 'organization_id', None)
        template_query = db.query(VoicemailTemplate).filter(
            VoicemailTemplate.id == template_id,
            VoicemailTemplate.user_id == current_user.id,
        )
        if org_id is not None:
            template_query = template_query.filter(VoicemailTemplate.organization_id == org_id)
        template = template_query.first()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        data = await request.json()

        if "name" in data:
            template.name = data["name"]
        if "category" in data:
            template.category = data["category"]
        if "message_text" in data:
            template.message_text = data["message_text"]
        if "variables" in data:
            template.variables = data["variables"]
        if "voice_provider" in data:
            template.voice_provider = data["voice_provider"]
        if "voice_id" in data:
            template.voice_id = data["voice_id"]
        if "voice_speed" in data:
            template.voice_speed = data["voice_speed"]
        if "delivery_method" in data:
            if data["delivery_method"] not in ALLOWED_DELIVERY_METHODS:
                raise HTTPException(status_code=400, detail=f"Invalid delivery method: {data['delivery_method']}")
            template.delivery_method = data["delivery_method"]

        db.commit()
        db.refresh(template)

        return {
            "success": True,
            "template": {
                "id": template.id,
                "name": template.name,
                "category": template.category,
                "message_text": template.message_text,
                "variables": template.variables,
                "audio_url": template.audio_url,
                "voice_provider": template.voice_provider,
                "voice_id": template.voice_id,
                "voice_speed": float(template.voice_speed) if template.voice_speed else 1.0,
                "delivery_method": template.delivery_method,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/templates/{template_id}")
async def delete_voicemail_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Soft-delete a voicemail template (sets is_active=False)."""
    VoicemailTemplate = get_voicemail_template_model()

    org_id = getattr(current_user, 'organization_id', None)
    template_query = db.query(VoicemailTemplate).filter(
        VoicemailTemplate.id == template_id,
        VoicemailTemplate.user_id == current_user.id,
    )
    if org_id is not None:
        template_query = template_query.filter(VoicemailTemplate.organization_id == org_id)
    template = template_query.first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.is_active = False
    db.commit()

    return {"success": True, "message": "Template deleted"}


# =============================================================================
# Campaign CRUD + Execution
# =============================================================================

@router.post("/campaigns")
async def create_campaign(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a voicemail campaign.

    Request body:
    {
        "name": "Rate Lock Reminder Blast",
        "description": "Remind all closing-stage leads about rate locks",
        "template_id": 5,
        "contact_filter": {"status": "closing", "tags": ["hot_lead"]},
        "throttle_rate": 50,
        "scheduled_at": "2026-02-10T14:00:00Z"  // optional — null = draft
    }
    """
    VoicemailCampaign = get_voicemail_campaign_model()
    VoicemailTemplate = get_voicemail_template_model()

    try:
        data = await request.json()
        org_id = getattr(current_user, 'organization_id', None)

        name = data.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Campaign name is required")

        template_id = data.get("template_id")
        if template_id:
            template_query = db.query(VoicemailTemplate).filter(
                VoicemailTemplate.id == template_id,
                VoicemailTemplate.is_active == True,
            )
            if org_id is not None:
                template_query = template_query.filter(
                    or_(
                        VoicemailTemplate.organization_id == None,
                        VoicemailTemplate.organization_id == org_id,
                    )
                )
            template = template_query.first()
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")

        scheduled_at = None
        if data.get("scheduled_at"):
            scheduled_at = datetime.fromisoformat(data["scheduled_at"].replace("Z", "+00:00"))

        campaign = VoicemailCampaign(
            user_id=current_user.id,
            organization_id=org_id,
            name=name,
            description=data.get("description", ""),
            template_id=template_id,
            contact_filter=data.get("contact_filter", {}),
            throttle_rate=data.get("throttle_rate", 100),
            scheduled_at=scheduled_at,
            status="scheduled" if scheduled_at else "draft",
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)

        logger.info(f"Created campaign {campaign.id}: {name}")

        return {
            "success": True,
            "campaign": _serialize_campaign(campaign),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating campaign: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/campaigns")
async def list_campaigns(
    status: str = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List voicemail campaigns for current user."""
    VoicemailCampaign = get_voicemail_campaign_model()

    try:
        org_id = getattr(current_user, 'organization_id', None)
        query = db.query(VoicemailCampaign).filter(
            VoicemailCampaign.user_id == current_user.id,
        )
        if org_id is not None:
            query = query.filter(VoicemailCampaign.organization_id == org_id)

        if status:
            query = query.filter(VoicemailCampaign.status == status)

        total = query.count()
        campaigns = query.order_by(VoicemailCampaign.created_at.desc()).offset(offset).limit(limit).all()

        return {
            "success": True,
            "total": total,
            "campaigns": [_serialize_campaign(c) for c in campaigns],
        }

    except Exception as e:
        logger.error(f"Error listing campaigns: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get campaign details."""
    VoicemailCampaign = get_voicemail_campaign_model()

    org_id = getattr(current_user, 'organization_id', None)
    campaign_query = db.query(VoicemailCampaign).filter(
        VoicemailCampaign.id == campaign_id,
        VoicemailCampaign.user_id == current_user.id,
    )
    if org_id is not None:
        campaign_query = campaign_query.filter(VoicemailCampaign.organization_id == org_id)
    campaign = campaign_query.first()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {"success": True, "campaign": _serialize_campaign(campaign)}


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update a draft/scheduled campaign."""
    VoicemailCampaign = get_voicemail_campaign_model()

    try:
        org_id = getattr(current_user, 'organization_id', None)
        campaign_query = db.query(VoicemailCampaign).filter(
            VoicemailCampaign.id == campaign_id,
            VoicemailCampaign.user_id == current_user.id,
        )
        if org_id is not None:
            campaign_query = campaign_query.filter(VoicemailCampaign.organization_id == org_id)
        campaign = campaign_query.first()

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if campaign.status not in ("draft", "scheduled"):
            raise HTTPException(status_code=400, detail="Can only edit draft or scheduled campaigns")

        data = await request.json()

        if "name" in data:
            campaign.name = data["name"]
        if "description" in data:
            campaign.description = data["description"]
        if "template_id" in data:
            campaign.template_id = data["template_id"]
        if "contact_filter" in data:
            campaign.contact_filter = data["contact_filter"]
        if "throttle_rate" in data:
            campaign.throttle_rate = data["throttle_rate"]
        if "scheduled_at" in data:
            if data["scheduled_at"]:
                campaign.scheduled_at = datetime.fromisoformat(data["scheduled_at"].replace("Z", "+00:00"))
                campaign.status = "scheduled"
            else:
                campaign.scheduled_at = None
                campaign.status = "draft"

        db.commit()
        db.refresh(campaign)

        return {"success": True, "campaign": _serialize_campaign(campaign)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating campaign: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


async def _resolve_and_dispatch_campaign(campaign_id: int, user_id: int, user_name: str):
    """
    Background task to resolve contacts, create VoicemailDrop records, run compliance
    checks, and dispatch drops via Vapi. Runs entirely in background to avoid
    Railway's 30s request timeout on large campaigns.
    """
    import asyncio
    from db import SessionLocal
    from database.tenant_mixin import set_tenant_context

    db = SessionLocal()
    # TENANT-017: Resolve org_id from user and set RLS context
    try:
        _org_row = db.execute(
            text("SELECT organization_id FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if _org_row and _org_row[0]:
            set_tenant_context(db, _org_row[0])
    except Exception as _exc:  # noqa: BLE001
        pass
    try:
        VoicemailCampaign = get_voicemail_campaign_model()
        VoicemailDrop = get_voicemail_drop_model()
        VoicemailTemplate = get_voicemail_template_model()
        from sqlalchemy import update as sa_update

        campaign = db.query(VoicemailCampaign).filter(
            VoicemailCampaign.id == campaign_id
        ).first()
        if not campaign:
            return

        # Verify campaign is still in "running" state (prevents double dispatch)
        if campaign.status != "running":
            logger.warning(f"Campaign {campaign_id} status is '{campaign.status}', not 'running' — aborting dispatch")
            return

        template = db.query(VoicemailTemplate).filter(
            VoicemailTemplate.id == campaign.template_id
        ).first()
        if not template:
            campaign.status = "failed"
            db.commit()
            return

        # --- Phase 1: Resolve contacts and create drop records ---
        import main
        Lead = main.Lead
        User = main.User
        contact_filter = campaign.contact_filter or {}
        # Whitelist allowed filter keys to prevent unexpected query behavior
        ALLOWED_FILTER_KEYS = {"status", "source", "stage", "assigned_to", "tag"}
        contact_filter = {k: v for k, v in contact_filter.items() if k in ALLOWED_FILTER_KEYS}

        # Get user's organization for multi-tenant isolation
        campaign_user = db.query(User).filter(User.id == user_id).first()
        campaign_org_id = campaign_user.organization_id if campaign_user else None

        query = db.query(Lead).filter(Lead.phone != None, Lead.phone != "")
        # Multi-tenant: only query leads belonging to user's organization
        if campaign_org_id:
            query = query.filter(Lead.organization_id == campaign_org_id)
        if contact_filter.get("status"):
            query = query.filter(Lead.status == contact_filter["status"])
        if contact_filter.get("source"):
            query = query.filter(Lead.source == contact_filter["source"])

        contacts = query.limit(1000).all()

        created_count = 0
        skipped_count = 0
        delivery_method = template.delivery_method or os.getenv("VOICEMAIL_DELIVERY_METHOD", "vapi_ai")

        for contact in contacts:
            # Check for pause/cancel every 100 contacts
            if (created_count + skipped_count) % 100 == 0 and (created_count + skipped_count) > 0:
                db.refresh(campaign)
                if campaign.status in ("paused", "cancelled"):
                    break

            is_allowed, reason = run_compliance_checks(contact.phone, contact.id, db, organization_id=campaign_org_id)
            if not is_allowed:
                skipped_count += 1
                continue

            # Dedup: skip if this phone already has a queued/sending drop from any campaign
            existing_pending = db.query(VoicemailDrop.id).filter(
                VoicemailDrop.phone_number == contact.phone,
                VoicemailDrop.status.in_(("queued", "sending")),
            ).first()
            if existing_pending:
                skipped_count += 1
                continue

            # Substitute variables in message
            msg = template.message_text
            first_name = getattr(contact, 'first_name', '') or ''
            last_name = getattr(contact, 'last_name', '') or ''
            full_name = " ".join(filter(None, [first_name, last_name]))
            msg = msg.replace("{{contact_name}}", full_name)
            msg = msg.replace("{{first_name}}", first_name)
            msg = msg.replace("{{last_name}}", last_name)
            msg = msg.replace("{{loan_officer}}", user_name)
            msg = msg.replace("{{company_name}}", os.getenv("COMPANY_NAME", "our office"))
            msg = msg.replace("{{phone}}", getattr(contact, 'phone', '') or '')
            msg = msg.replace("{{email}}", getattr(contact, 'email', '') or '')
            msg = re.sub(r'\{\{[^}]+\}\}', '', msg)
            # Normalize whitespace left by empty variable substitutions
            msg = re.sub(r'  +', ' ', msg).strip()

            drop = VoicemailDrop(
                user_id=user_id,
                organization_id=campaign_org_id,
                lead_id=contact.id,
                campaign_id=campaign.id,
                template_id=template.id,
                contact_name=f"{first_name} {last_name}".strip(),
                phone_number=contact.phone,
                message_text=msg,
                delivery_method=delivery_method,
                status='queued',
            )
            db.add(drop)
            created_count += 1

        campaign.total_contacts = created_count + skipped_count
        db.commit()

        logger.info(f"Campaign {campaign_id}: {created_count} drops created, {skipped_count} skipped")

        if created_count == 0:
            campaign.status = "completed"
            db.commit()
            return

        # --- Phase 2: Dispatch queued drops ---
        throttle_rate = campaign.throttle_rate or 10
        delay_between = 60.0 / max(throttle_rate, 1)

        queued_drops = db.query(VoicemailDrop).filter(
            VoicemailDrop.campaign_id == campaign_id,
            VoicemailDrop.status == "queued",
        ).all()

        sent = 0
        failed = 0
        DISPATCH_BATCH_SIZE = 5  # Concurrent Vapi calls per batch

        voice_provider = template.voice_provider if template else "deepgram"
        voice_id = template.voice_id if template else "asteria"
        voice_speed = template.voice_speed if template else 1.0
        audio_url = template.audio_url if template else None

        use_ringless = delivery_method == "ringless"

        async def _dispatch_one(drop_id, phone, msg_text, contact_name):
            """Send a single drop via the configured delivery method."""
            if use_ringless:
                return await send_voicemail_ringless(
                    phone_number=phone,
                    message=msg_text,
                    audio_url=audio_url,
                    voicemail_drop_id=drop_id,
                    voice=voice_id or "nova",
                    voice_speed=float(voice_speed or 1.0),
                )
            else:
                return await send_voicemail_via_vapi(
                    phone_number=phone,
                    message=msg_text,
                    recipient_name=contact_name or "",
                    user_name=user_name,
                    voicemail_drop_id=drop_id,
                    db=db,
                    voice_provider=voice_provider or "deepgram",
                    voice_id=voice_id or "asteria",
                    voice_speed=voice_speed or 1.0,
                    audio_url=audio_url,
                )

        # Process drops in batches for parallel calls
        for batch_start in range(0, len(queued_drops), DISPATCH_BATCH_SIZE):
            db.refresh(campaign)
            if campaign.status in ("paused", "cancelled"):
                logger.info(f"Campaign {campaign_id} {campaign.status} — stopping dispatch")
                break

            batch = queued_drops[batch_start:batch_start + DISPATCH_BATCH_SIZE]

            # Claim all drops in batch atomically
            claimed_drops = []
            for drop in batch:
                claimed = db.execute(
                    sa_update(VoicemailDrop)
                    .where(VoicemailDrop.id == drop.id)
                    .where(VoicemailDrop.status == "queued")
                    .values(status="sending")
                ).rowcount
                if claimed:
                    claimed_drops.append(drop)
            db.commit()

            if not claimed_drops:
                continue

            # Fire calls concurrently for the batch
            tasks = [
                _dispatch_one(d.id, d.phone_number, d.message_text, d.contact_name)
                for d in claimed_drops
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results (DB writes are serial)
            for drop, result in zip(claimed_drops, results):
                db.refresh(drop)
                if isinstance(result, Exception):
                    drop.status = "failed"
                    drop.error_message = str(result)[:500]
                    failed += 1
                    logger.error(f"Campaign {campaign_id} drop {drop.id} failed: {result}")
                else:
                    if use_ringless:
                        drop.rvm_session_id = result.get("session_id")
                        drop.rvm_provider = result.get("provider")
                    else:
                        drop.vapi_call_id = result.get("call_id")
                    sent += 1
            db.commit()

            # Throttle delay per batch (scaled to maintain overall rate)
            await asyncio.sleep(delay_between * len(claimed_drops))

        # Update campaign counts
        db.refresh(campaign)
        campaign.sent_count = sent
        campaign.failed_count = (campaign.failed_count or 0) + failed

        remaining = db.query(VoicemailDrop).filter(
            VoicemailDrop.campaign_id == campaign_id,
            VoicemailDrop.status == "queued",
        ).count()
        if remaining == 0 and campaign.status == "running":
            campaign.status = "completed"
            campaign.completed_at = datetime.now(timezone.utc)

        db.commit()
        logger.info(f"Campaign {campaign_id} dispatch done: {sent} sent, {failed} failed, {remaining} remaining")

    except Exception as e:
        logger.error(f"Campaign {campaign_id} dispatch error: {e}", exc_info=True)
        try:
            db.refresh(campaign)
            # Preserve partial progress counts before marking failed
            sent_so_far = db.query(VoicemailDrop).filter(
                VoicemailDrop.campaign_id == campaign_id,
                VoicemailDrop.status.in_(("delivered", "sent", "sending")),
            ).count()
            failed_so_far = db.query(VoicemailDrop).filter(
                VoicemailDrop.campaign_id == campaign_id,
                VoicemailDrop.status == "failed",
            ).count()
            campaign.sent_count = sent_so_far
            campaign.failed_count = failed_so_far
            campaign.status = "failed"
            db.commit()
            logger.info(f"Campaign {campaign_id} marked failed. Progress: {sent_so_far} sent, {failed_so_far} failed")
        except Exception as e:
            logger.error(f"Error marking campaign {campaign_id} as failed: {e}")
    finally:
        db.close()


@router.post("/campaigns/{campaign_id}/start")
async def start_campaign(
    campaign_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Start executing a campaign. Validates campaign, marks as running, then offloads
    contact resolution + compliance checks + dispatch to a background task
    to avoid Railway's 30s request timeout on large campaigns.
    """
    VoicemailCampaign = get_voicemail_campaign_model()
    VoicemailTemplate = get_voicemail_template_model()

    try:
        # Use SELECT FOR UPDATE NOWAIT to prevent two workers from starting the same campaign
        from sqlalchemy import text as sa_text
        org_id = getattr(current_user, 'organization_id', None)
        try:
            campaign_query = db.query(VoicemailCampaign).filter(
                VoicemailCampaign.id == campaign_id,
                VoicemailCampaign.user_id == current_user.id,
            )
            if org_id is not None:
                campaign_query = campaign_query.filter(VoicemailCampaign.organization_id == org_id)
            campaign = campaign_query.with_for_update(nowait=True).first()
        except Exception as lock_err:
            if "could not obtain lock" in str(lock_err).lower() or "lock" in str(lock_err).lower():
                raise HTTPException(status_code=409, detail="Campaign is already being started by another request")
            raise

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if campaign.status not in ("draft", "scheduled", "paused"):
            raise HTTPException(status_code=400, detail=f"Cannot start campaign in '{campaign.status}' status")

        if not campaign.template_id:
            raise HTTPException(status_code=400, detail="Campaign requires a template")

        template = db.query(VoicemailTemplate).filter(
            VoicemailTemplate.id == campaign.template_id
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Campaign template not found")

        # Atomic status transition: only update if still in a startable state
        from sqlalchemy import update
        rows_updated = db.execute(
            update(VoicemailCampaign)
            .where(VoicemailCampaign.id == campaign_id)
            .where(VoicemailCampaign.status.in_(("draft", "scheduled", "paused")))
            .values(status="running", started_at=datetime.now(timezone.utc))
        ).rowcount
        db.commit()

        if rows_updated == 0:
            raise HTTPException(status_code=409, detail="Campaign was already started by another request")

        # Offload all heavy work to background
        # OBS-002: Wrapped with _safe_background_task_vm for error surfacing
        user_name = current_user.full_name or "your loan officer"
        background_tasks.add_task(
            _safe_background_task_vm,
            _resolve_and_dispatch_campaign, campaign_id, current_user.id, user_name,
            task_name="resolve_and_dispatch_campaign",
        )

        logger.info(f"Campaign {campaign_id} started — contact resolution running in background")

        return {
            "success": True,
            "campaign_id": campaign_id,
            "status": "running",
            "message": "Campaign started. Contacts are being resolved and drops will be dispatched in the background.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting campaign: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Pause a running campaign."""
    VoicemailCampaign = get_voicemail_campaign_model()

    org_id = getattr(current_user, 'organization_id', None)
    campaign_query = db.query(VoicemailCampaign).filter(
        VoicemailCampaign.id == campaign_id,
        VoicemailCampaign.user_id == current_user.id,
    )
    if org_id is not None:
        campaign_query = campaign_query.filter(VoicemailCampaign.organization_id == org_id)
    campaign = campaign_query.first()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status != "running":
        raise HTTPException(status_code=400, detail="Can only pause running campaigns")

    campaign.status = "paused"
    campaign.paused_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "message": "Campaign paused"}


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Cancel a campaign and mark unsent drops as cancelled."""
    VoicemailCampaign = get_voicemail_campaign_model()
    VoicemailDrop = get_voicemail_drop_model()

    org_id = getattr(current_user, 'organization_id', None)
    campaign_query = db.query(VoicemailCampaign).filter(
        VoicemailCampaign.id == campaign_id,
        VoicemailCampaign.user_id == current_user.id,
    )
    if org_id is not None:
        campaign_query = campaign_query.filter(VoicemailCampaign.organization_id == org_id)
    campaign = campaign_query.first()

    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Campaign already {campaign.status}")

    # Cancel unsent drops
    cancelled_count = db.query(VoicemailDrop).filter(
        VoicemailDrop.campaign_id == campaign_id,
        VoicemailDrop.status.in_(["pending", "queued"]),
    ).update({"status": "failed", "error_message": "Campaign cancelled"}, synchronize_session=False)

    campaign.status = "cancelled"
    campaign.completed_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Campaign {campaign_id} cancelled, {cancelled_count} drops cancelled")

    return {"success": True, "message": f"Campaign cancelled, {cancelled_count} pending drops removed"}


def _serialize_campaign(campaign) -> dict:
    """Serialize a VoicemailCampaign to dict."""
    return {
        "id": campaign.id,
        "name": campaign.name,
        "description": campaign.description,
        "template_id": campaign.template_id,
        "contact_filter": campaign.contact_filter,
        "total_contacts": campaign.total_contacts,
        "status": campaign.status,
        "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        "started_at": campaign.started_at.isoformat() if campaign.started_at else None,
        "completed_at": campaign.completed_at.isoformat() if campaign.completed_at else None,
        "throttle_rate": campaign.throttle_rate,
        "sent_count": campaign.sent_count or 0,
        "delivered_count": campaign.delivered_count or 0,
        "failed_count": campaign.failed_count or 0,
        "callback_count": campaign.callback_count or 0,
        "total_cost": float(campaign.total_cost) if campaign.total_cost else 0,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
    }


# =============================================================================
# Consent Revocation
# =============================================================================

def _verify_revocation_token(token: str) -> Optional[dict]:
    """Verify a signed opt-out token (HMAC-SHA256). Returns payload or None."""
    import hmac as _hmac
    import hashlib
    import json
    import base64

    secret = os.getenv("CONSENT_REVOCATION_SECRET", os.getenv("SECRET_KEY", ""))
    if not secret:
        return None
    try:
        # Token format: base64(json_payload).base64(signature)
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        expected_sig = _hmac.new(
            secret.encode(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()
        if not _hmac.compare_digest(expected_sig, sig_b64):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        # Check expiration (tokens valid for 30 days)
        if payload.get("exp") and datetime.fromisoformat(payload["exp"]) < datetime.now(timezone.utc):
            return None
        return payload
    except Exception as e:
        logger.error(f"Error in _verify_revocation_token: {e}")
        return None


@router.post("/consent/revoke")
async def revoke_consent(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Revoke communication consent for a phone number or email.
    TCPA (effective April 2025) requires honoring revocation within 10 business days.

    Authentication: requires EITHER:
    - A valid auth token (staff processing a revocation request), OR
    - A signed revocation token in the body (public self-service opt-out link)

    Body: { "phone_number": str, "email": str (optional), "method": str, "token": str (optional) }
    """
    try:
        data = await request.json()
        phone_number = data.get("phone_number", "")
        email = data.get("email", "")
        method = data.get("method", "web_form")  # web_form, sms_stop, email, phone, verbal
        revocation_token = data.get("token", "")

        # --- Auth check: staff session OR signed revocation token ---
        is_authenticated = False

        # Try staff auth (bearer token)
        try:
            staff_user = await get_current_user(request, db)
            if staff_user:
                is_authenticated = True
                logger.info(f"Consent revocation by staff user {staff_user.id}")
        except Exception as e:
            logger.error(f"Error checking staff auth in revoke_consent: {e}")

        # Try signed revocation token (public opt-out link)
        if not is_authenticated and revocation_token:
            token_payload = _verify_revocation_token(revocation_token)
            if token_payload:
                # Token must match the phone/email being revoked
                token_phone = token_payload.get("phone", "")
                token_email = token_payload.get("email", "")
                if (token_phone and phone_number and _normalize_phone(token_phone) == _normalize_phone(phone_number)) or \
                   (token_email and email and token_email.lower() == email.lower()):
                    is_authenticated = True
                    logger.info(f"Consent revocation via signed token for phone={mask_phone(phone_number)}")
                else:
                    raise HTTPException(status_code=403, detail="Token does not match the contact being revoked")
            else:
                raise HTTPException(status_code=403, detail="Invalid or expired revocation token")

        if not is_authenticated:
            raise HTTPException(status_code=401, detail="Authentication required — provide a bearer token or signed revocation token")

        if not phone_number and not email:
            raise HTTPException(status_code=400, detail="phone_number or email is required")

        # Validate method
        valid_methods = {"web_form", "sms_stop", "email", "phone", "verbal"}
        if method not in valid_methods:
            method = "web_form"

        revoked_count = 0

        # 1. Add to internal DNC list
        if phone_number:
            from database.models.dialer import ContactDNCStatus
            digits = _normalize_phone(phone_number)

            existing = db.query(ContactDNCStatus).filter(
                or_(
                    ContactDNCStatus.phone_number == phone_number,
                    ContactDNCStatus.phone_number == digits,
                    ContactDNCStatus.phone_number == f"+1{digits}",
                )
            ).first()

            if not existing:
                dnc_entry = ContactDNCStatus(
                    phone_number=f"+1{digits}" if len(digits) == 10 else digits,
                    reason=f"Consent revoked via {method}",
                    source="consent_revocation",
                )
                db.add(dnc_entry)

        # 2. Update BorrowerProfile consent fields
        try:
            from database.models.borrower import BorrowerProfile
            filters = []
            # BorrowerProfile has no phone column — match on email only
            if email:
                filters.append(BorrowerProfile.email == email)

            if filters:
                borrowers = db.query(BorrowerProfile).filter(or_(*filters)).all()
                for borrower in borrowers:
                    borrower.communication_consent = False
                    borrower.marketing_consent = False
                    borrower.consent_revoked_at = datetime.now(timezone.utc)
                    borrower.consent_revocation_method = method
                    revoked_count += 1
        except ImportError:
            logger.debug("BorrowerProfile not available for consent revocation")

        # 3. Cancel any queued voicemail drops for this number
        if phone_number:
            VoicemailDrop = get_voicemail_drop_model()
            digits = _normalize_phone(phone_number)
            cancelled = db.query(VoicemailDrop).filter(
                VoicemailDrop.status.in_(["queued", "pending"]),
                or_(
                    VoicemailDrop.phone_number == phone_number,
                    VoicemailDrop.phone_number == digits,
                    VoicemailDrop.phone_number == f"+1{digits}",
                ),
            ).update(
                {"status": "cancelled", "error_message": f"Consent revoked via {method}"},
                synchronize_session=False,
            )
            logger.info(f"Cancelled {cancelled} queued drops for revoked number")

        db.commit()

        logger.info(
            f"Consent revocation processed: phone={phone_number}, email={email}, "
            f"method={method}, profiles_updated={revoked_count}"
        )

        return {
            "success": True,
            "message": "Consent revocation processed",
            "profiles_updated": revoked_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing consent revocation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# RVM Provider Webhooks (delivery status callbacks)
# =============================================================================

# Slybroadcast disposition codes → VoicemailDrop status
# Per API docs: Status field is "OK" (delivered) or "Failure" (failed)
_SLYBROADCAST_DISPO_MAP = {
    "OK": "delivered",
    "FAILURE": "failed",
}

# Drop Cowboy status → VoicemailDrop status
_DROPCOWBOY_STATUS_MAP = {
    "delivered": "delivered",
    "completed": "delivered",
    "failed": "failed",
    "rejected": "failed",
    "invalid": "failed",
}


@router.post("/webhook/rvm")
async def rvm_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive delivery status callbacks from RVM providers.

    Slybroadcast: form POST with $_POST['var'] containing 6 pipe-delimited
      quoted fields. Must respond with plain-text "OK".
      Format: "Session ID"|"Call To"|"Status"|"Reason for Failure"|"Delivery Time"|"Carrier"
      Status: "OK" (delivered) or "Failure" (failed)

    Drop Cowboy: sends JSON with foreign_id for correlation.
      Format: {"foreign_id": "123", "status": "delivered", ...}

    This endpoint requires no auth — providers can't send Bearer tokens.
    Validation is done via session_id / foreign_id matching existing records.
    """
    VoicemailDrop = get_voicemail_drop_model()
    VoicemailEvent = get_voicemail_event_model()

    try:
        content_type = request.headers.get("content-type", "")

        # --- Slybroadcast: form POST with 'var' field ---
        # Per API docs: disposition callback sends $_POST['var'] as
        # "Session ID"|"Call To"|"OK or Failure"|"Reason"|"Delivery Time"|"Carrier"
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            var_field = form.get("var", "")

            if not var_field:
                # Fallback: read raw body in case form parsing missed it
                body = await request.body()
                var_field = body.decode("utf-8", errors="replace").strip()

            if not var_field:
                logger.warning("Slybroadcast webhook: empty 'var' field")
                return Response(content="OK", media_type="text/plain")

            # Strip quotes from each field and split on |
            # Format: "session_id"|"phone"|"OK"|""|"2026-02-11 10:30:00"|"T-Mobile"
            parts = [p.strip().strip('"') for p in var_field.split("|")]

            session_id = parts[0] if len(parts) > 0 else ""
            phone = parts[1] if len(parts) > 1 else ""
            status_str = parts[2].upper() if len(parts) > 2 else ""
            failure_reason = parts[3] if len(parts) > 3 else ""
            delivery_time = parts[4] if len(parts) > 4 else ""
            carrier = parts[5] if len(parts) > 5 else ""

            new_status = _SLYBROADCAST_DISPO_MAP.get(status_str, "failed")

            # Find the drop by session_id
            drop = None
            if session_id:
                drop = db.query(VoicemailDrop).filter(
                    VoicemailDrop.rvm_session_id == session_id
                ).first()

            if drop:
                drop.status = new_status
                drop.rvm_dispo_code = status_str
                if new_status == "delivered":
                    drop.delivered_at = datetime.now(timezone.utc)

                event = VoicemailEvent(
                    voicemail_drop_id=drop.id,
                    event_type=new_status,
                    event_data={
                        "provider": "slybroadcast",
                        "session_id": session_id,
                        "phone": phone,
                        "dispo_code": status_str,
                        "failure_reason": failure_reason,
                        "delivery_time": delivery_time,
                        "carrier": carrier,
                    }
                )
                db.add(event)
                db.commit()
                logger.info(
                    f"Slybroadcast webhook: drop {drop.id} → {new_status} "
                    f"(status={status_str}, carrier={carrier})"
                )
            else:
                logger.warning(
                    f"Slybroadcast webhook: no matching drop for session={session_id}"
                )

            # Slybroadcast requires plain "OK" response
            return Response(content="OK", media_type="text/plain")

        # --- Drop Cowboy / JSON format ---
        body = await request.body()
        body_text = body.decode("utf-8", errors="replace").strip()

        # Check if this is actually a Slybroadcast callback sent without
        # proper content-type (pipe-delimited with quotes)
        if "|" in body_text and "application/json" not in content_type:
            # Same parsing as above, treat as Slybroadcast
            parts = [p.strip().strip('"') for p in body_text.split("|")]
            session_id = parts[0] if len(parts) > 0 else ""
            status_str = parts[2].upper() if len(parts) > 2 else ""
            new_status = _SLYBROADCAST_DISPO_MAP.get(status_str, "failed")
            if session_id:
                drop = db.query(VoicemailDrop).filter(
                    VoicemailDrop.rvm_session_id == session_id
                ).first()
                if drop:
                    drop.status = new_status
                    drop.rvm_dispo_code = status_str
                    if new_status == "delivered":
                        drop.delivered_at = datetime.now(timezone.utc)
                    db.commit()
                    logger.info(f"Slybroadcast webhook (raw): drop {drop.id} → {new_status}")
            return Response(content="OK", media_type="text/plain")

        try:
            data = await request.json()
        except Exception as e:
            logger.warning(f"RVM webhook: unrecognized body format: {body_text[:200]}: {e}")
            return Response(content="OK", media_type="text/plain")

        foreign_id = str(data.get("foreign_id", ""))
        dc_status = str(data.get("status", "")).lower()
        new_status = _DROPCOWBOY_STATUS_MAP.get(dc_status, "failed")

        drop = None
        if foreign_id:
            try:
                drop = db.query(VoicemailDrop).filter(
                    VoicemailDrop.id == int(foreign_id)
                ).first()
            except (ValueError, TypeError):
                # Try matching by rvm_session_id
                drop = db.query(VoicemailDrop).filter(
                    VoicemailDrop.rvm_session_id == foreign_id
                ).first()

        if drop:
            drop.status = new_status
            drop.rvm_dispo_code = dc_status
            if new_status == "delivered":
                drop.delivered_at = datetime.now(timezone.utc)

            event = VoicemailEvent(
                voicemail_drop_id=drop.id,
                event_type=new_status,
                event_data={
                    "provider": "dropcowboy",
                    "foreign_id": foreign_id,
                    "raw_status": dc_status,
                    "raw_data": {k: v for k, v in data.items() if k != "foreign_id"},
                }
            )
            db.add(event)
            db.commit()
            logger.info(
                f"Drop Cowboy webhook: drop {drop.id} → {new_status} (status={dc_status})"
            )
        else:
            logger.warning(
                f"Drop Cowboy webhook: no matching drop for foreign_id={foreign_id}"
            )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"RVM webhook error: {e}", exc_info=True)
        # Always return 200 to prevent provider retries flooding logs
        return Response(content="OK", media_type="text/plain")
