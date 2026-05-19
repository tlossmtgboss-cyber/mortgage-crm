"""
Smart Docs V2 SLA Enforcement Service

Production-grade SLA lifecycle management for document operations:

- Business-hours-aware timer calculation (configurable hours, weekends, holidays)
- Timer start / pause / resume / complete / exempt
- Warning and breach escalation chains (75%, 100%, 150%, 200%)
- Dashboard data: active SLAs, compliance rate, trending
- Per-user performance ranking
- Compliance reporting (daily/weekly/monthly, breach root-cause analysis)
- Default SLA config provisioning for new organizations
- Scheduled check cycle for batch warning/breach detection

Usage:
    from services.smart_docs.enterprise.sla_enforcement_service import SLAEnforcementService

    svc = SLAEnforcementService(db=session, org_id=42)
    tracking = await svc.start_sla("DOC_CLASSIFICATION", "document", doc_id, loan_id)
    status = await svc.check_sla_status(tracking.id)
    await svc.complete_sla(tracking.id)
    dashboard = await svc.get_sla_dashboard()
    alerts = await svc.run_sla_check_cycle()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import Session

from database.models.doc_sla_config import DocSLAConfig, DocSLATracking

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

class SLAType(str, Enum):
    DOC_CLASSIFICATION = "DOC_CLASSIFICATION"
    DOC_REVIEW = "DOC_REVIEW"
    INCOME_CALCULATION = "INCOME_CALCULATION"
    CONDITION_CLEARANCE = "CONDITION_CLEARANCE"
    BORROWER_RESPONSE = "BORROWER_RESPONSE"
    PACKAGE_GENERATION = "PACKAGE_GENERATION"
    SIGNING_COMPLETION = "SIGNING_COMPLETION"


class SLATimerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MET = "MET"
    BREACHED = "BREACHED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


# Default SLA targets in business hours per type
DEFAULT_SLA_TARGETS: Dict[str, Dict[str, Any]] = {
    SLAType.DOC_CLASSIFICATION: {
        "name": "Document Classification",
        "target_hours": 2.0,
        "warning_pct": 75.0,
        "business_hours_only": True,
        "escalation_chain": [
            {"at_pct": 75, "notify": "processor"},
            {"at_pct": 100, "notify": "manager"},
            {"at_pct": 150, "notify": "branch_manager"},
        ],
    },
    SLAType.DOC_REVIEW: {
        "name": "Document Review",
        "target_hours": 4.0,
        "warning_pct": 75.0,
        "business_hours_only": True,
        "escalation_chain": [
            {"at_pct": 75, "notify": "processor"},
            {"at_pct": 100, "notify": "manager"},
            {"at_pct": 150, "notify": "branch_manager"},
            {"at_pct": 200, "notify": "vp_operations"},
        ],
    },
    SLAType.INCOME_CALCULATION: {
        "name": "Income Calculation",
        "target_hours": 8.0,
        "warning_pct": 75.0,
        "business_hours_only": True,
        "escalation_chain": [
            {"at_pct": 75, "notify": "processor"},
            {"at_pct": 100, "notify": "manager"},
            {"at_pct": 150, "notify": "branch_manager"},
            {"at_pct": 200, "notify": "vp_operations"},
        ],
    },
    SLAType.CONDITION_CLEARANCE: {
        "name": "Condition Clearance",
        "target_hours": 24.0,
        "warning_pct": 75.0,
        "business_hours_only": True,
        "escalation_chain": [
            {"at_pct": 75, "notify": "processor"},
            {"at_pct": 100, "notify": "manager"},
            {"at_pct": 150, "notify": "branch_manager"},
            {"at_pct": 200, "notify": "vp_operations"},
        ],
    },
    SLAType.BORROWER_RESPONSE: {
        "name": "Borrower Document Response",
        "target_hours": 72.0,
        "warning_pct": 75.0,
        "business_hours_only": False,  # clock runs 24/7 for borrower
        "escalation_chain": [
            {"at_pct": 75, "notify": "loan_officer"},
            {"at_pct": 100, "notify": "processor"},
            {"at_pct": 150, "notify": "manager"},
        ],
    },
    SLAType.PACKAGE_GENERATION: {
        "name": "Submission Package Generation",
        "target_hours": 4.0,
        "warning_pct": 75.0,
        "business_hours_only": True,
        "escalation_chain": [
            {"at_pct": 75, "notify": "processor"},
            {"at_pct": 100, "notify": "manager"},
        ],
    },
    SLAType.SIGNING_COMPLETION: {
        "name": "E-Signature Completion",
        "target_hours": 48.0,
        "warning_pct": 75.0,
        "business_hours_only": False,  # clock runs 24/7 for borrower signatures
        "escalation_chain": [
            {"at_pct": 75, "notify": "loan_officer"},
            {"at_pct": 100, "notify": "processor"},
            {"at_pct": 150, "notify": "manager"},
        ],
    },
}

# ---------------------------------------------------------------------------
# Dynamic US Federal Holiday Calculator
# ---------------------------------------------------------------------------

def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of a weekday in a given month.

    Args:
        year: Calendar year.
        month: Month (1-12).
        weekday: Day of week (0=Monday, 6=Sunday).
        n: Which occurrence (1-based). Use -1 for last.

    Returns:
        The matching date.
    """
    import calendar
    if n == -1:
        # Last occurrence: start from last day of month and walk back
        last_day = calendar.monthrange(year, month)[1]
        d = date(year, month, last_day)
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return d
    # nth occurrence: find first occurrence, then skip (n-1) weeks
    first_day = date(year, month, 1)
    # Days until the target weekday
    days_ahead = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + timedelta(days=days_ahead)
    return first_occurrence + timedelta(weeks=n - 1)


