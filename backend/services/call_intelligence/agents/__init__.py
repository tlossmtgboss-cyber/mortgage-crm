"""
Call Intelligence Extraction Agents

Specialized AI agents for extracting structured data from mortgage call transcripts.

This module provides a suite of extraction agents, each focused on a specific
domain of mortgage application data:

Agents:
    IdentityExtractionAgent: Extracts borrower identity (name, SSN last 4, DOB, contact info)
    PropertyExtractionAgent: Extracts property details (address, type, purchase price)
    EmploymentExtractionAgent: Extracts employment info (employer, title, income)
    FinancialExtractionAgent: Extracts financial data (assets, liabilities, income sources)
    ComplianceExtractionAgent: Extracts compliance declarations (bankruptcy, foreclosure, citizenship)
    IntentExtractionAgent: Extracts loan intent (purpose, timeline, preferences)

Architecture:
    All agents inherit from BaseExtractionAgent and implement a two-phase extraction:
    1. LLM-first: Uses Claude/OpenAI for intelligent extraction with context
    2. Regex fallback: Pattern matching when LLM is unavailable or for validation

Shared Patterns:
    Common regex patterns for citizenship, marital status, etc. are consolidated
    in shared_patterns.py to ensure consistency across agents.

Logging Guidelines:
    - DEBUG: Internal processing details (pattern matching attempts, parse steps)
    - INFO: Successful extractions, LLM client initialization, processing summaries
    - WARNING: Recoverable errors, low confidence extractions, PII detected in input
    - ERROR: Failed extractions, API errors, invalid configurations

Testing:
    Unit tests are located in: backend/tests/unit/test_call_intelligence.py
    Run tests with: pytest tests/unit/test_call_intelligence.py -v

Example:
    from services.call_intelligence.agents import IdentityExtractionAgent

    agent = IdentityExtractionAgent(llm_client)
    result = await agent.extract(transcript_segments, existing_data={})

    for extraction in result.extractions:
        print(f"{extraction.field_name}: {extraction.value} (confidence: {extraction.confidence})")
"""

from .base_agent import BaseExtractionAgent
from .identity_agent import IdentityExtractionAgent
from .property_agent import PropertyExtractionAgent
from .employment_agent import EmploymentExtractionAgent
from .financial_agent import FinancialExtractionAgent
from .compliance_agent import ComplianceExtractionAgent
from .intent_agent import IntentExtractionAgent
from .urla_extraction_agent import URLAExtractionAgent
from .shared_patterns import (
    US_CITIZEN_PATTERNS_COMPILED,
    PERMANENT_RESIDENT_PATTERNS_COMPILED,
    NON_PERMANENT_RESIDENT_PATTERNS_COMPILED,
    MARITAL_STATUS_PATTERNS,
    match_citizenship,
    match_marital_status,
)

# Live call agents (Domain 4: Mobile + Call Intelligence)
from .live_transcription_agent import LiveTranscriptionAgent
from .sentiment_analysis_agent import SentimentAnalysisAgent
from .objection_detection_agent import ObjectionDetectionAgent
from .compliance_monitor_agent import ComplianceMonitorCallAgent
from .coaching_prompt_agent import CoachingPromptAgent

__all__ = [
    # Extraction agents
    "BaseExtractionAgent",
    "IdentityExtractionAgent",
    "PropertyExtractionAgent",
    "EmploymentExtractionAgent",
    "FinancialExtractionAgent",
    "ComplianceExtractionAgent",
    "IntentExtractionAgent",
    "URLAExtractionAgent",
    # Live call agents
    "LiveTranscriptionAgent",
    "SentimentAnalysisAgent",
    "ObjectionDetectionAgent",
    "ComplianceMonitorCallAgent",
    "CoachingPromptAgent",
    # Shared patterns
    "US_CITIZEN_PATTERNS_COMPILED",
    "PERMANENT_RESIDENT_PATTERNS_COMPILED",
    "NON_PERMANENT_RESIDENT_PATTERNS_COMPILED",
    "MARITAL_STATUS_PATTERNS",
    "match_citizenship",
    "match_marital_status",
]
