"""
Tool Usage Tracker

Tracks tool routing + invocation via Redis. Powers:
  - Monthly deprecation report (tools with <5 calls/mo for 3 months)
  - Router quality metrics (did Claude actually use the tools we routed?)
  - Per-agent tool effectiveness

Redis keys:
  tool_usage:routed:{YYYY-MM}:{tool}   — counter of times routed to model
  tool_usage:called:{YYYY-MM}:{tool}   — counter of times Claude actually invoked it
  tool_usage:agent:{YYYY-MM}:{agent}:{tool} — per-agent breakdown
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


def _month_key() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


@dataclass
class ToolUsageStats:
    tool_name: str
    month: str
    routed: int
    called: int

    @property
    def call_rate(self) -> float:
        return self.called / self.routed if self.routed else 0.0


class UsageTracker:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def record_routing(
        self,
        *,
        agent_type: str,
        role: str,
        intents: set,
        selected: list,
    ) -> None:
        if not self.redis:
            return
        try:
            month = _month_key()
            pipe = self.redis.pipeline()
            for tool in selected:
                pipe.hincrby(f"tool_usage:routed:{month}", tool, 1)
                pipe.hincrby(f"tool_usage:agent:{month}:{agent_type}", f"routed:{tool}", 1)
            pipe.expire(f"tool_usage:routed:{month}", 60 * 60 * 24 * 540)
            pipe.expire(f"tool_usage:agent:{month}:{agent_type}", 60 * 60 * 24 * 540)
            await pipe.execute()
        except Exception as e:
            logger.warning("Failed to record tool routing: %s", e)

    async def record_call(self, *, agent_type: str, tool_name: str) -> None:
        if not self.redis:
            return
        try:
            month = _month_key()
            pipe = self.redis.pipeline()
            pipe.hincrby(f"tool_usage:called:{month}", tool_name, 1)
            pipe.hincrby(f"tool_usage:agent:{month}:{agent_type}", f"called:{tool_name}", 1)
            pipe.expire(f"tool_usage:called:{month}", 60 * 60 * 24 * 540)
            await pipe.execute()
        except Exception as e:
            logger.warning("Failed to record tool call: %s", e)

    async def monthly_stats(self, month: Optional[str] = None) -> list:
        if not self.redis:
            return []
        month = month or _month_key()
        routed = await self.redis.hgetall(f"tool_usage:routed:{month}")
        called = await self.redis.hgetall(f"tool_usage:called:{month}")

        def _decode(d):
            return {
                (k.decode() if isinstance(k, bytes) else k): int(v)
                for k, v in d.items()
            }

        routed_map = _decode(routed)
        called_map = _decode(called)

        all_names = set(routed_map) | set(called_map)
        return [
            ToolUsageStats(
                tool_name=name,
                month=month,
                routed=routed_map.get(name, 0),
                called=called_map.get(name, 0),
            )
            for name in all_names
        ]

    async def deprecation_candidates(
        self,
        *,
        min_monthly_calls: int = 5,
        consecutive_months: int = 3,
    ) -> list:
        """Tools with fewer than min_monthly_calls for N consecutive months."""
        today = dt.datetime.now(dt.timezone.utc).replace(day=1)
        months = [
            (today - dt.timedelta(days=30 * i)).strftime("%Y-%m")
            for i in range(consecutive_months)
        ]

        per_month = {m: {s.tool_name: s for s in await self.monthly_stats(m)} for m in months}

        all_tools = set()
        for m in months:
            all_tools.update(per_month[m].keys())

        candidates = []
        for tool in all_tools:
            below = True
            for m in months:
                stats = per_month[m].get(tool)
                if stats and stats.called >= min_monthly_calls:
                    below = False
                    break
            if below:
                candidates.append(tool)

        return sorted(candidates)
