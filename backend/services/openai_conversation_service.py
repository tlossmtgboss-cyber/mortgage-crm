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

    def _build_system_prompt(
        self,
        persona: Dict,
        channel: str,
        qualification_data: Dict,
        conversation_stage: str
    ) -> str:
        """Build the system prompt for the AI assistant."""

        # Calculate what qualification fields are still needed
        required_fields = ["loan_purpose", "property_value", "closing_timeline", "first_name"]
        if channel == "sms":
            required_fields.append("email")
        else:
            required_fields.append("phone")

        collected_fields = [f for f in required_fields if qualification_data.get(f)]
        missing_fields = [f for f in required_fields if not qualification_data.get(f)]

        completion_pct = (len(collected_fields) / len(required_fields)) * 100 if required_fields else 0

        # Field descriptions for natural conversation
        field_questions = {
            "loan_purpose": "whether they're looking to purchase, refinance, or get a cash-out refinance",
            "property_value": "the approximate property value or purchase price they're considering",
            "closing_timeline": "their timeline - when they're hoping to close or move",
            "first_name": "their first name",
            "phone": "a phone number to reach them",
            "email": "an email address to send them information"
        }

        missing_descriptions = [field_questions.get(f, f) for f in missing_fields]

        system_prompt = f"""You are {persona.get('name', 'Sarah')}, a {persona.get('role', 'Senior Mortgage Consultant')} at {persona.get('company', 'Perennia AI')}.

PERSONALITY & TONE:
- Warm, friendly, and professional
- Genuinely helpful and empathetic
- Knowledgeable about mortgages but explain things simply
- Never pushy or salesy - focus on understanding their needs
- Use their first name when you know it

CONVERSATION RULES - CRITICAL:
1. Ask only ONE question at a time - never combine multiple questions
2. Acknowledge what they shared before asking the next question
3. Keep responses concise:
   - SMS: Maximum 160 characters (1 text message)
   - Email: Maximum 150 words
4. If they ask a question, answer it first, then continue qualifying
5. Never repeat information they've already given you
6. If they seem frustrated or hesitant, acknowledge their feelings

CURRENT CHANNEL: {channel.upper()}

QUALIFICATION STATUS:
- Progress: {completion_pct:.0f}% complete
- Information collected: {', '.join(collected_fields) if collected_fields else 'None yet'}
- Still need to learn: {', '.join(missing_descriptions) if missing_descriptions else 'Qualification complete!'}

QUALIFICATION DATA COLLECTED:
{json.dumps(qualification_data, indent=2)}

CONVERSATION STAGE: {conversation_stage}

YOUR GOALS:
1. Build rapport and understand their situation
2. Naturally gather the missing qualification information through conversation
3. When qualification is 80%+ complete, offer to schedule a consultation call
4. Answer any mortgage questions they have accurately and helpfully

APPOINTMENT BOOKING:
- If they want to schedule, ask for their preferred day and time
- Available times: Monday-Friday 9am-5pm, Saturday 10am-2pm
- Confirm the appointment details before finalizing

IMPORTANT:
- Do NOT make up information about rates, programs, or requirements
- If you don't know something specific, say you'll have a loan officer provide those details
- Never promise specific rates or approval
- Be honest and set realistic expectations

Remember: You're having a natural conversation, not filling out a form. Make them feel heard and understood."""

        return system_prompt

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
                "company": "Perennia AI"
            }

        try:
            # Build system prompt
            system_prompt = self._build_system_prompt(
                persona=persona,
                channel=channel,
                qualification_data=qualification_data,
                conversation_stage=conversation_stage
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

            logger.info(f"OpenAI response generated for {conversation_id} ({len(ai_response)} chars)")

            return {
                "text": ai_response,
                "type": "booking" if is_booking else "qualification",
                "ai_generated": True,
                "model": self.model,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "pinecone_contexts": len(relevant_context)
            }

        except Exception as e:
            logger.error(f"OpenAI response generation failed: {e}")
            return {
                "text": "Thank you for your message. Let me look into that and get back to you shortly.",
                "type": "error_fallback",
                "ai_generated": False,
                "error": str(e)
            }

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
            return {"error": str(e), "ai_analyzed": False}


# Global instance
openai_conversation_service = OpenAIConversationService()


def get_openai_service() -> OpenAIConversationService:
    """Get the OpenAI conversation service instance."""
    return openai_conversation_service
