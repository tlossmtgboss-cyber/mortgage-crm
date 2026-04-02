"""
Smart Docs Enterprise — Capacity Planning Service

Provides workload measurement, demand forecasting, load balancing, burnout
detection, hiring analysis, automation ROI, and what-if scenario modelling for
document-processing and underwriting teams.

All queries are org-isolated via ``organization_id``.

Usage:
    from services.smart_docs.enterprise.capacity_planning_service import (
        CapacityPlanningService,
    )

    service = CapacityPlanningService(db_session)
    snapshot = await service.get_current_capacity(org_id=1)
    forecast = await service.forecast_demand(org_id=1, days_ahead=30)
    recs     = await service.get_load_balance_recommendations(org_id=1)
    result   = await service.run_what_if(org_id=1, scenario=scenario)
    roi      = await service.get_automation_roi(org_id=1, start_date=..., end_date=...)
    alerts   = await service.get_burnout_alerts(org_id=1)
    hire     = await service.get_hiring_recommendation(org_id=1)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, cast, func, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Standard working hours per day / week
HOURS_PER_DAY = 8.0
HOURS_PER_WEEK = 40.0
WORKING_DAYS_PER_MONTH = 21.0

# Task complexity weights (relative to a simple paystub review = 1.0)
COMPLEXITY_WEIGHTS: Dict[str, float] = {
    "PAYSTUB": 1.0,
    "W2": 1.2,
    "BANK_STATEMENT": 1.5,
    "TAX_RETURN": 3.0,
    "BUSINESS_TAX_RETURN": 4.0,
    "PROFIT_LOSS": 2.5,
    "BALANCE_SHEET": 2.0,
    "INVESTMENT_STATEMENT": 1.8,
    "APPRAISAL": 2.5,
    "TITLE_REPORT": 2.0,
    "PURCHASE_CONTRACT": 1.5,
    "HOMEOWNERS_INSURANCE": 1.0,
    "DRIVERS_LICENSE": 0.5,
    "GIFT_LETTER": 1.2,
    "LOE": 1.5,
    "LEASE_AGREEMENT": 1.5,
    "FHA_CERT": 1.0,
    "VA_COE": 1.0,
    "DD214": 0.8,
    "BANKRUPTCY_DISCHARGE": 2.0,
    "OTHER": 1.0,
}

# Average minutes to process one complexity-unit (used when no historical data)
DEFAULT_MINUTES_PER_UNIT = 15.0

# Concurrent task limit per role
CONCURRENT_LIMITS: Dict[str, int] = {
    "processing": 25,
    "operations": 20,
    "underwriter": 15,
    "closer": 20,
    "sales": 35,
}

# Average expected documents per active loan by stage
DOCS_PER_LOAN_BY_STAGE: Dict[str, float] = {
    "APPLICATION": 4.0,
    "DISCLOSED": 3.0,
    "PROCESSING": 8.0,
    "SUBMITTED": 2.0,
    "UNDERWRITING": 3.0,
    "UW_RECEIVED": 2.0,
    "CONDITIONAL_APPROVAL": 4.0,
    "APPROVED": 1.5,
    "CTC": 1.0,
    "CLEAR_TO_CLOSE": 2.0,
    "CLOSING": 1.0,
    "DOCS": 3.0,
    "DOCS_OUT": 1.0,
}

# Seasonal multipliers (month index 1-12)
SEASONAL_MULTIPLIERS: Dict[int, float] = {
    1: 0.75,   # January — low
    2: 0.85,
    3: 0.95,
    4: 1.10,   # Spring ramp-up
    5: 1.20,
    6: 1.25,   # Summer peak
    7: 1.20,
    8: 1.15,
    9: 1.05,
    10: 0.95,
    11: 0.85,
    12: 0.70,  # December — low
}

# Burnout thresholds
OVERLOAD_PCT_WARN = 100.0
OVERLOAD_PCT_CRITICAL = 110.0
SUSTAINED_OVERLOAD_WEEKS = 2

# Hiring thresholds
OPTIMAL_UTILIZATION_PCT = 80.0
HIRING_TRIGGER_UTILIZATION_PCT = 90.0

# Terminal loan stages excluded from active pipeline counts
_TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY",
)


# =============================================================================
# ENUMS
# =============================================================================

class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ScenarioType(str, Enum):
    ADD_STAFF = "add_staff"
    VOLUME_CHANGE = "volume_change"
    AUTOMATE_DOC_TYPE = "automate_doc_type"
    REDUCE_STAFF = "reduce_staff"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TeamMemberWorkload:
    """Current workload snapshot for a single team member."""
    user_id: int
    name: str
    role: str
    active_loans: int
    pending_reviews: int
    docs_today: int
    docs_capacity_per_day: int
    weighted_load: float
    utilization_pct: float
    hours_worked_estimate: float
    hours_available: float
    avg_processing_minutes: float
    concurrent_limit: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "role": self.role,
            "active_loans": self.active_loans,
            "pending_reviews": self.pending_reviews,
            "docs_today": self.docs_today,
            "docs_capacity_per_day": self.docs_capacity_per_day,
            "weighted_load": round(self.weighted_load, 2),
            "utilization_pct": round(self.utilization_pct, 1),
            "hours_worked_estimate": round(self.hours_worked_estimate, 2),
            "hours_available": round(self.hours_available, 2),
            "avg_processing_minutes": round(self.avg_processing_minutes, 1),
            "concurrent_limit": self.concurrent_limit,
        }


@dataclass
class CapacitySnapshot:
    """Organization-wide capacity snapshot."""
    org_id: int
    generated_at: str
    total_team_members: int
    total_active_loans: int
    total_pending_reviews: int
    total_docs_today: int
    total_capacity_today: int
    org_utilization_pct: float
    avg_processing_time_by_type: Dict[str, float]
    team: List[TeamMemberWorkload]
    bottleneck_doc_types: List[Dict[str, Any]]
    bottleneck_stages: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "total_team_members": self.total_team_members,
            "total_active_loans": self.total_active_loans,
            "total_pending_reviews": self.total_pending_reviews,
            "total_docs_today": self.total_docs_today,
            "total_capacity_today": self.total_capacity_today,
            "org_utilization_pct": round(self.org_utilization_pct, 1),
            "avg_processing_time_by_type": {
                k: round(v, 1) for k, v in self.avg_processing_time_by_type.items()
            },
            "team": [t.to_dict() for t in self.team],
            "bottleneck_doc_types": self.bottleneck_doc_types,
            "bottleneck_stages": self.bottleneck_stages,
        }


@dataclass
class DemandForecast:
    """Projected demand over the forecast horizon."""
    org_id: int
    days_ahead: int
    generated_at: str
    pipeline_loans: int
    expected_document_volume: int
    expected_income_calculations: int
    expected_condition_reviews: int
    seasonal_factor: float
    projected_daily_volume: List[Dict[str, Any]]
    closings_scheduled: int
    expected_condition_volume: int
    historical_trend_pct: float
    capacity_gap: float  # positive = surplus, negative = deficit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "days_ahead": self.days_ahead,
            "generated_at": self.generated_at,
            "pipeline_loans": self.pipeline_loans,
            "expected_document_volume": self.expected_document_volume,
            "expected_income_calculations": self.expected_income_calculations,
            "expected_condition_reviews": self.expected_condition_reviews,
            "seasonal_factor": round(self.seasonal_factor, 2),
            "projected_daily_volume": self.projected_daily_volume,
            "closings_scheduled": self.closings_scheduled,
            "expected_condition_volume": self.expected_condition_volume,
            "historical_trend_pct": round(self.historical_trend_pct, 1),
            "capacity_gap": round(self.capacity_gap, 1),
        }


@dataclass
class Recommendation:
    """Load-balancing or operational recommendation."""
    priority: str  # high, medium, low
    category: str  # redistribution, priority_assignment, skill_routing
    message: str
    from_user_id: Optional[int] = None
    from_user_name: Optional[str] = None
    to_user_id: Optional[int] = None
    to_user_name: Optional[str] = None
    loan_ids: List[int] = field(default_factory=list)
    impact_estimate: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "priority": self.priority,
            "category": self.category,
            "message": self.message,
            "from_user_id": self.from_user_id,
            "from_user_name": self.from_user_name,
            "to_user_id": self.to_user_id,
            "to_user_name": self.to_user_name,
            "loan_ids": self.loan_ids,
            "impact_estimate": self.impact_estimate,
        }


@dataclass
class WhatIfScenario:
    """Input for a what-if scenario simulation."""
    scenario_type: str  # ScenarioType value
    # ADD_STAFF / REDUCE_STAFF
    staff_count: int = 0
    staff_role: str = "processing"
    # VOLUME_CHANGE
    volume_change_pct: float = 0.0
    # AUTOMATE_DOC_TYPE
    doc_type_to_automate: Optional[str] = None
    automation_efficiency_pct: float = 90.0  # what percentage of docs are handled without human


@dataclass
class ScenarioResult:
    """Output of a what-if scenario simulation."""
    scenario: Dict[str, Any]
    current_utilization_pct: float
    projected_utilization_pct: float
    current_sla_compliance_pct: float
    projected_sla_compliance_pct: float
    capacity_delta_docs_per_day: float
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "current_utilization_pct": round(self.current_utilization_pct, 1),
            "projected_utilization_pct": round(self.projected_utilization_pct, 1),
            "current_sla_compliance_pct": round(self.current_sla_compliance_pct, 1),
            "projected_sla_compliance_pct": round(self.projected_sla_compliance_pct, 1),
            "capacity_delta_docs_per_day": round(self.capacity_delta_docs_per_day, 1),
            "summary": self.summary,
            "details": self.details,
        }


@dataclass
class ROIAnalysis:
    """Automation ROI analysis over a date range."""
    org_id: int
    start_date: str
    end_date: str
    total_documents_processed: int
    auto_classified: int
    auto_accepted: int
    human_reviewed: int
    auto_income_calculations: int
    time_saved_hours: float
    cost_saved_estimate: float
    no_touch_rate_pct: float
    projected_annual_savings: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_documents_processed": self.total_documents_processed,
            "auto_classified": self.auto_classified,
            "auto_accepted": self.auto_accepted,
            "human_reviewed": self.human_reviewed,
            "auto_income_calculations": self.auto_income_calculations,
            "time_saved_hours": round(self.time_saved_hours, 1),
            "cost_saved_estimate": round(self.cost_saved_estimate, 2),
            "no_touch_rate_pct": round(self.no_touch_rate_pct, 1),
            "projected_annual_savings": round(self.projected_annual_savings, 2),
        }


@dataclass
class BurnoutAlert:
    """Alert for a team member approaching or in burnout territory."""
    user_id: int
    name: str
    role: str
    severity: str  # AlertSeverity value
    utilization_pct: float
    consecutive_overload_weeks: int
    message: str
    suggested_action: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "role": self.role,
            "severity": self.severity,
            "utilization_pct": round(self.utilization_pct, 1),
            "consecutive_overload_weeks": self.consecutive_overload_weeks,
            "message": self.message,
            "suggested_action": self.suggested_action,
        }


@dataclass
class HiringAnalysis:
    """Hiring recommendation with break-even and cost analysis."""
    org_id: int
    current_team_size: int
    current_utilization_pct: float
    current_loans_per_processor: float
    recommended_hires: int
    recommended_role: str
    trigger_reason: str
    cost_per_loan: float
    break_even_loans: int
    break_even_months: float
    volume_threshold_for_next_hire: int
    projected_utilization_after_hire: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "current_team_size": self.current_team_size,
            "current_utilization_pct": round(self.current_utilization_pct, 1),
            "current_loans_per_processor": round(self.current_loans_per_processor, 1),
            "recommended_hires": self.recommended_hires,
            "recommended_role": self.recommended_role,
            "trigger_reason": self.trigger_reason,
            "cost_per_loan": round(self.cost_per_loan, 2),
            "break_even_loans": self.break_even_loans,
            "break_even_months": round(self.break_even_months, 1),
            "volume_threshold_for_next_hire": self.volume_threshold_for_next_hire,
            "projected_utilization_after_hire": round(self.projected_utilization_after_hire, 1),
        }


@dataclass
class ShiftCoverage:
    """Shift planning analysis for processing team."""
    org_id: int
    coverage_by_hour: List[Dict[str, Any]]
    recommended_shifts: List[Dict[str, Any]]
    gap_hours: List[int]
    peak_hours: List[int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "org_id": self.org_id,
            "coverage_by_hour": self.coverage_by_hour,
            "recommended_shifts": self.recommended_shifts,
            "gap_hours": self.gap_hours,
            "peak_hours": self.peak_hours,
        }


# =============================================================================
# SERVICE
# =============================================================================

class CapacityPlanningService:
    """Enterprise capacity planning for document processing teams.

    All public methods are async, accept ``org_id`` for tenant isolation,
    and return strongly-typed dataclass results with ``.to_dict()`` helpers
    for JSON serialization.
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _today(self) -> date:
        return date.today()

    def _safe_pct(self, numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 0.0
        return (numerator / denominator) * 100.0

    def _get_processing_team(self, org_id: int) -> List[Dict[str, Any]]:
        """Return users in document-processing roles for the org."""
        rows = self.db.execute(text("""
            SELECT id, first_name, last_name, permission_role, role
            FROM users
            WHERE organization_id = :org_id
              AND is_active = true
              AND (
                  permission_role IN ('processing', 'operations')
                  OR role IN ('processor', 'underwriter', 'closer')
              )
            ORDER BY last_name, first_name
        """), {"org_id": org_id}).fetchall()
        return [dict(r._mapping) for r in rows]

    def _effective_role(self, user: Dict[str, Any]) -> str:
        """Normalise permission_role / role to a canonical role string."""
        pr = (user.get("permission_role") or "").lower()
        r = (user.get("role") or "").lower()
        if "underwriter" in r or "underwriter" in pr:
            return "underwriter"
        if "closer" in r or "closer" in pr:
            return "closer"
        if pr in ("processing", "operations"):
            return pr
        return "processing"

    def _user_full_name(self, user: Dict[str, Any]) -> str:
        first = user.get("first_name") or ""
        last = user.get("last_name") or ""
        name = f"{first} {last}".strip()
        return name or f"User {user['id']}"

    # ------------------------------------------------------------------
    # 1. get_current_capacity
    # ------------------------------------------------------------------

    async def get_current_capacity(self, org_id: int) -> CapacitySnapshot:
        """Build a real-time capacity snapshot for the org."""
        team_members = self._get_processing_team(org_id)
        if not team_members:
            return CapacitySnapshot(
                org_id=org_id,
                generated_at=self._now_utc().isoformat(),
                total_team_members=0,
                total_active_loans=0,
                total_pending_reviews=0,
                total_docs_today=0,
                total_capacity_today=0,
                org_utilization_pct=0.0,
                avg_processing_time_by_type={},
                team=[],
                bottleneck_doc_types=[],
                bottleneck_stages=[],
            )

        today = self._today()
        team_workloads: List[TeamMemberWorkload] = []
        user_ids = [u["id"] for u in team_members]

        # Pending reviews across org
        pending_by_reviewer = self._get_pending_reviews_by_user(org_id, user_ids)

        # Docs processed today per user (approximate via uploaded_by_user_id)
        docs_today_by_user = self._get_docs_processed_today(org_id, user_ids, today)

        # Active loans assigned to each processor/underwriter (via Loan.processor
        # or Loan.underwriter name match — best effort since these are string cols)
        active_loans_by_user = self._get_active_loans_by_team(org_id, team_members)

        # Average processing time by doc type (org-wide, last 90 days)
        avg_time_by_type = self._get_avg_processing_time_by_type(org_id)

        for user in team_members:
            uid = user["id"]
            role = self._effective_role(user)
            name = self._user_full_name(user)
            pending = pending_by_reviewer.get(uid, 0)
            docs_done_today = docs_today_by_user.get(uid, 0)
            active_loans = active_loans_by_user.get(uid, 0)
            concurrent_limit = CONCURRENT_LIMITS.get(role, 20)

            # Estimate weighted load from pending review types
            weighted_load = self._get_weighted_load_for_user(org_id, uid)

            # Capacity: available minutes / avg minutes per weighted unit
            avg_min = self._avg_minutes_per_unit(avg_time_by_type)
            capacity_per_day = int(
                (HOURS_PER_DAY * 60.0) / max(avg_min, 1.0)
            ) if avg_min > 0 else 32

            hours_worked = (docs_done_today * avg_min) / 60.0
            utilization = self._safe_pct(weighted_load, capacity_per_day)

            team_workloads.append(TeamMemberWorkload(
                user_id=uid,
                name=name,
                role=role,
                active_loans=active_loans,
                pending_reviews=pending,
                docs_today=docs_done_today,
                docs_capacity_per_day=capacity_per_day,
                weighted_load=weighted_load,
                utilization_pct=min(utilization, 200.0),
                hours_worked_estimate=hours_worked,
                hours_available=max(HOURS_PER_DAY - hours_worked, 0),
                avg_processing_minutes=avg_min,
                concurrent_limit=concurrent_limit,
            ))

        # Org-level totals
        total_pending = sum(tw.pending_reviews for tw in team_workloads)
        total_docs_today = sum(tw.docs_today for tw in team_workloads)
        total_capacity = sum(tw.docs_capacity_per_day for tw in team_workloads)
        total_active_loans = self._get_active_loan_count(org_id)
        org_util = self._safe_pct(total_docs_today, total_capacity)

        # Bottleneck analysis
        bottleneck_doc_types = self._get_bottleneck_doc_types(org_id)
        bottleneck_stages = self._get_bottleneck_stages(org_id)

        return CapacitySnapshot(
            org_id=org_id,
            generated_at=self._now_utc().isoformat(),
            total_team_members=len(team_workloads),
            total_active_loans=total_active_loans,
            total_pending_reviews=total_pending,
            total_docs_today=total_docs_today,
            total_capacity_today=total_capacity,
            org_utilization_pct=org_util,
            avg_processing_time_by_type=avg_time_by_type,
            team=team_workloads,
            bottleneck_doc_types=bottleneck_doc_types,
            bottleneck_stages=bottleneck_stages,
        )

    # ------------------------------------------------------------------
    # 2. forecast_demand
    # ------------------------------------------------------------------

    async def forecast_demand(
        self, org_id: int, days_ahead: int = 30,
    ) -> DemandForecast:
        """Forecast document processing demand over the next N days."""
        today = self._today()
        now = self._now_utc()

        # Pipeline loans in active stages
        pipeline_loans = self._get_active_loan_count(org_id)

        # Expected doc volume from pipeline
        expected_doc_volume = self._project_doc_volume_from_pipeline(org_id)

        # Seasonal factor for mid-point of forecast window
        mid_date = today + timedelta(days=days_ahead // 2)
        seasonal = SEASONAL_MULTIPLIERS.get(mid_date.month, 1.0)

        # Historical trend: compare last-30-day volume to prior-30-day
        trend_pct = self._get_volume_trend_pct(org_id)

        # Closings scheduled within forecast window
        closings = self._get_scheduled_closings(org_id, today, today + timedelta(days=days_ahead))

        # Expected conditions from closings (average ~4 conditions per closing)
        expected_conditions = closings * 4

        # Expected income calcs (~1 per pipeline loan in processing/submitted)
        expected_income = self._count_loans_needing_income_calc(org_id)

        # Adjusted daily volume
        current_capacity = self._get_total_daily_capacity(org_id)
        base_daily = expected_doc_volume / max(days_ahead, 1)
        adjusted_daily = base_daily * seasonal * (1.0 + trend_pct / 100.0)

        # Build daily projections (simplified: flat rate with seasonal)
        daily_projections: List[Dict[str, Any]] = []
        for offset in range(min(days_ahead, 60)):
            d = today + timedelta(days=offset)
            if d.weekday() >= 5:
                daily_projections.append({
                    "date": d.isoformat(),
                    "projected_volume": 0,
                    "is_weekend": True,
                })
                continue
            month_factor = SEASONAL_MULTIPLIERS.get(d.month, 1.0)
            vol = int(adjusted_daily * month_factor / seasonal)  # normalise so total is correct
            daily_projections.append({
                "date": d.isoformat(),
                "projected_volume": max(vol, 0),
                "is_weekend": False,
            })

        capacity_gap = current_capacity - adjusted_daily  # positive = surplus

        return DemandForecast(
            org_id=org_id,
            days_ahead=days_ahead,
            generated_at=now.isoformat(),
            pipeline_loans=pipeline_loans,
            expected_document_volume=int(expected_doc_volume * seasonal),
            expected_income_calculations=expected_income,
            expected_condition_reviews=expected_conditions,
            seasonal_factor=seasonal,
            projected_daily_volume=daily_projections,
            closings_scheduled=closings,
            expected_condition_volume=expected_conditions,
            historical_trend_pct=trend_pct,
            capacity_gap=capacity_gap,
        )

    # ------------------------------------------------------------------
    # 3. get_load_balance_recommendations
    # ------------------------------------------------------------------

    async def get_load_balance_recommendations(
        self, org_id: int,
    ) -> List[Recommendation]:
        """Identify overloaded team members and suggest redistribution."""
        snapshot = await self.get_current_capacity(org_id)
        recs: List[Recommendation] = []
        if not snapshot.team:
            return recs

        overloaded = [t for t in snapshot.team if t.utilization_pct > OVERLOAD_PCT_WARN]
        underloaded = [t for t in snapshot.team if t.utilization_pct < 60.0]

        # 1. Redistribution: move work from overloaded to underloaded
        for over in sorted(overloaded, key=lambda t: -t.utilization_pct):
            for under in sorted(underloaded, key=lambda t: t.utilization_pct):
                if over.role != under.role:
                    continue
                excess = over.pending_reviews - over.docs_capacity_per_day
                available = under.docs_capacity_per_day - under.pending_reviews
                if excess > 0 and available > 0:
                    transfer = min(excess, available)
                    recs.append(Recommendation(
                        priority="high" if over.utilization_pct > OVERLOAD_PCT_CRITICAL else "medium",
                        category="redistribution",
                        message=(
                            f"Transfer ~{transfer} pending reviews from {over.name} "
                            f"({over.utilization_pct:.0f}% util) to {under.name} "
                            f"({under.utilization_pct:.0f}% util)"
                        ),
                        from_user_id=over.user_id,
                        from_user_name=over.name,
                        to_user_id=under.user_id,
                        to_user_name=under.name,
                        impact_estimate=f"Reduces {over.name} utilization by ~{self._safe_pct(transfer, over.docs_capacity_per_day):.0f}%",
                    ))

        # 2. Priority-based assignment: loans closing soon should get priority
        closing_soon_loans = self._get_loans_closing_within(org_id, days=7)
        if closing_soon_loans:
            recs.append(Recommendation(
                priority="high",
                category="priority_assignment",
                message=(
                    f"{len(closing_soon_loans)} loans closing within 7 days — "
                    f"prioritize their pending document reviews"
                ),
                loan_ids=[l["id"] for l in closing_soon_loans],
                impact_estimate="Reduces risk of closing delays",
            ))

        # 3. Skill-based routing: complex income docs to senior processors
        complex_pending = self._get_complex_pending_docs(org_id)
        senior_members = [t for t in snapshot.team if t.utilization_pct < 85.0 and t.role in ("processing", "operations")]
        if complex_pending and senior_members:
            best = min(senior_members, key=lambda t: t.utilization_pct)
            recs.append(Recommendation(
                priority="medium",
                category="skill_routing",
                message=(
                    f"{len(complex_pending)} complex documents (tax returns, P&L) "
                    f"pending — route to {best.name} who has capacity"
                ),
                to_user_id=best.user_id,
                to_user_name=best.name,
                impact_estimate="Faster turnaround on complex income analysis",
            ))

        return recs

    # ------------------------------------------------------------------
    # 4. run_what_if
    # ------------------------------------------------------------------

    async def run_what_if(
        self, org_id: int, scenario: WhatIfScenario,
    ) -> ScenarioResult:
        """Run a what-if scenario and project impact on utilization and SLA."""
        snapshot = await self.get_current_capacity(org_id)
        current_util = snapshot.org_utilization_pct
        current_sla = self._get_sla_compliance_pct(org_id)
        current_capacity = snapshot.total_capacity_today
        current_demand = snapshot.total_pending_reviews

        projected_capacity = float(current_capacity)
        projected_demand = float(current_demand)
        summary = ""
        details: Dict[str, Any] = {}

        if scenario.scenario_type == ScenarioType.ADD_STAFF.value:
            per_person_capacity = int(
                (HOURS_PER_DAY * 60.0) / max(DEFAULT_MINUTES_PER_UNIT, 1.0)
            )
            added_capacity = scenario.staff_count * per_person_capacity
            projected_capacity += added_capacity
            projected_util = self._safe_pct(projected_demand, projected_capacity)
            sla_improvement = min(
                (added_capacity / max(projected_demand, 1)) * 10.0, 10.0
            )
            projected_sla = min(current_sla + sla_improvement, 100.0)
            summary = (
                f"Adding {scenario.staff_count} {scenario.staff_role}(s) increases daily "
                f"capacity by {added_capacity} docs, reducing utilization from "
                f"{current_util:.0f}% to {projected_util:.0f}%"
            )
            details = {
                "added_capacity_per_day": added_capacity,
                "new_team_size": snapshot.total_team_members + scenario.staff_count,
            }

        elif scenario.scenario_type == ScenarioType.REDUCE_STAFF.value:
            per_person_capacity = int(
                (HOURS_PER_DAY * 60.0) / max(DEFAULT_MINUTES_PER_UNIT, 1.0)
            )
            removed_capacity = scenario.staff_count * per_person_capacity
            projected_capacity = max(projected_capacity - removed_capacity, 1)
            projected_util = self._safe_pct(projected_demand, projected_capacity)
            sla_reduction = min(
                (removed_capacity / max(projected_demand, 1)) * 15.0, 30.0
            )
            projected_sla = max(current_sla - sla_reduction, 0.0)
            summary = (
                f"Removing {scenario.staff_count} {scenario.staff_role}(s) reduces daily "
                f"capacity by {removed_capacity} docs, increasing utilization from "
                f"{current_util:.0f}% to {projected_util:.0f}%"
            )
            details = {
                "removed_capacity_per_day": removed_capacity,
                "new_team_size": max(snapshot.total_team_members - scenario.staff_count, 0),
            }

        elif scenario.scenario_type == ScenarioType.VOLUME_CHANGE.value:
            pct = scenario.volume_change_pct
            projected_demand = projected_demand * (1.0 + pct / 100.0)
            projected_util = self._safe_pct(projected_demand, projected_capacity)
            sla_delta = -abs(pct) * 0.15 if pct > 0 else abs(pct) * 0.10
            projected_sla = max(min(current_sla + sla_delta, 100.0), 0.0)
            direction = "increase" if pct > 0 else "decrease"
            summary = (
                f"A {abs(pct):.0f}% volume {direction} changes demand from "
                f"{current_demand} to {projected_demand:.0f} docs/day, "
                f"{'raising' if pct > 0 else 'lowering'} utilization to {projected_util:.0f}%"
            )
            details = {
                "volume_change_pct": pct,
                "new_daily_demand": int(projected_demand),
            }

        elif scenario.scenario_type == ScenarioType.AUTOMATE_DOC_TYPE.value:
            doc_type = scenario.doc_type_to_automate or "BANK_STATEMENT"
            efficiency = scenario.automation_efficiency_pct / 100.0
            auto_count = self._count_pending_by_doc_type(org_id, doc_type)
            freed = int(auto_count * efficiency)
            projected_demand = max(projected_demand - freed, 0)
            projected_util = self._safe_pct(projected_demand, projected_capacity)
            weight = COMPLEXITY_WEIGHTS.get(doc_type, 1.0)
            time_saved_min = freed * weight * DEFAULT_MINUTES_PER_UNIT
            projected_sla = min(current_sla + (freed / max(current_demand, 1)) * 15.0, 100.0)
            summary = (
                f"Automating {doc_type} at {scenario.automation_efficiency_pct:.0f}% "
                f"efficiency removes ~{freed} docs from queue, saving "
                f"{time_saved_min / 60.0:.1f} hours/day and reducing utilization "
                f"to {projected_util:.0f}%"
            )
            details = {
                "doc_type": doc_type,
                "docs_automated": freed,
                "time_saved_hours_per_day": round(time_saved_min / 60.0, 1),
            }
        else:
            projected_util = current_util
            projected_sla = current_sla
            summary = "Unknown scenario type"

        capacity_delta = projected_capacity - projected_demand

        return ScenarioResult(
            scenario={
                "type": scenario.scenario_type,
                "params": {
                    "staff_count": scenario.staff_count,
                    "staff_role": scenario.staff_role,
                    "volume_change_pct": scenario.volume_change_pct,
                    "doc_type_to_automate": scenario.doc_type_to_automate,
                    "automation_efficiency_pct": scenario.automation_efficiency_pct,
                },
            },
            current_utilization_pct=current_util,
            projected_utilization_pct=projected_util,
            current_sla_compliance_pct=current_sla,
            projected_sla_compliance_pct=projected_sla,
            capacity_delta_docs_per_day=capacity_delta,
            summary=summary,
            details=details,
        )

    # ------------------------------------------------------------------
    # 5. get_automation_roi
    # ------------------------------------------------------------------

    async def get_automation_roi(
        self,
        org_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ROIAnalysis:
        """Calculate ROI from AI classification and auto-income calculations."""
        if end_date is None:
            end_date = self._today()
        if start_date is None:
            start_date = end_date - timedelta(days=90)

        params: Dict[str, Any] = {
            "org_id": org_id,
            "start_date": start_date,
            "end_date": end_date,
        }

        # Documents processed in the period
        doc_stats = self.db.execute(text("""
            SELECT
                COUNT(*) AS total,
                COUNT(CASE WHEN source = 'AI_CLASSIFIER' THEN 1 END) AS auto_classified,
                COUNT(CASE WHEN status = 'active' AND source = 'AI_CLASSIFIER' THEN 1 END) AS auto_accepted
            FROM documents
            WHERE organization_id = :org_id
              AND uploaded_at >= :start_date
              AND uploaded_at < :end_date + INTERVAL '1 day'
        """), params).fetchone()

        total_docs = (doc_stats.total if doc_stats else 0) or 0
        auto_classified = (doc_stats.auto_classified if doc_stats else 0) or 0
        auto_accepted = (doc_stats.auto_accepted if doc_stats else 0) or 0
        human_reviewed = total_docs - auto_accepted

        # Auto income calculations (from income_calculations table)
        income_stats = self.db.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM income_calculations
            WHERE organization_id = :org_id
              AND created_at >= :start_date
              AND created_at < :end_date + INTERVAL '1 day'
              AND calculation_type = 'initial'
        """), params).fetchone()
        auto_income = (income_stats.cnt if income_stats else 0) or 0

        # Time savings estimates
        avg_human_minutes = DEFAULT_MINUTES_PER_UNIT
        time_saved_classification = auto_accepted * (avg_human_minutes * 0.8) / 60.0  # 80% of manual time
        time_saved_income = auto_income * 45.0 / 60.0  # 45 min per manual income calc
        total_time_saved = time_saved_classification + time_saved_income

        # Cost: assume $35/hour fully-loaded processor cost
        hourly_rate = 35.0
        cost_saved = total_time_saved * hourly_rate

        # No-touch rate
        no_touch_pct = self._safe_pct(auto_accepted, total_docs)

        # Annualize
        period_days = max((end_date - start_date).days, 1)
        annual_factor = 365.0 / period_days
        projected_annual = cost_saved * annual_factor

        return ROIAnalysis(
            org_id=org_id,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            total_documents_processed=total_docs,
            auto_classified=auto_classified,
            auto_accepted=auto_accepted,
            human_reviewed=human_reviewed,
            auto_income_calculations=auto_income,
            time_saved_hours=total_time_saved,
            cost_saved_estimate=cost_saved,
            no_touch_rate_pct=no_touch_pct,
            projected_annual_savings=projected_annual,
        )

    # ------------------------------------------------------------------
    # 6. get_burnout_alerts
    # ------------------------------------------------------------------

    async def get_burnout_alerts(self, org_id: int) -> List[BurnoutAlert]:
        """Detect team members at risk of burnout based on sustained overload."""
        alerts: List[BurnoutAlert] = []
        team = self._get_processing_team(org_id)
        if not team:
            return alerts

        for user in team:
            uid = user["id"]
            name = self._user_full_name(user)
            role = self._effective_role(user)

            # Calculate utilization over last N weeks
            weekly_utils = self._get_weekly_utilization_history(org_id, uid, weeks=6)
            if not weekly_utils:
                continue

            current_util = weekly_utils[0] if weekly_utils else 0.0

            # Count consecutive weeks over threshold
            consecutive_overload = 0
            for util in weekly_utils:
                if util > OVERLOAD_PCT_CRITICAL:
                    consecutive_overload += 1
                else:
                    break

            if consecutive_overload >= SUSTAINED_OVERLOAD_WEEKS:
                alerts.append(BurnoutAlert(
                    user_id=uid,
                    name=name,
                    role=role,
                    severity=AlertSeverity.CRITICAL.value,
                    utilization_pct=current_util,
                    consecutive_overload_weeks=consecutive_overload,
                    message=(
                        f"{name} has been at >{OVERLOAD_PCT_CRITICAL:.0f}% capacity "
                        f"for {consecutive_overload} consecutive weeks"
                    ),
                    suggested_action=(
                        f"Immediately redistribute {int(current_util - OPTIMAL_UTILIZATION_PCT)}% "
                        f"of workload or provide schedule relief"
                    ),
                ))
            elif current_util > OVERLOAD_PCT_WARN:
                alerts.append(BurnoutAlert(
                    user_id=uid,
                    name=name,
                    role=role,
                    severity=AlertSeverity.WARNING.value,
                    utilization_pct=current_util,
                    consecutive_overload_weeks=consecutive_overload,
                    message=(
                        f"{name} is currently at {current_util:.0f}% capacity"
                    ),
                    suggested_action=(
                        "Monitor closely; consider partial workload redistribution"
                    ),
                ))

        # Sort by severity (critical first) then by utilization descending
        severity_order = {AlertSeverity.CRITICAL.value: 0, AlertSeverity.WARNING.value: 1, AlertSeverity.INFO.value: 2}
        alerts.sort(key=lambda a: (severity_order.get(a.severity, 9), -a.utilization_pct))

        return alerts

    # ------------------------------------------------------------------
    # 7. get_hiring_recommendation
    # ------------------------------------------------------------------

    async def get_hiring_recommendation(self, org_id: int) -> HiringAnalysis:
        """Analyse whether the org should hire, and provide cost/break-even data."""
        snapshot = await self.get_current_capacity(org_id)
        current_util = snapshot.org_utilization_pct
        active_loans = snapshot.total_active_loans
        team_size = snapshot.total_team_members
        loans_per_processor = active_loans / max(team_size, 1)

        # Cost assumptions
        annual_processor_cost = 55_000.0  # fully-loaded
        monthly_cost = annual_processor_cost / 12.0

        # Revenue per loan (industry average)
        avg_revenue_per_loan = 3_500.0

        # Capacity added by one processor
        per_person_capacity = int(
            (HOURS_PER_DAY * 60.0) / max(DEFAULT_MINUTES_PER_UNIT, 1.0)
        )

        # Break-even: how many additional loans does the new hire need to process
        # to cover their cost per month?
        loans_per_month_new = per_person_capacity * WORKING_DAYS_PER_MONTH * 0.3  # ~30% of capacity yields funded loans
        break_even_loans = int(math.ceil(monthly_cost / avg_revenue_per_loan))
        break_even_months = monthly_cost / max(loans_per_month_new * avg_revenue_per_loan / max(active_loans, 1), 0.01)
        break_even_months = min(break_even_months, 24.0)  # cap at 24

        # Determine recommendation
        if current_util > HIRING_TRIGGER_UTILIZATION_PCT:
            recommended_hires = max(1, int((current_util - OPTIMAL_UTILIZATION_PCT) / 25.0))
            trigger = f"Team is at {current_util:.0f}% utilization (>{HIRING_TRIGGER_UTILIZATION_PCT:.0f}% threshold)"
        elif loans_per_processor > 30:
            recommended_hires = 1
            trigger = f"Each processor handles {loans_per_processor:.0f} active loans (>30 threshold)"
        else:
            recommended_hires = 0
            trigger = f"Utilization at {current_util:.0f}% — no immediate need"

        # Volume threshold for next hire
        current_total_capacity = team_size * per_person_capacity
        target_utilization_pct = HIRING_TRIGGER_UTILIZATION_PCT / 100.0
        threshold_demand = int(current_total_capacity * target_utilization_pct)

        # Projected utilization after hire
        new_capacity = current_total_capacity + (recommended_hires * per_person_capacity)
        projected_util_after = self._safe_pct(snapshot.total_pending_reviews, new_capacity)

        # Cost per loan
        total_cost = team_size * annual_processor_cost
        funded_90d = self._get_funded_count(org_id, 90)
        annual_funded = funded_90d * 4  # annualise
        cost_per_loan = total_cost / max(annual_funded, 1)

        return HiringAnalysis(
            org_id=org_id,
            current_team_size=team_size,
            current_utilization_pct=current_util,
            current_loans_per_processor=loans_per_processor,
            recommended_hires=recommended_hires,
            recommended_role="processing",
            trigger_reason=trigger,
            cost_per_loan=cost_per_loan,
            break_even_loans=break_even_loans,
            break_even_months=break_even_months,
            volume_threshold_for_next_hire=threshold_demand,
            projected_utilization_after_hire=projected_util_after,
        )

    # ------------------------------------------------------------------
    # 8. get_shift_coverage
    # ------------------------------------------------------------------

    async def get_shift_coverage(self, org_id: int) -> ShiftCoverage:
        """Analyse hourly coverage and recommend optimal shift schedules."""
        # Get document upload distribution by hour (proxy for demand pattern)
        hourly_demand = self.db.execute(text("""
            SELECT
                EXTRACT(HOUR FROM uploaded_at) AS hour,
                COUNT(*) AS volume
            FROM documents
            WHERE organization_id = :org_id
              AND uploaded_at >= CURRENT_DATE - 90
            GROUP BY EXTRACT(HOUR FROM uploaded_at)
            ORDER BY hour
        """), {"org_id": org_id}).fetchall()

        demand_by_hour: Dict[int, int] = {int(r.hour): int(r.volume) for r in hourly_demand}
        total_volume = sum(demand_by_hour.values()) or 1

        # Build coverage map
        team = self._get_processing_team(org_id)
        team_size = len(team)
        # Assume standard 8-5 shift without specific user schedules
        standard_start = 8
        standard_end = 17

        coverage: List[Dict[str, Any]] = []
        gap_hours: List[int] = []
        peak_hours: List[int] = []

        for h in range(24):
            demand_pct = (demand_by_hour.get(h, 0) / total_volume) * 100.0
            staff_available = team_size if standard_start <= h < standard_end else 0
            is_gap = demand_pct > 3.0 and staff_available == 0
            is_peak = demand_pct > 8.0

            if is_gap:
                gap_hours.append(h)
            if is_peak:
                peak_hours.append(h)

            coverage.append({
                "hour": h,
                "demand_pct": round(demand_pct, 1),
                "staff_available": staff_available,
                "is_covered": staff_available > 0 or demand_pct < 1.0,
            })

        # Recommended shifts
        recommended_shifts: List[Dict[str, Any]] = []
        if peak_hours:
            peak_start = min(peak_hours)
            peak_end = max(peak_hours) + 1
            recommended_shifts.append({
                "name": "Primary Shift",
                "start_hour": max(peak_start - 1, 7),
                "end_hour": min(peak_end + 1, 18),
                "staff_needed": max(int(team_size * 0.7), 1),
                "reason": f"Covers peak demand hours {peak_start}:00-{peak_end}:00",
            })

        if gap_hours:
            gap_start = min(gap_hours)
            gap_end = max(gap_hours) + 1
            recommended_shifts.append({
                "name": "Extended Coverage Shift",
                "start_hour": gap_start,
                "end_hour": gap_end,
                "staff_needed": max(int(team_size * 0.2), 1),
                "reason": f"Covers demand gap at hours {gap_start}:00-{gap_end}:00",
            })

        if not recommended_shifts:
            recommended_shifts.append({
                "name": "Standard Shift",
                "start_hour": 8,
                "end_hour": 17,
                "staff_needed": team_size,
                "reason": "Standard business hours coverage",
            })

        return ShiftCoverage(
            org_id=org_id,
            coverage_by_hour=coverage,
            recommended_shifts=recommended_shifts,
            gap_hours=gap_hours,
            peak_hours=peak_hours,
        )

    # =================================================================
    # PRIVATE QUERY HELPERS
    # =================================================================

    def _get_active_loan_count(self, org_id: int) -> int:
        row = self.db.execute(text("""
            SELECT COUNT(*) AS cnt
            FROM loans
            WHERE organization_id = :org_id
              AND stage NOT IN :terminal_stages
        """.replace(":terminal_stages", self._terminal_in_clause())),
            {"org_id": org_id},
        ).fetchone()
        return int(row.cnt) if row else 0

    def _terminal_in_clause(self) -> str:
        return "(" + ", ".join(f"'{s}'" for s in _TERMINAL_STAGES) + ")"

    def _get_pending_reviews_by_user(
        self, org_id: int, user_ids: List[int],
    ) -> Dict[int, int]:
        """Count pending document reviews assigned to each user.

        Uses smart_documents.reviewed_by_user_id and document_requests
        with PENDING_REVIEW / OPEN status.
        """
        if not user_ids:
            return {}

        try:
            rows = self.db.execute(text("""
                SELECT
                    dr.assigned_to_user_id AS uid,
                    COUNT(*) AS cnt
                FROM document_requests dr
                WHERE dr.organization_id = :org_id
                  AND dr.is_active = true
                  AND dr.status IN ('OPEN', 'PENDING_REVIEW')
                  AND dr.assigned_to_user_id = ANY(:user_ids)
                GROUP BY dr.assigned_to_user_id
            """), {"org_id": org_id, "user_ids": user_ids}).fetchall()
            return {int(r.uid): int(r.cnt) for r in rows}
        except Exception as e:
            logger.debug(f"Pending reviews query failed (table may not have assigned_to_user_id): {e}")
            # Fallback: distribute evenly
            try:
                row = self.db.execute(text("""
                    SELECT COUNT(*) AS cnt
                    FROM document_requests
                    WHERE organization_id = :org_id
                      AND is_active = true
                      AND status IN ('OPEN', 'PENDING_REVIEW')
                """), {"org_id": org_id}).fetchone()
                total = int(row.cnt) if row else 0
                per_user = total // max(len(user_ids), 1)
                return {uid: per_user for uid in user_ids}
            except Exception as e2:
                logger.debug(f"Fallback pending reviews query failed: {e2}")
                return {}

    def _get_docs_processed_today(
        self, org_id: int, user_ids: List[int], today: date,
    ) -> Dict[int, int]:
        """Documents uploaded/processed today per user."""
        if not user_ids:
            return {}
        try:
            rows = self.db.execute(text("""
                SELECT
                    uploaded_by_user_id AS uid,
                    COUNT(*) AS cnt
                FROM documents
                WHERE organization_id = :org_id
                  AND uploaded_at >= :today
                  AND uploaded_by_user_id = ANY(:user_ids)
                GROUP BY uploaded_by_user_id
            """), {"org_id": org_id, "today": today, "user_ids": user_ids}).fetchall()
            return {int(r.uid): int(r.cnt) for r in rows}
        except Exception as e:
            logger.debug(f"Docs processed today query failed: {e}")
            return {}

    def _get_active_loans_by_team(
        self, org_id: int, team_members: List[Dict[str, Any]],
    ) -> Dict[int, int]:
        """Map user_id -> count of active loans where they are the processor or
        underwriter.  Since Loan.processor is a free-text name column, we
        match on CONCAT(first_name, ' ', last_name).
        """
        result: Dict[int, int] = {}
        for user in team_members:
            name = self._user_full_name(user)
            if not name or name.startswith("User "):
                continue
            try:
                query = f"""
                    SELECT COUNT(*) AS cnt
                    FROM loans
                    WHERE organization_id = :org_id
                      AND stage NOT IN {self._terminal_in_clause()}
                      AND (processor = :name OR underwriter = :name)
                """
                row = self.db.execute(text(query), {"org_id": org_id, "name": name}).fetchone()
                result[user["id"]] = int(row.cnt) if row else 0
            except Exception as e:
                logger.debug(f"Active loans query for {name} failed: {e}")
                result[user["id"]] = 0
        return result

    def _get_avg_processing_time_by_type(
        self, org_id: int, days: int = 90,
    ) -> Dict[str, float]:
        """Average minutes between document upload and acceptance, by doc type.

        Uses smart_documents reviewed_at - created_at as proxy.
        Falls back to complexity-weight defaults if no data.
        """
        try:
            rows = self.db.execute(text("""
                SELECT
                    sd.doc_type,
                    AVG(EXTRACT(EPOCH FROM (sd.reviewed_at - sd.created_at)) / 60.0) AS avg_minutes
                FROM smart_documents sd
                WHERE sd.organization_id = :org_id
                  AND sd.reviewed_at IS NOT NULL
                  AND sd.created_at >= CURRENT_DATE - :days
                GROUP BY sd.doc_type
            """), {"org_id": org_id, "days": days}).fetchall()
            if rows:
                return {r.doc_type: float(r.avg_minutes or DEFAULT_MINUTES_PER_UNIT) for r in rows}
        except Exception as e:
            logger.debug(f"Avg processing time query failed: {e}")

        # Fallback to weight-based estimates
        return {
            dt: weight * DEFAULT_MINUTES_PER_UNIT
            for dt, weight in COMPLEXITY_WEIGHTS.items()
        }

    def _avg_minutes_per_unit(self, time_map: Dict[str, float]) -> float:
        if not time_map:
            return DEFAULT_MINUTES_PER_UNIT
        return sum(time_map.values()) / len(time_map)

    def _get_weighted_load_for_user(self, org_id: int, user_id: int) -> float:
        """Calculate complexity-weighted pending workload for a user."""
        try:
            rows = self.db.execute(text("""
                SELECT dr.doc_type, COUNT(*) AS cnt
                FROM document_requests dr
                WHERE dr.organization_id = :org_id
                  AND dr.is_active = true
                  AND dr.status IN ('OPEN', 'PENDING_REVIEW')
                  AND dr.assigned_to_user_id = :user_id
                GROUP BY dr.doc_type
            """), {"org_id": org_id, "user_id": user_id}).fetchall()
            return sum(
                int(r.cnt) * COMPLEXITY_WEIGHTS.get(r.doc_type, 1.0)
                for r in rows
            )
        except Exception:
            # Fallback: use unweighted pending count
            try:
                rows2 = self.db.execute(text("""
                    SELECT COUNT(*) AS cnt
                    FROM document_requests
                    WHERE organization_id = :org_id
                      AND is_active = true
                      AND status IN ('OPEN', 'PENDING_REVIEW')
                      AND assigned_to_user_id = :user_id
                """), {"org_id": org_id, "user_id": user_id}).fetchone()
                return float(rows2.cnt) if rows2 else 0.0
            except Exception:
                return 0.0

    def _get_bottleneck_doc_types(self, org_id: int) -> List[Dict[str, Any]]:
        """Doc types with the longest average queue wait."""
        try:
            rows = self.db.execute(text("""
                SELECT
                    doc_type,
                    COUNT(*) AS pending_count,
                    AVG(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - created_at)) / 3600.0) AS avg_wait_hours
                FROM document_requests
                WHERE organization_id = :org_id
                  AND is_active = true
                  AND status IN ('OPEN', 'PENDING_REVIEW')
                GROUP BY doc_type
                HAVING COUNT(*) >= 2
                ORDER BY avg_wait_hours DESC
                LIMIT 5
            """), {"org_id": org_id}).fetchall()
            return [
                {
                    "doc_type": r.doc_type,
                    "pending_count": int(r.pending_count),
                    "avg_wait_hours": round(float(r.avg_wait_hours or 0), 1),
                    "complexity_weight": COMPLEXITY_WEIGHTS.get(r.doc_type, 1.0),
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug(f"Bottleneck doc types query failed: {e}")
            return []

    def _get_bottleneck_stages(self, org_id: int) -> List[Dict[str, Any]]:
        """Loan stages with the most pending document work."""
        try:
            query = f"""
                SELECT
                    l.stage,
                    COUNT(DISTINCT l.id) AS loan_count,
                    COUNT(dr.id) AS pending_docs
                FROM loans l
                JOIN document_requests dr ON dr.loan_id = l.id
                WHERE l.organization_id = :org_id
                  AND l.stage NOT IN {self._terminal_in_clause()}
                  AND dr.is_active = true
                  AND dr.status IN ('OPEN', 'PENDING_REVIEW')
                GROUP BY l.stage
                ORDER BY pending_docs DESC
                LIMIT 5
            """
            rows = self.db.execute(text(query), {"org_id": org_id}).fetchall()
            return [
                {
                    "stage": r.stage,
                    "loan_count": int(r.loan_count),
                    "pending_docs": int(r.pending_docs),
                }
                for r in rows
            ]
        except Exception as e:
            logger.debug(f"Bottleneck stages query failed: {e}")
            return []

    def _get_sla_compliance_pct(self, org_id: int) -> float:
        """Percentage of document requests resolved within SLA."""
        try:
            row = self.db.execute(text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE
                        WHEN status IN ('ACCEPTED', 'WAIVED')
                             AND (sla_due_at IS NULL OR updated_at <= sla_due_at)
                        THEN 1
                    END) AS within_sla
                FROM document_requests
                WHERE organization_id = :org_id
                  AND status NOT IN ('OPEN', 'PENDING_REVIEW')
                  AND created_at >= CURRENT_DATE - 90
            """), {"org_id": org_id}).fetchone()
            if row and row.total > 0:
                return self._safe_pct(int(row.within_sla), int(row.total))
        except Exception as e:
            logger.debug(f"SLA compliance query failed: {e}")
        return 85.0  # default assumption

    def _get_loans_closing_within(
        self, org_id: int, days: int = 7,
    ) -> List[Dict[str, Any]]:
        try:
            query = f"""
                SELECT id, loan_number, borrower_name, closing_date, processor
                FROM loans
                WHERE organization_id = :org_id
                  AND closing_date BETWEEN CURRENT_DATE AND CURRENT_DATE + :days
                  AND stage NOT IN {self._terminal_in_clause()}
                ORDER BY closing_date ASC
            """
            rows = self.db.execute(text(query), {"org_id": org_id, "days": days}).fetchall()
            return [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.debug(f"Loans closing within query failed: {e}")
            return []

    def _get_complex_pending_docs(self, org_id: int) -> List[Dict[str, Any]]:
        """Pending docs with complexity weight >= 2.5 (tax returns, P&L, etc.)."""
        high_complexity_types = [
            dt for dt, w in COMPLEXITY_WEIGHTS.items() if w >= 2.5
        ]
        if not high_complexity_types:
            return []
        type_in = "(" + ", ".join(f"'{t}'" for t in high_complexity_types) + ")"
        try:
            query = f"""
                SELECT id, doc_type, loan_id
                FROM document_requests
                WHERE organization_id = :org_id
                  AND is_active = true
                  AND status IN ('OPEN', 'PENDING_REVIEW')
                  AND doc_type IN {type_in}
                LIMIT 50
            """
            rows = self.db.execute(text(query), {"org_id": org_id}).fetchall()
            return [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.debug(f"Complex pending docs query failed: {e}")
            return []

    def _project_doc_volume_from_pipeline(self, org_id: int) -> float:
        """Project expected document volume from current pipeline composition."""
        try:
            query = f"""
                SELECT stage, COUNT(*) AS cnt
                FROM loans
                WHERE organization_id = :org_id
                  AND stage NOT IN {self._terminal_in_clause()}
                GROUP BY stage
            """
            rows = self.db.execute(text(query), {"org_id": org_id}).fetchall()
            total = 0.0
            for r in rows:
                total += int(r.cnt) * DOCS_PER_LOAN_BY_STAGE.get(r.stage, 2.0)
            return total
        except Exception as e:
            logger.debug(f"Pipeline doc projection query failed: {e}")
            return 0.0

    def _get_volume_trend_pct(self, org_id: int) -> float:
        """Compare last-30-day doc volume to prior-30-day volume."""
        try:
            row = self.db.execute(text("""
                SELECT
                    COUNT(CASE WHEN uploaded_at >= CURRENT_DATE - 30 THEN 1 END) AS recent,
                    COUNT(CASE WHEN uploaded_at >= CURRENT_DATE - 60
                               AND uploaded_at < CURRENT_DATE - 30 THEN 1 END) AS prior
                FROM documents
                WHERE organization_id = :org_id
                  AND uploaded_at >= CURRENT_DATE - 60
            """), {"org_id": org_id}).fetchone()
            recent = int(row.recent) if row else 0
            prior = int(row.prior) if row else 0
            if prior == 0:
                return 0.0
            return ((recent - prior) / prior) * 100.0
        except Exception as e:
            logger.debug(f"Volume trend query failed: {e}")
            return 0.0

    def _get_scheduled_closings(
        self, org_id: int, start: date, end: date,
    ) -> int:
        try:
            query = f"""
                SELECT COUNT(*) AS cnt
                FROM loans
                WHERE organization_id = :org_id
                  AND closing_date BETWEEN :start AND :end
                  AND stage NOT IN {self._terminal_in_clause()}
            """
            row = self.db.execute(text(query), {"org_id": org_id, "start": start, "end": end}).fetchone()
            return int(row.cnt) if row else 0
        except Exception as e:
            logger.debug(f"Scheduled closings query failed: {e}")
            return 0

    def _count_loans_needing_income_calc(self, org_id: int) -> int:
        try:
            query = f"""
                SELECT COUNT(*) AS cnt
                FROM loans
                WHERE organization_id = :org_id
                  AND stage IN ('PROCESSING', 'SUBMITTED', 'UNDERWRITING', 'UW_RECEIVED')
            """
            row = self.db.execute(text(query), {"org_id": org_id}).fetchone()
            return int(row.cnt) if row else 0
        except Exception as e:
            logger.debug(f"Loans needing income calc query failed: {e}")
            return 0

    def _get_total_daily_capacity(self, org_id: int) -> float:
        """Total org daily document processing capacity (doc units)."""
        team = self._get_processing_team(org_id)
        avg_time = self._avg_minutes_per_unit(
            self._get_avg_processing_time_by_type(org_id)
        )
        per_person = (HOURS_PER_DAY * 60.0) / max(avg_time, 1.0)
        return len(team) * per_person

    def _count_pending_by_doc_type(self, org_id: int, doc_type: str) -> int:
        try:
            row = self.db.execute(text("""
                SELECT COUNT(*) AS cnt
                FROM document_requests
                WHERE organization_id = :org_id
                  AND is_active = true
                  AND status IN ('OPEN', 'PENDING_REVIEW')
                  AND doc_type = :doc_type
            """), {"org_id": org_id, "doc_type": doc_type}).fetchone()
            return int(row.cnt) if row else 0
        except Exception as e:
            logger.debug(f"Pending by doc type query failed: {e}")
            return 0

    def _get_funded_count(self, org_id: int, days: int) -> int:
        try:
            row = self.db.execute(text("""
                SELECT COUNT(*) AS cnt
                FROM loans
                WHERE organization_id = :org_id
                  AND funded_date >= CURRENT_DATE - :days
            """), {"org_id": org_id, "days": days}).fetchone()
            return int(row.cnt) if row else 0
        except Exception as e:
            logger.debug(f"Funded count query failed: {e}")
            return 0

    def _get_weekly_utilization_history(
        self, org_id: int, user_id: int, weeks: int = 6,
    ) -> List[float]:
        """Return list of utilization percentages for last N weeks (most recent first).

        Approximation: (docs processed per week) / (capacity per week) * 100.
        """
        result: List[float] = []
        today = self._today()
        avg_time = self._avg_minutes_per_unit(
            self._get_avg_processing_time_by_type(org_id)
        )
        weekly_capacity = (HOURS_PER_WEEK * 60.0) / max(avg_time, 1.0)

        for w in range(weeks):
            week_end = today - timedelta(days=w * 7)
            week_start = week_end - timedelta(days=7)
            try:
                row = self.db.execute(text("""
                    SELECT COUNT(*) AS cnt
                    FROM documents
                    WHERE organization_id = :org_id
                      AND uploaded_by_user_id = :user_id
                      AND uploaded_at >= :start
                      AND uploaded_at < :end
                """), {
                    "org_id": org_id,
                    "user_id": user_id,
                    "start": week_start,
                    "end": week_end,
                }).fetchone()
                processed = int(row.cnt) if row else 0
                util = self._safe_pct(processed, weekly_capacity)
                result.append(util)
            except Exception as e:
                logger.debug(f"Weekly utilization query failed for week {w}: {e}")
                result.append(0.0)

        return result
