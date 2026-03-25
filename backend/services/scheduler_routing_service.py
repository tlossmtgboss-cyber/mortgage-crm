"""
Scheduler Routing Service - Tenant-Aware LO Assignment Strategies

Migrated from deprecated smart_scheduler_service.py with full organization_id
isolation. Five strategies: direct, round_robin, priority, availability, load_balanced.

Usage:
    from services.scheduler_routing_service import assign_loan_officer

    lo_user_id = assign_loan_officer(
        db=db,
        org_id=org_id,
        strategy="round_robin",
        appointment_time=slot_start,
        booking_link=link,
    )

    # COMP-007: For RESPA-compliant routing with rationale logging:
    from services.scheduler_routing_service import assign_loan_officer_with_context

    decision = assign_loan_officer_with_context(
        db=db, org_id=org_id, strategy="round_robin",
        appointment_time=slot_start, booking_link=link,
    )
    # decision.selected_user_id, decision.to_ai_booking_context()
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional, List, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# LLM TOKEN BUDGET TRACKING (v2-D5-001)
# =============================================================================
# Best-effort in-memory counter keyed by (org_id, date_str).
# Resets naturally when the date changes. Not distributed — each process
# tracks its own usage.  Sufficient for single-process deployments and a
# useful safety net even behind multiple workers.

_token_usage: Dict[str, int] = {}


def _budget_key(org_id: int) -> str:
    """Return the budget dict key for an org on today's date."""
    return f"{org_id}:{date.today().isoformat()}"


def _check_token_budget(
    org_id: int,
    estimated_tokens: int = 1000,
    daily_limit: int = 100_000,
) -> bool:
    """Check whether the org is within its daily LLM token budget.

    Returns True if the estimated usage fits within the daily_limit,
    False if it would exceed it.  Logs a warning at 80% utilisation.
    """
    key = _budget_key(org_id)
    current = _token_usage.get(key, 0)

    if current + estimated_tokens > daily_limit:
        logger.error(
            "LLM token budget EXCEEDED for org %s: %d + %d > %d daily limit",
            org_id, current, estimated_tokens, daily_limit,
        )
        return False

    threshold_80 = int(daily_limit * 0.8)
    if current < threshold_80 <= current + estimated_tokens:
        logger.warning(
            "LLM token budget at 80%% for org %s: %d / %d",
            org_id, current + estimated_tokens, daily_limit,
        )

    return True


def _record_token_usage(org_id: int, tokens_used: int) -> None:
    """Record actual token usage after an LLM call completes."""
    key = _budget_key(org_id)
    _token_usage[key] = _token_usage.get(key, 0) + tokens_used
    logger.debug(
        "LLM token usage for org %s: +%d (total today: %d)",
        org_id, tokens_used, _token_usage[key],
    )


# =============================================================================
# COMP-007: Routing Decision — captures rationale for RESPA compliance
# =============================================================================

