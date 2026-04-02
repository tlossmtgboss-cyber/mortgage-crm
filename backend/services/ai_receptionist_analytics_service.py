"""
AI Receptionist Business Intelligence Analytics Service
========================================================
Provides advanced analytics for the AI Receptionist system:
- Conversion funnel tracking (Call → Booking → Application → Funded)
- ROI measurement and visibility
- Performance benchmarking against industry standards
- Trend analysis and forecasting
- Cost savings calculations

Expected ROI: 300-1,775% based on:
- Labor cost savings: $15-25/hr saved per call handled
- After-hours coverage: 40% of leads come outside business hours
- Speed-to-lead improvement: 5x faster response = 21x more conversions
"""

import os
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

class FunnelStage(str, Enum):
    CALL = "call"
    ENGAGED = "engaged"  # Meaningful conversation
    APPOINTMENT = "appointment"
    APPLICATION = "application"
    PROCESSING = "processing"
    APPROVED = "approved"
    FUNDED = "funded"


# Industry benchmarks for comparison
INDUSTRY_BENCHMARKS = {
    "call_to_appointment_rate": 0.15,  # 15% industry average
    "appointment_to_application_rate": 0.40,  # 40%
    "application_to_funded_rate": 0.65,  # 65%
    "avg_response_time_seconds": 300,  # 5 minutes
    "avg_call_duration_seconds": 180,  # 3 minutes
    "after_hours_coverage_rate": 0.40,  # 40% of leads come after hours
}

# Cost assumptions for ROI calculation
COST_ASSUMPTIONS = {
    "avg_hourly_labor_cost": 25.0,  # $25/hr for receptionist
    "avg_call_handle_time_minutes": 5,  # 5 minutes per call
    "missed_lead_cost": 500.0,  # Estimated cost of missing a lead
    "avg_loan_commission": 5000.0,  # Average commission per funded loan
    "ai_cost_per_call": 0.15,  # ~$0.15 per AI call (VAPI + LLM)
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ConversionFunnel:
    """Conversion funnel metrics."""
    period_start: date
    period_end: date
    total_calls: int = 0
    engaged_calls: int = 0
    appointments_scheduled: int = 0
    applications_started: int = 0
    applications_submitted: int = 0
    loans_approved: int = 0
    loans_funded: int = 0

    @property
    def call_to_engaged_rate(self) -> float:
        return self.engaged_calls / self.total_calls if self.total_calls > 0 else 0

    @property
    def call_to_appointment_rate(self) -> float:
        return self.appointments_scheduled / self.total_calls if self.total_calls > 0 else 0

    @property
    def appointment_to_application_rate(self) -> float:
        return self.applications_started / self.appointments_scheduled if self.appointments_scheduled > 0 else 0

    @property
    def application_to_funded_rate(self) -> float:
        return self.loans_funded / self.applications_submitted if self.applications_submitted > 0 else 0

    @property
    def overall_conversion_rate(self) -> float:
        return self.loans_funded / self.total_calls if self.total_calls > 0 else 0

    def to_dict(self) -> Dict:
        return {
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat()
            },
            "counts": {
                "total_calls": self.total_calls,
                "engaged_calls": self.engaged_calls,
                "appointments_scheduled": self.appointments_scheduled,
                "applications_started": self.applications_started,
                "applications_submitted": self.applications_submitted,
                "loans_approved": self.loans_approved,
                "loans_funded": self.loans_funded
            },
            "conversion_rates": {
                "call_to_engaged": round(self.call_to_engaged_rate * 100, 2),
                "call_to_appointment": round(self.call_to_appointment_rate * 100, 2),
                "appointment_to_application": round(self.appointment_to_application_rate * 100, 2),
                "application_to_funded": round(self.application_to_funded_rate * 100, 2),
                "overall_conversion": round(self.overall_conversion_rate * 100, 2)
            }
        }


