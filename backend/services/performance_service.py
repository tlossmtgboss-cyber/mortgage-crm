"""
Performance Service
Calculate and track performance metrics for the Master Manager Platform.

Handles daily, weekly, and monthly performance calculations with:
- Volume metrics (files funded, leads converted, tasks completed)
- Quality metrics (error rate, rework rate)
- Efficiency metrics (cycle time, SLA compliance)
- Composite scoring and grading (A-F)
- Trend analysis and benchmarking
"""

from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from dataclasses import dataclass
from enum import Enum
import logging

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class PerformanceGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class TrendDirection(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class PeriodType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass
class PerformanceMetrics:
    """Performance metrics for a user over a period."""
    user_id: int
    user_name: str
    period_start: date
    period_end: date
    period_type: str

    # Volume
    files_in_pipeline: int
    files_funded: int
    files_cancelled: int
    leads_handled: int
    leads_converted: int
    tasks_completed: int
    tasks_overdue: int

    # Quality
    error_count: int
    error_rate_pct: float
    rework_count: int
    rework_rate_pct: float

    # Efficiency
    avg_task_duration_mins: float
    avg_file_cycle_time_days: float
    sla_compliance_pct: float
    on_time_completion_pct: float

    # Composite
    overall_score: float
    performance_grade: str

    # Benchmarks
    vs_team_avg_pct: float
    percentile_rank: int

    # Trend
    trend_direction: str
    trend_change_pct: float


# =============================================================================
# WEIGHT CONFIGURATION
# =============================================================================

# Weights for calculating overall performance score (must sum to 1.0)
PERFORMANCE_WEIGHTS = {
    "volume": 0.30,       # Files funded, leads converted
    "quality": 0.25,      # Error rate, rework rate
    "efficiency": 0.25,   # Cycle time, SLA compliance
    "timeliness": 0.20,   # On-time completion, task duration
}

# Scoring thresholds for grade calculation
GRADE_THRESHOLDS = {
    "A": 90,
    "B": 80,
    "C": 70,
    "D": 60,
    "F": 0,
}


class PerformanceService:
    """
    Service for calculating and managing performance metrics.
    """

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # DAILY PERFORMANCE CALCULATION
    # =========================================================================

    async def calculate_daily_performance(
        self,
        user_id: int,
        target_date: date,
        organization_id: Optional[int] = None
    ) -> PerformanceMetrics:
        """
        Calculate daily performance snapshot for a user.
        This aggregates all activity for a single day.
        """
        # Get user info
        user_query = text("""
            SELECT id, full_name, organization_id
            FROM users
            WHERE id = :user_id
        """)
        user = self.db.execute(user_query, {"user_id": user_id}).fetchone()

        if not user:
            raise ValueError(f"User {user_id} not found")

        org_id = organization_id or user.organization_id

        # Volume metrics for the day
        volume = await self._get_daily_volume_metrics(user_id, target_date)

        # Quality metrics
        quality = await self._get_daily_quality_metrics(user_id, target_date)

        # Efficiency metrics
        efficiency = await self._get_daily_efficiency_metrics(user_id, target_date)

        # Calculate composite score
        overall_score = self._calculate_composite_score(volume, quality, efficiency)
        grade = self._calculate_grade(overall_score)

        # Get benchmark comparison
        team_avg = await self._get_team_average_score(org_id, target_date, "daily")
        vs_team = ((overall_score - team_avg) / max(team_avg, 1)) * 100 if team_avg > 0 else 0

        # Get percentile rank
        percentile = await self._get_percentile_rank(user_id, overall_score, org_id, "daily")

        # Get trend (compare to previous day)
        prev_perf = await self._get_previous_performance(user_id, target_date, "daily")
        trend_direction, trend_change = self._calculate_trend(overall_score, prev_perf)

        metrics = PerformanceMetrics(
            user_id=user_id,
            user_name=user.full_name or "Unknown",
            period_start=target_date,
            period_end=target_date,
            period_type=PeriodType.DAILY.value,
            files_in_pipeline=volume.get("files_in_pipeline", 0),
            files_funded=volume.get("files_funded", 0),
            files_cancelled=volume.get("files_cancelled", 0),
            leads_handled=volume.get("leads_handled", 0),
            leads_converted=volume.get("leads_converted", 0),
            tasks_completed=volume.get("tasks_completed", 0),
            tasks_overdue=volume.get("tasks_overdue", 0),
            error_count=quality.get("error_count", 0),
            error_rate_pct=quality.get("error_rate_pct", 0.0),
            rework_count=quality.get("rework_count", 0),
            rework_rate_pct=quality.get("rework_rate_pct", 0.0),
            avg_task_duration_mins=efficiency.get("avg_task_duration_mins", 0.0),
            avg_file_cycle_time_days=efficiency.get("avg_file_cycle_time_days", 0.0),
            sla_compliance_pct=efficiency.get("sla_compliance_pct", 100.0),
            on_time_completion_pct=efficiency.get("on_time_completion_pct", 100.0),
            overall_score=overall_score,
            performance_grade=grade,
            vs_team_avg_pct=round(vs_team, 1),
            percentile_rank=percentile,
            trend_direction=trend_direction,
            trend_change_pct=round(trend_change, 1)
        )

        # Save to database
        await self._save_performance_record(metrics, org_id)

        return metrics

    async def _get_daily_volume_metrics(
        self,
        user_id: int,
        target_date: date
    ) -> Dict[str, Any]:
        """Get volume metrics for a specific day."""
        # Files in pipeline (as of that day)
        pipeline_query = text("""
            SELECT COUNT(*) as count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND created_at::date <= :target_date
            AND (funded_at IS NULL OR funded_at::date > :target_date)
            AND status NOT IN ('cancelled', 'denied', 'withdrawn')
        """)
        pipeline = self.db.execute(pipeline_query, {
            "user_id": user_id,
            "target_date": target_date
        }).fetchone()

        # Files funded that day
        funded_query = text("""
            SELECT COUNT(*) as count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND funded_at::date = :target_date
        """)
        funded = self.db.execute(funded_query, {
            "user_id": user_id,
            "target_date": target_date
        }).fetchone()

        # Files cancelled that day
        cancelled_query = text("""
            SELECT COUNT(*) as count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND status IN ('cancelled', 'denied', 'withdrawn')
            AND updated_at::date = :target_date
        """)
        cancelled = self.db.execute(cancelled_query, {
            "user_id": user_id,
            "target_date": target_date
        }).fetchone()

        # Leads handled (activities on that day)
        leads_query = text("""
            SELECT
                COUNT(DISTINCT l.id) as handled,
                COUNT(DISTINCT CASE WHEN l.status = 'converted' AND l.updated_at::date = :target_date THEN l.id END) as converted
            FROM leads l
            LEFT JOIN activities a ON a.lead_id = l.id AND a.created_at::date = :target_date
            WHERE l.owner_id = :user_id
            AND (a.id IS NOT NULL OR l.updated_at::date = :target_date)
        """)
        leads = self.db.execute(leads_query, {
            "user_id": user_id,
            "target_date": target_date
        }).fetchone()

        # Tasks completed that day
        tasks_query = text("""
            SELECT
                COUNT(CASE WHEN status = 'completed' AND completed_at::date = :target_date THEN 1 END) as completed,
                COUNT(CASE WHEN status != 'completed' AND due_date < :target_date THEN 1 END) as overdue
            FROM tasks
            WHERE owner_id = :user_id
        """)
        tasks = self.db.execute(tasks_query, {
            "user_id": user_id,
            "target_date": target_date
        }).fetchone()

        return {
            "files_in_pipeline": pipeline.count if pipeline else 0,
            "files_funded": funded.count if funded else 0,
            "files_cancelled": cancelled.count if cancelled else 0,
            "leads_handled": leads.handled if leads else 0,
            "leads_converted": leads.converted if leads else 0,
            "tasks_completed": tasks.completed if tasks else 0,
            "tasks_overdue": tasks.overdue if tasks else 0,
        }

    async def _get_daily_quality_metrics(
        self,
        user_id: int,
        target_date: date
    ) -> Dict[str, Any]:
        """Get quality metrics for a specific day."""
        # Count errors (from a quality_issues or errors table if exists, otherwise estimate)
        # For now, we'll derive from rework/revision counts
        errors_query = text("""
            SELECT
                COUNT(*) as error_count,
                SUM(CASE WHEN revision_count > 1 THEN 1 ELSE 0 END) as rework_count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND updated_at::date = :target_date
        """)

        try:
            errors = self.db.execute(errors_query, {
                "user_id": user_id,
                "target_date": target_date
            }).fetchone()

            total_files = errors.error_count or 1
            error_count = errors.rework_count or 0
            rework_count = errors.rework_count or 0
        except Exception as e:
            logger.warning(f"Error querying quality metrics in _get_daily_quality_metrics: {e}")
            total_files = 1
            error_count = 0
            rework_count = 0

        return {
            "error_count": error_count,
            "error_rate_pct": round((error_count / max(total_files, 1)) * 100, 2),
            "rework_count": rework_count,
            "rework_rate_pct": round((rework_count / max(total_files, 1)) * 100, 2),
        }

    async def _get_daily_efficiency_metrics(
        self,
        user_id: int,
        target_date: date
    ) -> Dict[str, Any]:
        """Get efficiency metrics for a specific day."""
        # Average task duration
        task_duration_query = text("""
            SELECT AVG(
                EXTRACT(EPOCH FROM (completed_at - created_at)) / 60
            ) as avg_duration_mins
            FROM tasks
            WHERE owner_id = :user_id
            AND completed_at::date = :target_date
            AND completed_at IS NOT NULL
        """)
        task_dur = self.db.execute(task_duration_query, {
            "user_id": user_id,
            "target_date": target_date
        }).fetchone()

        # SLA compliance (tasks completed on time)
        sla_query = text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN completed_at <= due_date OR due_date IS NULL THEN 1 END) as on_time
            FROM tasks
            WHERE owner_id = :user_id
            AND completed_at::date = :target_date
        """)
        sla = self.db.execute(sla_query, {
            "user_id": user_id,
            "target_date": target_date
        }).fetchone()

        # File cycle time (for files that closed that day)
        cycle_query = text("""
            SELECT AVG(
                EXTRACT(EPOCH FROM (funded_at - created_at)) / 86400
            ) as avg_cycle_days
            FROM loans
            WHERE loan_officer_id = :user_id
            AND funded_at::date = :target_date
        """)
        cycle = self.db.execute(cycle_query, {
            "user_id": user_id,
            "target_date": target_date
        }).fetchone()

        total_tasks = sla.total if sla else 0
        on_time_tasks = sla.on_time if sla else 0
        sla_pct = (on_time_tasks / max(total_tasks, 1)) * 100

        return {
            "avg_task_duration_mins": round(task_dur.avg_duration_mins or 0, 1),
            "avg_file_cycle_time_days": round(cycle.avg_cycle_days or 0, 1),
            "sla_compliance_pct": round(sla_pct, 1),
            "on_time_completion_pct": round(sla_pct, 1),  # Same as SLA for now
        }

    # =========================================================================
    # WEEKLY/MONTHLY ROLLUPS
    # =========================================================================

    async def calculate_weekly_performance(
        self,
        user_id: int,
        week_start: date,
        organization_id: Optional[int] = None
    ) -> PerformanceMetrics:
        """
        Calculate weekly performance by rolling up daily metrics.
        week_start should be a Monday.
        """
        week_end = week_start + timedelta(days=6)

        return await self._calculate_period_performance(
            user_id=user_id,
            period_start=week_start,
            period_end=week_end,
            period_type=PeriodType.WEEKLY.value,
            organization_id=organization_id
        )

    async def calculate_monthly_performance(
        self,
        user_id: int,
        month_start: date,
        organization_id: Optional[int] = None
    ) -> PerformanceMetrics:
        """
        Calculate monthly performance by rolling up daily/weekly metrics.
        month_start should be the 1st of the month.
        """
        # Calculate end of month
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)

        return await self._calculate_period_performance(
            user_id=user_id,
            period_start=month_start,
            period_end=month_end,
            period_type=PeriodType.MONTHLY.value,
            organization_id=organization_id
        )

    async def _calculate_period_performance(
        self,
        user_id: int,
        period_start: date,
        period_end: date,
        period_type: str,
        organization_id: Optional[int] = None
    ) -> PerformanceMetrics:
        """Calculate performance for any period by aggregating data."""
        # Get user info
        user_query = text("""
            SELECT id, full_name, organization_id
            FROM users
            WHERE id = :user_id
        """)
        user = self.db.execute(user_query, {"user_id": user_id}).fetchone()

        if not user:
            raise ValueError(f"User {user_id} not found")

        org_id = organization_id or user.organization_id

        # Aggregate volume metrics for the period
        volume = await self._get_period_volume_metrics(user_id, period_start, period_end)

        # Aggregate quality metrics
        quality = await self._get_period_quality_metrics(user_id, period_start, period_end)

        # Aggregate efficiency metrics
        efficiency = await self._get_period_efficiency_metrics(user_id, period_start, period_end)

        # Calculate composite score
        overall_score = self._calculate_composite_score(volume, quality, efficiency)
        grade = self._calculate_grade(overall_score)

        # Get benchmark comparison
        team_avg = await self._get_team_average_score(org_id, period_start, period_type)
        vs_team = ((overall_score - team_avg) / max(team_avg, 1)) * 100 if team_avg > 0 else 0

        # Get percentile rank
        percentile = await self._get_percentile_rank(user_id, overall_score, org_id, period_type)

        # Get trend
        prev_perf = await self._get_previous_performance(user_id, period_start, period_type)
        trend_direction, trend_change = self._calculate_trend(overall_score, prev_perf)

        metrics = PerformanceMetrics(
            user_id=user_id,
            user_name=user.full_name or "Unknown",
            period_start=period_start,
            period_end=period_end,
            period_type=period_type,
            files_in_pipeline=volume.get("files_in_pipeline", 0),
            files_funded=volume.get("files_funded", 0),
            files_cancelled=volume.get("files_cancelled", 0),
            leads_handled=volume.get("leads_handled", 0),
            leads_converted=volume.get("leads_converted", 0),
            tasks_completed=volume.get("tasks_completed", 0),
            tasks_overdue=volume.get("tasks_overdue", 0),
            error_count=quality.get("error_count", 0),
            error_rate_pct=quality.get("error_rate_pct", 0.0),
            rework_count=quality.get("rework_count", 0),
            rework_rate_pct=quality.get("rework_rate_pct", 0.0),
            avg_task_duration_mins=efficiency.get("avg_task_duration_mins", 0.0),
            avg_file_cycle_time_days=efficiency.get("avg_file_cycle_time_days", 0.0),
            sla_compliance_pct=efficiency.get("sla_compliance_pct", 100.0),
            on_time_completion_pct=efficiency.get("on_time_completion_pct", 100.0),
            overall_score=overall_score,
            performance_grade=grade,
            vs_team_avg_pct=round(vs_team, 1),
            percentile_rank=percentile,
            trend_direction=trend_direction,
            trend_change_pct=round(trend_change, 1)
        )

        # Save to database
        await self._save_performance_record(metrics, org_id)

        return metrics

    async def _get_period_volume_metrics(
        self,
        user_id: int,
        period_start: date,
        period_end: date
    ) -> Dict[str, Any]:
        """Get volume metrics for a date range."""
        # Files funded in period
        funded_query = text("""
            SELECT COUNT(*) as count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND funded_at::date BETWEEN :start_date AND :end_date
        """)
        funded = self.db.execute(funded_query, {
            "user_id": user_id,
            "start_date": period_start,
            "end_date": period_end
        }).fetchone()

        # Files in pipeline (at end of period)
        pipeline_query = text("""
            SELECT COUNT(*) as count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND created_at::date <= :end_date
            AND (funded_at IS NULL OR funded_at::date > :end_date)
            AND status NOT IN ('cancelled', 'denied', 'withdrawn')
        """)
        pipeline = self.db.execute(pipeline_query, {
            "user_id": user_id,
            "end_date": period_end
        }).fetchone()

        # Leads
        leads_query = text("""
            SELECT
                COUNT(DISTINCT l.id) as handled,
                COUNT(DISTINCT CASE WHEN l.status = 'converted' AND l.updated_at::date BETWEEN :start_date AND :end_date THEN l.id END) as converted
            FROM leads l
            WHERE l.owner_id = :user_id
            AND l.updated_at::date BETWEEN :start_date AND :end_date
        """)
        leads = self.db.execute(leads_query, {
            "user_id": user_id,
            "start_date": period_start,
            "end_date": period_end
        }).fetchone()

        # Tasks
        tasks_query = text("""
            SELECT
                COUNT(CASE WHEN status = 'completed' AND completed_at::date BETWEEN :start_date AND :end_date THEN 1 END) as completed,
                COUNT(CASE WHEN status != 'completed' AND due_date BETWEEN :start_date AND :end_date THEN 1 END) as overdue
            FROM tasks
            WHERE owner_id = :user_id
        """)
        tasks = self.db.execute(tasks_query, {
            "user_id": user_id,
            "start_date": period_start,
            "end_date": period_end
        }).fetchone()

        # Cancelled
        cancelled_query = text("""
            SELECT COUNT(*) as count
            FROM loans
            WHERE loan_officer_id = :user_id
            AND status IN ('cancelled', 'denied', 'withdrawn')
            AND updated_at::date BETWEEN :start_date AND :end_date
        """)
        cancelled = self.db.execute(cancelled_query, {
            "user_id": user_id,
            "start_date": period_start,
            "end_date": period_end
        }).fetchone()

        return {
            "files_in_pipeline": pipeline.count if pipeline else 0,
            "files_funded": funded.count if funded else 0,
            "files_cancelled": cancelled.count if cancelled else 0,
            "leads_handled": leads.handled if leads else 0,
            "leads_converted": leads.converted if leads else 0,
            "tasks_completed": tasks.completed if tasks else 0,
            "tasks_overdue": tasks.overdue if tasks else 0,
        }

    async def _get_period_quality_metrics(
        self,
        user_id: int,
        period_start: date,
        period_end: date
    ) -> Dict[str, Any]:
        """Get quality metrics for a date range."""
        try:
            errors_query = text("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN revision_count > 1 THEN 1 ELSE 0 END) as rework_count
                FROM loans
                WHERE loan_officer_id = :user_id
                AND updated_at::date BETWEEN :start_date AND :end_date
            """)
            errors = self.db.execute(errors_query, {
                "user_id": user_id,
                "start_date": period_start,
                "end_date": period_end
            }).fetchone()

            total = errors.total or 1
            rework = errors.rework_count or 0
        except Exception as e:
            logger.warning(f"Error querying quality metrics in _get_period_quality_metrics: {e}")
            total = 1
            rework = 0

        return {
            "error_count": rework,
            "error_rate_pct": round((rework / max(total, 1)) * 100, 2),
            "rework_count": rework,
            "rework_rate_pct": round((rework / max(total, 1)) * 100, 2),
        }

    async def _get_period_efficiency_metrics(
        self,
        user_id: int,
        period_start: date,
        period_end: date
    ) -> Dict[str, Any]:
        """Get efficiency metrics for a date range."""
        # Task duration
        task_dur_query = text("""
            SELECT AVG(
                EXTRACT(EPOCH FROM (completed_at - created_at)) / 60
            ) as avg_mins
            FROM tasks
            WHERE owner_id = :user_id
            AND completed_at::date BETWEEN :start_date AND :end_date
        """)
        task_dur = self.db.execute(task_dur_query, {
            "user_id": user_id,
            "start_date": period_start,
            "end_date": period_end
        }).fetchone()

        # SLA
        sla_query = text("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN completed_at <= due_date OR due_date IS NULL THEN 1 END) as on_time
            FROM tasks
            WHERE owner_id = :user_id
            AND completed_at::date BETWEEN :start_date AND :end_date
        """)
        sla = self.db.execute(sla_query, {
            "user_id": user_id,
            "start_date": period_start,
            "end_date": period_end
        }).fetchone()

        # Cycle time
        cycle_query = text("""
            SELECT AVG(
                EXTRACT(EPOCH FROM (funded_at - created_at)) / 86400
            ) as avg_days
            FROM loans
            WHERE loan_officer_id = :user_id
            AND funded_at::date BETWEEN :start_date AND :end_date
        """)
        cycle = self.db.execute(cycle_query, {
            "user_id": user_id,
            "start_date": period_start,
            "end_date": period_end
        }).fetchone()

        total = sla.total if sla else 0
        on_time = sla.on_time if sla else 0
        sla_pct = (on_time / max(total, 1)) * 100

        return {
            "avg_task_duration_mins": round(task_dur.avg_mins or 0, 1),
            "avg_file_cycle_time_days": round(cycle.avg_days or 0, 1),
            "sla_compliance_pct": round(sla_pct, 1),
            "on_time_completion_pct": round(sla_pct, 1),
        }

    # =========================================================================
    # SCORING AND GRADING
    # =========================================================================

    def _calculate_composite_score(
        self,
        volume: Dict[str, Any],
        quality: Dict[str, Any],
        efficiency: Dict[str, Any]
    ) -> float:
        """
        Calculate weighted composite performance score (0-100).
        """
        # Volume score (based on productivity)
        # More files funded and leads converted = higher score
        files_score = min(100, (volume.get("files_funded", 0) / 2) * 25)  # 8 files/month = 100
        leads_score = min(100, (volume.get("leads_converted", 0) / 5) * 25)  # 20 leads/month = 100
        tasks_score = min(100, (volume.get("tasks_completed", 0) / 20) * 25)  # 80 tasks/month = 100
        volume_score = (files_score + leads_score + tasks_score) / 3

        # Quality score (lower error rate = higher score)
        error_rate = quality.get("error_rate_pct", 0)
        quality_score = max(0, 100 - (error_rate * 10))  # 10% error rate = 0 score

        # Efficiency score
        sla_score = efficiency.get("sla_compliance_pct", 100)
        cycle_time = efficiency.get("avg_file_cycle_time_days", 30)
        cycle_score = max(0, 100 - ((cycle_time - 30) * 2))  # 30 days = 100, 50 days = 60
        efficiency_score = (sla_score + cycle_score) / 2

        # Timeliness score
        on_time = efficiency.get("on_time_completion_pct", 100)
        overdue_penalty = min(50, volume.get("tasks_overdue", 0) * 5)
        timeliness_score = max(0, on_time - overdue_penalty)

        # Weighted composite
        composite = (
            volume_score * PERFORMANCE_WEIGHTS["volume"] +
            quality_score * PERFORMANCE_WEIGHTS["quality"] +
            efficiency_score * PERFORMANCE_WEIGHTS["efficiency"] +
            timeliness_score * PERFORMANCE_WEIGHTS["timeliness"]
        )

        return round(min(100, max(0, composite)), 1)

    def _calculate_grade(self, score: float) -> str:
        """Calculate letter grade from numeric score."""
        if score >= GRADE_THRESHOLDS["A"]:
            return PerformanceGrade.A.value
        elif score >= GRADE_THRESHOLDS["B"]:
            return PerformanceGrade.B.value
        elif score >= GRADE_THRESHOLDS["C"]:
            return PerformanceGrade.C.value
        elif score >= GRADE_THRESHOLDS["D"]:
            return PerformanceGrade.D.value
        return PerformanceGrade.F.value

    def _calculate_trend(
        self,
        current_score: float,
        previous_score: Optional[float]
    ) -> Tuple[str, float]:
        """Calculate trend direction and change percentage."""
        if previous_score is None:
            return TrendDirection.STABLE.value, 0.0

        if previous_score == 0:
            return TrendDirection.STABLE.value, 0.0

        change_pct = ((current_score - previous_score) / previous_score) * 100

        if change_pct > 5:
            return TrendDirection.IMPROVING.value, change_pct
        elif change_pct < -5:
            return TrendDirection.DECLINING.value, change_pct
        return TrendDirection.STABLE.value, change_pct

    # =========================================================================
    # BENCHMARKING
    # =========================================================================

    async def _get_team_average_score(
        self,
        organization_id: Optional[int],
        period_start: date,
        period_type: str
    ) -> float:
        """Get team average score for comparison."""
        query = text("""
            SELECT AVG(overall_score) as avg_score
            FROM mm_talent_performance
            WHERE period_type = :period_type
            AND period_start = :period_start
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)

        result = self.db.execute(query, {
            "period_type": period_type,
            "period_start": period_start,
            "org_id": organization_id
        }).fetchone()

        return float(result.avg_score or 0) if result else 0.0

    async def _get_percentile_rank(
        self,
        user_id: int,
        score: float,
        organization_id: Optional[int],
        period_type: str
    ) -> int:
        """Calculate percentile rank for user's score."""
        query = text("""
            SELECT COUNT(*) as below_count
            FROM mm_talent_performance
            WHERE period_type = :period_type
            AND overall_score < :score
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)

        below = self.db.execute(query, {
            "period_type": period_type,
            "score": score,
            "org_id": organization_id
        }).fetchone()

        total_query = text("""
            SELECT COUNT(*) as total
            FROM mm_talent_performance
            WHERE period_type = :period_type
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)

        total = self.db.execute(total_query, {
            "period_type": period_type,
            "org_id": organization_id
        }).fetchone()

        if total and total.total > 0:
            return int((below.below_count / total.total) * 100)
        return 50  # Default to middle

    async def _get_previous_performance(
        self,
        user_id: int,
        current_period_start: date,
        period_type: str
    ) -> Optional[float]:
        """Get previous period's performance score for trend analysis."""
        # Calculate previous period start
        if period_type == PeriodType.DAILY.value:
            prev_start = current_period_start - timedelta(days=1)
        elif period_type == PeriodType.WEEKLY.value:
            prev_start = current_period_start - timedelta(weeks=1)
        elif period_type == PeriodType.MONTHLY.value:
            # Go back one month
            if current_period_start.month == 1:
                prev_start = date(current_period_start.year - 1, 12, 1)
            else:
                prev_start = date(current_period_start.year, current_period_start.month - 1, 1)
        else:
            return None

        query = text("""
            SELECT overall_score
            FROM mm_talent_performance
            WHERE user_id = :user_id
            AND period_type = :period_type
            AND period_start = :prev_start
        """)

        result = self.db.execute(query, {
            "user_id": user_id,
            "period_type": period_type,
            "prev_start": prev_start
        }).fetchone()

        return float(result.overall_score) if result else None

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    async def _save_performance_record(
        self,
        metrics: PerformanceMetrics,
        organization_id: Optional[int]
    ) -> None:
        """Save performance record to database."""
        query = text("""
            INSERT INTO mm_talent_performance (
                organization_id, user_id, period_start, period_end, period_type,
                files_in_pipeline, files_funded, files_cancelled,
                leads_handled, leads_converted, tasks_completed, tasks_overdue,
                error_count, error_rate_pct, rework_count, rework_rate_pct,
                avg_task_duration_mins, avg_file_cycle_time_days,
                sla_compliance_pct, on_time_completion_pct,
                overall_score, performance_grade,
                vs_team_avg_pct, percentile_rank,
                trend_direction, trend_change_pct,
                created_at
            )
            VALUES (
                :org_id, :user_id, :period_start, :period_end, :period_type,
                :files_in_pipeline, :files_funded, :files_cancelled,
                :leads_handled, :leads_converted, :tasks_completed, :tasks_overdue,
                :error_count, :error_rate_pct, :rework_count, :rework_rate_pct,
                :avg_task_duration_mins, :avg_file_cycle_time_days,
                :sla_compliance_pct, :on_time_completion_pct,
                :overall_score, :performance_grade,
                :vs_team_avg_pct, :percentile_rank,
                :trend_direction, :trend_change_pct,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (organization_id, user_id, period_start, period_type)
            DO UPDATE SET
                period_end = EXCLUDED.period_end,
                files_in_pipeline = EXCLUDED.files_in_pipeline,
                files_funded = EXCLUDED.files_funded,
                files_cancelled = EXCLUDED.files_cancelled,
                leads_handled = EXCLUDED.leads_handled,
                leads_converted = EXCLUDED.leads_converted,
                tasks_completed = EXCLUDED.tasks_completed,
                tasks_overdue = EXCLUDED.tasks_overdue,
                error_count = EXCLUDED.error_count,
                error_rate_pct = EXCLUDED.error_rate_pct,
                rework_count = EXCLUDED.rework_count,
                rework_rate_pct = EXCLUDED.rework_rate_pct,
                avg_task_duration_mins = EXCLUDED.avg_task_duration_mins,
                avg_file_cycle_time_days = EXCLUDED.avg_file_cycle_time_days,
                sla_compliance_pct = EXCLUDED.sla_compliance_pct,
                on_time_completion_pct = EXCLUDED.on_time_completion_pct,
                overall_score = EXCLUDED.overall_score,
                performance_grade = EXCLUDED.performance_grade,
                vs_team_avg_pct = EXCLUDED.vs_team_avg_pct,
                percentile_rank = EXCLUDED.percentile_rank,
                trend_direction = EXCLUDED.trend_direction,
                trend_change_pct = EXCLUDED.trend_change_pct
        """)

        self.db.execute(query, {
            "org_id": organization_id,
            "user_id": metrics.user_id,
            "period_start": metrics.period_start,
            "period_end": metrics.period_end,
            "period_type": metrics.period_type,
            "files_in_pipeline": metrics.files_in_pipeline,
            "files_funded": metrics.files_funded,
            "files_cancelled": metrics.files_cancelled,
            "leads_handled": metrics.leads_handled,
            "leads_converted": metrics.leads_converted,
            "tasks_completed": metrics.tasks_completed,
            "tasks_overdue": metrics.tasks_overdue,
            "error_count": metrics.error_count,
            "error_rate_pct": metrics.error_rate_pct,
            "rework_count": metrics.rework_count,
            "rework_rate_pct": metrics.rework_rate_pct,
            "avg_task_duration_mins": metrics.avg_task_duration_mins,
            "avg_file_cycle_time_days": metrics.avg_file_cycle_time_days,
            "sla_compliance_pct": metrics.sla_compliance_pct,
            "on_time_completion_pct": metrics.on_time_completion_pct,
            "overall_score": metrics.overall_score,
            "performance_grade": metrics.performance_grade,
            "vs_team_avg_pct": metrics.vs_team_avg_pct,
            "percentile_rank": metrics.percentile_rank,
            "trend_direction": metrics.trend_direction,
            "trend_change_pct": metrics.trend_change_pct,
        })
        self.db.commit()

    # =========================================================================
    # BATCH CALCULATIONS
    # =========================================================================

    async def calculate_all_daily_performance(
        self,
        target_date: date,
        organization_id: Optional[int] = None
    ) -> int:
        """Calculate daily performance for all active users."""
        users_query = text("""
            SELECT DISTINCT u.id
            FROM users u
            WHERE u.is_active = true
            AND (:org_id IS NULL OR u.organization_id = :org_id)
        """)

        users = self.db.execute(users_query, {"org_id": organization_id}).fetchall()

        count = 0
        for user_row in users:
            try:
                await self.calculate_daily_performance(
                    user_id=user_row.id,
                    target_date=target_date,
                    organization_id=organization_id
                )
                count += 1
            except SQLAlchemyError as e:
                logger.warning(f"Failed to calculate performance for user {user_row.id}: {e}")

        return count

    async def calculate_all_weekly_performance(
        self,
        week_start: date,
        organization_id: Optional[int] = None
    ) -> int:
        """Calculate weekly performance for all active users."""
        users_query = text("""
            SELECT DISTINCT u.id
            FROM users u
            WHERE u.is_active = true
            AND (:org_id IS NULL OR u.organization_id = :org_id)
        """)

        users = self.db.execute(users_query, {"org_id": organization_id}).fetchall()

        count = 0
        for user_row in users:
            try:
                await self.calculate_weekly_performance(
                    user_id=user_row.id,
                    week_start=week_start,
                    organization_id=organization_id
                )
                count += 1
            except SQLAlchemyError as e:
                logger.warning(f"Failed to calculate weekly performance for user {user_row.id}: {e}")

        return count

    async def calculate_all_monthly_performance(
        self,
        month_start: date,
        organization_id: Optional[int] = None
    ) -> int:
        """Calculate monthly performance for all active users."""
        users_query = text("""
            SELECT DISTINCT u.id
            FROM users u
            WHERE u.is_active = true
            AND (:org_id IS NULL OR u.organization_id = :org_id)
        """)

        users = self.db.execute(users_query, {"org_id": organization_id}).fetchall()

        count = 0
        for user_row in users:
            try:
                await self.calculate_monthly_performance(
                    user_id=user_row.id,
                    month_start=month_start,
                    organization_id=organization_id
                )
                count += 1
            except SQLAlchemyError as e:
                logger.warning(f"Failed to calculate monthly performance for user {user_row.id}: {e}")

        return count

    # =========================================================================
    # RETRIEVAL
    # =========================================================================

    async def get_user_performance(
        self,
        user_id: int,
        period_type: str = "monthly",
        limit: int = 12,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get performance history for a user."""
        query = text("""
            SELECT
                tp.*,
                u.full_name
            FROM mm_talent_performance tp
            JOIN users u ON u.id = tp.user_id
            WHERE tp.user_id = :user_id
            AND tp.period_type = :period_type
            AND (:org_id IS NULL OR tp.organization_id = :org_id)
            ORDER BY tp.period_start DESC
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "user_id": user_id,
            "period_type": period_type,
            "org_id": organization_id,
            "limit": limit
        }).fetchall()

        return [
            {
                "user_id": r.user_id,
                "user_name": r.full_name,
                "period_start": r.period_start.isoformat() if r.period_start else None,
                "period_end": r.period_end.isoformat() if r.period_end else None,
                "period_type": r.period_type,
                "volume": {
                    "files_in_pipeline": r.files_in_pipeline,
                    "files_funded": r.files_funded,
                    "files_cancelled": r.files_cancelled,
                    "leads_handled": r.leads_handled,
                    "leads_converted": r.leads_converted,
                    "tasks_completed": r.tasks_completed,
                    "tasks_overdue": r.tasks_overdue,
                },
                "quality": {
                    "error_count": r.error_count,
                    "error_rate_pct": r.error_rate_pct,
                    "rework_count": r.rework_count,
                    "rework_rate_pct": r.rework_rate_pct,
                },
                "efficiency": {
                    "avg_task_duration_mins": r.avg_task_duration_mins,
                    "avg_file_cycle_time_days": r.avg_file_cycle_time_days,
                    "sla_compliance_pct": r.sla_compliance_pct,
                    "on_time_completion_pct": r.on_time_completion_pct,
                },
                "overall_score": r.overall_score,
                "performance_grade": r.performance_grade,
                "vs_team_avg_pct": r.vs_team_avg_pct,
                "percentile_rank": r.percentile_rank,
                "trend": {
                    "direction": r.trend_direction,
                    "change_pct": r.trend_change_pct,
                },
            }
            for r in results
        ]

    async def get_performance_leaderboard(
        self,
        period_type: str = "monthly",
        period_start: Optional[date] = None,
        organization_id: Optional[int] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get performance leaderboard."""
        # Default to current period
        if period_start is None:
            today = date.today()
            if period_type == "monthly":
                period_start = date(today.year, today.month, 1)
            elif period_type == "weekly":
                period_start = today - timedelta(days=today.weekday())
            else:
                period_start = today

        query = text("""
            SELECT
                tp.user_id,
                u.full_name,
                rd.role_name,
                tp.overall_score,
                tp.performance_grade,
                tp.files_funded,
                tp.leads_converted,
                tp.tasks_completed,
                tp.sla_compliance_pct,
                tp.trend_direction,
                tp.trend_change_pct,
                tp.percentile_rank
            FROM mm_talent_performance tp
            JOIN users u ON u.id = tp.user_id
            LEFT JOIN mm_talent_capacity tc ON tc.user_id = tp.user_id
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE tp.period_type = :period_type
            AND tp.period_start = :period_start
            AND (:org_id IS NULL OR tp.organization_id = :org_id)
            ORDER BY tp.overall_score DESC
            LIMIT :limit
        """)

        results = self.db.execute(query, {
            "period_type": period_type,
            "period_start": period_start,
            "org_id": organization_id,
            "limit": limit
        }).fetchall()

        return [
            {
                "rank": idx + 1,
                "user_id": r.user_id,
                "user_name": r.full_name,
                "role_name": r.role_name,
                "overall_score": r.overall_score,
                "performance_grade": r.performance_grade,
                "key_metrics": {
                    "files_funded": r.files_funded,
                    "leads_converted": r.leads_converted,
                    "tasks_completed": r.tasks_completed,
                    "sla_compliance_pct": r.sla_compliance_pct,
                },
                "trend": {
                    "direction": r.trend_direction,
                    "change_pct": r.trend_change_pct,
                },
                "percentile_rank": r.percentile_rank,
            }
            for idx, r in enumerate(results)
        ]

    async def get_performance_dashboard(
        self,
        period_type: str = "monthly",
        organization_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get performance dashboard summary."""
        today = date.today()
        if period_type == "monthly":
            period_start = date(today.year, today.month, 1)
        elif period_type == "weekly":
            period_start = today - timedelta(days=today.weekday())
        else:
            period_start = today

        # Summary stats
        summary_query = text("""
            SELECT
                COUNT(*) as total_users,
                AVG(overall_score) as avg_score,
                COUNT(CASE WHEN performance_grade = 'A' THEN 1 END) as grade_a,
                COUNT(CASE WHEN performance_grade = 'B' THEN 1 END) as grade_b,
                COUNT(CASE WHEN performance_grade = 'C' THEN 1 END) as grade_c,
                COUNT(CASE WHEN performance_grade = 'D' THEN 1 END) as grade_d,
                COUNT(CASE WHEN performance_grade = 'F' THEN 1 END) as grade_f,
                COUNT(CASE WHEN trend_direction = 'improving' THEN 1 END) as improving,
                COUNT(CASE WHEN trend_direction = 'stable' THEN 1 END) as stable,
                COUNT(CASE WHEN trend_direction = 'declining' THEN 1 END) as declining,
                SUM(files_funded) as total_funded,
                SUM(leads_converted) as total_converted,
                AVG(sla_compliance_pct) as avg_sla
            FROM mm_talent_performance
            WHERE period_type = :period_type
            AND period_start = :period_start
            AND (:org_id IS NULL OR organization_id = :org_id)
        """)

        summary = self.db.execute(summary_query, {
            "period_type": period_type,
            "period_start": period_start,
            "org_id": organization_id
        }).fetchone()

        # Get leaderboard
        leaderboard = await self.get_performance_leaderboard(
            period_type=period_type,
            period_start=period_start,
            organization_id=organization_id,
            limit=10
        )

        return {
            "period": {
                "type": period_type,
                "start": period_start.isoformat(),
            },
            "summary": {
                "total_users": summary.total_users or 0,
                "avg_score": round(summary.avg_score or 0, 1),
                "total_funded": summary.total_funded or 0,
                "total_converted": summary.total_converted or 0,
                "avg_sla_compliance": round(summary.avg_sla or 0, 1),
            },
            "grade_distribution": {
                "A": summary.grade_a or 0,
                "B": summary.grade_b or 0,
                "C": summary.grade_c or 0,
                "D": summary.grade_d or 0,
                "F": summary.grade_f or 0,
            },
            "trends": {
                "improving": summary.improving or 0,
                "stable": summary.stable or 0,
                "declining": summary.declining or 0,
            },
            "leaderboard": leaderboard,
        }

    # =========================================================================
    # PROMOTION CANDIDATES
    # =========================================================================

    async def identify_promotion_candidates(
        self,
        organization_id: Optional[int] = None,
        min_score: float = 85,
        min_months: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Identify users who are potential promotion candidates based on
        sustained high performance.
        """
        cutoff_date = date.today() - timedelta(days=min_months * 30)

        query = text("""
            SELECT
                tp.user_id,
                u.full_name,
                rd.role_name,
                COUNT(*) as months_evaluated,
                AVG(tp.overall_score) as avg_score,
                MIN(tp.overall_score) as min_score,
                MAX(tp.overall_score) as max_score,
                SUM(tp.files_funded) as total_funded,
                AVG(tp.sla_compliance_pct) as avg_sla
            FROM mm_talent_performance tp
            JOIN users u ON u.id = tp.user_id
            LEFT JOIN mm_talent_capacity tc ON tc.user_id = tp.user_id
            LEFT JOIN mm_role_definitions rd ON rd.id = tc.role_definition_id
            WHERE tp.period_type = 'monthly'
            AND tp.period_start >= :cutoff_date
            AND (:org_id IS NULL OR tp.organization_id = :org_id)
            GROUP BY tp.user_id, u.full_name, rd.role_name
            HAVING AVG(tp.overall_score) >= :min_score
            AND COUNT(*) >= :min_months
            ORDER BY AVG(tp.overall_score) DESC
        """)

        results = self.db.execute(query, {
            "cutoff_date": cutoff_date,
            "org_id": organization_id,
            "min_score": min_score,
            "min_months": min_months
        }).fetchall()

        return [
            {
                "user_id": r.user_id,
                "user_name": r.full_name,
                "current_role": r.role_name,
                "months_evaluated": r.months_evaluated,
                "avg_score": round(r.avg_score, 1),
                "score_range": {
                    "min": round(r.min_score, 1),
                    "max": round(r.max_score, 1),
                },
                "total_funded": r.total_funded,
                "avg_sla": round(r.avg_sla, 1),
                "readiness_score": round(
                    (r.avg_score * 0.6) +
                    (min(100, r.months_evaluated * 10) * 0.2) +
                    (r.avg_sla * 0.2),
                    1
                ),
            }
            for r in results
        ]


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_performance_service(db: Session) -> PerformanceService:
    """Factory function to get PerformanceService instance."""
    return PerformanceService(db)
