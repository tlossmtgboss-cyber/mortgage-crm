"""
Public Mortgage Chat Service

AI-powered mortgage assistant for microsite visitors:
- Answers mortgage and lending questions
- Checks loan officer availability
- Books appointments with smart scheduling
- No authentication required (public facing)
"""

import os
import json
import logging
import uuid
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Get API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


class PublicMortgageChatService:
    """
    Public-facing AI mortgage assistant that can:
    - Answer mortgage questions
    - Check LO availability
    - Schedule appointments
    """

    def __init__(self, db: Session, user_slug: str):
        self.db = db
        self.user_slug = user_slug
        self.lo_info = None
        self.scheduler_settings = None
        self._load_loan_officer_info()

    def _load_loan_officer_info(self):
        """Load loan officer information for context"""
        from database.models import User
        from microsite_models import UserMicrosite

        # Get user by slug
        user = self.db.query(User).filter(User.slug == self.user_slug).first()
        if not user:
            logger.warning(f"User not found for slug: {self.user_slug}")
            return

        # Get user's bio from metadata
        bio = ""
        if user.user_metadata and isinstance(user.user_metadata, dict):
            bio = user.user_metadata.get("bio", "")

        self.lo_info = {
            "id": user.id,
            "name": user.full_name or self.user_slug.replace("-", " ").title(),
            "email": user.email,
            "phone": getattr(user, 'phone', None),
            "nmls_id": getattr(user, 'nmls_id', None),
            "bio": bio,
            "company": getattr(user, 'company', None),
            "organization_id": getattr(user, 'organization_id', None),
        }

        # Try to load scheduler settings for this user
        self._load_scheduler_settings(user.id)

    def _load_scheduler_settings(self, user_id: int):
        """Load scheduler settings and availability from User Profile work hours"""
        try:
            from services.smart_scheduler_service import SchedulerSettings, LoanOfficerSchedule, ScheduledAppointment

            # First, try to get work hours from User Profile (business_hours field)
            try:
                from database.models import User
                user = self.db.query(User).filter(User.id == user_id).first()
                if user and hasattr(user, 'business_hours') and user.business_hours:
                    user_hours = user.business_hours
                    work_start = user_hours.get('start', '09:00')
                    work_end = user_hours.get('end', '17:00')
                    work_days = user_hours.get('days', ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'])

                    # Convert user profile work hours to business_hours format
                    profile_business_hours = {}
                    all_days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    for day in all_days:
                        profile_business_hours[day] = {
                            "start": work_start,
                            "end": work_end,
                            "enabled": day in [d.lower() for d in work_days]
                        }

                    self.scheduler_settings = {
                        "business_hours": profile_business_hours,
                        "default_duration_minutes": 30,
                        "buffer_between_appointments": 15,
                        "min_notice_hours": 2,
                        "max_advance_days": 30,
                    }
                    logger.info(f"Loaded work hours from user profile: days={work_days}, {work_start}-{work_end}")
            except Exception as profile_err:
                logger.warning(f"Could not load user profile work hours: {profile_err}")

            # Get scheduler settings (override if exists) — filter by org for tenant isolation
            org_id = self.lo_info.get("organization_id") if self.lo_info else None
            settings = self.db.query(SchedulerSettings).filter(
                SchedulerSettings.user_id == user_id
            ).first()

            if not settings and org_id:
                # Fallback to org-level settings
                settings = self.db.query(SchedulerSettings).filter(
                    SchedulerSettings.organization_id == org_id
                ).first()

            if settings and settings.business_hours:
                # Only override if scheduler settings has actual business_hours configured
                self.scheduler_settings = self.scheduler_settings or {}
                self.scheduler_settings.update({
                    "business_hours": settings.business_hours,
                    "default_duration_minutes": settings.default_duration_minutes or 30,
                    "buffer_between_appointments": settings.buffer_between_appointments or 15,
                    "min_notice_hours": settings.min_notice_hours or 2,
                    "max_advance_days": settings.max_advance_days or 30,
                })

            # Get LO schedule if exists
            lo_schedule = self.db.query(LoanOfficerSchedule).filter(
                LoanOfficerSchedule.user_id == user_id
            ).first()

            if lo_schedule:
                self.scheduler_settings = self.scheduler_settings or {}
                self.scheduler_settings["custom_hours"] = lo_schedule.custom_hours
                self.scheduler_settings["blocked_times"] = lo_schedule.blocked_times or []

        except SQLAlchemyError as e:
            logger.warning(f"Could not load scheduler settings: {e}")
            self.scheduler_settings = None

    def get_available_slots(self, date: datetime = None, days_ahead: int = 7) -> List[Dict]:
        """Get available time slots for the next N days"""
        if not self.lo_info:
            return []

        available_slots = []
        start_date = date or datetime.now()

        # Default business hours if no settings
        default_hours = {
            "monday": {"start": "09:00", "end": "17:00", "enabled": True},
            "tuesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "wednesday": {"start": "09:00", "end": "17:00", "enabled": True},
            "thursday": {"start": "09:00", "end": "17:00", "enabled": True},
            "friday": {"start": "09:00", "end": "17:00", "enabled": True},
            "saturday": {"start": "10:00", "end": "14:00", "enabled": False},
            "sunday": {"start": "00:00", "end": "00:00", "enabled": False},
        }

        business_hours = default_hours
        if self.scheduler_settings:
            business_hours = self.scheduler_settings.get("business_hours", default_hours)

        duration = 30  # Default 30 min slots
        buffer = 15
        if self.scheduler_settings:
            duration = self.scheduler_settings.get("default_duration_minutes", 30)
            buffer = self.scheduler_settings.get("buffer_between_appointments", 15)

        # Get existing appointments
        existing_appointments = self._get_existing_appointments(start_date, days_ahead)

        for day_offset in range(days_ahead):
            check_date = start_date + timedelta(days=day_offset)
            day_name = check_date.strftime("%A").lower()

            hours = business_hours.get(day_name, {})
            if not hours.get("enabled", False):
                continue

            start_time_str = hours.get("start", "09:00")
            end_time_str = hours.get("end", "17:00")

            try:
                start_hour, start_min = map(int, start_time_str.split(":"))
                end_hour, end_min = map(int, end_time_str.split(":"))
            except Exception as e:
                logger.warning(f"Error parsing business hours for {day_name}: {e}")
                continue

            # Generate slots for this day
            current_time = check_date.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            day_end = check_date.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)

            # Skip if we're already past this day's end
            if day_offset == 0 and current_time < datetime.now():
                # Start from current time rounded up to next slot
                now = datetime.now()
                min_notice = 2
                if self.scheduler_settings:
                    min_notice = self.scheduler_settings.get("min_notice_hours", 2)
                earliest = now + timedelta(hours=min_notice)

                if earliest > current_time:
                    # Round up to next slot
                    minutes = earliest.minute
                    rounded_minutes = ((minutes // 30) + 1) * 30
                    if rounded_minutes >= 60:
                        earliest = earliest.replace(hour=earliest.hour + 1, minute=0)
                    else:
                        earliest = earliest.replace(minute=rounded_minutes)
                    current_time = earliest.replace(second=0, microsecond=0)

            while current_time + timedelta(minutes=duration) <= day_end:
                slot_end = current_time + timedelta(minutes=duration)

                # Check if slot conflicts with existing appointments
                is_available = True
                for appt in existing_appointments:
                    appt_start = appt.get("start_time")
                    appt_end = appt.get("end_time")
                    if appt_start and appt_end:
                        # Add buffer
                        appt_start_with_buffer = appt_start - timedelta(minutes=buffer)
                        appt_end_with_buffer = appt_end + timedelta(minutes=buffer)

                        if (current_time < appt_end_with_buffer and slot_end > appt_start_with_buffer):
                            is_available = False
                            break

                if is_available:
                    available_slots.append({
                        "date": check_date.strftime("%Y-%m-%d"),
                        "day": check_date.strftime("%A"),
                        "start_time": current_time.strftime("%H:%M"),
                        "end_time": slot_end.strftime("%H:%M"),
                        "display": f"{check_date.strftime('%A, %B %d')} at {current_time.strftime('%I:%M %p')}"
                    })

                current_time += timedelta(minutes=duration + buffer)

        return available_slots[:20]  # Return up to 20 slots

    def _get_existing_appointments(self, start_date: datetime, days_ahead: int) -> List[Dict]:
        """Get existing appointments for the time range"""
        if not self.lo_info:
            return []

        try:
            from services.smart_scheduler_service import ScheduledAppointment

            end_date = start_date + timedelta(days=days_ahead)
            org_id = self.lo_info.get("organization_id")

            filters = [
                ScheduledAppointment.loan_officer_id == self.lo_info["id"],
                ScheduledAppointment.start_time >= start_date,
                ScheduledAppointment.start_time <= end_date,
                ScheduledAppointment.status.in_(["scheduled", "confirmed"]),
            ]
            if org_id:
                filters.append(ScheduledAppointment.organization_id == org_id)

            appointments = self.db.query(ScheduledAppointment).filter(
                and_(*filters)
            ).all()

            return [
                {
                    "start_time": a.start_time,
                    "end_time": a.end_time,
                    "status": a.status
                }
                for a in appointments
            ]
        except Exception as e:
            logger.warning(f"Could not load appointments: {e}")
            return []

    def book_appointment(
        self,
        contact_name: str,
        contact_email: str,
        appointment_time: datetime,
        contact_phone: Optional[str] = None,
        appointment_type: str = "consultation",
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Book an appointment with the loan officer and create a lead"""
        if not self.lo_info:
            return {"success": False, "error": "Loan officer not found"}

        try:
            from services.smart_scheduler_service import ScheduledAppointment, AppointmentStatus
            from database.enums import LeadStage
            from database.models import Lead

            # Generate appointment ID
            appointment_id = f"APPT-{uuid.uuid4().hex[:8].upper()}"

            duration = 30
            if self.scheduler_settings:
                duration = self.scheduler_settings.get("default_duration_minutes", 30)

            end_time = appointment_time + timedelta(minutes=duration)

            # Check for slot conflicts - prevent double booking (with org filtering)
            conflict_filters = [
                ScheduledAppointment.loan_officer_id == self.lo_info["id"],
                ScheduledAppointment.status.in_([
                    AppointmentStatus.SCHEDULED.value,
                    AppointmentStatus.CONFIRMED.value
                ]),
                # Check for any overlap: existing starts before our end AND existing ends after our start
                ScheduledAppointment.start_time < end_time,
                ScheduledAppointment.end_time > appointment_time,
            ]
            org_id = self.lo_info.get("organization_id")
            if org_id:
                conflict_filters.append(ScheduledAppointment.organization_id == org_id)

            existing_appointment = self.db.query(ScheduledAppointment).filter(
                *conflict_filters
            ).first()

            if existing_appointment:
                logger.warning(f"Slot conflict: {appointment_time} already booked (appointment {existing_appointment.appointment_id})")
                return {
                    "success": False,
                    "error": "This time slot is no longer available. Please select a different time.",
                    "conflict": True,
                    "conflicting_slot": {
                        "start": existing_appointment.start_time.isoformat(),
                        "end": existing_appointment.end_time.isoformat()
                    }
                }

            # Create or find the lead in CRM
            lead = None
            lead_id = None
            try:
                # Check if lead already exists by email
                existing_lead = self.db.query(Lead).filter(
                    Lead.email == contact_email,
                    Lead.owner_id == self.lo_info["id"]
                ).first()

                if existing_lead:
                    lead = existing_lead
                    lead_id = existing_lead.id
                    logger.info(f"Found existing lead {lead_id} for {contact_email}")
                else:
                    # Parse name into first/last
                    name_parts = contact_name.strip().split(" ", 1)
                    first_name = name_parts[0]
                    last_name = name_parts[1] if len(name_parts) > 1 else ""

                    # Create new lead as Prospect
                    lead = Lead(
                        name=contact_name,
                        first_name=first_name,
                        last_name=last_name,
                        email=contact_email,
                        phone=contact_phone,
                        stage=LeadStage.PROSPECT,
                        source="AI Chat - Microsite",
                        owner_id=self.lo_info["id"],
                        ai_score=70,  # Good score since they're scheduling
                        sentiment="positive",
                        next_action=f"Consultation scheduled for {appointment_time.strftime('%B %d at %I:%M %p')}"
                    )
                    self.db.add(lead)
                    self.db.flush()  # Get the ID without committing

                    from services.client_file_service import ensure_client_file
                    ensure_client_file(self.db, lead)

                    lead_id = lead.id
                    logger.info(f"Created new lead {lead_id} for {contact_email} as Prospect")

            except Exception as lead_error:
                logger.warning(f"Could not create lead: {lead_error}")
                # Continue with appointment booking even if lead creation fails

            # Create the appointment with organization_id for tenant isolation
            appointment = ScheduledAppointment(
                appointment_id=appointment_id,
                loan_officer_id=self.lo_info["id"],
                lo_name=self.lo_info["name"],
                lo_email=self.lo_info["email"],
                contact_id=lead_id,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                appointment_type=appointment_type,
                start_time=appointment_time,
                end_time=end_time,
                duration_minutes=duration,
                status=AppointmentStatus.SCHEDULED.value,
                notes=notes,
                booked_via="ai_assistant",
                organization_id=self.lo_info.get("organization_id"),
            )

            self.db.add(appointment)
            self.db.commit()
            self.db.refresh(appointment)

            # Send notifications (async - don't block on failure)
            self._send_appointment_notifications(
                appointment_id=appointment_id,
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                appointment_time=appointment_time,
                duration=duration
            )

            return {
                "success": True,
                "appointment_id": appointment_id,
                "lead_id": lead_id,
                "lead_status": "prospect",
                "appointment": {
                    "id": appointment.id,
                    "appointment_id": appointment_id,
                    "loan_officer": self.lo_info["name"],
                    "contact_name": contact_name,
                    "start_time": appointment_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration_minutes": duration,
                    "type": appointment_type
                },
                "message": f"Appointment confirmed! {self.lo_info['name']} will call you on {appointment_time.strftime('%A, %B %d at %I:%M %p')}."
            }

        except Exception as e:
            logger.error(f"Error booking appointment: {e}")
            self.db.rollback()
            return {"success": False, "error": "Internal server error"}

    def _create_calendar_event(
        self,
        contact_name: str,
        contact_email: str,
        contact_phone: Optional[str],
        appointment_time: datetime,
        duration: int
    ):
        """Create calendar event on the loan officer's calendar via Microsoft Graph"""
        try:
            import asyncio
            from services.microsoft_graph import create_event_via_graph

            lo_id = self.lo_info['id']
            lo_name = self.lo_info['name']
            end_time = appointment_time + timedelta(minutes=duration)

            # Build event subject and body
            subject = f"Appointment: {contact_name} - Mortgage Consultation"
            body = f"""
            <div style="font-family: Arial, sans-serif;">
                <h3>Mortgage Consultation Appointment</h3>
                <p><strong>Contact:</strong> {contact_name}</p>
                <p><strong>Email:</strong> {contact_email or 'Not provided'}</p>
                <p><strong>Phone:</strong> {contact_phone or 'Not provided'}</p>
                <p><strong>Duration:</strong> {duration} minutes</p>
                <hr>
                <p style="color: #666;">This appointment was scheduled through the AI mortgage assistant on your website.</p>
            </div>
            """

            # Run the async function synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    create_event_via_graph(
                        user_id=lo_id,
                        subject=subject,
                        start=appointment_time,
                        end=end_time,
                        db=self.db,
                        attendees=[contact_email] if contact_email else None,
                        body=body
                    )
                )

                if result.success:
                    logger.info(f"Calendar event created for LO {lo_id}: {result.event_id}")
                else:
                    logger.warning(f"Failed to create calendar event: {result.error}")

            finally:
                loop.close()

        except Exception as e:
            logger.warning(f"Failed to create calendar event: {e}")
            # Don't fail the appointment booking if calendar fails

    def _send_appointment_notifications(
        self,
        appointment_id: str,
        contact_name: str,
        contact_email: str,
        contact_phone: Optional[str],
        appointment_time: datetime,
        duration: int
    ):
        """Send notifications for the appointment and create calendar event"""
        try:
            from services.notification_service import NotificationService
            notification_service = NotificationService()

            # Create calendar event on LO's calendar
            self._create_calendar_event(
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                appointment_time=appointment_time,
                duration=duration
            )

            lo_name = self.lo_info['name']
            lo_email = self.lo_info['email']
            lo_phone = self.lo_info.get('phone', '')

            formatted_time = appointment_time.strftime('%A, %B %d, %Y at %I:%M %p')

            # Send confirmation email with calendar invite to the contact/lead
            if contact_email:
                notification_service.send_appointment_confirmation(
                    borrower_email=contact_email,
                    borrower_name=contact_name,
                    appointment_type="Mortgage Consultation",
                    appointment_time=appointment_time,
                    lo_name=lo_name,
                    phone_number=contact_phone,
                    appointment_id=appointment_id,
                    duration_minutes=duration,
                    lo_email=lo_email,
                )
                logger.info(f"Sent appointment confirmation with calendar invite to {contact_email}")

            # Send notification to the loan officer with calendar invite
            if lo_email:
                import base64
                from utils.calendar_invite import generate_lo_appointment_ics

                # Generate calendar invite for LO
                lo_attachments = None
                try:
                    lo_ics_content = generate_lo_appointment_ics(
                        appointment_id=appointment_id,
                        contact_name=contact_name,
                        contact_email=contact_email,
                        contact_phone=contact_phone,
                        start_time=appointment_time,
                        duration_minutes=duration,
                        appointment_type="consultation",
                        loan_officer_name=lo_name,
                        loan_officer_email=lo_email,
                    )
                    lo_ics_base64 = base64.b64encode(lo_ics_content.encode('utf-8')).decode('utf-8')
                    lo_attachments = [{
                        'content': lo_ics_base64,
                        'filename': f'appointment-{appointment_id}.ics',
                        'type': 'text/calendar',
                    }]
                except Exception as e:
                    logger.warning(f"Failed to generate LO calendar invite: {e}")

                notification_service.send_email(
                    to_email=lo_email,
                    subject=f"New Appointment: {contact_name} - {formatted_time}",
                    html_content=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #1e40af;">New Appointment Scheduled</h2>
                        <p>A new appointment has been booked through your microsite:</p>

                        <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                            <p style="margin: 0;"><strong>Contact:</strong> {contact_name}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Email:</strong> {contact_email or 'Not provided'}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Phone:</strong> {contact_phone or 'Not provided'}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Date & Time:</strong> {formatted_time}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Duration:</strong> {duration} minutes</p>
                        </div>

                        <p>This appointment was scheduled through your AI mortgage assistant.</p>
                        <p style="color: #6b7280; font-size: 14px;">📅 Calendar invite attached - click to add to your calendar.</p>
                    </div>
                    """,
                    attachments=lo_attachments,
                )
                logger.info(f"Sent new appointment alert with calendar invite to {lo_email}")

            logger.info(f"Appointment {appointment_id} notifications sent")

        except Exception as e:
            logger.warning(f"Failed to send notifications: {e}")

    def generate_response(
        self,
        user_message: str,
        conversation_history: List[Dict] = None,
        session_id: str = None
    ) -> Dict[str, Any]:
        """Generate AI response to user message using Trust-First Architecture"""

        if not self.lo_info:
            return {
                "response": "I'm sorry, I couldn't find information about this loan officer. Please try again later.",
                "error": "Loan officer not found"
            }

        # Build context for AI
        lo_name = self.lo_info["name"]
        lo_bio = self.lo_info.get("bio", "")

        # Get current rate info for context
        rate_info = self._get_current_rate_info()

        # Determine conversation phase based on history (Trust-First Architecture)
        turn_count = len(conversation_history) if conversation_history else 0
        phase = self._determine_phase(turn_count, conversation_history, user_message)

        # Get available slots only for phase 4
        slots_text = ""
        if phase >= 4:
            available_slots = self.get_available_slots(days_ahead=5)
            if available_slots:
                slots_text = "\n".join([f"- {s['display']}" for s in available_slots[:8]])

        # Build phase-appropriate system prompt
        system_prompt = self._build_trust_first_prompt(
            phase=phase,
            lo_name=lo_name,
            lo_bio=lo_bio,
            rate_info=rate_info,
            slots_text=slots_text,
            turn_count=turn_count
        )

        # Build messages for API
        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

        messages.append({"role": "user", "content": user_message})

        # Try OpenAI first, then Anthropic
        try:
            response_text = self._call_openai(messages)
        except Exception as e:
            logger.warning(f"OpenAI call failed: {e}")
            try:
                response_text = self._call_anthropic(messages)
            except Exception as e2:
                logger.error(f"Anthropic call also failed: {e2}")
                response_text = self._fallback_response(user_message)

        # Check if user is trying to schedule (only relevant in phase 4)
        scheduling_intent = phase >= 4 and self._detect_scheduling_intent(user_message, response_text)

        # Check if user is asking about budget/affordability
        budget_intent = self._detect_budget_intent(user_message, response_text)

        # Get available slots only if scheduling is appropriate
        available_slots = self.get_available_slots(days_ahead=5) if scheduling_intent else []

        return {
            "response": response_text,
            "loan_officer": lo_name,
            "phase": phase,
            "turn_count": turn_count,
            "scheduling_intent": scheduling_intent,
            "budget_intent": budget_intent,
            "available_slots": available_slots[:5] if scheduling_intent else None
        }

    def _call_openai(self, messages: List[Dict]) -> str:
        """Call OpenAI API"""
        import openai

        if not OPENAI_API_KEY:
            raise Exception("OpenAI API key not configured")

        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=200,
            temperature=0.7
        )

        return response.choices[0].message.content

    def _call_anthropic(self, messages: List[Dict]) -> str:
        """Call Anthropic API as fallback"""
        import anthropic

        if not ANTHROPIC_API_KEY:
            raise Exception("Anthropic API key not configured")

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Convert messages format
        system_content = ""
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                api_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        from services.llm_gateway import llm_gateway
        llm_result = llm_gateway.complete_sync(
            intent="customer",
            system_prompt=system_content,
            messages=api_messages,
            max_tokens_override=200,
        )

        return llm_result.text

    def _fallback_response(self, user_message: str) -> str:
        """Fallback response if AI is unavailable - follows Trust-First approach with SHORT responses"""
        lo_name = self.lo_info.get("name", "the loan officer") if self.lo_info else "the loan officer"

        lower_message = user_message.lower()

        # Only offer scheduling if user explicitly asks for it (Trust-First)
        if any(word in lower_message for word in ["schedule", "appointment", "call me", "talk to", "speak with"]):
            return f"Happy to help you connect with {lo_name}! What's your name and best phone number?"

        if any(word in lower_message for word in ["rate", "rates", "interest"]):
            return "Current 30-year fixed rates are around 6.75-7% for most borrowers. Your exact rate depends on credit score and down payment. What's your situation looking like?"

        if any(word in lower_message for word in ["preapproval", "pre-approval", "qualify", "approved"]):
            return "Pre-approval is a great first step! It takes about 24-48 hours and shows sellers you're serious. Are you actively house hunting, or just exploring?"

        if any(word in lower_message for word in ["down payment", "down", "how much"]):
            return "Down payments range from 0% (VA/USDA) to 3.5% (FHA) to 3-20% (conventional). What price range are you looking at?"

        # Default trust-first response - helpful, no scheduling push
        return "Hey! I can help with rates, loan options, or pre-approval questions. What's on your mind?"

    def _detect_scheduling_intent(self, user_message: str, ai_response: str) -> bool:
        """Detect if user wants to schedule"""
        scheduling_keywords = [
            "schedule", "appointment", "book", "call", "meet", "talk",
            "available", "time", "calendar", "consultation", "speak"
        ]

        combined = (user_message + " " + ai_response).lower()
        return any(keyword in combined for keyword in scheduling_keywords)

    def _detect_budget_intent(self, user_message: str, ai_response: str) -> bool:
        """Detect if user is asking about budget, affordability, or payment amounts"""
        budget_keywords = [
            "afford", "budget", "payment", "monthly", "how much",
            "price range", "income", "debt", "dti", "can i buy",
            "qualify for", "what can i", "home price", "house price",
            "down payment", "calculate", "no more than", "max budget",
            "comfortable", "expensive", "cheaper"
        ]

        combined = (user_message + " " + ai_response).lower()
        return any(keyword in combined for keyword in budget_keywords)

    def _determine_phase(self, turn_count: int, history: List[Dict], user_message: str) -> int:
        """
        Determine conversation phase based on Trust-First Architecture.

        Phase 1 (Turns 0-2): Reassure & Orient - Be helpful, NO scheduling
        Phase 2 (Turns 3-5): Educate with Tradeoffs - Demonstrate expertise, NO scheduling
        Phase 3 (Turns 6-8): Personalize - Gather info naturally, NO scheduling
        Phase 4 (Turns 9+): Earned Next Step - NOW can offer scheduling

        Can also advance based on user explicitly asking to schedule/talk.
        """
        # Check if user explicitly wants to schedule (skip to phase 4)
        schedule_keywords = ["schedule", "appointment", "call me", "talk to", "speak with", "contact me", "call back"]
        if any(keyword in user_message.lower() for keyword in schedule_keywords):
            return 4

        # Phase based on conversation depth
        if turn_count <= 2:
            return 1  # Reassure & Orient
        elif turn_count <= 5:
            return 2  # Educate with Tradeoffs
        elif turn_count <= 8:
            return 3  # Personalize via Micro-Commitments
        else:
            return 4  # Earned Next Step - can offer scheduling

    def _build_trust_first_prompt(
        self,
        phase: int,
        lo_name: str,
        lo_bio: str,
        rate_info: str,
        slots_text: str,
        turn_count: int
    ) -> str:
        """Build phase-appropriate system prompt following Trust-First Architecture"""

        base_context = f"""You are a friendly, knowledgeable mortgage assistant representing {lo_name}.

About {lo_name}:
{lo_bio if lo_bio else f"{lo_name} is an experienced mortgage professional dedicated to helping clients achieve their homeownership dreams."}

CURRENT MARKET RATES (share when asked about rates):
{rate_info}

## CRITICAL: KEEP RESPONSES SHORT AND CONVERSATIONAL

⚠️ RESPONSE LENGTH RULES - FOLLOW STRICTLY:
- Keep responses to 2-4 SHORT sentences maximum
- Answer ONE question at a time, then ask a follow-up
- NO walls of text or long explanations
- NO numbered lists with 5+ items
- Use bullet points sparingly (max 3-4 bullets if needed)
- Write like you're texting a friend, not writing an essay
- If they ask a complex question, give a brief answer and offer to explain more

BAD EXAMPLE (too long):
"Rates depend on many factors including your credit score, down payment amount, loan type, property type, occupancy status, debt-to-income ratio, and current market conditions. Here are the current rate ranges: [lists 10 different scenarios]..."

GOOD EXAMPLE (conversational):
"Current 30-year fixed rates are around 6.75-7% for most borrowers. Your exact rate depends mainly on your credit score and down payment. What's your situation looking like?"

"""

        if phase == 1:
            return base_context + f"""## PHASE 1: REASSURE & ORIENT

Be friendly and helpful. Answer briefly, then ask ONE follow-up question.

DO: Be warm, use simple language, keep it short
DON'T: Offer calls/appointments, ask for contact info, be salesy

Just be helpful - earn their trust first."""

        elif phase == 2:
            return base_context + f"""## PHASE 2: EDUCATE

Share expertise briefly. Give honest tradeoffs when comparing options.

DO: Explain the "why", be balanced, ask follow-up questions
DON'T: Offer calls/appointments, ask for contact info, push solutions

Keep building credibility through helpful, SHORT answers."""

        elif phase == 3:
            return base_context + f"""## PHASE 3: PERSONALIZE

Ask ONE question at a time to understand their situation better.

Good questions: timeline, price range, credit situation, down payment
DO: Be conversational, explain why you're asking
DON'T: Offer calls yet, ask multiple questions at once

Keep responses SHORT - you're having a conversation, not giving a lecture."""

        else:  # Phase 4
            return base_context + f"""## PHASE 4: OFFER NEXT STEP - WITH VALUE PITCH

You've built trust. Now you CAN offer to connect them with {lo_name}.

IMPORTANT: When offering to schedule, emphasize the VALUE of speaking with {lo_name}:
- {lo_name} speaks with all clients before they start looking at homes
- Even 20 minutes with {lo_name} can help them get the best home for the best price
- The call puts them in a strong negotiating position - potentially saving thousands off the home price
- {lo_name}'s no-cost mortgage planning program can save them tens of thousands over 5-10 years
- Whether they use {lo_name} or not, this conversation is incredibly valuable

SAMPLE SCHEDULING PITCH (vary this naturally):
"I'd recommend setting up a quick call with {lo_name}. He talks with all our clients before they start looking - even 20 minutes can help you get the best home for the best price and put you in a strong position to potentially save thousands. Plus, his free mortgage planning program has saved clients tens of thousands over the years. Here are some available times - pick one that works for you!"

{("Available times:" + chr(10) + slots_text) if slots_text else ""}

If they say no: "No problem! I'm here whenever you have more questions."

Still keep responses reasonably short, but DO include the value messaging when offering times."""

    def _get_current_rate_info(self) -> str:
        """Get current market rate information for the AI context"""
        try:
            from sqlalchemy import text

            # Try to get rates from the database
            result = self.db.execute(text("""
                SELECT loan_type, term_years, base_rate, apr
                FROM rate_sheets
                WHERE effective_date = (SELECT MAX(effective_date) FROM rate_sheets)
                ORDER BY loan_type, term_years
            """))
            rates = result.fetchall()

            if rates:
                rate_text = []
                for r in rates:
                    rate_text.append(f"- {r.loan_type.title()} {r.term_years}yr: {float(r.base_rate):.3f}% (APR: {float(r.apr):.3f}%)")
                return "\n".join(rate_text)
        except SQLAlchemyError as e:
            logger.warning(f"Could not fetch rates from database: {e}")

        # Provide reasonable market rate ranges as fallback (updated periodically)
        # These should be updated regularly to reflect actual market conditions
        return """- 30-Year Fixed Conventional: 6.625% - 7.125% (depending on credit and down payment)
- 15-Year Fixed Conventional: 5.875% - 6.375%
- FHA 30-Year: 6.375% - 6.875% (lower credit requirements)
- VA 30-Year: 6.250% - 6.750% (for eligible veterans)
- Jumbo 30-Year: 6.875% - 7.375% (loans over $832,750)

Note: Rates change daily based on market conditions. These are approximate ranges - your actual rate depends on credit score, down payment, property type, and other factors."""


def get_public_chat_service(db: Session, user_slug: str) -> PublicMortgageChatService:
    """Factory function to get chat service instance"""
    return PublicMortgageChatService(db, user_slug)
