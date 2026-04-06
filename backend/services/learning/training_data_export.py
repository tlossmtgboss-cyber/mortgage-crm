"""
Training Data Export Job — Continual Learning (Domain 8)

Monthly job that exports approved agent runs as SFT-ready JSONL pairs for
downstream fine-tuning or evaluation.

Filters:
    - Only runs where output was used without subsequent correction (implicit
      positive signal).
    - Runs must have a successful status.
    - Optionally scoped to a single agent or all agents.

Output format (one JSON object per line):
    {"input": ..., "output": ..., "agent_id": ..., "quality_score": ...}
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, not_

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports
# ---------------------------------------------------------------------------

_models_loaded = False
_AgentExecution = None
_AgentContextEvent = None


def _ensure_models():
    global _models_loaded, _AgentExecution, _AgentContextEvent
    if _models_loaded:
        return
    from models.agent_governance import AgentExecution
    from database.models.agent_context import AgentContextEvent

    _AgentExecution = AgentExecution
    _AgentContextEvent = AgentContextEvent
    _models_loaded = True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_EXPORT_DIR = "/tmp/perennia_training_exports"
SUCCESS_STATUSES = {"completed", "success"}
MIN_QUALITY_SCORE = 0.5  # Skip runs below this inferred quality


# ---------------------------------------------------------------------------
# TrainingDataExportJob
# ---------------------------------------------------------------------------

class TrainingDataExportJob:
    """Monthly job that exports high-quality agent runs as SFT training data.

    Designed to run from a scheduler, management command, or API endpoint.
    Outputs a JSONL file with one training pair per line.
    """

    JOB_NAME = "training_data_export"

    def __init__(self, db: Session, export_dir: Optional[str] = None):
        self.db = db
        self.export_dir = export_dir or os.getenv(
            "TRAINING_EXPORT_DIR", DEFAULT_EXPORT_DIR
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def export(
        self,
        agent_id: Optional[str] = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        db: Optional[Session] = None,
    ) -> str:
        """Export approved runs as JSONL.

        Args:
            agent_id: Scope to a single agent (None = all agents).
            lookback_days: How far back to look for qualifying runs.
            db: Optional override session (uses self.db if None).

        Returns:
            Absolute path to the exported JSONL file.
        """
        session = db or self.db
        _ensure_models()

        # 1. Filter approved (uncorrected, successful) runs
        approved = await self._filter_approved_runs(agent_id, lookback_days, session)

        # 2. Transform into SFT pairs
        pairs = self._build_training_pairs(approved)

        # 3. Write JSONL
        file_path = self._write_jsonl(pairs, agent_id)

        logger.info(
            "Training export complete: %d pairs written to %s",
            len(pairs), file_path,
        )
        return file_path

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    async def _filter_approved_runs(
        self,
        agent_id: Optional[str],
        lookback_days: int,
        db: Session,
    ) -> list:
        """Return runs that were successful and NOT subsequently corrected.

        Logic:
            1. Fetch all successful executions in the lookback window.
            2. Fetch all correction events in the same window.
            3. Exclude any execution whose agent + time window overlaps
               a correction event (i.e., user corrected the output).
        """
        _ensure_models()
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # --- Successful executions ---
        exec_query = (
            db.query(_AgentExecution)
            .filter(
                and_(
                    _AgentExecution.created_at >= cutoff,
                    _AgentExecution.status.in_(SUCCESS_STATUSES),
                    _AgentExecution.success == True,  # noqa: E712
                )
            )
        )
        if agent_id:
            exec_query = exec_query.filter(
                _AgentExecution.agent_name == agent_id
            )

        executions = exec_query.order_by(_AgentExecution.created_at.asc()).all()

        if not executions:
            return []

        # --- Correction events in the same window ---
        correction_query = (
            db.query(
                _AgentContextEvent.agent_id,
                _AgentContextEvent.created_at,
            )
            .filter(
                and_(
                    _AgentContextEvent.event_type == "correction",
                    _AgentContextEvent.created_at >= cutoff,
                )
            )
        )
        if agent_id:
            correction_query = correction_query.filter(
                _AgentContextEvent.agent_id == agent_id
            )

        corrections = correction_query.all()

        # Build a set of (agent_name, correction_timestamp) for quick lookup.
        # An execution is "corrected" if a correction event for the same agent
        # was logged within 30 minutes after the execution completed.
        correction_window_minutes = 30
        corrected_keys: Set[str] = set()
        for agent_name, correction_ts in corrections:
            corrected_keys.add(f"{agent_name}::{correction_ts.isoformat()}")

        # Filter out executions that have a nearby correction
        approved = []
        for exc in executions:
            if self._was_corrected(exc, corrections, correction_window_minutes):
                continue
            approved.append(exc)

        logger.debug(
            "Filtered %d executions -> %d approved (no corrections)",
            len(executions), len(approved),
        )
        return approved

    @staticmethod
    def _was_corrected(
        execution, corrections: list, window_minutes: int
    ) -> bool:
        """Check whether a correction event exists close to this execution."""
        if not execution.completed_at and not execution.created_at:
            return False

        exec_time = execution.completed_at or execution.created_at
        agent_name = execution.agent_name

        for corr_agent, corr_ts in corrections:
            if corr_agent != agent_name:
                continue
            delta = (corr_ts - exec_time).total_seconds()
            # Correction must happen after the execution, within the window
            if 0 <= delta <= (window_minutes * 60):
                return True
        return False

    # ------------------------------------------------------------------
    # Pair construction
    # ------------------------------------------------------------------

    def _build_training_pairs(self, approved_runs: list) -> List[Dict[str, Any]]:
        """Convert approved executions into SFT-ready training pairs."""
        pairs: List[Dict[str, Any]] = []

        for run in approved_runs:
            input_data = self._extract_input(run)
            output_data = self._extract_output(run)

            if not input_data or not output_data:
                continue

            quality = self._compute_quality_score(run)
            if quality < MIN_QUALITY_SCORE:
                continue

            pairs.append({
                "input": input_data,
                "output": output_data,
                "agent_id": run.agent_name,
                "quality_score": round(quality, 4),
                "execution_id": str(run.execution_id),
                "created_at": (
                    run.created_at.isoformat() if run.created_at else None
                ),
            })

        return pairs

    @staticmethod
    def _extract_input(run) -> Optional[dict]:
        """Build the input portion of a training pair."""
        input_text = run.input_text
        input_data = run.input_data or {}

        if input_text:
            return {"text": input_text, "data": input_data}
        elif input_data:
            return {"data": input_data}
        return None

    @staticmethod
    def _extract_output(run) -> Optional[dict]:
        """Build the output portion of a training pair."""
        output = run.output_data or {}
        if not output:
            return None
        return output

    @staticmethod
    def _compute_quality_score(run) -> float:
        """Heuristic quality score for a run.

        Factors:
            - success flag (baseline)
            - response time relative to average (lower = better)
            - presence of output confidence score
            - trajectory length (more steps = more complex, potentially noisier)
        """
        score = 0.5  # Base for successful runs

        # Confidence boost
        output = run.output_data or {}
        confidence = output.get("confidence")
        if confidence is not None and isinstance(confidence, (int, float)):
            score += 0.3 * min(confidence, 1.0)

        # Fast response bonus (under 2 seconds)
        if run.response_time_ms and run.response_time_ms < 2000:
            score += 0.1

        # Penalize very long trajectories (might be noisy)
        trajectory = run.trajectory or []
        if isinstance(trajectory, list) and len(trajectory) > 10:
            score -= 0.1

        return max(0.0, min(1.0, score))

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _write_jsonl(
        self, pairs: List[Dict[str, Any]], agent_id: Optional[str]
    ) -> str:
        """Write training pairs as JSONL to the export directory."""
        Path(self.export_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        scope = agent_id or "all_agents"
        filename = f"training_{scope}_{timestamp}.jsonl"
        file_path = os.path.join(self.export_dir, filename)

        with open(file_path, "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, default=str) + "\n")

        logger.info("Wrote %d training pairs to %s", len(pairs), file_path)
        return file_path

    # ------------------------------------------------------------------
    # Summary / stats
    # ------------------------------------------------------------------

    async def get_export_stats(
        self,
        agent_id: Optional[str] = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> dict:
        """Preview how many records would be exported without writing a file."""
        _ensure_models()
        approved = await self._filter_approved_runs(
            agent_id, lookback_days, self.db
        )
        pairs = self._build_training_pairs(approved)

        agent_breakdown: Dict[str, int] = {}
        for p in pairs:
            name = p.get("agent_id", "unknown")
            agent_breakdown[name] = agent_breakdown.get(name, 0) + 1

        avg_quality = (
            sum(p["quality_score"] for p in pairs) / len(pairs)
            if pairs else 0.0
        )

        return {
            "total_approved_runs": len(approved),
            "total_training_pairs": len(pairs),
            "average_quality_score": round(avg_quality, 4),
            "agent_breakdown": agent_breakdown,
            "lookback_days": lookback_days,
        }
