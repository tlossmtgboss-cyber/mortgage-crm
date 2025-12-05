"""
Perennia AI - Historical Performance Analysis Tools
Tools for analyzing performance across time periods (quarters, months, custom ranges).

These tools provide historical comparisons that become more valuable as data accumulates.
When insufficient data exists for a period, helpful messages guide users about data availability.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from calendar import monthrange
import re

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
    calculate_percentage_change,
)


# =============================================================================
# Period Parsing Utilities
# =============================================================================

def parse_period(period: str, year: Optional[int] = None) -> Tuple[date, date]:
    """
    Parse a period string into start and end dates.

    Supports:
        - Quarter: "Q1", "Q2", "Q3", "Q4", "Q1 2025", "Q4-2024"
        - Month: "January", "Jan", "January 2025", "Jan-2025", "2025-01"
        - Date range: "2025-01-01 to 2025-03-31"
        - Relative: "last month", "last quarter", "YTD", "last 30 days"

    Returns:
        Tuple of (start_date, end_date)
    """
    period_clean = period.strip().lower()
    current_year = year or datetime.now().year
    today = date.today()

    # Quarter patterns
    quarter_match = re.match(r'^q([1-4])(?:\s*[-\s]?\s*(\d{4}))?$', period_clean)
    if quarter_match:
        q = int(quarter_match.group(1))
        q_year = int(quarter_match.group(2)) if quarter_match.group(2) else current_year
        quarter_months = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
        start_month, end_month = quarter_months[q]
        start = date(q_year, start_month, 1)
        end = date(q_year, end_month, monthrange(q_year, end_month)[1])
        return (start, end)

    # Month names
    month_names = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6,
        'july': 7, 'jul': 7, 'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
    }

    # Month with optional year
    month_match = re.match(r'^([a-z]+)(?:\s*[-\s]?\s*(\d{4}))?$', period_clean)
    if month_match and month_match.group(1) in month_names:
        month = month_names[month_match.group(1)]
        m_year = int(month_match.group(2)) if month_match.group(2) else current_year
        start = date(m_year, month, 1)
        end = date(m_year, month, monthrange(m_year, month)[1])
        return (start, end)

    # ISO month format (2025-01)
    iso_month_match = re.match(r'^(\d{4})-(\d{2})$', period_clean)
    if iso_month_match:
        m_year = int(iso_month_match.group(1))
        month = int(iso_month_match.group(2))
        start = date(m_year, month, 1)
        end = date(m_year, month, monthrange(m_year, month)[1])
        return (start, end)

    # Date range (2025-01-01 to 2025-03-31)
    range_match = re.match(r'^(\d{4}-\d{2}-\d{2})\s*(?:to|-)\s*(\d{4}-\d{2}-\d{2})$', period_clean)
    if range_match:
        start = date.fromisoformat(range_match.group(1))
        end = date.fromisoformat(range_match.group(2))
        return (start, end)

    # Relative periods
    if period_clean in ['last month', 'previous month']:
        first_of_this_month = today.replace(day=1)
        end = first_of_this_month - timedelta(days=1)
        start = end.replace(day=1)
        return (start, end)

    if period_clean in ['last quarter', 'previous quarter']:
        current_quarter = (today.month - 1) // 3 + 1
        if current_quarter == 1:
            q_year, q = today.year - 1, 4
        else:
            q_year, q = today.year, current_quarter - 1
        quarter_months = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
        start_month, end_month = quarter_months[q]
        start = date(q_year, start_month, 1)
        end = date(q_year, end_month, monthrange(q_year, end_month)[1])
        return (start, end)

    if period_clean in ['ytd', 'year to date']:
        start = date(today.year, 1, 1)
        end = today
        return (start, end)

    # Last N days
    days_match = re.match(r'^last\s*(\d+)\s*days?$', period_clean)
    if days_match:
        days = int(days_match.group(1))
        end = today
        start = today - timedelta(days=days)
        return (start, end)

    # This month/quarter
    if period_clean in ['this month', 'current month']:
        start = today.replace(day=1)
        end = today
        return (start, end)

    if period_clean in ['this quarter', 'current quarter']:
        current_quarter = (today.month - 1) // 3 + 1
        quarter_months = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
        start_month, _ = quarter_months[current_quarter]
        start = date(today.year, start_month, 1)
        end = today
        return (start, end)

    raise ValueError(f"Could not parse period: '{period}'. "
                     f"Supported formats: Q1-Q4, month names, YYYY-MM, date ranges, "
                     f"'last month', 'last quarter', 'YTD', 'last N days'")


def get_period_label(start: date, end: date) -> str:
    """Generate a human-readable label for a date range."""
    # Check if it's a quarter
    if start.day == 1:
        quarter_starts = {1: 'Q1', 4: 'Q2', 7: 'Q3', 10: 'Q4'}
        if start.month in quarter_starts:
            q = quarter_starts[start.month]
            expected_end_month = start.month + 2
            if end.month == expected_end_month and end.day == monthrange(end.year, end.month)[1]:
                return f"{q} {start.year}"

    # Check if it's a full month
    if start.day == 1 and end.day == monthrange(end.year, end.month)[1] and start.month == end.month:
        return start.strftime("%B %Y")

    # Otherwise, show date range
    return f"{start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')}"


def get_data_date_range() -> Tuple[Optional[date], Optional[date]]:
    """Get the earliest and latest dates with data in the system."""
    # Check loans
    loan_range = execute_single("""
        SELECT
            MIN(COALESCE(funded_date, created_at))::date as earliest,
            MAX(COALESCE(funded_date, created_at))::date as latest
        FROM loans
    """)

    # Check leads
    lead_range = execute_single("""
        SELECT
            MIN(created_at)::date as earliest,
            MAX(created_at)::date as latest
        FROM leads
    """)

    earliest = None
    latest = None

    if loan_range and loan_range['earliest']:
        earliest = loan_range['earliest']
        latest = loan_range['latest']

    if lead_range and lead_range['earliest']:
        if earliest is None or lead_range['earliest'] < earliest:
            earliest = lead_range['earliest']
        if latest is None or lead_range['latest'] > latest:
            latest = lead_range['latest']

    return (earliest, latest)


# =============================================================================
# Historical Performance Tools
# =============================================================================

@mortgage_tool(
    name="get_performance_by_period",
    description="Get performance metrics for a specific time period (quarter, month, or date range). "
                "Returns loans funded, volume, leads created, and conversion rate. "
                "Provides helpful guidance when data is unavailable for requested periods.",
    agent_roles=["pipeline_analyst", "manager", "executive", "team_coach", "all"],
    risk_level="low",
    examples=[
        "How did Q3 perform?",
        "Show me October 2025 metrics",
        "What was our performance last quarter?",
        "Get metrics for Q4 2025",
        "Performance for January through March",
    ],
)
def get_performance_by_period(
    period: str,
    lo_id: Optional[int] = None,
) -> ToolResult:
    """
    Get performance metrics for a specific time period.

    Args:
        period: Time period to analyze. Supports:
            - Quarters: "Q1", "Q3 2025", "Q4-2024"
            - Months: "January", "Oct 2025", "2025-01"
            - Ranges: "2025-01-01 to 2025-03-31"
            - Relative: "last month", "last quarter", "YTD", "last 30 days"
        lo_id: Optional loan officer ID to filter by

    Returns:
        ToolResult with loans_funded, volume, leads_created, conversion_rate
        or helpful message if no data exists for the period.
    """
    try:
        # Parse the period
        try:
            start_date, end_date = parse_period(period)
        except ValueError as e:
            return ToolResult.error(str(e))

        period_label = get_period_label(start_date, end_date)

        # Get system data range
        earliest, latest = get_data_date_range()

        # Check if we have any data at all
        if earliest is None:
            return ToolResult.success(
                data={
                    "period": period_label,
                    "start_date": format_date(start_date),
                    "end_date": format_date(end_date),
                    "has_data": False,
                    "message": "No data available yet. Historical comparisons will be available once loans and leads are tracked in the system.",
                },
                message="No data available yet. Historical comparisons will be available once loans and leads are tracked in the system."
            )

        # Check if requested period has data
        if end_date < earliest:
            return ToolResult.success(
                data={
                    "period": period_label,
                    "start_date": format_date(start_date),
                    "end_date": format_date(end_date),
                    "has_data": False,
                    "data_available_from": format_date(earliest),
                    "data_available_to": format_date(latest),
                    "message": f"No data available for {period_label}. Your earliest data is from {earliest.strftime('%B %Y')}.",
                },
                message=f"No data available for {period_label}. Your earliest data is from {earliest.strftime('%B %Y')}."
            )

        if start_date > latest:
            return ToolResult.success(
                data={
                    "period": period_label,
                    "start_date": format_date(start_date),
                    "end_date": format_date(end_date),
                    "has_data": False,
                    "data_available_from": format_date(earliest),
                    "data_available_to": format_date(latest),
                    "message": f"No data available for {period_label} yet. Your most recent data is from {latest.strftime('%B %Y')}.",
                },
                message=f"No data available for {period_label} yet. Your most recent data is from {latest.strftime('%B %Y')}."
            )

        # Build filters
        lo_filter = "AND l.loan_officer_id = :lo_id" if lo_id else ""
        params = {
            "start_date": start_date,
            "end_date": end_date,
        }
        if lo_id:
            params["lo_id"] = lo_id

        # Get funded loans in period
        funded_query = f"""
            SELECT
                COUNT(*) as loans_funded,
                COALESCE(SUM(amount), 0) as volume,
                AVG(amount) as avg_loan_size,
                AVG(EXTRACT(EPOCH FROM (funded_date - created_at)) / 86400) as avg_cycle_time
            FROM loans l
            WHERE l.stage = 'Funded'
            AND l.funded_date >= :start_date
            AND l.funded_date <= :end_date
            {lo_filter}
        """
        funded_data = execute_single(funded_query, params)

        # Get all loans created in period (for pipeline activity)
        created_query = f"""
            SELECT
                COUNT(*) as loans_created,
                COALESCE(SUM(amount), 0) as pipeline_volume
            FROM loans l
            WHERE l.created_at >= :start_date
            AND l.created_at <= :end_date
            {lo_filter}
        """
        created_data = execute_single(created_query, params)

        # Get leads created in period
        lead_lo_filter = "AND assigned_to = :lo_id" if lo_id else ""
        leads_query = f"""
            SELECT
                COUNT(*) as leads_created,
                COUNT(CASE WHEN stage IN ('Application', 'Pre-Approved', 'Pre-Qualified') THEN 1 END) as leads_converted
            FROM leads
            WHERE created_at >= :start_date
            AND created_at <= :end_date
            {lead_lo_filter}
        """
        leads_data = execute_single(leads_query, params)

        # Calculate conversion rate
        loans_funded = funded_data['loans_funded'] or 0 if funded_data else 0
        leads_created = leads_data['leads_created'] or 0 if leads_data else 0
        leads_converted = leads_data['leads_converted'] or 0 if leads_data else 0

        # Conversion can be leads to application or leads to funded
        lead_conversion_rate = (leads_converted / leads_created * 100) if leads_created > 0 else 0

        # Check if we have partial data
        has_full_data = start_date >= earliest
        data_note = None
        if not has_full_data:
            data_note = f"Partial data: your records begin {earliest.strftime('%B %d, %Y')}"

        # Check if period is in the future or ongoing
        today = date.today()
        is_ongoing = start_date <= today <= end_date
        is_future = start_date > today

        if is_future:
            return ToolResult.success(
                data={
                    "period": period_label,
                    "start_date": format_date(start_date),
                    "end_date": format_date(end_date),
                    "has_data": False,
                    "message": f"{period_label} is in the future. No data available yet.",
                },
                message=f"{period_label} is in the future. No data available yet."
            )

        result_data = {
            "period": period_label,
            "start_date": format_date(start_date),
            "end_date": format_date(end_date),
            "has_data": True,
            "is_complete_period": not is_ongoing,
            "metrics": {
                "loans_funded": loans_funded,
                "volume": float(funded_data['volume'] or 0) if funded_data else 0,
                "volume_formatted": format_currency(funded_data['volume']) if funded_data else "$0.00",
                "avg_loan_size": float(funded_data['avg_loan_size'] or 0) if funded_data else 0,
                "avg_loan_size_formatted": format_currency(funded_data['avg_loan_size']) if funded_data else "$0.00",
                "avg_cycle_time_days": round(funded_data['avg_cycle_time'] or 0, 1) if funded_data else 0,
                "loans_created": created_data['loans_created'] or 0 if created_data else 0,
                "pipeline_volume": float(created_data['pipeline_volume'] or 0) if created_data else 0,
                "pipeline_volume_formatted": format_currency(created_data['pipeline_volume']) if created_data else "$0.00",
                "leads_created": leads_created,
                "leads_converted": leads_converted,
                "lead_conversion_rate": round(lead_conversion_rate, 1),
            },
            "data_availability": {
                "earliest_data": format_date(earliest),
                "latest_data": format_date(latest),
                "has_full_period_data": has_full_data,
            },
        }

        if data_note:
            result_data["data_note"] = data_note

        if is_ongoing:
            result_data["note"] = f"Period is ongoing. Data through {today.strftime('%B %d, %Y')}."

        # Build summary message
        summary = f"{period_label}: {loans_funded} loans funded, {format_currency(funded_data['volume'] if funded_data else 0)}"
        if leads_created > 0:
            summary += f", {leads_created} leads ({lead_conversion_rate:.1f}% conversion)"

        return ToolResult.success(
            data=result_data,
            message=summary
        )

    except Exception as e:
        return ToolResult.error(f"Failed to get performance for period: {str(e)}")


@mortgage_tool(
    name="compare_periods",
    description="Compare performance between two time periods (e.g., Q3 vs Q4, October vs November). "
                "Shows changes in key metrics with percentage differences. "
                "Provides helpful guidance when insufficient data exists for comparison.",
    agent_roles=["pipeline_analyst", "manager", "executive", "team_coach", "all"],
    risk_level="low",
    examples=[
        "Compare Q3 to Q4",
        "How does October compare to November?",
        "Compare last quarter to this quarter",
        "Q4 2024 vs Q4 2025",
        "Compare this month to last month",
    ],
)
def compare_periods(
    period1: str,
    period2: str,
    lo_id: Optional[int] = None,
) -> ToolResult:
    """
    Compare performance metrics between two time periods.

    Args:
        period1: First (baseline) period for comparison
        period2: Second (comparison) period
        lo_id: Optional loan officer ID to filter by

    Returns:
        ToolResult with side-by-side comparison and percentage changes.
    """
    try:
        # Parse both periods
        try:
            start1, end1 = parse_period(period1)
            start2, end2 = parse_period(period2)
        except ValueError as e:
            return ToolResult.error(str(e))

        label1 = get_period_label(start1, end1)
        label2 = get_period_label(start2, end2)

        # Get system data range
        earliest, latest = get_data_date_range()

        if earliest is None:
            return ToolResult.success(
                data={
                    "period1": label1,
                    "period2": label2,
                    "has_data": False,
                    "message": "Historical comparisons will be available once you have data spanning multiple periods. No data has been recorded yet.",
                },
                message="Historical comparisons will be available once you have data spanning multiple periods. No data has been recorded yet."
            )

        # Check data availability for each period
        period1_has_data = not (end1 < earliest or start1 > latest)
        period2_has_data = not (end2 < earliest or start2 > latest)

        if not period1_has_data and not period2_has_data:
            return ToolResult.success(
                data={
                    "period1": label1,
                    "period2": label2,
                    "has_data": False,
                    "data_available_from": format_date(earliest),
                    "data_available_to": format_date(latest),
                    "message": f"No data available for either {label1} or {label2}. "
                               f"Your data spans {earliest.strftime('%B %Y')} to {latest.strftime('%B %Y')}.",
                },
                message=f"No data available for either period. Your data spans {earliest.strftime('%B %Y')} to {latest.strftime('%B %Y')}."
            )

        if not period1_has_data:
            return ToolResult.success(
                data={
                    "period1": label1,
                    "period2": label2,
                    "has_data": False,
                    "data_available_from": format_date(earliest),
                    "message": f"No data available for {label1}. Your earliest data is from {earliest.strftime('%B %Y')}.",
                },
                message=f"No data available for {label1}. Your earliest data is from {earliest.strftime('%B %Y')}."
            )

        if not period2_has_data:
            return ToolResult.success(
                data={
                    "period1": label1,
                    "period2": label2,
                    "has_data": False,
                    "data_available_to": format_date(latest),
                    "message": f"No data available for {label2}. Your most recent data is from {latest.strftime('%B %Y')}.",
                },
                message=f"No data available for {label2}. Your most recent data is from {latest.strftime('%B %Y')}."
            )

        # Helper to get metrics for a period
        def get_period_metrics(start: date, end: date) -> Dict[str, Any]:
            lo_filter = "AND l.loan_officer_id = :lo_id" if lo_id else ""
            params = {"start_date": start, "end_date": end}
            if lo_id:
                params["lo_id"] = lo_id

            funded = execute_single(f"""
                SELECT
                    COUNT(*) as loans_funded,
                    COALESCE(SUM(amount), 0) as volume,
                    AVG(amount) as avg_loan_size,
                    AVG(EXTRACT(EPOCH FROM (funded_date - created_at)) / 86400) as avg_cycle_time
                FROM loans l
                WHERE l.stage = 'Funded'
                AND l.funded_date >= :start_date AND l.funded_date <= :end_date
                {lo_filter}
            """, params)

            created = execute_single(f"""
                SELECT COUNT(*) as loans_created
                FROM loans l
                WHERE l.created_at >= :start_date AND l.created_at <= :end_date
                {lo_filter}
            """, params)

            lead_filter = "AND assigned_to = :lo_id" if lo_id else ""
            leads = execute_single(f"""
                SELECT
                    COUNT(*) as leads_created,
                    COUNT(CASE WHEN stage IN ('Application', 'Pre-Approved', 'Pre-Qualified') THEN 1 END) as leads_converted
                FROM leads
                WHERE created_at >= :start_date AND created_at <= :end_date
                {lead_filter}
            """, params)

            loans_funded = funded['loans_funded'] or 0 if funded else 0
            volume = float(funded['volume'] or 0) if funded else 0
            leads_created = leads['leads_created'] or 0 if leads else 0
            leads_converted = leads['leads_converted'] or 0 if leads else 0
            conversion_rate = (leads_converted / leads_created * 100) if leads_created > 0 else 0

            return {
                "loans_funded": loans_funded,
                "volume": volume,
                "avg_loan_size": float(funded['avg_loan_size'] or 0) if funded else 0,
                "avg_cycle_time": round(funded['avg_cycle_time'] or 0, 1) if funded else 0,
                "loans_created": created['loans_created'] or 0 if created else 0,
                "leads_created": leads_created,
                "leads_converted": leads_converted,
                "conversion_rate": round(conversion_rate, 1),
            }

        # Get metrics for both periods
        metrics1 = get_period_metrics(start1, end1)
        metrics2 = get_period_metrics(start2, end2)

        # Calculate changes
        def calc_change(old_val: float, new_val: float) -> Dict[str, Any]:
            if old_val == 0 and new_val == 0:
                return {"absolute": 0, "percentage": 0, "direction": "unchanged"}
            if old_val == 0:
                return {"absolute": new_val, "percentage": 100.0, "direction": "up"}

            abs_change = new_val - old_val
            pct_change = calculate_percentage_change(old_val, new_val)
            direction = "up" if abs_change > 0 else "down" if abs_change < 0 else "unchanged"

            return {
                "absolute": abs_change,
                "percentage": round(pct_change, 1),
                "direction": direction,
            }

        changes = {
            "loans_funded": calc_change(metrics1["loans_funded"], metrics2["loans_funded"]),
            "volume": calc_change(metrics1["volume"], metrics2["volume"]),
            "avg_loan_size": calc_change(metrics1["avg_loan_size"], metrics2["avg_loan_size"]),
            "leads_created": calc_change(metrics1["leads_created"], metrics2["leads_created"]),
            "conversion_rate": calc_change(metrics1["conversion_rate"], metrics2["conversion_rate"]),
        }

        # Check if we have enough data for meaningful comparison
        total_activity_p1 = metrics1["loans_funded"] + metrics1["leads_created"]
        total_activity_p2 = metrics2["loans_funded"] + metrics2["leads_created"]

        data_quality_note = None
        if total_activity_p1 == 0 and total_activity_p2 == 0:
            data_quality_note = "No loan or lead activity recorded in either period."
        elif total_activity_p1 == 0:
            data_quality_note = f"No activity recorded in {label1}. Comparison may not be meaningful."
        elif total_activity_p2 == 0:
            data_quality_note = f"No activity recorded in {label2}. Comparison may not be meaningful."
        elif start1 < earliest:
            data_quality_note = f"Partial data for {label1}: records begin {earliest.strftime('%B %d, %Y')}."

        # Build result
        result_data = {
            "comparison": f"{label1} vs {label2}",
            "has_data": True,
            "period1": {
                "label": label1,
                "start_date": format_date(start1),
                "end_date": format_date(end1),
                "metrics": {
                    **metrics1,
                    "volume_formatted": format_currency(metrics1["volume"]),
                    "avg_loan_size_formatted": format_currency(metrics1["avg_loan_size"]),
                },
            },
            "period2": {
                "label": label2,
                "start_date": format_date(start2),
                "end_date": format_date(end2),
                "metrics": {
                    **metrics2,
                    "volume_formatted": format_currency(metrics2["volume"]),
                    "avg_loan_size_formatted": format_currency(metrics2["avg_loan_size"]),
                },
            },
            "changes": changes,
            "summary": {
                "volume_change": f"{changes['volume']['direction']} {abs(changes['volume']['percentage']):.1f}%",
                "loans_change": f"{changes['loans_funded']['direction']} {abs(changes['loans_funded']['percentage']):.1f}%",
                "leads_change": f"{changes['leads_created']['direction']} {abs(changes['leads_created']['percentage']):.1f}%",
            },
            "data_availability": {
                "earliest_data": format_date(earliest),
                "latest_data": format_date(latest),
            },
        }

        if data_quality_note:
            result_data["data_quality_note"] = data_quality_note

        # Build summary message
        volume_direction = "↑" if changes['volume']['direction'] == 'up' else "↓" if changes['volume']['direction'] == 'down' else "→"
        summary = (f"{label1} → {label2}: "
                   f"Volume {volume_direction} {abs(changes['volume']['percentage']):.1f}% "
                   f"({format_currency(metrics1['volume'])} → {format_currency(metrics2['volume'])})")

        return ToolResult.success(
            data=result_data,
            message=summary
        )

    except Exception as e:
        return ToolResult.error(f"Failed to compare periods: {str(e)}")


@mortgage_tool(
    name="get_data_availability",
    description="Check what date ranges have data available for historical analysis. "
                "Useful for understanding what comparisons are possible.",
    agent_roles=["pipeline_analyst", "manager", "executive", "all"],
    risk_level="low",
    examples=[
        "What data do we have?",
        "When does our data start?",
        "What periods can I compare?",
    ],
)
def get_data_availability() -> ToolResult:
    """
    Get information about data availability for historical analysis.

    Returns:
        ToolResult with date ranges, data completeness, and available comparison options.
    """
    try:
        earliest, latest = get_data_date_range()

        if earliest is None:
            return ToolResult.success(
                data={
                    "has_data": False,
                    "message": "No data available yet. Historical comparisons will be available once loans and leads are tracked in the system.",
                    "tracking_since": None,
                },
                message="No data available yet. Historical comparisons will be available once loans and leads are tracked in the system."
            )

        today = date.today()
        days_of_data = (latest - earliest).days + 1

        # Check what we have data for
        loan_count = execute_single("SELECT COUNT(*) as count FROM loans")
        lead_count = execute_single("SELECT COUNT(*) as count FROM leads")
        funded_count = execute_single("SELECT COUNT(*) as count FROM loans WHERE stage = 'Funded'")

        # Determine available comparison options
        available_comparisons = []

        # Check for month-over-month
        if days_of_data >= 60:
            available_comparisons.append("month-over-month")

        # Check for quarter-over-quarter
        if days_of_data >= 180:
            available_comparisons.append("quarter-over-quarter")

        # Check for year-over-year
        if days_of_data >= 365:
            available_comparisons.append("year-over-year")

        # Months with data
        months_query = execute_query("""
            SELECT DISTINCT
                DATE_TRUNC('month', COALESCE(funded_date, created_at))::date as month
            FROM loans
            WHERE COALESCE(funded_date, created_at) IS NOT NULL
            ORDER BY month
        """)
        months_with_data = [row['month'].strftime('%B %Y') for row in months_query if row['month']]

        # Quarters with data
        quarters_with_data = []
        for row in months_query:
            if row['month']:
                q = (row['month'].month - 1) // 3 + 1
                quarter_label = f"Q{q} {row['month'].year}"
                if quarter_label not in quarters_with_data:
                    quarters_with_data.append(quarter_label)

        result_data = {
            "has_data": True,
            "tracking_since": format_date(earliest),
            "most_recent_data": format_date(latest),
            "days_of_data": days_of_data,
            "data_summary": {
                "total_loans": loan_count['count'] if loan_count else 0,
                "funded_loans": funded_count['count'] if funded_count else 0,
                "total_leads": lead_count['count'] if lead_count else 0,
            },
            "available_comparisons": available_comparisons if available_comparisons else ["none yet - need more data"],
            "months_with_data": months_with_data,
            "quarters_with_data": quarters_with_data,
        }

        if not available_comparisons:
            result_data["note"] = (
                f"Historical comparisons will be available once you have data spanning multiple periods. "
                f"Currently tracking since {earliest.strftime('%B %Y')}."
            )

        summary = f"Data available from {earliest.strftime('%B %Y')} to {latest.strftime('%B %Y')} ({days_of_data} days)"

        return ToolResult.success(
            data=result_data,
            message=summary
        )

    except Exception as e:
        return ToolResult.error(f"Failed to get data availability: {str(e)}")
