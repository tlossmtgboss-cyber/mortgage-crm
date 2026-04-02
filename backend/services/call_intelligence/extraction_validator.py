"""
Extraction Validator

Compares unified extraction vs parallel agent extraction to validate
that the 6x more efficient unified approach maintains extraction quality.

Usage:
    validator = ExtractionValidator(llm_client)
    report = await validator.validate_transcript(transcript)
    print(report.summary())

    # Or validate multiple transcripts
    reports = await validator.validate_batch(transcripts)
    summary = validator.aggregate_reports(reports)
"""

import logging
import time
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from .data_contracts import (
    CallIntelligenceRequest,
    CallIntelligenceResponse,
    ExtractedValue,
    ExtractionResult,
)
from .processor import CallIntelligenceProcessor

logger = logging.getLogger(__name__)


class ComparisonResult(str, Enum):
    """Result of comparing a single field extraction."""
    MATCH = "match"                    # Both extracted same value
    VALUE_MISMATCH = "value_mismatch"  # Both extracted but different values
    UNIFIED_ONLY = "unified_only"      # Only unified extracted
    AGENTS_ONLY = "agents_only"        # Only parallel agents extracted
    NEITHER = "neither"                # Neither extracted


@dataclass
class FieldComparison:
    """Comparison of a single field between extraction methods."""
    field_name: str
    domain: str  # identity, property, employment, financial, compliance, intent
    result: ComparisonResult

    unified_value: Optional[Any] = None
    unified_confidence: float = 0.0

    agents_value: Optional[Any] = None
    agents_confidence: float = 0.0

    confidence_diff: float = 0.0  # unified - agents

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "domain": self.domain,
            "result": self.result.value,
            "unified_value": self.unified_value,
            "unified_confidence": self.unified_confidence,
            "agents_value": self.agents_value,
            "agents_confidence": self.agents_confidence,
            "confidence_diff": self.confidence_diff,
        }


