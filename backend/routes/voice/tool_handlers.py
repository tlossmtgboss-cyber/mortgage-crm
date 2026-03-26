"""
Voice Routes - Tool Handlers

Contains:
- VoiceToolRateLimiter: Per-session rate limiter for voice CRM tool calls
- handle_browser_function_call: Browser voice AI CRM tool execution
- handle_ai_function_call: Telnyx AI receptionist tool execution
"""
import os
import logging
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import text

from .utils import mask_phone, logger as _utils_logger

logger = logging.getLogger(__name__)


# =============================================================================
# VOICE TOOL RATE LIMITER
# =============================================================================

class VoiceToolRateLimiter:
    """Per-session rate limiter for voice CRM tool calls via the OpenAI Realtime WebSocket.

    NOTE: In-memory rate limiter — does not persist across worker restarts.
    For production multi-worker deployment, migrate to Redis-backed rate limiting.
    """

    def __init__(self):
        self._calls: Dict[str, List[float]] = defaultdict(list)
        # (max_calls, window_seconds) per tool
        self._limits = {
            "send_sms": (3, 60),                  # 3 SMS per 60 seconds
            "send_email": (5, 60),                # 5 emails per 60 seconds
            "schedule_appointment": (5, 60),       # 5 bookings per 60 seconds
            "create_task": (10, 60),               # 10 tasks per 60 seconds
            "complete_task": (10, 60),             # 10 task completions per 60 seconds
            "start_scheduling_workflow": (2, 300),  # 2 workflows per 5 minutes
            "search_contact": (20, 60),            # 20 searches per 60 seconds
            "get_my_availability": (10, 60),       # 10 availability checks per 60 seconds
            "get_pipeline_summary": (5, 60),       # 5 pipeline queries per 60 seconds
            "get_recent_call_summary": (10, 60),   # 10 call summary queries per 60 seconds
            "get_call_artifacts": (10, 60),        # 10 artifact queries per 60 seconds
            "approve_artifact": (10, 60),          # 10 approvals per 60 seconds
            "execute_artifacts": (3, 60),          # 3 executions per 60 seconds
            "start_call_recording": (3, 60),       # 3 recording starts per 60 seconds
            "stop_call_recording": (3, 60),        # 3 recording stops per 60 seconds
            "send_document_checklist": (3, 60),    # 3 checklist sends per 60 seconds
        }
        self._default_limit = (30, 60)  # default: 30 calls per 60 seconds

    def check(self, session_id: str, tool_name: str) -> bool:
        """Returns True if the call is allowed, False if rate limited."""
        key = f"{session_id}:{tool_name}"
        now = time.time()
        max_calls, window = self._limits.get(tool_name, self._default_limit)

        # Prune entries outside the window
        self._calls[key] = [t for t in self._calls[key] if now - t < window]

        if len(self._calls[key]) >= max_calls:
            return False

        self._calls[key].append(now)
        return True


_voice_rate_limiter = VoiceToolRateLimiter()


# =============================================================================
# AI RECEPTIONIST FUNCTION CALL HANDLER (Telnyx inbound calls)
# =============================================================================