@dataclass
class ROIMetrics:
    """ROI calculation metrics."""
    period_start: date
    period_end: date

    # Costs
    ai_calls_cost: float = 0
    platform_cost: float = 0  # Monthly VAPI/Telnyx cost
    total_cost: float = 0

    # Savings
    labor_hours_saved: float = 0
    labor_cost_saved: float = 0
    after_hours_leads_captured: int = 0
    after_hours_value: float = 0
    missed_leads_prevented: int = 0
    missed_lead_value_saved: float = 0

    # Revenue attribution
    appointments_from_ai: int = 0
    funded_loans_from_ai: int = 0
    revenue_attributed: float = 0

    @property
    def total_savings(self) -> float:
        return self.labor_cost_saved + self.after_hours_value + self.missed_lead_value_saved

    @property
    def total_value_generated(self) -> float:
        return self.total_savings + self.revenue_attributed

    @property
    def net_benefit(self) -> float:
        return self.total_value_generated - self.total_cost

    @property
    def roi_percentage(self) -> float:
        if self.total_cost == 0:
            return 0
        return ((self.total_value_generated - self.total_cost) / self.total_cost) * 100

    def to_dict(self) -> Dict:
        return {
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat()
            },
            "costs": {
                "ai_calls": round(self.ai_calls_cost, 2),
                "platform": round(self.platform_cost, 2),
                "total": round(self.total_cost, 2)
            },
            "savings": {
                "labor_hours_saved": round(self.labor_hours_saved, 1),
                "labor_cost_saved": round(self.labor_cost_saved, 2),
                "after_hours_leads": self.after_hours_leads_captured,
                "after_hours_value": round(self.after_hours_value, 2),
                "missed_leads_prevented": self.missed_leads_prevented,
                "missed_lead_value": round(self.missed_lead_value_saved, 2),
                "total_savings": round(self.total_savings, 2)
            },
            "revenue": {
                "appointments_from_ai": self.appointments_from_ai,
                "funded_loans_from_ai": self.funded_loans_from_ai,
                "revenue_attributed": round(self.revenue_attributed, 2)
            },
            "roi": {
                "total_value_generated": round(self.total_value_generated, 2),
                "net_benefit": round(self.net_benefit, 2),
                "roi_percentage": round(self.roi_percentage, 1)
            }
        }


@dataclass
class PerformanceBenchmark:
    """Performance benchmarking against industry standards."""
    metric_name: str
    current_value: float
    benchmark_value: float
    unit: str = ""
    higher_is_better: bool = True

    @property
    def performance_vs_benchmark(self) -> float:
        """Returns percentage above/below benchmark."""
        if self.benchmark_value == 0:
            return 0
        diff = (self.current_value - self.benchmark_value) / self.benchmark_value * 100
        return diff if self.higher_is_better else -diff

    @property
    def status(self) -> str:
        perf = self.performance_vs_benchmark
        if perf >= 20:
            return "excellent"
        elif perf >= 0:
            return "good"
        elif perf >= -20:
            return "needs_improvement"
        else:
            return "critical"

    def to_dict(self) -> Dict:
        return {
            "metric": self.metric_name,
            "current": round(self.current_value, 2),
            "benchmark": round(self.benchmark_value, 2),
            "unit": self.unit,
            "vs_benchmark_pct": round(self.performance_vs_benchmark, 1),
            "status": self.status
        }


# ============================================================================
# ANALYTICS SERVICE
# ============================================================================

