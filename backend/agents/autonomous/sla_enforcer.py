"""
SLA Enforcer Agent

Runs every 30 minutes.
Monitors stage-to-stage transition times against SLA targets.
Escalates to managers when loans are critically behind.
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)

# Escalation thresholds: if a loan exceeds SLA by this multiplier, escalate to manager
ESCALATION_MULTIPLIER = 2.0

SLA_TARGETS_DAYS = {
    "APPLICATION": 3,
    "DISCLOSED": 7,
    "PROCESSING": 7,
    "SUBMITTED": 2,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 5,
    "CONDITIONAL_APPROVAL": 5,
    "APPROVED": 3,
    "CTC": 3,
    "CLEAR_TO_CLOSE": 3,
    "DOCS": 3,
    "DOCS_OUT": 5,
}


@autonomous_agent(
    name="sla_enforcer",
    description="Escalate loans critically behind SLA targets to managers",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=60,
)
def sla_enforcer(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find loans that have blown past SLA targets and escalate."""

    actions = 0

    # Find all active loans with their time in current stage
    loans = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.stage,
               l.loan_officer_id,
               CONCAT(u.first_name, ' ', u.last_name) as lo_name,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) as days_in_stage
        FROM loans l
        LEFT JOIN users u ON u.id = l.loan_officer_id
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY', 'NURTURE')
          AND l.stage_changed_at IS NOT NULL
    """), {"org_id": organization_id}).fetchall()

    escalated = 0
    for loan in loans:
        stage = loan[3]
        days = float(loan[6] or 0)
        sla = SLA_TARGETS_DAYS.get(stage)
        if not sla:
            continue

        escalation_threshold = sla * ESCALATION_MULTIPLIER
        if days < escalation_threshold:
            continue

        # Check if already escalated in the last 24h
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id
              AND title LIKE '%SLA escalation%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if existing:
            continue

        # Find the manager for this LO's branch/org
        manager = db.execute(text("""
            SELECT u.id FROM users u
            WHERE u.organization_id = :org_id
              AND u.role IN ('manager', 'branch_manager', 'admin')
              AND u.is_active = true
            ORDER BY
                CASE u.role WHEN 'branch_manager' THEN 1 WHEN 'manager' THEN 2 ELSE 3 END
            LIMIT 1
        """), {"org_id": organization_id}).fetchone()

        assigned_to = str(manager[0]) if manager else str(loan[4])

        db.execute(text("""
            INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                               priority, status, due_date, created_at, organization_id)
            VALUES (:title, :desc, :assigned, :loan_id,
                    'critical', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
        """), {
            "title": f"SLA escalation: {loan[2]} stuck {int(days)}d in {stage}",
            "desc": f"Loan {loan[1]} ({loan[2]}) has been in {stage} for {int(days)} days (SLA: {sla}d, threshold: {int(escalation_threshold)}d). LO: {loan[5]}. Requires management review.",
            "assigned": assigned_to,
            "loan_id": str(loan[0]),
            "org_id": organization_id,
        })
        escalated += 1
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"SLA enforcer commit failed: {e}")

    return {
        "summary": f"{escalated} loans escalated to management",
        "actions_taken": actions,
        "notifications_sent": 0,
        "loans_reviewed": len(loans),
        "escalations": escalated,
    }
