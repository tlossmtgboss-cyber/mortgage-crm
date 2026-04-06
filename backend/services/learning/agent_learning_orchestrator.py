"""
Agent Learning Orchestrator — Continual Learning (Domain 8)

Top-level coordinator for all three continual-learning layers:

    Context Layer  — AgentMemoryConsolidationJob (nightly)
    Harness Layer  — HarnessOptimizationAgent   (weekly)
    Model Layer    — TrainingDataExportJob       (monthly)

Schedules:
    Nightly   — trigger memory consolidation for all active agents
    Weekly    — trigger harness optimization for agents with >50 runs
    Continuous— listen for agent_context_events, batch hot-path updates
                every 15 min
    Monthly   — generate training data export for Admin review
    Alert     — if any agent's correction rate exceeds 20 % in a 7-day
                window, raise an immediate review alert

Designed to be invoked by APScheduler, a cron trigger, or an API endpoint.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports
# ---------------------------------------------------------------------------

_models_loaded = False
_AgentExecution = None
_AgentProfile = None
_AgentAlert = None
_AgentContextEvent = None


def _ensure_models():
    global _models_loaded, _AgentExecution, _AgentProfile, _AgentAlert, _AgentContextEvent
    if _models_loaded:
        return
    from models.agent_governance import AgentExecution, AgentProfile, AgentAlert
    from database.models.agent_context import AgentContextEvent

    _AgentExecution = AgentExecution
    _AgentProfile = AgentProfile
    _AgentAlert = AgentAlert
    _AgentContextEvent = AgentContextEvent
    _models_loaded = True


# ---------------------------------------------------------------------------
# AgentLearningOrchestrator
# ---------------------------------------------------------------------------

class AgentLearningOrchestrator:
    """Top-level coordinator for all three learning layers.

    Provides named entry points (``run_nightly``, ``run_weekly``, etc.)
    that a scheduler or management command can call.
    """

    CORRECTION_RATE_ALERT_THRESHOLD = 0.20
    BATCH_INTERVAL_MINUTES = 15
    MIN_RUNS_FOR_OPTIMIZATION = 50
    LOOKBACK_DAYS_WEEKLY = 7
    LOOKBACK_DAYS_MONTHLY = 30

    def __init__(self, db: Session):
        self.db = db

    # ==================================================================
    # NIGHTLY — Memory consolidation
    # ==================================================================

    async def run_nightly(self, db: Optional[Session] = None) -> dict:
        """Trigger AgentMemoryConsolidationJob for all active agents.

        Runs at ~02:00 UTC.  Returns a summary of consolidated agents
        and any errors.
        """
        session = db or self.db
        started = datetime.now(timezone.utc)
        summary: Dict[str, Any] = {
            "job": "nightly_consolidation",
            "started_at": started.isoformat(),
            "status": "running",
        }

        try:
            from services.learning.agent_memory_consolidation import (
                AgentMemoryConsolidationJob,
            )

            consolidator = AgentMemoryConsolidationJob(session)
            result = await consolidator.run()
            summary.update(result)
            summary["status"] = "completed"
        except Exception as e:
            logger.exception("Nightly consolidation failed")
            summary["status"] = "error"
            summary["error"] = str(e)

        # Also check correction rates (piggyback on nightly run)
        try:
            alerts = await self.check_correction_rates(session)
            summary["correction_alerts"] = len(alerts)
        except Exception as e:
            logger.exception("Correction-rate check failed during nightly run")
            summary["correction_check_error"] = str(e)

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Nightly orchestration complete: %s", summary.get("status"))
        return summary

    # ==================================================================
    # WEEKLY — Harness optimization
    # ==================================================================

    async def run_weekly(self, db: Optional[Session] = None) -> dict:
        """Trigger HarnessOptimizationAgent for agents with sufficient runs.

        Runs on Sundays at ~04:00 UTC.  Filters to agents with more than
        ``MIN_RUNS_FOR_OPTIMIZATION`` executions in the last 7 days.
        """
        session = db or self.db
        _ensure_models()
        started = datetime.now(timezone.utc)
        cutoff = started - timedelta(days=self.LOOKBACK_DAYS_WEEKLY)

        summary: Dict[str, Any] = {
            "job": "weekly_harness_optimization",
            "started_at": started.isoformat(),
            "agents_evaluated": 0,
            "proposals_submitted": 0,
            "skipped_low_volume": 0,
            "errors": [],
        }

        try:
            from services.learning.harness_optimization_agent import (
                HarnessOptimizationAgent,
            )

            optimizer = HarnessOptimizationAgent(session)

            # Find agents with enough recent executions
            candidates = self._find_optimization_candidates(session, cutoff)
            summary["agents_evaluated"] = len(candidates)

            for agent_name, run_count in candidates:
                if run_count < self.MIN_RUNS_FOR_OPTIMIZATION:
                    summary["skipped_low_volume"] += 1
                    continue

                try:
                    analysis = await optimizer.analyze_agent(
                        agent_name, lookback_days=self.LOOKBACK_DAYS_WEEKLY
                    )
                    proposal = await optimizer.generate_diff_proposal(
                        agent_name, analysis
                    )

                    if proposal.get("total_changes", 0) > 0:
                        await optimizer.submit_for_approval(agent_name, proposal)
                        summary["proposals_submitted"] += 1
                        logger.info(
                            "Submitted optimization proposal for %s "
                            "(%d changes, risk=%.0f)",
                            agent_name,
                            proposal["total_changes"],
                            proposal.get("risk_score", 0),
                        )
                except Exception as e:
                    logger.exception(
                        "Harness optimization failed for agent %s", agent_name
                    )
                    summary["errors"].append(
                        {"agent_name": agent_name, "error": str(e)}
                    )

        except Exception as e:
            logger.exception("Weekly harness optimization failed globally")
            summary["global_error"] = str(e)

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        summary["status"] = "completed" if not summary.get("global_error") else "error"
        logger.info(
            "Weekly orchestration complete: %d proposals from %d agents",
            summary["proposals_submitted"], summary["agents_evaluated"],
        )
        return summary

    # ==================================================================
    # CONTINUOUS — Hot-path event batching
    # ==================================================================

    async def process_event_batch(self, db: Optional[Session] = None) -> dict:
        """Process queued agent_context_events since the last batch.

        Called every ``BATCH_INTERVAL_MINUTES`` (default 15 min).
        Identifies high-priority corrections and applies immediate
        hot-path context updates.
        """
        session = db or self.db
        _ensure_models()
        batch_cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=self.BATCH_INTERVAL_MINUTES
        )

        summary: Dict[str, Any] = {
            "job": "event_batch_processing",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "events_processed": 0,
            "hot_path_updates": 0,
            "agents_affected": set(),
        }

        try:
            # Fetch unprocessed events in this batch window
            events = (
                session.query(_AgentContextEvent)
                .filter(_AgentContextEvent.created_at >= batch_cutoff)
                .order_by(_AgentContextEvent.created_at.asc())
                .all()
            )
            summary["events_processed"] = len(events)

            if not events:
                summary["status"] = "no_events"
                summary["agents_affected"] = []
                return summary

            # Group by agent
            by_agent: Dict[str, list] = {}
            for ev in events:
                agent = ev.agent_id or "unknown"
                by_agent.setdefault(agent, []).append(ev)
                summary["agents_affected"].add(agent)

            # For each agent, apply hot-path updates for corrections
            from services.learning.agent_memory_consolidation import (
                AgentMemoryConsolidationJob,
            )
            consolidator = AgentMemoryConsolidationJob(session)

            for agent_id, agent_events in by_agent.items():
                corrections = [
                    e for e in agent_events if e.event_type == "correction"
                ]
                if not corrections:
                    continue

                # Hot-path: write correction directly to context store
                for corr in corrections:
                    if corr.corrected_value is not None:
                        key = self._derive_context_key(corr)
                        await consolidator._upsert_context(
                            scope="agent",
                            scope_id=agent_id,
                            key=key,
                            value=corr.corrected_value,
                            source="hot_path",
                            confidence=0.85,  # Hot-path starts at moderate confidence
                        )
                        summary["hot_path_updates"] += 1

        except Exception as e:
            logger.exception("Event batch processing failed")
            summary["error"] = str(e)

        summary["agents_affected"] = list(summary["agents_affected"])
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        summary["status"] = summary.get("status", "completed")
        return summary

    # ==================================================================
    # MONTHLY — Training data export
    # ==================================================================

    async def run_monthly_export(self, db: Optional[Session] = None) -> dict:
        """Generate TrainingDataExport for Admin review.

        Runs on the 1st of each month.  Exports all approved runs from
        the past 30 days as SFT-ready JSONL.
        """
        session = db or self.db
        started = datetime.now(timezone.utc)
        summary: Dict[str, Any] = {
            "job": "monthly_training_export",
            "started_at": started.isoformat(),
        }

        try:
            from services.learning.training_data_export import (
                TrainingDataExportJob,
            )

            exporter = TrainingDataExportJob(session)

            # Preview stats first
            stats = await exporter.get_export_stats(
                lookback_days=self.LOOKBACK_DAYS_MONTHLY
            )
            summary["preview"] = stats

            # Run the export
            file_path = await exporter.export(
                lookback_days=self.LOOKBACK_DAYS_MONTHLY
            )
            summary["export_path"] = file_path
            summary["status"] = "completed"

        except Exception as e:
            logger.exception("Monthly training export failed")
            summary["status"] = "error"
            summary["error"] = str(e)

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Monthly export orchestration: %s", summary.get("status"))
        return summary

    # ==================================================================
    # ALERT — Correction-rate monitoring
    # ==================================================================

    async def check_correction_rates(
        self, db: Optional[Session] = None
    ) -> list:
        """Check if any agent's correction rate exceeds threshold.

        Returns a list of alerts created for agents in violation.
        """
        session = db or self.db
        _ensure_models()
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=self.LOOKBACK_DAYS_WEEKLY
        )

        # Get distinct agents with recent executions
        agents = (
            session.query(
                _AgentExecution.agent_name,
                func.count(_AgentExecution.id).label("run_count"),
            )
            .filter(_AgentExecution.created_at >= cutoff)
            .group_by(_AgentExecution.agent_name)
            .having(func.count(_AgentExecution.id) >= 10)  # Need enough data
            .all()
        )

        alerts_created: List[dict] = []

        for agent_name, run_count in agents:
            # Count corrections
            corrections = (
                session.query(func.count(_AgentContextEvent.id))
                .filter(
                    and_(
                        _AgentContextEvent.agent_id == agent_name,
                        _AgentContextEvent.event_type == "correction",
                        _AgentContextEvent.created_at >= cutoff,
                    )
                )
                .scalar()
            ) or 0

            rate = corrections / run_count if run_count > 0 else 0.0

            if rate >= self.CORRECTION_RATE_ALERT_THRESHOLD:
                alert_info = await self._alert_admin(agent_name, rate, session)
                alerts_created.append(alert_info)
                logger.warning(
                    "Agent %s correction rate %.1f%% exceeds threshold %.0f%%",
                    agent_name, rate * 100,
                    self.CORRECTION_RATE_ALERT_THRESHOLD * 100,
                )

        return alerts_created

    async def _alert_admin(
        self, agent_id: str, rate: float, db: Session
    ) -> dict:
        """Create a critical alert when correction rate exceeds threshold."""
        _ensure_models()

        # Find the agent profile FK
        profile = (
            db.query(_AgentProfile)
            .filter(_AgentProfile.agent_name == agent_id)
            .first()
        )

        alert = _AgentAlert(
            agent_id=profile.id if profile else 1,
            agent_name=profile.agent_name if profile else str(agent_id),
            alert_type="correction_rate_breach",
            severity="critical",
            title=f"High correction rate for {agent_id}: {rate:.1%}",
            message=(
                f"Agent {agent_id} has a {rate:.1%} correction rate over the "
                f"last {self.LOOKBACK_DAYS_WEEKLY} days, exceeding the "
                f"{self.CORRECTION_RATE_ALERT_THRESHOLD:.0%} threshold. "
                f"Immediate review recommended."
            ),
            details={
                "agent_id": agent_id,
                "correction_rate": round(rate, 4),
                "threshold": self.CORRECTION_RATE_ALERT_THRESHOLD,
                "lookback_days": self.LOOKBACK_DAYS_WEEKLY,
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "triggered_by": "agent_learning_orchestrator",
            },
            status="active",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        return {
            "alert_id": alert.id,
            "agent_id": agent_id,
            "correction_rate": round(rate, 4),
            "severity": "critical",
        }

    # ==================================================================
    # Full orchestration pass
    # ==================================================================

    async def run_full_cycle(self, db: Optional[Session] = None) -> dict:
        """Run all orchestration steps in sequence.

        Useful for testing or a manual "catch-up" invocation.
        """
        results: Dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        results["nightly"] = await self.run_nightly(db)
        results["event_batch"] = await self.process_event_batch(db)
        results["weekly"] = await self.run_weekly(db)
        results["monthly"] = await self.run_monthly_export(db)
        results["correction_alerts"] = await self.check_correction_rates(db)
        results["finished_at"] = datetime.now(timezone.utc).isoformat()

        return results

    # ==================================================================
    # Helpers
    # ==================================================================

    def _find_optimization_candidates(
        self, db: Session, cutoff: datetime
    ) -> List[tuple]:
        """Return (agent_name, run_count) for agents with recent executions."""
        _ensure_models()
        rows = (
            db.query(
                _AgentExecution.agent_name,
                func.count(_AgentExecution.id).label("run_count"),
            )
            .filter(_AgentExecution.created_at >= cutoff)
            .group_by(_AgentExecution.agent_name)
            .order_by(func.count(_AgentExecution.id).desc())
            .all()
        )
        return [(name, count) for name, count in rows]

    @staticmethod
    def _derive_context_key(event) -> str:
        """Best-effort context key from a correction event."""
        corrected = event.corrected_value
        original = event.original_output

        for payload in (corrected, original):
            if isinstance(payload, dict) and "context_key" in payload:
                return payload["context_key"]

        return f"correction_{event.event_type}_{event.agent_id}"
