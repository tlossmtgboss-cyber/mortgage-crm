"""
Autonomous Task Executor — polls for due tasks and dispatches them to agents.

    executor = AutonomousTaskExecutor()
    await executor.start()   # in lifespan / startup
    await executor.stop()    # in shutdown
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import and_
from sqlalchemy.orm import Session

from database.models.autonomous_task import AutonomousTask, TaskExecution
from database.models.core import Organization
from db import SessionLocal

logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL = int(os.getenv("AUTONOMOUS_POLL_INTERVAL_SECONDS", "60"))
_MAX_CONCURRENT_TASKS = int(os.getenv("AUTONOMOUS_MAX_CONCURRENT", "4"))


class AutonomousTaskExecutor:
    """Central engine that polls for due autonomous tasks and executes them."""

    AGENT_REGISTRY: Dict[str, str] = {
        "lead_nurturing": "services.autonomous.lead_nurturing_agent.LeadNurturingAgent",
        "compliance_watchdog": "services.autonomous.compliance_watchdog.ComplianceWatchdogAgent",
        "pipeline_monitor": "services.autonomous.pipeline_monitor.PipelineMonitorAgent",
        "document_followup": "services.autonomous.document_followup_agent.DocumentFollowupAgent",
        "rate_alert": "services.autonomous.rate_alert_agent.RateAlertAgent",
        "lead_scoring": "services.autonomous.lead_scoring_agent.LeadScoringAgent",
        "reporting": "services.autonomous.reporting_agent.ReportingAgent",
        "client_lifecycle": "services.autonomous.client_lifecycle_agent.ClientLifecycleAgent",
        "client_audit": "services.autonomous.client_audit_agent.ClientAuditAgent",
    }

    DEFAULT_TASKS: List[Dict[str, Any]] = [
        {"agent_type": "lead_nurturing", "task_name": "Daily Lead Nurturing",
         "schedule_cron": "0 9 * * 1-5", "config": {"days_threshold": 7}},
        {"agent_type": "compliance_watchdog", "task_name": "Compliance Check",
         "schedule_cron": "0 7 * * *", "config": {}},
        {"agent_type": "pipeline_monitor", "task_name": "Pipeline Health Check",
         "schedule_cron": "0 8 * * 1-5", "config": {}},
        {"agent_type": "document_followup", "task_name": "Document Follow-up",
         "schedule_cron": "0 10 * * 1-5", "config": {}},
        {"agent_type": "rate_alert", "task_name": "Rate Monitoring",
         "schedule_interval_minutes": 240, "config": {}},
        {"agent_type": "lead_scoring", "task_name": "Lead Scoring",
         "schedule_cron": "0 6 * * *", "config": {}},
        {"agent_type": "reporting", "task_name": "Morning Briefing",
         "schedule_cron": "0 7 * * 1-5", "config": {}},
        {"agent_type": "client_lifecycle", "task_name": "Client Lifecycle",
         "schedule_cron": "0 10 * * 1", "config": {}},
        {"agent_type": "client_audit", "task_name": "Daily Client Audit",
         "schedule_cron": "0 7 * * *", "config": {}},
    ]

    # ------------------------------------------------------------------ init

    def __init__(
        self,
        poll_interval: int = _DEFAULT_POLL_INTERVAL,
        max_concurrent: int = _MAX_CONCURRENT_TASKS,
    ) -> None:
        self._poll_interval = poll_interval
        self._max_concurrent = max_concurrent
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._agent_class_cache: Dict[str, Type] = {}

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            logger.warning("AutonomousTaskExecutor already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="autonomous-executor")
        logger.info("AutonomousTaskExecutor started (poll=%ds, concurrency=%d)",
                     self._poll_interval, self._max_concurrent)

    async def stop(self) -> None:
        """Gracefully stop, waiting up to 10s for in-flight work."""
        if not self._running:
            return
        self._running = False
        logger.info("AutonomousTaskExecutor stopping...")
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        logger.info("AutonomousTaskExecutor stopped")

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self.poll_and_execute()
            except Exception as e:
                logger.exception("Poll cycle failed: %s", e)
            for _ in range(self._poll_interval):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def poll_and_execute(self) -> int:
        """Find due tasks and execute them. Returns count executed."""
        due_tasks = self._get_due_tasks()
        if not due_tasks:
            return 0
        logger.info("Found %d due autonomous task(s)", len(due_tasks))
        coros = [self._run_guarded(t) for t in due_tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)
        executed = 0
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error("Task %s unhandled: %s", due_tasks[i].id, res)
            else:
                executed += 1
        return executed

    async def _run_guarded(self, task: AutonomousTask) -> None:
        async with self._semaphore:
            await self._execute_task(task)

    def _get_due_tasks(self) -> List[AutonomousTask]:
        """Query enabled tasks whose next_run_at <= now, ordered by priority."""
        db: Session = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            tasks = (
                db.query(AutonomousTask)
                .join(Organization, Organization.id == AutonomousTask.organization_id)
                .filter(and_(
                    AutonomousTask.is_enabled.is_(True),
                    AutonomousTask.next_run_at <= now,
                    Organization.is_active.is_(True),
                ))
                .order_by(AutonomousTask.priority.asc(), AutonomousTask.next_run_at.asc())
                .all()
            )
            # Touch attributes so they survive session close (detached state)
            for t in tasks:
                _ = (t.id, t.agent_type, t.organization_id, t.config,
                     t.timeout_seconds, t.max_retries, t.consecutive_failures,
                     t.schedule_cron, t.schedule_interval_minutes, t.task_name)
            return tasks
        except Exception as e:
            logger.exception("Failed to query due tasks: %s", e)
            return []
        finally:
            db.close()

    async def _execute_task(self, task: AutonomousTask) -> None:
        """Run a single autonomous task with timeout and error handling."""
        task_id, org_id, agent_type = task.id, task.organization_id, task.agent_type
        timeout = task.timeout_seconds or 300
        logger.info("Executing task %d [%s] org=%d timeout=%ds",
                     task_id, agent_type, org_id, timeout)

        t0 = time.monotonic()
        result: Dict[str, Any] = {}
        errors: List[str] = []
        status = "completed"

        try:
            agent_cls = self._resolve_agent_class(agent_type)
            if agent_cls is None:
                raise ValueError(f"Unknown agent_type: {agent_type!r}")
            from db import get_db_with_tenant
            with get_db_with_tenant(org_id) as db:
                agent = agent_cls(db=db, org_id=org_id, config=task.config or {})
                result = await asyncio.wait_for(agent.run(), timeout=timeout)
                db.commit()
        except asyncio.TimeoutError:
            status = "timeout"
            errors.append(f"Timed out after {timeout}s")
            logger.warning("Task %d [%s] timed out after %ds", task_id, agent_type, timeout)
        except Exception as e:
            status = "failed"
            errors.append(f"{type(e).__name__}: {str(e)[:500]}")
            logger.exception("Task %d [%s] failed: %s", task_id, agent_type, e)

        duration = round(time.monotonic() - t0, 2)
        try:
            self._record_execution(task_id, org_id, status, result, duration, errors)
            self._update_task_after_run(task_id, status, errors)
        except Exception as e:
            logger.exception("Failed to record execution for task %d: %s", task_id, e)

    def _resolve_agent_class(self, agent_type: str) -> Optional[Type]:
        """Lazily import and cache the agent class for *agent_type*."""
        if agent_type in self._agent_class_cache:
            return self._agent_class_cache[agent_type]
        dotted_path = self.AGENT_REGISTRY.get(agent_type)
        if not dotted_path:
            logger.error("No registry entry for agent_type=%r", agent_type)
            return None
        module_path, class_name = dotted_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            self._agent_class_cache[agent_type] = cls
            return cls
        except (ImportError, AttributeError) as e:
            logger.exception("Failed to resolve agent %r (%s): %s", agent_type, dotted_path, e)
            return None

    @staticmethod
    def _calculate_next_run(task: AutonomousTask) -> datetime:
        """Compute next run time from interval or cron expression."""
        now = datetime.now(timezone.utc)
        if task.schedule_interval_minutes:
            return now + timedelta(minutes=task.schedule_interval_minutes)
        if task.schedule_cron:
            try:
                return _next_cron_time(task.schedule_cron, now)
            except Exception as e:
                logger.warning("Cron parse failed for task %s (%r): %s",
                               task.id, task.schedule_cron, e)
        return now + timedelta(hours=24)

    def _record_execution(
        self, task_id: int, org_id: int, status: str,
        result: Dict[str, Any], duration: float, errors: List[str],
    ) -> None:
        """Write a TaskExecution row and update confidence graduation."""
        db: Session = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            execution = TaskExecution(
                task_id=task_id, organization_id=org_id, status=status,
                started_at=now - timedelta(seconds=duration), completed_at=now,
                duration_seconds=duration,
                items_processed=(result.get("leads_evaluated")
                                 or result.get("items_processed")
                                 or result.get("loans_evaluated", 0)),
                items_acted_on=(result.get("leads_contacted")
                                or result.get("items_acted_on")
                                or result.get("alerts_sent", 0)),
                actions_taken=result.get("actions"),
                result_summary=_build_summary(result, status),
                errors=errors if errors else None,
                metrics=result.get("metrics"), trigger="scheduled",
            )
            db.add(execution)
            db.commit()

            # Update confidence graduation for any auto-executed actions
            self._update_confidence_for_execution(db, org_id, execution.id, status)
        except Exception as e:
            db.rollback()
            logger.exception("Failed to write TaskExecution for task %d: %s", task_id, e)
        finally:
            db.close()

    @staticmethod
    def _update_confidence_for_execution(
        db: Session, org_id: int, execution_id: int, status: str,
    ) -> None:
        """Record auto-execution outcomes in the confidence graduation system."""
        try:
            from database.models.autonomous_task import AgentAction
            from services.autonomous.confidence_graduation import ConfidenceGraduationService

            # Find auto-executed actions (requires_approval=False) from this execution
            auto_actions = (
                db.query(AgentAction)
                .filter(
                    AgentAction.execution_id == execution_id,
                    AgentAction.requires_approval.is_(False),
                )
                .all()
            )
            if not auto_actions:
                return

            service = ConfidenceGraduationService(db)
            for action in auto_actions:
                service.record_auto_execution(
                    org_id=org_id,
                    action_type=action.action_type,
                    success=(action.status == "completed"),
                )
            db.commit()
        except ImportError:
            pass  # Graduation models not yet created
        except Exception as e:
            logger.debug("Confidence update skipped: %s", e)

    def _update_task_after_run(self, task_id: int, status: str, errors: List[str]) -> None:
        """Update AutonomousTask bookkeeping after a run."""
        db: Session = SessionLocal()
        try:
            task = db.query(AutonomousTask).filter(AutonomousTask.id == task_id).first()
            if task is None:
                logger.warning("Task %d not found for post-run update", task_id)
                return
            now = datetime.now(timezone.utc)
            task.last_run_at = now
            task.last_run_status = status
            task.updated_at = now
            if status == "completed":
                task.consecutive_failures = 0
            else:
                self._handle_failure(task, errors)
            task.next_run_at = self._calculate_next_run(task)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.exception("Failed to update task %d post-run: %s", task_id, e)
        finally:
            db.close()

    @staticmethod
    def _handle_failure(task: AutonomousTask, errors: List[str]) -> None:
        """Increment consecutive failures; disable if max_retries exceeded."""
        task.consecutive_failures = (task.consecutive_failures or 0) + 1
        max_retries = task.max_retries or 3
        if task.consecutive_failures >= max_retries:
            task.is_enabled = False
            logger.warning(
                "Task %d [%s] disabled after %d failures (max=%d). Errors: %s",
                task.id, task.agent_type, task.consecutive_failures, max_retries,
                "; ".join(errors[:3]) if errors else "unknown")
        else:
            logger.info("Task %d [%s] failure %d/%d: %s", task.id, task.agent_type,
                        task.consecutive_failures, max_retries,
                        errors[0] if errors else "unknown")

    async def seed_default_tasks(self, org_id: int) -> List[int]:
        """Create default autonomous task configs for a new org. Idempotent."""
        db: Session = SessionLocal()
        created_ids: List[int] = []
        try:
            existing = {
                r[0] for r in db.query(AutonomousTask.agent_type)
                .filter(AutonomousTask.organization_id == org_id).all()
            }
            to_create = [d for d in self.DEFAULT_TASKS if d["agent_type"] not in existing]
            for dflt in to_create:
                t = AutonomousTask(
                    organization_id=org_id, agent_type=dflt["agent_type"],
                    task_name=dflt["task_name"],
                    schedule_cron=dflt.get("schedule_cron"),
                    schedule_interval_minutes=dflt.get("schedule_interval_minutes"),
                    config=dflt.get("config", {}),
                    is_enabled=True, priority=5, max_retries=3, timeout_seconds=300,
                )
                t.next_run_at = self._calculate_next_run(t)
                db.add(t)
            db.commit()
            if to_create:
                created_ids = [
                    r[0] for r in db.query(AutonomousTask.id).filter(
                        AutonomousTask.organization_id == org_id,
                        AutonomousTask.agent_type.in_([d["agent_type"] for d in to_create]),
                    ).all()
                ]
            logger.info("Seeded %d autonomous tasks for org %d (skipped %d existing)",
                        len(created_ids), org_id, len(existing))
        except Exception as e:
            db.rollback()
            logger.exception("Failed to seed tasks for org %d: %s", org_id, e)
        finally:
            db.close()
        return created_ids


# ---------------------------------------------------------------------------
# Cron parsing
# ---------------------------------------------------------------------------

def _next_cron_time(expr: str, after: datetime) -> datetime:
    """Next datetime matching cron *expr* after *after*.
    Uses croniter if installed, otherwise brute-force minute walk.
    """
    try:
        from croniter import croniter  # type: ignore[import-untyped]
        return croniter(expr, after).get_next(datetime).replace(tzinfo=timezone.utc)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("croniter failed for %r: %s", expr, e)
    return _brute_force_next_cron(expr, after)


def _brute_force_next_cron(expr: str, after: datetime) -> datetime:
    """Walk minute-by-minute (up to 8 days). Supports *, int, ranges, lists."""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Cron must have 5 fields, got {len(parts)}: {expr!r}")
    matchers = [_parse_cron_field(parts[i], i) for i in range(5)]
    candidate = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    limit = after + timedelta(days=8)
    while candidate < limit:
        if (candidate.minute in matchers[0] and candidate.hour in matchers[1]
                and candidate.day in matchers[2] and candidate.month in matchers[3]
                and candidate.isoweekday() % 7 in matchers[4]):
            return candidate.replace(tzinfo=timezone.utc) if candidate.tzinfo is None else candidate
        candidate += timedelta(minutes=1)
    logger.warning("Cron fallback exhausted for %r", expr)
    return after + timedelta(hours=24)


def _parse_cron_field(field: str, index: int) -> set:
    """Parse one cron field into a set of valid integers."""
    full = [range(0, 60), range(0, 24), range(1, 32), range(1, 13), range(0, 7)]
    if field == "*":
        return set(full[index])
    result: set = set()
    for tok in field.split(","):
        tok = tok.strip()
        if "-" in tok:
            lo, hi = tok.split("-", 1)
            result.update(range(int(lo), int(hi) + 1))
        else:
            val = int(tok)
            if index == 4 and val == 7:
                val = 0
            result.add(val)
    return result


def _build_summary(result: Dict[str, Any], status: str) -> str:
    if status == "timeout":
        return "Task timed out before completing."
    if status == "failed":
        return "Task failed during execution."
    agent = result.get("agent", "unknown")
    processed = (result.get("leads_evaluated") or result.get("items_processed")
                 or result.get("loans_evaluated", 0))
    acted = (result.get("leads_contacted") or result.get("items_acted_on")
             or result.get("alerts_sent", 0))
    parts = [f"Agent: {agent}"]
    if processed:
        parts.append(f"processed={processed}")
    if acted:
        parts.append(f"acted_on={acted}")
    return ", ".join(parts)


# -- Module-level singleton --------------------------------------------------

_executor: Optional[AutonomousTaskExecutor] = None


def get_executor() -> AutonomousTaskExecutor:
    """Return (and lazily create) the module-level executor singleton."""
    global _executor
    if _executor is None:
        _executor = AutonomousTaskExecutor()
    return _executor
