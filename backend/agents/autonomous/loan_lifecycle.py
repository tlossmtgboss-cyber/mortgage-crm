"""
Loan Lifecycle Agents

Agents that manage the loan-to-close process:
1. condition_chase — Hourly, follow up on outstanding underwriting conditions
2. closing_countdown — Every 30 min, manage pre-closing checklists 7 days out
3. application_followup — Every 30 min, nudge incomplete applications
4. post_close_survey — Daily, send satisfaction survey 3 days after funding
5. credit_refresh — Daily, check if credit reports need 120-day refresh
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Condition Chase Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="condition_chase",
    description="Follow up on outstanding underwriting conditions",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=90,
)
def condition_chase(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create follow-up tasks for loans with outstanding conditions 3+ days old."""
    actions = 0

    # Loans in conditional approval or later with old conditions
    stale_conditions = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id, l.stage,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.stage_changed_at)) as days_in_stage
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage IN ('CONDITIONAL_APPROVAL', 'APPROVED', 'SUSPENDED')
          AND l.stage_changed_at < CURRENT_TIMESTAMP - INTERVAL '3 days'
    """), {"org_id": organization_id}).fetchall()

    for loan in stale_conditions:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%condition%chase%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '48 hours'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            days = int(loan[5] or 0)
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'high', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Chase conditions: {loan[2]} ({days}d in {loan[4]})",
                "desc": f"Loan {loan[1]} has been in {loan[4]} for {days} days. Follow up on outstanding conditions with borrower and UW.",
                "lo_id": str(loan[3]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Condition chase commit failed: {e}")

    return {
        "summary": f"{actions} condition chase tasks created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 2. Closing Countdown Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="closing_countdown",
    description="Manage pre-closing checklists for loans closing within 7 days",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=60,
)
def closing_countdown(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create closing prep tasks for loans with closing dates in 7 days."""
    actions = 0

    closing_soon = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.closing_date, (l.closing_date - CURRENT_DATE) as days_to_close
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.closing_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7
          AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
    """), {"org_id": organization_id}).fetchall()

    for loan in closing_soon:
        days_left = int(loan[5] or 0)
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%closing countdown%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        :priority, 'pending', :due, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Closing countdown: {loan[2]} in {days_left}d",
                "desc": f"Loan {loan[1]} closing {loan[4]}. Verify: CD sent, title clear, insurance bound, cashier's check amount confirmed, closing agent scheduled.",
                "lo_id": str(loan[3]),
                "loan_id": str(loan[0]),
                "priority": "critical" if days_left <= 2 else "high",
                "due": loan[4],
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Closing countdown commit failed: {e}")

    return {
        "summary": f"{actions} closing countdown tasks, {len(closing_soon)} loans closing soon",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 3. Application Follow-up Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="application_followup",
    description="Nudge incomplete or stalled applications",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=60,
)
def application_followup(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find applications stuck in APPLICATION stage for 48+ hours and nudge."""
    actions = 0

    stalled = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.loan_officer_id,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.created_at)) as days_old
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'APPLICATION'
          AND l.created_at < CURRENT_TIMESTAMP - INTERVAL '48 hours'
          AND l.created_at > CURRENT_TIMESTAMP - INTERVAL '14 days'
    """), {"org_id": organization_id}).fetchall()

    for loan in stalled:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%app follow%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '48 hours'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'high', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"App follow-up: {loan[2]} ({int(loan[5])}d stalled)",
                "desc": f"Loan {loan[1]} has been in APPLICATION for {int(loan[5])} days. Contact {loan[2]} to collect missing docs and advance.",
                "lo_id": str(loan[4]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Application followup commit failed: {e}")

    return {
        "summary": f"{actions} application follow-up tasks",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 4. Post-Close Survey Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="post_close_survey",
    description="Send satisfaction survey 3 days after loan funding",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=60,
)
def post_close_survey(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create survey tasks for recently funded loans."""
    actions = 0

    recently_funded = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.loan_officer_id, l.stage_changed_at
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.stage_changed_at BETWEEN CURRENT_DATE - 4 AND CURRENT_DATE - 2
    """), {"org_id": organization_id}).fetchall()

    for loan in recently_funded:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%survey%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'medium', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Send closing survey: {loan[2]}",
                "desc": f"Loan {loan[1]} funded {loan[5]}. Send satisfaction survey and request online review from {loan[2]}.",
                "lo_id": str(loan[4]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Post-close survey commit failed: {e}")

    return {
        "summary": f"{actions} survey tasks created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 5. Credit Refresh Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="credit_refresh",
    description="Check if credit reports need 120-day refresh",
    frequency=AgentFrequency.DAILY_8AM,
    max_runtime_seconds=60,
)
def credit_refresh(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find loans where credit report is approaching 120-day expiration."""
    actions = 0

    expiring_credit = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.credit_docs_expire_date,
               (l.credit_docs_expire_date - CURRENT_DATE) as days_remaining
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.credit_docs_expire_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 14
          AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
    """), {"org_id": organization_id}).fetchall()

    for loan in expiring_credit:
        days = int(loan[5] or 0)
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%credit refresh%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        :priority, 'pending', CURRENT_DATE + 3, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Credit refresh needed: {loan[2]} ({days}d remaining)",
                "desc": f"Credit report for {loan[2]} ({loan[1]}) expires {loan[4]}. Order refresh to avoid delays.",
                "lo_id": str(loan[3]),
                "loan_id": str(loan[0]),
                "priority": "critical" if days <= 3 else "high",
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Credit refresh commit failed: {e}")

    return {
        "summary": f"{actions} credit refresh tasks",
        "actions_taken": actions,
        "notifications_sent": 0,
    }
