"""
aria/core/voice_intelligence.py
Perennia AI — Voice Analytics & Intelligence

Tracks and analyzes Aria's voice interactions for continuous improvement.
Stores conversation outcomes, usage patterns, and satisfaction signals.

All persistence goes through the HTTP backend client or direct Redis.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from agents.aria_backend_client import call_backend_tool_safe

logger = logging.getLogger("aria.voice_intelligence")


# ─── In-memory aggregation buffer (flushed to backend periodically) ──────────
_interaction_buffer: List[Dict[str, Any]] = []
_MAX_BUFFER_SIZE = 100


class VoiceIntelligence:
    """Tracks and analyzes Aria's voice interactions for continuous improvement."""

    def __init__(self, organization_id: Optional[str] = None):
        self._org_id = organization_id

    # ─── Tracking ────────────────────────────────────────────────────

    def track_conversation_outcome(
        self,
        session_id: str,
        user_id: str,
        outcome: str,
        duration_seconds: int,
        intents_handled: List[str],
        tools_used: List[str],
        mode: str = "lo_assistant",
    ) -> None:
        """Record the outcome of a voice interaction for analytics.

        Args:
            session_id: Unique session identifier.
            user_id: The LO's user ID.
            outcome: One of 'completed', 'abandoned', 'transferred', 'error'.
            duration_seconds: How long the conversation lasted.
            intents_handled: List of intent names triggered during the session.
            tools_used: List of tool names executed.
            mode: Session mode (lo_assistant, inbound_receptionist, outbound_followup).
        """
        record = {
            "session_id": session_id,
            "user_id": user_id,
            "organization_id": self._org_id,
            "outcome": outcome,
            "duration_seconds": duration_seconds,
            "intents_handled": intents_handled,
            "tools_used": tools_used,
            "mode": mode,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        _interaction_buffer.append(record)

        if len(_interaction_buffer) >= _MAX_BUFFER_SIZE:
            self._flush_buffer()

    def track_tool_latency(
        self,
        tool_name: str,
        latency_ms: int,
        success: bool,
    ) -> None:
        """Track latency for individual tool calls to identify slow paths."""
        record = {
            "type": "tool_latency",
            "tool_name": tool_name,
            "latency_ms": latency_ms,
            "success": success,
            "organization_id": self._org_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        _interaction_buffer.append(record)

    def track_intent_resolution(
        self,
        user_utterance: str,
        resolved_intent: Optional[str],
        confidence: float,
        fallback: bool = False,
    ) -> None:
        """Track how well NLU resolves intents for training improvement."""
        record = {
            "type": "intent_resolution",
            "utterance_length": len(user_utterance.split()),
            "resolved_intent": resolved_intent,
            "confidence": confidence,
            "fallback": fallback,
            "organization_id": self._org_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        _interaction_buffer.append(record)

    # ─── Analytics Queries ───────────────────────────────────────────

    async def get_lo_voice_usage_stats(
        self, user_id: str, period_days: int = 30
    ) -> Dict[str, Any]:
        """Get voice usage statistics for a specific LO.

        Returns:
            Dict with total_conversations, total_duration_minutes,
            avg_duration_seconds, tools_used_count, top_intents.
        """
        result = await call_backend_tool_safe(
            "/internal/aria/analytics/usage",
            {
                "user_id": user_id,
                "organization_id": self._org_id,
                "period_days": period_days,
            },
        )
        if result.get("error"):
            # Return from buffer as fallback
            return self._compute_from_buffer(user_id, period_days)
        return result

    async def get_most_common_voice_queries(
        self, period_days: int = 30, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get the most frequently triggered intents across the org.

        Returns:
            List of {intent, count, avg_duration_seconds} sorted by frequency.
        """
        result = await call_backend_tool_safe(
            "/internal/aria/analytics/common-queries",
            {
                "organization_id": self._org_id,
                "period_days": period_days,
                "limit": limit,
            },
        )
        if result.get("error"):
            return self._compute_common_from_buffer(period_days, limit)
        return result.get("queries", [])

    async def calculate_time_saved(
        self, user_id: str, period_days: int = 30
    ) -> Dict[str, Any]:
        """Estimate time saved by using Aria vs manual lookup.

        Heuristic: each tool call saves ~2 minutes of manual CRM navigation.
        Each pipeline query saves ~3 minutes of report building.
        Each SMS/email saves ~1 minute of compose-and-send.
        """
        stats = await self.get_lo_voice_usage_stats(user_id, period_days)

        MANUAL_ESTIMATES = {
            "find_contact": 2.0,
            "get_pipeline_metrics": 3.0,
            "get_task_queue": 2.0,
            "send_sms_message": 1.5,
            "send_email": 2.0,
            "create_task": 1.5,
            "book_appointment": 3.0,
            "get_loans_by_status": 2.5,
            "get_rate_quote": 2.0,
            "find_contact_phone": 1.5,
            "find_contact_email": 1.5,
            "get_availability": 2.0,
            "default": 1.5,
        }

        total_minutes_saved = 0.0
        tool_breakdown = {}

        tools_used = stats.get("tools_used", {})
        if isinstance(tools_used, dict):
            for tool_name, count in tools_used.items():
                minutes = MANUAL_ESTIMATES.get(tool_name, MANUAL_ESTIMATES["default"])
                saved = minutes * count
                total_minutes_saved += saved
                tool_breakdown[tool_name] = {
                    "count": count,
                    "minutes_saved": round(saved, 1),
                }

        return {
            "total_minutes_saved": round(total_minutes_saved, 1),
            "total_hours_saved": round(total_minutes_saved / 60, 1),
            "period_days": period_days,
            "tool_breakdown": tool_breakdown,
            "conversations": stats.get("total_conversations", 0),
        }

    async def get_voice_satisfaction_score(
        self, user_id: str
    ) -> Dict[str, Any]:
        """Infer satisfaction from interaction patterns.

        Positive signals: conversation completed, multiple tool calls per session,
        returning user, session duration > 30s.
        Negative signals: abandoned sessions, single-turn exits, error outcomes.
        """
        stats = await self.get_lo_voice_usage_stats(user_id, 30)

        total = stats.get("total_conversations", 0)
        if total == 0:
            return {"score": None, "confidence": "low", "reason": "No conversations recorded."}

        completed = stats.get("completed_conversations", 0)
        abandoned = stats.get("abandoned_conversations", 0)
        errors = stats.get("error_conversations", 0)

        completion_rate = completed / total if total > 0 else 0
        error_rate = errors / total if total > 0 else 0

        # Score 0-100
        score = int(completion_rate * 80 + (1 - error_rate) * 20)
        score = max(0, min(100, score))

        confidence = "high" if total >= 20 else "medium" if total >= 5 else "low"

        return {
            "score": score,
            "confidence": confidence,
            "total_conversations": total,
            "completion_rate": round(completion_rate * 100, 1),
            "error_rate": round(error_rate * 100, 1),
        }

    # ─── Internal Helpers ────────────────────────────────────────────

    def _compute_from_buffer(
        self, user_id: str, period_days: int
    ) -> Dict[str, Any]:
        """Compute stats from in-memory buffer as fallback."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        cutoff_str = cutoff.isoformat()

        user_records = [
            r for r in _interaction_buffer
            if r.get("user_id") == user_id
            and r.get("recorded_at", "") >= cutoff_str
            and r.get("type") is None  # Only conversation records
        ]

        total = len(user_records)
        total_duration = sum(r.get("duration_seconds", 0) for r in user_records)
        all_intents: Dict[str, int] = {}
        all_tools: Dict[str, int] = {}

        for r in user_records:
            for intent in r.get("intents_handled", []):
                all_intents[intent] = all_intents.get(intent, 0) + 1
            for tool in r.get("tools_used", []):
                all_tools[tool] = all_tools.get(tool, 0) + 1

        return {
            "total_conversations": total,
            "total_duration_minutes": round(total_duration / 60, 1),
            "avg_duration_seconds": round(total_duration / total, 1) if total else 0,
            "tools_used": all_tools,
            "top_intents": sorted(all_intents.items(), key=lambda x: x[1], reverse=True)[:10],
            "completed_conversations": sum(1 for r in user_records if r.get("outcome") == "completed"),
            "abandoned_conversations": sum(1 for r in user_records if r.get("outcome") == "abandoned"),
            "error_conversations": sum(1 for r in user_records if r.get("outcome") == "error"),
            "source": "buffer",
        }

    def _compute_common_from_buffer(
        self, period_days: int, limit: int
    ) -> List[Dict[str, Any]]:
        """Compute common queries from buffer."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        cutoff_str = cutoff.isoformat()

        intent_counts: Dict[str, int] = {}
        for r in _interaction_buffer:
            if r.get("recorded_at", "") < cutoff_str:
                continue
            if self._org_id and r.get("organization_id") != self._org_id:
                continue
            for intent in r.get("intents_handled", []):
                intent_counts[intent] = intent_counts.get(intent, 0) + 1

        sorted_intents = sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"intent": k, "count": v} for k, v in sorted_intents]

    def _flush_buffer(self) -> None:
        """Flush buffered records to backend (fire and forget)."""
        global _interaction_buffer
        if not _interaction_buffer:
            return

        import asyncio
        batch = _interaction_buffer[:_MAX_BUFFER_SIZE]
        _interaction_buffer = _interaction_buffer[_MAX_BUFFER_SIZE:]

        async def _flush():
            try:
                await call_backend_tool_safe(
                    "/internal/aria/analytics/batch-record",
                    {"records": batch},
                )
            except Exception as e:
                logger.warning("Failed to flush analytics buffer: %s", e)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_flush())
            else:
                loop.run_until_complete(_flush())
        except RuntimeError:
            pass
