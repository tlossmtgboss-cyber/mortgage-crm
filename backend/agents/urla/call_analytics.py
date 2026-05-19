"""
Perennia AI — URLA Call Analytics
=================================
Aggregate analytics for URLA voice agent sessions.

Computes metrics across all sessions for a tenant within a date range:
  - Completion rates (started -> finalized)
  - Section-level drop-off analysis
  - Average call durations
  - Compliance score distributions
  - Data quality trends
  - Peak calling hours
  - Co-borrower frequency

Data source: Redis scan of urla:{tenant_id}:loan:* keys.
For production at scale, these metrics should be materialized to PostgreSQL
via a periodic job rather than computed on-demand from Redis.
"""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel

from .models import LoanPurpose, URLAApplication
from .state import URLAStateManager

logger = logging.getLogger(__name__)


# ============================================================================
# SECTION ORDERING — canonical progression through the URLA agent
# ============================================================================

SECTION_ORDER: List[str] = [
    "SECTION_1A",
    "SECTION_1B",
    "SECTION_1C",
    "SECTION_1D",
    "SECTION_1E",
    "SECTION_2",
    "SECTION_3",
    "SECTION_4A",
    "SECTION_4B",
    "SECTION_4C",
    "SECTION_4D",
    "SECTION_5A",
    "SECTION_5B",
    "SECTION_7",
    "SECTION_8",
    "COBORROWER_CHECK",
    "SECTION_6",
    "FINAL_SUMMARY",
    "FINALIZED",
]


# ============================================================================
# RESPONSE MODELS
# ============================================================================

class SectionDropoff(BaseModel):
    """Drop-off analysis for a single URLA section."""
    section: str
    started_count: int
    completed_count: int
    drop_off_count: int
    drop_off_rate: float  # 0.0-1.0


class HourlyDistribution(BaseModel):
    """Number of sessions started in a given UTC hour."""
    hour: int  # 0-23
    count: int


class URLACallMetrics(BaseModel):
    """Aggregate analytics for URLA voice agent sessions within a date range."""
    tenant_id: str
    period_start: datetime
    period_end: datetime
    computed_at: datetime

    # Volume
    total_sessions: int
    completed_applications: int
    in_progress_applications: int
    abandoned_applications: int

    # Rates (0.0-1.0)
    completion_rate: float
    abandonment_rate: float
    co_borrower_rate: float

    # Durations (minutes)
    avg_duration_minutes: float
    median_duration_minutes: float
    p90_duration_minutes: float

    # Section analysis
    avg_sections_per_session: float
    section_dropoffs: List[SectionDropoff]
    most_common_drop_off_section: Optional[str]

    # Quality (requires external call_scoring to have run; None until then)
    avg_compliance_score: Optional[float] = None
    avg_data_quality_score: Optional[float] = None
    avg_conversation_quality_score: Optional[float] = None

    # Distribution
    peak_hours: List[HourlyDistribution]

    # Loan characteristics
    avg_loan_amount: Optional[float] = None
    purchase_vs_refi_ratio: Optional[float] = None  # purchase_count / refi_count, None if no refis

    # Errors
    bytepro_push_failure_rate: float


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def compute_analytics(
    tenant_id: str,
    start: datetime,
    end: datetime,
    redis_url: Optional[str] = None,
) -> URLACallMetrics:
    """
    Scan Redis for all URLA applications belonging to *tenant_id* whose
    ``created_at`` falls within [start, end], then compute aggregate metrics.

    Parameters
    ----------
    tenant_id : str
        Multi-tenant scope.
    start : datetime
        Inclusive lower bound (UTC).
    end : datetime
        Inclusive upper bound (UTC).
    redis_url : str, optional
        Override the default REDIS_URL for testing.

    Returns
    -------
    URLACallMetrics
        Fully populated analytics payload.
    """
    state = URLAStateManager(redis_url=redis_url) if redis_url else URLAStateManager()
    try:
        await state.connect()
        apps = await _scan_applications(state, tenant_id, start, end)
    finally:
        await state.close()

    return _build_metrics(tenant_id, start, end, apps)


# ============================================================================
# REDIS SCAN
# ============================================================================

