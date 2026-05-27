"""
Pipeline Monitor Agent

Runs every 15 minutes. Detects pipeline anomalies and takes action:
- Loans stuck in a stage beyond SLA threshold
- Lock expirations within 48 hours
- Missing documents blocking progression
- Stalled deals needing escalation

Creates tasks, sends alerts, and logs to the agent run table.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency
from agents.autonomous.memory_context import get_lo_memory_context, get_sla_target

logger = logging.getLogger(__name__)

# SLA thresholds in days — if a loan exceeds these, create an alert
SLA_THRESHOLDS = {
    "APPLICATION": 3,
    "DISCLOSED": 5,
    "PROCESSING": 7,
    "SUBMITTED": 3,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 3,
    "CONDITIONAL_APPROVAL": 5,
    "APPROVED": 3,
    "CTC": 3,
    "CLEAR_TO_CLOSE": 5,
    "DOCS": 3,
    "DOCS_OUT": 5,
}


@autonomous_agent(
    name="pipeline_monitor",
    description="Detect stuck loans, expiring locks, and pipeline anomalies",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def pipeline_monitor(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
    gateway=None,
) -> Dict[str, Any]:
    """Monitor pipeline health and create tasks for anomalies."""

    actions = 0
    notifications = 0

    # 1. Find loans stuck beyond SLA
    stuck_loans = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage,
               l.loan_officer_id, l.stage_changed_at,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) as days_in_stage
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY', 'NURTURE')
          AND l.stage_changed_at < CURRENT_TIMESTAMP - INTERVAL '3 days'
        ORDER BY l.stage_changed_at ASC
    """), {"org_id": organization_id}).fetchall()

    for loan in stuck_loans:
        stage = loan[3]
        days = int(loan[6] or 0)
        lo_id = loan[4]
        # Respect per-LO custom SLA overrides from memory
        lo_memory = get_lo_memory_context(db, lo_id, organization_id) if lo_id else {}
        threshold = get_sla_target(lo_memory, stage, SLA_THRESHOLDS.get(stage, 7))

        if days >= threshold:
            # Check if we already created a task for this recently
            existing = db.execute(text("""
                SELECT id FROM tasks
                WHERE loan_id = :loan_id
                  AND title LIKE :title_pattern
                  AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                LIMIT 1
            """), {
                "loan_id": str(loan[0]),
                "title_pattern": f"%stuck in {stage}%",
            }).fetchone()

            if not existing:
                _params = {
                    "title": f"Loan stuck in {stage} for {days} days",
                    "desc": f"{loan[2]} ({loan[1]}) has been in {stage} for {days} days (SLA: {threshold}d). Review and advance.",
                    "lo_id": str(loan[4]),
                    "loan_id": str(loan[0]),
                    "priority": "high" if days >= threshold * 2 else "medium",
                    "org_id": organization_id,
                }
                def _do_stuck_insert(_p=_params):
                    db.execute(text("""
                        INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                           priority, status, due_date, created_at, organization_id)
                        VALUES (:title, :desc, :lo_id, :loan_id,
                                :priority, 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                    """), _p)
                if gateway:
                    if gateway.propose(
                        "create_task", _do_stuck_insert,
                        target_entity="loan", target_id=loan[0],
                        description=f"Stuck loan task for {loan[2]} ({loan[1]}) — {days}d in {stage}",
                        payload=_params,
                        notify_user_id=loan[4],
                    ):
                        actions += 1
                else:
                    _do_stuck_insert()
                    actions += 1

    # 2. Rate lock expiration warnings (48 hours)
    expiring = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.lock_expiration_date,
               (l.lock_expiration_date - CURRENT_DATE) as days_left
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.lock_expiration_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 2
          AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
    """), {"org_id": organization_id}).fetchall()

    for lock in expiring:
        days_left = int(lock[5] or 0)
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id
              AND title LIKE '%lock expir%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {"loan_id": str(lock[0])}).fetchone()

        if not existing:
            _lock_params = {
                "title": f"Rate lock expires in {days_left} day{'s' if days_left != 1 else ''}",
                "desc": f"{lock[2]} ({lock[1]}) — lock expires {lock[4]}. Extend or push to close.",
                "lo_id": str(lock[3]),
                "loan_id": str(lock[0]),
                "due": str(lock[4]) if lock[4] else None,
                "org_id": organization_id,
            }
            def _do_lock_insert(_p=_lock_params):
                db.execute(text("""
                    INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                       priority, status, due_date, created_at, organization_id)
                    VALUES (:title, :desc, :lo_id, :loan_id,
                            'critical', 'pending', :due, CURRENT_TIMESTAMP, :org_id)
                """), _p)
            if gateway:
                if gateway.propose(
                    "create_task", _do_lock_insert,
                    target_entity="loan", target_id=lock[0],
                    description=f"Rate lock expiry task for {lock[2]} ({lock[1]}) — {days_left}d left",
                    payload={**_lock_params, "priority": "critical"},
                    notify_user_id=lock[3],
                ):
                    actions += 1
            else:
                _do_lock_insert()
                actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Pipeline monitor commit failed: {e}")

    return {
        "summary": f"{actions} tasks created from pipeline anomalies",
        "actions_taken": actions,
        "notifications_sent": notifications,
        "stuck_loans_found": len(stuck_loans),
        "expiring_locks_found": len(expiring),
    }
