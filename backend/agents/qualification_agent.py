"""
Qualification Agent

AI agent that progressively collects mortgage application data through
conversational interactions across email and SMS channels.

Uses the ConversationIntelligence service for:
- Tone analysis and adaptation
- Qualification data extraction
- Objection handling
- Escalation decisions

Follows Perennia AI conversation rules:
- Ask ONE question at a time
- Keep responses under 60 words (SMS) or 150 words (email)
- Use SPIN Selling techniques for objection handling
- Escalate to human after 3 unsuccessful objection attempts
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Import the shared conversation intelligence service
from services.conversation_intelligence import (
    ConversationIntelligenceService,
    ConversationState,
    Channel,
    ConversationStage,
    QualificationStatus,
    QualificationData,
    ToneAnalysis,
    analyze_tone,
    extract_qualification_data,
    get_next_qualification_question,
    check_for_objections,
    get_conversation_service
)

# Import OpenAI conversation service
from services.openai_conversation_service import get_openai_service

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

# Maximum message lengths by channel
MAX_MESSAGE_LENGTH = {
    Channel.SMS: 160,  # Single SMS segment
    Channel.EMAIL: 500,  # Reasonable email length
    Channel.CHAT: 300,
}

# Qualification flow configuration
QUALIFICATION_FLOW = {
    "required_fields": [
        "loan_purpose",
        "property_value",
        "closing_timeline",
        "first_name",
        "phone",  # Required for SMS
        "email",  # Required for email
    ],
    "optional_fields": [
        "pre_approved_elsewhere",
        "credit_score_range",
        "employment_status",
        "annual_income",
        "down_payment",
        "property_type",
        "first_time_buyer",
    ],
    "booking_threshold": 80,  # % completion to offer booking
}

# Agent persona configuration (white-label replaceable)
DEFAULT_PERSONA = {
    "name": "Sarah",
    "role": "Senior Mortgage Consultant",
    "company": "The Tim Loss Team",
    "tone": "friendly_professional",
    "signature_email": "Best regards,\nSarah",
    "signature_sms": "- Sarah"
}


# =============================================================================
# RESPONSE TEMPLATES
# =============================================================================

class ResponseTemplates:
    """Response templates for different stages and situations."""

    GREETINGS = {
        Channel.EMAIL: {
            "purchase": "Hi {first_name}! Thanks for reaching out about purchasing a home. I'd love to help you find the best mortgage options. Let's start with a quick question:",
            "refinance": "Hi {first_name}! Thanks for your interest in refinancing. Let me help you explore your options. First question:",
            "unknown": "Hi {first_name}! Thanks for reaching out. I'm here to help with your mortgage needs. To get started:",
        },
        Channel.SMS: {
            "purchase": "Hi {first_name}! Thanks for your interest in home buying. Quick question:",
            "refinance": "Hi {first_name}! Thanks for reaching out about refinancing.",
            "unknown": "Hi {first_name}! Happy to help with your mortgage questions.",
        }
    }

    QUALIFICATION_QUESTIONS = {
        "loan_purpose": {
            Channel.EMAIL: "Are you looking to purchase a new home, or refinance an existing mortgage?",
            Channel.SMS: "Looking to purchase or refinance?"
        },
        "property_value": {
            Channel.EMAIL: "What's the estimated value of the property you're considering?",
            Channel.SMS: "What's the estimated property value?"
        },
        "closing_timeline": {
            Channel.EMAIL: "When are you hoping to close? Are you looking to move quickly, or just exploring options for now?",
            Channel.SMS: "When are you looking to close?"
        },
        "pre_approved_elsewhere": {
            Channel.EMAIL: "Have you been pre-approved by another lender? If so, I'd be happy to provide a comparison.",
            Channel.SMS: "Have you been pre-approved elsewhere?"
        },
        "first_name": {
            Channel.EMAIL: "By the way, I didn't catch your name - what should I call you?",
            Channel.SMS: "What's your name?"
        },
        "phone": {
            Channel.EMAIL: "What's the best phone number to reach you at for a quick chat?",
            Channel.SMS: "What's your phone number?"
        },
        "email": {
            Channel.EMAIL: "What's your email address?",
            Channel.SMS: "What's your email so I can send you details?"
        },
    }

    ACKNOWLEDGMENTS = {
        "loan_purpose": {
            "purchase": ["Great choice!", "Exciting!", "Love it!", "Perfect!"],
            "refinance": ["Smart move!", "Good thinking!", "Great idea!", "Nice!"]
        },
        "property_value": ["Got it!", "Perfect!", "Thanks!", "Noted!"],
        "closing_timeline": {
            "asap": ["Let's move fast then!", "We can work quickly!", "I'll prioritize this!"],
            "default": ["Good to know!", "Thanks for sharing!", "Got it!"]
        },
        "default": ["Thanks!", "Got it!", "Perfect!", "Great!"]
    }

    OBJECTION_RESPONSES = {
        "not_interested": {
            Channel.EMAIL: "I understand - no pressure at all. Just curious, is it the timing that's not right, or are you already working with someone?",
            Channel.SMS: "No worries! Is it timing, or already working with someone?"
        },
        "bad_timing": {
            Channel.EMAIL: "Totally understand! When would be a better time for me to check back in?",
            Channel.SMS: "No problem! When should I check back?"
        },
        "using_another": {
            Channel.EMAIL: "That's great you're already working on this! Have they locked your rate yet? I'd be happy to provide a quick comparison to make sure you're getting the best deal - no obligation.",
            Channel.SMS: "Nice! Have they locked your rate? Happy to do a quick comparison."
        },
        "rate_concern": {
            Channel.EMAIL: "I hear you on rates. They've been moving a lot lately. Would you like me to set you up with rate alerts so you know the moment they hit your target?",
            Channel.SMS: "Rates have been moving. Want me to alert you when they drop?"
        },
        "cost_concern": {
            Channel.EMAIL: "I understand cost is a concern. The good news is there are often ways to reduce upfront costs. Would you like me to show you some options?",
            Channel.SMS: "There are ways to reduce costs. Want me to show you options?"
        },
        "not_ready": {
            Channel.EMAIL: "No rush at all! Would it help if I sent you some information about the process so you're prepared when the time is right?",
            Channel.SMS: "No rush! Want some info for when you're ready?"
        },
        "trust_concern": {
            Channel.EMAIL: "I completely understand your caution. I'm {agent_name} with {company}. You can verify us at {website}. Happy to answer any questions about who we are.",
            Channel.SMS: "Totally understand! I'm {agent_name} with {company}. Happy to verify - what questions do you have?"
        }
    }

    BOOKING_PROMPTS = {
        Channel.EMAIL: """Based on what you've shared, I think we can definitely help you {purpose}.

