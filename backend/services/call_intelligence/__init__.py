"""
Call Intelligence Service

Processes call transcripts using AI agents to extract structured data
for the Application Engine.

The service includes 6 specialized AI agents:
1. Identity Agent - Names, SSN (last 4 only), DOB, contact info
2. Property Agent - Address, property details, purchase info
3. Employment Agent - Job history, employer details
4. Financial Agent - Income, assets, liabilities
5. Compliance Agent - Declarations, disclosures
6. Intent Agent - Loan purpose, timeline, preferences

SECURITY:
- SSN handling: Only last 4 digits are ever stored or transmitted
- All source_text fields are sanitized to remove PII
- Use pii_utils for any custom PII handling needs

Usage:
    from services.call_intelligence import CallIntelligenceProcessor

    processor = CallIntelligenceProcessor(db_session)
    result = await processor.process_transcript(
        call_id="call_123",
        transcript="..."
    )

    # Result contains extracted data for Application Engine
"""

from .processor import CallIntelligenceProcessor
from .agents import (
    IdentityExtractionAgent,
    PropertyExtractionAgent,
    EmploymentExtractionAgent,
    FinancialExtractionAgent,
    ComplianceExtractionAgent,
    IntentExtractionAgent,
)
from .data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    CallIntelligenceRequest,
    CallIntelligenceResponse,
)
from .pii_utils import (
    redact_ssn,
    extract_ssn_last_four,
    contains_ssn,
    mask_pii_for_logging,
    sanitize_source_text,
    redact_transcript_for_llm,
    redact_dob,
    redact_phone,
    redact_email,
)
from .extraction_validator import (
    ExtractionValidator,
    ValidationReport,
    AggregateReport,
    SAMPLE_TRANSCRIPTS,
)

__all__ = [
    # Processor
    "CallIntelligenceProcessor",
    # Agents
    "IdentityExtractionAgent",
    "PropertyExtractionAgent",
    "EmploymentExtractionAgent",
    "FinancialExtractionAgent",
    "ComplianceExtractionAgent",
    "IntentExtractionAgent",
    # Data contracts
    "TranscriptSegment",
    "ExtractionResult",
    "CallIntelligenceRequest",
    "CallIntelligenceResponse",
    # PII utilities
    "redact_ssn",
    "extract_ssn_last_four",
    "contains_ssn",
    "mask_pii_for_logging",
    "sanitize_source_text",
    "redact_transcript_for_llm",
    "redact_dob",
    "redact_phone",
    "redact_email",
    # Validation
    "ExtractionValidator",
    "ValidationReport",
    "AggregateReport",
    "SAMPLE_TRANSCRIPTS",
]
