"""
Speed-to-Lead Auto-Call Trigger Routes

Provides AI-powered outbound call initiation for new leads within 60 seconds.
Integrates with Vapi for AI calls, Telnyx for SMS fallback, and the telephony
compliance layer for TCPA/DNC enforcement.

Endpoints:
  POST /api/v1/speed-to-lead/trigger-call   — Initiate AI call for a lead
  POST /api/v1/speed-to-lead/new-lead-webhook — External webhook, async trigger
  GET  /api/v1/speed-to-lead/config          — Get per-org STL config
  PUT  /api/v1/speed-to-lead/config          — Update per-org STL config
"""

import hmac
import os
import logging
import re
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db
from services.voice_context_builder import build_outbound_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/speed-to-lead", tags=["Speed to Lead"])


# =============================================================================
# Auth dependency (lazy import to avoid circular imports)
# =============================================================================

def _get_auth_flexible():
    from routes.auth_deps import current_user_flexible_dep
    return current_user_flexible_dep


# =============================================================================
# Constants
# =============================================================================

# TCPA safe-harbor window: 8 AM - 9 PM borrower local time
TCPA_START = dt_time(8, 0)
TCPA_END = dt_time(21, 0)

# US area code -> IANA timezone (comprehensive; falls back to America/New_York)
AREA_CODE_TIMEZONE: Dict[str, str] = {
    # Eastern Time
    "201": "America/New_York", "202": "America/New_York", "203": "America/New_York",
    "207": "America/New_York", "212": "America/New_York", "215": "America/New_York",
    "216": "America/New_York", "229": "America/New_York", "231": "America/New_York",
    "234": "America/New_York", "239": "America/New_York", "240": "America/New_York",
    "248": "America/New_York", "252": "America/New_York", "267": "America/New_York",
    "269": "America/New_York", "272": "America/New_York", "276": "America/New_York",
    "301": "America/New_York", "302": "America/New_York", "304": "America/New_York",
    "305": "America/New_York", "313": "America/New_York", "315": "America/New_York",
    "321": "America/New_York", "330": "America/New_York", "336": "America/New_York",
    "339": "America/New_York", "347": "America/New_York", "351": "America/New_York",
    "352": "America/New_York", "386": "America/New_York", "401": "America/New_York",
    "404": "America/New_York", "407": "America/New_York", "410": "America/New_York",
    "412": "America/New_York", "413": "America/New_York", "419": "America/New_York",
    "440": "America/New_York", "443": "America/New_York", "470": "America/New_York",
    "475": "America/New_York", "478": "America/New_York", "484": "America/New_York",
    "502": "America/New_York", "508": "America/New_York", "513": "America/New_York",
    "516": "America/New_York", "517": "America/New_York", "518": "America/New_York",
    "540": "America/New_York", "551": "America/New_York", "561": "America/New_York",
    "567": "America/New_York", "570": "America/New_York", "571": "America/New_York",
    "585": "America/New_York", "586": "America/New_York", "603": "America/New_York",
    "607": "America/New_York", "609": "America/New_York", "610": "America/New_York",
    "614": "America/New_York", "616": "America/New_York", "617": "America/New_York",
    "631": "America/New_York", "646": "America/New_York", "678": "America/New_York",
    "681": "America/New_York", "689": "America/New_York", "704": "America/New_York",
    "706": "America/New_York", "716": "America/New_York", "717": "America/New_York",
    "718": "America/New_York", "724": "America/New_York", "727": "America/New_York",
    "732": "America/New_York", "740": "America/New_York", "754": "America/New_York",
    "757": "America/New_York", "762": "America/New_York", "770": "America/New_York",
    "772": "America/New_York", "774": "America/New_York", "781": "America/New_York",
    "786": "America/New_York", "803": "America/New_York", "804": "America/New_York",
    "810": "America/New_York", "813": "America/New_York", "828": "America/New_York",
    "843": "America/New_York", "845": "America/New_York", "848": "America/New_York",
    "856": "America/New_York", "857": "America/New_York", "860": "America/New_York",
    "862": "America/New_York", "863": "America/New_York", "864": "America/New_York",
    "878": "America/New_York", "904": "America/New_York", "908": "America/New_York",
    "910": "America/New_York", "912": "America/New_York", "914": "America/New_York",
    "917": "America/New_York", "919": "America/New_York", "929": "America/New_York",
    "937": "America/New_York", "941": "America/New_York", "954": "America/New_York",
    "973": "America/New_York", "978": "America/New_York", "980": "America/New_York",
    # Central Time
    "205": "America/Chicago", "210": "America/Chicago", "214": "America/Chicago",
    "217": "America/Chicago", "218": "America/Chicago", "219": "America/Chicago",
    "224": "America/Chicago", "225": "America/Chicago", "228": "America/Chicago",
    "251": "America/Chicago", "254": "America/Chicago", "256": "America/Chicago",
    "260": "America/Chicago", "262": "America/Chicago", "281": "America/Chicago",
    "309": "America/Chicago", "312": "America/Chicago", "314": "America/Chicago",
    "316": "America/Chicago", "317": "America/Chicago", "318": "America/Chicago",
    "319": "America/Chicago", "320": "America/Chicago", "325": "America/Chicago",
    "331": "America/Chicago", "334": "America/Chicago", "337": "America/Chicago",
    "346": "America/Chicago", "361": "America/Chicago", "380": "America/Chicago",
    "402": "America/Chicago", "405": "America/Chicago", "409": "America/Chicago",
    "414": "America/Chicago", "417": "America/Chicago", "430": "America/Chicago",
    "432": "America/Chicago", "469": "America/Chicago", "479": "America/Chicago",
    "501": "America/Chicago", "504": "America/Chicago", "507": "America/Chicago",
    "512": "America/Chicago", "515": "America/Chicago", "531": "America/Chicago",
    "534": "America/Chicago", "539": "America/Chicago", "563": "America/Chicago",
    "573": "America/Chicago", "580": "America/Chicago", "601": "America/Chicago",
    "608": "America/Chicago", "612": "America/Chicago", "615": "America/Chicago",
    "618": "America/Chicago", "620": "America/Chicago", "630": "America/Chicago",
    "636": "America/Chicago", "641": "America/Chicago", "651": "America/Chicago",
    "660": "America/Chicago", "662": "America/Chicago", "682": "America/Chicago",
    "701": "America/Chicago", "708": "America/Chicago", "712": "America/Chicago",
    "713": "America/Chicago", "715": "America/Chicago", "726": "America/Chicago",
    "731": "America/Chicago", "737": "America/Chicago", "763": "America/Chicago",
    "769": "America/Chicago", "773": "America/Chicago", "779": "America/Chicago",
    "785": "America/Chicago", "806": "America/Chicago", "812": "America/Chicago",
    "815": "America/Chicago", "816": "America/Chicago", "817": "America/Chicago",
    "830": "America/Chicago", "832": "America/Chicago", "847": "America/Chicago",
    "850": "America/Chicago", "870": "America/Chicago", "872": "America/Chicago",
    "901": "America/Chicago", "903": "America/Chicago", "913": "America/Chicago",
    "918": "America/Chicago", "920": "America/Chicago", "931": "America/Chicago",
    "936": "America/Chicago", "938": "America/Chicago", "940": "America/Chicago",
    "945": "America/Chicago", "947": "America/Chicago", "956": "America/Chicago",
    "972": "America/Chicago", "979": "America/Chicago",
    # Mountain Time
    "303": "America/Denver", "307": "America/Denver", "385": "America/Denver",
    "406": "America/Denver", "435": "America/Denver", "505": "America/Denver",
    "520": "America/Phoenix", "575": "America/Denver", "602": "America/Phoenix",
    "623": "America/Phoenix", "719": "America/Denver", "720": "America/Denver",
    "801": "America/Denver", "928": "America/Phoenix", "970": "America/Denver",
    "480": "America/Phoenix",
    # Pacific Time
    "206": "America/Los_Angeles", "208": "America/Los_Angeles",
    "209": "America/Los_Angeles", "213": "America/Los_Angeles",
    "253": "America/Los_Angeles", "310": "America/Los_Angeles",
    "323": "America/Los_Angeles", "341": "America/Los_Angeles",
    "360": "America/Los_Angeles", "408": "America/Los_Angeles",
    "415": "America/Los_Angeles", "424": "America/Los_Angeles",
    "425": "America/Los_Angeles", "442": "America/Los_Angeles",
    "458": "America/Los_Angeles", "503": "America/Los_Angeles",
    "509": "America/Los_Angeles", "510": "America/Los_Angeles",
    "530": "America/Los_Angeles", "541": "America/Los_Angeles",
    "559": "America/Los_Angeles", "562": "America/Los_Angeles",
    "564": "America/Los_Angeles", "619": "America/Los_Angeles",
    "626": "America/Los_Angeles", "628": "America/Los_Angeles",
    "650": "America/Los_Angeles", "657": "America/Los_Angeles",
    "661": "America/Los_Angeles", "669": "America/Los_Angeles",
    "702": "America/Los_Angeles", "707": "America/Los_Angeles",
    "714": "America/Los_Angeles", "725": "America/Los_Angeles",
    "747": "America/Los_Angeles", "760": "America/Los_Angeles",
    "775": "America/Los_Angeles", "805": "America/Los_Angeles",
    "818": "America/Los_Angeles", "831": "America/Los_Angeles",
    "858": "America/Los_Angeles", "909": "America/Los_Angeles",
    "916": "America/Los_Angeles", "925": "America/Los_Angeles",
    "935": "America/Los_Angeles", "949": "America/Los_Angeles",
    "951": "America/Los_Angeles", "971": "America/Los_Angeles",
    # Alaska / Hawaii
    "907": "America/Anchorage",
    "808": "Pacific/Honolulu",
}


