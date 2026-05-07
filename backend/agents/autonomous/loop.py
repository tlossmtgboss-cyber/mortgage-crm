"""
Autonomous Agent Loop — The heartbeat of Perennia AI

Provides infrastructure for scheduled agents that:
1. Wake up on a cron schedule
2. Analyze data (pipeline, leads, compliance, etc.)
3. Take action (create tasks, send notifications, update records)
4. Report results (email/SMS/in-app notification)

Each autonomous agent is a function registered with @autonomous_agent decorator.
The loop handles scheduling, error recovery, execution logging, and tenant isolation.
"""

import asyncio
import logging
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Cap concurrent agent executions to avoid exhausting Railway's ~20 DB connections.
# API requests, Aria voice tools, and scheduler tasks all share the same pool.
_MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "12"))
_agent_semaphore = threading.Semaphore(_MAX_CONCURRENT_AGENTS)


class AgentFrequency(str, Enum):
    """How often an autonomous agent runs."""
    EVERY_2_MIN = "every_2_min"
    EVERY_5_MIN = "every_5_min"
    EVERY_15_MIN = "every_15_min"
    EVERY_30_MIN = "every_30_min"
    HOURLY = "hourly"
    EVERY_2_HOURS = "every_2_hours"
    EVERY_4_HOURS = "every_4_hours"
    DAILY_6AM = "daily_6am"
    DAILY_7AM = "daily_7am"
    DAILY_8AM = "daily_8am"
    DAILY_9AM = "daily_9am"
    DAILY_12PM = "daily_12pm"
    DAILY_6PM = "daily_6pm"
    DAILY_9PM = "daily_9pm"
    WEEKLY_MONDAY = "weekly_monday"
    WEEKLY_FRIDAY = "weekly_friday"
    MONTHLY_FIRST = "monthly_first"


# Cron expressions for each frequency
FREQUENCY_CRON = {
    AgentFrequency.EVERY_2_MIN: {"minute": "*/2"},
    AgentFrequency.EVERY_5_MIN: {"minute": "*/5"},
    AgentFrequency.EVERY_15_MIN: {"minute": "*/15"},
    AgentFrequency.EVERY_30_MIN: {"minute": "*/30"},
    AgentFrequency.HOURLY: {"minute": "0"},
    AgentFrequency.EVERY_2_HOURS: {"minute": "0", "hour": "*/2"},
    AgentFrequency.EVERY_4_HOURS: {"minute": "0", "hour": "*/4"},
    AgentFrequency.DAILY_6AM: {"hour": "6", "minute": "5"},
    AgentFrequency.DAILY_7AM: {"hour": "7", "minute": "2"},
    AgentFrequency.DAILY_8AM: {"hour": "8", "minute": "7"},
    AgentFrequency.DAILY_9AM: {"hour": "9", "minute": "3"},
    AgentFrequency.DAILY_12PM: {"hour": "12", "minute": "0"},
    AgentFrequency.DAILY_6PM: {"hour": "18", "minute": "5"},
    AgentFrequency.DAILY_9PM: {"hour": "21", "minute": "0"},
    AgentFrequency.WEEKLY_MONDAY: {"day_of_week": "mon", "hour": "7", "minute": "0"},
    AgentFrequency.WEEKLY_FRIDAY: {"day_of_week": "fri", "hour": "16", "minute": "0"},
    AgentFrequency.MONTHLY_FIRST: {"day": "1", "hour": "7", "minute": "0"},
}


@dataclass
class AgentExecutionResult:
    """Result of an autonomous agent execution."""
    agent_name: str
    organization_id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    success: bool = False
    actions_taken: int = 0
    notifications_sent: int = 0
    error: Optional[str] = None
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return 0


@dataclass
class AutonomousAgentDef:
    """Definition of an autonomous agent."""
    name: str
    description: str
    frequency: AgentFrequency
    handler: Callable
    enabled: bool = True
    requires_feature_tier: Optional[str] = None  # "CORE", "PREMIUM", etc.
    max_runtime_seconds: int = 120
    notify_on_error: bool = True


# Global registry of autonomous agents
_agent_registry: Dict[str, AutonomousAgentDef] = {}


