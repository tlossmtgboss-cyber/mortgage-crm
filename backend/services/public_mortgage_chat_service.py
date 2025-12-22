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

        # Get available slots only if scheduling is appropriate
        available_slots = self.get_available_slots(days_ahead=5) if scheduling_intent else []

        return {
            "response": response_text,
            "loan_officer": lo_name,
            "phase": phase,
            "turn_count": turn_count,
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
        """Fallback response if AI is unavailable - follows Trust-First approach"""
        lo_name = self.lo_info.get("name", "the loan officer") if self.lo_info else "the loan officer"

        lower_message = user_message.lower()

        # Only offer scheduling if user explicitly asks for it (Trust-First)
        if any(word in lower_message for word in ["schedule", "appointment", "call me", "talk to", "speak with"]):
            return f"I'd be happy to help you connect with {lo_name}! Please share your name, email, and phone number, and I'll help you find a convenient time."

        if any(word in lower_message for word in ["rate", "rates", "interest"]):
            return f"""Great question! Current mortgage rates are approximately:

• 30-Year Fixed: 6.625% - 7.125%
• 15-Year Fixed: 5.875% - 6.375%
• FHA Loans: 6.375% - 6.875%
• VA Loans: 6.250% - 6.750%

Your actual rate will depend on your credit score, down payment amount, and loan type. Rates also change daily based on market conditions.

What type of loan are you considering, or would you like me to explain the differences between these options?"""

        if any(word in lower_message for word in ["preapproval", "pre-approval", "qualify", "approved"]):
            return """Pre-approval is a smart first step! Here's what you should know:

**What pre-approval does:**
• Shows sellers you're a serious buyer
• Tells you your approximate budget
• Locks in a rate for 60-90 days typically

**What you'll need:**
• Recent pay stubs (last 30 days)
• W-2s or tax returns (last 2 years)
• Bank statements (last 2-3 months)
• ID and Social Security number

Most pre-approvals take 24-48 hours once you have your documents ready. Are you buying soon, or just starting to explore your options?"""

        if any(word in lower_message for word in ["down payment", "down", "how much"]):
            return """Down payment requirements vary by loan type:

• **Conventional**: 3-20% (avoid PMI at 20%)
• **FHA**: 3.5% minimum
• **VA**: 0% for eligible veterans
• **USDA**: 0% for rural areas

A larger down payment typically means:
✓ Lower monthly payments
✓ Better interest rates
✓ More equity from day one

What price range are you looking at? That'll help me give you more specific numbers."""

        # Default trust-first response - helpful, no scheduling push
        return """Thanks for reaching out! I'm here to help with any mortgage questions you have.

I can help you understand:
• Current interest rates and loan options
• Down payment requirements
• The pre-approval process
• How much home you might qualify for

What's on your mind?"""

    def _detect_scheduling_intent(self, user_message: str, ai_response: str) -> bool:
        """Detect if user wants to schedule"""
        scheduling_keywords = [
            "schedule", "appointment", "book", "call", "meet", "talk",
            "available", "time", "calendar", "consultation", "speak"
        ]

        combined = (user_message + " " + ai_response).lower()
        return any(keyword in combined for keyword in scheduling_keywords)

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

"""

        if phase == 1:
            return base_context + f"""## PHASE 1: REASSURE & ORIENT (Current Phase)

YOUR GOAL: Create emotional safety and be genuinely helpful. The person may feel overwhelmed about mortgages.

WHAT TO DO:
1. Answer their question thoroughly and helpfully
2. Use simple, jargon-free language
3. Validate their concerns - mortgages ARE complex
4. Be warm, patient, and approachable
5. End with ONE follow-up question to learn more about their situation

TONE: Warm, welcoming, patient, knowledgeable but not condescending

⚠️ CRITICAL - DO NOT:
- Offer to schedule a call or appointment
- Ask for their phone number or email
- Mention connecting them with {lo_name}
- Say "when you're ready to talk" or anything about calls
- Be salesy or transactional

You must EARN trust first by being helpful. Right now, just answer their question well."""

        elif phase == 2:
            return base_context + f"""## PHASE 2: EDUCATE WITH TRADEOFFS (Current Phase)

YOUR GOAL: Demonstrate expertise through education, not selling. Show you understand nuances.

WHAT TO DO:
1. Explain concepts clearly with the "why" behind things
2. Present options with HONEST tradeoffs (pros AND cons)
3. Reference current market conditions when relevant
4. Use examples relevant to what they've shared
5. Ask 1-2 natural questions to better understand their needs
6. Continue building trust through valuable education

TONE: Expert but accessible, balanced and honest, educational not promotional

⚠️ CRITICAL - DO NOT:
- Offer to schedule a call or appointment
- Ask for their phone number or email
- Mention connecting them with {lo_name}
- Push one solution over another prematurely
- Make promises about rates or approval

You're still building credibility. Focus on being helpful, not pitching calls."""

        elif phase == 3:
            return base_context + f"""## PHASE 3: PERSONALIZE VIA MICRO-COMMITMENTS (Current Phase)

YOUR GOAL: Gather information through natural conversation to provide personalized guidance.

WHAT TO DO:
1. Ask ONE relevant question at a time
2. Explain WHY you're asking (shows you care)
3. Provide value with each response
4. Make info sharing feel like a conversation, not a form
5. Respond with personalized insights based on their answers

GOOD QUESTIONS TO ASK (one at a time):
- "Are you looking to move within a specific timeframe?"
- "What price range are you considering?"
- "Is your credit in good shape, or is that a concern?"
- "Do you have a sense of your down payment situation?"

TONE: Consultative, naturally curious, patient

⚠️ CRITICAL - DO NOT (not yet!):
- Offer to schedule a call or appointment
- Ask for their phone number yet
- Push for exact numbers if they're not ready
- Ask multiple questions at once

You're gathering info to provide better guidance. Keep demonstrating value."""

        else:  # Phase 4
            return base_context + f"""## PHASE 4: EARNED NEXT STEP (Current Phase)

YOU'VE BUILT TRUST through {turn_count} exchanges. Now you can suggest a next step.

YOUR GOAL: Present ONE clear, helpful next step based on the conversation.

WHAT TO DO:
1. Briefly summarize what you've learned about their situation
2. Recommend ONE specific next step (not multiple options)
3. Make it easy to say yes
4. If they decline, gracefully offer an alternative or continue being helpful

AVAILABLE TIMES for {lo_name}:
{slots_text if slots_text else "I can help coordinate a time that works."}

NEXT STEP OPTIONS (pick ONE based on their situation):
- High urgency: "Would you like me to have {lo_name} call you? I can set that up right now."
- Medium urgency: "Would you like to schedule a quick 15-minute call with {lo_name} to go over your numbers?"
- Lower urgency: "I can have {lo_name} send you a personalized rate quote based on what we discussed."

TO SCHEDULE, collect:
- Full name
- Phone number
- Email address
- Preferred time

TONE: Confident but not pushy, respectful of their decision

If they decline, say: "No problem at all! I'm here if you have more questions."

Do NOT:
- Offer multiple CTAs - pick ONE
- Be pushy if they decline
- Lose the helpful tone you've built"""

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
        except Exception as e:
            logger.warning(f"Could not fetch rates from database: {e}")

        # Provide reasonable market rate ranges as fallback (updated periodically)
        # These should be updated regularly to reflect actual market conditions
        return """- 30-Year Fixed Conventional: 6.625% - 7.125% (depending on credit and down payment)
- 15-Year Fixed Conventional: 5.875% - 6.375%
- FHA 30-Year: 6.375% - 6.875% (lower credit requirements)
- VA 30-Year: 6.250% - 6.750% (for eligible veterans)
- Jumbo 30-Year: 6.875% - 7.375% (loans over $766,550)

Note: Rates change daily based on market conditions. These are approximate ranges - your actual rate depends on credit score, down payment, property type, and other factors."""


def get_public_chat_service(db: Session, user_slug: str) -> PublicMortgageChatService:
    """Factory function to get chat service instance"""
    return PublicMortgageChatService(db, user_slug)