@dataclass
class ValidationReport:
    """Report comparing unified vs parallel agent extraction."""
    call_id: str
    transcript_length: int

    # Timing
    unified_time_ms: int = 0
    agents_time_ms: int = 0
    time_saved_ms: int = 0
    speedup_factor: float = 0.0

    # Field comparisons
    comparisons: List[FieldComparison] = field(default_factory=list)

    # Summary stats
    total_fields: int = 0
    matches: int = 0
    value_mismatches: int = 0
    unified_only: int = 0
    agents_only: int = 0
    neither: int = 0

    # Confidence analysis
    avg_unified_confidence: float = 0.0
    avg_agents_confidence: float = 0.0
    avg_confidence_diff: float = 0.0

    # Quality score (0-100)
    quality_score: float = 0.0

    # Errors
    unified_errors: List[str] = field(default_factory=list)
    agents_errors: List[str] = field(default_factory=list)

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def calculate_stats(self):
        """Calculate summary statistics from comparisons."""
        if not self.comparisons:
            return

        self.total_fields = len(self.comparisons)
        self.matches = len([c for c in self.comparisons if c.result == ComparisonResult.MATCH])
        self.value_mismatches = len([c for c in self.comparisons if c.result == ComparisonResult.VALUE_MISMATCH])
        self.unified_only = len([c for c in self.comparisons if c.result == ComparisonResult.UNIFIED_ONLY])
        self.agents_only = len([c for c in self.comparisons if c.result == ComparisonResult.AGENTS_ONLY])
        self.neither = len([c for c in self.comparisons if c.result == ComparisonResult.NEITHER])

        # Confidence averages (excluding neither)
        unified_confs = [c.unified_confidence for c in self.comparisons if c.unified_confidence > 0]
        agents_confs = [c.agents_confidence for c in self.comparisons if c.agents_confidence > 0]

        self.avg_unified_confidence = sum(unified_confs) / len(unified_confs) if unified_confs else 0
        self.avg_agents_confidence = sum(agents_confs) / len(agents_confs) if agents_confs else 0
        self.avg_confidence_diff = self.avg_unified_confidence - self.avg_agents_confidence

        # Calculate quality score
        # - Matches are good (+1)
        # - Unified-only is neutral (0) - might be finding more
        # - Agents-only is bad (-1) - missing extractions
        # - Value mismatches are very bad (-2)
        extracted_fields = self.total_fields - self.neither
        if extracted_fields > 0:
            score = (
                self.matches * 1.0 +
                self.unified_only * 0.5 +  # Bonus for finding more
                self.agents_only * -1.0 +  # Penalty for missing
                self.value_mismatches * -2.0
            )
            # Normalize to 0-100
            max_score = extracted_fields * 1.0
            min_score = extracted_fields * -2.0
            self.quality_score = ((score - min_score) / (max_score - min_score)) * 100

        # Calculate speedup
        if self.agents_time_ms > 0:
            self.time_saved_ms = self.agents_time_ms - self.unified_time_ms
            self.speedup_factor = self.agents_time_ms / self.unified_time_ms if self.unified_time_ms > 0 else 0

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"=== Extraction Validation Report ===",
            f"Call ID: {self.call_id}",
            f"Transcript: {self.transcript_length:,} chars",
            f"",
            f"--- Timing ---",
            f"Unified:  {self.unified_time_ms:,}ms",
            f"Agents:   {self.agents_time_ms:,}ms",
            f"Speedup:  {self.speedup_factor:.1f}x ({self.time_saved_ms:,}ms saved)",
            f"",
            f"--- Field Comparison ---",
            f"Total fields:     {self.total_fields}",
            f"Matches:          {self.matches} ({self.matches/self.total_fields*100:.0f}%)" if self.total_fields else "Matches: 0",
            f"Value mismatches: {self.value_mismatches}",
            f"Unified-only:     {self.unified_only}",
            f"Agents-only:      {self.agents_only}",
            f"Neither:          {self.neither}",
            f"",
            f"--- Confidence ---",
            f"Unified avg:  {self.avg_unified_confidence:.1f}",
            f"Agents avg:   {self.avg_agents_confidence:.1f}",
            f"Difference:   {self.avg_confidence_diff:+.1f}",
            f"",
            f"--- Quality Score ---",
            f"Score: {self.quality_score:.1f}/100",
            f"Grade: {self._get_grade()}",
        ]

        if self.value_mismatches > 0:
            lines.append(f"")
            lines.append(f"--- Value Mismatches ---")
            for c in self.comparisons:
                if c.result == ComparisonResult.VALUE_MISMATCH:
                    lines.append(f"  {c.field_name}:")
                    lines.append(f"    Unified: {c.unified_value} (conf: {c.unified_confidence:.0f})")
                    lines.append(f"    Agents:  {c.agents_value} (conf: {c.agents_confidence:.0f})")

        if self.agents_only > 0:
            lines.append(f"")
            lines.append(f"--- Missing from Unified ---")
            for c in self.comparisons:
                if c.result == ComparisonResult.AGENTS_ONLY:
                    lines.append(f"  {c.field_name}: {c.agents_value} (conf: {c.agents_confidence:.0f})")

        return "\n".join(lines)

    def _get_grade(self) -> str:
        """Get letter grade from quality score."""
        if self.quality_score >= 95:
            return "A+"
        elif self.quality_score >= 90:
            return "A"
        elif self.quality_score >= 85:
            return "B+"
        elif self.quality_score >= 80:
            return "B"
        elif self.quality_score >= 75:
            return "C+"
        elif self.quality_score >= 70:
            return "C"
        elif self.quality_score >= 60:
            return "D"
        else:
            return "F"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "transcript_length": self.transcript_length,
            "timing": {
                "unified_ms": self.unified_time_ms,
                "agents_ms": self.agents_time_ms,
                "time_saved_ms": self.time_saved_ms,
                "speedup_factor": round(self.speedup_factor, 2),
            },
            "field_stats": {
                "total": self.total_fields,
                "matches": self.matches,
                "value_mismatches": self.value_mismatches,
                "unified_only": self.unified_only,
                "agents_only": self.agents_only,
                "neither": self.neither,
            },
            "confidence": {
                "unified_avg": round(self.avg_unified_confidence, 1),
                "agents_avg": round(self.avg_agents_confidence, 1),
                "difference": round(self.avg_confidence_diff, 1),
            },
            "quality_score": round(self.quality_score, 1),
            "grade": self._get_grade(),
            "comparisons": [c.to_dict() for c in self.comparisons],
            "errors": {
                "unified": self.unified_errors,
                "agents": self.agents_errors,
            },
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AggregateReport:
    """Aggregated report across multiple validation runs."""
    total_transcripts: int = 0
    total_fields_compared: int = 0

    # Aggregate timing
    total_unified_time_ms: int = 0
    total_agents_time_ms: int = 0
    avg_speedup_factor: float = 0.0

    # Aggregate field stats
    total_matches: int = 0
    total_mismatches: int = 0
    total_unified_only: int = 0
    total_agents_only: int = 0

    # Quality
    avg_quality_score: float = 0.0
    min_quality_score: float = 100.0
    max_quality_score: float = 0.0

    # Pass/fail threshold
    passing_threshold: float = 85.0
    passing_count: int = 0
    failing_count: int = 0

    # Individual reports
    reports: List[ValidationReport] = field(default_factory=list)

    def summary(self) -> str:
        """Generate human-readable aggregate summary."""
        match_rate = self.total_matches / self.total_fields_compared * 100 if self.total_fields_compared else 0
        pass_rate = self.passing_count / self.total_transcripts * 100 if self.total_transcripts else 0

        lines = [
            f"=== Aggregate Validation Report ===",
            f"Transcripts validated: {self.total_transcripts}",
            f"",
            f"--- Overall Results ---",
            f"Pass rate:     {self.passing_count}/{self.total_transcripts} ({pass_rate:.0f}%)",
            f"Match rate:    {self.total_matches}/{self.total_fields_compared} ({match_rate:.0f}%)",
            f"Avg quality:   {self.avg_quality_score:.1f}/100",
            f"Quality range: {self.min_quality_score:.0f} - {self.max_quality_score:.0f}",
            f"",
            f"--- Performance ---",
            f"Avg speedup:   {self.avg_speedup_factor:.1f}x",
            f"Total saved:   {(self.total_agents_time_ms - self.total_unified_time_ms)/1000:.1f}s",
            f"",
            f"--- Field Statistics ---",
            f"Matches:       {self.total_matches}",
            f"Mismatches:    {self.total_mismatches}",
            f"Unified-only:  {self.total_unified_only}",
            f"Agents-only:   {self.total_agents_only}",
        ]

        if self.failing_count > 0:
            lines.append(f"")
            lines.append(f"--- Failing Transcripts ---")
            for report in self.reports:
                if report.quality_score < self.passing_threshold:
                    lines.append(f"  {report.call_id}: {report.quality_score:.0f}/100")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_transcripts": self.total_transcripts,
            "pass_rate": self.passing_count / self.total_transcripts if self.total_transcripts else 0,
            "avg_quality_score": round(self.avg_quality_score, 1),
            "avg_speedup_factor": round(self.avg_speedup_factor, 2),
            "field_stats": {
                "total": self.total_fields_compared,
                "matches": self.total_matches,
                "mismatches": self.total_mismatches,
                "unified_only": self.total_unified_only,
                "agents_only": self.total_agents_only,
            },
            "quality_range": {
                "min": round(self.min_quality_score, 1),
                "max": round(self.max_quality_score, 1),
            },
        }