# =============================================================================
# Pydantic Schemas
# =============================================================================

class TriggerCallRequest(BaseModel):
    """Request to trigger an AI outbound call for a lead."""
    lead_id: int = Field(..., description="ID of the lead to call")
    force: bool = Field(False, description="Bypass quiet-hours check (for testing only)")


class NewLeadWebhookPayload(BaseModel):
    """Payload from any lead source (web form, API, LOS sync)."""
    lead_id: int = Field(..., description="ID of the lead that was just created")
    source: Optional[str] = Field(None, description="Lead source identifier")
    api_key: Optional[str] = Field(None, description="Webhook authentication key")


class SpeedToLeadConfigUpdate(BaseModel):
    """Per-org speed-to-lead configuration."""
    sla_seconds: Optional[int] = Field(None, ge=10, le=600, description="SLA target in seconds (default 60)")
    channels_enabled: Optional[List[str]] = Field(None, description="Enabled channels: call, sms, email")
    quiet_hours_start: Optional[str] = Field(None, description="Quiet hours start HH:MM (default 21:00)")
    quiet_hours_end: Optional[str] = Field(None, description="Quiet hours end HH:MM (default 08:00)")
    weekend_calls_enabled: Optional[bool] = Field(None, description="Allow calls on weekends")
    fallback_to_sms: Optional[bool] = Field(None, description="Send SMS if call cannot be placed")
    ai_greeting_override: Optional[str] = Field(None, description="Custom first message for AI calls")


