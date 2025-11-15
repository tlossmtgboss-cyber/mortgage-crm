"""
Enhanced AI Memory Service with A/B Testing Integration
Shows how to integrate experiments with AI responses
"""
import logging
from typing import Optional, Dict
from datetime import datetime, timezone
from sqlalchemy.orm import Session
import anthropic
import json

from integrations.pinecone_service import vector_memory
from main import ConversationMemory, Lead, Loan, User
from ab_testing.experiment_service import ExperimentService

logger = logging.getLogger(__name__)


class ContextAwareAIWithExperiments:
    """Enhanced AI service with A/B testing support"""

    def __init__(self):
        self.anthropic_api_key = anthropic.api_key
        if not self.anthropic_api_key:
            import os
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

        self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        self.vector_memory = vector_memory

    async def get_intelligent_response_with_ab_test(
        self,
        db: Session,
        user_id: int,
        current_message: str,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        include_context: bool = True,
        session_id: Optional[str] = None
    ) -> Dict:
        """
        Generate AI response with A/B testing for prompt variations

        This method:
        1. Checks if user is in an active prompt experiment
        2. Uses the assigned variant's prompt configuration
        3. Records experiment results (resolution rate, satisfaction, etc.)
        4. Falls back to default behavior if no experiment is running
        """
        try:
            # Check if there's an active prompt experiment
            experiment_service = ExperimentService(db)
            variant = experiment_service.get_variant_for_user(
                experiment_name="lead_qualification_prompt",  # Example experiment name
                user_id=user_id,
                session_id=session_id
            )

            # Get context as usual
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

            lead_context = ""
            if lead_id:
                lead_context = await self._get_lead_context(db, lead_id)

            loan_context = ""
            if loan_id:
                loan_context = await self._get_loan_context(db, loan_id)

            # Build system prompt - use variant if in experiment
            if variant:
                # Use experimental prompt configuration
                system_prompt = self._build_experimental_prompt(
                    variant=variant,
                    relevant_history=relevant_history,
                    lead_context=lead_context,
                    loan_context=loan_context
                )
                logger.info(
                    f"Using experimental prompt variant '{variant['variant_name']}' "
                    f"for user {user_id}"
                )
            else:
                # Use default prompt
                system_prompt = self._build_system_prompt(
                    relevant_history,
                    lead_context,
                    loan_context
                )

            # Generate response with Claude
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

            # Extract metadata
            conversation_metadata = await self._extract_conversation_metadata(
                current_message,
                ai_response
            )

            # If in experiment, record results
            if variant:
                await self._record_experiment_results(
                    db=db,
                    experiment_service=experiment_service,
                    experiment_name="lead_qualification_prompt",
                    user_id=user_id,
                    session_id=session_id,
                    metadata=conversation_metadata,
                    response_quality=self._assess_response_quality(ai_response)
                )

            # Store conversation
            conversation_text = f"User: {current_message}\n\nAssistant: {ai_response}"

            if self.vector_memory.enabled:
                pinecone_id = await self.vector_memory.store_conversation(
                    user_id=user_id,
                    conversation_text=conversation_text,
                    metadata={
                        "lead_id": lead_id,
                        "loan_id": loan_id,
                        "experiment_variant": variant["variant_name"] if variant else "none",
                        **conversation_metadata
                    }
                )

                memory_record = ConversationMemory(
                    user_id=user_id,
                    lead_id=lead_id,
                    loan_id=loan_id,
                    conversation_summary=conversation_text[:500],
                    key_points=conversation_metadata.get("key_points", {}),
                    sentiment=conversation_metadata.get("sentiment", "neutral"),
                    intent=conversation_metadata.get("intent", "unknown"),
                    pinecone_id=pinecone_id,
                    relevance_score=1.0
                )
                db.add(memory_record)
                db.commit()

            return {
                "response": ai_response,
                "context_used": len(relevant_history) > 0,
                "context_count": len(relevant_history),
                "metadata": conversation_metadata,
                "has_memory": self.vector_memory.enabled,
                "experiment_variant": variant["variant_name"] if variant else None,
                "in_experiment": variant is not None
            }

        except Exception as e:
            logger.error(f"Error generating intelligent response: {e}")
            return {
                "response": "I apologize, but I'm having trouble generating a response right now.",
                "context_used": False,
                "error": str(e)
            }

    def _build_experimental_prompt(
        self,
        variant: Dict,
        relevant_history,
        lead_context: str,
        loan_context: str
    ) -> str:
        """
        Build system prompt using experimental variant configuration

        Variant config examples:
        - {"system_prompt": "Custom prompt...", "include_examples": true}
        - {"temperature": 0.7, "system_prompt_template": "..."}
        """
        config = variant.get("config", {})

        # Get base prompt from variant config
        base_prompt = config.get(
            "system_prompt",
            "You are an intelligent AI assistant for a mortgage CRM system."
        )

        # Check if variant includes few-shot examples
        if config.get("include_examples", False):
            examples = config.get("examples", [])
            if examples:
                base_prompt += "\n\n## EXAMPLES:\n"
                for idx, example in enumerate(examples, 1):
                    base_prompt += f"\n{idx}. {example}\n"

        # Add context sections (same as default)
        context_sections = []

        if relevant_history:
            context_sections.append("\n## PAST CONVERSATION CONTEXT:")
            for idx, conv in enumerate(relevant_history, 1):
                timestamp = conv.get("timestamp", "Unknown")
                text = conv.get("text", "")
                context_sections.append(f"[{idx}] {timestamp}")
                context_sections.append(f"{text}\n")

        if lead_context:
            context_sections.append("\n## CURRENT LEAD INFORMATION:")
            context_sections.append(lead_context)

        if loan_context:
            context_sections.append("\n## CURRENT LOAN INFORMATION:")
            context_sections.append(loan_context)

        # Add response guidelines from variant config or use default
        guidelines = config.get("response_guidelines", """
## RESPONSE GUIDELINES:
1. Reference past conversations naturally when relevant
2. Be concise but informative
3. Maintain professional mortgage industry tone
4. Highlight important details and action items
""")
        context_sections.append(guidelines)

        return base_prompt + "\n".join(context_sections)

    def _build_system_prompt(self, relevant_history, lead_context, loan_context) -> str:
        """Default system prompt (when not in experiment)"""
        base_prompt = """You are an intelligent AI assistant for a mortgage CRM system. Your role is to help mortgage loan officers manage their business efficiently.

You have access to conversation history and context. Use this information to provide personalized, relevant responses."""

        context_sections = []

        if relevant_history:
            context_sections.append("\n## PAST CONVERSATION CONTEXT:")
            for idx, conv in enumerate(relevant_history, 1):
                timestamp = conv.get("timestamp", "Unknown")
                text = conv.get("text", "")
                context_sections.append(f"[{idx}] {timestamp}")
                context_sections.append(f"{text}\n")

        if lead_context:
            context_sections.append("\n## CURRENT LEAD INFORMATION:")
            context_sections.append(lead_context)

        if loan_context:
            context_sections.append("\n## CURRENT LOAN INFORMATION:")
            context_sections.append(loan_context)

        context_sections.append("""
## RESPONSE GUIDELINES:
1. Reference past conversations naturally when relevant
2. Be concise but informative
3. Maintain professional mortgage industry tone
4. Highlight important details and action items
""")

        return base_prompt + "\n".join(context_sections)

    async def _record_experiment_results(
        self,
        db: Session,
        experiment_service: ExperimentService,
        experiment_name: str,
        user_id: Optional[int],
        session_id: Optional[str],
        metadata: Dict,
        response_quality: float
    ):
        """Record experiment metrics"""
        try:
            # Record multiple metrics for the experiment

            # 1. Response quality (0-1 scale)
            experiment_service.record_result(
                experiment_name=experiment_name,
                metric_name="response_quality",
                metric_value=response_quality,
                user_id=user_id,
                session_id=session_id
            )

            # 2. Sentiment as numeric (positive=1, neutral=0.5, negative=0)
            sentiment = metadata.get("sentiment", "neutral")
            sentiment_score = {
                "positive": 1.0,
                "neutral": 0.5,
                "negative": 0.0
            }.get(sentiment, 0.5)

            experiment_service.record_result(
                experiment_name=experiment_name,
                metric_name="sentiment_score",
                metric_value=sentiment_score,
                user_id=user_id,
                session_id=session_id
            )

            # 3. Resolution rate (1 if intent understood, 0 otherwise)
            intent = metadata.get("intent", "unknown")
            resolution_rate = 1.0 if intent != "unknown" else 0.0

            experiment_service.record_result(
                experiment_name=experiment_name,
                metric_name="resolution_rate",
                metric_value=resolution_rate,
                user_id=user_id,
                session_id=session_id
            )

        except Exception as e:
            logger.error(f"Error recording experiment results: {e}")

    def _assess_response_quality(self, response: str) -> float:
        """
        Simple heuristic to assess response quality
        In production, use more sophisticated metrics or user feedback
        """
        # Basic quality indicators
        length = len(response)
        has_actionable_items = any(
            word in response.lower()
            for word in ["should", "recommend", "suggest", "next step"]
        )

        # Score 0-1
        quality = 0.5  # Base score

        if 50 <= length <= 500:  # Good length
            quality += 0.2

        if has_actionable_items:
            quality += 0.15

        if response.count(".") >= 2:  # Multiple sentences
            quality += 0.15

        return min(quality, 1.0)

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
Source: {lead.source or 'N/A'}"""
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
Stage: {loan.stage}"""
            return context
        except Exception as e:
            logger.error(f"Error getting loan context: {e}")
            return ""

    async def _extract_conversation_metadata(self, user_message: str, ai_response: str) -> Dict:
        """Extract key metadata from conversation"""
        try:
            analysis_prompt = f"""Analyze this conversation and extract structured information:

User: {user_message}
Assistant: {ai_response}

Extract and return ONLY a JSON object with:
{{
    "sentiment": "positive|neutral|negative",
    "intent": "brief description of user's intent",
    "key_points": {{}}
}}

Return ONLY valid JSON."""

            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[{"role": "user", "content": analysis_prompt}]
            )

            analysis = json.loads(response.content[0].text)
            return analysis

        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return {
                "sentiment": "neutral",
                "intent": "general_inquiry",
                "key_points": {}
            }


# Global instance
context_ai_with_experiments = ContextAwareAIWithExperiments()
