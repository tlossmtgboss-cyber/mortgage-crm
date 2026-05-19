"""Cross-Channel Context Sharing Service.

Breaks down channel silos so AI (Claude, Vapi, SMS agents) can reference
prior interactions across calls, SMS, email, and calendar when engaging
a lead.  Every public function enforces organization_id tenant isolation.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory context cache (PERF-012)
# ---------------------------------------------------------------------------
_context_cache: Dict[Tuple[int, int], Tuple[float, Dict[str, Any]]] = {}
_cache_ttl: float = 120.0  # seconds

# ---------------------------------------------------------------------------
# Scoring weights for engagement events
# ---------------------------------------------------------------------------
ENGAGEMENT_WEIGHTS: Dict[str, int] = {
    "sms_response": 5,
    "email_open": 2,
    "email_click": 5,
    "call_answered": 10,
    "call_voicemail": 2,
    "appointment_booked": 20,
    "application_started": 30,
    "voicemail_callback": 15,
}


# ---------------------------------------------------------------------------
# 1. get_lead_engagement_context
# ---------------------------------------------------------------------------

async def get_lead_engagement_context(
    db: Session,
    lead_id: int,
    organization_id: int,
) -> Dict[str, Any]:
    """Return a structured dict summarizing the lead's cross-channel engagement.

    All queries are scoped to *organization_id* for tenant isolation.
    Results are cached for 2 minutes (PERF-012).
    """
    # --- Check cache (PERF-012) -----------------------------------------------
    cache_key = (lead_id, organization_id)
    cached = _context_cache.get(cache_key)
    if cached is not None:
        cached_at, cached_result = cached
        if time.monotonic() - cached_at < _cache_ttl:
            return cached_result

    t0 = time.monotonic()

    # --- Load lead ONCE, pass to helpers (PERF-014) ---------------------------
    lead = _load_lead(db, lead_id, organization_id)

    result = {
        "last_call": _get_last_call(db, lead_id, organization_id),
        "sms_conversation": _get_sms_context(db, lead_id, organization_id),
        "email_history": _get_email_history(db, lead_id, organization_id),
        "qualification_data": await merge_qualification_data(db, lead_id, organization_id, lead=lead),
        "deal_breaker_result": _get_deal_breaker_result(db, lead_id, organization_id, lead=lead),
        "drip_status": _get_drip_status(db, lead_id, organization_id),
        "appointments": _get_appointments(db, lead_id, organization_id),
        "overall_engagement_score": _compute_engagement_score(db, lead_id, organization_id, lead=lead),
        "channel_preference": _derive_channel_preference(db, lead_id, organization_id, lead=lead),
    }

    # --- Cache result (PERF-012) ----------------------------------------------
    _context_cache[cache_key] = (time.monotonic(), result)

    # --- Performance timing (OBS-015) -----------------------------------------
    elapsed_ms = (time.monotonic() - t0) * 1000
    if elapsed_ms > 500:
        logger.warning(
            "get_lead_engagement_context for lead %d took %.0fms (threshold 500ms)",
            lead_id,
            elapsed_ms,
        )

    return result


# ---------------------------------------------------------------------------
# 2. build_ai_prompt_context
# ---------------------------------------------------------------------------

async def build_ai_prompt_context(
    db: Session,
    lead_id: int,
    organization_id: int,
) -> str:
    """Build a concise natural-language context block (<500 tokens) for AI prompts."""
    ctx = await get_lead_engagement_context(db, lead_id, organization_id)
    parts: List[str] = []

    # --- Lead basics ----------------------------------------------------------
    lead = _load_lead(db, lead_id, organization_id)
    if lead:
        name = lead.name or "Unknown"
        parts.append(f"Lead: {name} | Stage: {lead.stage or 'New'}")

    # --- SMS context ----------------------------------------------------------
    sms = ctx.get("sms_conversation") or {}
    if sms.get("message_count"):
        parts.append(
            f"SMS: {sms['message_count']} messages, "
            f"stage={sms.get('stage', '?')}, "
            f"last msg {_relative_time(sms.get('last_message_at'))}"
        )
        collected = sms.get("collected_data") or {}
        if collected:
            snippets = [f"{k}={v}" for k, v in list(collected.items())[:5]]
            parts.append(f"  SMS collected: {', '.join(snippets)}")

    # --- Last call ------------------------------------------------------------
    call = ctx.get("last_call") or {}
    if call.get("date"):
        line = f"Last call ({_relative_time(call['date'])})"
        if call.get("duration"):
            line += f", {call['duration']}s"
        if call.get("summary"):
            line += f": {call['summary'][:120]}"
        if call.get("sentiment"):
            line += f" [sentiment: {call['sentiment']}]"
        parts.append(line)
        if call.get("action_items"):
            parts.append(f"  Action items: {', '.join(call['action_items'][:3])}")

    # --- Email ----------------------------------------------------------------
    email = ctx.get("email_history") or {}
    if email.get("total_sent"):
        line = f"Email: {email['total_sent']} sent"
        if email.get("total_opens"):
            line += f", {email['total_opens']} opens"
        if email.get("last_sent"):
            line += f", last sent {_relative_time(email['last_sent'])}"
        parts.append(line)

    # --- Qualification --------------------------------------------------------
    qual = ctx.get("qualification_data") or {}
    filled = {k: v for k, v in qual.items() if v is not None and k != "sources"}
    if filled:
        pct = _qualification_pct(qual)
        missing = _missing_fields(qual)
        parts.append(f"Qualification: {pct}% complete")
        if missing:
            parts.append(f"  Missing: {', '.join(missing[:5])}")
        if qual.get("credit_range"):
            parts.append(f"  Credit: {qual['credit_range']}")
        if qual.get("loan_purpose"):
            parts.append(f"  Purpose: {qual['loan_purpose']}")
        if qual.get("loan_amount"):
            parts.append(f"  Amount: ${qual['loan_amount']:,.0f}")

    # --- Deal breaker ---------------------------------------------------------
    db_result = ctx.get("deal_breaker_result") or {}
    if db_result.get("has_deal_breakers") is not None:
        if db_result["has_deal_breakers"]:
            names = [b["name"] for b in db_result.get("deal_breakers", [])[:3]]
            parts.append(f"Deal breakers: {', '.join(names)} | Action: {db_result.get('recommended_action', '?')}")
        else:
            programs = db_result.get("eligible_programs") or []
            parts.append(f"Deal breaker check: clean. Eligible: {', '.join(programs[:4]) or 'TBD'}")

    # --- Drip -----------------------------------------------------------------
    drip = ctx.get("drip_status") or {}
    if drip.get("enrollments"):
        names = [e.get("sequence_name", "?") for e in drip["enrollments"]]
        parts.append(f"Drip: enrolled in {', '.join(names)}")

    # --- Appointments ---------------------------------------------------------
    appts = ctx.get("appointments") or {}
    upcoming = appts.get("upcoming") or []
    if upcoming:
        a = upcoming[0]
        parts.append(f"Next appointment: {a.get('title', '?')} on {a.get('scheduled_start', '?')}")

    # --- Engagement / preference ----------------------------------------------
    score = ctx.get("overall_engagement_score", 0)
    pref = ctx.get("channel_preference", "unknown")
    parts.append(f"Engagement score: {score} | Preferred channel: {pref}")

    # Trim to ~500 tokens (rough heuristic: 1 token ~ 4 chars)
    result = "\n".join(parts)
    if len(result) > 2000:
        result = result[:1997] + "..."
    return result


# ---------------------------------------------------------------------------
# 3. merge_qualification_data
# ---------------------------------------------------------------------------

async def merge_qualification_data(
    db: Session,
    lead_id: int,
    organization_id: int,
    *,
    lead=None,
) -> Dict[str, Any]:
    """Combine qualification data from all channels with source attribution.

    Priority order (later overwrites earlier unless None):
      1. SMS conversation context_data (last 90 days only — DATA-008)
      2. Call transcript extracted entities (last 90 days only — DATA-008)
      3. Lead model fields (authoritative)

    Pass *lead* to avoid a redundant DB load (PERF-014).
    """
    merged: Dict[str, Any] = {
        "credit_score": None,
        "credit_range": None,
        "loan_purpose": None,
        "loan_amount": None,
        "property_value": None,
        "down_payment": None,
        "annual_income": None,
        "employment_status": None,
        "first_time_buyer": None,
        "property_type": None,
        "timeline": None,
        "loan_type": None,
        "debt_to_income": None,
        "sources": {},
    }

    freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    # --- Source 1: SMS AI conversation context_data ---------------------------
    try:
        from database.models.sms_conversation import SMSAIConversation
        sms_conv = (
            db.query(SMSAIConversation)
            .filter(
                SMSAIConversation.lead_id == lead_id,
                SMSAIConversation.organization_id == organization_id,
            )
            .order_by(desc(SMSAIConversation.last_message_at))
            .first()
        )
        # DATA-008: Only use SMS data from the last 90 days
        if (
            sms_conv
            and sms_conv.context_data
            and sms_conv.last_message_at
            and sms_conv.last_message_at >= freshness_cutoff
        ):
            _sms_data = sms_conv.context_data or {}
            _MAP = {
                "credit_score": "credit_score",
                "credit_range": "credit_range",
                "loan_purpose": "loan_purpose",
                "loan_amount": "loan_amount",
                "property_value": "property_value",
                "down_payment": "down_payment",
                "income": "annual_income",
                "annual_income": "annual_income",
                "employment": "employment_status",
                "employment_status": "employment_status",
                "first_time_buyer": "first_time_buyer",
                "property_type": "property_type",
                "timeline": "timeline",
                "loan_type": "loan_type",
            }
            for sms_key, merged_key in _MAP.items():
                val = _sms_data.get(sms_key)
                if val is not None:
                    merged[merged_key] = val
                    merged["sources"][merged_key] = "sms"
        elif sms_conv and sms_conv.context_data and sms_conv.last_message_at:
            logger.debug(
                "Skipping stale SMS qualification data for lead %d (last message: %s)",
                lead_id,
                sms_conv.last_message_at.isoformat(),
            )
    except Exception as e:
        logger.exception(f"Error reading SMS context for lead {lead_id}: {e}")

    # --- Source 2: Call transcript entity extractions --------------------------
    try:
        from database.models.communication import Activity
        from database.enums import ActivityType

        # DATA-008: Only use call data from the last 90 days
        call_activities = (
            db.query(Activity)
            .filter(
                Activity.lead_id == lead_id,
                Activity.organization_id == organization_id,
                Activity.type == ActivityType.CALL,
                Activity.created_at >= freshness_cutoff,
            )
            .order_by(desc(Activity.created_at))
            .limit(5)
            .all()
        )
        for act in call_activities:
            meta = act.user_metadata or {}
            entities = meta.get("extracted_entities") or meta.get("entities") or {}
            for key in ("credit_score", "loan_purpose", "loan_amount", "property_value",
                        "down_payment", "annual_income", "employment_status",
                        "property_type", "timeline", "loan_type"):
                val = entities.get(key)
                if val is not None and merged.get(key) is None:
                    merged[key] = val
                    merged["sources"][key] = "call"
    except Exception as e:
        logger.exception(f"Error reading call entities for lead {lead_id}: {e}")

    # --- Source 3: Lead model fields (authoritative) --------------------------
    if lead is None:
        lead = _load_lead(db, lead_id, organization_id)
    if lead:
        _lead_map = {
            "credit_score": lead.credit_score,
            "loan_purpose": lead.loan_purpose,
            "loan_amount": float(lead.loan_amount) if lead.loan_amount else None,
            "property_value": float(lead.property_value) if lead.property_value else None,
            "down_payment": float(lead.down_payment) if lead.down_payment else None,
            "annual_income": float(lead.annual_income) if lead.annual_income else None,
            "employment_status": lead.employment_status,
            "first_time_buyer": lead.first_time_buyer,
            "property_type": lead.property_type,
            "loan_type": lead.loan_type,
            "debt_to_income": float(lead.debt_to_income) if lead.debt_to_income else None,
        }
        for key, val in _lead_map.items():
            if val is not None:
                merged[key] = val
                merged["sources"][key] = "lead_record"

        # Credit range derivation
        if merged.get("credit_score") and not merged.get("credit_range"):
            cs = int(merged["credit_score"])
            if cs >= 740:
                merged["credit_range"] = "Excellent (740+)"
            elif cs >= 700:
                merged["credit_range"] = "Good (700-739)"
            elif cs >= 660:
                merged["credit_range"] = "Fair (660-699)"
            elif cs >= 620:
                merged["credit_range"] = "Below Average (620-659)"
            else:
                merged["credit_range"] = f"Low ({cs})"
            merged["sources"]["credit_range"] = "derived"

        # Timeline from expected_purchase_date
        if not merged.get("timeline") and lead.expected_purchase_date:
            days = (lead.expected_purchase_date - datetime.now(timezone.utc)).days
            if days <= 30:
                merged["timeline"] = "Immediate (< 30 days)"
            elif days <= 90:
                merged["timeline"] = "Short-term (1-3 months)"
            elif days <= 180:
                merged["timeline"] = "Medium-term (3-6 months)"
            else:
                merged["timeline"] = "Long-term (6+ months)"
            merged["sources"]["timeline"] = "derived"

    return merged


# ---------------------------------------------------------------------------
# 4. update_engagement_score
# ---------------------------------------------------------------------------

async def update_engagement_score(
    db: Session,
    lead_id: int,
    event_type: str,
    channel: str,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Increment lead.ai_score based on engagement event.

    Returns the updated score and delta applied.
    """
    # Invalidate context cache on score update (PERF-012)
    if organization_id is not None:
        _context_cache.pop((lead_id, organization_id), None)

    delta = ENGAGEMENT_WEIGHTS.get(event_type, 0)
    if delta == 0:
        logger.warning(f"Unknown engagement event_type '{event_type}' for lead {lead_id}")
        return {"lead_id": lead_id, "delta": 0, "new_score": None, "event_type": event_type}

    try:
        from database.models.lead_loan import Lead

        filters = [Lead.id == lead_id]
        if organization_id is not None:
            filters.append(Lead.organization_id == organization_id)
        lead = db.query(Lead).filter(*filters).first()
        if not lead:
            logger.warning(f"Lead {lead_id} not found for engagement score update")
            return {"lead_id": lead_id, "delta": delta, "new_score": None, "event_type": event_type}

        old_score = lead.ai_score or 0
        lead.ai_score = min(100, old_score + delta)
        db.commit()

        logger.info(
            f"Engagement score for lead {lead_id}: {old_score} -> {lead.ai_score} "
            f"(+{delta} from {event_type}/{channel})"
        )

        return {
            "lead_id": lead_id,
            "delta": delta,
            "old_score": old_score,
            "new_score": lead.ai_score,
            "event_type": event_type,
            "channel": channel,
        }
    except Exception as e:
        logger.exception(f"Failed to update engagement score for lead {lead_id}: {e}")
        db.rollback()
        return {"lead_id": lead_id, "delta": delta, "new_score": None, "error": str(e)}


