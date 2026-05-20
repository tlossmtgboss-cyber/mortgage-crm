import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def handle_inbound_sms(
    db: Session,
    phone_number: str,
    message_text: str,
    telnyx_message_id: str,
    organization_id: Optional[int] = None,
    contact_name: Optional[str] = None,
) -> dict:
    from services.sms_ai_responder import classify_message, generate_recommendation
    from services.sms_task_service import assign_task_to_user, create_sms_task
    from services.sms_confidence_engine import should_auto_respond, record_outcome
    from telephony.phone_utils import normalize_phone
    phone_number = normalize_phone(phone_number)

    category, priority = "general", "normal"
    try:
        category, priority = classify_message(message_text)
    except Exception as e:
        logger.exception("Message classification failed for phone=%s: %s", phone_number, e)

    assigned_user_id = None
    lead_id = None
    if organization_id:
        try:
            assigned_user_id = assign_task_to_user(db, phone_number, organization_id)
        except Exception as e:
            logger.exception("Task assignment failed for phone=%s org=%s: %s", phone_number, organization_id, e)

        try:
            lead_row = db.execute(
                text("SELECT id, first_name, last_name FROM leads WHERE phone = :phone AND organization_id = :org_id ORDER BY updated_at DESC LIMIT 1"),
                {"phone": phone_number, "org_id": organization_id},
            ).fetchone()
            if lead_row:
                lead_id = lead_row.id
                if not contact_name:
                    parts = [lead_row.first_name, lead_row.last_name]
                    resolved = " ".join(p for p in parts if p)
                    if resolved:
                        contact_name = resolved
        except Exception as e:
            logger.exception("Lead lookup failed for phone=%s org=%s: %s", phone_number, organization_id, e)

    task = create_sms_task(
        db,
        organization_id=organization_id or 0,
        phone_number=phone_number,
        inbound_message=message_text,
        inbound_message_id=telnyx_message_id,
        contact_name=contact_name,
        lead_id=lead_id,
        assigned_user_id=assigned_user_id,
        category=category,
        priority=priority,
    )
    task_id = task.get("id")

    recommendation = None
    ai_confidence = 0
    try:
        recommendation = generate_recommendation(db, task_id, organization_id or 0)
        ai_confidence = recommendation.get("confidence", 0)
        category = recommendation.get("category", category)
    except Exception as e:
        logger.exception("AI recommendation failed for task=%s: %s", task_id, e)

    # Check if this phone has an active conversation (recent messages within 30 min)
    is_active_conversation = False
    try:
        recent = db.execute(
            text("""
                SELECT COUNT(*) AS cnt FROM sms_panel_messages
                WHERE phone = :phone AND organization_id = :oid
                  AND created_at > NOW() - INTERVAL '30 minutes'
            """),
            {"phone": phone_number, "oid": organization_id or 0},
        ).scalar()
        is_active_conversation = (recent or 0) > 0
    except Exception as e:
        logger.warning("Active conversation check failed: %s", e)

    auto_responded = False
    if organization_id and recommendation and recommendation.get("recommendation"):
        try:
            # Auto-respond if: confidence engine says yes OR this is an active conversation
            should_auto = should_auto_respond(db, organization_id, category, user_id=assigned_user_id)
            if should_auto or is_active_conversation:
                send_result = _send_response(
                    to_phone=phone_number,
                    message=recommendation["recommendation"],
                    organization_id=organization_id,
                    user_id=assigned_user_id,
                    lead_id=lead_id,
                )
                if send_result.get("status") == "sent":
                    now = datetime.now(timezone.utc)
                    db.execute(
                        text("""
                            UPDATE sms_tasks
                            SET status = 'auto_responded',
                                response_text = :response,
                                response_source = 'ai_auto',
                                response_sent_at = :now,
                                updated_at = :now
                            WHERE id = :tid
                        """),
                        {
                            "response": recommendation["recommendation"],
                            "now": now,
                            "tid": task_id,
                        },
                    )
                    auto_responded = True

                    try:
                        record_outcome(db, organization_id, assigned_user_id, category, "accepted")
                    except Exception as e:
                        logger.warning("Confidence recording failed for task=%s: %s", task_id, e)

                    _store_panel_message(
                        db,
                        phone=phone_number,
                        message=recommendation["recommendation"],
                        org_id=organization_id,
                        user_id=assigned_user_id,
                        telnyx_msg_id=send_result.get("id"),
                    )
                else:
                    db.execute(
                        text("UPDATE sms_tasks SET status = 'pending', updated_at = :now WHERE id = :tid"),
                        {"now": datetime.now(timezone.utc), "tid": task_id},
                    )
        except Exception as e:
            logger.exception("Auto-respond failed for task=%s: %s", task_id, e)

    # Try to extract name/email from conversation and create a lead
    if organization_id and not lead_id and auto_responded:
        try:
            _try_create_lead_from_conversation(db, phone_number, organization_id, assigned_user_id)
        except Exception as e:
            logger.warning("Lead extraction failed for phone=%s: %s", phone_number, e)

    # Check if conversation has reached a scheduling decision
    if organization_id and auto_responded and is_active_conversation:
        try:
            from services.sms_ai_responder import extract_conversation_intent
            intent = extract_conversation_intent(db, phone_number, organization_id)
            if intent.get("action") == "schedule" and intent.get("time_description"):
                _schedule_appointment_from_sms(
                    db, phone_number, organization_id, assigned_user_id,
                    contact_name=intent.get("name") or contact_name,
                    time_description=intent["time_description"],
                    lead_id=lead_id,
                )
            elif intent.get("action") == "call_now":
                _notify_immediate_callback(
                    db, phone_number, organization_id, assigned_user_id,
                    contact_name=intent.get("name") or contact_name,
                    lead_id=lead_id,
                )
        except Exception as e:
            logger.warning("Scheduling intent handling failed for phone=%s: %s", phone_number, e)

    db.commit()

    if not auto_responded and assigned_user_id:
        try:
            from services.push_notification_service import PushNotificationService
            push_svc = PushNotificationService()
            display_name = contact_name or phone_number
            preview = message_text[:80] + ("..." if len(message_text) > 80 else "")
            push_svc.send_to_user(
                db,
                user_id=assigned_user_id,
                title="",
                body="",
                notification_type="sms_escalation",
                template_data={"contact_name": display_name, "reason": preview},
                extra_data={"task_id": task_id, "phone": phone_number, "lead_id": lead_id},
            )
        except Exception as e:
            logger.warning("Push notification failed for escalation task=%s: %s", task_id, e)

    return {
        "task_id": task_id,
        "status": "auto_responded" if auto_responded else "pending",
        "auto_responded": auto_responded,
        "ai_confidence": ai_confidence,
        "category": category,
    }


