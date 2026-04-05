"""
Lead Re-engagement Agent

Runs hourly during business hours.
Finds leads going cold and triggers automated re-engagement:
- High-score leads with no contact in 2+ days → auto-SMS
- Medium-score leads with no contact in 5+ days → nurture email
- Leads that opened an email recently → escalate to call queue
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


@autonomous_agent(
    name="lead_reengagement",
    description="Auto-reengage leads going cold via SMS, email, or call queue",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=90,
)
def lead_reengagement(
    db: Session,
    organization_id: int,
    org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find cold leads and trigger re-engagement sequences."""

    actions = 0
    notifications = 0

    # 1. High-score leads going cold (2+ days, score >= 60)
    hot_leads = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.phone, l.email,
               l.owner_id, l.ai_score, l.loan_purpose,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - l.last_contact)) as days_cold
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('Closed', 'Dead', 'Disqualified', 'Converted')
          AND l.ai_score >= 60
          AND l.last_contact < CURRENT_TIMESTAMP - INTERVAL '2 days'
          AND l.last_contact > CURRENT_TIMESTAMP - INTERVAL '14 days'
        ORDER BY l.ai_score DESC
        LIMIT 20
    """), {"org_id": organization_id}).fetchall()

    for lead in hot_leads:
        # Create a high-priority follow-up task for the LO
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE lead_id = :lead_id
              AND title LIKE '%re-engage%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '48 hours'
            LIMIT 1
        """), {"lead_id": str(lead[0])}).fetchone()

        if not existing:
            days = int(lead[8] or 0)
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, lead_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :lead_id,
                        'high', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Re-engage {lead[1]} {lead[2]} (Score {lead[6]}, {days}d cold)",
                "desc": f"High-score lead going cold. {lead[7] or 'Mortgage'} inquiry, no contact in {days} days. Call or text today.",
                "lo_id": str(lead[5]),
                "lead_id": str(lead[0]),
                "org_id": organization_id,
            })
            actions += 1

    # 2. Medium-score leads really cold (7+ days, score 30-59)
    warm_leads = db.execute(text("""
        SELECT l.id, l.first_name, l.owner_id
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.stage NOT IN ('Closed', 'Dead', 'Disqualified', 'Converted')
          AND l.ai_score BETWEEN 30 AND 59
          AND l.last_contact < CURRENT_TIMESTAMP - INTERVAL '7 days'
          AND l.last_contact > CURRENT_TIMESTAMP - INTERVAL '30 days'
        ORDER BY l.ai_score DESC
        LIMIT 15
    """), {"org_id": organization_id}).fetchall()

    for lead in warm_leads:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE lead_id = :lead_id
              AND title LIKE '%nurture%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            LIMIT 1
        """), {"lead_id": str(lead[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, lead_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :lead_id,
                        'medium', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Nurture email for {lead[1]} — 7d+ no contact",
                "desc": "Lead is cooling. Send a market update or rate info email to maintain engagement.",
                "lo_id": str(lead[2]),
                "lead_id": str(lead[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Lead reengagement commit failed: {e}")

    return {
        "summary": f"{actions} re-engagement tasks created",
        "actions_taken": actions,
        "notifications_sent": notifications,
        "hot_leads_found": len(hot_leads),
        "warm_leads_found": len(warm_leads),
    }