# ===========================================================================
# PRIVATE HELPERS
# ===========================================================================

def _load_lead(db: Session, lead_id: int, organization_id: int):
    """Load a Lead row with tenant isolation."""
    try:
        from database.models.lead_loan import Lead
        return (
            db.query(Lead)
            .filter(Lead.id == lead_id, Lead.organization_id == organization_id)
            .first()
        )
    except Exception as e:
        logger.exception(f"Error loading lead {lead_id}: {e}")
        return None


# --- Call context -----------------------------------------------------------

def _get_last_call(db: Session, lead_id: int, organization_id: int) -> Optional[Dict]:
    """Most recent call log for this lead."""
    try:
        from database.models.dialer import CallLog
        call = (
            db.query(CallLog)
            .filter(
                CallLog.lead_id == lead_id,
                CallLog.organization_id == organization_id,
            )
            .order_by(desc(CallLog.created_at))
            .first()
        )
        if not call:
            return None

        # Try to pull summary / action items from the Activity or the call itself
        summary = call.ai_note_summary or call.notes
        action_items: List[str] = []
        sentiment: Optional[str] = None

        # Check companion Activity for richer data
        try:
            from database.models.communication import Activity
            from database.enums import ActivityType

            activity = (
                db.query(Activity)
                .filter(
                    Activity.lead_id == lead_id,
                    Activity.organization_id == organization_id,
                    Activity.type == ActivityType.CALL,
                )
                .order_by(desc(Activity.created_at))
                .first()
            )
            if activity:
                sentiment = activity.sentiment
                meta = activity.user_metadata or {}
                action_items = meta.get("action_items", [])
                if not summary and activity.content:
                    summary = activity.content
        except Exception as _exc:  # noqa: BLE001
            pass

        return {
            "date": call.created_at.isoformat() if call.created_at else None,
            "duration": call.duration_seconds,
            "outcome": call.outcome.value if call.outcome else call.disposition,
            "summary": summary,
            "action_items": action_items,
            "sentiment": sentiment,
            "has_recording": bool(call.recording_url),
            "has_transcript": call.transcript_status == "completed",
        }
    except Exception as e:
        logger.exception(f"Error fetching last call for lead {lead_id}: {e}")
        return None


