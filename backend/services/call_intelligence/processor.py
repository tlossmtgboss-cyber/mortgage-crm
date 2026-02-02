"""
Call Intelligence Processor

Main processor that coordinates extraction agents and produces
structured data for the Application Engine.
"""

import logging
import time
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from .llm_client import BaseLLMClient

from .data_contracts import (
    CallIntelligenceRequest,
    CallIntelligenceResponse,
    ExtractionResult,
    ExtractedValue,
    TranscriptSegment,
    SpeakerRole,
)
from .process_transcript import parse_transcript as parse_transcript_improved
from .pii_utils import mask_pii_for_logging
from .agents import (
    IdentityExtractionAgent,
    PropertyExtractionAgent,
    EmploymentExtractionAgent,
    FinancialExtractionAgent,
    ComplianceExtractionAgent,
    IntentExtractionAgent,
)

logger = logging.getLogger(__name__)


class CallIntelligenceProcessor:
    """
    Main processor for call transcript intelligence extraction.

    Coordinates multiple specialized AI agents to extract structured
    data from call transcripts.
    """

    VERSION = "1.0"

    def __init__(
        self,
        db_session: Optional["Session"] = None,
        llm_client: Optional["BaseLLMClient"] = None,
    ):
        """
        Initialize processor with agents.

        Args:
            db_session: SQLAlchemy session for database operations
            llm_client: LLM client for AI extractions (OpenAI, Anthropic, etc.)
        """
        self.db = db_session
        self.llm_client = llm_client

        # Initialize extraction agents
        self.identity_agent = IdentityExtractionAgent(llm_client)
        self.property_agent = PropertyExtractionAgent(llm_client)
        self.employment_agent = EmploymentExtractionAgent(llm_client)
        self.financial_agent = FinancialExtractionAgent(llm_client)
        self.compliance_agent = ComplianceExtractionAgent(llm_client)
        self.intent_agent = IntentExtractionAgent(llm_client)

        self._agents = {
            "identity": self.identity_agent,
            "property": self.property_agent,
            "employment": self.employment_agent,
            "financial": self.financial_agent,
            "compliance": self.compliance_agent,
            "intent": self.intent_agent,
        }

    async def process_transcript(
        self,
        request: CallIntelligenceRequest,
    ) -> CallIntelligenceResponse:
        """
        Process a call transcript through all extraction agents.

        Args:
            request: CallIntelligenceRequest with transcript and options

        Returns:
            CallIntelligenceResponse with all extractions
        """
        start_time = time.time()
        logger.info(f"Processing call transcript: {request.call_id}")

        response = CallIntelligenceResponse(call_id=request.call_id)

        try:
            # Parse transcript into segments if needed
            segments = request.segments
            if not segments and request.transcript:
                segments = self._parse_transcript(request.transcript)

            if not segments:
                response.success = False
                response.errors.append("No transcript content to process")
                return response

            # Determine which agents to run
            agents_to_run = request.agents_to_run or list(self._agents.keys())

            # Run agents in parallel
            agent_tasks = []
            for agent_name in agents_to_run:
                if agent_name in self._agents:
                    agent = self._agents[agent_name]
                    task = asyncio.create_task(
                        self._run_agent(agent, segments, request.existing_borrower_data)
                    )
                    agent_tasks.append((agent_name, task))

            # Gather results
            for agent_name, task in agent_tasks:
                try:
                    result = await task
                    response.agent_results.append(result)

                    # Map to appropriate extraction category
                    self._map_extractions(response, agent_name, result)

                except Exception as e:
                    safe_error = mask_pii_for_logging(str(e))
                    logger.exception(f"Agent {agent_name} failed: {safe_error}")
                    response.errors.append(f"Agent {agent_name}: {safe_error}")

            # Calculate summary stats
            self._calculate_stats(response)

            # Save to database if session available
            if self.db:
                await self._save_results(request, response)

            response.processing_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Call {request.call_id} processed: "
                f"{response.total_extractions} extractions, "
                f"{response.processing_time_ms}ms"
            )

            return response

        except Exception as e:
            safe_error = mask_pii_for_logging(str(e))
            logger.exception(f"Call processing failed: {safe_error}")
            response.success = False
            response.errors.append(safe_error)
            response.processing_time_ms = int((time.time() - start_time) * 1000)
            return response

    def process_transcript_sync(
        self,
        request: CallIntelligenceRequest,
    ) -> CallIntelligenceResponse:
        """Synchronous version of process_transcript."""
        return asyncio.run(self.process_transcript(request))

    async def _run_agent(
        self,
        agent,
        segments: List[TranscriptSegment],
        existing_data: Dict[str, Any],
    ) -> ExtractionResult:
        """Run a single extraction agent."""
        start_time = time.time()

        try:
            result = await agent.extract(segments, existing_data)
            result.processing_time_ms = int((time.time() - start_time) * 1000)
            return result
        except Exception as e:
            return ExtractionResult(
                agent_name=agent.AGENT_NAME,
                errors=[str(e)],
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    def _parse_transcript(self, transcript: str) -> List[TranscriptSegment]:
        """
        Parse raw transcript text into segments.

        Uses the improved parser from process_transcript.py which handles:
        - Role-based keyword detection (Loan Officer, Borrower, etc.)
        - Speech pattern analysis for role inference
        - Multiple transcript formats
        - Automatic role inference for 2-party conversations
        """
        return parse_transcript_improved(transcript)

    def _map_extractions(
        self,
        response: CallIntelligenceResponse,
        agent_name: str,
        result: ExtractionResult,
    ) -> None:
        """Map agent results to response categories."""
        extractions_dict = {}

        for extraction in result.extractions:
            extractions_dict[extraction.field_name] = extraction.value
            extractions_dict[f"{extraction.field_name}_confidence"] = extraction.confidence

        if agent_name == "identity":
            response.identity_extractions.update(extractions_dict)
        elif agent_name == "property":
            response.address_extractions.update(extractions_dict)
        elif agent_name == "employment":
            response.employment_extractions.update(extractions_dict)
        elif agent_name == "financial":
            # Split financial into income, assets, liabilities
            for extraction in result.extractions:
                if extraction.field_name.startswith(("income", "salary", "wage", "bonus", "commission")):
                    response.income_extractions[extraction.field_name] = extraction.value
                    response.income_extractions[f"{extraction.field_name}_confidence"] = extraction.confidence
                elif extraction.field_name.startswith(("asset", "bank", "savings", "checking", "retirement")):
                    response.assets_extractions[extraction.field_name] = extraction.value
                    response.assets_extractions[f"{extraction.field_name}_confidence"] = extraction.confidence
                elif extraction.field_name.startswith(("debt", "loan", "liability", "payment", "owe")):
                    response.liabilities_extractions[extraction.field_name] = extraction.value
                    response.liabilities_extractions[f"{extraction.field_name}_confidence"] = extraction.confidence
                elif extraction.field_name.startswith(("property", "real_estate", "rental")):
                    response.reo_extractions[extraction.field_name] = extraction.value
                    response.reo_extractions[f"{extraction.field_name}_confidence"] = extraction.confidence
                else:
                    response.income_extractions[extraction.field_name] = extraction.value
        elif agent_name == "compliance":
            response.declarations_extractions.update(extractions_dict)
        elif agent_name == "intent":
            response.intent_extractions.update(extractions_dict)

    def _calculate_stats(self, response: CallIntelligenceResponse) -> None:
        """Calculate summary statistics."""
        total = 0
        high_conf = 0
        low_conf = 0

        for result in response.agent_results:
            for extraction in result.extractions:
                total += 1
                if extraction.confidence >= 90:
                    high_conf += 1
                elif extraction.confidence < 70:
                    low_conf += 1

        response.total_extractions = total
        response.high_confidence_count = high_conf
        response.low_confidence_count = low_conf

    async def _save_results(
        self,
        request: CallIntelligenceRequest,
        response: CallIntelligenceResponse,
    ) -> None:
        """Save extraction results to database."""
        try:
            from sqlalchemy import text

            # Save to call_intelligence_results table
            self.db.execute(
                text("""
                    INSERT INTO call_intelligence_results
                    (call_id, loan_id, organization_id, extractions,
                     total_extractions, high_confidence_count, processing_time_ms, created_at)
                    VALUES
                    (:call_id, :loan_id, :org_id, :extractions,
                     :total, :high_conf, :processing_time, :created_at)
                    ON CONFLICT (call_id) DO UPDATE SET
                        extractions = :extractions,
                        total_extractions = :total,
                        processing_time_ms = :processing_time,
                        updated_at = :created_at
                """),
                {
                    "call_id": request.call_id,
                    "loan_id": request.loan_id,
                    "org_id": request.organization_id,
                    "extractions": str(response.to_dict()),
                    "total": response.total_extractions,
                    "high_conf": response.high_confidence_count,
                    "processing_time": response.processing_time_ms,
                    "created_at": datetime.utcnow(),
                }
            )
            self.db.commit()
        except Exception as e:
            safe_error = mask_pii_for_logging(str(e))
            logger.warning(f"Failed to save call intelligence results: {safe_error}")
            try:
                self.db.rollback()
            except Exception as rollback_err:
                logger.debug(f"Rollback also failed: {rollback_err}")

    def get_supported_agents(self) -> List[Dict[str, Any]]:
        """Get list of supported extraction agents."""
        return [
            {
                "name": "identity",
                "description": "Extracts borrower identity information (name, SSN last 4, DOB, contact)",
                "fields": ["first_name", "last_name", "ssn_last_four", "date_of_birth", "email", "phone"],
            },
            {
                "name": "property",
                "description": "Extracts property and address information",
                "fields": ["address", "city", "state", "zip", "property_type", "purchase_price"],
            },
            {
                "name": "employment",
                "description": "Extracts employment history and details",
                "fields": ["employer", "position", "start_date", "income_type", "is_self_employed"],
            },
            {
                "name": "financial",
                "description": "Extracts income, assets, and liabilities",
                "fields": ["salary", "bonus", "bank_accounts", "debts", "rental_income"],
            },
            {
                "name": "compliance",
                "description": "Extracts declaration responses and compliance items",
                "fields": ["bankruptcy", "foreclosure", "judgments", "citizenship"],
            },
            {
                "name": "intent",
                "description": "Extracts loan intent and preferences",
                "fields": ["loan_purpose", "timeline", "down_payment", "rate_preference"],
            },
        ]
