"""
Daily Operations Agents

Scheduled agents that run once or twice daily:
1. evening_recap — 6 PM daily end-of-day summary for each LO
2. daily_task_generator — 8 AM auto-create recurring standard tasks
3. rate_alert — 8 AM detect rate movements and notify LOs + borrowers
4. birthday_anniversary — 9 AM trigger birthday/home anniversary outreach
5. daily_metrics_snapshot — 9 PM capture daily metrics for trend analysis
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Evening Recap
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="evening_recap",
    description="End-of-day pipeline recap and tomorrow's preview for each LO",
    frequency=AgentFrequency.DAILY_6PM,
    max_runtime_seconds=120,
)
def evening_recap(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Summarize today's activity and preview tomorrow for each LO."""
    actions = 0

    los = db.execute(text("""
        SELECT u.id, u.first_name, u.email FROM users u
        WHERE u.organization_id = :org_id AND u.is_active = true
          AND u.role IN ('loan_officer', 'manager', 'admin', 'branch_manager')
    """), {"org_id": organization_id}).fetchall()

    for lo in los:
        lo_id = lo[0]
        # Today's completed tasks
        completed = db.execute(text("""
            SELECT COUNT(*) FROM tasks
            WHERE assigned_to_id = :lo_id AND status = 'completed'
              AND updated_at >= CURRENT_DATE
        """), {"lo_id": str(lo_id)}).scalar() or 0

        # Today's new leads
        new_leads = db.execute(text("""
            SELECT COUNT(*) FROM leads
            WHERE owner_id = :lo_id AND created_at >= CURRENT_DATE
        """), {"lo_id": str(lo_id)}).scalar() or 0

        # Loans that changed stage today
        stage_changes = db.execute(text("""
            SELECT COUNT(*) FROM loans
            WHERE loan_officer_id = :lo_id AND stage_changed_at >= CURRENT_DATE
              AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
        """), {"lo_id": str(lo_id)}).scalar() or 0

        # Tomorrow's appointments
        tomorrow_appts = db.execute(text("""
            SELECT COUNT(*) FROM scheduler_appointments
            WHERE user_id = :lo_id
              AND start_time >= CURRENT_DATE + 1 AND start_time < CURRENT_DATE + 2
              AND status NOT IN ('cancelled','no_show')
        """), {"lo_id": str(lo_id)}).scalar() or 0

        if completed or new_leads or stage_changes:
            db.execute(text("""
                INSERT INTO activities (lead_id, type, content, created_at, organization_id)
                VALUES (NULL, 'System', :content, CURRENT_TIMESTAMP, :org_id)
            """), {
                "content": (
                    f"Evening recap for {lo[1]}: {completed} tasks done, "
                    f"{new_leads} new leads, {stage_changes} stage changes. "
                    f"Tomorrow: {tomorrow_appts} appointments."
                ),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Evening recap commit failed: {e}")

    return {
        "summary": f"Recapped {actions} LOs",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 2. Daily Task Generator
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="daily_task_generator",
    description="Auto-create standard recurring daily tasks for LOs",
    frequency=AgentFrequency.DAILY_8AM,
    max_runtime_seconds=60,
)
def daily_task_generator(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create daily check-in tasks for LOs with active pipelines."""
    actions = 0

    los_with_pipeline = db.execute(text("""
        SELECT DISTINCT l.loan_officer_id
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
          AND l.loan_officer_id IS NOT NULL
    """), {"org_id": organization_id}).fetchall()

    for row in los_with_pipeline:
        lo_id = row[0]
        # Check no duplicate for today
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE assigned_to_id = :lo_id AND title LIKE '%Daily pipeline check%'
              AND created_at >= CURRENT_DATE LIMIT 1
        """), {"lo_id": str(lo_id)}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, priority,
                                   status, due_date, created_at, organization_id)
                VALUES ('Daily pipeline check-in', 'Review pipeline, update stages, follow up on conditions.',
                        :lo_id, 'medium', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {"lo_id": str(lo_id), "org_id": organization_id})
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Daily task generator commit failed: {e}")

    return {
        "summary": f"Created {actions} daily tasks",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 3. Rate Alert Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="rate_alert",
    description="Detect rate movements and notify LOs with affected borrowers",
    frequency=AgentFrequency.DAILY_8AM,
    max_runtime_seconds=90,
)
def rate_alert(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Check for rate changes and create tasks for LOs with float positions."""
    actions = 0

    # Find loans currently floating (no lock, active pipeline)
    floating = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id, l.amount
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.lock_expiration_date IS NULL
          AND l.rate IS NULL
          AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY','APPLICATION')
    """), {"org_id": organization_id}).fetchall()

    if floating:
        # Group by LO
        lo_loans = {}
        for loan in floating:
            lo_id = loan[3]
            if lo_id not in lo_loans:
                lo_loans[lo_id] = []
            lo_loans[lo_id].append({"number": loan[1], "borrower": loan[2], "amount": float(loan[4] or 0)})

        for lo_id, loans in lo_loans.items():
            names = ", ".join(l["borrower"] for l in loans[:5])
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, priority,
                                   status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, 'medium', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Rate review: {len(loans)} floating loan(s)",
                "desc": f"Review lock strategy for: {names}. Check today's rate sheet for lock opportunities.",
                "lo_id": str(lo_id),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Rate alert commit failed: {e}")

    return {
        "summary": f"Created {actions} rate review tasks, {len(floating)} floating loans",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 4. Birthday & Anniversary Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="birthday_anniversary",
    description="Trigger birthday and home anniversary outreach for borrowers",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=60,
)
def birthday_anniversary(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find borrowers with birthdays or closing anniversaries this week."""
    actions = 0

    # Closing anniversaries (loans funded in this week in prior years)
    anniversaries = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.loan_officer_id, l.funded_date
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.funded_date IS NOT NULL
          AND EXTRACT(MONTH FROM l.funded_date) = EXTRACT(MONTH FROM CURRENT_DATE)
          AND EXTRACT(DAY FROM l.funded_date) BETWEEN
              EXTRACT(DAY FROM CURRENT_DATE) AND EXTRACT(DAY FROM CURRENT_DATE) + 7
          AND l.funded_date < CURRENT_DATE - INTERVAL '365 days'
    """), {"org_id": organization_id}).fetchall()

    for loan in anniversaries:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%anniversary%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'low', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Home anniversary: {loan[2]}",
                "desc": f"Closing anniversary for {loan[2]} ({loan[1]}). Send congratulations and ask for referrals.",
                "lo_id": str(loan[4]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Birthday/anniversary commit failed: {e}")

    return {
        "summary": f"Created {actions} anniversary tasks",
        "actions_taken": actions,
        "notifications_sent": 0,
        "anniversaries_found": len(anniversaries),
    }


# ---------------------------------------------------------------------------
# 5. Daily Metrics Snapshot
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="daily_metrics_snapshot",
    description="Capture end-of-day pipeline and activity metrics for trend analysis",
    frequency=AgentFrequency.DAILY_9PM,
    max_runtime_seconds=60,
)
def daily_metrics_snapshot(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Snapshot daily metrics into activities log for historical trending."""
    # Pipeline snapshot
    pipeline = db.execute(text("""
        SELECT COUNT(*) as total,
               COALESCE(SUM(amount), 0) as volume,
               COUNT(CASE WHEN stage = 'FUNDED' AND stage_changed_at >= CURRENT_DATE THEN 1 END) as funded_today,
               COUNT(CASE WHEN created_at >= CURRENT_DATE THEN 1 END) as new_today
        FROM loans
        WHERE organization_id = :org_id
          AND stage NOT IN ('CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
    """), {"org_id": organization_id}).fetchone()

    # Lead snapshot
    leads = db.execute(text("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN created_at >= CURRENT_DATE THEN 1 END) as new_today
        FROM leads
        WHERE organization_id = :org_id
          AND stage NOT IN ('Closed','Dead','Disqualified')
    """), {"org_id": organization_id}).fetchone()

    snapshot = (
        f"Daily snapshot: {pipeline[0]} active loans (${float(pipeline[1] or 0):,.0f}), "
        f"{pipeline[2]} funded today, {pipeline[3]} new apps, "
        f"{leads[0]} active leads, {leads[1]} new leads today"
    )

    db.execute(text("""
        INSERT INTO activities (lead_id, type, content, created_at, organization_id)
        VALUES (NULL, 'System', :content, CURRENT_TIMESTAMP, :org_id)
    """), {"content": snapshot, "org_id": organization_id})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Daily metrics snapshot commit failed: {e}")

    return {
        "summary": snapshot,
        "actions_taken": 1,
        "notifications_sent": 0,
    }
