"""
Call Intelligence Processor

Main processor that coordinates extraction agents and produces
structured data for the Application Engine.

This module provides the central CallIntelligenceProcessor class that:
- Parses raw transcripts into speaker-attributed segments
- Runs multiple extraction agents in parallel (identity, property, employment, etc.)
- Alternatively uses unified extraction engine for 6x efficiency (feature flag)
- Categorizes extractions into mortgage application domains
- Tracks confidence scores and processing metrics
- Optionally persists results to the database

Extraction Modes:
    - UNIFIED (default): Single LLM call extracts all domains (~6x more efficient)
    - PARALLEL_AGENTS: Legacy mode with 6 parallel LLM calls per transcript

Example:
    from services.call_intelligence.processor import CallIntelligenceProcessor
    from services.call_intelligence.data_contracts import CallIntelligenceRequest

    # Initialize processor (llm_client optional for regex-only extraction)
    processor = CallIntelligenceProcessor(db_session=session, llm_client=llm)

    # Create request
    request = CallIntelligenceRequest(
        call_id="call-123",
        loan_id=456,
        organization_id=1,
        transcript="Tim: Hello, how can I help?\\nJack: I want to buy a house.",
    )

    # Process (async)
    response = await processor.process_transcript(request)

    # Access results
    print(f"Total extractions: {response.total_extractions}")
    print(f"High confidence: {response.high_confidence_count}")
    for agent_result in response.agent_results:
        for extraction in agent_result.extractions:
            print(f"  {extraction.field_name}: {extraction.value}")
"""

import logging
import os
import time
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from .llm_client import BaseLLMClient

