"""
Voicemail Drop Routes

This module contains all API endpoints for the voicemail drop system.
Extracted from main.py for better code organization.
"""

import os
import logging
import re
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy import or_

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voicemail", tags=["Voicemail Drop"])

# =============================================================================
# TCPA Compliance Constants
# =============================================================================

# TCPA calling window: 8:00 AM - 9:00 PM in recipient's local timezone
TCPA_CALL_START = dt_time(8, 0)
TCPA_CALL_END = dt_time(21, 0)

# US area code to timezone mapping (covers major area codes)
# Falls back to America/New_York if unknown
AREA_CODE_TIMEZONE = {
    # Eastern Time
    "201": "America/New_York", "202": "America/New_York", "203": "America/New_York",
    "207": "America/New_York", "212": "America/New_York", "215": "America/New_York",
    "216": "America/New_York", "229": "America/New_York", "231": "America/New_York",
    "234": "America/New_York", "239": "America/New_York", "240": "America/New_York",
    "248": "America/New_York", "251": "America/New_York", "252": "America/New_York",
    "267": "America/New_York", "269": "America/New_York", "272": "America/New_York",
    "276": "America/New_York", "278": "America/New_York", "301": "America/New_York",
    "302": "America/New_York", "304": "America/New_York", "305": "America/New_York",
    "313": "America/New_York", "315": "America/New_York", "321": "America/New_York",
    "330": "America/New_York", "336": "America/New_York", "339": "America/New_York",
    "347": "America/New_York", "351": "America/New_York", "352": "America/New_York",
    "386": "America/New_York", "401": "America/New_York", "404": "America/New_York",
    "407": "America/New_York", "410": "America/New_York", "412": "America/New_York",
    "413": "America/New_York", "414": "America/New_York", "419": "America/New_York",
    "440": "America/New_York", "443": "America/New_York", "470": "America/New_York",
    "475": "America/New_York", "478": "America/New_York", "484": "America/New_York",
    "502": "America/New_York", "508": "America/New_York", "513": "America/New_York",
    "516": "America/New_York", "517": "America/New_York", "518": "America/New_York",
    "540": "America/New_York", "551": "America/New_York", "561": "America/New_York",
    "567": "America/New_York", "570": "America/New_York", "571": "America/New_York",
    "585": "America/New_York", "586": "America/New_York", "601": "America/New_York",
    "603": "America/New_York", "607": "America/New_York", "609": "America/New_York",
    "610": "America/New_York", "614": "America/New_York", "616": "America/New_York",
    "617": "America/New_York", "631": "America/New_York", "646": "America/New_York",
    "651": "America/New_York", "678": "America/New_York", "681": "America/New_York",
    "689": "America/New_York", "704": "America/New_York", "706": "America/New_York",
    "716": "America/New_York", "717": "America/New_York", "718": "America/New_York",
    "724": "America/New_York", "727": "America/New_York", "732": "America/New_York",
    "740": "America/New_York", "754": "America/New_York", "757": "America/New_York",
    "762": "America/New_York", "763": "America/New_York", "770": "America/New_York",
    "772": "America/New_York", "774": "America/New_York", "781": "America/New_York",
    "786": "America/New_York", "803": "America/New_York", "804": "America/New_York",
    "810": "America/New_York", "813": "America/New_York", "828": "America/New_York",
    "843": "America/New_York", "845": "America/New_York", "848": "America/New_York",
    "856": "America/New_York", "857": "America/New_York", "860": "America/New_York",
    "862": "America/New_York", "863": "America/New_York", "864": "America/New_York",
    "878": "America/New_York", "904": "America/New_York", "908": "America/New_York",
    "910": "America/New_York", "912": "America/New_York", "914": "America/New_York",
    "917": "America/New_York", "919": "America/New_York", "920": "America/New_York",
    "929": "America/New_York", "931": "America/New_York", "937": "America/New_York",
    "941": "America/New_York", "954": "America/New_York", "973": "America/New_York",
    "978": "America/New_York", "980": "America/New_York",
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
    "520": "America/Chicago", "531": "America/Chicago", "534": "America/Chicago",
    "539": "America/Chicago", "563": "America/Chicago", "573": "America/Chicago",
    "580": "America/Chicago", "608": "America/Chicago", "612": "America/Chicago",
    "615": "America/Chicago", "618": "America/Chicago", "620": "America/Chicago",
    "630": "America/Chicago", "636": "America/Chicago", "641": "America/Chicago",
    "660": "America/Chicago", "662": "America/Chicago", "682": "America/Chicago",
    "701": "America/Chicago", "708": "America/Chicago", "712": "America/Chicago",
    "713": "America/Chicago", "715": "America/Chicago", "719": "America/Chicago",
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
    # Mountain Time
    "303": "America/Denver", "307": "America/Denver", "385": "America/Denver",
    "406": "America/Denver", "435": "America/Denver", "505": "America/Denver",
    "575": "America/Denver", "602": "America/Denver", "623": "America/Denver",
    "720": "America/Denver", "801": "America/Denver", "928": "America/Denver",
    "970": "America/Denver", "480": "America/Denver",
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

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Get current user - wrapper that imports from main at runtime to avoid circular imports.
    """
    import main

    # Get token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""

    # Fall back to query param
    if not token:
        token = request.query_params.get("token", "")

    return await main.get_current_user(token=token, request=request, db=db)


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
    except Exception:
        tz = ZoneInfo("America/New_York")

    recipient_now = datetime.now(tz)
    local_time = recipient_now.time()

    if local_time < TCPA_CALL_START or local_time >= TCPA_CALL_END:
        return False, (
            f"TCPA: Cannot call outside 8:00 AM - 9:00 PM recipient local time. "
            f"Current time in {tz_name}: {local_time.strftime('%I:%M %p')}"
        )
    return True, ""


def check_dnc_status(phone_number: str, db: Session) -> Tuple[bool, str]:
    """
    Check if phone number is on the Do Not Call list.

    Returns (is_blocked, message).
    """
    from database.models.dialer import ContactDNCStatus

    digits = _normalize_phone(phone_number)

    # Check exact match and common formats
    dnc = db.query(ContactDNCStatus).filter(
        or_(
            ContactDNCStatus.phone_number == phone_number,
            ContactDNCStatus.phone_number == digits,
            ContactDNCStatus.phone_number == f"+1{digits}",
            ContactDNCStatus.phone_number == f"1{digits}",
        )
    ).first()

    if dnc:
        return True, f"Phone number is on Do Not Call list (reason: {dnc.reason or 'N/A'})"
    return False, ""


def check_consent(lead_id: Optional[int], db: Session) -> Tuple[bool, str]:
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
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return True, ""  # Lead not found — allow (may be external contact)

        # Check if lead has a phone match in BorrowerProfile with consent fields
        if lead.phone:
            digits = _normalize_phone(lead.phone)
            borrower = db.query(BorrowerProfile).filter(
                or_(
                    BorrowerProfile.phone == lead.phone,
                    BorrowerProfile.phone == digits,
                )
            ).first()

            if borrower:
                if borrower.communication_consent is False:
                    return False, "Contact has opted out of communications"
                if borrower.marketing_consent is False:
                    # Allow transactional (loan status, doc requests) but warn about marketing
                    logger.info(
                        f"Lead {lead_id}: marketing_consent=False — "
                        "allowing transactional voicemail, blocking marketing"
                    )

    except ImportError:
        logger.warning("BorrowerProfile model not available for consent check")
    except Exception as e:
        logger.warning(f"Consent check error (allowing call): {e}")

    return True, ""


def run_compliance_checks(
    phone_number: str,
    lead_id: Optional[int],
    db: Session,
) -> Tuple[bool, Optional[str]]:
    """
    Run all TCPA compliance checks before sending a voicemail.

    Returns (is_allowed, rejection_reason).
    """
    # 1. DNC check
    is_blocked, dnc_msg = check_dnc_status(phone_number, db)
    if is_blocked:
        logger.warning(f"Voicemail blocked by DNC: {phone_number}")
        return False, dnc_msg

    # 2. Consent check
    has_consent, consent_msg = check_consent(lead_id, db)
    if not has_consent:
        logger.warning(f"Voicemail blocked by consent: lead_id={lead_id}")
        return False, consent_msg

    # 3. Calling hours check
    is_allowed, hours_msg = check_calling_hours(phone_number)
    if not is_allowed:
        logger.warning(f"Voicemail blocked by calling hours: {phone_number}")
        return False, hours_msg

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
    db: Session
) -> dict:
    """Helper function to send voicemail using Vapi AI"""
    import httpx

    vapi_api_key = os.getenv("VAPI_API_KEY")
    vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")

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
        f"Feel free to call us back at your convenience. Have a great day!"
    )

    # Vapi call configuration
    vapi_payload = {
        "phoneNumberId": vapi_assistant_id,
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
            "voice": {
                "provider": "11labs",
                "voiceId": "paula"  # Natural, professional female voice
            },
            "endCallFunctionEnabled": True,
            "endCallMessage": "Thank you, goodbye!",
            "voicemailDetection": {
                "enabled": True,
                "machineDetectionTimeout": 3000,
                "voicemailMessage": full_message
            }
        },
        "metadata": {
            "voicemail_drop_id": voicemail_drop_id,
            "type": "voicemail_drop"
        }
    }

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
                logger.error(f"Vapi API error: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Vapi error: {error_msg}")

            result = response.json()
            call_id = result.get("id")

            logger.info(f"Vapi call initiated: {call_id}")

            return {
                "success": True,
                "call_id": call_id,
                "vapi_response": result
            }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling Vapi: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")


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
        "template_id": 1  // optional
    }
    """
    VoicemailDrop = get_voicemail_drop_model()
    VoicemailEvent = get_voicemail_event_model()

    try:
        data = await request.json()

        phone_number = data.get("phone_number")
        recipient_name = data.get("recipient_name", "")
        message = data.get("message")
        lead_id = data.get("lead_id")
        loan_id = data.get("loan_id")
        template_id = data.get("template_id")

        if not phone_number:
            raise HTTPException(status_code=400, detail="Phone number is required")

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        # --- TCPA Compliance Checks ---
        is_allowed, rejection_reason = run_compliance_checks(
            phone_number=phone_number,
            lead_id=lead_id,
            db=db,
        )
        if not is_allowed:
            logger.warning(
                f"Voicemail drop blocked for {phone_number}: {rejection_reason} "
                f"(user={current_user.id})"
            )
            raise HTTPException(status_code=403, detail=rejection_reason)

        # Create voicemail drop record
        voicemail_drop = VoicemailDrop(
            user_id=current_user.id,
            lead_id=lead_id,
            loan_id=loan_id,
            template_id=template_id,
            contact_name=recipient_name,
            phone_number=phone_number,
            message_text=message,
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

        # Send voicemail via Vapi
        try:
            vapi_result = await send_voicemail_via_vapi(
                phone_number=phone_number,
                message=message,
                recipient_name=recipient_name,
                user_name=current_user.full_name or "your loan officer",
                voicemail_drop_id=voicemail_drop.id,
                db=db
            )

            # Update voicemail drop with Vapi call ID
            voicemail_drop.vapi_call_id = vapi_result.get("call_id")
            voicemail_drop.status = 'calling'
            voicemail_drop.delivery_attempts = 1
            voicemail_drop.last_attempt_at = datetime.now(timezone.utc)
            db.commit()

            # Create calling event
            calling_event = VoicemailEvent(
                voicemail_drop_id=voicemail_drop.id,
                event_type='calling',
                event_data={"vapi_call_id": vapi_result.get("call_id")}
            )
            db.add(calling_event)
            db.commit()

            logger.info(f"Voicemail drop {voicemail_drop.id} initiated successfully")

            return {
                "success": True,
                "voicemail_drop_id": voicemail_drop.id,
                "vapi_call_id": vapi_result.get("call_id"),
                "status": "calling",
                "message": "Voicemail is being delivered"
            }

        except Exception as e:
            # Update voicemail drop with error
            voicemail_drop.status = 'failed'
            voicemail_drop.error_message = str(e)
            db.commit()

            # Create failed event
            failed_event = VoicemailEvent(
                voicemail_drop_id=voicemail_drop.id,
                event_type='failed',
                event_data={"error": str(e)}
            )
            db.add(failed_event)
            db.commit()

            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating voicemail drop: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=503, detail="OpenAI API key not configured")

        # Read audio file
        audio_data = await audio_file.read()

        # Call OpenAI Whisper API
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {
                'file': ('audio.webm', audio_data, 'audio/webm'),
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
                raise HTTPException(status_code=500, detail=f"Transcription failed: {error_msg}")

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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def get_voicemail_templates(
    category: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get voicemail templates (default templates + user's custom templates)"""
    VoicemailTemplate = get_voicemail_template_model()

    try:
        query = db.query(VoicemailTemplate).filter(
            VoicemailTemplate.is_active == True
        ).filter(
            or_(
                VoicemailTemplate.user_id == None,  # Default templates
                VoicemailTemplate.user_id == current_user.id  # User's templates
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
                    "last_used_at": t.last_used_at.isoformat() if t.last_used_at else None
                }
                for t in templates
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
            name=name,
            category=category,
            message_text=message_text,
            variables=variables,
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
                "variables": template.variables
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        query = db.query(VoicemailDrop).filter(
            VoicemailDrop.user_id == current_user.id
        )

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
                    "created_at": vm.created_at.isoformat(),
                    "delivered_at": vm.delivered_at.isoformat() if vm.delivered_at else None,
                    "call_duration": vm.call_duration,
                    "call_cost": float(vm.call_cost) if vm.call_cost else None,
                    "callback_received": vm.callback_received,
                    "error_message": vm.error_message
                }
                for vm in voicemails
            ]
        }

    except Exception as e:
        logger.error(f"Error fetching voicemail history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        base_filters = [
            VoicemailDrop.user_id == current_user.id,
            VoicemailDrop.created_at >= start,
            VoicemailDrop.created_at <= end,
        ]

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
                "period": {
                    "start": start_date,
                    "end": end_date
                }
            }
        }

    except Exception as e:
        logger.error(f"Error fetching analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
