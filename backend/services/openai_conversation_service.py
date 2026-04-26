"""
OpenAI Conversation Service

Provides AI-powered response generation for email and SMS conversations
using OpenAI's GPT models with optional Pinecone memory retrieval.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIConversationService:
    """Service for generating AI responses using OpenAI GPT models."""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # Cost-effective default

        if not self.api_key:
            logger.warning("OpenAI API key not configured - AI responses disabled")
            self.enabled = False
            self.client = None
        else:
            try:
                self.client = OpenAI(api_key=self.api_key)
                self.enabled = True
                logger.info(f"OpenAI conversation service initialized with model: {self.model}")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI: {e}")
                self.enabled = False
                self.client = None

        # Try to import Pinecone memory service
        try:
            from integrations.pinecone_service import vector_memory
            self.vector_memory = vector_memory if vector_memory.enabled else None
            if self.vector_memory:
                logger.info("Pinecone memory service connected")
        except Exception as e:
            logger.warning(f"Pinecone memory not available: {e}")
            self.vector_memory = None

    def _determine_phase(self, turn_count: int, user_message: str) -> int:
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

    def _build_system_prompt(
        self,
        persona: Dict,
        channel: str,
        qualification_data: Dict,
        conversation_stage: str,
        phase: int = 1,
        turn_count: int = 0
    ) -> str:
        """Build phase-appropriate system prompt following Trust-First Architecture."""

        lo_name = persona.get('lo_name', 'Tim')
        available_times = persona.get('available_times', 'Monday-Friday 9am-5pm, Saturday 10am-2pm')

        # Build collected info string from qualification data
        collected_items = []
        if qualification_data:
            field_labels = {
                'loan_purpose': 'Loan Purpose',
                'property_value': 'Property Value',
                'loan_amount': 'Loan Amount',
                'closing_timeline': 'Timeline',
                'first_name': 'First Name',
                'last_name': 'Last Name',
                'email': 'Email',
                'phone': 'Phone',
                'credit_score_range': 'Credit Score',
                'employment_status': 'Employment',
                'annual_income': 'Annual Income',
                'down_payment': 'Down Payment',
                'property_type': 'Property Type',
                'first_time_buyer': 'First Time Buyer',
                'pre_approved_elsewhere': 'Pre-Approved Elsewhere',
            }
            for field, label in field_labels.items():
                value = qualification_data.get(field)
                if value is not None and value != '':
                    collected_items.append(f"- {label}: {value}")

        if collected_items:
            collected_info = "\n".join(collected_items)
        else:
            collected_info = "- (No information collected yet - ask about their loan purpose first)"

        # Base context for all phases
        base_context = f"""You are {persona.get('name', 'Sarah')}, a {persona.get('role', 'Senior Mortgage Consultant')} at {persona.get('company', 'The Tim Loss Team')}.

## CRITICAL ROLE CLARIFICATION - READ CAREFULLY:
- YOU are Sarah, an AI mortgage assistant
- YOU are helping PROSPECTS who are interested in getting a mortgage
- The person you're talking to is a POTENTIAL CUSTOMER looking for mortgage help
- You work WITH {lo_name} (the loan officer) to help customers
- Your job is to ANSWER their questions, QUALIFY them, and SCHEDULE appointments with {lo_name}
- You are NOT a customer. You do NOT need a mortgage. You are the ASSISTANT helping them.

PERSONALITY & TONE:
- Warm, friendly, and professional
- Genuinely helpful and empathetic
- Knowledgeable about mortgages but explain things simply
- Never pushy or salesy - focus on understanding their needs
- Use their first name when you know it

CURRENT CHANNEL: {channel.upper()}

## CRITICAL: KEEP RESPONSES SHORT AND CONVERSATIONAL

⚠️ RESPONSE LENGTH RULES - FOLLOW STRICTLY:
- SMS: Maximum 160 characters (1 text message)
- Email: Maximum 2-4 sentences or 100 words
- Ask only ONE question at a time - never combine multiple questions
- Answer their question first, then ask a follow-up
- NO walls of text or long explanations
- Write like you're texting a friend, not writing an essay