def _get_federal_holidays(year: int) -> set[date]:
    """Compute US federal holidays for a given year.

    Covers the 10 standard federal holidays:
      - New Year's Day (Jan 1)
      - MLK Day (3rd Monday of January)
      - Presidents' Day (3rd Monday of February)
      - Memorial Day (last Monday of May)
      - Independence Day (Jul 4)
      - Labor Day (1st Monday of September)
      - Columbus Day (2nd Monday of October)
      - Veterans Day (Nov 11)
      - Thanksgiving (4th Thursday of November)
      - Christmas Day (Dec 25)

    Returns:
        Set of date objects for all federal holidays in the given year.
    """
    holidays: set[date] = set()

    # Fixed-date holidays
    holidays.add(date(year, 1, 1))    # New Year's Day
    holidays.add(date(year, 7, 4))    # Independence Day
    holidays.add(date(year, 11, 11))  # Veterans Day
    holidays.add(date(year, 12, 25))  # Christmas Day

    # Floating holidays (weekday 0=Monday, 3=Thursday)
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))    # MLK Day: 3rd Monday of Jan
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))    # Presidents' Day: 3rd Monday of Feb
    holidays.add(_nth_weekday_of_month(year, 5, 0, -1))   # Memorial Day: last Monday of May
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))    # Labor Day: 1st Monday of Sep
    holidays.add(_nth_weekday_of_month(year, 10, 0, 2))   # Columbus Day: 2nd Monday of Oct
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))   # Thanksgiving: 4th Thursday of Nov

    return holidays


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SLAStatus:
    """Current status of an SLA timer."""
    tracking_id: int
    sla_type: str
    status: str
    elapsed_business_hours: float
    target_hours: float
    remaining_hours: float
    pct_elapsed: float
    is_warning: bool
    is_breached: bool
    is_paused: bool
    target_at: datetime
    warning_at: Optional[datetime]
    started_at: datetime
    completed_at: Optional[datetime]
    entity_type: str
    entity_id: Optional[int]
    loan_id: int
    assigned_to_user_id: Optional[int]
    escalation_level: int


@dataclass
class SLAAlert:
    """Alert generated during an SLA check cycle."""
    tracking_id: int
    sla_type: str
    alert_type: str  # WARNING, BREACH, ESCALATION
    loan_id: int
    entity_type: str
    entity_id: Optional[int]
    pct_elapsed: float
    escalation_level: int
    notify_role: str
    message: str


@dataclass
class SLADashboard:
    """Aggregated SLA dashboard data."""
    active_count: int
    met_count: int
    breached_count: int
    paused_count: int
    compliance_rate: float  # % met out of (met + breached)
    active_slas: List[SLAStatus]
    by_type: Dict[str, Dict[str, Any]]
    at_risk: List[SLAStatus]
    trending: Dict[str, Any]


@dataclass
class ComplianceReport:
    """SLA compliance report for a date range."""
    period_start: date
    period_end: date
    total_completed: int
    total_met: int
    total_breached: int
    compliance_rate: float
    avg_completion_hours: float
    by_type: Dict[str, Dict[str, Any]]
    by_user: List[Dict[str, Any]]
    breach_analysis: List[Dict[str, Any]]
    time_in_queue: Dict[str, float]
    trend_vs_prior: Optional[Dict[str, Any]] = None


@dataclass
class UserSLAPerformance:
    """Per-user SLA performance metrics."""
    user_id: int
    user_name: str
    total_completed: int
    total_met: int
    total_breached: int
    compliance_rate: float
    avg_completion_hours: float
    rank: int = 0


# =============================================================================
# BUSINESS HOURS CALCULATOR
# =============================================================================

class BusinessHoursCalculator:
    """
    Calculates business hours between two datetimes, respecting configurable
    start/end hours, weekend exclusion, and holiday calendars.
    """

    def __init__(
        self,
        start_hour: int = 8,
        end_hour: int = 18,
        exclude_weekends: bool = True,
        exclude_holidays: bool = True,
        org_holidays: Optional[List[date]] = None,
        state: Optional[str] = None,
    ):
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.hours_per_day = end_hour - start_hour
        self.exclude_weekends = exclude_weekends
        self.exclude_holidays = exclude_holidays
        self.state = state.upper() if state else None
        # Use central HolidayCalendar for state-aware holiday detection;
        # fall back to the legacy federal-only set if import fails.
        self._calendar = None
        self._holidays: set[date] = set()
        if exclude_holidays:
            try:
                from services.holiday_calendar import HolidayCalendar
                self._calendar = HolidayCalendar(custom_closures=org_holidays)
            except Exception:  # pragma: no cover — defensive fallback
                current_year = datetime.now(timezone.utc).year
                self._holidays.update(_get_federal_holidays(current_year))
                self._holidays.update(_get_federal_holidays(current_year + 1))
                if org_holidays:
                    self._holidays.update(org_holidays)
        elif org_holidays:
            self._holidays.update(org_holidays)

    def is_business_day(self, d: date) -> bool:
        """Check if a date is a business day."""
        if self.exclude_weekends and d.weekday() >= 5:
            return False
        if self.exclude_holidays:
            if self._calendar is not None:
                if self._calendar.is_holiday(d, state=self.state):
                    return False
            elif d in self._holidays:
                return False
        return True

    def _clamp_to_business(self, dt: datetime) -> datetime:
        """Clamp a datetime to within business hours on the same day."""
        day_start = dt.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        day_end = dt.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
        if dt < day_start:
            return day_start
        if dt > day_end:
            return day_end
        return dt

    def _next_business_start(self, dt: datetime) -> datetime:
        """Find the next business day start at or after dt."""
        d = dt.date()
        # If we are before end of business on a business day, return max(dt, start_of_day)
        day_end = dt.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
        if self.is_business_day(d) and dt < day_end:
            day_start = dt.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
            return max(dt, day_start)
        # Otherwise advance to next business day
        d += timedelta(days=1)
        while not self.is_business_day(d):
            d += timedelta(days=1)
        return datetime(d.year, d.month, d.day, self.start_hour, 0, 0, tzinfo=dt.tzinfo)

    def calculate_elapsed(self, start: datetime, end: datetime) -> float:
        """
        Calculate business hours elapsed between start and end.

        Returns fractional hours. Negative if end < start (returns 0).
        """
        if end <= start:
            return 0.0

        total_hours = 0.0
        current = self._next_business_start(start)

        while current < end:
            day_end_dt = current.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
            if end < day_end_dt:
                # End is within this business day
                total_hours += (end - current).total_seconds() / 3600.0
                break
            else:
                # Full remaining business hours for this day
                total_hours += (day_end_dt - current).total_seconds() / 3600.0
                # Move to next business day
                next_day = current.date() + timedelta(days=1)
                while not self.is_business_day(next_day):
                    next_day += timedelta(days=1)
                current = datetime(
                    next_day.year, next_day.month, next_day.day,
                    self.start_hour, 0, 0, tzinfo=current.tzinfo,
                )

        return max(total_hours, 0.0)

    def add_business_hours(self, start: datetime, hours: float) -> datetime:
        """
        Add business hours to a start datetime and return the resulting datetime.

        If hours is 0 or negative, returns start clamped to next business start.
        """
        if hours <= 0:
            return self._next_business_start(start)

        remaining = hours
        current = self._next_business_start(start)

        while remaining > 0:
            day_end_dt = current.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
            available = (day_end_dt - current).total_seconds() / 3600.0

            if remaining <= available:
                return current + timedelta(hours=remaining)
            else:
                remaining -= available
                # Advance to next business day
                next_day = current.date() + timedelta(days=1)
                while not self.is_business_day(next_day):
                    next_day += timedelta(days=1)
                current = datetime(
                    next_day.year, next_day.month, next_day.day,
                    self.start_hour, 0, 0, tzinfo=current.tzinfo,
                )

        return current