# All fields we expect to potentially extract
ALL_EXTRACTION_FIELDS = {
    "identity": [
        "first_name", "last_name", "middle_name", "suffix",
        "ssn_last_four", "date_of_birth", "email", "phone",
        "marital_status", "dependents", "citizenship_status",
    ],
    "property": [
        "street_address", "city", "state", "zip_code",
        "property_type", "purchase_price", "down_payment",
        "down_payment_percent", "current_housing_status",
        "current_housing_payment", "years_at_current_address",
    ],
    "employment": [
        "employer_name", "job_title", "employment_start_date",
        "years_at_job", "employment_type", "is_self_employed",
        "business_name", "industry", "employer_phone",
        "employer_address", "previous_employer", "years_at_previous_job",
    ],
    "financial": [
        "annual_salary", "monthly_salary", "hourly_rate",
        "bonus_income", "commission_income", "overtime_income",
        "rental_income", "other_income", "checking_balance",
        "savings_balance", "retirement_balance", "investment_balance",
        "gift_funds", "car_payment", "student_loan_payment",
        "credit_card_payment", "other_debt_payment",
    ],
    "compliance": [
        "has_bankruptcy", "bankruptcy_type", "bankruptcy_discharge_date",
        "has_foreclosure", "foreclosure_date", "has_judgments",
        "has_delinquent_debt", "is_party_to_lawsuit", "has_alimony",
        "alimony_amount", "will_occupy_as_primary", "is_first_time_buyer",
        "has_ownership_interest",
    ],
    "intent": [
        "loan_purpose", "loan_type_preference", "rate_type_preference",
        "target_timeline", "urgency", "has_preapproval", "has_realtor",
        "realtor_name", "has_property_identified", "competing_with_other_lenders",
    ],
}


