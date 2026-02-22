"""
Accounting Routes Package.

This package contains all API routes for the accounting system.
"""

# ============================================================================
# FEATURE TIER: EXPERIMENTAL
# This module is in the experimental tier -- frozen, no SLA.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================

from .chart_of_accounts_routes import router as chart_of_accounts_router
from .journal_entry_routes import router as journal_entry_router
from .period_routes import router as period_router
from .ar_routes import router as ar_router
from .ap_routes import router as ap_router
from .reports_routes import router as reports_router
from .bank_routes import router as bank_router
from .budget_routes import router as budget_router

__all__ = [
    'chart_of_accounts_router',
    'journal_entry_router',
    'period_router',
    'ar_router',
    'ap_router',
    'reports_router',
    'bank_router',
    'budget_router',
]
