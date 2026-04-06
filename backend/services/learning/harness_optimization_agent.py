"""
Harness Optimization Agent — Continual Learning (Domain 8)

Weekly job that analyzes the last 7 days of agent execution traces and
proposes harness improvements (graph-node changes, prompt updates, tool
configuration tweaks).  All proposals are routed to an Admin for manual
approval — nothing is auto-deployed.

Pipeline:
    1. Pull last 7 days of agent_executions for the target agent
    2. Identify: high-latency runs, low-confidence outputs, correction
       clusters, timeout patterns, tool-call failures
    3. Generate a structured diff proposal: which graph nodes to change,
       prompt updates, tool changes
    4. Route proposal to Admin for approval (no auto-deploy)
    5. After approval, tag new version in agent_profiles
    6. Run AgentGym regression before promotion
"""

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports (avoids circular imports at module load time)
# ---------------------------------------------------------------------------

_models_loaded = False
_AgentExecution = None
_AgentProfile = None
_AgentAlert = None
_AgentContextEvent = None
_GymTestRun = None


def _ensure_models():
    """Load models on first use."""
    global _models_loaded, _AgentExecution, _AgentProfile, _AgentAlert
    global _AgentContextEvent, _GymTestRun
    if _models_loaded:
        return
    from models.agent_governance import (
        AgentExecution,
        AgentProfile,
        AgentAlert,
        GymTestRun,
    )
    from database.models.agent_context import AgentContextEvent

    _AgentExecution = AgentExecution
    _AgentProfile = AgentProfile
    _AgentAlert = AgentAlert
    _AgentContextEvent = AgentContextEvent
    _GymTestRun = GymTestRun
    _models_loaded = True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LOOKBACK_DAYS = 7
HIGH_LATENCY_PERCENTILE = 0.95  # runs above p95 are flagged
LOW_CONFIDENCE_THRESHOLD = 0.60
CORRECTION_RATE_ALERT = 0.20  # 20 % correction rate triggers alert
TIMEOUT_STATUS = "timeout"
FAILURE_STATUSES = {"failed", "error", "timeout"}


# ---------------------------------------------------------------------------
# HarnessOptimizationAgent
# ---------------------------------------------------------------------------

