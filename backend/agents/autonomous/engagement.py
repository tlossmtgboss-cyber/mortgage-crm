"""
Engagement Agents

Real-time and frequent engagement-focused autonomous agents:
1. speed_to_lead — Every 2 min, ensure new leads contacted within 60s target
2. appointment_prep — Every 15 min, prep materials before appointments
3. borrower_status_updater — Hourly, proactive milestone updates to borrowers
4. referral_thank_you — Hourly, thank referral partners for new leads
5. drip_campaign_engine — Every 15 min, trigger next drip message in sequences
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Speed-to-Lead Enforcer
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="speed_to_lead",
    description="Ensure new leads get first contact attempt within 60 seconds",
    frequency=AgentFrequency.EVERY_2_MIN,
    max_runtime_seconds=30,
)
def speed_to_lead(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find leads created in last 5 min with no activity and create urgent tasks."""
    actions = 0

    untouched = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.phone, l.email, l.owner_id, l.source
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.created_at > CURRENT_TIMESTAMP - INTERVAL '5 minutes'
          AND l.last_contact IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM tasks t WHERE t.lead_id = l.id AND t.title LIKE '%Speed-to-lead%'
          )
          AND NOT EXISTS (
              SELECT 1 FROM activities a WHERE a.lead_id = l.id AND a.type IN ('Call', 'SMS', 'Email')
          )
    """), {"org_id": organization_id}).fetchall()

    for lead in untouched:
        db.execute(text("""
            INSERT INTO tasks (title, description, assigned_to_id, lead_id,
                               priority, status, due_date, created_at, organization_id)
            VALUES (:title, :desc, :lo_id, :lead_id,
                    'critical', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
        """), {
            "title": f"Speed-to-lead: Call {lead[1]} {lead[2]} NOW",
            "desc": f"New lead from {lead[6] or 'unknown source'}. Phone: {lead[3] or 'N/A'}, Email: {lead[4] or 'N/A'}. Contact within 60 seconds for best conversion.",
            "lo_id": str(lead[5]) if lead[5] else None,
            "lead_id": str(lead[0]),
            "org_id": organization_id,
        })
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Speed-to-lead commit failed: {e}")

    return {
        "summary": f"{actions} speed-to-lead alerts created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 2. Appointment Prep Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="appointment_prep",
    description="Send prep materials 2 hours before appointments",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=60,
)
def appointment_prep(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create prep tasks for appointments starting in the next 2 hours."""
    actions = 0

    upcoming = db.execute(text("""
        SELECT sa.id, sa.title, sa.start_time, sa.user_id, sa.lead_id,
               sa.appointment_type, l.first_name, l.last_name
        FROM scheduler_appointments sa
        LEFT JOIN leads l ON l.id = sa.lead_id
        WHERE sa.organization_id = :org_id
          AND sa.start_time BETWEEN CURRENT_TIMESTAMP + INTERVAL '90 minutes'
                                AND CURRENT_TIMESTAMP + INTERVAL '2 hours 15 minutes'
          AND sa.status NOT IN ('cancelled', 'no_show', 'completed')
    """), {"org_id": organization_id}).fetchall()

    for appt in upcoming:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE title LIKE :pattern AND created_at > CURRENT_TIMESTAMP - INTERVAL '3 hours'
            LIMIT 1
        """), {"pattern": f"%Prep for%{appt[0]}%"}).fetchone()

        if not existing:
            lead_name = f"{appt[6] or ''} {appt[7] or ''}".strip() or "borrower"
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, lead_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :lead_id,
                        'high', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Prep for appointment #{appt[0]} with {lead_name}",
                "desc": f"{appt[5] or 'Meeting'} at {appt[2]}. Review loan file, prepare documents, and check conditions.",
                "lo_id": str(appt[3]),
                "lead_id": str(appt[4]) if appt[4] else None,
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Appointment prep commit failed: {e}")

    return {
        "summary": f"{actions} prep tasks created for upcoming appointments",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 3. Borrower Status Updater
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="borrower_status_updater",
    description="Proactive status updates to borrowers on milestone changes",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=60,
)
def borrower_status_updater(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find loans that hit milestones in last hour and create notification tasks."""
    actions = 0

    MILESTONE_STAGES = ['DISCLOSED', 'SUBMITTED', 'CONDITIONAL_APPROVAL', 'APPROVED',
                        'CTC', 'CLEAR_TO_CLOSE', 'DOCS_OUT', 'FUNDED']

    milestones = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.loan_officer_id, l.stage
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage_changed_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
          AND l.stage = ANY(:stages)
    """), {"org_id": organization_id, "stages": MILESTONE_STAGES}).fetchall()

    for loan in milestones:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%borrower update%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '4 hours'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'medium', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Send borrower update: {loan[2]} reached {loan[5]}",
                "desc": f"Loan {loan[1]} for {loan[2]} hit {loan[5]}. Send status update email to {loan[3] or 'borrower'}.",
                "lo_id": str(loan[4]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Borrower status updater commit failed: {e}")

    return {
        "summary": f"{actions} borrower update tasks created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 4. Referral Thank-You Agent
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="referral_thank_you",
    description="Send thank-you tasks to LOs when referral partners send new leads",
    frequency=AgentFrequency.HOURLY,
    max_runtime_seconds=60,
)
def referral_thank_you(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create thank-you tasks for referral-sourced leads received today."""
    actions = 0

    referral_leads = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.source, l.owner_id, l.referral_source
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.created_at >= CURRENT_DATE
          AND (l.source ILIKE '%referral%' OR l.referral_source IS NOT NULL)
          AND NOT EXISTS (
              SELECT 1 FROM tasks t WHERE t.lead_id = l.id AND t.title LIKE '%Thank referral%'
          )
    """), {"org_id": organization_id}).fetchall()

    for lead in referral_leads:
        ref_source = lead[5] or lead[3] or "referral partner"
        db.execute(text("""
            INSERT INTO tasks (title, description, assigned_to_id, lead_id,
                               priority, status, due_date, created_at, organization_id)
            VALUES (:title, :desc, :lo_id, :lead_id,
                    'medium', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
        """), {
            "title": f"Thank referral partner for {lead[1]} {lead[2]}",
            "desc": f"New referral from {ref_source}. Send a thank-you and status update to maintain the relationship.",
            "lo_id": str(lead[4]) if lead[4] else None,
            "lead_id": str(lead[0]),
            "org_id": organization_id,
        })
        actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Referral thank-you commit failed: {e}")

    return {
        "summary": f"{actions} referral thank-you tasks created",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 5. Drip Campaign Engine
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="drip_campaign_engine",
    description="Trigger next drip messages for active sequences",
    frequency=AgentFrequency.EVERY_15_MIN,
    max_runtime_seconds=90,
)
def drip_campaign_engine(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Check for leads in nurture stage needing next drip touch."""
    actions = 0

    # Leads in nurture with no recent contact (3+ days)
    nurture_leads = db.execute(text("""
        SELECT l.id, l.first_name, l.last_name, l.email, l.phone,
               l.owner_id, l.stage, l.last_contact,
               EXTRACT(DAY FROM (CURRENT_TIMESTAMP - COALESCE(l.last_contact, l.created_at))) as days_since
        FROM leads l
        WHERE l.organization_id = :org_id
          AND l.stage IN ('Nurture', 'Follow Up', 'Contacted')
          AND COALESCE(l.last_contact, l.created_at) < CURRENT_TIMESTAMP - INTERVAL '3 days'
          AND COALESCE(l.last_contact, l.created_at) > CURRENT_TIMESTAMP - INTERVAL '90 days'
          AND l.email IS NOT NULL
        ORDER BY l.ai_score DESC NULLS LAST
        LIMIT 30
    """), {"org_id": organization_id}).fetchall()

    for lead in nurture_leads:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE lead_id = :lead_id AND title LIKE '%drip%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '3 days'
            LIMIT 1
        """), {"lead_id": str(lead[0])}).fetchone()

        if not existing:
            days = int(lead[8] or 0)
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, lead_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :lead_id,
                        'low', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Drip: Send nurture email to {lead[1]} ({days}d)",
                "desc": f"{lead[1]} {lead[2]} in {lead[6]} stage, {days} days since last contact. Send market update or rate info.",
                "lo_id": str(lead[5]) if lead[5] else None,
                "lead_id": str(lead[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Drip campaign commit failed: {e}")

    return {
        "summary": f"{actions} drip tasks created from {len(nurture_leads)} nurture leads",
        "actions_taken": actions,
        "notifications_sent": 0,
    }