# =============================================================================
# Table Initialization
# =============================================================================

_tables_initialized = False


def _ensure_tables(db: Session):
    """Create speed_to_lead_config and speed_to_lead_events tables if missing."""
    global _tables_initialized
    if _tables_initialized:
        return

    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS speed_to_lead_config (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL UNIQUE REFERENCES organizations(id),
                sla_seconds INTEGER NOT NULL DEFAULT 60,
                channels_enabled JSONB NOT NULL DEFAULT '["call", "sms"]'::jsonb,
                quiet_hours_start VARCHAR(5) NOT NULL DEFAULT '21:00',
                quiet_hours_end VARCHAR(5) NOT NULL DEFAULT '08:00',
                weekend_calls_enabled BOOLEAN NOT NULL DEFAULT false,
                fallback_to_sms BOOLEAN NOT NULL DEFAULT true,
                ai_greeting_override TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS speed_to_lead_events (
                id SERIAL PRIMARY KEY,
                lead_id INTEGER NOT NULL,
                organization_id INTEGER,
                event VARCHAR(50) NOT NULL,
                channel VARCHAR(20),
                meta TEXT,
                vapi_call_id VARCHAR(100),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_stl_events_lead ON speed_to_lead_events (lead_id)
        """))
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_stl_events_org_created ON speed_to_lead_events (organization_id, created_at)
        """))
        db.commit()
        _tables_initialized = True
    except Exception as e:
        db.rollback()
        logger.warning(f"STL table init note: {e}")
        _tables_initialized = True  # Don't retry on every request


# =============================================================================
# Helpers
# =============================================================================

def _format_e164(phone: str) -> Optional[str]:
    """Normalize a US phone number to E.164 format."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if len(digits) > 10 and phone.startswith("+"):
        return f"+{digits}"
    return None


def _extract_area_code(phone: str) -> Optional[str]:
    """Extract 3-digit US area code from a phone number."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return digits[:3]
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:4]
    return None


def _get_borrower_timezone(phone: Optional[str]) -> str:
    """Resolve borrower timezone from phone area code. Default: Eastern."""
    area = _extract_area_code(phone or "")
    if area:
        return AREA_CODE_TIMEZONE.get(area, "America/New_York")
    return "America/New_York"


def _is_tcpa_quiet_hours(
    phone: Optional[str] = None,
    quiet_start: str = "21:00",
    quiet_end: str = "08:00",
) -> bool:
    """
    Check if it's currently in TCPA quiet hours for the borrower's timezone.
    Default quiet window: 9 PM - 8 AM.

    Returns True if calls are NOT allowed right now.
    """
    try:
        import pytz
    except ImportError:
        from zoneinfo import ZoneInfo
        pytz = None

    tz_name = _get_borrower_timezone(phone)

    try:
        if pytz:
            tz = pytz.timezone(tz_name)
            local_now = datetime.now(tz).time()
        else:
            tz = ZoneInfo(tz_name)
            local_now = datetime.now(tz).time()
    except Exception:
        # If timezone resolution fails, be conservative: assume quiet hours
        return True

    # Parse quiet hours
    try:
        start_h, start_m = (int(x) for x in quiet_start.split(":"))
        end_h, end_m = (int(x) for x in quiet_end.split(":"))
        start = dt_time(start_h, start_m)
        end = dt_time(end_h, end_m)
    except (ValueError, IndexError):
        start = TCPA_END   # 9 PM
        end = TCPA_START   # 8 AM

    # Quiet window wraps midnight (e.g. 21:00 -> 08:00)
    if start > end:
        return local_now >= start or local_now < end
    else:
        return start <= local_now < end


def _is_weekend(phone: Optional[str] = None) -> bool:
    """Check if today is Saturday (5) or Sunday (6) in the borrower's local timezone."""
    tz_name = _get_borrower_timezone(phone)
    try:
        import pytz
        tz = pytz.timezone(tz_name)
        local_now = datetime.now(tz)
    except Exception:
        local_now = datetime.now(timezone.utc)
    return local_now.weekday() in (5, 6)


