"""
Income Calculation Engines

Specialized engines for each income type:
- W2Engine: W-2 wages and paystub analysis
- ScheduleCEngine: Self-employment (Schedule C)
- RentalEngine: Rental income (Schedule E)
- K1Engine: Partnership, S-Corp, C-Corp income
- BankStatementEngine: Bank statement analysis (Non-QM)
"""

from .w2_engine import W2Engine
from .schedule_c_engine import ScheduleCEngine
from .rental_engine import RentalEngine
from .k1_engine import K1Engine
from .bank_statement_engine import BankStatementEngine

__all__ = [
    "W2Engine",
    "ScheduleCEngine",
    "RentalEngine",
    "K1Engine",
    "BankStatementEngine",
]
