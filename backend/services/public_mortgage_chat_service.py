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
        """Book an appointment with the loan officer"""
        if not self.lo_info:
            return {"success": False, "error": "Loan officer not found"}

        try:
            from services.smart_scheduler_service import ScheduledAppointment, AppointmentStatus

            # Generate appointment ID
            appointment_id = f"APPT-{uuid.uuid4().hex[:8].upper()}"

            duration = 30
            if self.scheduler_settings:
                duration = self.scheduler_settings.get("default_duration_minutes", 30)

            end_time = appointment_time + timedelta(minutes=duration)

            # Create the appointment
            appointment = ScheduledAppointment(
                appointment_id=appointment_id,
                loan_officer_id=self.lo_info["id"],
                lo_name=self.lo_info["name"],
                lo_email=self.lo_info["email"],
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

            return {
                "success": True,
                "appointment_id": appointment_id,
                "appointment": {
                    "id": appointment.id,
                    "appointment_id": appointment_id,
                    "loan_officer": self.lo_info["name"],
                    "contact_name": contact_name,
                    "start_time": appointment_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "duration_minutes": duration,
                    "type": appointment_type
                }
            }

        except Exception as e:
            logger.error(f"Error booking appointment: {e}")
            self.db.rollback()
            return {"success": False, "error": str(e)}

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

Your role is to:
1. Answer questions about mortgages, home loans, refinancing, and the lending process
2. Help visitors understand their options
3. Encourage them to schedule a consultation with {lo_name}
4. Be helpful, professional, and warm

Available appointment times for the next few days:
{slots_text if slots_text else "Please ask about availability to see current openings."}

IMPORTANT GUIDELINES:
- Keep responses concise (2-4 sentences for simple questions)
- Be encouraging about scheduling a call with {lo_name}
- If someone seems interested in talking to {lo_name}, suggest scheduling a call
- You can answer general mortgage questions about rates, loan types, down payments, credit scores, etc.
- For specific rate quotes or pre-approval, encourage them to schedule a consultation
- Be warm and personable, but professional

When someone wants to schedule:
- Ask for their name, email, and phone number
- Confirm a time from the available slots
- Let them know you'll help them book the appointment

Do NOT:
- Make up specific rates or terms
- Promise approval or specific outcomes
- Provide legal or tax advice
- Share personal information about the loan officer beyond what's provided"""

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