class HarnessOptimizationAgent:
    """Weekly agent that analyzes traces and proposes harness improvements.

    Designed to run inside an async scheduler (e.g. APScheduler) or as a
    standalone invocation from a management command / API endpoint.
    """

    JOB_NAME = "harness_optimization"

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def analyze_agent(
        self, agent_id: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS
    ) -> dict:
        """Full analysis pipeline for a single agent.

        Returns a structured analysis dict with sections:
            latency, confidence, corrections, timeouts, tool_failures, summary
        """
        _ensure_models()
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        runs = self._fetch_runs(agent_id, cutoff)
        if not runs:
            return {
                "agent_id": agent_id,
                "lookback_days": lookback_days,
                "total_runs": 0,
                "analysis": None,
                "message": "No executions found in lookback window",
            }

        analysis: Dict[str, Any] = {
            "agent_id": agent_id,
            "lookback_days": lookback_days,
            "total_runs": len(runs),
            "window_start": cutoff.isoformat(),
            "window_end": datetime.now(timezone.utc).isoformat(),
        }

        # 1. High-latency detection
        analysis["latency"] = self._analyze_latency(runs)

        # 2. Low-confidence outputs
        analysis["low_confidence_rate"] = await self._compute_low_confidence(runs)

        # 3. Correction clusters
        analysis["correction_rate"] = await self._compute_correction_rate(
            agent_id, lookback_days
        )

        # 4. Timeout patterns
        analysis["timeout"] = self._analyze_timeouts(runs)

        # 5. Tool-call failures
        analysis["tool_failures"] = await self._extract_tool_failures(runs)

        # Summary risk score (0-100, higher = more issues)
        analysis["risk_score"] = self._compute_risk_score(analysis)

        logger.info(
            "Harness analysis for agent %s: %d runs, risk_score=%.1f",
            agent_id, len(runs), analysis["risk_score"],
        )
        return analysis

    async def generate_diff_proposal(
        self, agent_id: str, analysis: dict
    ) -> dict:
        """Transform analysis into a structured diff proposal.

        Returns a proposal dict with sections:
            node_changes, prompt_updates, tool_changes, rationale, priority
        """
        if not analysis or analysis.get("total_runs", 0) == 0:
            return {"agent_id": agent_id, "changes": [], "status": "no_data"}

        proposal: Dict[str, Any] = {
            "proposal_id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "risk_score": analysis.get("risk_score", 0),
            "node_changes": [],
            "prompt_updates": [],
            "tool_changes": [],
            "rationale": [],
        }

        # --- Node change proposals ---
        latency = analysis.get("latency", {})
        if latency.get("high_latency_count", 0) > 0:
            proposal["node_changes"].append({
                "type": "optimize_node",
                "target": "execute",
                "reason": (
                    f"{latency['high_latency_count']} runs exceeded p95 latency "
                    f"({latency.get('p95_ms', 0):.0f}ms)"
                ),
                "suggestion": "Add early-exit guard or split into sub-nodes",
            })
            proposal["rationale"].append("High latency detected in execute node")

        # --- Prompt update proposals ---
        correction_rate = analysis.get("correction_rate", 0)
        if correction_rate > CORRECTION_RATE_ALERT:
            proposal["prompt_updates"].append({
                "type": "refine_system_prompt",
                "reason": (
                    f"Correction rate {correction_rate:.1%} exceeds "
                    f"{CORRECTION_RATE_ALERT:.0%} threshold"
                ),
                "suggestion": (
                    "Incorporate top correction patterns into system prompt "
                    "as explicit instructions"
                ),
            })
            proposal["rationale"].append(
                f"Correction rate {correction_rate:.1%} above threshold"
            )

        low_confidence = analysis.get("low_confidence_rate", 0)
        if low_confidence > 0.15:
            proposal["prompt_updates"].append({
                "type": "add_examples",
                "reason": (
                    f"{low_confidence:.1%} of outputs below confidence "
                    f"threshold {LOW_CONFIDENCE_THRESHOLD}"
                ),
                "suggestion": "Add few-shot examples for common low-confidence patterns",
            })

        # --- Tool change proposals ---
        tool_failures = analysis.get("tool_failures", [])
        for tf in tool_failures:
            if tf.get("failure_rate", 0) > 0.10:
                proposal["tool_changes"].append({
                    "type": "fix_or_replace_tool",
                    "tool_name": tf["tool_name"],
                    "failure_rate": tf["failure_rate"],
                    "failure_count": tf["failure_count"],
                    "reason": f"Tool {tf['tool_name']} failing at {tf['failure_rate']:.1%}",
                    "suggestion": "Review tool implementation or add fallback",
                })

        timeout = analysis.get("timeout", {})
        if timeout.get("timeout_rate", 0) > 0.05:
            proposal["tool_changes"].append({
                "type": "increase_timeout_budget",
                "timeout_rate": timeout["timeout_rate"],
                "reason": (
                    f"Timeout rate {timeout['timeout_rate']:.1%} suggests "
                    f"insufficient time budget"
                ),
                "suggestion": "Increase tool timeout or add streaming fallback",
            })

        # Priority based on risk
        risk = analysis.get("risk_score", 0)
        if risk >= 70:
            proposal["priority"] = "critical"
        elif risk >= 40:
            proposal["priority"] = "high"
        elif risk >= 20:
            proposal["priority"] = "medium"
        else:
            proposal["priority"] = "low"

        total_changes = (
            len(proposal["node_changes"])
            + len(proposal["prompt_updates"])
            + len(proposal["tool_changes"])
        )
        proposal["total_changes"] = total_changes
        proposal["status"] = "pending_review" if total_changes > 0 else "no_changes"

        return proposal

    async def submit_for_approval(
        self, agent_id: str, proposal: dict
    ) -> str:
        """Create an admin alert with the proposal for manual review.

        Returns the alert ID for tracking.
        """
        _ensure_models()

        # Look up agent profile for the FK
        profile = (
            self.db.query(_AgentProfile)
            .filter(_AgentProfile.agent_name == agent_id)
            .first()
        )
        if not profile:
            # Try numeric ID
            try:
                profile = self.db.query(_AgentProfile).get(int(agent_id))
            except (ValueError, TypeError):
                pass

        if not profile:
            logger.warning("No AgentProfile found for %s; creating alert without FK", agent_id)

        alert = _AgentAlert(
            agent_id=profile.id if profile else 1,
            agent_name=profile.agent_name if profile else str(agent_id),
            alert_type="harness_optimization",
            severity=proposal.get("priority", "medium"),
            title=f"Harness optimization proposal for {agent_id}",
            message=(
                f"{proposal.get('total_changes', 0)} changes proposed "
                f"(risk score: {proposal.get('risk_score', 0):.0f})"
            ),
            details={
                "proposal": proposal,
                "submitted_by": self.JOB_NAME,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            },
            status="active",
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)

        logger.info(
            "Submitted harness proposal for agent %s as alert %d",
            agent_id, alert.id,
        )
        return str(alert.id)

    async def apply_approved_proposal(
        self, agent_id: str, proposal: dict
    ) -> dict:
        """After admin approval: bump version, then run AgentGym regression.

        Returns dict with new_version and regression results.
        """
        _ensure_models()

        # 1. Tag new version in agent_profiles
        profile = (
            self.db.query(_AgentProfile)
            .filter(_AgentProfile.agent_name == agent_id)
            .first()
        )
        if not profile:
            return {"error": f"Agent profile not found: {agent_id}"}

        old_version = profile.version or "1.0.0"
        new_version = self._bump_version(old_version)
        profile.version = new_version
        profile.config = {
            **(profile.config or {}),
            "last_optimization": {
                "proposal_id": proposal.get("proposal_id"),
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "previous_version": old_version,
            },
        }
        self.db.commit()

        # 2. Run AgentGym regression
        regression = await self._run_gym_regression(agent_id)

        return {
            "agent_id": agent_id,
            "old_version": old_version,
            "new_version": new_version,
            "regression": regression,
        }

    # ------------------------------------------------------------------
    # Analysis helpers
    # ------------------------------------------------------------------

    def _fetch_runs(self, agent_id: str, cutoff: datetime) -> list:
        """Fetch execution rows for the agent within the lookback window."""
        _ensure_models()

        # Try matching on agent_name first (most common), then numeric ID
        query = (
            self.db.query(_AgentExecution)
            .filter(
                and_(
                    _AgentExecution.agent_name == agent_id,
                    _AgentExecution.created_at >= cutoff,
                )
            )
            .order_by(_AgentExecution.created_at.asc())
        )
        rows = query.all()

        if not rows:
            try:
                numeric_id = int(agent_id)
                rows = (
                    self.db.query(_AgentExecution)
                    .filter(
                        and_(
                            _AgentExecution.agent_id == numeric_id,
                            _AgentExecution.created_at >= cutoff,
                        )
                    )
                    .order_by(_AgentExecution.created_at.asc())
                    .all()
                )
            except (ValueError, TypeError):
                pass

        return rows

    def _analyze_latency(self, runs: list) -> dict:
        """Identify high-latency runs and compute percentiles."""
        response_times = [
            r.response_time_ms for r in runs
            if r.response_time_ms is not None and r.response_time_ms > 0
        ]
        if not response_times:
            return {
                "sample_size": 0,
                "avg_ms": 0,
                "p95_ms": 0,
                "max_ms": 0,
                "high_latency_count": 0,
            }

        response_times.sort()
        n = len(response_times)
        p95_idx = int(n * HIGH_LATENCY_PERCENTILE)
        p95_val = response_times[min(p95_idx, n - 1)]

        high_latency_runs = [t for t in response_times if t > p95_val]

        return {
            "sample_size": n,
            "avg_ms": sum(response_times) / n,
            "p95_ms": p95_val,
            "max_ms": max(response_times),
            "high_latency_count": len(high_latency_runs),
            "high_latency_threshold_ms": p95_val,
        }

    def _analyze_timeouts(self, runs: list) -> dict:
        """Detect timeout patterns in executions."""
        total = len(runs)
        if total == 0:
            return {"total": 0, "timeouts": 0, "timeout_rate": 0.0}

        timeouts = [
            r for r in runs
            if r.status == TIMEOUT_STATUS
            or (r.error_message and "timeout" in (r.error_message or "").lower())
        ]
        timeout_count = len(timeouts)

        # Group timeouts by hour-of-day to detect patterns
        hour_distribution: Dict[int, int] = defaultdict(int)
        for t in timeouts:
            if t.created_at:
                hour_distribution[t.created_at.hour] += 1

        peak_hour = (
            max(hour_distribution, key=hour_distribution.get)
            if hour_distribution else None
        )

        return {
            "total": total,
            "timeouts": timeout_count,
            "timeout_rate": timeout_count / total if total > 0 else 0.0,
            "hour_distribution": dict(hour_distribution),
            "peak_hour": peak_hour,
        }

    async def _compute_correction_rate(
        self, agent_id: str, days: int
    ) -> float:
        """Fraction of runs that were subsequently corrected via context events."""
        _ensure_models()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Total runs in window
        total_runs = (
            self.db.query(func.count(_AgentExecution.id))
            .filter(
                and_(
                    _AgentExecution.agent_name == agent_id,
                    _AgentExecution.created_at >= cutoff,
                )
            )
            .scalar()
        ) or 0

        if total_runs == 0:
            return 0.0

        # Correction events in same window
        corrections = (
            self.db.query(func.count(_AgentContextEvent.id))
            .filter(
                and_(
                    _AgentContextEvent.agent_id == agent_id,
                    _AgentContextEvent.event_type == "correction",
                    _AgentContextEvent.created_at >= cutoff,
                )
            )
            .scalar()
        ) or 0

        return corrections / total_runs

    async def _extract_tool_failures(self, runs: list) -> list:
        """Aggregate tool-call failure data from execution traces.

        Returns list of dicts: [{tool_name, failure_count, total_calls, failure_rate}]
        """
        tool_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "failures": 0}
        )

        for run in runs:
            tool_calls = run.tool_calls or []
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                name = call.get("name") or call.get("tool_name") or "unknown"
                tool_stats[name]["total"] += 1
                status = call.get("status", "")
                if status in FAILURE_STATUSES or call.get("error"):
                    tool_stats[name]["failures"] += 1

        results = []
        for tool_name, stats in tool_stats.items():
            total = stats["total"]
            failures = stats["failures"]
            results.append({
                "tool_name": tool_name,
                "total_calls": total,
                "failure_count": failures,
                "failure_rate": failures / total if total > 0 else 0.0,
            })

        # Sort by failure rate descending
        results.sort(key=lambda x: x["failure_rate"], reverse=True)
        return results

    async def _compute_low_confidence(self, runs: list) -> float:
        """Fraction of runs whose output confidence is below threshold."""
        if not runs:
            return 0.0

        low_count = 0
        scored_count = 0

        for run in runs:
            output = run.output_data or {}
            confidence = output.get("confidence")
            if confidence is not None:
                scored_count += 1
                if confidence < LOW_CONFIDENCE_THRESHOLD:
                    low_count += 1

        if scored_count == 0:
            return 0.0

        return low_count / scored_count

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_risk_score(self, analysis: dict) -> float:
        """Composite risk score (0-100) from all analysis dimensions."""
        score = 0.0

        # Latency contribution (0-25)
        latency = analysis.get("latency", {})
        if latency.get("sample_size", 0) > 0:
            high_pct = (
                latency.get("high_latency_count", 0)
                / latency["sample_size"]
            )
            score += min(high_pct * 100, 25)

        # Correction rate contribution (0-25)
        correction = analysis.get("correction_rate", 0)
        score += min(correction * 125, 25)  # 20% correction -> 25 points

        # Timeout contribution (0-25)
        timeout = analysis.get("timeout", {})
        timeout_rate = timeout.get("timeout_rate", 0)
        score += min(timeout_rate * 250, 25)  # 10% timeout -> 25 points

        # Low confidence contribution (0-15)
        low_conf = analysis.get("low_confidence_rate", 0)
        score += min(low_conf * 100, 15)

        # Tool failure contribution (0-10)
        tool_failures = analysis.get("tool_failures", [])
        if tool_failures:
            worst_rate = max(tf.get("failure_rate", 0) for tf in tool_failures)
            score += min(worst_rate * 100, 10)

        return min(score, 100.0)

    # ------------------------------------------------------------------
    # Version management
    # ------------------------------------------------------------------

    @staticmethod
    def _bump_version(version: str) -> str:
        """Increment the patch segment of a semver string."""
        parts = version.split(".")
        if len(parts) != 3:
            return "1.0.1"
        try:
            major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
            return f"{major}.{minor}.{patch + 1}"
        except ValueError:
            return "1.0.1"

    # ------------------------------------------------------------------
    # AgentGym regression
    # ------------------------------------------------------------------

    async def _run_gym_regression(self, agent_id: str) -> dict:
        """Trigger a gym test run for the agent and return results summary.

        Uses AgentGymService if available; returns a stub otherwise.
        """
        try:
            from services.agent_gym_service import AgentGymService

            gym = AgentGymService(self.db)
            run = gym.start_test_run(agent_name=agent_id)
            return {
                "run_id": str(run.get("run_id", "")),
                "status": run.get("status", "triggered"),
                "message": "Regression test triggered",
            }
        except Exception as e:
            logger.warning("AgentGym regression skipped for %s: %s", agent_id, e)
            return {
                "status": "skipped",
                "reason": str(e),
            }