# --- SMS context ------------------------------------------------------------

def _get_sms_context(db: Session, lead_id: int, organization_id: int) -> Optional[Dict]:
    """Latest SMS AI conversation for this lead."""
    try:
        from database.models.sms_conversation import SMSAIConversation
        conv = (
            db.query(SMSAIConversation)
            .filter(
                SMSAIConversation.lead_id == lead_id,
                SMSAIConversation.organization_id == organization_id,
            )
            .order_by(desc(SMSAIConversation.last_message_at))
            .first()
        )
        if not conv:
            # Fall back to legacy SMSConversation
            return _get_legacy_sms_context(db, lead_id, organization_id)

        # Get last message text
        last_message_text = None
        try:
            from database.models.sms_conversation import SMSAIConversationMessage
            last_msg = (
                db.query(SMSAIConversationMessage)
                .filter(SMSAIConversationMessage.conversation_id == conv.id)
                .order_by(desc(SMSAIConversationMessage.created_at))
                .first()
            )
            if last_msg:
                last_message_text = last_msg.content[:200] if last_msg.content else None
        except Exception as _exc:  # noqa: BLE001
            pass

        return {
            "status": conv.status,
            "stage": conv.current_stage,
            "collected_data": conv.context_data or {},
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
            "last_message_text": last_message_text,
            "message_count": conv.message_count or 0,
        }
    except Exception as e:
        logger.exception(f"Error fetching SMS context for lead {lead_id}: {e}")
        return None