def autonomous_agent(
    name: str,
    description: str,
    frequency: AgentFrequency,
    enabled: bool = True,
    max_runtime_seconds: int = 120,
):
    """Decorator to register an autonomous agent."""
    def decorator(func: Callable) -> Callable:
        _agent_registry[name] = AutonomousAgentDef(
            name=name,
            description=description,
            frequency=frequency,
            handler=func,
            enabled=enabled,
            max_runtime_seconds=max_runtime_seconds,
        )
        logger.info(f"Registered autonomous agent: {name} ({frequency.value})")
        return func
    return decorator


def get_registry() -> Dict[str, AutonomousAgentDef]:
    """Get the autonomous agent registry."""
    return _agent_registry


def _get_active_organizations(db: Session) -> List[Dict[str, Any]]:
    """Get all active organizations for multi-tenant execution."""
    try:
        result = db.execute(text("""
            SELECT o.id, o.name
            FROM organizations o
            WHERE o.is_active = true
            ORDER BY o.id
        """))
        return [{"id": row[0], "name": row[1], "timezone": "America/New_York"} for row in result.fetchall()]
    except Exception as e:
        logger.error(f"Failed to fetch organizations: {e}")
        return []


def _log_execution(db: Session, result: AgentExecutionResult):
    """Log autonomous agent execution to the database."""
    try:
        db.execute(text("""
            INSERT INTO autonomous_agent_runs
                (agent_name, organization_id, started_at, completed_at,
                 success, actions_taken, notifications_sent, error, summary)
            VALUES
                (:agent_name, :org_id, :started_at, :completed_at,
                 :success, :actions_taken, :notifications_sent, :error, :summary)
        """), {
            "agent_name": result.agent_name,
            "org_id": result.organization_id,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "success": result.success,
            "actions_taken": result.actions_taken,
            "notifications_sent": result.notifications_sent,
            "error": result.error,
            "summary": result.summary[:2000] if result.summary else None,
        })
        db.commit()
    except Exception as e:
        logger.warning(f"Failed to log agent execution: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def run_agent_for_org(
    agent_def: AutonomousAgentDef,
    org: Dict[str, Any],
) -> AgentExecutionResult:
    """Execute an autonomous agent for a single organization.

    Creates a fresh DB session with tenant context set for RLS isolation.
    """
    from database import SessionLocal

    result = AgentExecutionResult(
        agent_name=agent_def.name,
        organization_id=org["id"],
        started_at=datetime.now(timezone.utc),
    )

    acquired = _agent_semaphore.acquire(timeout=30)
    if not acquired:
        result.success = False
        result.error = "Skipped: too many agents running concurrently"
        result.completed_at = datetime.now(timezone.utc)
        logger.warning(f"Agent {agent_def.name} skipped for org {org['id']}: semaphore timeout (max {_MAX_CONCURRENT_AGENTS} concurrent)")
        # Persist skipped runs so they appear in the audit table
        try:
            skip_db = SessionLocal()
            _log_execution(skip_db, result)
            skip_db.close()
        except Exception:
            pass
        return result

    db = SessionLocal()
    try:
        # Set RLS tenant context
        db.execute(text("SET app.current_tenant = :org_id"), {"org_id": str(org["id"])})

        # Execute the agent handler
        handler_result = agent_def.handler(db=db, organization_id=org["id"], org_timezone=org.get("timezone", "America/New_York"))

        if isinstance(handler_result, dict):
            result.actions_taken = handler_result.get("actions_taken", 0)
            result.notifications_sent = handler_result.get("notifications_sent", 0)
            result.summary = handler_result.get("summary", "")
            result.details = handler_result

        result.success = True
        result.completed_at = datetime.now(timezone.utc)

        # Log execution
        _log_execution(db, result)

    except Exception as e:
        result.success = False
        result.error = f"{type(e).__name__}: {str(e)}"
        result.completed_at = datetime.now(timezone.utc)
        logger.error(f"Agent {agent_def.name} failed for org {org['id']}: {e}")
        logger.debug(traceback.format_exc())

        try:
            db.rollback()
            _log_execution(db, result)
        except Exception:
            pass
    finally:
        db.close()
        _agent_semaphore.release()

    return result