def _check_dnc_opt_out(db: Session, phone: str, organization_id: Optional[int]) -> Optional[str]:
    """
    Check DNC list and SMS/call opt-out status.

    Returns a reason string if blocked, or None if clear.
    """
    if not phone:
        return "no_phone_number"

    # Check telephony compliance layer (DNC list)
    try:
        from telephony.compliance import ComplianceChecker
        checker = ComplianceChecker(db, organization_id=organization_id)
        is_dnc, dnc_reason = checker.check_dnc(phone)
        if is_dnc:
            return f"dnc:{dnc_reason or 'on_dnc_list'}"
    except Exception as e:
        logger.warning(f"DNC check unavailable: {e}")

    # Check SMS opt-out (reuse sms_compliance for call consent too)
    try:
        from routes.sms_compliance_routes import is_opted_out
        if is_opted_out(db, phone, organization_id):
            return "opted_out"
    except Exception as e:
        logger.warning(f"Opt-out check unavailable: {e}")

    # Check lead-level Do Not Call stage
    try:
        row = db.execute(text("""
            SELECT stage FROM leads
            WHERE phone = :phone AND organization_id = :org_id
            AND UPPER(stage) = 'DO NOT CALL'
            LIMIT 1
        """), {"phone": phone, "org_id": organization_id}).fetchone()
        if row:
            return "lead_stage_do_not_call"
    except Exception as e:
        logger.warning(f"Lead DNC stage check failed: {e}")

    # Check call_consent from channel_preferences if available
    try:
        row = db.execute(text("""
            SELECT call_consent FROM channel_preferences
            WHERE phone = :phone AND organization_id = :org_id
            LIMIT 1
        """), {"phone": phone, "org_id": organization_id}).fetchone()
        if row and row.call_consent is False:
            return "no_call_consent"
    except Exception as e:
        logger.warning("Call consent check unavailable (table may not exist): %s", e)

    return None


def _get_org_config(db: Session, organization_id: int) -> Dict[str, Any]:
    """Load per-org speed-to-lead config, with defaults."""
    defaults = {
        "sla_seconds": 60,
        "channels_enabled": ["call", "sms"],
        "quiet_hours_start": "21:00",
        "quiet_hours_end": "08:00",
        "weekend_calls_enabled": False,
        "fallback_to_sms": True,
        "ai_greeting_override": None,
    }
    try:
        row = db.execute(text("""
            SELECT sla_seconds, channels_enabled, quiet_hours_start, quiet_hours_end,
                   weekend_calls_enabled, fallback_to_sms, ai_greeting_override
            FROM speed_to_lead_config
            WHERE organization_id = :org_id
        """), {"org_id": organization_id}).fetchone()
        if row:
            return {
                "sla_seconds": row.sla_seconds,
                "channels_enabled": row.channels_enabled or defaults["channels_enabled"],
                "quiet_hours_start": row.quiet_hours_start or defaults["quiet_hours_start"],
                "quiet_hours_end": row.quiet_hours_end or defaults["quiet_hours_end"],
                "weekend_calls_enabled": row.weekend_calls_enabled,
                "fallback_to_sms": row.fallback_to_sms,
                "ai_greeting_override": row.ai_greeting_override,
            }
    except Exception as e:
        logger.debug(f"Config lookup fallback to defaults: {e}")

    return defaults


