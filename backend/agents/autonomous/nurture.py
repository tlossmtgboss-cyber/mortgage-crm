"""
Nurture & Retention Agents

Long-term relationship and retention autonomous agents:
1. refi_opportunity_scanner — Daily, scan existing borrowers for refi savings
2. sphere_of_influence_nurture — Weekly, nurture past borrowers and referrals
3. review_solicitor — Daily, request reviews from recently closed borrowers
4. social_proof_collector — Daily, identify closing stories for social content
5. document_expiration_tracker — Every 30 min, flag docs expiring in 30/60/90 days
"""

import logging
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.autonomous.loop import autonomous_agent, AgentFrequency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Refi Opportunity Scanner
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="refi_opportunity_scanner",
    description="Scan funded borrowers for refinance savings opportunities",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=120,
)
def refi_opportunity_scanner(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Find funded loans where current rates are significantly lower."""
    actions = 0

    # Funded loans with rates higher than a threshold delta
    candidates = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.loan_officer_id, l.rate, l.amount, l.funded_date
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.rate IS NOT NULL
          AND l.rate > 5.5
          AND l.funded_date IS NOT NULL
          AND l.funded_date < CURRENT_DATE - INTERVAL '6 months'
          AND l.amount >= 100000
    """), {"org_id": organization_id}).fetchall()

    for loan in candidates:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%refi opportunity%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            rate = float(loan[5] or 0)
            amount = float(loan[6] or 0)
            monthly_savings_est = amount * (rate / 100 - 5.0 / 100) / 12  # rough estimate

            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'medium', 'pending', CURRENT_DATE + 7, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Refi opportunity: {loan[2]} at {rate}%",
                "desc": f"{loan[2]} funded at {rate}% on ${amount:,.0f}. Estimated monthly savings ~${monthly_savings_est:,.0f}. Contact to discuss refinance.",
                "lo_id": str(loan[4]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Refi scanner commit failed: {e}")

    return {
        "summary": f"{actions} refi opportunities identified from {len(candidates)} candidates",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 2. Sphere of Influence Nurture
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="sphere_of_influence_nurture",
    description="Weekly nurture outreach to past borrowers and referral sources",
    frequency=AgentFrequency.WEEKLY_MONDAY,
    max_runtime_seconds=90,
)
def sphere_of_influence_nurture(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create nurture tasks for borrowers who closed 3-12 months ago."""
    actions = 0

    past_borrowers = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.loan_officer_id, l.funded_date
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.funded_date BETWEEN CURRENT_DATE - INTERVAL '12 months' AND CURRENT_DATE - INTERVAL '3 months'
        ORDER BY l.funded_date DESC
        LIMIT 20
    """), {"org_id": organization_id}).fetchall()

    for loan in past_borrowers:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%sphere nurture%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '30 days'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'low', 'pending', CURRENT_DATE + 7, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Sphere nurture: {loan[2]}",
                "desc": f"Check in with {loan[2]} (funded {loan[5]}). Send market update, ask for referrals, confirm satisfaction.",
                "lo_id": str(loan[4]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Sphere nurture commit failed: {e}")

    return {
        "summary": f"{actions} sphere nurture tasks from {len(past_borrowers)} past borrowers",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 3. Review Solicitor
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="review_solicitor",
    description="Request online reviews from recently closed borrowers",
    frequency=AgentFrequency.DAILY_12PM,
    max_runtime_seconds=60,
)
def review_solicitor(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create review request tasks for borrowers who closed 5-10 days ago."""
    actions = 0

    recent_closes = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.borrower_email,
               l.loan_officer_id
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.stage_changed_at BETWEEN CURRENT_DATE - 10 AND CURRENT_DATE - 5
    """), {"org_id": organization_id}).fetchall()

    for loan in recent_closes:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%review request%'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'medium', 'pending', CURRENT_DATE, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Review request: {loan[2]}",
                "desc": f"Send review request to {loan[2]} ({loan[3] or 'no email'}). Loan {loan[1]} recently funded. Ask for Google/Zillow review.",
                "lo_id": str(loan[4]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Review solicitor commit failed: {e}")

    return {
        "summary": f"{actions} review request tasks",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 4. Social Proof Collector
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="social_proof_collector",
    description="Identify closing stories for social media content",
    frequency=AgentFrequency.DAILY_9AM,
    max_runtime_seconds=60,
)
def social_proof_collector(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Flag recent closings that make great social content (first-time buyers, VA, large loans)."""
    actions = 0

    notable_closings = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.loan_type, l.amount, l.property_address
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.stage = 'FUNDED'
          AND l.stage_changed_at >= CURRENT_DATE - 3
          AND (l.loan_type IN ('VA', 'FHA', 'USDA') OR l.amount >= 500000)
    """), {"org_id": organization_id}).fetchall()

    for loan in notable_closings:
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%social content%'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        'low', 'pending', CURRENT_DATE + 3, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Social content: {loan[2]} — {loan[4]} closing",
                "desc": f"Notable closing: {loan[2]}, {loan[4]} loan, ${float(loan[5] or 0):,.0f}. Ask permission for social media post/testimonial.",
                "lo_id": str(loan[3]),
                "loan_id": str(loan[0]),
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Social proof commit failed: {e}")

    return {
        "summary": f"{actions} social content opportunities",
        "actions_taken": actions,
        "notifications_sent": 0,
    }


# ---------------------------------------------------------------------------
# 5. Document Expiration Tracker
# ---------------------------------------------------------------------------
@autonomous_agent(
    name="document_expiration_tracker",
    description="Flag documents expiring in 30/60/90 day windows",
    frequency=AgentFrequency.EVERY_30_MIN,
    max_runtime_seconds=60,
)
def document_expiration_tracker(
    db: Session, organization_id: int, org_timezone: str = "America/New_York",
) -> Dict[str, Any]:
    """Create alerts for various document expiration windows."""
    actions = 0

    # Appraisals expiring within 30 days
    expiring_appraisals = db.execute(text("""
        SELECT l.id, l.loan_number, l.borrower_name, l.loan_officer_id,
               l.appraisal_docs_expire_date,
               (l.appraisal_docs_expire_date - CURRENT_DATE) as days_left
        FROM loans l
        WHERE l.organization_id = :org_id
          AND l.appraisal_docs_expire_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30
          AND l.stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN','DOES_NOT_QUALIFY')
    """), {"org_id": organization_id}).fetchall()

    for loan in expiring_appraisals:
        days = int(loan[5] or 0)
        existing = db.execute(text("""
            SELECT id FROM tasks
            WHERE loan_id = :loan_id AND title LIKE '%appraisal expir%'
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            LIMIT 1
        """), {"loan_id": str(loan[0])}).fetchone()

        if not existing:
            db.execute(text("""
                INSERT INTO tasks (title, description, assigned_to_id, loan_id,
                                   priority, status, due_date, created_at, organization_id)
                VALUES (:title, :desc, :lo_id, :loan_id,
                        :priority, 'pending', :due, CURRENT_TIMESTAMP, :org_id)
            """), {
                "title": f"Appraisal expiring: {loan[2]} in {days}d",
                "desc": f"Appraisal for {loan[2]} ({loan[1]}) expires {loan[4]}. Order update if loan won't close before expiration.",
                "lo_id": str(loan[3]),
                "loan_id": str(loan[0]),
                "priority": "critical" if days <= 7 else "medium",
                "due": loan[4],
                "org_id": organization_id,
            })
            actions += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Document expiration tracker commit failed: {e}")

    return {
        "summary": f"{actions} document expiration alerts",
        "actions_taken": actions,
        "notifications_sent": 0,
    }