from .data_contracts import (
    CallIntelligenceRequest,
    CallIntelligenceResponse,
    CallOutcomeData,
    ExtractionResult,
    ExtractedValue,
    TranscriptSegment,
    SpeakerRole,
    ExtractionMethod,
)
from .process_transcript import parse_transcript as parse_transcript_improved
from .pii_utils import mask_pii_for_logging, redact_transcript_for_llm
from .agents import (
    IdentityExtractionAgent,
    PropertyExtractionAgent,
    EmploymentExtractionAgent,
    FinancialExtractionAgent,
    ComplianceExtractionAgent,
    IntentExtractionAgent,
)
from .unified_extractor import UnifiedExtractionEngine, UnifiedExtractionResult
from .metrics import (
    track_extraction,
    track_error,
    track_confidence,
    ACTIVE_EXTRACTIONS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# FEATURE FLAGS
# =============================================================================
# Set USE_UNIFIED_EXTRACTOR=true to use the unified extraction engine (6x more efficient)
# Set USE_UNIFIED_EXTRACTOR=false to use the legacy parallel agents approach

USE_UNIFIED_EXTRACTOR = os.getenv("USE_UNIFIED_EXTRACTOR", "true").lower() == "true"
"""
Feature flag to enable unified extraction engine.

When enabled (default):
- Single LLM call extracts all domains at once
- ~6x reduction in API calls and costs
- Faster processing time

When disabled:
- Falls back to 6 parallel agent LLM calls
- Use during migration/validation period
"""


# =============================================================================
# FIELD CATEGORIZATION
# =============================================================================
# These prefixes determine how extracted financial fields are categorized
# into income, assets, liabilities, or real estate owned (REO) buckets.

INCOME_FIELD_PREFIXES = ("income", "salary", "wage", "bonus", "commission")
"""Field prefixes that indicate income-related extractions."""

ASSET_FIELD_PREFIXES = ("asset", "bank", "savings", "checking", "retirement", "investment")
"""Field prefixes that indicate asset-related extractions."""

LIABILITY_FIELD_PREFIXES = ("debt", "loan", "liability", "payment", "owe", "credit_card", "auto_loan", "student_loan")
"""Field prefixes that indicate liability-related extractions."""

REO_FIELD_PREFIXES = ("property", "real_estate", "rental", "reo")
"""Field prefixes that indicate real estate owned extractions."""


class CallIntelligenceProcessor:
    """
    Main processor for call transcript intelligence extraction.

    Coordinates extraction using either:
    - Unified extraction engine (single LLM call, default)
    - Multiple specialized AI agents (legacy, 6 parallel calls)

    The extraction mode is controlled by the USE_UNIFIED_EXTRACTOR feature flag.
    """

    VERSION = "2.0"

    def __init__(
        self,
        db_session: Optional["Session"] = None,
        llm_client: Optional["BaseLLMClient"] = None,
        use_unified: Optional[bool] = None,
    ):
        """
        Initialize processor with agents.

        Args:
            db_session: SQLAlchemy session for database operations
            llm_client: LLM client for AI extractions (OpenAI, Anthropic, etc.)
            use_unified: Override for unified extraction flag (None = use env var)
        """
        self.db = db_session
        self.llm_client = llm_client

        # Determine extraction mode
        self.use_unified = use_unified if use_unified is not None else USE_UNIFIED_EXTRACTOR

        # Initialize unified extractor if LLM client available and flag enabled
        self._unified_extractor: Optional[UnifiedExtractionEngine] = None
        if self.use_unified and llm_client:
            try:
                self._unified_extractor = UnifiedExtractionEngine(llm_client)
                logger.info("Unified extraction engine initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize unified extractor: {e}. Falling back to agents.")
                self.use_unified = False

        # Initialize extraction agents (for fallback or when unified is disabled)
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
        Process a call transcript through extraction.

        Uses unified extraction engine by default (single LLM call),
        with fallback to parallel agents if unified is disabled or fails.

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

            # Redact PII before sending to external LLM APIs
            segments, pii_stats = self._redact_segments_for_llm(segments)
            response.pii_redaction_stats = pii_stats

            # Use unified extraction if available
            if self.use_unified and self._unified_extractor:
                response = await self._process_with_unified(
                    request, segments, response
                )
            else:
                response = await self._process_with_agents(
                    request, segments, response
                )

            # Extract call outcome from intent extractions
            self._populate_call_outcome(response)

            # Calculate summary stats
            self._calculate_stats(response)

            # Save to database if session available
            if self.db:
                await self._save_results(request, response)

            response.processing_time_ms = int((time.time() - start_time) * 1000)

            # Track metrics
            track_extraction(
                method=response.extraction_method,
                duration_ms=response.processing_time_ms,
                field_count=response.total_extractions,
                high_confidence_count=response.high_confidence_count,
                low_confidence_count=response.low_confidence_count,
                success=True,
            )

            logger.info(
                f"Call {request.call_id} processed: "
                f"{response.total_extractions} extractions, "
                f"{response.processing_time_ms}ms, "
                f"method={response.extraction_method}"
            )

            return response

        except Exception as e:
            safe_error = mask_pii_for_logging(str(e))
            logger.exception(f"Call processing failed: {safe_error}")
            response.success = False
            response.errors.append(safe_error)
            response.processing_time_ms = int((time.time() - start_time) * 1000)

            # Track error metrics
            error_type = "unknown"
            if "timeout" in str(e).lower():
                error_type = "timeout"
            elif "rate" in str(e).lower():
                error_type = "rate_limit"
            elif "parse" in str(e).lower() or "json" in str(e).lower():
                error_type = "parse_error"

            track_error(error_type, method=response.extraction_method or "unknown")
            track_extraction(
                method=response.extraction_method or "unknown",
                duration_ms=response.processing_time_ms,
                success=False,
            )

            return response

    async def _process_with_unified(
        self,
        request: CallIntelligenceRequest,
        segments: List[TranscriptSegment],
        response: CallIntelligenceResponse,
    ) -> CallIntelligenceResponse:
        """
        Process transcript using unified extraction engine.

        Single LLM call extracts all domains at once.
        """
        try:
            unified_result = await self._unified_extractor.extract_all(
                call_id=request.call_id,
                segments=segments,
                existing_data=request.existing_borrower_data,
            )

            # Convert unified result to response format
            response = self._convert_unified_to_response(
                request.call_id, unified_result, response
            )
            response.extraction_method = ExtractionMethod.UNIFIED.value
            response.model_version = unified_result.prompt_hash

            return response

        except Exception as e:
            safe_error = mask_pii_for_logging(str(e))
            logger.warning(f"Unified extraction failed, falling back to agents: {safe_error}")

            # Fall back to parallel agents
            return await self._process_with_agents(request, segments, response)

    async def _process_with_agents(
        self,
        request: CallIntelligenceRequest,
        segments: List[TranscriptSegment],
        response: CallIntelligenceResponse,
    ) -> CallIntelligenceResponse:
        """
        Process transcript using parallel extraction agents.

        Legacy method with 6 parallel LLM calls.
        """
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

        response.extraction_method = ExtractionMethod.PARALLEL_AGENTS.value
        return response

    def _convert_unified_to_response(
        self,
        call_id: str,
        unified_result: UnifiedExtractionResult,
        response: CallIntelligenceResponse,
    ) -> CallIntelligenceResponse:
        """Convert unified extraction result to response format."""

        # Map identity extractions
        for field_name, extraction in unified_result.identity.items():
            response.identity_extractions[field_name] = extraction.value
            response.identity_extractions[f"{field_name}_confidence"] = extraction.confidence

        # Map property/address extractions
        for field_name, extraction in unified_result.property_info.items():
            response.address_extractions[field_name] = extraction.value
            response.address_extractions[f"{field_name}_confidence"] = extraction.confidence

        # Map employment extractions
        for field_name, extraction in unified_result.employment.items():
            response.employment_extractions[field_name] = extraction.value
            response.employment_extractions[f"{field_name}_confidence"] = extraction.confidence

        # Map financial extractions (split into categories)
        for field_name, extraction in unified_result.financial.items():
            if field_name.startswith(INCOME_FIELD_PREFIXES):
                response.income_extractions[field_name] = extraction.value
                response.income_extractions[f"{field_name}_confidence"] = extraction.confidence
            elif field_name.startswith(ASSET_FIELD_PREFIXES):
                response.assets_extractions[field_name] = extraction.value
                response.assets_extractions[f"{field_name}_confidence"] = extraction.confidence
            elif field_name.startswith(LIABILITY_FIELD_PREFIXES):
                response.liabilities_extractions[field_name] = extraction.value
                response.liabilities_extractions[f"{field_name}_confidence"] = extraction.confidence
            elif field_name.startswith(REO_FIELD_PREFIXES):
                response.reo_extractions[field_name] = extraction.value
                response.reo_extractions[f"{field_name}_confidence"] = extraction.confidence
            else:
                # Default uncategorized financial fields to income
                response.income_extractions[field_name] = extraction.value
                response.income_extractions[f"{field_name}_confidence"] = extraction.confidence

        # Map compliance/declarations extractions
        for field_name, extraction in unified_result.compliance.items():
            response.declarations_extractions[field_name] = extraction.value
            response.declarations_extractions[f"{field_name}_confidence"] = extraction.confidence

        # Map intent extractions
        for field_name, extraction in unified_result.intent.items():
            response.intent_extractions[field_name] = extraction.value
            response.intent_extractions[f"{field_name}_confidence"] = extraction.confidence

        # Convert to agent_results for backward compatibility
        response.agent_results = unified_result.to_agent_results()

        # Copy errors and warnings
        response.errors.extend(unified_result.errors)

        return response

    def process_transcript_sync(
        self,
        request: CallIntelligenceRequest,
    ) -> CallIntelligenceResponse:
        """
        Synchronous version of process_transcript.

        Handles both sync and async contexts safely:
        - If called from sync code: creates new event loop
        - If called from async code: runs in existing loop

        Note: Prefer using process_transcript() directly in async code.
        """
        try:
            # Check if we're already in an async context
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(self.process_transcript(request))

        # Already in async context - need different approach
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                self.process_transcript(request)
            )
            return future.result()

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

    def _redact_segments_for_llm(
        self,
        segments: List[TranscriptSegment],
    ) -> tuple:
        """
        Redact PII from transcript segments before sending to external LLM APIs.

        Creates new segment copies with redacted text so originals are preserved.
        Redacts: SSN, DOB, phone, email, credit card, bank account numbers.
        Preserves: names and addresses (needed for extraction).

        Returns:
            Tuple of (redacted_segments, aggregate_pii_stats)
        """
        aggregate_stats: Dict[str, int] = {}
        redacted_segments = []

        for segment in segments:
            redacted_text, stats = redact_transcript_for_llm(segment.text)

            # Accumulate stats across all segments
            for key, count in stats.items():
                aggregate_stats[key] = aggregate_stats.get(key, 0) + count

            # Create new segment with redacted text (preserve all other fields)
            redacted_segments.append(TranscriptSegment(
                speaker=segment.speaker,
                text=redacted_text,
                index=segment.index,
                start_time=segment.start_time,
                end_time=segment.end_time,
                confidence=segment.confidence,
            ))

        total = aggregate_stats.get("total", 0)
        if total > 0:
            logger.info(
                f"PII redaction complete: {total} items redacted across "
                f"{len(segments)} segments before LLM transmission"
            )

        return redacted_segments, aggregate_stats

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
            # Split financial into income, assets, liabilities, REO based on field prefixes
            # See INCOME_FIELD_PREFIXES, ASSET_FIELD_PREFIXES, etc. for categorization rules
            for extraction in result.extractions:
                if extraction.field_name.startswith(INCOME_FIELD_PREFIXES):
                    response.income_extractions[extraction.field_name] = extraction.value
                    response.income_extractions[f"{extraction.field_name}_confidence"] = extraction.confidence
                elif extraction.field_name.startswith(ASSET_FIELD_PREFIXES):
                    response.assets_extractions[extraction.field_name] = extraction.value
                    response.assets_extractions[f"{extraction.field_name}_confidence"] = extraction.confidence
                elif extraction.field_name.startswith(LIABILITY_FIELD_PREFIXES):
                    response.liabilities_extractions[extraction.field_name] = extraction.value
                    response.liabilities_extractions[f"{extraction.field_name}_confidence"] = extraction.confidence
                elif extraction.field_name.startswith(REO_FIELD_PREFIXES):
                    response.reo_extractions[extraction.field_name] = extraction.value
                    response.reo_extractions[f"{extraction.field_name}_confidence"] = extraction.confidence
                else:
                    # Default uncategorized financial fields to income
                    response.income_extractions[extraction.field_name] = extraction.value
        elif agent_name == "compliance":
            response.declarations_extractions.update(extractions_dict)
        elif agent_name == "intent":
            response.intent_extractions.update(extractions_dict)

    def _populate_call_outcome(self, response: CallIntelligenceResponse) -> None:
        """
        Extract call outcome data from intent extractions.

        Call outcome fields are extracted by the intent agent and then
        consolidated into a CallOutcomeData object for easy access.
        """
        if not response.intent_extractions:
            return

        try:
            # Build extractions dict in the format CallOutcomeData.from_extractions expects
            # The intent extractions may have flat values or nested {value, confidence} dicts
            extractions = {}
            for key, value in response.intent_extractions.items():
                # Skip confidence fields - they're paired with main fields
                if key.endswith("_confidence"):
                    continue

                # Check if there's a paired confidence value
                confidence_key = f"{key}_confidence"
                confidence = response.intent_extractions.get(confidence_key, 0)

                extractions[key] = {
                    "value": value,
                    "confidence": confidence,
                }

            response.call_outcome = CallOutcomeData.from_extractions(extractions)

            # Log if significant call outcome detected
            if response.call_outcome.outcome != "unknown":
                logger.info(
                    f"Call outcome detected: {response.call_outcome.outcome} "
                    f"(confidence: {response.call_outcome.outcome_confidence:.0f}%)"
                )
            if response.call_outcome.callback_scheduled:
                logger.info(f"Callback scheduled: {response.call_outcome.callback_datetime or 'time TBD'}")
            if response.call_outcome.application_started:
                logger.info("Application started during call")

        except Exception as e:
            logger.warning(f"Failed to populate call outcome: {e}")
            # Don't fail processing - call outcome is supplementary data

    def _calculate_stats(self, response: CallIntelligenceResponse) -> None:
        """Calculate summary statistics and log confidence distribution."""
        total = 0
        high_conf = 0
        medium_conf = 0
        low_conf = 0

        for result in response.agent_results:
            for extraction in result.extractions:
                total += 1
                if extraction.confidence >= 90:
                    high_conf += 1
                elif extraction.confidence >= 70:
                    medium_conf += 1
                else:
                    low_conf += 1

        response.total_extractions = total
        response.high_confidence_count = high_conf
        response.low_confidence_count = low_conf

        # Log confidence distribution for monitoring extraction quality
        if total > 0:
            high_pct = (high_conf / total) * 100
            low_pct = (low_conf / total) * 100
            logger.info(
                f"Confidence distribution: {high_conf}/{total} high ({high_pct:.0f}%), "
                f"{medium_conf}/{total} medium, {low_conf}/{total} low ({low_pct:.0f}%)"
            )
            if low_pct > 30:
                logger.warning(
                    f"High proportion of low-confidence extractions ({low_pct:.0f}%) - "
                    "consider reviewing transcript quality or extraction patterns"
                )

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
                    "created_at": datetime.now(timezone.utc),
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
