"""
Income Intelligence Engine

Automated income calculation engine for mortgage underwriting.
Calculates qualifying income from uploaded documents following
agency guidelines (Fannie Mae, Freddie Mac, FHA, VA).

Components:
- Orchestrator: Coordinates all engines and aggregates results
- Engines: Specialized calculators for each income type
- Data Contracts: Standardized input/output formats

Usage:
    from income_engine import IncomeOrchestrator

    orchestrator = IncomeOrchestrator(db_session)
    result = await orchestrator.calculate_income(
        loan_id=123,
        borrower_id=1,
        document_facts=extracted_data
    )
"""

from .orchestrator import IncomeOrchestrator
from .base import BaseIncomeEngine, EngineResult, IncomeStream, IncomeFlag, FlagRuleId
from .data_contracts import (
    DocumentFacts,
    W2Facts,
    PaystubFacts,
    ScheduleCFacts,
    ScheduleEFacts,
    K1Facts,
    BankStatementFacts,
    BankStatementMonth,
    RentalProperty,
    CalculationRequest,
    CalculationResponse,
    IncomeStreamType,
    FlagSeverity,
    TrendDirection,
)
from .routes import router as income_router

__version__ = "1.0.0"
__all__ = [
    # Main orchestrator
    "IncomeOrchestrator",
    # Base classes
    "BaseIncomeEngine",
    "EngineResult",
    "IncomeStream",
    "IncomeFlag",
    "FlagRuleId",
    # Data contracts
    "DocumentFacts",
    "W2Facts",
    "PaystubFacts",
    "ScheduleCFacts",
    "ScheduleEFacts",
    "K1Facts",
    "BankStatementFacts",
    "BankStatementMonth",
    "RentalProperty",
    "CalculationRequest",
    "CalculationResponse",
    # Enums
    "IncomeStreamType",
    "FlagSeverity",
    "TrendDirection",
    # API Router
    "income_router",
]