class ExtractionValidator:
    """
    Validates unified extraction quality against parallel agent extraction.

    Runs both extraction methods on the same transcript and compares:
    - Which fields were extracted
    - Extracted values
    - Confidence scores
    - Processing time
    """

    def __init__(self, llm_client, db_session=None):
        """
        Initialize validator.

        Args:
            llm_client: LLM client for extraction
            db_session: Optional database session
        """
        self.llm_client = llm_client
        self.db_session = db_session

        # Create two processors - one unified, one parallel
        self.unified_processor = CallIntelligenceProcessor(
            db_session=db_session,
            llm_client=llm_client,
            use_unified=True,
        )

        self.agents_processor = CallIntelligenceProcessor(
            db_session=db_session,
            llm_client=llm_client,
            use_unified=False,
        )

    async def validate_transcript(
        self,
        transcript: str,
        call_id: Optional[str] = None,
    ) -> ValidationReport:
        """
        Validate extraction quality on a single transcript.

        Args:
            transcript: The transcript text to process
            call_id: Optional call ID (generated if not provided)

        Returns:
            ValidationReport with comparison results
        """
        import uuid
        call_id = call_id or f"validation-{uuid.uuid4().hex[:8]}"

        report = ValidationReport(
            call_id=call_id,
            transcript_length=len(transcript),
        )

        # Create request
        request = CallIntelligenceRequest(
            call_id=call_id,
            transcript=transcript,
        )

        # Run unified extraction
        logger.info(f"Running unified extraction for {call_id}")
        unified_start = time.time()
        try:
            unified_response = await self.unified_processor.process_transcript(request)
            report.unified_time_ms = int((time.time() - unified_start) * 1000)
            report.unified_errors = unified_response.errors
        except Exception as e:
            logger.error(f"Unified extraction failed: {e}")
            report.unified_errors.append(str(e))
            unified_response = None

        # Run parallel agents extraction
        logger.info(f"Running parallel agents extraction for {call_id}")
        agents_start = time.time()
        try:
            agents_response = await self.agents_processor.process_transcript(request)
            report.agents_time_ms = int((time.time() - agents_start) * 1000)
            report.agents_errors = agents_response.errors
        except Exception as e:
            logger.error(f"Parallel agents extraction failed: {e}")
            report.agents_errors.append(str(e))
            agents_response = None

        # Compare results
        if unified_response and agents_response:
            report.comparisons = self._compare_responses(unified_response, agents_response)
            report.calculate_stats()

        logger.info(
            f"Validation complete for {call_id}: "
            f"score={report.quality_score:.0f}, "
            f"matches={report.matches}/{report.total_fields}, "
            f"speedup={report.speedup_factor:.1f}x"
        )

        return report

    async def validate_batch(
        self,
        transcripts: List[Tuple[str, str]],  # List of (call_id, transcript)
        max_concurrent: int = 3,
    ) -> AggregateReport:
        """
        Validate multiple transcripts and aggregate results.

        Args:
            transcripts: List of (call_id, transcript) tuples
            max_concurrent: Maximum concurrent validations

        Returns:
            AggregateReport with aggregated statistics
        """
        aggregate = AggregateReport()

        # Process with limited concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def validate_one(call_id: str, transcript: str) -> ValidationReport:
            async with semaphore:
                return await self.validate_transcript(transcript, call_id)

        tasks = [
            validate_one(call_id, transcript)
            for call_id, transcript in transcripts
        ]

        reports = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        for report in reports:
            if isinstance(report, Exception):
                logger.error(f"Validation failed: {report}")
                continue

            aggregate.reports.append(report)
            aggregate.total_transcripts += 1
            aggregate.total_fields_compared += report.total_fields
            aggregate.total_unified_time_ms += report.unified_time_ms
            aggregate.total_agents_time_ms += report.agents_time_ms
            aggregate.total_matches += report.matches
            aggregate.total_mismatches += report.value_mismatches
            aggregate.total_unified_only += report.unified_only
            aggregate.total_agents_only += report.agents_only

            aggregate.min_quality_score = min(aggregate.min_quality_score, report.quality_score)
            aggregate.max_quality_score = max(aggregate.max_quality_score, report.quality_score)

            if report.quality_score >= aggregate.passing_threshold:
                aggregate.passing_count += 1
            else:
                aggregate.failing_count += 1

        # Calculate averages
        if aggregate.total_transcripts > 0:
            aggregate.avg_quality_score = sum(r.quality_score for r in aggregate.reports) / aggregate.total_transcripts

            speedups = [r.speedup_factor for r in aggregate.reports if r.speedup_factor > 0]
            aggregate.avg_speedup_factor = sum(speedups) / len(speedups) if speedups else 0

        return aggregate

    def _compare_responses(
        self,
        unified: CallIntelligenceResponse,
        agents: CallIntelligenceResponse,
    ) -> List[FieldComparison]:
        """Compare two extraction responses field by field."""
        comparisons = []

        # Map response extractions to domain
        unified_by_domain = self._extract_by_domain(unified)
        agents_by_domain = self._extract_by_domain(agents)

        # Compare each domain
        for domain, fields in ALL_EXTRACTION_FIELDS.items():
            unified_domain = unified_by_domain.get(domain, {})
            agents_domain = agents_by_domain.get(domain, {})

            # Get all fields mentioned in either response
            all_fields = set(fields) | set(unified_domain.keys()) | set(agents_domain.keys())

            for field_name in all_fields:
                unified_ext = unified_domain.get(field_name)
                agents_ext = agents_domain.get(field_name)

                comparison = self._compare_field(field_name, domain, unified_ext, agents_ext)
                comparisons.append(comparison)

        return comparisons

    def _extract_by_domain(
        self,
        response: CallIntelligenceResponse,
    ) -> Dict[str, Dict[str, ExtractedValue]]:
        """Extract values organized by domain from response."""
        result = {
            "identity": {},
            "property": {},
            "employment": {},
            "financial": {},
            "compliance": {},
            "intent": {},
        }

        # Map from agent_results
        for agent_result in response.agent_results:
            domain = agent_result.agent_name
            if domain in result:
                for extraction in agent_result.extractions:
                    if extraction.value is not None:
                        result[domain][extraction.field_name] = extraction

        return result

    def _compare_field(
        self,
        field_name: str,
        domain: str,
        unified_ext: Optional[ExtractedValue],
        agents_ext: Optional[ExtractedValue],
    ) -> FieldComparison:
        """Compare a single field extraction."""
        comparison = FieldComparison(
            field_name=field_name,
            domain=domain,
            result=ComparisonResult.NEITHER,
        )

        has_unified = unified_ext is not None and unified_ext.value is not None
        has_agents = agents_ext is not None and agents_ext.value is not None

        if has_unified:
            comparison.unified_value = unified_ext.value
            comparison.unified_confidence = unified_ext.confidence

        if has_agents:
            comparison.agents_value = agents_ext.value
            comparison.agents_confidence = agents_ext.confidence

        # Determine result
        if has_unified and has_agents:
            # Both extracted - check if values match
            if self._values_match(unified_ext.value, agents_ext.value):
                comparison.result = ComparisonResult.MATCH
            else:
                comparison.result = ComparisonResult.VALUE_MISMATCH
            comparison.confidence_diff = comparison.unified_confidence - comparison.agents_confidence
        elif has_unified:
            comparison.result = ComparisonResult.UNIFIED_ONLY
        elif has_agents:
            comparison.result = ComparisonResult.AGENTS_ONLY
        else:
            comparison.result = ComparisonResult.NEITHER

        return comparison

    def _values_match(self, value1: Any, value2: Any) -> bool:
        """Check if two extracted values match (with fuzzy matching for strings)."""
        if value1 is None or value2 is None:
            return value1 == value2

        # Normalize strings
        if isinstance(value1, str) and isinstance(value2, str):
            v1 = value1.lower().strip()
            v2 = value2.lower().strip()
            return v1 == v2

        # Handle numbers
        if isinstance(value1, (int, float)) and isinstance(value2, (int, float)):
            # Allow small tolerance for floating point
            return abs(float(value1) - float(value2)) < 0.01

        # Handle booleans
        if isinstance(value1, bool) or isinstance(value2, bool):
            return bool(value1) == bool(value2)

        # Default comparison
        return value1 == value2