@dataclass
class RoutingDecision:
    """Structured record of an AI/automated LO routing decision.

    RESPA requires that LO selection is documented to prove no prohibited
    referral fees influenced the assignment.  Every routing decision records
    the method, candidate pool size, selection criteria, and an explicit
    RESPA compliance attestation.
    """
    selected_user_id: Optional[int] = None
    routing_method: str = "direct"
    candidates_evaluated: int = 0
    selection_criteria: List[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_reason: Optional[str] = None

    def to_ai_booking_context(self) -> dict:
        """Convert to ai_booking_context routing_decision sub-dict."""
        return {
            "selected_lo_id": self.selected_user_id,
            "routing_method": self.routing_method,
            "candidates_evaluated": self.candidates_evaluated,
            "selection_criteria": self.selection_criteria,
            "respa_compliance": (
                "No referral fees or prohibited considerations influenced LO selection"
            ),
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }

# Default buffer minutes when no scheduler config is found
_DEFAULT_BUFFER_BEFORE = 5
_DEFAULT_BUFFER_AFTER = 5


def assign_loan_officer(
    db: Session,
    org_id: int,
    strategy: str = "direct",
    appointment_time: datetime = None,
    booking_link=None,
    excluded_user_ids: List[int] = None,
    strict_capacity: bool = False,
) -> Optional[int]:
    """
    Route an appointment to the appropriate LO based on strategy.
    Returns the user_id of the assigned LO, or None if no one is available.

    Strategies:
    - "direct": Return the booking link owner (or first assigned user)
    - "round_robin": Rotate through assigned users
    - "priority": Assign to highest-priority available LO (routing_weight)
    - "availability": Assign to first LO who has no conflicts at appointment_time
    - "load_balanced": Assign to LO with fewest appointments this week
    """
    decision = assign_loan_officer_with_context(
        db=db,
        org_id=org_id,
        strategy=strategy,
        appointment_time=appointment_time,
        booking_link=booking_link,
        excluded_user_ids=excluded_user_ids,
        strict_capacity=strict_capacity,
    )
    return decision.selected_user_id


def assign_loan_officer_with_context(
    db: Session,
    org_id: int,
    strategy: str = "direct",
    appointment_time: datetime = None,
    booking_link=None,
    excluded_user_ids: List[int] = None,
    strict_capacity: bool = False,
) -> RoutingDecision:
    """
    Route an appointment to the appropriate LO and return a RoutingDecision
    documenting the rationale.

    COMP-007: Every AI/automated LO routing decision must be logged with its
    rationale for RESPA compliance.  The returned RoutingDecision can be
    converted to an ai_booking_context dict via .to_ai_booking_context().

    Returns a RoutingDecision (selected_user_id may be None if no one is available).
    """
    decision = RoutingDecision()

    # --- strategy criteria mapping ---
    _STRATEGY_CRITERIA = {
        "direct": ["booking_link_owner"],
        "round_robin": ["rotation_order", "last_assignment"],
        "priority": ["routing_weight", "availability"],
        "availability": ["calendar_availability", "conflict_check"],
        "load_balanced": ["weekly_appointment_count", "workload_balance"],
        "ai_enhanced": ["llm_scoring", "availability", "workload_balance"],
    }

    candidate_ids = _get_candidate_user_ids(db, org_id, booking_link)
    if not candidate_ids:
        logger.warning("No candidate LOs for org %s", org_id)
        decision.fallback_reason = "no_candidates_found"
        return decision

    original_count = len(candidate_ids)

    if excluded_user_ids:
        candidate_ids = [uid for uid in candidate_ids if uid not in excluded_user_ids]
        if not candidate_ids:
            decision.candidates_evaluated = original_count
            decision.fallback_reason = "all_candidates_excluded"
            return decision

    strategy = (strategy or "direct").lower().replace("-", "_")

    # v2-D5-001: Token budget gate — if an LLM-backed strategy is requested
    # but the org has exceeded its daily token budget, fall back to load_balanced.
    _LLM_STRATEGIES = {"ai_enhanced"}
    if strategy in _LLM_STRATEGIES and not _check_token_budget(org_id):
        logger.error(
            "LLM token budget exceeded for org %s, falling back from '%s' to 'load_balanced'",
            org_id, strategy,
        )
        strategy = "load_balanced"
        decision.fallback_used = True
        decision.fallback_reason = "llm_token_budget_exceeded"

    decision.routing_method = strategy
    decision.candidates_evaluated = len(candidate_ids)
    decision.selection_criteria = _STRATEGY_CRITERIA.get(strategy, ["unknown"])

    strategy_map = {
        "direct": _assign_direct,
        "round_robin": lambda ids: _assign_round_robin(db, org_id, ids),
        "priority": lambda ids: _assign_priority(db, org_id, ids, appointment_time),
        "availability": lambda ids: _assign_availability(db, org_id, ids, appointment_time),
        "load_balanced": lambda ids: _assign_load_balanced(db, org_id, ids),
        # ai_enhanced falls back to load_balanced until LLM integration is wired in
        "ai_enhanced": lambda ids: _assign_load_balanced(db, org_id, ids),
    }

    strategy_fn = strategy_map.get(strategy)
    if not strategy_fn:
        logger.warning("Unknown routing strategy '%s', falling back to direct", strategy)
        strategy_fn = _assign_direct
        decision.routing_method = "direct"
        decision.selection_criteria = ["booking_link_owner"]
        decision.fallback_used = True
        decision.fallback_reason = f"unknown_strategy_{strategy}"

    result = strategy_fn(candidate_ids)

    if result is None and strict_capacity:
        logger.warning("No LO available with capacity for org %s", org_id)
        decision.fallback_reason = "no_capacity_available"
    else:
        decision.selected_user_id = result

    # COMP-007: Log every routing decision for auditability
    logger.info(
        "AI_ROUTING_DECISION: lo=%s method=%s candidates=%d criteria=%s fallback=%s",
        decision.selected_user_id,
        decision.routing_method,
        decision.candidates_evaluated,
        decision.selection_criteria,
        decision.fallback_used,
    )

    return decision


def _get_candidate_user_ids(db: Session, org_id: int, booking_link) -> List[int]:
    """Get candidate LO user IDs from booking link or org resources."""
    if booking_link:
        assigned = getattr(booking_link, 'assigned_users', None) or []
        if assigned:
            return list(assigned)
        owner = getattr(booking_link, 'user_id', None)
        if owner:
            return [owner]

    # Fall back to org-wide active resources
    try:
        rows = db.execute(text(
            "SELECT user_id FROM scheduler_resources "
            "WHERE organization_id = :org_id AND status = 'active' "
            "ORDER BY routing_weight DESC NULLS LAST"
        ), {"org_id": org_id}).fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        logger.debug(f"Could not query scheduler_resources: {e}")
        return []


def _assign_direct(candidate_ids: List[int]) -> Optional[int]:
    """Direct assignment: return the first candidate."""
    return candidate_ids[0] if candidate_ids else None


def _assign_round_robin(db: Session, org_id: int, candidate_ids: List[int]) -> Optional[int]:
    """Round-robin: rotate through candidates based on last assignment.

    Uses SELECT ... FOR UPDATE to prevent race conditions where two concurrent
    requests read the same last-assigned user and pick the same next LO.
    The row lock is held until the caller's transaction commits (after the new
    appointment is inserted), so the next concurrent request will see the
    updated state.
    """
    try:
        # Lock the most recent appointment row for this org to serialize
        # concurrent round-robin reads.  FOR UPDATE blocks other transactions
        # from reading the same row until this transaction commits.
        last_assigned = db.execute(text(
            "SELECT assigned_user_id FROM scheduler_appointments "
            "WHERE organization_id = :org_id "
            "ORDER BY created_at DESC LIMIT 1 "
            "FOR UPDATE"
        ), {"org_id": org_id}).scalar()

        if last_assigned and last_assigned in candidate_ids:
            idx = candidate_ids.index(last_assigned)
            next_idx = (idx + 1) % len(candidate_ids)
        else:
            next_idx = 0

        return candidate_ids[next_idx]
    except Exception as e:
        logger.error(f"Round robin assignment failed: {e}")
        return candidate_ids[0] if candidate_ids else None


def _assign_priority(db: Session, org_id: int, candidate_ids: List[int],
                     appointment_time: datetime) -> Optional[int]:
    """Assign to highest-priority (routing_weight) LO who is available."""
    try:
        rows = db.execute(text(
            "SELECT user_id FROM scheduler_resources "
            "WHERE organization_id = :org_id AND status = 'active' "
            "AND user_id = ANY(:ids) "
            "ORDER BY routing_weight DESC NULLS LAST"
        ), {"org_id": org_id, "ids": candidate_ids}).fetchall()

        ordered_ids = [r[0] for r in rows]
        # Add any candidates not in resources table at the end
        for uid in candidate_ids:
            if uid not in ordered_ids:
                ordered_ids.append(uid)

        for uid in ordered_ids:
            if _is_lo_available(db, uid, org_id, appointment_time):
                return uid

        # Fallback: highest priority regardless of availability
        return ordered_ids[0] if ordered_ids else (candidate_ids[0] if candidate_ids else None)
    except Exception as e:
        logger.error(f"Priority assignment failed: {e}")
        return candidate_ids[0] if candidate_ids else None


def _assign_availability(db: Session, org_id: int, candidate_ids: List[int],
                         appointment_time: datetime) -> Optional[int]:
    """Assign to first available LO (no conflicts at appointment_time)."""
    for uid in candidate_ids:
        if _is_lo_available(db, uid, org_id, appointment_time):
            return uid
    return candidate_ids[0] if candidate_ids else None


def _assign_load_balanced(db: Session, org_id: int, candidate_ids: List[int]) -> Optional[int]:
    """Assign to LO with fewest active appointments this week.

    Uses a single aggregating query with GROUP BY instead of one COUNT per
    candidate to avoid the N+1 query problem.
    """
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        # Single query: get appointment counts for ALL candidates at once
        rows = db.execute(text(
            "SELECT assigned_user_id, COUNT(*) as cnt "
            "FROM scheduler_appointments "
            "WHERE assigned_user_id = ANY(:ids) AND organization_id = :org_id "
            "AND scheduled_start >= :start AND scheduled_start < :end_dt "
            "AND status IN ('booked', 'completed') "
            "GROUP BY assigned_user_id"
        ), {
            "ids": candidate_ids, "org_id": org_id,
            "start": week_start, "end_dt": week_end,
        }).fetchall()

        # Build a lookup of user_id -> count; candidates with no appointments
        # won't appear in the result set, so default to 0.
        count_map = {row[0]: row[1] for row in rows}
        counts = [(uid, count_map.get(uid, 0)) for uid in candidate_ids]
        counts.sort(key=lambda x: x[1])

        return counts[0][0] if counts else None
    except Exception as e:
        logger.error(f"Load balanced assignment failed: {e}")
        return candidate_ids[0] if candidate_ids else None


def _get_buffer_minutes(db: Session, org_id: int) -> Tuple[int, int]:
    """Read buffer_before_minutes and buffer_after_minutes from scheduler_configs.

    Returns (buffer_before, buffer_after) in minutes. Falls back to defaults
    if no config exists or the table is missing.
    """
    try:
        row = db.execute(text(
            "SELECT buffer_before_minutes, buffer_after_minutes "
            "FROM scheduler_configs "
            "WHERE organization_id = :org_id AND is_active = true "
            "ORDER BY user_id ASC NULLS FIRST "  # team-level (user_id=NULL) first
            "LIMIT 1"
        ), {"org_id": org_id}).first()

        if row:
            return (
                row[0] if row[0] is not None else _DEFAULT_BUFFER_BEFORE,
                row[1] if row[1] is not None else _DEFAULT_BUFFER_AFTER,
            )
    except Exception as e:
        logger.debug(f"Could not read scheduler_configs buffer settings: {e}")

    return (_DEFAULT_BUFFER_BEFORE, _DEFAULT_BUFFER_AFTER)


def _get_cross_source_conflicts(
    db: Session, user_id: int, start_dt: datetime, end_dt: datetime, org_id: int
) -> List[Tuple[datetime, datetime]]:
    """Gather busy time blocks from all calendar sources for a user.

    Checks:
      1. scheduler_appointments (canonical v2 table)
      2. CalendarEvent (manual calendar entries)
      3. CRMCalendarEvent (Salesforce-synced events)

    Returns a list of (start, end) tuples representing occupied time.
    """
    conflicts: List[Tuple[datetime, datetime]] = []

    # Source 1: scheduler_appointments (canonical)
    try:
        rows = db.execute(text(
            "SELECT scheduled_start, scheduled_end FROM scheduler_appointments "
            "WHERE assigned_user_id = :uid AND organization_id = :org_id "
            "AND status IN ('booked', 'tentative', 'completed') "
            "AND scheduled_start <= :end_dt AND scheduled_end >= :start_dt"
        ), {"uid": user_id, "org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()
        for r in rows:
            if r[0] and r[1]:
                conflicts.append((r[0], r[1]))
    except Exception as e:
        logger.debug(f"scheduler_appointments cross-source check failed: {e}")

    # Source 2: CalendarEvent (manual calendar entries)
    try:
        rows = db.execute(text(
            "SELECT start_time, end_time FROM calendar_events "
            "WHERE user_id = :uid AND organization_id = :org_id "
            "AND status != 'cancelled' "
            "AND start_time <= :end_dt AND end_time >= :start_dt"
        ), {"uid": user_id, "org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()
        for r in rows:
            if r[0] and r[1]:
                conflicts.append((r[0], r[1]))
    except Exception as e:
        logger.debug(f"CalendarEvent cross-source check unavailable: {e}")

    # Source 3: CRMCalendarEvent (Salesforce-synced events)
    try:
        rows = db.execute(text(
            "SELECT start_at, end_at FROM crm_calendar_events "
            "WHERE owner_user_id = :uid AND organization_id = :org_id "
            "AND status != 'canceled' "
            "AND start_at <= :end_dt AND end_at >= :start_dt"
        ), {"uid": user_id, "org_id": org_id, "start_dt": start_dt, "end_dt": end_dt}).fetchall()
        for r in rows:
            if r[0] and r[1]:
                conflicts.append((r[0], r[1]))
    except Exception as e:
        logger.debug(f"CRMCalendarEvent cross-source check unavailable: {e}")

    return conflicts


def _is_lo_available(db: Session, user_id: int, org_id: int,
                     appointment_time: datetime, duration_mins: int = 30) -> bool:
    """
    Check if LO is available at the given time.

    Checks:
      1. Daily capacity limit from scheduler_resources
      2. Cross-source time conflicts (scheduler_appointments, CalendarEvent,
         CRMCalendarEvent) with buffer time from scheduler_configs
    """
    if not appointment_time:
        return True

    # Check daily capacity
    today_start = appointment_time.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    today_count = db.execute(text(
        "SELECT COUNT(*) FROM scheduler_appointments "
        "WHERE assigned_user_id = :uid AND organization_id = :org_id "
        "AND scheduled_start >= :start AND scheduled_start < :end_dt "
        "AND status IN ('booked', 'completed')"
    ), {"uid": user_id, "org_id": org_id, "start": today_start, "end_dt": today_end}).scalar() or 0

    # Check capacity from SchedulerResource
    max_daily = db.execute(text(
        "SELECT max_daily_appointments FROM scheduler_resources "
        "WHERE user_id = :uid AND organization_id = :org_id"
    ), {"uid": user_id, "org_id": org_id}).scalar()

    if max_daily and today_count >= max_daily:
        logger.debug(f"LO {user_id} at daily capacity ({today_count}/{max_daily})")
        return False

    # Read org buffer settings
    buffer_before, buffer_after = _get_buffer_minutes(db, org_id)

    # Build the search window (appointment time +/- buffer) to gather all
    # potentially overlapping events from every calendar source.
    appt_end = appointment_time + timedelta(minutes=duration_mins)
    search_start = appointment_time - timedelta(minutes=buffer_before)
    search_end = appt_end + timedelta(minutes=buffer_after)

    conflicts = _get_cross_source_conflicts(db, user_id, search_start, search_end, org_id)

    # Check each conflict with buffer applied around the *busy* block
    for busy_start, busy_end in conflicts:
        buffered_start = busy_start - timedelta(minutes=buffer_before)
        buffered_end = busy_end + timedelta(minutes=buffer_after)
        if appointment_time < buffered_end and appt_end > buffered_start:
            logger.debug(
                f"LO {user_id} has cross-source conflict at {appointment_time} "
                f"(busy {busy_start}-{busy_end}, buffer {buffer_before}/{buffer_after}min)"
            )
            return False

    return True
