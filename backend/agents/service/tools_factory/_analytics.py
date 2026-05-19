"""Historical analytics tool wrappers (extracted verbatim)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_analytics_tools(db: Session, current_user: Any, ctx: Dict[str, Any]) -> Dict[str, Callable]:
    tools: Dict[str, Callable] = {}

    _ = (db, current_user, ctx)  # signature parity — these wrappers are stateless

    # ============ Historical Analytics Tools ============
    # Import and wrap the historical tools from the tools module

    from ..tools.historical import (
        get_performance_by_period as _get_performance_by_period,
        compare_periods as _compare_periods,
        get_data_availability as _get_data_availability,
    )

    async def execute_get_performance_by_period(args):
        """Get performance metrics for a specific time period."""
        period = args.get("period", "this month")
        lo_id = args.get("lo_id")
        try:
            result = _get_performance_by_period(period=period, lo_id=lo_id)
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in get_performance_by_period: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["get_performance_by_period"] = execute_get_performance_by_period

    async def execute_compare_periods(args):
        """Compare performance between two time periods."""
        period1 = args.get("period1", "last month")
        period2 = args.get("period2", "this month")
        lo_id = args.get("lo_id")
        try:
            result = _compare_periods(period1=period1, period2=period2, lo_id=lo_id)
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in compare_periods: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["compare_periods"] = execute_compare_periods

    async def execute_get_data_availability(args):
        """Get information about available historical data."""
        try:
            result = _get_data_availability()
            if hasattr(result, 'to_dict'):
                return result.to_dict()
            return result
        except Exception as e:
            logger.error(f"Error in get_data_availability: {e}")
            return {"status": "error", "error": "Internal server error"}

    tools["get_data_availability"] = execute_get_data_availability

    return tools