def process_user_response(
    db: Session,
    task_id: int,
    organization_id: int,
    user_id: int,
    response_text: str,
    response_source: str,
) -> dict:
    from services.sms_task_service import respond_to_task
    from services.sms_confidence_engine import record_outcome

    task = respond_to_task(
        db,
        task_id=task_id,
        organization_id=organization_id,
        user_id=user_id,
        response_text=response_text,
        response_source=response_source,
    )

    phone_number = task.get("phone_number", "")
    lead_id = task.get("lead_id")
    category = task.get("category", "general")

    message_sent = False
    send_result = _send_response(
        to_phone=phone_number,
        message=response_text,
        organization_id=organization_id,
        user_id=user_id,
        lead_id=lead_id,
    )
    if send_result.get("status") == "sent":
        message_sent = True

    confidence_updated = False
    try:
        outcome = "accepted" if response_source in ("ai_accepted", "ai_suggested", "ai", "auto") else "edited" if response_source == "ai_edited" else "rejected"
        record_outcome(db, organization_id, user_id, category, outcome)
        confidence_updated = True
    except Exception as e:
        logger.warning("Confidence recording failed for task=%s: %s", task_id, e)

    try:
        now = datetime.now(timezone.utc)
        # User-edited responses are the best training signal — they show
        # what the LO actually wants. Rate them high so they're used as
        # patterns for future recommendations.
        rate_map = {
            "ai_accepted": 1.0,
            "ai_suggested": 1.0,
            "ai": 1.0,
            "auto": 1.0,
            "ai_edited": 0.85,
            "manual": 0.75,
        }
        rate = rate_map.get(response_source, 0.75)
        db.execute(
            text("""
                INSERT INTO sms_response_patterns
                    (organization_id, category, response_template, success_rate, times_used, created_at, updated_at)
                VALUES
                    (:org_id, :category, :template, :rate, 1, :now, :now)
                ON CONFLICT (organization_id, category, md5(response_template))
                DO UPDATE SET
                    times_used = sms_response_patterns.times_used + 1,
                    success_rate = GREATEST(sms_response_patterns.success_rate, EXCLUDED.success_rate),
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "org_id": organization_id,
                "category": category,
                "template": response_text[:500],
                "rate": rate,
                "now": now,
            },
        )
    except Exception as e:
        logger.warning("Pattern recording failed for task=%s: %s", task_id, e)

    _store_panel_message(
        db,
        phone=phone_number,
        message=response_text,
        org_id=organization_id,
        user_id=user_id,
        telnyx_msg_id=send_result.get("id"),
    )

    try:
        now = datetime.now(timezone.utc)
        db.execute(
            text("""
                INSERT INTO sms_ai_audit_log
                    (organization_id, task_id, action, details, user_id, created_at)
                VALUES
                    (:org_id, :tid, :action, :details, :uid, :now)
            """),
            {
                "org_id": organization_id,
                "tid": task_id,
                "action": "user_response",
                "details": json.dumps({
                    "response_source": response_source,
                    "message_sent": message_sent,
                    "category": category,
                }),
                "uid": user_id,
                "now": now,
            },
        )
    except Exception as e:
        logger.warning("Audit log write failed for task=%s: %s", task_id, e)

    db.commit()

    return {
        "task_id": task_id,
        "message_sent": message_sent,
        "confidence_updated": confidence_updated,
    }


def _send_response(
    to_phone: str,
    message: str,
    organization_id: Optional[int] = None,
    user_id: Optional[int] = None,
    lead_id: Optional[int] = None,
) -> dict:
    from telephony.phone_utils import normalize_phone
    to_phone = normalize_phone(to_phone)

    try:
        from telephony.sms import send_sms_verified
        return send_sms_verified(
            to=to_phone,
            text=message,
            organization_id=organization_id,
            user_id=user_id,
            lead_id=lead_id,
        )
    except Exception as e:
        logger.exception("SMS send failed to=%s: %s", to_phone, e)

        # Queue for retry on transient transmission errors
        try:
            from db import SessionLocal
            _retry_db = SessionLocal()
            try:
                from integrations.sms_retry_queue import enqueue_sms
                queue_id = enqueue_sms(
                    _retry_db,
                    to_phone=to_phone,
                    message_body=message,
                    lead_id=lead_id,
                    user_id=user_id,
                )
                if queue_id:
                    logger.info("Auto-responder SMS queued for retry (id=%s) to=%s", queue_id, to_phone)
            finally:
                _retry_db.close()
        except Exception as q_err:
            logger.warning("Failed to enqueue auto-responder SMS for retry: %s", q_err)

        return {"id": None, "status": "failed", "error": str(e)}


def _store_panel_message(
    db: Session,
    phone: str,
    message: str,
    org_id: Optional[int],
    user_id: Optional[int] = None,
    telnyx_msg_id: Optional[str] = None,
    sender_name: str = "Aria",
) -> None:
    try:
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        db.execute(
            text("""
                INSERT INTO sms_panel_messages
                    (id, phone, organization_id, direction, body,
                     sender_name, sender_user_id, status,
                     telnyx_message_id, created_at)
                VALUES
                    (:id, :phone, :org_id, 'outbound', :body,
                     :sender_name, :sender_user_id, 'sent',
                     :telnyx_id, :now)
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": msg_id,
                "phone": phone,
                "org_id": org_id,
                "body": message[:2000],
                "sender_name": sender_name,
                "sender_user_id": user_id,
                "telnyx_id": telnyx_msg_id,
                "now": now,
            },
        )
        db.flush()
    except Exception as e:
        logger.warning("Failed to store panel message for phone=%s: %s", phone, e)