async def _scan_applications(
    state: URLAStateManager,
    tenant_id: str,
    start: datetime,
    end: datetime,
) -> List[URLAApplication]:
    """
    Iterate over all ``urla:{tenant_id}:loan:*`` keys via SCAN and
    deserialize + filter by date range.

    Uses ``state.load_application()`` rather than raw ``redis.get()`` so
    encryption is handled transparently by the state manager.
    """
    apps: List[URLAApplication] = []
    pattern = f"urla:{tenant_id}:loan:*"
    prefix = f"urla:{tenant_id}:loan:"

    # Ensure start/end are tz-aware for comparison
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    async for key in state.redis.scan_iter(match=pattern, count=100):
        # Extract loan_id from the key
        loan_id = key[len(prefix):] if isinstance(key, str) else key.decode()[len(prefix):]
        if not loan_id:
            continue

        try:
            app = await state.load_application(tenant_id, loan_id)
        except Exception as _exc:  # noqa: BLE001
            logger.warning("Failed to deserialize URLA record %s", key, exc_info=True)
            continue

        if app is None:
            continue

        # Ensure created_at is tz-aware
        created = app.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        if start <= created <= end:
            apps.append(app)

    logger.info(
        "URLA analytics scan: tenant=%s period=%s..%s found=%d",
        tenant_id, start.date(), end.date(), len(apps),
    )
    return apps


# ============================================================================
# METRIC BUILDERS
# ============================================================================

def _build_metrics(
    tenant_id: str,
    start: datetime,
    end: datetime,
    apps: List[URLAApplication],
) -> URLACallMetrics:
    """Assemble all sub-metrics into the final URLACallMetrics payload."""
    total = len(apps)

    completed = [a for a in apps if a.is_finalized]
    in_progress = [a for a in apps if not a.is_finalized and _is_in_progress(a)]
    abandoned = [a for a in apps if not a.is_finalized and not _is_in_progress(a)]

    duration_stats = compute_duration_stats(apps)
    dropoffs = compute_section_dropoffs(apps)
    hourly = compute_hourly_distribution(apps)
    loan_chars = compute_loan_characteristics(apps)

    # Most common drop-off: the section with the highest drop_off_count
    # among non-terminal sections (exclude FINALIZED which has 0 by definition)
    most_common_dropoff: Optional[str] = None
    if dropoffs:
        candidate = max(
            (d for d in dropoffs if d.section != "FINALIZED"),
            key=lambda d: d.drop_off_count,
            default=None,
        )
        if candidate and candidate.drop_off_count > 0:
            most_common_dropoff = candidate.section

    # BytePro push failure rate: finalized apps that never got a bytepro_loan_number
    finalized_count = len(completed)
    bytepro_failures = sum(
        1 for a in completed if not a.bytepro_loan_number
    )
    bytepro_failure_rate = (
        bytepro_failures / finalized_count if finalized_count > 0 else 0.0
    )

    # Co-borrower rate
    co_borrower_count = sum(1 for a in apps if len(a.borrowers) > 1)

    return URLACallMetrics(
        tenant_id=tenant_id,
        period_start=start,
        period_end=end,
        computed_at=datetime.now(timezone.utc),
        # Volume
        total_sessions=total,
        completed_applications=len(completed),
        in_progress_applications=len(in_progress),
        abandoned_applications=len(abandoned),
        # Rates
        completion_rate=len(completed) / total if total > 0 else 0.0,
        abandonment_rate=len(abandoned) / total if total > 0 else 0.0,
        co_borrower_rate=co_borrower_count / total if total > 0 else 0.0,
        # Durations
        avg_duration_minutes=duration_stats["avg"],
        median_duration_minutes=duration_stats["median"],
        p90_duration_minutes=duration_stats["p90"],
        # Section analysis
        avg_sections_per_session=_avg_sections(apps),
        section_dropoffs=dropoffs,
        most_common_drop_off_section=most_common_dropoff,
        # Quality — not yet computed; requires external scoring pipeline
        avg_compliance_score=None,
        avg_data_quality_score=None,
        avg_conversation_quality_score=None,
        # Distribution
        peak_hours=hourly,
        # Loan characteristics
        avg_loan_amount=loan_chars.get("avg_loan_amount"),
        purchase_vs_refi_ratio=loan_chars.get("purchase_vs_refi_ratio"),
        # Errors
        bytepro_push_failure_rate=bytepro_failure_rate,
    )


def _is_in_progress(app: URLAApplication) -> bool:
    """
    An application is "in progress" if its current_section indicates
    active work (not START, not a PAUSED-then-expired state with no
    completed sections).
    """
    if app.current_section == "START" and not app.completed_sections:
        return False
    if app.current_section == "COMPLETE":
        return False
    # If the session has at least one completed section or moved past START,
    # treat it as in-progress rather than abandoned.
    return bool(app.completed_sections) or app.current_section != "START"


# ============================================================================
# SECTION DROP-OFF ANALYSIS
# ============================================================================

