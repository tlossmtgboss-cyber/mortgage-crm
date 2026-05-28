"""
Conversation Intelligence - Analysis Service

AI-powered post-call analysis using Claude for:
- Call summarization
- Sentiment and intent detection
- Action item extraction
- Compliance checking
- Coaching opportunity identification
- Mortgage-specific data extraction
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

import anthropic

from services.ci_transcription_service import TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

ANALYSIS_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096


@dataclass
class CallAnalysisConfig:
    """Configuration for call analysis."""
    extract_action_items: bool = True
    extract_loan_details: bool = True
    check_compliance: bool = True
    identify_coaching: bool = True
    include_sentiment_per_segment: bool = False


@dataclass
class ActionItem:
    """An action item extracted from the call."""
    description: str
    assignee: str  # agent, customer, other
    priority: str  # high, medium, low
    due_date: Optional[str] = None
    context: Optional[str] = None


@dataclass
class ComplianceFlag:
    """A compliance concern detected in the call."""
    rule_type: str
    severity: str  # critical, high, medium, low
    description: str
    evidence: str
    timestamp_range: Optional[str] = None


@dataclass
class CoachingOpportunity:
    """A coaching/training opportunity identified."""
    category: str  # greeting, discovery, objection_handling, closing, etc.
    observation: str
    recommendation: str
    example_from_call: Optional[str] = None
    priority: str = "medium"


@dataclass
class LoanDetailsExtracted:
    """Mortgage-specific details extracted from the call."""
    loan_purpose: Optional[str] = None  # purchase, refinance, cash-out
    property_type: Optional[str] = None
    property_value: Optional[float] = None
    loan_amount: Optional[float] = None
    down_payment: Optional[float] = None
    credit_score_mentioned: Optional[str] = None
    income_mentioned: Optional[str] = None
    employment_status: Optional[str] = None
    rate_discussed: Optional[str] = None
    timeline: Optional[str] = None
    pre_approved: Optional[bool] = None
    first_time_buyer: Optional[bool] = None


@dataclass
class CallAnalysisResult:
    """Complete analysis result for a call."""
    # Summary
    summary: str = ""
    summary_bullets: List[str] = field(default_factory=list)

    # Call classification
    call_disposition: str = ""  # completed, voicemail, callback_scheduled, etc.
    call_purpose: str = ""  # rate_inquiry, application_followup, document_request
    call_outcome: str = ""  # successful, needs_followup, escalation_required

    # Topics and content
    topics_discussed: List[Dict[str, Any]] = field(default_factory=list)
    action_items: List[ActionItem] = field(default_factory=list)
    follow_ups_needed: List[str] = field(default_factory=list)

    # Customer insights
    customer_sentiment: str = "neutral"  # positive, neutral, negative, mixed
    customer_intent: str = ""  # ready_to_proceed, exploring_options, concerned
    objections_raised: List[Dict[str, str]] = field(default_factory=list)
    questions_asked: List[str] = field(default_factory=list)

    # Agent performance
    agent_performance: Dict[str, Any] = field(default_factory=dict)
    coaching_opportunities: List[CoachingOpportunity] = field(default_factory=list)

    # Compliance
    compliance_flags: List[ComplianceFlag] = field(default_factory=list)
    required_disclosures_given: List[str] = field(default_factory=list)

    # Mortgage-specific
    loan_details: Optional[LoanDetailsExtracted] = None
    property_details: Dict[str, Any] = field(default_factory=dict)
    borrower_info_collected: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    analysis_model: str = ANALYSIS_MODEL
    tokens_used: int = 0
    processing_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        # Convert nested dataclasses
        result["action_items"] = [asdict(a) for a in self.action_items]
        result["coaching_opportunities"] = [asdict(c) for c in self.coaching_opportunities]
        result["compliance_flags"] = [asdict(f) for f in self.compliance_flags]
        if self.loan_details:
            result["loan_details"] = asdict(self.loan_details)
        return result


# =============================================================================
# ANALYSIS SERVICE
# =============================================================================

class CallAnalysisService:
    """
    Service for analyzing call transcriptions using Claude.

    Usage:
        service = CallAnalysisService()
        result = await service.analyze_call(transcription_result)
    """

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None

    async def analyze_call(
        self,
        transcription: TranscriptionResult,
        config: Optional[CallAnalysisConfig] = None,
        call_metadata: Optional[Dict[str, Any]] = None
    ) -> CallAnalysisResult:
        """
        Analyze a transcribed call.

        Args:
            transcription: The transcription result
            config: Analysis configuration
            call_metadata: Additional context (call type, agent info, etc.)

        Returns:
            CallAnalysisResult
        """
        if not self.client:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        config = config or CallAnalysisConfig()
        call_metadata = call_metadata or {}

        start_time = datetime.now()

        # Format transcript for analysis
        formatted_transcript = self._format_transcript(transcription)

        # Build the analysis prompt
        prompt = self._build_analysis_prompt(formatted_transcript, config, call_metadata)

        # Call Claude
        try:
            from agents.anthropic_client import cached_system_block
            response = self.client.messages.create(
                model=ANALYSIS_MODEL,
                max_tokens=MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                system=cached_system_block(self._get_system_prompt())
            )

            # Parse the response
            analysis_text = response.content[0].text
            result = self._parse_analysis_response(analysis_text, config)

            # Add metadata
            result.analysis_model = ANALYSIS_MODEL
            result.tokens_used = response.usage.input_tokens + response.usage.output_tokens
            result.processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            return result

        except Exception as e:
            logger.error(f"Call analysis failed: {e}")
            raise

    def _get_system_prompt(self) -> str:
        """Get the system prompt for call analysis."""
        return """You are an expert mortgage call analyzer. Your job is to analyze transcripts of phone calls between mortgage loan officers and customers.

