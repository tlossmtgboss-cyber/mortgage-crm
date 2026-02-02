"""
Call Intelligence Extraction Agents

Specialized AI agents for extracting structured data from call transcripts.
"""

from .base_agent import BaseExtractionAgent
from .identity_agent import IdentityExtractionAgent
from .property_agent import PropertyExtractionAgent
from .employment_agent import EmploymentExtractionAgent
from .financial_agent import FinancialExtractionAgent
from .compliance_agent import ComplianceExtractionAgent
from .intent_agent import IntentExtractionAgent
from .shared_patterns import (
    US_CITIZEN_PATTERNS_COMPILED,
    PERMANENT_RESIDENT_PATTERNS_COMPILED,
    NON_PERMANENT_RESIDENT_PATTERNS_COMPILED,
    MARITAL_STATUS_PATTERNS,
    match_citizenship,
    match_marital_status,
)

__all__ = [
    "BaseExtractionAgent",
    "IdentityExtractionAgent",
    "PropertyExtractionAgent",
    "EmploymentExtractionAgent",
    "FinancialExtractionAgent",
    "ComplianceExtractionAgent",
    "IntentExtractionAgent",
    # Shared patterns
    "US_CITIZEN_PATTERNS_COMPILED",
    "PERMANENT_RESIDENT_PATTERNS_COMPILED",
    "NON_PERMANENT_RESIDENT_PATTERNS_COMPILED",
    "MARITAL_STATUS_PATTERNS",
    "match_citizenship",
    "match_marital_status",
]