def _try_create_lead_from_conversation(
    db: Session,
    phone_number: str,
    organization_id: int,
    assigned_user_id: Optional[int] = None,
) -> None:
    """Extract name/email from SMS conversation and create a lead if enough info is gathered."""
    import re

    # Already have a lead for this phone? Skip.
    existing = db.execute(
        text("SELECT id FROM leads WHERE phone = :phone AND organization_id = :oid LIMIT 1"),
        {"phone": phone_number, "oid": organization_id},
    ).fetchone()
    if existing:
        return

    # Pull recent inbound messages from this phone
    messages = db.execute(
        text("""
            SELECT direction, body FROM sms_panel_messages
            WHERE phone = :phone AND organization_id = :oid
            ORDER BY created_at ASC LIMIT 20
        """),
        {"phone": phone_number, "oid": organization_id},
    ).mappings().all()

    if not messages:
        return

    inbound_text = " ".join(m["body"] for m in messages if m["direction"] == "inbound" and m["body"])

    # Extract email
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', inbound_text)
    email = email_match.group(0) if email_match else None

    # Extract name — use LLM for accuracy
    name = None
    try:
        from services.llm_gateway import llm_gateway
        extract_result = llm_gateway.complete_sync(
            intent="calls",
            system_prompt="Extract the person's full name from this SMS conversation. Reply with ONLY the name, nothing else. If no name is found, reply with NONE.",
            messages=[{"role": "user", "content": inbound_text[:500]}],
            max_tokens_override=50,
            temperature_override=0.0,
        )
        extracted = extract_result.text.strip()
        if extracted and extracted.upper() != "NONE" and len(extracted) < 60:
            name = extracted
    except Exception as e:
        logger.warning("Name extraction LLM call failed: %s", e)

    if not name:
        return

    # Split name
    parts = name.split(None, 1)
    first_name = parts[0] if parts else name
    last_name = parts[1] if len(parts) > 1 else ""

    now = datetime.now(timezone.utc)
    try:
        db.execute(
            text("""
                INSERT INTO leads (
                    organization_id, first_name, last_name, email, phone,
                    source, stage, assigned_user_id, created_at, updated_at
                ) VALUES (
                    :oid, :first, :last, :email, :phone,
                    'SMS Conversation', 'New', :uid, :now, :now
                )
            """),
            {
                "oid": organization_id,
                "first": first_name,
                "last": last_name,
                "email": email,
                "phone": phone_number,
                "uid": assigned_user_id,
                "now": now,
            },
        )
        db.flush()
        logger.info(
            "[SMS Lead] Created lead from conversation: %s %s (%s) phone=%s org=%s",
            first_name, last_name, email or "no email", phone_number, organization_id,
        )
    except Exception as e:
        logger.warning("Failed to create lead from SMS conversation: %s", e)