def _get_legacy_sms_context(db: Session, lead_id: int, organization_id: int) -> Optional[Dict]:
    """Fall back to the legacy SMSConversation model (Integer PKs)."""
    try:
        from database.models.communication import SMSConversation
        conv = (
            db.query(SMSConversation)
            .filter(
                SMSConversation.lead_id == lead_id,
                SMSConversation.organization_id == organization_id,
            )
            .order_by(desc(SMSConversation.last_message_at))
            .first()
        )
        if not conv:
            return None
        return {
            "status": "active" if conv.is_active else "closed",
            "stage": None,
            "collected_data": conv.context or {},
            "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
            "last_message_text": None,
            "message_count": conv.message_count or 0,
        }
    except Exception as e:
        logger.exception(f"Error fetching legacy SMS context for lead {lead_id}: {e}")
        return None


# --- Email context ----------------------------------------------------------

def _get_email_history(db: Session, lead_id: int, organization_id: int) -> Optional[Dict]:
    """Email send/open/click summary for this lead."""
    try:
        from database.models.communication import EmailMessage

        # PERF-013: Limit to most recent 50 emails to avoid unbounded query
        emails = (
            db.query(EmailMessage)
            .filter(
                EmailMessage.lead_id == lead_id,
                EmailMessage.organization_id == organization_id,
            )
            .order_by(desc(EmailMessage.created_at))
            .limit(50)
            .all()
        )
        if not emails:
            return None

        outbound = [e for e in emails if e.direction == "outbound"]
        last_sent = outbound[0] if outbound else None
        templates_sent = list({e.subject for e in outbound if e.subject})

        # Tracking events (opens/clicks) from EmailTrackingEvent
        total_opens = 0
        total_clicks = 0
        last_opened: Optional[str] = None
        try:
            from database.models.email_tracking import EmailTrackingEvent
            tracking_events = (
                db.query(
                    EmailTrackingEvent.event_type,
                    func.count().label("cnt"),
                    func.max(EmailTrackingEvent.created_at).label("last_at"),
                )
                .filter(EmailTrackingEvent.organization_id == str(organization_id))
                .filter(
                    EmailTrackingEvent.tracking_id.in_(
                        [e.microsoft_message_id for e in outbound if e.microsoft_message_id]
                    )
                )
                .group_by(EmailTrackingEvent.event_type)
                .all()
            )
            for row in tracking_events:
                if row.event_type == "open":
                    total_opens = row.cnt
                    last_opened = row.last_at.isoformat() if row.last_at else None
                elif row.event_type == "click":
                    total_clicks = row.cnt
        except Exception as _exc:  # noqa: BLE001
            logger.debug(f"Could not fetch email tracking events for lead {lead_id}")

        return {
            "total_sent": len(outbound),
            "total_received": len(emails) - len(outbound),
            "total_opens": total_opens,
            "total_clicks": total_clicks,
            "last_sent": last_sent.created_at.isoformat() if last_sent and last_sent.created_at else None,
            "last_subject": last_sent.subject if last_sent else None,
            "last_opened": last_opened,
            "templates_sent": templates_sent[:10],
        }
    except Exception as e:
        logger.exception(f"Error fetching email history for lead {lead_id}: {e}")
        return None