def _log_stl_event(
    db: Session,
    lead_id: int,
    organization_id: Optional[int],
    event: str,
    channel: Optional[str] = None,
    meta: Optional[dict] = None,
    vapi_call_id: Optional[str] = None,
):
    """Best-effort logging to speed_to_lead_events."""
    try:
        db.execute(text("""
            INSERT INTO speed_to_lead_events (lead_id, organization_id, event, channel, meta, vapi_call_id, created_at)
            VALUES (:lid, :org_id, :event, :channel, :meta, :vapi_call_id, :now)
        """), {
            "lid": lead_id,
            "org_id": organization_id,
            "event": event,
            "channel": channel,
            "meta": str(meta)[:2000] if meta else None,
            "vapi_call_id": vapi_call_id,
            "now": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log STL event: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def _log_activity(
    db: Session,
    lead_id: int,
    organization_id: Optional[int],
    user_id: Optional[int],
    activity_type: str,
    content: str,
    metadata: Optional[dict] = None,
):
    """Log to the activities table for CRM visibility."""
    try:
        db.execute(text("""
            INSERT INTO activities (lead_id, organization_id, user_id, type, content, user_metadata, created_at)
            VALUES (:lid, :org_id, :uid, :atype, :content, :meta, :now)
        """), {
            "lid": lead_id,
            "org_id": organization_id,
            "uid": user_id,
            "atype": activity_type,
            "content": content,
            "meta": str(metadata) if metadata else None,
            "now": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log activity: {e}")
        try:
            db.rollback()
        except Exception:
            pass


# =============================================================================
# Vapi AI Call Initiation
# =============================================================================

async def _initiate_vapi_call(
    phone_e164: str,
    lead_name: str,
    lead_id: int,
    organization_id: Optional[int],
    owner_id: Optional[int],
    greeting_override: Optional[str] = None,
    outbound_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Initiate an AI outbound call via Vapi.

    If outbound_context is provided (from build_outbound_context), uses
    personalized system prompt, greeting, and voicemail message with
    cross-channel engagement data. Otherwise falls back to generic prompts.

    Returns dict with:
      - success: bool
      - vapi_call_id: str (if success)
      - error: str (if failure)
    """
    import httpx

    vapi_api_key = os.getenv("VAPI_API_KEY")
    if not vapi_api_key:
        return {"success": False, "error": "VAPI_API_KEY not configured"}

    vapi_phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")
    if not vapi_phone_number_id:
        return {"success": False, "error": "VAPI_PHONE_NUMBER_ID not configured"}

    # Use enriched context if available, otherwise fall back to generic prompts
    ctx = outbound_context or {}

    first_message = greeting_override or ctx.get("first_message") or (
        f"Hi {lead_name}! This is Aria from Perennia AI calling on behalf of your "
        f"loan officer. Thank you for your interest in mortgage options. "
        f"I'd love to help you get started. Do you have a moment to chat?"
    )

    system_prompt = ctx.get("system_prompt") or (
        f"You are Aria, an AI assistant for a mortgage loan officer at Perennia AI. "
        f"You are making a speed-to-lead callback to {lead_name} who just expressed "
        f"interest in mortgage services. Your goals: "
        f"1) Confirm the lead's interest and introduce yourself warmly. "
        f"2) Ask about their timeline, loan type, and property location. "
        f"3) Qualify the lead (credit score range, employment, down payment). "
        f"4) Offer to schedule a consultation with their loan officer. "
        f"5) If they want to schedule, confirm a time that works. "
        f"Be professional, warm, and concise. Do not pressure or rush them. "
        f"If they ask to be called back later, note the preferred time. "
        f"If they are not interested, thank them and end the call gracefully. "
        f"COMPLIANCE (ECOA): NEVER ask about or discuss race, color, religion, national origin, "
        f"sex, marital status, age, familial status, disability, or receipt of public assistance. "
        f"If the borrower volunteers such information, do NOT record it or ask follow-up questions about it. "
        f"COMPLIANCE (RATES): NEVER quote specific interest rates, APRs, or monthly payment amounts."
    )

    voicemail_message = ctx.get("voicemail_message") or (
        f"Hi {lead_name}, this is a message from your loan officer's team at Perennia AI. "
        f"We received your mortgage inquiry and wanted to connect. "
        f"Your loan officer will be reaching out shortly. Thank you!"
    )

    payload = {
        "phoneNumberId": vapi_phone_number_id,
        "customer": {
            "number": phone_e164,
            "name": lead_name,
        },
        "assistant": {
            "firstMessage": first_message,
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "messages": [
                    {"role": "system", "content": system_prompt},
                ],
            },
            "voice": {
                "provider": "deepgram",
                "voiceId": "asteria",
            },
            "endCallMessage": "Thank you for your time! Your loan officer will follow up shortly. Have a great day!",
            "endCallPhrases": ["goodbye", "have a great day", "talk to you later", "not interested"],
            "voicemailDetection": {
                "provider": "vapi",
                "beepMaxAwaitSeconds": 25,
            },
            "voicemailMessage": voicemail_message,
            "metadata": {
                "lead_id": lead_id,
                "organization_id": organization_id,
                "owner_id": owner_id,
                "trigger": "speed_to_lead",
                "context_enriched": bool(ctx.get("system_prompt")),
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.vapi.ai/call/phone",
                json=payload,
                headers={
                    "Authorization": f"Bearer {vapi_api_key}",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code in (200, 201):
                data = response.json()
                return {
                    "success": True,
                    "vapi_call_id": data.get("id"),
                    "status": data.get("status", "queued"),
                }
            else:
                error_text = response.text[:500]
                logger.error(f"Vapi call creation failed ({response.status_code}): {error_text}")
                return {"success": False, "error": f"Vapi API {response.status_code}"}

    except Exception as e:
        logger.exception(f"Vapi call initiation error: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# SMS Fallback
# =============================================================================

async def _send_sms_fallback(
    phone_e164: str,
    lead_name: str,
    lead_id: int,
    organization_id: Optional[int],
) -> Dict[str, Any]:
    """Send an SMS when a call cannot be placed (quiet hours, no phone, etc.)."""
    import httpx

    telnyx_key = os.getenv("TELNYX_API_KEY", "")
    from_number = os.getenv("TELNYX_FROM_NUMBER", "")
    profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

    if not telnyx_key or not from_number:
        return {"success": False, "error": "Telnyx SMS not configured"}

    body = (
        f"Hi {lead_name or 'there'}! Thanks for your interest in mortgage options. "
        f"A loan officer will be reaching out shortly to discuss how we can help. "
        f"Reply STOP to opt out."
    )

    payload: Dict[str, Any] = {
        "to": phone_e164,
        "from": from_number,
        "text": body,
    }
    if profile_id:
        payload["messaging_profile_id"] = profile_id

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.telnyx.com/v2/messages",
                json=payload,
                headers={
                    "Authorization": f"Bearer {telnyx_key}",
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code < 400:
            return {"success": True, "channel": "sms"}
        else:
            logger.error(f"SMS fallback failed {resp.status_code}: {resp.text[:200]}")
            return {"success": False, "error": f"SMS send {resp.status_code}"}

    except Exception as e:
        logger.exception(f"SMS fallback error: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Background Task: Execute Speed-to-Lead Call Flow
# =============================================================================

async def _execute_stl_call(
    db_url: str,
    lead_id: int,
    organization_id: int,
    owner_id: Optional[int] = None,
    force: bool = False,
):
    """
    Background task: initiate AI call within 60 seconds of lead creation.

    Flow:
      1. Load lead + org config
      2. Check DNC / opt-out
      3. Check TCPA quiet hours + weekend
      4. Initiate Vapi AI call
      5. On failure -> fallback to SMS
      6. Log everything to activities + speed_to_lead_events
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        _ensure_tables(db)

        # Load lead
        lead = db.execute(text("""
            SELECT id, first_name, last_name, phone, email, organization_id,
                   owner_id, stage, source, loan_type, state
            FROM leads WHERE id = :lid
        """), {"lid": lead_id}).fetchone()

        if not lead:
            logger.warning(f"STL call: lead {lead_id} not found")
            return

        org_id = organization_id or lead.organization_id
        lo_id = owner_id or lead.owner_id
        phone = lead.phone
        lead_name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or "there"
        phone_e164 = _format_e164(phone) if phone else None

        started_at = datetime.now(timezone.utc)
        _log_stl_event(db, lead_id, org_id, "call_flow_started", meta={
            "source": lead.source, "has_phone": bool(phone),
        })

        # Load org config
        config = _get_org_config(db, org_id) if org_id else {
            "sla_seconds": 60, "channels_enabled": ["call", "sms"],
            "quiet_hours_start": "21:00", "quiet_hours_end": "08:00",
            "weekend_calls_enabled": False, "fallback_to_sms": True,
            "ai_greeting_override": None,
        }

        channels = config.get("channels_enabled", ["call", "sms"])

        # ---- No phone? SMS/email only ----
        if not phone_e164:
            _log_stl_event(db, lead_id, org_id, "no_phone", channel="none")
            _log_activity(db, lead_id, org_id, lo_id, "note",
                          "Speed-to-lead: no phone number available, skipping call.")
            return

        # ---- DNC / opt-out check ----
        block_reason = _check_dnc_opt_out(db, phone, org_id)
        if block_reason:
            _log_stl_event(db, lead_id, org_id, "blocked", channel="call",
                           meta={"reason": block_reason})
            _log_activity(db, lead_id, org_id, lo_id, "note",
                          f"Speed-to-lead call blocked: {block_reason}")
            logger.info(f"STL call blocked for lead {lead_id}: {block_reason}")
            return

        # ---- Quiet hours check ----
        in_quiet_hours = _is_tcpa_quiet_hours(
            phone=phone,
            quiet_start=config.get("quiet_hours_start", "21:00"),
            quiet_end=config.get("quiet_hours_end", "08:00"),
        )

        # ---- Weekend check ----
        is_wknd = _is_weekend(phone)
        weekend_blocked = is_wknd and not config.get("weekend_calls_enabled", False)

        call_blocked = (in_quiet_hours or weekend_blocked) and not force

        if call_blocked:
            reason = "quiet_hours" if in_quiet_hours else "weekend"
            _log_stl_event(db, lead_id, org_id, "tcpa_blocked", channel="call",
                           meta={"reason": reason, "phone_tz": _get_borrower_timezone(phone)})

            # Fallback to SMS if configured
            if config.get("fallback_to_sms", True) and "sms" in channels:
                sms_result = await _send_sms_fallback(phone_e164, lead_name, lead_id, org_id)
                if sms_result.get("success"):
                    _log_stl_event(db, lead_id, org_id, "sms_fallback_sent", channel="sms")
                    _log_activity(db, lead_id, org_id, lo_id, "sms",
                                  f"Speed-to-lead SMS sent (call blocked: {reason})")
                else:
                    _log_stl_event(db, lead_id, org_id, "sms_fallback_failed", channel="sms",
                                   meta=sms_result)
            else:
                _log_activity(db, lead_id, org_id, lo_id, "note",
                              f"Speed-to-lead call blocked ({reason}), no SMS fallback.")

            logger.info(f"STL call blocked for lead {lead_id}: {reason}")
            return

        # ---- Build cross-channel context for AI call ----
        outbound_ctx = None
        try:
            outbound_ctx = build_outbound_context(db, lead_id, org_id)
        except Exception as e:
            logger.warning(f"Outbound context build failed (non-fatal): {e}")

        # ---- Initiate AI call via Vapi ----
        if "call" in channels:
            call_result = await _initiate_vapi_call(
                phone_e164=phone_e164,
                lead_name=lead_name,
                lead_id=lead_id,
                organization_id=org_id,
                owner_id=lo_id,
                greeting_override=config.get("ai_greeting_override"),
                outbound_context=outbound_ctx,
            )

            elapsed_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

            if call_result.get("success"):
                vapi_call_id = call_result.get("vapi_call_id")
                _log_stl_event(db, lead_id, org_id, "call_initiated", channel="vapi",
                               vapi_call_id=vapi_call_id,
                               meta={"elapsed_ms": elapsed_ms})
                _log_activity(db, lead_id, org_id, lo_id, "call",
                              f"Speed-to-lead AI call initiated via Vapi (ID: {vapi_call_id})",
                              metadata={"vapi_call_id": vapi_call_id, "elapsed_ms": elapsed_ms})

                # Also log to call_logs if the table exists
                try:
                    db.execute(text("""
                        INSERT INTO call_logs (call_sid, phone_number, direction, status,
                            organization_id, agent_id, created_at)
                        VALUES (:sid, :phone, 'outbound', 'initiated', :org_id, :lo_id, :now)
                    """), {
                        "sid": vapi_call_id,
                        "phone": phone,
                        "org_id": org_id,
                        "lo_id": lo_id,
                        "now": datetime.now(timezone.utc),
                    })
                    db.commit()
                except Exception as e:
                    logger.warning("Failed to log STL call to call_logs for lead %s: %s", lead_id, e)
                    db.rollback()

                logger.info(
                    f"STL call initiated for lead {lead_id} in {elapsed_ms}ms "
                    f"(vapi_call_id={vapi_call_id})"
                )
                return

            # Call failed -> fallback to SMS
            logger.warning(f"STL Vapi call failed for lead {lead_id}: {call_result.get('error')}")
            _log_stl_event(db, lead_id, org_id, "call_failed", channel="vapi",
                           meta={"error": call_result.get("error"), "elapsed_ms": elapsed_ms})

            if config.get("fallback_to_sms", True) and "sms" in channels:
                sms_result = await _send_sms_fallback(phone_e164, lead_name, lead_id, org_id)
                if sms_result.get("success"):
                    _log_stl_event(db, lead_id, org_id, "sms_fallback_sent", channel="sms")
                    _log_activity(db, lead_id, org_id, lo_id, "sms",
                                  "Speed-to-lead SMS sent (Vapi call failed, SMS fallback)")
                else:
                    _log_stl_event(db, lead_id, org_id, "sms_fallback_failed", channel="sms",
                                   meta=sms_result)

        elif "sms" in channels:
            # Call channel not enabled, try SMS directly
            sms_result = await _send_sms_fallback(phone_e164, lead_name, lead_id, org_id)
            if sms_result.get("success"):
                _log_stl_event(db, lead_id, org_id, "sms_sent", channel="sms")
                _log_activity(db, lead_id, org_id, lo_id, "sms",
                              "Speed-to-lead SMS sent (call channel disabled)")

        _log_stl_event(db, lead_id, org_id, "call_flow_completed", meta={
            "elapsed_ms": int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
        })

    except Exception as e:
        logger.exception(f"STL call flow failed for lead {lead_id}: {e}")
        try:
            _log_stl_event(db, lead_id, organization_id, "call_flow_error",
                           meta={"error": str(e)[:500]})
        except Exception as log_err:
            logger.error("Failed to log STL call flow error for lead %s: %s", lead_id, log_err)
    finally:
        db.close()
        engine.dispose()


# =============================================================================
# Routes
# =============================================================================

@router.post("/trigger-call")
async def trigger_call(
    body: TriggerCallRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Trigger an AI outbound call for a specific lead.

    The call is initiated asynchronously via Vapi within 60 seconds.
    If the call cannot be placed (TCPA quiet hours, no phone, DNC),
    the system falls back to SMS.

    Requires authentication.
    """
    auth_dep = _get_auth_flexible()
    current_user = await auth_dep(request, db)

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    _ensure_tables(db)

    # Verify lead exists and belongs to the user's org
    lead = db.execute(text("""
        SELECT id, phone, first_name, last_name, owner_id, stage
        FROM leads
        WHERE id = :lid AND organization_id = :org_id
    """), {"lid": body.lead_id, "org_id": org_id}).fetchone()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found in your organization")

    # Quick validation
    phone_e164 = _format_e164(lead.phone) if lead.phone else None
    if not phone_e164:
        # Immediate SMS fallback check
        return {
            "status": "skipped",
            "reason": "Lead has no valid phone number",
            "lead_id": body.lead_id,
        }

    # Pre-flight DNC check (synchronous, before background task)
    block_reason = _check_dnc_opt_out(db, lead.phone, org_id)
    if block_reason:
        _log_stl_event(db, body.lead_id, org_id, "blocked_preflight",
                       channel="call", meta={"reason": block_reason})
        return {
            "status": "blocked",
            "reason": block_reason,
            "lead_id": body.lead_id,
        }

    # Dispatch to background task
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")

    background_tasks.add_task(
        _execute_stl_call,
        db_url=db_url,
        lead_id=body.lead_id,
        organization_id=org_id,
        owner_id=lead.owner_id,
        force=body.force,
    )

    return {
        "status": "triggered",
        "lead_id": body.lead_id,
        "phone_last4": lead.phone[-4:] if lead.phone else None,
        "message": "AI call will be initiated within 60 seconds",
    }


@router.post("/new-lead-webhook")
async def new_lead_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Webhook endpoint for any lead source (web form, API, LOS sync).

    Validates the lead exists and auto-triggers an AI call within 60 seconds.
    Returns immediately while processing happens asynchronously.

    Authentication: X-API-Key header or api_key in payload.

    Rate limiting: This endpoint should be behind X-RateLimit enforcement
    (e.g., 30 requests/minute per source IP). The idempotency check below
    provides application-level protection against duplicate webhook retries.
    """
    _ensure_tables(db)

    # --- SEC-002 Fix: Timing-safe API key validation with empty-key rejection ---
    expected_key = os.getenv("SPEED_TO_LEAD_WEBHOOK_KEY", "")
    if not expected_key:
        logger.error("SPEED_TO_LEAD_WEBHOOK_KEY is not configured; rejecting all webhook requests")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    api_key_header = request.headers.get("X-API-Key", "")
    payload = await request.json()

    # Allow api_key in body as fallback
    api_key = api_key_header or payload.get("api_key", "")

    # Reject empty/None API keys before comparison
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    # Timing-safe comparison to prevent timing attacks
    if not hmac.compare_digest(api_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        body = NewLeadWebhookPayload(**payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    # --- IDOR Fix: Verify lead exists AND belongs to a valid organization ---
    # Query requires organization_id IS NOT NULL to ensure the lead is org-scoped
    lead = db.execute(text("""
        SELECT l.id, l.phone, l.organization_id, l.owner_id, l.first_name
        FROM leads l
        INNER JOIN organizations o ON o.id = l.organization_id
        WHERE l.id = :lid AND l.organization_id IS NOT NULL
    """), {"lid": body.lead_id}).fetchone()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.phone:
        return {
            "status": "accepted",
            "lead_id": body.lead_id,
            "call_triggered": False,
            "reason": "no_phone_number",
        }

    # --- Idempotency: reject if a speed-to-lead call was already triggered
    #     for this lead in the last 60 seconds (prevents duplicate webhook retries) ---
    try:
        recent_event = db.execute(text("""
            SELECT id FROM speed_to_lead_events
            WHERE lead_id = :lid
              AND event = 'call_flow_started'
              AND created_at > NOW() - INTERVAL '60 seconds'
            LIMIT 1
        """), {"lid": body.lead_id}).fetchone()
        if recent_event:
            logger.info(
                "STL webhook: duplicate suppressed for lead %s (event %s within 60s)",
                body.lead_id, recent_event.id,
            )
            return {
                "status": "accepted",
                "lead_id": body.lead_id,
                "call_triggered": False,
                "reason": "duplicate_suppressed",
                "message": "A speed-to-lead call was already triggered for this lead recently",
            }
    except Exception as e:
        # Non-fatal: if the idempotency check fails, allow the call to proceed
        logger.warning("STL idempotency check failed (non-fatal): %s", e)

    # Dispatch background call
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")

    background_tasks.add_task(
        _execute_stl_call,
        db_url=db_url,
        lead_id=body.lead_id,
        organization_id=lead.organization_id,
        owner_id=lead.owner_id,
    )

    logger.info("STL webhook: auto-call triggered for lead %s (source=%s, org=%s)", body.lead_id, body.source, lead.organization_id)

    return {
        "status": "accepted",
        "lead_id": body.lead_id,
        "call_triggered": True,
        "message": "AI call will be initiated within 60 seconds",
    }


@router.get("/config")
async def get_config(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get the per-organization speed-to-lead configuration.

    Returns defaults if no custom config has been set.
    """
    auth_dep = _get_auth_flexible()
    current_user = await auth_dep(request, db)

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    _ensure_tables(db)

    config = _get_org_config(db, org_id)
    return {
        "organization_id": org_id,
        "config": config,
    }


@router.put("/config")
async def update_config(
    body: SpeedToLeadConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Update per-organization speed-to-lead configuration.

    Only provided fields are updated; omitted fields retain current values.
    """
    auth_dep = _get_auth_flexible()
    current_user = await auth_dep(request, db)

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    _ensure_tables(db)

    # Validate channels
    if body.channels_enabled is not None:
        valid_channels = {"call", "sms", "email"}
        invalid = set(body.channels_enabled) - valid_channels
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid channels: {invalid}. Valid: {valid_channels}",
            )

    # Validate time format
    for field_name in ("quiet_hours_start", "quiet_hours_end"):
        val = getattr(body, field_name, None)
        if val:
            try:
                parts = val.split(":")
                h, m = int(parts[0]), int(parts[1])
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError
            except (ValueError, IndexError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid {field_name} format. Use HH:MM (e.g., '21:00')",
                )

    # Check if config exists
    existing = db.execute(text("""
        SELECT id FROM speed_to_lead_config WHERE organization_id = :org_id
    """), {"org_id": org_id}).fetchone()

    import json

    if existing:
        # Build dynamic UPDATE
        updates = []
        params: Dict[str, Any] = {"org_id": org_id, "now": datetime.now(timezone.utc)}

        if body.sla_seconds is not None:
            updates.append("sla_seconds = :sla")
            params["sla"] = body.sla_seconds
        if body.channels_enabled is not None:
            updates.append("channels_enabled = :channels::jsonb")
            params["channels"] = json.dumps(body.channels_enabled)
        if body.quiet_hours_start is not None:
            updates.append("quiet_hours_start = :qhs")
            params["qhs"] = body.quiet_hours_start
        if body.quiet_hours_end is not None:
            updates.append("quiet_hours_end = :qhe")
            params["qhe"] = body.quiet_hours_end
        if body.weekend_calls_enabled is not None:
            updates.append("weekend_calls_enabled = :wce")
            params["wce"] = body.weekend_calls_enabled
        if body.fallback_to_sms is not None:
            updates.append("fallback_to_sms = :fts")
            params["fts"] = body.fallback_to_sms
        if body.ai_greeting_override is not None:
            updates.append("ai_greeting_override = :ago")
            params["ago"] = body.ai_greeting_override

        if updates:
            updates.append("updated_at = :now")
            sql = f"UPDATE speed_to_lead_config SET {', '.join(updates)} WHERE organization_id = :org_id"
            db.execute(text(sql), params)
            db.commit()
    else:
        # INSERT with defaults + provided values
        db.execute(text("""
            INSERT INTO speed_to_lead_config (
                organization_id, sla_seconds, channels_enabled,
                quiet_hours_start, quiet_hours_end,
                weekend_calls_enabled, fallback_to_sms, ai_greeting_override,
                created_at, updated_at
            ) VALUES (
                :org_id, :sla, :channels::jsonb, :qhs, :qhe, :wce, :fts, :ago, :now, :now
            )
        """), {
            "org_id": org_id,
            "sla": body.sla_seconds or 60,
            "channels": json.dumps(body.channels_enabled or ["call", "sms"]),
            "qhs": body.quiet_hours_start or "21:00",
            "qhe": body.quiet_hours_end or "08:00",
            "wce": body.weekend_calls_enabled if body.weekend_calls_enabled is not None else False,
            "fts": body.fallback_to_sms if body.fallback_to_sms is not None else True,
            "ago": body.ai_greeting_override,
            "now": datetime.now(timezone.utc),
        })
        db.commit()

    # Return updated config
    config = _get_org_config(db, org_id)
    return {
        "organization_id": org_id,
        "config": config,
        "updated": True,
    }