class WallClockCalculator:
    """
    Simple wall-clock hour calculator for SLAs that run 24/7
    (e.g., borrower response, signing completion).
    """

    def calculate_elapsed(self, start: datetime, end: datetime) -> float:
        if end <= start:
            return 0.0
        return (end - start).total_seconds() / 3600.0

    def add_business_hours(self, start: datetime, hours: float) -> datetime:
        return start + timedelta(hours=hours)


# =============================================================================
# SERVICE
# =============================================================================

class SLAEnforcementService:
    """
    Async-style SLA enforcement service for Smart Docs V2.

    All public methods are async. Organization isolation is enforced
    on every query via org_id filtering.
    """

    def __init__(self, db: Session, org_id: int):
        self.db = db
        self.org_id = org_id

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _utcnow(self) -> datetime:
        return datetime.now(timezone.utc)

    def _get_config(self, sla_type: str) -> Optional[DocSLAConfig]:
        """Get active SLA config for this org and type."""
        return (
            self.db.query(DocSLAConfig)
            .filter(
                DocSLAConfig.organization_id == self.org_id,
                DocSLAConfig.sla_type == sla_type,
                DocSLAConfig.is_active.is_(True),
            )
            .first()
        )

    def _get_tracking(self, tracking_id: int) -> Optional[DocSLATracking]:
        """Get tracking record scoped to this org."""
        return (
            self.db.query(DocSLATracking)
            .filter(
                DocSLATracking.id == tracking_id,
                DocSLATracking.organization_id == self.org_id,
            )
            .first()
        )

    def _build_calculator(self, config: DocSLAConfig) -> BusinessHoursCalculator | WallClockCalculator:
        """Build the appropriate hours calculator for a config."""
        if not config.business_hours_only:
            return WallClockCalculator()

        # Load org-specific holidays if available
        org_holidays: List[date] = []
        try:
            from database.models.core import Organization
            org = self.db.query(Organization).filter(Organization.id == self.org_id).first()
            if org and hasattr(org, "holiday_calendar") and org.holiday_calendar:
                for entry in org.holiday_calendar:
                    try:
                        org_holidays.append(date.fromisoformat(entry))
                    except (ValueError, TypeError):
                        pass
        except Exception as _exc:  # noqa: BLE001
            pass

        return BusinessHoursCalculator(
            start_hour=config.business_hours_start or 8,
            end_hour=config.business_hours_end or 18,
            exclude_weekends=config.exclude_weekends if config.exclude_weekends is not None else True,
            exclude_holidays=config.exclude_holidays if config.exclude_holidays is not None else True,
            org_holidays=org_holidays,
        )

    def _compute_status(self, tracking: DocSLATracking, config: DocSLAConfig) -> SLAStatus:
        """Build SLAStatus from a tracking record."""
        now = self._utcnow()
        calc = self._build_calculator(config)

        # Calculate elapsed, accounting for pauses
        if tracking.status == SLATimerStatus.PAUSED and tracking.paused_at:
            effective_end = tracking.paused_at
        elif tracking.completed_at:
            effective_end = tracking.completed_at
        else:
            effective_end = now

        elapsed = calc.calculate_elapsed(tracking.started_at, effective_end)
        # Subtract paused time
        paused_hours = tracking.total_paused_hours or 0.0
        elapsed = max(elapsed - paused_hours, 0.0)

        target_hours = config.target_hours
        remaining = max(target_hours - elapsed, 0.0)
        pct = (elapsed / target_hours * 100.0) if target_hours > 0 else 0.0
        warning_pct = config.warning_threshold_pct or 75.0

        return SLAStatus(
            tracking_id=tracking.id,
            sla_type=config.sla_type,
            status=tracking.status,
            elapsed_business_hours=round(elapsed, 2),
            target_hours=target_hours,
            remaining_hours=round(remaining, 2),
            pct_elapsed=round(pct, 1),
            is_warning=pct >= warning_pct and not tracking.breached,
            is_breached=tracking.breached or pct >= 100.0,
            is_paused=tracking.status == SLATimerStatus.PAUSED,
            target_at=tracking.target_at,
            warning_at=tracking.warning_at,
            started_at=tracking.started_at,
            completed_at=tracking.completed_at,
            entity_type=tracking.entity_type or "",
            entity_id=tracking.entity_id,
            loan_id=tracking.loan_id,
            assigned_to_user_id=tracking.assigned_to_user_id,
            escalation_level=tracking.escalation_level or 0,
        )

    # -----------------------------------------------------------------
    # Default Config Provisioning
    # -----------------------------------------------------------------

    async def provision_default_configs(self) -> List[DocSLAConfig]:
        """
        Create default SLA configs for a new organization.
        Skips any types that already have an active config.
        Returns the list of newly created configs.
        """
        existing_types = set(
            row[0]
            for row in self.db.query(DocSLAConfig.sla_type)
            .filter(
                DocSLAConfig.organization_id == self.org_id,
                DocSLAConfig.is_active.is_(True),
            )
            .all()
        )

        created: List[DocSLAConfig] = []
        for sla_type_val, defaults in DEFAULT_SLA_TARGETS.items():
            sla_type_str = sla_type_val.value if isinstance(sla_type_val, SLAType) else sla_type_val
            if sla_type_str in existing_types:
                continue

            config = DocSLAConfig(
                organization_id=self.org_id,
                sla_name=defaults["name"],
                sla_type=sla_type_str,
                target_hours=defaults["target_hours"],
                warning_threshold_pct=defaults["warning_pct"],
                business_hours_only=defaults["business_hours_only"],
                business_hours_start=8,
                business_hours_end=18,
                exclude_weekends=True,
                exclude_holidays=True,
                escalation_enabled=True,
                escalation_chain=defaults["escalation_chain"],
                is_active=True,
            )
            self.db.add(config)
            created.append(config)

        if created:
            self.db.flush()
            logger.info(
                "Provisioned %d default SLA configs for org %s",
                len(created),
                self.org_id,
            )

        return created

    # -----------------------------------------------------------------
    # Timer Lifecycle
    # -----------------------------------------------------------------

    async def start_sla(
        self,
        sla_type: str,
        entity_type: str,
        entity_id: int,
        loan_id: int,
        document_id: Optional[int] = None,
        assigned_to_user_id: Optional[int] = None,
    ) -> DocSLATracking:
        """
        Start an SLA timer for a specific entity.

        Looks up the active SLA config for the given type. Calculates
        target_at and warning_at using business hours if applicable.

        Raises ValueError if no active config exists for the SLA type.
        """
        config = self._get_config(sla_type)
        if not config:
            # Auto-provision defaults if none exist, then retry
            await self.provision_default_configs()
            config = self._get_config(sla_type)
            if not config:
                raise ValueError(
                    f"No active SLA config for type '{sla_type}' in org {self.org_id}"
                )

        now = self._utcnow()
        calc = self._build_calculator(config)

        target_at = calc.add_business_hours(now, config.target_hours)
        warning_hours = config.target_hours * (config.warning_threshold_pct or 75.0) / 100.0
        warning_at = calc.add_business_hours(now, warning_hours)

        tracking = DocSLATracking(
            organization_id=self.org_id,
            sla_config_id=config.id,
            loan_id=loan_id,
            document_id=document_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status=SLATimerStatus.ACTIVE,
            started_at=now,
            target_at=target_at,
            warning_at=warning_at,
            elapsed_business_hours=0.0,
            breached=False,
            total_paused_hours=0.0,
            assigned_to_user_id=assigned_to_user_id,
            escalation_level=0,
        )
        self.db.add(tracking)
        self.db.flush()

        logger.info(
            "Started SLA %s (id=%s) for %s/%s on loan %s — target %s",
            sla_type,
            tracking.id,
            entity_type,
            entity_id,
            loan_id,
            target_at.isoformat(),
        )
        return tracking

    async def check_sla_status(self, tracking_id: int) -> SLAStatus:
        """
        Check the current status of an SLA timer.

        Raises ValueError if tracking record not found.
        """
        tracking = self._get_tracking(tracking_id)
        if not tracking:
            raise ValueError(f"SLA tracking {tracking_id} not found in org {self.org_id}")

        config = self.db.query(DocSLAConfig).get(tracking.sla_config_id)
        if not config:
            raise ValueError(f"SLA config {tracking.sla_config_id} not found")

        return self._compute_status(tracking, config)

    async def complete_sla(self, tracking_id: int) -> SLAStatus:
        """
        Mark an SLA timer as completed (MET or BREACHED based on elapsed time).

        Returns the final SLAStatus.
        Raises ValueError if tracking record not found or already completed.
        """
        tracking = self._get_tracking(tracking_id)
        if not tracking:
            raise ValueError(f"SLA tracking {tracking_id} not found in org {self.org_id}")
        if tracking.status in (SLATimerStatus.MET, SLATimerStatus.BREACHED, SLATimerStatus.CANCELLED):
            raise ValueError(f"SLA tracking {tracking_id} already in terminal state: {tracking.status}")

        config = self.db.query(DocSLAConfig).get(tracking.sla_config_id)
        if not config:
            raise ValueError(f"SLA config {tracking.sla_config_id} not found")

        now = self._utcnow()
        calc = self._build_calculator(config)

        # If paused, account for pause time up to now
        if tracking.status == SLATimerStatus.PAUSED and tracking.paused_at:
            pause_duration = calc.calculate_elapsed(tracking.paused_at, now)
            tracking.total_paused_hours = (tracking.total_paused_hours or 0.0) + pause_duration
            tracking.paused_at = None
            tracking.pause_reason = None

        elapsed = calc.calculate_elapsed(tracking.started_at, now)
        elapsed -= tracking.total_paused_hours or 0.0
        elapsed = max(elapsed, 0.0)

        breached = elapsed >= config.target_hours
        tracking.status = SLATimerStatus.BREACHED if breached else SLATimerStatus.MET
        tracking.completed_at = now
        tracking.breached = breached
        tracking.elapsed_business_hours = round(elapsed, 4)

        self.db.flush()

        logger.info(
            "Completed SLA %s (id=%s): %s in %.2f hours (target %.2f)",
            config.sla_type,
            tracking_id,
            tracking.status,
            elapsed,
            config.target_hours,
        )
        return self._compute_status(tracking, config)

    async def pause_sla(self, tracking_id: int, reason: str) -> None:
        """
        Pause an active SLA timer.

        Time stops accruing while paused. Typical reasons: awaiting borrower,
        awaiting third-party, system outage.

        Raises ValueError if not in ACTIVE state.
        """
        tracking = self._get_tracking(tracking_id)
        if not tracking:
            raise ValueError(f"SLA tracking {tracking_id} not found in org {self.org_id}")
        if tracking.status != SLATimerStatus.ACTIVE:
            raise ValueError(f"Cannot pause SLA in state {tracking.status}")

        now = self._utcnow()
        tracking.status = SLATimerStatus.PAUSED
        tracking.paused_at = now
        tracking.pause_reason = reason[:200] if reason else None

        self.db.flush()
        logger.info("Paused SLA %s: %s", tracking_id, reason)

    async def resume_sla(self, tracking_id: int) -> None:
        """
        Resume a paused SLA timer.

        Adds the paused duration to total_paused_hours and recalculates
        target_at / warning_at to account for the pause.

        Raises ValueError if not in PAUSED state.
        """
        tracking = self._get_tracking(tracking_id)
        if not tracking:
            raise ValueError(f"SLA tracking {tracking_id} not found in org {self.org_id}")
        if tracking.status != SLATimerStatus.PAUSED:
            raise ValueError(f"Cannot resume SLA in state {tracking.status}")

        now = self._utcnow()
        config = self.db.query(DocSLAConfig).get(tracking.sla_config_id)
        if not config:
            raise ValueError(f"SLA config {tracking.sla_config_id} not found")

        calc = self._build_calculator(config)

        # Calculate how long we were paused
        paused_at = tracking.paused_at or now
        if config.business_hours_only:
            pause_hours = calc.calculate_elapsed(paused_at, now)
        else:
            pause_hours = (now - paused_at).total_seconds() / 3600.0

        tracking.total_paused_hours = (tracking.total_paused_hours or 0.0) + pause_hours
        tracking.status = SLATimerStatus.ACTIVE
        tracking.paused_at = None
        tracking.pause_reason = None

        # Shift target_at and warning_at forward by the pause duration
        pause_delta = timedelta(hours=pause_hours)
        if tracking.target_at:
            tracking.target_at = tracking.target_at + pause_delta
        if tracking.warning_at:
            tracking.warning_at = tracking.warning_at + pause_delta

        self.db.flush()
        logger.info("Resumed SLA %s after %.2f hours paused", tracking_id, pause_hours)

    async def cancel_sla(self, tracking_id: int, reason: Optional[str] = None) -> None:
        """Cancel an SLA timer (e.g., loan cancelled, document no longer needed)."""
        tracking = self._get_tracking(tracking_id)
        if not tracking:
            raise ValueError(f"SLA tracking {tracking_id} not found in org {self.org_id}")
        if tracking.status in (SLATimerStatus.MET, SLATimerStatus.BREACHED, SLATimerStatus.CANCELLED):
            raise ValueError(f"SLA tracking {tracking_id} already terminal: {tracking.status}")

        tracking.status = SLATimerStatus.CANCELLED
        tracking.completed_at = self._utcnow()
        if reason:
            tracking.pause_reason = reason[:200]

        self.db.flush()
        logger.info("Cancelled SLA %s: %s", tracking_id, reason or "no reason")

    async def exempt_sla(
        self,
        tracking_id: int,
        reason: str,
        exempted_by_user_id: int,
    ) -> None:
        """
        Mark an SLA timer as exempt (with approval).

        Exempt SLAs are excluded from compliance rate calculations.
        """
        tracking = self._get_tracking(tracking_id)
        if not tracking:
            raise ValueError(f"SLA tracking {tracking_id} not found in org {self.org_id}")

        tracking.exempted = True
        tracking.exemption_reason = reason[:200] if reason else None
        tracking.exempted_by_user_id = exempted_by_user_id

        self.db.flush()
        logger.info(
            "Exempted SLA %s by user %s: %s",
            tracking_id,
            exempted_by_user_id,
            reason,
        )

    # -----------------------------------------------------------------
    # Active SLA Queries
    # -----------------------------------------------------------------

    async def get_active_slas(
        self,
        loan_id: Optional[int] = None,
        sla_type: Optional[str] = None,
        assigned_to_user_id: Optional[int] = None,
        include_paused: bool = True,
        limit: int = 200,
    ) -> List[SLAStatus]:
        """
        Get active SLA timers with current status, optionally filtered.
        """
        query = (
            self.db.query(DocSLATracking, DocSLAConfig)
            .join(DocSLAConfig, DocSLATracking.sla_config_id == DocSLAConfig.id)
            .filter(DocSLATracking.organization_id == self.org_id)
        )

        active_states = [SLATimerStatus.ACTIVE]
        if include_paused:
            active_states.append(SLATimerStatus.PAUSED)
        query = query.filter(DocSLATracking.status.in_(active_states))

        if loan_id is not None:
            query = query.filter(DocSLATracking.loan_id == loan_id)
        if sla_type:
            query = query.filter(DocSLAConfig.sla_type == sla_type)
        if assigned_to_user_id is not None:
            query = query.filter(DocSLATracking.assigned_to_user_id == assigned_to_user_id)

        query = query.order_by(DocSLATracking.target_at.asc()).limit(limit)

        results: List[SLAStatus] = []
        for tracking, config in query.all():
            results.append(self._compute_status(tracking, config))

        return results

    # -----------------------------------------------------------------
    # SLA Dashboard
    # -----------------------------------------------------------------

    async def get_sla_dashboard(self) -> SLADashboard:
        """
        Build aggregated SLA dashboard for the organization.

        Includes:
        - Counts by status
        - Compliance rate
        - Active SLA list with time remaining
        - At-risk SLAs (past warning threshold)
        - Breakdown by SLA type
        - Trend data (current vs prior 30-day period)
        """
        now = self._utcnow()

        # ---- Counts by status (last 90 days to keep scope bounded) ----
        ninety_days_ago = now - timedelta(days=90)
        status_counts = dict(
            self.db.query(DocSLATracking.status, func.count(DocSLATracking.id))
            .filter(
                DocSLATracking.organization_id == self.org_id,
                DocSLATracking.started_at >= ninety_days_ago,
                DocSLATracking.exempted.is_(False),
            )
            .group_by(DocSLATracking.status)
            .all()
        )

        active_count = status_counts.get(SLATimerStatus.ACTIVE, 0) + status_counts.get(SLATimerStatus.PAUSED, 0)
        met_count = status_counts.get(SLATimerStatus.MET, 0)
        breached_count = status_counts.get(SLATimerStatus.BREACHED, 0)
        paused_count = status_counts.get(SLATimerStatus.PAUSED, 0)
        completed = met_count + breached_count
        compliance_rate = (met_count / completed * 100.0) if completed > 0 else 100.0

        # ---- Active SLAs ----
        active_slas = await self.get_active_slas(include_paused=True)

        # ---- At-risk (past warning threshold) ----
        at_risk = [s for s in active_slas if s.is_warning and not s.is_breached]

        # ---- By type ----
        by_type_rows = (
            self.db.query(
                DocSLAConfig.sla_type,
                DocSLATracking.status,
                func.count(DocSLATracking.id),
                func.avg(DocSLATracking.elapsed_business_hours),
            )
            .join(DocSLAConfig, DocSLATracking.sla_config_id == DocSLAConfig.id)
            .filter(
                DocSLATracking.organization_id == self.org_id,
                DocSLATracking.started_at >= ninety_days_ago,
                DocSLATracking.exempted.is_(False),
            )
            .group_by(DocSLAConfig.sla_type, DocSLATracking.status)
            .all()
        )

        by_type: Dict[str, Dict[str, Any]] = {}
        for sla_type_val, status, count, avg_hours in by_type_rows:
            if sla_type_val not in by_type:
                by_type[sla_type_val] = {"met": 0, "breached": 0, "active": 0, "avg_hours": 0.0}
            if status == SLATimerStatus.MET:
                by_type[sla_type_val]["met"] = count
                by_type[sla_type_val]["avg_hours"] = round(float(avg_hours or 0), 2)
            elif status == SLATimerStatus.BREACHED:
                by_type[sla_type_val]["breached"] = count
            elif status in (SLATimerStatus.ACTIVE, SLATimerStatus.PAUSED):
                by_type[sla_type_val]["active"] += count

        for vals in by_type.values():
            total_done = vals["met"] + vals["breached"]
            vals["compliance_rate"] = round(vals["met"] / total_done * 100, 1) if total_done > 0 else 100.0

        # ---- Trending (current 30d vs prior 30d) ----
        trending = await self._calculate_trend(now)

        return SLADashboard(
            active_count=active_count,
            met_count=met_count,
            breached_count=breached_count,
            paused_count=paused_count,
            compliance_rate=round(compliance_rate, 1),
            active_slas=active_slas,
            by_type=by_type,
            at_risk=at_risk,
            trending=trending,
        )

    async def _calculate_trend(self, now: datetime) -> Dict[str, Any]:
        """Compare current 30-day window to prior 30-day window."""
        current_start = now - timedelta(days=30)
        prior_start = now - timedelta(days=60)

        def _period_stats(start: datetime, end: datetime) -> Tuple[int, int]:
            met = (
                self.db.query(func.count(DocSLATracking.id))
                .filter(
                    DocSLATracking.organization_id == self.org_id,
                    DocSLATracking.status == SLATimerStatus.MET,
                    DocSLATracking.completed_at >= start,
                    DocSLATracking.completed_at < end,
                    DocSLATracking.exempted.is_(False),
                )
                .scalar()
            ) or 0
            breached = (
                self.db.query(func.count(DocSLATracking.id))
                .filter(
                    DocSLATracking.organization_id == self.org_id,
                    DocSLATracking.status == SLATimerStatus.BREACHED,
                    DocSLATracking.completed_at >= start,
                    DocSLATracking.completed_at < end,
                    DocSLATracking.exempted.is_(False),
                )
                .scalar()
            ) or 0
            return met, breached

        curr_met, curr_breached = _period_stats(current_start, now)
        prior_met, prior_breached = _period_stats(prior_start, current_start)

        curr_total = curr_met + curr_breached
        prior_total = prior_met + prior_breached
        curr_rate = (curr_met / curr_total * 100.0) if curr_total > 0 else 100.0
        prior_rate = (prior_met / prior_total * 100.0) if prior_total > 0 else 100.0

        delta = round(curr_rate - prior_rate, 1)
        direction = "improving" if delta > 0 else "declining" if delta < 0 else "stable"

        return {
            "current_period_compliance": round(curr_rate, 1),
            "prior_period_compliance": round(prior_rate, 1),
            "delta_pct": delta,
            "direction": direction,
            "current_period_total": curr_total,
            "prior_period_total": prior_total,
        }

    # -----------------------------------------------------------------
    # Per-User Performance
    # -----------------------------------------------------------------

    async def get_user_performance(
        self,
        days: int = 30,
        limit: int = 50,
    ) -> List[UserSLAPerformance]:
        """
        Get per-user SLA performance metrics, ranked by compliance rate.
        """
        cutoff = self._utcnow() - timedelta(days=days)

        rows = (
            self.db.query(
                DocSLATracking.assigned_to_user_id,
                func.count(DocSLATracking.id).label("total"),
                func.count(
                    case(
                        (DocSLATracking.status == SLATimerStatus.MET, DocSLATracking.id),
                    )
                ).label("met"),
                func.count(
                    case(
                        (DocSLATracking.status == SLATimerStatus.BREACHED, DocSLATracking.id),
                    )
                ).label("breached"),
                func.avg(DocSLATracking.elapsed_business_hours).label("avg_hours"),
            )
            .filter(
                DocSLATracking.organization_id == self.org_id,
                DocSLATracking.assigned_to_user_id.isnot(None),
                DocSLATracking.status.in_([SLATimerStatus.MET, SLATimerStatus.BREACHED]),
                DocSLATracking.completed_at >= cutoff,
                DocSLATracking.exempted.is_(False),
            )
            .group_by(DocSLATracking.assigned_to_user_id)
            .having(func.count(DocSLATracking.id) > 0)
            .order_by(
                (
                    func.count(case((DocSLATracking.status == SLATimerStatus.MET, DocSLATracking.id)))
                    * 100.0
                    / func.count(DocSLATracking.id)
                ).desc()
            )
            .limit(limit)
            .all()
        )

        # Look up user names
        user_ids = [r[0] for r in rows if r[0]]
        user_names: Dict[int, str] = {}
        if user_ids:
            try:
                from database.models.core import User
                users = (
                    self.db.query(User.id, User.first_name, User.last_name)
                    .filter(User.id.in_(user_ids))
                    .all()
                )
                for uid, fn, ln in users:
                    user_names[uid] = f"{fn or ''} {ln or ''}".strip() or f"User {uid}"
            except Exception as _exc:  # noqa: BLE001
                pass

        results: List[UserSLAPerformance] = []
        for rank_idx, (user_id, total, met, breached, avg_hours) in enumerate(rows, 1):
            compliance = (met / total * 100.0) if total > 0 else 100.0
            results.append(UserSLAPerformance(
                user_id=user_id,
                user_name=user_names.get(user_id, f"User {user_id}"),
                total_completed=total,
                total_met=met,
                total_breached=breached,
                compliance_rate=round(compliance, 1),
                avg_completion_hours=round(float(avg_hours or 0), 2),
                rank=rank_idx,
            ))

        return results

    # -----------------------------------------------------------------
    # Compliance Reporting
    # -----------------------------------------------------------------

    async def get_compliance_report(
        self,
        start_date: date,
        end_date: date,
    ) -> ComplianceReport:
        """
        Generate SLA compliance report for a date range.

        Includes overall stats, breakdown by type, by user, breach root-cause
        analysis, time-in-queue analysis, and trend vs prior period.
        """
        start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
        period_days = (end_date - start_date).days or 1

        # ---- Overall ----
        base_filter = and_(
            DocSLATracking.organization_id == self.org_id,
            DocSLATracking.completed_at >= start_dt,
            DocSLATracking.completed_at <= end_dt,
            DocSLATracking.status.in_([SLATimerStatus.MET, SLATimerStatus.BREACHED]),
            DocSLATracking.exempted.is_(False),
        )

        overall = self.db.query(
            func.count(DocSLATracking.id),
            func.count(case((DocSLATracking.status == SLATimerStatus.MET, DocSLATracking.id))),
            func.count(case((DocSLATracking.status == SLATimerStatus.BREACHED, DocSLATracking.id))),
            func.avg(DocSLATracking.elapsed_business_hours),
        ).filter(base_filter).first()

        total, total_met, total_breached, avg_hours = overall or (0, 0, 0, 0.0)
        compliance_rate = (total_met / total * 100.0) if total > 0 else 100.0

        # ---- By type ----
        type_rows = (
            self.db.query(
                DocSLAConfig.sla_type,
                func.count(DocSLATracking.id),
                func.count(case((DocSLATracking.status == SLATimerStatus.MET, DocSLATracking.id))),
                func.count(case((DocSLATracking.status == SLATimerStatus.BREACHED, DocSLATracking.id))),
                func.avg(DocSLATracking.elapsed_business_hours),
            )
            .join(DocSLAConfig, DocSLATracking.sla_config_id == DocSLAConfig.id)
            .filter(base_filter)
            .group_by(DocSLAConfig.sla_type)
            .all()
        )

        by_type: Dict[str, Dict[str, Any]] = {}
        for sla_type_val, cnt, met, breached, avg_h in type_rows:
            by_type[sla_type_val] = {
                "total": cnt,
                "met": met,
                "breached": breached,
                "compliance_rate": round(met / cnt * 100, 1) if cnt > 0 else 100.0,
                "avg_hours": round(float(avg_h or 0), 2),
            }

        # ---- By user ----
        user_perf = await self.get_user_performance(days=period_days)
        by_user = [
            {
                "user_id": u.user_id,
                "user_name": u.user_name,
                "total": u.total_completed,
                "met": u.total_met,
                "breached": u.total_breached,
                "compliance_rate": u.compliance_rate,
                "avg_hours": u.avg_completion_hours,
                "rank": u.rank,
            }
            for u in user_perf
        ]

        # ---- Breach analysis (root-cause by entity_type and sla_type) ----
        breach_rows = (
            self.db.query(
                DocSLAConfig.sla_type,
                DocSLATracking.entity_type,
                func.count(DocSLATracking.id),
                func.avg(DocSLATracking.elapsed_business_hours),
            )
            .join(DocSLAConfig, DocSLATracking.sla_config_id == DocSLAConfig.id)
            .filter(
                base_filter,
                DocSLATracking.status == SLATimerStatus.BREACHED,
            )
            .group_by(DocSLAConfig.sla_type, DocSLATracking.entity_type)
            .order_by(func.count(DocSLATracking.id).desc())
            .all()
        )

        breach_analysis = [
            {
                "sla_type": sla_type_val,
                "entity_type": entity_type,
                "count": count,
                "avg_hours_over": round(float(avg_h or 0), 2),
            }
            for sla_type_val, entity_type, count, avg_h in breach_rows
        ]

        # ---- Time-in-queue by SLA type ----
        queue_rows = (
            self.db.query(
                DocSLAConfig.sla_type,
                func.avg(DocSLATracking.elapsed_business_hours),
            )
            .join(DocSLAConfig, DocSLATracking.sla_config_id == DocSLAConfig.id)
            .filter(base_filter)
            .group_by(DocSLAConfig.sla_type)
            .all()
        )
        time_in_queue = {
            sla_type_val: round(float(avg_h or 0), 2) for sla_type_val, avg_h in queue_rows
        }

        # ---- Trend vs prior period ----
        prior_start = start_date - timedelta(days=period_days)
        prior_end = start_date - timedelta(days=1)
        prior_start_dt = datetime(prior_start.year, prior_start.month, prior_start.day, tzinfo=timezone.utc)
        prior_end_dt = datetime(prior_end.year, prior_end.month, prior_end.day, 23, 59, 59, tzinfo=timezone.utc)

        prior_overall = self.db.query(
            func.count(DocSLATracking.id),
            func.count(case((DocSLATracking.status == SLATimerStatus.MET, DocSLATracking.id))),
        ).filter(
            DocSLATracking.organization_id == self.org_id,
            DocSLATracking.completed_at >= prior_start_dt,
            DocSLATracking.completed_at <= prior_end_dt,
            DocSLATracking.status.in_([SLATimerStatus.MET, SLATimerStatus.BREACHED]),
            DocSLATracking.exempted.is_(False),
        ).first()

        prior_total, prior_met = prior_overall or (0, 0)
        prior_rate = (prior_met / prior_total * 100.0) if prior_total > 0 else 100.0
        delta = round(compliance_rate - prior_rate, 1)

        trend_vs_prior = {
            "prior_period": f"{prior_start.isoformat()} to {prior_end.isoformat()}",
            "prior_compliance_rate": round(prior_rate, 1),
            "current_compliance_rate": round(compliance_rate, 1),
            "delta_pct": delta,
            "direction": "improving" if delta > 0 else "declining" if delta < 0 else "stable",
        }

        return ComplianceReport(
            period_start=start_date,
            period_end=end_date,
            total_completed=total,
            total_met=total_met,
            total_breached=total_breached,
            compliance_rate=round(compliance_rate, 1),
            avg_completion_hours=round(float(avg_hours or 0), 2),
            by_type=by_type,
            by_user=by_user,
            breach_analysis=breach_analysis,
            time_in_queue=time_in_queue,
            trend_vs_prior=trend_vs_prior,
        )

    # -----------------------------------------------------------------
    # SLA Check Cycle (Batch Warning / Breach Detection)
    # -----------------------------------------------------------------

    async def run_sla_check_cycle(self) -> List[SLAAlert]:
        """
        Run a batch check on all active SLAs for this organization.

        For each active timer:
        1. Calculate current elapsed business hours.
        2. If past warning threshold but not yet notified at that level, emit WARNING.
        3. If past 100% target, mark as BREACHED and emit BREACH alert.
        4. If past escalation thresholds (150%, 200%), escalate and emit ESCALATION alert.

        Returns a list of SLAAlert objects that should be dispatched
        (notifications, emails, escalation engine triggers).
        """
        now = self._utcnow()
        alerts: List[SLAAlert] = []

        # Fetch all active (non-paused, non-exempt) tracking records
        active_records = (
            self.db.query(DocSLATracking, DocSLAConfig)
            .join(DocSLAConfig, DocSLATracking.sla_config_id == DocSLAConfig.id)
            .filter(
                DocSLATracking.organization_id == self.org_id,
                DocSLATracking.status == SLATimerStatus.ACTIVE,
                DocSLATracking.exempted.is_(False),
            )
            .all()
        )

        for tracking, config in active_records:
            calc = self._build_calculator(config)
            elapsed = calc.calculate_elapsed(tracking.started_at, now)
            elapsed -= tracking.total_paused_hours or 0.0
            elapsed = max(elapsed, 0.0)

            target = config.target_hours
            if target <= 0:
                continue

            pct = elapsed / target * 100.0
            warning_pct = config.warning_threshold_pct or 75.0
            chain = config.escalation_chain or []
            current_level = tracking.escalation_level or 0

            # --- Breach detection ---
            if pct >= 100.0 and not tracking.breached:
                tracking.breached = True
                tracking.status = SLATimerStatus.BREACHED
                tracking.completed_at = now
                tracking.elapsed_business_hours = round(elapsed, 4)

                notify_role = self._chain_role_at_pct(chain, 100.0)
                alerts.append(SLAAlert(
                    tracking_id=tracking.id,
                    sla_type=config.sla_type,
                    alert_type="BREACH",
                    loan_id=tracking.loan_id,
                    entity_type=tracking.entity_type or "",
                    entity_id=tracking.entity_id,
                    pct_elapsed=round(pct, 1),
                    escalation_level=current_level,
                    notify_role=notify_role,
                    message=(
                        f"SLA BREACHED: {config.sla_name} for loan {tracking.loan_id} "
                        f"({round(elapsed, 1)}h elapsed, target {target}h)"
                    ),
                ))
                logger.warning(
                    "SLA BREACH: %s (id=%s) loan=%s elapsed=%.2fh target=%.2fh",
                    config.sla_type, tracking.id, tracking.loan_id, elapsed, target,
                )
                # Fall through to escalation checks — post-breach escalation
                # (150%, 200%) must still fire for senior management notification

            # --- Warning detection ---
            if pct >= warning_pct and current_level == 0:
                tracking.escalation_level = 1
                tracking.last_escalation_at = now

                notify_role = self._chain_role_at_pct(chain, warning_pct)
                alerts.append(SLAAlert(
                    tracking_id=tracking.id,
                    sla_type=config.sla_type,
                    alert_type="WARNING",
                    loan_id=tracking.loan_id,
                    entity_type=tracking.entity_type or "",
                    entity_id=tracking.entity_id,
                    pct_elapsed=round(pct, 1),
                    escalation_level=1,
                    notify_role=notify_role,
                    message=(
                        f"SLA WARNING: {config.sla_name} for loan {tracking.loan_id} "
                        f"at {round(pct, 0)}% ({round(elapsed, 1)}h / {target}h)"
                    ),
                ))

            # --- Additional escalation levels ---
            for step in sorted(chain, key=lambda s: s.get("at_pct", 0)):
                step_pct = step.get("at_pct", 0)
                step_level = chain.index(step) + 1
                if step_pct > warning_pct and pct >= step_pct and current_level < step_level:
                    tracking.escalation_level = step_level
                    tracking.last_escalation_at = now

                    alerts.append(SLAAlert(
                        tracking_id=tracking.id,
                        sla_type=config.sla_type,
                        alert_type="ESCALATION",
                        loan_id=tracking.loan_id,
                        entity_type=tracking.entity_type or "",
                        entity_id=tracking.entity_id,
                        pct_elapsed=round(pct, 1),
                        escalation_level=step_level,
                        notify_role=step.get("notify", "manager"),
                        message=(
                            f"SLA ESCALATION (L{step_level}): {config.sla_name} "
                            f"for loan {tracking.loan_id} at {round(pct, 0)}%"
                        ),
                    ))

            # Update elapsed for tracking record
            tracking.elapsed_business_hours = round(elapsed, 4)

        self.db.flush()

        if alerts:
            logger.info(
                "SLA check cycle for org %s: %d alerts (%d warnings, %d breaches, %d escalations)",
                self.org_id,
                len(alerts),
                len([a for a in alerts if a.alert_type == "WARNING"]),
                len([a for a in alerts if a.alert_type == "BREACH"]),
                len([a for a in alerts if a.alert_type == "ESCALATION"]),
            )

        return alerts

    def _chain_role_at_pct(self, chain: List[Dict], target_pct: float) -> str:
        """Find the notify role in the escalation chain closest to target_pct."""
        if not chain:
            return "manager"

        best_role = chain[0].get("notify", "manager")
        best_pct = 0.0

        for step in chain:
            step_pct = step.get("at_pct", 0)
            if step_pct <= target_pct and step_pct >= best_pct:
                best_pct = step_pct
                best_role = step.get("notify", "manager")

        return best_role

    # -----------------------------------------------------------------
    # SLA Config Management
    # -----------------------------------------------------------------

    async def get_configs(self, active_only: bool = True) -> List[DocSLAConfig]:
        """Get all SLA configs for this org."""
        query = self.db.query(DocSLAConfig).filter(
            DocSLAConfig.organization_id == self.org_id,
        )
        if active_only:
            query = query.filter(DocSLAConfig.is_active.is_(True))
        return query.order_by(DocSLAConfig.sla_type).all()

    async def update_config(
        self,
        config_id: int,
        updates: Dict[str, Any],
    ) -> DocSLAConfig:
        """
        Update an SLA config. Only allowed fields are modified.

        Does NOT retroactively change existing active timers.
        """
        config = (
            self.db.query(DocSLAConfig)
            .filter(
                DocSLAConfig.id == config_id,
                DocSLAConfig.organization_id == self.org_id,
            )
            .first()
        )
        if not config:
            raise ValueError(f"SLA config {config_id} not found in org {self.org_id}")

        allowed_fields = {
            "sla_name", "target_hours", "warning_threshold_pct",
            "business_hours_only", "business_hours_start", "business_hours_end",
            "exclude_weekends", "exclude_holidays",
            "escalation_enabled", "escalation_chain", "is_active",
        }

        for key, value in updates.items():
            if key in allowed_fields:
                setattr(config, key, value)

        self.db.flush()
        logger.info("Updated SLA config %s for org %s", config_id, self.org_id)
        return config
