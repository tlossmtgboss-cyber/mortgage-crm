"""
Call Intelligence Service

Processes call transcripts using AI agents to extract structured data
for the Application Engine.

The service includes 6 specialized AI agents:
1. Identity Agent - Names, SSN, DOB, contact info
2. Property Agent - Address, property details, purchase info
3. Employment Agent - Job history, employer details
4. Financial Agent - Income, assets, liabilities
5. Compliance Agent - Declarations, disclosures
6. Intent Agent - Loan purpose, timeline, preferences

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

__all__ = [
    "CallIntelligenceProcessor",
    "IdentityExtractionAgent",
    "PropertyExtractionAgent",
    "EmploymentExtractionAgent",
    "FinancialExtractionAgent",
    "ComplianceExtractionAgent",
    "IntentExtractionAgent",
    "TranscriptSegment",
    "ExtractionResult",
    "CallIntelligenceRequest",
    "CallIntelligenceResponse",
]