# --- Deal breaker -----------------------------------------------------------

def _get_deal_breaker_result(db: Session, lead_id: int, organization_id: int, *, lead=None) -> Optional[Dict]:
    """Return the last deal-breaker evaluation stored in lead.user_metadata."""
    if lead is None:
        lead = _load_lead(db, lead_id, organization_id)
    if not lead:
        return None
    meta = lead.user_metadata or {}
    return meta.get("deal_breaker_result")


# --- Drip status ------------------------------------------------------------

def _get_drip_status(db: Session, lead_id: int, organization_id: int) -> Dict[str, Any]:
    """Return current drip enrollment status for this lead within their org."""
    try:
        from services.drip_enrollment_service import get_drip_enrollment_service
        svc = get_drip_enrollment_service()
        enrollments = svc.get_active_enrollments(
            db=db, lead_id=str(lead_id), org_id=str(organization_id)
        )
        return {
            "enrolled": bool(enrollments),
            "enrollments": enrollments,  # already dicts from _enrollment_to_dict
        }
    except Exception as e:
        logger.debug(f"Could not fetch drip status for lead {lead_id}: {e}")
        return {"enrolled": False, "enrollments": []}


# --- Appointments -----------------------------------------------------------

def _get_appointments(db: Session, lead_id: int, organization_id: int) -> Dict[str, Any]:
    """Upcoming and recent past appointments for this lead."""
    try:
        from database.models.scheduler import Appointment
        now = datetime.now(timezone.utc)

        upcoming = (
            db.query(Appointment)
            .filter(
                Appointment.lead_id == lead_id,
                Appointment.organization_id == organization_id,
                Appointment.scheduled_start >= now,
                Appointment.status.notin_(["cancelled", "rescheduled"]),
            )
            .order_by(Appointment.scheduled_start)
            .limit(3)
            .all()
        )

        past = (
            db.query(Appointment)
            .filter(
                Appointment.lead_id == lead_id,
                Appointment.organization_id == organization_id,
                Appointment.scheduled_start < now,
            )
            .order_by(desc(Appointment.scheduled_start))
            .limit(3)
            .all()
        )

        def _appt_dict(a) -> Dict:
            return {
                "id": a.id,
                "title": a.title,
                "scheduled_start": a.scheduled_start.isoformat() if a.scheduled_start else None,
                "duration_minutes": a.duration_minutes,
                "status": a.status.value if hasattr(a.status, "value") else str(a.status),
                "meeting_mode": a.meeting_mode.value if hasattr(a.meeting_mode, "value") else str(a.meeting_mode),
            }

        return {
            "upcoming": [_appt_dict(a) for a in upcoming],
            "past": [_appt_dict(a) for a in past],
            "total_upcoming": len(upcoming),
            "total_past": len(past),
        }
    except Exception as e:
        logger.exception(f"Error fetching appointments for lead {lead_id}: {e}")
        # Fall back to CalendarEvent if scheduler.Appointment table doesn't exist
        return _get_calendar_events_fallback(db, lead_id, organization_id)