def _schedule_appointment_from_sms(
    db: Session,
    phone_number: str,
    organization_id: int,
    assigned_user_id: Optional[int],
    contact_name: Optional[str] = None,
    time_description: Optional[str] = None,
    lead_id: Optional[int] = None,
) -> None:
    """Parse a natural-language time and create a calendar appointment."""
    from dateutil import parser as dateutil_parser
    import pytz

    if not time_description or not assigned_user_id:
        return

    # Resolve lead_id if we don't have one
    if not lead_id:
        row = db.execute(
            text("SELECT id FROM leads WHERE phone = :phone AND organization_id = :oid LIMIT 1"),
            {"phone": phone_number, "oid": organization_id},
        ).fetchone()
        if row:
            lead_id = row.id

    # Use LLM to parse the natural-language time into an ISO datetime
    eastern = pytz.timezone("America/New_York")
    now_eastern = datetime.now(eastern)
    try:
        from services.llm_gateway import llm_gateway
        parse_result = llm_gateway.complete_sync(
            intent="calls",
            system_prompt=(
                "Convert this scheduling text to an ISO 8601 datetime. "
                f"The current date/time is {now_eastern.strftime('%Y-%m-%d %H:%M %A')} Eastern. "
                "Reply with ONLY the datetime in format YYYY-MM-DDTHH:MM:00, nothing else. "
                "If the time is ambiguous (e.g. 'morning'), pick a reasonable default (10:00 AM for morning, 2:00 PM for afternoon). "
                "If you truly cannot determine a date/time, reply with NONE."
            ),
            messages=[{"role": "user", "content": time_description}],
            max_tokens_override=30,
            temperature_override=0.0,
        )
        raw = parse_result.text.strip()
        if not raw or raw.upper() == "NONE":
            logger.info("[SMS Schedule] Could not parse time: %r", time_description)
            return
        scheduled_start = dateutil_parser.isoparse(raw)
    except Exception as e:
        logger.warning("[SMS Schedule] Time parsing failed for %r: %s", time_description, e)
        return

    # Make timezone-aware in Eastern, then convert to UTC for storage
    if scheduled_start.tzinfo is None:
        scheduled_start = eastern.localize(scheduled_start)
    scheduled_start_utc = scheduled_start.astimezone(pytz.utc)
    scheduled_end_utc = scheduled_start_utc + __import__("datetime").timedelta(minutes=15)

    # Don't schedule in the past
    if scheduled_start_utc < datetime.now(timezone.utc):
        logger.info("[SMS Schedule] Parsed time is in the past: %s", scheduled_start_utc)
        return

    # Check for duplicate — don't double-book same phone+time
    dup = db.execute(
        text("""
            SELECT id FROM scheduler_appointments
            WHERE organization_id = :oid AND attendee_phone = :phone
              AND scheduled_start = :start AND status NOT IN ('cancelled', 'no_show')
            LIMIT 1
        """),
        {"oid": organization_id, "phone": phone_number, "start": scheduled_start_utc.replace(tzinfo=None)},
    ).fetchone()
    if dup:
        logger.info("[SMS Schedule] Duplicate appointment exists for phone=%s at %s", phone_number, scheduled_start_utc)
        return

    now = datetime.now(timezone.utc)
    display_name = contact_name or phone_number
    try:
        db.execute(
            text("""
                INSERT INTO scheduler_appointments (
                    organization_id, assigned_user_id, lead_id,
                    title, description, meeting_type, meeting_mode,
                    scheduled_start, scheduled_end, duration_minutes,
                    timezone, attendee_name, attendee_phone,
                    status, status_changed_at, booked_by_ai,
                    ai_booking_context, external_source,
                    created_at, updated_at
                ) VALUES (
                    :oid, :uid, :lid,
                    :title, :desc, 'consultation', 'phone',
                    :start, :end, 15,
                    'America/New_York', :name, :phone,
                    'booked', :now, true,
                    :context, 'sms_auto_responder',
                    :now, :now
                )
            """),
            {
                "oid": organization_id,
                "uid": assigned_user_id,
                "lid": lead_id,
                "title": f"Call with {display_name}",
                "desc": f"Scheduled via SMS conversation. Borrower requested: {time_description}",
                "start": scheduled_start_utc.replace(tzinfo=None),
                "end": scheduled_end_utc.replace(tzinfo=None),
                "name": display_name,
                "phone": phone_number,
                "now": now,
                "context": json.dumps({"source": "sms_intake", "time_description": time_description}),
            },
        )
        db.flush()
        logger.info(
            "[SMS Schedule] Appointment created for %s at %s (org=%s)",
            display_name, scheduled_start_utc.isoformat(), organization_id,
        )
    except Exception as e:
        logger.warning("[SMS Schedule] Failed to create appointment: %s", e)
        return

    # Notify the LO about the new appointment
    try:
        from services.push_notification_service import PushNotificationService
        push_svc = PushNotificationService()
        time_str = scheduled_start.strftime("%-I:%M %p on %b %-d")
        push_svc.send_to_user(
            db,
            user_id=assigned_user_id,
            title=f"New Call Scheduled — {display_name}",
            body=f"Aria booked a call for {time_str} via SMS",
            notification_type="appointment_booked",
            extra_data={"phone": phone_number, "lead_id": lead_id},
        )
    except Exception as e:
        logger.warning("[SMS Schedule] Push notification failed: %s", e)


def _notify_immediate_callback(
    db: Session,
    phone_number: str,
    organization_id: int,
    assigned_user_id: Optional[int],
    contact_name: Optional[str] = None,
    lead_id: Optional[int] = None,
) -> None:
    """Send a high-priority push notification telling the LO to call this person now."""
    if not assigned_user_id:
        return

    display_name = contact_name or phone_number
    try:
        from services.push_notification_service import PushNotificationService
        push_svc = PushNotificationService()
        push_svc.send_to_user(
            db,
            user_id=assigned_user_id,
            title=f"Call Now — {display_name}",
            body=f"{display_name} is requesting a call right now",
            notification_type="sms_callback_request",
            extra_data={
                "phone": phone_number,
                "lead_id": lead_id,
                "action": "call_now",
                "priority": "urgent",
            },
        )
        logger.info(
            "[SMS Callback] Sent urgent callback notification for %s to user=%s org=%s",
            phone_number, assigned_user_id, organization_id,
        )
    except Exception as e:
        logger.warning("[SMS Callback] Push notification failed for phone=%s: %s", phone_number, e)
