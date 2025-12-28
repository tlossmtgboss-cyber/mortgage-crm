"""
Income Services Package

AI-powered income extraction and underwriting calculation services.
"""

from .income_calculation_service import (
    IncomeCalculationService,
    IncomeCalculationResult,
    get_income_calculation_service,
)

__all__ = [
    "IncomeCalculationService",
    "IncomeCalculationResult",
    "get_income_calculation_service",
]