IMPORTANT:
- Do NOT make up information about rates, programs, or requirements
- Never promise specific rates or approval
- Be honest and set realistic expectations
- NEVER pretend to be a customer or ask for mortgage help - you ARE the helper

## ALREADY COLLECTED INFORMATION (DO NOT RE-ASK THESE):
{collected_info}

CRITICAL: If information is listed above as "already collected", DO NOT ask for it again.
Move to the NEXT unanswered question instead. Acknowledge what they shared and continue forward.
"""

        # Phase-specific instructions
        if phase == 1:
            phase_instructions = f"""
## PHASE 1: REASSURE & ORIENT (Current Phase)

You're in the early trust-building phase. Be friendly and helpful.

DO:
- Answer their questions briefly and helpfully
- Be warm and use simple language
- Ask ONE follow-up question to understand their situation

DON'T:
- Offer calls or appointments yet
- Ask for contact information
- Be salesy or pushy
- Mention scheduling or consultations

Just be genuinely helpful - earn their trust first."""

        elif phase == 2:
            phase_instructions = f"""
## PHASE 2: EDUCATE (Current Phase)

Share your expertise briefly. Give honest tradeoffs when comparing options.

DO:
- Explain the "why" behind mortgage concepts
- Be balanced when discussing options
- Ask follow-up questions to understand their needs better

DON'T:
- Offer calls or appointments yet
- Ask for contact information
- Push any particular solution

Keep building credibility through helpful, SHORT answers."""

        elif phase == 3:
            phase_instructions = f"""
## PHASE 3: PERSONALIZE (Current Phase)

Ask questions to understand their specific situation better.

Good questions: timeline, price range, credit situation, down payment plans

DO:
- Be conversational and explain why you're asking
- Tailor your advice to what they've shared

DON'T:
- Offer calls or appointments yet
- Ask multiple questions at once
- Be pushy about gathering information

