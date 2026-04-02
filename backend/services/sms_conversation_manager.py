"""SMS conversation threading — maintains multi-turn context for AI SMS conversations."""
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Dict, List

from sqlalchemy.orm import Session

from database.models.sms_conversation import SMSAIConversation as SMSConversation, SMSAIConversationMessage as SMSConversationMessage
from services.sms_intent_detector import SMSIntentDetector

logger = logging.getLogger(__name__)


class SMSConversationManager:
    """Tracks conversation state and context across SMS messages."""

    def __init__(self):
        self.intent_detector = SMSIntentDetector()

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

        # 5. Generate AI response
        response_text = await self._generate_response(
            db, conversation, message, intent_result
        )

        # 6. Store outbound message
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
            except Exception:
                pass

            conversation = SMSConversation(
                phone_number=phone,
                lead_id=lead_id,
                organization_id=org_id,
            )
            db.add(conversation)
            db.flush()

        return conversation

    async def _generate_response(self, db: Session, conversation: SMSConversation,
                                  message: str, intent_result) -> str:
        """Generate contextual AI response based on conversation stage and intent."""
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
        """Progressive qualification — ask the next relevant question."""
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
        """Empathetic objection handling responses."""
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