# =============================================================================
# Sample Transcripts for Testing
# =============================================================================

SAMPLE_TRANSCRIPTS = [
    (
        "sample-prequal-001",
        """
Loan Officer: Good morning! Thank you for calling. How can I help you today?
Borrower: Hi, I'm looking to buy a house and wanted to get pre-qualified for a mortgage.
Loan Officer: I'd be happy to help with that. Can I start by getting your name?
Borrower: Sure, my name is Michael Johnson.
Loan Officer: Great, Michael. And what's your date of birth?
Borrower: March 15, 1985.
Loan Officer: Perfect. And the best phone number to reach you?
Borrower: 555-123-4567.
Loan Officer: And your email address?
Borrower: michael.johnson@email.com
Loan Officer: Now, where do you currently work?
Borrower: I work at Google as a software engineer.
Loan Officer: How long have you been there?
Borrower: About 4 years now.
Loan Officer: And what's your annual salary?
Borrower: I make $175,000 base salary, plus I get about $50,000 in stock grants annually.
Loan Officer: Do you have any other income?
Borrower: No, that's my only income.
Loan Officer: What about monthly debts? Any car payments, student loans?
Borrower: I have a car payment of $450 a month and student loans at $300 a month.
Loan Officer: Do you have any savings or checking accounts?
Borrower: I have about $80,000 in savings and maybe $15,000 in checking.
Loan Officer: What price range are you looking at for the house?
Borrower: We're looking at houses around $650,000 to $700,000.
Loan Officer: And how much do you have for a down payment?
Borrower: We've saved up $140,000 for the down payment.
Loan Officer: Is this going to be your primary residence?
Borrower: Yes, this will be our primary home.
Loan Officer: Have you ever filed for bankruptcy or had a foreclosure?
Borrower: No, never.
Loan Officer: Do you currently own any other properties?
Borrower: No, this would be our first home.
"""
    ),
    (
        "sample-refinance-002",
        """
Loan Officer: Hello, how can I assist you today?
Borrower: Hi, I'm interested in refinancing my current mortgage.
Loan Officer: Sure, I can help with that. What's your name?
Borrower: Sarah Williams.
Loan Officer: And your current address, Sarah?
Borrower: 123 Oak Street, San Francisco, California 94102.
Loan Officer: What's your current mortgage balance approximately?
Borrower: Around $380,000 I think.
Loan Officer: And what was the purchase price of the home?
Borrower: We bought it for $550,000 three years ago.
Loan Officer: What's your current interest rate?
Borrower: It's 6.5%.
Loan Officer: Where do you work?
Borrower: I'm a nurse at UCSF Medical Center.
Loan Officer: Annual income?
Borrower: About $95,000.
Loan Officer: Any other income? Spouse's income?
Borrower: My husband makes about $85,000. He's a teacher.
Loan Officer: Monthly debts besides the mortgage?
Borrower: Just my car at $350 a month.
Loan Officer: What are you hoping to achieve with the refinance?
Borrower: Mainly to get a lower rate if possible. Maybe pull out some cash for renovations.
Loan Officer: How much cash out are you thinking?
Borrower: Maybe $50,000 for a kitchen remodel.
"""
    ),
]


async def run_validation_demo():
    """
    Demo function to run validation on sample transcripts.

    Note: Requires an LLM client to be configured.
    """
    print("=" * 60)
    print("Extraction Validator Demo")
    print("=" * 60)
    print("\nThis demo requires an LLM client.")
    print("To run validation, use:")
    print("\n  from services.call_intelligence.extraction_validator import ExtractionValidator")
    print("  from services.call_intelligence.llm_client import create_llm_client")
    print("")
    print("  llm_client = create_llm_client()")
    print("  validator = ExtractionValidator(llm_client)")
    print("  report = await validator.validate_transcript(transcript)")
    print("  print(report.summary())")
    print("")
    print("Sample transcripts available in SAMPLE_TRANSCRIPTS")
    print("=" * 60)