def _get_calendar_events_fallback(db: Session, lead_id: int, organization_id: int) -> Dict[str, Any]:
    """Fall back to CalendarEvent table."""
    try:
        from database.models.communication import CalendarEvent
        now = datetime.now(timezone.utc)

        upcoming = (
            db.query(CalendarEvent)
            .filter(
                CalendarEvent.lead_id == lead_id,
                CalendarEvent.organization_id == organization_id,
                CalendarEvent.start_time >= now,
                CalendarEvent.status != "cancelled",
            )
            .order_by(CalendarEvent.start_time)
            .limit(3)
            .all()
        )

        past = (
            db.query(CalendarEvent)
            .filter(
                CalendarEvent.lead_id == lead_id,
                CalendarEvent.organization_id == organization_id,
                CalendarEvent.start_time < now,
            )
            .order_by(desc(CalendarEvent.start_time))
            .limit(3)
            .all()
        )

        def _evt_dict(e) -> Dict:
            return {
                "id": e.id,
                "title": e.title,
                "scheduled_start": e.start_time.isoformat() if e.start_time else None,
                "duration_minutes": None,
                "status": e.status,
                "meeting_mode": e.event_type,
            }

        return {
            "upcoming": [_evt_dict(e) for e in upcoming],
            "past": [_evt_dict(e) for e in past],
            "total_upcoming": len(upcoming),
            "total_past": len(past),
        }
    except Exception as e:
        logger.exception(f"Error fetching calendar events for lead {lead_id}: {e}")
        return {"upcoming": [], "past": [], "total_upcoming": 0, "total_past": 0}


