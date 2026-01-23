"""
AI Underwriting Engine

A comprehensive, Fannie Mae/Freddie Mac/FHA/VA compliant automated underwriting system.
This engine provides:

- Income calculation and verification (W-2, self-employed, variable, rental)
- Asset analysis and large deposit detection
- Credit assessment and DTI calculation
- Automated condition generation and clearing
- Multi-program guideline eligibility checking
- Comprehensive loan data validation and cross-checks
- Fraud indicator detection

The engine processes loan applications in seconds, applying agency guidelines
with the expertise of a senior underwriter.

Usage:
    from services.underwriting_engine import underwrite_loan

    result = underwrite_loan(
        loan_data={"loan_amount": 400000, "property_value": 500000, ...},
        income_data={"income_sources": [...]},
        asset_data={"accounts": [...]},
        credit_data={"credit_score": 720, "tradelines": [...]},
    )

    print(result["decision"])  # approve, approve_eligible, refer, suspend, deny
"""

# Income Calculator
from .income_calculator import (
    IncomeCalculator,
    IncomeResult,
    IncomeItem,
    IncomeType,
    IncomeStatus,
)

# Asset Analyzer
from .asset_analyzer import (
    AssetAnalyzer,
    AssetResult,
    AssetItem,
    AssetType,
    AssetStatus,
    LargeDeposit,
)

# Credit Analyzer
from .credit_analyzer import (
    CreditAnalyzer,
    CreditResult,
    Tradeline,
    TradelineStatus,
    CreditEvent,
    CreditEventType,
)

# Condition Generator
from .condition_generator import (
    ConditionGenerator,
    ConditionClearing,
    Condition,
    ConditionType,
    ConditionCategory,
    ConditionPriority,
    ConditionStatus,
    generate_loan_conditions,
)

# Eligibility Engine
from .eligibility_engine import (
    EligibilityEngine,
    EligibilityResult,
    LoanScenario,
    Agency,
    LoanPurpose,
    PropertyType,
    OccupancyType,
    ConventionalEligibility,
    FHAEligibility,
    VAEligibility,
    check_loan_eligibility,
)

# Loan Engineering (Data Validation)
from .loan_engineering import (
    LoanDataValidator,
    ValidationResult,
    ValidationFinding,
    ValidationSeverity,
    ValidationCategory,
    FraudIndicatorDetector,
    DocumentMatcher,
    validate_loan_file,
)

# Main Underwriting Engine
from .underwriting_engine import (
    UnderwritingEngine,
    UnderwritingResult,
    UnderwritingDecision,
    UnderwritingFinding,
    RiskLevel,
    underwrite_loan,
)

# Convenience aliases for backwards compatibility
AssetAnalysisResult = AssetResult
CreditAnalysisResult = CreditResult

__all__ = [
    # Income
    'IncomeCalculator',
    'IncomeResult',
    'IncomeItem',
    'IncomeType',
    'IncomeStatus',

    # Assets
    'AssetAnalyzer',
    'AssetResult',
    'AssetAnalysisResult',
    'AssetItem',
    'AssetType',
    'AssetStatus',
    'LargeDeposit',

    # Credit
    'CreditAnalyzer',
    'CreditResult',
    'CreditAnalysisResult',
    'Tradeline',
    'TradelineStatus',
    'CreditEvent',
    'CreditEventType',

    # Conditions
    'ConditionGenerator',
    'ConditionClearing',
    'Condition',
    'ConditionType',
    'ConditionCategory',
    'ConditionPriority',
    'ConditionStatus',
    'generate_loan_conditions',

    # Eligibility
    'EligibilityEngine',
    'EligibilityResult',
    'LoanScenario',
    'Agency',
    'LoanPurpose',
    'PropertyType',
    'OccupancyType',
    'ConventionalEligibility',
    'FHAEligibility',
    'VAEligibility',
    'check_loan_eligibility',

    # Validation
    'LoanDataValidator',
    'ValidationResult',
    'ValidationFinding',
    'ValidationSeverity',
    'ValidationCategory',
    'FraudIndicatorDetector',
    'DocumentMatcher',
    'validate_loan_file',

    # Main Engine
    'UnderwritingEngine',
    'UnderwritingResult',
    'UnderwritingDecision',
    'UnderwritingFinding',
    'RiskLevel',
    'underwrite_loan',
]


# Version info
__version__ = "1.0.0"
__author__ = "Perennia AI"