You should:
1. Provide concise, actionable summaries
2. Identify the call purpose and outcome
3. Extract specific mortgage-related details discussed
4. Detect compliance issues or required disclosures
5. Identify coaching opportunities for the agent
6. Note customer sentiment and objections

Always respond in valid JSON format as specified in the prompt.

Key mortgage compliance items to check:
- NMLS ID disclosure when requested
- No guaranteed rate claims without lock
- Equal housing / fair lending compliance
- Privacy handling of sensitive data (SSN, account numbers)
- State-specific disclosures (CA DBO, TX home equity rules, etc.)

Key coaching areas to assess:
- Greeting and introduction
- Discovery and needs assessment
- Product presentation clarity
- Objection handling
- Closing and next steps
- Active listening and empathy"""

    def _format_transcript(self, transcription: TranscriptionResult) -> str:
        """Format transcript for analysis."""
        lines = []
        for seg in transcription.segments:
            timestamp = f"[{seg.start_time_ms // 1000}s]"
            speaker = seg.speaker.upper()
            lines.append(f"{timestamp} {speaker}: {seg.text}")
        return "\n".join(lines)

    def _build_analysis_prompt(
        self,
        transcript: str,
        config: CallAnalysisConfig,
        metadata: Dict[str, Any]
    ) -> str:
        """Build the analysis prompt."""
        call_type = metadata.get("call_type", "inbound")
        agent_name = metadata.get("agent_name", "Agent")

        prompt = f"""Analyze this mortgage call transcript and provide a comprehensive analysis.

CALL METADATA:
- Call Type: {call_type}
- Agent: {agent_name}

TRANSCRIPT:
{transcript}

Provide your analysis in the following JSON format:
{{
    "summary": "2-3 sentence summary of the call",
    "summary_bullets": ["Key point 1", "Key point 2", "Key point 3"],

    "call_disposition": "completed | voicemail | callback_scheduled | transferred | dropped",
    "call_purpose": "rate_inquiry | application_followup | document_request | status_check | new_lead | general_question",
    "call_outcome": "successful | needs_followup | escalation_required | no_action_needed",

    "topics_discussed": [
        {{"topic": "topic name", "confidence": 0.9}}
    ],

    "customer_sentiment": "positive | neutral | negative | mixed",
    "customer_intent": "ready_to_proceed | exploring_options | concerned | not_interested | undecided",

    "objections_raised": [
        {{"objection": "description", "handled": true/false, "handling_quality": "good | fair | poor"}}
    ],

    "questions_asked": ["Question 1 from customer", "Question 2"],
"""

        if config.extract_action_items:
            prompt += """
    "action_items": [
        {{"description": "action description", "assignee": "agent | customer", "priority": "high | medium | low"}}
    ],

    "follow_ups_needed": ["Follow up item 1", "Follow up item 2"],
"""

        if config.check_compliance:
            prompt += """
    "compliance_flags": [
        {{"rule_type": "nmls_disclosure | rate_guarantee | fair_lending | privacy", "severity": "critical | high | medium | low", "description": "what happened", "evidence": "quote from transcript"}}
    ],

    "required_disclosures_given": ["NMLS ID", "Equal Housing", "etc."],
"""

        if config.identify_coaching:
            prompt += """
    "coaching_opportunities": [
        {{"category": "greeting | discovery | presentation | objection_handling | closing | empathy", "observation": "what was observed", "recommendation": "how to improve", "priority": "high | medium | low"}}
    ],

    "agent_performance": {{
        "greeting_score": 1-10,
        "discovery_score": 1-10,
        "presentation_score": 1-10,
        "objection_handling_score": 1-10,
        "closing_score": 1-10,
        "empathy_score": 1-10,
        "overall_notes": "brief assessment"
    }},
"""

        if config.extract_loan_details:
            prompt += """
    "loan_details": {{
        "loan_purpose": "purchase | refinance | cash_out | null",
        "property_type": "single_family | condo | townhouse | multi_family | null",
        "property_value": null or number,
        "loan_amount": null or number,
        "down_payment": null or number,
        "credit_score_mentioned": "score or range if mentioned",
        "income_mentioned": "income if mentioned",
        "employment_status": "employed | self_employed | retired | etc",
        "rate_discussed": "rate if mentioned",
        "timeline": "closing timeline if mentioned",
        "pre_approved": true/false/null,
        "first_time_buyer": true/false/null
    }},

    "borrower_info_collected": {{
        "name": "if collected",
        "email": "if collected",
        "phone": "if collected",
        "address": "if collected"
    }},
"""

        prompt += """
}}

