"""SMS conversation threading — maintains multi-turn context for AI SMS conversations.

Uses Claude (Anthropic API) for intelligent, contextual response generation with
canned templates as fallback. Integrates with the Deal Breaker bridge for
qualification routing.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

from sqlalchemy.orm import Session

from database.models.sms_conversation import SMSAIConversation as SMSConversation, SMSAIConversationMessage as SMSConversationMessage
from services.sms_intent_detector import SMSIntentDetector

logger = logging.getLogger(__name__)

# Claude model for SMS response generation
_CLAUDE_MODEL = "claude-sonnet-4-20250514"
_CLAUDE_MAX_TOKENS = 300
_CLAUDE_TIMEOUT = 10.0  # seconds — SMS responses must be fast


class SMSConversationManager:
    """Tracks conversation state and context across SMS messages."""

    def __init__(self):
        self.intent_detector = SMSIntentDetector()
        self._anthropic_client = None

    def _get_anthropic_client(self):
        """Lazy-init async Anthropic client. Returns None if API key not configured."""
        if self._anthropic_client is None:
            try:
                import anthropic
                self._anthropic_client = anthropic.AsyncAnthropic(
                    timeout=_CLAUDE_TIMEOUT,
                )
            except Exception as e:
                logger.warning("Failed to initialize Anthropic client: %s", e)
                return None
        return self._anthropic_client

    async def process_inbound(self, db: Session, phone: str, message: str, org_id: str) -> Dict:
        """Process inbound SMS with conversation context. Returns response to send."""
        # 1. Get or create conversation thread
        conversation = self._get_or_create_conversation(db, phone, org_id)

        # 2. Detect intent
        context = {"current_stage": conversation.current_stage}
        intent_result = self.intent_detector.detect_intent(message, context)

        # Escalate to LLM if ambiguous
        if self.intent_detector.needs_llm_classification(intent_result):
            history = self.get_conversation_history(db, phone, org_id, limit=5)
            history_dicts = [{"direction": m.direction, "content": m.content} for m in history]
            intent_result = await self.intent_detector.detect_intent_llm(message, history_dicts)

        # 3. Store inbound message
        inbound_msg = SMSConversationMessage(
            conversation_id=conversation.id,
            direction="inbound",
            content=message,
            intent=intent_result.intent,
            confidence=intent_result.confidence,
            intent_method=intent_result.method,
            entities=intent_result.entities,
            ai_generated=False,
        )
        db.add(inbound_msg)

        # 4. Update conversation state
        if intent_result.suggested_stage and intent_result.confidence >= 0.7:
            conversation.current_stage = intent_result.suggested_stage

        # Merge extracted entities into context_data
        if intent_result.entities:
            ctx = conversation.context_data or {}
            ctx.update(intent_result.entities)
            conversation.context_data = ctx

        conversation.last_message_at = datetime.now(timezone.utc)
        conversation.message_count = (conversation.message_count or 0) + 1

        # 5. Check Deal Breaker bridge after qualifying data accumulates
        deal_breaker_result = await self._check_deal_breaker(db, conversation)

        # 6. Generate AI response
        if deal_breaker_result and deal_breaker_result.get("action") != "skip":
            # Deal breaker evaluation produced a routing decision — use its response
            response_text = deal_breaker_result.get("sms_response", "")
            if deal_breaker_result.get("next_stage"):
                conversation.current_stage = deal_breaker_result["next_stage"]
        else:
            response_text = await self._generate_response(
                db, conversation, message, intent_result
            )

        # 7. Store outbound message
        outbound_msg = SMSConversationMessage(
            conversation_id=conversation.id,
            direction="outbound",
            content=response_text,
            intent=intent_result.intent,
            ai_generated=True,
        )
        db.add(outbound_msg)
        conversation.message_count = (conversation.message_count or 0) + 1

        db.commit()

        return {
            "response": response_text,
            "intent": intent_result.intent,
            "confidence": intent_result.confidence,
            "conversation_id": conversation.id,
            "stage": conversation.current_stage,
        }

    def get_conversation_history(self, db: Session, phone: str, org_id: str, limit: int = 20) -> List:
        """Get recent conversation messages for context window."""
        conversation = db.query(SMSConversation).filter(
            SMSConversation.phone_number == phone,
            SMSConversation.organization_id == org_id,
            SMSConversation.status == "active",
        ).first()

        if not conversation:
            return []

        return db.query(SMSConversationMessage).filter(
            SMSConversationMessage.conversation_id == conversation.id,
        ).order_by(SMSConversationMessage.created_at.desc()).limit(limit).all()[::-1]

    def close_conversation(self, db: Session, phone: str, org_id: str, reason: str):
        """Close conversation thread."""
        conversation = db.query(SMSConversation).filter(
            SMSConversation.phone_number == phone,
            SMSConversation.organization_id == org_id,
            SMSConversation.status == "active",
        ).first()

        if conversation:
            conversation.status = "closed"
            conversation.close_reason = reason
            db.commit()

    def _get_or_create_conversation(self, db: Session, phone: str, org_id: str) -> SMSConversation:
        """Get active conversation or create new one."""
        conversation = db.query(SMSConversation).filter(
            SMSConversation.phone_number == phone,
            SMSConversation.organization_id == org_id,
            SMSConversation.status == "active",
        ).first()

        if not conversation:
            # Try to find associated lead by phone
            lead_id = None
            try:
                from database.models.lead_loan import Lead
                lead = db.query(Lead).filter(Lead.phone == phone).first()
                if lead:
                    lead_id = lead.id
            except Exception as _exc:  # noqa: BLE001
                pass

            conversation = SMSConversation(
                phone_number=phone,
                lead_id=lead_id,
                organization_id=org_id,
            )
            db.add(conversation)
            db.flush()

        return conversation

    # -----------------------------------------------------------------------
    # Deal Breaker integration
    # -----------------------------------------------------------------------

    async def _check_deal_breaker(self, db: Session, conversation: SMSConversation) -> Optional[Dict]:
        """Check if qualification data is sufficient for deal breaker evaluation."""
        try:
            from services.engagement_deal_breaker_bridge import (
                should_evaluate,
                evaluate_qualification_data,
                on_qualification_stage_complete,
            )

            ctx = conversation.context_data or {}
            if not should_evaluate(ctx):
                return {"action": "skip"}

            result = await on_qualification_stage_complete(
                db=db,
                conversation_id=conversation.id,
                lead_id=str(conversation.lead_id) if conversation.lead_id else None,
                context_data=ctx,
                organization_id=conversation.organization_id,
            )

            # Persist the updated context_data (deal breaker flags)
            conversation.context_data = ctx

            return result
        except Exception as e:
            logger.exception("Deal breaker evaluation failed: %s", e)
            return {"action": "skip", "reason": "error"}

    # -----------------------------------------------------------------------
    # Cross-channel context — prior call summaries
    # -----------------------------------------------------------------------

    def _get_prior_call_summary(self, db: Session, conversation: SMSConversation) -> Optional[str]:
        """Fetch summaries of prior calls with this lead for cross-channel awareness."""
        if not conversation.lead_id:
            return None

        try:
            from database.models.communication import Activity
            from database.enums import ActivityType

            calls = db.query(Activity).filter(
                Activity.lead_id == conversation.lead_id,
                Activity.type == ActivityType.CALL,
            ).order_by(Activity.created_at.desc()).limit(3).all()

            if not calls:
                return None

            summaries = []
            for call in calls:
                when = call.created_at.strftime("%b %d") if call.created_at else "unknown date"
                content = (call.content or "No notes")[:150]
                sentiment = f" (sentiment: {call.sentiment})" if call.sentiment else ""
                summaries.append(f"- {when}: {content}{sentiment}")

            return "Prior calls with this lead:\n" + "\n".join(summaries)
        except Exception as e:
            logger.debug("Could not fetch prior call context: %s", e)
            return None

    # -----------------------------------------------------------------------
    # Persona config
    # -----------------------------------------------------------------------

    def _get_persona_config(self, db: Session, org_id: str) -> Dict[str, Any]:
        """Load per-tenant persona configuration from script_customization."""
        try:
            from services.script_customization_service import ScriptCustomizationService
            svc = ScriptCustomizationService()
            config = svc.get_config(db, org_id)
            return config.get("persona", {})
        except Exception as e:
            logger.debug("Could not load persona config: %s", e)
            return {}

    # -----------------------------------------------------------------------
    # AI response generation (Claude primary, templates fallback)
    # -----------------------------------------------------------------------

    def _build_system_prompt(
        self,
        conversation: SMSConversation,
        persona: Dict[str, Any],
        call_summary: Optional[str],
    ) -> str:
        """Build the system prompt for Claude SMS response generation."""
        persona_name = persona.get("name", "Aria")
        personality = persona.get("personality", "professional, warm, knowledgeable")

        ctx = conversation.context_data or {}
        collected_data = {k: v for k, v in ctx.items() if not k.startswith("_")}

        prompt_parts = [
            f"You are {persona_name}, an AI mortgage assistant for a loan officer. "
            f"Your personality is {personality}.",
            "",
            "RULES (you must follow these exactly):",
            "- You are having an SMS text conversation. Keep responses concise.",
            "- If the borrower asks a simple question, respond in under 160 characters (1 SMS segment).",
            "- If the borrower asks a detailed question, you may use up to 300 characters (2 SMS segments).",
            "- NEVER quote specific interest rates, APRs, or fees — say 'rates change daily' or offer to connect with the LO.",
            "- You MUST comply with ECOA: never reference race, color, religion, national origin, sex, marital status, age, or public assistance status.",
            "- If asked whether you are a real person or AI, honestly say you are an AI assistant working with their loan officer.",
            "- When discussing loan products or programs, include NMLS# if available from the persona config.",
            "- Ask ONE question at a time during qualification.",
            "- Use empathetic, conversational language — not corporate or robotic.",
            "- NEVER repeat the exact same phrasing you used in a previous message in this conversation.",
            "- If the borrower says stop, unsubscribe, or wants no further contact, respect it immediately.",
            "",
            f"Current conversation stage: {conversation.current_stage}",
        ]

        if collected_data:
            prompt_parts.append(f"Data collected so far: {collected_data}")

        questions_asked = ctx.get("_questions_asked", [])
        if questions_asked:
            prompt_parts.append(f"Questions already asked: {questions_asked}")

        all_qualifying_fields = ["loan_purpose", "timeline", "price_range", "credit_range", "employment"]
        remaining = [f for f in all_qualifying_fields if f not in questions_asked]
        if remaining and conversation.current_stage in ("greeting", "qualifying"):
            prompt_parts.append(f"Next qualification questions to ask (pick the next ONE): {remaining}")

        if call_summary:
            prompt_parts.append("")
            prompt_parts.append("CROSS-CHANNEL CONTEXT — the borrower has spoken with us before:")
            prompt_parts.append(call_summary)
            prompt_parts.append("Reference what was discussed if relevant, but don't repeat it verbatim.")

        nmls = persona.get("nmls_id") or persona.get("nmls")
        if nmls:
            prompt_parts.append(f"NMLS# {nmls}")

        return "\n".join(prompt_parts)

    def _build_conversation_messages(
        self,
        db: Session,
        conversation: SMSConversation,
        current_message: str,
    ) -> List[Dict[str, str]]:
        """Build the messages array for Claude from conversation history."""
        history = db.query(SMSConversationMessage).filter(
            SMSConversationMessage.conversation_id == conversation.id,
        ).order_by(SMSConversationMessage.created_at.desc()).limit(10).all()[::-1]

        messages = []
        for msg in history:
            role = "user" if msg.direction == "inbound" else "assistant"
            messages.append({"role": role, "content": msg.content})

        # Add the current inbound message (not yet committed, so not in history query)
        messages.append({"role": "user", "content": current_message})

        return messages

    async def _generate_ai_response(
        self,
        db: Session,
        conversation: SMSConversation,
        message: str,
        intent_result,
    ) -> Optional[str]:
        """Call Claude to generate a contextual SMS response.

        Returns the response text, or None if Claude is unavailable (caller falls back to templates).
        """
        client = self._get_anthropic_client()
        if client is None:
            return None

        try:
            # Load persona and cross-channel context
            persona = self._get_persona_config(db, conversation.organization_id)
            call_summary = self._get_prior_call_summary(db, conversation)

            system_prompt = self._build_system_prompt(conversation, persona, call_summary)
            conversation_messages = self._build_conversation_messages(db, conversation, message)

            # Ensure we have at least one message
            if not conversation_messages:
                conversation_messages = [{"role": "user", "content": message}]

            response = await asyncio.wait_for(
                client.messages.create(
                    model=_CLAUDE_MODEL,
                    max_tokens=_CLAUDE_MAX_TOKENS,
                    system=system_prompt,
                    messages=conversation_messages,
                ),
                timeout=15.0,
            )

            if response.content and len(response.content) > 0:
                ai_text = response.content[0].text.strip()
                # Safety: strip any accidental rate quotes (belt-and-suspenders)
                if ai_text:
                    return ai_text

            logger.warning("Claude returned empty response for conversation %s", conversation.id)
            return None

        except asyncio.TimeoutError:
            logger.warning("Claude SMS generation timed out after 15s for conversation %s", conversation.id)
            return None
        except Exception as e:
            logger.warning("Claude SMS generation failed (falling back to templates): %s", e)
            return None

    # -----------------------------------------------------------------------
    # Main response dispatcher — AI primary, templates fallback
    # -----------------------------------------------------------------------

    async def _generate_response(self, db: Session, conversation: SMSConversation,
                                  message: str, intent_result) -> str:
        """Generate contextual response. Tries Claude first, falls back to canned templates."""
        # Try Claude AI response first
        ai_response = await self._generate_ai_response(db, conversation, message, intent_result)
        if ai_response:
            # Track that we used AI in context_data for analytics
            ctx = conversation.context_data or {}
            ctx["_last_response_source"] = "claude"
            conversation.context_data = ctx
            return ai_response

        # ---------- Fallback: canned template logic ----------
        logger.info("Using template fallback for conversation %s", conversation.id)
        ctx = conversation.context_data or {}
        ctx["_last_response_source"] = "template"
        conversation.context_data = ctx

        return await self._generate_template_response(db, conversation, message, intent_result)

    async def _generate_template_response(self, db: Session, conversation: SMSConversation,
                                           message: str, intent_result) -> str:
        """Fallback canned template responses when Claude is unavailable."""
        stage = conversation.current_stage
        intent = intent_result.intent

        # Handle objections with empathy
        if intent == "objection":
            return self._get_objection_response(message)

        # Handle scheduling requests
        if intent == "scheduling":
            return "I'd love to set up a time for you to speak with your loan officer! What days and times work best for you this week?"

        # Handle positive/ready signals
        if intent == "positive":
            if stage == "greeting":
                return "Great to hear! A few quick questions to get you pointed in the right direction — are you looking to purchase a new home or refinance?"
            return "That's great! Let me connect you with your loan officer to take the next step. What's a good time for a quick call?"

        # Handle document-related
        if intent == "document":
            return "You can upload documents securely through your borrower portal. Need the link? I can send it right over."

        # Default qualifying flow — ask one question at a time
        return await self._qualifying_response(conversation, message, intent_result)

    async def _qualifying_response(self, conversation: SMSConversation,
                                    message: str, intent_result) -> str:
        """Progressive qualification — ask the next relevant question (template fallback)."""
        ctx = conversation.context_data or {}
        asked = ctx.get("_questions_asked", [])

        QUALIFYING_QUESTIONS = [
            ("loan_purpose", "Are you looking to purchase a home, refinance, or something else?"),
            ("timeline", "What's your timeline? Looking to move in the next 1-3 months, 3-6 months, or just exploring?"),
            ("price_range", "What price range or loan amount are you considering?"),
            ("credit_range", "Do you have a general sense of your credit score range? (Excellent 740+, Good 680-739, Fair 620-679, or Below 620)"),
            ("employment", "Are you currently employed, self-employed, or retired?"),
        ]

        for field, question in QUALIFYING_QUESTIONS:
            if field not in asked:
                ctx.setdefault("_questions_asked", []).append(field)
                conversation.context_data = ctx
                return question

        # All questions asked — suggest next step
        return "Thanks for sharing all that info! Based on what you've told me, I think a quick call with your loan officer would be really valuable. Want me to set that up?"

    def _get_objection_response(self, message: str) -> str:
        """Empathetic objection handling responses (template fallback)."""
        message_lower = message.lower()

        if any(w in message_lower for w in ["not interested", "no thanks"]):
            return "No problem at all! If your situation changes or you have questions down the road, we're here to help. Have a great day!"
        if any(w in message_lower for w in ["already working with", "have a lender"]):
            return "That's great you're already working with someone! If you ever want a second opinion or to compare options, don't hesitate to reach out."
        if any(w in message_lower for w in ["too expensive", "can't afford"]):
            return "I understand — affordability is important. There are actually programs with low or no down payment that might surprise you. Want me to send some info, no pressure?"
        if any(w in message_lower for w in ["bad timing", "not now", "later"]):
            return "Totally understand — timing is everything. Want me to check back in a few months when things settle down?"

        return "I appreciate you letting me know. We're here whenever you're ready — no pressure at all!"