async def handle_ai_function_call(func_name: str, args: dict, call_context: dict, db) -> dict:
    """
    Handle function calls from the AI receptionist.
    Returns the result to send back to OpenAI.
    """
    caller_name = call_context.get('caller_name') or call_context.get('lead_data', {}).get('name') or 'Unknown'
    caller_phone = call_context.get('caller_number') or 'Unknown'

    if func_name == "schedule_appointment":
        # Schedule an appointment and save to database
        date_str = args.get('date', '')
        time_str = args.get('time', '')
        reason = args.get('reason', 'Mortgage consultation')

        try:
            # Parse the date and time
            if date_str and time_str:
                appointment_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            else:
                # Default to tomorrow at 10 AM if not specified
                appointment_datetime = datetime.now() + timedelta(days=1)
                appointment_datetime = appointment_datetime.replace(hour=10, minute=0, second=0)

            # Save to appointments table
            db.execute(text("""
                INSERT INTO appointments (
                    id, caller_name, caller_phone, appointment_datetime,
                    reason, status, created_at, call_sid, notes
                ) VALUES (
                    gen_random_uuid(), :caller_name, :caller_phone, :appointment_datetime,
                    :reason, 'scheduled', NOW(), :call_sid, :notes
                )
            """), {
                "caller_name": caller_name,
                "caller_phone": caller_phone,
                "appointment_datetime": appointment_datetime,
                "reason": reason,
                "call_sid": call_context.get('call_sid'),
                "notes": f"Scheduled via AI receptionist. Context: {json.dumps(call_context.get('lead_data', {}))}"
            })
            db.commit()

            formatted_time = appointment_datetime.strftime("%A, %B %d at %I:%M %p")
            logger.info(f"Appointment scheduled on {formatted_time}")

            return {
                "success": True,
                "message": f"Appointment scheduled for {formatted_time}",
                "appointment_time": formatted_time,
                "caller_name": caller_name
            }

        except Exception as e:
            logger.error(f"Failed to schedule appointment: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Sorry, I couldn't save the appointment. Please try again."
            }

    elif func_name == "transfer_to_loan_officer":
        # Log the transfer request
        reason = args.get('reason', '')
        urgency = args.get('urgency', 'medium')

        try:
            db.execute(text("""
                INSERT INTO call_transfers (
                    id, caller_name, caller_phone, transfer_reason,
                    urgency, status, created_at, call_sid
                ) VALUES (
                    gen_random_uuid(), :caller_name, :caller_phone, :reason,
                    :urgency, 'requested', NOW(), :call_sid
                )
            """), {
                "caller_name": caller_name,
                "caller_phone": caller_phone,
                "reason": reason,
                "urgency": urgency,
                "call_sid": call_context.get('call_sid')
            })
            db.commit()

            logger.info(f"Transfer requested - {reason} ({urgency})")

            return {
                "success": True,
                "message": "I'll transfer you to a loan officer now.",
                "transfer_initiated": True
            }

        except Exception as e:
            logger.error(f"Failed to log transfer: {e}")
            db.rollback()
            return {
                "success": True,  # Still transfer even if logging fails
                "message": "Transferring you now."
            }

    elif func_name == "take_message":
        # Save the message
        name = args.get('name', caller_name)
        phone = args.get('phone', caller_phone)
        message = args.get('message', '')
        callback_urgency = args.get('callback_urgency', 'today')

        try:
            db.execute(text("""
                INSERT INTO voice_messages (
                    id, caller_name, caller_phone, message,
                    callback_urgency, status, created_at, call_sid
                ) VALUES (
                    gen_random_uuid(), :caller_name, :caller_phone, :message,
                    :callback_urgency, 'new', NOW(), :call_sid
                )
            """), {
                "caller_name": name,
                "caller_phone": phone,
                "message": message,
                "callback_urgency": callback_urgency,
                "call_sid": call_context.get('call_sid')
            })
            db.commit()

            logger.info(f"Message saved: {name} - {message[:50]}...")

            return {
                "success": True,
                "message": f"Got it! I've saved your message and someone will call you back {callback_urgency}.",
                "callback_urgency": callback_urgency
            }

        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "I'm sorry, I had trouble saving your message. Could you repeat that?"
            }

    else:
        logger.warning(f"Unknown function called: {func_name}")
        return {
            "success": False,
            "message": "I'm not sure how to help with that. Let me connect you with someone who can."
        }


# =============================================================================
# BROWSER VOICE FUNCTION CALL HANDLER
# =============================================================================

