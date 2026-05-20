"""
AI Prospect Re-Engagement Service

Scans stale leads, initiates SMS outreach on behalf of the LO,
carries multi-turn AI conversations to schedule appointments,
and handles opt-outs by creating tasks.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default eligible stages for re-engagement (mixed-case, matching Lead.stage values)
DEFAULT_ELIGIBLE_STAGES = [
    "Prospect",
    "Long-Term Nurture",
    "Attempted Contact",
    "New",
    "Credit Repair",
]

DEFAULT_INITIAL_MESSAGE = (
    "Hi {first_name}! This is {lo_first_name}'s team. "
    "With recent rate changes, {lo_first_name} wanted to reconnect about "
    "your mortgage goals. Would you be open to a quick call? "
    "Reply YES and we'll find a time that works!"
)


class ProspectReEngagementService:
    """Core engine for AI-driven prospect re-engagement via SMS."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def get_config(self, organization_id: int) -> Optional[Dict[str, Any]]:
        """Get re-engagement config for an org, or return defaults."""
        row = self.db.execute(text("""
            SELECT id, organization_id, enabled, stale_days, daily_limit,
                   max_turns, expiry_days, initial_message_template,
                   eligible_stages
            FROM ai_reengagement_config
            WHERE organization_id = :org_id
        """), {"org_id": organization_id}).fetchone()

        if row:
            r = dict(row._mapping)
            return r

        return {
            "organization_id": organization_id,
            "enabled": False,
            "stale_days": 30,
            "daily_limit": 20,
            "max_turns": 8,
            "expiry_days": 7,
            "initial_message_template": None,
            "eligible_stages": DEFAULT_ELIGIBLE_STAGES,
        }

    # ------------------------------------------------------------------
    # Scan & Initiate
    # ------------------------------------------------------------------

    def scan_stale_prospects(
        self,
        organization_id: int,
        stale_days: int = 30,
        limit: int = 20,
        eligible_stages: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find leads eligible for re-engagement outreach.

        Filters:
        - In eligible stages
        - No contact in stale_days (or last_contact IS NULL)
        - Has a phone number
        - Not opted out of SMS
        - No active AI conversation already
        - Has an assigned LO (owner_id)
        """
        stages = eligible_stages or DEFAULT_ELIGIBLE_STAGES

        # Build stage placeholders dynamically since text() doesn't expand tuples
        stage_placeholders = ", ".join(f":stage_{i}" for i in range(len(stages)))
        stage_params = {f"stage_{i}": s for i, s in enumerate(stages)}

        params = {
            "org_id": organization_id,
            "stale_days": stale_days,
            "limit": limit,
            **stage_params,
        }

        sql = """
            SELECT
                l.id, l.first_name, l.last_name, l.phone, l.email,
                l.stage, l.last_contact, l.owner_id, l.organization_id
            FROM leads l
            WHERE l.organization_id = :org_id
              AND l.stage IN (""" + stage_placeholders + """)
              AND l.phone IS NOT NULL
              AND l.phone != ''
              AND l.owner_id IS NOT NULL
              AND (l.last_contact IS NULL OR l.last_contact < NOW() - INTERVAL '1 day' * :stale_days)
              -- Not opted out
              AND NOT EXISTS (
                  SELECT 1 FROM sms_opt_outs o
                  WHERE o.phone_number = l.phone
              )
              -- No active AI conversation
              AND NOT EXISTS (
                  SELECT 1 FROM ai_prospect_conversations c
                  WHERE c.lead_id = l.id
                    AND c.state IN ('initial_outreach_sent', 'awaiting_reply', 'scheduling', 'pending_outreach')
              )
              -- Check channel_preferences if table exists
              AND NOT EXISTS (
                  SELECT 1 FROM channel_preferences cp
                  WHERE cp.lead_id = l.id
                    AND (cp.do_not_sms = true OR cp.sms_consent = false)
              )
            ORDER BY l.last_contact ASC NULLS FIRST
            LIMIT :limit
        """
        results = self.db.execute(text(sql), params).fetchall()

        return [dict(r._mapping) for r in results]

    def initiate_outreach(self, lead_id: int) -> Dict[str, Any]:
        """
        Initiate AI re-engagement outreach for a single lead.

        1. Load lead + LO info
        2. TCPA hours check
        3. Compliance checks (opt-out, channel preference)
        4. Send personalized SMS
        5. Create conversation record
        6. Log activity + update last_contact
        """
        # Load lead
        lead = self.db.execute(text("""
            SELECT l.id, l.first_name, l.last_name, l.phone, l.email,
                   l.stage, l.owner_id, l.organization_id
            FROM leads l
            WHERE l.id = :lead_id
        """), {"lead_id": lead_id}).fetchone()

        if not lead:
            return {"success": False, "error": f"Lead {lead_id} not found"}

        lead_data = dict(lead._mapping)

        if not lead_data["phone"]:
            return {"success": False, "error": "Lead has no phone number"}

        if not lead_data["owner_id"]:
            return {"success": False, "error": "Lead has no assigned LO"}

        normalized_phone = _normalize_phone(lead_data["phone"])

        # Load LO
        lo = self.db.execute(text("""
            SELECT id, first_name, last_name, email
            FROM users
            WHERE id = :lo_id
        """), {"lo_id": lead_data["owner_id"]}).fetchone()

        if not lo:
            return {"success": False, "error": "Assigned LO not found"}

        lo_data = dict(lo._mapping)

        # Resolve LO's company (organization name) so borrower-facing copy
        # reads as the LO's actual brokerage (e.g. "CMG Home Loans"),
        # never the platform name.
        lo_company = ""
        try:
            org_row = self.db.execute(text("""
                SELECT name FROM organizations WHERE id = :oid
            """), {"oid": lead_data["organization_id"]}).fetchone()
            if org_row and org_row[0]:
                lo_company = org_row[0]
        except Exception:
            pass

        # TCPA hours check
        tcpa_ok, tcpa_reason = _check_tcpa_hours(normalized_phone)
        if not tcpa_ok:
            return {"success": False, "error": f"TCPA restricted: {tcpa_reason}"}

        # Opt-out check
        opt_out = self.db.execute(text("""
            SELECT 1 FROM sms_opt_outs WHERE phone_number = :phone LIMIT 1
        """), {"phone": normalized_phone}).fetchone()

        if opt_out:
            return {"success": False, "error": "Lead is opted out of SMS"}

        # Channel preference check
        pref = self.db.execute(text("""
            SELECT do_not_sms, sms_consent FROM channel_preferences
            WHERE lead_id = :lead_id LIMIT 1
        """), {"lead_id": lead_id}).fetchone()

        if pref:
            pref_data = dict(pref._mapping)
            if pref_data.get("do_not_sms"):
                return {"success": False, "error": "Lead has do_not_sms preference"}
            if pref_data.get("sms_consent") is False:
                return {"success": False, "error": "Lead has not consented to SMS"}

        # Get org config for template
        config = self.get_config(lead_data["organization_id"])
        template = config.get("initial_message_template") or DEFAULT_INITIAL_MESSAGE
        expiry_days = config.get("expiry_days", 7)
        max_turns = config.get("max_turns", 8)

        # Build message
        message = template.format(
            first_name=lead_data["first_name"] or "there",
            lo_first_name=lo_data["first_name"] or "your loan officer",
            lo_last_name=lo_data.get("last_name", ""),
        )

        # Get the Telnyx from number
        from_number = os.getenv("TELNYX_PHONE_NUMBER", "")
        if not from_number:
            return {"success": False, "error": "TELNYX_PHONE_NUMBER not configured"}

        # Send SMS
        message_id = _send_sms_sync(normalized_phone, message, from_number)
        if not message_id:
            return {"success": False, "error": "Failed to send SMS"}

        now = datetime.now(timezone.utc)

        # Create conversation record
        self.db.execute(text("""
            INSERT INTO ai_prospect_conversations (
                organization_id, lead_id, lo_user_id,
                lead_phone, telnyx_from_number,
                state, state_changed_at,
                context, messages, proposed_times,
                turn_count, max_turns,
                expires_at, first_outreach_at, last_message_at, created_at
            ) VALUES (
                :org_id, :lead_id, :lo_id,
                :phone, :from_number,
                'initial_outreach_sent', :now,
                :context::jsonb, :messages::jsonb, '[]'::jsonb,
                1, :max_turns,
                :expires_at, :now, :now, :now
            )
        """), {
            "org_id": lead_data["organization_id"],
            "lead_id": lead_id,
            "lo_id": lo_data["id"],
            "phone": normalized_phone,
            "from_number": from_number,
            "now": now,
            "context": _json_dumps({
                "lo_first_name": lo_data["first_name"],
                "lo_last_name": lo_data.get("last_name", ""),
                "lo_email": lo_data.get("email", ""),
                "lo_company": lo_company,
                "lead_first_name": lead_data["first_name"],
                "lead_last_name": lead_data.get("last_name", ""),
                "lead_email": lead_data.get("email", ""),
                "lead_stage": lead_data.get("stage", ""),
            }),
            "messages": _json_dumps([{
                "role": "assistant",
                "content": message,
                "timestamp": now.isoformat(),
            }]),
            "max_turns": max_turns,
            "expires_at": now + timedelta(days=expiry_days),
        })

        # Log activity
        self.db.execute(text("""
            INSERT INTO activities (lead_id, type, content, created_at, user_id)
            VALUES (:lead_id, 'SMS', :content, :now, :lo_id)
        """), {
            "lead_id": lead_id,
            "content": f"[AI Re-Engagement] Outreach sent: {message[:100]}...",
            "now": now,
            "lo_id": lo_data["id"],
        })

        # Update lead last_contact
        self.db.execute(text("""
            UPDATE leads SET last_contact = :now WHERE id = :lead_id
        """), {"now": now, "lead_id": lead_id})

        # Store in sms_messages for audit trail
        self.db.execute(text("""
            INSERT INTO sms_messages (
                direction, from_number, to_number, body,
                provider, provider_message_id, status, created_at
            ) VALUES (
                'outbound', :from_number, :to_number, :body,
                'telnyx', :message_id, 'sent', :now
            )
        """), {
            "from_number": from_number,
            "to_number": normalized_phone,
            "body": message,
            "message_id": message_id,
            "now": now,
        })

        self.db.commit()

        return {
            "success": True,
            "lead_id": lead_id,
            "message_id": message_id,
            "message": message,
        }

    # ------------------------------------------------------------------
    # Handle inbound reply (called from webhook intercept)
    # ------------------------------------------------------------------

    def handle_reply(self, from_phone: str, message_body: str) -> Optional[Dict[str, Any]]:
        """
        Handle an inbound SMS that may belong to an active AI conversation.

        Returns:
        - dict with response info if this message was handled
        - None if no active conversation found (falls through to normal SMS flow)
        """
        normalized = _normalize_phone(from_phone)

        # Look up active conversation — use FOR UPDATE to prevent race conditions
        conv = self.db.execute(text("""
            SELECT id, lead_id, lo_user_id, lead_phone, telnyx_from_number,
                   state, context, messages, proposed_times,
                   turn_count, max_turns, organization_id
            FROM ai_prospect_conversations
            WHERE lead_phone = :phone
              AND state IN ('initial_outreach_sent', 'awaiting_reply', 'scheduling')
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE
        """), {"phone": normalized}).fetchone()

        if not conv:
            return None  # No active conversation — fall through

        conv_data = dict(conv._mapping)
        conv_id = conv_data["id"]

        # Check turn limit
        if conv_data["turn_count"] >= conv_data["max_turns"]:
            self._transition_state(conv_id, "expired", "Max turns reached")
            self._create_task_for_lo(
                conv_data,
                f"AI Re-Engagement: Max turns reached for lead — consider manual follow-up",
            )
            self.db.commit()
            return {"status": "expired", "reason": "max_turns"}

        # Opt-out check first
        if _is_opt_out_message(message_body):
            return self._handle_opt_out(conv_data, message_body)

        # Parse existing messages
        messages = conv_data.get("messages") or []
        if isinstance(messages, str):
            messages = _json_loads(messages)

        context = conv_data.get("context") or {}
        if isinstance(context, str):
            context = _json_loads(context)

        # Append inbound message
        now = datetime.now(timezone.utc)
        messages.append({
            "role": "user",
            "content": message_body,
            "timestamp": now.isoformat(),
        })

        # Generate AI response
        ai_result = self._generate_ai_response(
            conv_data=conv_data,
            context=context,
            messages=messages,
            inbound_message=message_body,
        )

        response_text = ai_result.get("response_text", "")
        intent = ai_result.get("intent", "ambiguous")
        next_state = ai_result.get("next_state")
        parsed_time = ai_result.get("parsed_time")

        # Append AI response
        messages.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # State transitions
        if intent == "opt_out":
            return self._handle_opt_out(conv_data, message_body)

        elif intent == "decline":
            reason = ai_result.get("decline_reason", message_body[:100])
            return self._handle_decline(conv_data, reason, response_text, messages)

        elif intent == "interested" and conv_data["state"] != "scheduling":
            # Move to scheduling, propose times
            proposed = ai_result.get("proposed_times") or []
            self._update_conversation(conv_id, {
                "state": "scheduling",
                "messages": messages,
                "proposed_times": proposed,
                "turn_count": conv_data["turn_count"] + 1,
            })
            # Send response
            self._send_and_log(conv_data, response_text, messages)
            return {"status": "scheduling", "response": response_text}

        elif intent == "confirm_time" and parsed_time:
            # Attempt booking
            booking = self._attempt_booking(conv_data, parsed_time)
            if booking.get("success"):
                messages.append({
                    "role": "assistant",
                    "content": booking["confirmation_message"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                self._update_conversation(conv_id, {
                    "state": "appointment_booked",
                    "messages": messages,
                    "booked_appointment_id": booking.get("appointment_id"),
                    "outcome": "booked",
                    "completed_at": datetime.now(timezone.utc),
                    "turn_count": conv_data["turn_count"] + 1,
                })
                _send_sms_sync(
                    conv_data["lead_phone"],
                    booking["confirmation_message"],
                    conv_data["telnyx_from_number"],
                )
                self.db.commit()
                return {"status": "appointment_booked", "appointment_id": booking.get("appointment_id")}
            else:
                # Booking failed — ask for another time
                self._update_conversation(conv_id, {
                    "messages": messages,
                    "turn_count": conv_data["turn_count"] + 1,
                })
                self._send_and_log(conv_data, response_text, messages)
                return {"status": "scheduling", "response": response_text}

        else:
            # Ambiguous or continuing conversation. If Aria proposed specific
            # times in this turn, promote the conversation to the scheduling
            # state so the next inbound is treated as a possible time pick.
            proposed = ai_result.get("proposed_times") or []
            new_state = next_state or conv_data["state"]
            if proposed:
                new_state = "scheduling"
            if new_state == "initial_outreach_sent":
                new_state = "awaiting_reply"

            update_payload = {
                "state": new_state,
                "messages": messages,
                "turn_count": conv_data["turn_count"] + 1,
            }
            if proposed:
                update_payload["proposed_times"] = proposed
            self._update_conversation(conv_id, update_payload)
            self._send_and_log(conv_data, response_text, messages)
            return {"status": new_state, "response": response_text}

    # ------------------------------------------------------------------
    # AI Response Generation
    # ------------------------------------------------------------------

    def _generate_ai_response(
        self,
        conv_data: Dict,
        context: Dict,
        messages: List[Dict],
        inbound_message: str,
    ) -> Dict[str, Any]:
        """
        Use Claude to classify intent and craft a reply.

        Returns: {response_text, intent, next_state, parsed_time, decline_reason, proposed_times}
        """
        lo_name = context.get("lo_first_name", "your loan officer")
        lead_name = context.get("lead_first_name", "there")
        lo_company = context.get("lo_company") or ""
        # Backfill org name for conversations created before lo_company was tracked
        if not lo_company:
            try:
                org_row = self.db.execute(text("""
                    SELECT name FROM organizations WHERE id = :oid
                """), {"oid": conv_data.get("organization_id")}).fetchone()
                if org_row and org_row[0]:
                    lo_company = org_row[0]
            except Exception:
                pass
        lo_company = lo_company or f"{lo_name}'s team"
        current_state = conv_data.get("state", "awaiting_reply")

        # Build conversation history for the prompt
        history_lines = []
        for m in messages[-6:]:  # Last 6 messages for context
            role_label = "Lead" if m["role"] == "user" else "Assistant"
            history_lines.append(f"{role_label}: {m['content']}")
        history_text = "\n".join(history_lines)

        # Always inject real LO calendar availability so Aria can propose
        # specific times on every turn, even when the lead asks a question
        # rather than committing. Without this, the LLM tends to deflect
        # ("the LO will reach out") instead of actively scheduling.
        available_slots_text = self._get_available_slots_text(conv_data)

        system_prompt = f"""You are Aria, the scheduling assistant for {lo_name} at {lo_company}. You represent {lo_name} and {lo_company} — never any other brand, platform, or vendor. Your single job is to BOOK a consultation call between {lead_name} and {lo_name}.

You are texting with {lead_name}. Keep each SMS under 280 characters (2 segments). Be warm, professional, and decisive — never wishy-washy.

Current conversation state: {current_state}

GROUND RULES (non-negotiable):
- NEVER say "{lo_name} will reach out", "will contact you", "will get back to you", "will call you later", or anything that defers the booking to a future human action. YOU are the one booking the time, right now, in this conversation.
- NEVER end a reply without either (a) proposing 2-3 specific times from the available slots, or (b) confirming a specific time the lead just gave.
- Do NOT use emojis. Do NOT mention AI or automation. Speak as {lo_name}'s human-sounding assistant.
- Do NOT quote rates, fees, or loan terms. If asked about rates/fees, briefly say {lo_name} will cover that on the call, then propose times.

INTENT CLASSIFICATION (pick one):
- "interested"   — they want to talk/schedule, but haven't committed to a specific time yet (yes, sure, sounds good, vague questions, anything not a clear no)
- "confirm_time" — they named or accepted a SPECIFIC date+time (e.g. "Thursday at 2pm", "yes that works", "tomorrow morning at 10")
- "decline"      — they are clearly not interested (no thanks, not now, lose my number, maybe later)
- "opt_out"     — STOP / unsubscribe / quit
- "ambiguous"   — they asked a question or made small talk; you should ANSWER briefly and then propose specific times in the SAME message

RESPONSE PLAYBOOK BY INTENT:
- interested OR ambiguous → answer their question in one sentence (if any), then propose 2-3 specific times from the available slots below. Example: "Happy to walk you through it on a quick call. I've got Wed 10am, Thu 2pm, or Fri 9am — which works?"
- confirm_time → confirm the exact day/time and set parsed_time. Example: "Perfect, locking you in for Thursday at 2pm. {lo_name} will call you then and you'll get a confirmation + reminder."
- decline → be gracious, leave the door open. Example: "All good — if anything changes, just text back and we'll find a time."
- opt_out → short acknowledgement, no further pitch.

AVAILABLE TIMES on {lo_name}'s calendar (use ONLY these — do not invent times):
{available_slots_text if available_slots_text else "(no specific slots loaded — ask the lead for 2 day/time options that work for them this week)"}

Respond with EXACTLY this JSON format (no markdown, no extra text):
{{"intent": "interested|confirm_time|decline|opt_out|ambiguous", "response_text": "your SMS reply here", "next_state": "scheduling|declined|opt_out|awaiting_reply", "parsed_time": null, "decline_reason": null, "proposed_times": []}}

- If intent is confirm_time, set parsed_time to the ISO datetime they confirmed (e.g. "2026-03-03T14:00:00").
- For interested or ambiguous intents, ALWAYS populate proposed_times with 2-3 ISO datetimes drawn from the available slots, and reference those exact times in response_text."""

        user_prompt = f"""Conversation history:
{history_text}

Lead's latest message: "{inbound_message}"

Classify intent and generate response:"""

        try:
            import json
            result = _call_ai(system_prompt, user_prompt)
            parsed = json.loads(result)
            return parsed
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            # Fallback: never punt to the LO — keep the booking flow moving.
            # If we have real slots, surface the first two so the lead can pick.
            fallback_text = (
                f"Happy to set you up with {lo_name}. What day/time works "
                "best for you this week? I can lock it in right now."
            )
            try:
                if available_slots_text and available_slots_text.startswith("-"):
                    first_two = [
                        line[2:] for line in available_slots_text.splitlines()[:2]
                        if line.startswith("- ")
                    ]
                    if first_two:
                        fallback_text = (
                            f"Want me to put you on {lo_name}'s calendar? "
                            f"I've got {first_two[0]} or {first_two[-1]} open — which works?"
                        )
            except Exception:
                pass
            return {
                "intent": "ambiguous",
                "response_text": fallback_text,
                "next_state": "scheduling",
                "parsed_time": None,
                "proposed_times": [],
            }

    def _get_available_slots_text(self, conv_data: Dict) -> str:
        """Fetch available appointment slots via direct ORM query with org filtering."""
        try:
            from services.smart_scheduler_service import ScheduledAppointment, AppointmentStatus

            lo_user_id = conv_data.get("lo_user_id")
            org_id = conv_data.get("organization_id")
            now = datetime.now(timezone.utc)
            end_dt = now + timedelta(days=5)

            query = self.db.query(ScheduledAppointment).filter(
                ScheduledAppointment.start_time >= now,
                ScheduledAppointment.start_time <= end_dt,
                ScheduledAppointment.status.in_([
                    AppointmentStatus.SCHEDULED.value,
                    AppointmentStatus.CONFIRMED.value,
                ]),
            )
            if lo_user_id:
                query = query.filter(ScheduledAppointment.loan_officer_id == lo_user_id)
            if org_id:
                query = query.filter(ScheduledAppointment.organization_id == org_id)

            upcoming = query.order_by(ScheduledAppointment.start_time).all()

            # Build busy times and suggest open slots
            busy_times = set()
            for appt in upcoming:
                busy_times.add(appt.start_time.strftime("%Y-%m-%d %H:%M"))

            # Suggest 3 open slots in the next 3 business days
            slots = []
            now = datetime.now(timezone.utc)
            for day_offset in range(1, 5):
                candidate = now + timedelta(days=day_offset)
                if candidate.weekday() >= 5:  # Skip weekends
                    continue
                for hour in [10, 14, 16]:
                    slot_time = candidate.replace(hour=hour, minute=0, second=0, microsecond=0)
                    slot_str = slot_time.strftime("%Y-%m-%d %H:%M")
                    if slot_str not in busy_times and slot_time > now:
                        slots.append(slot_time)
                    if len(slots) >= 3:
                        break
                if len(slots) >= 3:
                    break

            if not slots:
                return "No specific slots found — ask the lead for their preferred day/time."

            lines = []
            for s in slots:
                lines.append(f"- {s.strftime('%A, %B %d at %I:%M %p')}")
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Failed to fetch available slots: {e}")
            return "Unable to fetch calendar — ask the lead for their preferred day/time."

    # ------------------------------------------------------------------
    # Booking
    # ------------------------------------------------------------------

    def _attempt_booking(self, conv_data: Dict, appointment_time_str: str) -> Dict[str, Any]:
        """Attempt to book an appointment via direct ORM with organization_id filtering."""
        try:
            from services.smart_scheduler_service import ScheduledAppointment, AppointmentStatus
            from datetime import datetime as dt
            import uuid as _uuid

            appointment_time = dt.fromisoformat(appointment_time_str)

            context = conv_data.get("context") or {}
            if isinstance(context, str):
                context = _json_loads(context)

            contact_name = f"{context.get('lead_first_name', '')} {context.get('lead_last_name', '')}".strip() or "Prospect"
            contact_email = context.get("lead_email", "")
            contact_phone = conv_data["lead_phone"]
            lo_user_id = conv_data["lo_user_id"]
            org_id = conv_data["organization_id"]

            duration_minutes = 30
            end_time = appointment_time + timedelta(minutes=duration_minutes)
            appt_id = f"APPT-{str(_uuid.uuid4())[:8].upper()}"

            appointment = ScheduledAppointment(
                appointment_id=appt_id,
                loan_officer_id=lo_user_id,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                appointment_type="re_engagement_consultation",
                start_time=appointment_time,
                end_time=end_time,
                duration_minutes=duration_minutes,
                status=AppointmentStatus.SCHEDULED.value,
                notes="Booked via AI prospect re-engagement",
                booked_via="ai_assistant",
                organization_id=org_id,
            )
            self.db.add(appointment)
            self.db.commit()

            lo_name = context.get("lo_first_name", "your loan officer")
            time_str = appointment_time.strftime("%A, %B %d at %I:%M %p")
            confirmation = (
                f"You're all set! {lo_name} will call you on {time_str}. "
                f"We'll send a reminder before the call."
            )
            return {
                "success": True,
                "appointment_id": appt_id,
                "confirmation_message": confirmation,
            }

        except Exception as e:
            logger.error(f"Booking attempt failed: {e}")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Opt-out & Decline
    # ------------------------------------------------------------------

    def _handle_opt_out(self, conv_data: Dict, message_body: str) -> Dict[str, Any]:
        """Process opt-out: update sms_opt_outs, send confirmation, create task."""
        conv_id = conv_data["id"]
        phone = conv_data["lead_phone"]

        # Insert into sms_opt_outs
        self.db.execute(text("""
            INSERT INTO sms_opt_outs (phone_number, opt_out_message, lead_id, user_id)
            VALUES (:phone, :message, :lead_id, :lo_id)
            ON CONFLICT (phone_number, user_id) DO UPDATE SET opted_out_at = CURRENT_TIMESTAMP
        """), {
            "phone": phone,
            "message": message_body,
            "lead_id": conv_data["lead_id"],
            "lo_id": conv_data["lo_user_id"],
        })

        # Send required confirmation (skip compliance — TCPA *requires* this message)
        confirmation = "You've been unsubscribed from text messages. Reply START to re-subscribe."
        _send_sms_sync(phone, confirmation, conv_data["telnyx_from_number"], skip_compliance=True)

        # Transition state
        self._transition_state(conv_id, "opt_out", f"Opted out: {message_body[:100]}")

        # Create task for LO
        context = conv_data.get("context") or {}
        if isinstance(context, str):
            context = _json_loads(context)
        lead_name = f"{context.get('lead_first_name', '')} {context.get('lead_last_name', '')}".strip() or "Lead"

        task_id = self._create_task_for_lo(
            conv_data,
            f"AI Re-Engagement: {lead_name} opted out of SMS — \"{message_body[:80]}\"",
        )

        # Log activity
        self.db.execute(text("""
            INSERT INTO activities (lead_id, type, content, created_at, user_id)
            VALUES (:lead_id, 'SMS', :content, :now, :lo_id)
        """), {
            "lead_id": conv_data["lead_id"],
            "content": f"[AI Re-Engagement] Lead opted out: {message_body[:100]}",
            "now": datetime.now(timezone.utc),
            "lo_id": conv_data["lo_user_id"],
        })

        self.db.commit()
        return {"status": "opt_out", "task_id": task_id}

    def _handle_decline(
        self,
        conv_data: Dict,
        reason: str,
        response_text: str,
        messages: List[Dict],
    ) -> Dict[str, Any]:
        """Process decline: send gracious goodbye, create task."""
        conv_id = conv_data["id"]
        context = conv_data.get("context") or {}
        if isinstance(context, str):
            context = _json_loads(context)

        lo_name = context.get("lo_first_name", "your loan officer")
        lead_name = f"{context.get('lead_first_name', '')} {context.get('lead_last_name', '')}".strip() or "Lead"

        # Use AI-generated response or fallback
        if not response_text:
            response_text = f"No problem at all! {lo_name} is always here if anything changes. Have a great day!"

        # Send farewell
        _send_sms_sync(conv_data["lead_phone"], response_text, conv_data["telnyx_from_number"])

        messages.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        self._update_conversation(conv_id, {
            "state": "declined",
            "messages": messages,
            "outcome": "declined",
            "outcome_notes": reason,
            "completed_at": datetime.now(timezone.utc),
            "turn_count": conv_data["turn_count"] + 1,
        })

        task_id = self._create_task_for_lo(
            conv_data,
            f"AI Re-Engagement: {lead_name} not interested — \"{reason[:80]}\"",
        )

        # Log activity
        self.db.execute(text("""
            INSERT INTO activities (lead_id, type, content, created_at, user_id)
            VALUES (:lead_id, 'SMS', :content, :now, :lo_id)
        """), {
            "lead_id": conv_data["lead_id"],
            "content": f"[AI Re-Engagement] Lead declined: {reason[:100]}",
            "now": datetime.now(timezone.utc),
            "lo_id": conv_data["lo_user_id"],
        })

        self.db.commit()
        return {"status": "declined", "task_id": task_id}

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    def expire_stale_conversations(self) -> int:
        """
        Expire conversations past their expires_at with no response.
        Creates a task for each expired conversation.
        Returns the count of expired conversations.
        """
        expired = self.db.execute(text("""
            SELECT id, lead_id, lo_user_id, organization_id, context, lead_phone
            FROM ai_prospect_conversations
            WHERE expires_at < NOW()
              AND state IN ('initial_outreach_sent', 'awaiting_reply', 'scheduling')
        """)).fetchall()

        count = 0
        for row in expired:
            conv_data = dict(row._mapping)
            self._transition_state(conv_data["id"], "expired", "No response — conversation expired")

            context = conv_data.get("context") or {}
            if isinstance(context, str):
                context = _json_loads(context)
            lead_name = f"{context.get('lead_first_name', '')} {context.get('lead_last_name', '')}".strip() or "Lead"

            self._create_task_for_lo(
                conv_data,
                f"AI Re-Engagement: No response from {lead_name} — consider manual follow-up",
            )
            count += 1

        if count > 0:
            self.db.commit()
            logger.info(f"Expired {count} stale AI re-engagement conversations")

        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _transition_state(self, conv_id: int, new_state: str, notes: str = ""):
        """Transition conversation to a new state."""
        self.db.execute(text("""
            UPDATE ai_prospect_conversations
            SET state = :state,
                state_changed_at = NOW(),
                outcome_notes = COALESCE(outcome_notes, '') || :notes,
                completed_at = CASE
                    WHEN :state IN ('appointment_booked', 'declined', 'opt_out', 'expired', 'cancelled')
                    THEN NOW() ELSE completed_at END
            WHERE id = :id
        """), {"id": conv_id, "state": new_state, "notes": notes})

    def _update_conversation(self, conv_id: int, updates: Dict[str, Any]):
        """Update conversation fields."""
        set_clauses = []
        params = {"id": conv_id}

        for key, value in updates.items():
            if key in ("state", "turn_count", "outcome", "outcome_notes",
                       "booked_appointment_id", "completed_at"):
                set_clauses.append(f"{key} = :{key}")
                params[key] = value
            elif key == "messages":
                set_clauses.append("messages = :messages::jsonb")
                params["messages"] = _json_dumps(value)
            elif key == "proposed_times":
                set_clauses.append("proposed_times = :proposed_times::jsonb")
                params["proposed_times"] = _json_dumps(value)

        if "state" in updates:
            set_clauses.append("state_changed_at = NOW()")

        set_clauses.append("last_message_at = NOW()")

        if not set_clauses:
            return

        sql = f"UPDATE ai_prospect_conversations SET {', '.join(set_clauses)} WHERE id = :id"
        self.db.execute(text(sql), params)

    def _create_task_for_lo(self, conv_data: Dict, title: str) -> Optional[int]:
        """Create a task for the loan officer about this conversation."""
        try:
            result = self.db.execute(text("""
                INSERT INTO tasks (
                    organization_id, title, description, status, priority,
                    owner_id, lead_id, related_type, created_at
                ) VALUES (
                    :org_id, :title, :description, 'pending', 'medium',
                    :owner_id, :lead_id, 'ai_reengagement', NOW()
                )
                RETURNING id
            """), {
                "org_id": conv_data["organization_id"],
                "title": title[:255],
                "description": f"Auto-generated by AI prospect re-engagement system. Conversation ID: {conv_data['id']}",
                "owner_id": conv_data["lo_user_id"],
                "lead_id": conv_data["lead_id"],
            })
            row = result.fetchone()
            task_id = row[0] if row else None

            # Link task to conversation
            if task_id:
                self.db.execute(text("""
                    UPDATE ai_prospect_conversations SET task_id = :task_id WHERE id = :id
                """), {"task_id": task_id, "id": conv_data["id"]})

            return task_id
        except Exception as e:
            logger.error(f"Failed to create task for LO: {e}")
            return None

    def _send_and_log(self, conv_data: Dict, response_text: str, messages: List[Dict]):
        """Send SMS and log activity."""
        if response_text:
            _send_sms_sync(
                conv_data["lead_phone"],
                response_text,
                conv_data["telnyx_from_number"],
            )

            # Store outbound SMS in sms_messages for audit trail
            self.db.execute(text("""
                INSERT INTO sms_messages (
                    direction, from_number, to_number, body,
                    provider, status, created_at
                ) VALUES (
                    'outbound', :from_number, :to_number, :body,
                    'telnyx', 'sent', NOW()
                )
            """), {
                "from_number": conv_data["telnyx_from_number"],
                "to_number": conv_data["lead_phone"],
                "body": response_text,
            })

            # Log activity
            self.db.execute(text("""
                INSERT INTO activities (lead_id, type, content, created_at, user_id)
                VALUES (:lead_id, 'SMS', :content, NOW(), :lo_id)
            """), {
                "lead_id": conv_data["lead_id"],
                "content": f"[AI Re-Engagement] Sent: {response_text[:150]}",
                "lo_id": conv_data["lo_user_id"],
            })

            # Update lead last_contact
            self.db.execute(text("""
                UPDATE leads SET last_contact = NOW() WHERE id = :lead_id
            """), {"lead_id": conv_data["lead_id"]})

        self.db.commit()


# ==========================================================================
# Module-level utility functions
# ==========================================================================

def _normalize_phone(phone: str) -> str:
    """Normalize phone to E.164 format."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    return f"+{digits}" if not phone.startswith('+') else phone


_OPT_OUT_KEYWORDS = ['stop', 'unsubscribe', 'cancel', 'end', 'quit', 'optout', 'opt-out', 'opt out']


def _is_opt_out_message(message: str) -> bool:
    """Check if message is an opt-out request."""
    message_lower = message.lower().strip()
    for keyword in _OPT_OUT_KEYWORDS:
        if message_lower == keyword or message_lower.startswith(keyword + ' '):
            return True
    return False


def _check_tcpa_hours(phone: str) -> tuple:
    """
    Check if current time is within TCPA allowed hours (8AM-9PM)
    in the recipient's local timezone based on area code.
    Returns (is_allowed, reason).
    """
    try:
        import pytz
    except ImportError:
        return True, ""

    # Try to use the voicemail_drop_routes timezone lookup
    try:
        from routes.voicemail_drop_routes import _get_recipient_timezone
        tz_name = _get_recipient_timezone(phone)
    except (ImportError, Exception):
        tz_name = "America/New_York"

    try:
        tz = pytz.timezone(tz_name)
        local_now = datetime.now(tz)
        hour = local_now.hour

        if hour < 8 or hour >= 21:
            return False, f"Outside TCPA hours ({hour}:00 local in {tz_name}). Allowed: 8AM-9PM."

        return True, ""
    except Exception:
        return True, ""


def _send_sms_sync(
    to_number: str,
    message: str,
    from_number: str,
    skip_compliance: bool = False,
) -> Optional[str]:
    """Send SMS via the centralized Telnyx chokepoint.

    The chokepoint handles compliance gate + STOP footer.
    *skip_compliance* is forwarded as bypass_compliance for legally
    required messages (opt-out confirmations).
    """
    try:
        from telephony.sms import send_sms_verified

        result = send_sms_verified(
            to=to_number,
            from_=from_number,
            text=message,
            bypass_compliance=skip_compliance,
        )

        if result.get("status") == "sent":
            message_id = result.get("id", "")
            logger.info(f"AI re-engagement SMS sent to {to_number}. ID: {message_id}")
            return message_id
        else:
            reason = result.get("reason", "unknown")
            logger.warning(f"AI re-engagement SMS blocked for ...{to_number[-4:]}: {reason}")
            return None

    except Exception as e:
        logger.error(f"AI re-engagement SMS send error: {e}")
        return None


def _call_ai(system_prompt: str, user_prompt: str) -> str:
    """Call Claude API for intent classification and response generation."""
    import json

    # Use the same pattern as existing AI features (openai-compatible client)
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback to OpenAI client if configured
        api_key = os.getenv("OPENAI_API_KEY", "")

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")

    # Fallback: try OpenAI-compatible API
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=500,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")

    # Last resort: return a safe fallback
    logger.error("No AI API key configured — returning fallback response")
    return json.dumps({
        "intent": "ambiguous",
        "response_text": "Thanks for your reply! Let me have your loan officer follow up directly.",
        "next_state": "awaiting_reply",
        "parsed_time": None,
    })


def _json_dumps(obj) -> str:
    """Safe JSON serialization."""
    import json
    if isinstance(obj, str):
        return obj

    def _default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.dumps(obj, default=_default)


def _json_loads(s) -> Any:
    """Safe JSON deserialization."""
    import json
    if not isinstance(s, str):
        return s
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s


# ==========================================================================
# Scheduler job wrappers (called from scheduler_service.py)
# ==========================================================================

def run_prospect_reengagement_scan():
    """
    Daily scan job: iterate all enabled orgs, find stale leads, initiate outreach.
    Called from SchedulerService cron job.

    Note: This is a system-wide scheduler that processes all orgs.
    Per-org RLS context is set inside the org iteration loop.
    """
    from database import SessionLocal

    session = SessionLocal()
    try:
        svc = ProspectReEngagementService(session)

        # Get all enabled org configs
        configs = session.execute(text("""
            SELECT organization_id, stale_days, daily_limit, eligible_stages
            FROM ai_reengagement_config
            WHERE enabled = true
        """)).fetchall()

        total_initiated = 0

        for config_row in configs:
            cfg = dict(config_row._mapping)
            org_id = cfg["organization_id"]
            # TENANT-017: Set RLS context per org iteration
            try:
                from database.tenant_mixin import set_tenant_context
                set_tenant_context(session, org_id)
            except Exception:
                pass
            stale_days = cfg.get("stale_days") or 30
            daily_limit = cfg.get("daily_limit") or 20
            eligible_stages = cfg.get("eligible_stages") or DEFAULT_ELIGIBLE_STAGES

            # Check how many we already sent today
            sent_today = session.execute(text("""
                SELECT COUNT(*) FROM ai_prospect_conversations
                WHERE organization_id = :org_id
                  AND first_outreach_at >= CURRENT_DATE
            """), {"org_id": org_id}).scalar() or 0

            remaining = max(0, daily_limit - sent_today)
            if remaining <= 0:
                logger.info(f"Org {org_id}: daily limit reached ({sent_today}/{daily_limit})")
                continue

            prospects = svc.scan_stale_prospects(
                organization_id=org_id,
                stale_days=stale_days,
                limit=remaining,
                eligible_stages=eligible_stages,
            )

            for prospect in prospects:
                try:
                    result = svc.initiate_outreach(prospect["id"])
                    if result.get("success"):
                        total_initiated += 1
                        logger.info(f"Initiated re-engagement for lead {prospect['id']}")
                    else:
                        logger.warning(f"Skipped lead {prospect['id']}: {result.get('error')}")
                except Exception as e:
                    logger.error(f"Failed to initiate outreach for lead {prospect['id']}: {e}")
                    session.rollback()

        logger.info(f"Prospect re-engagement scan complete: {total_initiated} outreach messages sent")

    except Exception as e:
        logger.error(f"Prospect re-engagement scan failed: {e}")
        session.rollback()
    finally:
        session.close()


def run_prospect_reengagement_expiry():
    """
    Daily expiry job: expire stale conversations that received no reply.
    Called from SchedulerService cron job.

    Note: System-wide cron job; processes all tenants.
    """
    from database import SessionLocal

    session = SessionLocal()
    try:
        svc = ProspectReEngagementService(session)
        expired_count = svc.expire_stale_conversations()
        logger.info(f"Prospect re-engagement expiry: {expired_count} conversations expired")
    except Exception as e:
        logger.error(f"Prospect re-engagement expiry failed: {e}")
        session.rollback()
    finally:
        session.close()
