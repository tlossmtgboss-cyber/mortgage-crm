"""
AI Memory Service with RAG (Retrieval-Augmented Generation)
Provides context-aware AI responses using conversation history
"""
import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import anthropic
import json

from integrations.pinecone_service import vector_memory
from main import ConversationMemory, Lead, Loan, User

logger = logging.getLogger(__name__)


class ContextAwareAI:
    """Enhanced AI service with memory and context retrieval"""

    def __init__(self):
        self.anthropic_api_key = anthropic.api_key
        if not self.anthropic_api_key:
            import os
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

        self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        self.vector_memory = vector_memory

    async def get_intelligent_response(
        self,
        db: Session,
        user_id: int,
        current_message: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        include_context: bool = True
    ) -> Dict:
        """
        Generate AI response with relevant context from past conversations

        Args:
            db: Database session
            user_id: ID of the user
            current_message: The current user message
            lead_id: Optional lead ID for context
            loan_id: Optional loan ID for context
            include_context: Whether to include past conversation context

        Returns:
            Dict with response, context_used, and metadata
        """
        try:
            # 1. Retrieve relevant past context if enabled
            relevant_history = []
            if include_context and self.vector_memory.enabled:
                filter_metadata = {}
                if lead_id:
                    filter_metadata["lead_id"] = lead_id

                relevant_history = await self.vector_memory.retrieve_relevant_context(
                    user_id=user_id,
                    current_query=current_message,
                    top_k=5,
                    filter_metadata=filter_metadata if filter_metadata else None
                )

                # Update access tracking in database
                for context in relevant_history:
                    pinecone_id = context.get("metadata", {}).get("pinecone_id")
                    if pinecone_id:
                        await self._update_memory_access(db, pinecone_id)

            # 2. Get lead/loan context if provided
            lead_context = ""
            if lead_id:
                lead_context = await self._get_lead_context(db, lead_id)

            loan_context = ""
            if loan_id:
                loan_context = await self._get_loan_context(db, loan_id)

            # 3. Build enhanced system prompt with context
            system_prompt = self._build_system_prompt(
                relevant_history,
                lead_context,
                loan_context
            )

            # 4. Generate response with Claude
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": current_message
                }]
            )

            ai_response = response.content[0].text

            # 5. Extract key information from conversation
            conversation_metadata = await self._extract_conversation_metadata(
                current_message,
                ai_response
            )

            # 6. Store this conversation for future context
            conversation_text = f"User: {current_message}\n\nAssistant: {ai_response}"

            if self.vector_memory.enabled:
                pinecone_id = await self.vector_memory.store_conversation(
                    user_id=user_id,
                    conversation_text=conversation_text,
                    metadata={
                        "lead_id": lead_id,
                        "loan_id": loan_id,
                        **conversation_metadata
                    }
                )

                # Store metadata in database
                memory_record = ConversationMemory(
                    user_id=user_id,
                    lead_id=lead_id,
                    loan_id=loan_id,
                    conversation_summary=conversation_text[:500],  # First 500 chars
                    key_points=conversation_metadata.get("key_points", {}),
                    sentiment=conversation_metadata.get("sentiment", "neutral"),
                    intent=conversation_metadata.get("intent", "unknown"),
                    pinecone_id=pinecone_id,
                    relevance_score=1.0  # New memories start with high relevance
                )
                db.add(memory_record)
                db.commit()

            return {
                "response": ai_response,
                "context_used": len(relevant_history) > 0,
                "context_count": len(relevant_history),
                "metadata": conversation_metadata,
                "has_memory": self.vector_memory.enabled
            }

        except Exception as e:
            logger.error(f"Error generating intelligent response: {e}")
            return {
                "response": "I apologize, but I'm having trouble generating a response right now. Please try again.",
                "context_used": False,
                "error": str(e)
            }

    def _build_system_prompt(
        self,
        relevant_history: List[Dict],
        lead_context: str,
        loan_context: str
    ) -> str:
        """Build enhanced system prompt with all available context"""

        base_prompt = """You are an intelligent AI assistant for a mortgage CRM system. Your role is to help mortgage loan officers manage their business efficiently.

You have access to conversation history and context. Use this information to provide personalized, relevant responses that reference past interactions when appropriate."""

        context_sections = []

        # Add conversation history if available
        if relevant_history:
            context_sections.append("\n## PAST CONVERSATION CONTEXT:")
            context_sections.append("Here are relevant past interactions with this user:\n")

            for idx, conv in enumerate(relevant_history, 1):
                timestamp = conv.get("timestamp", "Unknown time")
                text = conv.get("text", "")
                score = conv.get("relevance_score", 0)

                context_sections.append(f"[{idx}] {timestamp} (Relevance: {score:.2f})")
                context_sections.append(f"{text}\n")

            context_sections.append("\nUse these past conversations to provide context-aware responses.")

        # Add lead context if available
        if lead_context:
            context_sections.append("\n## CURRENT LEAD INFORMATION:")
            context_sections.append(lead_context)

        # Add loan context if available
        if loan_context:
            context_sections.append("\n## CURRENT LOAN INFORMATION:")
            context_sections.append(loan_context)

        # Add guidelines
        context_sections.append("""

## RESPONSE GUIDELINES:
1. Reference past conversations naturally when relevant
2. Be concise but informative
3. If you don't have information, say so clearly
4. Maintain professional mortgage industry tone
5. Highlight important details and action items
6. Use context to avoid asking questions you should know the answer to
""")

        return base_prompt + "\n".join(context_sections)

    async def _get_lead_context(self, db: Session, lead_id: int) -> str:
        """Get formatted context about a lead"""
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if not lead:
                return ""

            context = f"""Lead: {lead.name}
Phone: {lead.phone or 'N/A'}
Email: {lead.email or 'N/A'}
Stage: {lead.stage}
Source: {lead.source or 'N/A'}
Credit Score: {lead.credit_score or 'N/A'}
Loan Amount Estimate: ${lead.loan_amount_estimate or 0:,.0f}
Property Value: ${lead.property_value or 0:,.0f}
Notes: {lead.notes or 'None'}"""

            return context
        except Exception as e:
            logger.error(f"Error getting lead context: {e}")
            return ""

    async def _get_loan_context(self, db: Session, loan_id: int) -> str:
        """Get formatted context about a loan"""
        try:
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return ""

            context = f"""Loan Amount: ${loan.amount or 0:,.0f}
Loan Type: {loan.loan_type or 'N/A'}
Stage: {loan.stage}
Interest Rate: {loan.interest_rate or 'N/A'}%
Property Address: {loan.property_address or 'N/A'}
Status: {loan.status or 'In Progress'}"""

            return context
        except Exception as e:
            logger.error(f"Error getting loan context: {e}")
            return ""

    async def _extract_conversation_metadata(
        self,
        user_message: str,
        ai_response: str
    ) -> Dict:
        """Extract key metadata from conversation using Claude"""
        try:
            # Use Claude to analyze the conversation
            analysis_prompt = f"""Analyze this conversation and extract structured information:

User: {user_message}
Assistant: {ai_response}

Extract and return ONLY a JSON object with:
{{
    "sentiment": "positive|neutral|negative",
    "intent": "brief description of user's intent",
    "key_points": {{
        "entities": ["list", "of", "mentioned", "people/companies"],
        "topics": ["list", "of", "discussed", "topics"],
        "action_items": ["list", "of", "action", "items"],
        "loan_details": {{}},
        "property_details": {{}}
    }}
}}

Return ONLY valid JSON, no other text."""

            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": analysis_prompt
                }]
            )

            # Parse JSON response
            analysis = json.loads(response.content[0].text)
            return analysis

        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return {
                "sentiment": "neutral",
                "intent": "general_inquiry",
                "key_points": {}
            }

    async def _update_memory_access(self, db: Session, pinecone_id: str):
        """Update access tracking for a memory"""
        try:
            memory = db.query(ConversationMemory).filter(
                ConversationMemory.pinecone_id == pinecone_id
            ).first()

            if memory:
                memory.access_count += 1
                memory.last_accessed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.error(f"Error updating memory access: {e}")


# Global instance
context_ai = ContextAwareAI()
