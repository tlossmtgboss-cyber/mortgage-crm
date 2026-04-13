"""
Income Services Package

Provides:
- UnifiedIncomeCalculator: Calculate all 14 income types
- AIIncomeDetectionService: Detect income type from documents
- IncomeReviewWorkflowService: Manage review and approval workflow
- IncomeCalculationService: Legacy calculation service
"""

from .income_calculation_service import (
    IncomeCalculationService,
    IncomeCalculationResult as LegacyIncomeCalculationResult,
    get_income_calculation_service,
)

from .unified_income_calculator import (
    UnifiedIncomeType,
    PayFrequency,
    AveragingMethod,
    ConfidenceLevel,
    CalculationStep,
    IncomeCalculationResult,
    UnifiedIncomeCalculator,
    get_unified_income_calculator,
    W2HourlyData,
    W2SalaryData,
    OTBonusData,
    CommissionData,
    NonTaxSSData,
    NonTaxOtherData,
    BankStatementPersonalData,
    BankStatementBusinessData,
    RentalScheduleEData,
    SelfEmployment1084Data,
)

from .ai_income_detection_service import (
    IncomeDocumentType,
    ExtractedField,
    DocumentDetectionResult,
    AIIncomeDetectionService,
    get_ai_income_detection_service,
)

from .income_review_workflow import (
    ReviewStatus,
    ReviewAction,
    ConfidenceThreshold,
    ReviewHistoryEntry,
    IncomeReviewItem,
    ReviewQueueSummary,
    IncomeReviewWorkflowService,
    IncomeReviewOrchestrator,
    get_income_review_workflow,
    get_income_review_orchestrator,
)

from .form_1084_service import (
    Form1084Data,
    Form1084Service,
    get_form_1084_service,
)

__all__ = [
    # Legacy
    "IncomeCalculationService",
    "LegacyIncomeCalculationResult",
    "get_income_calculation_service",

    # Unified Calculator
    "UnifiedIncomeType",
    "PayFrequency",
    "AveragingMethod",
    "ConfidenceLevel",
    "CalculationStep",
    "IncomeCalculationResult",
    "UnifiedIncomeCalculator",
    "get_unified_income_calculator",

    # Data classes
    "W2HourlyData",
    "W2SalaryData",
    "OTBonusData",
    "CommissionData",
    "NonTaxSSData",
    "NonTaxOtherData",
    "BankStatementPersonalData",
    "BankStatementBusinessData",
    "RentalScheduleEData",
    "SelfEmployment1084Data",

    # Detection
    "IncomeDocumentType",
    "ExtractedField",
    "DocumentDetectionResult",
    "AIIncomeDetectionService",
    "get_ai_income_detection_service",

    # Review Workflow
    "ReviewStatus",
    "ReviewAction",
    "ConfidenceThreshold",
    "ReviewHistoryEntry",
    "IncomeReviewItem",
    "ReviewQueueSummary",
    "IncomeReviewWorkflowService",
    "IncomeReviewOrchestrator",
    "get_income_review_workflow",
    "get_income_review_orchestrator",

    # Form 1084
    "Form1084Data",
    "Form1084Service",
    "get_form_1084_service",
]