Important:
- Only include fields where information was actually discussed
- Use null for fields where no information was provided
- Be specific with evidence and quotes
- Focus on actionable insights"""

        return prompt

    def _parse_analysis_response(
        self,
        response_text: str,
        config: CallAnalysisConfig
    ) -> CallAnalysisResult:
        """Parse Claude's response into CallAnalysisResult."""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_text = response_text
            if "```json" in response_text:
                json_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_text = response_text.split("```")[1].split("```")[0]

            data = json.loads(json_text)

            result = CallAnalysisResult(
                summary=data.get("summary", ""),
                summary_bullets=data.get("summary_bullets", []),
                call_disposition=data.get("call_disposition", ""),
                call_purpose=data.get("call_purpose", ""),
                call_outcome=data.get("call_outcome", ""),
                topics_discussed=data.get("topics_discussed", []),
                customer_sentiment=data.get("customer_sentiment", "neutral"),
                customer_intent=data.get("customer_intent", ""),
                objections_raised=data.get("objections_raised", []),
                questions_asked=data.get("questions_asked", []),
                follow_ups_needed=data.get("follow_ups_needed", []),
                required_disclosures_given=data.get("required_disclosures_given", []),
                agent_performance=data.get("agent_performance", {}),
                property_details=data.get("property_details", {}),
                borrower_info_collected=data.get("borrower_info_collected", {}),
            )

            # Parse action items
            for item in data.get("action_items", []):
                result.action_items.append(ActionItem(
                    description=item.get("description", ""),
                    assignee=item.get("assignee", "agent"),
                    priority=item.get("priority", "medium"),
                    due_date=item.get("due_date"),
                    context=item.get("context")
                ))

            # Parse compliance flags
            for flag in data.get("compliance_flags", []):
                result.compliance_flags.append(ComplianceFlag(
                    rule_type=flag.get("rule_type", ""),
                    severity=flag.get("severity", "medium"),
                    description=flag.get("description", ""),
                    evidence=flag.get("evidence", ""),
                    timestamp_range=flag.get("timestamp_range")
                ))

            # Parse coaching opportunities
            for opp in data.get("coaching_opportunities", []):
                result.coaching_opportunities.append(CoachingOpportunity(
                    category=opp.get("category", ""),
                    observation=opp.get("observation", ""),
                    recommendation=opp.get("recommendation", ""),
                    example_from_call=opp.get("example_from_call"),
                    priority=opp.get("priority", "medium")
                ))

            # Parse loan details
            loan_data = data.get("loan_details", {})
            if loan_data:
                result.loan_details = LoanDetailsExtracted(
                    loan_purpose=loan_data.get("loan_purpose"),
                    property_type=loan_data.get("property_type"),
                    property_value=loan_data.get("property_value"),
                    loan_amount=loan_data.get("loan_amount"),
                    down_payment=loan_data.get("down_payment"),
                    credit_score_mentioned=loan_data.get("credit_score_mentioned"),
                    income_mentioned=loan_data.get("income_mentioned"),
                    employment_status=loan_data.get("employment_status"),
                    rate_discussed=loan_data.get("rate_discussed"),
                    timeline=loan_data.get("timeline"),
                    pre_approved=loan_data.get("pre_approved"),
                    first_time_buyer=loan_data.get("first_time_buyer")
                )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse analysis response as JSON: {e}")
            # Return partial result with just the summary
            return CallAnalysisResult(
                summary=response_text[:500] if response_text else "Analysis parsing failed"
            )

    async def generate_call_summary(
        self,
        transcription: TranscriptionResult,
        max_bullets: int = 5
    ) -> Dict[str, Any]:
        """Generate a quick summary of a call without full analysis."""
        if not self.client:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        formatted_transcript = self._format_transcript(transcription)

        prompt = f"""Summarize this mortgage call in {max_bullets} bullet points. Focus on:
- What the customer wanted
- Key information discussed
- Outcome/next steps

TRANSCRIPT:
{formatted_transcript}

Respond with JSON: {{"bullets": ["point 1", "point 2", ...], "one_liner": "one sentence summary"}}"""

        response = self.client.messages.create(
            model=ANALYSIS_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            text = response.content[0].text
            if "```" in text:
                text = text.split("```")[1].split("```")[0]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.exception(f"Failed to parse call summary response as JSON: {e}")
            return {"bullets": [], "one_liner": response.content[0].text[:200]}


# =============================================================================
# SPECIALIZED ANALYZERS
# =============================================================================

class ComplianceAnalyzer:
    """Specialized analyzer for compliance checking."""

    COMPLIANCE_RULES = {
        "nmls_disclosure": {
            "description": "NMLS ID must be provided when requested",
            "triggers": ["nmls", "license", "id number", "credentials"],
            "severity": "high"
        },
        "rate_guarantee": {
            "description": "Cannot guarantee rates without a lock",
            "prohibited": ["guarantee", "promise", "locked in", "won't change"],
            "severity": "high"
        },
        "fair_lending": {
            "description": "No discrimination based on protected classes",
            "prohibited": ["people like you", "your neighborhood", "your type"],
            "severity": "critical"
        },
        "privacy": {
            "description": "Handle sensitive data appropriately",
            "sensitive": ["ssn", "social security", "account number"],
            "severity": "medium"
        }
    }

    def check_compliance(
        self,
        transcription: TranscriptionResult,
        state: Optional[str] = None
    ) -> List[ComplianceFlag]:
        """Run rule-based compliance checks on transcription."""
        flags = []

        full_text = transcription.full_text.lower()

        # Check each rule
        for rule_id, rule in self.COMPLIANCE_RULES.items():
            # Check prohibited phrases
            for phrase in rule.get("prohibited", []):
                if phrase.lower() in full_text:
                    flags.append(ComplianceFlag(
                        rule_type=rule_id,
                        severity=rule["severity"],
                        description=rule["description"],
                        evidence=f"Found prohibited phrase: '{phrase}'"
                    ))

        return flags


class SentimentAnalyzer:
    """Analyze sentiment throughout a call."""

    POSITIVE_WORDS = ["great", "thank", "perfect", "excellent", "wonderful", "appreciate", "helpful"]
    NEGATIVE_WORDS = ["frustrated", "angry", "disappointed", "terrible", "awful", "upset", "confused"]

    def analyze_sentiment_trajectory(
        self,
        segments: List[TranscriptionSegment]
    ) -> Dict[str, Any]:
        """Analyze how sentiment changes throughout the call."""
        customer_sentiments = []

        for seg in segments:
            if seg.speaker == "customer":
                text_lower = seg.text.lower()
                pos_count = sum(1 for w in self.POSITIVE_WORDS if w in text_lower)
                neg_count = sum(1 for w in self.NEGATIVE_WORDS if w in text_lower)

                if pos_count > neg_count:
                    sentiment = "positive"
                elif neg_count > pos_count:
                    sentiment = "negative"
                else:
                    sentiment = "neutral"

                customer_sentiments.append({
                    "timestamp_ms": seg.start_time_ms,
                    "sentiment": sentiment,
                    "text_preview": seg.text[:50]
                })

        # Determine trajectory
        if len(customer_sentiments) >= 2:
            first_half = customer_sentiments[:len(customer_sentiments)//2]
            second_half = customer_sentiments[len(customer_sentiments)//2:]

            first_neg = sum(1 for s in first_half if s["sentiment"] == "negative")
            second_neg = sum(1 for s in second_half if s["sentiment"] == "negative")

            if second_neg < first_neg:
                trajectory = "improving"
            elif second_neg > first_neg:
                trajectory = "declining"
            else:
                trajectory = "stable"
        else:
            trajectory = "insufficient_data"

        return {
            "trajectory": trajectory,
            "sentiment_timeline": customer_sentiments,
            "overall": self._calculate_overall_sentiment(customer_sentiments)
        }

    def _calculate_overall_sentiment(self, sentiments: List[Dict]) -> str:
        if not sentiments:
            return "neutral"

        pos = sum(1 for s in sentiments if s["sentiment"] == "positive")
        neg = sum(1 for s in sentiments if s["sentiment"] == "negative")

        if pos > neg * 2:
            return "positive"
        elif neg > pos * 2:
            return "negative"
        elif pos > 0 and neg > 0:
            return "mixed"
        return "neutral"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_analysis_service() -> CallAnalysisService:
    """Get singleton analysis service."""
    return CallAnalysisService()


def get_compliance_analyzer() -> ComplianceAnalyzer:
    """Get compliance analyzer."""
    return ComplianceAnalyzer()


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """Get sentiment analyzer."""
    return SentimentAnalyzer()