def run_agent_all_orgs(agent_name: str) -> List[AgentExecutionResult]:
    """Run an autonomous agent across all active organizations.

    This is the function registered with APScheduler.
    """
    agent_def = _agent_registry.get(agent_name)
    if not agent_def:
        logger.error(f"Unknown autonomous agent: {agent_name}")
        return []

    if not agent_def.enabled:
        logger.debug(f"Skipping disabled agent: {agent_name}")
        return []

    from database import SessionLocal
    db = SessionLocal()
    try:
        orgs = _get_active_organizations(db)
    finally:
        db.close()

    if not orgs:
        logger.warning(f"No active organizations found for agent {agent_name}")
        return []

    logger.info(f"Running autonomous agent '{agent_name}' for {len(orgs)} organization(s)")
    start = time.time()

    results = []
    for org in orgs:
        result = run_agent_for_org(agent_def, org)
        results.append(result)
        if result.success:
            logger.info(
                f"  [{org['name']}] {agent_name}: {result.actions_taken} actions, "
                f"{result.notifications_sent} notifications ({result.duration_ms:.0f}ms)"
            )
        else:
            logger.error(f"  [{org['name']}] {agent_name} FAILED: {result.error}")

    elapsed = time.time() - start
    success_count = sum(1 for r in results if r.success)
    logger.info(
        f"Agent '{agent_name}' complete: {success_count}/{len(results)} orgs succeeded "
        f"({elapsed:.1f}s total)"
    )

    return results


def register_all_autonomous_agents(scheduler):
    """Register all autonomous agents with APScheduler.

    Called from startup_event in main.py.
    """
    from apscheduler.triggers.cron import CronTrigger

    # Import all agent modules to trigger @autonomous_agent registration
    # Original 5 agents (morning_briefing deleted as dead code — now uses MorningBriefingService)
    try:
        from agents.autonomous import pipeline_monitor  # noqa: F401
        from agents.autonomous import compliance_watchdog  # noqa: F401
        from agents.autonomous import lead_reengagement  # noqa: F401
        from agents.autonomous import sla_enforcer  # noqa: F401
    except ImportError as e:
        logger.warning(f"Core autonomous agents failed to import: {e}")

    # Fleet agents (40 additional agents across 8 modules)
    # Disabled by default — enable via ENABLE_FLEET_AGENTS=true when DB can handle the load
    if os.getenv("ENABLE_FLEET_AGENTS", "true").lower() == "true":
        try:
            from agents.autonomous import daily_ops  # noqa: F401  (5 agents)
            from agents.autonomous import engagement  # noqa: F401  (5 agents)
            from agents.autonomous import risk_compliance  # noqa: F401  (5 agents)
            from agents.autonomous import analytics  # noqa: F401  (5 agents)
            from agents.autonomous import loan_lifecycle  # noqa: F401  (5 agents)
            from agents.autonomous import infrastructure  # noqa: F401  (5 agents)
            from agents.autonomous import nurture  # noqa: F401  (5 agents)
            from agents.autonomous import queue_ops  # noqa: F401  (5 agents)
        except ImportError as e:
            logger.warning(f"Fleet autonomous agents failed to import: {e}")
    else:
        logger.info("Fleet agents disabled (ENABLE_FLEET_AGENTS != true). Only core 5 agents active.")

    registered = 0
    for name, agent_def in _agent_registry.items():
        if not agent_def.enabled:
            continue

        cron_kwargs = FREQUENCY_CRON.get(agent_def.frequency, {"hour": "7", "minute": "0"})
        trigger = CronTrigger(**cron_kwargs, timezone="America/New_York")

        scheduler.add_job(
            run_agent_all_orgs,
            trigger=trigger,
            args=[name],
            id=f"autonomous_{name}",
            name=f"Autonomous: {agent_def.description}",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=30,  # 30s grace — skip missed runs on restart to avoid connection burst
        )
        registered += 1
        logger.info(f"Scheduled autonomous agent: {name} ({agent_def.frequency.value})")

    logger.info(f"Registered {registered} autonomous agents with scheduler")
    return registered
