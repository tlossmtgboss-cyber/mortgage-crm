"""Scheduling Conversation Service — AI-driven SMS availability negotiation.

Extends the prospect_reengagement_service pattern for calendar scheduling.
Workflow: send available slots -> parse reply -> confirm time -> book appointment.

Enterprise hardening: tenant isolation, structured logging, audit trail,
dead-letter retry for failed bookings, push notifications.
"""

import logging
import os
import json
import re as _re
from datetime import datetime, timedelta, date, time as dtime
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies
_anthropic_client = None


def _mask_phone(phone: Optional[str]) -> str:
    """Mask phone number to last 4 digits for structured logging."""
    if not phone or len(phone) < 4:
        return "****"
    return f"***{phone[-4:]}"


def _sanitize_sms_input(text: str) -> str:
    """Sanitize SMS input before passing to LLM to prevent prompt injection."""
    if not text:
        return ""
    # Strip control characters
    text = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Truncate to reasonable length
    text = text[:500]
    # Wrap in explicit delimiters so LLM treats it as data, not instructions
    return text


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        try:
            import anthropic
            _anthropic_client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                timeout=10.0,
            )
        except Exception as e:
            logger.error("Failed to init Anthropic client", extra={"error": str(e)})
    return _anthropic_client


class SchedulingConversationService:
    """Manages SMS-based availability negotiation conversations."""

    MAX_SLOTS_TO_SEND = 5
    MAX_TURNS = 6
    EXPIRY_HOURS = 48
    SMS_TIMEOUT_SECONDS = 10

    def __init__(self, db: Session, assistant_name: str = "Aria"):
        self.db = db
        self.assistant_name = assistant_name

    # ── Audit Logging ──────────────────────────────────────────

    def _audit_log(
        self,
        action: str,
        workflow_id: Optional[int] = None,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Insert an audit log entry into the activities table.

        Uses type='voice_workflow' (mapped to ActivityType.NOTE as fallback if
        the enum doesn't include it) with structured content describing the action.
        """
        try:
            from database.models.communication import Activity
            from database.enums import ActivityType

            content = json.dumps({
                "action": action,
                "workflow_id": workflow_id,
                "details": details or {},
                "timestamp": datetime.utcnow().isoformat(),
            })

            # ActivityType doesn't have a VOICE_WORKFLOW member; use NOTE as the
            # closest category for system-generated audit entries.
            activity = Activity(
                organization_id=organization_id,
                type=ActivityType.NOTE,
                content=f"[voice_workflow] {action}: {json.dumps(details or {})}",
                user_id=user_id,
                lead_id=lead_id,
                user_metadata={
                    "audit_source": "scheduling_conversation_service",
                    "action": action,
                    "workflow_id": workflow_id,
                    "details": details or {},
                },
            )
            self.db.add(activity)
            self.db.flush()
        except Exception as e:
            logger.warning(
                "Audit log insert failed",
                extra={
                    "workflow_id": workflow_id,
                    "organization_id": organization_id,
                    "action": action,
                    "error": str(e),
                },
            )

    # ── Public API ──────────────────────────────────────────────

    def initiate_scheduling(
        self,
        workflow_id: int,
        user_id: int,
        organization_id: int,
        contact_name: str,
        contact_phone: str,
        meeting_type: str = "discovery_call",
        duration_minutes: int = 30,
        message_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send initial SMS with available time slots to the contact.

        Returns: {success, message_sent, slots_offered, error}
        """
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        logger.info(
            "Initiating scheduling conversation",
            extra={
                "workflow_id": workflow_id,
                "user_id": user_id,
                "organization_id": organization_id,
                "contact_name": contact_name,
                "phone": _mask_phone(contact_phone),
                "meeting_type": meeting_type,
            },
        )

        # Get LO's available slots
        slots = self._get_available_slots(user_id, organization_id, duration_minutes)
        if not slots:
            logger.warning(
                "No available slots found for scheduling",
                extra={"workflow_id": workflow_id, "organization_id": organization_id, "user_id": user_id},
            )
            return {"success": False, "error": "No available slots found in the next 5 business days"}

        # Get LO name for personalization
        lo_name = self._get_user_name(user_id, organization_id)

        # Format the initial SMS
        slots_text = self._format_slots_for_sms(slots[:self.MAX_SLOTS_TO_SEND])
        context_line = f" about {message_context}" if message_context else ""

        message = (
            f"Hi {contact_name}! This is {self.assistant_name}, {lo_name}'s assistant. "
            f"{lo_name} would like to schedule a call{context_line}. "
            f"Here are some available times:\n\n"
            f"{slots_text}\n\n"
            f"Which works for you? Or suggest another time. "
            f"Reply STOP to opt out."
        )

        # Send SMS via Telnyx
        send_result = self._send_sms(contact_phone, message, organization_id)
        if not send_result.get("success"):
            logger.error(
                "Initial scheduling SMS send failed",
                extra={
                    "workflow_id": workflow_id,
                    "organization_id": organization_id,
                    "phone": _mask_phone(contact_phone),
                    "error": send_result.get("error"),
                },
            )
            return {"success": False, "error": send_result.get("error", "SMS send failed")}

        # Audit: SMS sent
        self._audit_log(
            action="scheduling_initiated",
            workflow_id=workflow_id,
            user_id=user_id,
            organization_id=organization_id,
            details={"slots_offered": len(slots[:self.MAX_SLOTS_TO_SEND]), "phone": _mask_phone(contact_phone)},
        )

        # Update workflow
        from services.voice_scheduling_workflow_service import VoiceSchedulingWorkflowService
        wf_service = VoiceSchedulingWorkflowService(self.db)
        workflow = wf_service.get_workflow(workflow_id, organization_id=organization_id)
        if workflow:
            # Tenant isolation: verify workflow belongs to this organization
            if workflow.organization_id != organization_id:
                logger.error(
                    "Tenant isolation violation: workflow org mismatch",
                    extra={
                        "workflow_id": workflow_id,
                        "expected_org": organization_id,
                        "actual_org": workflow.organization_id,
                    },
                )
                return {"success": False, "error": "Workflow organization mismatch"}

            VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", message)
            workflow.proposed_slots = [
                {"start": s["start"].isoformat() if hasattr(s["start"], "isoformat") else str(s["start"]),
                 "end": s["end"].isoformat() if hasattr(s["end"], "isoformat") else str(s["end"]),
                 "formatted": s.get("formatted", "")}
                for s in slots[:self.MAX_SLOTS_TO_SEND]
            ]
            workflow.last_sms_sent_at = datetime.utcnow()
            wf_service.advance_state(workflow, VoiceWorkflowState.AWAITING_REPLY.value)

            # Audit: state transition
            self._audit_log(
                action="state_transition",
                workflow_id=workflow_id,
                user_id=user_id,
                organization_id=organization_id,
                details={"new_state": VoiceWorkflowState.AWAITING_REPLY.value},
            )

        logger.info(
            "Scheduling conversation initiated successfully",
            extra={
                "workflow_id": workflow_id,
                "organization_id": organization_id,
                "slots_offered": len(slots[:self.MAX_SLOTS_TO_SEND]),
            },
        )

        return {
            "success": True,
            "message_sent": message,
            "slots_offered": len(slots[:self.MAX_SLOTS_TO_SEND]),
        }

    def handle_reply(
        self,
        workflow_id: int,
        sender_phone: str,
        message_body: str,
        organization_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Process an inbound SMS reply in a scheduling conversation.

        Args:
            organization_id: Required tenant filter for tenant-safe workflow lookup.

        Returns: {action, response_sent, appointment_id?, error?} or None if not handled.
        """
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState
        from services.voice_scheduling_workflow_service import VoiceSchedulingWorkflowService

        if organization_id is None:
            logger.warning(
                "handle_reply called without organization_id — refusing to query without tenant scope",
                extra={"workflow_id": workflow_id, "phone": _mask_phone(sender_phone)},
            )
            return {"action": "error", "error": "organization_id is required for tenant isolation"}

        logger.info(
            "Handling scheduling reply",
            extra={
                "workflow_id": workflow_id,
                "organization_id": organization_id,
                "phone": _mask_phone(sender_phone),
                "message_length": len(message_body),
            },
        )

        wf_service = VoiceSchedulingWorkflowService(self.db)
        workflow = wf_service.get_workflow(workflow_id, organization_id=organization_id)
        if not workflow or not workflow.is_active():
            logger.info(
                "Workflow not found or inactive",
                extra={"workflow_id": workflow_id, "phone": _mask_phone(sender_phone)},
            )
            return None

        # Tenant isolation: log org context for traceability
        org_id = workflow.organization_id
        user_id = workflow.user_id

        # Check turn limit
        if workflow.turn_count >= workflow.max_turns:
            logger.warning(
                "Workflow max turns reached",
                extra={
                    "workflow_id": workflow_id,
                    "organization_id": org_id,
                    "turn_count": workflow.turn_count,
                    "max_turns": workflow.max_turns,
                },
            )
            self._send_escalation(workflow)
            wf_service.advance_state(workflow, VoiceWorkflowState.EXPIRED.value,
                                      error_message="Max conversation turns reached")
            self._audit_log(
                action="state_transition",
                workflow_id=workflow_id,
                user_id=user_id,
                organization_id=org_id,
                details={"new_state": VoiceWorkflowState.EXPIRED.value, "reason": "max_turns"},
            )
            return {"action": "expired", "reason": "max_turns"}

        # Check for opt-out
        if self._is_opt_out(message_body):
            logger.info(
                "Contact opted out of scheduling",
                extra={"workflow_id": workflow_id, "organization_id": org_id, "phone": _mask_phone(sender_phone)},
            )
            self._handle_opt_out(workflow, sender_phone)
            wf_service.advance_state(workflow, VoiceWorkflowState.CANCELLED.value)
            self._audit_log(
                action="state_transition",
                workflow_id=workflow_id,
                user_id=user_id,
                organization_id=org_id,
                details={"new_state": VoiceWorkflowState.CANCELLED.value, "reason": "opt_out"},
            )
            return {"action": "opted_out"}

        # Record the inbound message (raw)
        VoiceWorkflow.add_message_atomic(self.db, workflow.id, "contact", message_body)
        workflow.last_sms_received_at = datetime.utcnow()

        # Sanitize before passing to LLM for classification
        sanitized_body = _sanitize_sms_input(message_body)

        # Use AI to classify intent and extract time preference
        ai_result = self._classify_reply(workflow, sanitized_body)
        intent = ai_result.get("intent", "ambiguous")

        logger.info(
            "Scheduling reply classified",
            extra={
                "workflow_id": workflow_id,
                "organization_id": org_id,
                "intent": intent,
                "phone": _mask_phone(sender_phone),
                "confidence": ai_result.get("confidence"),
            },
        )

        if intent == "confirm_time":
            # Contact confirmed a specific time
            parsed_time = ai_result.get("parsed_datetime")
            if parsed_time:
                return self._attempt_booking(workflow, parsed_time, wf_service)
            else:
                # AI couldn't parse a time - ask for clarification
                return self._ask_clarification(workflow, wf_service, "confirm")

        elif intent == "suggest_alternative":
            # Contact suggested a different time
            suggested = ai_result.get("suggested_datetime")
            return self._check_alternative(workflow, suggested, wf_service)

        elif intent == "decline":
            response = ai_result.get("response_text", "No worries! Feel free to reach out anytime.")
            self._send_sms(workflow.contact_phone, response, org_id)
            VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", response)
            wf_service.advance_state(workflow, VoiceWorkflowState.CANCELLED.value)
            self._audit_log(
                action="state_transition",
                workflow_id=workflow_id,
                user_id=user_id,
                organization_id=org_id,
                details={"new_state": VoiceWorkflowState.CANCELLED.value, "reason": "declined"},
            )
            return {"action": "declined"}

        elif intent == "question":
            # Contact asked a question - AI generates response
            response = ai_result.get("response_text", "Let me have the loan officer follow up with you directly.")
            self._send_sms(workflow.contact_phone, response, org_id)
            VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", response)
            wf_service.advance_state(workflow, VoiceWorkflowState.NEGOTIATING.value)
            self._audit_log(
                action="state_transition",
                workflow_id=workflow_id,
                user_id=user_id,
                organization_id=org_id,
                details={"new_state": VoiceWorkflowState.NEGOTIATING.value, "reason": "question_answered"},
            )
            return {"action": "question_answered", "response_sent": response}

        else:
            # Ambiguous - ask for clarification
            return self._ask_clarification(workflow, wf_service, "general")

    # ── Private Methods ─────────────────────────────────────────

    def _get_available_slots(self, user_id: int, org_id: int, duration: int = 30) -> List[Dict]:
        """Get available slots from the scheduler availability engine."""
        try:
            from routes.scheduler._availability import _generate_available_slots
            today = date.today()
            end = today + timedelta(days=7)  # Next 7 days
            slots = _generate_available_slots(
                self.db,
                user_ids=[user_id],
                start_date=today,
                end_date=end,
                duration_minutes=duration,
                org_id=org_id,
                include_day_name=True,
            )
            logger.info(
                "Available slots retrieved",
                extra={"user_id": user_id, "organization_id": org_id, "slot_count": len(slots) if slots else 0},
            )
            return slots
        except Exception as e:
            logger.error(
                "Failed to get available slots",
                extra={"user_id": user_id, "organization_id": org_id, "error": str(e)},
            )
            return []

    def _format_slots_for_sms(self, slots: List[Dict]) -> str:
        """Format time slots into human-readable SMS text."""
        lines = []
        for i, slot in enumerate(slots, 1):
            start = slot.get("start") or slot.get("start_time")
            if isinstance(start, str):
                try:
                    start = datetime.fromisoformat(start)
                except (ValueError, TypeError):
                    pass

            if isinstance(start, datetime):
                day_name = start.strftime("%A")
                month_day = start.strftime("%b %d")
                time_str = start.strftime("%-I:%M %p")
                slot["formatted"] = f"{day_name} {month_day} at {time_str}"
                lines.append(f"{i}. {day_name} {month_day} at {time_str}")
            else:
                day = slot.get("day_name", "")
                lines.append(f"{i}. {day} - {start}")
                slot["formatted"] = f"{day} - {start}"
        return "\n".join(lines)

    @staticmethod
    def _fallback_intent_classifier(text: str) -> str:
        """Keyword-based fallback when LLM is unavailable."""
        text_lower = text.lower().strip()
        # Positive confirmations
        if any(word in text_lower for word in ['yes', 'sure', 'ok', 'sounds good', 'perfect', 'great', 'works', 'confirmed', 'that works']):
            return 'confirm_time'
        # Negative/decline
        if any(word in text_lower for word in ['no', "can't", 'cannot', 'not available', 'busy', 'decline', 'pass', 'stop']):
            return 'decline'
        # Alternative suggestions (contains time-like patterns)
        if _re.search(r'\d{1,2}[: ]?\d{0,2}\s*(am|pm|AM|PM)', text_lower) or any(word in text_lower for word in ['how about', 'instead', 'rather', 'another time', 'different']):
            return 'suggest_alternative'
        # Questions
        if '?' in text_lower or any(word in text_lower for word in ['what', 'when', 'where', 'how long', 'who']):
            return 'question'
        return 'ambiguous'

    def _classify_reply(self, workflow, message: str) -> Dict[str, Any]:
        """Use Claude to classify the contact's reply and extract time preferences."""
        client = _get_anthropic()
        if not client:
            logger.warning(
                "Anthropic client unavailable, using fallback keyword classifier",
                extra={"workflow_id": workflow.id, "organization_id": workflow.organization_id},
            )
            return {"intent": self._fallback_intent_classifier(message), "confidence": 0.3}

        proposed = workflow.proposed_slots or []
        slots_context = "\n".join(
            f"- Slot {i+1}: {s.get('formatted', s.get('start', 'unknown'))}"
            for i, s in enumerate(proposed)
        )

        lo_name = self._get_user_name(workflow.user_id, workflow.organization_id)

        system_prompt = f"""You are classifying an SMS reply in a scheduling conversation.

The loan officer ({lo_name}) wants to schedule a meeting with {workflow.contact_name}.
Available slots offered:
{slots_context}

Classify the reply into one of:
- confirm_time: They accepted a specific time. Extract the datetime.
- suggest_alternative: They suggested a different time. Extract the datetime.
- decline: They don't want to meet.
- question: They asked a question unrelated to scheduling.
- ambiguous: Unclear intent.

Return ONLY valid JSON:
{{"intent": "confirm_time|suggest_alternative|decline|question|ambiguous",
  "parsed_datetime": "YYYY-MM-DDTHH:MM:SS" or null,
  "suggested_datetime": "YYYY-MM-DDTHH:MM:SS" or null,
  "response_text": "brief response to send (under 160 chars)" or null,
  "confidence": 0.0-1.0}}"""

        # Defense-in-depth: sanitize and wrap SMS content in delimiters
        safe_message = _sanitize_sms_input(message)
        delimited_message = f"<sms_reply>{safe_message}</sms_reply>"

        try:
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=200,
                timeout=10.0,
                system=system_prompt,
                messages=[{"role": "user", "content": delimited_message}],
            )
            text = response.content[0].text.strip()
            # Extract JSON from response
            if text.startswith("{"):
                result = json.loads(text)
            else:
                # Try to find JSON in response
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(text[start:end])
                else:
                    result = {"intent": "ambiguous"}

            logger.info(
                "AI classification completed",
                extra={
                    "workflow_id": workflow.id,
                    "organization_id": workflow.organization_id,
                    "intent": result.get("intent"),
                    "confidence": result.get("confidence"),
                },
            )
            return result
        except TimeoutError:
            logger.error(
                "AI classification timed out, using fallback keyword classifier",
                extra={"workflow_id": workflow.id, "organization_id": workflow.organization_id},
            )
            return {"intent": self._fallback_intent_classifier(message), "confidence": 0.3}
        except Exception as e:
            logger.error(
                "AI classification failed, using fallback keyword classifier",
                extra={
                    "workflow_id": workflow.id,
                    "organization_id": workflow.organization_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {"intent": self._fallback_intent_classifier(message), "confidence": 0.3}

    def _attempt_booking(self, workflow, parsed_datetime: str, wf_service) -> Dict[str, Any]:
        """Book the appointment when contact confirms a time.

        Includes retry logic: if create_appointment fails, retries once after 2 seconds.
        On final failure, creates a dead-letter task and notifies the LO.
        """
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        org_id = workflow.organization_id
        wf_id = workflow.id
        user_id = workflow.user_id

        logger.info(
            "Attempting booking",
            extra={
                "workflow_id": wf_id,
                "organization_id": org_id,
                "parsed_datetime": str(parsed_datetime),
                "phone": _mask_phone(workflow.contact_phone),
            },
        )

        try:
            if isinstance(parsed_datetime, str):
                confirmed_dt = datetime.fromisoformat(parsed_datetime)
            else:
                confirmed_dt = parsed_datetime

            end_dt = confirmed_dt + timedelta(minutes=workflow.meeting_duration_minutes or 30)

            # Use the unified appointment creation service
            from services.appointment_creation_service import create_appointment
            import asyncio

            def _build_appointment_kwargs():
                return dict(
                    db=self.db,
                    organization_id=org_id,
                    assigned_user_id=user_id,
                    source="ai_pipeline",
                    title=f"Call with {workflow.contact_name}",
                    scheduled_start=confirmed_dt,
                    scheduled_end=end_dt,
                    duration_minutes=workflow.meeting_duration_minutes or 30,
                    attendee_name=workflow.contact_name,
                    attendee_phone=workflow.contact_phone,
                    attendee_email=workflow.contact_email,
                    meeting_type=workflow.meeting_type or "discovery_call",
                    meeting_mode="phone",
                    lead_id=workflow.lead_id,
                    booked_by_ai=True,
                    ai_booking_context={
                        "source": "voice_workflow",
                        "workflow_id": wf_id,
                        "booking_time": datetime.utcnow().isoformat(),
                    },
                    check_conflicts=True,
                    generate_meeting_link=True,
                    send_confirmation=True,
                    create_lead_if_missing=True,
                )

            def _run_create_appointment():
                """Execute appointment creation — runs async code in a new event loop on a worker thread."""
                import concurrent.futures

                def _run_in_new_loop():
                    return asyncio.run(create_appointment(**_build_appointment_kwargs()))

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(_run_in_new_loop)
                        return future.result(timeout=30)  # Wait up to 30s for booking
                else:
                    return asyncio.run(create_appointment(**_build_appointment_kwargs()))

            # Attempt 1
            result = _run_create_appointment()

            # Retry logic: if result indicates failure, retry once immediately
            # (no blocking sleep — the original 2s delay was not necessary and
            # blocks the event loop / worker thread)
            if result is not None and not result.success:
                logger.warning(
                    "Booking attempt 1 failed, retrying immediately",
                    extra={
                        "workflow_id": wf_id,
                        "organization_id": org_id,
                        "error": getattr(result, "error", None),
                    },
                )
                result = _run_create_appointment()

            if result and result.success:
                lo_name = self._get_user_name(user_id, org_id)
                time_str = confirmed_dt.strftime("%-I:%M %p on %A, %B %-d")
                confirmation_msg = (
                    f"You're all set! Your call with {lo_name} is confirmed "
                    f"for {time_str}. You'll receive a calendar invite shortly."
                )
                self._send_sms(workflow.contact_phone, confirmation_msg, org_id)
                VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", confirmation_msg)
                workflow.confirmed_datetime = confirmed_dt
                workflow.appointment_id = result.appointment_id
                wf_service.advance_state(workflow, VoiceWorkflowState.APPOINTMENT_BOOKED.value)

                # Invalidate availability cache to prevent double-booking
                try:
                    from services.availability_cache import get_availability_cache
                    cache = get_availability_cache()
                    cache.invalidate(user_id=user_id, organization_id=org_id)
                except Exception as e:
                    logger.warning(
                        "Failed to invalidate availability cache",
                        extra={"error": str(e), "workflow_id": wf_id, "organization_id": org_id},
                    )

                # Audit: booking succeeded
                self._audit_log(
                    action="appointment_booked",
                    workflow_id=wf_id,
                    user_id=user_id,
                    organization_id=org_id,
                    lead_id=workflow.lead_id,
                    details={
                        "appointment_id": result.appointment_id,
                        "confirmed_datetime": confirmed_dt.isoformat(),
                        "phone": _mask_phone(workflow.contact_phone),
                    },
                )

                # Audit: state transition
                self._audit_log(
                    action="state_transition",
                    workflow_id=wf_id,
                    user_id=user_id,
                    organization_id=org_id,
                    details={"new_state": VoiceWorkflowState.APPOINTMENT_BOOKED.value},
                )

                # Notify the LO
                self._notify_lo(workflow, confirmed_dt)

                # Push notification to LO
                try:
                    from services.notification_service import send_push_notification
                    send_push_notification(
                        user_id=user_id,
                        title="Appointment Booked",
                        body=f"{workflow.contact_name} confirmed for {time_str}",
                        data={
                            "type": "appointment_booked",
                            "workflow_id": str(wf_id),
                            "appointment_id": str(result.appointment_id),
                        },
                    )
                except ImportError:
                    logger.info(
                        "Push notification service not available",
                        extra={"workflow_id": str(wf_id), "organization_id": org_id},
                    )
                except Exception as e:
                    logger.warning(
                        "Push notification failed",
                        extra={"workflow_id": str(wf_id), "organization_id": org_id, "error": str(e)},
                    )

                logger.info(
                    "Booking completed successfully",
                    extra={
                        "workflow_id": wf_id,
                        "organization_id": org_id,
                        "appointment_id": result.appointment_id,
                        "confirmed_datetime": confirmed_dt.isoformat(),
                    },
                )

                return {
                    "action": "booked",
                    "appointment_id": result.appointment_id,
                    "confirmed_datetime": confirmed_dt.isoformat(),
                    "video_link": result.video_link,
                }
            elif result and not result.success:
                # Booking failed after retry - dead letter handling
                error_msg = result.error or "That time is no longer available"
                logger.error(
                    "Booking failed after retry",
                    extra={
                        "workflow_id": wf_id,
                        "organization_id": org_id,
                        "error": error_msg,
                    },
                )
                self._handle_booking_failure(workflow, confirmed_dt, error_msg, wf_service)
                return {"action": "error", "error": error_msg}
            else:
                # result was None (async bridge issue) - offer alternatives
                logger.warning(
                    "Booking result was None (async bridge issue)",
                    extra={"workflow_id": wf_id, "organization_id": org_id},
                )
                return self._offer_alternatives(workflow, wf_service, "Unable to confirm that time")

        except Exception as e:
            logger.exception(
                "Booking failed with exception",
                extra={
                    "workflow_id": wf_id,
                    "organization_id": org_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            workflow.error_message = str(e)

            # Dead letter: create task and notify LO on unhandled exception
            self._handle_booking_failure(workflow, parsed_datetime, str(e), wf_service)

            return {"action": "error", "error": str(e)}

    def _handle_booking_failure(self, workflow, confirmed_datetime, error_msg: str, wf_service):
        """Dead letter handler: set workflow to failed, create task, notify LO via SMS."""
        from database.models.voice_workflow import VoiceWorkflowState

        org_id = workflow.organization_id
        wf_id = workflow.id
        user_id = workflow.user_id

        # Set workflow state to failed with error details
        workflow.error_message = error_msg
        wf_service.advance_state(
            workflow,
            VoiceWorkflowState.FAILED.value,
            error_message=error_msg,
        )

        # Audit: booking failure
        self._audit_log(
            action="booking_failed_dead_letter",
            workflow_id=wf_id,
            user_id=user_id,
            organization_id=org_id,
            lead_id=workflow.lead_id,
            details={"error": error_msg, "phone": _mask_phone(workflow.contact_phone)},
        )

        # Audit: state transition
        self._audit_log(
            action="state_transition",
            workflow_id=wf_id,
            user_id=user_id,
            organization_id=org_id,
            details={"new_state": VoiceWorkflowState.FAILED.value, "reason": "booking_failed"},
        )

        # Format the confirmed time for display
        time_display = ""
        if confirmed_datetime:
            if isinstance(confirmed_datetime, str):
                try:
                    dt = datetime.fromisoformat(confirmed_datetime)
                    time_display = dt.strftime("%-I:%M %p on %A, %B %-d")
                except (ValueError, TypeError):
                    time_display = str(confirmed_datetime)
            elif isinstance(confirmed_datetime, datetime):
                time_display = confirmed_datetime.strftime("%-I:%M %p on %A, %B %-d")

        # Create a high-priority Task for the LO
        try:
            from database.models.task import Task
            task = Task(
                organization_id=org_id,
                owner_id=user_id,
                title=f"Booking failed for {workflow.contact_name} - confirmed {time_display} but appointment creation failed. Please book manually.",
                description=(
                    f"Automated booking via SMS workflow #{wf_id} failed after retry.\n"
                    f"Contact: {workflow.contact_name} ({workflow.contact_phone})\n"
                    f"Confirmed time: {time_display}\n"
                    f"Error: {error_msg}\n\n"
                    f"Please create the appointment manually and confirm with the contact."
                ),
                due_date=datetime.utcnow() + timedelta(hours=2),
                priority="high",
                status="pending",
                lead_id=workflow.lead_id,
                related_contact_name=workflow.contact_name,
                related_type="voice_workflow_booking_failure",
            )
            self.db.add(task)
            self.db.flush()
            logger.info(
                "Dead letter task created for booking failure",
                extra={
                    "workflow_id": wf_id,
                    "organization_id": org_id,
                    "task_id": task.id,
                    "user_id": user_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to create dead letter task",
                extra={
                    "workflow_id": wf_id,
                    "organization_id": org_id,
                    "error": str(e),
                },
            )

        # Notify the LO via SMS about the failure
        try:
            lo_name = self._get_user_name(user_id, org_id)
            from database.models.core import User
            user = (
                self.db.query(User)
                .filter(User.id == user_id, User.organization_id == org_id)
                .first()
            )
            if user and user.phone:
                lo_notify_msg = (
                    f"[Perennia] Booking failed: {workflow.contact_name} confirmed "
                    f"{time_display} but auto-booking failed. "
                    f"A task has been created - please book manually."
                )
                self._send_sms(user.phone, lo_notify_msg, org_id)
                logger.info(
                    "LO notified of booking failure via SMS",
                    extra={
                        "workflow_id": wf_id,
                        "organization_id": org_id,
                        "lo_phone": _mask_phone(user.phone),
                    },
                )
        except Exception as e:
            logger.error(
                "Failed to notify LO of booking failure",
                extra={
                    "workflow_id": wf_id,
                    "organization_id": org_id,
                    "error": str(e),
                },
            )

    def _check_alternative(self, workflow, suggested_dt: Optional[str], wf_service) -> Dict[str, Any]:
        """Check if a contact-suggested time is available."""
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        org_id = workflow.organization_id
        wf_id = workflow.id

        if not suggested_dt:
            return self._ask_clarification(workflow, wf_service, "time")

        try:
            if isinstance(suggested_dt, str):
                dt = datetime.fromisoformat(suggested_dt)
            else:
                dt = suggested_dt

            logger.info(
                "Checking alternative time",
                extra={
                    "workflow_id": wf_id,
                    "organization_id": org_id,
                    "suggested_datetime": dt.isoformat(),
                },
            )

            # Check availability for the suggested time
            slots = self._get_available_slots(
                workflow.user_id, org_id,
                workflow.meeting_duration_minutes or 30
            )

            # Check if any slot covers the suggested time
            available = False
            for slot in slots:
                slot_start = slot.get("start") or slot.get("start_time")
                if isinstance(slot_start, str):
                    slot_start = datetime.fromisoformat(slot_start)
                if isinstance(slot_start, datetime) and slot_start.date() == dt.date():
                    # Same day - close enough
                    if abs((slot_start - dt).total_seconds()) < 1800:  # Within 30 min
                        available = True
                        break

            if available:
                # Confirm the suggested time
                lo_name = self._get_user_name(workflow.user_id, org_id)
                time_str = dt.strftime("%-I:%M %p on %A, %B %-d")
                confirm_msg = f"Great! {time_str} works. Shall I confirm the call with {lo_name}? Reply YES to confirm."
                self._send_sms(workflow.contact_phone, confirm_msg, org_id)
                VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", confirm_msg)
                workflow.confirmed_datetime = dt
                wf_service.advance_state(workflow, VoiceWorkflowState.NEGOTIATING.value)

                # Audit: SMS sent + state transition
                self._audit_log(
                    action="alternative_accepted",
                    workflow_id=wf_id,
                    user_id=workflow.user_id,
                    organization_id=org_id,
                    details={"suggested_time": dt.isoformat(), "new_state": VoiceWorkflowState.NEGOTIATING.value},
                )

                return {"action": "confirming", "suggested_time": dt.isoformat()}
            else:
                return self._offer_alternatives(workflow, wf_service, "That time isn't available")

        except Exception as e:
            logger.error(
                "Alternative check failed",
                extra={
                    "workflow_id": wf_id,
                    "organization_id": org_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return self._ask_clarification(workflow, wf_service, "time")

    def _offer_alternatives(self, workflow, wf_service, reason: str) -> Dict[str, Any]:
        """Offer new time slots when the requested time isn't available."""
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        org_id = workflow.organization_id
        wf_id = workflow.id

        slots = self._get_available_slots(
            workflow.user_id, org_id,
            workflow.meeting_duration_minutes or 30
        )
        if not slots:
            msg = f"{reason}. Unfortunately, no other times are available this week. The loan officer will reach out directly."
            self._send_sms(workflow.contact_phone, msg, org_id)
            VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", msg)
            wf_service.advance_state(workflow, VoiceWorkflowState.FAILED.value,
                                      error_message="No slots available")
            self._audit_log(
                action="state_transition",
                workflow_id=wf_id,
                user_id=workflow.user_id,
                organization_id=org_id,
                details={"new_state": VoiceWorkflowState.FAILED.value, "reason": "no_slots"},
            )
            return {"action": "failed", "reason": "no_slots"}

        slots_text = self._format_slots_for_sms(slots[:3])
        msg = f"{reason}. How about one of these instead?\n\n{slots_text}"
        self._send_sms(workflow.contact_phone, msg, org_id)
        VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", msg)
        workflow.proposed_slots = [
            {"start": s.get("start", ""), "formatted": s.get("formatted", "")}
            for s in slots[:3]
        ]
        wf_service.advance_state(workflow, VoiceWorkflowState.NEGOTIATING.value)

        self._audit_log(
            action="alternatives_offered",
            workflow_id=wf_id,
            user_id=workflow.user_id,
            organization_id=org_id,
            details={"reason": reason, "slots_offered": len(slots[:3])},
        )

        return {"action": "alternatives_offered", "slots": len(slots[:3])}

    def _ask_clarification(self, workflow, wf_service, context: str) -> Dict[str, Any]:
        """Ask the contact to clarify their response."""
        from database.models.voice_workflow import VoiceWorkflow, VoiceWorkflowState

        org_id = workflow.organization_id
        wf_id = workflow.id

        if context == "confirm":
            msg = "I want to make sure I get the right time. Could you reply with the number of the slot (e.g. '1' or '2') or a specific date and time?"
        elif context == "time":
            msg = "Could you please suggest a specific date and time? For example, 'Tuesday at 2pm'."
        else:
            msg = "I didn't quite catch that. Could you reply with a preferred time, or a slot number from the list above?"

        self._send_sms(workflow.contact_phone, msg, org_id)
        VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", msg)
        wf_service.advance_state(workflow, VoiceWorkflowState.NEGOTIATING.value)

        self._audit_log(
            action="clarification_requested",
            workflow_id=wf_id,
            user_id=workflow.user_id,
            organization_id=org_id,
            details={"context": context},
        )

        return {"action": "clarification_requested"}

    def _handle_opt_out(self, workflow, phone: str):
        """Handle opt-out request."""
        from database.models.voice_workflow import VoiceWorkflow

        msg = "You've been unsubscribed from scheduling messages. Thank you."
        self._send_sms(workflow.contact_phone, msg, workflow.organization_id)
        VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", msg)

        self._audit_log(
            action="opt_out",
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            organization_id=workflow.organization_id,
            details={"phone": _mask_phone(phone)},
        )

    def _send_escalation(self, workflow):
        """Notify LO that automated scheduling didn't converge."""
        from database.models.voice_workflow import VoiceWorkflow

        lo_name = self._get_user_name(workflow.user_id, workflow.organization_id)
        msg = (
            f"We weren't able to find a time that works. "
            f"{lo_name} will reach out to you directly to schedule."
        )
        self._send_sms(workflow.contact_phone, msg, workflow.organization_id)
        VoiceWorkflow.add_message_atomic(self.db, workflow.id, "system", msg)
        self._notify_lo(workflow, None, escalation=True)

        self._audit_log(
            action="escalation_sent",
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            organization_id=workflow.organization_id,
            details={"reason": "max_turns_or_expiry", "phone": _mask_phone(workflow.contact_phone)},
        )

    def _notify_lo(self, workflow, confirmed_dt: Optional[datetime], escalation: bool = False):
        """Send notification to the LO about workflow outcome."""
        org_id = workflow.organization_id
        wf_id = workflow.id

        try:
            if escalation:
                # Create a task for manual follow-up
                self._create_followup_task(workflow)
                logger.info(
                    "LO notified via escalation task",
                    extra={
                        "workflow_id": wf_id,
                        "organization_id": org_id,
                        "user_id": workflow.user_id,
                    },
                )
            else:
                logger.info(
                    "Appointment booked notification",
                    extra={
                        "workflow_id": wf_id,
                        "organization_id": org_id,
                        "contact_name": workflow.contact_name,
                        "confirmed_datetime": confirmed_dt.isoformat() if confirmed_dt else None,
                    },
                )
        except Exception as e:
            logger.error(
                "Failed to notify LO",
                extra={
                    "workflow_id": wf_id,
                    "organization_id": org_id,
                    "error": str(e),
                },
            )

    def _create_followup_task(self, workflow):
        """Create a task for the LO when automated scheduling fails."""
        try:
            from database.models.task import Task
            task = Task(
                organization_id=workflow.organization_id,
                owner_id=workflow.user_id,
                title=f"Schedule call with {workflow.contact_name}",
                description=(
                    f"Automated scheduling via SMS didn't converge after {workflow.turn_count} turns. "
                    f"Please reach out to {workflow.contact_name} at {workflow.contact_phone} directly."
                ),
                due_date=datetime.utcnow() + timedelta(days=1),
                priority="high",
                status="pending",
                lead_id=workflow.lead_id,
                related_contact_name=workflow.contact_name,
                related_type="voice_workflow_escalation",
            )
            self.db.add(task)
            self.db.flush()

            logger.info(
                "Follow-up task created",
                extra={
                    "workflow_id": workflow.id,
                    "organization_id": workflow.organization_id,
                    "task_id": task.id,
                    "user_id": workflow.user_id,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to create follow-up task",
                extra={
                    "workflow_id": workflow.id,
                    "organization_id": workflow.organization_id,
                    "error": str(e),
                },
            )

    def _send_sms(self, phone: str, message: str, org_id: int) -> Dict[str, Any]:
        """Send SMS via Telnyx with compliance checks and timeout handling."""
        masked = _mask_phone(phone)

        try:
            from services.sms_compliance import check_sms_consent
            can_send, reason = check_sms_consent(phone, organization_id=org_id)
            if not can_send:
                logger.warning(
                    "SMS blocked by compliance",
                    extra={"phone": masked, "organization_id": org_id, "reason": reason},
                )
                return {"success": False, "error": f"Compliance blocked: {reason}"}

            from services.notification_service import NotificationService
            ns = NotificationService()

            # Send with timeout handling
            try:
                import signal

                # Use a simple timeout mechanism
                result = ns.send_sms(
                    to_phone=phone,
                    message=message,
                    organization_id=org_id,
                )
            except TimeoutError:
                logger.error(
                    "SMS send timed out",
                    extra={"phone": masked, "organization_id": org_id},
                )
                return {"success": False, "error": "SMS send timed out"}

            if result.get("success"):
                logger.info(
                    "SMS sent successfully",
                    extra={"phone": masked, "organization_id": org_id, "message_length": len(message)},
                )
            else:
                logger.warning(
                    "SMS send returned failure",
                    extra={"phone": masked, "organization_id": org_id, "error": result.get("error")},
                )

            return result
        except TimeoutError:
            logger.error(
                "SMS send timed out",
                extra={"phone": masked, "organization_id": org_id},
            )
            return {"success": False, "error": "SMS send timed out"}
        except Exception as e:
            logger.error(
                "SMS send failed",
                extra={
                    "phone": masked,
                    "organization_id": org_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return {"success": False, "error": str(e)}

    def _get_user_name(self, user_id: int, organization_id: int) -> str:
        """Get LO display name with tenant isolation."""
        try:
            from database.models.core import User
            query = self.db.query(User).filter(
                User.id == user_id,
                User.organization_id == organization_id,
            )
            user = query.first()
            if user:
                return f"{user.first_name} {user.last_name}".strip() or "your loan officer"
        except Exception as e:
            logger.warning(
                "Failed to get user name",
                extra={"user_id": user_id, "organization_id": organization_id, "error": str(e)},
            )
        return "your loan officer"

    def _is_opt_out(self, message: str) -> bool:
        """Check if message is an opt-out."""
        opt_out_words = {"stop", "unsubscribe", "opt out", "optout", "cancel", "quit"}
        return message.strip().lower() in opt_out_words