# --- Engagement scoring -----------------------------------------------------

def _compute_engagement_score(db: Session, lead_id: int, organization_id: int, *, lead=None) -> int:
    """Return the lead's current ai_score (engagement proxy)."""
    if lead is None:
        lead = _load_lead(db, lead_id, organization_id)
    return lead.ai_score if lead and lead.ai_score is not None else 0


# --- Channel preference -----------------------------------------------------

def _derive_channel_preference(db: Session, lead_id: int, organization_id: int, *, lead=None) -> str:
    """Determine which channel the lead engages with most.

    Checks explicit ChannelPreference first, then falls back to activity
    frequency analysis.
    """
    # 1. Explicit preference on the lead record
    if lead is None:
        lead = _load_lead(db, lead_id, organization_id)
    if lead and lead.preferred_communication:
        return lead.preferred_communication

    # 2. Explicit ChannelPreference row
    try:
        from database.models.communication import ChannelPreference
        pref = (
            db.query(ChannelPreference)
            .filter(
                ChannelPreference.lead_id == lead_id,
                ChannelPreference.organization_id == organization_id,
            )
            .first()
        )
        if pref and pref.preferred_channels:
            channels = pref.preferred_channels
            if isinstance(channels, list) and channels:
                return channels[0]
    except Exception as _exc:  # noqa: BLE001
        pass

    # 3. Infer from activity counts (last 90 days)
    try:
        from database.models.communication import Activity
        from database.enums import ActivityType

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        counts = (
            db.query(Activity.type, func.count().label("cnt"))
            .filter(
                Activity.lead_id == lead_id,
                Activity.organization_id == organization_id,
                Activity.created_at >= cutoff,
            )
            .group_by(Activity.type)
            .all()
        )
        if counts:
            channel_map = {
                ActivityType.CALL: "call",
                ActivityType.SMS: "sms",
                ActivityType.EMAIL: "email",
            }
            best = max(counts, key=lambda r: r.cnt)
            return channel_map.get(best.type, str(best.type))
    except Exception as _exc:  # noqa: BLE001
        pass

    return "unknown"


# --- Utility ----------------------------------------------------------------

def _relative_time(iso_str: Optional[str]) -> str:
    """Convert ISO datetime string to a human-friendly relative time."""
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        if delta.days > 30:
            return f"{delta.days // 30} months ago"
        if delta.days > 0:
            return f"{delta.days} days ago"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours} hours ago"
        minutes = delta.seconds // 60
        return f"{minutes} minutes ago" if minutes > 0 else "just now"
    except Exception as _exc:  # noqa: BLE001
        return str(iso_str)


def _qualification_pct(qual: Dict) -> int:
    """Estimate how complete the qualification profile is."""
    key_fields = [
        "credit_score", "loan_purpose", "loan_amount", "property_value",
        "down_payment", "annual_income", "employment_status", "property_type",
        "loan_type", "timeline",
    ]
    filled = sum(1 for k in key_fields if qual.get(k) is not None)
    return int((filled / len(key_fields)) * 100)


def _missing_fields(qual: Dict) -> List[str]:
    """Return list of key qualification fields still missing."""
    key_fields = [
        "credit_score", "loan_purpose", "loan_amount", "property_value",
        "down_payment", "annual_income", "employment_status", "property_type",
        "loan_type", "timeline",
    ]
    friendly = {
        "credit_score": "credit score",
        "loan_purpose": "loan purpose",
        "loan_amount": "loan amount",
        "property_value": "property value",
        "down_payment": "down payment",
        "annual_income": "annual income",
        "employment_status": "employment status",
        "property_type": "property type",
        "loan_type": "loan type",
        "timeline": "buying timeline",
    }
    return [friendly.get(k, k) for k in key_fields if qual.get(k) is None]