async def handle_browser_function_call(
    func_name: str, args: dict, db, session_id: str = "anonymous",
    organization_id: str = None, user_id: int = None
) -> dict:
    """
    Handle CRM function calls from the browser voice AI agent.
    Unlike handle_ai_function_call (which handles inbound phone calls),
    this handles tools used by the LO speaking to their AI assistant in the browser.

    CRIT-2: All DB queries are scoped to organization_id when available.
    """

    # Rate limit check before executing any tool
    if not _voice_rate_limiter.check(session_id, func_name):
        logger.warning(
            "Voice tool rate limited",
            extra={"session_id": session_id, "tool": func_name}
        )
        return {"success": False, "error": f"Rate limited: too many {func_name} calls. Please wait.", "message": f"Rate limited: too many {func_name} calls. Please wait."}

    logger.info(f"Browser function call: {func_name}({args})", extra={"user_id": user_id, "org_id": organization_id})

    if func_name == "search_contact":
        name_query = args.get("name", "").strip()
        if not name_query:
            return {"success": False, "message": "Please provide a name to search for."}

        try:
            # CRIT-2: Tenant-scoped lead search
            org_filter = "AND organization_id = :org_id" if organization_id else ""
            query_params = {"pattern": f"%{name_query}%"}
            if organization_id:
                query_params["org_id"] = organization_id
            results = db.execute(text(f"""
                SELECT id, first_name, last_name, name, phone, email, stage, source
                FROM leads
                WHERE (
                    LOWER(COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')) LIKE LOWER(:pattern)
                    OR LOWER(COALESCE(name, '')) LIKE LOWER(:pattern)
                    OR LOWER(COALESCE(first_name, '')) LIKE LOWER(:pattern)
                    OR LOWER(COALESCE(last_name, '')) LIKE LOWER(:pattern)
                )
                {org_filter}
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 5
            """), query_params).fetchall()

            if not results:
                return {"success": True, "message": f"No contacts found matching '{name_query}'.", "contacts": []}

            contacts = []
            for row in results:
                contact_name = f"{row.first_name or ''} {row.last_name or ''}".strip() or row.name or "Unknown"
                contacts.append({
                    "id": str(row.id),
                    "name": contact_name,
                    "phone": row.phone or "",
                    "email": row.email or "",
                    "stage": row.stage or "",
                    "source": row.source or ""
                })

            return {
                "success": True,
                "message": f"Found {len(contacts)} contact(s) matching '{name_query}'.",
                "contacts": contacts
            }

        except Exception as e:
            logger.error(f"Error searching contacts: {e}")
            db.rollback()
            return {"success": False, "message": f"Error searching contacts: {str(e)}"}

    elif func_name == "send_sms":
        phone_number = args.get("phone_number", "")
        message_text = args.get("message", "")
        contact_name = args.get("contact_name", "Unknown")

        if not phone_number or not message_text:
            return {"success": False, "message": "Phone number and message are required to send SMS."}

        try:
            from telephony.sms import send_sms as telnyx_send_sms

            telnyx_api_key = os.getenv("TELNYX_API_KEY")
            telnyx_from_number = os.getenv("TELNYX_FROM_NUMBER", os.getenv("TELNYX_PHONE_NUMBER", ""))
            messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

            if not telnyx_api_key or not telnyx_from_number:
                return {"success": False, "message": "SMS not configured. Missing Telnyx credentials."}

            telnyx_send_sms(
                to=phone_number,
                from_=telnyx_from_number,
                text=message_text,
                messaging_profile_id=messaging_profile_id or None,
                api_key=telnyx_api_key,
            )

            logger.info(f"SMS sent to {mask_phone(phone_number)} ({contact_name})")

            return {
                "success": True,
                "message": f"SMS sent to {contact_name} at {phone_number}."
            }

        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            return {"success": False, "message": f"Failed to send SMS: {str(e)}"}

    elif func_name == "get_my_availability":
        days_ahead = args.get("days_ahead", 5)
        duration_minutes = args.get("duration_minutes", 30)

        try:
            # Generate available slots based on business hours (9 AM - 5 PM, weekdays)
            from datetime import date as date_type
            slots = []
            today = datetime.now()

            for day_offset in range(1, days_ahead + 1):
                check_date = today + timedelta(days=day_offset)
                # Skip weekends
                if check_date.weekday() >= 5:
                    continue

                date_str = check_date.strftime("%Y-%m-%d")
                day_name = check_date.strftime("%A")

                # CRIT-2: Tenant-scoped appointment lookup
                appt_params = {"check_date": date_str}
                appt_org_filter = ""
                if organization_id:
                    appt_org_filter = "AND organization_id = :org_id"
                    appt_params["org_id"] = organization_id
                existing = db.execute(text(f"""
                    SELECT appointment_datetime
                    FROM appointments
                    WHERE DATE(appointment_datetime) = :check_date
                        AND status != 'cancelled'
                        {appt_org_filter}
                    ORDER BY appointment_datetime
                """), appt_params).fetchall()

                booked_hours = {row.appointment_datetime.hour for row in existing} if existing else set()

                # Generate available hour slots (9 AM to 5 PM)
                day_slots = []
                for hour in range(9, 17):
                    if hour not in booked_hours:
                        day_slots.append(f"{hour:02d}:00")

                if day_slots:
                    slots.append({
                        "date": date_str,
                        "day": day_name,
                        "available_times": day_slots
                    })

            return {
                "success": True,
                "message": f"Found availability for the next {days_ahead} days.",
                "slots": slots
            }

        except Exception as e:
            logger.error(f"Error getting availability: {e}")
            db.rollback()
            return {"success": False, "message": f"Error checking availability: {str(e)}"}

    elif func_name == "schedule_appointment":
        contact_name = args.get("contact_name", "")
        contact_email = args.get("contact_email", "")
        contact_phone = args.get("contact_phone", "")
        date_str = args.get("date", "")
        time_str = args.get("time", "")
        duration = args.get("duration_minutes", 30)
        meeting_type = args.get("meeting_type", "discovery_call")
        reason = args.get("reason", meeting_type.replace("_", " ").title())

        if not contact_name or not date_str or not time_str:
            return {"success": False, "message": "Contact name, date, and time are required."}

        try:
            appointment_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

            # CRIT-2: Include organization_id for tenant scoping
            db.execute(text("""
                INSERT INTO appointments (
                    id, caller_name, caller_phone, appointment_datetime,
                    reason, status, created_at, notes, organization_id
                ) VALUES (
                    gen_random_uuid(), :contact_name, :contact_phone, :appointment_datetime,
                    :reason, 'scheduled', NOW(), :notes, :org_id
                )
            """), {
                "contact_name": contact_name,
                "contact_phone": contact_phone,
                "appointment_datetime": appointment_datetime,
                "reason": reason,
                "notes": f"Type: {meeting_type}. Email: {contact_email}. Scheduled via browser voice assistant.",
                "org_id": organization_id,
            })
            db.commit()

            formatted_time = appointment_datetime.strftime("%A, %B %d at %I:%M %p")
            logger.info(f"Appointment scheduled: {contact_name} on {formatted_time}")

            return {
                "success": True,
                "message": f"Appointment with {contact_name} scheduled for {formatted_time}.",
                "appointment_time": formatted_time,
                "contact_name": contact_name
            }

        except Exception as e:
            logger.error(f"Failed to schedule appointment: {e}")
            db.rollback()
            return {"success": False, "message": f"Failed to schedule appointment: {str(e)}"}

    elif func_name == "create_task":
        title = args.get("title", "")
        description = args.get("description", "")
        due_date_str = args.get("due_date", "")
        priority = args.get("priority", "medium")

        if not title:
            return {"success": False, "message": "Task title is required."}

        try:
            due_date = None
            if due_date_str:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d")

            # CRIT-2: Include organization_id for tenant scoping
            db.execute(text("""
                INSERT INTO tasks (
                    id, title, description, due_date, priority,
                    status, created_at, organization_id
                ) VALUES (
                    gen_random_uuid(), :title, :description, :due_date, :priority,
                    'pending', NOW(), :org_id
                )
            """), {
                "title": title,
                "description": description or "Created via voice assistant",
                "due_date": due_date,
                "priority": priority,
                "org_id": organization_id,
            })
            db.commit()

            due_info = f" (due {due_date_str})" if due_date_str else ""
            logger.info(f"Task created: {title}{due_info}")

            return {
                "success": True,
                "message": f"Task created: '{title}'{due_info} with {priority} priority."
            }

        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            db.rollback()
            return {"success": False, "message": f"Failed to create task: {str(e)}"}

    elif func_name == "start_scheduling_workflow":
        contact_name = args.get("contact_name", "")
        contact_phone = args.get("contact_phone", "")
        meeting_type = args.get("meeting_type", "discovery_call")
        message_context = args.get("message_context", "")

        if not contact_name or not contact_phone:
            return {"success": False, "message": "Contact name and phone number are required."}

        try:
            # Get next 3 available slots to include in the SMS
            today = datetime.now()
            available_slots = []
            for day_offset in range(1, 8):
                check_date = today + timedelta(days=day_offset)
                if check_date.weekday() >= 5:
                    continue
                date_str = check_date.strftime("%Y-%m-%d")

                # CRIT-2: Tenant-scoped appointment lookup
                sched_params = {"check_date": date_str}
                sched_org_filter = ""
                if organization_id:
                    sched_org_filter = "AND organization_id = :org_id"
                    sched_params["org_id"] = organization_id
                existing = db.execute(text(f"""
                    SELECT appointment_datetime
                    FROM appointments
                    WHERE DATE(appointment_datetime) = :check_date
                        AND status != 'cancelled'
                        {sched_org_filter}
                """), sched_params).fetchall()

                booked_hours = {row.appointment_datetime.hour for row in existing} if existing else set()

                for hour in [10, 14, 11, 15, 9, 13, 16]:
                    if hour not in booked_hours and len(available_slots) < 3:
                        slot_dt = check_date.replace(hour=hour, minute=0, second=0)
                        available_slots.append(slot_dt.strftime("%A %m/%d at %I:%M %p"))

                if len(available_slots) >= 3:
                    break

            # Build the SMS message
            context_part = f" to {message_context}" if message_context else ""
            slots_text = "\n".join(f"  {i+1}. {slot}" for i, slot in enumerate(available_slots))
            sms_text = (
                f"Hi {contact_name}, this is from your loan officer's office. "
                f"We'd like to schedule a quick call{context_part}. "
                f"Here are some available times:\n{slots_text}\n"
                f"Reply with a number or suggest another time!"
            )

            # Send the SMS via Telnyx
            from telephony.sms import send_sms as telnyx_send_sms
            telnyx_api_key = os.getenv("TELNYX_API_KEY")
            telnyx_from_number = os.getenv("TELNYX_FROM_NUMBER", os.getenv("TELNYX_PHONE_NUMBER", ""))
            messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

            if not telnyx_api_key or not telnyx_from_number:
                return {"success": False, "message": "SMS not configured. Missing Telnyx credentials."}

            telnyx_send_sms(
                to=contact_phone,
                from_=telnyx_from_number,
                text=sms_text,
                messaging_profile_id=messaging_profile_id or None,
                api_key=telnyx_api_key,
            )

            logger.info(f"Scheduling workflow started for {contact_name} at {mask_phone(contact_phone)}")

            return {
                "success": True,
                "message": f"Scheduling workflow started! SMS sent to {contact_name} with {len(available_slots)} available time slots. They can reply to pick a time."
            }

        except Exception as e:
            logger.error(f"Error starting scheduling workflow: {e}")
            db.rollback()
            return {"success": False, "message": f"Failed to start scheduling workflow: {str(e)}"}

    elif func_name == "get_pipeline_summary":
        try:
            # CRIT-2: Tenant-scoped pipeline query
            pipeline_params = {}
            pipeline_org_filter = ""
            if organization_id:
                pipeline_org_filter = "WHERE organization_id = :org_id"
                pipeline_params["org_id"] = organization_id
            summary = db.execute(text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')) as active_loans,
                    COALESCE(SUM(amount) FILTER (WHERE stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')), 0) as active_volume,
                    COUNT(*) FILTER (WHERE stage IN ('CTC', 'CLEAR_TO_CLOSE', 'DOCS', 'DOCS_OUT', 'CLOSING')) as closing_soon,
                    COUNT(*) FILTER (WHERE stage = 'FUNDED' AND funded_date >= CURRENT_DATE - 30) as funded_last_30,
                    COALESCE(SUM(amount) FILTER (WHERE stage = 'FUNDED' AND funded_date >= CURRENT_DATE - 30), 0) as funded_volume_30
                FROM loans
                {pipeline_org_filter}
            """), pipeline_params).fetchone()

            active_volume = float(summary.active_volume or 0)
            funded_volume = float(summary.funded_volume_30 or 0)

            return {
                "success": True,
                "message": (
                    f"Pipeline summary: {summary.active_loans} active loans "
                    f"totaling ${active_volume:,.0f}. "
                    f"{summary.closing_soon} loans closing soon. "
                    f"{summary.funded_last_30} loans funded in the last 30 days "
                    f"for ${funded_volume:,.0f}."
                ),
                "pipeline": {
                    "active_loans": summary.active_loans,
                    "active_volume": active_volume,
                    "closing_soon": summary.closing_soon,
                    "funded_last_30_days": summary.funded_last_30,
                    "funded_volume_30_days": funded_volume
                }
            }

        except Exception as e:
            logger.error(f"Error getting pipeline summary: {e}")
            db.rollback()
            return {"success": False, "message": f"Error retrieving pipeline: {str(e)}"}

    elif func_name == "send_email":
        email_to = args.get("email", "").strip()
        subject = args.get("subject", "").strip()
        body = args.get("body", "").strip()
        contact_name = args.get("contact_name", "")

        if not email_to or not subject or not body:
            return {"success": False, "message": "Email address, subject, and body are all required to send an email."}

        try:
            # Lazy import to avoid loading heavy email dependencies at module level
            from services.microsoft_graph import send_email_via_graph

            display_name = contact_name or email_to

            # send_email_via_graph expects (to, subject, body_html)
            # Wrap plain-text body in minimal HTML for Graph API
            body_html = body.replace("\n", "<br>")
            await send_email_via_graph(email_to, subject, body_html)

            # Log the email activity to the DB for audit trail
            try:
                # CRIT-2: Tenant-scoped activity log
                db.execute(text("""
                    INSERT INTO activities (
                        id, type, content, created_at, organization_id, user_id
                    ) VALUES (
                        gen_random_uuid(), 'Email', :content, NOW(), :org_id, :user_id
                    )
                """), {
                    "content": f"Voice-sent email to {display_name} ({email_to}): {subject}",
                    "org_id": organization_id,
                    "user_id": user_id,
                })
                db.commit()
            except Exception as log_err:
                logger.warning(f"Email sent but failed to log activity: {log_err}")
                db.rollback()

            logger.info(f"Email sent to {email_to} ({display_name}) subject='{subject}'")

            return {
                "success": True,
                "message": f"Email sent to {display_name} with subject '{subject}'."
            }

        except ImportError:
            logger.error("send_email_via_graph not available — falling back to SMTP")
            try:
                # Fallback: use smtplib if Graph API helper is unavailable
                import smtplib
                from email.mime.text import MIMEText

                smtp_host = os.getenv("SMTP_HOST", "")
                smtp_port = int(os.getenv("SMTP_PORT", "587"))
                smtp_user = os.getenv("SMTP_USER", "")
                smtp_pass = os.getenv("SMTP_PASSWORD", "")
                from_email = os.getenv("SMTP_FROM_EMAIL", smtp_user)

                if not smtp_host or not smtp_user:
                    return {"success": False, "message": "Email not configured. Missing SMTP or Microsoft Graph credentials."}

                msg = MIMEText(body)
                msg["Subject"] = subject
                msg["From"] = from_email
                msg["To"] = email_to

                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)

                logger.info(f"Email sent via SMTP to {email_to} subject='{subject}'")
                return {
                    "success": True,
                    "message": f"Email sent to {contact_name or email_to} with subject '{subject}'."
                }

            except Exception as smtp_err:
                logger.error(f"SMTP fallback also failed: {smtp_err}")
                return {"success": False, "message": f"Failed to send email: {str(smtp_err)}"}

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return {"success": False, "message": f"Failed to send email: {str(e)}"}

    elif func_name == "complete_task":
        task_title = args.get("task_title", "").strip()
        task_id = args.get("task_id", "").strip()

        if not task_title and not task_id:
            return {"success": False, "message": "Please provide a task title or task ID to complete."}

        try:
            # CRIT-2: Tenant-scoped task lookup
            task_params = {}
            org_filter = ""
            if organization_id:
                org_filter = "AND organization_id = :org_id"
                task_params["org_id"] = organization_id

            task_row = None

            if task_id:
                # Look up by exact ID first
                task_params["task_id"] = task_id
                task_row = db.execute(text(f"""
                    SELECT id, title, status
                    FROM tasks
                    WHERE id = :task_id
                        AND status != 'completed'
                        {org_filter}
                    LIMIT 1
                """), task_params).fetchone()

            if not task_row and task_title:
                # Fall back to ILIKE search by title
                task_params["pattern"] = f"%{task_title}%"
                task_row = db.execute(text(f"""
                    SELECT id, title, status
                    FROM tasks
                    WHERE LOWER(title) LIKE LOWER(:pattern)
                        AND status != 'completed'
                        {org_filter}
                    ORDER BY created_at DESC
                    LIMIT 1
                """), task_params).fetchone()

            if not task_row:
                search_term = task_id or task_title
                return {
                    "success": False,
                    "message": f"No open task found matching '{search_term}'."
                }

            # Mark as completed
            complete_params = {"task_id": str(task_row.id)}
            if organization_id:
                complete_params["org_id"] = organization_id
            db.execute(text(f"""
                UPDATE tasks
                SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                WHERE id = :task_id {org_filter}
            """), complete_params)
            db.commit()

            logger.info(f"Task completed: '{task_row.title}' (id={task_row.id})")

            return {
                "success": True,
                "message": f"Task '{task_row.title}' marked as completed."
            }

        except Exception as e:
            logger.error(f"Error completing task: {e}")
            db.rollback()
            return {"success": False, "message": f"Failed to complete task: {str(e)}"}

    elif func_name == "start_call_recording":
        import uuid as uuid_mod

        client_name = args.get("client_name", "")
        client_phone = args.get("client_phone", "")
        context_note = args.get("context", "")

        try:
            session_uuid = uuid_mod.uuid4()
            now = datetime.now(timezone.utc)

            telephony_call_id = args.get("call_control_id", "") or args.get("telephony_call_id", "")
            call_provider = args.get("call_provider", "")
            call_meta = {}
            if client_name:
                call_meta["client_name"] = client_name
            if client_phone:
                call_meta["client_phone"] = client_phone
            if context_note:
                call_meta["context"] = context_note
            if telephony_call_id:
                call_meta["telephony_call_id"] = telephony_call_id
            if call_provider:
                call_meta["call_provider"] = call_provider

            # Build participants JSONB
            participants = []
            if client_name or client_phone:
                participant = {"role": "borrower"}
                if client_name:
                    participant["name"] = client_name
                if client_phone:
                    participant["phone"] = client_phone
                participants.append(participant)

            # CRIT-2: Include organization_id for tenant isolation
            db.execute(text("""
                INSERT INTO call_sessions (
                    id, organization_id, capture_mode, status,
                    user_id, started_at, metadata, participants
                ) VALUES (
                    :id, :org_id, 'mobile_app', 'active',
                    :user_id, :started_at, :metadata, :participants
                )
            """), {
                "id": session_uuid,
                "org_id": organization_id,
                "user_id": user_id,
                "started_at": now,
                "metadata": json.dumps(call_meta),
                "participants": json.dumps(participants),
            })
            db.commit()

            session_id_str = str(session_uuid)
            context_msg = f" Context: {context_note}." if context_note else ""
            client_msg = f" Client: {client_name}." if client_name else ""

            logger.info(f"Call recording started: session={session_id_str[:8]}{client_msg}")

            return {
                "success": True,
                "message": f"Call recording started.{client_msg}{context_msg} Session ID: {session_id_str[:8]}.",
                "session_id": session_id_str,
            }

        except Exception as e:
            logger.error(f"Error starting call recording: {e}")
            db.rollback()
            return {"success": False, "message": f"Failed to start recording: {str(e)}"}

    elif func_name == "stop_call_recording":
        session_id_arg = args.get("session_id", "")

        try:
            now = datetime.now(timezone.utc)

            # CRIT-2: Tenant-scoped session lookup
            if session_id_arg:
                stop_params = {"session_id": session_id_arg}
                stop_org_filter = ""
                if organization_id:
                    stop_org_filter = "AND organization_id = :org_id"
                    stop_params["org_id"] = organization_id

                session_row = db.execute(text(f"""
                    SELECT id, status, started_at
                    FROM call_sessions
                    WHERE id = :session_id AND status = 'active'
                        {stop_org_filter}
                    LIMIT 1
                """), stop_params).fetchone()
            else:
                # Find most recent active session for this user/org
                stop_params = {}
                stop_filters = ["status = 'active'"]
                if organization_id:
                    stop_filters.append("organization_id = :org_id")
                    stop_params["org_id"] = organization_id
                if user_id:
                    stop_filters.append("user_id = :user_id")
                    stop_params["user_id"] = user_id

                stop_where = " AND ".join(stop_filters)
                session_row = db.execute(text(f"""
                    SELECT id, status, started_at
                    FROM call_sessions
                    WHERE {stop_where}
                    ORDER BY started_at DESC
                    LIMIT 1
                """), stop_params).fetchone()

            if not session_row:
                return {"success": False, "message": "No active call recording found to stop."}

            found_session_id = str(session_row.id)

            # Update session: status -> processing, set ended_at
            update_params = {"session_id": found_session_id, "ended_at": now}
            update_org_filter = ""
            if organization_id:
                update_org_filter = "AND organization_id = :org_id"
                update_params["org_id"] = organization_id

            db.execute(text(f"""
                UPDATE call_sessions
                SET status = 'processing', ended_at = :ended_at, updated_at = NOW()
                WHERE id = :session_id
                    {update_org_filter}
            """), update_params)
            db.commit()

            logger.info(f"Call recording stopped: session={found_session_id[:8]}")

            # Trigger AI agent pipeline (non-blocking)
            agents_triggered = False
            try:
                from services.voice_ci_bridge_service import VoiceCIBridgeService
                bridge = VoiceCIBridgeService(db, organization_id, user_id)
                bridge._trigger_agent_pipeline(found_session_id)
                agents_triggered = True
                logger.info(f"Agent pipeline triggered for session={found_session_id[:8]}")
            except Exception as agent_err:
                logger.error(f"Agent trigger failed (non-blocking): {agent_err}")

            return {
                "success": True,
                "message": f"Call recording stopped. AI analysis is processing. Session: {found_session_id[:8]}.",
                "session_id": found_session_id,
                "agents_triggered": agents_triggered,
            }

        except Exception as e:
            logger.error(f"Error stopping call recording: {e}")
            db.rollback()
            return {"success": False, "message": f"Failed to stop recording: {str(e)}"}

    elif func_name == "send_document_checklist":
        session_id_arg = args.get("session_id", "")
        send_via = args.get("send_via", "sms")
        recipient_phone = args.get("recipient_phone", "")
        recipient_email = args.get("recipient_email", "")

        try:
            # Resolve session ID if not provided — find most recent for org
            if not session_id_arg:
                resolve_params = {}
                resolve_org_filter = ""
                if organization_id:
                    resolve_org_filter = "WHERE organization_id = :org_id"
                    resolve_params["org_id"] = organization_id

                recent_session = db.execute(text(f"""
                    SELECT id
                    FROM call_sessions
                    {resolve_org_filter}
                    ORDER BY started_at DESC NULLS LAST
                    LIMIT 1
                """), resolve_params).fetchone()

                if not recent_session:
                    return {"success": True, "message": "No call intelligence sessions found.", "sent": False}

                session_id_arg = str(recent_session.id)

            # CRIT-2: Query document_request artifacts scoped to organization_id
            checklist_params = {"session_id": session_id_arg}
            checklist_org_filter = ""
            if organization_id:
                checklist_org_filter = "AND organization_id = :org_id"
                checklist_params["org_id"] = organization_id

            artifacts = db.execute(text(f"""
                SELECT id, title, content
                FROM call_artifacts
                WHERE session_id = :session_id
                    AND artifact_type = 'document_request'
                    {checklist_org_filter}
                ORDER BY created_at ASC
            """), checklist_params).fetchall()

            if not artifacts:
                return {
                    "success": True,
                    "message": "No document requests found in this call session.",
                    "sent": False,
                }

            # Build checklist text
            checklist_lines = ["Document Checklist:"]
            for i, art in enumerate(artifacts, 1):
                title = art.title or art.content or "Document"
                checklist_lines.append(f"  {i}. {title}")

            checklist_text = "\n".join(checklist_lines)
            sent_channels = []

            # Send via SMS using Telnyx
            if send_via in ("sms", "both") and recipient_phone:
                from telephony.sms import send_sms as telnyx_send_sms

                telnyx_api_key = os.getenv("TELNYX_API_KEY")
                telnyx_from_number = os.getenv("TELNYX_FROM_NUMBER", os.getenv("TELNYX_PHONE_NUMBER", ""))
                messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

                if telnyx_api_key and telnyx_from_number:
                    telnyx_send_sms(
                        to=recipient_phone,
                        from_=telnyx_from_number,
                        text=checklist_text,
                        messaging_profile_id=messaging_profile_id or None,
                        api_key=telnyx_api_key,
                    )
                    sent_channels.append("sms")
                    logger.info(f"Document checklist sent via SMS to {mask_phone(recipient_phone)}")
                else:
                    logger.warning("SMS not configured — skipping SMS delivery for document checklist")

            # Send via email using SendGrid
            if send_via in ("email", "both") and recipient_email:
                try:
                    import sendgrid
                    from sendgrid.helpers.mail import Mail

                    sg_api_key = os.getenv("SENDGRID_API_KEY")
                    from_email = os.getenv("SENDGRID_FROM_EMAIL", os.getenv("FROM_EMAIL", "noreply@perenniaai.com"))

                    if sg_api_key:
                        sg = sendgrid.SendGridAPIClient(api_key=sg_api_key)
                        mail = Mail(
                            from_email=from_email,
                            to_emails=recipient_email,
                            subject="Your Document Checklist",
                            plain_text_content=checklist_text,
                        )
                        sg.send(mail)
                        sent_channels.append("email")
                        logger.info(f"Document checklist sent via email to {recipient_email}")
                    else:
                        logger.warning("SendGrid not configured — skipping email delivery for document checklist")
                except ImportError:
                    logger.warning("sendgrid package not installed — skipping email delivery")
                except Exception as email_err:
                    logger.error(f"Error sending checklist email: {email_err}")

            if not sent_channels:
                return {
                    "success": False,
                    "message": "Could not send checklist. Provide a phone number for SMS or email address, and ensure messaging is configured.",
                }

            return {
                "success": True,
                "message": f"Document checklist with {len(artifacts)} items sent via {', '.join(sent_channels)}.",
                "sent_via": sent_channels,
                "items": len(artifacts),
                "session_id": session_id_arg,
            }

        except Exception as e:
            logger.error(f"Error sending document checklist: {e}")
            db.rollback()
            return {"success": False, "message": f"Failed to send document checklist: {str(e)}"}

    # CI tool dispatch — delegates to ci_tools module for remaining CI handlers
    elif func_name in (
        "get_recent_call_summary", "get_call_artifacts",
        "approve_artifact", "execute_artifacts",
        "send_document_checklist",
    ):
        from .ci_tools import CI_TOOL_HANDLERS
        handler = CI_TOOL_HANDLERS.get(func_name)
        if handler:
            return await handler(args=args, db=db, organization_id=organization_id, user_id=user_id)
        return {"success": False, "message": f"CI tool '{func_name}' not found."}

    else:
        logger.warning(f"Unknown browser function called: {func_name}")
        return {
            "success": False,
            "message": f"I don't know how to handle '{func_name}'. Available actions: search contacts, send SMS, send email, check availability, schedule appointments, create tasks, complete tasks, start scheduling workflows, get pipeline summary, start/stop call recording, get call summaries, get call artifacts, approve artifacts, execute artifacts, and send document checklist."
        }