Keep responses SHORT - you're having a conversation, not conducting an interview."""

        else:  # Phase 4
            phase_instructions = f"""
## PHASE 4: OFFER NEXT STEP - WITH VALUE PITCH (Current Phase)

You've built trust through the conversation. Now you CAN offer to connect them with {lo_name}.

WHEN RECOMMENDING THE LOAN OFFICER - USE THIS VALUE PITCH:
"I'd recommend setting up a quick call with {lo_name}. He talks with all our clients before they start looking - even 20 minutes can help you get the best home for the best price and put you in a strong position to potentially save thousands. Plus, his free mortgage planning program has saved clients tens of thousands over the years."

Available times: {available_times}

If they're not ready: "No problem! I'm here whenever you have more questions."

DO NOT just say "I recommend reaching out to your loan officer" - always include the value pitch and specific times."""

        return base_context + phase_instructions

    async def generate_response(
        self,
        conversation_id: str,
        channel: str,
        user_message: str,
        conversation_history: List[Dict],
        qualification_data: Dict,
        conversation_stage: str,
        persona: Dict = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate an AI response using OpenAI.

        Args:
            conversation_id: Unique conversation identifier
            channel: 'email' or 'sms'
            user_message: The user's current message
            conversation_history: List of previous messages [{role, content}]
            qualification_data: Currently collected qualification data
            conversation_stage: Current stage of the conversation
            persona: Agent persona configuration
            user_id: User ID for Pinecone memory retrieval

        Returns:
            Dict with response text and metadata
        """
        if not self.enabled:
            logger.warning("OpenAI not enabled - returning fallback response")
            return {
                "text": "Thank you for your message. A mortgage specialist will get back to you shortly.",
                "type": "fallback",
                "ai_generated": False,
                "error": "OpenAI not configured"
            }

        # Default persona
        if not persona:
            persona = {
                "name": "Sarah",
                "role": "Senior Mortgage Consultant",
                "company": "The Tim Loss Team",
                "lo_name": "Tim",  # Default LO name for value pitch
                "available_times": "Monday-Friday 9am-5pm, Saturday 10am-2pm"
            }

        try:
            # Calculate turn count from conversation history
            turn_count = len([m for m in conversation_history if m.get("role") == "user"])

            # Determine conversation phase based on Trust-First Architecture
            phase = self._determine_phase(turn_count, user_message)

            # Build phase-appropriate system prompt
            system_prompt = self._build_system_prompt(
                persona=persona,
                channel=channel,
                qualification_data=qualification_data,
                conversation_stage=conversation_stage,
                phase=phase,
                turn_count=turn_count
            )

            # Build messages array
            messages = [{"role": "system", "content": system_prompt}]

            # Retrieve relevant context from Pinecone if available
            relevant_context = []
            if self.vector_memory and user_id:
                try:
                    relevant_context = await self.vector_memory.retrieve_relevant_context(
                        user_id=user_id,
                        current_query=user_message,
                        top_k=3
                    )
                    if relevant_context:
                        context_text = "\n".join([
                            f"[Previous conversation - {ctx['timestamp']}]: {ctx['text']}"
                            for ctx in relevant_context
                        ])
                        messages.append({
                            "role": "system",
                            "content": f"RELEVANT PAST CONTEXT:\n{context_text}"
                        })
                        logger.info(f"Retrieved {len(relevant_context)} relevant contexts from Pinecone")
                except Exception as e:
                    logger.warning(f"Failed to retrieve Pinecone context: {e}")

            # Add conversation history (last 10 messages for context)
            for msg in conversation_history[-10:]:
                role = "assistant" if msg.get("role") == "assistant" else "user"
                messages.append({"role": role, "content": msg.get("content", "")})

            # Add current user message
            messages.append({"role": "user", "content": user_message})

            # Set max tokens based on channel
            max_tokens = 100 if channel == "sms" else 300

            # Call OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
                presence_penalty=0.1,
                frequency_penalty=0.1
            )

            ai_response = response.choices[0].message.content.strip()

            # Truncate SMS to 160 chars if needed
            if channel == "sms" and len(ai_response) > 160:
                # Try to truncate at a sentence boundary
                truncated = ai_response[:157]
                last_period = truncated.rfind('.')
                last_question = truncated.rfind('?')
                last_sentence = max(last_period, last_question)
                if last_sentence > 100:
                    ai_response = truncated[:last_sentence + 1]
                else:
                    ai_response = truncated + "..."

            # Store conversation in Pinecone for future retrieval
            if self.vector_memory and user_id:
                try:
                    await self.vector_memory.store_conversation(
                        user_id=user_id,
                        conversation_text=f"User: {user_message}\nAssistant: {ai_response}",
                        metadata={
                            "conversation_id": conversation_id,
                            "channel": channel,
                            "stage": conversation_stage,
                            "qualification_pct": qualification_data.get("completion_percentage", 0)
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to store in Pinecone: {e}")

            # Detect if response is trying to book an appointment
            is_booking = any(phrase in ai_response.lower() for phrase in [
                "schedule", "book", "appointment", "call you", "consultation",
                "what time", "when works", "available"
            ])

            logger.info(f"OpenAI response generated for {conversation_id} (phase {phase}, {len(ai_response)} chars)")

            return {
                "text": ai_response,
                "type": "booking" if is_booking else "qualification",
                "ai_generated": True,
                "model": self.model,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "pinecone_contexts": len(relevant_context),
                "trust_phase": phase,
                "turn_count": turn_count
            }

        except Exception as e:
            logger.error(f"OpenAI response generation failed: {e}")
            return {
                "text": "Thank you for your message. Let me look into that and get back to you shortly.",
                "type": "error_fallback",
                "ai_generated": False,
                "error": "Internal server error"
            }

    def generate_email_response_sync(
        self,
        conversation_id: str,
        user_message: str,
        conversation_history: List[Dict],
        loan_context: str = "",
        additional_context: str = "",
        lo_name: str = "Tim",
        lo_available_times: str = "Monday-Friday 9am-5pm, Saturday 10am-2pm"
    ) -> Dict[str, Any]:
        """
        Generate an AI response for email conversations (synchronous version).

        This is the consolidated method for all email AI responses.
        Uses Trust-First Architecture to determine appropriate phase.

        Args:
            conversation_id: Unique conversation identifier
            user_message: The user's current message
            conversation_history: List of previous messages [{role, content}]
            loan_context: Optional loan information context
            additional_context: Any additional context
            lo_name: Loan officer name for value pitch
            lo_available_times: Available appointment times

        Returns:
            Dict with response text and metadata
        """
        if not self.enabled:
            logger.warning("OpenAI not enabled - returning fallback response")
            return {
                "text": "Thank you for your message. A mortgage specialist will get back to you shortly.",
                "ai_generated": False,
                "error": "OpenAI not configured"
            }

        try:
            # Calculate turn count from conversation history
            turn_count = len([m for m in conversation_history if m.get("role") == "user"])

            # Determine conversation phase based on Trust-First Architecture
            phase = self._determine_phase(turn_count, user_message)

            # Build the system prompt with Trust-First phases
            system_prompt = self._build_email_system_prompt(
                phase=phase,
                turn_count=turn_count,
                loan_context=loan_context,
                additional_context=additional_context,
                lo_name=lo_name,
                lo_available_times=lo_available_times
            )

            # Build messages array
            messages = [{"role": "system", "content": system_prompt}]

            # Add conversation history (last 10 messages for context)
            for msg in conversation_history[-10:]:
                role = "assistant" if msg.get("role") == "assistant" else "user"
                messages.append({"role": role, "content": msg.get("content", "")})

            # Add current user message
            messages.append({"role": "user", "content": user_message})

            # Call OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=300,
                temperature=0.7
            )

            ai_response = response.choices[0].message.content.strip()

            logger.info(f"Email response generated for {conversation_id} (phase {phase}, turn {turn_count}, {len(ai_response)} chars)")

            return {
                "text": ai_response,
                "ai_generated": True,
                "model": self.model,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "trust_phase": phase,
                "turn_count": turn_count
            }

        except Exception as e:
            logger.error(f"Email response generation failed: {e}")
            return {
                "text": "Thank you for your message. Let me look into that and get back to you shortly.",
                "ai_generated": False,
                "error": "Internal server error"
            }

    def _build_email_system_prompt(
        self,
        phase: int,
        turn_count: int,
        loan_context: str = "",
        additional_context: str = "",
        lo_name: str = "Tim",
        lo_available_times: str = "Monday-Friday 9am-5pm, Saturday 10am-2pm"
    ) -> str:
        """Build phase-appropriate system prompt for email responses."""

        base_prompt = f"""You are Sarah, an AI Mortgage Assistant for The Tim Loss Team, responding to email inquiries.

## CRITICAL ROLE CLARIFICATION:
- YOU work WITH {lo_name} (the loan officer) to help customers
- {lo_name} is YOUR loan officer - the person you're emailing IS the customer/prospect
- NEVER say "I recommend checking with your lender" - YOU ARE the lender's assistant!
- When someone asks about rates: offer to have {lo_name} get them personalized numbers

PERSONALITY & TONE:
- Warm, friendly, and professional
- Genuinely helpful and empathetic
- Knowledgeable about mortgages but explain things simply
- Never pushy or salesy

{loan_context}

{f"Additional Context: {additional_context}" if additional_context else ""}

## CRITICAL: KEEP RESPONSES SHORT AND CONVERSATIONAL

⚠️ RESPONSE LENGTH RULES - FOLLOW STRICTLY:
- Keep responses to 2-4 SHORT sentences maximum
- Answer ONE question at a time
- NO walls of text or long explanations
- NO numbered lists with 5+ items

IMPORTANT FOR RATE/PROGRAM QUESTIONS:
- Do NOT say "check with your lender/website" - that's nonsensical since YOU are the lender's assistant
- For rate questions: "I don't have your specific rate info, but {lo_name} can get you exact numbers based on your situation. Want me to set that up?"
- For program questions: Answer generally if you know, then offer {lo_name} for specifics
- Never promise specific rates or approval
"""

        # Phase-specific instructions
        if phase == 1:
            phase_instructions = f"""
## PHASE 1: REASSURE & ORIENT (Turn {turn_count})

You're in the early trust-building phase. Be friendly and helpful.

DO: Answer their questions briefly, be warm, ask ONE follow-up question
DON'T: Offer calls/appointments, ask for contact info, be salesy

Just be genuinely helpful - earn their trust first."""

        elif phase == 2:
            phase_instructions = f"""
## PHASE 2: EDUCATE (Turn {turn_count})

Share your expertise briefly. Give honest tradeoffs when comparing options.

DO: Explain the "why", be balanced, ask follow-up questions
DON'T: Offer calls/appointments, ask for contact info, push solutions

Keep building credibility through helpful, SHORT answers."""

        elif phase == 3:
            phase_instructions = f"""
## PHASE 3: PERSONALIZE (Turn {turn_count})

Ask questions to understand their specific situation better.

DO: Be conversational, tailor advice to what they've shared
DON'T: Offer calls/appointments yet, ask multiple questions at once

Keep responses SHORT - you're having a conversation, not conducting an interview."""

        else:  # Phase 4
            phase_instructions = f"""
## PHASE 4: OFFER NEXT STEP - WITH VALUE PITCH (Turn {turn_count})

You've built trust through the conversation. Now you CAN offer to connect them with {lo_name}.

WHEN RECOMMENDING THE LOAN OFFICER - USE THIS VALUE PITCH:
"I'd recommend setting up a quick call with {lo_name}. He talks with all our clients before they start looking - even 20 minutes can help you get the best home for the best price and put you in a strong position to potentially save thousands. Plus, his free mortgage planning program has saved clients tens of thousands over the years. Here are some times that work: {lo_available_times}"

If they're not ready: "No problem! I'm here whenever you have more questions."

DO NOT just say "I recommend reaching out to your loan officer" - always include the value pitch and specific times."""

        return base_prompt + phase_instructions + """

Sign off as:
Best regards,
Sarah
AI Mortgage Assistant | The Tim Loss Team"""

    async def analyze_message(
        self,
        message: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """
        Analyze a message for intent, sentiment, and extract qualification data.

        Args:
            message: The message to analyze
            context: Additional context about the conversation

        Returns:
            Dict with analysis results
        """
        if not self.enabled:
            return {"error": "OpenAI not configured"}

        try:
            analysis_prompt = f"""Analyze this message from a mortgage lead and extract information.

MESSAGE: {message}

CONTEXT: {context}

Return a JSON object with:
{{
    "sentiment": "positive" | "neutral" | "negative",
    "urgency": "low" | "medium" | "high",
    "intent": "question" | "information" | "scheduling" | "objection" | "greeting" | "other",
    "extracted_data": {{
        "first_name": string or null,
        "last_name": string or null,
        "phone": string or null,
        "email": string or null,
        "loan_purpose": "purchase" | "refinance" | "cash_out" | null,
        "property_value": number or null,
        "property_type": string or null,
        "closing_timeline": string or null,
        "credit_score_range": string or null,
        "employment_status": string or null,
        "annual_income": number or null,
        "down_payment": number or null
    }},
    "questions_asked": [list of questions the user asked],
    "objections": [list of any objections or concerns expressed],
    "appointment_time_mentioned": string or null (if they mentioned a specific time)
}}

Only include fields that are explicitly mentioned. Return valid JSON only."""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a message analyzer. Return only valid JSON."},
                    {"role": "user", "content": analysis_prompt}
                ],
                max_tokens=500,
                temperature=0.1  # Low temperature for consistent extraction
            )

            result_text = response.choices[0].message.content.strip()

            # Parse JSON response
            # Handle potential markdown code blocks
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]

            analysis = json.loads(result_text)
            analysis["ai_analyzed"] = True

            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI analysis response: {e}")
            return {"error": "Failed to parse analysis", "ai_analyzed": False}
        except Exception as e:
            logger.error(f"OpenAI analysis failed: {e}")
            return {"error": "Internal server error", "ai_analyzed": False}


# Global instance
openai_conversation_service = OpenAIConversationService()


def get_openai_service() -> OpenAIConversationService:
    """Get the OpenAI conversation service instance."""
    return openai_conversation_service
