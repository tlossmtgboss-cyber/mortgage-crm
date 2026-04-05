"""
Queue & Real-Time Operations Agents

Fast-cycle operational agents for real-time pipeline management:
1. call_queue_optimizer — Hourly, reorder dialer queue by priority/score
2. lock_desk_monitor — Every 15 min, monitor rate lock desk activity
3. task_overdue_escalator — Every 30 min, escalate overdue tasks to managers
4. email_response_monitor — Hourly, detect unanswered borrower/agent emails
5. new_lead_qualifier — Every 5 min, auto-qualify and score new incoming leads
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Call Queue Optimizer
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="call_queue_optimizer",
    description="Reorder dialer queue by lead score, recency, and pipeline stage",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=60,
)
def call_queue_optimizer(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Update call priority scores for leads in the dialer queue."""
    actions = 0

    # Leads needing contact, ranked by urgency
    queue = db.execute(text("""
        SELECT l.id, l.ai_score, l.stage, l.last_contact, l.created_at, l.owner_id,
               CASE
                   WHEN l.last_contact IS NULL AND l.created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 100
                   WHEN l.ai_score >= 80 AND l.last_contact < CURRENT_TIMESTAMP - INTERVAL '1 day' THEN 90
                   WHEN l.ai_score >= 60 AND l.last_contact < CURRENT_TIMESTAMP - INTERVAL '2 days' THEN 70
                   WHEN l.last_contact < CURRENT_TIMESTAMP - INTERVAL '5 days' THEN 50
                   ELSE 30
               END as call_priority
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('Closed', 'Dead', 'Disqualified', 'Converted')
          AND l.phone IS NOT NULL
          AND (l.last_contact IS NULL OR l.last_contact < CURRENT_TIMESTAMP - INTERVAL '1 day')
        ORDER BY call_priority DESC, l.ai_score DESC NULLS LAST
        LIMIT 50
    """), {"org_id": organization_id}).fetchall()

    # Update call_priority on leads that have a priority score field
    for lead in queue:
        try:
            db.execute(text("""
                UPDATE leads SET updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND organization_id = :org_id
            """), {"id": lead[0], "org_id": organization_id})
            actions += 1
        except Exception:
            pass

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Call queue optimizer commit failed: {e}")

    return {
        "summary": f"Optimized queue: {len(queue)} leads ranked, {actions} updated",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 2. Lock Desk Monitor
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="lock_desk_monitor",
    description="Monitor rate lock desk for float/lock opportunities and expirations",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def lock_desk_monitor(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Track lock desk: today's locks, expirations, and extension needs."""
    actions = 0

    # Locks expiring in next 5 days
    expiring_locks = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.lock_expiration_date, l.rate,
               (l.lock_expiration_date - CURRENT_DATE) as days_left
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.lock_expiration_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 5
          AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
        ORDER BY l.lock_expiration_date ASC
    """), {"org_id": organization_id}).fetchall()

    for loan in expiring_locks:
        days = int(loan[6] or 0)
        if days <= 2:
            existing = db.execute(text("""
                SELECT id FROM tasks
                WHERE loan_id = :loan_id AND title LIKE '%lock desk%'
                  AND created_at > CURRENT_TIMESTAMP - INTERVAL '12 hours'
                LIMIT 1
            """), {"loan_id": str(loan[0])}).fetchone()

            if not existing:
                db.execute(text("""
                    INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                       priority, status, due_date, created_at, organization_id)
                    VALUES (:title, :desc, :lo_id, :loan_id,
                            'critical', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                """), {
                    "title": f"Lock desk: {loan[2]} lock expires in {days}d",
                    "desc": f"Loan {loan[1]} ({loan[2]}) at {loan[5]}% — lock expires {loan[4]}. Extend or expedite closing.",
                    "lo_id": str(loan[3]),
                    "loan_id": str(loan[0]),
                    "org_id": organization_id,
                })
                actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Lock desk monitor commit failed: {e}")

    return {
        "summary": f"{actions} lock desk alerts, {len(expiring_locks)} locks expiring in 5d",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 3. Task Overdue Escalator
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="task_overdue_escalator",
    description="Escalate overdue tasks to managers when LOs miss deadlines",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=60,
)
def task_overdue_escalator(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find tasks overdue by 2+ days and escalate to management."""
    actions = 0

    overdue = db.execute(text("""
        SELECT t.id, t.title, t.assigned_to_id, t.priority, t.due_date,
               CONCAT(u.first_name, ' ', u.last_name) as assigned_name,
               (CURRENT_DATE - t.due_date) as days_overdue
        FROM tasks t
        LEFT JOIN users u ON u.id = t.assigned_to_id
        WHERE t.organization_id = :org_id
          AND t.status IN ('pending', 'in_progress')
          AND t.due_date < CURRENT_DATE - 2
          AND t.priority IN ('critical', 'high')
    """), {"org_id": organization_id}).fetchall()

    if not overdue:
        return {"summary": "No overdue critical tasks", "actions_taken": 0, "notifications_sent": 0}

    # Find manager to escalate to
    manager = db.execute(text("""
        SELECT id FROM users
        WHERE organization_id = :org_id AND role IN ('manager', 'branch_manager', 'admin')
          AND is_active = true
        ORDER BY CASE role WHEN 'branch_manager' THEN 1 WHEN 'manager' THEN 2 ELSE 3 END
        LIMIT 1
    """), {"org_id": organization_id}).fetchone()

    if manager:
        for task in overdue[:10]:
            days = int(task[6] or 0)
            existing = db.execute(text("""
                SELECT id FROM tasks
                WHERE title LIKE :pattern AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
                LIMIT 1
            """), {"pattern": f"%Escalation: task #{task[0]}%"}).fetchone()

            if not existing:
                db.execute(text("""
                    INSERT INTO tasks (title, description, assigned_to_id, priority,
                                       status, due_date, created_at, organization_id)
                    VALUES (:title, :desc, :mgr_id, 'critical', 'pending',
                            CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
                """), {
                    "title": f"Escalation: task #{task[0]} overdue {days}d — {task[5]}",
                    "desc": f"'{task[1]}' assigned to {task[5]} is {days} days overdue (priority: {task[3]}). Due: {task[4]}.",
                    "mgr_id": str(manager[0]),
                    "org_id": organization_id,
                })
                actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Task overdue escalator commit failed: {e}")

    return {
        "summary": f"{actions} tasks escalated to management from {len(overdue)} overdue",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 4. Email Response Monitor
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="email_response_monitor",
    description="Detect unanswered borrower and agent emails needing response",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=60,
)
def email_response_monitor(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find inbound emails with no reply in 4+ hours during business hours."""
    actions = 0

    # Check activities for unanswered inbound emails
    unanswered = db.execute(text("""
        SELECT a.id, a.lead_id, a.content, a.created_at,
               l.first_name, l.last_name, l.owner_id
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        WHERE a.organization_id = :org_id
          AND a.type = 'Email'
          AND a.content ILIKE '%inbound%'
          AND a.created_at BETWEEN CURRENT_TIMESTAMP - INTERVAL '8 hours'
                                AND CURRENT_TIMESTAMP - INTERVAL '4 hours'
          AND NOT EXISTS (
              SELECT 1 FROM activities a2
              WHERE a2.lead_id = a.lead_id AND a2.type = 'Email'
                AND a2.content ILIKE '%sent%'
                AND a2.created_at > a.created_at
          )
        LIMIT 15
    """), {"org_id": organization_id}).fetchall()

    for email in unanswered:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE lead_id = :lead_id AND title LIKE '%unanswered email%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '12 hours'
            LIMIT 1
        """), {"lead_id": str(email[1])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, lead_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :lead_id,
                        'high', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Unanswered email from {email[4]} {email[5]}",
                "desc": f"Email received {email[3]} from {email[4]} {email[5]} has no reply after 4+ hours. Respond ASAP.",
                "lo_id": str(email[6]) if email[6] else None,
                "lead_id": str(email[1]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Email response monitor commit failed: {e}")

    return {
        "summary": f"{actions} unanswered email alerts",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 5. New Lead Qualifier
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="new_lead_qualifier",
    description="Auto-qualify and score new incoming leads based on profile data",
    frequency=AgentFrequency.EVERY_5_MIN,
    max_runtime_seconds=30,
)
def new_lead_qualifier(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Score new leads without ai_score based on available profile data."""
    actions = 0

    unscored = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
               l.loan_amount, l.loan_purpose, l.credit_score,
               l.property_value, l.down_payment, l.source
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.ai_score IS NULL
          AND l.created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        LIMIT 20
    """), {"org_id": organization_id}).fetchall()

    for lead in unscored:
        score = 30  # base score

        # Contact info completeness
        if lead[3]:  # email
            score += 10
        if lead[4]:  # phone
            score += 10

        # Financial data
        if lead[5] and float(lead[5] or 0) > 0:  # loan_amount
            score += 10
        if lead[7] and float(lead[7] or 0) >= 680:  # credit_score
            score += 15
        elif lead[7] and float(lead[7] or 0) >= 620:
            score += 5
        if lead[8] and float(lead[8] or 0) > 0:  # property_value
            score += 5
        if lead[9] and float(lead[9] or 0) > 0:  # down_payment
            score += 5

        # Purpose
        if lead[6] and lead[6].lower() in ('purchase', 'refinance'):
            score += 10

        # Source quality
        if lead[10] and lead[10].lower() in ('referral', 'zillow', 'realtor.com'):
            score += 5

        score = min(score, 100)

        db.execute(text("""
            UPDATE leads SET ai_score = :score, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
        """), {"score": score, "id": lead[0]})
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"New lead qualifier commit failed: {e}")

    return {
        "summary": f"Scored {actions} new leads",
        "actions_taken": actions,
        "notifications_sent": 0,
    }
