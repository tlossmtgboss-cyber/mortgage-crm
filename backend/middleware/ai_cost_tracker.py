"""
AI Cost Tracker — Per-Organization AI Budget Enforcement

Tracks estimated AI API costs per organization using in-memory sliding
windows.  Designed to complement the detailed token-level tracking in
``ai_usage_middleware.py`` by providing a fast, synchronous budget gate
that can reject requests *before* making expensive API calls.

Usage:
    from middleware.ai_cost_tracker import get_ai_budget_tracker

    tracker = get_ai_budget_tracker()

    # Before making an AI call:
    tracker.enforce_budget(org_id=42, operation="review")

    # After a successful AI call:
    tracker.track_call(org_id=42, operation="review", estimated_cost=0.15)

    # Query usage:
    usage = tracker.get_usage(org_id=42, period_hours=24)

The tracker raises ``HTTPException(429)`` when an org exceeds its daily
budget, preventing runaway AI costs.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional, Tuple

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# =============================================================================
# Cost Estimates
# =============================================================================

# Estimated cost per AI operation (USD).  These are rough averages based on
# typical token counts for each Smart Docs V2 operation.
OPERATION_COSTS: Dict[str, float] = {
    "classification": 0.05,
    "review": 0.15,          # Vision model for document review
    "ocr_page": 0.10,
    "income_analysis": 0.08,
    "call_analysis": 0.05,
    "extraction": 0.12,
    "batch_classify": 0.20,
    "cross_validate": 0.10,
    "bank_analysis": 0.15,
}

DEFAULT_OPERATION_COST = 0.05


# =============================================================================
# Budget Tracker
# =============================================================================

@dataclass
class _CostEntry:
    """A single tracked cost event."""
    timestamp: float       # time.monotonic()
    wall_time: float       # time.time() — for human-readable reporting
    operation: str
    cost: float


class AIBudgetTracker:
    """Tracks estimated AI costs per organization with budget enforcement.

    Uses an in-memory sliding window (deque of cost entries) per org.
    Thread-safe via threading.Lock.

    Parameters
    ----------
    default_daily_budget : float
        Default maximum daily AI spend per organization (USD).
    cleanup_interval : int
        Seconds between automatic cleanup of stale org entries.
    """

    _instance: Optional["AIBudgetTracker"] = None
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any) -> "AIBudgetTracker":
        """Singleton — one tracker per process."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instance = instance
        return cls._instance

    def __init__(
        self,
        default_daily_budget: float = 50.0,
        cleanup_interval: int = 300,
    ) -> None:
        if self._initialized:
            return
        self.default_daily_budget = default_daily_budget
        self.cleanup_interval = cleanup_interval

        # {org_id: deque[_CostEntry]}
        self._entries: Dict[int, Deque[_CostEntry]] = defaultdict(deque)
        # Per-org budget overrides
        self._budgets: Dict[int, float] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._initialized = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def track_call(
        self,
        org_id: int,
        operation: str,
        estimated_cost: Optional[float] = None,
    ) -> float:
        """Record an AI API call and return the estimated cost used.

        Parameters
        ----------
        org_id : int
            Organization ID.
        operation : str
            Operation type (e.g. ``"review"``, ``"classification"``).
        estimated_cost : float, optional
            Override cost.  Defaults to the cost estimate for *operation*.

        Returns
        -------
        float
            The cost that was recorded.
        """
        cost = estimated_cost if estimated_cost is not None else self.get_cost_estimate(operation)
        now_mono = time.monotonic()
        now_wall = time.time()

        entry = _CostEntry(
            timestamp=now_mono,
            wall_time=now_wall,
            operation=operation,
            cost=cost,
        )

        with self._lock:
            self._maybe_cleanup(now_mono)
            self._entries[org_id].append(entry)

        logger.debug(
            "AI cost tracked: org=%d op=%s cost=$%.4f",
            org_id,
            operation,
            cost,
        )
        return cost

    def track_call_with_tokens(
        self,
        org_id: int,
        agent_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: Optional[int] = None,
        user_id: Optional[int] = None,
        db=None,
    ) -> float:
        """Record an AI API call with token-level detail.

        Updates the in-memory budget window AND persists to
        ``ai_cost_records`` via the persistent cost tracker if a
        database session is provided.

        Parameters
        ----------
        org_id : int
            Organization ID.
        agent_type : str
            Agent role identifier (e.g. ``"pipeline_analyst"``).
        model : str
            Model identifier (e.g. ``"claude-sonnet-4-6"``).
        input_tokens : int
            Number of input/prompt tokens.
        output_tokens : int
            Number of output/completion tokens.
        duration_ms : int, optional
            Wall-clock latency of the API call.
        user_id : int, optional
            User who triggered the call.
        db : Session, optional
            SQLAlchemy session for persistent tracking.

        Returns
        -------
        float
            The computed cost in USD.
        """
        # Calculate cost using the persistent tracker's pricing
        try:
            from services.ai_cost_tracker import calculate_cost as _calc
            cost = float(_calc(model, input_tokens, output_tokens))
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            cost = self.get_cost_estimate(agent_type)

        # Record in the in-memory sliding window
        self.track_call(org_id, agent_type, estimated_cost=cost)

        # Persist to ai_cost_records if a DB session is available
        if db is not None:
            try:
                from services.ai_cost_tracker import AICostTracker
                tracker = AICostTracker(db)
                tracker.record_usage(
                    org_id=org_id,
                    agent_type=agent_type,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    user_id=user_id,
                )
            except Exception as e:
                logger.debug("Persistent cost tracking skipped: %s", e)

        return cost

    def get_usage(
        self,
        org_id: int,
        period_hours: int = 24,
    ) -> Dict[str, Any]:
        """Return usage stats for *org_id* over the last *period_hours*.

        Returns
        -------
        dict
            Keys: ``total_cost``, ``call_count``, ``by_operation``,
            ``budget``, ``remaining_budget``, ``budget_used_pct``.
        """
        cutoff = time.monotonic() - (period_hours * 3600)
        budget = self._budgets.get(org_id, self.default_daily_budget)

        with self._lock:
            entries = self._entries.get(org_id, deque())
            in_window = [e for e in entries if e.timestamp > cutoff]

        total_cost = sum(e.cost for e in in_window)
        by_operation: Dict[str, Dict[str, Any]] = {}
        for e in in_window:
            if e.operation not in by_operation:
                by_operation[e.operation] = {"count": 0, "cost": 0.0}
            by_operation[e.operation]["count"] += 1
            by_operation[e.operation]["cost"] += e.cost

        # Round for readability
        for op_stats in by_operation.values():
            op_stats["cost"] = round(op_stats["cost"], 4)

        remaining = max(0.0, budget - total_cost)

        return {
            "org_id": org_id,
            "period_hours": period_hours,
            "total_cost": round(total_cost, 4),
            "call_count": len(in_window),
            "by_operation": by_operation,
            "budget": budget,
            "remaining_budget": round(remaining, 4),
            "budget_used_pct": round((total_cost / budget) * 100, 1) if budget > 0 else 0.0,
        }

    def check_budget(
        self,
        org_id: int,
        max_daily_budget: Optional[float] = None,
    ) -> bool:
        """Return ``True`` if the org is under its daily budget.

        Parameters
        ----------
        org_id : int
            Organization ID.
        max_daily_budget : float, optional
            Override budget for this check.  Defaults to the org's configured
            budget or the global default.
        """
        budget = max_daily_budget or self._budgets.get(org_id, self.default_daily_budget)
        usage = self.get_usage(org_id, period_hours=24)
        return usage["total_cost"] < budget

    def enforce_budget(
        self,
        org_id: int,
        operation: Optional[str] = None,
    ) -> None:
        """Raise ``HTTPException(429)`` if the org has exceeded its daily AI budget.

        Call this *before* making an AI API call to prevent cost overruns.
        """
        if not self.check_budget(org_id):
            usage = self.get_usage(org_id, period_hours=24)
            logger.warning(
                "AI budget exceeded: org=%d spent=$%.2f budget=$%.2f",
                org_id,
                usage["total_cost"],
                usage["budget"],
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "AI processing budget exceeded",
                    "org_id": org_id,
                    "daily_budget": usage["budget"],
                    "spent_today": usage["total_cost"],
                    "message": (
                        f"Organization has used ${usage['total_cost']:.2f} of "
                        f"${usage['budget']:.2f} daily AI budget. "
                        "Please try again tomorrow or contact your administrator "
                        "to increase the limit."
                    ),
                },
            )

    def set_org_budget(self, org_id: int, daily_budget: float) -> None:
        """Set a custom daily budget for an organization."""
        with self._lock:
            self._budgets[org_id] = daily_budget
        logger.info("AI budget set: org=%d budget=$%.2f", org_id, daily_budget)

    def get_cost_estimate(self, operation: str) -> float:
        """Return the estimated cost for an operation type."""
        return OPERATION_COSTS.get(operation, DEFAULT_OPERATION_COST)

    def reset(self, org_id: Optional[int] = None) -> None:
        """Clear tracked costs.  If *org_id* is given, clear only that org."""
        with self._lock:
            if org_id is None:
                self._entries.clear()
            else:
                self._entries.pop(org_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _maybe_cleanup(self, now: float) -> None:
        """Remove entries older than 48 hours and empty org buckets."""
        if now - self._last_cleanup < self.cleanup_interval:
            return
        self._last_cleanup = now
        cutoff = now - (48 * 3600)  # Keep 48h of history
        stale_orgs = []
        for org_id, entries in self._entries.items():
            # Remove old entries
            while entries and entries[0].timestamp < cutoff:
                entries.popleft()
            if not entries:
                stale_orgs.append(org_id)
        for org_id in stale_orgs:
            del self._entries[org_id]
        if stale_orgs:
            logger.debug("AI cost tracker cleanup: removed %d stale orgs", len(stale_orgs))


# Module-level singleton
_tracker = AIBudgetTracker()


def get_ai_budget_tracker() -> AIBudgetTracker:
    """Return the process-wide AIBudgetTracker singleton."""
    return _tracker