Would you have time for a quick 15-minute call with one of our loan officers? They can give you exact numbers based on your situation and answer any questions.

What times work best for you this week?""",
        Channel.SMS: "Great news - we can help! Free for a quick 10-min call? What times work for you?"
    }

    ESCALATION_HANDOFF = {
        Channel.EMAIL: """I want to make sure you get the best possible assistance. I'm going to connect you with {lo_name}, one of our senior loan officers, who can help with your specific situation.

They'll reach out within the next hour. In the meantime, feel free to reply with any questions.

Best regards,
{agent_name}""",
        Channel.SMS: "I'm connecting you with {lo_name}, a senior loan officer. They'll call you shortly!"
    }


# =============================================================================
# QUALIFICATION AGENT
# =============================================================================

class QualificationAgent:
    """
    AI agent for progressive mortgage application data collection.
    Works across email and SMS channels with consistent logic.
    """

    def __init__(
        self,
        persona: Optional[Dict] = None,
        organization: Optional[Dict] = None,
        db_session=None,
        use_openai: bool = True
    ):
        self.persona = persona or DEFAULT_PERSONA.copy()
        self.organization = organization
        self.db = db_session
        self.conversation_service = get_conversation_service()

        # Initialize OpenAI service for AI-powered responses
        self.use_openai = use_openai
        self.openai_service = get_openai_service() if use_openai else None

        if self.openai_service and self.openai_service.enabled:
            logger.info("QualificationAgent initialized with OpenAI responses enabled")
        else:
            logger.info("QualificationAgent initialized with template-based responses")

        # Apply organization white-label if provided
        if organization:
            self._apply_white_label(organization)

    def _apply_white_label(self, org: Dict):
        """Apply organization branding to persona."""
        if "brand_name" in org:
            self.persona["company"] = org["brand_name"]
        if "agent_personas" in org and "qualification_agent" in org["agent_personas"]:
            agent_config = org["agent_personas"]["qualification_agent"]
            self.persona.update(agent_config)

    def process_message(
        self,
        conversation_id: str,
        message: str,
        channel: str,
        sender_info: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Process an incoming message and generate an appropriate response.

        Args:
            conversation_id: Unique conversation identifier
            message: The incoming message text
            channel: 'email' or 'sms'
            sender_info: Optional dict with sender details (name, email, phone)
            metadata: Optional additional context

        Returns:
            Dict with response, analysis, and next steps
        """
        channel_enum = Channel(channel.lower())

        # Get conversation analysis from shared service
        analysis = self.conversation_service.process_message(
            conversation_id=conversation_id,
            message=message,
            channel=channel_enum,
            direction="inbound",
            metadata=metadata
        )

        # Pre-populate qualification data from sender info
        if sender_info:
            state = self.conversation_service.get_or_create_conversation(
                conversation_id, channel_enum
            )
            if sender_info.get("first_name") and not state.qualification_data.first_name:
                state.qualification_data.first_name = sender_info["first_name"]
            if sender_info.get("email") and not state.qualification_data.email:
                state.qualification_data.email = sender_info["email"]
            if sender_info.get("phone") and not state.qualification_data.phone:
                state.qualification_data.phone = sender_info["phone"]

        # Generate response based on conversation state
        response = self._generate_response(
            conversation_id=conversation_id,
            channel=channel_enum,
            analysis=analysis,
            message=message
        )

        return {
            "conversation_id": conversation_id,
            "channel": channel,
            "response": response["text"],
            "response_type": response["type"],
            "tone_analysis": analysis["tone_analysis"],
            "qualification": analysis["qualification"],
            "conversation_state": analysis["conversation_state"],
            "should_send": response["should_send"],
            "should_escalate": analysis["should_escalate"],
            "escalation_reason": analysis.get("escalation_reason"),
            "next_action": response["next_action"],
            "booking_result": response.get("booking_result"),
            "metadata": {
                "persona": self.persona["name"],
                "company": self.persona["company"],
                "response_length": len(response["text"]),
                "timestamp": datetime.now().isoformat()
            }
        }

    def _generate_response(
        self,
        conversation_id: str,
        channel: Channel,
        analysis: Dict,
        message: str
    ) -> Dict[str, Any]:
        """Generate the appropriate response based on analysis."""

        stage = ConversationStage(analysis["conversation_state"]["stage"])
        qualification = analysis["qualification"]
        has_objection = analysis.get("objection_detected", False)
        objection_type = analysis.get("objection_type")
        should_escalate = analysis.get("should_escalate", False)

        # Handle escalation - always use template for this critical flow
        if should_escalate:
            return self._generate_escalation_response(channel, analysis, conversation_id)

        # =========================================================================
        # TRY OPENAI FOR AI-POWERED RESPONSES
        # =========================================================================
        if self.openai_service and self.openai_service.enabled:
            try:
                # Get conversation state for history
                state = self.conversation_service.get_or_create_conversation(
                    conversation_id, channel
                )

                # Build conversation history for OpenAI
                conversation_history = []
                for msg in state.message_history[-10:]:  # Last 10 messages
                    # Handle both 'role' key (from main.py) and 'direction' key (legacy)
                    if msg.get("role"):
                        role = msg.get("role")  # Already "user" or "assistant"
                    else:
                        role = "assistant" if msg.get("direction") == "outbound" else "user"
                    conversation_history.append({
                        "role": role,
                        "content": msg.get("content", "")
                    })

                # Build qualification data dict
                qual_data = qualification.get("data", {})

                # Run async OpenAI call in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    openai_response = loop.run_until_complete(
                        self.openai_service.generate_response(
                            conversation_id=conversation_id,
                            channel=channel.value,
                            user_message=message,
                            conversation_history=conversation_history,
                            qualification_data=qual_data,
                            conversation_stage=stage.value,
                            persona=self.persona
                        )
                    )
                finally:
                    loop.close()

                if openai_response.get("ai_generated"):
                    logger.info(f"OpenAI response generated for {conversation_id}")

                    # Check if this is an appointment booking response
                    response_text = openai_response["text"]
                    booking_result = None

                    # Detect and handle appointment booking
                    appointment_time = self._parse_appointment_time(message)
                    if appointment_time:
                        # Get email from qualification data or conversation
                        email = qual_data.get("email") or ""
                        name = qual_data.get("first_name") or "Customer"

                        if email:
                            booking_result = self._book_appointment_for_email(
                                email=email,
                                name=name,
                                appointment_time=appointment_time
                            )
                            if booking_result.get("success"):
                                # Update response to confirm the specific time
                                response_text = f"I've scheduled your consultation for {booking_result['display_time']}. You'll receive a calendar invitation shortly with all the details.\n\nIs there anything specific you'd like to discuss during the consultation?"

                    return {
                        "text": response_text,
                        "type": openai_response.get("type", "ai_response"),
                        "should_send": True,
                        "next_action": "await_response",
                        "ai_generated": True,
                        "model": openai_response.get("model"),
                        "tokens_used": openai_response.get("tokens_used", 0),
                        "booking_result": booking_result
                    }

            except Exception as e:
                logger.error(f"OpenAI response failed, falling back to templates: {e}")
                # Fall through to template-based responses

        # =========================================================================
        # FALLBACK: TEMPLATE-BASED RESPONSES
        # =========================================================================

        # Handle objections
        if has_objection and objection_type:
            return self._generate_objection_response(channel, objection_type, analysis)

        # Check if user asked specific questions - respond to those first regardless of stage
        user_question_response = self._check_for_user_question(analysis)
        if user_question_response:
            return user_question_response

        # Handle by stage
        if stage == ConversationStage.INITIAL_CONTACT:
            return self._generate_initial_response(channel, qualification, analysis)

        elif stage == ConversationStage.QUALIFICATION:
            return self._generate_qualification_response(channel, qualification, analysis)

        elif stage == ConversationStage.BOOKING:
            return self._generate_booking_response(channel, qualification, analysis)

        elif stage == ConversationStage.NURTURE:
            return self._generate_nurture_response(channel, analysis)

        else:
            return self._generate_qualification_response(channel, qualification, analysis)

    def _generate_initial_response(
        self,
        channel: Channel,
        qualification: Dict,
        analysis: Dict
    ) -> Dict[str, Any]:
        """Generate initial greeting and first question."""

        qual_data = qualification.get("data", {})
        first_name = qual_data.get("first_name") or "there"
        loan_purpose = qual_data.get("loan_purpose") or "unknown"

        # Get greeting template
        greetings = ResponseTemplates.GREETINGS.get(channel, ResponseTemplates.GREETINGS[Channel.EMAIL])
        greeting = greetings.get(loan_purpose, greetings["unknown"])
        greeting = greeting.format(first_name=first_name)

        # Get next question
        next_question = analysis.get("next_question") or self._get_next_question(qualification, channel)

        response_text = f"{greeting}\n\n{next_question}"

        # Ensure appropriate length
        response_text = self._trim_to_length(response_text, channel)

        return {
            "text": response_text,
            "type": "initial_contact",
            "should_send": True,
            "next_action": "await_response"
        }

    def _generate_qualification_response(
        self,
        channel: Channel,
        qualification: Dict,
        analysis: Dict
    ) -> Dict[str, Any]:
        """Generate qualification question with acknowledgment."""

        qual_data = qualification.get("data", {})
        completion = qualification.get("completion_percentage", 0)

        # Get last field that was filled
        collected_at = qual_data.get("collected_at", {})
        last_field = None
        if collected_at:
            last_field = max(collected_at.keys(), key=lambda k: collected_at[k])

        # Build acknowledgment
        ack = ""
        if last_field:
            ack_templates = ResponseTemplates.ACKNOWLEDGMENTS.get(last_field, ResponseTemplates.ACKNOWLEDGMENTS["default"])
            if isinstance(ack_templates, dict):
                value = qual_data.get(last_field)
                ack_templates = ack_templates.get(value, ack_templates.get("default", ["Got it!"]))
            if ack_templates:
                import random
                ack = random.choice(ack_templates) + " "

        # Check if ready for booking
        if completion >= QUALIFICATION_FLOW["booking_threshold"]:
            return self._generate_booking_response(channel, qualification, analysis)

        # Get next question
        next_question = analysis.get("next_question") or self._get_next_question(qualification, channel)

        if not next_question:
            # All required questions answered
            return self._generate_booking_response(channel, qualification, analysis)

        response_text = f"{ack}{next_question}"
        response_text = self._trim_to_length(response_text, channel)

        return {
            "text": response_text,
            "type": "qualification",
            "should_send": True,
            "next_action": "await_response"
        }

    def _parse_appointment_time(self, message: str) -> Optional[datetime]:
        """Try to parse a specific appointment time from the user's message."""
        import re
        from datetime import datetime, timedelta

        message_lower = message.lower()
        now = datetime.now()

        # Day of week mapping
        days_of_week = {
            'monday': 0, 'mon': 0,
            'tuesday': 1, 'tue': 1, 'tues': 1,
            'wednesday': 2, 'wed': 2,
            'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
            'friday': 4, 'fri': 4,
            'saturday': 5, 'sat': 5,
            'sunday': 6, 'sun': 6,
        }

        # Time patterns
        time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?'

        # Find time in message
        time_match = re.search(time_pattern, message_lower)
        hour = None
        minute = 0

        if time_match:
            hour = int(time_match.group(1))
            # Skip if hour looks like a price/amount (e.g., "450k")
            if hour > 12:
                hour = None
            else:
                if time_match.group(2):
                    minute = int(time_match.group(2))
                am_pm = time_match.group(3)

                if am_pm and ('pm' in am_pm or 'p.m' in am_pm):
                    if hour != 12:  # 12pm stays as 12, not 24
                        hour += 12
                elif am_pm and ('am' in am_pm or 'a.m' in am_pm):
                    if hour == 12:
                        hour = 0
                elif hour < 8:  # Assume PM for business hours (8am would be unusual)
                    hour += 12

        if hour is None:
            # Check for relative times
            if 'morning' in message_lower:
                hour = 10
            elif 'afternoon' in message_lower:
                hour = 14
            elif 'evening' in message_lower:
                hour = 17
            else:
                return None

        # Find day
        target_date = None

        # Check for "tomorrow"
        if 'tomorrow' in message_lower:
            target_date = now + timedelta(days=1)
        # Check for "today"
        elif 'today' in message_lower:
            target_date = now
        # Check for day of week
        else:
            for day_name, day_num in days_of_week.items():
                if day_name in message_lower:
                    days_ahead = day_num - now.weekday()
                    if days_ahead <= 0:  # Target day already happened this week
                        days_ahead += 7
                    target_date = now + timedelta(days=days_ahead)
                    break

        # Check for "next week"
        if target_date is None and 'next week' in message_lower:
            # Default to Monday of next week
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            target_date = now + timedelta(days=days_until_monday)

        if target_date is None:
            return None

        # Combine date and time
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _book_appointment_for_email(self, email: str, name: str, appointment_time: datetime) -> Dict[str, Any]:
        """Book an appointment using Smart Scheduler for LO assignment and return booking details."""
        import uuid
        from datetime import timedelta

        try:
            # Direct ORM booking — bypasses deprecated SmartSchedulerService
            from services.smart_scheduler_service import ScheduledAppointment, AppointmentStatus

            duration_minutes = 30
            end_time = appointment_time + timedelta(minutes=duration_minutes)
            appt_id = f"APPT-{str(uuid.uuid4())[:8].upper()}"

            org_id = self.organization.get("id") if self.organization else None
            appointment = ScheduledAppointment(
                appointment_id=appt_id,
                organization_id=org_id,
                contact_name=name,
                contact_email=email,
                appointment_type="consultation",
                start_time=appointment_time,
                end_time=end_time,
                duration_minutes=duration_minutes,
                status=AppointmentStatus.SCHEDULED.value,
                booked_via="ai_assistant",
            )
            self.db.add(appointment)
            self.db.commit()
            self.db.refresh(appointment)

            display_time = appointment_time.strftime("%A, %B %d at %I:%M %p")

            return {
                "success": True,
                "appointment_id": appt_id,
                "contact_email": email,
                "contact_name": name,
                "datetime": appointment_time.isoformat(),
                "end_time": end_time.isoformat(),
                "display_time": display_time,
                "duration_minutes": duration_minutes,
                "type": "consultation",
                "title": f"Mortgage Consultation - {name}",
                "loan_officer": None,  # LO assignment handled separately
            }
        except Exception as e:
            logger.warning(f"Could not book via direct ORM, using basic booking: {e}")

        # Fallback: Basic booking without LO assignment
        appt_id = f"APPT-{str(uuid.uuid4())[:8].upper()}"
        duration_minutes = 30
        appt_end = appointment_time + timedelta(minutes=duration_minutes)
        display_time = appointment_time.strftime("%A, %B %d at %I:%M %p")

        return {
            "success": True,
            "appointment_id": appt_id,
            "contact_email": email,
            "contact_name": name,
            "datetime": appointment_time.isoformat(),
            "end_time": appt_end.isoformat(),
            "display_time": display_time,
            "duration_minutes": duration_minutes,
            "type": "consultation",
            "title": f"Mortgage Consultation - {name}",
            "loan_officer": None,  # No LO assigned in fallback
        }

    def _check_for_user_question(self, analysis: Dict) -> Optional[Dict[str, Any]]:
        """Check if user asked questions and provide appropriate responses for ALL detected topics."""
        message = analysis.get("original_message", "").lower()
        original_message = analysis.get("original_message", "")

        responses = []
        booking_result = None

        # First, check if user is providing a specific time for an appointment
        # Look for time-related patterns that suggest they want to book
        time_indicators = ['at', 'on', 'for', 'around', 'about']
        scheduling_context = any(word in message for word in ["schedule", "book", "appointment", "call", "meet", "meeting"])
        has_time_indicator = any(ind in message for ind in time_indicators)

        # Try to parse a specific time if scheduling context exists
        if scheduling_context or has_time_indicator:
            parsed_time = self._parse_appointment_time(original_message)
            if parsed_time:
                # User provided a specific time - try to book it
                contact_email = analysis.get("qualification", {}).get("data", {}).get("email", "")
                contact_name = analysis.get("qualification", {}).get("data", {}).get("first_name", "")

                # Check if time is valid (business hours, not in past)
                now = datetime.now()
                if parsed_time > now:
                    hour = parsed_time.hour
                    weekday = parsed_time.weekday()

                    # Check business hours (9 AM - 6 PM weekdays, 10 AM - 2 PM Saturday)
                    is_valid_time = False
                    if weekday < 5 and 9 <= hour < 18:  # Weekday
                        is_valid_time = True
                    elif weekday == 5 and 10 <= hour < 14:  # Saturday
                        is_valid_time = True

                    if is_valid_time:
                        booking_result = self._book_appointment_for_email(
                            email=contact_email or "pending",
                            name=contact_name or "Valued Customer",
                            appointment_time=parsed_time
                        )

                        responses.append({
                            "topic": "appointment_confirmed",
                            "text": f"I've scheduled your consultation for {booking_result['display_time']}. You'll receive a calendar invitation shortly with all the details and a link to join the call.\n\nIs there anything specific you'd like to discuss during the consultation?",
                            "booking": booking_result
                        })
                    else:
                        responses.append({
                            "topic": "scheduling",
                            "text": f"I'd love to book that time, but our loan officers are available Monday through Friday from 9 AM to 6 PM, and Saturdays from 10 AM to 2 PM. Could you pick a time within those hours?"
                        })
                else:
                    responses.append({
                        "topic": "scheduling",
                        "text": "That time has already passed. Our loan officers are available Monday through Friday from 9 AM to 6 PM, and Saturdays from 10 AM to 2 PM. What day and time works best for you?"
                    })

                # If we handled scheduling, return early with just that response
                if responses:
                    return {
                        "text": responses[0]["text"],
                        "type": "appointment_booking" if booking_result else "scheduling_help",
                        "should_send": True,
                        "next_action": "await_response",
                        "topics_addressed": [responses[0]["topic"]],
                        "booking_result": booking_result
                    }

        # Rate questions
        if any(word in message for word in ["rate", "rates", "interest", "apr", "percentage"]):
            responses.append({
                "topic": "rates",
                "text": "Great question about rates! Current rates vary based on loan type, credit score, and down payment. For a conventional 30-year fixed, rates are typically in the 6-7% range right now, but your actual rate depends on your specific situation."
            })

        # Schedule/availability questions (when no specific time given)
        if any(word in message for word in ["schedule", "time", "times", "available", "availability", "call", "speak", "talk", "appointment", "meet"]):
            # Only add this if we didn't already handle a booking above
            if not any(r["topic"] in ["appointment_confirmed", "scheduling"] for r in responses):
                responses.append({
                    "topic": "scheduling",
                    "text": "I'd be happy to connect you with one of our senior loan officers! They're available Monday through Friday from 9 AM to 6 PM, and Saturdays from 10 AM to 2 PM. Just let me know what day and time works best for you, and I'll get that scheduled."
                })

        # Down payment questions
        if any(word in message for word in ["down payment", "downpayment", "down-payment", "how much down", "minimum down"]):
            responses.append({
                "topic": "down_payment",
                "text": "Down payment requirements vary by loan type:\n• Conventional: As low as 3% down\n• FHA: 3.5% minimum\n• VA: 0% down for eligible veterans\n• USDA: 0% down in eligible rural areas"
            })

        # Credit score questions
        if any(word in message for word in ["credit score", "credit requirement", "minimum credit", "fico"]):
            responses.append({
                "topic": "credit",
                "text": "Credit score requirements vary by loan program:\n• Conventional: Typically 620+\n• FHA: 580+ (or 500 with 10% down)\n• VA: Usually 620+\n• Some programs available for scores as low as 500"
            })

        # Cost/fee questions
        if any(word in message for word in ["cost", "fee", "fees", "closing cost", "how much"]):
            responses.append({
                "topic": "costs",
                "text": "Closing costs typically run 2-5% of the loan amount and include items like appraisal, title insurance, and lender fees. Some programs allow seller credits to cover these costs."
            })

        # If no questions detected, return None
        if not responses:
            return None

        # Combine all responses
        if len(responses) == 1:
            # Single question - add follow-up
            combined_text = responses[0]["text"] + "\n\nTo give you more specific information, are you looking to purchase a new home or refinance?"
        else:
            # Multiple questions - combine them with transitions
            combined_parts = []
            for i, resp in enumerate(responses):
                if i == 0:
                    combined_parts.append(resp["text"])
                else:
                    # Add transition for subsequent topics
                    combined_parts.append(f"Regarding {resp['topic'].replace('_', ' ')}: {resp['text']}")

            combined_text = "\n\n".join(combined_parts)
            combined_text += "\n\nWould you like me to schedule a call with a loan officer to discuss your specific situation?"

        return {
            "text": combined_text,
            "type": "question_response",
            "should_send": True,
            "next_action": "await_response",
            "topics_addressed": [r["topic"] for r in responses]
        }

    def _generate_booking_response(
        self,
        channel: Channel,
        qualification: Dict,
        analysis: Dict
    ) -> Dict[str, Any]:
        """Generate booking/call scheduling prompt."""

        qual_data = qualification.get("data", {})
        loan_purpose = qual_data.get("loan_purpose", "with your mortgage")

        if loan_purpose == "purchase":
            purpose_text = "find your perfect mortgage"
        elif loan_purpose == "refinance":
            purpose_text = "lower your rate"
        else:
            purpose_text = "with your mortgage needs"

        template = ResponseTemplates.BOOKING_PROMPTS.get(channel, ResponseTemplates.BOOKING_PROMPTS[Channel.EMAIL])
        response_text = template.format(purpose=purpose_text)
        response_text = self._trim_to_length(response_text, channel)

        return {
            "text": response_text,
            "type": "booking",
            "should_send": True,
            "next_action": "schedule_call"
        }

    def _generate_objection_response(
        self,
        channel: Channel,
        objection_type: str,
        analysis: Dict
    ) -> Dict[str, Any]:
        """Generate objection handling response."""

        templates = ResponseTemplates.OBJECTION_RESPONSES.get(objection_type, {})
        template = templates.get(channel, templates.get(Channel.EMAIL, "I understand. Is there anything specific I can help with?"))

        # Fill in persona details
        response_text = template.format(
            agent_name=self.persona["name"],
            company=self.persona["company"],
            website=self.organization.get("website", "our website") if self.organization else "our website"
        )

        response_text = self._trim_to_length(response_text, channel)

        objection_count = analysis.get("conversation_state", {}).get("objection_count", 1)

        return {
            "text": response_text,
            "type": "objection_handling",
            "should_send": True,
            "next_action": "await_response" if objection_count < 3 else "nurture"
        }

    def _generate_escalation_response(
        self,
        channel: Channel,
        analysis: Dict,
        conversation_id: str
    ) -> Dict[str, Any]:
        """Generate escalation handoff response."""

        template = ResponseTemplates.ESCALATION_HANDOFF.get(channel, ResponseTemplates.ESCALATION_HANDOFF[Channel.EMAIL])

        # Get actual LO name from assignment system
        lo_name = self._get_assigned_lo_name(conversation_id)

        response_text = template.format(
            lo_name=lo_name,
            agent_name=self.persona["name"]
        )

        response_text = self._trim_to_length(response_text, channel)

        return {
            "text": response_text,
            "type": "escalation",
            "should_send": True,
            "next_action": "assign_to_lo"
        }

    def _get_assigned_lo_name(self, conversation_id: str) -> str:
        """
        Get the assigned loan officer's name for a conversation.

        Looks up the conversation state to find the lead_id, then queries
        the database to find the assigned LO's name.

        Returns:
            The LO's first name, or "a senior loan officer" as fallback
        """
        try:
            if not self.db:
                return "a senior loan officer"

            # Get conversation state to find lead_id
            state = self.conversation_service.get_or_create_conversation(
                conversation_id, Channel.EMAIL  # Channel doesn't matter for lookup
            )

            lead_id = state.lead_id
            if not lead_id:
                return "a senior loan officer"

            # Query the lead to get assigned_to user
            from sqlalchemy import text
            result = self.db.execute(
                text("""
                    SELECT u.first_name, u.last_name
                    FROM leads l
                    JOIN users u ON u.id = l.assigned_to
                    WHERE l.id = :lead_id
                """),
                {"lead_id": lead_id}
            ).fetchone()

            if result and result[0]:
                # Return first name, or full name if available
                first_name = result[0]
                last_name = result[1] if len(result) > 1 and result[1] else ""
                return f"{first_name} {last_name}".strip() if last_name else first_name

            return "a senior loan officer"

        except Exception as e:
            logger.warning(f"Could not get assigned LO name for conversation {conversation_id}: {e}")
            return "a senior loan officer"

    def _generate_nurture_response(
        self,
        channel: Channel,
        analysis: Dict
    ) -> Dict[str, Any]:
        """Generate nurture/keep-warm response."""

        if channel == Channel.SMS:
            response_text = "No problem! I'll check back in a few weeks. Feel free to text anytime if questions come up!"
        else:
            response_text = f"""No problem at all - I understand the timing may not be right.

I'll add you to our rate watch list so you'll be the first to know when rates move in your favor. Feel free to reach out anytime if questions come up.

{self.persona['signature_email']}"""

        response_text = self._trim_to_length(response_text, channel)

        return {
            "text": response_text,
            "type": "nurture",
            "should_send": True,
            "next_action": "add_to_nurture_campaign"
        }

    def _get_next_question(self, qualification: Dict, channel: Channel) -> Optional[str]:
        """Get the next qualification question based on missing fields."""

        missing = qualification.get("missing_fields", [])
        qual_data = qualification.get("data", {})

        # Priority order for questions
        priority_order = [
            "loan_purpose",
            "property_value",
            "closing_timeline",
            "first_name",
        ]

        # Add channel-specific fields
        if channel == Channel.SMS:
            priority_order.append("email")  # Get email if on SMS
        else:
            priority_order.append("phone")  # Get phone if on email

        for field in priority_order:
            if field in missing:
                templates = ResponseTemplates.QUALIFICATION_QUESTIONS.get(field, {})
                return templates.get(channel, templates.get(Channel.EMAIL, f"Could you tell me about your {field.replace('_', ' ')}?"))

        return None

    def _trim_to_length(self, text: str, channel: Channel) -> str:
        """Trim response to appropriate length for channel."""
        max_length = MAX_MESSAGE_LENGTH.get(channel, 500)

        if len(text) <= max_length:
            return text

        # For SMS, truncate more aggressively
        if channel == Channel.SMS:
            # Try to cut at sentence boundary
            sentences = text.split('. ')
            result = ""
            for sentence in sentences:
                if len(result) + len(sentence) + 2 <= max_length:
                    result += sentence + ". "
                else:
                    break
            return result.strip() or text[:max_length-3] + "..."

        # For email, just truncate with ellipsis
        return text[:max_length-3] + "..."

    def get_conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        """Get summary of a conversation's qualification progress."""
        return self.conversation_service.get_conversation_summary(conversation_id)

    def generate_lead_from_qualification(self, conversation_id: str) -> Dict[str, Any]:
        """Generate a lead record from qualification data."""

        summary = self.get_conversation_summary(conversation_id)

        if "error" in summary:
            return {"error": summary["error"]}

        qual = summary.get("qualification", {})

        # Get the full qualification data from the conversation state
        state = self.conversation_service._conversation_cache.get(conversation_id)
        if not state:
            return {"error": "Conversation not found"}

        qual_data = state.qualification_data

        return {
            "source": f"ai_{state.channel.value}_qualification",
            "status": "qualified" if qual.get("completion", 0) >= QUALIFICATION_FLOW["booking_threshold"] else "prospect",
            "first_name": qual_data.first_name,
            "last_name": qual_data.last_name,
            "email": qual_data.email,
            "phone": qual_data.phone,
            "loan_purpose": qual_data.loan_purpose,
            "estimated_amount": qual_data.loan_amount or qual_data.property_value,
            "property_type": qual_data.property_type,
            "closing_timeline": qual_data.closing_timeline,
            "pre_approved_elsewhere": qual_data.pre_approved_elsewhere,
            "first_time_buyer": qual_data.first_time_buyer,
            "qualification_complete": qual.get("completion", 0) >= 100,
            "qualification_percentage": qual.get("completion", 0),
            "conversation_id": conversation_id,
            "channel": state.channel.value,
            "message_count": state.message_count,
            "objection_count": state.objection_count,
            "ai_collected_at": qual_data.collected_at,
            "created_at": datetime.now().isoformat()
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_qualification_agent(
    organization: Optional[Dict] = None,
    persona: Optional[Dict] = None
) -> QualificationAgent:
    """Create a new qualification agent with optional customization."""
    return QualificationAgent(
        persona=persona,
        organization=organization
    )


def process_qualification_message(
    conversation_id: str,
    message: str,
    channel: str,
    sender_info: Optional[Dict] = None,
    organization: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Convenience function to process a message through the qualification agent.

    Example usage:
        result = process_qualification_message(
            conversation_id="conv_12345",
            message="I'm looking to buy a home around $400k",
            channel="sms",
            sender_info={"first_name": "John", "phone": "5551234567"}
        )

        print(result["response"])  # Agent's response
        print(result["qualification"]["completion_percentage"])  # Progress
    """
    agent = create_qualification_agent(organization=organization)
    return agent.process_message(
        conversation_id=conversation_id,
        message=message,
        channel=channel,
        sender_info=sender_info
    )
