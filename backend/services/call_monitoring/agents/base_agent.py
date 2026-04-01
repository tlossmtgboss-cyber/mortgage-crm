"""
Base Call Monitoring Agent

Abstract base class for all call monitoring AI agents.
Provides common functionality for LLM calls and artifact generation.
"""

import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from sqlalchemy.orm import Session
import anthropic

logger = logging.getLogger(__name__)

# Claude model configuration
AGENT_MODEL = os.getenv("CALL_MONITORING_MODEL", "claude-sonnet-4-20250514")
AGENT_MODEL_FAST = os.getenv("CALL_MONITORING_MODEL_FAST", "claude-haiku-4-5-20251001")
MAX_TOKENS = 4096

# Per-agent model recommendations: agents that do simpler extraction/formatting
# can use the fast model. Complex agents (scribe, underwriter) need Sonnet.
AGENT_MODEL_MAP: Dict[str, str] = {
    "scribe": AGENT_MODEL,          # Sonnet: nuanced summarization, action items
    "junior_lo": AGENT_MODEL,       # Sonnet: pricing scenarios, 5 C's analysis
    "underwriter": AGENT_MODEL,     # Sonnet: risk assessment, compliance review
    "calculator": AGENT_MODEL_FAST, # Haiku: structured data extraction for calcs
    "marketing": AGENT_MODEL_FAST,  # Haiku: story/quote capture, simpler extraction
    "scheduling": AGENT_MODEL_FAST, # Haiku: calendar coordination, simple routing
}


@dataclass
class AgentResult:
    """Result from agent processing."""
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    raw_output: Optional[str] = None
    model_used: str = AGENT_MODEL
    tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class BaseCallAgent(ABC):
    """
    Abstract base class for call monitoring AI agents.

    Provides:
    - Claude API integration with per-agent model selection
    - Common prompt building
    - Artifact extraction
    - Error handling

    Subclasses can override the model by setting `recommended_model` class
    attribute, or the model is auto-selected from AGENT_MODEL_MAP based on
    agent_type.
    """

    # Subclasses can set this to override the default model selection.
    # Values: "sonnet", "haiku", or a full model string.
    recommended_model: Optional[str] = None

    def __init__(self, db: Session):
        self.db = db
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = self._select_model()

    def _select_model(self) -> str:
        """Select the appropriate model for this agent.

        Priority:
        1. Class-level recommended_model override (set by subclass)
        2. AGENT_MODEL_MAP lookup by agent_type
        3. Default AGENT_MODEL (Sonnet)
        """
        # Check for subclass override
        if self.recommended_model:
            if self.recommended_model == "haiku":
                return AGENT_MODEL_FAST
            elif self.recommended_model == "sonnet":
                return AGENT_MODEL
            else:
                # Assume it's a full model string
                return self.recommended_model

        # Look up in the agent model map
        try:
            agent_type = self.agent_type
            if agent_type in AGENT_MODEL_MAP:
                return AGENT_MODEL_MAP[agent_type]
        except (AttributeError, NotImplementedError):
            pass

        # Default to Sonnet
        return AGENT_MODEL

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Return the agent type identifier."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass

    @abstractmethod
    def build_user_prompt(self, context: Dict[str, Any]) -> str:
        """Build the user prompt from context."""
        pass

    @abstractmethod
    def parse_response(self, response_text: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse the LLM response into artifacts."""
        pass

    async def process(self, context: Dict[str, Any]) -> AgentResult:
        """
        Process a call transcript and generate artifacts.

        Args:
            context: Dictionary containing:
                - transcript: Full call transcript
                - session_id: Call session ID
                - loan_id: Optional loan ID
                - lead_id: Optional lead ID
                - loan: Optional loan data dict
                - lead: Optional lead data dict
                - participants: List of participants
                - metadata: Additional metadata

        Returns:
            AgentResult with generated artifacts
        """
        try:
            # Build prompts
            user_prompt = self.build_user_prompt(context)

            logger.info(
                f"[{self.agent_type.upper()}] Processing call with model={self.model}"
            )

            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=self.system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Extract response text
            response_text = response.content[0].text if response.content else ""

            # Parse into artifacts
            artifacts = self.parse_response(response_text, context)

            # Build result
            result = AgentResult(
                artifacts=artifacts,
                raw_output=response_text,
                model_used=self.model,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            logger.info(
                f"{self.agent_type} agent processed call: "
                f"{len(artifacts)} artifacts, {result.tokens_used} tokens"
            )

            return result

        except Exception as e:
            logger.error(f"{self.agent_type} agent error: {e}")
            raise

    def _extract_json_from_response(self, response_text: str) -> Optional[Dict]:
        """Extract JSON from response text."""
        try:
            # Try to find JSON block
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_str = response_text[json_start:json_end].strip()
            elif "{" in response_text:
                # Find the outermost JSON object
                start = response_text.find("{")
                depth = 0
                end = start
                for i, char in enumerate(response_text[start:], start):
                    if char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                json_str = response_text[start:end]
            else:
                return None

            return json.loads(json_str)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from response: {e}")
            return None

    def _truncate_transcript(self, transcript: str, max_words: int = 10000) -> str:
        """Truncate transcript to fit within token limits."""
        words = transcript.split()
        if len(words) > max_words:
            # Keep first and last portions
            half = max_words // 2
            truncated = " ".join(words[:half]) + "\n\n[... middle portion truncated ...]\n\n" + " ".join(words[-half:])
            return truncated
        return transcript

    def _format_participants(self, participants: List[Dict]) -> str:
        """Format participants list for prompt."""
        if not participants:
            return "Unknown participants"

        lines = []
        for p in participants:
            role = p.get('role', 'unknown')
            name = p.get('name', 'Unknown')
            lines.append(f"- {name} ({role})")

        return "\n".join(lines)

    def _format_loan_context(self, loan: Optional[Dict]) -> str:
        """Format loan context for prompt."""
        if not loan:
            return "No loan information available"

        lines = [
            f"Loan Number: {loan.get('loan_number', 'N/A')}",
            f"Borrower: {loan.get('borrower_name', 'N/A')}",
            f"Loan Amount: ${loan.get('loan_amount', 0):,.2f}" if loan.get('loan_amount') else "Loan Amount: N/A",
            f"Loan Type: {loan.get('loan_type', 'N/A')}",
            f"Property: {loan.get('property_address', 'N/A')}",
            f"Status: {loan.get('status', 'N/A')}",
            f"Credit Score: {loan.get('credit_score', 'N/A')}",
        ]

        return "\n".join(lines)

    def _format_lead_context(self, lead: Optional[Dict]) -> str:
        """Format lead context for prompt."""
        if not lead:
            return "No lead information available"

        lines = [
            f"Name: {lead.get('name', 'N/A')}",
            f"Email: {lead.get('email', 'N/A')}",
            f"Phone: {lead.get('phone', 'N/A')}",
            f"Stage: {lead.get('stage', 'N/A')}",
            f"Source: {lead.get('source', 'N/A')}",
        ]

        return "\n".join(lines)
