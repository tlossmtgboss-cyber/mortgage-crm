"""
Token Budget Manager — Per-Agent Cost Governance

Enforces daily token budgets per agent_id. Tracks input + output tokens
against a configurable per-agent budget (or default), warns at 80%
utilization, and rejects requests that would exceed the budget.

This is a HOT CACHE only — uses an in-memory dict keyed by (agent_id, date).
A persistent ledger (Postgres table `agent_token_usage` keyed by org/agent/day)
should be added later for cross-restart durability, multi-process aggregation,
and historical reporting / chargeback.

Module-level singleton: `token_budget_manager`.
"""

from __future__ import annotations

import logging
from datetime import date
from threading import Lock
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class TokenBudgetManager:
    """Per-agent daily token budget enforcer (in-memory)."""

    def __init__(
        self,
        *,
        default_budget_tokens: int = 50_000,
        per_agent_overrides: Optional[Dict[str, int]] = None,
    ):
        self.default_budget_tokens = int(default_budget_tokens)
        self.per_agent_overrides: Dict[str, int] = dict(per_agent_overrides or {})
        # key: (agent_id, iso-date-string) -> tokens_used
        self._usage: Dict[Tuple[str, str], int] = {}
        self._warned_80pct: set[Tuple[str, str]] = set()
        self._lock = Lock()

    # ---- internals -----------------------------------------------------

    def _today_key(self, agent_id: str) -> Tuple[str, str]:
        return (str(agent_id), date.today().isoformat())

    def _budget_for(self, agent_id: str) -> int:
        return int(self.per_agent_overrides.get(str(agent_id), self.default_budget_tokens))

    # ---- public api ----------------------------------------------------

    def check_and_reserve(self, agent_id: str, requested_tokens: int) -> bool:
        """
        Return True if `requested_tokens` fits inside today's remaining budget.
        Returns False (and logs an error) if it would exceed.
        Warns once per agent/day at >=80% utilization.

        Note: This does NOT actually decrement until `record_usage` is called.
        It is a pre-flight check + warning gate.
        """
        with self._lock:
            key = self._today_key(agent_id)
            used = self._usage.get(key, 0)
            budget = self._budget_for(agent_id)
            projected = used + int(requested_tokens)

            if projected > budget:
                logger.error(
                    "Token budget exceeded for agent=%s used=%d requested=%d budget=%d",
                    agent_id, used, requested_tokens, budget,
                )
                return False

            pct = projected / budget if budget > 0 else 0.0
            if pct >= 0.80 and key not in self._warned_80pct:
                logger.warning(
                    "Token budget at %.0f%% utilization for agent=%s (used=%d/%d)",
                    pct * 100, agent_id, projected, budget,
                )
                self._warned_80pct.add(key)
            return True

    def record_usage(
        self,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
        agent_role: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """
        Increment the running counter for today's usage and emit to the
        in-process governance metrics store. Metrics emit is wrapped in
        try/except so a telemetry failure NEVER leaks into the caller.
        """
        delta = int(input_tokens) + int(output_tokens)
        if delta <= 0:
            return
        with self._lock:
            key = self._today_key(agent_id)
            self._usage[key] = self._usage.get(key, 0) + delta

        try:
            from agents.orchestration.governance_metrics import governance_metrics
            governance_metrics.record_token_usage(
                agent_id=str(agent_id),
                agent_role=str(agent_role or "unknown"),
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
                model=model,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("token_budget metrics emit swallowed: %s", exc)

    def get_usage(self, agent_id: str) -> dict:
        """Return current usage snapshot for agent_id (today)."""
        with self._lock:
            key = self._today_key(agent_id)
            used = self._usage.get(key, 0)
            budget = self._budget_for(agent_id)
            remaining = max(0, budget - used)
            pct = (used / budget) if budget > 0 else 0.0
            return {
                "tokens_used": used,
                "tokens_remaining": remaining,
                "pct_utilization": round(pct, 4),
                "budget": budget,
            }

    def reset_daily(self) -> None:
        """
        Reset all counters. Intended to be called by a scheduled job at midnight.
        Safe to call any time — wipes the in-memory ledger.
        """
        with self._lock:
            self._usage.clear()
            self._warned_80pct.clear()
            logger.info("TokenBudgetManager: daily reset complete")


# Module-level singleton
token_budget_manager = TokenBudgetManager()