class AIReceptionistAnalyticsService:
    """
    Business Intelligence analytics for AI Receptionist.

    Provides:
    - Conversion funnel tracking
    - ROI measurement
    - Performance benchmarking
    - Trend analysis
    """

    def __init__(self, db: Session, organization_id: int = None):
        self.db = db
        self.organization_id = organization_id

    # ========================================================================
    # CONVERSION FUNNEL
    # ========================================================================

    def get_conversion_funnel(
        self,
        start_date: date = None,
        end_date: date = None,
        user_id: int = None
    ) -> ConversionFunnel:
        """
        Get conversion funnel metrics for the specified period.

        Tracks: Call → Engaged → Appointment → Application → Funded
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        funnel = ConversionFunnel(period_start=start_date, period_end=end_date)

        # Build user filter
        user_filter = ""
        params = {"start_date": start_date, "end_date": end_date}
        if user_id:
            user_filter = "AND user_id = :user_id"
            params["user_id"] = user_id

        # Get call metrics from AI receptionist activities
        try:
            sql = """
                SELECT
                    COUNT(*) as total_calls,
                    COUNT(CASE WHEN outcome_status = 'engaged' OR outcome_status = 'completed' THEN 1 END) as engaged_calls,
                    COUNT(CASE WHEN action_type = 'appointment_scheduled' THEN 1 END) as appointments
                FROM ai_receptionist_activity
                WHERE DATE(timestamp) BETWEEN :start_date AND :end_date
            """
            if user_filter:
                sql += " " + user_filter
            calls_result = self.db.execute(text(sql), params).fetchone()

            if calls_result:
                funnel.total_calls = calls_result[0] or 0
                funnel.engaged_calls = calls_result[1] or 0
                funnel.appointments_scheduled = calls_result[2] or 0
        except SQLAlchemyError as e:
            logger.warning(f"Could not fetch AI receptionist activity: {e}")
            # Try alternative table
            try:
                calls_result = self.db.execute(text("""
                    SELECT
                        COUNT(*) as total_conversations
                    FROM ai_receptionist_conversations
                    WHERE DATE(started_at) BETWEEN :start_date AND :end_date
                """), params).fetchone()
                if calls_result:
                    funnel.total_calls = calls_result[0] or 0
            except Exception as e2:
                logger.warning(f"Could not fetch conversations: {e2}")

        # Get application and loan metrics
        try:
            loans_sql = """
                SELECT
                    COUNT(CASE WHEN source = 'ai_receptionist' OR source LIKE '%ai%' THEN 1 END) as ai_applications,
                    COUNT(CASE WHEN (source = 'ai_receptionist' OR source LIKE '%ai%') AND status = 'approved' THEN 1 END) as approved,
                    COUNT(CASE WHEN (source = 'ai_receptionist' OR source LIKE '%ai%') AND status = 'funded' THEN 1 END) as funded
                FROM loans
                WHERE DATE(created_at) BETWEEN :start_date AND :end_date
            """
            if user_filter:
                loans_sql += " " + user_filter.replace('user_id', 'loan_officer_id')
            loans_result = self.db.execute(text(loans_sql), params).fetchone()

            if loans_result:
                funnel.applications_submitted = loans_result[0] or 0
                funnel.applications_started = funnel.applications_submitted  # Simplification
                funnel.loans_approved = loans_result[1] or 0
                funnel.loans_funded = loans_result[2] or 0
        except SQLAlchemyError as e:
            logger.warning(f"Could not fetch loan metrics: {e}")

        return funnel

    def get_funnel_trend(
        self,
        days: int = 30,
        granularity: str = "day"  # day, week, month
    ) -> List[Dict]:
        """Get conversion funnel trend over time."""
        trends = []
        end_date = date.today()

        if granularity == "day":
            for i in range(days):
                d = end_date - timedelta(days=i)
                funnel = self.get_conversion_funnel(start_date=d, end_date=d)
                trends.append({
                    "date": d.isoformat(),
                    **funnel.to_dict()["counts"],
                    **funnel.to_dict()["conversion_rates"]
                })
        elif granularity == "week":
            for i in range(days // 7):
                week_end = end_date - timedelta(days=i*7)
                week_start = week_end - timedelta(days=6)
                funnel = self.get_conversion_funnel(start_date=week_start, end_date=week_end)
                trends.append({
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    **funnel.to_dict()["counts"],
                    **funnel.to_dict()["conversion_rates"]
                })

        return list(reversed(trends))

    # ========================================================================
    # ROI CALCULATION
    # ========================================================================

    def calculate_roi(
        self,
        start_date: date = None,
        end_date: date = None,
        platform_monthly_cost: float = 500.0
    ) -> ROIMetrics:
        """
        Calculate ROI for the AI Receptionist.

        ROI components:
        1. Labor cost savings (calls handled by AI vs human)
        2. After-hours lead capture value
        3. Missed lead prevention value
        4. Revenue attribution from AI-sourced loans
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        days_in_period = (end_date - start_date).days + 1

        roi = ROIMetrics(period_start=start_date, period_end=end_date)

        # Get call counts
        funnel = self.get_conversion_funnel(start_date, end_date)
        total_calls = funnel.total_calls

        # Calculate costs
        roi.ai_calls_cost = total_calls * COST_ASSUMPTIONS["ai_cost_per_call"]
        roi.platform_cost = platform_monthly_cost * (days_in_period / 30)
        roi.total_cost = roi.ai_calls_cost + roi.platform_cost

        # Calculate labor savings
        roi.labor_hours_saved = (total_calls * COST_ASSUMPTIONS["avg_call_handle_time_minutes"]) / 60
        roi.labor_cost_saved = roi.labor_hours_saved * COST_ASSUMPTIONS["avg_hourly_labor_cost"]

        # Estimate after-hours value
        # Assumption: 40% of calls are after hours, worth $500 each in lead value
        roi.after_hours_leads_captured = int(total_calls * INDUSTRY_BENCHMARKS["after_hours_coverage_rate"])
        roi.after_hours_value = roi.after_hours_leads_captured * COST_ASSUMPTIONS["missed_lead_cost"] * 0.3  # 30% would have been lost

        # Missed lead prevention
        # AI answers instantly; without AI, ~20% of calls would go to voicemail and be lost
        roi.missed_leads_prevented = int(total_calls * 0.2)
        roi.missed_lead_value_saved = roi.missed_leads_prevented * COST_ASSUMPTIONS["missed_lead_cost"]

        # Revenue attribution
        roi.appointments_from_ai = funnel.appointments_scheduled
        roi.funded_loans_from_ai = funnel.loans_funded
        roi.revenue_attributed = funnel.loans_funded * COST_ASSUMPTIONS["avg_loan_commission"]

        return roi

    def get_roi_trend(
        self,
        months: int = 6
    ) -> List[Dict]:
        """Get monthly ROI trend."""
        trends = []
        today = date.today()

        for i in range(months):
            month_end = (today.replace(day=1) - timedelta(days=i*30)).replace(day=1) - timedelta(days=1)
            month_start = month_end.replace(day=1)

            if month_end > today:
                month_end = today

            roi = self.calculate_roi(start_date=month_start, end_date=month_end)
            trends.append({
                "month": month_start.strftime("%Y-%m"),
                **roi.to_dict()
            })

        return list(reversed(trends))

    # ========================================================================
    # PERFORMANCE BENCHMARKING
    # ========================================================================

    def get_performance_benchmarks(
        self,
        start_date: date = None,
        end_date: date = None
    ) -> List[PerformanceBenchmark]:
        """
        Compare AI Receptionist performance against industry benchmarks.
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        benchmarks = []
        funnel = self.get_conversion_funnel(start_date, end_date)

        # Call to Appointment Rate
        benchmarks.append(PerformanceBenchmark(
            metric_name="Call to Appointment Rate",
            current_value=funnel.call_to_appointment_rate * 100,
            benchmark_value=INDUSTRY_BENCHMARKS["call_to_appointment_rate"] * 100,
            unit="%",
            higher_is_better=True
        ))

        # Application to Funded Rate
        benchmarks.append(PerformanceBenchmark(
            metric_name="Application to Funded Rate",
            current_value=funnel.application_to_funded_rate * 100,
            benchmark_value=INDUSTRY_BENCHMARKS["application_to_funded_rate"] * 100,
            unit="%",
            higher_is_better=True
        ))

        # Get response time metrics
        try:
            response_result = self.db.execute(text("""
                SELECT AVG(response_time_avg_seconds) as avg_response
                FROM ai_receptionist_metrics_daily
                WHERE date BETWEEN :start_date AND :end_date
            """), {"start_date": start_date, "end_date": end_date}).fetchone()

            if response_result and response_result[0]:
                benchmarks.append(PerformanceBenchmark(
                    metric_name="Average Response Time",
                    current_value=response_result[0],
                    benchmark_value=INDUSTRY_BENCHMARKS["avg_response_time_seconds"],
                    unit="seconds",
                    higher_is_better=False  # Lower is better
                ))
        except SQLAlchemyError as e:
            logger.warning(f"Could not fetch response time metrics: {e}")

        # After-hours coverage
        try:
            after_hours_result = self.db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN EXTRACT(HOUR FROM timestamp) < 9
                               OR EXTRACT(HOUR FROM timestamp) >= 17 THEN 1 END) as after_hours
                FROM ai_receptionist_activity
                WHERE DATE(timestamp) BETWEEN :start_date AND :end_date
            """), {"start_date": start_date, "end_date": end_date}).fetchone()

            if after_hours_result and after_hours_result[0]:
                coverage = (after_hours_result[1] or 0) / after_hours_result[0] * 100
                benchmarks.append(PerformanceBenchmark(
                    metric_name="After-Hours Coverage",
                    current_value=coverage,
                    benchmark_value=INDUSTRY_BENCHMARKS["after_hours_coverage_rate"] * 100,
                    unit="%",
                    higher_is_better=True
                ))
        except Exception as e:
            logger.warning(f"Could not fetch after-hours metrics: {e}")

        return benchmarks

    # ========================================================================
    # EXECUTIVE SUMMARY
    # ========================================================================

    def get_executive_summary(
        self,
        start_date: date = None,
        end_date: date = None
    ) -> Dict[str, Any]:
        """
        Get executive summary dashboard data.

        Returns comprehensive metrics suitable for C-level reporting.
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        funnel = self.get_conversion_funnel(start_date, end_date)
        roi = self.calculate_roi(start_date, end_date)
        benchmarks = self.get_performance_benchmarks(start_date, end_date)

        # Calculate comparison to previous period
        prev_start = start_date - timedelta(days=(end_date - start_date).days + 1)
        prev_end = start_date - timedelta(days=1)
        prev_funnel = self.get_conversion_funnel(prev_start, prev_end)
        prev_roi = self.calculate_roi(prev_start, prev_end)

        def calc_change(current, previous):
            if previous == 0:
                return 0
            return round(((current - previous) / previous) * 100, 1)

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "headline_metrics": {
                "total_calls_handled": {
                    "value": funnel.total_calls,
                    "change_pct": calc_change(funnel.total_calls, prev_funnel.total_calls)
                },
                "appointments_scheduled": {
                    "value": funnel.appointments_scheduled,
                    "change_pct": calc_change(funnel.appointments_scheduled, prev_funnel.appointments_scheduled)
                },
                "loans_funded": {
                    "value": funnel.loans_funded,
                    "change_pct": calc_change(funnel.loans_funded, prev_funnel.loans_funded)
                },
                "roi_percentage": {
                    "value": round(roi.roi_percentage, 1),
                    "change_pct": calc_change(roi.roi_percentage, prev_roi.roi_percentage)
                }
            },
            "financial_impact": {
                "total_cost": round(roi.total_cost, 2),
                "total_savings": round(roi.total_savings, 2),
                "revenue_attributed": round(roi.revenue_attributed, 2),
                "net_benefit": round(roi.net_benefit, 2)
            },
            "conversion_funnel": funnel.to_dict(),
            "roi_breakdown": roi.to_dict(),
            "benchmarks": [b.to_dict() for b in benchmarks],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
