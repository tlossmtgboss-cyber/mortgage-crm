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
        from main import User
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
        }

        # Try to load scheduler settings for this user
        self._load_scheduler_settings(user.id)

    def _load_scheduler_settings(self, user_id: int):
        """Load scheduler settings and availability"""
        try:
            from services.smart_scheduler_service import SchedulerSettings, LoanOfficerSchedule, ScheduledAppointment

            # Get scheduler settings
            settings = self.db.query(SchedulerSettings).filter(
                SchedulerSettings.user_id == user_id
            ).first()

            if not settings:
                # Use default settings
                settings = self.db.query(SchedulerSettings).first()

            if settings:
                self.scheduler_settings = {
                    "business_hours": settings.business_hours or {},
                    "default_duration_minutes": settings.default_duration_minutes or 30,
                    "buffer_between_appointments": settings.buffer_between_appointments or 15,
                    "min_notice_hours": settings.min_notice_hours or 2,
                    "max_advance_days": settings.max_advance_days or 30,
                }

            # Get LO schedule if exists
            lo_schedule = self.db.query(LoanOfficerSchedule).filter(
                LoanOfficerSchedule.user_id == user_id
            ).first()

            if lo_schedule:
                self.scheduler_settings = self.scheduler_settings or {}
                self.scheduler_settings["custom_hours"] = lo_schedule.custom_hours
                self.scheduler_settings["blocked_times"] = lo_schedule.blocked_times or []

        except Exception as e:
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
            except:
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
            appointments = self.db.query(ScheduledAppointment).filter(
                and_(
                    ScheduledAppointment.loan_officer_id == self.lo_info["id"],
                    ScheduledAppointment.start_time >= start_date,
                    ScheduledAppointment.start_time <= end_date,
                    ScheduledAppointment.status.in_(["scheduled", "confirmed"])
                )
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
            from main import Lead, LeadStage

            # Generate appointment ID
            appointment_id = f"APPT-{uuid.uuid4().hex[:8].upper()}"

            duration = 30
            if self.scheduler_settings:
                duration = self.scheduler_settings.get("default_duration_minutes", 30)

            end_time = appointment_time + timedelta(minutes=duration)

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
                    lead_id = lead.id
                    logger.info(f"Created new lead {lead_id} for {contact_email} as Prospect")

            except Exception as lead_error:
                logger.warning(f"Could not create lead: {lead_error}")
                # Continue with appointment booking even if lead creation fails

            # Create the appointment
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
                booked_via="ai_assistant"
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
            return {"success": False, "error": str(e)}

    def _send_appointment_notifications(
        self,
        appointment_id: str,
        contact_name: str,
        contact_email: str,
        contact_phone: Optional[str],
        appointment_time: datetime,
        duration: int
    ):
        """Send notifications for the appointment"""
        try:
            from services.notification_service import NotificationService
            notification_service = NotificationService()

            lo_name = self.lo_info['name']
            lo_email = self.lo_info['email']
            lo_phone = self.lo_info.get('phone', '')

            formatted_time = appointment_time.strftime('%A, %B %d, %Y at %I:%M %p')

            # Send confirmation email to the contact/lead
            if contact_email:
                notification_service.send_email(
                    to_email=contact_email,
                    subject=f"Appointment Confirmed with {lo_name}",
                    html_content=f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #1e40af;">Appointment Confirmed!</h2>
                        <p>Hi {contact_name},</p>
                        <p>Your appointment has been scheduled:</p>

                        <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                            <p style="margin: 0;"><strong>Date & Time:</strong> {formatted_time}</p>
                            <p style="margin: 10px 0 0 0;"><strong>Duration:</strong> {duration} minutes</p>
                            <p style="margin: 10px 0 0 0;"><strong>With:</strong> {lo_name}</p>
                        </div>

                        <p>{lo_name} will call you at the scheduled time to discuss your mortgage needs.</p>

                        <p style="color: #6b7280; font-size: 14px; margin-top: 30px;">
                            Need to reschedule? Reply to this email or call {lo_phone if lo_phone else 'your loan officer'}.
                        </p>
                    </div>
                    """
                )
                logger.info(f"Sent appointment confirmation to {contact_email}")

            # Send notification to the loan officer
            if lo_email:
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
                    </div>
                    """
                )
                logger.info(f"Sent new appointment alert to {lo_email}")

            logger.info(f"Appointment {appointment_id} notifications sent")

        except Exception as e:
            logger.warning(f"Failed to send notifications: {e}")

    def generate_response(
        self,
        user_message: str,
        conversation_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """Generate AI response to user message"""

        if not self.lo_info:
            return {
                "response": "I'm sorry, I couldn't find information about this loan officer. Please try again later.",
                "error": "Loan officer not found"
            }

        # Build context for AI
        lo_name = self.lo_info["name"]
        lo_bio = self.lo_info.get("bio", "")

        # Get available slots for context
        available_slots = self.get_available_slots(days_ahead=5)
        slots_text = ""
        if available_slots:
            slots_text = "\n".join([f"- {s['display']}" for s in available_slots[:8]])

        system_prompt = f"""You are a friendly and professional AI mortgage assistant for {lo_name}, a loan officer.

About {lo_name}:
{lo_bio if lo_bio else f"{lo_name} is an experienced mortgage professional dedicated to helping clients achieve their homeownership dreams."}

Your PRIMARY GOAL is to:
1. Answer the user's mortgage question helpfully
2. ALWAYS proactively offer to schedule a call with {lo_name} at the END of every response
3. Collect the user's name, email, and phone number to schedule the appointment

{lo_name}'s available times for calls:
{slots_text if slots_text else "Availability coming soon - please provide your contact info and we'll reach out."}

RESPONSE FORMAT - Follow this structure for EVERY response:
1. Answer their question briefly (2-3 sentences)
2. Add value or context if helpful
3. ALWAYS end with a proactive scheduling offer like:
   "Would you like me to have {lo_name} give you a call to discuss this further? Here are some times that work:
   [list 3-4 available times]
   Just share your name, phone number, and email, and I'll get that scheduled for you!"

IMPORTANT - BE PROACTIVE:
- Don't wait for them to ask about scheduling
- After answering ANY question, proactively suggest a call
- Make it easy - offer specific times from the available slots
- Ask for: name, phone number, and email address
- Once they provide contact info and choose a time, confirm the appointment

COLLECTING INFO:
- If they provide partial info (just name or just email), acknowledge it and ask for the missing pieces
- You need: Full name, Phone number, Email address, and Preferred time
- Once you have all info, confirm: "Perfect! I've scheduled your call with {lo_name} for [time]. You'll receive a confirmation at [email]. {lo_name} will call you at [phone]. Is there anything specific you'd like to discuss during the call?"

TONE:
- Warm, friendly, and helpful
- Professional but not stiff
- Enthusiastic about helping them connect with {lo_name}

Do NOT:
- Make up specific rates or terms
- Promise approval or specific outcomes
- Provide legal or tax advice
- End a response without offering to schedule a call"""

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

        # Check if user is trying to schedule
        scheduling_intent = self._detect_scheduling_intent(user_message, response_text)

        return {
            "response": response_text,
            "loan_officer": lo_name,
            "scheduling_intent": scheduling_intent,
            "available_slots": available_slots[:5] if scheduling_intent else None
        }

    def _call_openai(self, messages: List[Dict]) -> str:
        """Call OpenAI API"""
        import openai

        if not OPENAI_API_KEY:
            raise Exception("OpenAI API key not configured")

        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
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

        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            system=system_content,
            messages=api_messages
        )

        return response.content[0].text

    def _fallback_response(self, user_message: str) -> str:
        """Fallback response if AI is unavailable"""
        lo_name = self.lo_info.get("name", "the loan officer") if self.lo_info else "the loan officer"

        lower_message = user_message.lower()

        if any(word in lower_message for word in ["schedule", "appointment", "call", "meet", "book", "talk"]):
            return f"I'd love to help you schedule a conversation with {lo_name}! Please share your name and email, and I'll help you find a convenient time."

        if any(word in lower_message for word in ["rate", "rates", "interest"]):
            return f"Mortgage rates vary based on several factors including loan type, credit score, and down payment. {lo_name} can provide you with a personalized rate quote during a quick consultation. Would you like to schedule a call?"

        if any(word in lower_message for word in ["preapproval", "pre-approval", "qualify", "approved"]):
            return f"Getting pre-approved is a great first step! {lo_name} can walk you through the process and help you understand your buying power. Would you like to schedule a pre-approval consultation?"

        return f"Thanks for reaching out! I'm here to help answer your mortgage questions. If you'd like personalized guidance, I can help you schedule a call with {lo_name}. What would you like to know?"

    def _detect_scheduling_intent(self, user_message: str, ai_response: str) -> bool:
        """Detect if user wants to schedule"""
        scheduling_keywords = [
            "schedule", "appointment", "book", "call", "meet", "talk",
            "available", "time", "calendar", "consultation", "speak"
        ]

        combined = (user_message + " " + ai_response).lower()
        return any(keyword in combined for keyword in scheduling_keywords)


def get_public_chat_service(db: Session, user_slug: str) -> PublicMortgageChatService:
    """Factory function to get chat service instance"""
    return PublicMortgageChatService(db, user_slug)