def compute_section_dropoffs(apps: List[URLAApplication]) -> List[SectionDropoff]:
    """
    For each section in the canonical order, count how many applications
    *reached* that section (started_count) and how many *completed* it
    (completed_count). The difference is the drop-off at that section.

    An application "reached" section N if it completed section N-1 (or if
    N is the first section). An application "completed" section N if that
    section name appears in ``completed_sections``.
    """
    if not apps:
        return []

    results: List[SectionDropoff] = []

    for idx, section in enumerate(SECTION_ORDER):
        if idx == 0:
            # Every application that exists reached the first section
            started = len(apps)
        else:
            # Reached this section = completed the previous one
            prev_section = SECTION_ORDER[idx - 1]
            started = sum(
                1 for a in apps if prev_section in a.completed_sections
            )

        completed = sum(1 for a in apps if section in a.completed_sections)
        drop_off = max(started - completed, 0)
        drop_off_rate = drop_off / started if started > 0 else 0.0

        results.append(SectionDropoff(
            section=section,
            started_count=started,
            completed_count=completed,
            drop_off_count=drop_off,
            drop_off_rate=round(drop_off_rate, 4),
        ))

    return results


# ============================================================================
# DURATION STATISTICS
# ============================================================================

def compute_duration_stats(apps: List[URLAApplication]) -> Dict[str, float]:
    """
    Calculate session duration from ``created_at`` to ``finalized_at``
    (for finalized apps) or ``updated_at`` (for in-progress/abandoned apps).

    Returns dict with ``avg``, ``median``, ``p90`` in minutes.
    All values are 0.0 if no applications are provided.
    """
    if not apps:
        return {"avg": 0.0, "median": 0.0, "p90": 0.0}

    durations_minutes: List[float] = []

    for app in apps:
        start = app.created_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        # Use finalized_at for completed apps, updated_at otherwise
        end = app.finalized_at if app.finalized_at else app.updated_at
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        delta = end - start
        minutes = max(delta.total_seconds() / 60.0, 0.0)
        durations_minutes.append(minutes)

    if not durations_minutes:
        return {"avg": 0.0, "median": 0.0, "p90": 0.0}

    durations_sorted = sorted(durations_minutes)
    avg = statistics.mean(durations_sorted)
    median = statistics.median(durations_sorted)

    # P90: the value below which 90% of observations fall
    p90_idx = int(len(durations_sorted) * 0.9)
    # Clamp to last index for small datasets
    p90_idx = min(p90_idx, len(durations_sorted) - 1)
    p90 = durations_sorted[p90_idx]

    return {
        "avg": round(avg, 2),
        "median": round(median, 2),
        "p90": round(p90, 2),
    }


# ============================================================================
# HOURLY DISTRIBUTION
# ============================================================================

def compute_hourly_distribution(apps: List[URLAApplication]) -> List[HourlyDistribution]:
    """
    Group applications by the UTC hour of ``created_at``.
    Returns a list of 24 entries (hours 0-23), sorted by count descending
    so the first entry is the peak hour.
    """
    counts: Dict[int, int] = {h: 0 for h in range(24)}
    for app in apps:
        hour = app.created_at.hour
        counts[hour] += 1

    return sorted(
        [HourlyDistribution(hour=h, count=c) for h, c in counts.items()],
        key=lambda d: (-d.count, d.hour),
    )


# ============================================================================
# LOAN CHARACTERISTICS
# ============================================================================

def compute_loan_characteristics(apps: List[URLAApplication]) -> Dict[str, Optional[float]]:
    """
    Extract aggregate loan characteristics from Section 4a data.

    Returns
    -------
    dict
        avg_loan_amount : float or None
            Average requested loan amount across apps that have one.
        purchase_vs_refi_ratio : float or None
            purchase_count / refi_count. None if zero refis (avoids division
            by zero). If zero purchases, returns 0.0.
    """
    loan_amounts: List[float] = []
    purchase_count = 0
    refi_count = 0

    for app in apps:
        s4 = app.section_4
        if not s4 or not s4.section_4a:
            continue
        s4a = s4.section_4a

        if s4a.loan_amount is not None:
            loan_amounts.append(float(s4a.loan_amount))

        if s4a.loan_purpose:
            purpose = s4a.loan_purpose
            # loan_purpose is stored as the enum value string due to
            # use_enum_values=True in model_config
            if purpose == LoanPurpose.PURCHASE or purpose == "PURCHASE":
                purchase_count += 1
            elif purpose == LoanPurpose.REFINANCE or purpose == "REFINANCE":
                refi_count += 1

    avg_loan = round(statistics.mean(loan_amounts), 2) if loan_amounts else None

    if refi_count > 0:
        ratio: Optional[float] = round(purchase_count / refi_count, 2)
    elif purchase_count > 0:
        ratio = None  # All purchases, no refis — ratio is undefined
    else:
        ratio = None

    return {
        "avg_loan_amount": avg_loan,
        "purchase_vs_refi_ratio": ratio,
    }


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _avg_sections(apps: List[URLAApplication]) -> float:
    """Average number of completed sections across all applications."""
    if not apps:
        return 0.0
    total_sections = sum(len(a.completed_sections) for a in apps)
    return round(total_sections / len(apps), 2)
